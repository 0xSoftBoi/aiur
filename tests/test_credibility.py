"""Tests for the NASA-STD-7009B credibility block and its Wilson intervals.

Two things are being protected here.  First, the arithmetic: an interval
that is subtly wrong is worse than no interval, because it launders a small
campaign into apparent precision.  Second, the honesty rules — a level
without a justification, a validation level claimed without conceptual
validation, or a campaign report that quietly drops its caveats are exactly
the failures the block exists to prevent, so each one is asserted.

Reference interval values below were computed from the Wilson formula by
hand (see the arithmetic in each test's comment) and cross-checked against
the closed form's defining property: at each bound ``b`` of an interior
interval, ``n·(p̂ - b)² = z²·b·(1 - b)``.
"""

import json
import math
import unittest
from dataclasses import asdict

from aiur.sim import campaign
from aiur.sim.credibility import (
    CREDIBILITY_FACTORS,
    Assessment,
    CredibilityAssessment,
    CredibilityFactor,
    FactorScore,
    RateInterval,
    TWIN_CREDIBILITY,
    credibility_block,
    warnings_for,
    wilson_interval,
)


def _score(
    factor: CredibilityFactor,
    level: int = 1,
    threshold: int = 1,
) -> FactorScore:
    """Minimal valid score, used to build assessments under test."""

    return FactorScore(
        factor=factor,
        level=level,
        threshold=threshold,
        justification="test fixture",
        evidence=("test fixture",),
        level_1_conditions_met=True,
    )


class WilsonIntervalTests(unittest.TestCase):
    def test_hand_computed_interval_for_eighteen_of_twenty(self) -> None:
        # p̂ = 0.9, n = 20, z = 1.96: z² = 3.8416, denominator = 1.19208,
        # center = (0.9 + 0.09604)/1.19208 = 0.835548,
        # half = (1.96/1.19208)·sqrt(0.0045 + 0.00240100) = 0.136586.
        low, high = wilson_interval(18, 20)
        self.assertAlmostEqual(low, 0.698962, places=6)
        self.assertAlmostEqual(high, 0.972134, places=6)

    def test_zero_successes_gives_a_lower_bound_of_exactly_zero(self) -> None:
        low, high = wilson_interval(0, 10)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 0.277540, places=6)

    def test_all_successes_gives_an_upper_bound_of_exactly_one(self) -> None:
        low, high = wilson_interval(10, 10)
        self.assertAlmostEqual(low, 0.722460, places=6)
        self.assertEqual(high, 1.0)

    def test_a_perfect_thirty_episode_bin_is_not_certainty(self) -> None:
        # The reason the sweep rows carry intervals at all: the Wald
        # interval at 30/30 has zero width, which reads as certainty.
        low, high = wilson_interval(30, 30)
        self.assertAlmostEqual(low, 0.886483, places=6)
        self.assertEqual(high, 1.0)
        self.assertLess(low, 0.95)

    def test_bounds_satisfy_the_defining_equation(self) -> None:
        # Independent check of the closed form: the Wilson bounds are the
        # roots of n(p̂ - p)² = z²p(1 - p).
        for successes, trials in ((1, 2), (18, 20), (29, 30), (95, 100)):
            with self.subTest(successes=successes, trials=trials):
                p_hat = successes / trials
                for bound in wilson_interval(successes, trials):
                    self.assertAlmostEqual(
                        trials * (p_hat - bound) ** 2,
                        1.96**2 * bound * (1.0 - bound),
                        places=9,
                    )

    def test_interval_narrows_as_the_sample_grows_at_a_fixed_rate(self) -> None:
        widths = []
        for successes, trials in ((19, 20), (95, 100), (950, 1000)):
            low, high = wilson_interval(successes, trials)
            widths.append(high - low)
        for wider, narrower in zip(widths, widths[1:]):
            self.assertLess(narrower, wider)

    def test_interval_always_brackets_the_point_estimate(self) -> None:
        for trials in (1, 2, 5, 30, 200):
            for successes in range(trials + 1):
                with self.subTest(successes=successes, trials=trials):
                    low, high = wilson_interval(successes, trials)
                    self.assertLessEqual(low, successes / trials)
                    self.assertLessEqual(successes / trials, high)
                    self.assertGreaterEqual(low, 0.0)
                    self.assertLessEqual(high, 1.0)

    def test_higher_confidence_widens_the_interval(self) -> None:
        narrow = wilson_interval(18, 20, z=1.0)
        wide = wilson_interval(18, 20, z=2.576)
        self.assertLess(wide[0], narrow[0])
        self.assertGreater(wide[1], narrow[1])

    def test_invalid_inputs_raise(self) -> None:
        for successes, trials in ((0, 0), (0, -1), (-1, 10), (11, 10)):
            with self.subTest(successes=successes, trials=trials):
                with self.assertRaises(ValueError):
                    wilson_interval(successes, trials)
        with self.assertRaises(ValueError):
            wilson_interval(5, 10, z=0.0)

    def test_rate_interval_reports_percent_and_keeps_the_counts(self) -> None:
        payload = RateInterval("nominal_capture_rate_pct", 18, 20).as_dict()
        self.assertEqual(payload["successes"], 18)
        self.assertEqual(payload["trials"], 20)
        self.assertEqual(payload["point_pct"], 90.0)
        self.assertEqual(payload["ci_low_pct"], 69.9)
        self.assertEqual(payload["ci_high_pct"], 97.21)
        self.assertEqual(payload["method"], "Wilson score interval")

    def test_rate_interval_rejects_an_impossible_count(self) -> None:
        with self.assertRaises(ValueError):
            RateInterval("nominal_capture_rate_pct", 3, 0)


class FactorScoreTests(unittest.TestCase):
    def test_a_score_without_justification_is_rejected(self) -> None:
        for justification in ("", "   ", "\n"):
            with self.subTest(justification=justification):
                with self.assertRaises(ValueError):
                    FactorScore(
                        factor=CredibilityFactor.VERIFICATION,
                        level=2,
                        threshold=3,
                        justification=justification,
                        evidence=("unit suite",),
                    )

    def test_a_level_above_zero_must_name_its_evidence(self) -> None:
        with self.assertRaises(ValueError):
            FactorScore(
                factor=CredibilityFactor.VERIFICATION,
                level=2,
                threshold=3,
                justification="claims a level with nothing behind it",
            )

    def test_level_zero_may_have_no_evidence(self) -> None:
        score = FactorScore(
            factor=CredibilityFactor.USE_ANALYSIS_TECHNICAL_REVIEW,
            level=0,
            threshold=1,
            justification="no independent review has been held",
        )
        self.assertEqual(score.evidence, ())

    def test_levels_outside_zero_to_four_are_rejected(self) -> None:
        for level, threshold in ((5, 4), (-1, 1), (2, 5)):
            with self.subTest(level=level, threshold=threshold):
                with self.assertRaises(ValueError):
                    FactorScore(
                        factor=CredibilityFactor.VERIFICATION,
                        level=level,
                        threshold=threshold,
                        justification="out of range",
                        evidence=("x",),
                    )

    def test_fractional_levels_are_rejected_because_there_is_no_partial_credit(
        self,
    ) -> None:
        with self.assertRaises(TypeError):
            FactorScore(
                factor=CredibilityFactor.VERIFICATION,
                level=2.5,  # type: ignore[arg-type]
                threshold=3,
                justification="partial credit is not a thing in 7009B",
                evidence=("x",),
            )

    def test_gap_is_achieved_minus_threshold(self) -> None:
        deficient = _score(CredibilityFactor.VERIFICATION, level=1, threshold=3)
        self.assertEqual(deficient.gap, -2)
        self.assertFalse(deficient.meets_threshold)
        exceeded = _score(CredibilityFactor.VERIFICATION, level=4, threshold=3)
        self.assertEqual(exceeded.gap, 1)
        self.assertTrue(exceeded.meets_threshold)


class ValidationGatingTests(unittest.TestCase):
    def test_validation_above_level_one_requires_the_level_one_conditions(
        self,
    ) -> None:
        with self.assertRaises(ValueError) as raised:
            FactorScore(
                factor=CredibilityFactor.VALIDATION,
                level=3,
                threshold=3,
                justification="claims empirical validation without conceptual",
                evidence=("bench comparison",),
                level_1_conditions_met=False,
            )
        self.assertIn("conceptually validated", str(raised.exception))

    def test_validation_above_level_one_is_allowed_once_conditions_hold(self) -> None:
        score = FactorScore(
            factor=CredibilityFactor.VALIDATION,
            level=3,
            threshold=3,
            justification="hypothetical post-calibration state",
            evidence=("P0-B replay within declared tolerances",),
            level_1_conditions_met=True,
        )
        self.assertEqual(score.level, 3)

    def test_the_gating_rule_applies_only_to_the_validation_factor(self) -> None:
        score = FactorScore(
            factor=CredibilityFactor.VERIFICATION,
            level=4,
            threshold=3,
            justification="the gate is a validation-factor rule only",
            evidence=("unit suite",),
        )
        self.assertEqual(score.level, 4)


class AssessmentStructureTests(unittest.TestCase):
    def _complete_scores(self) -> tuple[FactorScore, ...]:
        return tuple(_score(factor) for factor in CREDIBILITY_FACTORS)

    def test_a_partial_assessment_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as raised:
            CredibilityAssessment(
                subject="partial",
                scored_on="2026-08-08",
                threshold_basis="test",
                scores=self._complete_scores()[:-1],
            )
        self.assertIn("unscored", str(raised.exception))

    def test_a_factor_cannot_be_scored_twice(self) -> None:
        scores = self._complete_scores()
        with self.assertRaises(ValueError):
            CredibilityAssessment(
                subject="duplicated",
                scored_on="2026-08-08",
                threshold_basis="test",
                scores=scores + (scores[0],),
            )

    def test_assessments_split_five_capability_and_six_results_factors(self) -> None:
        self.assertEqual(len(CREDIBILITY_FACTORS), 11)
        self.assertEqual(
            len(TWIN_CREDIBILITY.for_assessment(Assessment.CAPABILITY)), 5
        )
        self.assertEqual(len(TWIN_CREDIBILITY.for_assessment(Assessment.RESULTS)), 6)


class TwinCredibilityTests(unittest.TestCase):
    def test_validation_is_level_one_conceptual_only(self) -> None:
        validation = TWIN_CREDIBILITY.score_for(CredibilityFactor.VALIDATION)
        self.assertEqual(validation.level, 1)
        self.assertTrue(validation.level_1_conditions_met)

    def test_the_validation_gap_is_reported(self) -> None:
        validation = TWIN_CREDIBILITY.score_for(CredibilityFactor.VALIDATION)
        self.assertLess(validation.gap, 0)
        self.assertIn(validation, TWIN_CREDIBILITY.deficiencies())
        gaps = {row["factor"]: row["gap"] for row in TWIN_CREDIBILITY.as_dict()["gaps"]}
        self.assertEqual(gaps[CredibilityFactor.VALIDATION.value], validation.gap)

    def test_every_factor_carries_a_justification(self) -> None:
        for score in TWIN_CREDIBILITY.scores:
            with self.subTest(factor=score.factor.value):
                self.assertTrue(score.justification.strip())

    def test_warnings_always_state_that_no_empirical_validation_exists(self) -> None:
        warnings = warnings_for(TWIN_CREDIBILITY)
        matches = [w for w in warnings if "no empirical validation" in w]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].startswith("[M&S 32 e]"))
        self.assertIn("Impact:", matches[0])

    def test_warnings_always_carry_the_scope_waiver_and_known_defects(self) -> None:
        warnings = warnings_for(TWIN_CREDIBILITY)
        self.assertTrue(any(w.startswith("[M&S 32 g]") for w in warnings))
        defects = [w for w in warnings if w.startswith("[M&S 32 h]")]
        self.assertTrue(defects)
        self.assertTrue(any("0.36 N" in w for w in defects))

    def test_warnings_report_domain_exits_and_violated_assumptions(self) -> None:
        warnings = warnings_for(
            TWIN_CREDIBILITY,
            outside_declared_domain=("mean_wind_m_s=1.5",),
            violated_assumptions=("two simultaneous faults were injected",),
        )
        domain = [w for w in warnings if w.startswith("[M&S 32 c]")]
        assumptions = [w for w in warnings if w.startswith("[M&S 32 b]")]
        self.assertEqual(len(domain), 1)
        self.assertIn("mean_wind_m_s=1.5", domain[0])
        self.assertEqual(len(assumptions), 1)
        self.assertIn("simultaneous faults", assumptions[0])

    def test_every_factor_below_threshold_produces_a_warning(self) -> None:
        warnings = warnings_for(TWIN_CREDIBILITY)
        unachieved = [w for w in warnings if w.startswith("[M&S 32 a]")]
        self.assertEqual(len(unachieved), len(TWIN_CREDIBILITY.deficiencies()))

    def test_block_reports_no_estimate_when_no_rate_was_measurable(self) -> None:
        block = credibility_block(
            TWIN_CREDIBILITY,
            no_estimate_reason="the campaign ran no fault-free episodes",
        )
        uncertainty = block["uncertainty"]
        self.assertEqual(uncertainty["rate_intervals"], [])
        self.assertIn("[M&S 33]c", uncertainty["statement"])


class CampaignReportCredibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.campaign = campaign.run_campaign(
            "sil-p0b", episodes=6, seed=5, fault_fraction=0.34
        )

    def test_report_carries_the_credibility_block(self) -> None:
        block = self.campaign.credibility
        self.assertEqual(len(block["capability_assessment"]), 5)
        self.assertEqual(len(block["results_assessment"]), 6)
        self.assertTrue(block["gaps"])
        self.assertTrue(block["warnings"])
        self.assertTrue(block["declared_domain"])

    def test_interval_brackets_the_reported_capture_rate(self) -> None:
        intervals = self.campaign.credibility["uncertainty"]["rate_intervals"]
        self.assertEqual(len(intervals), 1)
        interval = intervals[0]
        self.assertEqual(interval["metric"], "nominal_capture_rate_pct")
        point = self.campaign.metrics["nominal_capture_rate_pct"]
        self.assertEqual(interval["point_pct"], point)
        self.assertLessEqual(interval["ci_low_pct"], point)
        self.assertLessEqual(point, interval["ci_high_pct"])
        # Four fault-free episodes cannot support a >=95% claim; the point
        # estimate of 100% alone would suggest it does.
        self.assertLess(interval["ci_low_pct"], 95.0)

    def test_failed_gate_criteria_appear_as_unachieved_acceptance_criteria(
        self,
    ) -> None:
        warnings = self.campaign.credibility["warnings"]
        self.assertTrue(
            any("at least 200 seeded episodes" in w for w in warnings),
            warnings,
        )

    def test_report_stays_json_serializable(self) -> None:
        payload = json.loads(json.dumps(asdict(self.campaign)))
        self.assertIn("credibility", payload)
        self.assertIn("uncertainty", payload["credibility"])

    def test_existing_report_keys_are_unchanged(self) -> None:
        for key in (
            "scenario",
            "gate_id",
            "episodes",
            "metrics",
            "outcome_counts",
            "unsafe_details",
            "verdict_passed",
            "verdict",
        ):
            with self.subTest(key=key):
                self.assertIn(key, asdict(self.campaign))


class SweepIntervalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # One episode per bin: this test is about the reported statistics,
        # not about the study's findings, which need 30 episodes per bin.
        cls.sweep = campaign.run_sweep(
            "degraded-sensor-sweep", episodes_per_bin=1, seed=3
        )

    def test_every_bin_row_carries_an_interval_around_its_point(self) -> None:
        for row in self.sweep["bins"]:
            with self.subTest(noise_scale=row["noise_scale"]):
                self.assertLessEqual(row["ci_low_pct"], row["capture_rate_pct"])
                self.assertLessEqual(row["capture_rate_pct"], row["ci_high_pct"])
                self.assertGreaterEqual(row["ci_low_pct"], 0.0)
                self.assertLessEqual(row["ci_high_pct"], 100.0)

    def test_a_single_episode_bin_has_a_nearly_useless_interval(self) -> None:
        row = self.sweep["bins"][0]
        self.assertGreater(row["ci_high_pct"] - row["ci_low_pct"], 50.0)

    def test_bins_outside_the_declared_domain_are_warned_about(self) -> None:
        warnings = self.sweep["credibility"]["warnings"]
        domain = [w for w in warnings if w.startswith("[M&S 32 c]")]
        # noise_scale 3, 10 and 30 all exceed the declared Lighthouse grade.
        self.assertEqual(len(domain), 3)
        self.assertTrue(all("noise_scale=" in w for w in domain))

    def test_sweep_keeps_its_existing_shape(self) -> None:
        self.assertEqual(self.sweep["study"], "degraded-sensor-sweep")
        first = self.sweep["bins"][0]
        for key in (
            "noise_scale",
            "episodes",
            "capture_rate_pct",
            "unsafe_episodes",
            "mean_aborts",
        ):
            with self.subTest(key=key):
                self.assertIn(key, first)


class WilsonReferenceTests(unittest.TestCase):
    """Guard against a refactor silently switching to the Wald interval."""

    def test_wald_and_wilson_disagree_where_it_matters(self) -> None:
        successes, trials = 30, 30
        p_hat = successes / trials
        wald_half = 1.96 * math.sqrt(p_hat * (1 - p_hat) / trials)
        self.assertEqual(wald_half, 0.0)
        low, high = wilson_interval(successes, trials)
        self.assertGreater(high - low, 0.10)


if __name__ == "__main__":
    unittest.main()
