import dataclasses
import unittest

from aiur.loop_graph import GATES, Stage
from aiur.requirements import (
    REQUIREMENTS,
    ClosureStatus,
    Requirement,
    VerificationMethod,
    coverage_report,
    requirement_by_id,
    requirements_for_gate,
    snapshot,
    validate_requirements,
)
from aiur.sim.gates import SIL_GATES


def _registry_with(requirement_id: str, **changes: object) -> tuple[Requirement, ...]:
    """Copy of the registry with one requirement replaced.

    The real registry is never mutated; every negative test runs against a
    copy so a failing assertion cannot leak into the next test.
    """

    return tuple(
        dataclasses.replace(requirement, **changes)
        if requirement.id == requirement_id
        else requirement
        for requirement in REQUIREMENTS
    )


class RequirementRegistryTests(unittest.TestCase):
    def test_registry_validates_clean(self) -> None:
        self.assertEqual(validate_requirements(), ())

    def test_ids_are_unique_sorted_and_resolvable(self) -> None:
        ids = [requirement.id for requirement in REQUIREMENTS]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        for requirement_id in ids:
            self.assertEqual(requirement_by_id(requirement_id).id, requirement_id)

    def test_unknown_requirement_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            requirement_by_id("P0-DOCK-999")

    def test_every_gate_closes_at_least_one_requirement(self) -> None:
        for gate in (*GATES, *SIL_GATES):
            self.assertTrue(
                requirements_for_gate(gate.gate_id),
                f"{gate.gate_id} closes no requirement",
            )

    def test_linked_criteria_exist_in_their_gate(self) -> None:
        criteria = {
            gate.gate_id: {criterion.metric for criterion in gate.criteria}
            for gate in (*GATES, *SIL_GATES)
        }
        for requirement in REQUIREMENTS:
            if requirement.criterion_metric is None:
                continue
            self.assertIn(requirement.gate_id, criteria)
            self.assertIn(
                requirement.criterion_metric,
                criteria[requirement.gate_id],
                f"{requirement.id} links a metric {requirement.gate_id} does not define",
            )

    def test_closed_requirements_name_their_evidence(self) -> None:
        closed = [r for r in REQUIREMENTS if r.status is ClosureStatus.CLOSED]
        self.assertTrue(closed)
        for requirement in closed:
            self.assertTrue(
                requirement.closing_evidence.strip(),
                f"{requirement.id} is closed without evidence",
            )

    def test_accepted_risks_carry_a_rationale(self) -> None:
        accepted = [r for r in REQUIREMENTS if r.status is ClosureStatus.ACCEPTED_RISK]
        self.assertEqual(
            {requirement.id for requirement in accepted},
            {"SIL-005", "SIL-006"},
        )
        for requirement in accepted:
            self.assertGreater(len(requirement.rationale.strip()), 40)

    def test_program_limits_are_encoded(self) -> None:
        self.assertIn("0.20 m/s", requirement_by_id("P0-DOCK-002").limit)
        self.assertIn("0.10 m/s", requirement_by_id("P0-DOCK-003").limit)
        self.assertIn("180 mm", requirement_by_id("P0-DOCK-001").limit)
        self.assertIn("180 g", requirement_by_id("P0-MASS-001").limit)
        self.assertIn("8 g", requirement_by_id("P0-MASS-002").limit)
        self.assertIn("S1", requirement_by_id("P0-DOCK-004").limit)
        self.assertIn("S2", requirement_by_id("P0-DOCK-004").limit)


class RequirementValidationTests(unittest.TestCase):
    def test_closed_without_evidence_is_an_error(self) -> None:
        errors = validate_requirements(_registry_with("SIL-001", closing_evidence=""))
        self.assertIn("SIL-001 is closed without closing evidence", errors)
        self.assertEqual(validate_requirements(), ())

    def test_accepted_risk_without_rationale_is_an_error(self) -> None:
        errors = validate_requirements(_registry_with("SIL-006", rationale=""))
        self.assertIn("SIL-006 accepts risk without a rationale", errors)

    def test_bogus_criterion_metric_is_caught(self) -> None:
        errors = validate_requirements(
            _registry_with("P0-DOCK-002", criterion_metric="closing_speed_but_faster")
        )
        self.assertIn(
            "P0-DOCK-002 links criterion closing_speed_but_faster which gate P0-B "
            "does not define",
            errors,
        )

    def test_criterion_without_a_gate_is_caught(self) -> None:
        errors = validate_requirements(
            _registry_with("P0-MASS-003", criterion_metric="dock_mass_g")
        )
        self.assertIn(
            "P0-MASS-003 links criterion dock_mass_g without a gate",
            errors,
        )

    def test_unknown_gate_is_caught(self) -> None:
        errors = validate_requirements(_registry_with("P0-SAFE-001", gate_id="P0-Z"))
        self.assertIn("P0-SAFE-001 references unknown gate P0-Z", errors)

    def test_gate_at_another_stage_is_caught(self) -> None:
        errors = validate_requirements(
            _registry_with("P0-MASS-001", stage=Stage.TETHERED_FLIGHT)
        )
        self.assertIn(
            "P0-MASS-001 is staged tethered_flight but gate P0-A closes at bench_hil",
            errors,
        )

    def test_missing_method_is_caught(self) -> None:
        errors = validate_requirements(_registry_with("P0-DOCK-001", method=None))
        self.assertIn("P0-DOCK-001 has no verification method", errors)

    def test_empty_schema_field_is_caught(self) -> None:
        errors = validate_requirements(_registry_with("P0-DOCK-002", limit="  "))
        self.assertIn("P0-DOCK-002 has an empty limit", errors)

    def test_duplicate_and_unsorted_ids_are_caught(self) -> None:
        errors = validate_requirements(REQUIREMENTS + (REQUIREMENTS[0],))
        self.assertIn("requirement ids must be unique", errors)
        self.assertIn("requirement ids must be listed in sorted order", errors)


class CoverageReportTests(unittest.TestCase):
    def test_totals_equal_the_registry_size(self) -> None:
        report = coverage_report()
        self.assertEqual(report["total"], len(REQUIREMENTS))
        for key in ("by_status", "by_method", "by_stage"):
            self.assertEqual(
                sum(report[key].values()),
                len(REQUIREMENTS),
                f"{key} does not account for every requirement",
            )

    def test_every_enum_value_is_a_stable_key(self) -> None:
        report = coverage_report()
        self.assertEqual(
            set(report["by_status"]), {status.value for status in ClosureStatus}
        )
        self.assertEqual(
            set(report["by_method"]), {method.value for method in VerificationMethod}
        )
        self.assertEqual(set(report["by_stage"]), {stage.value for stage in Stage})

    def test_open_ids_are_grouped_by_stage(self) -> None:
        report = coverage_report()
        open_ids = {i for ids in report["open_ids_by_stage"].values() for i in ids}
        expected = {
            requirement.id
            for requirement in REQUIREMENTS
            if requirement.status in (ClosureStatus.OPEN, ClosureStatus.IN_WORK)
        }
        self.assertEqual(open_ids, expected)
        self.assertIn(
            "P0-MASS-001", report["open_ids_by_stage"][Stage.BENCH_HIL.value]
        )

    def test_unverified_means_no_gate_and_no_evidence(self) -> None:
        self.assertEqual(coverage_report()["unverified"], ["SIL-005", "SIL-006"])

    def test_dropping_a_gate_link_makes_a_requirement_unverified(self) -> None:
        report = coverage_report(_registry_with("P0-SAFE-005", gate_id=None))
        self.assertIn("P0-SAFE-005", report["unverified"])
        self.assertNotIn("P0-SAFE-005", coverage_report()["unverified"])


class SnapshotTests(unittest.TestCase):
    def test_snapshot_reports_validity_and_every_requirement(self) -> None:
        data = snapshot()
        self.assertTrue(data["valid"])
        self.assertEqual(data["errors"], [])
        self.assertEqual(len(data["requirements"]), len(REQUIREMENTS))
        first = data["requirements"][0]
        self.assertEqual(first["id"], REQUIREMENTS[0].id)
        self.assertEqual(first["method"], REQUIREMENTS[0].method.value)
        self.assertEqual(first["stage"], REQUIREMENTS[0].stage.value)


if __name__ == "__main__":
    unittest.main()
