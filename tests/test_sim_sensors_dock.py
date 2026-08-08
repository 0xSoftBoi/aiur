"""Tests for the digital-twin measurement chain and the mechanical dock seam.

Covers aiur/sim/sensors.py (PoseSensor, Switch, KeeperServo) and
aiur/sim/dock_physics.py (DockAssembly, which wraps the REAL
aiur.dock_controller.DockController).  The drone is driven kinematically:
tests set position/velocity between dock steps instead of flying the body.

All tests use fixed seeds and fixed-step timing; nothing here depends on
wall-clock time or platform randomness.
"""

import random
import unittest

from aiur.dock_controller import DockState, KeeperCommand
from aiur.sim.bodies import DroneBody, DroneParams
from aiur.sim.dock_physics import (
    DockAssembly,
    DockCommands,
    DockGeometry,
    ProbePhase,
)
from aiur.sim.events import EventKind
from aiur.sim.sensors import (
    TOY_GRADE,
    KeeperServo,
    PoseSensor,
    PoseSensorParams,
    Switch,
    SwitchFault,
)
from aiur.sim.vec import ZERO, Vec3

#: Engine fixed step (50 Hz), matching aiur/sim/engine.py.
DT = 0.02

#: Dock entrance-plane center used by all DockAssembly tests.
CENTER = Vec3()


def quiet_sensor_params(**overrides: float) -> PoseSensorParams:
    """Sensor params with every stochastic term disabled unless overridden."""

    base = dict(
        position_sigma_m=0.0,
        velocity_sigma_m_s=0.0,
        latency_s=0.0,
        dropout_rate_per_s=0.0,
        dropout_duration_s=0.0,
    )
    base.update(overrides)
    return PoseSensorParams(**base)


class PoseSensorTests(unittest.TestCase):
    def test_position_step_appears_after_configured_latency(self) -> None:
        params = quiet_sensor_params(latency_s=0.06)
        sensor = PoseSensor(params, random.Random(1), DT)
        before = Vec3(0.0, 0.0, 0.0)
        after = Vec3(1.0, 2.0, 3.0)

        measurement = None
        for _ in range(6):
            measurement = sensor.step(before, ZERO)
        self.assertTrue(measurement.valid)
        self.assertEqual(measurement.position, before)
        self.assertAlmostEqual(measurement.age_s, params.latency_s)

        delay_steps = round(params.latency_s / DT)
        readings = []
        for _ in range(delay_steps + 1):
            readings.append(sensor.step(after, ZERO).position)

        # The step change stays invisible for exactly delay_steps samples,
        # then appears: a latency of ~latency_s at the sensor rate.
        for reading in readings[:delay_steps]:
            self.assertEqual(reading, before)
        self.assertEqual(readings[delay_steps], after)

    def test_position_noise_is_zero_mean_at_small_sigma(self) -> None:
        params = quiet_sensor_params(position_sigma_m=0.003)
        sensor = PoseSensor(params, random.Random(2024), DT)
        truth = Vec3(1.0, -2.0, 0.5)

        n = 400
        sum_x = sum_y = sum_z = 0.0
        saw_noise = False
        for _ in range(n):
            measurement = sensor.step(truth, ZERO)
            self.assertTrue(measurement.valid)
            residual = measurement.position - truth
            sum_x += residual.x
            sum_y += residual.y
            sum_z += residual.z
            if residual.norm() > 0.0:
                saw_noise = True

        self.assertTrue(saw_noise)
        # Standard error of the mean is sigma/sqrt(n) = 0.15 mm; 1 mm is a
        # generous bound and the fixed seed makes the check deterministic.
        self.assertLess(abs(sum_x / n), 0.001)
        self.assertLess(abs(sum_y / n), 0.001)
        self.assertLess(abs(sum_z / n), 0.001)

    def test_forced_outage_invalidates_and_ages_measurement(self) -> None:
        params = quiet_sensor_params(latency_s=0.04)
        sensor = PoseSensor(params, random.Random(3), DT)
        truth = Vec3(0.5, 0.0, 0.0)

        measurement = None
        for _ in range(5):
            measurement = sensor.step(truth, ZERO)
        self.assertTrue(measurement.valid)
        self.assertAlmostEqual(measurement.age_s, params.latency_s)

        sensor.forced_outage = True
        for i in range(1, 5):
            measurement = sensor.step(truth, ZERO)
            self.assertFalse(measurement.valid)
            # The last good fix is held while the age keeps growing.
            self.assertEqual(measurement.position, truth)
            self.assertAlmostEqual(measurement.age_s, params.latency_s + i * DT)

        sensor.forced_outage = False
        measurement = sensor.step(truth, ZERO)
        self.assertTrue(measurement.valid)
        self.assertAlmostEqual(measurement.age_s, params.latency_s)

    def test_bias_shifts_the_reported_position(self) -> None:
        sensor = PoseSensor(quiet_sensor_params(), random.Random(4), DT)
        truth = Vec3(0.3, 0.4, -0.1)
        bias = Vec3(0.05, -0.02, 0.01)
        sensor.bias = bias

        measurement = sensor.step(truth, ZERO)
        self.assertTrue(measurement.valid)
        self.assertEqual(measurement.position, truth + bias)

    def test_same_seed_produces_identical_measurement_stream(self) -> None:
        def run(seed: int) -> list:
            sensor = PoseSensor(TOY_GRADE, random.Random(seed), DT)
            stream = []
            for i in range(200):
                truth_p = Vec3(0.01 * i, -0.02 * i, 0.005 * i)
                truth_v = Vec3(0.5, -1.0, 0.25)
                stream.append(sensor.step(truth_p, truth_v))
            return stream

        self.assertEqual(run(99), run(99))


class SwitchTests(unittest.TestCase):
    def test_debounce_delays_flip_by_configured_steps(self) -> None:
        switch = Switch(debounce_s=0.06, dt_s=DT)  # three debounce steps

        self.assertFalse(switch.step(True))
        self.assertFalse(switch.step(True))
        self.assertTrue(switch.step(True))

        self.assertTrue(switch.step(False))
        self.assertTrue(switch.step(False))
        self.assertFalse(switch.step(False))

    def test_short_glitch_is_rejected_by_debounce(self) -> None:
        switch = Switch(debounce_s=0.06, dt_s=DT)
        self.assertFalse(switch.step(True))
        self.assertFalse(switch.step(False))
        self.assertFalse(switch.step(True))
        self.assertFalse(switch.step(False))

    def test_stuck_open_reports_false_regardless_of_physical_state(self) -> None:
        switch = Switch(dt_s=DT)
        switch.fault = SwitchFault.STUCK_OPEN
        for _ in range(5):
            self.assertFalse(switch.step(True))

    def test_stuck_closed_reports_true_regardless_of_physical_state(self) -> None:
        switch = Switch(dt_s=DT)
        switch.fault = SwitchFault.STUCK_CLOSED
        for _ in range(5):
            self.assertTrue(switch.step(False))


class KeeperServoTests(unittest.TestCase):
    def test_close_travel_time_matches_within_one_step(self) -> None:
        travel_time_s = 0.35
        servo = KeeperServo(travel_time_s=travel_time_s)
        self.assertTrue(servo.physically_open)

        steps = 0
        while not servo.physically_closed:
            servo.step(DT, close_commanded=True)
            steps += 1
            self.assertLess(steps, 100, "servo never reached closed")

        self.assertLessEqual(abs(steps * DT - travel_time_s), DT + 1e-9)

    def test_jam_freezes_position_in_both_directions(self) -> None:
        servo = KeeperServo(travel_time_s=0.35)
        for _ in range(5):
            servo.step(DT, close_commanded=True)
        frozen = servo.position
        self.assertGreater(frozen, 0.0)

        servo.jammed = True
        for _ in range(10):
            servo.step(DT, close_commanded=True)
        self.assertEqual(servo.position, frozen)
        for _ in range(10):
            servo.step(DT, close_commanded=False)
        self.assertEqual(servo.position, frozen)


class DockAssemblyTests(unittest.TestCase):
    """Drives a real DroneBody kinematically against the mechanical dock."""

    def _dock(self) -> DockAssembly:
        return DockAssembly(DockGeometry(), dt_s=DT)

    def _drone(self) -> DroneBody:
        return DroneBody(DroneParams(), Vec3())

    def _step(self, dock, drone, t, commands=None):
        if commands is None:
            commands = DockCommands()
        return dock.step(t, CENTER, ZERO, drone, commands)

    def _cross_entrance(self, dock, drone, *, lateral_m=0.0, vz=0.1):
        """Drive the probe tip up through the entrance plane in two steps.

        Returns (t, first_result, crossing_result).
        """

        h = dock.geometry.probe_height_m
        drone.position = Vec3(lateral_m, 0.0, -0.005 - h)  # tip 5 mm below plane
        drone.velocity = Vec3(0.0, 0.0, vz)
        first = self._step(dock, drone, 0.0)
        drone.position = Vec3(lateral_m, 0.0, 0.005 - h)  # tip 5 mm above plane
        crossing = self._step(dock, drone, DT)
        return DT, first, crossing

    def _rise_to_seat(self, dock, drone, t):
        """Integrate the drone upward at its own velocity until it seats."""

        events = []
        last = None
        for _ in range(80):
            t += DT
            drone.position = drone.position + drone.velocity * DT
            last = self._step(dock, drone, t)
            events.extend(last.events)
            if dock.probe_phase is ProbePhase.SEATED:
                break
        return t, events, last

    def _enable_capture(self, dock, drone, t):
        """Hold capture_enable until the real controller confirms capture."""

        events = []
        last = None
        for _ in range(60):
            t += DT
            last = self._step(dock, drone, t, DockCommands(capture_enable=True))
            events.extend(last.events)
            if last.controller.capture_confirmed:
                break
        return t, events, last

    def _seated_dock(self):
        dock = self._dock()
        drone = self._drone()
        t, _, crossing = self._cross_entrance(dock, drone, vz=0.1)
        self.assertIs(crossing.probe_phase, ProbePhase.INSERTED)
        t, _, last = self._rise_to_seat(dock, drone, t)
        self.assertIs(dock.probe_phase, ProbePhase.SEATED)
        self.assertTrue(last.seat_truth)
        return dock, drone, t

    def _captured_dock(self):
        dock, drone, t = self._seated_dock()
        t, _, last = self._enable_capture(dock, drone, t)
        self.assertTrue(last.controller.capture_confirmed)
        return dock, drone, t

    def test_gentle_centered_crossing_inserts_seats_and_captures(self) -> None:
        dock = self._dock()
        drone = self._drone()

        t, first, crossing = self._cross_entrance(dock, drone, vz=0.1)
        self.assertEqual(first.events, ())
        self.assertEqual(
            [e.kind for e in crossing.events], [EventKind.FUNNEL_INSERTION]
        )
        self.assertIs(crossing.probe_phase, ProbePhase.INSERTED)
        self.assertAlmostEqual(crossing.contact_closing_speed_m_s, 0.1)

        t, rise_events, last = self._rise_to_seat(dock, drone, t)
        self.assertIs(dock.probe_phase, ProbePhase.SEATED)
        self.assertIn(EventKind.PROBE_SEATED, [e.kind for e in rise_events])
        self.assertTrue(last.seat_truth)
        # Without capture_enable, the real controller must sit in OPEN.
        self.assertEqual(last.controller.state, DockState.OPEN)
        self.assertFalse(last.controller.capture_confirmed)

        t, capture_events, last = self._enable_capture(dock, drone, t)
        self.assertEqual(last.controller.state, DockState.CAPTURED)
        self.assertTrue(last.controller.capture_confirmed)
        self.assertTrue(last.keeper_closed_truth)
        self.assertTrue(last.reported_s1)
        self.assertTrue(last.reported_s2)
        capture_kinds = [e.kind for e in capture_events]
        self.assertIn(EventKind.CAPTURE_CONFIRMED, capture_kinds)
        self.assertNotIn(EventKind.FALSE_CAPTURE_CONFIRMED, capture_kinds)

    def test_rim_annulus_crossing_scores_prop_funnel_contact(self) -> None:
        dock = self._dock()
        drone = self._drone()
        g = dock.geometry
        lateral = g.funnel_entrance_radius_m + 0.5 * g.rim_annulus_m

        _, _, crossing = self._cross_entrance(dock, drone, lateral_m=lateral, vz=0.1)
        self.assertEqual(
            [e.kind for e in crossing.events], [EventKind.PROP_FUNNEL_CONTACT]
        )
        self.assertIs(crossing.probe_phase, ProbePhase.FREE)
        # The funnel edge deflects the aircraft downward.
        self.assertLess(drone.velocity.z, 0.0)

    def test_overspeed_crossing_bounces_without_insertion(self) -> None:
        dock = self._dock()
        drone = self._drone()
        g = dock.geometry
        vz = 2.0 * g.bounce_speed_m_s

        _, _, crossing = self._cross_entrance(dock, drone, vz=vz)
        self.assertEqual(
            [e.kind for e in crossing.events], [EventKind.OVERSPEED_CONTACT]
        )
        self.assertIs(crossing.probe_phase, ProbePhase.FREE)
        self.assertAlmostEqual(crossing.contact_closing_speed_m_s, vz)
        # Bounce: half the closing speed, reversed.
        self.assertAlmostEqual(drone.velocity.z, -0.5 * vz)

    def test_off_axis_insertion_is_centered_by_funnel_taper(self) -> None:
        dock = self._dock()
        drone = self._drone()
        g = dock.geometry

        t, _, crossing = self._cross_entrance(dock, drone, lateral_m=0.05, vz=0.1)
        self.assertIs(crossing.probe_phase, ProbePhase.INSERTED)

        for _ in range(80):
            t += DT
            drone.position = drone.position + drone.velocity * DT
            self._step(dock, drone, t)
            rel = (drone.position + Vec3(0.0, 0.0, g.probe_height_m)) - CENTER
            # Mirrors _funnel_allowed_radius: linear taper plus 2 mm clearance.
            allowed = (
                g.funnel_entrance_radius_m
                * max(0.0, 1.0 - rel.z / g.seat_travel_m)
                + 0.002
            )
            self.assertLessEqual(rel.lateral_norm(), allowed + 1e-9)
            if dock.probe_phase is ProbePhase.SEATED:
                break

        self.assertIs(dock.probe_phase, ProbePhase.SEATED)
        # The seat pins the probe on the dock axis.
        self.assertAlmostEqual(drone.position.lateral_norm(), 0.0)

    def test_seated_armed_drone_descending_pulls_out_of_open_collet(self) -> None:
        dock, drone, t = self._seated_dock()
        g = dock.geometry
        self.assertTrue(drone.armed)
        self.assertFalse(dock.servo.physically_closed)

        descent = 4.0 * g.collet_pullout_speed_m_s
        drone.velocity = Vec3(0.0, 0.0, -descent)
        drone.position = drone.position + drone.velocity * DT
        result = self._step(dock, drone, t + DT)

        self.assertIn(EventKind.PROBE_WITHDRAWN, [e.kind for e in result.events])
        self.assertIs(result.probe_phase, ProbePhase.INSERTED)
        self.assertFalse(result.seat_truth)

    def test_emergency_release_from_captured_drives_keeper_open(self) -> None:
        dock, drone, t = self._captured_dock()
        self.assertTrue(dock.servo.physically_closed)

        t += DT
        result = self._step(dock, drone, t, DockCommands(emergency_release=True))
        self.assertEqual(result.controller.state, DockState.RELEASING)
        self.assertEqual(result.controller.keeper_command, KeeperCommand.OPEN)
        self.assertFalse(result.controller.capture_confirmed)
        self.assertIn(EventKind.RELEASED, [e.kind for e in result.events])

        for _ in range(25):
            t += DT
            result = self._step(dock, drone, t, DockCommands(emergency_release=True))
        self.assertTrue(dock.servo.physically_open)
        self.assertFalse(result.keeper_closed_truth)

    def test_disarmed_drone_with_keeper_open_uncommanded_is_dropped(self) -> None:
        dock, drone, t = self._captured_dock()
        drone.disarm()
        # Mechanical failure: keeper falls open with no release commanded.
        dock.servo.position = 0.0

        result = self._step(dock, drone, t + DT)
        self.assertFalse(result.keeper_closed_truth)
        self.assertIn(EventKind.DROPPED_AIRCRAFT, [e.kind for e in result.events])


if __name__ == "__main__":
    unittest.main()
