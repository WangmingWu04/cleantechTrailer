
import csv
import threading
from pathlib import Path
from datetime import datetime

# Import the existing App class.
# If your main program has a different filename,
# change co2_pi_app to its actual Python module name.
import sys

sys.path.insert(
    0,
    str(Path(__file__).parent / "co2_control_system_v9")
)

from co2_pi_app import App


class FakeVar:
    """Replace Tkinter StringVar for testing."""
    def set(self, value):
        self.value = value


class FakeExperimentManager:
    """Provide an independent CSV path for this test."""
    def __init__(self, path):
        self.path = path

    def get_file_path(self, file_type):
        if file_type != "co2":
            raise ValueError(f"Unexpected file type: {file_type}")
        return str(self.path)


# Create a unique output file so existing files are not overwritten.
output_dir = Path("simulation_output")
output_dir.mkdir(exist_ok=True)

filename = (
    "co2_data_simulation_"
    + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    + ".csv"
)
output_path = output_dir / filename


# Create an App object WITHOUT starting the Tkinter GUI
# or the Arduino discovery thread.
app = App.__new__(App)

# Initialize only the attributes used by open_csv() and data_row().
app.experiment_manager = FakeExperimentManager(output_path)
app.experiment_active = True

app.logging = False
app.csvfile = None
app.writer = None
app.csv_logging_error = None
app.csv_error_notified = False

app.pi_g = 0.0
app.prev_gps = None
app.prev_ms = None
app.sync_time = None

app.live = FakeVar()
app.totals = FakeVar()
app.timing = FakeVar()
app.filelabel = FakeVar()

app.sensor_data_lock = threading.Lock()

# Simulated Safety Arduino data.
app.latest_safety_data = {
    "timestamp": "2026-11-24T12:00:00.000-07:00",
    "inlet_temperature": 23.5,
    "inlet_humidity": 45.0
}

# Simulated Ambient Weather data.
app.latest_weather_data = {
    "timestamp": "2026-11-24T12:00:00-07:00",
    "temperature": 72.5,
    "humidity": 47,
    "rainfall": 0.0,
    "wind_speed": 1.2,
    "wind_direction": 180,
    "solar_radiation": 350,
    "pressure": 28.58,
    "dew_point": 50.2
}


# Open CSV using the existing method in the main program.
if not App.open_csv(app):
    raise RuntimeError("Could not open the simulation CSV.")

# Simulate three CO2 DATA messages.
simulated_co2_messages = [
    ["DATA", "1000", "12.5", "1.2", "0.35", "0.008"],
    ["DATA", "2000", "13.0", "1.3", "0.40", "0.009"],
    ["DATA", "3000", "13.5", "1.4", "0.45", "0.010"]
]

# First two rows use the same Safety and Weather data.
App.data_row(app, simulated_co2_messages[0])
App.data_row(app, simulated_co2_messages[1])

# Simulate updated sensor readings before the third CO2 row.
app.latest_safety_data = {
    "timestamp": "2026-11-24T12:01:00.000-07:00",
    "inlet_temperature": 24.0,
    "inlet_humidity": 46.0
}

app.latest_weather_data = {
    "timestamp": "2026-11-24T12:01:00-07:00",
    "temperature": 73.0,
    "humidity": 48,
    "rainfall": 0.0,
    "wind_speed": 1.5,
    "wind_direction": 190,
    "solar_radiation": 360,
    "pressure": 28.59,
    "dew_point": 51.0
}

App.data_row(app, simulated_co2_messages[2])

# Close the test CSV.
App.close_csv(app)


# Read and validate the generated CSV.
with output_path.open("r", newline="", encoding="utf-8") as file:
    rows = list(csv.reader(file))

header = rows[0]
data_rows = rows[1:]

print("\n===== CSV SIMULATION RESULTS =====")
print("Output file:", output_path)
print("Header columns:", len(header))
print("Data rows:", len(data_rows))
print("Data row column counts:", [len(row) for row in data_rows])

# Check the CSV structure.
assert len(header) == 23, "Expected 23 header columns."
assert len(data_rows) == 3, "Expected 3 simulated CO2 rows."
assert all(len(row) == 23 for row in data_rows), (
    "At least one data row does not have 23 columns."
)

# Check that the weather timestamp is repeated,
# then updated when new weather data arrives.
weather_timestamp_index = header.index("Weather Timestamp")

weather_timestamps = [
    row[weather_timestamp_index] for row in data_rows
]

assert weather_timestamps[0] == weather_timestamps[1], (
    "Weather timestamp should repeat when no new reading arrives."
)
assert weather_timestamps[1] != weather_timestamps[2], (
    "Weather timestamp should update when new weather data arrives."
)

print("Weather timestamps:", weather_timestamps)
print("\nAll CSV simulation checks passed.")
