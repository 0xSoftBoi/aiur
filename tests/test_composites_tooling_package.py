"""The machine-shop tooling package, checked against the models that made it.

A drawing package is the point where an analysis becomes metal, and it is
also the point where an analysis stops being checkable by reading it. The
things that can go wrong here are not arithmetic slips in a formula — they
are a tool that quietly reverted to the part dimension, a matched die whose
two halves no longer close on a part thickness, a section view that draws a
bore as solid metal, and a committed drawing that has stopped agreeing with
the laminate it moulds.

So these tests measure the geometry back out of the artifacts rather than
re-deriving it: they read the moulding faces, close the dies numerically,
and compare what comes out against ``aiur.composites``.
"""

import importlib.util
import json
import math
import struct
import sys
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from aiur.composites import flatpattern, springin, tooling
from aiur.composites.schedules import schedule

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "hardware" / "composites" / "tooling"
GENERATED = PACKAGE_DIR / "generated"


def _load_generator():
    path = PACKAGE_DIR / "generate_tools.py"
    spec = importlib.util.spec_from_file_location("generate_tools", path)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because the module defines dataclasses, and
    # ``dataclasses`` resolves a field's type through ``sys.modules``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()


def _point_to_segment_mm(point, start, end) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def _face(tool) -> list:
    start, end = tool.moulding_span
    return list(tool.section)[start : end + 1]


class MeshTest(unittest.TestCase):
    """A tool a shop cannot open is not a deliverable."""

    def setUp(self):
        self.tools = GENERATOR.tools()

    def test_every_mesh_is_closed_and_manifold(self):
        for tool in self.tools:
            with self.subTest(tool.tool_id):
                self.assertEqual(0, tool.mesh.degenerate_faces())
                self.assertEqual(0, tool.mesh.nonmanifold_edges())
                self.assertGreater(tool.mesh.volume_mm3(), 0.0)

    def test_every_mesh_fits_inside_the_stock_it_quotes(self):
        # The RFQ prices the stock. If the envelope ever outgrew it the shop
        # would quote a billet the part does not fit in.
        for tool in self.tools:
            low, high = tool.mesh.bounds()
            for axis in range(3):
                with self.subTest(tool=tool.tool_id, axis=axis):
                    self.assertLessEqual(high[axis] - low[axis], tool.stock_mm[axis])

    def test_the_committed_stl_matches_the_mesh(self):
        for tool in self.tools:
            with self.subTest(tool.tool_id):
                payload = (GENERATED / f"{tool.stem}.stl").read_bytes()
                (count,) = struct.unpack("<I", payload[80:84])
                self.assertEqual(len(tool.mesh.triangles), count)
                self.assertEqual(84 + 50 * count, len(payload))


class CompensationTest(unittest.TestCase):
    """The one thing this package exists to get right."""

    def test_every_tool_is_scaled_below_the_part(self):
        # Aluminium against carbon: the tool grows more on the way up, so it
        # has to start smaller. A factor at or above one would mean the sign
        # of the correction had flipped.
        for part_id in ("CS-100", "CS-200", "CS-400"):
            with self.subTest(part_id):
                self.assertLess(GENERATOR.scale_factor(part_id), 1.0)
                self.assertGreater(GENERATOR.scale_factor(part_id), 0.99)

    def test_the_scale_factor_is_the_tooling_module_s_own(self):
        for part_id in ("CS-100", "CS-200", "CS-400"):
            expected = tooling.compensation_factor(
                part_cte_per_k=GENERATOR.part_cte_per_k(part_id),
                tool_cte_per_k=GENERATOR.TOOL_MATERIAL.cte_per_k,
                cooldown_k=GENERATOR.cooldown_k(),
            )
            self.assertEqual(expected, GENERATOR.scale_factor(part_id), part_id)

    def test_the_throat_is_cut_smaller_than_the_part(self):
        cone = flatpattern.PART_SHAPES["CS-100"]
        values = {
            dimension.label: dimension.value_mm
            for dimension in GENERATOR.throat_cup_tool().dimensions
        }
        self.assertLess(values["cavity throat radius"], cone.inner_radius_mm)
        self.assertAlmostEqual(
            cone.inner_radius_mm * GENERATOR.scale_factor("CS-100"),
            values["cavity throat radius"],
            places=9,
        )

    def test_the_cone_angle_is_opened_by_the_predicted_spring_in(self):
        corner = GENERATOR.registered_corner("CS-100", "throat cup cone half-angle")
        values = {
            dimension.label: dimension.value_mm
            for dimension in GENERATOR.throat_cup_tool().dimensions
        }
        compensation = GENERATOR.corner_compensation_deg(
            "CS-100", corner.enclosed_angle_deg
        )
        self.assertGreater(compensation, 0.0)
        self.assertAlmostEqual(
            corner.enclosed_angle_deg + compensation,
            values["cone half-angle"],
            places=9,
        )

    def test_the_mandrel_carries_no_corner_compensation(self):
        # A cylindrical section has no enclosed corner. The absence is a
        # result, and a future edit that "fixed" it by adding spring-in to a
        # cylinder should fail here rather than quietly reach a machinist.
        tube = flatpattern.PART_SHAPES["CS-200"]
        laminate = schedule("CS-200").laminate()
        values = {
            dimension.label: dimension.value_mm
            for dimension in GENERATOR.boom_mandrel_tool().dimensions
        }
        self.assertAlmostEqual(
            (tube.radius_mm - laminate.thickness_mm / 2.0)
            * GENERATOR.scale_factor("CS-200"),
            values["crown radius"],
            places=9,
        )
        self.assertEqual(tube.subtended_angle_deg, values["subtended angle"])

    def test_the_registered_corner_is_the_one_that_is_cut(self):
        # The corner register is the design record. A tool angle taken from
        # anywhere else could disagree with it without anything failing.
        for part_id, feature in (
            ("CS-100", "throat cup cone half-angle"),
            ("CS-400", "tine root bend"),
        ):
            corner = GENERATOR.registered_corner(part_id, feature)
            self.assertIn(corner, springin.CORNERS)
        with self.assertRaises(KeyError):
            GENERATOR.registered_corner("CS-100", "a corner nobody registered")


class MatchedDieTest(unittest.TestCase):
    """The dies are the only tool here whose two halves have to agree."""

    def setUp(self):
        self.cavity, self.punch = GENERATOR.tine_die_tools()
        self.thickness = schedule("CS-400").laminate().thickness_mm

    def test_the_closed_gap_is_the_part_thickness_everywhere(self):
        # This is the dimension a shop is asked to shim-check, and the one an
        # innocent-looking change to either half would break silently. The
        # tolerance allows for the arc being faceted, nothing more.
        cavity_face = _face(self.cavity)
        punch_face = _face(self.punch)
        tolerance = 4.0 * max(
            self.cavity.faceting_error_mm, self.punch.faceting_error_mm
        )
        for point in punch_face:
            gap = min(
                _point_to_segment_mm(point, cavity_face[index], cavity_face[index + 1])
                for index in range(len(cavity_face) - 1)
            )
            self.assertAlmostEqual(self.thickness, gap, delta=max(tolerance, 1e-6))

    def test_the_two_halves_are_cut_to_one_corner_angle(self):
        cavity = {d.label: d.value_mm for d in self.cavity.dimensions}
        punch = {d.label: d.value_mm for d in self.punch.dimensions}
        self.assertEqual(cavity["enclosed corner angle"], punch["enclosed corner angle"])

    def test_the_cut_corner_is_open_and_measures_what_it_claims(self):
        cavity = {d.label: d.value_mm for d in self.cavity.dimensions}
        corner = GENERATOR.registered_corner("CS-400", "tine root bend")
        self.assertGreater(cavity["enclosed corner angle"], corner.enclosed_angle_deg)

        # Measure the angle back out of the geometry: the leg directions at
        # each end of the moulding face.
        face = _face(self.cavity)
        leg_a = (face[0][0] - face[1][0], face[0][1] - face[1][1])
        leg_b = (face[-1][0] - face[-2][0], face[-1][1] - face[-2][1])
        cosine = (leg_a[0] * leg_b[0] + leg_a[1] * leg_b[1]) / (
            math.hypot(*leg_a) * math.hypot(*leg_b)
        )
        self.assertAlmostEqual(
            cavity["enclosed corner angle"], math.degrees(math.acos(cosine)), places=6
        )

    def test_the_punch_radius_is_the_cavity_radius_less_a_thickness(self):
        cavity = {d.label: d.value_mm for d in self.cavity.dimensions}
        punch = {d.label: d.value_mm for d in self.punch.dimensions}
        self.assertAlmostEqual(
            cavity["outer corner radius"] - punch["inner corner radius"],
            self.thickness,
            places=9,
        )

    def test_the_inner_radius_is_not_tighter_than_the_laminate_allows(self):
        # The two-thicknesses rule is a rule about the *part* — it is the
        # laminate that thins on the outside of a tight corner. The tool is
        # cut under it by the compensation, and reading the tool dimension
        # against a part rule is exactly the confusion this package is built
        # to prevent, so the test does the conversion the rule needs.
        punch = {d.label: d.value_mm for d in self.punch.dimensions}
        part_radius = punch["inner corner radius"] / GENERATOR.scale_factor("CS-400")
        self.assertGreaterEqual(part_radius, 2.0 * self.thickness)
        self.assertLess(punch["inner corner radius"], part_radius)

    def test_the_developed_length_comes_from_the_schedule(self):
        item = schedule("CS-400")
        cavity = {d.label: d.value_mm for d in self.cavity.dimensions}
        arc = math.radians(180.0 - cavity["enclosed corner angle"]) * (
            cavity["outer corner radius"] - self.thickness / 2.0
        )
        developed = cavity["blade leg length"] + cavity["root leg length"] + arc
        self.assertAlmostEqual(
            item.area_m2 * 1e6 / GENERATOR.TINE_WIDTH_MM * GENERATOR.scale_factor("CS-400"),
            developed,
            places=6,
        )


class DimensionTest(unittest.TestCase):
    def setUp(self):
        self.tools = GENERATOR.tools()

    def test_a_moulding_dimension_is_never_quoted_at_a_free_tolerance(self):
        # The tolerance class is what a shop prices and what an inspector
        # checks. A moulding surface loosened to the free class would be an
        # invisible relaxation of the part's own tolerance.
        for tool in self.tools:
            for dimension in tool.dimensions:
                if dimension.feature_class != "moulding surface":
                    continue
                if dimension.unit == "deg":
                    continue
                with self.subTest(tool=tool.tool_id, dimension=dimension.label):
                    self.assertLessEqual(
                        dimension.tolerance_mm, GENERATOR.TOLERANCE_FREE
                    )

    def test_every_dimension_states_where_it_came_from(self):
        for tool in self.tools:
            for dimension in tool.dimensions:
                with self.subTest(tool=tool.tool_id, dimension=dimension.label):
                    self.assertGreater(len(dimension.basis), 12)

    def test_every_tool_carries_at_least_one_moulding_dimension(self):
        for tool in self.tools:
            classes = {dimension.feature_class for dimension in tool.dimensions}
            self.assertIn("moulding surface", classes, tool.tool_id)


class SheetTest(unittest.TestCase):
    def setUp(self):
        self.tools = GENERATOR.tools()

    def test_every_sheet_is_well_formed_svg(self):
        for tool in self.tools:
            with self.subTest(tool.tool_id):
                root = ElementTree.fromstring(
                    (GENERATED / f"{tool.stem}_sheet.svg").read_text(encoding="utf-8")
                )
                self.assertTrue(root.tag.endswith("svg"))
                self.assertEqual("420mm", root.get("width"))
                self.assertEqual("297mm", root.get("height"))

    def test_every_sheet_carries_the_compensation_warning(self):
        # The single sentence that stops a machinist from correcting a
        # compensated dimension back to the part drawing.
        for tool in self.tools:
            text = (GENERATED / f"{tool.stem}_sheet.svg").read_text(encoding="utf-8")
            with self.subTest(tool.tool_id):
                self.assertIn("DO NOT WORK TO THE PART DRAWING", text)
                self.assertIn(
                    f"SCALE FACTOR {GENERATOR.scale_factor(tool.part_id):.6f}", text
                )

    def test_the_section_stays_inside_its_view(self):
        x0, y0, x1, y1 = GENERATOR.VIEW_BOX
        for tool in self.tools:
            regions, _ = GENERATOR._sections(tool)
            points = [point for region, _ in regions for point in region]
            ratio, ox, oy = GENERATOR._fit(points)
            units = ratio * GENERATOR.UNITS_PER_MM
            for x, y in points:
                with self.subTest(tool.tool_id):
                    self.assertGreaterEqual(ox + x * units, x0 - 1e-6)
                    self.assertLessEqual(ox + x * units, x1 + 1e-6)
                    self.assertGreaterEqual(oy - y * units, y0 - 1e-6)
                    self.assertLessEqual(oy - y * units, y1 + 1e-6)

    def test_a_revolved_tool_is_sectioned_as_two_regions(self):
        # An annulus sections into two. Drawing it as one closes the bore up
        # and shows solid metal where the push-rod goes.
        cup = GENERATOR.throat_cup_tool()
        regions, is_revolved = GENERATOR._sections(cup)
        self.assertTrue(is_revolved)
        self.assertEqual(2, len(regions))
        for region, span in regions:
            face = region[span[0] : span[1] + 1]
            self.assertEqual(2, len(face))
            # The moulding face is the cone: it changes both radius and height.
            self.assertNotEqual(face[0][0], face[1][0])
            self.assertNotEqual(face[0][1], face[1][1])


class PackageTest(unittest.TestCase):
    def test_the_committed_package_is_current(self):
        stale = GENERATOR.check_outputs(GENERATED)
        self.assertEqual(
            [],
            stale,
            "the tooling package is stale; run "
            "python hardware/composites/tooling/generate_tools.py",
        )

    def test_generation_is_deterministic(self):
        self.assertEqual(GENERATOR.artifacts(), GENERATOR.artifacts())

    def test_check_mode_agrees(self):
        self.assertEqual(0, GENERATOR.main(["--check", "--out-dir", str(GENERATED)]))

    def test_the_rfq_prices_every_tool(self):
        rows = {row["item"]: row for row in GENERATOR.rfq_rows()}
        self.assertEqual({tool.tool_id for tool in GENERATOR.tools()}, set(rows))
        for tool in GENERATOR.tools():
            row = rows[tool.tool_id]
            with self.subTest(tool.tool_id):
                self.assertGreater(row["removal_fraction"], 0.0)
                self.assertLess(row["removal_fraction"], 1.0)
                self.assertAlmostEqual(
                    tool.mesh.volume_mm3() / 1000.0, row["finished_volume_cm3"], delta=0.1
                )
                self.assertIn("do not work to the part drawing", row["note"])

    def test_the_manifest_publishes_the_compensation_it_applied(self):
        manifest = json.loads(
            (GENERATED / "tooling_manifest.json").read_text(encoding="utf-8")
        )
        factors = manifest["compensation"]["scale_factors"]
        for part_id in ("CS-100", "CS-200", "CS-400"):
            self.assertAlmostEqual(
                GENERATOR.scale_factor(part_id), factors[part_id], places=8
            )
        self.assertEqual(len(springin.CORNERS), len(manifest["compensation"]["spring_in_deg"]))

    def test_the_manifest_says_the_laminates_are_not_qualified(self):
        # The tools are real; the laminates they mould are a design study.
        # A shop reading only the manifest should still learn that.
        manifest = json.loads(
            (GENERATED / "tooling_manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("design study", manifest["status"])


if __name__ == "__main__":
    unittest.main()
