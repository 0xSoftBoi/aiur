#!/usr/bin/env python3
"""Generate the CARRIER-P0 composite tooling package for a machine shop.

This is what a shop needs to quote and cut the moulds: solid geometry for
CAM, a dimensioned sheet per tool carrying tolerances and secondary
operations, and a request-for-quote line per item.

Everything is derived.  The moulding surfaces come from the part geometry in
``aiur.composites.flatpattern`` and ``aiur.composites.schedules``, the
thermal-expansion compensation from ``aiur.composites.tooling``, and the
corner compensation from ``aiur.composites.springin``.  Nothing is drawn by
hand and no dimension is typed twice, so a laminate change cannot leave a
tool drawing behind.

**The single most important thing in this package.**  These tools are
deliberately *not* cut to the part dimensions.  A part is moulded at 180 degC
and inspected at 20 degC, and aluminium moves an order of magnitude more than
the laminate over that range, so a tool cut to the part drawing produces a
part that misses its tolerance by several times the tolerance.  Every
moulding dimension here already carries that compensation, and every sheet
says so in the title block.  A machinist who "corrects" one back to the part
drawing scraps the tool.

Regenerate from the repository root:

    python hardware/composites/tooling/generate_tools.py
    python hardware/composites/tooling/generate_tools.py --check
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script convenience
    sys.path.insert(0, str(REPO_ROOT))

from aiur.composites import flatpattern, springin, tooling
from aiur.composites.schedules import POST_GEL_SHRINKAGE_FRACTION, schedule
from hardware.dock.cad.generate_rev_a import (
    Mesh,
    extrude_polygon,
    lathe,
    validate_mesh,
    write_binary_stl,
)

Vec2 = tuple[float, float]

#: Every tool in this package is cut from the material the trade study in
#: ``aiur.composites.tooling`` selected.  It is imported rather than named so
#: that a trade re-run which changes the answer breaks this file loudly.
TOOL_MATERIAL = tooling.ALUMINIUM_6061
#: Cure temperature the tools are compensated for, degC.
CURE_TEMPERATURE_C = 180.0
#: Temperature the part is inspected at, degC.
INSPECTION_TEMPERATURE_C = 20.0
#: Aluminium density, kg/m^3, for the shipping mass on the RFQ.
ALUMINIUM_DENSITY_KG_M3 = 2700.0

#: Revolve segment count for a surface of revolution.
REVOLVE_SEGMENTS = 240
#: Segments used to approximate a fillet or a crowned surface in a section.
FILLET_SEGMENTS = 24

#: Tolerance classes, mm.  A moulding surface is what the part copies; a
#: datum locates the part or the next operation; a free dimension only has to
#: keep out of the way.  Quoting one tolerance for a whole tool is what makes
#: a tool expensive for no structural return.
TOLERANCE_MOULDING = 0.05
TOLERANCE_DATUM = 0.05
TOLERANCE_FREE = 0.25
#: Angular tolerance on a compensated corner, degrees.  Tighter than the
#: compensation itself, or the compensation is noise.
TOLERANCE_ANGLE_DEG = 0.05
#: Moulding-surface finish, micrometres Ra.  A moulded face is a cast of the
#: tool: it reproduces every tool mark in it, including the ones a machinist
#: would consider cosmetic.
MOULDING_FINISH_RA_UM = 0.4
#: Stock allowance added to the finished envelope on each axis, mm.
STOCK_ALLOWANCE_MM = 6.0

#: The tine's width, mm.  The CS-400 schedule's own edge rationale calls it a
#: 12 mm wide cantilevered strip, and its laminate area divided by this width
#: is the developed length the die has to form.
TINE_WIDTH_MM = 12.0


# --------------------------------------------------------------------------
# Compensation
# --------------------------------------------------------------------------


def cooldown_k() -> float:
    return CURE_TEMPERATURE_C - INSPECTION_TEMPERATURE_C


def part_cte_per_k(part_id: str) -> float:
    """In-plane CTE of the part's laminate, averaged over the two axes."""

    cte = schedule(part_id).laminate().cte_per_k()
    return 0.5 * (cte[0] + cte[1])


def scale_factor(part_id: str) -> float:
    """Uniform scale applied to every moulding dimension of a tool.

    Below one for an aluminium tool against a carbon part: the tool grows
    more on the way up, so it has to start smaller for the part to land on
    nominal on the way down.
    """

    return tooling.compensation_factor(
        part_cte_per_k=part_cte_per_k(part_id),
        tool_cte_per_k=TOOL_MATERIAL.cte_per_k,
        cooldown_k=cooldown_k(),
    )


def corner_compensation_deg(part_id: str, enclosed_angle_deg: float) -> float:
    """Spring-in to be cut open into a moulded corner, degrees.

    The part's corner closes on cooldown, so the tool's is opened by the same
    amount.  A cylindrical section has no enclosed corner and gets none of
    this, which is why the boom mandrel carries a scale factor and nothing
    else.
    """

    thermal, chemical, tool_interaction = springin.spring_in_deg(
        schedule(part_id).laminate(),
        enclosed_angle_deg=enclosed_angle_deg,
        cooldown_k=cooldown_k(),
        shrinkage_fraction=POST_GEL_SHRINKAGE_FRACTION,
    )
    return thermal + chemical + tool_interaction


def registered_corner(part_id: str, feature: str) -> springin.CornerFeature:
    """The corner from the spring-in register, by part and feature.

    Looked up rather than restated so a tool cannot be cut to an angle the
    corner register has stopped agreeing with.
    """

    for corner in springin.CORNERS:
        if corner.part_id == part_id and corner.feature == feature:
            return corner
    raise KeyError(f"{part_id} has no registered corner {feature!r}")


# --------------------------------------------------------------------------
# Tool records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolDimension:
    """One dimension on a tool drawing, carrying where it came from."""

    label: str
    value_mm: float
    tolerance_mm: float
    #: What the dimension is for: "moulding surface", "datum", "sealing",
    #: or "free".  The class is what sets the price.
    feature_class: str
    basis: str
    unit: str = "mm"


@dataclass(frozen=True)
class Tool:
    tool_id: str
    name: str
    part_id: str
    description: str
    #: "female" forms the part's outer surface; "male" its inner.
    mould_type: str
    #: "revolved" sections are (radius, z); "extruded" are (x, y).
    section_kind: str
    section: tuple[Vec2, ...]
    #: Inclusive index range of ``section`` that is the moulding surface.
    moulding_span: tuple[int, int]
    mesh: Mesh
    dimensions: tuple[ToolDimension, ...]
    secondary_operations: tuple[str, ...]
    notes: tuple[str, ...]
    #: Largest chordal deviation between the faceted model and the analytic
    #: surface it approximates, mm.
    faceting_error_mm: float = 0.0

    @property
    def stem(self) -> str:
        return self.tool_id.lower().replace("-", "")

    @property
    def stock_mm(self) -> tuple[float, float, float]:
        low, high = self.mesh.bounds()
        return tuple(
            round(high[axis] - low[axis] + STOCK_ALLOWANCE_MM, 1) for axis in range(3)
        )  # type: ignore[return-value]


def _chordal_error_mm(radius: float, sweep_deg: float, segments: int) -> float:
    """Sagitta of one facet of an arc — how far the model is inside the surface."""

    half = math.radians(sweep_deg) / (2.0 * segments)
    return radius * (1.0 - math.cos(half))


# --------------------------------------------------------------------------
# T-100 — throat cup mould
# --------------------------------------------------------------------------


def throat_cup_tool() -> Tool:
    """Female mould for the CS-100 capture throat cup."""

    cone = flatpattern.PART_SHAPES["CS-100"]
    corner = registered_corner("CS-100", "throat cup cone half-angle")
    scale = scale_factor("CS-100")
    compensation = corner_compensation_deg("CS-100", corner.enclosed_angle_deg)

    # The throat feeds the capture-chain tolerance stack, so it is the
    # dimension that is held; the rim follows from the compensated cone angle
    # rather than being compensated independently and disagreeing with it.
    half_angle = corner.enclosed_angle_deg + compensation
    throat_r = cone.inner_radius_mm * scale
    depth = cone.height_mm * scale
    rim_r = throat_r + depth * math.tan(math.radians(half_angle))

    seal_land = 25.0
    land_margin = 10.0
    base = 15.0
    bore_r = 6.0
    outer_r = rim_r + seal_land + land_margin
    height = base + depth

    # (radius, z), closed.  Every radius is positive: the mould is an annulus
    # about a central bore, which is what a revolved solid needs to be
    # watertight and is also where the demoulding push-rod goes.
    section: tuple[Vec2, ...] = (
        (bore_r, 0.0),
        (outer_r, 0.0),
        (outer_r, height),
        (rim_r, height),
        (throat_r, base),
        (bore_r, base),
    )
    mesh = lathe("t100_throat_cup_mould", list(section), REVOLVE_SEGMENTS)

    return Tool(
        tool_id="T-100",
        name="throat cup mould",
        part_id="CS-100",
        description=(
            "Female mould forming the outer surface of the capture throat cup. "
            "The cavity is the part's aircraft-contact face, so the cavity's "
            "finish is the part's finish."
        ),
        mould_type="female",
        section_kind="revolved",
        section=section,
        moulding_span=(3, 4),
        mesh=mesh,
        dimensions=(
            ToolDimension(
                "cavity throat radius",
                throat_r,
                TOLERANCE_MOULDING,
                "moulding surface",
                f"part throat R{cone.inner_radius_mm:g} x {scale:.6f} thermal scale",
            ),
            ToolDimension(
                "cavity rim radius",
                rim_r,
                TOLERANCE_MOULDING,
                "moulding surface",
                "derived from the held throat and the compensated cone angle",
            ),
            ToolDimension(
                "cavity depth",
                depth,
                TOLERANCE_MOULDING,
                "moulding surface",
                f"part depth {cone.height_mm:g} x {scale:.6f} thermal scale",
            ),
            ToolDimension(
                "cone half-angle",
                half_angle,
                TOLERANCE_ANGLE_DEG,
                "moulding surface",
                f"part {corner.enclosed_angle_deg:g} deg opened by "
                f"{compensation:.3f} deg of predicted spring-in",
                unit="deg",
            ),
            ToolDimension(
                "seal land width",
                seal_land,
                TOLERANCE_FREE,
                "sealing",
                "sealant-tape land outboard of the cavity rim; flat and continuous",
            ),
            ToolDimension(
                "top face flatness",
                0.05,
                TOLERANCE_MOULDING,
                "sealing",
                "flatness of the whole top annulus, not a size",
            ),
            ToolDimension(
                "central bore diameter",
                2 * bore_r,
                TOLERANCE_DATUM,
                "datum",
                "H7; demould push-rod and centring pin, plugged during cure",
            ),
            ToolDimension(
                "outside radius", outer_r, TOLERANCE_FREE, "free", "stock envelope"
            ),
            ToolDimension(
                "overall height",
                height,
                TOLERANCE_FREE,
                "free",
                "base thickness plus cavity depth",
            ),
        ),
        secondary_operations=(
            "2 x 6 H7 dowel holes on a 140 mm bolt circle, 180 deg apart, through "
            "the top annulus into the base — they locate the trim template",
            "4 x M6 x 12 deep tapped in the back face on a 120 mm bolt circle — "
            "handling and fixturing only",
            "1 x 3 wide x 2 deep radial groove across the seal land, outside "
            "diameter to cavity rim — thermocouple route out from under the bag",
            "plug the central bore flush during cure; the plug is shop-supplied",
            "break all edges 0.3 x 45 deg except inside the cavity",
        ),
        notes=(
            "The cavity is a moulding surface. No stamping, scribing, engraving "
            "or witness marks anywhere inside it — the part copies them, and a "
            "copied tool mark on the aircraft-contact face is a reject.",
            "Identification is stamped on the outside diameter only.",
            "The seal land must be flat and continuous. A scratch across it is a "
            "vacuum leak, and a leak during cure makes a porous part that no "
            "inspection afterwards will separate from a good one cheaply.",
            "Machine the cavity with a radial or helical toolpath, not a raster: "
            "a raster leaves a cusp pattern that prints through into a 0.4 mm "
            "laminate.",
        ),
        faceting_error_mm=_chordal_error_mm(outer_r, 360.0, REVOLVE_SEGMENTS),
    )


# --------------------------------------------------------------------------
# T-200 — boom mandrel
# --------------------------------------------------------------------------


def boom_mandrel_tool() -> Tool:
    """Male mandrel for the CS-200 deployable boom."""

    tube = flatpattern.PART_SHAPES["CS-200"]
    laminate = schedule("CS-200").laminate()
    scale = scale_factor("CS-200")

    # The mandrel forms the inner surface, so its crown is the part's
    # mid-surface radius less half the laminate thickness.
    crown_r = (tube.radius_mm - laminate.thickness_mm / 2.0) * scale
    subtended = tube.subtended_angle_deg
    runout = 20.0
    length = tube.length_mm + 2 * runout

    half = math.radians(subtended) / 2.0
    base_half_width = 30.0
    base_depth = 30.0
    centre_y = base_depth - crown_r
    shoulder_y = centre_y + crown_r * math.cos(half)

    section: list[Vec2] = [
        (-base_half_width, 0.0),
        (base_half_width, 0.0),
        (base_half_width, shoulder_y),
    ]
    crown_start = len(section)
    for index in range(FILLET_SEGMENTS + 1):
        angle = half - 2.0 * half * index / FILLET_SEGMENTS
        section.append(
            (crown_r * math.sin(angle), centre_y + crown_r * math.cos(angle))
        )
    crown_end = len(section) - 1
    section.append((-base_half_width, shoulder_y))
    mesh = extrude_polygon("t200_boom_mandrel", section, length)

    return Tool(
        tool_id="T-200",
        name="boom mandrel",
        part_id="CS-200",
        description=(
            "Male mandrel forming the inner surface of the deployable "
            "capture-ring boom. The laminate is laid over the crown and bagged "
            "down onto it."
        ),
        mould_type="male",
        section_kind="extruded",
        section=tuple(section),
        moulding_span=(crown_start, crown_end),
        mesh=mesh,
        dimensions=(
            ToolDimension(
                "crown radius",
                crown_r,
                TOLERANCE_MOULDING,
                "moulding surface",
                f"part mid-surface R{tube.radius_mm:g} less half the "
                f"{laminate.thickness_mm:.3f} mm laminate, x {scale:.6f} thermal scale",
            ),
            ToolDimension(
                "subtended angle",
                subtended,
                0.10,
                "moulding surface",
                "part section angle; a cylindrical section has no enclosed "
                "corner, so no spring-in compensation applies",
                unit="deg",
            ),
            ToolDimension(
                "crown radius form error",
                0.03,
                TOLERANCE_MOULDING,
                "moulding surface",
                "deviation from a true circular arc, checked along the length",
            ),
            ToolDimension(
                "moulding length",
                tube.length_mm,
                TOLERANCE_FREE,
                "moulding surface",
                "part length; the mandrel is longer by the runout at each end",
            ),
            ToolDimension(
                "overall length",
                length,
                TOLERANCE_FREE,
                "free",
                f"part length plus {runout:g} mm runout each end for bag tuck-off",
            ),
            ToolDimension(
                "base width", 2 * base_half_width, TOLERANCE_FREE, "free", "stock envelope"
            ),
            ToolDimension(
                "base depth", base_depth, TOLERANCE_FREE, "free", "stock envelope"
            ),
            ToolDimension(
                "base flatness",
                0.05,
                TOLERANCE_DATUM,
                "datum",
                "the mandrel is located and clamped on its base",
            ),
        ),
        secondary_operations=(
            "2 x 6 H7 dowel holes in the base, 200 mm apart on the centreline — "
            "they locate the mandrel in the layup fixture",
            "2 x M8 through the base for clamping to the bench",
            "blend the crown-to-shoulder transition smoothly; a step there prints "
            "through into a 0.16 mm laminate",
            "break all edges 0.3 x 45 deg except on the crown",
        ),
        notes=(
            "The crown is a moulding surface. Machine it along the length, not "
            "across it: circumferential tool marks transfer into the part and sit "
            "transverse to the direction it is later rolled.",
            "This tool carries a thermal scale factor and no spring-in "
            "compensation, because a cylindrical section has no enclosed corner "
            "to spring in. That is a result, not an omission.",
            "The crown radius is the inner surface. The part's quoted radius is "
            "its mid-surface, and the difference is half a laminate thickness.",
        ),
        faceting_error_mm=_chordal_error_mm(crown_r, subtended, FILLET_SEGMENTS),
    )


# --------------------------------------------------------------------------
# T-300 / T-301 — keeper tine matched dies
# --------------------------------------------------------------------------


def _moulding_face(
    *,
    centre: Vec2,
    radius: float,
    enclosed_angle_deg: float,
    leg_a_mm: float,
    leg_b_mm: float,
) -> list[Vec2]:
    """The L-shaped moulding face of one die half, as a polyline.

    Leg A leaves the corner along +x with the enclosed angle opening upward;
    leg B leaves it at ``enclosed_angle_deg`` from leg A.  Both legs are
    tangent to the fillet by construction rather than by arithmetic, which is
    what makes the matched pair close on a uniform gap: give the two halves
    the same centre and radii differing by one laminate thickness, and every
    point of one face is exactly that thickness from the other.

    Returned from the free end of leg A, over the corner, to the free end of
    leg B.
    """

    theta = math.radians(enclosed_angle_deg)
    # Tangent points: the fillet touches leg A directly below the centre and
    # leg B along the inward normal of leg B.
    normal_b = (math.sin(theta), -math.cos(theta))
    t1 = (centre[0], centre[1] - radius)
    t2 = (centre[0] - radius * normal_b[0], centre[1] - radius * normal_b[1])

    direction_a = (1.0, 0.0)
    direction_b = (math.cos(theta), math.sin(theta))
    a_end = (t1[0] + direction_a[0] * leg_a_mm, t1[1] + direction_a[1] * leg_a_mm)
    b_end = (t2[0] + direction_b[0] * leg_b_mm, t2[1] + direction_b[1] * leg_b_mm)

    sweep = math.radians(180.0 - enclosed_angle_deg)
    start_angle = -math.pi / 2.0
    arc = [
        (
            centre[0] + radius * math.cos(start_angle - sweep * index / FILLET_SEGMENTS),
            centre[1] + radius * math.sin(start_angle - sweep * index / FILLET_SEGMENTS),
        )
        for index in range(FILLET_SEGMENTS + 1)
    ]
    return [a_end, *arc, b_end]


def tine_die_tools() -> tuple[Tool, Tool]:
    """T-300 / T-301: the matched die set for the CS-400 keeper tine."""

    item = schedule("CS-400")
    laminate = item.laminate()
    thickness = laminate.thickness_mm
    scale = scale_factor("CS-400")
    corner = registered_corner("CS-400", "tine root bend")
    compensation = corner_compensation_deg("CS-400", corner.enclosed_angle_deg)
    enclosed = corner.enclosed_angle_deg + compensation

    # The inner radius is set by the laminate, not by preference: a corner
    # tighter than about two thicknesses thins the outer plies and wrinkles
    # the inner ones.
    inner_radius = max(2.0 * thickness, 3.0) * scale
    outer_radius = inner_radius + thickness

    # The developed length the die has to form is the schedule's own laminate
    # area over the tine width, so a laminate area change moves the die.
    developed_mm = item.area_m2 * 1e6 / TINE_WIDTH_MM * scale
    arc_mm = math.radians(180.0 - enclosed) * (inner_radius + thickness / 2.0)
    straight_mm = developed_mm - arc_mm
    leg_a = 0.60 * straight_mm
    leg_b = straight_mm - leg_a

    width = TINE_WIDTH_MM * scale + 16.0
    back = 18.0

    # One centre for both halves. The cavity's apex sits at the origin, which
    # puts its leg-A face on y = 0.
    half = math.radians(enclosed) / 2.0
    centre = (outer_radius / math.tan(half), outer_radius)

    cavity_face = _moulding_face(
        centre=centre,
        radius=outer_radius,
        enclosed_angle_deg=enclosed,
        leg_a_mm=leg_a,
        leg_b_mm=leg_b,
    )
    punch_face = _moulding_face(
        centre=centre,
        radius=inner_radius,
        enclosed_angle_deg=enclosed,
        leg_a_mm=leg_a,
        leg_b_mm=leg_b,
    )

    # The cavity is a rectangular block with the L cut out of it: the face,
    # then out to the top-left corner, down the left side and along the base.
    cavity_section = [
        *cavity_face,
        (-back, cavity_face[-1][1]),
        (-back, -back),
        (cavity_face[0][0], -back),
    ]
    # The punch is the solid inside the L: the face, closed off by a back that
    # sits clear of the cavity's walls.
    punch_section = [
        *punch_face,
        (punch_face[0][0], punch_face[-1][1]),
    ]

    cavity_mesh = extrude_polygon("t300_tine_die_cavity", cavity_section, width)
    punch_mesh = extrude_polygon("t301_tine_die_punch", punch_section, width)

    shared_notes = (
        "Matched pair. The gap between the two moulding faces IS the part "
        f"thickness, {thickness:.3f} mm nominal, and it is the dimension that "
        "matters more than either half on its own: cut both, close them dry, "
        "and shim-check the gap before either half is accepted.",
        "The enclosed corner is cut open by the predicted spring-in. Do not "
        "correct it back to 90 degrees.",
        "Bore the dowels and the closing-bolt holes with the two halves "
        "clamped together as a set, so they close in register.",
        "The solid model carries the moulding geometry and the block envelope. "
        "Dowel, bolt and thermocouple features are listed as secondary "
        "operations and are not in the model.",
    )

    cavity = Tool(
        tool_id="T-300",
        name="keeper tine die — cavity half",
        part_id="CS-400",
        description=(
            "Cavity half of the matched die set, forming the outer surface of "
            "the keeper tine. The tine is the retention path, so both of its "
            "faces are tooled and neither is left to a vacuum bag."
        ),
        mould_type="female",
        section_kind="extruded",
        section=tuple(cavity_section),
        moulding_span=(0, len(cavity_face) - 1),
        mesh=cavity_mesh,
        dimensions=(
            ToolDimension(
                "enclosed corner angle",
                enclosed,
                TOLERANCE_ANGLE_DEG,
                "moulding surface",
                f"part {corner.enclosed_angle_deg:g} deg opened by "
                f"{compensation:.3f} deg of predicted spring-in",
                unit="deg",
            ),
            ToolDimension(
                "outer corner radius",
                outer_radius,
                TOLERANCE_MOULDING,
                "moulding surface",
                "inner radius plus one laminate thickness",
            ),
            ToolDimension(
                "blade leg length",
                leg_a,
                TOLERANCE_FREE,
                "moulding surface",
                "60 % of the developed length from the CS-400 laminate area",
            ),
            ToolDimension(
                "root leg length",
                leg_b,
                TOLERANCE_FREE,
                "moulding surface",
                "the remainder of the developed length",
            ),
            ToolDimension(
                "die width", width, TOLERANCE_FREE, "free", "tine width plus margin"
            ),
            ToolDimension(
                "back thickness", back, TOLERANCE_FREE, "free", "block envelope"
            ),
        ),
        secondary_operations=(
            "2 x 8 H7 dowel holes through the back, bored as a set with T-301",
            "4 x M8 through for the closing bolts, clear of the moulding face",
            "1 x 3 wide x 2 deep thermocouple groove in the back face, breaking "
            "out at the die edge",
            "break all edges 0.3 x 45 deg except on the moulding face",
        ),
        notes=shared_notes,
        faceting_error_mm=_chordal_error_mm(
            outer_radius, 180.0 - enclosed, FILLET_SEGMENTS
        ),
    )

    punch = Tool(
        tool_id="T-301",
        name="keeper tine die — punch half",
        part_id="CS-400",
        description=(
            "Punch half of the matched die set; forms the inner surface of the "
            "keeper tine and carries the closing load into the laminate."
        ),
        mould_type="male",
        section_kind="extruded",
        section=tuple(punch_section),
        moulding_span=(0, len(punch_face) - 1),
        mesh=punch_mesh,
        dimensions=(
            ToolDimension(
                "enclosed corner angle",
                enclosed,
                TOLERANCE_ANGLE_DEG,
                "moulding surface",
                "matches T-300; the pair is cut to one angle",
                unit="deg",
            ),
            ToolDimension(
                "inner corner radius",
                inner_radius,
                TOLERANCE_MOULDING,
                "moulding surface",
                f"max(2 x laminate thickness, 3.0) x {scale:.6f} thermal scale",
            ),
            ToolDimension(
                "closed gap to T-300",
                thickness,
                0.03,
                "moulding surface",
                "the part thickness; verify by shim with the pair closed dry",
            ),
            ToolDimension(
                "blade leg length", leg_a, TOLERANCE_FREE, "moulding surface", "matches T-300"
            ),
            ToolDimension(
                "root leg length", leg_b, TOLERANCE_FREE, "moulding surface", "matches T-300"
            ),
            ToolDimension("die width", width, TOLERANCE_FREE, "free", "matches T-300"),
        ),
        secondary_operations=(
            "dowel and closing-bolt holes bored as a set with T-300",
            "break all edges 0.3 x 45 deg except on the moulding face",
        ),
        notes=shared_notes,
        faceting_error_mm=_chordal_error_mm(
            inner_radius, 180.0 - enclosed, FILLET_SEGMENTS
        ),
    )
    return cavity, punch


def tools() -> list[Tool]:
    cavity, punch = tine_die_tools()
    return [throat_cup_tool(), boom_mandrel_tool(), cavity, punch]


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

SHEET_W = 1240.0
#: The sheet is a real A3 landscape page, 420 x 297 mm, drawn in a unit grid
#: of four units per millimetre.  Fixing the physical size is what lets the
#: sheet claim a scale ratio: "2:1" on a page whose size is undefined means
#: nothing, and a shop that scales a print off it would be working to a lie.
SHEET_MM = (420.0, 297.0)
UNITS_PER_MM = 4.0
SHEET_W = SHEET_MM[0] * UNITS_PER_MM
SHEET_H = SHEET_MM[1] * UNITS_PER_MM
#: Standard drawing scales, largest first.  A sheet is drawn at the largest
#: one that fits, so a shop reads a ratio it recognises instead of 3.47:1.
SCALE_LADDER = (5.0, 4.0, 2.5, 2.0, 1.0, 0.5, 0.25, 0.2, 0.1)
#: The view the section is fitted into, in sheet units: x0, y0, x1, y1.
VIEW_BOX = (64.0, 216.0, 660.0, 544.0)
#: Vertical pitch of a wrapped body line, sheet units.
LINE = 18.0

SHEET_STYLE = """
  .t{font:700 26px system-ui,sans-serif;fill:#111827}
  .h{font:700 13px system-ui,sans-serif;fill:#111827;letter-spacing:0.04em}
  .s{font:500 12.5px system-ui,sans-serif;fill:#4b5563}
  .l{font:600 12.5px system-ui,sans-serif;fill:#111827}
  .m{font:600 12.5px ui-monospace,SFMono-Regular,Menlo,monospace;fill:#111827}
  .w{font:700 14px system-ui,sans-serif;fill:#b91c1c}
  .body{stroke:#111827;stroke-width:2;fill:#eef2f7;stroke-linejoin:round}
  .mould{stroke:#b91c1c;stroke-width:3.2;fill:none;stroke-linejoin:round;stroke-linecap:round}
  .dim{stroke:#263238;stroke-width:1.2;fill:none;marker-start:url(#a);marker-end:url(#a)}
  .ext{stroke:#9ca3af;stroke-width:1}
  .ax{stroke:#9ca3af;stroke-width:1.2;stroke-dasharray:12 4 3 4}
  .rule{stroke:#d1d5db;stroke-width:1}
  .frame{stroke:#111827;stroke-width:1.6;fill:none}
"""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("—", "&#8212;")
        .replace("Ø", "&#216;")
        .replace("°", "&#176;")
        .replace("³", "&#179;")
    )


def _wrap(text: str, width: int, hanging: str = "") -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = hanging + word
        else:
            current = candidate
    lines.append(current)
    return lines


def _paragraph(text: str, x: float, y: float, width: int, css: str = "s") -> tuple[str, float]:
    """Left-aligned wrapped text.  Returns the markup and the baseline it ended on."""

    out = []
    offset = y
    for index, line in enumerate(_wrap(text, width)):
        offset = y + LINE * index
        out.append(f'<text x="{x:.0f}" y="{offset:.0f}" class="{css}">{_escape(line)}</text>')
    return "".join(out), offset


def _list_block(
    title: str, entries: Sequence[str], x: float, y: float, width: int
) -> tuple[str, float]:
    out = [f'<text x="{x:.0f}" y="{y:.0f}" class="h">{title}</text>']
    offset = y + 8
    for index, entry in enumerate(entries, start=1):
        for line in _wrap(f"{index}. {entry}", width, hanging="    "):
            offset += LINE
            out.append(f'<text x="{x:.0f}" y="{offset:.0f}" class="s">{_escape(line)}</text>')
        offset += 6
    return "".join(out), offset


def _sections(tool: Tool) -> tuple[list[tuple[list[Vec2], tuple[int, int]]], bool]:
    """The closed outlines the sheet draws, each with its moulding span.

    A revolved tool sections into *two* disjoint regions, one either side of
    the axis, because the solid is an annulus about a central bore.  Drawing
    them as one polygon would close the bore up and show solid metal where
    the push-rod goes, which is exactly the kind of quiet lie a generated
    drawing exists to make impossible.
    """

    start, end = tool.moulding_span
    if tool.section_kind != "revolved":
        return [(list(tool.section), (start, end))], False

    right = [(radius, z) for radius, z in tool.section]
    left = [(-radius, z) for radius, z in reversed(tool.section)]
    count = len(tool.section)
    return [
        (left, (count - 1 - end, count - 1 - start)),
        (right, (start, end)),
    ], True


def _fit(points: Sequence[Vec2]) -> tuple[float, float, float]:
    """Pick a standard scale and the origin that centres the view.

    The returned scale is a true drawing ratio: millimetres on the printed
    page per millimetre of tool.
    """

    x0, y0, x1, y1 = VIEW_BOX
    low_x = min(point[0] for point in points)
    low_y = min(point[1] for point in points)
    span_x = max(point[0] for point in points) - low_x
    span_y = max(point[1] for point in points) - low_y

    ratio = SCALE_LADDER[-1]
    for candidate in SCALE_LADDER:
        drawn_x = span_x * candidate * UNITS_PER_MM
        drawn_y = span_y * candidate * UNITS_PER_MM
        if drawn_x <= (x1 - x0) and drawn_y <= (y1 - y0):
            ratio = candidate
            break

    units = ratio * UNITS_PER_MM
    origin_x = x0 + ((x1 - x0) - span_x * units) / 2.0 - low_x * units
    origin_y = y0 + ((y1 - y0) + span_y * units) / 2.0 + low_y * units
    return ratio, origin_x, origin_y


def _dimension_table(tool: Tool, x: float, y: float) -> tuple[str, float]:
    columns = (0.0, 500.0, 620.0, 700.0)
    out = [
        f'<text x="{x + columns[0]:.0f}" y="{y:.0f}" class="h">DIMENSION</text>'
        f'<text x="{x + columns[1]:.0f}" y="{y:.0f}" class="h">VALUE</text>'
        f'<text x="{x + columns[2]:.0f}" y="{y:.0f}" class="h">TOL</text>'
        f'<text x="{x + columns[3]:.0f}" y="{y:.0f}" class="h">CLASS</text>'
        f'<line x1="{x:.0f}" y1="{y + 10:.0f}" x2="{x + 820:.0f}" y2="{y + 10:.0f}" class="rule"/>'
    ]
    offset = y + 10
    for dimension in tool.dimensions:
        offset += 24
        out.append(
            f'<text x="{x + columns[0]:.0f}" y="{offset:.0f}" class="l">'
            f"{_escape(dimension.label)}</text>"
            f'<text x="{x + columns[1]:.0f}" y="{offset:.0f}" class="m">'
            f"{dimension.value_mm:.3f} {dimension.unit}</text>"
            f'<text x="{x + columns[2]:.0f}" y="{offset:.0f}" class="m">'
            f"&#177;{dimension.tolerance_mm:g}</text>"
            f'<text x="{x + columns[3]:.0f}" y="{offset:.0f}" class="s">'
            f"{dimension.feature_class}</text>"
        )
        for line in _wrap(dimension.basis, 74):
            offset += 16
            out.append(
                f'<text x="{x + columns[0]:.0f}" y="{offset:.0f}" class="s">'
                f"{_escape(line)}</text>"
            )
    return "".join(out), offset


def _linear_dimension(a: Vec2, b: Vec2, label: str, *, vertical: bool) -> str:
    """An arrowed dimension line between two placed points, with its text."""

    if vertical:
        text_x, text_y = a[0] + 10, (a[1] + b[1]) / 2.0
        anchor = "start"
    else:
        text_x, text_y = (a[0] + b[0]) / 2.0, a[1] + 20
        anchor = "middle"
    return (
        f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" class="dim"/>'
        f'<text x="{text_x:.1f}" y="{text_y:.1f}" class="m" text-anchor="{anchor}">'
        f"{_escape(label)}</text>"
    )


def sheet(tool: Tool) -> str:
    regions, is_revolved = _sections(tool)
    every_point = [point for region, _ in regions for point in region]
    ratio, ox, oy = _fit(every_point)
    units = ratio * UNITS_PER_MM

    def place(point: Vec2) -> Vec2:
        return (ox + point[0] * units, oy - point[1] * units)

    outlines = []
    for region, span in regions:
        body = " ".join(f"{x:.2f},{y:.2f}" for x, y in (place(p) for p in region))
        outlines.append(f'<polygon points="{body}" class="body"/>')
        face = " ".join(
            f"{x:.2f},{y:.2f}"
            for x, y in (place(p) for p in region[span[0] : span[1] + 1])
        )
        outlines.append(f'<polyline points="{face}" class="mould"/>')

    axis = ""
    if is_revolved:
        axis_x = place((0.0, 0.0))[0]
        axis = (
            f'<line x1="{axis_x:.1f}" y1="{VIEW_BOX[1] - 18:.0f}" x2="{axis_x:.1f}" '
            f'y2="{VIEW_BOX[3] + 18:.0f}" class="ax"/>'
        )

    # Two overall dimensions on the view. Everything else lives in the table,
    # where it carries a tolerance, a feature class and the basis it came from.
    low_x = min(point[0] for point in every_point)
    high_x = max(point[0] for point in every_point)
    low_y = min(point[1] for point in every_point)
    high_y = max(point[1] for point in every_point)
    width_label = ("Ø" if is_revolved else "") + f"{high_x - low_x:.2f}"
    dimension_y = VIEW_BOX[3] + 30
    dims = _linear_dimension(
        (place((low_x, low_y))[0], dimension_y),
        (place((high_x, low_y))[0], dimension_y),
        width_label,
        vertical=False,
    ) + _linear_dimension(
        (VIEW_BOX[2] + 26, place((high_x, high_y))[1]),
        (VIEW_BOX[2] + 26, place((high_x, low_y))[1]),
        f"{high_y - low_y:.2f}",
        vertical=True,
    )

    table_x = 744.0
    table, table_bottom = _dimension_table(tool, table_x, VIEW_BOX[1])

    finish = (
        f"{TOOL_MATERIAL.name}, T651 tooling plate. Rough, stress relieve, then "
        f"finish — machining rolled plate releases residual stress, and a tool "
        f"that moves after finishing has to be cut again.",
        f"Moulding surface {MOULDING_FINISH_RA_UM:g} Ra; all other machined faces "
        f"1.6 Ra.",
        f"Service: {CURE_TEMPERATURE_C + 20:.0f} degC under 690 kPa, repeatedly.",
        f"Model faceting lies inside the true surface by "
        f"{tool.faceting_error_mm * 1000:.0f} micrometres. Where the model and this "
        f"table disagree, the table governs.",
    )
    finish_markup = [
        f'<text x="{table_x:.0f}" y="{table_bottom + 46:.0f}" class="h">'
        "MATERIAL, FINISH AND SERVICE</text>"
    ]
    finish_bottom = table_bottom + 46
    for entry in finish:
        for line in _wrap(entry, 92):
            finish_bottom += LINE
            finish_markup.append(
                f'<text x="{table_x:.0f}" y="{finish_bottom:.0f}" class="s">'
                f"{_escape(line)}</text>"
            )

    description, description_bottom = _paragraph(
        tool.description, VIEW_BOX[0], dimension_y + 50, 78
    )
    low, high = tool.mesh.bounds()
    envelope = " x ".join(f"{high[axis] - low[axis]:.1f}" for axis in range(3))
    envelope_line = (
        f'<text x="{VIEW_BOX[0]:.0f}" y="{description_bottom + 26:.0f}" class="l">'
        f"Finished envelope {envelope} mm &#8212; stock {tool.stock_mm[0]:.0f} x "
        f"{tool.stock_mm[1]:.0f} x {tool.stock_mm[2]:.0f} mm &#8212; "
        f"{tool.mesh.volume_mm3() / 1000.0:.0f} cm&#179; finished.</text>"
    )

    band = max(description_bottom + 26, finish_bottom) + 48
    operations, operations_bottom = _list_block(
        "SECONDARY OPERATIONS", tool.secondary_operations, VIEW_BOX[0], band, 74
    )
    notes, notes_bottom = _list_block("NOTES", tool.notes, table_x, band, 74)

    footer = SHEET_H - 44
    overflow = max(operations_bottom, notes_bottom) - (footer - 30)
    if overflow > 0:
        raise ValueError(
            f"{tool.tool_id}: sheet content runs {overflow:.0f} units past the "
            "frame; shorten the notes or move to a larger sheet"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_MM[0]:.0f}mm" height="{SHEET_MM[1]:.0f}mm" viewBox="0 0 {SHEET_W:.0f} {SHEET_H:.0f}">
  <defs>
    <marker id="a" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#263238"/>
    </marker>
    <style>{SHEET_STYLE}</style>
  </defs>
  <rect width="{SHEET_W:.0f}" height="{SHEET_H:.0f}" fill="#fff"/>
  <rect x="40" y="40" width="{SHEET_W - 80:.0f}" height="{SHEET_H - 80:.0f}" class="frame"/>
  <text x="{VIEW_BOX[0]:.0f}" y="100" class="t">CARRIER-P0 TOOLING &#8212; {tool.tool_id} {_escape(tool.name.upper())}</text>
  <text x="{VIEW_BOX[0]:.0f}" y="128" class="s">MOULDS {tool.part_id} &#8212; {tool.mould_type.upper()} MOULD &#8212; A3 SHEET, DIMENSIONS IN mm &#8212; GENERATED FROM generate_tools.py</text>
  <text x="{VIEW_BOX[0]:.0f}" y="164" class="w">MOULDING DIMENSIONS ARE COMPENSATED. SCALE FACTOR {scale_factor(tool.part_id):.6f} APPLIED. DO NOT WORK TO THE PART DRAWING.</text>
  <text x="{VIEW_BOX[0]:.0f}" y="198" class="h">SECTION &#8212; MOULDING SURFACE IN RED &#8212; DRAWN AT {ratio:g}:1</text>
  {axis}
  {"".join(outlines)}
  {dims}
  {description}
  {envelope_line}
  {table}
  {"".join(finish_markup)}
  {operations}
  {notes}
  <line x1="{VIEW_BOX[0]:.0f}" y1="{footer - 22:.0f}" x2="{SHEET_W - VIEW_BOX[0]:.0f}" y2="{footer - 22:.0f}" class="rule"/>
  <text x="{VIEW_BOX[0]:.0f}" y="{footer:.0f}" class="s">The solid model {tool.stem}.stl is the master geometry. This sheet carries tolerances, feature classes, secondary operations and notes &#8212; it does not redefine the surface.</text>
</svg>
"""


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------


def _stock_volume_cm3(tool: Tool) -> float:
    stock = tool.stock_mm
    return stock[0] * stock[1] * stock[2] / 1000.0


def rfq_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for tool in tools():
        finished_cm3 = tool.mesh.volume_mm3() / 1000.0
        stock_cm3 = _stock_volume_cm3(tool)
        rows.append(
            {
                "item": tool.tool_id,
                "description": f"{tool.name} for {tool.part_id}",
                "quantity": 1,
                "material": "aluminium 6061-T651 tooling plate, stress relieved",
                "stock_mm": " x ".join(f"{value:.0f}" for value in tool.stock_mm),
                "stock_volume_cm3": round(stock_cm3, 1),
                "finished_volume_cm3": round(finished_cm3, 1),
                "removal_fraction": round(1.0 - finished_cm3 / stock_cm3, 3),
                "finished_mass_kg": round(
                    finished_cm3 * ALUMINIUM_DENSITY_KG_M3 / 1e6, 2
                ),
                "moulding_tolerance_mm": TOLERANCE_MOULDING,
                "moulding_finish_ra_um": MOULDING_FINISH_RA_UM,
                "free_tolerance_mm": TOLERANCE_FREE,
                "model_file": f"{tool.stem}.stl",
                "drawing_file": f"{tool.stem}_sheet.svg",
                "inspection_deliverable": (
                    "CMM report on every dimension classed as a moulding surface "
                    "or datum; surface-finish witness on the moulding face"
                ),
                "note": "compensated geometry — do not work to the part drawing",
            }
        )
    return rows


def manifest() -> dict[str, object]:
    entries = []
    for tool in tools():
        low, high = tool.mesh.bounds()
        entries.append(
            {
                "tool_id": tool.tool_id,
                "name": tool.name,
                "part_id": tool.part_id,
                "description": tool.description,
                "mould_type": tool.mould_type,
                "mould_scale_factor": round(scale_factor(tool.part_id), 8),
                "dimensions": [asdict(dimension) for dimension in tool.dimensions],
                "secondary_operations": list(tool.secondary_operations),
                "notes": list(tool.notes),
                "stl": f"{tool.stem}.stl",
                "drawing": f"{tool.stem}_sheet.svg",
                "stock_mm": list(tool.stock_mm),
                "triangles": len(tool.mesh.triangles),
                "bounds_mm": {
                    "min": [round(value, 3) for value in low],
                    "max": [round(value, 3) for value in high],
                },
                "finished_volume_cm3": round(tool.mesh.volume_mm3() / 1000.0, 2),
                "faceting_error_mm": round(tool.faceting_error_mm, 5),
                "degenerate_faces": tool.mesh.degenerate_faces(),
                "nonmanifold_edges": tool.mesh.nonmanifold_edges(),
            }
        )

    return {
        "package": "CARRIER-P0 composite tooling",
        "units": "mm",
        "status": (
            "design study; the laminates these tools mould are sized against "
            "handbook lamina data and hold no measured allowables"
        ),
        "material": TOOL_MATERIAL.name,
        "cure_temperature_c": CURE_TEMPERATURE_C,
        "inspection_temperature_c": INSPECTION_TEMPERATURE_C,
        "cooldown_k": cooldown_k(),
        "tolerances_mm": {
            "moulding_surface": TOLERANCE_MOULDING,
            "datum": TOLERANCE_DATUM,
            "free": TOLERANCE_FREE,
        },
        "corner_tolerance_deg": TOLERANCE_ANGLE_DEG,
        "moulding_finish_ra_um": MOULDING_FINISH_RA_UM,
        "compensation": {
            "why": (
                "The tool defines the part at cure temperature and the part is "
                "inspected at room temperature. Aluminium moves an order of "
                "magnitude more than the laminate over that range, so a tool cut "
                "to the part drawing makes a part that misses its tolerance."
            ),
            "scale_factors": {
                part_id: round(scale_factor(part_id), 8)
                for part_id in ("CS-100", "CS-200", "CS-400")
            },
            "spring_in_deg": {
                f"{corner.part_id} {corner.feature}": round(
                    corner_compensation_deg(corner.part_id, corner.enclosed_angle_deg), 4
                )
                for corner in springin.CORNERS
            },
        },
        "tools": entries,
        "notes": [
            "The STL is the master geometry. The sheets carry tolerances, "
            "feature classes, secondary operations and notes, not a "
            "redefinition of the surface.",
            "Every moulding dimension is compensated. A machinist who corrects "
            "one back to the part drawing scraps the tool.",
            "Rough, stress relieve, then finish. Machining a tool out of rolled "
            "plate releases residual stress, and a tool that moves after "
            "finishing has to be cut again.",
            "Dowel, tapped and thermocouple features are listed as secondary "
            "operations and are not in the solid models.",
        ],
    }


def artifacts() -> dict[str, bytes]:
    """Every file in the package, keyed by name, as bytes.

    Built in memory so ``--check`` can compare against what is committed
    without writing anything.
    """

    output: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory() as scratch:
        stl = Path(scratch) / "tool.stl"
        for tool in tools():
            validate_mesh(tool.mesh)
            write_binary_stl(tool.mesh, stl, revision=tool.tool_id)
            output[f"{tool.stem}.stl"] = stl.read_bytes()
            output[f"{tool.stem}_sheet.svg"] = sheet(tool).encode("utf-8")

    rows = rfq_rows()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    output["rfq.csv"] = buffer.getvalue().encode("utf-8")

    output["tooling_manifest.json"] = (
        json.dumps(manifest(), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return output


def generate_outputs(output_dir: Path) -> dict[str, bytes]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = artifacts()
    for name, payload in files.items():
        (output_dir / name).write_bytes(payload)
    return files


def check_outputs(output_dir: Path) -> list[str]:
    stale: list[str] = []
    for name, payload in artifacts().items():
        path = output_dir / name
        if not path.exists() or path.read_bytes() != payload:
            stale.append(name)
    return stale


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir", type=Path, default=Path(__file__).resolve().parent / "generated"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed package is stale, without writing",
    )
    args = parser.parse_args(argv)

    if args.check:
        stale = check_outputs(args.out_dir)
        if stale:
            print(
                "stale tooling package: "
                + ", ".join(stale)
                + "\nrun python hardware/composites/tooling/generate_tools.py"
            )
            return 1
        print(f"{args.out_dir} is current")
        return 0

    files = generate_outputs(args.out_dir)
    for tool in tools():
        low, high = tool.mesh.bounds()
        print(
            f"{tool.tool_id} {tool.name}: {len(tool.mesh.triangles)} triangles, "
            f"{tool.mesh.volume_mm3() / 1000.0:.1f} cm3 finished, stock "
            + " x ".join(f"{value:.0f}" for value in tool.stock_mm)
            + " mm"
        )
    print(f"wrote {len(files)} files to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
