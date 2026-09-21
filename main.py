import time
from sensors.weather import WeatherStation
from logging_system.logger import DataLogger


def main():
    # 创建传感器对象
    station = WeatherStation()

    # 创建日志记录器（数据将保存到 logs/weather.csv）
    logger = DataLogger("logs/weather.csv")

    print("气象站数据记录已启动，按 Ctrl+C 停止。")

    # 无限循环，每 5 秒记录一次
    while True:
        # 1. 读取模拟数据
        data = station.read_data()

        # 2. 打印到屏幕（方便观察）
        print(f"湿度: {data['humidity']}% | 温度: {data['temperature']}°C | 降雨: {data['rainfall']}mm")

        # 3. 写入 CSV
        logger.log_weather(data)

        # 4. 等待 5 秒
        time.sleep(5)


if __name__ == "__main__":
    main()