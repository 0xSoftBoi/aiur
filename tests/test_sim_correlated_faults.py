import random
import unittest
from dataclasses import replace

from aiur.dock_controller import DockState
from aiur.sim.dock_physics import DockAssembly, DockCommands, DockGeometry
from aiur.sim.engine import run_episode
from aiur.sim.events import EventKind
from aiur.sim.faults import (
    CORRELATED_PAIRS,
    FaultKind,
    FaultSpec,
    sample_correlated_fault_plan,
)
from aiur.sim.scenarios import sil_p0b
from aiur.sim.sensors import SwitchFault
from aiur.sim.vec import Vec3


class CorrelatedFaultTests(unittest.TestCase):
    def test_every_correlated_pair_names_two_distinct_faults(self) -> None:
        for coupling, first, second in CORRELATED_PAIRS:
            self.assertTrue(coupling.strip(), "a pair must state its coupling")
            self.assertIsNot(first, second)

    def test_correlated_plan_is_a_pair_with_overlapping_windows(self) -> None:
        rng = random.Random(7)
        for _ in range(50):
            plan = sample_correlated_fault_plan(rng)
            self.assertEqual(len(plan), 2)
            # A shared cause does not stagger its effects by much.
            self.assertLessEqual(abs(plan[0].t_start_s - plan[1].t_start_s), 1.0)

    def test_correlated_plans_are_deterministic_for_a_seed(self) -> None:
        self.assertEqual(
            sample_correlated_fault_plan(random.Random(11)),
            sample_correlated_fault_plan(random.Random(11)),
        )

    def test_keeper_switch_faults_reach_the_mechanism(self) -> None:
        """The S2 channel was unreachable before these fault kinds existed."""

        for kind, expected in (
            (FaultKind.KEEPER_SWITCH_STUCK_OPEN, SwitchFault.STUCK_OPEN),
            (FaultKind.KEEPER_SWITCH_STUCK_CLOSED, SwitchFault.STUCK_CLOSED),
        ):
            config = replace(
                sil_p0b(3), fault_plan=(FaultSpec(kind, 0.0, duration_s=999.0),)
            )
            result = run_episode(config, 3)
            self.assertTrue(
                any(e.kind is EventKind.FAULT_INJECTED for e in result.events),
                f"{kind.value} never activated",
            )
            self.assertEqual(result.unsafe_events, ())

    def test_correlated_campaign_produces_no_unsafe_outcome(self) -> None:
        """Coupled double faults may refuse a recovery; they may not be unsafe."""

        for seed in range(40):
            result = run_episode(sil_p0b(seed, correlated_fault=True), seed)
            self.assertEqual(
                result.unsafe_events,
                (),
                f"seed {seed} produced {[e.kind.value for e in result.unsafe_events]}",
            )

    def test_a_fast_bias_ramp_is_caught_and_aborted(self) -> None:
        """The defence works where it can see the fault."""

        config = replace(
            sil_p0b(5),
            fault_plan=(
                FaultSpec(
                    FaultKind.POSE_BIAS_RAMP, 3.0, duration_s=120.0, magnitude=0.10
                ),
            ),
        )
        result = run_episode(config, 5)
        reasons = [e.detail for e in result.events if e.kind is EventKind.ABORT]
        self.assertIn("pose_jump_detected", reasons)
        self.assertEqual(result.unsafe_events, ())

    def test_slow_bias_ramp_reproduces_the_documented_residual(self) -> None:
        """SIL-005 is demonstrated by the twin, not merely argued from analysis.

        docs/digital-twin.md finding 3 says a bias that ramps slowly is
        invisible to a single-source estimator and walks the aircraft into the
        funnel rim.  Until the ramp fault existed the twin could only inject
        steps, which the jump detector always catches, so the model could show
        the defence working and never show it failing.

        At 0.02 m/s — 0.4 mm per step against a 30 mm threshold — the detector
        never fires and the aircraft crosses the entrance plane outside the
        90 mm funnel radius.  This test pins that the residual is real and
        reachable.  If it starts passing without a deliberate design change,
        something has silently altered the fault model or the guidance, and the
        risk acceptance rests on a demonstration that no longer holds.
        """

        config = sil_p0b(0)
        ramp_rate = 0.02
        self.assertLess(
            ramp_rate * config.dt_s,
            config.guidance.pose_jump_threshold_m,
            "the ramp must be invisible to the detector for this test to mean anything",
        )

        contacts = detected = 0
        trials = 15
        for seed in range(trials):
            episode = replace(
                sil_p0b(seed),
                fault_plan=(
                    FaultSpec(
                        FaultKind.POSE_BIAS_RAMP,
                        3.0,
                        duration_s=120.0,
                        magnitude=ramp_rate,
                    ),
                ),
            )
            result = run_episode(episode, seed)
            if any(e.kind is EventKind.PROP_FUNNEL_CONTACT for e in result.events):
                contacts += 1
            if any(
                e.kind is EventKind.ABORT and e.detail == "pose_jump_detected"
                for e in result.events
            ):
                detected += 1

        # Detection is incidental, not reliable: a dropout lets the ramp
        # accumulate, so recovery sometimes looks like a step and trips the
        # detector.  That is luck, not a defence, and the majority of episodes
        # get no warning at all.
        self.assertLess(
            detected,
            trials,
            "the detector caught every episode; the ramp is no longer the "
            "undetectable case this test exists to hold",
        )
        self.assertGreater(
            contacts,
            0,
            "the accepted residual SIL-005 is no longer reproducible; if that "
            "is the result of a deliberate mitigation, update the acceptance",
        )

    def test_ramp_fault_is_excluded_from_the_random_gate_menu(self) -> None:
        """An accepted, characterised residual does not belong in a gate lottery.

        Sampling SIL-005 a few percent of the time would fail gates at random
        without adding information, and would tempt someone to weaken the
        criterion.  It is characterised by the nav-bias-ramp-sweep study
        instead.
        """

        from aiur.sim.faults import _FAULT_MENU

        self.assertNotIn(FaultKind.POSE_BIAS_RAMP, _FAULT_MENU)


class ControllerResetFaultTests(unittest.TestCase):
    def _seated_captured_dock(self) -> DockAssembly:
        dock = DockAssembly(DockGeometry(), dt_s=0.02)
        # Drive the real controller to CAPTURED through legitimate inputs.
        dock.seat_switch.fault = SwitchFault.STUCK_CLOSED
        dock.keeper_switch.fault = SwitchFault.NONE
        t = 0.0
        for _ in range(80):
            dock.step(t, Vec3(), Vec3(), None, DockCommands(capture_enable=True))
            t += 0.02
        return dock

    def test_reset_replaces_the_controller_but_not_the_mechanism(self) -> None:
        dock = self._seated_captured_dock()
        before = dock.controller
        servo_position = dock.servo.position
        probe_phase = dock.probe_phase

        dock.reset_controller()

        self.assertIsNot(dock.controller, before)
        self.assertEqual(dock.controller.state, DockState.OPEN)
        # A power blip does not move hardware.
        self.assertEqual(dock.servo.position, servo_position)
        self.assertEqual(dock.probe_phase, probe_phase)

    def test_reset_fault_actually_perturbs_the_episode(self) -> None:
        """Activating is not the same as testing anything.

        An earlier window put the reset at 2-10 s, but nominal captures land
        between about 10 s and 35 s, so the reset always arrived while the dock
        was open — where restarting the controller is indistinguishable from
        not restarting it.  The FAULT_INJECTED event fired and the episode was
        byte-identical to nominal, which is a fault quota that measures
        nothing.  The window must reach the keeper.
        """

        seed = 3
        baseline = run_episode(sil_p0b(seed), seed)
        capture = next(
            e.t_s for e in baseline.events if e.kind is EventKind.CAPTURE_CONFIRMED
        )

        config = replace(
            sil_p0b(seed),
            fault_plan=(FaultSpec(FaultKind.CONTROLLER_RESET, capture, duration_s=0.5),),
        )
        result = run_episode(config, seed)

        self.assertTrue(
            any(e.kind is EventKind.FAULT_INJECTED for e in result.events),
            "controller reset never activated",
        )
        perturbed = [
            (e.kind, round(e.t_s, 2))
            for e in result.events
            if e.kind is not EventKind.FAULT_INJECTED
        ]
        self.assertNotEqual(
            perturbed,
            [(e.kind, round(e.t_s, 2)) for e in baseline.events],
            "the reset changed nothing; it landed where the dock was open",
        )
        self.assertEqual(result.unsafe_events, ())

    def test_reset_at_the_capture_instant_does_not_strand_the_aircraft(self) -> None:
        """Regression: the abort retry must not re-latch the dock it is leaving.

        ``reset_fault`` means opposite things in the two fault states.  In
        FAULT_OPEN it clears only while both switches read open, so it is a
        safe retry.  In FAULT_LOCKED it clears while both read closed — it
        confirms a capture — so sending it during an abort re-captured the
        aircraft the supervisor had just decided to leave, and guidance and
        mechanism then waited for each other until the episode timed out with
        the vehicle armed and held.
        """

        for seed in (0, 1, 2, 3, 7):
            baseline = run_episode(sil_p0b(seed), seed)
            capture = [
                e.t_s for e in baseline.events if e.kind is EventKind.CAPTURE_CONFIRMED
            ]
            if not capture:
                continue
            config = replace(
                sil_p0b(seed),
                fault_plan=(
                    FaultSpec(FaultKind.CONTROLLER_RESET, capture[0], duration_s=0.5),
                ),
            )
            result = run_episode(config, seed)
            self.assertEqual(result.unsafe_events, (), f"seed {seed}")
            self.assertNotEqual(
                result.outcome.value,
                "timeout",
                f"seed {seed} deadlocked: guidance and dock disagreed until timeout",
            )


if __name__ == "__main__":
    unittest.main()
