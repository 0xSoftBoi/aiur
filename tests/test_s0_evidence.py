import unittest

from aiur.s0_evidence import (
    EvidenceError,
    reduce_chamber,
    reduce_flight,
    reduce_flights,
    reduce_tethered,
    reduce_trials,
    verdict,
)
from aiur.strato_sim import SCENARIOS, FlightScenario, run_flight


def _rows(seed: int) -> list[dict[str, str]]:
    result = run_flight(FlightScenario(seed=seed))
    return [{k: str(v) for k, v in row.items()} for row in result.rows]


def _manifest(seed: int, **overrides: object) -> dict[str, object]:
    result = run_flight(FlightScenario(seed=seed))
    manifest: dict[str, object] = {
        "run_id": f"F{seed}",
        "article_rev": "Rev-A",
        "git_commit": "abc",
        "evidence_kind": "flown",
        "predicted_landing_x_km": result.landing_x_km,
        "predicted_landing_y_km": result.landing_y_km,
        "airspace_coordination_ref": "NOTAM 12/345",
        "recovered": True,
        "recovery_x_km": result.landing_x_km + 1.0,
        "recovery_y_km": result.landing_y_km,
        "storage_checksum_verified": True,
        "third_party_contacts": 0,
    }
    manifest.update(overrides)
    return manifest


def _trials(*, computer_off: bool = True, link_failures: int = 0) -> list[dict[str, str]]:
    rows = [
        {"trial_id": f"T{i}", "kind": "termination", "computer_powered": "1", "fired": "1"}
        for i in range(10)
    ]
    if computer_off:
        rows.append({"trial_id": "T-OFF", "kind": "termination", "computer_powered": "0", "fired": "1"})
    for i in range(10):
        rows.append(
            {
                "trial_id": f"L{i}",
                "kind": "link",
                "computer_powered": "1",
                "fired": "0" if i < link_failures else "1",
            }
        )
    return rows


class FlightReductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _rows(1)

    def test_one_flight_reduces_to_the_gate_metrics(self) -> None:
        metrics = reduce_flight(self.rows, _manifest(1))
        self.assertGreaterEqual(metrics["max_altitude_m"], 25_000.0)
        self.assertGreaterEqual(metrics["geotagged_frames_above_threshold"], 50)
        self.assertLessEqual(metrics["telemetry_gap_max_s"], 60.0)
        self.assertEqual(metrics["payload_recovered"], 1)
        self.assertAlmostEqual(metrics["landing_error_km"], 1.0, places=6)
        self.assertEqual(metrics["airspace_authorisation_on_file"], 1)

    def test_two_flown_flights_close_the_gate_and_the_requirements(self) -> None:
        flights = [(self.rows, _manifest(1)), (_rows(2), _manifest(2))]
        report = verdict("S0-C", reduce_flights(flights, _trials()))
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["evidence_kind"], "flown")
        self.assertTrue(report["closes_requirements"])
        self.assertEqual(report["metrics"]["sounding_flights"], 2)

    def test_a_single_flight_does_not_pass(self) -> None:
        report = verdict("S0-C", reduce_flights([(self.rows, _manifest(1))], _trials()))
        self.assertFalse(report["passed"])
        self.assertIn("at least two free flights of the same configuration", report["failed_criteria"])

    def test_missing_computer_off_trial_fails_the_gate(self) -> None:
        flights = [(self.rows, _manifest(1)), (_rows(2), _manifest(2))]
        report = verdict("S0-C", reduce_flights(flights, _trials(computer_off=False)))
        self.assertFalse(report["passed"])
        self.assertIn(
            "flight termination demonstrated with the payload computer powered off",
            report["failed_criteria"],
        )

    def test_blank_coordination_fails_the_gate(self) -> None:
        flights = [(self.rows, _manifest(1, airspace_coordination_ref=" ")), (_rows(2), _manifest(2))]
        report = verdict("S0-C", reduce_flights(flights, _trials()))
        self.assertFalse(report["passed"])
        self.assertIn(
            "airspace coordination for the launch recorded before release",
            report["failed_criteria"],
        )

    def test_absent_coordination_field_is_missing_evidence(self) -> None:
        manifest = _manifest(1)
        del manifest["airspace_coordination_ref"]
        with self.assertRaises(EvidenceError):
            reduce_flight(self.rows, manifest)

    def test_recovered_without_landing_is_inconsistent(self) -> None:
        rows = [row for row in self.rows if row["state"] != "landed"]
        with self.assertRaises(EvidenceError):
            reduce_flight(rows, _manifest(1))

    def test_geotagged_frame_without_a_fix_is_rejected(self) -> None:
        rows = [dict(row) for row in self.rows]
        for row in rows:
            if row["frame_captured"] == "1":
                row["gnss_valid"] = "0"
                row["altitude_m"] = ""
                break
        with self.assertRaises(EvidenceError):
            reduce_flight(rows, _manifest(1))

    def test_duplicate_run_ids_are_rejected(self) -> None:
        with self.assertRaises(EvidenceError):
            reduce_flights([(self.rows, _manifest(1)), (self.rows, _manifest(1))], _trials())

    def test_unknown_evidence_kind_is_rejected(self) -> None:
        with self.assertRaises(EvidenceError):
            reduce_flight(self.rows, _manifest(1, evidence_kind="vibes"))

    def test_mixed_evidence_kinds_do_not_close_requirements(self) -> None:
        flights = [(self.rows, _manifest(1)), (_rows(2), _manifest(2, evidence_kind="simulated"))]
        report = verdict("S0-C", reduce_flights(flights, _trials()))
        self.assertTrue(report["passed"])
        self.assertFalse(report["closes_requirements"])


class GroundLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _rows(1)

    def _ground(self, *, drop: tuple[float, float] | None = None, bogus: bool = False) -> list[dict[str, str]]:
        rows = []
        for row in self.rows:
            if row["telemetry_sent"] != "1":
                continue
            t = float(row["t_s"])
            ok = not (drop is not None and drop[0] <= t < drop[0] + drop[1])
            rows.append({"rx_t_s": str(t + 0.3), "packet_t_s": row["t_s"], "rssi_dbm": "-90", "decoded_ok": "1" if ok else "0"})
        if bogus:
            # 15 s from the nearest 30 s transmit: outside the match tolerance.
            rows.append({"rx_t_s": "1246.0", "packet_t_s": "1245.0", "rssi_dbm": "-90", "decoded_ok": "1"})
        return rows

    def test_ground_log_agreeing_with_the_package_gives_the_same_gap(self) -> None:
        with_ground = reduce_flight(self.rows, _manifest(1), ground=self._ground())
        without = reduce_flight(self.rows, _manifest(1))
        self.assertEqual(with_ground["telemetry_gap_max_s"], without["telemetry_gap_max_s"])

    def test_ground_side_blackout_is_the_gap_that_counts(self) -> None:
        metrics = reduce_flight(self.rows, _manifest(1), ground=self._ground(drop=(2000.0, 400.0)))
        self.assertGreaterEqual(metrics["telemetry_gap_max_s"], 400.0)
        report = verdict("S0-C", reduce_flights([(self.rows, _manifest(1), self._ground(drop=(2000.0, 400.0))), (_rows(2), _manifest(2))], _trials()))
        self.assertFalse(report["passed"])
        self.assertIn("no telemetry gap longer than five minutes in flight", report["failed_criteria"])

    def test_decoded_packet_matching_no_transmit_is_inconsistent(self) -> None:
        with self.assertRaises(EvidenceError):
            reduce_flight(self.rows, _manifest(1), ground=self._ground(bogus=True))

    def test_ground_log_with_nothing_decoded_is_missing_evidence(self) -> None:
        silent = [dict(r, decoded_ok="0") for r in self._ground()]
        with self.assertRaises(EvidenceError):
            reduce_flight(self.rows, _manifest(1), ground=silent)


class TetheredReductionTests(unittest.TestCase):
    @staticmethod
    def _ascent(seed: int, **overrides: object) -> tuple[list[dict[str, str]], dict[str, object]]:
        rows = _rows(seed)[:900]  # a tethered ascent is short; the log shape is the same
        manifest: dict[str, object] = {
            "run_id": f"T{seed}",
            "article_rev": "Rev-A",
            "git_commit": "abc",
            "evidence_kind": "flown",
            "images_downlinked": 12,
            "parachute_deployments": 1 if seed == 3 else 0,
            "parachute_failures": 0,
            "crew_contacts": 0,
        }
        manifest.update(overrides)
        return rows, manifest

    def test_three_ascents_with_one_deployment_close_s0_b(self) -> None:
        ascents = [self._ascent(1), self._ascent(2), self._ascent(3)]
        report = verdict("S0-B", reduce_tethered(ascents, _trials()))
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["closes_requirements"])
        self.assertEqual(report["metrics"]["tethered_flights"], 3)
        self.assertEqual(report["metrics"]["end_to_end_images_downlinked"], 36)

    def test_two_ascents_or_no_deployment_fail(self) -> None:
        report = verdict("S0-B", reduce_tethered([self._ascent(1), self._ascent(2)], _trials()))
        self.assertFalse(report["passed"])
        self.assertIn("at least three tethered ascents", report["failed_criteria"])
        self.assertIn("termination fired aloft and the parachute deployed", report["failed_criteria"])

    def test_crew_contact_fails_the_gate(self) -> None:
        ascents = [self._ascent(1), self._ascent(2), self._ascent(3, crew_contacts=1)]
        report = verdict("S0-B", reduce_tethered(ascents, _trials()))
        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["crew_contacts"], 1)

    def test_more_failures_than_deployments_is_inconsistent(self) -> None:
        with self.assertRaises(EvidenceError):
            reduce_tethered([self._ascent(3, parachute_failures=2)], _trials())


class TrialReductionTests(unittest.TestCase):
    def test_counts_each_kind(self) -> None:
        metrics = reduce_trials(_trials(link_failures=2))
        self.assertEqual(metrics["termination_command_trials"], 11)
        self.assertEqual(metrics["termination_failures"], 0)
        self.assertEqual(metrics["termination_verified_with_payload_computer_off"], 1)
        self.assertEqual(metrics["telemetry_link_trials"], 10)
        self.assertEqual(metrics["telemetry_link_failures"], 2)

    def test_unknown_kind_is_rejected(self) -> None:
        rows = _trials()
        rows[0]["kind"] = "vibe"
        with self.assertRaises(EvidenceError):
            reduce_trials(rows)


class ChamberReductionTests(unittest.TestCase):
    @staticmethod
    def _soak(hours: float = 3.5, dropouts: int = 0, frames: int = 120) -> list[dict[str, str]]:
        rows = []
        n = int(hours * 60)
        for minute in range(n + 1):
            temp = 20.0 - (80.0 * min(minute, 60) / 60.0)  # to -60 in the first hour
            rows.append(
                {
                    "t_s": str(minute * 60),
                    "internal_temp_c": f"{temp:.1f}",
                    "chamber_temp_c": f"{temp - 5:.1f}",
                    "imaging_ok": "0" if minute < dropouts else "1",
                    "tracking_ok": "1",
                    "termination_ok": "1",
                    "frame_stored": "1" if minute < frames else "0",
                }
            )
        return rows

    @staticmethod
    def _drops(worst: float = 4.6) -> list[dict[str, str]]:
        return [
            {"drop_id": "D1", "descent_rate_m_s": "4.2"},
            {"drop_id": "D2", "descent_rate_m_s": str(worst)},
        ]

    @staticmethod
    def _bench(mass: float = 0.812) -> dict[str, object]:
        return {
            "run_id": "S0A-1",
            "article_rev": "Rev-A",
            "git_commit": "abc",
            "evidence_kind": "bench",
            "payload_package_mass_kg": mass,
        }

    def test_a_clean_soak_closes_s0_a(self) -> None:
        report = verdict("S0-A", reduce_chamber(self._soak(), _trials(), self._drops(), self._bench()))
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["closes_requirements"])
        self.assertAlmostEqual(report["metrics"]["cold_soak_hours"], 3.5, places=6)
        self.assertLessEqual(report["metrics"]["cold_soak_min_temp_c"], -55.0)
        self.assertEqual(report["metrics"]["imaging_chain_captures"], 120)

    def test_one_dropout_fails_the_gate(self) -> None:
        report = verdict(
            "S0-A", reduce_chamber(self._soak(dropouts=1), _trials(), self._drops(), self._bench())
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["cold_soak_functional_dropouts"], 1)

    def test_fast_drop_and_heavy_package_fail(self) -> None:
        report = verdict(
            "S0-A", reduce_chamber(self._soak(), _trials(), self._drops(worst=5.4), self._bench(1.9))
        )
        self.assertFalse(report["passed"])
        self.assertIn("drop-tested descent rate at the landing-speed limit", report["failed_criteria"])
        self.assertIn("payload package stays under the 4 lb regulatory ceiling", report["failed_criteria"])

    def test_missing_bench_mass_is_missing_evidence(self) -> None:
        bench = self._bench()
        del bench["payload_package_mass_kg"]
        with self.assertRaises(EvidenceError):
            reduce_chamber(self._soak(), _trials(), self._drops(), bench)


if __name__ == "__main__":
    unittest.main()
