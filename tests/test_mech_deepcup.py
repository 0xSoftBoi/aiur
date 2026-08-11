"""Tests for the deep-cup capture candidate (aiur/sim/mech_deepcup.py).

The candidate exists to be evaluated, not defended.  So these tests do two
jobs: they check the properties the programme's safety case requires of any
mechanism (truth separate from indication, no capture claim from command
alone, honest unsafe events, release that works under load), and they pin
every *weakness* the spec claims, so that a later edit which quietly stops
exercising a weakness fails here instead of turning into a flattering
number in the trade study.

Three of those pinned weaknesses are the reason to have run this at all:

* a straight bore has no benign contact surface, so a wind-driven lateral
  excursion the funnel absorbs as a centring push reaches the wall here as a
  guarded-rotor strike;
* the deep cup produces a rotor-wall strike on the P0-C launch departure
  with no fault injected, because the guidance stack's carrier-proximity
  evasion commands 0.6 m/s laterally while the aircraft is still inside the
  cup, and unlike the funnel a straight bore cannot physically veto it;
* the trade study's own harness runs only ``sil_p0b`` on a bench rig, which
  has no hull and therefore no evasion reflex, so the study structurally
  cannot see that last failure.

Everything is deterministic: seeded episodes and a kinematic bench, no
wall-clock dependence.
"""

from __future__ import annotations

from dataclasses import replace
import unittest

from aiur.dock_controller import DockState
from aiur.sim.bodies import DroneBody, DroneParams
from aiur.sim.disturbances import outdoor_breeze
from aiur.sim.dock_physics import DockCommands, ProbePhase
from aiur.sim.engine import EpisodeOutcome, run_episode
from aiur.sim.events import UNSAFE_EVENT_KINDS, EventKind
from aiur.sim.guidance import GuidanceParams
from aiur.sim.mech_deepcup import (
    SPEC,
    CupGeometry,
    DeepCupAssembly,
    mechanism_factory,
)
from aiur.sim.mechanism import CaptureMechanism, MechanismSpec
from aiur.sim.scenarios import sil_p0b, sil_p0c
from aiur.sim.sensors import SwitchFault
from aiur.sim.vec import ZERO, Vec3

DT = 0.02  # engine step, 50 Hz
DOCK_CENTER = Vec3(0.0, 0.0, 2.0)
#: Enough seeds to see the behaviour without turning the suite into a
#: campaign.  Rates belong in aiur.sim.design_study, which runs hundreds;
#: these tests only have to catch a candidate that has stopped behaving the
#: way its spec says it behaves.
SEEDS = range(1, 10)
ENABLE = DockCommands(capture_enable=True)


class _Bench:
    """Kinematic bench: drive one aircraft into one stationary cup.

    Deliberately not the engine.  Episode-level tests answer "does this
    architecture work in the twin"; the bench answers "does this piece of
    geometry do what its docstring says", which needs the aircraft put
    exactly where the question is.
    """

    def __init__(self, geometry: CupGeometry | None = None) -> None:
        self.mech = DeepCupAssembly(geometry or CupGeometry(), dt_s=DT)
        self.drone = DroneBody(DroneParams(), Vec3())
        self.t_s = 0.0
        self.events: list = []
        self.last = None

    @property
    def geometry(self) -> CupGeometry:
        return self.mech.geometry

    @property
    def crown_z(self) -> float:
        return self.drone.position.z + self.geometry.crown_height_m - DOCK_CENTER.z

    def place(self, *, lateral_m: float = 0.0, crown_z_m: float = -0.05) -> None:
        self.drone.position = Vec3(
            lateral_m,
            0.0,
            DOCK_CENTER.z + crown_z_m - self.geometry.crown_height_m,
        )
        self.drone.velocity = ZERO

    def step(self, commands: DockCommands = DockCommands(), climb_m_s: float | None = None):
        """Advance one step.  ``climb_m_s=None`` leaves motion to the mechanism."""

        if climb_m_s is not None:
            self.drone.velocity = Vec3(0.0, 0.0, climb_m_s)
            self.drone.position = self.drone.position + self.drone.velocity * DT
        result = self.mech.step(self.t_s, DOCK_CENTER, ZERO, self.drone, commands)
        self.t_s += DT
        self.events.extend(result.events)
        self.last = result
        return result

    def fly_in(
        self,
        *,
        lateral_m: float = 0.0,
        climb_m_s: float = 0.05,
        commands: DockCommands = DockCommands(),
        steps: int = 260,
        stop_crown_z: float | None = None,
    ):
        self.place(lateral_m=lateral_m)
        for _ in range(steps):
            self.step(commands=commands, climb_m_s=climb_m_s)
            if stop_crown_z is not None and self.crown_z >= stop_crown_z:
                break
        return self.last

    def hold(self, n_steps: int, commands: DockCommands = DockCommands()):
        for _ in range(n_steps):
            self.step(commands=commands, climb_m_s=0.0)
        return self.last

    def coast(self, n_steps: int, commands: DockCommands = DockCommands()):
        """Step with the mechanism owning the aircraft's motion entirely."""

        for _ in range(n_steps):
            self.step(commands=commands, climb_m_s=None)
        return self.last

    def kinds(self) -> list:
        return [event.kind for event in self.events]


def _episode(seed: int, *, build=mechanism_factory, scenario=sil_p0b, **kwargs):
    config = scenario(seed, **kwargs)
    if build is not None:
        config = replace(config, mechanism_factory=build)
    return run_episode(config, seed)


class ProtocolTests(unittest.TestCase):
    def test_assembly_satisfies_capture_mechanism(self) -> None:
        self.assertIsInstance(SPEC.build(DT), CaptureMechanism)

    def test_spec_satisfies_mechanism_spec(self) -> None:
        self.assertIsInstance(SPEC, MechanismSpec)
        self.assertEqual(SPEC.key, "deepcup")

    def test_registered_in_the_trade_study(self) -> None:
        from aiur.sim.architectures import CANDIDATES

        self.assertIn("deepcup", [spec.key for spec in CANDIDATES])

    def test_geometry_rejects_a_bore_the_rotors_cannot_fit(self) -> None:
        with self.assertRaises(ValueError):
            CupGeometry(bore_radius_m=0.070)


class NominalCaptureTests(unittest.TestCase):
    """Does it capture at all, and does it stay safe while doing it."""

    def test_captures_in_sil_p0b(self) -> None:
        captured = [
            _episode(seed).outcome is EpisodeOutcome.SUCCESS for seed in SEEDS
        ]
        self.assertGreaterEqual(sum(captured), 7, "deep cup stopped capturing")

    def test_no_unsafe_events_nominal(self) -> None:
        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.assertEqual(_episode(seed).unsafe_events, ())

    def test_no_unsafe_events_under_injected_faults(self) -> None:
        """Aborting is acceptable; striking or dropping is not."""

        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.assertEqual(_episode(seed, with_fault=True).unsafe_events, ())
                self.assertEqual(
                    _episode(seed, correlated_fault=True).unsafe_events, ()
                )

    def test_deterministic(self) -> None:
        first = _episode(3)
        second = _episode(3)
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.duration_s, second.duration_s)


class TruthVersusIndicationTests(unittest.TestCase):
    def test_no_capture_claim_from_an_empty_cup(self) -> None:
        """A stuck-actuated crown switch confirms a capture on nothing.

        The bar spans the whole bore, so S2 closes identically on an
        occupied and an empty cup: FMECA FM-KP-03 transfers to this
        architecture unchanged, and the model must say so rather than
        quietly reporting a good capture.
        """

        bench = _Bench()
        bench.mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        for _ in range(120):
            result = bench.mech.step(bench.t_s, DOCK_CENTER, ZERO, None, ENABLE)
            bench.t_s += DT
            bench.events.extend(result.events)

        self.assertIn(EventKind.FALSE_CAPTURE_CONFIRMED, bench.kinds())
        self.assertNotIn(EventKind.CAPTURE_CONFIRMED, bench.kinds())
        # Indication says captured; truth says nothing is held.
        self.assertTrue(result.reported_s1)
        self.assertTrue(result.reported_s2)
        self.assertFalse(result.seat_truth)
        self.assertFalse(result.keeper_closed_truth)

    def test_confirmed_capture_means_physical_retention(self) -> None:
        bench = _Bench()
        result = bench.fly_in(commands=ENABLE)
        self.assertTrue(result.controller.capture_confirmed)
        self.assertTrue(result.seat_truth)
        self.assertTrue(result.keeper_closed_truth)
        self.assertIn(EventKind.CAPTURE_CONFIRMED, bench.kinds())
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, bench.kinds())

    def test_controller_reset_keeps_the_mechanism(self) -> None:
        bench = _Bench()
        bench.fly_in(commands=ENABLE)
        position = bench.mech.servo.position
        phase = bench.mech.probe_phase
        bench.mech.reset_controller()
        self.assertIs(bench.mech.controller.state, DockState.OPEN)
        self.assertEqual(bench.mech.servo.position, position)
        self.assertIs(bench.mech.probe_phase, phase)


class AcceptanceEnvelopeTests(unittest.TestCase):
    """The architecture's whole argument, and where it stops being true."""

    def test_off_axis_capture_is_carried_off_axis(self) -> None:
        """A cup does not centre.  An aircraft caught at 30 mm stays at 30 mm.

        This is the trade against the baseline, whose funnel taper pulls the
        probe to within 2 mm of the throat axis before the fork moves.
        """

        offset = 0.030
        bench = _Bench()
        result = bench.fly_in(lateral_m=offset, commands=ENABLE)
        self.assertTrue(result.controller.capture_confirmed)
        self.assertTrue(result.keeper_closed_truth)
        self.assertAlmostEqual(bench.drone.position.x, offset, places=6)
        self.assertNotIn(EventKind.PROP_FUNNEL_CONTACT, bench.kinds())

    def test_sensed_envelope_is_narrower_than_the_bore(self) -> None:
        """Mechanically seated, and the crown switch cannot see it.

        The floating crown plate tips under an off-centre load, so the
        sensed envelope (±35 mm) is the number the architecture can claim,
        not the mechanical ±72.5 mm.  Truth says seated, indication says
        nothing, and no capture follows — which is the safe direction.
        """

        bench = _Bench()
        offset = 0.050
        self.assertGreater(offset, bench.geometry.crown_switch_radius_m)
        self.assertLess(offset, bench.geometry.prop_clearance_m)

        result = bench.fly_in(lateral_m=offset, commands=ENABLE)
        self.assertIs(result.probe_phase, ProbePhase.SEATED)
        self.assertTrue(result.seat_truth)
        self.assertFalse(result.reported_s1)
        self.assertIs(result.controller.state, DockState.OPEN)
        self.assertFalse(result.controller.capture_confirmed)
        self.assertNotIn(EventKind.PROP_FUNNEL_CONTACT, bench.kinds())

    def test_supervisor_seat_confirm_caps_the_acceptance(self) -> None:
        """The mechanism's acceptance is not the system's acceptance.

        ``GuidanceParams.seat_confirm_m`` is a 3D navigation distance to a
        *point*, sized for a throat.  A cup has no point, and a non-centring
        cup keeps whatever lateral offset the approach arrived with, so the
        shared supervisor refuses to enable capture on captures the cup
        would happily make.  Relaxing the constant recovers them — and that
        is a software trade against the finding-2 plausibility gate, not a
        mechanism improvement.
        """

        tight = sum(_episode(s).outcome is EpisodeOutcome.SUCCESS for s in SEEDS)
        relaxed_params = replace(GuidanceParams(), seat_confirm_m=0.025)
        relaxed = sum(
            _episode(s, guidance=relaxed_params).outcome is EpisodeOutcome.SUCCESS
            for s in SEEDS
        )
        self.assertGreater(relaxed, tight)


class ContactModelTests(unittest.TestCase):
    """The cup has no benign contact surface.  Prove the model knows that."""

    def test_rotor_disc_strikes_the_wall_after_the_cap_is_already_inside(self) -> None:
        """The mouth accepts the crown 40 mm before it rejects the rotors.

        The funnel rejects a bad approach at the entrance plane.  The cup
        swallows the crown cap first and only discovers the problem when the
        rotor plane reaches the rim, by which point the aircraft is
        committed.  That ordering is the hazard, so the test checks the
        order, not just the events.
        """

        bench = _Bench()
        offset = 0.090
        self.assertGreater(offset, bench.geometry.prop_clearance_m)
        bench.fly_in(lateral_m=offset)

        kinds = bench.kinds()
        self.assertIn(EventKind.FUNNEL_INSERTION, kinds)
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, kinds)
        self.assertLess(
            kinds.index(EventKind.FUNNEL_INSERTION),
            kinds.index(EventKind.PROP_FUNNEL_CONTACT),
        )
        contact = next(
            e for e in bench.events if e.kind is EventKind.PROP_FUNNEL_CONTACT
        )
        self.assertIn("rotor_wall", contact.detail)
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, UNSAFE_EVENT_KINDS)

    def test_mouth_ring_strike_outside_the_cap_window(self) -> None:
        bench = _Bench()
        bench.fly_in(lateral_m=0.200)
        kinds = bench.kinds()
        self.assertIn(EventKind.PROP_FUNNEL_CONTACT, kinds)
        self.assertNotIn(EventKind.FUNNEL_INSERTION, kinds)

    def test_clean_miss_is_not_scored_as_contact(self) -> None:
        """Under-reporting is the failure mode; over-reporting is one too."""

        bench = _Bench()
        bench.fly_in(lateral_m=0.320)
        self.assertEqual(bench.events, [])

    def test_latch_swept_into_the_airframe_is_a_contact(self) -> None:
        """Closing the bar too low drives its ramp into the belly hoop.

        Reached the way the FMECA says it is reached: a stuck-actuated crown
        switch (FM-SN-03) lets the controller command close while the
        aircraft is still short of the seat.  The baseline fork has no
        equivalent because it only ever crosses a Ø16 mm throat.
        """

        bench = _Bench()
        geometry = bench.geometry
        low_crown = geometry.latch_face_m - geometry.latch_cam_lift_m - 0.010
        bench.fly_in(stop_crown_z=low_crown + geometry.belly_below_crown_m)
        bench.mech.seat_switch.fault = SwitchFault.STUCK_CLOSED
        bench.hold(60, commands=ENABLE)

        contacts = [
            e for e in bench.events if e.kind is EventKind.PROP_FUNNEL_CONTACT
        ]
        self.assertTrue(contacts)
        self.assertIn("latch_swept_into_airframe", contacts[-1].detail)

    def test_wind_turns_lateral_excursion_into_rotor_strikes(self) -> None:
        """The sharpest form of the same defect, at episode level.

        A funnel absorbs a wind-driven lateral excursion as a centring push.
        A straight bore has nothing benign to absorb it with, so the same
        excursion reaches the wall as a guarded-rotor contact.  The baseline
        strikes nothing at this wind level; the deep cup does.
        """

        wind = outdoor_breeze(1.0)
        seeds = range(1, 5)  # windy episodes are slow; four is enough to see it

        def contacts(build):
            found = []
            for seed in seeds:
                config = sil_p0b(seed, air=wind)
                config = replace(config, max_duration_s=45.0)
                if build is not None:
                    config = replace(config, mechanism_factory=build)
                found.extend(
                    e
                    for e in run_episode(config, seed).events
                    if e.kind is EventKind.PROP_FUNNEL_CONTACT
                )
            return found

        deep = contacts(mechanism_factory)
        baseline = contacts(None)
        self.assertTrue(deep, "the wind-driven rotor strike disappeared")
        self.assertGreater(len(deep), len(baseline))

    def test_overspeed_arrival_at_the_deck_pad(self) -> None:
        bench = _Bench()
        bench.fly_in(climb_m_s=bench.geometry.seat_impact_speed_m_s + 0.10)
        self.assertIn(EventKind.OVERSPEED_CONTACT, bench.kinds())


class RetentionAndReleaseTests(unittest.TestCase):
    """Rev-A's defect was a keeper that could not let go.  Check this one can."""

    def _capture_and_disarm(self, bench: _Bench):
        result = bench.fly_in(commands=ENABLE)
        self.assertTrue(result.controller.capture_confirmed)
        bench.drone.disarm()
        return result

    def test_no_passive_retention_before_the_bar_closes(self) -> None:
        """Nothing holds an unpowered aircraft in an open cup.  It falls.

        The baseline pins a disarmed aircraft to its seat by fiat, which
        docs/dock-deletion-review.md calls out as a model that never tests
        the retention claim it makes.  This one lets go.
        """

        bench = _Bench()
        bench.fly_in()  # no capture_enable: the bar never closes
        self.assertIs(bench.mech.probe_phase, ProbePhase.SEATED)
        seated_z = bench.crown_z
        bench.drone.disarm()
        bench.coast(40)
        self.assertLess(bench.crown_z, seated_z)
        self.assertIn(EventKind.PROBE_WITHDRAWN, bench.kinds())

    def test_bar_leaving_under_load_is_a_dropped_aircraft(self) -> None:
        """FM-KP-04: back-drive out of engagement with an aircraft on it."""

        bench = _Bench()
        self._capture_and_disarm(bench)
        bench.mech.servo.position = 0.0  # horn slip / back-drive
        bench.coast(4, commands=ENABLE)
        self.assertIn(EventKind.DROPPED_AIRCRAFT, bench.kinds())

    def test_commanded_release_lets_a_disarmed_aircraft_go(self) -> None:
        bench = _Bench()
        self._capture_and_disarm(bench)
        seated_z = bench.crown_z
        bench.coast(120, commands=DockCommands(release_request=True))

        self.assertTrue(bench.mech.servo.physically_open)
        self.assertIn(EventKind.RELEASED, bench.kinds())
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, bench.kinds())
        self.assertLess(bench.crown_z, seated_z)

    def test_release_works_under_the_bench_screening_load(self) -> None:
        """Loaded release at the P0-A 5 N axial screen still opens the bar."""

        bench = _Bench()
        self._capture_and_disarm(bench)
        bench.mech.external_load_n = 5.0
        bench.coast(120, commands=DockCommands(release_request=True))
        self.assertFalse(bench.mech.latch_bound)
        self.assertTrue(bench.mech.servo.physically_open)
        self.assertIn(EventKind.RELEASED, bench.kinds())

    def test_release_binds_above_the_pivot_moment_allowance(self) -> None:
        """The claimed weakness, exercised: past ~12 N the bar cannot open.

        A full-bore bar reacts the retained load up to half a span from its
        pivot.  Above the modelled boss allowance the bar tips in its
        bearing and stops moving in both directions, the controller times
        out into FAULT_OPEN, and the aircraft is still hanging there.
        """

        bench = _Bench()
        self._capture_and_disarm(bench)
        self.assertLess(bench.mech.latch_bind_load_n, 20.0)
        bench.mech.external_load_n = 20.0
        result = bench.coast(120, commands=DockCommands(release_request=True))

        self.assertTrue(bench.mech.latch_bound)
        self.assertTrue(bench.mech.servo.physically_closed)
        self.assertTrue(result.keeper_closed_truth)
        self.assertIs(result.controller.state, DockState.FAULT_OPEN)
        self.assertNotIn(EventKind.DROPPED_AIRCRAFT, bench.kinds())

    def test_static_release_margins_match_the_claimed_weakness(self) -> None:
        mech = SPEC.build(DT)
        # Friction margin is generous: the load is normal to the travel.
        self.assertGreaterEqual(mech.release_force_margin(5.0), 2.0)
        # The pivot boss is the problem, and only while the bar is
        # unsupported — which is exactly when its cam ramp lifts an aircraft.
        self.assertGreaterEqual(mech.pivot_moment_margin(5.0), 2.0)
        self.assertLess(mech.pivot_moment_margin(5.0, far_catch_engaged=False), 2.0)


class LaunchScenarioTests(unittest.TestCase):
    """The finding the trade-study harness cannot see."""

    def test_seed_seated_supports_a_launch_scenario(self) -> None:
        """The engine's pre-roll must be able to start this cup captured."""

        result = _episode(2, scenario=sil_p0c)
        self.assertGreater(result.duration_s, 0.0)

    def test_launch_departure_walks_the_rotors_into_the_bore_wall(self) -> None:
        """Unsafe on P0-C with no fault injected, and why.

        In DEPART the guidance stack's carrier-proximity reflex commands
        0.6 m/s laterally while the aircraft is still 60 mm inside the cup.
        The baseline survives the identical command because the funnel taper
        physically clamps the probe to a few millimetres of the axis on the
        way out; a straight bore has no such veto, so the guarded rotors
        reach the wall.  This is pinned as a test because it is the
        candidate's disqualifying result, and because ``sil_p0b`` runs on a
        bench rig with no hull and therefore never exercises the reflex —
        the trade study alone would have reported this architecture clean.
        """

        strikes = []
        for seed in SEEDS:
            result = _episode(seed, scenario=sil_p0c)
            strikes.extend(
                event
                for event in result.events
                if event.kind is EventKind.PROP_FUNNEL_CONTACT and event.t_s < 2.0
            )
        self.assertTrue(strikes, "the launch-departure rotor strike disappeared")
        self.assertIn("rotor_wall", strikes[0].detail)

    def test_sil_p0b_cannot_see_the_launch_strike(self) -> None:
        """Records why the study harness is not sufficient evidence here.

        The same seeds, on the bench rig the trade study actually runs, are
        clean.  A candidate can therefore pass the study and still be unsafe
        on a carrier, which is a statement about the harness.
        """

        for seed in SEEDS:
            self.assertEqual(_episode(seed).unsafe_events, ())


class CostTermTests(unittest.TestCase):
    """Numbers the twin cannot compute, pinned so they cannot drift silently."""

    def test_mass_estimate_blows_the_dock_allocation(self) -> None:
        self.assertGreater(SPEC.est_dock_mass_g, 180.0)
        self.assertGreater(SPEC.est_dock_mass_g, 4.0 * 75.0)  # baseline dock

    def test_aircraft_side_mass_stays_inside_the_probe_budget(self) -> None:
        self.assertLessEqual(SPEC.est_probe_mass_g, 8.0)

    def test_two_sensed_channels_and_one_actuator(self) -> None:
        self.assertEqual(SPEC.sensed_channels, 2)
        self.assertEqual(SPEC.actuator_count, 1)

    def test_weaknesses_are_stated(self) -> None:
        self.assertGreaterEqual(len(SPEC.known_weaknesses), 8)


if __name__ == "__main__":
    unittest.main()
