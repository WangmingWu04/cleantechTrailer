import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add project root to Python import path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from logging_system.experiment_manager import ExperimentManager


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = ExperimentManager(data_dir=temp_dir)

        # Create a test experiment
        experiment_path = manager.start_experiment("RetryTest")

        info_path = experiment_path / "experiment_info.json"

        # Keep the original os.replace function
        real_replace = __import__(
            "logging_system.experiment_manager",
            fromlist=["os"]
        ).os.replace

        # Simulate one failed save, then allow the next save to succeed
        attempts = 0

        def simulated_replace(src, dst):
            nonlocal attempts
            attempts += 1

            if attempts == 1:
                raise PermissionError("Simulated save failure")

            return real_replace(src, dst)

        with patch(
            "logging_system.experiment_manager.os.replace",
            side_effect=simulated_replace
        ):
            # First attempt should fail
            try:
                manager.end_experiment(status="completed")
                raise AssertionError("The first save should have failed.")
            except PermissionError:
                print("PASS: First save failed as expected.")

            # Manager state must remain available for retry
            assert manager.current_experiment_path == experiment_path
            assert manager.experiment_info is not None
            print("PASS: Experiment state was preserved.")

            # Original metadata file should remain unchanged
            with open(info_path, "r", encoding="utf-8") as file:
                saved_info = json.load(file)

            assert saved_info["status"] == "running"
            assert saved_info["end_time"] is None
            print("PASS: Original metadata was preserved.")

            # Temporary file should have been cleaned up
            assert not info_path.with_suffix(".tmp").exists()
            print("PASS: Temporary file was cleaned up.")

            # Retry should succeed
            finished_path = manager.end_experiment(status="completed")

            assert finished_path == experiment_path
            assert manager.current_experiment_path is None
            assert manager.experiment_info is None
            print("PASS: Retry succeeded and manager state was cleared.")

        # Verify final metadata
        with open(info_path, "r", encoding="utf-8") as file:
            final_info = json.load(file)

        assert final_info["status"] == "completed"
        assert final_info["end_time"] is not None
        print("PASS: Final metadata is correct.")

    print("\nALL TESTS PASSED.")


if __name__ == "__main__":
    main()