import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch, call
import unittest.mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from co2_control_system_v9.co2_pi_app import App


def make_fake_app(end_experiment):
    app = App.__new__(App)

    app.finalization_in_progress = False
    app.pending_finalization_status = "completed"
    app.pending_finalization_stage = "metadata"
    app.experiment_active = True
    app.experiment_stopping = True


    app.experiment_manager = SimpleNamespace(
        end_experiment=end_experiment
    )

    app.retry_finalize_button = Mock()

    return app


def test_retry_success():
    manager_save = Mock()

    app = make_fake_app(manager_save)

    app.retry_finalize_experiment()

    manager_save.assert_called_once_with(status="completed")

    assert app.experiment_active is False
    assert app.experiment_stopping is False
    assert app.pending_finalization_status is None
    assert app.finalization_in_progress is False

    app.retry_finalize_button.config.assert_called_once_with(
        state="disabled"
    )

    print("PASS: Successful retry updates GUI state.")


def test_retry_failure():
    manager_save = Mock(
        side_effect=PermissionError("Simulated save failure")
    )

    app = make_fake_app(manager_save)

    with patch(
        "co2_control_system_v9.co2_pi_app.messagebox.showerror"
    ) as showerror:
        app.retry_finalize_experiment()

    manager_save.assert_called_once_with(status="completed")

    assert app.experiment_active is True
    assert app.experiment_stopping is True
    assert app.pending_finalization_status == "completed"
    assert app.finalization_in_progress is False

    showerror.assert_called_once()

    print("PASS: Failed retry preserves pending GUI state.")



def test_cleanup_failure_then_retry():
    manager_save = Mock()
    app = make_fake_app(manager_save)

    app.pending_finalization_stage = "cleanup"

    app._cleanup_experiment_collection = Mock(
        side_effect=[
            PermissionError("Simulated cleanup failure"),
            None
        ]
    )

    with patch(
        "co2_control_system_v9.co2_pi_app.messagebox.showerror"
    ) as showerror:

        # First attempt: cleanup fails.
        app.retry_finalize_experiment()

        assert app.pending_finalization_stage == "cleanup"
        assert app.experiment_active is True
        assert app.finalization_in_progress is False
        manager_save.assert_not_called()
        showerror.assert_called_once()

        # Second attempt: cleanup succeeds, metadata is saved.
        app.retry_finalize_experiment()

    app._cleanup_experiment_collection.assert_has_calls([
        unittest.mock.call(),
        unittest.mock.call()
    ])

    manager_save.assert_called_once_with(status="completed")

    assert app.pending_finalization_status is None
    assert app.pending_finalization_stage is None
    assert app.experiment_active is False
    assert app.experiment_stopping is False
    assert app.finalization_in_progress is False

    print("PASS: Cleanup failure can be retried successfully.")


def test_metadata_retry_does_not_repeat_cleanup():
    manager_save = Mock(
        side_effect=[
            PermissionError("Simulated metadata save failure"),
            None
        ]
    )

    app = make_fake_app(manager_save)
    app.pending_finalization_stage = "metadata"

    app._cleanup_experiment_collection = Mock()

    with patch(
        "co2_control_system_v9.co2_pi_app.messagebox.showerror"
    ) as showerror:

        # First attempt: metadata save fails.
        app.retry_finalize_experiment()

        assert app.pending_finalization_stage == "metadata"
        assert app.experiment_active is True
        assert app.finalization_in_progress is False
        showerror.assert_called_once()

        # Second attempt: metadata save succeeds.
        app.retry_finalize_experiment()

    app._cleanup_experiment_collection.assert_not_called()
    manager_save.assert_has_calls([
        unittest.mock.call(status="completed"),
        unittest.mock.call(status="completed")
    ])

    assert app.pending_finalization_status is None
    assert app.pending_finalization_stage is None
    assert app.experiment_active is False
    assert app.experiment_stopping is False
    assert app.finalization_in_progress is False

    print("PASS: Metadata retry does not repeat cleanup.")




def main():
    test_retry_success()
    test_retry_failure()
    test_cleanup_failure_then_retry()
    test_metadata_retry_does_not_repeat_cleanup()

    print("\nALL GUI RETRY TESTS PASSED.")

if __name__ == "__main__":
    main()