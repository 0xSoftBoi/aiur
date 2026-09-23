import json
import math
import tempfile
import unittest
from pathlib import Path

from aiur.s0_evidence import read_csv, read_manifest, reduce_flights, verdict
from aiur.strato_sim import (
    SCENARIOS,
    FlightScenario,
    predict_landing,
    run_flight,
    write_flight,
    write_simulated_termination_trials,
)


class NominalFlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_flight(SCENARIOS["nominal"])

    def test_reaches_the_stratosphere_bursts_and_lands(self) -> None:
        self.assertGreaterEqual(self.result.max_altitude_m, 25_000.0)
        self.assertIsNotNone(self.result.burst_altitude_m)
        self.assertTrue(self.result.landed)
        self.assertIsNone(self.result.termination_reason)
        self.assertFalse(self.result.timer_fired)

    def test_observes_above_the_threshold_with_position_tags(self) -> None:
        frames = [
            row
            for row in self.result.rows
            if row["frame_captured"] and row["geotagged"] and float(row["altitude_m"]) >= 20_000.0
        ]
        self.assertGreaterEqual(len(frames), 50)

    def test_is_deterministic_for_a_seed(self) -> None:
        again = run_flight(SCENARIOS["nominal"])
        self.assertEqual(again.landing_x_km, self.result.landing_x_km)
        self.assertEqual(len(again.rows), len(self.result.rows))

    def test_prediction_is_close_to_the_gusty_flight(self) -> None:
        px, py = predict_landing(SCENARIOS["nominal"])
        error = math.hypot(px - self.result.landing_x_km, py - self.result.landing_y_km)
        self.assertLess(error, 15.0)
        self.assertLess(math.hypot(px, py), 120.0, "prediction must sit inside the geofence")


class FaultScenarioTests(unittest.TestCase):
    def test_short_gnss_dropout_is_survived(self) -> None:
        result = run_flight(SCENARIOS["gnss-dropout"])
        self.assertIsNone(result.termination_reason)
        self.assertTrue(result.landed)

    def test_long_gnss_loss_brings_the_package_down(self) -> None:
        result = run_flight(SCENARIOS["gnss-lost"])
        self.assertEqual(result.termination_reason, "position unknown too long")
        self.assertLess(result.max_altitude_m, 20_000.0)
        self.assertTrue(result.landed)

    def test_float_off_is_ended_by_the_mission_clock(self) -> None:
        result = run_flight(SCENARIOS["float-off"])
        self.assertIsNone(result.burst_altitude_m)
        self.assertIn("mission clock", result.termination_reason or "")
        self.assertTrue(result.timer_fired)
        self.assertTrue(result.landed)

    def test_frozen_computer_is_brought_down_by_the_timer(self) -> None:
        result = run_flight(SCENARIOS["computer-freeze"])
        self.assertTrue(result.timer_fired)
        self.assertTrue(result.landed)
        self.assertTrue(any(row["state"] == "frozen" for row in result.rows))

    def test_ground_command_ends_the_flight_early(self) -> None:
        result = run_flight(SCENARIOS["ground-terminate"])
        self.assertIn("ground command", result.termination_reason or "")
        self.assertLess(result.max_altitude_m, 20_000.0)

    def test_blackout_shows_up_as_a_telemetry_gap(self) -> None:
        result = run_flight(SCENARIOS["blackout"])
        received = [float(row["t_s"]) for row in result.rows if row["telemetry_received"]]
        gaps = [b - a for a, b in zip(received, received[1:])]
        self.assertGreater(max(gaps), 150.0)

    def test_invalid_tick_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_flight(FlightScenario(tick_s=0.0))


class WrittenEvidenceTests(unittest.TestCase):
    def test_two_simulated_flights_close_s0_c_but_do_not_close_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            flights = []
            for seed in (1, 2):
                scenario = FlightScenario(seed=seed)
                write_flight(run_flight(scenario), out, run_id=f"nominal-{seed}", git_commit="test")
                flights.append(
                    (
                        read_csv(out / f"nominal-{seed}-flight-log.csv"),
                        read_manifest(out / f"nominal-{seed}-flight-manifest.json"),
                        read_csv(out / f"nominal-{seed}-ground-log.csv"),
                    )
                )
            trials = read_csv(write_simulated_termination_trials(out))
            report = verdict("S0-C", reduce_flights(flights, trials))
            self.assertTrue(report["passed"], report)
            self.assertEqual(report["evidence_kind"], "simulated")
            self.assertFalse(report["closes_requirements"])
            manifest = json.loads((out / "nominal-1-flight-manifest.json").read_text())
            self.assertEqual(manifest["evidence_kind"], "simulated")
            self.assertIn("simulated", manifest["airspace_coordination_ref"].lower())


if __name__ == "__main__":
    unittest.main()
