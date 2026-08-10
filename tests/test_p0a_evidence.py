import csv
import tempfile
import unittest
from pathlib import Path

from aiur.loop_graph import DERIVED_LIFE_TEST_CYCLES, evaluate_gate
from aiur.p0a_evidence import REQUIRED_FAULT_MODES, EvidenceError, reduce_p0a


IDENTITY = {"run_id": "P0A-001", "article_rev": "A1", "git_commit": "abc123"}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class P0AEvidenceTests(unittest.TestCase):
    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _nominal(self, root: Path) -> tuple[Path, Path, Path, Path]:
        article = root / "article.csv"
        cycles = root / "cycles.csv"
        loads = root / "loads.csv"
        faults = root / "faults.csv"
        write_csv(
            article,
            [
                *IDENTITY,
                "dock_mass_g",
                "probe_mass_g",
                "propellers_installed",
                "keeper_close_force_margin",
                "keeper_open_force_margin",
            ],
            [
                {
                    **IDENTITY,
                    "dock_mass_g": 150,
                    "probe_mass_g": 6.5,
                    "propellers_installed": 0,
                    "keeper_close_force_margin": 2.4,
                    "keeper_open_force_margin": 2.2,
                }
            ],
        )
        cycle_rows = []
        # 20 run-in cycles with a settled force trend, then the derived life test.
        run_in_count = 20
        total_cycles = run_in_count + DERIVED_LIFE_TEST_CYCLES
        for cycle in range(1, total_cycles + 1):
            run_in = cycle <= run_in_count
            emergency = (not run_in) and cycle % 25 == 0
            loaded = emergency and (cycle // 25) % 2 == 0
            cycle_rows.append(
                {
                    **IDENTITY,
                    "cycle": cycle,
                    "phase": "run_in" if run_in else "life",
                    "insertion_force_n": 2.0 if run_in else 2.0,
                    "release_force_n": 1.5,
                    "capture_confirmed": 1,
                    "release_completed": 1,
                    "structural_failure": 0,
                    "ambiguous_capture_confirmation": 0,
                    "emergency_release_trial": int(emergency),
                    "emergency_release_load_n": 5.1 if loaded else 0.0,
                    "emergency_release_success": 1 if emergency else "",
                }
            )
        write_csv(
            cycles,
            [
                *IDENTITY,
                "cycle",
                "phase",
                "insertion_force_n",
                "release_force_n",
                "capture_confirmed",
                "release_completed",
                "structural_failure",
                "ambiguous_capture_confirmation",
                "emergency_release_trial",
                "emergency_release_load_n",
                "emergency_release_success",
            ],
            cycle_rows,
        )
        write_csv(
            faults,
            [
                *IDENTITY,
                "trial",
                "fault_mode",
                "required_response_observed",
                "unsafe_state_entered",
            ],
            [
                {
                    **IDENTITY,
                    "trial": index + 1,
                    "fault_mode": mode,
                    "required_response_observed": 1,
                    "unsafe_state_entered": 0,
                }
                for index, mode in enumerate(REQUIRED_FAULT_MODES)
            ],
        )
        load_rows = []
        for phase in ("pre_cycle", "post_cycle"):
            for direction in ("AXIAL", "+X", "-X", "+Y", "-Y"):
                load_rows.append(
                    {
                        **IDENTITY,
                        "phase": phase,
                        "direction": direction,
                        "held_load_n": 5.1 if direction == "AXIAL" else 1.1,
                        "duration_s": 10,
                        "retained": 1,
                        "structural_damage": 0,
                    }
                )
        write_csv(
            loads,
            [*IDENTITY, "phase", "direction", "held_load_n", "duration_s", "retained", "structural_damage"],
            load_rows,
        )
        return article, cycles, loads, faults

    def test_complete_nominal_evidence_passes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metrics = reduce_p0a(*self._nominal(Path(directory)))
        verdict = evaluate_gate("P0-A", metrics)
        self.assertTrue(verdict.passed, verdict)
        self.assertEqual(metrics["life_test_cycles"], DERIVED_LIFE_TEST_CYCLES)
        self.assertEqual(metrics["run_in_cycles"], 20)
        self.assertEqual(metrics["run_in_force_trend_stabilized"], 1)
        self.assertGreaterEqual(metrics["loaded_emergency_release_trials"], 10)
        self.assertEqual(metrics["fault_insertion_trials"], len(REQUIRED_FAULT_MODES))
        self.assertEqual(metrics["fault_insertion_unsafe_responses"], 0)

    def test_missing_fault_mode_is_incomplete_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads, faults = self._nominal(Path(directory))
            rows = self._read_rows(faults)[:-1]
            write_csv(faults, list(rows[0]), rows)
            with self.assertRaises(EvidenceError) as caught:
                reduce_p0a(article, cycles, loads, faults)
        self.assertIn("never exercised", str(caught.exception))

    def test_unloaded_release_does_not_satisfy_loaded_quota(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads, faults = self._nominal(Path(directory))
            rows = self._read_rows(cycles)
            for row in rows:
                row["emergency_release_load_n"] = "0"
            write_csv(cycles, list(rows[0]), rows)
            metrics = reduce_p0a(article, cycles, loads, faults)
        self.assertEqual(metrics["loaded_emergency_release_trials"], 0)
        self.assertFalse(evaluate_gate("P0-A", metrics).passed)

    def test_drifting_run_in_force_is_not_stabilized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads, faults = self._nominal(Path(directory))
            rows = self._read_rows(cycles)
            drift = 1.0
            for row in rows:
                if row["phase"] == "run_in":
                    drift += 0.5
                    row["insertion_force_n"] = f"{drift}"
            write_csv(cycles, list(rows[0]), rows)
            metrics = reduce_p0a(article, cycles, loads, faults)
        self.assertEqual(metrics["run_in_force_trend_stabilized"], 0)

    def test_missing_post_cycle_direction_is_rejected_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads, faults = self._nominal(Path(directory))
            rows = self._read_rows(loads)
            rows = [row for row in rows if not (row["phase"] == "post_cycle" and row["direction"] == "-Y")]
            write_csv(loads, list(rows[0]), rows)
            with self.assertRaises(EvidenceError):
                reduce_p0a(article, cycles, loads, faults)

    def test_short_load_screen_is_recorded_as_failed_not_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads, faults = self._nominal(Path(directory))
            rows = self._read_rows(loads)
            rows[0]["duration_s"] = "9.9"
            write_csv(loads, list(rows[0]), rows)
            metrics = reduce_p0a(article, cycles, loads, faults)
        self.assertFalse(evaluate_gate("P0-A", metrics).passed)
        self.assertEqual(metrics["axial_screen_load_held_n"], 0.0)

    def test_failed_capture_does_not_count_as_completed_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads, faults = self._nominal(Path(directory))
            rows = self._read_rows(cycles)
            # The last row is a life-phase cycle; a capture that did not
            # confirm is not a completed cycle even though the row exists.
            rows[-1]["capture_confirmed"] = "0"
            write_csv(cycles, list(rows[0]), rows)
            metrics = reduce_p0a(article, cycles, loads, faults)
        self.assertEqual(metrics["life_test_cycles"], DERIVED_LIFE_TEST_CYCLES - 1)
        self.assertFalse(evaluate_gate("P0-A", metrics).passed)


if __name__ == "__main__":
    unittest.main()
