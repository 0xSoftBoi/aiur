import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from hardware.strato.cad.generate_package_rev_a import (
    CURRENT,
    PackageRevision,
    cross_section_svg,
    cut_layout,
    cut_sheet_svg,
    foam_mass_kg,
    generate_outputs,
    manifest,
    panels,
    smallest_face_mm2,
    weight_size_ratio_oz_per_in2,
)


class PackageCadTests(unittest.TestCase):
    def test_exterior_is_interior_plus_two_walls(self) -> None:
        self.assertEqual(CURRENT.exterior_length_mm, CURRENT.interior_length_mm + 2 * CURRENT.wall_mm)
        self.assertEqual(CURRENT.exterior_width_mm, CURRENT.interior_width_mm + 2 * CURRENT.wall_mm)
        self.assertEqual(CURRENT.exterior_height_mm, CURRENT.interior_height_mm + 2 * CURRENT.wall_mm)

    def test_six_panels_fit_the_stock_sheet_without_overlap(self) -> None:
        self.assertEqual(sum(panel.quantity for panel in panels()), 6)
        placed = cut_layout()
        self.assertEqual(len(placed), 6)
        boxes = [
            (float(p["x_mm"]), float(p["y_mm"]), float(p["x_mm"]) + float(p["length_mm"]), float(p["y_mm"]) + float(p["width_mm"]))
            for p in placed
        ]
        for i, a in enumerate(boxes):
            self.assertLessEqual(a[2], CURRENT.sheet_width_mm)
            self.assertLessEqual(a[3], CURRENT.sheet_length_mm)
            for b in boxes[i + 1 :]:
                overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                self.assertFalse(overlap, f"panels overlap: {a} {b}")

    def test_weight_size_ratio_is_under_the_regulatory_limb(self) -> None:
        self.assertLess(weight_size_ratio_oz_per_in2(), 3.0)
        # And stays under it even at the 4 lb ceiling the program never uses.
        self.assertLess(weight_size_ratio_oz_per_in2(mass_kg=1.814), 3.0)
        self.assertGreater(smallest_face_mm2(), 0.0)

    def test_foam_mass_is_a_small_part_of_the_allocation(self) -> None:
        self.assertGreater(foam_mass_kg(), 0.03)
        self.assertLess(foam_mass_kg(), 0.10)

    def test_drawings_are_well_formed_svg(self) -> None:
        for svg in (cut_sheet_svg(), cross_section_svg(), cross_section_svg(dark=True)):
            root = ElementTree.fromstring(svg)
            self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("CAMERA PORT", cross_section_svg())
        self.assertIn("GNSS PATCH", cut_sheet_svg())

    def test_manifest_and_outputs(self) -> None:
        data = manifest()
        self.assertEqual(data["exterior_mm"], [170.0, 140.0, 120.0])
        self.assertEqual(len(data["outputs"]), 4)
        with tempfile.TemporaryDirectory() as tmp:
            written = generate_outputs(Path(tmp))
            self.assertEqual([p.name for p in written], data["outputs"])
            reloaded = json.loads((Path(tmp) / "strato_package_rev_a_manifest.json").read_text())
            self.assertEqual(reloaded["exterior_mm"], data["exterior_mm"])

    def test_committed_outputs_match_the_generator(self) -> None:
        generated = Path(__file__).resolve().parents[1] / "hardware" / "strato" / "cad" / "generated"
        self.assertEqual(
            (generated / "strato_package_rev_a_section.svg").read_text(encoding="utf-8"),
            cross_section_svg(),
            "regenerate hardware/strato/cad/generated with generate_package_rev_a.py",
        )
        self.assertEqual(
            json.loads((generated / "strato_package_rev_a_manifest.json").read_text(encoding="utf-8")),
            manifest(),
        )

    def test_invalid_revisions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PackageRevision(camera_port_diameter_mm=90.0).validate()
        with self.assertRaises(ValueError):
            PackageRevision(camera_port_height_mm=75.0).validate()
        with self.assertRaises(ValueError):
            PackageRevision(wall_mm=0.0).validate()


if __name__ == "__main__":
    unittest.main()
