"""Physics-layer tests for the CARRIER-P0 digital twin.

Covers aiur/sim/vec.py, aiur/sim/disturbances.py, and aiur/sim/bodies.py.
Everything is deterministic: seeded RNGs only, no wall-clock dependence.
"""

import math
import random
import unittest

from aiur.sim.bodies import (
    CarrierBody,
    CarrierParams,
    DroneBody,
    DroneParams,
    KinematicRig,
    RigParams,
)
from aiur.sim.disturbances import (
    INDOOR_CALM,
    AirModel,
    AirModelParams,
    outdoor_breeze,
)
from aiur.sim.vec import ZERO, Vec3


DT = 0.02  # engine step, 50 Hz


class VecTestMixin:
    def assertVecAlmostEqual(self, a, b, places=7, msg=None):
        self.assertAlmostEqual(a.x, b.x, places=places, msg=msg)
        self.assertAlmostEqual(a.y, b.y, places=places, msg=msg)
        self.assertAlmostEqual(a.z, b.z, places=places, msg=msg)


class Vec3Tests(unittest.TestCase, VecTestMixin):
    def test_arithmetic_operators(self) -> None:
        a = Vec3(1.0, -2.0, 3.0)
        b = Vec3(0.5, 4.0, -1.0)
        self.assertEqual(a + b, Vec3(1.5, 2.0, 2.0))
        self.assertEqual(a - b, Vec3(0.5, -6.0, 4.0))
        self.assertEqual(a * 2.0, Vec3(2.0, -4.0, 6.0))
        self.assertEqual(2.0 * a, Vec3(2.0, -4.0, 6.0))
        self.assertEqual(-a, Vec3(-1.0, 2.0, -3.0))

    def test_norm_and_lateral_norm(self) -> None:
        v = Vec3(3.0, 4.0, 12.0)
        self.assertAlmostEqual(v.norm(), 13.0)
        self.assertAlmostEqual(v.lateral_norm(), 5.0)
        self.assertEqual(ZERO.norm(), 0.0)
        self.assertEqual(Vec3(0.0, 0.0, 9.0).lateral_norm(), 0.0)

    def test_clamped_respects_norm_bound(self) -> None:
        v = Vec3(3.0, 4.0, 0.0)  # norm 5
        clamped = v.clamped(2.5)
        self.assertAlmostEqual(clamped.norm(), 2.5)
        # Direction is preserved.
        self.assertVecAlmostEqual(clamped, Vec3(1.5, 2.0, 0.0))

    def test_clamped_returns_vector_unchanged_when_within_bound(self) -> None:
        v = Vec3(0.1, -0.2, 0.05)
        self.assertIs(v.clamped(1.0), v)
        self.assertIs(ZERO.clamped(0.0), ZERO)

    def test_clamped_rejects_negative_bound(self) -> None:
        with self.assertRaises(ValueError):
            Vec3(1.0, 0.0, 0.0).clamped(-0.1)

    def test_lateral_and_with_z_helpers(self) -> None:
        v = Vec3(1.0, 2.0, 3.0)
        self.assertEqual(v.lateral(), Vec3(1.0, 2.0, 0.0))
        self.assertEqual(v.with_z(-5.0), Vec3(1.0, 2.0, -5.0))


class AirModelTests(unittest.TestCase):
    def test_zero_sigma_returns_exactly_the_mean_wind(self) -> None:
        mean = Vec3(0.2, -0.1, 0.05)
        model = AirModel(AirModelParams(mean_wind=mean, sigma_m_s=0.0), random.Random(1))
        for _ in range(20):
            self.assertEqual(model.step(DT), mean)

    def test_same_seed_reproduces_identical_sequence(self) -> None:
        params = AirModelParams(
            mean_wind=Vec3(0.1, 0.0, 0.0), sigma_m_s=0.2, correlation_time_s=1.0
        )
        model_a = AirModel(params, random.Random(123))
        model_b = AirModel(params, random.Random(123))
        seq_a = [model_a.step(DT) for _ in range(50)]
        seq_b = [model_b.step(DT) for _ in range(50)]
        self.assertEqual(seq_a, seq_b)
        # The process actually fluctuates; this is not a degenerate check.
        self.assertTrue(any(v != params.mean_wind for v in seq_a))

    def test_parameter_validation_raises(self) -> None:
        with self.assertRaises(ValueError):
            AirModelParams(sigma_m_s=-0.01)
        with self.assertRaises(ValueError):
            AirModelParams(vertical_sigma_scale=-0.5)
        with self.assertRaises(ValueError):
            AirModelParams(correlation_time_s=0.0)
        with self.assertRaises(ValueError):
            outdoor_breeze(-1.0)
        with self.assertRaises(ValueError):
            AirModel(INDOOR_CALM, random.Random(0)).step(0.0)

    def test_outdoor_breeze_scales_with_mean_speed(self) -> None:
        params = outdoor_breeze(2.0)
        self.assertEqual(params.mean_wind, Vec3(2.0, 0.0, 0.0))
        self.assertAlmostEqual(params.sigma_m_s, 0.5)


class DroneBodyTests(unittest.TestCase, VecTestMixin):
    def test_converges_to_commanded_velocity_in_still_air(self) -> None:
        drone = DroneBody(DroneParams(), Vec3())
        command = Vec3(0.3, 0.0, 0.0)
        for _ in range(500):  # 10 s, ~50 closed-loop time constants
            drone.step(DT, command, ZERO)
        # The wind-coupling drag acts even in still air, so the model settles
        # at a documented steady-state tracking offset below the command:
        # v_ss = cmd * (1/tau) / (1/tau + k_wind)  (~82% of cmd for defaults).
        p = drone.params
        gain = (1.0 / p.velocity_tau_s) / (1.0 / p.velocity_tau_s + p.wind_coupling_per_s)
        self.assertVecAlmostEqual(drone.velocity, command * gain, places=4)
        self.assertGreater(drone.velocity.x, 0.8 * command.x)
        self.assertEqual(drone.velocity.y, 0.0)
        self.assertEqual(drone.velocity.z, 0.0)

    def test_constant_wind_with_zero_command_causes_steady_drift(self) -> None:
        drone = DroneBody(DroneParams(), Vec3())
        wind = Vec3(0.8, 0.0, 0.0)
        for _ in range(500):  # 10 s
            drone.step(DT, ZERO, wind)
        p = drone.params
        expected = wind.x * p.wind_coupling_per_s / (
            1.0 / p.velocity_tau_s + p.wind_coupling_per_s
        )
        self.assertAlmostEqual(drone.velocity.x, expected, places=4)
        self.assertGreater(drone.velocity.x, 0.05)
        self.assertGreater(drone.position.x, 0.0)

    def test_acceleration_limit_bounds_velocity_change_per_step(self) -> None:
        drone = DroneBody(DroneParams(), Vec3())
        command = Vec3(2.5, 0.0, 0.0)  # demands 10 m/s^2 unclamped tracking
        max_accel = drone.params.max_accel_m_s2
        previous = drone.velocity
        first_delta = None
        for _ in range(200):
            drone.step(DT, command, ZERO)
            delta = (drone.velocity - previous).norm()
            if first_delta is None:
                first_delta = delta
            # In still air the drag disturbance opposes motion, so the
            # clamped tracking term is the only accelerating force and the
            # per-step velocity change stays within the limit.
            self.assertLessEqual(delta, max_accel * DT + 1e-12)
            previous = drone.velocity
        # From rest the very first step rides the clamp exactly.
        self.assertAlmostEqual(first_delta, max_accel * DT)

    def test_disarmed_drone_ignores_step(self) -> None:
        drone = DroneBody(DroneParams(), Vec3(1.0, 2.0, 3.0))
        drone.step(DT, Vec3(0.5, 0.0, 0.0), ZERO)
        drone.disarm()
        self.assertFalse(drone.armed)
        self.assertEqual(drone.velocity, ZERO)
        position = drone.position
        remaining = drone.remaining_flight_s
        for _ in range(10):
            drone.step(DT, Vec3(1.0, 1.0, 1.0), Vec3(2.0, 0.0, 0.0))
        self.assertEqual(drone.position, position)
        self.assertEqual(drone.velocity, ZERO)
        self.assertEqual(drone.remaining_flight_s, remaining)

    def test_battery_drains_with_drain_multiplier(self) -> None:
        nominal = DroneBody(DroneParams(), Vec3())
        sagging = DroneBody(DroneParams(), Vec3())
        sagging.drain_multiplier = 2.0
        for _ in range(10):  # 0.2 s of flight
            nominal.step(DT, ZERO, ZERO)
            sagging.step(DT, ZERO, ZERO)
        endurance = DroneParams().endurance_s
        self.assertAlmostEqual(nominal.remaining_flight_s, endurance - 0.2)
        self.assertAlmostEqual(sagging.remaining_flight_s, endurance - 0.4)

    def test_battery_never_goes_negative(self) -> None:
        drone = DroneBody(DroneParams(), Vec3())
        drone.remaining_flight_s = 0.01
        drone.step(DT, ZERO, ZERO)
        self.assertEqual(drone.remaining_flight_s, 0.0)


class CarrierBodyTests(unittest.TestCase, VecTestMixin):
    def test_stays_put_at_setpoint_with_no_disturbance(self) -> None:
        start = Vec3(1.0, -2.0, 3.0)
        carrier = CarrierBody(CarrierParams(), start)
        for _ in range(200):
            carrier.step(0.05, ZERO)
        self.assertEqual(carrier.position, start)
        self.assertEqual(carrier.velocity, ZERO)

    def test_displaced_carrier_returns_toward_station_setpoint(self) -> None:
        setpoint = Vec3()
        carrier = CarrierBody(
            CarrierParams(), Vec3(1.0, 0.0, 0.0), station_setpoint=setpoint
        )
        for _ in range(800):  # 40 s
            carrier.step(0.05, ZERO)
        error = (carrier.position - setpoint).norm()
        self.assertLess(error, 0.05)
        self.assertLess(carrier.velocity.norm(), 0.05)

    def test_holdable_steady_wind_produces_bounded_station_offset(self) -> None:
        carrier = CarrierBody(CarrierParams(), Vec3())
        wind = Vec3(0.2, 0.0, 0.0)  # drag 0.3 N, within 0.4 N lateral thrust
        for _ in range(1600):  # 80 s
            carrier.step(0.05, wind)
        p = carrier.params
        expected_offset = wind.x * p.linear_drag_n_per_m_s / p.station_kp_n_per_m
        self.assertAlmostEqual(carrier.position.x, expected_offset, delta=0.05)
        self.assertLess(carrier.position.x, 1.0)
        self.assertAlmostEqual(carrier.position.y, 0.0)
        self.assertAlmostEqual(carrier.position.z, 0.0)
        self.assertLess(carrier.velocity.norm(), 0.01)

    def test_tether_limits_excursion_under_overpowering_wind(self) -> None:
        # 0.6 m/s wind gives 0.9 N of drag, more than the 0.4 N the
        # station-keeping thrusters can supply: untethered, the carrier
        # drifts without bound; tethered, the excursion from the anchor is
        # capped at tether length plus a small elastic stretch.
        params = CarrierParams()
        anchor = Vec3()
        wind = Vec3(0.6, 0.0, 0.0)
        steps = 2400  # 120 s

        tethered = CarrierBody(params, Vec3(0.0, 0.0, 3.0), tether_anchor=anchor)
        max_distance = 0.0
        for _ in range(steps):
            tethered.step(0.05, wind)
            max_distance = max(max_distance, (tethered.position - anchor).norm())
        elastic_margin = 0.3
        self.assertLessEqual(max_distance, params.tether_length_m + elastic_margin)
        # The tether was actually engaged, not merely slack the whole run.
        self.assertGreater(max_distance, params.tether_length_m)

        untethered = CarrierBody(params, Vec3(0.0, 0.0, 3.0))
        for _ in range(steps):
            untethered.step(0.05, wind)
        self.assertGreater(
            (untethered.position - anchor).norm(),
            params.tether_length_m + elastic_margin,
        )

    def test_envelope_normalized_distance_inside_and_outside(self) -> None:
        position = Vec3(1.0, 2.0, 3.0)
        carrier = CarrierBody(CarrierParams(), position)
        inside = position + Vec3(0.5, 0.0, 0.0)  # deep inside the 2.25 m semi-axis
        well_below = position + Vec3(0.0, 0.0, -2.0)  # far below the 0.76 m semi-axis
        self.assertLess(carrier.envelope_normalized_distance(inside), 1.0)
        self.assertGreater(carrier.envelope_normalized_distance(well_below), 1.0)

    def test_envelope_inflation_grows_the_keep_out(self) -> None:
        position = Vec3()
        carrier = CarrierBody(CarrierParams(), position)
        point = position + Vec3(0.0, 0.0, -0.9)  # just outside the bare hull
        bare = carrier.envelope_normalized_distance(point)
        inflated = carrier.envelope_normalized_distance(point, inflate_m=0.3)
        self.assertGreater(bare, 1.0)
        self.assertLess(inflated, bare)
        self.assertLess(inflated, 1.0)


class KinematicRigTests(unittest.TestCase, VecTestMixin):
    def test_dock_velocity_matches_finite_difference_of_center(self) -> None:
        rig = KinematicRig(RigParams(), Vec3(1.0, 2.0, 3.0), random.Random(11))
        for _ in range(100):  # advance to t = 2 s so phases are exercised
            rig.step(DT, ZERO)
        h = 0.005
        center_before = rig.dock_center()
        rig.step(h, ZERO)
        velocity_mid = rig.dock_velocity()
        rig.step(h, ZERO)
        center_after = rig.dock_center()
        central_difference = (center_after - center_before) * (1.0 / (2.0 * h))
        self.assertVecAlmostEqual(central_difference, velocity_mid, places=6)

    def test_rig_is_deterministic_from_its_seed(self) -> None:
        rig_a = KinematicRig(RigParams(), Vec3(), random.Random(7))
        rig_b = KinematicRig(RigParams(), Vec3(), random.Random(7))
        for _ in range(25):
            rig_a.step(DT, ZERO)
            rig_b.step(DT, ZERO)
        self.assertEqual(rig_a.dock_center(), rig_b.dock_center())
        self.assertEqual(rig_a.dock_velocity(), rig_b.dock_velocity())

    def test_rig_center_stays_within_programmed_amplitudes(self) -> None:
        params = RigParams()
        base = Vec3(0.5, -0.5, 2.0)
        rig = KinematicRig(params, base, random.Random(3))
        for _ in range(400):  # 8 s covers a full lateral period
            rig.step(DT, ZERO)
            offset = rig.dock_center() - base
            self.assertLessEqual(abs(offset.x), params.lateral_amplitude_m + 1e-12)
            self.assertEqual(offset.y, 0.0)
            self.assertLessEqual(abs(offset.z), params.vertical_amplitude_m + 1e-12)

    def test_rig_has_no_envelope_to_strike(self) -> None:
        rig = KinematicRig(RigParams(), Vec3(), random.Random(0))
        self.assertEqual(rig.envelope_normalized_distance(Vec3()), math.inf)
        self.assertEqual(
            rig.envelope_normalized_distance(Vec3(9.0, 9.0, 9.0), inflate_m=1.0),
            math.inf,
        )


if __name__ == "__main__":
    unittest.main()
