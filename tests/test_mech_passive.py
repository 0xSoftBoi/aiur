"""Tests for the passive snap-detent capture candidate.

The point of these tests is not that the module runs.  It is that every claim
the candidate makes about itself is checked against the model, in both
directions: the strengths it is entered into the trade study for (a brownout
cannot change what it holds; no actuator can jam) and the weaknesses it
declares (an empty hold/release window, one sensed channel, no commanded
release).  A declared weakness that no test exercises is a sentence, not a
finding.
"""

from dataclasses import replace
import unittest

from aiur.dock_controller import DockState
from aiur.sim.bodies import DroneBody, DroneParams
from aiur.sim.dock_physics import DockCommands, ProbePhase
from aiur.sim.engine import EpisodeOutcome, run_episode
from aiur.sim.events import EventKind, UNSAFE_EVENT_KINDS
from aiur.sim.mech_passive import (
    SPEC,
    PassiveDetentDock,
    PassiveDetentGeometry,
    PassiveDetentParams,
    admissible_retention_for_insertion,
    passive_mechanism_factory,
    retention_window_n,
    window_is_empty,
)
from aiur.sim.mechanism import CaptureMechanism, MechanismSpec
from aiur.sim.scenarios import sil_p0b, sil_p0c
from aiur.sim.sensors import SwitchFault
from aiur.sim.vec import ZERO, Vec3

DT = 0.02
DOCK = Vec3(0.0, 0.0, 2.0)

#: The only sizing that both admits the probe and holds the docked weight: a
#: near one-way barb at the review's backstop force.  It cannot release, which
#: is the whole finding, so it is named rather than treated as a default.
BARB = PassiveDetentParams(retention_force_n=0.468, insertion_force_ratio=0.15)

#: The same detent on an aircraft whose propellers can push down.  This is the
#: only configuration in which capture, retention and release all work.
REVERSIBLE = replace(BARB, retention_force_n=0.50, reverse_thrust_n=0.10)


def make_dock(params=None, geometry=None) -> PassiveDetentDock:
    return PassiveDetentDock(geometry, params, dt_s=DT)


def make_drone(dock: PassiveDetentDock, rel_z: float, lateral: float = 0.0) -> DroneBody:
    """An aircraft whose probe tip sits ``rel_z`` above the entrance plane."""

    tip = DOCK + Vec3(lateral, 0.0, rel_z)
    return DroneBody(DroneParams(), tip - Vec3(0.0, 0.0, dock.geometry.probe_height_m))


def outcomes(params, seeds, scenario=sil_p0b, **kwargs):
    """Run a cell of episodes through the real engine with this detent."""

    results = []
    for seed in seeds:
        config = replace(
            scenario(seed, **kwargs),
            mechanism_factory=passive_mechanism_factory(params),
        )
        results.append(run_episode(config, seed))
    return results


class ProtocolTests(unittest.TestCase):
    def test_spec_and_mechanism_satisfy_the_study_protocols(self) -> None:
        self.assertIsInstance(SPEC, MechanismSpec)
        self.assertEqual(SPEC.key, "passive")
        mechanism = SPEC.build(DT)
        self.assertIsInstance(mechanism, CaptureMechanism)
        self.assertIs(mechanism.probe_phase, ProbePhase.FREE)

    def test_spec_declares_no_actuator_and_one_channel(self) -> None:
        # These two numbers are the candidate's entire pitch and its entire
        # cost.  If either ever changes, it is a different architecture.
        self.assertEqual(SPEC.actuator_count, 0)
        self.assertEqual(SPEC.sensed_channels, 1)
        self.assertTrue(SPEC.known_weaknesses)


class ForceWindowTests(unittest.TestCase):
    """The arithmetic the whole candidate turns on."""

    def test_window_is_empty_for_every_retention_force_and_friction(self) -> None:
        # Hold requires breakaway > weight; release requires breakaway <=
        # the pull-out force, which for unidirectional propellers is that
        # same weight.  Sweep both parameters and assert no cell does both.
        for retention in (0.0, 0.02, 0.074, 0.2, 0.4677, 0.468, 1.0, 5.0):
            for friction in (0.8, 1.0, 1.15, 2.0):
                params = PassiveDetentParams(
                    retention_force_n=retention, release_friction_factor=friction
                )
                hold_min, release_max = retention_window_n(params)
                holds = retention > hold_min
                releases = retention <= release_max
                self.assertFalse(
                    holds and releases,
                    f"R={retention} f={friction} claimed to both hold and release",
                )
                self.assertTrue(holds or releases)
        self.assertTrue(window_is_empty(PassiveDetentParams()))

    def test_reverse_thrust_is_the_only_thing_that_opens_the_window(self) -> None:
        params = replace(PassiveDetentParams(), reverse_thrust_n=0.10)
        self.assertFalse(window_is_empty(params))
        hold_min, release_max = retention_window_n(params)
        self.assertLess(hold_min, release_max)

    def test_backstop_sizing_is_unreachable_by_a_conventional_detent(self) -> None:
        params = PassiveDetentParams()  # R = 0.468 N, ratio 0.35
        geometry = PassiveDetentGeometry()
        # The guidance stack creeps the last stretch at 0.03 m/s.
        admissible = admissible_retention_for_insertion(params, geometry, 0.03)
        self.assertLess(admissible, params.retention_force_n)
        # The lead-in asymmetry that would just admit it: a near one-way
        # barb, well outside a conventional detent, and the sizing at which
        # the aircraft can then never fly back out.
        viable_ratio = (
            params.insertion_force_ratio * admissible / params.retention_force_n
        )
        self.assertLess(viable_ratio, 0.19)
        self.assertGreater(viable_ratio, 0.15)


class NominalCaptureTests(unittest.TestCase):
    def test_captures_every_seed_at_the_only_insertable_holding_sizing(self) -> None:
        results = outcomes(BARB, range(1, 13))
        self.assertTrue(all(r.outcome is EpisodeOutcome.SUCCESS for r in results))
        self.assertTrue(all(r.captures == 1 for r in results))
        self.assertFalse([e for r in results for e in r.unsafe_events])

    def test_default_sizing_does_not_capture_and_fails_safe(self) -> None:
        # The honest default holds the docked weight with a conventional
        # detent, and a 37 g aircraft then cannot push the probe past it.
        # Failing to capture is a legitimate result; failing to *say so* is
        # not, so the run must end safe-incomplete with zero unsafe events
        # and zero capture claims.
        results = outcomes(PassiveDetentParams(), range(1, 13))
        self.assertTrue(
            all(r.outcome is EpisodeOutcome.SAFE_INCOMPLETE for r in results)
        )
        self.assertEqual(sum(r.captures for r in results), 0)
        self.assertFalse([e for r in results for e in r.unsafe_events])

    def test_blocked_probe_stalls_short_of_the_seat_and_S1_stays_silent(self) -> None:
        dock = make_dock(PassiveDetentParams())
        drone = make_drone(dock, -0.01)
        t = 0.0
        result = dock.step(t, DOCK, ZERO, drone, DockCommands())
        for _ in range(400):
            t += DT
            drone.position = drone.position + Vec3(0.0, 0.0, 0.03 * DT)
            drone.velocity = Vec3(0.0, 0.0, 0.03)
            result = dock.step(t, DOCK, ZERO, drone, DockCommands(capture_enable=True))
        rel_z = (drone.position + Vec3(0.0, 0.0, dock.geometry.probe_height_m) - DOCK).z
        self.assertAlmostEqual(rel_z, dock.geometry.detent_plane_m, places=6)
        self.assertIs(dock.probe_phase, ProbePhase.INSERTED)
        self.assertTrue(dock.last_diagnostics.insertion_blocked)
        self.assertFalse(result.seat_truth)
        self.assertFalse(result.reported_s1)
        self.assertFalse(result.controller.capture_confirmed)

    def test_determinism(self) -> None:
        config = replace(
            sil_p0b(7), mechanism_factory=passive_mechanism_factory(BARB)
        )
        first = run_episode(config, 7)
        second = run_episode(config, 7)
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.duration_s, second.duration_s)


class NoCaptureClaimWithoutRetentionTests(unittest.TestCase):
    def test_empty_throat_with_a_stuck_seat_switch_is_reported_as_false(self) -> None:
        # The declared weakness: one channel means one lie is enough.  The
        # mechanism must not hide it — truth and indication disagree, and
        # the disagreement is emitted.
        dock = make_dock(BARB)
        dock.seat_switch.fault = SwitchFault.STUCK_CLOSED
        t = 0.0
        kinds: list[EventKind] = []
        for _ in range(40):
            result = dock.step(t, DOCK, ZERO, None, DockCommands(capture_enable=True))
            kinds.extend(e.kind for e in result.events)
            t += DT
        self.assertTrue(result.controller.capture_confirmed)
        self.assertTrue(result.reported_s1)
        self.assertFalse(result.seat_truth)
        self.assertFalse(result.keeper_closed_truth)
        self.assertIn(EventKind.FALSE_CAPTURE_CONFIRMED, kinds)
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, kinds)

    def test_confirmation_needs_the_dwell_and_the_switch(self) -> None:
        dock = make_dock(BARB)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        commands = DockCommands(capture_enable=True)
        result = dock.step(0.0, DOCK, ZERO, drone, commands)
        self.assertIs(result.controller.state, DockState.LOCKING)
        self.assertFalse(result.controller.capture_confirmed)
        result = dock.step(0.18, DOCK, ZERO, drone, commands)
        self.assertFalse(result.controller.capture_confirmed)
        result = dock.step(0.20, DOCK, ZERO, drone, commands)
        self.assertTrue(result.controller.capture_confirmed)
        # And the confirmation is a sensed fact, not a latched belief: pull
        # the only channel and the claim goes away in the same step.
        dock.seat_switch.fault = SwitchFault.STUCK_OPEN
        result = dock.step(0.22, DOCK, ZERO, drone, commands)
        self.assertFalse(result.controller.capture_confirmed)
        # ...while the mechanism is still, in truth, holding the aircraft.
        self.assertTrue(result.keeper_closed_truth)

    def test_reported_second_channel_is_never_true(self) -> None:
        dock = make_dock(BARB)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        dock.keeper_switch.fault = SwitchFault.STUCK_CLOSED
        for step in range(30):
            result = dock.step(step * DT, DOCK, ZERO, drone, DockCommands(capture_enable=True))
            self.assertFalse(result.reported_s2)
        self.assertTrue(result.keeper_closed_truth)


class DropTests(unittest.TestCase):
    def test_retention_below_the_docked_weight_drops_the_aircraft(self) -> None:
        # Sized for abort transparency, as the deletion review's lower bound
        # requires, the detent cannot hold what it just claimed to capture.
        soft = replace(BARB, retention_force_n=0.064)
        results = outcomes(soft, range(1, 13))
        self.assertTrue(all(r.outcome is EpisodeOutcome.UNSAFE for r in results))
        for result in results:
            kinds = [e.kind for e in result.events]
            self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds)
            self.assertIn(EventKind.DROPPED_AIRCRAFT, kinds)

    def test_disarmed_aircraft_falls_out_of_a_soft_detent(self) -> None:
        # The physically-timed path, driven by hand so it is exercised
        # independently of the engine's episode-termination behaviour.
        dock = make_dock(replace(BARB, retention_force_n=0.10))
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        result = dock.step(0.0, DOCK, ZERO, drone, DockCommands())
        self.assertIs(result.probe_phase, ProbePhase.SEATED)
        drone.disarm()
        result = dock.step(DT, DOCK, ZERO, drone, DockCommands())
        self.assertIn(EventKind.DROPPED_AIRCRAFT, [e.kind for e in result.events])
        self.assertFalse(result.keeper_closed_truth)
        self.assertIs(dock.probe_phase, ProbePhase.INSERTED)

    def test_holding_detent_does_not_drop_and_does_not_over_report(self) -> None:
        dock = make_dock(BARB)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        drone.disarm()
        kinds: list[EventKind] = []
        for step in range(60):
            result = dock.step(step * DT, DOCK, ZERO, drone, DockCommands(capture_enable=True))
            kinds.extend(e.kind for e in result.events)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, kinds)
        self.assertTrue(result.keeper_closed_truth)
        self.assertTrue(result.seat_truth)


class ReleaseTests(unittest.TestCase):
    def test_commanded_release_works_when_the_aircraft_can_push_down(self) -> None:
        # The full launch/sortie/recover cycle: seeded captured, released by
        # thrust, flown away, and recaptured.  Release is the criterion the
        # baseline's Rev-A failed, so it is checked end to end, not asserted.
        results = outcomes(REVERSIBLE, range(1, 5), scenario=sil_p0c)
        self.assertTrue(all(r.outcome is EpisodeOutcome.SUCCESS for r in results))
        self.assertFalse([e for r in results for e in r.unsafe_events])

    def test_a_detent_that_holds_can_never_be_flown_out_of(self) -> None:
        # Same episode, same detent, propellers that cannot push: the
        # aircraft is captured and stays captured forever.  Not an unsafe
        # event and not a success — a vehicle that cannot be launched.
        results = outcomes(BARB, range(1, 5), scenario=sil_p0c)
        self.assertTrue(all(r.outcome is EpisodeOutcome.TIMEOUT for r in results))
        self.assertFalse([e for r in results for e in r.unsafe_events])

    def test_release_under_load_is_a_force_comparison_not_a_command(self) -> None:
        for retention, should_release in ((0.30, True), (0.468, False)):
            with self.subTest(retention=retention):
                dock = make_dock(replace(BARB, retention_force_n=retention))
                drone = make_drone(dock, dock.geometry.seat_travel_m)
                dock.seed_seated(drone, DOCK, ZERO)
                released = False
                for step in range(120):
                    # Stand in for the engine: the aircraft keeps demanding a
                    # descent every step, thrust unloading as it goes.
                    drone.velocity = Vec3(0.0, 0.0, -0.10)
                    result = dock.step(
                        step * DT,
                        DOCK,
                        ZERO,
                        drone,
                        DockCommands(emergency_release=True),
                    )
                    if result.probe_phase is not ProbePhase.SEATED:
                        released = True
                        break
                self.assertEqual(released, should_release)
                if not released:
                    self.assertTrue(dock.last_diagnostics.release_blocked)
                    self.assertTrue(dock.last_diagnostics.detent_engaged)

    def test_emergency_release_moves_no_hardware(self) -> None:
        # It declares a release.  With no actuator there is nothing else it
        # can do, and the mechanism must not pretend otherwise.
        dock = make_dock(BARB)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        result = dock.step(0.0, DOCK, ZERO, drone, DockCommands(emergency_release=True))
        self.assertIs(result.controller.state, DockState.RELEASING)
        self.assertTrue(result.keeper_closed_truth)
        self.assertTrue(dock.detent_engaged)


class ActuatorFreeStrengthTests(unittest.TestCase):
    """The reasons the candidate is in the study at all."""

    def test_brownout_cannot_change_what_is_held(self) -> None:
        dock = make_dock(BARB)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        commands = DockCommands(capture_enable=True)
        for step in range(20):
            result = dock.step(step * DT, DOCK, ZERO, drone, commands)
        self.assertTrue(result.controller.capture_confirmed)

        position = drone.position
        dock.reset_controller()
        self.assertTrue(dock.detent_engaged)
        self.assertIs(dock.probe_phase, ProbePhase.SEATED)
        self.assertIs(dock.supervisor.state, DockState.OPEN)

        # One step later the restarted supervisor has re-derived that it is
        # holding something, from the only channel it has.
        result = dock.step(0.40, DOCK, ZERO, drone, DockCommands())
        self.assertIs(result.controller.state, DockState.CAPTURED)
        self.assertTrue(result.controller.capture_confirmed)
        self.assertTrue(result.keeper_closed_truth)
        self.assertEqual(drone.position, position)
        self.assertIn(EventKind.CAPTURE_CONFIRMED, [e.kind for e in result.events])

    def test_a_brownout_with_a_stuck_switch_confirms_a_capture_of_nothing(self) -> None:
        # The other side of the same coin, and the reason the restart
        # behaviour above is cheap: with one channel there is nothing to
        # check it against.
        dock = make_dock(BARB)
        dock.seat_switch.fault = SwitchFault.STUCK_CLOSED
        dock.reset_controller()
        result = dock.step(0.0, DOCK, ZERO, None, DockCommands())
        self.assertTrue(result.controller.capture_confirmed)
        self.assertFalse(result.keeper_closed_truth)
        self.assertIn(
            EventKind.FALSE_CAPTURE_CONFIRMED, [e.kind for e in result.events]
        )

    def test_actuator_faults_are_structurally_inert(self) -> None:
        # A jam cannot exist without an actuator.  This is both the headline
        # strength and the reason a like-for-like fault campaign flatters
        # this candidate: the fault is injected and nothing happens.
        dock = make_dock(BARB)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        dock.servo.jammed = True
        dock.keeper_switch.fault = SwitchFault.STUCK_OPEN
        commands = DockCommands(capture_enable=True)
        for step in range(20):
            result = dock.step(step * DT, DOCK, ZERO, drone, commands)
        self.assertTrue(result.controller.capture_confirmed)
        self.assertTrue(result.keeper_closed_truth)

    def test_fault_trigger_can_still_see_the_mechanism_holding(self) -> None:
        # The KEEPER_CLOSED fault trigger reads servo.physically_closed.  If
        # that were hard-wired False, controller-reset faults would never arm
        # and this candidate would pass fault campaigns untested.
        dock = make_dock(BARB)
        self.assertFalse(dock.servo.physically_closed)
        drone = make_drone(dock, dock.geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        self.assertTrue(dock.servo.physically_closed)

    def test_fault_episodes_stay_safe_at_a_holding_sizing(self) -> None:
        results = outcomes(BARB, range(1, 25), with_fault=True)
        self.assertFalse([e for r in results for e in r.unsafe_events])
        results = outcomes(BARB, range(1, 25), correlated_fault=True)
        self.assertFalse([e for r in results for e in r.unsafe_events])


class SingleChannelLossTests(unittest.TestCase):
    def test_weight_transfer_can_silence_the_only_channel(self) -> None:
        # A detent holds at its retaining face, not against the seat, so the
        # aircraft sags when its weight transfers.  Sag beyond the seat
        # switch hysteresis silences S1 at the exact moment the capture
        # becomes load-bearing, and with no second channel the system then
        # reports a release while physically holding the aircraft.  This is
        # a Rev-B tolerance requirement the study surfaces: backlash must
        # stay under the switch hysteresis.
        geometry = PassiveDetentGeometry(detent_backlash_m=0.006)
        self.assertGreater(geometry.detent_backlash_m, geometry.seat_hysteresis_m)
        dock = make_dock(BARB, geometry)
        drone = make_drone(dock, geometry.seat_travel_m)
        dock.seed_seated(drone, DOCK, ZERO)
        commands = DockCommands(capture_enable=True)
        for step in range(20):
            result = dock.step(step * DT, DOCK, ZERO, drone, commands)
        self.assertTrue(result.controller.capture_confirmed)

        drone.disarm()
        kinds: list[EventKind] = []
        for step in range(20, 60):
            result = dock.step(step * DT, DOCK, ZERO, drone, commands)
            kinds.extend(e.kind for e in result.events)

        self.assertIn(EventKind.RELEASED, kinds)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, kinds)
        self.assertFalse(result.reported_s1)
        self.assertFalse(result.controller.capture_confirmed)
        # Indication says released.  Truth says held.
        self.assertTrue(result.keeper_closed_truth)
        self.assertIs(dock.probe_phase, ProbePhase.SEATED)
        self.assertIs(result.controller.state, DockState.FAULT_LOCKED)


class ContactHonestyTests(unittest.TestCase):
    """Unsafe contact events must be emitted, not smoothed away."""

    def test_rim_strike_is_reported(self) -> None:
        dock = make_dock(BARB)
        lateral = dock.geometry.funnel_entrance_radius_m + 0.03
        drone = make_drone(dock, -0.01, lateral=lateral)
        dock.step(0.0, DOCK, ZERO, drone, DockCommands())
        drone.position = drone.position + Vec3(0.0, 0.0, 0.015)
        drone.velocity = Vec3(0.0, 0.0, 0.05)
        result = dock.step(DT, DOCK, ZERO, drone, DockCommands())
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, [e.kind for e in result.events])
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, UNSAFE_EVENT_KINDS)
        self.assertIs(dock.probe_phase, ProbePhase.FREE)

    def test_overspeed_contact_is_reported_and_bounces(self) -> None:
        dock = make_dock(BARB)
        drone = make_drone(dock, -0.01)
        dock.step(0.0, DOCK, ZERO, drone, DockCommands())
        drone.position = drone.position + Vec3(0.0, 0.0, 0.015)
        drone.velocity = Vec3(0.0, 0.0, 0.40)
        result = dock.step(DT, DOCK, ZERO, drone, DockCommands())
        self.assertIn(EventKind.OVERSPEED_CONTACT, [e.kind for e in result.events])
        self.assertIs(dock.probe_phase, ProbePhase.FREE)
        self.assertLess(drone.velocity.z, 0.0)

    def test_insertion_is_reported_with_its_closing_speed(self) -> None:
        dock = make_dock(BARB)
        drone = make_drone(dock, -0.01)
        dock.step(0.0, DOCK, ZERO, drone, DockCommands())
        drone.position = drone.position + Vec3(0.0, 0.0, 0.015)
        drone.velocity = Vec3(0.0, 0.0, 0.05)
        result = dock.step(DT, DOCK, ZERO, drone, DockCommands())
        self.assertIn(EventKind.FUNNEL_INSERTION, [e.kind for e in result.events])
        self.assertAlmostEqual(result.contact_closing_speed_m_s, 0.05, places=6)


class GeometryValidationTests(unittest.TestCase):
    def test_rejects_impossible_geometry_and_parameters(self) -> None:
        with self.assertRaises(ValueError):
            PassiveDetentGeometry(detent_throw_m=0.0)
        with self.assertRaises(ValueError):
            PassiveDetentGeometry(detent_engage_travel_m=0.2)
        with self.assertRaises(ValueError):
            PassiveDetentParams(retention_force_n=-1.0)
        with self.assertRaises(ValueError):
            PassiveDetentParams(release_friction_factor=0.0)
        with self.assertRaises(ValueError):
            PassiveDetentDock(dt_s=0.0)

    def test_factory_mirrors_the_episode_funnel_geometry(self) -> None:
        config = sil_p0b(1)
        dock = passive_mechanism_factory(BARB)(config, DT)
        self.assertEqual(
            dock.geometry.seat_travel_m, config.dock_geometry.seat_travel_m
        )
        self.assertEqual(
            dock.geometry.probe_height_m, config.dock_geometry.probe_height_m
        )
        self.assertEqual(
            dock.geometry.funnel_entrance_radius_m,
            config.dock_geometry.funnel_entrance_radius_m,
        )


if __name__ == "__main__":
    unittest.main()
