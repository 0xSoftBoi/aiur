import unittest

from aiur.flight_supervisor import (
    FlightInputs,
    FlightLimits,
    FlightState,
    FlightSupervisor,
    IndependentTimer,
)


def fix(altitude: float, **overrides: object) -> FlightInputs:
    base = {"arm_pin_pulled": True, "gnss_valid": True, "altitude_m": altitude, "range_from_launch_km": 0.0}
    base.update(overrides)
    return FlightInputs(**base)  # type: ignore[arg-type]


def armed_supervisor(limits: FlightLimits | None = None) -> FlightSupervisor:
    supervisor = FlightSupervisor(limits)
    supervisor.step(0.0, fix(100.0))
    return supervisor


def climb_to(supervisor: FlightSupervisor, start_s: float, altitude: float, **overrides: object) -> float:
    """Feed a 5 m/s climb from the current fix until the altitude is reached."""

    t = start_s
    current = supervisor._last_fix[1] if supervisor._last_fix else 100.0
    while current < altitude:
        t += 1.0
        current = min(altitude, current + 5.0)
        supervisor.step(t, fix(current, **overrides))
    return t


class ArmingTests(unittest.TestCase):
    def test_pin_in_stays_safe_with_cutdown_inhibited(self) -> None:
        supervisor = FlightSupervisor()
        output = supervisor.step(0.0, FlightInputs(arm_pin_pulled=False, gnss_valid=True, altitude_m=100.0))
        self.assertIs(output.state, FlightState.SAFE)
        self.assertFalse(output.cutdown)

    def test_arming_requires_a_fix(self) -> None:
        supervisor = FlightSupervisor()
        output = supervisor.step(0.0, FlightInputs(arm_pin_pulled=True, gnss_valid=False))
        self.assertIs(output.state, FlightState.SAFE)
        self.assertEqual(output.reason, "arming requires a GNSS fix")
        output = supervisor.step(1.0, fix(100.0))
        self.assertIs(output.state, FlightState.ARMED)
        self.assertEqual(supervisor.launch_altitude_m, 100.0)

    def test_pin_reinserted_on_the_ground_disarms(self) -> None:
        supervisor = armed_supervisor()
        output = supervisor.step(1.0, fix(100.0, arm_pin_pulled=False))
        self.assertIs(output.state, FlightState.SAFE)
        self.assertIsNone(supervisor.armed_at_s)

    def test_monotonic_time_is_enforced(self) -> None:
        supervisor = armed_supervisor()
        with self.assertRaises(ValueError):
            supervisor.step(-1.0, fix(100.0))


class PhaseTests(unittest.TestCase):
    def test_ascent_is_declared_on_measured_climb(self) -> None:
        supervisor = armed_supervisor()
        output = supervisor.step(1.0, fix(120.0))
        self.assertIs(output.state, FlightState.ARMED)
        output = supervisor.step(2.0, fix(131.0))
        self.assertIs(output.state, FlightState.ASCENT)
        self.assertEqual(output.capture_period_s, FlightLimits().capture_period_low_s)

    def test_threshold_switches_to_stratosphere_cadence(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 20_000.0)
        output = supervisor.step(t + 1.0, fix(20_005.0))
        self.assertIs(output.state, FlightState.STRATOSPHERE)
        self.assertEqual(output.capture_period_s, FlightLimits().capture_period_high_s)
        self.assertTrue(output.geotag)

    def test_frames_are_not_geotagged_without_a_fix(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 5_000.0)
        output = supervisor.step(t + 1.0, fix(5_000.0, gnss_valid=False, altitude_m=None, range_from_launch_km=None))
        self.assertIs(output.state, FlightState.ASCENT)
        self.assertFalse(output.geotag)

    def test_burst_descent_and_landing(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 30_000.0)
        altitude = 30_000.0
        for _ in range(60):
            t += 1.0
            altitude -= 15.0
            output = supervisor.step(t, fix(altitude))
        self.assertIs(output.state, FlightState.DESCENT)
        self.assertEqual(output.reason, "sustained descent: burst")
        # Hold near the launch altitude with a near-zero rate.
        for _ in range(200):
            t += 1.0
            output = supervisor.step(t, fix(100.0))
        self.assertIs(output.state, FlightState.LANDED)
        self.assertTrue(output.beacon_only)
        self.assertIsNone(output.capture_period_s)
        self.assertEqual(output.telemetry_period_s, FlightLimits().beacon_period_s)


class TerminationTests(unittest.TestCase):
    def test_ground_command_latches_cutdown(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 10_000.0)
        output = supervisor.step(t + 1.0, fix(10_005.0, ground_terminate=True))
        self.assertIs(output.state, FlightState.TERMINATING)
        self.assertTrue(output.cutdown)
        self.assertEqual(output.reason, "ground command")
        output = supervisor.step(t + 2.0, fix(10_010.0))
        self.assertTrue(output.cutdown, "cutdown must stay asserted once commanded")

    def test_ceiling_terminates_a_balloon_that_did_not_burst(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 36_000.0)
        output = supervisor.step(t + 1.0, fix(36_005.0))
        self.assertTrue(output.cutdown)
        self.assertEqual(output.reason, "ceiling: balloon did not burst")

    def test_geofence_terminates(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 15_000.0)
        output = supervisor.step(t + 1.0, fix(15_005.0, range_from_launch_km=121.0))
        self.assertTrue(output.cutdown)
        self.assertIn("geofence", output.reason or "")

    def test_position_unknown_too_long_terminates(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 8_000.0)
        lost = FlightInputs(arm_pin_pulled=True, gnss_valid=False)
        output = supervisor.step(t + 599.0, lost)
        self.assertFalse(output.cutdown)
        output = supervisor.step(t + 600.0, lost)
        self.assertTrue(output.cutdown)
        self.assertEqual(output.reason, "position unknown too long")

    def test_mission_clock_terminates(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 5_000.0)
        output = supervisor.step(3.0 * 3600.0, fix(5_000.0))
        self.assertTrue(output.cutdown)
        self.assertEqual(output.reason, "mission clock limit")
        self.assertGreater(3.0 * 3600.0, t)

    def test_termination_then_descent(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 12_000.0)
        supervisor.step(t + 1.0, fix(12_005.0, ground_terminate=True))
        altitude = 12_005.0
        for _ in range(60):
            t += 1.0
            altitude -= 10.0
            output = supervisor.step(t, fix(altitude))
        self.assertIs(output.state, FlightState.DESCENT)
        self.assertTrue(output.cutdown)


class PowerAndThermalTests(unittest.TestCase):
    def test_low_battery_drops_to_beacon_only(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 5_000.0)
        output = supervisor.step(t + 1.0, fix(5_005.0, battery_v=4.3))
        self.assertTrue(output.beacon_only)
        self.assertIsNone(output.capture_period_s)
        self.assertFalse(output.cutdown, "low battery is not a termination trigger")

    def test_cold_camera_off_but_telemetry_normal(self) -> None:
        supervisor = armed_supervisor()
        t = climb_to(supervisor, 0.0, 5_000.0)
        output = supervisor.step(t + 1.0, fix(5_005.0, internal_temp_c=-35.0))
        self.assertIsNone(output.capture_period_s)
        self.assertFalse(output.beacon_only)
        self.assertEqual(output.telemetry_period_s, FlightLimits().telemetry_period_s)


class IndependentTimerTests(unittest.TestCase):
    def test_fires_at_the_limit_and_ignores_everything_else(self) -> None:
        timer = IndependentTimer(100.0)
        self.assertFalse(timer.step(0.0, False))
        self.assertFalse(timer.step(10.0, True))
        self.assertFalse(timer.step(109.0, False))  # pin back in: no effect
        self.assertTrue(timer.step(110.0, False))
        self.assertTrue(timer.step(111.0, True))

    def test_fires_while_the_supervisor_is_frozen(self) -> None:
        supervisor = armed_supervisor()
        timer = IndependentTimer(FlightLimits().max_mission_s)
        timer.step(0.0, True)
        # The supervisor is never stepped again: the payload computer froze.
        self.assertTrue(timer.step(FlightLimits().max_mission_s, True))
        self.assertFalse(supervisor.cutdown_latched)

    def test_limits_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            IndependentTimer(0.0)
        with self.assertRaises(ValueError):
            FlightSupervisor(FlightLimits(ceiling_m=10_000.0))


if __name__ == "__main__":
    unittest.main()
