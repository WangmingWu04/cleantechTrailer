# CO2 System I/O Map

## Sensors / Measurements

### CO2 Sensor 1
- Description: CO2 concentration during desorption, flowing into the storage tank
- Range listed in I/O sheet: 1-100%
- Software role: Input
- Status: Confirmed from I/O sheet

### CO2 Sensor 2
- Description: CO2 concentration flowing out of the storage tank into the formic acid cell
- Range listed in I/O sheet: 1-100%
- Software role: Input
- Status: Confirmed from I/O sheet

### Flow
- Description: 1-2 LPM flow control
- Software role: To be confirmed
- Status: Need project team clarification

## Actuators / Outputs

### Valve 1
- Description: Open/Close signal
- Software role: Output
- Status: Confirmed from I/O sheet
- Control logic: To be determined

### Valve 2
- Description: Open/Close signal
- Software role: Output
- Status: Confirmed from I/O sheet
- Control logic: To be determined

### Valve 3
- Description: Open/Close signal
- Software role: Output
- Status: Confirmed from I/O sheet
- Control logic: To be determined

### Valve 4
- Description: Open/Close signal
- Software role: Output
- Status: Confirmed from I/O sheet
- Control logic: To be determined

### Vacuum Pump
- Description: On/Off signal
- Software role: Output
- Status: Confirmed from I/O sheet
- Control logic: To be determined

### Desorption Heater
- Description: PID control signal for desorption heater
- Listed under: Input in I/O sheet
- Software role: To be confirmed
- Status: I/O direction is ambiguous and needs project team clarification
- PID parameters: To be determined

## System Control Signals

### Start / Stop
- Description: Start/Stop signal
- Software role: Input
- Status: Confirmed from I/O sheet
- Control behavior: To be determined

### Emergency Shutoff
- Description: Emergency shutoff procedure signal
- Software role: Input
- Status: Confirmed from I/O sheet
- Safety behavior: Must be defined by project team / approved safety requirements