"""Tests for the three-jaw iris capture candidate (aiur/sim/mech_iris.py).

The point of these tests is not that the iris works.  It is that when the
iris does not work, the twin says so.  Every claim the candidate makes in
``SPEC.known_weaknesses`` is exercised here against the model, so a reader
can check that the weaknesses are real rather than modest.

Bench tests drive the drone kinematically (position/velocity set between
mechanism steps), matching tests/test_sim_sensors_dock.py.  Episode tests
run the real engine, the real guidance stack, and the real DockController.
Everything is deterministic: fixed seeds, fixed step, no wall clock.
"""

import unittest
from dataclasses import replace

from aiur.dock_controller import DockState
from aiur.sim.bodies import DroneBody, DroneParams
from aiur.sim.dock_physics import DockCommands, ProbePhase
from aiur.sim.engine import EpisodeOutcome, run_episode
from aiur.sim.events import UNSAFE_EVENT_KINDS, EventKind
from aiur.sim.mech_iris import (
    JAW_COUNT,
    SPEC,
    IrisGeometry,
    IrisMechanism,
    iris_mechanism_factory,
)
from aiur.sim.mechanism import CaptureMechanism, MechanismSpec
from aiur.sim.scenarios import sil_p0b, sil_p0c
from aiur.sim.sensors import SwitchFault
from aiur.sim.vec import ZERO, Vec3

#: Engine fixed step (50 Hz), matching aiur/sim/engine.py.
DT = 0.02

#: Dock entrance-plane center used by every bench test.
CENTER = Vec3()

#: Seeds used for the smoke campaign.  Small and fixed so a regression is a
#: reproducible failure rather than a flake.
SMOKE_SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)


def bench(lateral_offset_m: float = 0.0, geometry: IrisGeometry | None = None):
    """An iris with a probe already seated, ready for the keeper sequence.

    Bypasses seed_seated for the offset cases on purpose: seed_seated centers
    the probe, and a test of centering must not be handed a centered probe.
    """

    mech = IrisMechanism(geometry or IrisGeometry(), dt_s=DT)
    g = mech.geometry
    drone = DroneBody(
        DroneParams(), Vec3(lateral_offset_m, 0.0, g.seat_travel_m - g.probe_height_m)
    )
    mech.probe_phase = ProbePhase.SEATED
    mech._prev_rel_z = g.seat_travel_m
    return mech, drone


def drive(mech, drone, commands, steps, t0=0.0):
    """Run ``steps`` mechanism steps, returning (all results, all events).

    Callers that want the *end* state take ``results[-1]``; callers testing a
    transient must search, because the real controller reopens the jaws on a
    lock timeout and the end state of a failed capture is an open dock.
    """

    results = []
    events = []
    t = t0
    for _ in range(steps):
        result = mech.step(t, CENTER, ZERO, drone, commands)
        results.append(result)
        events.extend(result.events)
        t += DT
    return results, events


def bench_with_bind(close_limit, jaw=1):
    """A seated bench iris with one linkage that will not close past a point."""

    mech, drone = bench()
    mech.jaw_close_limit[jaw] = close_limit
    return mech, drone


def pin_jaws(mech, closures):
    """Seize the jaw train at a fixed geometry, whatever the drive does.

    An injected linkage defect that will neither close further nor retract.
    Geometry tests need it because the controller times out on a capture
    that never confirms and commands the jaws open, which would erase the
    state under test before it could be inspected.
    """

    mech.jaw_close_limit = list(closures)
    mech.jaw_open_limit = list(closures)


def kinds(events):
    return [event.kind for event in events]


class ProtocolAndSpecTests(unittest.TestCase):
    def test_spec_and_mechanism_satisfy_the_study_protocols(self) -> None:
        self.assertIsInstance(SPEC, MechanismSpec)
        self.assertEqual(SPEC.key, "iris")
        mechanism = SPEC.build(DT)
        self.assertIsInstance(mechanism, CaptureMechanism)
        self.assertIs(mechanism.probe_phase, ProbePhase.FREE)

    def test_spec_does_not_inflate_its_sensed_channel_count(self) -> None:
        # Three jaw switches in series are one channel, not three.  If anyone
        # ever "improves" this number, they have to break this test first.
        self.assertEqual(SPEC.sensed_channels, 2)
        self.assertEqual(len(SPEC.build(DT).jaw_switches), JAW_COUNT)

    def test_geometry_rejects_a_band_that_does_not_discriminate(self) -> None:
        # The band is the entire empty-throat argument; a geometry where it
        # no longer brackets the mast must not be constructible.
        with self.assertRaises(ValueError):
            IrisGeometry(band_outer_reach_m=0.0012)  # inside the mast radius
        with self.assertRaises(ValueError):
            IrisGeometry(band_inner_reach_m=0.0002)  # below the empty stop
        with self.assertRaises(ValueError):
            IrisGeometry(band_outer_reach_m=0.0070)  # out past the head


class NominalCaptureTests(unittest.TestCase):
    def test_bench_capture_confirms_on_real_retention(self) -> None:
        mech, drone = bench()
        results, events = drive(mech, drone, DockCommands(capture_enable=True), 120)
        result = results[-1]

        self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds(events))
        self.assertIs(result.controller.state, DockState.CAPTURED)
        self.assertTrue(result.controller.capture_confirmed)
        # Truth and indication agree, and both are checked separately.
        self.assertTrue(result.keeper_closed_truth)
        self.assertTrue(result.head_above_jaws)
        self.assertTrue(result.reported_s1)
        self.assertTrue(result.reported_s2)
        self.assertEqual(result.jaw_reported, (True,) * JAW_COUNT)
        # All three jaws stopped on the mast, not on the head or on nothing.
        for reach in result.jaw_reaches_m:
            self.assertAlmostEqual(reach, mech.geometry.mast_radius_m, places=9)

    def test_confirmation_arrives_inside_the_controller_lock_timeout(self) -> None:
        # The band debounce is squeezed between the empty transit below and
        # this timeout above; if either bound moves, capture rate moves.
        mech, drone = bench()
        confirmed_at = None
        t = 0.0
        for _ in range(120):
            result = mech.step(t, CENTER, ZERO, drone, DockCommands(capture_enable=True))
            if result.controller.capture_confirmed and confirmed_at is None:
                confirmed_at = t
            t += DT
        self.assertIsNotNone(confirmed_at)
        self.assertLess(confirmed_at, mech.controller.lock_timeout_s)

    def test_sil_p0b_episodes_capture_and_produce_no_unsafe_events(self) -> None:
        for seed in SMOKE_SEEDS:
            with self.subTest(seed=seed):
                config = replace(sil_p0b(seed), mechanism_factory=iris_mechanism_factory)
                result = run_episode(config, seed)
                self.assertIs(result.outcome, EpisodeOutcome.SUCCESS)
                self.assertEqual(result.captures, 1)
                self.assertEqual(result.unsafe_events, ())
                self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds(result.events))

    def test_launch_then_recover_episode_works_from_the_engine_preroll(self) -> None:
        # sil_p0c starts captured, so the engine's pre-roll must be able to
        # walk the real controller to a confirmed capture through this
        # mechanism.  A candidate that cannot be seeded cannot host the
        # launch scenarios, which would itself be a finding.
        for seed in (1, 4, 9):
            with self.subTest(seed=seed):
                config = replace(sil_p0c(seed), mechanism_factory=iris_mechanism_factory)
                result = run_episode(config, seed)
                self.assertIs(result.outcome, EpisodeOutcome.SUCCESS)
                self.assertEqual(result.unsafe_events, ())

    def test_episodes_are_deterministic_for_a_fixed_seed(self) -> None:
        config = replace(sil_p0b(11), mechanism_factory=iris_mechanism_factory)
        self.assertEqual(run_episode(config, 11), run_episode(config, 11))


class RadialClosureTests(unittest.TestCase):
    """The architecture's headline claim, checked rather than asserted."""

    def test_closure_centers_a_mast_at_the_full_throat_offset(self) -> None:
        # docs/dock-deletion-review.md: the Ø16 mm throat allows 2.0 mm of
        # radial head offset, and the Rev-A fork's 4.2 mm slot accepts only
        # 0.6 mm of it.  The iris must accept the whole 2.0 mm.
        throat_offset_m = 0.0020
        rev_a_fork_acceptance_m = 0.0006
        self.assertGreater(throat_offset_m, rev_a_fork_acceptance_m)

        mech, drone = bench(lateral_offset_m=throat_offset_m)
        results, events = drive(mech, drone, DockCommands(capture_enable=True), 120)
        result = results[-1]

        self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertLess(result.mast_offset_m, 1e-6)
        self.assertEqual(result.jaw_reported, (True,) * JAW_COUNT)
        self.assertTrue(result.keeper_closed_truth)
        # The mast really did start where it was put and really did move.
        self.assertAlmostEqual(results[0].mast_offset_m, throat_offset_m, places=9)

    def test_the_jaws_do_the_centering_not_the_seat_model(self) -> None:
        # Control for the test above.  With no close command the probe must
        # stay exactly where it was put; if the seat model quietly recentered
        # it, the centering claim above would be vacuous.
        mech, drone = bench(lateral_offset_m=0.0020)
        results, _ = drive(mech, drone, DockCommands(), 120)
        self.assertAlmostEqual(results[-1].mast_offset_m, 0.0020, places=9)
        self.assertEqual(max(results[-1].jaw_closures), 0.0)


class NoCaptureWithoutRetentionTests(unittest.TestCase):
    def test_closing_on_an_empty_throat_never_reports_jaws_closed(self) -> None:
        # The single most important claim: S2' cannot be produced by an
        # empty mechanism.  A stuck seat switch drives the controller into
        # LOCKING with nothing in the dock, which is FMECA FM-KP-03.
        mech = IrisMechanism(dt_s=DT)
        mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        results, events = drive(mech, None, DockCommands(capture_enable=True), 200)

        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds(events))
        self.assertFalse(any(step.reported_s2 for step in results))
        self.assertIs(results[-1].controller.state, DockState.FAULT_OPEN)
        self.assertEqual(results[-1].controller.fault_reason, "lock_timeout")
        # The jaws really did drive all the way to their empty stop; the
        # refusal is discrimination, not a mechanism that never moved.
        self.assertAlmostEqual(max(max(s.jaw_closures) for s in results), 1.0)

    def test_empty_jaws_pass_through_the_band_but_the_switch_rejects_it(self) -> None:
        # Proof that the mechanism above is the debounce, not luck: the jaws
        # really do traverse the band, and the raw band predicate really is
        # true for several steps.  Only the debounce suppresses it.
        mech = IrisMechanism(dt_s=DT)
        mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        raw_in_band = 0
        t = 0.0
        for _ in range(60):
            result = mech.step(t, CENTER, ZERO, None, DockCommands(capture_enable=True))
            if mech._jaw_in_band(0):
                raw_in_band += 1
            self.assertFalse(result.reported_s2)
            t += DT
        self.assertGreater(raw_in_band, 1)

    def test_a_head_stalled_in_the_jaw_plane_is_not_a_capture(self) -> None:
        # The probe stops short with its Ø12 mm head level with the jaws.
        # The jaws stop on the head, far outside the band, so nothing
        # reports closed even though the jaws have physically stopped.
        mech = IrisMechanism(dt_s=DT)
        g = mech.geometry
        drone = DroneBody(
            DroneParams(),
            Vec3(0.0, 0.0, g.jaw_plane_z_m + 0.002 - g.probe_height_m),
        )
        mech.probe_phase = ProbePhase.INSERTED
        mech._prev_rel_z = g.jaw_plane_z_m
        pin_jaws(mech, [1.0] * JAW_COUNT)

        results, events = drive(mech, drone, DockCommands(capture_enable=True), 60)
        result = results[-1]
        self.assertFalse(result.head_above_jaws)
        self.assertFalse(result.keeper_closed_truth)
        self.assertFalse(result.reported_s2)
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        # The jaws are stopped by the head, not by their own stop: reach
        # equals the head radius, which is why the band cannot be reached.
        for reach in result.jaw_reaches_m:
            self.assertAlmostEqual(reach, g.head_radius_m, places=9)

    def test_capture_claim_is_never_taken_from_the_actuator_command(self) -> None:
        # The drive ring reaches its stop while the jaws are held open by an
        # injected linkage bind.  A mechanism that read the command, or the
        # servo, would confirm here.
        mech, drone = bench()
        pin_jaws(mech, [0.2] * JAW_COUNT)

        peak_drive = 0.0
        events = []
        reported_s2 = False
        t = 0.0
        for _ in range(200):
            result = mech.step(t, CENTER, ZERO, drone, DockCommands(capture_enable=True))
            events.extend(result.events)
            reported_s2 = reported_s2 or result.reported_s2
            peak_drive = max(peak_drive, mech.servo.position)
            t += DT

        # The drive ring went all the way to its stop and the jaws did not.
        self.assertGreater(peak_drive, 0.9)
        self.assertEqual(max(mech.jaw_closure), 0.2)
        self.assertFalse(reported_s2)
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds(events))

    def test_no_false_capture_across_the_smoke_and_fault_campaigns(self) -> None:
        for seed in SMOKE_SEEDS:
            for label, config in (
                ("nominal", sil_p0b(seed)),
                ("fault", sil_p0b(seed, with_fault=True)),
                ("correlated", sil_p0b(seed, correlated_fault=True)),
            ):
                with self.subTest(seed=seed, case=label):
                    result = run_episode(
                        replace(config, mechanism_factory=iris_mechanism_factory), seed
                    )
                    self.assertNotIn(
                        EventKind.FALSE_CAPTURE_CONFIRMED, kinds(result.events)
                    )
                    for event in result.events:
                        self.assertNotIn(event.kind, UNSAFE_EVENT_KINDS)


class LaggingJawTests(unittest.TestCase):
    """The jam mode three linkages add over one fork."""

    def test_a_badly_lagging_jaw_blocks_capture(self) -> None:
        mech, drone = bench()
        mech.jaw_close_limit[1] = 0.45
        results, events = drive(mech, drone, DockCommands(capture_enable=True), 200)

        self.assertTrue(any(not step.jaws_synchronized for step in results))
        self.assertFalse(any(step.reported_s2 for step in results))
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds(events))
        # The dock times out and opens itself, which is the safe outcome.
        self.assertIs(results[-1].controller.state, DockState.FAULT_OPEN)

    def test_a_lagging_jaw_is_positively_diagnosed_only_in_a_narrow_band(self) -> None:
        # SPEC claims the per-jaw switches diagnose "jaw N lags" only when at
        # least one jaw still holds the band.  Both halves of that claim are
        # checked, because a weakness nobody exercises is a weakness nobody
        # believes.
        diagnosed = self._scan_bind(0.76)
        self.assertIsNotNone(diagnosed)
        self.assertFalse(diagnosed.reported_s2)
        self.assertIn(False, diagnosed.jaw_reported)
        self.assertIn(True, diagnosed.jaw_reported)

        # Bind the same jaw harder and the diagnosis disappears: the other
        # two jaws overrun past the displaced mast and every switch reads
        # open.  The mechanism knows something is wrong, not which jaw.
        self.assertIsNone(self._scan_bind(0.60))
        # Sampled before the 1.0 s lock timeout reopens the dock.
        blind, _ = drive(*bench_with_bind(0.60), DockCommands(capture_enable=True), 45)
        stalled = blind[-1]
        self.assertEqual(stalled.jaw_reported, (False,) * JAW_COUNT)
        self.assertFalse(stalled.reported_s2)
        self.assertFalse(stalled.jaws_synchronized)

    def _scan_bind(self, limit: float):
        """First step whose per-jaw switches positively show a lag, if any."""

        mech, drone = bench_with_bind(limit)
        t = 0.0
        for _ in range(150):
            result = mech.step(t, CENTER, ZERO, drone, DockCommands(capture_enable=True))
            if result.jaw_lag_reported:
                return result
            t += DT
        return None

    def test_a_lagging_jaw_pushes_the_mast_off_axis(self) -> None:
        # The symmetric-grip claim is conditional on synchronisation: an
        # unsynchronised close reintroduces exactly the one-sided side load
        # on the mast that the architecture is supposed to remove.
        mech, drone = bench()
        mech.jaw_close_limit[1] = 0.45
        results, _ = drive(mech, drone, DockCommands(capture_enable=True), 60)
        self.assertGreater(max(step.mast_offset_m for step in results), 0.0005)


class RetentionGeometryTests(unittest.TestCase):
    def test_one_closed_jaw_out_of_three_does_not_retain_the_head(self) -> None:
        # The opening is the mean of the three jaw reaches, so a single jaw
        # cannot hold a Ø12 mm head on its own.  Stated as a property of the
        # jaw *set*, which is what a three-jaw claim has to be.
        mech, drone = bench()
        pin_jaws(mech, [0.0, 0.0, 1.0])
        results, _ = drive(mech, drone, DockCommands(capture_enable=True), 120)
        self.assertTrue(results[-1].head_above_jaws)
        self.assertFalse(results[-1].keeper_closed_truth)
        self.assertTrue(mech.head_can_pass)

    def test_two_closed_jaws_out_of_three_do_retain_the_head(self) -> None:
        mech, drone = bench()
        pin_jaws(mech, [0.0, 1.0, 1.0])
        results, _ = drive(mech, drone, DockCommands(capture_enable=True), 120)
        self.assertTrue(results[-1].keeper_closed_truth)
        # ...but it is not reported, because the two closed jaws overran the
        # displaced mast and left the band.  Under-claiming is the safe
        # direction and the mechanism takes it.
        self.assertFalse(any(step.reported_s2 for step in results))

    def test_closed_jaws_block_a_head_that_has_not_reached_them(self) -> None:
        mech = IrisMechanism(dt_s=DT)
        g = mech.geometry
        start_z = g.jaw_plane_z_m - 0.010
        drone = DroneBody(DroneParams(), Vec3(0.0, 0.0, start_z - g.probe_height_m))
        mech.probe_phase = ProbePhase.INSERTED
        mech._prev_rel_z = start_z
        pin_jaws(mech, [1.0] * JAW_COUNT)

        result = None
        for _ in range(60):
            drone.velocity = Vec3(0.0, 0.0, 0.05)
            drone.position = drone.position + drone.velocity * DT
            result = mech.step(0.0, CENTER, ZERO, drone, DockCommands())
        rel_z = (drone.position + Vec3(0.0, 0.0, g.probe_height_m)).z
        self.assertLessEqual(rel_z, g.jaw_plane_z_m + 1e-9)
        self.assertIs(result.probe_phase, ProbePhase.INSERTED)
        self.assertFalse(result.seat_truth)


class ReleaseTests(unittest.TestCase):
    def test_release_works_with_an_aircraft_hanging_on_the_jaws(self) -> None:
        # The Rev-A defect this study exists to avoid repeating: a keeper
        # that cannot release what it captured.  The aircraft is disarmed,
        # so the jaws are carrying it when the command arrives.
        mech, drone = bench()
        results, _ = drive(mech, drone, DockCommands(capture_enable=True), 60)
        self.assertTrue(results[-1].controller.capture_confirmed)
        drone.disarm()

        results, events = drive(
            mech, drone, DockCommands(release_request=True), 120, t0=1.2
        )
        released = results[-1]
        self.assertIn(EventKind.RELEASED, kinds(events))
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, kinds(events))
        self.assertFalse(released.keeper_closed_truth)
        self.assertFalse(released.reported_s2)
        self.assertEqual(max(released.jaw_closures), 0.0)

    def test_emergency_release_opens_the_jaws_from_a_fault_locked_state(self) -> None:
        mech, drone = bench()
        drive(mech, drone, DockCommands(capture_enable=True), 60)
        drone.disarm()
        # Force sensor disagreement so the controller fails locked.
        mech.seat_switch.fault = SwitchFault.STUCK_OPEN
        results, _ = drive(mech, drone, DockCommands(), 60, t0=1.2)
        self.assertIs(results[-1].controller.state, DockState.FAULT_LOCKED)

        results, _ = drive(mech, drone, DockCommands(emergency_release=True), 120, t0=2.4)
        self.assertEqual(max(results[-1].jaw_closures), 0.0)
        self.assertFalse(results[-1].keeper_closed_truth)

    def test_a_release_that_binds_is_reported_and_not_faked(self) -> None:
        # The iris analogue of the Rev-A release defect: the linkages will
        # not retract.  Truth must keep saying "still gripped" while the
        # controller runs out its release timeout.
        mech, drone = bench()
        drive(mech, drone, DockCommands(capture_enable=True), 60)
        drone.disarm()
        mech.jaw_open_limit = [0.86] * JAW_COUNT

        results, events = drive(
            mech, drone, DockCommands(release_request=True), 200, t0=1.2
        )
        stuck = results[-1]
        self.assertTrue(stuck.keeper_closed_truth)
        self.assertTrue(stuck.head_above_jaws)
        self.assertTrue(stuck.reported_s2)
        self.assertIs(stuck.controller.state, DockState.FAULT_OPEN)
        self.assertEqual(stuck.controller.fault_reason, "release_timeout")
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, kinds(events))

    def test_grip_lost_with_no_release_command_is_a_dropped_aircraft(self) -> None:
        mech, drone = bench()
        drive(mech, drone, DockCommands(capture_enable=True), 60)
        drone.disarm()
        # A linkage failure that lets the jaws fall open under load.
        mech.jaw_close_limit = [0.0] * JAW_COUNT
        results, events = drive(
            mech, drone, DockCommands(capture_enable=True), 80, t0=1.2
        )
        self.assertIn(EventKind.DROPPED_AIRCRAFT, kinds(events))
        self.assertFalse(results[-1].keeper_closed_truth)


class DiscriminationMarginTests(unittest.TestCase):
    """The timing weakness SPEC claims, exercised rather than asserted."""

    def test_nominal_geometry_has_the_claimed_transit_margin(self) -> None:
        g = IrisGeometry()
        self.assertLess(g.empty_band_transit_s, g.jaw_switch_debounce_s)
        margin = g.jaw_switch_debounce_s / g.empty_band_transit_s
        self.assertGreater(margin, 1.7)
        self.assertLess(margin, 2.0)  # it is thin, and SPEC says so

    def test_a_slow_actuator_reopens_the_empty_throat_false_positive(self) -> None:
        # 0.80 s stroke was a live cell in docs/dock-deletion-review.md, so
        # this is not a contrived number.  The empty transit then exceeds the
        # debounce and the band switch asserts on an empty dock.
        slow = IrisGeometry(jaw_travel_time_s=0.80)
        self.assertGreater(slow.empty_band_transit_s, slow.jaw_switch_debounce_s)

        mech = IrisMechanism(slow, dt_s=DT)
        mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        results, events = drive(mech, None, DockCommands(capture_enable=True), 200)

        self.assertIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds(events))
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertTrue(any(step.reported_s2 for step in results))
        # The mechanism was wrong about itself in the indication, and right
        # in the truth, on every single step.  That is the whole discipline.
        self.assertFalse(any(step.keeper_closed_truth for step in results))

    def test_a_slow_actuator_still_captures_a_real_probe(self) -> None:
        # The failure above is a discrimination failure, not a capture
        # failure; keeping the two apart is the point of reporting it.
        mech, drone = bench(geometry=IrisGeometry(jaw_travel_time_s=0.80))
        results, events = drive(mech, drone, DockCommands(capture_enable=True), 200)
        self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds(events))
        self.assertTrue(results[-1].keeper_closed_truth)


class ContactHonestyTests(unittest.TestCase):
    """Unsafe contacts must be reported at the baseline's rate, not lower."""

    def test_rim_crossing_scores_prop_funnel_contact(self) -> None:
        mech = IrisMechanism(dt_s=DT)
        g = mech.geometry
        lateral = g.funnel_entrance_radius_m + 0.010
        drone = DroneBody(DroneParams(), Vec3(lateral, 0.0, -0.002 - g.probe_height_m))
        drone.velocity = Vec3(0.0, 0.0, 0.10)

        events = []
        for _ in range(6):
            result = mech.step(0.0, CENTER, ZERO, drone, DockCommands())
            events.extend(result.events)
            drone.position = drone.position + Vec3(0.0, 0.0, 0.002)
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, kinds(events))

    def test_fast_crossing_scores_overspeed_contact_and_does_not_insert(self) -> None:
        mech = IrisMechanism(dt_s=DT)
        g = mech.geometry
        drone = DroneBody(DroneParams(), Vec3(0.0, 0.0, -0.002 - g.probe_height_m))
        drone.velocity = Vec3(0.0, 0.0, g.bounce_speed_m_s + 0.20)

        events = []
        for _ in range(4):
            result = mech.step(0.0, CENTER, ZERO, drone, DockCommands())
            events.extend(result.events)
            drone.position = drone.position + Vec3(0.0, 0.0, 0.002)
        self.assertIn(EventKind.OVERSPEED_CONTACT, kinds(events))
        self.assertIs(mech.probe_phase, ProbePhase.FREE)

    def test_slow_centered_crossing_inserts(self) -> None:
        mech = IrisMechanism(dt_s=DT)
        g = mech.geometry
        drone = DroneBody(DroneParams(), Vec3(0.0, 0.0, -0.002 - g.probe_height_m))
        drone.velocity = Vec3(0.0, 0.0, 0.05)

        events = []
        for _ in range(4):
            result = mech.step(0.0, CENTER, ZERO, drone, DockCommands())
            events.extend(result.events)
            drone.position = drone.position + Vec3(0.0, 0.0, 0.002)
        self.assertIn(EventKind.FUNNEL_INSERTION, kinds(events))
        self.assertIs(mech.probe_phase, ProbePhase.INSERTED)


class ControllerResetTests(unittest.TestCase):
    def test_a_brownout_loses_the_logic_and_keeps_the_hardware(self) -> None:
        mech, drone = bench()
        drive(mech, drone, DockCommands(capture_enable=True), 60)
        drone.disarm()
        jaws_before = list(mech.jaw_closure)

        mech.reset_controller()
        self.assertEqual(mech.jaw_closure, jaws_before)
        self.assertIs(mech.controller.state, DockState.OPEN)

        results, events = drive(mech, drone, DockCommands(), 20, t0=1.2)
        # FM-CH-06: the restarted controller sees both channels made over an
        # occupied seat and holds rather than commanding open.
        self.assertIs(results[-1].controller.state, DockState.FAULT_LOCKED)
        self.assertTrue(results[-1].keeper_closed_truth)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, kinds(events))


if __name__ == "__main__":
    unittest.main()
