"""Tool material selection and thermal-expansion compensation.

A mould is a machine for holding a shape at a temperature the part will never
see again.  Everything hard about tooling for thin high-precision laminates
follows from that sentence:

* the tool defines the part at **cure** temperature, but the part is
  inspected at room temperature, so a tool cut to the drawing produces a part
  that is not on the drawing — the difference is the CTE mismatch times the
  cooldown, and on a 300 mm part with an aluminium tool it is a third of a
  millimetre, which is ten times the tolerance;
* the tool's **thermal mass** decides how far the part lags the oven, and
  therefore whether the cure cycle the part experiences is the cure cycle the
  spec describes.  This is not a separate concern from the cure model — it is
  an input to it, and :func:`areal_heat_capacity_j_m2_k` is what
  ``aiur.composites.cure`` consumes;
* the tool's surface decides the part's surface, because a moulded face is a
  cast of the tool and will faithfully reproduce every scratch in it.

The trade below screens five candidate tool materials on two thresholds —
surviving the cure, and lasting the programme — and then scores the
survivors on four criteria, three of them computed from physical properties
and one (cost) a stated judgement.

The result for this program is not the aerospace-standard answer.  Invar
wins the dimensional criterion outright and comes last overall, because a
65 kg/m^2 invar tool in a small oven roughly doubles the part's thermal lag
and quadruples the lead time for a programme whose whole point is iteration
speed.  Machined aluminium wins — the worst dimensional performer of the
metals — because its error is *compensable* and the compensation is
arithmetic.  What has to be right is therefore the compensation factor, and
the process control that follows from it: an aluminium tool for a 300 mm
part is cut 0.97 mm away from the drawing, so the tool drawing must state
its own scale factor, and a machinist who works to the part drawing by
mistake produces a tool that is wrong by six times the tolerance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .clt import Laminate

#: Reference part dimension the dimensional criterion is scored on, mm.
REFERENCE_PART_LENGTH_MM = 300.0
#: Reference cooldown, K: a 180 degC cure back to a 25 degC inspection.
REFERENCE_COOLDOWN_K = 155.0
#: Dimensional tolerance the program holds on a moulded in-plane dimension,
#: mm.  Taken from what the capture-chain tolerance stack can absorb.
IN_PLANE_TOLERANCE_MM = 0.15

#: Cures this program expects to run on one tool through P0. A tool that
#: survives this many is durable enough; surviving ten times as many is worth
#: nothing here, which is why durability is a screen and not a score.
PROGRAM_CURE_DEMAND = 40


@dataclass(frozen=True)
class ToolMaterial:
    """A candidate mould material."""

    name: str
    cte_per_k: float
    density_kg_m3: float
    specific_heat_j_kg_k: float
    #: Typical wall or plate thickness a tool of this material is built in, mm.
    typical_thickness_mm: float
    max_service_temperature_c: float
    #: Number of cure cycles before the moulding surface needs rework.
    #: Engineering target from ordinary shop experience.
    durability_cycles: int
    #: Relative cost of a finished tool, aluminium = 1.0.  Judgement.
    relative_cost: float
    #: Relative lead time to a finished tool, aluminium = 1.0.  Judgement.
    relative_lead_time: float
    #: Surface finish achievable without hand polishing, micrometres Ra.
    surface_finish_ra_um: float
    #: Uncertainty on the CTE itself, 1/K.  This is what decides how well a
    #: compensated tool actually works: the compensation removes the mismatch
    #: the model knows about, and leaves behind the part the model has wrong.
    #: A carbon tool's CTE is the least certain of the set, because it is a
    #: laminate whose own layup and fibre content vary.
    cte_uncertainty_per_k: float = 0.0
    note: str = ""

    def areal_heat_capacity_j_m2_k(self) -> float:
        """Heat capacity per unit tool area, J/(m^2.K).

        This is the number the cure model needs, and the reason a heavy tool
        undercures a part: the oven has to heat the tool through the same
        film coefficient it heats the part through.
        """

        return self.density_kg_m3 * (self.typical_thickness_mm * 1e-3) * self.specific_heat_j_kg_k

    def areal_mass_kg_m2(self) -> float:
        return self.density_kg_m3 * self.typical_thickness_mm * 1e-3


#: Aluminium tooling plate: the shop default.  Cheap, fast to machine,
#: thermally responsive, and dimensionally the worst of the metals.
ALUMINIUM_6061 = ToolMaterial(
    name="aluminium 6061 plate",
    cte_per_k=23.6e-6,
    density_kg_m3=2700.0,
    specific_heat_j_kg_k=900.0,
    typical_thickness_mm=6.0,
    max_service_temperature_c=200.0,
    durability_cycles=500,
    relative_cost=1.0,
    relative_lead_time=1.0,
    surface_finish_ra_um=0.4,
    cte_uncertainty_per_k=0.8e-6,
    note="requires a computed compensation factor; without one it is unusable",
)

TOOL_STEEL_P20 = ToolMaterial(
    name="tool steel P20",
    cte_per_k=12.8e-6,
    density_kg_m3=7800.0,
    specific_heat_j_kg_k=460.0,
    typical_thickness_mm=8.0,
    max_service_temperature_c=400.0,
    durability_cycles=5000,
    relative_cost=2.2,
    relative_lead_time=2.0,
    surface_finish_ra_um=0.2,
    cte_uncertainty_per_k=0.5e-6,
    note="durable and heavy; the thermal mass is the problem, not the price",
)

INVAR_36 = ToolMaterial(
    name="invar 36",
    cte_per_k=1.6e-6,
    density_kg_m3=8100.0,
    specific_heat_j_kg_k=515.0,
    typical_thickness_mm=8.0,
    max_service_temperature_c=400.0,
    durability_cycles=5000,
    relative_cost=6.0,
    relative_lead_time=4.0,
    surface_finish_ra_um=0.2,
    cte_uncertainty_per_k=0.3e-6,
    note="dimensionally ideal, and the heaviest and slowest thing in the shop",
)

CARBON_TOOL = ToolMaterial(
    name="carbon/epoxy tooling laminate",
    cte_per_k=3.0e-6,
    density_kg_m3=1550.0,
    specific_heat_j_kg_k=1000.0,
    typical_thickness_mm=5.0,
    max_service_temperature_c=190.0,
    durability_cycles=150,
    relative_cost=2.8,
    relative_lead_time=2.5,
    surface_finish_ra_um=0.8,
    cte_uncertainty_per_k=1.0e-6,
    note=(
        "CTE-matched to the part and light, but it must itself be moulded off "
        "a master, so it inherits that master's error and adds a step"
    ),
)

TOOLING_BOARD = ToolMaterial(
    name="epoxy tooling board",
    cte_per_k=45.0e-6,
    density_kg_m3=1200.0,
    specific_heat_j_kg_k=1500.0,
    typical_thickness_mm=25.0,
    max_service_temperature_c=120.0,
    durability_cycles=20,
    relative_cost=0.6,
    relative_lead_time=0.5,
    surface_finish_ra_um=1.6,
    cte_uncertainty_per_k=4.0e-6,
    note="prototype-only: fastest to a first part, and it will not survive a 180 degC cure",
)

TOOL_MATERIALS: tuple[ToolMaterial, ...] = (
    ALUMINIUM_6061,
    TOOL_STEEL_P20,
    INVAR_36,
    CARBON_TOOL,
    TOOLING_BOARD,
)


# --------------------------------------------------------------------------
# Compensation
# --------------------------------------------------------------------------


def compensation_factor(*, part_cte_per_k: float, tool_cte_per_k: float, cooldown_k: float) -> float:
    """Scale factor to apply to a nominal dimension when cutting the tool.

    At cure temperature the part takes the tool's dimension.  Cooling to room
    temperature, each contracts by its own CTE, so

        L_part(RT) = L_tool(RT) (1 + a_tool dT) / (1 + a_part dT)

    for a temperature *rise* ``dT`` to cure; inverting for the tool dimension
    that lands the part on nominal gives the factor returned here.
    """

    return (1.0 + part_cte_per_k * cooldown_k) / (1.0 + tool_cte_per_k * cooldown_k)


def compensated_tool_length_mm(
    nominal_part_length_mm: float,
    *,
    part_cte_per_k: float,
    tool_cte_per_k: float,
    cooldown_k: float = REFERENCE_COOLDOWN_K,
) -> float:
    return nominal_part_length_mm * compensation_factor(
        part_cte_per_k=part_cte_per_k,
        tool_cte_per_k=tool_cte_per_k,
        cooldown_k=cooldown_k,
    )


def uncompensated_error_mm(
    nominal_part_length_mm: float,
    *,
    part_cte_per_k: float,
    tool_cte_per_k: float,
    cooldown_k: float = REFERENCE_COOLDOWN_K,
) -> float:
    """How far off a part comes out if the tool is cut to the drawing."""

    factor = compensation_factor(
        part_cte_per_k=part_cte_per_k,
        tool_cte_per_k=tool_cte_per_k,
        cooldown_k=cooldown_k,
    )
    return nominal_part_length_mm * (1.0 / factor - 1.0)


def thermal_lag_time_constant_s(
    tool: ToolMaterial,
    *,
    laminate_thickness_mm: float = 1.0,
    laminate_density_kg_m3: float = 1550.0,
    laminate_specific_heat_j_kg_k: float = 1000.0,
    film_coefficient_w_m2_k: float = 25.0,
    exchange_area_factor: float = 2.0,
) -> float:
    """Lumped thermal time constant of the tool-plus-part assembly, s.

    Multiplied by the oven's ramp rate, this is how far the part runs behind
    the oven — which is the single most useful number for deciding whether a
    cure recipe can be run as written.
    """

    part = laminate_density_kg_m3 * laminate_thickness_mm * 1e-3 * laminate_specific_heat_j_kg_k
    total = part + tool.areal_heat_capacity_j_m2_k()
    return total / (film_coefficient_w_m2_k * exchange_area_factor)


# --------------------------------------------------------------------------
# Trade study
# --------------------------------------------------------------------------

#: Trade weights.
#:
#: Two criteria that belong in an obvious version of this trade are missing,
#: and their absence is the point.  Temperature capability and durability are
#: **thresholds**, not scores: a tool that survives the cure with headroom to
#: spare is not better than one that merely survives it, and a tool good for
#: 5000 cures is not better than one good for 500 when the programme will run
#: forty.  Scoring them on a normalised scale is how a trade study elects the
#: heaviest, slowest, most expensive candidate on the strength of margin
#: nobody needs — which is exactly what the first version of this study did,
#: returning tool steel.  They are screens now, and what remains scored is
#: what genuinely differentiates the candidates for this programme.
TRADE_WEIGHTS: dict[str, float] = {
    "dimensional_robustness": 0.35,
    "thermal_responsiveness": 0.25,
    "cost": 0.20,
    "lead_time": 0.20,
}


def _normalise(values: list[float], *, higher_is_better: bool) -> list[float]:
    """Scale a criterion onto 0-1 across the candidate set."""

    low, high = min(values), max(values)
    if high == low:
        return [1.0] * len(values)
    if higher_is_better:
        return [(value - low) / (high - low) for value in values]
    return [(high - value) / (high - low) for value in values]


def trade_study(
    *,
    part_cte_per_k: float,
    cure_temperature_c: float = 180.0,
    cooldown_k: float = REFERENCE_COOLDOWN_K,
    ramp_c_per_min: float = 2.0,
) -> dict[str, object]:
    """Score the candidate tool materials for this program's parts."""

    # Screens first: anything that cannot survive the cure, or cannot last
    # the programme, is not a candidate however it would have scored.
    screened_out = []
    candidates = []
    for tool in TOOL_MATERIALS:
        headroom = tool.max_service_temperature_c - cure_temperature_c
        if headroom < 10.0:
            screened_out.append(
                {
                    "name": tool.name,
                    "reason": (
                        f"{headroom:.0f} K of headroom over a {cure_temperature_c:.0f} degC "
                        "cure; needs at least 10 K"
                    ),
                }
            )
            continue
        if tool.durability_cycles < PROGRAM_CURE_DEMAND:
            screened_out.append(
                {
                    "name": tool.name,
                    "reason": (
                        f"{tool.durability_cycles} cures against a programme demand of "
                        f"{PROGRAM_CURE_DEMAND}"
                    ),
                }
            )
            continue
        candidates.append(tool)

    errors = [
        abs(
            uncompensated_error_mm(
                REFERENCE_PART_LENGTH_MM,
                part_cte_per_k=part_cte_per_k,
                tool_cte_per_k=tool.cte_per_k,
                cooldown_k=cooldown_k,
            )
        )
        for tool in candidates
    ]
    lags = [
        thermal_lag_time_constant_s(tool) / 60.0 * ramp_c_per_min for tool in candidates
    ]
    temperature_headroom = [
        tool.max_service_temperature_c - cure_temperature_c for tool in candidates
    ]
    # Residual error after compensation: the compensation factor removes the
    # CTE mismatch the model knows, and leaves behind the part it has wrong.
    residuals = [
        REFERENCE_PART_LENGTH_MM * tool.cte_uncertainty_per_k * cooldown_k
        for tool in candidates
    ]

    scores = {
        "dimensional_robustness": _normalise(residuals, higher_is_better=False),
        "thermal_responsiveness": _normalise(lags, higher_is_better=False),
        "cost": _normalise([tool.relative_cost for tool in candidates], higher_is_better=False),
        "lead_time": _normalise(
            [tool.relative_lead_time for tool in candidates], higher_is_better=False
        ),
    }

    rows = []
    for index, tool in enumerate(candidates):
        total = sum(TRADE_WEIGHTS[key] * scores[key][index] for key in TRADE_WEIGHTS)
        rows.append(
            {
                "name": tool.name,
                "cte_per_k": tool.cte_per_k,
                "uncompensated_error_mm": round(errors[index], 4),
                "compensation_factor": round(
                    compensation_factor(
                        part_cte_per_k=part_cte_per_k,
                        tool_cte_per_k=tool.cte_per_k,
                        cooldown_k=cooldown_k,
                    ),
                    6,
                ),
                "needs_compensation": errors[index] > IN_PLANE_TOLERANCE_MM,
                "residual_error_after_compensation_mm": round(residuals[index], 4),
                "residual_within_tolerance": residuals[index] <= IN_PLANE_TOLERANCE_MM,
                "areal_mass_kg_m2": round(tool.areal_mass_kg_m2(), 2),
                "thermal_lag_k_at_ramp": round(lags[index], 2),
                "temperature_headroom_k": round(temperature_headroom[index], 1),
                "usable_at_cure_temperature": temperature_headroom[index] >= 10.0,
                "durability_cycles": tool.durability_cycles,
                "relative_cost": tool.relative_cost,
                "scores": {key: round(scores[key][index], 3) for key in TRADE_WEIGHTS},
                "total_score": round(total, 4),
                "note": tool.note,
            }
        )

    ranked = sorted(rows, key=lambda row: row["total_score"], reverse=True)
    return {
        "reference_part_length_mm": REFERENCE_PART_LENGTH_MM,
        "cooldown_k": cooldown_k,
        "part_cte_per_k": part_cte_per_k,
        "ramp_c_per_min": ramp_c_per_min,
        "in_plane_tolerance_mm": IN_PLANE_TOLERANCE_MM,
        "weights": TRADE_WEIGHTS,
        "program_cure_demand": PROGRAM_CURE_DEMAND,
        "screened_out": screened_out,
        "candidates": rows,
        "selected": ranked[0]["name"] if ranked else None,
        "runner_up": ranked[1]["name"] if len(ranked) > 1 else None,
    }


def snapshot() -> dict[str, object]:
    from .schedules import schedule

    # Scored against the throat cup, the part with the tightest moulded
    # tolerance and the one whose tool is cut first.
    laminate: Laminate = schedule("CS-100").laminate()
    part_cte = 0.5 * (laminate.cte_per_k()[0] + laminate.cte_per_k()[1])
    study = trade_study(part_cte_per_k=part_cte)
    return {
        "units": {"length": "mm", "cte": "1/K", "mass": "kg/m^2"},
        "scored_against_part": "CS-100",
        "trade": study,
        "tool_materials": [
            {
                **asdict(tool),
                "areal_heat_capacity_j_m2_k": round(tool.areal_heat_capacity_j_m2_k(), 1),
                "thermal_lag_time_constant_min": round(
                    thermal_lag_time_constant_s(tool) / 60.0, 2
                ),
            }
            for tool in TOOL_MATERIALS
        ],
    }


def main() -> int:
    print(json.dumps(snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
