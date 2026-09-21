from controls.co2_controller import CO2Controller


controller = CO2Controller()

controller.update_inputs(
    sensor1_co2=50.0,
    sensor2_co2=30.0,
    start=True,
    emergency_stop=False
)

print("Sensor 1:", controller.sensor1_co2)
print("Sensor 2:", controller.sensor2_co2)
print("Start:", controller.start)
print("Emergency stop:", controller.emergency_stop)

print("Outputs:", controller.get_outputs())