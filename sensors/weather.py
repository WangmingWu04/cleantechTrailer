import random


class WeatherStation:
    def read_data(self):
        humidity = round(random.uniform(40, 70), 1)
        temperature = round(random.uniform(20, 35), 1)
        rainfall = round(random.uniform(0, 2), 2)

        return {
            "humidity": humidity,
            "temperature": temperature,
            "rainfall": rainfall
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

    print(data)
    print(station.validate_data(data))