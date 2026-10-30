CO2 CONTROL SYSTEM - V6

Files:
- control_arduino.ino : CONTROL Arduino firmware
- data_arduino.ino    : DATA Arduino firmware, 1 Hz desorption logging
- safety_arduino.ino  : SAFETY Arduino firmware
- co2_pi_app.py       : Raspberry Pi 4 / Raspberry Pi OS GUI

Key safety behavior:
- MAX6675 > configured temperature limit (default 150 C): immediate latched emergency, all phases.
- MAX6675 or SHT30 humidity reporting lost for configured delay (default 15 s): latched emergency, all phases.
- SHT30 humidity > configured limit (default 30% RH) continuously for configured delay (default 5 min): latched emergency ONLY during ADSORB. Timer resets on leaving ADSORB.
- Pressure >= configured limit (default 0 psig) continuously for configured delay (default 5 min): latched emergency ONLY during DESORB. Timer resets on leaving DESORB.
- SAFETY D5 -> CONTROL A1 hardwired interlock.
- Emergency response: CONTROL performs 3-minute evacuation then enters lockout until reset.
- Physical CONTROL switch OFF initiates 3-minute SHUTDOWN evacuation.

Pi communication:
- Explicit SAFETY phases: PHASE,ADSORB / PHASE,EVACUATION / PHASE,DESORB / PHASE,IDLE.
- 1 s GET_STATUS heartbeat to CONTROL, DATA and SAFETY; 5 s stale-connection indication.
- Reset sequence waits for OK,SAFETY_RESET before sending RESET_ERROR to CONTROL.
- Safety settings are editable in GUI and active for current powered SAFETY session.

Data:
- DATA transmits at 1 Hz during desorption logging.
- Pi synchronizes real-world timestamp to DATA Arduino elapsed millis at START_LOG.
- Pi independently integrates CO2 using trapezoidal integration.
- CSVs stored by default in ~/CO2_Data and named by desorption start date/time plus optional experiment name.

Python dependencies:
  python3, python3-tk, pyserial

Typical install:
  sudo apt update
  sudo apt install python3 python3-tk python3-venv
  python3 -m venv .venv
  source .venv/bin/activate
  pip install pyserial
  python3 co2_pi_app.py

V7 STARTUP / SERIAL FIXES
- Raspberry Pi keeps identified Arduino serial ports open persistently. A missed heartbeat changes connection status but does not close/reopen the port. Only an actual serial I/O failure allows rediscovery/reopening.
- CONTROL no longer treats SAFETY D5 HIGH during initial sensor validation as an emergency.
- CONTROL holds all outputs OFF and displays "Safety startup / Waiting..." until Safety A1 has been observed LOW once.
- CONTROL rejects START until that safety validation has completed.
- Physical enable switch OFF at power-up establishes the initial state and does not trigger the 3-minute shutdown. Only a later ON-to-OFF transition triggers controlled shutdown.

V8 UPDATE - DATA ARDUINO DISCOVERY FIX
--------------------------------------
The Raspberry Pi serial discovery routine now keeps each candidate Arduino port
open through the board's USB-reset/startup period and retries IDENTIFY on that
same open serial session. It no longer uses the short open/timeout/close cycle
that could repeatedly reset an unidentified DATA Arduino.

Normal controller connections remain persistent after identification. Missed
heartbeats do not close a port; only a real serial I/O failure marks the serial
object dead and allows rediscovery.

V9 changes:
- Safety Arduino pressure sensor input changed to A2.
- Data Arduino sends LIVE,CO2%,SLPM at 1 Hz outside desorption logging.
- Pi Data screen displays LIVE measurements without writing them to CSV or integrating them.
- Existing DATA stream, timestamp synchronization, CSV logging, and CO2 integration remain desorption-only.
