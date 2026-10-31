import os
import tempfile
import unittest
from unittest.mock import Mock

from co2_control_system_v9.co2_pi_app import App


class TestCSVLogging(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.app = App.__new__(App)

        self.app.experiment_active = True
        self.app.logging = False
        self.app.csvfile = None
        self.app.writer = None
        self.app.csv_logging_error = None
        self.app.csv_error_notified = False

        self.app.filelabel = Mock()
        self.app.experiment_manager = Mock()

        csv_path = os.path.join(self.temp_dir.name, "co2.csv")
        self.app.experiment_manager.get_file_path.return_value = csv_path

    def test_open_csv_creates_header(self):
        self.app.open_csv()

        csv_path = self.app.experiment_manager.get_file_path.return_value

        self.assertTrue(os.path.exists(csv_path))
        self.assertTrue(self.app.logging)
        self.assertIsNotNone(self.app.csvfile)
        self.assertIsNotNone(self.app.writer)

        self.app.close_csv()

        with open(csv_path, "r", encoding="utf-8") as file:
            header = file.readline()

        self.assertIn("CO2 (%)", header)
        self.assertIn("Flow (SLPM)", header)

    def test_open_csv_does_not_duplicate_header(self):
        csv_path = self.app.experiment_manager.get_file_path.return_value

        with open(csv_path, "w", encoding="utf-8") as file:
            file.write("Existing Header\n")

        self.app.open_csv()
        self.app.close_csv()

        with open(csv_path, "r", encoding="utf-8") as file:
            lines = file.readlines()

        self.assertEqual(lines.count("Existing Header\n"), 1)
        self.assertEqual(len(lines), 1)

    def test_close_csv_clears_file_references(self):
        self.app.open_csv()

        self.app.close_csv()

        self.assertFalse(self.app.logging)
        self.assertIsNone(self.app.csvfile)
        self.assertIsNone(self.app.writer)

    def test_close_csv_preserves_references_when_close_fails(self):
        self.app.logging = True
        self.app.csvfile = Mock()
        self.app.csvfile.close.side_effect = OSError("File close failed")
        self.app.writer = Mock()

        with self.assertRaises(OSError):
            self.app.close_csv()

        self.assertFalse(self.app.logging)
        self.assertIsNotNone(self.app.csvfile)
        self.assertIsNotNone(self.app.writer)

    def test_data_row_stops_logging_when_csv_write_fails(self):
        self.app.logging = True
        self.app.csvfile = Mock()
        self.app.writer = Mock()
        self.app.writer.writerow.side_effect = OSError("Disk write failed")

        self.app.prev_gps = None
        self.app.prev_ms = None
        self.app.pi_g = 0.0
        self.app.sync_time = None

        self.app.live = Mock()
        self.app.totals = Mock()
        self.app.timing = Mock()

        with unittest.mock.patch(
        "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
        ) as showwarning:
            self.app.data_row([
                "DATA",
                "1000",
                "20.0",
                "1.0",
                "0.5",
                "0.01"
            ])

        showwarning.assert_called_once()


        self.assertFalse(
            self.app.logging,
            "CSV logging should stop after a write failure."
        )

    def test_csv_logging_error_shows_warning_only_once(self):
        self.app.csvfile = Mock()
        self.app.csvfile.close.side_effect = OSError("File close failed")
        self.app.writer = Mock()
        self.app.csv_error_notified = False

        with unittest.mock.patch(
            "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
        ) as showwarning:
            self.app.handle_csv_logging_error(
                OSError("Disk write failed")
            )
            self.app.handle_csv_logging_error(
                OSError("Another write failed")
            )

        showwarning.assert_called_once()

    def test_data_row_stops_logging_when_flush_fails(self):
        self.app.logging = True
        self.app.csvfile = Mock()
        self.app.csvfile.flush.side_effect = OSError("Disk flush failed")
        self.app.writer = Mock()

        self.app.prev_gps = None
        self.app.prev_ms = None
        self.app.pi_g = 0.0
        self.app.sync_time = None

        self.app.live = Mock()
        self.app.totals = Mock()
        self.app.timing = Mock()

        with unittest.mock.patch(
            "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
        ) as showwarning:
            self.app.data_row([
                "DATA",
                "1000",
                "20.0",
                "1.0",
                "0.5",
                "0.01"
            ])

        self.assertFalse(self.app.logging)
        self.assertIn("Disk flush failed", self.app.csv_logging_error)
        showwarning.assert_called_once()

    def test_open_csv_without_active_experiment(self):
        self.app.experiment_active = False

        with unittest.mock.patch(
            "co2_control_system_v9.co2_pi_app.messagebox.showerror"
        ) as showerror:
            self.app.open_csv()

        showerror.assert_called_once()
        self.assertFalse(self.app.logging)
        self.assertIsNone(self.app.csvfile)
        self.assertIsNone(self.app.writer)

    def test_open_csv_handles_file_open_failure(self):
        with unittest.mock.patch(
            "builtins.open",
            side_effect=OSError("Permission denied")
        ):
            with unittest.mock.patch(
                "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
            ) as showwarning:
                self.app.open_csv()

        self.assertFalse(self.app.logging)
        self.assertIsNone(self.app.csvfile)
        self.assertIsNone(self.app.writer)
        self.assertIn("Permission denied", self.app.csv_logging_error)
        showwarning.assert_called_once()

    def test_open_csv_handles_header_write_failure(self):
        with unittest.mock.patch(
            "co2_control_system_v9.co2_pi_app.csv.writer"
        ) as mock_writer:
            mock_writer.return_value.writerow.side_effect = OSError(
                "Header write failed"
            )

            with unittest.mock.patch(
                "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
            ) as showwarning:
                self.app.open_csv()

        self.assertFalse(self.app.logging)
        self.assertIsNone(self.app.csvfile)
        self.assertIsNone(self.app.writer)
        self.assertIn("Header write failed", self.app.csv_logging_error)
        showwarning.assert_called_once()

    def test_open_csv_handles_header_flush_failure(self):
        with unittest.mock.patch(
            "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
        ) as showwarning:
            with unittest.mock.patch(
                "co2_control_system_v9.co2_pi_app.open",
                create=True,
            ) as mock_open:
                mock_file = mock_open.return_value
                mock_file.flush.side_effect = OSError(
                    "Header flush failed"
                )

                self.app.open_csv()

        self.assertFalse(self.app.logging)
        self.assertIsNone(self.app.csvfile)
        self.assertIsNone(self.app.writer)
        self.assertIn(
            "Header flush failed",
            self.app.csv_logging_error
        )
        showwarning.assert_called_once()

    def test_open_csv_does_not_overwrite_file_reference_when_previous_close_failed(self):
        old_file = Mock()
        old_file.close.side_effect = OSError("Previous file close failed")

        self.app.csvfile = old_file
        self.app.writer = Mock()

        with unittest.mock.patch(
            "co2_control_system_v9.co2_pi_app.messagebox.showwarning"
        ):
            self.app.open_csv()

        self.assertIs(
            self.app.csvfile,
            old_file,
            "The previous file reference should not be overwritten."
        )

if __name__ == "__main__":
    unittest.main()