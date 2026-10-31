
import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone


class ExperimentManager:
    def __init__(self, data_dir=None):
        # Locate the project root directory
        project_root = Path(__file__).resolve().parent.parent

        # Default experiment data directory inside the project
        if data_dir is None:
            self.data_dir = project_root / "CO2_Data"
        else:
            self.data_dir = Path(data_dir)

        # Create the data directory if it does not exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.current_experiment_path = None
        self.experiment_info = None

        self.file_names = {
            "co2": "co2_data.csv",
            "weather": "weather_data.csv",
            "status": "system_status.csv"
        }

    def start_experiment(self, experiment_name=""):
        if self.current_experiment_path is not None:
            raise RuntimeError("An experiment is already running.")

        start_time = datetime.now(timezone.utc).astimezone()
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")

        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in experiment_name.strip()
        )

        folder_name = f"Experiment_{timestamp}"
        if safe_name:
            folder_name += f"_{safe_name}"

        experiment_path = self.data_dir / folder_name

        suffix = 1
        while experiment_path.exists():
            experiment_path = self.data_dir / f"{folder_name}_{suffix}"
            suffix += 1

        experiment_path.mkdir(parents=True)

        experiment_info = {
            "experiment_name": experiment_name,
            "start_time": start_time.isoformat(),
            "end_time": None,
            "status": "initializing"
        }

        info_path = experiment_path / "experiment_info.json"

        try:
            with open(info_path, "w", encoding="utf-8") as file:
                json.dump(
                    experiment_info,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

            weather_headers = [
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

            self._create_csv("weather", weather_headers, experiment_path)
            self._create_empty_file("co2", experiment_path)

            self._create_csv(
                "status",
                ["timestamp", "device", "raw_message"],
                experiment_path
            )

            experiment_info["status"] = "running"

            with open(info_path, "w", encoding="utf-8") as file:
                json.dump(
                    experiment_info,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

        except Exception:
            self.current_experiment_path = None
            self.experiment_info = None
            raise

        self.current_experiment_path = experiment_path
        self.experiment_info = experiment_info

        print(f"Experiment started: {experiment_path}")

        return experiment_path

    def _save_experiment_info(self):
        info_path = self.current_experiment_path / "experiment_info.json"
        temp_path = info_path.with_suffix(".tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(
                    self.experiment_info,
                    file,
                    indent=4,
                    ensure_ascii=False
                )
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_path, info_path)

        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _create_csv(self, file_type, headers, experiment_path=None):
        if experiment_path is None:
            file_path = self.get_file_path(file_type)
        else:
            file_path = experiment_path / self.file_names[file_type]

        with open(file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(headers)

    def _create_empty_file(self, file_type, experiment_path=None):
        if experiment_path is None:
            file_path = self.get_file_path(file_type)
        else:
            file_path = experiment_path / self.file_names[file_type]

        file_path.touch(exist_ok=True)

    def get_experiment_path(self):
        if self.current_experiment_path is None:
            raise RuntimeError("No experiment is currently running.")

        return self.current_experiment_path

    def get_file_path(self, file_type):
        if self.current_experiment_path is None:
            raise RuntimeError("No experiment is currently running.")

        if file_type not in self.file_names:
            raise ValueError(f"Unknown file type: {file_type}")

        return self.current_experiment_path / self.file_names[file_type]

    def end_experiment(self, status="completed"):
        if self.current_experiment_path is None:
            raise RuntimeError("No experiment is currently running.")

        if status not in ("completed", "aborted"):
            raise ValueError(
                "Experiment status must be 'completed' or 'aborted'."
            )

        if self.experiment_info["end_time"] is None:
            end_time = datetime.now(timezone.utc).astimezone()
            self.experiment_info["end_time"] = end_time.isoformat()

        self.experiment_info["status"] = status

        self._save_experiment_info()

        finished_path = self.current_experiment_path

        self.current_experiment_path = None
        self.experiment_info = None

        print(f"Experiment ended with status '{status}': {finished_path}")

        return finished_path