"""Tests for the capture-architecture trade study's reduction and report.

These deliberately do not run the campaign.  Evaluating five architectures
across eight conditions takes minutes, and what needs guarding here is not
the physics — every mechanism has its own suite for that — but the layer
that turns episode counts into the row a human reads and ranks on.  That
layer is where a mistake is quiet: a wrong tolerance or a dropped field
still produces a well-formed table, and a well-formed table gets believed.

The report is the artefact a hardware decision gets made from, so the
fields that decision hinges on are asserted to be present, not merely
computable.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiur.sim.architectures import BASELINE, CANDIDATES
from aiur.sim.design_study import (
    COLLAPSE_RATE_PCT,
    NOISE_SCALES,
    WIND_LEVELS_M_S,
    ArchitectureResult,
    ConditionResult,
    run_study,
)


def _condition(axis: str, level: float, rate: float, unsafe: int = 0) -> ConditionResult:
    return ConditionResult(
        axis=axis,
        level=level,
        episodes=24,
        capture_rate_pct=rate,
        ci_low_pct=max(0.0, rate - 10.0),
        ci_high_pct=min(100.0, rate + 10.0),
        unsafe_episodes=unsafe,
    )


def _result(**changes) -> ArchitectureResult:
    """An otherwise-unremarkable row, so each test varies one thing."""

    fields = dict(
        key="candidate",
        name="Candidate",
        summary="A candidate.",
        noise_tolerance=10.0,
        wind_tolerance_m_s=0.5,
        nominal_capture_rate_pct=99.0,
        fault_episodes=24,
        unsafe_fault_outcomes=0,
        conditions=(_condition("noise", 1.0, 99.0),),
        part_count=5,
        actuator_count=1,
        sensed_channels=2,
        est_dock_mass_g=75.0,
        est_probe_mass_g=2.0,
        known_weaknesses=("A weakness.",),
    )
    fields.update(changes)
    return ArchitectureResult(**fields)


class SafetyPredicateTests(unittest.TestCase):
    """``safe`` is the first ranking key, so it has to mean what it says."""

    def test_clean_run_is_safe(self):
        self.assertTrue(_result().safe)

    def test_unsafe_fault_outcome_is_not_safe(self):
        self.assertFalse(_result(unsafe_fault_outcomes=1).safe)

    def test_unsafe_event_at_any_condition_is_not_safe(self):
        # An unsafe episode on the wind axis counts even though the fault
        # axis was clean: the axes are conditions of the same article, not
        # separate safety cases, and a strike is a strike wherever it fell.
        row = _result(
            conditions=(
                _condition("noise", 1.0, 99.0),
                _condition("wind", 1.0, 80.0, unsafe=1),
            )
        )
        self.assertFalse(row.safe)


class ReportShapeTests(unittest.TestCase):
    """The report is what a build decision reads; assert its fields exist."""

    def setUp(self):
        self.rows = [
            _result(key="a", name="A", noise_tolerance=30.0),
            _result(key="b", name="B", noise_tolerance=3.0),
        ]
        self.report = self._study(self.rows)

    def _study(self, rows):
        """Run the reduction with evaluation stubbed to fixed rows."""

        from aiur.sim import design_study

        specs = [type("Spec", (), {"key": r.key})() for r in rows]
        by_key = {r.key: r for r in rows}
        original = design_study.evaluate_architecture
        design_study.evaluate_architecture = (
            lambda spec, **kwargs: by_key[spec.key]
        )
        try:
            return run_study(specs, episodes_per_condition=24, seed=1)
        finally:
            design_study.evaluate_architecture = original

    def test_safe_survives_serialisation(self):
        # asdict() drops properties.  Ranking safety first and then omitting
        # it from the report would leave a table that looks authoritative
        # while withholding the finding it was ranked on.
        for architecture in self.report["architectures"]:
            self.assertIn("safe", architecture)
            self.assertIsInstance(architecture["safe"], bool)

    def test_report_is_json_serialisable(self):
        # The CLI prints JSON and tools/report_study.py reads it back; a
        # report that only exists as Python objects is not an artefact.
        round_tripped = json.loads(json.dumps(self.report, sort_keys=True))
        self.assertEqual(
            [a["key"] for a in round_tripped["architectures"]],
            [a["key"] for a in self.report["architectures"]],
        )

    def test_cost_terms_are_reported_beside_results(self):
        # The whole argument for not emitting a single score is that the
        # reader sees the cost terms next to the simulated ones.
        for architecture in self.report["architectures"]:
            for field in (
                "part_count",
                "actuator_count",
                "sensed_channels",
                "est_dock_mass_g",
                "known_weaknesses",
            ):
                self.assertIn(field, architecture)

    def test_no_aggregate_score_is_emitted(self):
        # Guards the design decision, not an implementation detail: adding a
        # "score" key later should require deleting this test deliberately.
        for architecture in self.report["architectures"]:
            self.assertNotIn("score", architecture)

    def test_ranked_by_positioning_tolerance(self):
        self.assertEqual(
            [a["key"] for a in self.report["architectures"]], ["a", "b"]
        )

    def test_unsafe_candidate_ranks_below_safe_one(self):
        # Safety outranks tolerance, so the better-positioned but unsafe
        # candidate must not top the table.
        report = self._study(
            [
                _result(key="a", noise_tolerance=30.0, unsafe_fault_outcomes=1),
                _result(key="b", noise_tolerance=3.0),
            ]
        )
        self.assertEqual([a["key"] for a in report["architectures"]], ["b", "a"])

    def test_caveats_are_carried_with_the_numbers(self):
        # "Simulation only, nothing built" has to travel with the table.
        self.assertTrue(self.report["caveats"])
        self.assertTrue(
            any("Simulation only" in c for c in self.report["caveats"])
        )


class RegistryTests(unittest.TestCase):
    def test_baseline_is_entered_on_the_same_axes(self):
        # The incumbent competes rather than presides.
        self.assertIn(BASELINE, CANDIDATES)

    def test_every_candidate_declares_its_cost_terms(self):
        for spec in CANDIDATES:
            with self.subTest(spec.key):
                self.assertGreater(spec.part_count, 0)
                self.assertGreaterEqual(spec.actuator_count, 0)
                self.assertGreater(spec.est_dock_mass_g, 0.0)
                self.assertTrue(spec.known_weaknesses, "a candidate with no "
                                "stated weakness has not been examined")

    def test_candidate_keys_are_unique(self):
        keys = [spec.key for spec in CANDIDATES]
        self.assertEqual(len(keys), len(set(keys)))


class AxisTests(unittest.TestCase):
    def test_nominal_condition_is_on_the_noise_axis(self):
        # evaluate_architecture reads nominal capture off noise level 1.0;
        # dropping that level would make it raise rather than mislead, but
        # the axis is a published assumption, so pin it.
        self.assertIn(1.0, NOISE_SCALES)

    def test_wind_axis_leaves_still_air_to_the_noise_axis(self):
        self.assertIn(0.0, WIND_LEVELS_M_S)

    def test_collapse_threshold_sits_below_the_gate_requirement(self):
        # "Collapsed" must mean unusable, not marginal — otherwise the
        # tolerance number reports a design that would fail SIL anyway.
        self.assertLess(COLLAPSE_RATE_PCT, 95.0)


if __name__ == "__main__":
    unittest.main()
