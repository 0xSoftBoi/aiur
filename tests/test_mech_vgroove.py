"""Tests for the V-trough / over-centre-latch capture candidate.

Two jobs, and the second is the one that matters.

The first is the obvious one: does ``aiur.sim.mech_vgroove`` satisfy the
``CaptureMechanism`` contract, capture under nominal conditions, and release
what it captured.

The second is to make every claim in ``SPEC.known_weaknesses`` falsifiable.
A candidate in a trade study is judged partly on its own honesty report, so
an unexercised weakness list is worth nothing — it costs the author nothing
to write and the reader cannot check it.  Each weakness therefore has a test
below that reproduces it, and one of them (the smaller trough mouth) is
tested against the baseline's own geometry so the comparison is explicit
rather than asserted.
"""

from __future__ import annotations

from dataclasses import replace
import math
import unittest

from aiur.dock_controller import DockState
from aiur.sim.bodies import DroneBody, DroneParams
from aiur.sim.disturbances import outdoor_breeze
from aiur.sim.dock_physics import DockCommands, DockGeometry, ProbePhase
from aiur.sim.engine import EpisodeOutcome, run_episode
from aiur.sim.events import UNSAFE_EVENT_KINDS, EventKind
from aiur.sim.faults import FaultKind
from aiur.sim.mech_vgroove import (
    SPEC,
    KNOWN_WEAKNESSES,
    OverCentreLatch,
    OverCentreLatchParams,
    VGrooveGeometry,
    VGrooveMechanism,
    VGrooveStepResult,
    vgroove_factory,
)
from aiur.sim.mechanism import CaptureMechanism, MechanismSpec
from aiur.sim.scenarios import sil_p0b, sil_p0c
from aiur.sim.sensors import SwitchFault
from aiur.sim.vec import ZERO, Vec3

DT = 0.02  # engine step, 50 Hz
DOCK_CENTER = Vec3(0.0, 0.0, 2.0)


class MechanismHarness(unittest.TestCase):
    """Drives one mechanism directly, with the aircraft flown by hand.

    The engine is not involved: these tests are about the mechanism's own
    physics and its truth-versus-indication behaviour, and mixing in the
    guidance stack would make a failure ambiguous between the two.
    """

    def setUp(self) -> None:
        self.mech = VGrooveMechanism(dt_s=DT)
        self.geometry = self.mech.geometry
        self.drone = DroneBody(DroneParams(), Vec3(0.0, 0.0, 1.0))
        self.t = 0.0

    # -- driving helpers --------------------------------------------------

    def place_tip(self, rel: Vec3) -> None:
        """Put the cross-bar at ``rel`` relative to the dock reference."""

        self.drone.position = (
            DOCK_CENTER + rel - Vec3(0.0, 0.0, self.geometry.probe_height_m)
        )

    def tip_rel(self) -> Vec3:
        return (
            self.drone.position
            + Vec3(0.0, 0.0, self.geometry.probe_height_m)
            - DOCK_CENTER
        )

    def drive(
        self,
        steps: int,
        *,
        climb_m_s: float = 0.0,
        commands: DockCommands | None = None,
        until=None,
    ) -> list[VGrooveStepResult]:
        """Fly the aircraft at a fixed relative vertical rate and step."""

        results: list[VGrooveStepResult] = []
        cmd = commands if commands is not None else DockCommands()
        for _ in range(steps):
            if self.drone.armed:
                self.drone.position = self.drone.position + Vec3(
                    0.0, 0.0, climb_m_s * DT
                )
                self.drone.velocity = Vec3(0.0, 0.0, climb_m_s)
            result = self.mech.step(self.t, DOCK_CENTER, ZERO, self.drone, cmd)
            results.append(result)
            self.t += DT
            if until is not None and until(result):
                break
        return results

    def seat_bar(self, *, climb_m_s: float = 0.05) -> list[VGrooveStepResult]:
        """Fly the bar up from below the mouth until it seats."""

        self.place_tip(Vec3(0.0, 0.0, self.geometry.mouth_z_m - 0.02))
        results = self.drive(
            400,
            climb_m_s=climb_m_s,
            until=lambda r: r.probe_phase is ProbePhase.SEATED,
        )
        return results

    def capture(self) -> list[VGrooveStepResult]:
        """Seat, then let the real controller latch, and disarm on confirm."""

        results = self.seat_bar()
        self.assertIs(self.mech.probe_phase, ProbePhase.SEATED, "bar failed to seat")
        results += self.drive(
            200,
            climb_m_s=0.03,
            commands=DockCommands(capture_enable=True),
            until=lambda r: r.controller.capture_confirmed,
        )
        self.assertTrue(results[-1].controller.capture_confirmed, "never captured")
        # The engine disarms only on a confirmed capture; mirror that, because
        # a disarmed aircraft is the only condition under which the mechanism
        # is the sole thing holding it.
        self.drone.disarm()
        return results

    @staticmethod
    def kinds(results) -> list[EventKind]:
        return [event.kind for result in results for event in result.events]


class ContractTests(MechanismHarness):
    def test_satisfies_the_capture_mechanism_protocol(self) -> None:
        self.assertIsInstance(self.mech, CaptureMechanism)
        self.assertIsInstance(SPEC, MechanismSpec)
        self.assertEqual(SPEC.key, "vgroove")

    def test_spec_build_returns_a_ready_mechanism(self) -> None:
        built = SPEC.build(DT)
        self.assertIsInstance(built, CaptureMechanism)
        self.assertIs(built.probe_phase, ProbePhase.FREE)
        # Ready means it can be stepped immediately with no further setup.
        result = built.step(0.0, DOCK_CENTER, ZERO, None, DockCommands())
        self.assertIs(result.probe_phase, ProbePhase.FREE)
        self.assertFalse(result.controller.capture_confirmed)

    def test_step_result_is_a_dock_step_result(self) -> None:
        """The engine and guidance consume the baseline type; do not break it."""

        from aiur.sim.dock_physics import DockStepResult

        result = self.mech.step(0.0, DOCK_CENTER, ZERO, None, DockCommands())
        self.assertIsInstance(result, DockStepResult)

    def test_fault_injector_reaches_this_mechanism(self) -> None:
        """The shared injector writes servo.jammed and reads the switches."""

        self.mech.servo.jammed = True
        self.assertTrue(self.mech.latch.jammed)
        self.mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        self.mech.keeper_switch.fault = SwitchFault.STUCK_OPEN
        result = self.mech.step(0.0, DOCK_CENTER, ZERO, None, DockCommands())
        self.assertTrue(result.reported_s1)
        self.assertFalse(result.reported_s2)

    def test_seed_seated_supports_the_launch_scenarios(self) -> None:
        self.mech.seed_seated(self.drone, DOCK_CENTER, ZERO)
        self.assertIs(self.mech.probe_phase, ProbePhase.SEATED)
        self.assertAlmostEqual(self.tip_rel().z, self.geometry.seat_travel_m)
        self.assertEqual(self.mech.bar_yaw_error_rad, 0.0)

    def test_geometry_rejects_impossible_troughs(self) -> None:
        with self.assertRaises(ValueError):
            VGrooveGeometry(trough_seat_half_width_m=0.10)
        with self.assertRaises(ValueError):
            VGrooveGeometry(trough_depth_m=0.0)
        with self.assertRaises(ValueError):
            # The status switch must not be able to trip before the latch is
            # bistable; that ordering is a safety rule, not a preference.
            OverCentreLatchParams(switch_trip_position=0.5)


class NominalCaptureTests(MechanismHarness):
    def test_captures_a_nominally_aligned_bar(self) -> None:
        results = self.capture()
        kinds = self.kinds(results)
        self.assertIn(EventKind.FUNNEL_INSERTION, kinds)
        self.assertIn(EventKind.PROBE_SEATED, kinds)
        self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds)
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds)
        final = results[-1]
        self.assertTrue(final.seat_truth)
        self.assertTrue(final.keeper_closed_truth)
        self.assertTrue(final.latch_over_centre)

    def test_engine_captures_across_seeds_at_the_default_yaw(self) -> None:
        """The smoke test, as a regression: sil-p0b with this mechanism."""

        build = lambda cfg, dt: SPEC.build(dt)  # noqa: E731
        outcomes = []
        for seed in range(1, 13):
            config = replace(sil_p0b(seed), mechanism_factory=build)
            result = run_episode(config, seed)
            outcomes.append(result)
            self.assertEqual(result.unsafe_events, ())
        self.assertTrue(all(r.captures >= 1 for r in outcomes))
        self.assertTrue(all(r.outcome is EpisodeOutcome.SUCCESS for r in outcomes))

    def test_engine_launch_and_recover_cycle(self) -> None:
        """Pre-roll capture, commanded release, departure, and re-capture."""

        build = lambda cfg, dt: SPEC.build(dt)  # noqa: E731
        for seed in (1, 2, 3):
            config = replace(sil_p0c(seed), mechanism_factory=build)
            result = run_episode(config, seed)
            self.assertEqual(result.unsafe_events, ())
            self.assertIs(result.outcome, EpisodeOutcome.SUCCESS)
            kinds = [event.kind for event in result.events]
            self.assertIn(EventKind.RELEASED, kinds)
            self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds)

    def test_episodes_are_deterministic(self) -> None:
        build = lambda cfg, dt: SPEC.build(dt)  # noqa: E731
        config = replace(sil_p0b(7), mechanism_factory=build)
        first = run_episode(config, 7)
        second = run_episode(config, 7)
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.duration_s, second.duration_s)

    def test_no_injected_fault_produces_an_unsafe_event(self) -> None:
        build = lambda cfg, dt: SPEC.build(dt)  # noqa: E731
        for seed in range(1, 25):
            for kwargs in ({"with_fault": True}, {"correlated_fault": True}):
                config = replace(sil_p0b(seed, **kwargs), mechanism_factory=build)
                result = run_episode(config, seed)
                self.assertEqual(
                    result.unsafe_events,
                    (),
                    f"seed={seed} {kwargs} produced {result.unsafe_events}",
                )


class TruthVersusIndicationTests(MechanismHarness):
    def test_a_commanded_latch_is_not_evidence_of_capture(self) -> None:
        """Jam the latch shut at zero travel and command close anyway.

        The controller commands CLOSE for a full lock timeout and nothing is
        confirmed, because confirmation runs off sensed state.  This is the
        architecture's non-negotiable property stated as a test.
        """

        self.seat_bar()
        self.mech.latch.jammed = True
        results = self.drive(
            120, climb_m_s=0.03, commands=DockCommands(capture_enable=True)
        )
        commanded_close = any(
            r.controller.keeper_command.value == "close" for r in results
        )
        self.assertTrue(commanded_close, "the controller never even tried")
        self.assertFalse(any(r.controller.capture_confirmed for r in results))
        self.assertFalse(any(r.keeper_closed_truth for r in results))
        self.assertIs(results[-1].controller.state, DockState.FAULT_OPEN)
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, self.kinds(results))

    def test_false_capture_on_an_empty_trough_is_reported_as_false(self) -> None:
        """S1 stuck actuated with no aircraft: the empty-trough cut set.

        Inherited unchanged from the baseline (dock-fmeca TOP-2 branch G2-1),
        and the point of the test is that the mechanism *says so* rather than
        recording a clean capture.
        """

        self.mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        results = []
        for _ in range(120):
            results.append(
                self.mech.step(
                    self.t,
                    DOCK_CENTER,
                    ZERO,
                    None,
                    DockCommands(capture_enable=True),
                )
            )
            self.t += DT
        kinds = self.kinds(results)
        self.assertIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds)
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds)
        confirmed = [r for r in results if r.controller.capture_confirmed]
        self.assertTrue(confirmed)
        # Indication says captured; truth says there is nothing in the trough.
        self.assertTrue(all(r.reported_s1 and r.reported_s2 for r in confirmed))
        self.assertFalse(any(r.seat_truth for r in confirmed))

    def test_retention_truth_leads_the_status_switch(self) -> None:
        """The bail is under the bar before the switch says it is.

        The safe ordering: an early-tripping switch would confirm a capture
        on a partial engagement (FM-KP-02 / FM-SN-08), so the model is built
        with the trip point after engagement and the test pins that order.
        """

        self.seat_bar()
        results = self.drive(
            60,
            climb_m_s=0.03,
            commands=DockCommands(capture_enable=True),
            until=lambda r: r.reported_s2,
        )
        first_truth = next(i for i, r in enumerate(results) if r.keeper_closed_truth)
        first_reported = next(i for i, r in enumerate(results) if r.reported_s2)
        self.assertLess(first_truth, first_reported)

    def test_controller_brownout_keeps_the_mechanism(self) -> None:
        """Logic restarts, hardware does not: the latch stays where it was."""

        self.capture()
        position = self.mech.latch.position
        self.mech.reset_controller()
        result = self.mech.step(self.t, DOCK_CENTER, ZERO, self.drone, DockCommands())
        self.assertEqual(self.mech.latch.position, position)
        self.assertTrue(result.keeper_closed_truth)
        # The restarted controller finds both switches made over an occupied
        # seat and holds, rather than commanding open onto a hanging aircraft.
        self.assertIs(result.controller.state, DockState.FAULT_LOCKED)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, self.kinds([result]))


class ReleaseTests(MechanismHarness):
    def test_release_works_under_load(self) -> None:
        """The Rev-A defect was a keeper that could not let go.  This can."""

        self.capture()
        self.assertFalse(self.drone.armed)
        results = self.drive(
            120,
            commands=DockCommands(release_request=True),
            until=lambda r: not r.keeper_closed_truth,
        )
        self.assertFalse(results[-1].keeper_closed_truth)
        self.assertFalse(any(r.release_stalled for r in results))
        kinds = self.kinds(results)
        self.assertIn(EventKind.RELEASED, kinds)
        # Commanded release is not a drop.
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, kinds)
        # And the latch actually reaches the open stop, not just past centre.
        self.drive(60, commands=DockCommands(release_request=True))
        self.assertTrue(self.mech.latch.physically_open)

    def test_emergency_release_works_under_load(self) -> None:
        self.capture()
        results = self.drive(
            120,
            commands=DockCommands(emergency_release=True),
            until=lambda r: not r.keeper_closed_truth,
        )
        self.assertFalse(results[-1].keeper_closed_truth)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, self.kinds(results))

    def test_an_undersized_drive_cannot_release_and_says_so(self) -> None:
        """The model is able to fail the Rev-A way, which is why it is credible.

        Give the drive less force margin than the loaded toggle needs.  The
        latch stalls at the toggle, the aircraft stays mechanically retained,
        and the model reports both facts.

        It also reproduces the last entry in ``SPEC.known_weaknesses``, which
        was written *because* this test found it.  S2 senses the over-centre
        stop, so it goes open the moment the linkage leaves that stop —
        while the bail is still across the bar.  The controller therefore
        sees a completed release, emits ``RELEASED``, and never trips its
        release timeout (which needs the switch to stay made), all with an
        aircraft still hanging on the latch.  Indication and truth disagree
        in the dangerous direction, and the only reason that is visible at
        all is that this module keeps them apart.
        """

        self.mech = VGrooveMechanism(
            latch_params=OverCentreLatchParams(release_force_margin=1.2),
            dt_s=DT,
        )
        self.capture()
        results = self.drive(150, commands=DockCommands(release_request=True))
        self.assertTrue(any(r.release_stalled for r in results))
        final = results[-1]
        # Truth: still held.
        self.assertTrue(final.keeper_closed_truth, "silently let go")
        self.assertGreater(
            final.latch_position, self.mech.latch.params.engage_position
        )
        # Indication: the controller believes the dock let go.
        self.assertFalse(final.reported_s2)
        self.assertIn(EventKind.RELEASED, self.kinds(results))
        self.assertIs(final.controller.state, DockState.RELEASING)
        # Nothing was dropped and nothing claims a capture.
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, self.kinds(results))
        self.assertFalse(final.controller.capture_confirmed)


class YawWeaknessTests(MechanismHarness):
    """Weakness 1 and 2: the V leaves yaw free, and the yaw model is invented."""

    def test_a_badly_yawed_bar_never_seats(self) -> None:
        self.mech = VGrooveMechanism(dt_s=DT, yaw_error_rad=math.radians(30.0))
        self.place_tip(Vec3(0.0, 0.0, self.mech.geometry.mouth_z_m - 0.02))
        results = self.drive(500, climb_m_s=0.05)
        self.assertIs(self.mech.probe_phase, ProbePhase.INSERTED)
        self.assertNotIn(EventKind.PROBE_SEATED, self.kinds(results))
        # It entered the trough and then wedged short of the apex.
        self.assertIn(EventKind.FUNNEL_INSERTION, self.kinds(results))
        self.assertLess(
            results[-1].bar_height_above_mouth_m, self.mech.geometry.trough_depth_m
        )
        # Past the wedge limit the flanks self-lock: no derotation at all.
        self.assertAlmostEqual(
            results[-1].bar_yaw_error_rad, math.radians(30.0), places=9
        )

    def test_a_moderately_yawed_bar_seats_late(self) -> None:
        """Between aligned and wedged the architecture degrades, not fails."""

        aligned = VGrooveMechanism(dt_s=DT, yaw_error_rad=0.0)
        yawed = VGrooveMechanism(dt_s=DT, yaw_error_rad=math.radians(10.0))
        times = []
        for mech in (aligned, yawed):
            self.mech = mech
            self.drone = DroneBody(DroneParams(), Vec3(0.0, 0.0, 1.0))
            self.t = 0.0
            results = self.seat_bar()
            self.assertIs(mech.probe_phase, ProbePhase.SEATED)
            times.append(len(results))
        self.assertGreater(times[1], times[0] + 20, "yaw cost no time at all")

    def test_capture_rate_collapses_with_arrival_yaw(self) -> None:
        """The weakness at episode level, through the real guidance stack."""

        seeds = range(1, 13)
        rates = {}
        for degrees in (0.0, 5.0, 20.0, 30.0):
            build = vgroove_factory(yaw_error_rad=math.radians(degrees))
            captures = 0
            for seed in seeds:
                config = replace(sil_p0b(seed), mechanism_factory=build)
                result = run_episode(config, seed)
                captures += 1 if result.captures else 0
                # Failing on yaw must be safe: abort, never a strike.
                self.assertEqual(result.unsafe_events, ())
            rates[degrees] = captures
        self.assertEqual(rates[0.0], len(seeds))
        self.assertEqual(rates[5.0], len(seeds))
        self.assertEqual(rates[30.0], 0)
        self.assertLess(rates[20.0], rates[5.0])

    def test_the_yaw_default_is_a_parameter_not_a_law(self) -> None:
        """Weakness 2: nothing in the twin supplies yaw, so this is an input."""

        self.assertAlmostEqual(VGrooveGeometry().nominal_yaw_error_rad, 0.087, places=3)
        self.assertNotEqual(
            VGrooveMechanism(dt_s=DT, yaw_error_rad=0.2).bar_yaw_error_rad,
            VGrooveMechanism(dt_s=DT).bar_yaw_error_rad,
        )


class BistabilityTests(MechanismHarness):
    """Weakness 4 and 7: bistability starts at dead centre, and is untested
    by the shared fault menu."""

    def test_a_dead_actuator_past_centre_holds_the_aircraft(self) -> None:
        self.capture()
        self.mech.latch.powered = False
        # Command open anyway: with no drive authority the toggle spring wins.
        results = self.drive(100, commands=DockCommands(emergency_release=True))
        self.assertTrue(results[-1].keeper_closed_truth)
        self.assertEqual(self.mech.latch.position, 1.0)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, self.kinds(results))

    def test_a_dead_actuator_short_of_centre_drops_the_aircraft(self) -> None:
        """The cost of the same property, reported as a drop, not hidden."""

        self.capture()
        params = self.mech.latch.params
        # Park the linkage in the band that is engaged but not yet bistable —
        # fault-tree branch G1-2a.  Set directly because no command sequence
        # can hold a toggle latch mid-travel, which is itself the point.
        self.mech.latch.position = 0.5 * (
            params.engage_position + params.centre_position
        )
        self.assertTrue(self.mech.latch.engaged)
        self.assertFalse(self.mech.latch.over_centre)
        self.mech.latch.powered = False
        results = self.drive(100, commands=DockCommands(capture_enable=True))
        self.assertIn(EventKind.DROPPED_AIRCRAFT, self.kinds(results))
        self.assertEqual(self.mech.latch.position, 0.0)

    def test_the_shared_fault_menu_cannot_test_this(self) -> None:
        """Weakness 7, as an assertion about the repository, not a promise.

        If a power-loss fault is ever added to aiur/sim/faults.py this test
        fails, and the weakness text must be rewritten.  That is the intent:
        the claim expires when the gap closes.
        """

        names = {kind.value for kind in FaultKind}
        self.assertFalse([name for name in names if "power" in name])
        self.assertIn("keeper_servo_jam", names)


class AbortOpacityTests(MechanismHarness):
    """Weakness 5: once the bail is in the trough the aircraft is trapped."""

    def test_a_closing_bail_blocks_departure(self) -> None:
        """Mid-travel: the bar is trapped for as long as the bail is across.

        It does eventually get out, and the reason is worth stating: pulling
        down 14 mm unseats the seat switch, the controller calls
        ``probe_lost_during_lock`` and retracts the bail.  Software let it
        go; the mechanism never did.
        """

        self.seat_bar()
        self.drive(
            30,
            climb_m_s=0.03,
            commands=DockCommands(capture_enable=True),
            until=lambda r: r.latch_position >= self.geometry.bail_in_throat_position,
        )
        self.assertFalse(
            self.mech.latch.engaged, "already latched; not the case under test"
        )
        results = self.drive(
            40, climb_m_s=-0.20, commands=DockCommands(capture_enable=True)
        )
        blocked = [r for r in results if r.abort_blocked]
        self.assertTrue(blocked, "the bail did not obstruct the departure at all")
        for result in blocked:
            tip_z = result.bar_height_above_mouth_m + self.geometry.mouth_z_m
            self.assertGreaterEqual(tip_z, self.geometry.bail_plane_z_m - 1e-9)

    def test_a_latched_bail_blocks_departure_outright(self) -> None:
        """Past engagement there is no abort at all without a release command."""

        self.seat_bar()
        self.drive(
            60,
            climb_m_s=0.03,
            commands=DockCommands(capture_enable=True),
            until=lambda r: r.keeper_closed_truth,
        )
        self.assertTrue(self.mech.latch.engaged)
        self.assertTrue(self.drone.armed, "this is an abort, not a capture")
        results = self.drive(
            60, climb_m_s=-0.30, commands=DockCommands(capture_enable=True)
        )
        self.assertIs(self.mech.probe_phase, ProbePhase.SEATED)
        self.assertTrue(results[-1].seat_truth)
        self.assertAlmostEqual(self.tip_rel().z, self.geometry.seat_travel_m)
        self.assertNotIn(EventKind.PROBE_WITHDRAWN, self.kinds(results))

    def test_an_open_bail_lets_the_aircraft_leave(self) -> None:
        """The same test with no bail closing: departure is free.

        Weakness 8 as well — a V seat has no axial retention whatever, so an
        unlatched bar leaves on any downward relative motion.
        """

        self.seat_bar()
        results = self.drive(80, climb_m_s=-0.05)
        kinds = self.kinds(results)
        self.assertIn(EventKind.PROBE_WITHDRAWN, kinds)
        self.assertIs(self.mech.probe_phase, ProbePhase.FREE)


class AcceptanceGeometryTests(MechanismHarness):
    """Weakness 6: the trough mouth is smaller than the Ø180 mm funnel."""

    def cross_at(self, x: float, y: float):
        self.place_tip(Vec3(x, y, self.geometry.mouth_z_m - 0.01))
        self.drive(1, climb_m_s=0.05)
        self.place_tip(Vec3(x, y, self.geometry.mouth_z_m + 0.001))
        return self.drive(1, climb_m_s=0.05)

    def test_an_arrival_the_funnel_would_swallow_is_a_structure_contact(self) -> None:
        offset = 0.070
        baseline_radius = DockGeometry().funnel_entrance_radius_m
        self.assertLess(
            offset,
            baseline_radius,
            "pick an offset the baseline funnel actually accepts",
        )
        self.assertGreater(offset, self.geometry.trough_mouth_half_width_m)
        results = self.cross_at(0.0, offset)
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, self.kinds(results))
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, UNSAFE_EVENT_KINDS)
        self.assertIs(self.mech.probe_phase, ProbePhase.FREE)

    def test_the_smaller_mouth_costs_unsafe_episodes_under_wind(self) -> None:
        """The weakness that decides the trade, pinned as a regression.

        Indoor calm hides it; 1.0 m/s of wind does not.  The guidance loop's
        steady-state offset under mean wind puts the bar outside a 110 mm
        trough that a Ø180 mm funnel would have swallowed, and the guarded
        prop meets the structure.  The baseline is clean over the same seeds,
        so this is a property of the mechanism and not of the weather.
        """

        build = lambda cfg, dt: SPEC.build(dt)  # noqa: E731
        seeds = (8, 19, 26)  # found by sweeping 1..40; see known_weaknesses
        contacts = 0
        for seed in seeds:
            config = sil_p0b(seed, air=outdoor_breeze(1.0))
            baseline = run_episode(config, seed)
            self.assertEqual(baseline.unsafe_events, (), f"baseline seed={seed}")
            candidate = run_episode(replace(config, mechanism_factory=build), seed)
            kinds = [event.kind for event in candidate.unsafe_events]
            contacts += kinds.count(EventKind.PROP_FUNNEL_CONTACT)
        self.assertEqual(contacts, len(seeds))

    def test_indoor_calm_hides_the_smaller_mouth(self) -> None:
        """Which is exactly why the weakness has to be stated, not measured once."""

        build = lambda cfg, dt: SPEC.build(dt)  # noqa: E731
        for seed in (8, 19, 26):
            config = replace(sil_p0b(seed), mechanism_factory=build)
            self.assertEqual(run_episode(config, seed).unsafe_events, ())

    def test_the_mouth_is_anisotropic(self) -> None:
        """Along the groove it accepts what it rejects across the groove."""

        offset = 0.065
        along = self.cross_at(offset, 0.0)
        self.assertIn(EventKind.FUNNEL_INSERTION, self.kinds(along))

        self.setUp()
        across = self.cross_at(0.0, offset)
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, self.kinds(across))

    def test_overspeed_arrival_is_reported_and_bounces(self) -> None:
        self.place_tip(Vec3(0.0, 0.0, self.geometry.mouth_z_m - 0.01))
        self.drive(1, climb_m_s=0.40)
        self.place_tip(Vec3(0.0, 0.0, self.geometry.mouth_z_m + 0.001))
        results = self.drive(1, climb_m_s=0.40)
        self.assertIn(EventKind.OVERSPEED_CONTACT, self.kinds(results))
        self.assertIn(EventKind.OVERSPEED_CONTACT, UNSAFE_EVENT_KINDS)
        self.assertIs(self.mech.probe_phase, ProbePhase.FREE)
        self.assertLess(self.drone.velocity.z, 0.0)


class SensedChannelTests(MechanismHarness):
    """Weakness 3: two channels, neither of which senses a bar."""

    def test_the_latch_reaches_its_stop_on_an_empty_trough(self) -> None:
        latch = OverCentreLatch()
        for _ in range(100):
            latch.step(DT, True, False)
        self.assertTrue(latch.physically_closed)
        # Nothing in the sensed set can tell this from a real capture; only
        # S1, which is the channel the empty-trough cut set defeats.
        self.assertEqual(SPEC.sensed_channels, 2)

    def test_weakness_list_is_populated_and_shared_with_the_spec(self) -> None:
        self.assertGreaterEqual(len(KNOWN_WEAKNESSES), 5)
        self.assertEqual(SPEC.known_weaknesses, KNOWN_WEAKNESSES)
        self.assertTrue(all(isinstance(text, str) and text for text in KNOWN_WEAKNESSES))


class LatchUnitTests(unittest.TestCase):
    def test_the_toggle_band_costs_time_in_both_directions(self) -> None:
        latch = OverCentreLatch()
        p = latch.params
        band_steps = 0
        outside_steps = 0
        while latch.position < 1.0:
            in_band = abs(latch.position - p.centre_position) <= p.band_half_width
            latch.step(DT, True, False)
            if in_band:
                band_steps += 1
            else:
                outside_steps += 1
        band_width = 2.0 * p.band_half_width
        # Time per unit travel is higher inside the band than outside it.
        self.assertGreater(band_steps / band_width, outside_steps / (1.0 - band_width))

    def test_unpowered_latch_seeks_the_nearer_stable_end(self) -> None:
        for start, expected in ((0.95, 1.0), (0.80, 0.0), (0.30, 0.0)):
            latch = OverCentreLatch()
            latch.position = start
            latch.powered = False
            for _ in range(200):
                latch.step(DT, True, False)
            self.assertEqual(latch.position, expected, f"from {start}")

    def test_a_jam_freezes_the_linkage(self) -> None:
        latch = OverCentreLatch()
        latch.position = 0.4
        latch.jammed = True
        for _ in range(50):
            latch.step(DT, True, False)
        self.assertEqual(latch.position, 0.4)


if __name__ == "__main__":
    unittest.main()
