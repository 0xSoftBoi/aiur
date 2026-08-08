"""Unit tests for the terminal guidance supervisor (aiur/sim/guidance.py).

TerminalGuidance is constructed directly with synthetic PoseMeasurement
inputs; no engine or physics loop is involved.  Geometry matches the
DockGeometry defaults (probe_height_m=0.05, seat_travel_m=0.10), so with the
dock entrance at z=2.0 the rendezvous standoff target for the drone center is
z = 2.0 - 0.05 - 0.55 = 1.40.
"""

import unittest

from aiur.dock_controller import DockOutput, DockState, KeeperCommand
from aiur.sim.dock_physics import DockStepResult, ProbePhase
from aiur.sim.events import EventKind
from aiur.sim.guidance import (
    APPROACH_PHASES,
    FleetSequencer,
    GuidanceParams,
    GuidancePhase,
    TerminalGuidance,
)
from aiur.sim.sensors import PoseMeasurement
from aiur.sim.vec import Vec3, ZERO

DT = 0.02
DOCK_POS = Vec3(0.0, 0.0, 2.0)
STATION = Vec3(0.0, 0.0, 1.0)
#: Drone-center position that puts the probe tip at the rendezvous standoff.
STANDOFF = Vec3(0.0, 0.0, 1.40)
FLIGHT_S = 600.0


def meas(position, valid=True):
    return PoseMeasurement(position=position, velocity=ZERO, valid=valid, age_s=0.04)


DOCK_MEAS = meas(DOCK_POS)


def make_guidance():
    return TerminalGuidance(
        GuidanceParams(),
        drone_index=0,
        probe_height_m=0.05,
        seat_travel_m=0.10,
        station=STATION,
    )


def open_dock_feedback(reported_s1=False):
    """A minimal dock feedback frame: controller OPEN, keeper open."""

    return DockStepResult(
        probe_phase=ProbePhase.FREE,
        seat_truth=False,
        keeper_closed_truth=False,
        reported_s1=reported_s1,
        reported_s2=False,
        controller=DockOutput(
            state=DockState.OPEN,
            keeper_command=KeeperCommand.OPEN,
            capture_confirmed=False,
            fault_reason=None,
        ),
        contact_closing_speed_m_s=None,
        events=(),
    )


class TerminalGuidanceTests(unittest.TestCase):
    def test_station_hold_without_authorization_stays_put(self):
        guidance = make_guidance()
        t = 0.0
        for _ in range(10):
            decision = guidance.step(t, DT, meas(STATION), DOCK_MEAS, None, FLIGHT_S)
            self.assertIs(decision.phase, GuidancePhase.STATION_HOLD)
            self.assertEqual(decision.velocity_cmd, ZERO)
            self.assertFalse(decision.disarm)
            t += DT

    def test_authorization_moves_station_hold_to_rendezvous(self):
        guidance = make_guidance()
        sequencer = FleetSequencer([guidance])

        decision = guidance.step(0.0, DT, meas(STATION), DOCK_MEAS, None, FLIGHT_S)
        self.assertIs(decision.phase, GuidancePhase.STATION_HOLD)

        self.assertTrue(sequencer.authorize(0))
        decision = guidance.step(DT, DT, meas(STATION), DOCK_MEAS, None, FLIGHT_S)
        self.assertIs(decision.phase, GuidancePhase.RENDEZVOUS)

    def test_invalid_pose_holds_then_aborts_after_timeout(self):
        guidance = make_guidance()
        FleetSequencer([guidance]).authorize(0)
        t = 0.0
        decision = guidance.step(t, DT, meas(STATION), DOCK_MEAS, None, FLIGHT_S)
        self.assertIs(decision.phase, GuidancePhase.RENDEZVOUS)

        # Stale pose first commands a hold: zero velocity, no abort, for up
        # to pose_hold_timeout_s (0.5 s = 25 steps; assert well inside it).
        invalid = meas(STATION, valid=False)
        for _ in range(20):
            t += DT
            decision = guidance.step(t, DT, invalid, DOCK_MEAS, None, FLIGHT_S)
            self.assertIs(decision.phase, GuidancePhase.RENDEZVOUS)
            self.assertEqual(decision.velocity_cmd, ZERO)
            self.assertEqual(decision.events, ())

        # Past the timeout the supervisor aborts with a machine-readable reason.
        abort_events = []
        for _ in range(10):
            t += DT
            decision = guidance.step(t, DT, invalid, DOCK_MEAS, None, FLIGHT_S)
            abort_events = [e for e in decision.events if e.kind is EventKind.ABORT]
            if abort_events:
                break
        self.assertEqual(len(abort_events), 1)
        self.assertEqual(abort_events[0].detail, "relative_pose_invalid")
        self.assertIs(decision.phase, GuidancePhase.ABORT_DESCEND)
        self.assertEqual(guidance.abort_count, 1)

        # Blind abort descent: down is always away from the dock envelope.
        t += DT
        decision = guidance.step(t, DT, invalid, DOCK_MEAS, None, FLIGHT_S)
        self.assertEqual(
            decision.velocity_cmd,
            Vec3(0.0, 0.0, -guidance.params.blind_descent_speed_m_s),
        )

    def test_pose_jump_aborts_and_quarantines_the_approach(self):
        guidance = make_guidance()
        FleetSequencer([guidance]).authorize(0)
        t = 0.0

        # First valid measurement arms the jump detector; the drone sits just
        # off the standoff so RENDEZVOUS does not immediately hand off.
        pos = Vec3(0.05, 0.0, 1.40)
        decision = guidance.step(t, DT, meas(pos), DOCK_MEAS, None, FLIGHT_S)
        self.assertIs(decision.phase, GuidancePhase.RENDEZVOUS)

        # A 40 mm single-step displacement exceeds pose_jump_threshold_m (30 mm).
        jumped = Vec3(0.09, 0.0, 1.40)
        t += DT
        decision = guidance.step(t, DT, meas(jumped), DOCK_MEAS, None, FLIGHT_S)
        self.assertIs(decision.phase, GuidancePhase.ABORT_DESCEND)
        reasons = [e.detail for e in decision.events if e.kind is EventKind.ABORT]
        self.assertEqual(reasons, ["pose_jump_detected"])

        # The post-jump position is already inside the standoff capture radius,
        # so only the quarantine can be blocking re-entry to RENDEZVOUS.
        # pose_quarantine_s = 20 s at 50 Hz is 1000 steps.
        steps_blocked = 0
        reentered = False
        for _ in range(1100):
            t += DT
            decision = guidance.step(t, DT, meas(jumped), DOCK_MEAS, None, FLIGHT_S)
            if decision.phase is GuidancePhase.RENDEZVOUS:
                reentered = True
                break
            self.assertNotIn(decision.phase, APPROACH_PHASES)
            steps_blocked += 1
        self.assertTrue(reentered, "approach never resumed after quarantine decay")
        self.assertGreaterEqual(steps_blocked, 900)
        self.assertEqual(guidance.abort_count, 1)

    def test_implausible_seat_report_sets_dock_untrusted_and_aborts(self):
        guidance = make_guidance()
        FleetSequencer([guidance]).authorize(0)
        # Probe tip is ~0.72 m from the seat: far beyond 2x seat_plausibility_m.
        pos = Vec3(0.3, 0.0, 1.40)
        decision = guidance.step(0.0, DT, meas(pos), DOCK_MEAS, None, FLIGHT_S)
        self.assertIs(decision.phase, GuidancePhase.RENDEZVOUS)
        self.assertFalse(guidance.dock_untrusted)

        decision = guidance.step(
            DT, DT, meas(pos), DOCK_MEAS, open_dock_feedback(reported_s1=True), FLIGHT_S
        )
        self.assertTrue(guidance.dock_untrusted)
        self.assertIs(decision.phase, GuidancePhase.ABORT_DESCEND)
        reasons = [e.detail for e in decision.events if e.kind is EventKind.ABORT]
        self.assertEqual(reasons, ["dock_seat_sensor_implausible"])
        self.assertEqual(guidance.abort_count, 1)

        # The lying dock stays distrusted; no repeated abort on the same report.
        decision = guidance.step(
            2 * DT, DT, meas(pos), DOCK_MEAS, open_dock_feedback(reported_s1=True), FLIGHT_S
        )
        self.assertTrue(guidance.dock_untrusted)
        self.assertEqual(guidance.abort_count, 1)

    def test_capture_enable_only_ever_asserted_in_seated_wait(self):
        guidance = make_guidance()
        sequencer = FleetSequencer([guidance])
        t = 0.0
        pos = STATION
        phases_seen = set()

        # Unauthorized station hold first.
        for _ in range(5):
            decision = guidance.step(t, DT, meas(pos), DOCK_MEAS, None, FLIGHT_S)
            self.assertFalse(decision.dock_commands.capture_enable)
            phases_seen.add(decision.phase)
            t += DT

        # Authorize and fly the commanded velocity (simple kinematic drone)
        # through RENDEZVOUS and ALIGN into TERMINAL.
        self.assertTrue(sequencer.authorize(0))
        terminal_steps = 0
        for _ in range(2000):
            decision = guidance.step(t, DT, meas(pos), DOCK_MEAS, None, FLIGHT_S)
            self.assertFalse(decision.dock_commands.capture_enable)
            phases_seen.add(decision.phase)
            pos = pos + decision.velocity_cmd * DT
            t += DT
            if decision.phase is GuidancePhase.TERMINAL:
                terminal_steps += 1
                if terminal_steps >= 25:
                    break

        self.assertGreaterEqual(terminal_steps, 25)
        self.assertEqual(guidance.abort_count, 0)
        for phase in (
            GuidancePhase.STATION_HOLD,
            GuidancePhase.RENDEZVOUS,
            GuidancePhase.ALIGN,
            GuidancePhase.TERMINAL,
        ):
            self.assertIn(phase, phases_seen)


class FleetSequencerTests(unittest.TestCase):
    def _pair(self):
        guidances = [
            TerminalGuidance(
                GuidanceParams(),
                drone_index=index,
                probe_height_m=0.05,
                seat_travel_m=0.10,
                station=STATION,
            )
            for index in range(2)
        ]
        return guidances, FleetSequencer(guidances)

    def test_single_token_authorize_release_cycle(self):
        (g0, g1), sequencer = self._pair()

        self.assertIsNone(sequencer.token_holder)
        self.assertTrue(sequencer.authorize(0))
        self.assertEqual(sequencer.token_holder, 0)
        self.assertTrue(g0.approach_authorized)
        self.assertFalse(g1.approach_authorized)

        # Second aircraft is refused while the token is held.
        self.assertFalse(sequencer.authorize(1))
        self.assertEqual(sequencer.token_holder, 0)
        self.assertFalse(g1.approach_authorized)

        # Re-authorizing the holder is idempotent.
        self.assertTrue(sequencer.authorize(0))
        self.assertEqual(sequencer.token_holder, 0)

        # Release frees the token for the other aircraft.
        sequencer.release(0)
        self.assertIsNone(sequencer.token_holder)
        self.assertFalse(g0.approach_authorized)
        self.assertTrue(sequencer.authorize(1))
        self.assertEqual(sequencer.token_holder, 1)
        self.assertTrue(g1.approach_authorized)
        self.assertFalse(g0.approach_authorized)

    def test_release_by_non_holder_is_ignored(self):
        (g0, _g1), sequencer = self._pair()
        self.assertTrue(sequencer.authorize(0))
        sequencer.release(1)
        self.assertEqual(sequencer.token_holder, 0)
        self.assertTrue(g0.approach_authorized)

    def test_audit_flags_simultaneous_dock_approach(self):
        (g0, g1), sequencer = self._pair()

        self.assertEqual(sequencer.audit(0.0), ())

        # Force the invariant violation the sequencer exists to prevent.
        g0.phase = GuidancePhase.RENDEZVOUS
        g1.phase = GuidancePhase.TERMINAL
        events = sequencer.audit(5.0)
        self.assertEqual(len(events), 1)
        self.assertIs(events[0].kind, EventKind.SIMULTANEOUS_DOCK_APPROACH)
        self.assertEqual(events[0].detail, "drones=[0, 1]")

        # A single approaching aircraft is nominal.
        g1.phase = GuidancePhase.STATION_HOLD
        self.assertEqual(sequencer.audit(6.0), ())


if __name__ == "__main__":
    unittest.main()
