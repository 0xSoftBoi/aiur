"""Flat-pattern development and ply-book generation checks.

The development tests lean on the fact that a developable surface flattens
*exactly*: the sector angle is right only if the developed area equals the
surface area and every developed arc equals the circumference it came from.
Those are identities, not tolerances, so they catch a wrong sector angle that
no eyeballed drawing would.

The ply-book tests check the thing a generated drawing can most easily get
wrong, which is not its geometry but its agreement with the design it claims
to represent — and, above all, the lay-down order. A sheet that lists the
plies from the wrong end builds the part inside out.
"""

import math
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from aiur.composites import flatpattern
from aiur.composites.clt import Laminate
from aiur.composites.flatpattern import (
    ConeFrustum,
    Development,
    PART_SHAPES,
    SlitTube,
    develop,
    evaluate,
    gores_for_tolerance,
    nesting_utilisation,
    rotational_envelope,
    seam_stagger_ok,
    snapshot,
    staggered_seams,
    validate_geometry,
)
from aiur.composites.process import debulk_schedule
from aiur.composites.schedules import SCHEDULES, schedule

REPO_ROOT = Path(__file__).resolve().parents[1]


class ConeDevelopmentTest(unittest.TestCase):
    def setUp(self):
        self.cone = ConeFrustum(inner_radius_mm=20.0, outer_radius_mm=55.0, height_mm=35.0)
        self.development = develop(self.cone)

    def test_developed_area_equals_the_surface_area(self):
        # The identity that proves the sector angle: flattening a developable
        # surface neither creates nor destroys area.
        self.assertAlmostEqual(
            self.cone.lateral_area_mm2, self.development.area_mm2, places=9
        )

    def test_developed_arcs_equal_the_circumferences_they_came_from(self):
        sector = math.radians(self.development.sector_angle_deg)
        self.assertAlmostEqual(
            2.0 * math.pi * self.cone.inner_radius_mm,
            self.development.inner_radius_mm * sector,
            places=9,
        )
        self.assertAlmostEqual(
            2.0 * math.pi * self.cone.outer_radius_mm,
            self.development.outer_radius_mm * sector,
            places=9,
        )

    def test_radial_width_equals_the_slant_length(self):
        self.assertAlmostEqual(
            self.cone.slant_mm,
            self.development.outer_radius_mm - self.development.inner_radius_mm,
            places=9,
        )

    def test_forty_five_degree_cone_has_the_expected_half_angle(self):
        self.assertAlmostEqual(45.0, self.cone.half_angle_deg, places=9)

    def test_fibre_drift_equals_the_sector_angle(self):
        # The finding this module exists for: meridians develop to radial
        # lines, so a straight fibre's angle to them changes one-for-one.
        self.assertAlmostEqual(
            self.development.sector_angle_deg,
            self.development.fibre_angle_drift_deg,
            places=12,
        )

    def test_shallower_cone_drifts_less(self):
        shallow = develop(ConeFrustum(inner_radius_mm=50.0, outer_radius_mm=55.0, height_mm=60.0))
        self.assertLess(
            shallow.fibre_angle_drift_deg, self.development.fibre_angle_drift_deg
        )

    def test_cylinder_is_refused_as_a_cone(self):
        with self.assertRaises(ValueError):
            ConeFrustum(inner_radius_mm=30.0, outer_radius_mm=30.0, height_mm=50.0)

    def test_degenerate_geometry_is_refused(self):
        with self.assertRaises(ValueError):
            ConeFrustum(inner_radius_mm=-1.0, outer_radius_mm=30.0, height_mm=50.0)
        with self.assertRaises(ValueError):
            ConeFrustum(inner_radius_mm=10.0, outer_radius_mm=30.0, height_mm=0.0)


class TubeDevelopmentTest(unittest.TestCase):
    def setUp(self):
        self.tube = SlitTube(radius_mm=22.3, subtended_angle_deg=90.0, length_mm=250.0)
        self.development = develop(self.tube)

    def test_developed_width_is_the_arc_length(self):
        self.assertAlmostEqual(
            22.3 * math.pi / 2.0, self.development.width_mm, places=9
        )

    def test_area_is_preserved(self):
        self.assertAlmostEqual(
            self.tube.lateral_area_mm2, self.development.area_mm2, places=9
        )

    def test_a_cylinder_has_no_fibre_drift(self):
        # The contrast that stops the cone's answer being over-generalised.
        self.assertEqual(0.0, self.development.fibre_angle_drift_deg)

    def test_one_gore_suffices_without_drift(self):
        self.assertEqual(1, gores_for_tolerance(self.development))

    def test_invalid_subtended_angle_is_refused(self):
        with self.assertRaises(ValueError):
            SlitTube(radius_mm=20.0, subtended_angle_deg=400.0, length_mm=100.0)


class GoreCountTest(unittest.TestCase):
    def test_gore_count_scales_with_drift_and_tolerance(self):
        development = develop(PART_SHAPES["CS-100"])
        tight = gores_for_tolerance(development, tolerance_deg=3.0)
        loose = gores_for_tolerance(development, tolerance_deg=15.0)
        self.assertGreater(tight, loose)
        self.assertEqual(
            math.ceil(development.fibre_angle_drift_deg / 6.0), tight
        )

    def test_holding_three_degrees_on_this_cone_is_impractical(self):
        # 43 gores is the number that turns "hold the fibre angle" from a
        # process requirement into a design decision.
        development = develop(PART_SHAPES["CS-100"])
        self.assertGreater(gores_for_tolerance(development), 20)

    def test_non_positive_tolerance_is_refused(self):
        with self.assertRaises(ValueError):
            gores_for_tolerance(develop(PART_SHAPES["CS-100"]), tolerance_deg=0.0)


class RotationalEnvelopeTest(unittest.TestCase):
    def test_quasi_isotropic_fabric_stack_is_rotationally_isotropic(self):
        # Equal fabric thickness at 0 and 45 is the fabric equivalent of a
        # quasi-isotropic laminate, and the keeper tine is built that way.
        envelope = rotational_envelope(schedule("CS-400").laminate())
        self.assertTrue(envelope["in_plane_isotropic"])
        self.assertAlmostEqual(1.0, envelope["ex_ratio"], places=3)

    def test_unidirectional_stack_is_strongly_direction_dependent(self):
        envelope = rotational_envelope(schedule("CS-300").laminate())
        self.assertGreater(envelope["ex_ratio"], 2.0)

    def test_throat_cup_is_nearly_isotropic_because_it_has_to_be(self):
        # It sits on a cone, so its own fibre angle varies by 255 degrees.
        envelope = rotational_envelope(schedule("CS-100").laminate())
        self.assertLess(envelope["ex_ratio"], 1.10)

    def test_the_predecessor_stack_would_not_have_been(self):
        # The five-ply stack this replaced: one carbon ply at 0 against two
        # at 45. Kept as a test so the reason for the sixth ply survives.
        from aiur.composites.clt import Ply

        predecessor = Laminate.from_top_down(
            [
                Ply("PW-G-1080", 45.0),
                Ply("PW-C-80", 45.0),
                Ply("PW-C-80", 0.0),
                Ply("PW-C-80", 45.0),
                Ply("PW-G-1080", 45.0),
            ]
        )
        self.assertGreater(rotational_envelope(predecessor)["ex_ratio"], 1.4)

    def test_invalid_sweep_is_refused(self):
        with self.assertRaises(ValueError):
            rotational_envelope(schedule("CS-400").laminate(), span_deg=0.0)


class NestingAndSeamTest(unittest.TestCase):
    def test_rectangle_nests_perfectly(self):
        nesting = nesting_utilisation(develop(PART_SHAPES["CS-200"]))
        self.assertAlmostEqual(1.0, nesting["utilisation"], places=6)
        self.assertAlmostEqual(0.0, nesting["scrap_fraction"], places=6)

    def test_annular_sector_wastes_about_half_the_stock(self):
        nesting = nesting_utilisation(develop(PART_SHAPES["CS-100"]))
        self.assertGreater(nesting["scrap_fraction"], 0.4)
        self.assertLess(nesting["scrap_fraction"], 0.7)

    def test_every_pattern_fits_the_roll(self):
        for part_id in PART_SHAPES:
            self.assertTrue(
                nesting_utilisation(develop(PART_SHAPES[part_id]))["fits_roll_width"],
                part_id,
            )

    def test_staggered_seams_satisfy_the_stagger_rule(self):
        self.assertTrue(seam_stagger_ok(list(staggered_seams(6))))

    def test_stacked_seams_are_rejected(self):
        self.assertFalse(seam_stagger_ok([0.0, 0.0, 0.0]))

    def test_seam_count_matches_the_ply_count(self):
        self.assertEqual(6, len(staggered_seams(6)))
        with self.assertRaises(ValueError):
            staggered_seams(0)


class GeometryRegistryTest(unittest.TestCase):
    def test_registry_is_valid(self):
        self.assertEqual([], validate_geometry())

    def test_schedule_areas_come_from_the_developed_geometry(self):
        for part_id in PART_SHAPES:
            report = evaluate(part_id)
            self.assertAlmostEqual(
                report["declared_area_m2"],
                report["developed_area_m2"],
                delta=0.02 * report["developed_area_m2"],
                msg=part_id,
            )

    def test_snapshot_is_valid(self):
        report = snapshot()
        self.assertTrue(report["valid"])
        self.assertEqual([], report["errors"])


class PlyBookTest(unittest.TestCase):
    """The generated sheets must agree with the schedules they come from."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        path = REPO_ROOT / "hardware" / "composites" / "plybook" / "generate_plybook.py"
        spec = importlib.util.spec_from_file_location("generate_plybook", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_generator_writes_a_sheet_for_every_part(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.module.generate_outputs(Path(directory))
            for item in SCHEDULES:
                self.assertIn(item.part_id, manifest["parts"])
                entry = manifest["parts"][item.part_id]
                self.assertTrue((Path(directory) / entry["layup_sheet"]).exists())
            for part_id in PART_SHAPES:
                entry = manifest["parts"][part_id]
                self.assertTrue((Path(directory) / entry["flat_pattern"]).exists())

    def test_every_sheet_is_well_formed_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            self.module.generate_outputs(Path(directory))
            svgs = list(Path(directory).glob("*.svg"))
            self.assertTrue(svgs)
            for svg in svgs:
                ElementTree.parse(svg)

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            self.module.generate_outputs(Path(first))
            self.module.generate_outputs(Path(second))
            for path in sorted(Path(first).iterdir()):
                self.assertEqual(
                    path.read_text(),
                    (Path(second) / path.name).read_text(),
                    path.name,
                )

    def test_committed_ply_book_is_current(self):
        # A stale drawing on disk is worse than none: it is a document the
        # shop trusts and the analysis has moved past.
        committed = REPO_ROOT / "hardware" / "composites" / "plybook" / "generated"
        with tempfile.TemporaryDirectory() as directory:
            self.module.generate_outputs(Path(directory))
            for path in sorted(Path(directory).iterdir()):
                target = committed / path.name
                self.assertTrue(target.exists(), f"{path.name} is not committed")
                self.assertEqual(
                    path.read_text(),
                    target.read_text(),
                    f"{path.name} is stale; regenerate the ply book",
                )

    def test_layup_sheet_lists_plies_tool_side_first(self):
        # The convention error that builds a part inside out. The design
        # stack is top-surface-first; the laminator starts at the tool, so
        # the sheet must be the reverse of the schedule's listing.
        item = schedule("CS-300")
        root = ElementTree.fromstring(self.module.layup_sheet_svg("CS-300"))
        namespace = "{http://www.w3.org/2000/svg}"
        materials = [
            element.text
            for element in root.iter(f"{namespace}text")
            if element.get("x") == "24" and element.text != "material"
        ]
        expected = [ply.material for ply in item.laminate().plies]
        self.assertEqual(expected, materials)
        self.assertEqual(
            [ply.material for ply in reversed(item.plies_top_down)], materials
        )

    def test_layup_sheet_marks_the_debulk_points(self):
        for item in SCHEDULES:
            svg = self.module.layup_sheet_svg(item.part_id)
            expected = len(debulk_schedule(item.laminate().ply_count))
            self.assertEqual(expected, svg.count("DEBULK"), item.part_id)

    def test_layup_sheet_carries_the_hold_point(self):
        for item in SCHEDULES:
            self.assertIn("HOLD POINT", self.module.layup_sheet_svg(item.part_id))

    def test_flat_patterns_carry_a_check_line(self):
        for part_id in PART_SHAPES:
            report = evaluate(part_id)
            svg = (
                self.module.cone_pattern_svg(part_id)
                if report["development"]["kind"] == "annular_sector"
                else self.module.rectangle_pattern_svg(part_id)
            )
            self.assertIn("measure before cutting", svg)

    def test_cone_sheet_states_the_drift(self):
        svg = self.module.cone_pattern_svg("CS-100")
        self.assertIn("Fibre angle drifts", svg)
        self.assertIn("255", svg)

    def test_manifest_records_the_design_study_status(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.module.generate_outputs(Path(directory))
        self.assertIn("design study", manifest["status"])


if __name__ == "__main__":
    unittest.main()
