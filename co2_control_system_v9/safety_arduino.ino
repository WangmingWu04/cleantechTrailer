#include <max6675.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>

const char CONTROLLER_ID[]="SAFETY";
const int thermoDO=9,thermoCS=7,thermoCLK=3;
MAX6675 thermocouple(thermoCLK,thermoCS,thermoDO);
Adafruit_SHT31 sht30=Adafruit_SHT31();
const int pressurePin=A2,safetyTripPin=5;
float maxTemp=150.0,maxRH=30.0,pressureLimit=0.0;
unsigned long rhTripMs=300000UL,sensorLossMs=15000UL,pressureTripMs=300000UL;
float processTemp=NAN,inletTemp=NAN,inletRH=NAN,pressurePSIG=0;
bool shtOK=false,emergency=false;
enum Phase{PHASE_IDLE,PHASE_ADSORB,PHASE_EVACUATION,PHASE_DESORB}; Phase currentPhase=PHASE_IDLE;
bool maxValidEver=false,shtValidEver=false;
bool maxLoss=false,shtLoss=false,rhHigh=false,pressureHigh=false;
unsigned long maxLossStart=0,shtLossStart=0,rhStart=0,pressureStart=0,lastRead=0,lastStatus=0;
enum Reason{NONE,OVER_TEMP,HIGH_RH,MAX_LOST,SHT_LOST,HIGH_PRESSURE}; Reason reason=NONE;
char cmdBuf[60];byte cmdIdx=0;

void setup(){Serial.begin(115200);pinMode(safetyTripPin,OUTPUT);digitalWrite(safetyTripPin,HIGH);pinMode(pressurePin,INPUT);Wire.begin();shtOK=sht30.begin(0x44);unsigned long n=millis();maxLoss=true;shtLoss=true;maxLossStart=n;shtLossStart=n;delay(500);updateSensors();Serial.println(F("READY,SAFETY"));}
void loop(){readPi();updateSensors();checkSafety();updateTrip();if(millis()-lastStatus>=1000){lastStatus=millis();sendStatus();}}
void updateSensors(){if(lastRead&&millis()-lastRead<500)return;lastRead=millis();processTemp=thermocouple.readCelsius();updatePressure();if(!shtOK)shtOK=sht30.begin(0x44);if(shtOK){inletTemp=sht30.readTemperature();inletRH=sht30.readHumidity();if(isnan(inletRH))shtOK=false;}else{inletTemp=NAN;inletRH=NAN;}}
void updatePressure(){unsigned long t=0;for(int i=0;i<10;i++)t+=analogRead(pressurePin);float raw=t/10.0f;float v=raw*(5.0/1023.0);pressurePSIG=-14.7+((v-1.0)/4.0)*44.7;}
void checkSafety(){unsigned long now=millis();
  if(!isnan(processTemp)){maxValidEver=true;maxLoss=false;}else{if(!maxLoss){maxLoss=true;maxLossStart=now;}if(now-maxLossStart>=sensorLossMs&&!emergency)trip(MAX_LOST);}
  if(!isnan(inletRH)){shtValidEver=true;shtLoss=false;}else{if(!shtLoss){shtLoss=true;shtLossStart=now;}if(now-shtLossStart>=sensorLossMs&&!emergency)trip(SHT_LOST);}
  if(emergency)return;
  if(!isnan(processTemp)&&processTemp>maxTemp){trip(OVER_TEMP);return;}
  // Humidity trip only during ADSORPTION. Leaving Adsorption resets the timer.
  if(currentPhase==PHASE_ADSORB && !isnan(inletRH) && inletRH>maxRH){
    if(!rhHigh){rhHigh=true;rhStart=now;}
    if(now-rhStart>=rhTripMs){trip(HIGH_RH);return;}
  }else{rhHigh=false;rhStart=0;}
  // Pressure trip only during DESORPTION. Leaving Desorption resets the timer.
  if(currentPhase==PHASE_DESORB && pressurePSIG>=pressureLimit){
    if(!pressureHigh){pressureHigh=true;pressureStart=now;}
    if(now-pressureStart>=pressureTripMs){trip(HIGH_PRESSURE);return;}
  }else{pressureHigh=false;pressureStart=0;}
}
void trip(Reason r){emergency=true;reason=r;digitalWrite(safetyTripPin,HIGH);Serial.print(F("ALARM,"));Serial.println(reasonText());}
void updateTrip(){if(emergency||!maxValidEver||!shtValidEver)digitalWrite(safetyTripPin,HIGH);else digitalWrite(safetyTripPin,LOW);}
const char* reasonText(){switch(reason){case OVER_TEMP:return "OVER_TEMPERATURE";case HIGH_RH:return "HIGH_HUMIDITY";case MAX_LOST:return "MAX6675_SIGNAL_LOST";case SHT_LOST:return "SHT30_SIGNAL_LOST";case HIGH_PRESSURE:return "HIGH_PRESSURE_DESORB";default:return "NONE";}}
void resetError(){if(isnan(processTemp)){Serial.println(F("ERROR,MAX6675_NOT_REPORTING"));return;}if(isnan(inletRH)){Serial.println(F("ERROR,SHT30_NOT_REPORTING"));return;}if(processTemp>maxTemp){Serial.println(F("ERROR,TEMPERATURE_STILL_HIGH"));return;}if(currentPhase==PHASE_ADSORB&&inletRH>maxRH){Serial.println(F("ERROR,HUMIDITY_STILL_HIGH"));return;}if(currentPhase==PHASE_DESORB&&pressurePSIG>=pressureLimit){Serial.println(F("ERROR,PRESSURE_STILL_HIGH"));return;}emergency=false;reason=NONE;rhHigh=pressureHigh=maxLoss=shtLoss=false;maxValidEver=shtValidEver=true;digitalWrite(safetyTripPin,LOW);Serial.println(F("OK,SAFETY_RESET"));}
void readPi(){while(Serial.available()){char c=Serial.read();if(c=='\n'){cmdBuf[cmdIdx]=0;processCmd(cmdBuf);cmdIdx=0;}else if(c!='\r'&&cmdIdx<59)cmdBuf[cmdIdx++]=c;}}
void sendConfig(){Serial.print(F("CONFIG,SAFETY,"));Serial.print(maxTemp,2);Serial.print(',');Serial.print(maxRH,2);Serial.print(',');Serial.print(rhTripMs/1000UL);Serial.print(',');Serial.print(pressureLimit,2);Serial.print(',');Serial.print(pressureTripMs/1000UL);Serial.print(',');Serial.println(sensorLossMs/1000UL);}
void setSafety(char *data){
  char *a=strtok(data,",");char *b=strtok(NULL,",");char *c=strtok(NULL,",");char *d=strtok(NULL,",");char *e=strtok(NULL,",");char *f=strtok(NULL,",");char *extra=strtok(NULL,",");
  if(!a||!b||!c||!d||!e||!f||extra){Serial.println(F("ERROR,BAD_SAFETY_FORMAT"));return;}
  float nt=atof(a),nrh=atof(b),np=atof(d);unsigned long nrhs=strtoul(c,NULL,10),nps=strtoul(e,NULL,10),nloss=strtoul(f,NULL,10);
  if(nt<=0||nrh<0||nrh>100||nrhs==0||nps==0||nloss==0){Serial.println(F("ERROR,BAD_SAFETY_VALUE"));return;}
  maxTemp=nt;maxRH=nrh;rhTripMs=nrhs*1000UL;pressureLimit=np;pressureTripMs=nps*1000UL;sensorLossMs=nloss*1000UL;
  rhHigh=false;pressureHigh=false;rhStart=pressureStart=0;Serial.println(F("OK,SAFETY_SETTINGS"));sendConfig();
}
void processCmd(char*c){if(!strcmp(c,"IDENTIFY")){Serial.println(F("ID,SAFETY"));return;}if(!strcmp(c,"GET_STATUS")){sendStatus();return;}if(!strcmp(c,"GET_CONFIG")){sendConfig();return;}if(!strncmp(c,"SET_SAFETY,",11)){setSafety(c+11);return;}if(!strcmp(c,"RESET_ERROR")){resetError();return;}if(!strcmp(c,"PHASE,ADSORB")){currentPhase=PHASE_ADSORB;rhHigh=false;rhStart=0;pressureHigh=false;pressureStart=0;Serial.println(F("OK,PHASE,ADSORB"));return;}if(!strcmp(c,"PHASE,EVACUATION")){currentPhase=PHASE_EVACUATION;rhHigh=false;rhStart=0;pressureHigh=false;pressureStart=0;Serial.println(F("OK,PHASE,EVACUATION"));return;}if(!strcmp(c,"PHASE,DESORB")){currentPhase=PHASE_DESORB;rhHigh=false;rhStart=0;pressureHigh=false;pressureStart=0;Serial.println(F("OK,PHASE,DESORB"));return;}if(!strcmp(c,"PHASE,IDLE")){currentPhase=PHASE_IDLE;rhHigh=false;rhStart=0;pressureHigh=false;pressureStart=0;Serial.println(F("OK,PHASE,IDLE"));return;}Serial.println(F("ERROR,UNKNOWN_COMMAND"));}
void sendStatus(){Serial.print(F("STATUS,SAFETY,"));if(emergency)Serial.print(reasonText());else if(!maxValidEver||!shtValidEver)Serial.print(F("NOT_READY"));else Serial.print(F("SAFE"));Serial.print(',');if(isnan(processTemp))Serial.print(F("ERR"));else Serial.print(processTemp,2);Serial.print(',');Serial.print(pressurePSIG,2);Serial.print(',');if(isnan(inletTemp))Serial.print(F("ERR"));else Serial.print(inletTemp,2);Serial.print(',');if(isnan(inletRH))Serial.print(F("ERR"));else Serial.print(inletRH,2);Serial.print(',');Serial.print(rhHigh?(millis()-rhStart)/1000UL:0);Serial.print(',');Serial.print(maxLoss?(millis()-maxLossStart)/1000UL:0);Serial.print(',');Serial.print(shtLoss?(millis()-shtLossStart)/1000UL:0);Serial.print(',');Serial.print(pressureHigh?(millis()-pressureStart)/1000UL:0);Serial.print(F(",PHASE="));Serial.print(phaseText());Serial.print(F(",TRIP="));Serial.println(digitalRead(safetyTripPin));}

const char* phaseText(){switch(currentPhase){case PHASE_ADSORB:return "ADSORB";case PHASE_EVACUATION:return "EVACUATION";case PHASE_DESORB:return "DESORB";default:return "IDLE";}}
