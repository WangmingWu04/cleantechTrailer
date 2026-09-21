import csv
import os
from datetime import datetime


class DataLogger:
    def __init__(self, filename):
        self.filename = filename

        # 如果目录不存在则自动创建
        os.makedirs(
            os.path.dirname(filename),
            exist_ok=True
        )

        # 如果文件不存在，先写入表头
        if not os.path.exists(filename):
            with open(filename, "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "timestamp",
                    "humidity",
                    "temperature",
                    "rainfall"
                ])

    def log_weather(self, data):
        # 获取当前时间（带秒的 ISO 格式）
        timestamp = datetime.now().isoformat(timespec="seconds")

        # 追加一行天气数据
        with open(self.filename, "a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                timestamp,
                data["humidity"],
                data["temperature"],
                data["rainfall"]
            ])
if __name__ == "__main__":
    # 临时测试：存到 logs 文件夹下的 weather.csv
    logger = DataLogger("logs/weather.csv")
    
    # 模拟一次天气数据（实际会调用你的 WeatherStation）
    test_data = {"humidity": 65.3, "temperature": 31.7, "rainfall": 1.39}
    logger.log_weather(test_data)
    print("数据已写入 CSV")