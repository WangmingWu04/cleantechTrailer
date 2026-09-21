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


if __name__ == "__main__":
    station = WeatherStation()

    data = station.read_data()

    print(data)