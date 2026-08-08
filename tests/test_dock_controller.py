import unittest

from aiur.dock_controller import (
    DockController,
    DockInputs,
    DockState,
    KeeperCommand,
)


class DockControllerTests(unittest.TestCase):
    def _capture(self, controller: DockController) -> None:
        out = controller.step(
            0.0,
            DockInputs(
                seat_switch=True,
                keeper_closed_switch=False,
                capture_enable=True,
            ),
        )
        self.assertEqual(out.state, DockState.LOCKING)
        self.assertFalse(out.capture_confirmed)

        out = controller.step(
            0.1,
            DockInputs(
                seat_switch=True,
                keeper_closed_switch=True,
                capture_enable=True,
            ),
        )
        self.assertEqual(out.state, DockState.CAPTURED)
        self.assertTrue(out.capture_confirmed)

    def test_seat_switch_alone_never_confirms_capture(self) -> None:
        controller = DockController()
        out = controller.step(
            0.0,
            DockInputs(
                seat_switch=True,
                keeper_closed_switch=False,
                capture_enable=True,
            ),
        )
        self.assertEqual(out.keeper_command, KeeperCommand.CLOSE)
        self.assertFalse(out.capture_confirmed)

    def test_capture_requires_seat_and_keeper_feedback(self) -> None:
        controller = DockController()
        self._capture(controller)

    def test_probe_loss_during_lock_fails_open(self) -> None:
        controller = DockController()
        controller.step(
            0.0,
            DockInputs(True, False, capture_enable=True),
        )
        out = controller.step(
            0.1,
            DockInputs(False, False, capture_enable=True),
        )
        self.assertEqual(out.state, DockState.FAULT_OPEN)
        self.assertEqual(out.keeper_command, KeeperCommand.OPEN)
        self.assertEqual(out.fault_reason, "probe_lost_during_lock")

    def test_lock_timeout_fails_open(self) -> None:
        controller = DockController(lock_timeout_s=0.5)
        controller.step(0.0, DockInputs(True, False, capture_enable=True))
        out = controller.step(0.5, DockInputs(True, False, capture_enable=True))
        self.assertEqual(out.state, DockState.FAULT_OPEN)
        self.assertEqual(out.keeper_command, KeeperCommand.OPEN)
        self.assertEqual(out.fault_reason, "lock_timeout")

    def test_sensor_disagreement_after_capture_fails_locked(self) -> None:
        controller = DockController()
        self._capture(controller)
        out = controller.step(
            0.2,
            DockInputs(seat_switch=False, keeper_closed_switch=True),
        )
        self.assertEqual(out.state, DockState.FAULT_LOCKED)
        self.assertEqual(out.keeper_command, KeeperCommand.CLOSE)
        self.assertFalse(out.capture_confirmed)

    def test_normal_release_requires_physical_separation(self) -> None:
        controller = DockController()
        self._capture(controller)

        out = controller.step(
            0.2,
            DockInputs(True, True, release_request=True),
        )
        self.assertEqual(out.state, DockState.RELEASING)
        self.assertEqual(out.keeper_command, KeeperCommand.OPEN)

        out = controller.step(0.3, DockInputs(True, False))
        self.assertEqual(out.state, DockState.RELEASING)

        out = controller.step(0.4, DockInputs(False, False))
        self.assertEqual(out.state, DockState.OPEN)

    def test_emergency_release_overrides_fault_locked(self) -> None:
        controller = DockController()
        self._capture(controller)
        controller.step(0.2, DockInputs(False, True))

        out = controller.step(
            0.3,
            DockInputs(False, True, emergency_release=True),
        )
        self.assertEqual(out.state, DockState.RELEASING)
        self.assertEqual(out.keeper_command, KeeperCommand.OPEN)

    def test_normal_release_cannot_open_fault_locked_capture(self) -> None:
        controller = DockController()
        self._capture(controller)
        controller.step(0.2, DockInputs(False, True))

        out = controller.step(
            0.3,
            DockInputs(False, True, release_request=True),
        )
        self.assertEqual(out.state, DockState.FAULT_LOCKED)
        self.assertEqual(out.keeper_command, KeeperCommand.CLOSE)

    def test_non_monotonic_timestamp_is_rejected(self) -> None:
        controller = DockController()
        controller.step(1.0, DockInputs(False, False))
        with self.assertRaises(ValueError):
            controller.step(0.9, DockInputs(False, False))

    def test_power_on_with_keeper_closed_holds_instead_of_dropping(self) -> None:
        """A restart while an aircraft is docked must not command the keeper open.

        A rebooted controller sees only the switches: both made is exactly the
        signature of a real capture.  Starting in OPEN and reacting to a closed
        keeper as an anomaly would command open and drop the aircraft, and the
        FAULT_OPEN reset path cannot clear until both switches read open — i.e.
        until after it has fallen.  Holding is the recoverable error.
        """

        rebooted = DockController()
        out = rebooted.step(0.0, DockInputs(seat_switch=True, keeper_closed_switch=True))

        self.assertEqual(out.state, DockState.FAULT_LOCKED)
        self.assertEqual(out.keeper_command, KeeperCommand.CLOSE)
        self.assertEqual(out.fault_reason, "power_on_with_keeper_closed")
        # It holds the aircraft, but it does not claim a capture it never saw.
        self.assertFalse(out.capture_confirmed)

    def test_power_on_held_state_recovers_to_captured_on_operator_confirmation(self) -> None:
        rebooted = DockController()
        rebooted.step(0.0, DockInputs(True, True))
        out = rebooted.step(0.1, DockInputs(True, True, reset_fault=True))

        self.assertEqual(out.state, DockState.CAPTURED)
        self.assertTrue(out.capture_confirmed)

    def test_power_on_with_closed_keeper_and_no_probe_needs_emergency_release(self) -> None:
        """Opening a keeper whose contents are unknown stays a human decision."""

        rebooted = DockController()
        rebooted.step(0.0, DockInputs(seat_switch=False, keeper_closed_switch=True))
        # A plain reset cannot clear it: the seat switch is open, so the
        # operator cannot confirm a capture either.
        blocked = rebooted.step(0.1, DockInputs(False, True, reset_fault=True))
        self.assertEqual(blocked.state, DockState.FAULT_LOCKED)
        self.assertEqual(blocked.keeper_command, KeeperCommand.CLOSE)

        released = rebooted.step(0.2, DockInputs(False, True, emergency_release=True))
        self.assertEqual(released.state, DockState.RELEASING)
        self.assertEqual(released.keeper_command, KeeperCommand.OPEN)

    def test_power_on_with_open_keeper_starts_open(self) -> None:
        controller = DockController()
        out = controller.step(0.0, DockInputs(seat_switch=False, keeper_closed_switch=False))
        self.assertEqual(out.state, DockState.OPEN)
        self.assertEqual(out.keeper_command, KeeperCommand.OPEN)

    def test_keeper_closing_unexpectedly_while_running_still_fails_open(self) -> None:
        """The power-on rule must not blunt the in-run anomaly response.

        Mid-operation the controller knows it never commanded a close, so a
        keeper that reports closed is a genuine fault with nothing retained,
        and failing open is still correct.
        """

        controller = DockController()
        controller.step(0.0, DockInputs(False, False))
        out = controller.step(0.1, DockInputs(seat_switch=False, keeper_closed_switch=True))

        self.assertEqual(out.state, DockState.FAULT_OPEN)
        self.assertEqual(out.keeper_command, KeeperCommand.OPEN)
        self.assertEqual(out.fault_reason, "keeper_reports_closed_while_open")

    def test_seat_switch_lost_on_weight_transfer_faults_every_capture(self) -> None:
        """Pin the failure mode behind requirement P0-DOCK-010.

        The controller is correct here: losing S1 after capture is genuine
        sensor disagreement and failing locked is the safe response.  The
        defect this test documents is mechanical.  A seat switch actuated by
        maintained force rather than probe position opens as soon as the
        aircraft disarms and its weight transfers from thrust to the keeper
        tines — the docked aircraft weighs about 0.47 N against a switch
        operating force of 0.74 N or more — so a force-actuated S1 would turn
        every successful capture into FAULT_LOCKED.  If this test ever starts
        failing because the controller was relaxed, the fix was applied to the
        wrong layer.
        """

        controller = DockController()
        self._capture(controller)

        out = controller.step(0.5, DockInputs(seat_switch=False, keeper_closed_switch=True))

        self.assertEqual(out.state, DockState.FAULT_LOCKED)
        self.assertEqual(out.fault_reason, "capture_sensor_disagreement")
        self.assertFalse(out.capture_confirmed)
        self.assertEqual(out.keeper_command, KeeperCommand.CLOSE)


if __name__ == "__main__":
    unittest.main()

