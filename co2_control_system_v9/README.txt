CO2 CONTROL SYSTEM - V6

Files:
- control_arduino.ino : CONTROL Arduino firmware
- data_arduino.ino    : DATA Arduino firmware, 1 Hz experiment logging
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
- Pressing START creates the experiment folder and initial CSV files before the automatic cycle begins.
- The Pi retries creation of the experiment folder and startup files up to three times. If setup still fails, it reports the error and does not start the experiment.
- START_LOG is requested before the automatic cycle begins and retried up to three times if the DATA Arduino does not confirm it.
- DATA transmits at 1 Hz while logging, including ADSORB and EVACUATION phases, not only DESORB.
- The Pi synchronizes real-world timestamps to DATA Arduino elapsed milliseconds at START_LOG and independently integrates CO2 using trapezoidal integration.
- The CO2 CSV is initialized before the CONTROL Arduino starts the automatic cycle. If CSV opening fails, the Pi retries up to three times and aborts startup if it still cannot open the file.
- A CO2 CSV write or flush failure stops logging, reports the error, and requests the normal evacuation shutdown. The experiment is marked aborted after shutdown completes.
- Experiment data is stored under the project's CO2_Data directory by default, in a timestamped folder with an optional experiment name.

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
- DATA logging starts before the automatic cycle, records across all cycle phases, and uses the experiment folder created when START is pressed.
- Runtime CO2 CSV write/flush failures request normal evacuation and mark the experiment aborted.
