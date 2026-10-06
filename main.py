import time
from sensors.weather import WeatherStation
from logging_system.logger import DataLogger


def main():
    # 创建传感器对象
    station = WeatherStation()

    # 创建日志记录器（数据将保存到 logs/weather.csv）
    logger = DataLogger("logs/weather.csv")

    print("Weather station data logging started. Press Ctrl+C to stop.")

    # 无限循环，每 5 秒记录一次
    try:
        while True:
            # 1. 读取真实天气数据
            data = station.read_data()

            # 2. 检查数据是否合理
            if not station.validate_data(data):
                print("Invalid weather data detected. Skipping this record.")
                continue

            # 3. 打印到屏幕，方便观察
            print(
                f"Time: {data['timestamp']} | "
                f"Humidity: {data['humidity']}% | "
                f"Temperature: {data['temperature']}°F | "
                f"Rainfall: {data['rainfall']}in"
            )

            # 4. 写入 CSV
            logger.log_weather(data)

            # 5. 等待 5 秒
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nWeather station data logging stopped.")


if __name__ == "__main__":
    main()