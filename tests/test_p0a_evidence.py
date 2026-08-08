import csv
import tempfile
import unittest
from pathlib import Path

from aiur.loop_graph import evaluate_gate
from aiur.p0a_evidence import EvidenceError, reduce_p0a


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

    def _nominal(self, root: Path) -> tuple[Path, Path, Path]:
        article = root / "article.csv"
        cycles = root / "cycles.csv"
        loads = root / "loads.csv"
        write_csv(
            article,
            [*IDENTITY, "dock_mass_g", "probe_mass_g", "propellers_installed"],
            [{**IDENTITY, "dock_mass_g": 150, "probe_mass_g": 6.5, "propellers_installed": 0}],
        )
        cycle_rows = []
        for cycle in range(1, 51):
            emergency = cycle % 5 == 0
            cycle_rows.append(
                {
                    **IDENTITY,
                    "cycle": cycle,
                    "capture_confirmed": 1,
                    "release_completed": 1,
                    "structural_failure": 0,
                    "ambiguous_capture_confirmation": 0,
                    "emergency_release_trial": int(emergency),
                    "emergency_release_success": 1 if emergency else "",
                }
            )
        write_csv(
            cycles,
            [
                *IDENTITY,
                "cycle",
                "capture_confirmed",
                "release_completed",
                "structural_failure",
                "ambiguous_capture_confirmation",
                "emergency_release_trial",
                "emergency_release_success",
            ],
            cycle_rows,
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
        return article, cycles, loads

    def test_complete_nominal_evidence_passes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metrics = reduce_p0a(*self._nominal(Path(directory)))
        self.assertTrue(evaluate_gate("P0-A", metrics).passed)
        self.assertEqual(metrics["manual_cycles"], 50)
        self.assertEqual(metrics["emergency_release_trials"], 10)

    def test_missing_post_cycle_direction_is_rejected_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads = self._nominal(Path(directory))
            rows = self._read_rows(loads)
            rows = [row for row in rows if not (row["phase"] == "post_cycle" and row["direction"] == "-Y")]
            write_csv(loads, list(rows[0]), rows)
            with self.assertRaises(EvidenceError):
                reduce_p0a(article, cycles, loads)

    def test_short_load_screen_is_recorded_as_failed_not_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads = self._nominal(Path(directory))
            rows = self._read_rows(loads)
            rows[0]["duration_s"] = "9.9"
            write_csv(loads, list(rows[0]), rows)
            metrics = reduce_p0a(article, cycles, loads)
        self.assertFalse(evaluate_gate("P0-A", metrics).passed)
        self.assertEqual(metrics["axial_screen_load_held_n"], 0.0)

    def test_failed_capture_does_not_count_as_completed_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            article, cycles, loads = self._nominal(Path(directory))
            rows = self._read_rows(cycles)
            rows[0]["capture_confirmed"] = "0"
            write_csv(cycles, list(rows[0]), rows)
            metrics = reduce_p0a(article, cycles, loads)
        self.assertEqual(metrics["manual_cycles"], 49)
        self.assertFalse(evaluate_gate("P0-A", metrics).passed)


if __name__ == "__main__":
    unittest.main()
