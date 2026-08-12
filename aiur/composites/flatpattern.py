"""Flat-pattern development and what it does to fibre direction.

A ply is cut flat and ends up on a curved part.  For the developable
surfaces in this program — a cone and a slit tube — that mapping is exact:
no stretching, no shearing, no darts.  What it is *not* is angle-preserving
with respect to the part, and that distinction is the reason this module
exists.

**On a cone, a straight fibre does not hold a constant angle.**  Develop a
cone and its meridians become radial lines fanning out from the apex.  A ply
cut with straight fibres has one fixed direction in the flat pattern, so the
angle between that fibre and the local meridian changes by exactly one degree
for every degree of sector angle traversed.  The throat cup's development
spans 255 degrees, so a ply nominally at 45 degrees is at 45 degrees in one
place and at every other angle somewhere else on the same part.

This is not a defect to be fixed by better cutting.  It is a property of
cones, and there are only three responses:

1. cut the part from many narrow gores, so each gore's drift is small — 43
   gores for a 3-degree tolerance on this part, which is absurd;
2. accept a fibre angle that varies and design a laminate that does not care;
3. use a different geometry.

The throat cup takes the second route, and this module is what makes it a
decision rather than an oversight: :func:`rotational_envelope` measures how
much a laminate's stiffness changes when the whole stack is rotated, which
is exactly what drift does to it.  The original five-ply throat cup varied
by 47 % in ``Ex`` around its own circumference.  The stack that shipped
varies by 7 %, and the residual 7 % is entirely the two glass plies, which
sit at 45 degrees with nothing at 0 to balance them.

A slit tube has no such problem: a cylinder's development has parallel
meridians, so the drift is zero. That is worth knowing before assuming the
cone's answer generalises.

Secondary outputs, both of which cost real money in a prepreg shop:

* **nesting utilisation** — an annular sector nests badly against a
  rectangular roll, and prepreg is bought by the metre;
* **seam stagger** — splices in adjacent plies must be offset, or the joint
  becomes a through-thickness weakness rather than a local one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math

from .clt import Laminate, Ply

#: Fibre angle tolerance the program would like to hold on a moulded ply.
#: Engineering target; DOE-4 measures what is achievable on a flat pattern,
#: and this module shows that a cone defeats it by geometry regardless.
FIBRE_ANGLE_TOLERANCE_DEG = 3.0

#: Minimum offset between splices in adjacent plies, mm.  A splice is a local
#: discontinuity; splices stacked on top of each other are a through-thickness
#: one, which is a different and much worse thing.
MIN_SEAM_STAGGER_MM = 25.0

#: Prepreg roll width the shop buys, mm.
ROLL_WIDTH_MM = 1000.0


# --------------------------------------------------------------------------
# Shapes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ConeFrustum:
    """A truncated cone: the throat cup, and most funnel geometry."""

    inner_radius_mm: float
    outer_radius_mm: float
    height_mm: float

    def __post_init__(self) -> None:
        if self.inner_radius_mm <= 0 or self.outer_radius_mm <= 0:
            raise ValueError("radii must be positive")
        if self.height_mm <= 0:
            raise ValueError("height must be positive")
        if self.outer_radius_mm <= self.inner_radius_mm:
            raise ValueError("outer radius must exceed inner; a cylinder is a SlitTube")

    @property
    def slant_mm(self) -> float:
        return math.hypot(self.outer_radius_mm - self.inner_radius_mm, self.height_mm)

    @property
    def half_angle_deg(self) -> float:
        """Cone half-angle measured from the axis."""

        return math.degrees(
            math.asin((self.outer_radius_mm - self.inner_radius_mm) / self.slant_mm)
        )

    @property
    def lateral_area_mm2(self) -> float:
        return math.pi * (self.inner_radius_mm + self.outer_radius_mm) * self.slant_mm


@dataclass(frozen=True)
class SlitTube:
    """A tube open along one generator: the deployable boom's section."""

    radius_mm: float
    subtended_angle_deg: float
    length_mm: float

    def __post_init__(self) -> None:
        if self.radius_mm <= 0 or self.length_mm <= 0:
            raise ValueError("radius and length must be positive")
        if not 0.0 < self.subtended_angle_deg < 360.0:
            raise ValueError("subtended angle must be in (0, 360)")

    @property
    def developed_width_mm(self) -> float:
        return self.radius_mm * math.radians(self.subtended_angle_deg)

    @property
    def lateral_area_mm2(self) -> float:
        return self.developed_width_mm * self.length_mm


@dataclass(frozen=True)
class Development:
    """A shape flattened, plus what flattening did to fibre direction."""

    kind: str
    area_mm2: float
    #: Sector geometry, populated for a cone.
    sector_angle_deg: float
    inner_radius_mm: float
    outer_radius_mm: float
    #: Rectangle geometry, populated for a tube.
    width_mm: float
    height_mm: float
    #: Bounding box of the flat pattern, mm.
    bounding_box_mm: tuple[float, float]
    #: Angle between a straight fibre and the local meridian, from one end of
    #: the pattern to the other.  Zero for any development whose meridians
    #: stay parallel.
    fibre_angle_drift_deg: float


def develop(shape: ConeFrustum | SlitTube) -> Development:
    """Flatten a developable shape exactly.

    For a cone the development is an annular sector.  The sector angle is
    ``2 pi sin(alpha)``, which is what makes the arc at each developed radius
    equal the circumference it came from — and what makes the developed area
    equal the lateral area exactly, which is the check worth running.
    """

    if isinstance(shape, ConeFrustum):
        sine = (shape.outer_radius_mm - shape.inner_radius_mm) / shape.slant_mm
        inner = shape.inner_radius_mm / sine
        outer = shape.outer_radius_mm / sine
        sector = 2.0 * math.pi * sine
        area = 0.5 * sector * (outer * outer - inner * inner)
        # Bounding box of an annular sector, taken conservatively as the
        # square that contains the full outer circle when the sector wraps
        # more than half a turn; a shop nests better than this, and the
        # utilisation figure is deliberately pessimistic rather than
        # optimistic about someone else's nesting.
        if sector >= math.pi:
            box = (2.0 * outer, 2.0 * outer)
        else:
            box = (2.0 * outer * math.sin(sector / 2.0), outer)
        return Development(
            kind="annular_sector",
            area_mm2=area,
            sector_angle_deg=math.degrees(sector),
            inner_radius_mm=inner,
            outer_radius_mm=outer,
            width_mm=0.0,
            height_mm=0.0,
            bounding_box_mm=box,
            # Meridians on the development are radial lines, so the angle a
            # straight fibre makes with them changes one-for-one with the
            # sector angle swept.
            fibre_angle_drift_deg=math.degrees(sector),
        )

    return Development(
        kind="rectangle",
        area_mm2=shape.lateral_area_mm2,
        sector_angle_deg=0.0,
        inner_radius_mm=0.0,
        outer_radius_mm=0.0,
        width_mm=shape.developed_width_mm,
        height_mm=shape.length_mm,
        bounding_box_mm=(shape.developed_width_mm, shape.length_mm),
        # A cylinder's meridians develop to parallel lines, so a straight
        # fibre holds its angle everywhere on the part.
        fibre_angle_drift_deg=0.0,
    )


def gores_for_tolerance(
    development: Development, *, tolerance_deg: float = FIBRE_ANGLE_TOLERANCE_DEG
) -> int:
    """Gores needed to hold fibre angle within a tolerance across the part.

    Each gore may span twice the tolerance, because the nominal angle can be
    set at the gore's centre and drift half the allowance either way.
    """

    if tolerance_deg <= 0:
        raise ValueError("tolerance must be positive")
    if development.fibre_angle_drift_deg <= 0.0:
        return 1
    return max(1, math.ceil(development.fibre_angle_drift_deg / (2.0 * tolerance_deg)))


def nesting_utilisation(development: Development, *, roll_width_mm: float = ROLL_WIDTH_MM) -> dict:
    """Pattern area against the stock it is cut from.

    A single-part figure, and pessimistic: real nesting interleaves parts and
    rotates them.  It is here because prepreg is bought by the metre and an
    annular sector is one of the worst shapes to buy by the metre.
    """

    width, height = development.bounding_box_mm
    if width > roll_width_mm:
        width, height = height, width
    fits = width <= roll_width_mm
    box_area = width * height
    return {
        "bounding_box_mm": [round(width, 2), round(height, 2)],
        "fits_roll_width": fits,
        "pattern_area_mm2": round(development.area_mm2, 1),
        "bounding_box_area_mm2": round(box_area, 1),
        "utilisation": round(development.area_mm2 / box_area, 4) if box_area else 0.0,
        "scrap_fraction": round(1.0 - development.area_mm2 / box_area, 4) if box_area else 0.0,
    }


# --------------------------------------------------------------------------
# What drift does to a laminate
# --------------------------------------------------------------------------


def rotational_envelope(laminate: Laminate, *, span_deg: float = 180.0, step_deg: float = 1.0) -> dict:
    """How much a laminate's in-plane stiffness changes as it is rotated.

    Fibre drift rotates the whole stack together, so its structural
    consequence is exactly this envelope.  A ratio of 1.0 means the laminate
    is in-plane isotropic and does not care where on the cone it sits; a
    ratio of 1.5 means one part of the cone is half again as stiff as
    another, from a single laminate schedule.
    """

    if span_deg <= 0 or step_deg <= 0:
        raise ValueError("span and step must be positive")
    plies = laminate.plies
    ex_values: list[float] = []
    gxy_values: list[float] = []
    worst_angle = 0.0
    steps = int(span_deg / step_deg) + 1
    for index in range(steps):
        angle = index * step_deg
        rotated = Laminate(
            Ply(ply.material, ply.angle_deg + angle, ply.thickness_mm) for ply in plies
        )
        constants = rotated.engineering_constants()
        ex_values.append(constants["ex_mpa"])
        gxy_values.append(constants["gxy_mpa"])
        if constants["ex_mpa"] == min(ex_values):
            worst_angle = angle
    return {
        "span_deg": span_deg,
        "ex_min_mpa": round(min(ex_values), 1),
        "ex_max_mpa": round(max(ex_values), 1),
        "ex_ratio": round(max(ex_values) / min(ex_values), 4),
        "gxy_ratio": round(max(gxy_values) / min(gxy_values), 4),
        "softest_rotation_deg": worst_angle,
        "in_plane_isotropic": max(ex_values) / min(ex_values) < 1.02,
    }


def seam_stagger_ok(seam_positions_mm: list[float], *, minimum_mm: float = MIN_SEAM_STAGGER_MM) -> bool:
    """True when no two adjacent plies place their splice too close together."""

    return all(
        abs(second - first) >= minimum_mm
        for first, second in zip(seam_positions_mm, seam_positions_mm[1:])
    )


def staggered_seams(ply_count: int, *, pitch_mm: float = MIN_SEAM_STAGGER_MM) -> tuple[float, ...]:
    """Seam positions that satisfy the stagger rule, measured along the arc."""

    if ply_count <= 0:
        raise ValueError("ply count must be positive")
    return tuple(index * pitch_mm for index in range(ply_count))


# --------------------------------------------------------------------------
# The program's geometry
# --------------------------------------------------------------------------

#: Part geometry, kept here rather than in the laminate schedules because a
#: schedule is about the stack and this is about the surface.  The areas the
#: schedules charge against the mass budget are derived from these shapes, so
#: the two cannot disagree; ``validate_geometry`` checks it.
PART_SHAPES: dict[str, ConeFrustum | SlitTube] = {
    # Throat cup: a 45-degree half-angle cone from the Ø40 throat out to the
    # Ø110 bonded flange.
    "CS-100": ConeFrustum(inner_radius_mm=20.0, outer_radius_mm=55.0, height_mm=35.0),
    # One boom: a 35 mm developed width of tube, 250 mm long.
    "CS-200": SlitTube(radius_mm=22.3, subtended_angle_deg=90.0, length_mm=250.0),
}


def evaluate(part_id: str) -> dict:
    """Develop one part and report what the development costs it."""

    from .schedules import schedule

    shape = PART_SHAPES[part_id]
    item = schedule(part_id)
    laminate = item.laminate()
    development = develop(shape)
    drift = development.fibre_angle_drift_deg
    envelope = rotational_envelope(laminate, span_deg=min(drift, 180.0) if drift else 1.0)
    return {
        "part_id": part_id,
        "shape": {"kind": type(shape).__name__, **asdict(shape)},
        "development": asdict(development),
        "declared_area_m2": item.area_m2,
        "developed_area_m2": round(development.area_mm2 / 1e6, 6),
        "gores_for_tolerance": gores_for_tolerance(development),
        "fibre_angle_tolerance_deg": FIBRE_ANGLE_TOLERANCE_DEG,
        "stiffness_envelope_over_drift": envelope,
        "nesting": nesting_utilisation(development),
        "seam_positions_mm": staggered_seams(laminate.ply_count),
    }


def validate_geometry() -> list[str]:
    """Checks the development arithmetic and its agreement with the schedules."""

    from .schedules import schedule

    errors: list[str] = []
    for part_id, shape in PART_SHAPES.items():
        development = develop(shape)
        # The development of a developable surface has exactly the area of
        # the surface.  If this fails, the sector angle is wrong.
        if abs(development.area_mm2 - shape.lateral_area_mm2) > 1e-6 * shape.lateral_area_mm2:
            errors.append(
                f"{part_id}: developed area {development.area_mm2:.1f} does not match "
                f"the surface area {shape.lateral_area_mm2:.1f}"
            )
        item = schedule(part_id)
        declared = item.area_m2 * item.quantity
        developed = development.area_mm2 / 1e6 * item.quantity
        if abs(declared - developed) > 0.02 * developed:
            errors.append(
                f"{part_id}: schedule area {declared:.5f} m^2 disagrees with the "
                f"developed area {developed:.5f} m^2 by more than 2 %"
            )
        if not nesting_utilisation(development)["fits_roll_width"]:
            errors.append(f"{part_id}: flat pattern does not fit the prepreg roll width")
    return errors


def snapshot() -> dict:
    errors = validate_geometry()
    return {
        "units": {"length": "mm", "angle": "deg", "area": "mm^2"},
        "valid": not errors,
        "errors": errors,
        "fibre_angle_tolerance_deg": FIBRE_ANGLE_TOLERANCE_DEG,
        "min_seam_stagger_mm": MIN_SEAM_STAGGER_MM,
        "roll_width_mm": ROLL_WIDTH_MM,
        "parts": [evaluate(part_id) for part_id in PART_SHAPES],
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
