"""Cure, distortion, tooling, constituent-content and quality-system checks.

These cover the process half of the composites discipline.  Several of the
tests assert *physics* rather than a stored number — a reaction that must
speed up with temperature, a conversion ceiling that must rise with the hold
temperature, a corner that must close rather than open on cooldown — so that
a sign error or a swapped constant is caught by the behaviour it produces
instead of by a value someone would have to re-derive to check.
"""

import contextlib
import io
import json
import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from aiur.composites import allowables, cure, doe, process, spc, springin, tooling, traveler
from aiur.composites.cure import (
    CURE_180_FAST,
    CURE_180_STANDARD,
    CureCycle,
    CureSegment,
    MIN_CURE_COMPLETENESS,
    QUALIFIED_CYCLE_IDS,
    acceptance,
    conversion_ceiling,
    evaluate_cycle,
    glass_transition_c,
    reaction_rate,
    simulate,
    temperature_for_conversion,
    validate_cycles,
    viscosity_pa_s,
)
from aiur.composites.materials import chemistry
from aiur.composites.schedules import schedule


class CureKineticsTest(unittest.TestCase):
    def setUp(self):
        self.chem = chemistry("epoxy-180C-toughened")

    def test_reaction_speeds_up_with_temperature(self):
        cold = reaction_rate(self.chem, 0.2, 120.0)
        hot = reaction_rate(self.chem, 0.2, 180.0)
        self.assertGreater(hot, cold)

    def test_reaction_stops_at_full_conversion(self):
        self.assertEqual(0.0, reaction_rate(self.chem, 1.0, 180.0))

    def test_reaction_stalls_past_the_conversion_ceiling(self):
        ceiling = conversion_ceiling(self.chem, 180.0)
        below = reaction_rate(self.chem, ceiling - 0.1, 180.0)
        above = reaction_rate(self.chem, ceiling + 0.1, 180.0)
        self.assertGreater(below, 10.0 * above)

    def test_conversion_ceiling_rises_with_temperature(self):
        self.assertLess(
            conversion_ceiling(self.chem, 120.0), conversion_ceiling(self.chem, 180.0)
        )

    def test_temperature_for_conversion_inverts_the_ceiling(self):
        temperature = temperature_for_conversion(self.chem, 0.90)
        self.assertAlmostEqual(0.90, conversion_ceiling(self.chem, temperature), places=9)

    def test_full_cure_needs_a_postcure_above_the_cure_temperature(self):
        # The finding that set the acceptance criteria: 0.90 conversion is
        # not reachable at a 180 degC hold.
        self.assertGreater(temperature_for_conversion(self.chem, 0.90), 180.0)

    def test_isothermal_hold_converges_to_its_ceiling(self):
        alpha = self.chem.initial_conversion
        for _ in range(int(6 * 3600 / 2)):
            alpha = min(alpha + reaction_rate(self.chem, alpha, 180.0) * 2.0, 1.0)
        self.assertLess(alpha, conversion_ceiling(self.chem, 180.0) + 0.08)
        self.assertGreater(alpha, conversion_ceiling(self.chem, 180.0))

    def test_glass_transition_rises_monotonically_with_cure(self):
        values = [glass_transition_c(self.chem, alpha) for alpha in (0.0, 0.3, 0.6, 0.9, 1.0)]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(self.chem.tg_uncured_c, values[0], places=9)
        self.assertAlmostEqual(self.chem.tg_full_c, values[-1], places=9)

    def test_viscosity_falls_with_temperature_and_rises_with_cure(self):
        cold = viscosity_pa_s(self.chem, 0.05, 80.0)
        hot = viscosity_pa_s(self.chem, 0.05, 140.0)
        self.assertLess(hot, cold)
        advanced = viscosity_pa_s(self.chem, 0.35, 140.0)
        self.assertGreater(advanced, hot)

    def test_gelled_resin_has_no_finite_viscosity(self):
        self.assertEqual(math.inf, viscosity_pa_s(self.chem, self.chem.gel_conversion, 150.0))


class CureCycleTest(unittest.TestCase):
    def test_qualified_cycles_pass_their_acceptance_criteria(self):
        self.assertEqual([], validate_cycles())
        for cycle_id in QUALIFIED_CYCLE_IDS:
            report = evaluate_cycle(cure.cycle(cycle_id))
            self.assertTrue(report["passed"], cycle_id)

    def test_fast_candidate_fails_on_thermal_lag(self):
        # The candidate is kept in the register because it is tempting. It
        # fails for the reason the cure model exists to expose: a 5 degC/min
        # ramp on a thermally massive tool means the dwell the part sees is
        # not the dwell the recipe describes.
        report = evaluate_cycle(CURE_180_FAST)
        self.assertFalse(report["passed"])
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("thermal_lag_k", failed)

    def test_air_profile_follows_the_segments(self):
        cycle = CURE_180_STANDARD
        self.assertAlmostEqual(20.0, cycle.air_temperature_c(0.0, 20.0), places=9)
        # 2 degC/min from 20 degC reaches 110 degC after 45 minutes.
        self.assertAlmostEqual(110.0, cycle.air_temperature_c(45.0, 20.0), places=6)
        # ...and holds there for the next hour.
        self.assertAlmostEqual(110.0, cycle.air_temperature_c(100.0, 20.0), places=6)

    def test_duration_matches_the_segment_arithmetic(self):
        cycle = CureCycle(
            cycle_id="TEST", name="test", chemistry="epoxy-180C-toughened",
            segments=(CureSegment(120.0, 2.0, 30.0), CureSegment(20.0, 5.0, 0.0)),
        )
        # 50 min up, 30 min hold, 20 min down.
        self.assertAlmostEqual(100.0, cycle.duration_min(20.0), places=6)

    def test_part_lags_the_oven_on_the_way_up(self):
        result = simulate(CURE_180_STANDARD, laminate_thickness_mm=1.6)
        self.assertGreater(result.max_thermal_lag_k, 0.0)

    def test_thin_laminate_barely_exotherms(self):
        result = simulate(CURE_180_STANDARD, laminate_thickness_mm=0.35)
        self.assertLess(result.max_exotherm_overshoot_k, 3.0)

    def test_thicker_laminate_exotherms_more(self):
        thin = simulate(CURE_180_STANDARD, laminate_thickness_mm=0.35)
        thick = simulate(CURE_180_STANDARD, laminate_thickness_mm=6.0)
        self.assertGreater(thick.max_exotherm_overshoot_k, thin.max_exotherm_overshoot_k)

    def test_heavier_tool_increases_the_lag(self):
        light = replace(CURE_180_STANDARD, tool_areal_heat_capacity_j_m2_k=1000.0)
        heavy = replace(CURE_180_STANDARD, tool_areal_heat_capacity_j_m2_k=40000.0)
        self.assertGreater(
            simulate(heavy, laminate_thickness_mm=1.0).max_thermal_lag_k,
            simulate(light, laminate_thickness_mm=1.0).max_thermal_lag_k,
        )

    def test_cooldown_is_not_counted_as_an_exotherm(self):
        # A thermally massive tool trails the falling oven air on cooldown.
        # That is the tool giving heat back, not the resin generating it.
        cycle = replace(CURE_180_STANDARD, tool_areal_heat_capacity_j_m2_k=40000.0)
        result = simulate(cycle, laminate_thickness_mm=0.35)
        self.assertLess(result.max_exotherm_overshoot_k, 5.0)

    def test_pressure_window_lies_between_flow_and_gel(self):
        result = simulate(CURE_180_STANDARD, laminate_thickness_mm=1.6)
        self.assertIsNotNone(result.pressure_window_min)
        opens, closes = result.pressure_window_min
        self.assertLess(opens, closes)
        self.assertAlmostEqual(closes, result.gel_time_min, places=6)

    def test_short_hold_fails_cure_completeness(self):
        starved = replace(
            CURE_180_STANDARD,
            cycle_id="TEST-SHORT",
            segments=(
                CureSegment(180.0, 2.0, 5.0),
                CureSegment(60.0, 2.5, 0.0),
            ),
        )
        result = simulate(starved, laminate_thickness_mm=1.6)
        checks = {check.name: check for check in acceptance(result, starved)}
        self.assertFalse(checks["cure_completeness"].passed)

    def test_cold_hold_fails_the_service_margin(self):
        # A hold too cold cures to its own ceiling and still cannot hold the
        # service temperature: completeness passes, service margin does not.
        cold = replace(
            CURE_180_STANDARD,
            cycle_id="TEST-COLD",
            segments=(CureSegment(90.0, 2.0, 600.0), CureSegment(40.0, 2.0, 0.0)),
            service_temperature_c=60.0,
        )
        result = simulate(cold, laminate_thickness_mm=1.6)
        checks = {check.name: check for check in acceptance(result, cold)}
        self.assertFalse(checks["service_margin_k"].passed)

    def test_every_acceptance_check_states_a_consequence(self):
        result = simulate(CURE_180_STANDARD, laminate_thickness_mm=1.6)
        for check in acceptance(result, CURE_180_STANDARD):
            self.assertTrue(check.consequence, check.name)

    def test_completeness_criterion_is_relative_to_the_ceiling(self):
        self.assertLess(MIN_CURE_COMPLETENESS, 1.0)
        report = evaluate_cycle(cure.cycle("CC-120-OVEN"))
        # The 120 degC system cures to about 0.73 and is accepted, because
        # 0.73 is essentially all its hold temperature can reach.
        self.assertLess(report["result"]["final_alpha"], 0.80)
        self.assertTrue(report["passed"])


class SpringInTest(unittest.TestCase):
    def setUp(self):
        self.laminate = schedule("CS-400").laminate()

    def test_both_mechanisms_close_the_corner(self):
        thermal, chemical, _ = springin.spring_in_deg(
            self.laminate, enclosed_angle_deg=90.0, cooldown_k=155.0, shrinkage_fraction=0.5
        )
        self.assertGreater(thermal, 0.0)
        self.assertGreater(chemical, 0.0)

    def test_magnitude_is_in_the_range_a_shop_sees(self):
        result = springin.evaluate(
            "CS-400", self.laminate, enclosed_angle_deg=90.0, cure_temperature_c=180.0
        )
        self.assertGreater(result.total_spring_in_deg, 0.2)
        self.assertLess(result.total_spring_in_deg, 2.0)

    def test_tool_is_cut_open_by_the_predicted_amount(self):
        result = springin.evaluate(
            "CS-400", self.laminate, enclosed_angle_deg=90.0, cure_temperature_c=180.0
        )
        self.assertGreater(result.compensated_tool_angle_deg, 90.0)
        self.assertAlmostEqual(
            90.0 + result.total_spring_in_deg, result.compensated_tool_angle_deg, places=6
        )

    def test_spring_in_scales_with_the_enclosed_angle(self):
        small = sum(
            springin.spring_in_deg(
                self.laminate, enclosed_angle_deg=45.0, cooldown_k=155.0, shrinkage_fraction=0.5
            )
        )
        large = sum(
            springin.spring_in_deg(
                self.laminate, enclosed_angle_deg=90.0, cooldown_k=155.0, shrinkage_fraction=0.5
            )
        )
        self.assertAlmostEqual(2.0, large / small, places=6)

    def test_lower_cure_temperature_reduces_but_does_not_remove_spring_in(self):
        hot = springin.evaluate(
            "CS-400", self.laminate, enclosed_angle_deg=90.0, cure_temperature_c=180.0
        )
        cold = springin.evaluate(
            "CS-400", self.laminate, enclosed_angle_deg=90.0, cure_temperature_c=120.0
        )
        self.assertLess(cold.total_spring_in_deg, hot.total_spring_in_deg)
        # Chemical shrinkage does not care what temperature it cured at.
        self.assertAlmostEqual(
            hot.delta_chemical_deg, cold.delta_chemical_deg, places=6
        )
        self.assertGreater(cold.total_spring_in_deg, 0.0)

    def test_through_thickness_expansion_dominates_in_plane(self):
        self.assertGreater(
            springin.through_thickness_cte(self.laminate),
            10.0 * springin.in_plane_cte(self.laminate),
        )

    def test_signed_cooldown_is_refused(self):
        with self.assertRaises(ValueError):
            springin.spring_in_deg(
                self.laminate, enclosed_angle_deg=90.0, cooldown_k=-155.0,
                shrinkage_fraction=0.5,
            )

    def test_measurement_closes_the_compensation_loop(self):
        update = springin.update_from_measurement(
            tool_angle_deg=90.75, measured_part_angle_deg=90.15, nominal_angle_deg=90.0
        )
        self.assertAlmostEqual(0.60, update["measured_spring_in_deg"], places=6)
        self.assertAlmostEqual(90.60, update["corrected_tool_angle_deg"], places=6)
        self.assertAlmostEqual(0.15, update["residual_error_deg"], places=6)

    def test_every_functional_corner_is_evaluated(self):
        report = springin.snapshot()
        self.assertTrue(report["corners"])
        for corner in report["corners"]:
            self.assertTrue(corner["consequence"])
            self.assertGreater(corner["total_spring_in_deg"], 0.0)


class ToolingTest(unittest.TestCase):
    def test_compensated_tool_puts_the_part_on_nominal(self):
        part_cte, tool_cte, cooldown = 2.6e-6, 23.6e-6, 155.0
        tool_length = tooling.compensated_tool_length_mm(
            300.0, part_cte_per_k=part_cte, tool_cte_per_k=tool_cte, cooldown_k=cooldown
        )
        # Forward-simulate the cooldown from the tool's dimension at cure.
        part_at_room = tool_length * (1.0 + tool_cte * cooldown) / (1.0 + part_cte * cooldown)
        self.assertAlmostEqual(300.0, part_at_room, places=9)

    def test_matched_cte_needs_no_compensation(self):
        factor = tooling.compensation_factor(
            part_cte_per_k=3.0e-6, tool_cte_per_k=3.0e-6, cooldown_k=155.0
        )
        self.assertAlmostEqual(1.0, factor, places=12)

    def test_aluminium_error_is_large_enough_to_matter(self):
        error = tooling.uncompensated_error_mm(
            300.0, part_cte_per_k=2.6e-6, tool_cte_per_k=23.6e-6
        )
        self.assertGreater(abs(error), 6.0 * tooling.IN_PLANE_TOLERANCE_MM)

    def test_heavier_tool_has_a_longer_time_constant(self):
        self.assertGreater(
            tooling.thermal_lag_time_constant_s(tooling.INVAR_36),
            tooling.thermal_lag_time_constant_s(tooling.CARBON_TOOL),
        )

    def test_tooling_board_is_screened_out_on_temperature(self):
        study = tooling.trade_study(part_cte_per_k=2.6e-6)
        screened = {row["name"] for row in study["screened_out"]}
        self.assertIn("epoxy tooling board", screened)
        self.assertNotIn(
            "epoxy tooling board", {row["name"] for row in study["candidates"]}
        )

    def test_low_durability_tool_is_screened_out_when_the_program_needs_more(self):
        study = tooling.trade_study(part_cte_per_k=2.6e-6, cure_temperature_c=120.0)
        with patch.object(tooling, "PROGRAM_CURE_DEMAND", 1000):
            demanding = tooling.trade_study(part_cte_per_k=2.6e-6, cure_temperature_c=120.0)
        self.assertIn(
            "carbon/epoxy tooling laminate", {row["name"] for row in study["candidates"]}
        )
        self.assertIn(
            "carbon/epoxy tooling laminate",
            {row["name"] for row in demanding["screened_out"]},
        )

    def test_selected_tool_is_the_highest_scoring_survivor(self):
        study = tooling.trade_study(part_cte_per_k=2.6e-6)
        best = max(study["candidates"], key=lambda row: row["total_score"])
        self.assertEqual(best["name"], study["selected"])

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(1.0, sum(tooling.TRADE_WEIGHTS.values()), places=12)

    def test_tool_heat_capacity_feeds_the_cure_model(self):
        # The link the tooling module claims: its areal heat capacity is the
        # number the cure model consumes.
        self.assertAlmostEqual(
            tooling.ALUMINIUM_6061.areal_heat_capacity_j_m2_k(),
            cure.ALUMINIUM_TOOL_6MM_J_M2_K,
            places=6,
        )


class ConstituentContentTest(unittest.TestCase):
    def test_fibre_volume_fraction_matches_the_hand_calculation(self):
        # 8 plies of 193 gsm at 1.76 g/cm^3 over 1.6 mm.
        vf = process.fibre_volume_fraction(
            ply_count=8, fibre_areal_weight_gsm=193.0, thickness_mm=1.6,
            fibre_density_g_cm3=1.76,
        )
        self.assertAlmostEqual((8 * 193.0) / (1.76e6) / 1.6e-3, vf, places=9)

    def test_thicker_panel_means_less_fibre(self):
        thin = process.fibre_volume_fraction(
            ply_count=8, fibre_areal_weight_gsm=193.0, thickness_mm=1.55,
            fibre_density_g_cm3=1.76,
        )
        thick = process.fibre_volume_fraction(
            ply_count=8, fibre_areal_weight_gsm=193.0, thickness_mm=1.75,
            fibre_density_g_cm3=1.76,
        )
        self.assertGreater(thin, thick)

    def test_void_free_panel_reports_no_voids(self):
        theoretical = process.theoretical_density_g_cm3(
            fibre_volume_fraction=0.55, fibre_density_g_cm3=1.76, resin_density_g_cm3=1.28
        )
        self.assertAlmostEqual(
            0.0,
            process.void_fraction(
                measured_density_g_cm3=theoretical, theoretical_density_g_cm3=theoretical
            ),
            places=12,
        )

    def test_lighter_panel_reports_voids(self):
        voids = process.void_fraction(
            measured_density_g_cm3=1.52, theoretical_density_g_cm3=1.544
        )
        self.assertAlmostEqual((1.544 - 1.52) / 1.544, voids, places=9)
        self.assertGreater(voids, 0.0)

    def test_digestion_returns_the_resin_mass_fraction(self):
        self.assertAlmostEqual(
            0.35,
            process.resin_mass_fraction_from_digestion(
                specimen_mass_g=10.0, residue_fibre_mass_g=6.5
            ),
            places=9,
        )

    def test_immersion_density_uses_the_fluid_density(self):
        density = process.density_from_immersion(
            dry_mass_g=10.0, immersed_mass_g=3.5, fluid_density_g_cm3=0.9970
        )
        self.assertAlmostEqual(10.0 * 0.9970 / 6.5, density, places=9)

    def test_impossible_immersion_measurement_is_refused(self):
        with self.assertRaises(ValueError):
            process.density_from_immersion(dry_mass_g=5.0, immersed_mass_g=6.0)

    def test_debulk_removes_air_with_diminishing_returns(self):
        steps = [process.entrapped_air_after_debulks(n) for n in range(5)]
        self.assertEqual(steps, sorted(steps, reverse=True))
        first_gain = steps[0] - steps[1]
        third_gain = steps[2] - steps[3]
        self.assertGreater(first_gain, 4.0 * third_gain)

    def test_debulking_never_reaches_zero(self):
        self.assertGreater(process.entrapped_air_after_debulks(50), 0.0)
        self.assertAlmostEqual(
            process.DEBULK_AIR_FLOOR, process.entrapped_air_after_debulks(50), places=6
        )

    def test_critical_parts_need_more_debulks_than_general(self):
        self.assertGreaterEqual(
            process.required_debulk_cycles(process.MAX_VOID_FRACTION_CRITICAL),
            process.required_debulk_cycles(process.MAX_VOID_FRACTION_GENERAL),
        )

    def test_debulk_schedule_starts_at_the_first_ply_and_ends_at_the_last(self):
        points = process.debulk_schedule(8, plies_per_debulk=3)
        self.assertEqual(1, points[0])
        self.assertEqual(8, points[-1])
        self.assertEqual(sorted(set(points)), list(points))

    def test_panel_acceptance_uses_the_tighter_limit_on_critical_parts(self):
        general = replace(process.EXAMPLE_PANEL, part_id="CS-100")
        self.assertEqual(
            process.MAX_VOID_FRACTION_CRITICAL,
            process.evaluate_panel(process.EXAMPLE_PANEL).void_limit,
        )
        self.assertEqual(
            process.MAX_VOID_FRACTION_GENERAL, process.evaluate_panel(general).void_limit
        )

    def test_porous_panel_is_rejected(self):
        porous = replace(process.EXAMPLE_PANEL, measured_density_g_cm3=1.45)
        result = process.evaluate_panel(porous)
        self.assertFalse(result.accepted)
        failed = {check["name"] for check in result.checks if not check["passed"]}
        self.assertIn("void_fraction", failed)

    def test_negative_porosity_is_reported_as_an_input_problem(self):
        dense = replace(process.EXAMPLE_PANEL, measured_density_g_cm3=1.70)
        result = process.evaluate_panel(dense)
        failed = {check["name"] for check in result.checks if not check["passed"]}
        self.assertIn("void_fraction_not_negative", failed)

    def test_thick_panel_is_flagged_and_its_stiffness_knockdown_reported(self):
        thick = replace(process.EXAMPLE_PANEL, measured_thickness_mm=1.95)
        result = process.evaluate_panel(thick)
        failed = {check["name"] for check in result.checks if not check["passed"]}
        self.assertIn("cured_ply_thickness_mm", failed)
        self.assertLess(result.stiffness_ratio_vs_nominal, 1.0)

    def test_example_panel_is_accepted(self):
        self.assertTrue(process.evaluate_panel(process.EXAMPLE_PANEL).accepted)


class TravelerTest(unittest.TestCase):
    def test_definition_is_valid(self):
        self.assertEqual([], traveler.validate_traveler_definition())

    def test_layup_verification_is_a_hold_point_with_a_reason(self):
        step = next(s for s in traveler.TRAVELER_STEPS if s.step_id == "OP-35")
        self.assertTrue(step.hold_point)
        self.assertIn("unverifiable", step.hold_reason)

    def test_hold_point_without_a_reason_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            traveler.TravelerStep(
                "OP-99", traveler.StepType.INSPECTION, "t", "i", "PS-100",
                hold_point=True, records=("x",),
            )

    def _clean_record(self, **overrides):
        base = dict(
            serial="TEST-SN001",
            part_id="CS-400",
            lot_id="LOT-1",
            roll_id="R-1",
            cumulative_out_time_h=100.0,
            thaw_time_h=12.0,
            cure_cycle_id="CC-180-STD",
            steps=tuple(
                traveler.StepRecord(
                    step.step_id,
                    operator="A. Operator",
                    inspector="B. Inspector" if step.hold_point else "",
                    values={name: "recorded" for name in step.records},
                )
                for step in traveler.TRAVELER_STEPS
            ),
        )
        base.update(overrides)
        return traveler.TravelerRecord(**base)

    def test_clean_traveler_is_accepted(self):
        findings = traveler.evaluate_traveler(self._clean_record())
        self.assertEqual([], findings)
        self.assertEqual("accept", traveler.disposition(findings))

    def test_expired_out_time_rejects_the_part(self):
        record = self._clean_record(cumulative_out_time_h=300.0)
        findings = traveler.evaluate_traveler(record)
        self.assertIn("NCR-OUTTIME", {finding.code for finding in findings})
        self.assertEqual("reject", traveler.disposition(findings))

    def test_out_time_warning_does_not_reject(self):
        record = self._clean_record(cumulative_out_time_h=210.0)
        findings = traveler.evaluate_traveler(record)
        self.assertEqual({"NCR-OUTTIME-WARN"}, {finding.code for finding in findings})
        self.assertEqual("use-as-is pending review", traveler.disposition(findings))

    def test_short_thaw_rejects_the_part(self):
        record = self._clean_record(thaw_time_h=2.0)
        codes = {finding.code for finding in traveler.evaluate_traveler(record)}
        self.assertIn("NCR-THAW", codes)

    def test_missing_traceability_rejects_the_part(self):
        record = self._clean_record(lot_id="")
        codes = {finding.code for finding in traveler.evaluate_traveler(record)}
        self.assertIn("NCR-TRACE", codes)

    def test_self_signed_hold_point_rejects_the_part(self):
        steps = tuple(
            replace(step, inspector="A. Operator") if step.step_id == "OP-35" else step
            for step in self._clean_record().steps
        )
        codes = {
            finding.code
            for finding in traveler.evaluate_traveler(self._clean_record(steps=steps))
        }
        self.assertIn("NCR-HOLD-SELF", codes)

    def test_unsigned_hold_point_rejects_the_part(self):
        steps = tuple(
            replace(step, inspector="") if step.step_id == "OP-40" else step
            for step in self._clean_record().steps
        )
        codes = {
            finding.code
            for finding in traveler.evaluate_traveler(self._clean_record(steps=steps))
        }
        self.assertIn("NCR-HOLD", codes)

    def test_missing_step_rejects_the_part(self):
        steps = tuple(
            step for step in self._clean_record().steps if step.step_id != "OP-50"
        )
        codes = {
            finding.code
            for finding in traveler.evaluate_traveler(self._clean_record(steps=steps))
        }
        self.assertIn("NCR-INCOMPLETE", codes)

    def test_out_of_sequence_signing_rejects_the_part(self):
        original = list(self._clean_record().steps)
        original[2], original[5] = original[5], original[2]
        codes = {
            finding.code
            for finding in traveler.evaluate_traveler(self._clean_record(steps=tuple(original)))
        }
        self.assertIn("NCR-SEQUENCE", codes)

    def test_missing_record_field_is_a_minor_finding(self):
        steps = tuple(
            replace(step, values={}) if step.step_id == "OP-30" else step
            for step in self._clean_record().steps
        )
        findings = traveler.evaluate_traveler(self._clean_record(steps=steps))
        record_findings = [f for f in findings if f.code == "NCR-RECORD"]
        self.assertTrue(record_findings)
        self.assertFalse(record_findings[0].critical)

    def test_example_record_is_rejected_for_the_stated_reason(self):
        report = traveler.snapshot()
        self.assertEqual("reject", report["example_evaluation"]["disposition"])


class TravelerTemplateTest(unittest.TestCase):
    """The shop-floor template is generated from the executable definition.

    A traveler CSV that has drifted from the step list is worse than no
    template: it is a document the shop trusts and the evaluator rejects.
    """

    TEMPLATE = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "hardware"
        / "composites"
        / "traveler-template.csv"
    )

    def test_template_exists_and_lists_every_step_in_order(self):
        lines = self.TEMPLATE.read_text().strip().splitlines()
        self.assertEqual(len(traveler.TRAVELER_STEPS) + 1, len(lines))
        step_ids = [line.split(",", 1)[0] for line in lines[1:]]
        self.assertEqual([step.step_id for step in traveler.TRAVELER_STEPS], step_ids)

    def test_template_marks_the_hold_points(self):
        rows = {
            line.split(",")[0]: line
            for line in self.TEMPLATE.read_text().strip().splitlines()[1:]
        }
        for step in traveler.TRAVELER_STEPS:
            self.assertEqual(step.hold_point, "HOLD" in rows[step.step_id], step.step_id)

    def test_template_carries_every_required_record_field(self):
        text = self.TEMPLATE.read_text()
        for step in traveler.TRAVELER_STEPS:
            for name in step.records:
                self.assertIn(name, text, f"{step.step_id}: {name}")


class AllowablesTest(unittest.TestCase):
    def test_tolerance_factors_match_published_tables(self):
        # CMH-17 normal one-sided factors; the closed form used here sits
        # slightly below the exact values, which the module states.
        for n, expected_b in ((10, 2.355), (20, 1.926), (30, 1.777), (100, 1.527)):
            self.assertAlmostEqual(expected_b, allowables.b_basis_factor(n), delta=0.04)
        for n, expected_a in ((10, 3.981), (30, 3.064), (100, 2.684)):
            self.assertAlmostEqual(expected_a, allowables.a_basis_factor(n), delta=0.05)

    def test_factors_shrink_as_the_sample_grows(self):
        factors = [allowables.b_basis_factor(n) for n in (4, 10, 30, 100)]
        self.assertEqual(factors, sorted(factors, reverse=True))

    def test_a_basis_is_always_more_conservative_than_b_basis(self):
        for n in (4, 10, 30, 100):
            self.assertGreater(allowables.a_basis_factor(n), allowables.b_basis_factor(n))

    def test_tiny_sample_is_refused(self):
        with self.assertRaises(ValueError):
            allowables.b_basis_factor(3)

    def test_basis_value_lies_below_the_mean(self):
        values = (742.0, 768.0, 715.0, 759.0, 733.0, 751.0)
        b_value = allowables.basis_value(values, basis="B")
        a_value = allowables.basis_value(values, basis="A")
        self.assertLess(b_value, allowables.mean(values))
        self.assertLess(a_value, b_value)

    def test_scatter_drives_coupon_count(self):
        tight = allowables.coupons_required(coefficient_of_variation=0.04)
        loose = allowables.coupons_required(coefficient_of_variation=0.10)
        self.assertLess(tight, loose)

    def test_single_lot_data_does_not_qualify_as_a_basis_value(self):
        coupons = allowables.CouponSet(
            "PW-C-193", "tension 0", "rtd", (742.0, 768.0, 715.0, 759.0, 733.0, 751.0), lots=1
        )
        result = allowables.evaluate_coupon_set(coupons)
        self.assertFalse(result.qualifies_as_basis_value)
        self.assertTrue(any("lot" in warning for warning in result.warnings))

    def test_high_scatter_is_reported_as_a_process_problem(self):
        coupons = allowables.CouponSet(
            "PW-C-193", "tension 0", "rtd",
            (742.0, 900.0, 615.0, 810.0, 640.0, 830.0), lots=3,
        )
        result = allowables.evaluate_coupon_set(coupons)
        self.assertTrue(any("process-driven" in warning for warning in result.warnings))

    def test_hot_wet_knockdown_reduces_the_design_allowable(self):
        values = (742.0, 768.0, 715.0, 759.0, 733.0, 751.0)
        dry = allowables.evaluate_coupon_set(
            allowables.CouponSet("PW-C-193", "sbs", "rtd", values, lots=3)
        )
        wet = allowables.evaluate_coupon_set(
            allowables.CouponSet(
                "PW-C-193", "sbs", "etw_matrix_dominated", values, lots=3
            )
        )
        self.assertLess(wet.design_allowable_mpa, dry.design_allowable_mpa)

    def test_program_holds_no_measured_allowables(self):
        self.assertEqual(0, allowables.program_status()["measured_allowables"])

    def test_coupon_plan_covers_the_critical_properties(self):
        properties = {coupon.property_name for coupon in allowables.COUPON_PLAN}
        self.assertIn("in-plane shear", properties)
        self.assertIn("short-beam strength", properties)
        self.assertIn("compression 0", properties)


class ProcessCapabilityTest(unittest.TestCase):
    def test_centred_process_has_cp_equal_to_cpk(self):
        values = [10.0 - 0.1, 10.0, 10.0 + 0.1, 10.0, 10.0 - 0.05, 10.0 + 0.05]
        result = spc.capability(
            values, characteristic="test", lower_spec=9.0, upper_spec=11.0
        )
        self.assertAlmostEqual(result.cp, result.cpk, places=6)

    def test_off_centre_process_is_diagnosed(self):
        # Spread comfortably inside a 9-11 specification, mean sitting well
        # up towards the upper limit: the half-day-of-adjustment case.
        values = [10.30, 10.70, 10.50, 10.50, 10.35, 10.65]
        result = spc.capability(
            values, characteristic="test", lower_spec=9.0, upper_spec=11.0
        )
        self.assertGreater(result.cp, result.cpk)
        self.assertIn("off-centre", result.diagnosis)

    def test_variable_process_is_diagnosed_differently(self):
        values = [9.2, 10.8, 10.1, 9.6, 10.6, 9.4]
        result = spc.capability(
            values, characteristic="test", lower_spec=9.0, upper_spec=11.0
        )
        self.assertLess(result.cp, spc.MIN_CPK)
        self.assertIn("too variable", result.diagnosis)

    def test_capability_of_one_implies_a_measurable_defect_rate(self):
        # Cpk = 1 is three sigma each side: about 0.27 % outside.
        sigma = 1.0 / 3.0
        values = [-sigma, sigma, 0.0, -sigma, sigma, 0.0]
        result = spc.capability(
            values, characteristic="test", lower_spec=-1.0, upper_spec=1.0
        )
        self.assertGreater(result.expected_defect_rate, 0.0)

    def test_capability_needs_a_specification_limit(self):
        with self.assertRaises(ValueError):
            spc.capability([1.0, 2.0], characteristic="test")

    def test_control_chart_limits_bracket_the_grand_mean(self):
        chart = spc.control_chart(spc.EXAMPLE_CPT_SUBGROUPS, characteristic="test")
        self.assertLess(chart.xbar_lower, chart.grand_mean)
        self.assertGreater(chart.xbar_upper, chart.grand_mean)
        self.assertTrue(chart.in_control)

    def test_control_chart_detects_a_shifted_subgroup(self):
        subgroups = list(spc.EXAMPLE_CPT_SUBGROUPS)
        subgroups.append((0.260, 0.262, 0.259, 0.261))
        chart = spc.control_chart(subgroups, characteristic="test")
        self.assertFalse(chart.in_control)
        self.assertIn(len(subgroups) - 1, chart.out_of_control_subgroups)

    def test_control_chart_refuses_ragged_subgroups(self):
        with self.assertRaises(ValueError):
            spc.control_chart([(1.0, 2.0), (1.0, 2.0, 3.0)], characteristic="test")

    def test_rolled_throughput_yield_is_below_every_step(self):
        rty = spc.rolled_throughput_yield(spc.EXAMPLE_CELL)
        for step in spc.EXAMPLE_CELL:
            self.assertLess(rty, step.first_pass_yield)

    def test_yield_report_exposes_hidden_rework(self):
        report = spc.yield_report(spc.EXAMPLE_CELL)
        self.assertGreater(report["hidden_rework_fraction"], 0.0)
        self.assertEqual("layup and debulk", report["worst_step"]["name"])


class ExperimentPlanTest(unittest.TestCase):
    def test_plan_is_valid(self):
        self.assertEqual([], doe.validate_experiments())

    def test_every_experiment_names_the_assumption_it_replaces(self):
        for experiment in doe.EXPERIMENTS:
            self.assertTrue(experiment.replaces)

    def test_design_matrix_is_a_full_factorial(self):
        design = doe.design_matrix(3)
        self.assertEqual(8, len(design))
        self.assertEqual(8, len(set(design)))
        for row in design:
            self.assertTrue(all(value in (-1, 1) for value in row))

    def test_design_matrix_is_balanced(self):
        design = doe.design_matrix(3, replicates=2)
        for column in range(3):
            self.assertEqual(0, sum(row[column] for row in design))

    def test_run_order_is_a_reproducible_permutation(self):
        first = doe.run_order(16, seed=7)
        second = doe.run_order(16, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(sorted(first), list(range(16)))
        self.assertNotEqual(first, tuple(range(16)))

    def test_different_seeds_give_different_orders(self):
        self.assertNotEqual(doe.run_order(16, seed=1), doe.run_order(16, seed=2))

    def test_main_effects_recover_a_synthetic_response(self):
        design = doe.design_matrix(3)
        responses = [
            100.0 + 10.0 * row[0] + 4.0 * row[1] + 2.0 * row[0] * row[1] for row in design
        ]
        effects = doe.main_effects(design, responses)
        self.assertAlmostEqual(20.0, effects[0], places=9)
        self.assertAlmostEqual(8.0, effects[1], places=9)
        self.assertAlmostEqual(0.0, effects[2], places=9)

    def test_interaction_effect_recovers_a_synthetic_interaction(self):
        design = doe.design_matrix(3)
        responses = [
            100.0 + 10.0 * row[0] + 4.0 * row[1] + 2.0 * row[0] * row[1] for row in design
        ]
        self.assertAlmostEqual(4.0, doe.interaction_effect(design, responses, 0, 1), places=9)
        self.assertAlmostEqual(0.0, doe.interaction_effect(design, responses, 0, 2), places=9)

    def test_minimum_detectable_effect_falls_with_more_runs(self):
        few = doe.minimum_detectable_effect(sigma=1.0, runs=8)
        many = doe.minimum_detectable_effect(sigma=1.0, runs=32)
        self.assertAlmostEqual(2.0, few / many, places=9)

    def test_run_sheet_covers_every_run(self):
        for experiment in doe.EXPERIMENTS:
            sheet = doe.plan(experiment)
            self.assertEqual(sheet["runs"], len(sheet["run_sheet"]))
            self.assertEqual(
                list(range(1, sheet["runs"] + 1)),
                [row["run_order"] for row in sheet["run_sheet"]],
            )

    def test_centre_points_are_coded_at_zero(self):
        sheet = doe.plan(doe.DOE_2)
        centres = [row for row in sheet["run_sheet"] if all(v == 0 for v in row["coded"])]
        self.assertEqual(doe.DOE_2.centre_points, len(centres))

    def test_single_replicate_experiment_is_rejected(self):
        weak = replace(doe.DOE_4, replicates=1)
        with patch.object(doe, "EXPERIMENTS", (weak,)):
            errors = doe.validate_experiments()
        self.assertTrue(any("replicates" in error for error in errors))


class PackageGateTest(unittest.TestCase):
    def test_composites_gate_passes_and_is_serialisable(self):
        from aiur.composites.__main__ import main as composites_main

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = composites_main()
        self.assertEqual(0, code)
        report = json.loads(buffer.getvalue())
        self.assertTrue(report["valid"])
        self.assertEqual([], report["errors"])
        self.assertEqual([], report["critical_failures"])

    def test_gate_reports_the_evidence_state_honestly(self):
        from aiur.composites.__main__ import snapshot

        state = snapshot()["evidence_state"]
        self.assertEqual(0, state["measured_allowables"])
        self.assertIn("design study", state["statement"])


if __name__ == "__main__":
    unittest.main()
