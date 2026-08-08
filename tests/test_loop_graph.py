import unittest

from aiur.loop_graph import (
    GATES,
    Stage,
    ENGINEERING_LOOP,
    evaluate_gate,
    gate_by_id,
    validate_loop_graph,
)


def passing_metrics(gate_id: str, **overrides: float | int) -> dict[str, float | int]:
    """Build a metric set that satisfies every criterion of a gate.

    Derived from the gate definition itself so adding a criterion cannot
    leave these tests asserting against a stale idea of the gate; each test
    then overrides only the value it is actually about.
    """

    metrics: dict[str, float | int] = {}
    for criterion in gate_by_id(gate_id).criteria:
        if criterion.operator == ">=":
            metrics[criterion.metric] = criterion.threshold
        elif criterion.operator == "<=":
            metrics[criterion.metric] = criterion.threshold
        else:
            metrics[criterion.metric] = criterion.threshold
    metrics.update(overrides)
    return metrics


class EngineeringLoopTests(unittest.TestCase):
    def test_passing_metrics_helper_covers_every_gate(self) -> None:
        for gate in GATES:
            self.assertTrue(evaluate_gate(gate.gate_id, passing_metrics(gate.gate_id)).passed)

    def test_loop_graph_invariants_hold(self) -> None:
        self.assertEqual(validate_loop_graph(), ())

    def test_no_changed_article_can_shortcut_to_flight(self) -> None:
        entries = [edge for edge in ENGINEERING_LOOP if edge.target is Stage.TETHERED_FLIGHT]
        self.assertEqual(
            {(edge.source, edge.event) for edge in entries},
            {
                (Stage.BENCH_HIL, "bench_gate_pass"),
                (
                    Stage.DISPOSITION,
                    "repeat_exact_configuration_for_more_evidence",
                ),
            },
        )

    def test_p0_a_nominal_bench_evidence_passes(self) -> None:
        verdict = evaluate_gate(
            "P0-A",
            passing_metrics(
                "P0-A",
                dock_mass_g=176,
                probe_mass_g=6.8,
                axial_screen_load_held_n=5.2,
                lateral_screen_load_held_n=1.1,
            ),
        )
        self.assertTrue(verdict.passed)

    def test_p0_a_rejects_understrength_latch(self) -> None:
        verdict = evaluate_gate(
            "P0-A",
            passing_metrics("P0-A", axial_screen_load_held_n=4.9),
        )
        self.assertFalse(verdict.passed)
        self.assertIn(
            "positive keeper holds the P0 axial screening load",
            verdict.failed_criteria,
        )

    def test_p0_b_nominal_evidence_passes(self) -> None:
        verdict = evaluate_gate(
            "P0-B",
            passing_metrics("P0-B", captures_last_10=9, max_closing_speed_m_s=0.18),
        )
        self.assertTrue(verdict.passed)

    def test_p0_b_fails_without_kill_path_verified_with_autonomy_off(self) -> None:
        verdict = evaluate_gate(
            "P0-B",
            passing_metrics("P0-B", kill_path_verified_with_autonomy_off=0),
        )
        self.assertFalse(verdict.passed)
        self.assertIn(
            "kill path demonstrated with the autonomy computer powered off",
            verdict.failed_criteria,
        )

    def test_p0_a_fails_without_loaded_emergency_releases(self) -> None:
        verdict = evaluate_gate(
            "P0-A",
            passing_metrics("P0-A", loaded_emergency_release_trials=0),
        )
        self.assertFalse(verdict.passed)

    def test_p0_a_fails_without_keeper_force_margin(self) -> None:
        verdict = evaluate_gate("P0-A", passing_metrics("P0-A", keeper_close_force_margin=1.4))
        self.assertFalse(verdict.passed)

    def test_p0_b_lucky_but_overspeed_capture_fails(self) -> None:
        verdict = evaluate_gate(
            "P0-B",
            {
                "consecutive_attempts": 10,
                "captures_last_10": 10,
                "max_closing_speed_m_s": 0.21,
                "prop_funnel_contacts": 0,
                "safety_abort_failures": 0,
            },
        )
        self.assertFalse(verdict.passed)
        self.assertIn(
            "closing speed stays inside the capture envelope",
            verdict.failed_criteria,
        )

    def test_missing_evidence_never_passes(self) -> None:
        verdict = evaluate_gate("P0-C", {"captures_last_10": 10})
        self.assertFalse(verdict.passed)
        self.assertIn("envelope_strikes", verdict.missing_metrics)

    def test_unknown_gate_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            evaluate_gate("P0-Z", {})


if __name__ == "__main__":
    unittest.main()
