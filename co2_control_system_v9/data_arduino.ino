#include <SoftwareSerial.h>
#include <LiquidCrystal_I2C.h>
#include <ctype.h>
#include <stdlib.h>

const char CONTROLLER_ID[]="DATA";
#define TxPin 2
#define RxPin 3
LiquidCrystal_I2C lcd(0x27,16,2);
SoftwareSerial GSSSerial(RxPin,TxPin);
byte readCO2[]={0xFE,0x44,0x00,0x08,0x02,0x9F,0x25};
char numericBuffer[12]; uint8_t numericIndex=0;
const int flowPin=A3;
const float CO2_MOLAR_MASS=44.01f, MOLAR_VOLUME_STP=22.414f, CO2_G_PER_SL=CO2_MOLAR_MASS/MOLAR_VOLUME_STP;
float latestPercent=0, latestFlow=0, totalG=0; bool valid=false, loggingActive=false, completedLog=false;
unsigned long lastCO2Ms=0,lastDisplayMs=0,lastSendMs=0,lastLiveMs=0,lastRequestMs=0,logStartMs=0;
const unsigned long DISPLAY_MS=250, SEND_MS=1000, LIVE_MS=1000, REQUEST_MS=1000;
char cmdBuf[50];byte cmdIdx=0;

void setup(){lcd.init();lcd.backlight();pinMode(flowPin,INPUT);Serial.begin(115200);GSSSerial.begin(38400);lastCO2Ms=millis();lastRequestMs=millis()-REQUEST_MS;Serial.println(F("READY,DATA"));}
void loop(){readPi();if(millis()-lastRequestMs>=REQUEST_MS){GSSSerial.write(readCO2,sizeof(readCO2));lastRequestMs=millis();}GSSSerial.listen();while(GSSSerial.available()){char c=GSSSerial.read();if(numericIndex<sizeof(numericBuffer)-1)numericBuffer[numericIndex++]=c;else numericIndex=0;if(numericIndex==7&&c=='\n')parseCO2();if(numericIndex>=7)numericIndex=0;}refreshDisplay();sendData();sendLiveData();}
float readFlow(){int raw=analogRead(flowPin)/2.1;return(raw/1023.0f)*5.0f;}
void parseCO2(){numericBuffer[numericIndex]=0;char*p=numericBuffer;while(*p&&!isdigit((unsigned char)*p))p++;if(!*p){numericIndex=0;return;}uint16_t v=(uint16_t)strtoul(p,NULL,10);latestPercent=v/10000.0f;latestFlow=readFlow();valid=true;unsigned long now=millis();float dt=(now-lastCO2Ms)/1000.0f;lastCO2Ms=now;if(loggingActive){float gps=latestPercent*(latestFlow/60.0f)*CO2_G_PER_SL;totalG+=gps*dt;}numericIndex=0;}
void refreshDisplay(){
  if(millis()-lastDisplayMs<DISPLAY_MS)return;
  lastDisplayMs=millis();
  if(!valid){lcd.setCursor(0,0);lcd.print("Waiting sensor  ");lcd.setCursor(0,1);lcd.print("No data yet     ");return;}
  lcd.setCursor(0,0);lcd.print("C:");lcd.print(latestPercent*100,2);lcd.print("% F:");lcd.print(latestFlow,2);lcd.print("  ");
  lcd.setCursor(0,1);
  if(loggingActive){lcd.print("T:");lcd.print(totalG,2);lcd.print("g ");lcd.print(totalG/CO2_MOLAR_MASS,3);lcd.print("m   ");}
  else if(completedLog){lcd.print("Total: ");lcd.print(totalG,2);lcd.print("g     ");}
  else {lcd.print("Waiting Desorb  ");}
}
void sendData(){if(!valid||!loggingActive||millis()-lastSendMs<SEND_MS)return;lastSendMs=millis();Serial.print(F("DATA,"));Serial.print(millis()-logStartMs);Serial.print(',');Serial.print(latestPercent*100,4);Serial.print(',');Serial.print(latestFlow,4);Serial.print(',');Serial.print(totalG,6);Serial.print(',');Serial.println(totalG/CO2_MOLAR_MASS,8);}
void sendLiveData(){if(!valid||loggingActive||millis()-lastLiveMs<LIVE_MS)return;lastLiveMs=millis();Serial.print(F("LIVE,"));Serial.print(latestPercent*100,4);Serial.print(',');Serial.println(latestFlow,4);}
void readPi(){while(Serial.available()){char c=Serial.read();if(c=='\n'){cmdBuf[cmdIdx]=0;processCmd(cmdBuf);cmdIdx=0;}else if(c!='\r'&&cmdIdx<49)cmdBuf[cmdIdx++]=c;}}
void processCmd(char*c){if(!strcmp(c,"IDENTIFY")){Serial.println(F("ID,DATA"));return;}if(!strcmp(c,"GET_STATUS")){sendStatus();return;}if(!strcmp(c,"START_LOG")){totalG=0;completedLog=false;logStartMs=millis();lastCO2Ms=millis();lastSendMs=millis()-SEND_MS;loggingActive=true;Serial.print(F("LOG_STARTED,"));Serial.println(logStartMs);return;}if(!strcmp(c,"STOP_LOG")){loggingActive=false;completedLog=true;Serial.println(F("OK,LOG_STOPPED"));return;}Serial.println(F("ERROR,UNKNOWN_COMMAND"));}
void sendStatus(){Serial.print(F("STATUS,DATA,"));Serial.print(valid?F("OK"):F("NO_DATA"));Serial.print(',');Serial.print(loggingActive?F("LOGGING"):F("IDLE"));Serial.print(',');if(valid)Serial.print(latestPercent*100,4);else Serial.print(F("NA"));Serial.print(',');Serial.print(latestFlow,4);Serial.print(',');Serial.print(totalG,6);Serial.print(',');Serial.println(totalG/CO2_MOLAR_MASS,8);}
