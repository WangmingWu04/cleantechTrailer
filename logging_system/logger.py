import csv
import os


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
        # 使用气象站数据中的时间戳
        timestamp = data["timestamp"]

        # 追加一行天气数据
        with open(self.filename, "a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                timestamp,
                data["humidity"],
                data["temperature"],
                data["rainfall"]
            ])