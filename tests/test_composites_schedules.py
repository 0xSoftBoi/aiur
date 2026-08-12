"""Material registry and laminate schedule checks.

Two things are being protected here.  The first is arithmetic consistency in
the material registry — a lamina whose thickness, areal weight and density
disagree is a lamina that will size a part wrongly and never say so.  The
second is that the schedule registry's own guards actually bite: a design
rule nobody can break, or a waiver rule that never fires, is decoration.
Most of the tests below deliberately construct a *bad* schedule and require
the validator to catch it.
"""

import contextlib
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from aiur.composites import schedules
from aiur.composites.clt import Laminate, Ply
from aiur.composites.materials import (
    Basis,
    MATERIALS,
    PW_CARBON_193,
    allowable_grade,
    chemistry,
    material,
    validate_materials,
)
from aiur.composites.schedules import (
    CS_200_DEPLOYABLE_BOOM,
    CS_400_KEEPER_TINE,
    LaminateSchedule,
    OPEN_FINDINGS,
    SCHEDULES,
    TEN_PERCENT_RULE,
    Waiver,
    budget_line_kg,
    evaluate,
    evaluate_all,
    failing_checks,
    handling_moment_n,
    main as schedules_main,
    mass_rollup,
    max_unsupported_span_mm,
    retention_force_n,
    schedule,
    snapshot,
    validate_schedules,
)


class MaterialRegistryTest(unittest.TestCase):
    def test_registry_is_self_consistent(self):
        self.assertEqual([], validate_materials())

    def test_every_material_names_a_known_resin_system(self):
        for mat in MATERIALS.values():
            self.assertIsNotNone(chemistry(mat.chemistry))

    def test_nominal_lamina_is_void_free(self):
        for mat in MATERIALS.values():
            self.assertAlmostEqual(
                mat.theoretical_density_g_cm3(), mat.cured_density_g_cm3, delta=0.01
            )

    def test_areal_mass_exceeds_the_fibre_it_contains(self):
        for mat in MATERIALS.values():
            self.assertGreater(mat.areal_mass_g_m2, mat.fibre_areal_weight_gsm)

    def test_reciprocity_holds(self):
        for mat in MATERIALS.values():
            self.assertAlmostEqual(
                mat.nu12 * mat.e2_mpa / mat.e1_mpa, mat.nu21, places=12
            )

    def test_inconsistent_density_is_caught(self):
        broken = replace(PW_CARBON_193, cured_density_g_cm3=1.40)
        with patch.dict(MATERIALS, {broken.name: broken}):
            errors = validate_materials()
        self.assertTrue(any("rule-of-mixtures" in error for error in errors))

    def test_inconsistent_strain_to_failure_is_caught(self):
        broken = replace(PW_CARBON_193, ultimate_strain_1=0.03)
        with patch.dict(MATERIALS, {broken.name: broken}):
            errors = validate_materials()
        self.assertTrue(any("ultimate strain" in error for error in errors))

    def test_unphysical_poisson_ratio_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            replace(PW_CARBON_193, nu12=0.9)

    def test_unbalanced_weave_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            replace(PW_CARBON_193, e2_mpa=PW_CARBON_193.e1_mpa * 0.5)

    def test_unknown_material_lookup_names_the_alternatives(self):
        with self.assertRaises(KeyError) as caught:
            material("NOT-A-MATERIAL")
        self.assertIn("PW-C-193", str(caught.exception))

    def test_handbook_data_is_not_an_allowable(self):
        from aiur.composites.materials import DESIGN_GRADE_BASES

        for mat in MATERIALS.values():
            self.assertEqual(Basis.HANDBOOK_REPRESENTATIVE, mat.basis)
            self.assertNotIn(mat.basis, DESIGN_GRADE_BASES)
            self.assertTrue(allowable_grade(mat.basis).startswith("trade study"))


class ScheduleRegistryTest(unittest.TestCase):
    def test_registry_is_valid(self):
        self.assertEqual([], validate_schedules())

    def test_no_check_fails(self):
        self.assertEqual([], failing_checks())

    def test_every_schedule_is_symmetric_and_uncoupled(self):
        for item in SCHEDULES:
            laminate = item.laminate()
            self.assertTrue(laminate.is_symmetric(), item.part_id)
            self.assertFalse(laminate.is_coupled(), item.part_id)

    def test_every_schedule_is_balanced(self):
        for item in SCHEDULES:
            self.assertTrue(item.laminate().is_balanced(), item.part_id)

    def test_part_ids_are_unique(self):
        ids = [item.part_id for item in SCHEDULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_schedule_lookup_rejects_unknown_parts(self):
        with self.assertRaises(KeyError):
            schedule("CS-999")

    def test_findings_register_is_empty_and_agrees_with_the_checks(self):
        # Both directions matter: an empty register with a failing advisory
        # check is a hidden problem, and a populated one with no failure is
        # stale paperwork.  validate_schedules enforces both.
        self.assertEqual((), OPEN_FINDINGS)
        self.assertEqual([], failing_checks())


class DesignRuleEnforcementTest(unittest.TestCase):
    """The rules must actually reject a laminate that breaks them."""

    def _schedule_with(self, plies, **overrides):
        base = dict(
            part_id="TEST-001",
            name="test part",
            description="constructed to break a rule",
            plies_top_down=tuple(plies),
            area_m2=0.01,
            mass_allocation_g=50.0,
            budget_line=schedules.DOCK_BUDGET_LINE,
            load_cases=(schedules.cooldown_case(180.0),),
        )
        base.update(overrides)
        return LaminateSchedule(**base)

    def test_unsymmetric_schedule_is_rejected(self):
        item = self._schedule_with(
            [Ply("PW-C-193", 45.0), Ply("PW-C-193", 0.0), Ply("PW-C-193", 0.0)]
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("not symmetric" in error for error in errors))

    def test_schedule_without_load_cases_is_rejected(self):
        item = self._schedule_with(
            [Ply("PW-C-193", 45.0), Ply("PW-C-193", 45.0)], load_cases=()
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("no load cases" in error for error in errors))

    def test_ply_thickness_override_is_rejected_on_a_design_schedule(self):
        item = self._schedule_with(
            [Ply("PW-C-193", 45.0, 0.25), Ply("PW-C-193", 45.0, 0.25)]
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("thickness override" in error for error in errors))

    def test_cylindrical_edge_without_rationale_is_rejected(self):
        item = self._schedule_with(
            [Ply("PW-C-193", 45.0), Ply("PW-C-193", 45.0)], edge="cylindrical"
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("written rationale" in error for error in errors))

    def test_unknown_budget_line_is_rejected(self):
        item = self._schedule_with(
            [Ply("PW-C-193", 45.0), Ply("PW-C-193", 45.0)],
            budget_line="a line that does not exist",
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("unknown budget line" in error for error in errors))

    def test_stale_waiver_is_rejected(self):
        # A waiver for a rule the laminate no longer breaks must be deleted,
        # not left to accumulate.
        item = self._schedule_with(
            [Ply("PW-C-193", 45.0), Ply("PW-C-193", 0.0),
             Ply("PW-C-193", 0.0), Ply("PW-C-193", 45.0)],
            waivers=(
                Waiver(
                    "max_contiguous_plies",
                    "a rationale long enough to satisfy the minimum length check",
                ),
            ),
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("outlived the rule break" in error for error in errors))

    def test_waiver_needs_a_written_rationale(self):
        item = replace(CS_200_DEPLOYABLE_BOOM, waivers=(Waiver("ten_percent_rule", "no"),))
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("written rationale" in error for error in errors))

    def test_waiver_naming_an_unknown_rule_is_rejected(self):
        item = replace(
            CS_200_DEPLOYABLE_BOOM,
            waivers=(
                Waiver("no_such_rule", "a rationale long enough to pass the length check"),
            ),
        )
        with patch.object(schedules, "SCHEDULES", (item,)):
            errors = validate_schedules()
        self.assertTrue(any("unknown rule" in error for error in errors))

    def test_ten_percent_rule_counts_empty_families(self):
        # The rule exists to catch a missing direction, so an orientation
        # family with zero thickness has to fail it rather than be skipped.
        item = self._schedule_with([Ply("UD-C-IM", 45.0), Ply("UD-C-IM", -45.0)])
        result = evaluate(item)
        rule = next(c for c in result["checks"] if c["name"] == "ten_percent_rule")
        self.assertFalse(rule["passed"])
        self.assertEqual(0.0, rule["actual"])

    def test_boom_waiver_is_live(self):
        # The deployable boom genuinely breaks the 10 % rule, and its waiver
        # is what keeps it legal.  If this stops being true the waiver is
        # stale and validate_schedules will say so.
        result = evaluate(CS_200_DEPLOYABLE_BOOM)
        rule = next(c for c in result["checks"] if c["name"] == "ten_percent_rule")
        self.assertTrue(rule["waived"])
        self.assertTrue(rule["passed"])
        self.assertLess(rule["actual"], TEN_PERCENT_RULE)


class LoadCaseTest(unittest.TestCase):
    def test_handling_moment_scales_with_span(self):
        self.assertAlmostEqual(
            2.0 * handling_moment_n(50.0), handling_moment_n(100.0), places=12
        )

    def test_handling_moment_refuses_a_non_positive_span(self):
        with self.assertRaises(ValueError):
            handling_moment_n(0.0)

    def test_retention_force_follows_the_p0_mass_budget(self):
        from aiur.p0 import baseline_p0_budget

        aircraft = sum(
            item.mass_kg_each
            for item in baseline_p0_budget()
            if item.name
            in {
                "Crazyflie 2.1 Brushless + guards",
                "Lighthouse positioning deck",
                "drone-side capture probe allocation",
            }
        )
        self.assertAlmostEqual(
            aircraft * 9.81 * schedules.RETENTION_LIMIT_LOAD_FACTOR,
            retention_force_n(),
            places=9,
        )

    def test_every_schedule_carries_a_cooldown_case(self):
        for item in SCHEDULES:
            names = {case.name for case in item.load_cases}
            self.assertIn("LC-COOL", names, item.part_id)

    def test_cooldown_case_is_evaluated_with_free_edges(self):
        # A part coming off its tool is unrestrained; evaluating the residual
        # stress state against a restrained edge would understate it.
        for item in SCHEDULES:
            for case in item.load_cases:
                if case.name == "LC-COOL":
                    self.assertEqual("free", case.edge)

    def test_retention_case_is_critical_and_the_others_are_not(self):
        critical = [case for case in CS_400_KEEPER_TINE.load_cases if case.critical]
        self.assertEqual(["LC-RETAIN"], [case.name for case in critical])

    def test_span_capacity_bounds_the_designed_support_pitch(self):
        for item in SCHEDULES:
            if item.support_pitch_mm is None:
                continue
            capacity = max_unsupported_span_mm(item.laminate(), edge=item.edge)
            self.assertLessEqual(item.support_pitch_mm, capacity, item.part_id)

    def test_span_capacity_is_where_the_strength_ratio_reaches_the_factor(self):
        laminate = schedule("CS-100").laminate()
        capacity = max_unsupported_span_mm(laminate, edge="cylindrical")
        at_capacity = laminate.response(
            m_per_mm=(handling_moment_n(capacity), 0.0, 0.0), edge="cylindrical"
        )
        self.assertAlmostEqual(1.5, at_capacity.first_ply_failure_ratio, delta=0.01)


class MassBudgetTest(unittest.TestCase):
    def test_every_part_is_inside_its_areal_mass_limit(self):
        for result in evaluate_all():
            check = next(c for c in result["checks"] if c["name"] == "areal_mass_g_m2")
            self.assertTrue(check["passed"], result["part_id"])

    def test_areal_limit_is_the_allocation_over_the_area(self):
        for item in SCHEDULES:
            self.assertAlmostEqual(
                item.mass_allocation_g / (item.area_m2 * item.quantity),
                item.max_areal_mass_g_m2,
                places=9,
            )

    def test_allocations_fit_inside_the_p0_budget_lines(self):
        for entry in mass_rollup():
            self.assertLessEqual(entry["allocated_g"], entry["budget_g"], entry["budget_line"])
            self.assertTrue(entry["within_allocation"], entry["budget_line"])

    def test_budget_lines_are_read_from_the_p0_model(self):
        self.assertAlmostEqual(0.180, budget_line_kg(schedules.DOCK_BUDGET_LINE), places=9)
        with self.assertRaises(KeyError):
            budget_line_kg("not a budget line")

    def test_part_mass_accounts_for_quantity(self):
        boom = schedule("CS-200")
        self.assertEqual(12, boom.quantity)
        self.assertAlmostEqual(
            boom.laminate().areal_mass_g_m2 * boom.area_m2 * 12,
            boom.part_mass_g(),
            places=6,
        )


class StowageTest(unittest.TestCase):
    def test_boom_stows_inside_its_strain_allowable(self):
        result = evaluate(CS_200_DEPLOYABLE_BOOM)
        stow = result["stowage"]
        self.assertIsNotNone(stow)
        self.assertGreaterEqual(stow["stow_radius_mm"], stow["minimum_radius_mm"])

    def test_only_the_deployable_carries_a_stow_requirement(self):
        stowed = [item.part_id for item in SCHEDULES if item.stow_radius_mm is not None]
        self.assertEqual(["CS-200"], stowed)


class SnapshotTest(unittest.TestCase):
    def test_snapshot_is_json_serialisable_and_valid(self):
        report = snapshot()
        json.dumps(report)
        self.assertTrue(report["valid"])
        self.assertEqual([], report["critical_failures"])

    def test_snapshot_records_which_cases_are_sizing(self):
        report = snapshot()
        sizing = {
            (result["part_id"], case["name"])
            for result in report["schedules"]
            for case in result["load_cases"]
            if case["sizing"]
        }
        # The two findings the module docstring claims: handling sizes the
        # throat cup, and cooldown sizes the rail.
        self.assertIn(("CS-100", "LC-HANDLE"), sizing)
        self.assertIn(("CS-300", "LC-COOL"), sizing)

    def test_evidence_grade_is_reported_as_a_design_study(self):
        for result in evaluate_all():
            self.assertTrue(
                result["evidence_grade"].startswith("trade study"), result["part_id"]
            )

    def test_main_returns_zero_when_the_registry_is_clean(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = schedules_main()
        self.assertEqual(0, code)
        json.loads(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
