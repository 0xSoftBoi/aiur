#!/usr/bin/env python3
"""Generate the CARRIER-P0 ply book: 1:1 flat patterns and layup sheets.

A ply book is what a laminator actually works from. It is not a summary of
the design — it is the design, in the only form that survives contact with a
cutting table: a full-size outline to cut against, an arrow saying which way
the fibre goes, and a numbered sequence saying which ply follows which.

Everything here is derived from the executable schedules and the flat-pattern
development, so the sheet and the analysis cannot disagree. Nothing is drawn
by hand and no dimension is typed twice.

The patterns print at 1:1. Each sheet carries a 100 mm check line, because a
printer that silently scales to fit turns a controlled drawing into a
confident lie, and the check line is the only thing standing between that and
a scrapped ply.

Regenerate from the repository root:

    python hardware/composites/plybook/generate_plybook.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script convenience
    sys.path.insert(0, str(REPO_ROOT))

from aiur.composites import flatpattern
from aiur.composites.clt import Laminate
from aiur.composites.process import debulk_schedule
from aiur.composites.schedules import SCHEDULES, schedule

#: Printed check line length, mm.  A printer that scales to fit is the most
#: common way a 1:1 template stops being 1:1.
CHECK_LINE_MM = 100.0
#: Margin around the pattern on the sheet, mm.
SHEET_MARGIN_MM = 25.0

STYLE = """
  .outline { fill: none; stroke: #111; stroke-width: 0.5; }
  .cutline { fill: none; stroke: #111; stroke-width: 0.8; }
  .netline { fill: none; stroke: #888; stroke-width: 0.4; stroke-dasharray: 4 2; }
  .fibre { stroke: #b00; stroke-width: 0.6; fill: none; }
  .fibrehead { fill: #b00; }
  .check { stroke: #060; stroke-width: 0.8; fill: none; }
  .ply { fill: #d8d8d8; stroke: #111; stroke-width: 0.4; }
  .plyalt { fill: #f2f2f2; stroke: #111; stroke-width: 0.4; }
  text { font-family: "DejaVu Sans", "Helvetica", sans-serif; fill: #111; }
  .title { font-size: 5px; font-weight: bold; }
  .label { font-size: 3px; }
  .small { font-size: 2.4px; fill: #444; }
  .warn { font-size: 3px; fill: #b00; }
"""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _fibre_arrow(x: float, y: float, angle_deg: float, length: float, label: str) -> str:
    """A fibre-direction arrow with its angle called out."""

    theta = math.radians(angle_deg)
    dx, dy = math.cos(theta) * length / 2.0, -math.sin(theta) * length / 2.0
    x1, y1, x2, y2 = x - dx, y - dy, x + dx, y + dy
    head = 2.0
    left = (
        x2 - head * math.cos(theta - math.radians(20)),
        y2 + head * math.sin(theta - math.radians(20)),
    )
    right = (
        x2 - head * math.cos(theta + math.radians(20)),
        y2 + head * math.sin(theta + math.radians(20)),
    )
    return (
        f'<line class="fibre" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
        f'<polygon class="fibrehead" points="{x2:.2f},{y2:.2f} '
        f'{left[0]:.2f},{left[1]:.2f} {right[0]:.2f},{right[1]:.2f}"/>'
        f'<text class="label" x="{x2 + 2:.2f}" y="{y2 - 1:.2f}">{_escape(label)}</text>'
    )


def _check_line(x: float, y: float) -> str:
    return (
        f'<line class="check" x1="{x:.2f}" y1="{y:.2f}" '
        f'x2="{x + CHECK_LINE_MM:.2f}" y2="{y:.2f}"/>'
        f'<line class="check" x1="{x:.2f}" y1="{y - 2:.2f}" x2="{x:.2f}" y2="{y + 2:.2f}"/>'
        f'<line class="check" x1="{x + CHECK_LINE_MM:.2f}" y1="{y - 2:.2f}" '
        f'x2="{x + CHECK_LINE_MM:.2f}" y2="{y + 2:.2f}"/>'
        f'<text class="label" x="{x + CHECK_LINE_MM / 2 - 18:.2f}" y="{y - 3:.2f}">'
        f'{CHECK_LINE_MM:g} mm — measure before cutting</text>'
    )


def _sector_path(cx: float, cy: float, inner: float, outer: float, sector_deg: float) -> str:
    """Annular-sector outline, drawn symmetrically about straight up."""

    half = math.radians(sector_deg) / 2.0
    large = 1 if sector_deg > 180.0 else 0

    def point(radius: float, angle: float) -> tuple[float, float]:
        return (cx + radius * math.sin(angle), cy - radius * math.cos(angle))

    o1, o2 = point(outer, -half), point(outer, half)
    i2, i1 = point(inner, half), point(inner, -half)
    return (
        f"M {o1[0]:.3f} {o1[1]:.3f} "
        f"A {outer:.3f} {outer:.3f} 0 {large} 1 {o2[0]:.3f} {o2[1]:.3f} "
        f"L {i2[0]:.3f} {i2[1]:.3f} "
        f"A {inner:.3f} {inner:.3f} 0 {large} 0 {i1[0]:.3f} {i1[1]:.3f} Z"
    )


def cone_pattern_svg(part_id: str) -> str:
    """1:1 flat pattern for a conical part, with the fibre-drift callout."""

    item = schedule(part_id)
    report = flatpattern.evaluate(part_id)
    development = report["development"]
    inner = development["inner_radius_mm"]
    outer = development["outer_radius_mm"]
    sector = development["sector_angle_deg"]
    drift = development["fibre_angle_drift_deg"]
    envelope = report["stiffness_envelope_over_drift"]

    width = 2.0 * outer + 2.0 * SHEET_MARGIN_MM
    height = 2.0 * outer + 3.0 * SHEET_MARGIN_MM + 30.0
    cx, cy = width / 2.0, SHEET_MARGIN_MM + 25.0 + outer

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}mm" '
        f'height="{height:.1f}mm" viewBox="0 0 {width:.1f} {height:.1f}">',
        f"<style>{STYLE}</style>",
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" fill="#fff"/>',
        f'<text class="title" x="{SHEET_MARGIN_MM:.1f}" y="12">'
        f'{_escape(item.part_id)} {_escape(item.name)} — flat pattern, 1:1</text>',
        f'<text class="small" x="{SHEET_MARGIN_MM:.1f}" y="18">'
        f'developed cone: sector {sector:.1f}°, R{inner:.2f} to R{outer:.2f} mm, '
        f'{development["area_mm2"] / 1e6:.5f} m² per ply, {item.laminate().ply_count} plies</text>',
        _check_line(SHEET_MARGIN_MM, height - SHEET_MARGIN_MM + 8.0),
        f'<path class="cutline" d="{_sector_path(cx, cy, inner, outer, sector)}"/>',
    ]

    # Meridians at the pattern edges and centre, which are what the fibre
    # angle is measured against and what makes the drift visible.
    half = math.radians(sector) / 2.0
    for angle, tag in ((-half, "seam A"), (0.0, "zero mark"), (half, "seam B")):
        x1 = cx + inner * math.sin(angle)
        y1 = cy - inner * math.cos(angle)
        x2 = cx + outer * math.sin(angle)
        y2 = cy - outer * math.cos(angle)
        parts.append(f'<line class="netline" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
        # Push the callout clear of the outline along its own meridian, so a
        # label never sits on top of a line somebody has to cut against.
        lx = cx + (outer + 6.0) * math.sin(angle)
        ly = cy - (outer + 6.0) * math.cos(angle)
        anchor = "middle" if abs(angle) < 1e-9 else ("end" if angle < 0 else "start")
        parts.append(
            f'<text class="small" text-anchor="{anchor}" x="{lx:.2f}" y="{ly:.2f}">{tag}</text>'
        )

    # One straight fibre, drawn as the laminator would lay it, plus the angle
    # it actually makes with the meridian at each seam.
    radius = (inner + outer) / 2.0
    parts.append(
        _fibre_arrow(cx, cy - radius, 45.0, min(outer, 60.0), "fibre as cut: 45° at the zero mark")
    )
    parts.append(
        f'<text class="warn" x="{SHEET_MARGIN_MM:.1f}" y="{height - SHEET_MARGIN_MM - 6:.1f}">'
        f'Fibre angle drifts {drift:.0f}° across this pattern — '
        f'{drift / 2:.0f}° either side of the zero mark.</text>'
    )
    parts.append(
        f'<text class="small" x="{SHEET_MARGIN_MM:.1f}" y="{height - SHEET_MARGIN_MM - 1.5:.1f}">'
        f'This is a property of cones, not of the cutting. The laminate is built '
        f'in-plane isotropic so it does not matter: Ex varies {(envelope["ex_ratio"] - 1) * 100:.0f}% '
        f'over the full drift.</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def rectangle_pattern_svg(part_id: str) -> str:
    """1:1 flat pattern for a developed tube."""

    item = schedule(part_id)
    report = flatpattern.evaluate(part_id)
    development = report["development"]
    pattern_width = development["width_mm"]
    pattern_height = development["height_mm"]

    width = pattern_width + 2.0 * SHEET_MARGIN_MM + 40.0
    height = pattern_height + 3.0 * SHEET_MARGIN_MM
    x0, y0 = SHEET_MARGIN_MM, SHEET_MARGIN_MM + 10.0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}mm" '
        f'height="{height:.1f}mm" viewBox="0 0 {width:.1f} {height:.1f}">',
        f"<style>{STYLE}</style>",
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" fill="#fff"/>',
        f'<text class="title" x="{SHEET_MARGIN_MM:.1f}" y="12">'
        f'{_escape(item.part_id)} {_escape(item.name)} — flat pattern, 1:1 '
        f'(×{item.quantity})</text>',
        f'<text class="small" x="{SHEET_MARGIN_MM:.1f}" y="18">'
        f'developed slit tube: {pattern_width:.2f} × {pattern_height:.0f} mm, '
        f'no fibre-angle drift — a cylinder develops with parallel meridians</text>',
        f'<rect class="cutline" x="{x0:.2f}" y="{y0:.2f}" '
        f'width="{pattern_width:.2f}" height="{pattern_height:.2f}"/>',
        _check_line(SHEET_MARGIN_MM, height - SHEET_MARGIN_MM + 8.0),
    ]
    for fraction in (0.25, 0.75):
        parts.append(
            _fibre_arrow(
                x0 + pattern_width / 2.0,
                y0 + pattern_height * fraction,
                45.0,
                pattern_width * 0.8,
                "45°",
            )
        )
    parts.append(
        f'<text class="small" x="{x0 + pattern_width + 4:.1f}" y="{y0 + 6:.1f}">'
        f'stows rolled to R{item.stow_radius_mm:g} mm</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def layup_sheet_svg(part_id: str) -> str:
    """Stacking sequence, ply by ply, in lay-down order with debulk points."""

    item = schedule(part_id)
    laminate = item.laminate()
    debulks = set(debulk_schedule(laminate.ply_count))

    row_height = 9.0
    width = 190.0
    height = 40.0 + row_height * (laminate.ply_count + 1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}mm" '
        f'height="{height:.1f}mm" viewBox="0 0 {width:.1f} {height:.1f}">',
        f"<style>{STYLE}</style>",
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" fill="#fff"/>',
        f'<text class="title" x="10" y="12">{_escape(item.part_id)} '
        f'{_escape(item.name)} — layup sequence</text>',
        f'<text class="small" x="10" y="18">{_escape(laminate.describe())}, '
        f'{laminate.thickness_mm:.3f} mm nominal, tool side: '
        f'{_escape(item.tool_side)}</text>',
        f'<text class="small" x="10" y="24">lay in this order — ply 1 goes against the '
        f'tool. The design stack is listed top-surface-first and this sheet is its '
        f'reverse, which is the order a laminator works in.</text>',
    ]

    y = 30.0
    parts.append(
        f'<text class="label" x="10" y="{y:.1f}">ply</text>'
        f'<text class="label" x="24" y="{y:.1f}">material</text>'
        f'<text class="label" x="70" y="{y:.1f}">angle</text>'
        f'<text class="label" x="92" y="{y:.1f}">thickness</text>'
        f'<text class="label" x="125" y="{y:.1f}">action after</text>'
    )
    y += 4.0
    # Plies are stored bottom-first, which is tool-side first — the order a
    # laminator lays them.
    for index, ply in enumerate(laminate.plies, start=1):
        row_class = "ply" if index % 2 else "plyalt"
        parts.append(
            f'<rect class="{row_class}" x="10" y="{y:.1f}" width="{width - 20:.1f}" '
            f'height="{row_height - 1:.1f}"/>'
        )
        text_y = y + row_height - 3.5
        action = "DEBULK" if index in debulks else ""
        if index == laminate.ply_count:
            action = "DEBULK, then bag for cure"
        parts.append(
            f'<text class="label" x="12" y="{text_y:.1f}">{index}</text>'
            f'<text class="label" x="24" y="{text_y:.1f}">{_escape(ply.material)}</text>'
            f'<text class="label" x="70" y="{text_y:.1f}">{ply.angle_deg:g}°</text>'
            f'<text class="label" x="92" y="{text_y:.1f}">{ply.thickness:.3f} mm</text>'
            f'<text class="warn" x="125" y="{text_y:.1f}">{action}</text>'
        )
        y += row_height

    y += 5.0
    parts.append(
        f'<text class="warn" x="10" y="{y:.1f}">HOLD POINT — second person verifies '
        f'ply count and every orientation before the bag goes on (PS-300)</text>'
    )
    parts.append(
        f'<text class="small" x="10" y="{y + 4:.1f}">after cure no inspection method '
        f'distinguishes a ply laid at 0° from one laid at 45°</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def generate_outputs(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, dict] = {}

    for part_id, shape in flatpattern.PART_SHAPES.items():
        report = flatpattern.evaluate(part_id)
        if report["development"]["kind"] == "annular_sector":
            svg = cone_pattern_svg(part_id)
        else:
            svg = rectangle_pattern_svg(part_id)
        name = f"{part_id.lower()}_flat_pattern.svg"
        (output_dir / name).write_text(svg, encoding="utf-8")
        written[part_id] = {
            "flat_pattern": name,
            "developed_area_m2": report["developed_area_m2"],
            "fibre_angle_drift_deg": round(report["development"]["fibre_angle_drift_deg"], 2),
            "gores_for_3deg_tolerance": report["gores_for_tolerance"],
            "nesting_utilisation": report["nesting"]["utilisation"],
            "stiffness_ratio_over_drift": report["stiffness_envelope_over_drift"]["ex_ratio"],
        }

    for item in SCHEDULES:
        name = f"{item.part_id.lower()}_layup_sheet.svg"
        (output_dir / name).write_text(layup_sheet_svg(item.part_id), encoding="utf-8")
        entry = written.setdefault(item.part_id, {})
        entry["layup_sheet"] = name
        laminate = item.laminate()
        entry["stack"] = laminate.describe()
        entry["ply_count"] = laminate.ply_count
        entry["thickness_mm"] = round(laminate.thickness_mm, 4)
        entry["debulk_after_plies"] = list(debulk_schedule(laminate.ply_count))

    manifest = {
        "article": "CARRIER-P0 composite ply book",
        "units": "mm",
        "status": (
            "design study; the laminates are sized against handbook lamina data "
            "and no part here is released for a flight article"
        ),
        "check_line_mm": CHECK_LINE_MM,
        "parts": written,
        "notes": [
            "Patterns print 1:1. Measure the check line before cutting anything.",
            "Plies are listed in lay-down order: ply 1 goes against the tool.",
            "The cone's fibre angle drifts with position by construction; the "
            "laminate is built in-plane isotropic so that it does not matter.",
        ],
    }
    (output_dir / "plybook_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    args = parser.parse_args(argv)
    manifest = generate_outputs(args.out_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
