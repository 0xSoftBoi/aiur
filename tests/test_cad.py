import json
import struct
import tempfile
import unittest
from pathlib import Path

from hardware.dock.cad.generate_rev_a import (
    REV_A,
    funnel_mesh,
    generate_outputs,
    keeper_mesh,
    meshes,
    probe_head_mesh,
)


class RevACadTests(unittest.TestCase):
    def test_every_mesh_is_watertight_and_non_degenerate(self) -> None:
        for mesh in meshes():
            with self.subTest(mesh=mesh.name):
                self.assertEqual(mesh.degenerate_faces(), 0)
                self.assertEqual(mesh.nonmanifold_edges(), 0)
                self.assertGreater(mesh.volume_mm3(), 0)

    def test_funnel_envelope_matches_frozen_rev_a_interface(self) -> None:
        low, high = funnel_mesh().bounds()
        self.assertAlmostEqual(high[0] - low[0], REV_A.funnel_mouth_diameter_mm, places=6)
        self.assertAlmostEqual(high[1] - low[1], REV_A.funnel_mouth_diameter_mm, places=6)
        self.assertAlmostEqual(high[2] - low[2], REV_A.funnel_total_height_mm, places=6)

    def test_probe_head_and_keeper_critical_dimensions(self) -> None:
        probe_low, probe_high = probe_head_mesh().bounds()
        self.assertAlmostEqual(
            probe_high[0] - probe_low[0], REV_A.probe_head_diameter_mm, places=6
        )

        keeper_low, keeper_high = keeper_mesh().bounds()
        self.assertAlmostEqual(
            keeper_high[0] - keeper_low[0], REV_A.keeper_length_mm, places=6
        )
        self.assertAlmostEqual(
            keeper_high[1] - keeper_low[1], REV_A.keeper_width_mm, places=6
        )
        self.assertAlmostEqual(
            keeper_high[2] - keeper_low[2], REV_A.keeper_thickness_mm, places=6
        )
        self.assertGreater(REV_A.keeper_slot_width_mm, REV_A.probe_mast_diameter_mm)
        self.assertLess(REV_A.keeper_slot_width_mm, REV_A.probe_head_diameter_mm)

    def test_printed_geometry_preserves_dock_mass_headroom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = generate_outputs(Path(directory))
        # Development sub-budget, not a claim about the physical print.
        self.assertLessEqual(manifest["printed_petg_mass_estimate_g"], 110.0)

    def test_generator_writes_deterministic_binary_stls_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = generate_outputs(output)
            for mesh in meshes():
                data = (output / f"{mesh.name}.stl").read_bytes()
                self.assertEqual(struct.unpack("<I", data[80:84])[0], len(mesh.triangles))
                self.assertEqual(len(data), 84 + 50 * len(mesh.triangles))

            on_disk = json.loads((output / "p0a_rev_a_manifest.json").read_text())
            self.assertEqual(on_disk, manifest)
            self.assertIn("50 mm CHECK", (output / "p0a_drill_template.svg").read_text())


if __name__ == "__main__":
    unittest.main()
