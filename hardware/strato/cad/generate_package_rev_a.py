#!/usr/bin/env python3
"""Generate the STRATO-P0 Rev-A payload package geometry.

The package is a closed-cell foam box: six XPS panels cut from sheet, a
camera port in one wall, a GNSS patch under a foam-only lid, and a load line
that runs *around* the box rather than into it, so the enclosure carries no
tensile load.  Foam is cut, not printed, so the manufacturing artifacts are
a dimensioned cut sheet and a cross-section, plus a manifest that carries
the exterior dimensions, the smallest face, and the weight/size ratio the
regulation asks about.

Dependency-free so a clean checkout regenerates the drawings.  Dimensions in
millimetres.  This is a first-article fit geometry, not a flight-qualified
enclosure: the physical fit owns the final dimensions, this file owns what
gets cut to test it.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

POUND_KG = 0.45359237
OUNCE_KG = POUND_KG / 16.0
INCH_MM = 25.4


@dataclass(frozen=True)
class PackageRevision:
    """One complete parameter set for the enclosure."""

    name: str = "Rev-A"
    interior_length_mm: float = 130.0
    interior_width_mm: float = 100.0
    interior_height_mm: float = 80.0
    wall_mm: float = 20.0
    #: XPS insulation board; the density is the low end of the range vendors
    #: publish for 30-series XPS and is an allocation until the cut panels
    #: are weighed.
    foam_density_kg_m3: float = 32.0
    camera_port_diameter_mm: float = 30.0
    #: Port centre height above the interior floor, on the +x wall.
    camera_port_height_mm: float = 40.0
    #: GNSS patch footprint under the lid; foam only above it, no tape, no
    #: foil, nothing conductive.
    gnss_patch_mm: float = 25.0
    #: Load-line grooves: two loops around the box, this far in from the
    #: ends, so the line carries the package and the foam only locates it.
    line_groove_inset_mm: float = 30.0
    line_groove_mm: float = 4.0
    #: Package allocation the weight/size ratio is reported against.
    allocation_mass_kg: float = 1.0
    #: Stock sheet the cut sheet is laid out on.
    sheet_width_mm: float = 600.0
    sheet_length_mm: float = 1250.0
    kerf_mm: float = 2.0

    def validate(self) -> None:
        if min(self.interior_length_mm, self.interior_width_mm, self.interior_height_mm) <= 0:
            raise ValueError("interior dimensions must be positive")
        if self.wall_mm <= 0:
            raise ValueError("wall must be positive")
        if self.camera_port_diameter_mm >= min(self.interior_width_mm, self.interior_height_mm):
            raise ValueError("camera port does not fit the wall")
        if self.camera_port_height_mm + self.camera_port_diameter_mm / 2 > self.interior_height_mm:
            raise ValueError("camera port breaks the lid line")
        if self.gnss_patch_mm >= min(self.interior_length_mm, self.interior_width_mm):
            raise ValueError("GNSS patch does not fit the lid")
        if 2 * self.line_groove_inset_mm >= self.exterior_length_mm:
            raise ValueError("line grooves overlap")

    @property
    def exterior_length_mm(self) -> float:
        return self.interior_length_mm + 2 * self.wall_mm

    @property
    def exterior_width_mm(self) -> float:
        return self.interior_width_mm + 2 * self.wall_mm

    @property
    def exterior_height_mm(self) -> float:
        return self.interior_height_mm + 2 * self.wall_mm


REV_A = PackageRevision()
CURRENT = REV_A


@dataclass(frozen=True)
class Panel:
    name: str
    length_mm: float
    width_mm: float
    quantity: int
    note: str


def panels(rev: PackageRevision = CURRENT) -> tuple[Panel, ...]:
    """Six-panel butt-jointed box: floor and lid full exterior size, long
    walls span the interior length between the short walls, short walls span
    the exterior width."""

    rev.validate()
    return (
        Panel("floor", rev.exterior_length_mm, rev.exterior_width_mm, 1, "full exterior footprint"),
        Panel("lid", rev.exterior_length_mm, rev.exterior_width_mm, 1, "GNSS patch beneath; foam only above"),
        Panel("short wall", rev.exterior_width_mm, rev.interior_height_mm, 2, "one carries the camera port (+x)"),
        Panel("long wall", rev.interior_length_mm, rev.interior_height_mm, 2, "between the short walls"),
    )


def foam_volume_mm3(rev: PackageRevision = CURRENT) -> float:
    exterior = rev.exterior_length_mm * rev.exterior_width_mm * rev.exterior_height_mm
    interior = rev.interior_length_mm * rev.interior_width_mm * rev.interior_height_mm
    port = math.pi * (rev.camera_port_diameter_mm / 2) ** 2 * rev.wall_mm
    return exterior - interior - port


def foam_mass_kg(rev: PackageRevision = CURRENT) -> float:
    return foam_volume_mm3(rev) * 1e-9 * rev.foam_density_kg_m3


def smallest_face_mm2(rev: PackageRevision = CURRENT) -> float:
    dims = sorted((rev.exterior_length_mm, rev.exterior_width_mm, rev.exterior_height_mm))
    return dims[0] * dims[1]


def weight_size_ratio_oz_per_in2(rev: PackageRevision = CURRENT, mass_kg: float | None = None) -> float:
    """14 CFR 101.1(a)(4)(i): package weight in ounces over its smallest face in square inches."""

    mass = rev.allocation_mass_kg if mass_kg is None else mass_kg
    return (mass / OUNCE_KG) / (smallest_face_mm2(rev) / INCH_MM**2)


def cut_layout(rev: PackageRevision = CURRENT) -> list[dict[str, float | str]]:
    """Place every panel on the stock sheet, row by row, with kerf."""

    rev.validate()
    placements: list[dict[str, float | str]] = []
    x = 0.0
    y = 0.0
    row_height = 0.0
    for panel in panels(rev):
        for copy in range(panel.quantity):
            if x + panel.length_mm > rev.sheet_width_mm:
                x = 0.0
                y += row_height + rev.kerf_mm
                row_height = 0.0
            if y + panel.width_mm > rev.sheet_length_mm:
                raise ValueError("panels do not fit the stock sheet")
            placements.append(
                {
                    "panel": f"{panel.name} {copy + 1}" if panel.quantity > 1 else panel.name,
                    "x_mm": x,
                    "y_mm": y,
                    "length_mm": panel.length_mm,
                    "width_mm": panel.width_mm,
                }
            )
            x += panel.length_mm + rev.kerf_mm
            row_height = max(row_height, panel.width_mm)
    return placements


def _svg_head(width: float, height: float, dark: bool, title: str) -> list[str]:
    bg = "#0b0c0d" if dark else "#ffffff"
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{title}">',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{bg}"/>',
    ]


def cut_sheet_svg(rev: PackageRevision = CURRENT, *, dark: bool = False) -> str:
    """Cut sheet at 1 px = 1 mm on the stock sheet outline."""

    ink = "#d9d4c7" if dark else "#111111"
    faint = "#4a4f57" if dark else "#9a9a9a"
    accent = "#ff6428"
    margin = 40.0
    width = rev.sheet_width_mm + 2 * margin
    height = 420.0 + 2 * margin
    lines = _svg_head(width, height, dark, f"STRATO-P0 {rev.name} foam cut sheet")
    lines.append(
        f'<g font-family="ui-monospace, Menlo, monospace" font-size="11" fill="{ink}" '
        f'transform="translate({margin:.0f},{margin:.0f})">'
    )
    lines.append(
        f'<rect x="0" y="0" width="{rev.sheet_width_mm:.0f}" height="400" fill="none" stroke="{faint}" stroke-dasharray="6 6"/>'
    )
    lines.append(f'<text x="0" y="-12">XPS SHEET {rev.sheet_width_mm:.0f} x {rev.sheet_length_mm:.0f} x {rev.wall_mm:.0f} MM (FIRST 400 MM SHOWN) / KERF {rev.kerf_mm:.0f} MM</text>')
    for place in cut_layout(rev):
        x = float(place["x_mm"])
        y = float(place["y_mm"])
        w = float(place["length_mm"])
        h = float(place["width_mm"])
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="none" stroke="{ink}" stroke-width="1.2"/>')
        lines.append(f'<text x="{x + 6:.1f}" y="{y + 16:.1f}">{str(place["panel"]).upper()}</text>')
        lines.append(f'<text x="{x + 6:.1f}" y="{y + 30:.1f}" fill="{faint}">{w:.0f} x {h:.0f}</text>')
        if str(place["panel"]).startswith("short wall 1"):
            cx = x + w / 2
            cy = y + h - rev.camera_port_height_mm
            r = rev.camera_port_diameter_mm / 2
            lines.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="{accent}" stroke-width="1.5"/>')
            lines.append(f'<text x="{cx + r + 4:.1f}" y="{cy + 4:.1f}" fill="{accent}">Ø{rev.camera_port_diameter_mm:.0f} PORT</text>')
        if str(place["panel"]) == "lid":
            s = rev.gnss_patch_mm
            lines.append(f'<rect x="{x + w / 2 - s / 2:.1f}" y="{y + h / 2 - s / 2:.1f}" width="{s:.0f}" height="{s:.0f}" fill="none" stroke="{accent}" stroke-dasharray="3 3"/>')
            lines.append(f'<text x="{x + w / 2 + s / 2 + 4:.1f}" y="{y + h / 2 + 4:.1f}" fill="{accent}">GNSS PATCH BELOW</text>')
    lines.append(f'<text x="0" y="418" fill="{faint}">SOURCE generate_package_rev_a.py / {rev.name} / FIRST-ARTICLE FIT GEOMETRY, NOT FLIGHT-QUALIFIED</text>')
    lines.append("</g></svg>")
    return "\n".join(lines) + "\n"


def cross_section_svg(rev: PackageRevision = CURRENT, *, dark: bool = False) -> str:
    """Side elevation through the camera port, 2 px = 1 mm, dimensioned."""

    ink = "#d9d4c7" if dark else "#111111"
    faint = "#6b7078" if dark else "#8a8a8a"
    foam = "#1d2126" if dark else "#f0ede6"
    accent = "#ff6428"
    scale = 2.0
    margin = 130.0
    ext_l = rev.exterior_length_mm * scale
    ext_h = rev.exterior_height_mm * scale
    wall = rev.wall_mm * scale
    width = ext_l + 2 * margin + 160
    height = ext_h + 2 * margin + 60
    lines = _svg_head(width, height, dark, f"STRATO-P0 {rev.name} package cross-section")
    lines.append(
        f'<g font-family="ui-monospace, Menlo, monospace" font-size="12" fill="{ink}" '
        f'transform="translate({margin:.0f},{margin:.0f})">'
    )
    # Foam section: outer minus inner, drawn as two rects.
    lines.append(f'<rect x="0" y="0" width="{ext_l:.1f}" height="{ext_h:.1f}" fill="{foam}" stroke="{ink}" stroke-width="1.5"/>')
    lines.append(f'<rect x="{wall:.1f}" y="{wall:.1f}" width="{ext_l - 2 * wall:.1f}" height="{ext_h - 2 * wall:.1f}" fill="none" stroke="{ink}" stroke-width="1.5"/>')
    # Lid line.
    lines.append(f'<line x1="0" y1="{wall:.1f}" x2="{ext_l:.1f}" y2="{wall:.1f}" stroke="{faint}" stroke-dasharray="4 4"/>')
    # Camera port on the +x wall.
    port_r = rev.camera_port_diameter_mm / 2 * scale
    port_cy = ext_h - wall - rev.camera_port_height_mm * scale
    port_fill = "#0b0c0d" if dark else "#ffffff"
    lines.append(f'<rect x="{ext_l - wall:.1f}" y="{port_cy - port_r:.1f}" width="{wall:.1f}" height="{2 * port_r:.1f}" fill="{port_fill}" stroke="{accent}" stroke-width="1.5"/>')
    lines.append(f'<text x="{ext_l + 8:.1f}" y="{port_cy + 4:.1f}" fill="{accent}">Ø{rev.camera_port_diameter_mm:.0f} CAMERA PORT</text>')
    # GNSS patch under the lid.
    patch = rev.gnss_patch_mm * scale
    lines.append(f'<rect x="{ext_l / 2 - patch / 2:.1f}" y="{wall:.1f}" width="{patch:.1f}" height="6" fill="{accent}"/>')
    lines.append(f'<text x="{ext_l / 2 - patch / 2:.1f}" y="{wall + 22:.1f}" fill="{accent}">GNSS PATCH / FOAM ONLY ABOVE</text>')
    # Load-line grooves on the outside (two loops).
    for inset in (rev.line_groove_inset_mm, rev.exterior_length_mm - rev.line_groove_inset_mm):
        gx = inset * scale
        lines.append(f'<line x1="{gx:.1f}" y1="-14" x2="{gx:.1f}" y2="{ext_h + 14:.1f}" stroke="{accent}" stroke-width="2" stroke-dasharray="2 4"/>')
    lines.append(f'<text x="{rev.line_groove_inset_mm * scale + 6:.1f}" y="-20" fill="{accent}">LOAD LINE x2 / AROUND THE BOX, NEVER INTO IT</text>')
    # Dimensions.
    dy = ext_h + 34
    lines.append(f'<line x1="0" y1="{dy:.1f}" x2="{ext_l:.1f}" y2="{dy:.1f}" stroke="{ink}"/>')
    lines.append(f'<text x="{ext_l / 2 - 30:.1f}" y="{dy - 6:.1f}">{rev.exterior_length_mm:.0f}</text>')
    lines.append(f'<line x1="{wall:.1f}" y1="{dy + 22:.1f}" x2="{ext_l - wall:.1f}" y2="{dy + 22:.1f}" stroke="{faint}"/>')
    lines.append(f'<text x="{ext_l / 2 - 30:.1f}" y="{dy + 16:.1f}" fill="{faint}">{rev.interior_length_mm:.0f} INT</text>')
    dx = -34
    lines.append(f'<line x1="{dx}" y1="0" x2="{dx}" y2="{ext_h:.1f}" stroke="{ink}"/>')
    lines.append(f'<text x="{dx - 30}" y="{ext_h / 2 - 4:.1f}">{rev.exterior_height_mm:.0f}</text>')
    lines.append(f'<line x1="{dx - 44}" y1="{wall:.1f}" x2="{dx - 44}" y2="{ext_h - wall:.1f}" stroke="{faint}"/>')
    lines.append(f'<text x="{dx - 88}" y="{ext_h / 2 + 14:.1f}" fill="{faint}">{rev.interior_height_mm:.0f} INT</text>')
    lines.append(f'<text x="{ext_l + 8:.1f}" y="{wall / 2 + 4:.1f}" fill="{faint}">WALL {rev.wall_mm:.0f}</text>')
    # Title block.
    ty = ext_h + 70
    lines.append(f'<text x="0" y="{ty:.1f}">STRATO-P0 PACKAGE / {rev.name} / SECTION THROUGH CAMERA PORT / MM</text>')
    lines.append(
        f'<text x="0" y="{ty + 16:.1f}" fill="{faint}">EXTERIOR {rev.exterior_length_mm:.0f} x {rev.exterior_width_mm:.0f} x {rev.exterior_height_mm:.0f} / '
        f'SMALLEST FACE {smallest_face_mm2(rev) / INCH_MM**2:.1f} IN² / {weight_size_ratio_oz_per_in2(rev):.2f} OZ/IN² AT {rev.allocation_mass_kg:.1f} KG (LIMIT 3.0)</text>'
    )
    lines.append(f'<text x="0" y="{ty + 32:.1f}" fill="{faint}">SOURCE generate_package_rev_a.py / FIRST-ARTICLE FIT GEOMETRY, NOT FLIGHT-QUALIFIED</text>')
    lines.append("</g></svg>")
    return "\n".join(lines) + "\n"


def manifest(rev: PackageRevision = CURRENT) -> dict[str, object]:
    rev.validate()
    return {
        "revision": asdict(rev),
        "exterior_mm": [rev.exterior_length_mm, rev.exterior_width_mm, rev.exterior_height_mm],
        "interior_volume_l": rev.interior_length_mm * rev.interior_width_mm * rev.interior_height_mm * 1e-6,
        "foam_volume_l": foam_volume_mm3(rev) * 1e-6,
        "foam_mass_kg_estimate": round(foam_mass_kg(rev), 4),
        "smallest_face_in2": round(smallest_face_mm2(rev) / INCH_MM**2, 2),
        "weight_size_ratio_oz_per_in2_at_allocation": round(weight_size_ratio_oz_per_in2(rev), 3),
        "weight_size_ratio_limit_oz_per_in2": 3.0,
        "panels": [asdict(panel) for panel in panels(rev)],
        "cut_layout": cut_layout(rev),
        "outputs": [
            "strato_package_rev_a_cut_sheet.svg",
            "strato_package_rev_a_section.svg",
            "strato_package_rev_a_section_dark.svg",
            "strato_package_rev_a_manifest.json",
        ],
    }


def generate_outputs(out_dir: Path, rev: PackageRevision = CURRENT) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in (
        ("strato_package_rev_a_cut_sheet.svg", cut_sheet_svg(rev)),
        ("strato_package_rev_a_section.svg", cross_section_svg(rev)),
        ("strato_package_rev_a_section_dark.svg", cross_section_svg(rev, dark=True)),
        ("strato_package_rev_a_manifest.json", json.dumps(manifest(rev), indent=2) + "\n"),
    ):
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate STRATO-P0 Rev-A package geometry.")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "generated")
    args = parser.parse_args(argv)
    for path in generate_outputs(args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
