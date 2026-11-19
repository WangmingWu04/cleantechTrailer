
import csv
import os


class DataLogger:
    def __init__(self, filename):
        self.filename = filename

        os.makedirs(
            os.path.dirname(filename),
            exist_ok=True
        )

        self.headers = [
            "timestamp",
            "humidity",
            "temperature",
            "rainfall",
            "wind_speed",
            "wind_direction",
            "solar_radiation",
            "pressure",
            "dew_point"
        ]

        # Create a new CSV file with all nine columns.
        if not os.path.exists(filename):
            with open(filename, "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(self.headers)

        else:
            # Check whether an existing CSV has the correct format.
            with open(filename, "r", newline="") as file:
                reader = csv.reader(file)
                existing_headers = next(reader, [])

            if existing_headers != self.headers:
                raise ValueError(
                    f"CSV format mismatch in {filename}. "
                    "Please rename or back up the old CSV file "
                    "before starting the logger."
                )

    def log_weather(self, data):
        with open(self.filename, "a", newline="") as file:
            writer = csv.writer(file)

            writer.writerow([
                data["timestamp"],
                data["humidity"],
                data["temperature"],
                data["rainfall"],
                data["wind_speed"],
                data["wind_direction"],
                data["solar_radiation"],
                data["pressure"],
                data["dew_point"]
            ])
