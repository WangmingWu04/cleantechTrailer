#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);
const char CONTROLLER_ID[] = "CONTROL";

// Outputs
const int bellowsEvac = 8;
const int stateChange = 9;
const int adsorbPin = 4;
const int desorbPin = 5;
const int bellowsTank = 6;
const int vacuumPin = 14;

// Inputs
const int onoffPin = 10;       // physical master enable, HIGH = enabled
const int safetyInputPin = A1; // Safety Arduino D5, HIGH = safety trip/not ready

// Normal cycle
unsigned long adsorbTimeS = 14400UL;
unsigned long evacuationTimeS = 55UL;
unsigned long desorbTimeS = 3300UL;
const unsigned long MAX_STATE_TIME_S = 172800UL;

enum Mode { MODE_AUTO, MODE_MANUAL };
enum CycleState { ADSORB, EVACUATION, DESORB };
enum SpecialState { SPECIAL_NONE, SHUTDOWN_EVAC, EMERGENCY_EVAC, LOCKOUT };
Mode mode = MODE_AUTO;
CycleState cycleState = ADSORB;
SpecialState specialState = SPECIAL_NONE;

bool processRunning = false;
bool vacuumDelayPending = false;
unsigned long stateStartMs = 0;
unsigned long vacuumDelayStartMs = 0;
unsigned long specialStartMs = 0;
const unsigned long VACUUM_DELAY_MS = 10000UL;
const unsigned long SPECIAL_EVAC_MS = 180000UL; // 3 min

bool lastSwitch = LOW;
bool safetySystemValidated = false; // Becomes true only after Safety D5/A1 has been observed LOW once
const byte BUF_SIZE = 100;
char cmdBuf[BUF_SIZE];
byte cmdIdx = 0;

void setup() {
  Serial.begin(115200);
  lcd.init(); lcd.backlight();
  pinMode(bellowsEvac, OUTPUT); pinMode(stateChange, OUTPUT);
  pinMode(adsorbPin, OUTPUT); pinMode(desorbPin, OUTPUT);
  pinMode(bellowsTank, OUTPUT); pinMode(vacuumPin, OUTPUT);
  pinMode(onoffPin, INPUT); pinMode(safetyInputPin, INPUT);
  stopAllOutputs();
  lastSwitch = digitalRead(onoffPin);
  Serial.print(F("READY,")); Serial.println(CONTROLLER_ID);
}

void loop() {
  readSerial();
  bool sw = digitalRead(onoffPin);
  bool safetySignal = digitalRead(safetyInputPin);

  // Startup safety validation:
  // SAFETY intentionally holds D5 HIGH while its sensors initialize.
  // Do not interpret that normal startup condition as an emergency.
  // CONTROL remains fully stopped until it has observed SAFETY LOW once.
  if (!safetySystemValidated) {
    stopAllOutputs();
    lastSwitch = sw; // Establish initial switch state; OFF at boot is not a shutdown edge.

    if (safetySignal == LOW) {
      safetySystemValidated = true;
      Serial.println(F("SAFETY,READY"));
    } else {
      lcd.setCursor(0,0); lcd.print("Safety startup  ");
      lcd.setCursor(0,1); lcd.print("Waiting...      ");
      return;
    }
  }

  // Only a real HIGH->LOW transition after startup initiates controlled shutdown.
  if (lastSwitch == HIGH && sw == LOW && specialState == SPECIAL_NONE) {
    startSpecialEvac(false);
  }
  lastSwitch = sw;

  // After SAFETY has been validated, any subsequent HIGH is a genuine trip.
  // Safety has priority, including during normal shutdown evacuation.
  if (safetySignal == HIGH &&
      specialState != EMERGENCY_EVAC && specialState != LOCKOUT) {
    startSpecialEvac(true);
  }

  if (specialState != SPECIAL_NONE) {
    handleSpecialState();
    return;
  }

  if (mode == MODE_AUTO && processRunning) {
    runAutomaticCycle();
  } else if (mode == MODE_MANUAL) {
    displayManual();
  } else {
    displayReady();
  }
}

void startSpecialEvac(bool emergency) {
  processRunning = false;
  vacuumDelayPending = false;
  specialState = emergency ? EMERGENCY_EVAC : SHUTDOWN_EVAC;
  specialStartMs = millis();
  applyEvacuationOutputs();
  Serial.println(emergency ? F("EMERGENCY,EVACUATION_STARTED") : F("SHUTDOWN,EVACUATION_STARTED"));
}

void handleSpecialState() {
  if (specialState == SHUTDOWN_EVAC || specialState == EMERGENCY_EVAC) {
    updateVacuumDelay();
    unsigned long elapsed = millis() - specialStartMs;
    unsigned long rem = elapsed >= SPECIAL_EVAC_MS ? 0 : (SPECIAL_EVAC_MS - elapsed) / 1000UL;
    lcd.setCursor(0,0); lcd.print(specialState == SHUTDOWN_EVAC ? "SHUTDOWN EVAC   " : "EMERGENCY EVAC  ");
    lcd.setCursor(0,1); printRemainMMSS(rem);
    if (elapsed >= SPECIAL_EVAC_MS) {
      stopAllOutputs();
      if (specialState == EMERGENCY_EVAC) {
        specialState = LOCKOUT;
        Serial.println(F("EMERGENCY,LOCKOUT"));
      } else {
        specialState = SPECIAL_NONE;
        Serial.println(F("SHUTDOWN,COMPLETE"));
      }
    }
    return;
  }
  if (specialState == LOCKOUT) {
    stopAllOutputs();
    lcd.setCursor(0,0); lcd.print("SYSTEM ERROR    ");
    lcd.setCursor(0,1); lcd.print("RESET REQUIRED  ");
  }
}

void runAutomaticCycle() {
  updateVacuumDelay();
  unsigned long total = currentDurationS();
  unsigned long elapsed = (millis() - stateStartMs) / 1000UL;
  if (elapsed >= total) {
    if (cycleState == ADSORB) cycleState = EVACUATION;
    else if (cycleState == EVACUATION) cycleState = DESORB;
    else cycleState = ADSORB;
    stateStartMs = millis();
    applyCycleOutputs();
    sendState();
    elapsed = 0;
    total = currentDurationS();
  }
  displayCycle(total - elapsed);
}

void applyCycleOutputs() {
  if (cycleState == ADSORB) {
    stopAllOutputs(); digitalWrite(adsorbPin, HIGH);
  } else if (cycleState == EVACUATION) {
    applyEvacuationOutputs();
  } else {
    stopAllOutputs();
    digitalWrite(stateChange, HIGH); digitalWrite(desorbPin, HIGH); digitalWrite(bellowsTank, HIGH);
    vacuumDelayPending = true; vacuumDelayStartMs = millis();
  }
}

void applyEvacuationOutputs() {
  stopAllOutputs();
  digitalWrite(bellowsEvac, HIGH); digitalWrite(desorbPin, HIGH);
  vacuumDelayPending = true; vacuumDelayStartMs = millis();
}

void updateVacuumDelay() {
  if (vacuumDelayPending && millis() - vacuumDelayStartMs >= VACUUM_DELAY_MS) {
    digitalWrite(vacuumPin, HIGH); vacuumDelayPending = false;
  }
}

void stopAllOutputs() {
  digitalWrite(bellowsEvac, LOW); digitalWrite(stateChange, LOW);
  digitalWrite(adsorbPin, LOW); digitalWrite(desorbPin, LOW);
  digitalWrite(bellowsTank, LOW); digitalWrite(vacuumPin, LOW);
  vacuumDelayPending = false;
}

unsigned long currentDurationS() {
  if (cycleState == ADSORB) return adsorbTimeS;
  if (cycleState == EVACUATION) return evacuationTimeS;
  return desorbTimeS;
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { cmdBuf[cmdIdx] = 0; processCommand(cmdBuf); cmdIdx = 0; }
    else if (c != '\r' && cmdIdx < BUF_SIZE-1) cmdBuf[cmdIdx++] = c;
  }
}

void processCommand(char *cmd) {
  if (!strcmp(cmd,"IDENTIFY")) { Serial.println(F("ID,CONTROL")); return; }
  if (!strcmp(cmd,"GET_STATUS")) { sendStatus(); return; }

  // Reset is allowed only after emergency evacuation completes and safety is clear.
  if (!strcmp(cmd,"RESET_ERROR")) {
    if (specialState != LOCKOUT) { Serial.println(F("ERROR,NOT_LOCKED_OUT")); return; }
    if (digitalRead(safetyInputPin) == HIGH) { Serial.println(F("ERROR,SAFETY_FAULT_ACTIVE")); return; }
    specialState = SPECIAL_NONE; cycleState = ADSORB; processRunning = false; mode = MODE_AUTO; stopAllOutputs();
    Serial.println(F("OK,EMERGENCY_RESET")); return;
  }

  // During special states all normal Pi commands are blocked.
  if (specialState != SPECIAL_NONE) { Serial.println(F("ERROR,SPECIAL_STATE_ACTIVE")); return; }

  // Master switch OFF: do not accept operational commands.
  if (digitalRead(onoffPin) == LOW) { Serial.println(F("ERROR,SYSTEM_SWITCH_OFF")); return; }
  if (!safetySystemValidated || digitalRead(safetyInputPin) == HIGH) { Serial.println(F("ERROR,SAFETY_NOT_READY")); return; }

  if (!strcmp(cmd,"START")) {
    if (mode != MODE_AUTO) { Serial.println(F("ERROR,NOT_AUTO_MODE")); return; }
    if (processRunning) { Serial.println(F("ERROR,ALREADY_RUNNING")); return; }
    cycleState = ADSORB; stateStartMs = millis(); processRunning = true; applyCycleOutputs(); sendState(); Serial.println(F("OK,STARTED")); return;
  }
  if (!strcmp(cmd,"STOP")) { startSpecialEvac(false); return; }
  if (!strcmp(cmd,"MODE,AUTO")) { if(processRunning){Serial.println(F("ERROR,CYCLE_RUNNING"));return;} stopAllOutputs(); mode=MODE_AUTO; Serial.println(F("OK,MODE,AUTO")); return; }
  if (!strcmp(cmd,"MODE,MANUAL")) { if(processRunning){Serial.println(F("ERROR,CYCLE_RUNNING"));return;} stopAllOutputs(); mode=MODE_MANUAL; Serial.println(F("OK,MODE,MANUAL")); return; }
  if (!strncmp(cmd,"SET_TIMES,",10)) { setTimes(cmd+10); return; }
  if (!strncmp(cmd,"SET_OUTPUT,",11)) { setOutput(cmd+11); return; }
  Serial.println(F("ERROR,UNKNOWN_COMMAND"));
}

void setTimes(char *data) {
  if (processRunning) { Serial.println(F("ERROR,CYCLE_RUNNING")); return; }
  char *a=strtok(data,","), *e=strtok(NULL,","), *d=strtok(NULL,",");
  if(!a||!e||!d||strtok(NULL,",")){Serial.println(F("ERROR,BAD_TIME_FORMAT"));return;}
  unsigned long av=strtoul(a,NULL,10), ev=strtoul(e,NULL,10), dv=strtoul(d,NULL,10);
  if(!av||!ev||!dv||av>MAX_STATE_TIME_S||ev>MAX_STATE_TIME_S||dv>MAX_STATE_TIME_S){Serial.println(F("ERROR,BAD_TIME_VALUE"));return;}
  adsorbTimeS=av; evacuationTimeS=ev; desorbTimeS=dv;
  Serial.print(F("OK,TIMES,"));Serial.print(av);Serial.print(',');Serial.print(ev);Serial.print(',');Serial.println(dv);
}

void setOutput(char *data) {
  if(mode!=MODE_MANUAL){Serial.println(F("ERROR,NOT_MANUAL_MODE"));return;}
  char *name=strtok(data,","), *vs=strtok(NULL,","); if(!name||!vs){Serial.println(F("ERROR,BAD_OUTPUT_FORMAT"));return;}
  int v=atoi(vs); if(v!=0&&v!=1){Serial.println(F("ERROR,BAD_OUTPUT_VALUE"));return;}
  int pin=-1;
  if(!strcmp(name,"ADSORB"))pin=adsorbPin; else if(!strcmp(name,"DESORB"))pin=desorbPin;
  else if(!strcmp(name,"BELLOWS_EVAC"))pin=bellowsEvac; else if(!strcmp(name,"BELLOWS_TANK"))pin=bellowsTank;
  else if(!strcmp(name,"VACUUM"))pin=vacuumPin; else if(!strcmp(name,"STATE_CHANGE"))pin=stateChange;
  if(pin<0){Serial.println(F("ERROR,UNKNOWN_OUTPUT"));return;} digitalWrite(pin,v);
  Serial.print(F("OK,OUTPUT,"));Serial.print(name);Serial.print(',');Serial.println(v);
}

void sendState(){ Serial.print(F("STATE,")); Serial.println(cycleState==ADSORB?F("ADSORB"):cycleState==EVACUATION?F("EVACUATION"):F("DESORB")); }

void sendStatus() {
  Serial.print(F("STATUS,CONTROL,"));
  Serial.print(mode==MODE_AUTO?F("AUTO"):F("MANUAL")); Serial.print(',');
  if(specialState==SHUTDOWN_EVAC)Serial.print(F("SHUTDOWN")); else if(specialState==EMERGENCY_EVAC)Serial.print(F("EMERGENCY_EVAC")); else if(specialState==LOCKOUT)Serial.print(F("LOCKOUT")); else Serial.print(processRunning?F("RUNNING"):F("STOPPED"));
  Serial.print(',');
  if(specialState!=SPECIAL_NONE) Serial.print(F("SPECIAL")); else if(!processRunning)Serial.print(F("IDLE")); else Serial.print(cycleState==ADSORB?F("ADSORB"):cycleState==EVACUATION?F("EVACUATION"):F("DESORB"));
  Serial.print(','); Serial.print(getRemainingS());
  Serial.print(F(",SWITCH="));Serial.print(digitalRead(onoffPin)); Serial.print(F(",SAFETY="));Serial.print(digitalRead(safetyInputPin));
  Serial.print(F(",ADSORB="));Serial.print(digitalRead(adsorbPin)); Serial.print(F(",DESORB="));Serial.print(digitalRead(desorbPin));
  Serial.print(F(",BELLOWS_EVAC="));Serial.print(digitalRead(bellowsEvac)); Serial.print(F(",BELLOWS_TANK="));Serial.print(digitalRead(bellowsTank));
  Serial.print(F(",VACUUM="));Serial.print(digitalRead(vacuumPin)); Serial.print(F(",STATE_CHANGE="));Serial.println(digitalRead(stateChange));
}

unsigned long getRemainingS(){
  if(specialState==SHUTDOWN_EVAC||specialState==EMERGENCY_EVAC){unsigned long e=(millis()-specialStartMs)/1000UL;return e>=180?0:180-e;}
  if(!processRunning)return 0; unsigned long e=(millis()-stateStartMs)/1000UL,t=currentDurationS();return e>=t?0:t-e;
}

void displayCycle(unsigned long rem){lcd.setCursor(0,0);lcd.print(cycleState==ADSORB?"Adsorb          ":cycleState==EVACUATION?"Evacuation      ":"Desorb          ");lcd.setCursor(0,1);printHHMMSS(rem);}
void displayManual(){lcd.setCursor(0,0);lcd.print("Manual control  ");lcd.setCursor(0,1);lcd.print("Pi has control  ");}
void displayReady(){
  if(digitalRead(onoffPin)==LOW){lcd.setCursor(0,0);lcd.print("System disabled ");lcd.setCursor(0,1);lcd.print("Switch ON       ");}
  else {lcd.setCursor(0,0);lcd.print("System ready    ");lcd.setCursor(0,1);lcd.print("Waiting for Pi  ");}
}
void printHHMMSS(unsigned long s){unsigned long h=s/3600,m=(s%3600)/60,sec=s%60;if(h<10)lcd.print('0');lcd.print(h);lcd.print(':');if(m<10)lcd.print('0');lcd.print(m);lcd.print(':');if(sec<10)lcd.print('0');lcd.print(sec);lcd.print("        ");}
void printRemainMMSS(unsigned long s){unsigned long m=s/60,sec=s%60;lcd.print("Remain: ");if(m<10)lcd.print('0');lcd.print(m);lcd.print(':');if(sec<10)lcd.print('0');lcd.print(sec);lcd.print("   ");}
