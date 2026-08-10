import json
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from hardware.dock.cad.generate_rev_a import (
    CURRENT,
    REV_A,
    crank_mesh,
    cross_section_svg,
    drill_template_svg,
    funnel_mesh,
    generate_outputs,
    link_mesh,
    linkage_drill_template_svg,
    keeper_mesh,
    meshes,
    probe_head_mesh,
)


class DockCadTests(unittest.TestCase):
    def test_every_mesh_is_watertight_and_non_degenerate(self) -> None:
        for mesh in meshes():
            with self.subTest(mesh=mesh.name):
                self.assertEqual(mesh.degenerate_faces(), 0)
                self.assertEqual(mesh.nonmanifold_edges(), 0)
                self.assertGreater(mesh.volume_mm3(), 0)

    def test_funnel_envelope_matches_the_frozen_interface(self) -> None:
        low, high = funnel_mesh().bounds()
        self.assertAlmostEqual(high[0] - low[0], CURRENT.funnel_mouth_diameter_mm, places=6)
        self.assertAlmostEqual(high[1] - low[1], CURRENT.funnel_mouth_diameter_mm, places=6)
        self.assertAlmostEqual(high[2] - low[2], CURRENT.funnel_total_height_mm, places=6)

    def test_probe_head_and_keeper_critical_dimensions(self) -> None:
        probe_low, probe_high = probe_head_mesh().bounds()
        self.assertAlmostEqual(
            probe_high[0] - probe_low[0], CURRENT.probe_head_diameter_mm, places=6
        )

        keeper_low, keeper_high = keeper_mesh().bounds()
        self.assertAlmostEqual(
            keeper_high[0] - keeper_low[0], CURRENT.keeper_length_mm, places=6
        )
        self.assertAlmostEqual(
            keeper_high[1] - keeper_low[1], CURRENT.keeper_width_mm, places=6
        )
        self.assertAlmostEqual(
            keeper_high[2] - keeper_low[2], CURRENT.keeper_thickness_mm, places=6
        )
        self.assertGreater(CURRENT.keeper_slot_width_mm, CURRENT.probe_mast_diameter_mm)
        self.assertLess(CURRENT.keeper_slot_width_mm, CURRENT.probe_head_diameter_mm)
        # The slot must also stay inside the seat it retains against, or the
        # tines have nothing to bear on.
        self.assertLess(
            CURRENT.keeper_slot_width_mm, CURRENT.probe_head_seat_diameter_mm
        )

    def test_commanded_stroke_clears_the_head(self) -> None:
        """The defect that forced Rev-B, pinned in the geometry itself."""

        self.assertLess(CURRENT.release_travel_shortfall_mm(), 0.0)
        # The tines must still reach far enough to bear the whole seat.
        self.assertGreaterEqual(
            CURRENT.keeper_tine_reach_mm, CURRENT.probe_head_seat_diameter_mm / 2.0
        )

    def test_printed_geometry_preserves_dock_mass_headroom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = generate_outputs(Path(directory))
        # Development sub-budget, not a claim about the physical print.
        self.assertLessEqual(manifest["printed_petg_mass_estimate_g"], 110.0)

    def test_generator_writes_deterministic_binary_stls_and_manifest(self) -> None:
        slug = CURRENT.name.lower().replace("-", "_")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = generate_outputs(output)
            for mesh in meshes():
                data = (output / f"{mesh.name}_{slug}.stl").read_bytes()
                self.assertEqual(struct.unpack("<I", data[80:84])[0], len(mesh.triangles))
                self.assertEqual(len(data), 84 + 50 * len(mesh.triangles))
                # The header must name the revision that produced the mesh, or
                # two revisions are indistinguishable on a print bed.
                self.assertIn(CURRENT.name.upper(), data[:80].decode("ascii"))

            on_disk = json.loads((output / f"p0a_{slug}_manifest.json").read_text())
            self.assertEqual(on_disk, manifest)
            self.assertIn(
                "50 mm CHECK", (output / f"p0a_drill_template_{slug}.svg").read_text()
            )

    def test_two_revisions_cannot_overwrite_each_other(self) -> None:
        """A superseded part must not be able to masquerade as the current one.

        Rev-A and Rev-B produce genuinely different keepers and probe heads.
        While both wrote the same filenames with the same hardcoded REV-A
        header, nothing on disk — not the name, not the slicer-visible
        header — distinguished them.
        """

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            generate_outputs(output, REV_A)
            generate_outputs(output, CURRENT)
            names = {path.name for path in output.iterdir()}

        for mesh in ("p0a_keeper", "p0a_probe_head"):
            self.assertIn(f"{mesh}_rev_a.stl", names)
            self.assertIn(f"{mesh}_rev_b.stl", names)


if __name__ == "__main__":
    unittest.main()


class KeeperDriveTests(unittest.TestCase):
    """The linkage closes the other half of the stroke chain.

    ``release_travel_shortfall_mm`` checks that the commanded stroke clears
    the probe head.  Nothing checked that the mechanism can *deliver* the
    commanded stroke, which is the same declared-but-unconsumed shape that
    produced the Rev-A defect — a number in the dataclass that no geometry
    had to honour.
    """

    def test_linkage_delivers_the_commanded_stroke(self) -> None:
        self.assertLessEqual(CURRENT.drive_stroke_shortfall_mm(), 0.0)
        # In-line slider-crank: stroke is exactly twice the crank radius.
        self.assertAlmostEqual(
            CURRENT.drive_stroke_mm, 2.0 * CURRENT.crank_radius_mm, places=9
        )

    def test_both_halves_of_the_stroke_chain_close(self) -> None:
        # servo rotation -> keeper travel -> head clearance
        self.assertLessEqual(CURRENT.drive_stroke_shortfall_mm(), 0.0)
        self.assertLess(CURRENT.release_travel_shortfall_mm(), 0.0)

    def test_obliquity_stays_bounded(self) -> None:
        """Link angle sets the side load the keeper guides carry."""

        self.assertLess(CURRENT.drive_obliquity_deg, 25.0)
        self.assertGreater(CURRENT.link_length_mm, CURRENT.crank_radius_mm)

    def test_drive_pin_stays_inside_the_keeper_back(self) -> None:
        """A pin that breaks into the slot or out of the back edge is a reject.

        keeper_mesh raises rather than generating it, so this is a build-time
        failure, not something discovered when a printed part splits.
        """

        margin = CURRENT.drive_pin_diameter_mm / 2.0 + CURRENT.drive_pin_edge_margin_mm
        self.assertLess(
            CURRENT.keeper_pin_x_mm + margin, -CURRENT.keeper_slot_width_mm / 2.0
        )
        self.assertGreater(
            CURRENT.keeper_pin_x_mm - margin, -CURRENT.keeper_back_reach_mm
        )

    def test_a_pin_that_breaks_into_the_slot_is_rejected(self) -> None:
        import dataclasses

        bad = dataclasses.replace(CURRENT, keeper_pin_x_mm=-1.0)
        with self.assertRaises(ValueError):
            keeper_mesh(bad)

    def test_crank_and_link_are_watertight(self) -> None:
        for mesh in (crank_mesh(), link_mesh()):
            with self.subTest(mesh=mesh.name):
                self.assertEqual(mesh.degenerate_faces(), 0)
                self.assertEqual(mesh.nonmanifold_edges(), 0)
                self.assertGreater(mesh.volume_mm3(), 0.0)

    def test_linkage_template_carries_the_real_centres(self) -> None:
        svg = linkage_drill_template_svg()
        self.assertIn("50 mm CHECK", svg)
        self.assertIn(f'cx="{20 + CURRENT.crank_radius_mm:g}"', svg)
        self.assertIn(f'cx="{20 + CURRENT.link_length_mm:g}"', svg)


class DrawingTests(unittest.TestCase):
    """A drawing is a build document, so it is derived like every other one.

    The hand-drawn cross-section still showed a Ø6 seat and a 4.2 mm slot
    after Rev-B moved both, and nothing in the repository could tell.
    """

    def _texts(self, svg: str) -> str:
        root = ElementTree.fromstring(svg)
        return " ".join(e.text or "" for e in root.iter() if e.tag.endswith("text"))

    def test_every_svg_is_well_formed(self) -> None:
        for name, svg in (
            ("cross_section", cross_section_svg()),
            ("flange_template", drill_template_svg()),
            ("linkage_template", linkage_drill_template_svg()),
        ):
            with self.subTest(drawing=name):
                ElementTree.fromstring(svg)

    def test_cross_section_callouts_track_the_revision(self) -> None:
        text = self._texts(cross_section_svg())
        self.assertIn(CURRENT.name.upper(), text)
        for value in (
            CURRENT.funnel_mouth_diameter_mm,
            CURRENT.funnel_throat_diameter_mm,
            CURRENT.probe_head_diameter_mm,
            CURRENT.probe_head_seat_diameter_mm,
            CURRENT.keeper_slot_width_mm,
            CURRENT.keeper_open_travel_mm,
        ):
            with self.subTest(value=value):
                self.assertIn(f"{value:g}", text)

    def test_cross_section_would_not_show_a_superseded_dimension(self) -> None:
        """Rev-A's seat and slot must not appear on a Rev-B drawing."""

        text = self._texts(cross_section_svg())
        self.assertNotIn(f"seat Ø{REV_A.probe_head_seat_diameter_mm:g}", text)
        self.assertNotIn(f"slot {REV_A.keeper_slot_width_mm:g}", text)
        # ...and the Rev-A drawing does show them, so the check has teeth.
        rev_a_text = self._texts(cross_section_svg(REV_A))
        self.assertIn(f"seat Ø{REV_A.probe_head_seat_diameter_mm:g}", rev_a_text)
