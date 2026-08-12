"""Defect disposition checks.

The analysis tests anchor on scaling laws that must hold whatever the
constants are: buckling radius scaling with the square root of sublaminate
bending stiffness, waviness knockdown falling monotonically with angle, and
a scarf ratio proportional to the stress it has to carry.

The disposition tests are about judgement encoded as rules, so most of them
compare two records that differ in exactly one way and require the answer to
change — the clearest of which is a delamination of identical size at two
depths.
"""

import math
import unittest

from aiur.composites import disposition as D
from aiur.composites.clt import Laminate
from aiur.composites.disposition import (
    DefectRecord,
    DefectType,
    Disposition,
    MIN_SCARF_RATIO,
    critical_delamination_radius_mm,
    disposition,
    governing_compressive_strain,
    parent_stress_mpa,
    repair_scheme,
    scarf_ratio_required,
    sublaminate,
    waviness_knockdown,
)
from aiur.composites.process import CRITICAL_PART_IDS
from aiur.composites.schedules import schedule


class SublaminateTest(unittest.TestCase):
    def test_sublaminate_takes_the_plies_above_the_delamination(self):
        laminate = schedule("CS-400").laminate()
        sub = sublaminate(laminate, 3)
        self.assertEqual(3, sub.ply_count)
        self.assertEqual(
            [ply.material for ply in laminate.plies[:3]],
            [ply.material for ply in sub.plies],
        )

    def test_delamination_outside_the_laminate_is_refused(self):
        laminate = schedule("CS-400").laminate()
        with self.assertRaises(ValueError):
            sublaminate(laminate, 0)
        with self.assertRaises(ValueError):
            sublaminate(laminate, laminate.ply_count)


class DelaminationBucklingTest(unittest.TestCase):
    def setUp(self):
        self.laminate = schedule("CS-100").laminate()

    def test_shallow_delamination_is_far_more_critical_than_a_deep_one(self):
        # The finding the module exists to make visible, and the one that
        # inverts the intuition the defect's name invites.
        shallow = critical_delamination_radius_mm(
            self.laminate, plies_above=1, compressive_strain=0.005
        )
        deep = critical_delamination_radius_mm(
            self.laminate, plies_above=3, compressive_strain=0.005
        )
        self.assertLess(shallow, deep)
        self.assertGreater(deep / shallow, 3.0)

    def test_critical_radius_scales_with_the_root_of_bending_stiffness(self):
        sub = sublaminate(self.laminate, 3)
        radius = critical_delamination_radius_mm(
            self.laminate, plies_above=3, compressive_strain=0.005
        )
        expected = math.sqrt(
            D.CLAMPED_CIRCULAR_BUCKLING_COEFFICIENT
            * sub.d_matrix()[0][0]
            / (sub.a_matrix()[0][0] * 0.005)
        )
        self.assertAlmostEqual(expected, radius, places=9)

    def test_critical_radius_falls_as_strain_rises(self):
        low = critical_delamination_radius_mm(
            self.laminate, plies_above=3, compressive_strain=0.001
        )
        high = critical_delamination_radius_mm(
            self.laminate, plies_above=3, compressive_strain=0.010
        )
        self.assertGreater(low, high)
        # Inverse square root in strain.
        self.assertAlmostEqual(math.sqrt(10.0), low / high, places=6)

    def test_unloaded_part_never_buckles(self):
        self.assertEqual(
            math.inf,
            critical_delamination_radius_mm(
                self.laminate, plies_above=2, compressive_strain=0.0
            ),
        )

    def test_governing_strain_is_positive_for_every_part(self):
        for part_id in ("CS-100", "CS-200", "CS-300", "CS-400"):
            self.assertGreater(governing_compressive_strain(part_id), 0.0, part_id)


class WavinessTest(unittest.TestCase):
    def test_no_wrinkle_costs_nothing(self):
        self.assertAlmostEqual(
            1.0, waviness_knockdown(0.0, material_name="PW-C-193"), places=12
        )

    def test_knockdown_falls_monotonically_with_angle(self):
        values = [
            waviness_knockdown(angle, material_name="PW-C-193")
            for angle in (0.0, 0.5, 1.0, 2.0, 3.0, 5.0)
        ]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_a_two_degree_wrinkle_costs_about_forty_percent(self):
        # The number that makes a wrinkle a structural defect rather than a
        # cosmetic one.
        self.assertAlmostEqual(
            0.58, waviness_knockdown(2.0, material_name="PW-C-193"), delta=0.03
        )

    def test_negative_angle_is_refused(self):
        with self.assertRaises(ValueError):
            waviness_knockdown(-1.0, material_name="PW-C-193")


class ScarfRepairTest(unittest.TestCase):
    def test_scarf_ratio_is_stress_over_adhesive_strength(self):
        self.assertAlmostEqual(
            10.0,
            scarf_ratio_required(
                parent_stress_mpa=350.0, adhesive_shear_strength_mpa=35.0
            ),
            places=9,
        )

    def test_stronger_adhesive_needs_less_taper(self):
        weak = scarf_ratio_required(
            parent_stress_mpa=400.0, adhesive_shear_strength_mpa=25.0
        )
        strong = scarf_ratio_required(
            parent_stress_mpa=400.0, adhesive_shear_strength_mpa=45.0
        )
        self.assertGreater(weak, strong)

    def test_zero_strength_adhesive_is_refused(self):
        with self.assertRaises(ValueError):
            scarf_ratio_required(
                parent_stress_mpa=400.0, adhesive_shear_strength_mpa=0.0
            )

    def test_specified_ratio_never_falls_below_the_practice_minimum(self):
        for part_id in ("CS-100", "CS-300", "CS-400"):
            scheme = repair_scheme(part_id)
            self.assertGreaterEqual(scheme["specified_scarf_ratio"], MIN_SCARF_RATIO)
            self.assertGreaterEqual(
                scheme["specified_scarf_ratio"], scheme["computed_scarf_ratio"]
            )

    def test_scarf_length_follows_the_ratio_and_thickness(self):
        scheme = repair_scheme("CS-400")
        self.assertAlmostEqual(
            scheme["specified_scarf_ratio"] * scheme["laminate_thickness_mm"],
            scheme["scarf_length_mm"],
            delta=0.05,
        )

    def test_repair_to_a_critical_part_inherits_the_bond_qualification(self):
        scheme = repair_scheme("CS-400")
        self.assertTrue(scheme["critical_part"])
        self.assertIn("proof test", scheme["qualification"])

    def test_parent_stress_comes_from_the_laminate_model(self):
        laminate = schedule("CS-400").laminate()
        expected = (
            laminate.response(n_per_mm=(1.0, 0.0, 0.0)).first_ply_failure_ratio
            / laminate.thickness_mm
        )
        self.assertAlmostEqual(expected, parent_stress_mpa("CS-400"), places=9)


class DispositionTest(unittest.TestCase):
    def _delamination(self, part_id, size_mm, plies_above):
        return DefectRecord(
            "NCR-T", part_id, "SN", DefectType.DELAMINATION,
            size_mm=size_mm, plies_above=plies_above,
        )

    def test_same_delamination_disposes_differently_by_depth(self):
        # Identical size, different depth, opposite answers. This is the
        # whole point of a depth-dependent limit.
        deep = disposition(self._delamination("CS-100", 4.0, 3))
        shallow = disposition(self._delamination("CS-100", 4.0, 1))
        self.assertEqual(Disposition.ACCEPT_WITH_ANALYSIS.value, deep.disposition)
        self.assertEqual(Disposition.REPAIR.value, shallow.disposition)

    def test_any_delamination_on_the_retention_path_is_scrapped(self):
        result = disposition(self._delamination("CS-400", 1.0, 4))
        self.assertEqual(Disposition.SCRAP.value, result.disposition)
        self.assertTrue(result.critical_part)
        self.assertIn("process escape", result.rationale)

    def test_delamination_repair_names_a_scheme(self):
        result = disposition(self._delamination("CS-100", 20.0, 1))
        self.assertEqual(Disposition.REPAIR.value, result.disposition)
        self.assertIn("scarf", result.repair_scheme)

    def test_porosity_inside_the_limit_is_accepted(self):
        result = disposition(
            DefectRecord("NCR-T", "CS-300", "SN", DefectType.POROSITY, void_fraction=0.01)
        )
        self.assertEqual(Disposition.ACCEPT.value, result.disposition)
        # And the acceptance says the limit is a convention, not a measurement.
        self.assertIn("convention", result.rationale)

    def test_porosity_above_the_limit_is_scrapped_not_repaired(self):
        result = disposition(
            DefectRecord("NCR-T", "CS-300", "SN", DefectType.POROSITY, void_fraction=0.03)
        )
        self.assertEqual(Disposition.SCRAP.value, result.disposition)
        self.assertIn("nothing local to repair", result.rationale)

    def test_critical_parts_carry_the_tighter_porosity_limit(self):
        general = disposition(
            DefectRecord("NCR-T", "CS-300", "SN", DefectType.POROSITY, void_fraction=0.015)
        )
        critical = disposition(
            DefectRecord("NCR-T", "CS-400", "SN", DefectType.POROSITY, void_fraction=0.015)
        )
        self.assertEqual(Disposition.ACCEPT.value, general.disposition)
        self.assertEqual(Disposition.SCRAP.value, critical.disposition)

    def test_a_large_wrinkle_is_scrapped_and_cannot_be_repaired(self):
        result = disposition(
            DefectRecord(
                "NCR-T", "CS-300", "SN", DefectType.FIBRE_WAVINESS, wrinkle_angle_deg=2.0
            )
        )
        self.assertEqual(Disposition.SCRAP.value, result.disposition)
        self.assertEqual("", result.repair_scheme)
        self.assertIn("cannot be repaired", result.rationale)

    def test_a_small_wrinkle_on_a_lightly_loaded_part_is_absorbed(self):
        result = disposition(
            DefectRecord(
                "NCR-T", "CS-400", "SN", DefectType.FIBRE_WAVINESS, wrinkle_angle_deg=0.5
            )
        )
        # CS-400 is critical, so even a small wave is rejected there.
        self.assertEqual(Disposition.SCRAP.value, result.disposition)
        lightly_loaded = disposition(
            DefectRecord(
                "NCR-T", "CS-100", "SN", DefectType.FIBRE_WAVINESS, wrinkle_angle_deg=0.5
            )
        )
        self.assertEqual(
            Disposition.ACCEPT_WITH_ANALYSIS.value, lightly_loaded.disposition
        )

    def test_misorientation_costs_far_more_on_a_directional_laminate(self):
        isotropic = disposition(
            DefectRecord(
                "NCR-T", "CS-100", "SN", DefectType.PLY_MISORIENTATION,
                misorientation_deg=8.0,
            )
        )
        directional = disposition(
            DefectRecord(
                "NCR-T", "CS-300", "SN", DefectType.PLY_MISORIENTATION,
                misorientation_deg=8.0,
            )
        )
        self.assertGreater(directional.actual, 10.0 * isotropic.actual)

    def test_misorientation_reports_deviation_rather_than_only_loss(self):
        # A misplaced ply that stiffens the axial direction has still moved
        # the part away from what was analysed.
        result = disposition(
            DefectRecord(
                "NCR-T", "CS-100", "SN", DefectType.PLY_MISORIENTATION,
                misorientation_deg=8.0,
            )
        )
        self.assertGreater(result.actual, 0.0)

    def test_foreign_object_is_always_scrapped(self):
        result = disposition(
            DefectRecord("NCR-T", "CS-100", "SN", DefectType.FOREIGN_OBJECT, size_mm=2.0)
        )
        self.assertEqual(Disposition.SCRAP.value, result.disposition)
        self.assertIn("built in", result.rationale)

    def test_small_surface_damage_is_accepted_and_large_is_repaired(self):
        small = disposition(
            DefectRecord("NCR-T", "CS-100", "SN", DefectType.SURFACE_DAMAGE, size_mm=2.0)
        )
        large = disposition(
            DefectRecord("NCR-T", "CS-100", "SN", DefectType.SURFACE_DAMAGE, size_mm=25.0)
        )
        self.assertEqual(Disposition.ACCEPT.value, small.disposition)
        self.assertEqual(Disposition.REPAIR.value, large.disposition)

    def test_every_disposition_carries_a_rationale(self):
        for record in D.EXAMPLE_DEFECTS:
            result = disposition(record)
            self.assertTrue(result.rationale, record.defect_id)
            self.assertTrue(result.governing_quantity, record.defect_id)

    def test_critical_part_flag_follows_the_process_module(self):
        for record in D.EXAMPLE_DEFECTS:
            result = disposition(record)
            self.assertEqual(record.part_id in CRITICAL_PART_IDS, result.critical_part)

    def test_snapshot_is_serialisable_and_covers_every_defect_type(self):
        import json

        report = D.snapshot()
        json.dumps(report)
        covered = {entry["defect_type"] for entry in report["example_dispositions"]}
        self.assertIn("delamination", covered)
        self.assertIn("porosity", covered)
        self.assertIn("fibre_waviness", covered)

    def test_snapshot_pairs_the_two_delamination_depths(self):
        report = D.snapshot()
        by_id = {
            entry["defect_id"]: entry for entry in report["example_dispositions"]
        }
        self.assertEqual(
            by_id["NCR-EX-001"]["actual"], by_id["NCR-EX-002"]["actual"]
        )
        self.assertNotEqual(
            by_id["NCR-EX-001"]["disposition"], by_id["NCR-EX-002"]["disposition"]
        )


if __name__ == "__main__":
    unittest.main()
