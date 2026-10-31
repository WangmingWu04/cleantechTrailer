from controls.co2_controller import CO2Controller


controller = CO2Controller()

# Test normal input updates.
controller.update_inputs(
    sensor1_co2=50.0,
    sensor2_co2=30.0,
    start=True,
    emergency_stop=False
)

assert controller.sensor1_co2 == 50.0
assert controller.sensor2_co2 == 30.0
assert controller.start is True
assert controller.emergency_stop is False

# Test initial output state.
outputs = controller.get_outputs()

assert isinstance(outputs, dict)
assert all(output is False for output in outputs.values())

print("PASS: Controller inputs are updated correctly.")
print("PASS: All controller outputs are initially False.")

# Test emergency stop input.
controller.update_inputs(
    sensor1_co2=50.0,
    sensor2_co2=30.0,
    start=True,
    emergency_stop=True
)

assert controller.emergency_stop is True

print("PASS: Emergency stop input is updated correctly.")
print("\nALL CO2 CONTROLLER TESTS PASSED.")