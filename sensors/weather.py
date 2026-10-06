import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo


class WeatherStation:
    def __init__(self):
        self.api_key = os.environ["AMBIENT_API_KEY"]
        self.application_key = os.environ["AMBIENT_APPLICATION_KEY"]

        self.url = "https://rt.ambientweather.net/v1/devices"

    def read_data(self):
        params = {
            "apiKey": self.api_key,
            "applicationKey": self.application_key,
        }

        response = requests.get(self.url, params=params)
        response.raise_for_status()

        devices = response.json()

        if not devices:
            raise ValueError("No weather station found.")

        data = devices[0]["lastData"]

        timestamp_utc = datetime.fromisoformat(
            data["date"].replace("Z", "+00:00")
        )

        timestamp_local = timestamp_utc.astimezone(
            ZoneInfo(data["tz"])
        )

        return {
            "timestamp": timestamp_local.isoformat(),
            "temperature": data["tempf"],
            "humidity": data["humidity"],
            "rainfall": data["hourlyrainin"],
            "wind_speed": data["windspeedmph"],
            "wind_direction": data["winddir"],
            "solar_radiation": data["solarradiation"],
            "pressure": data["baromrelin"],
            "dew_point": data["dewPoint"],
        }

    def validate_data(self, data):
        if not 0 <= data["humidity"] <= 100:
            return False

        if data["rainfall"] < 0:
            return False

        return True


if __name__ == "__main__":
    station = WeatherStation()

    data = station.read_data()

    print("Weather data:")
    print("Timestamp:", data["timestamp"])
    print("Temperature:", data["temperature"], "F")
    print("Humidity:", data["humidity"], "%")
    print("Rainfall:", data["rainfall"], "in")
    print("Wind speed:", data["wind_speed"], "mph")
    print("Wind direction:", data["wind_direction"], "degrees")
    print("Solar radiation:", data["solar_radiation"])
    print("Pressure:", data["pressure"], "inHg")
    print("Dew point:", data["dew_point"], "F")

    print()
    print("Data valid:", station.validate_data(data))