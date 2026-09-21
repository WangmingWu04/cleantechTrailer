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
    try:
        while True:
            # 1. 读取模拟数据
            data = station.read_data()

            # 2. 检查数据是否合理
            if not station.validate_data(data):
                print("检测到无效的气象数据，跳过本次记录。")
                continue

            # 3. 打印到屏幕，方便观察
            print(
                f"湿度: {data['humidity']}% | "
                f"温度: {data['temperature']}°C | "
                f"降雨: {data['rainfall']}mm"
            )

            # 4. 写入 CSV
            logger.log_weather(data)

            # 5. 等待 5 秒
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n气象站数据记录已停止。")


if __name__ == "__main__":
    main()