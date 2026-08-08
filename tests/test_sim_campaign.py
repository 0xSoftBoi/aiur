"""End-to-end tests for the digital-twin episode engine, scenario builders,
SIL gates, and campaign runner.

Kept deliberately fast: single episodes and tiny campaigns only.  Every seed
is fixed, so each assertion documents the exact deterministic behavior of the
(config, seed) pair it names.
"""

import contextlib
import io
import json
import unittest

from aiur.loop_graph import evaluate_gate, gate_by_id
from aiur.sim import campaign
from aiur.sim.engine import EpisodeOutcome, run_episode
from aiur.sim.events import EventKind
from aiur.sim.gates import evaluate_sil_gate, validate_sil_gates
from aiur.sim.scenarios import sil_p0b, sil_p0c, sil_p0d

P0B_SEED = 7
P0C_SEED = 3
P0D_SEED = 11


def _event_kinds(result):
    return [event.kind for event in result.events]


class EpisodeDeterminismTests(unittest.TestCase):
    def test_same_config_and_seed_reproduce_the_episode_exactly(self) -> None:
        first = run_episode(sil_p0b(P0B_SEED), P0B_SEED)
        second = run_episode(sil_p0b(P0B_SEED), P0B_SEED)
        self.assertEqual(first.outcome, second.outcome)
        self.assertEqual(first.duration_s, second.duration_s)
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.captures, second.captures)
        self.assertEqual(first.aborts, second.aborts)
        self.assertEqual(
            first.max_contact_closing_m_s, second.max_contact_closing_m_s
        )


class NominalSilP0bEpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_episode(sil_p0b(P0B_SEED), P0B_SEED)

    def test_episode_ends_in_success(self) -> None:
        self.assertIs(self.result.outcome, EpisodeOutcome.SUCCESS)
        self.assertTrue(self.result.script_completed)

    def test_exactly_one_true_capture_confirmed(self) -> None:
        kinds = _event_kinds(self.result)
        self.assertEqual(kinds.count(EventKind.CAPTURE_CONFIRMED), 1)
        self.assertEqual(kinds.count(EventKind.FALSE_CAPTURE_CONFIRMED), 0)
        self.assertEqual(self.result.captures, 1)

    def test_no_unsafe_events(self) -> None:
        self.assertEqual(self.result.unsafe_events, ())

    def test_telemetry_empty_when_not_requested(self) -> None:
        self.assertEqual(self.result.telemetry, ())


class NominalSilP0cEpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_episode(sil_p0c(P0C_SEED), P0C_SEED)

    def test_launch_sortie_recover_script_completes(self) -> None:
        self.assertIs(self.result.outcome, EpisodeOutcome.SUCCESS)
        self.assertTrue(self.result.script_completed)

    def test_one_capture_after_launch(self) -> None:
        self.assertEqual(self.result.captures, 1)

    def test_release_precedes_the_recovery_capture(self) -> None:
        kinds = _event_kinds(self.result)
        self.assertIn(EventKind.RELEASED, kinds)
        self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds)
        self.assertLess(
            kinds.index(EventKind.RELEASED),
            kinds.index(EventKind.CAPTURE_CONFIRMED),
        )

    def test_no_unsafe_events(self) -> None:
        self.assertEqual(self.result.unsafe_events, ())


class NominalSilP0dEpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_episode(sil_p0d(P0D_SEED), P0D_SEED)

    def test_two_aircraft_sequence_completes(self) -> None:
        self.assertIs(self.result.outcome, EpisodeOutcome.SUCCESS)
        self.assertTrue(self.result.script_completed)

    def test_no_separation_or_simultaneous_approach_violations(self) -> None:
        kinds = _event_kinds(self.result)
        self.assertEqual(kinds.count(EventKind.SEPARATION_VIOLATION), 0)
        self.assertEqual(kinds.count(EventKind.SIMULTANEOUS_DOCK_APPROACH), 0)

    def test_both_a_capture_and_a_safe_landing_occur(self) -> None:
        kinds = _event_kinds(self.result)
        self.assertIn(EventKind.CAPTURE_CONFIRMED, kinds)
        self.assertIn(EventKind.SAFE_LANDING, kinds)


class TelemetryRecordingTests(unittest.TestCase):
    def test_recorded_telemetry_is_nonempty_and_time_ordered(self) -> None:
        result = run_episode(sil_p0b(P0B_SEED, record_telemetry=True), P0B_SEED)
        self.assertGreater(len(result.telemetry), 0)
        times = [row.t_s for row in result.telemetry]
        for earlier, later in zip(times, times[1:]):
            self.assertLessEqual(earlier, later)
        self.assertEqual(times[0], 0.0)


class SilGateTests(unittest.TestCase):
    PASSING_SIL_B_METRICS = {
        "episodes": 200,
        "nominal_capture_rate_pct": 97.5,
        "max_contact_closing_m_s": 0.15,
        "prop_funnel_contacts": 0,
        "overspeed_contacts": 0,
        "envelope_strikes": 0,
        "fault_episodes": 50,
        "unsafe_fault_outcomes": 0,
    }

    def test_sil_gate_definitions_are_structurally_valid(self) -> None:
        self.assertEqual(validate_sil_gates(), ())

    def test_missing_metrics_fail_the_gate_and_are_listed(self) -> None:
        verdict = evaluate_sil_gate("SIL-B", {})
        self.assertFalse(verdict.passed)
        self.assertEqual(
            set(verdict.missing_metrics), set(self.PASSING_SIL_B_METRICS)
        )

    def test_complete_passing_metrics_pass_sil_b(self) -> None:
        verdict = evaluate_sil_gate("SIL-B", self.PASSING_SIL_B_METRICS)
        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.missing_metrics, ())
        self.assertEqual(verdict.failed_criteria, ())

    def test_unknown_gate_id_raises(self) -> None:
        with self.assertRaises(KeyError):
            evaluate_sil_gate("SIL-Z", self.PASSING_SIL_B_METRICS)


class TinyCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.campaign = campaign.run_campaign(
            "sil-p0b", episodes=6, seed=5, fault_fraction=0.34
        )

    def test_campaign_runs_the_requested_episode_count(self) -> None:
        self.assertEqual(self.campaign.episodes, 6)
        self.assertEqual(self.campaign.metrics["episodes"], 6)
        # round(6 * 0.34) == 2 fault episodes.
        self.assertEqual(self.campaign.metrics["fault_episodes"], 2)

    def test_verdict_fails_purely_on_episode_and_fault_quotas(self) -> None:
        self.assertFalse(self.campaign.verdict_passed)
        failed = self.campaign.verdict["failed_criteria"]
        self.assertIn("at least 200 seeded episodes", failed)
        quota_criteria = {
            "at least 200 seeded episodes",
            "at least 50 fault-injection episodes",
        }
        self.assertTrue(set(failed) <= quota_criteria)
        self.assertEqual(self.campaign.verdict["missing_metrics"], ())

    def test_no_unsafe_episodes(self) -> None:
        self.assertEqual(self.campaign.unsafe_details, ())
        self.assertNotIn(
            EpisodeOutcome.UNSAFE.value, self.campaign.outcome_counts
        )
        self.assertEqual(self.campaign.metrics["prop_funnel_contacts"], 0)
        self.assertEqual(self.campaign.metrics["envelope_strikes"], 0)
        self.assertEqual(self.campaign.metrics["unsafe_fault_outcomes"], 0)

    def test_outcome_counts_cover_every_episode(self) -> None:
        self.assertEqual(sum(self.campaign.outcome_counts.values()), 6)


class CampaignCliTests(unittest.TestCase):
    def test_main_prints_json_and_exits_one_on_quota_failure(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = campaign.main(
                ["--scenario", "sil-p0b", "--episodes", "4", "--seed", "2"]
            )
        self.assertEqual(exit_code, 1)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["scenario"], "sil-p0b")
        self.assertEqual(payload["gate_id"], "SIL-B")
        self.assertEqual(payload["episodes"], 4)
        self.assertFalse(payload["verdict_passed"])
        self.assertIn(
            "at least 200 seeded episodes",
            payload["verdict"]["failed_criteria"],
        )


class LoopGraphRegressionTests(unittest.TestCase):
    """The SIL-gate refactor must not break the hardware-gate evaluator."""

    def test_evaluate_gate_still_passes_p0a_with_complete_metrics(self) -> None:
        # Built from the gate definition so a new criterion cannot silently
        # turn this regression test into an assertion about a stale gate.
        metrics: dict[str, float | int] = {
            criterion.metric: criterion.threshold
            for criterion in gate_by_id("P0-A").criteria
        }
        verdict = evaluate_gate("P0-A", metrics)
        self.assertEqual(verdict.gate_id, "P0-A")
        self.assertTrue(verdict.passed, verdict)
        self.assertEqual(verdict.missing_metrics, ())
        self.assertEqual(verdict.failed_criteria, ())

    def test_evaluate_gate_still_fails_p0a_on_missing_evidence(self) -> None:
        verdict = evaluate_gate("P0-A", {"life_test_cycles": 600})
        self.assertFalse(verdict.passed)
        self.assertIn("dock_mass_g", verdict.missing_metrics)


if __name__ == "__main__":
    unittest.main()
