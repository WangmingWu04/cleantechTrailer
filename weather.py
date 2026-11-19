class CO2Controller:
    def __init__(self):
        self.state = "NORMAL"

        self.sensor1_co2 = None
        self.sensor2_co2 = None

        self.start = False
        self.emergency_stop = False

        self.valve1 = False
        self.valve2 = False
        self.valve3 = False
        self.valve4 = False

        self.vacuum_pump = False
        self.sensor2_co2 = None

        self.start = False
        self.emergency_stop = False

        self.valve1 = False
        self.valve2 = False
        self.valve3 = False
        self.valve4 = False

        self.vacuum_pump = False

    def update_inputs(
        self,
        sensor1_co2,
        sensor2_co2,
        start,
        emergency_stop
    ):
        self.sensor1_co2 = sensor1_co2
        self.sensor2_co2 = sensor2_co2

        self.start = start
        self.emergency_stop = emergency_stop

    def get_outputs(self):
        return {
            "valve1": self.valve1,
            "valve2": self.valve2,
            "valve3": self.valve3,
            "valve4": self.valve4,
            "vacuum_pump": self.vacuum_pump
        }