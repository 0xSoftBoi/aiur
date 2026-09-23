import csv
import tempfile
import unittest
from pathlib import Path

from aiur.flight_main import (
    PI_BACKEND_CONTRACT,
    FakeClock,
    FlightProgram,
    RecordedSensors,
    RecordingActuators,
    SimulatedSensors,
    east_north_km,
    main,
)
from aiur.flight_supervisor import FlightState
from aiur.s0_evidence import reduce_flight


def fly(**sensor_overrides: object) -> tuple[FlightState, FlightProgram, RecordingActuators, Path, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    log = Path(tmp.name) / "flight-log.csv"
    sensors = SimulatedSensors(**sensor_overrides)
    actuators = RecordingActuators(sensors)
    program = FlightProgram(sensors, actuators, FakeClock(), log)
    final = program.run()
    return final, program, actuators, log, tmp


class GeometryTests(unittest.TestCase):
    def test_one_degree_of_longitude_at_the_equator(self) -> None:
        east, north = east_north_km(0.0, 1.0, 0.0, 0.0)
        self.assertAlmostEqual(east, 111.19, places=1)
        self.assertAlmostEqual(north, 0.0, places=9)


class SimulatedFlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.final, cls.program, cls.actuators, cls.log, cls.tmp = fly()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_flies_to_landed_and_logs_every_tick(self) -> None:
        self.assertIs(self.final, FlightState.LANDED)
        with self.log.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), self.program.rows_written)
        self.assertGreater(len(rows), 6000)
        self.assertEqual(rows[-1]["state"], "landed")

    def test_nominal_flight_never_asserts_cutdown(self) -> None:
        self.assertFalse(any(self.actuators.cutdown_history))
        self.assertEqual(len(self.actuators.cutdown_history), self.program.rows_written)

    def test_captures_and_packets_follow_the_supervisor_cadence(self) -> None:
        self.assertGreater(len(self.actuators.frames), 500)
        self.assertGreater(len(self.actuators.packets), 200)
        with self.log.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        above = [
            float(r["t_s"])
            for r in rows
            if r["frame_captured"] == "1" and r["altitude_m"] and float(r["altitude_m"]) >= 20_000.0
        ]
        gaps = [b - a for a, b in zip(above, above[1:])]
        self.assertGreater(len(gaps), 100)
        self.assertTrue(all(abs(g - 5.0) < 1e-6 for g in gaps), "5 s cadence above the threshold")
        below = [
            float(r["t_s"])
            for r in rows
            if r["frame_captured"] == "1" and r["altitude_m"] and 1_000.0 < float(r["altitude_m"]) < 10_000.0
            and r["state"] == "ascent"
        ]
        self.assertTrue(all(abs(b - a - 10.0) < 1e-6 for a, b in zip(below, below[1:])), "10 s below")

    def test_log_is_reducible_by_the_s0_c_reducer(self) -> None:
        with self.log.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        last = [r for r in rows if r["x_km"]][-1]
        manifest = {
            "run_id": "sim-main",
            "article_rev": "Rev-A",
            "git_commit": "test",
            "evidence_kind": "simulated",
            "predicted_landing_x_km": float(last["x_km"]),
            "predicted_landing_y_km": float(last["y_km"]),
            "airspace_coordination_ref": "SIM",
            "recovered": True,
            "recovery_x_km": float(last["x_km"]),
            "recovery_y_km": float(last["y_km"]),
            "storage_checksum_verified": True,
            "third_party_contacts": 0,
        }
        metrics = reduce_flight(rows, manifest)
        self.assertGreater(metrics["max_altitude_m"], 25_000.0)
        self.assertGreaterEqual(metrics["geotagged_frames_above_threshold"], 50)
        self.assertLessEqual(metrics["telemetry_gap_max_s"], 30.0)


class FaultTests(unittest.TestCase):
    def test_ground_command_asserts_cutdown_and_holds_it(self) -> None:
        final, program, actuators, _, tmp = fly(terminate_at_s=1500.0)
        try:
            self.assertIs(final, FlightState.LANDED)
            first = actuators.cutdown_history.index(True)
            self.assertTrue(all(actuators.cutdown_history[first:]), "cutdown never withdrawn")
            self.assertEqual(program.supervisor.termination_reason, "ground command")
        finally:
            tmp.cleanup()

    def test_short_gnss_dropout_keeps_flying_without_geotags(self) -> None:
        final, _, actuators, log, tmp = fly(gnss_dropout=(1000.0, 120.0))
        try:
            self.assertIs(final, FlightState.LANDED)
            self.assertFalse(any(actuators.cutdown_history))
            untagged = [t for t, tag in actuators.frames if 1000.0 <= t < 1120.0 and not tag]
            self.assertTrue(untagged)
        finally:
            tmp.cleanup()

    def test_radio_failure_is_logged_as_not_received(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            log = Path(tmp.name) / "log.csv"
            sensors = SimulatedSensors()
            actuators = RecordingActuators(sensors, radio_ok=False)
            FlightProgram(sensors, actuators, FakeClock(), log, max_runtime_s=300.0).run()
            with log.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(any(r["telemetry_sent"] == "1" for r in rows))
            self.assertFalse(any(r["telemetry_received"] == "1" for r in rows))
        finally:
            tmp.cleanup()


class ReplayTests(unittest.TestCase):
    def test_replaying_a_log_reproduces_the_supervisor_states(self) -> None:
        final, _, _, log, tmp = fly(terminate_at_s=2000.0)
        try:
            with log.open(newline="") as handle:
                original = list(csv.DictReader(handle))
            out = Path(tmp.name) / "replay.csv"
            program = FlightProgram(RecordedSensors(original), RecordingActuators(), FakeClock(), out)
            program.run()
            with out.open(newline="") as handle:
                replayed = list(csv.DictReader(handle))
            self.assertEqual(len(replayed), len(original))
            self.assertEqual(
                [r["state"] for r in replayed], [r["state"] for r in original]
            )
            self.assertEqual(
                [r["cutdown"] for r in replayed], [r["cutdown"] for r in original]
            )
        finally:
            tmp.cleanup()

    def test_empty_replay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RecordedSensors([])


class CliTests(unittest.TestCase):
    def test_pi_backend_states_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--backend", "pi", "--log", str(Path(tmp) / "x.csv")])
        self.assertEqual(code, 2)
        self.assertIn("burn-wire", PI_BACKEND_CONTRACT)

    def test_sim_backend_runs_to_landing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "x.csv"
            self.assertEqual(main(["--backend", "sim", "--log", str(log)]), 0)
            self.assertTrue(log.exists())


if __name__ == "__main__":
    unittest.main()
