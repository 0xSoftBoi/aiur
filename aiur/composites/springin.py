"""Spring-in prediction and tool compensation for CARRIER-P0 laminates.

A composite part does not come off its tool at the angle it was moulded at.
Every enclosed corner closes up — the flanges rotate toward each other — by a
few tenths of a degree, and the part is *not* defective: the tool is.  This
module predicts how much, so the tool can be cut open by that amount and the
part can come off at nominal.

Two mechanisms drive it, and both come from the same asymmetry: a laminate is
fibre-dominated in plane and resin-dominated through the thickness.

**Thermal.**  On cooldown the corner's arc length shrinks by the in-plane CTE
(near zero for carbon) while its thickness shrinks by the through-thickness
CTE (forty times larger).  A shorter radius across a nearly constant arc is a
smaller enclosed angle.

**Chemical.**  Cure shrinkage after gelation does the same thing, and it does
it whatever the cure temperature.  This is why a low-temperature cure reduces
spring-in but never eliminates it, and why a programme that switches resins to
fix a distortion problem is often disappointed.

The prediction is Radford's, which is the standard closed form:

    dtheta / theta = (a_L - a_T) dT / (1 + a_T dT)  +  (p_L - p_T) / (1 + p_T)

with ``L`` in-plane along the arc and ``T`` through the thickness.

A third mechanism — **tool-part interaction** — is real, is often larger than
either of the above on a thin part, and has no closed form.  The tool grips
the laminate as it heats and shears the outer plies, locking in a stress that
releases on demould as warp in flat regions as well as angle change at
corners.  It depends on the release agent, the tool surface, the bag pressure
and the ramp rate, which is to say it depends on the shop rather than on the
material.  It is carried here as an explicit, separately labeled allowance
with a value of zero and a DoE that measures it (DOE-2), rather than folded
into a fudged CTE where it would silently corrupt the physics.

Everything this module predicts is an engineering target until DOE-2 measures
spring-in on the real tool.  The compensation loop that closes it is in
:func:`compensated_tool_angle` and :func:`update_from_measurement`: measure
the first article, correct the tool, and the second article is nominal.  That
loop is the deliverable — not the equation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .clt import Laminate

#: Tool-part interaction allowance, degrees per degree of enclosed angle.
#: Zero until DOE-2 measures it; kept as a named term so the model reports an
#: incomplete prediction honestly instead of an apparently complete one.
TOOL_INTERACTION_ALLOWANCE = 0.0

#: Angular tolerance the program holds on a moulded corner, degrees.  Set by
#: what the capture-chain tolerance stack can absorb, not by what is easy.
CORNER_ANGLE_TOLERANCE_DEG = 0.25


def _thickness_weighted(laminate: Laminate, attribute: str) -> float:
    total = laminate.thickness_mm
    return sum(
        getattr(ply.mat, attribute) * ply.thickness for ply in laminate.plies
    ) / total


def in_plane_cte(laminate: Laminate) -> float:
    """Laminate in-plane CTE along the corner arc, 1/K.

    Taken as the mean of the laminate's two in-plane CTEs: a corner's arc runs
    in one in-plane direction, but which one depends on how the part is laid
    into the tool, and for the near-isotropic stacks here the two differ by
    less than the tolerance on either.
    """

    cte = laminate.cte_per_k()
    return 0.5 * (cte[0] + cte[1])


def through_thickness_cte(laminate: Laminate) -> float:
    """Laminate through-thickness CTE, 1/K.

    Thickness-weighted mean of the plies' through-thickness values.  Plies
    stack in series through the thickness and each is free to expand, so the
    weighted mean is exact here in a way the in-plane average never is.
    """

    return _thickness_weighted(laminate, "alpha3_per_k")


def through_thickness_shrinkage(laminate: Laminate, fraction: float) -> float:
    """Post-gel through-thickness cure shrinkage, dimensionless."""

    if not 0.0 <= fraction <= 1.0:
        raise ValueError("shrinkage fraction must be in [0, 1]")
    return _thickness_weighted(laminate, "shrink3") * fraction


def in_plane_shrinkage(laminate: Laminate, fraction: float) -> float:
    """Post-gel in-plane cure shrinkage, dimensionless.

    Fibre-direction shrinkage is what survives into the laminate: the plies
    restrain each other in plane, so the resin's chemical shrinkage shows up
    almost entirely through the thickness.
    """

    if not 0.0 <= fraction <= 1.0:
        raise ValueError("shrinkage fraction must be in [0, 1]")
    return _thickness_weighted(laminate, "shrink1") * fraction


@dataclass(frozen=True)
class SpringInResult:
    part_id: str
    nominal_angle_deg: float
    delta_thermal_deg: float
    delta_chemical_deg: float
    delta_tool_interaction_deg: float
    total_spring_in_deg: float
    compensated_tool_angle_deg: float
    within_tolerance_uncompensated: bool
    in_plane_cte_per_k: float
    through_thickness_cte_per_k: float
    delta_t_k: float
    basis: str


def spring_in_deg(
    laminate: Laminate,
    *,
    enclosed_angle_deg: float,
    cooldown_k: float,
    shrinkage_fraction: float,
    tool_interaction_allowance: float = TOOL_INTERACTION_ALLOWANCE,
) -> tuple[float, float, float]:
    """Return ``(thermal, chemical, tool)`` spring-in components, degrees.

    ``cooldown_k`` is the temperature **drop** from cure to room temperature,
    as a positive magnitude, and the shrinkage terms are likewise positive
    contraction magnitudes.  That convention differs from the signed
    ``delta_t_k`` used by the laminate load cases, and the difference is
    deliberate rather than sloppy: Radford's expression is written in terms
    of a drop, and mixing the two conventions in one function is what made
    the first version of this model report the thermal and chemical terms
    with opposite signs — a corner cannot both close and open on cooldown,
    and the disagreement is what caught the error.

    All three components are returned as positive magnitudes of angular
    *closure*, which is how a tool is corrected and how a shop describes it.
    """

    if enclosed_angle_deg <= 0:
        raise ValueError("enclosed angle must be positive")
    if cooldown_k < 0:
        raise ValueError("cooldown must be given as a positive temperature drop")

    alpha_l = in_plane_cte(laminate)
    alpha_t = through_thickness_cte(laminate)
    shrink_l = in_plane_shrinkage(laminate, shrinkage_fraction)
    shrink_t = through_thickness_shrinkage(laminate, shrinkage_fraction)

    # Both bracketed terms are negative — the through-thickness expansion and
    # shrinkage exceed the in-plane ones — so each closes the angle.
    thermal = -enclosed_angle_deg * (alpha_l - alpha_t) * cooldown_k / (1.0 + alpha_t * cooldown_k)
    chemical = -enclosed_angle_deg * (shrink_l - shrink_t) / (1.0 + shrink_t)
    tool = enclosed_angle_deg * tool_interaction_allowance
    return (thermal, chemical, tool)


def compensated_tool_angle(nominal_angle_deg: float, spring_in_total_deg: float) -> float:
    """Angle to cut into the tool so the part demoulds at nominal."""

    return nominal_angle_deg + spring_in_total_deg


def evaluate(
    part_id: str,
    laminate: Laminate,
    *,
    enclosed_angle_deg: float,
    cure_temperature_c: float,
    room_temperature_c: float = 25.0,
    shrinkage_fraction: float = 0.5,
    tool_interaction_allowance: float = TOOL_INTERACTION_ALLOWANCE,
) -> SpringInResult:
    cooldown = cure_temperature_c - room_temperature_c
    thermal, chemical, tool = spring_in_deg(
        laminate,
        enclosed_angle_deg=enclosed_angle_deg,
        cooldown_k=cooldown,
        shrinkage_fraction=shrinkage_fraction,
        tool_interaction_allowance=tool_interaction_allowance,
    )
    total = thermal + chemical + tool
    return SpringInResult(
        part_id=part_id,
        nominal_angle_deg=enclosed_angle_deg,
        delta_thermal_deg=round(thermal, 4),
        delta_chemical_deg=round(chemical, 4),
        delta_tool_interaction_deg=round(tool, 4),
        total_spring_in_deg=round(total, 4),
        compensated_tool_angle_deg=round(
            compensated_tool_angle(enclosed_angle_deg, total), 4
        ),
        within_tolerance_uncompensated=abs(total) <= CORNER_ANGLE_TOLERANCE_DEG,
        in_plane_cte_per_k=in_plane_cte(laminate),
        through_thickness_cte_per_k=through_thickness_cte(laminate),
        delta_t_k=-cooldown,
        basis="analysis; handbook CTE and shrinkage, tool interaction unmeasured",
    )


def update_from_measurement(
    *,
    tool_angle_deg: float,
    measured_part_angle_deg: float,
    nominal_angle_deg: float,
) -> dict[str, float]:
    """Close the compensation loop from a first-article measurement.

    The prediction sizes the first tool.  The first part measures what the
    prediction got wrong, and this returns the tool angle that makes the
    second part nominal.  A shop that runs this loop needs a good prediction
    once and an accurate measurement every time; a shop that runs only the
    prediction needs it to be right, which it will not be until DOE-2.
    """

    measured_spring_in = tool_angle_deg - measured_part_angle_deg
    return {
        "measured_spring_in_deg": round(measured_spring_in, 4),
        "corrected_tool_angle_deg": round(nominal_angle_deg + measured_spring_in, 4),
        "residual_error_deg": round(measured_part_angle_deg - nominal_angle_deg, 4),
    }


@dataclass(frozen=True)
class CornerFeature:
    """A moulded corner on a real part, with the angle its function needs."""

    part_id: str
    feature: str
    enclosed_angle_deg: float
    cure_temperature_c: float
    consequence: str


#: The corners in the P0 composite set whose angle matters functionally.
CORNERS: tuple[CornerFeature, ...] = (
    CornerFeature(
        part_id="CS-100",
        feature="throat cup cone half-angle",
        enclosed_angle_deg=45.0,
        cure_temperature_c=180.0,
        consequence=(
            "a closed cone angle narrows the funnel throat and eats lateral "
            "capture margin directly out of the tolerance stack"
        ),
    ),
    CornerFeature(
        part_id="CS-100",
        feature="bonded flange to cone",
        enclosed_angle_deg=90.0,
        cure_temperature_c=180.0,
        consequence=(
            "a closed flange corner opens a gap at the bond line, which the "
            "adhesive fills with a thick bondline and a weak joint"
        ),
    ),
    CornerFeature(
        part_id="CS-300",
        feature="rail web to cap angle",
        enclosed_angle_deg=90.0,
        cure_temperature_c=180.0,
        consequence="a closed rail angle preloads the carriage and raises drag",
    ),
    CornerFeature(
        part_id="CS-400",
        feature="tine root bend",
        enclosed_angle_deg=90.0,
        cure_temperature_c=180.0,
        consequence=(
            "a closed tine root moves the retention ledge, which is the "
            "critical dimension in the capture-chain tolerance stack"
        ),
    ),
)


def evaluate_all() -> list[dict[str, object]]:
    from .schedules import POST_GEL_SHRINKAGE_FRACTION, schedule

    results = []
    for corner in CORNERS:
        laminate = schedule(corner.part_id).laminate()
        result = evaluate(
            corner.part_id,
            laminate,
            enclosed_angle_deg=corner.enclosed_angle_deg,
            cure_temperature_c=corner.cure_temperature_c,
            shrinkage_fraction=POST_GEL_SHRINKAGE_FRACTION,
        )
        results.append({**asdict(corner), **asdict(result)})
    return results


def snapshot() -> dict[str, object]:
    results = evaluate_all()
    return {
        "units": {"angle": "deg", "cte": "1/K"},
        "corner_angle_tolerance_deg": CORNER_ANGLE_TOLERANCE_DEG,
        "tool_interaction_allowance": TOOL_INTERACTION_ALLOWANCE,
        "tool_interaction_status": (
            "unmeasured; DOE-2 measures it on the production tool and this "
            "allowance is updated from that result"
        ),
        # Every corner needing compensation is the expected state, not a
        # problem: it means the model is doing its job before the tool is cut.
        "corners_needing_compensation": [
            result["feature"]
            for result in results
            if not result["within_tolerance_uncompensated"]
        ],
        "corners": results,
    }


def main() -> int:
    print(json.dumps(snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
