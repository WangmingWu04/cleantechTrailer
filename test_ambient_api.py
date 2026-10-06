import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

API_KEY = os.environ["AMBIENT_API_KEY"]
APPLICATION_KEY = os.environ["AMBIENT_APPLICATION_KEY"]

url = "https://rt.ambientweather.net/v1/devices"

params = {
    "apiKey": API_KEY,
    "applicationKey": APPLICATION_KEY,
}

response = requests.get(url, params=params)

print("HTTP status:", response.status_code)

if response.status_code == 200:
    devices = response.json()

    with open("ambient_raw.json", "w", encoding="utf-8") as file:
        file.write(response.text)

    print("Raw API response saved to ambient_raw.json")

    print("Number of devices:", len(devices))

    station = devices[0]

    print("Station name:", station["info"]["name"])
    print("MAC address:", station["macAddress"])

    data = station["lastData"]

    print()
    print("Weather data:")
    print("Temperature:", data["tempf"], "F")
    print("Humidity:", data["humidity"], "%")
    print("Wind speed:", data["windspeedmph"], "mph")
    print("Wind direction:", data["winddir"], "degrees")
    print("Solar radiation:", data["solarradiation"])
    print("Hourly rain:", data["hourlyrainin"], "in")
    print("Daily rain:", data["dailyrainin"], "in")
    print("Pressure:", data["baromrelin"], "inHg")

    timestamp_utc = datetime.fromisoformat(
        data["date"].replace("Z", "+00:00")
    )

    timestamp_local = timestamp_utc.astimezone(
        ZoneInfo("America/Phoenix")
    )

    print("Timestamp UTC:", timestamp_utc)
    print("Timestamp Phoenix:", timestamp_local)

else:
    print("API request failed.")
    print(response.text)