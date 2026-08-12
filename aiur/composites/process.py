"""Constituent-content and consolidation checks for CARRIER-P0 laminates.

Three numbers decide whether a cured panel is the laminate the stress model
assumed: fibre volume fraction, void content, and thickness.  They are not
independent — they are three views of the same consolidation — and this
module computes all three from what a shop can actually measure, so that a
panel is accepted or rejected on arithmetic rather than on appearance.

**Fibre volume fraction** comes free with a caliper.  For a known number of
plies of known fibre areal weight, ``Vf = n W / (rho_f t)``: a panel that
measures thick is a panel with less fibre in it, and its stiffness is down in
exactly that proportion.  This is the cheapest process measurement in
composites and the most neglected.

**Void content** comes from density (ASTM D2734): compare the panel's
measured density against the void-free density its constituents imply, and
the deficit is air.  Voids are the defect that matters most and shows least —
they cost interlaminar and compression strength, they are invisible on a
finished surface, and above about 2 % they turn a laminate into a different
material.

**Thickness per ply** is the same measurement as fibre volume fraction, said
in the units a traveler uses and an inspector can check against a drawing.

The debulk model is the one piece here that is a *model* rather than an
arithmetic identity: entrapped interply air falls roughly geometrically with
each debulk, toward a floor set by how well the bag and the resin can move
air out of the stack.  Its constants are engineering targets, and DOE-2 is
the experiment that replaces them.  It is included because the alternative —
"debulk every three plies" with no stated basis — is how a shop ends up
debulking either too little to matter or so often that it becomes the cost
driver of the part.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .materials import PlyMaterial, material as lookup_material

# --------------------------------------------------------------------------
# Acceptance limits
# --------------------------------------------------------------------------

#: Void content limits by part criticality, volume fraction.
MAX_VOID_FRACTION_GENERAL = 0.020
MAX_VOID_FRACTION_CRITICAL = 0.010
#: Fibre volume fraction band.  Below the floor the part is resin-rich, heavy
#: and soft; above the ceiling it is starved, and a starved laminate has
#: dry fibre that no inspection method reliably finds.
MIN_FIBRE_VOLUME_FRACTION = 0.50
MAX_FIBRE_VOLUME_FRACTION = 0.62
#: Cured-per-ply-thickness tolerance as a fraction of nominal CPT.
CPT_TOLERANCE_FRACTION = 0.10

#: Parts whose void limit is the tighter critical one.  The keeper tine is
#: the retention path; a void-driven interlaminar failure there drops an
#: aircraft, which no other part in the set can do.
CRITICAL_PART_IDS: frozenset[str] = frozenset({"CS-400"})


# --------------------------------------------------------------------------
# Constituent arithmetic
# --------------------------------------------------------------------------


def fibre_volume_fraction(
    *,
    ply_count: int,
    fibre_areal_weight_gsm: float,
    thickness_mm: float,
    fibre_density_g_cm3: float,
) -> float:
    """Fibre volume fraction from a caliper measurement and the ply count."""

    if ply_count <= 0:
        raise ValueError("ply count must be positive")
    if thickness_mm <= 0:
        raise ValueError("thickness must be positive")
    fibre_areal_mass_g_m2 = ply_count * fibre_areal_weight_gsm
    fibre_thickness_mm = fibre_areal_mass_g_m2 / (fibre_density_g_cm3 * 1e6) * 1e3
    return fibre_thickness_mm / thickness_mm


def theoretical_density_g_cm3(
    *,
    fibre_volume_fraction: float,
    fibre_density_g_cm3: float,
    resin_density_g_cm3: float,
) -> float:
    """Void-free density from the constituent rule of mixtures."""

    if not 0.0 < fibre_volume_fraction < 1.0:
        raise ValueError("fibre volume fraction must be in (0, 1)")
    return (
        fibre_volume_fraction * fibre_density_g_cm3
        + (1.0 - fibre_volume_fraction) * resin_density_g_cm3
    )


def void_fraction(*, measured_density_g_cm3: float, theoretical_density_g_cm3: float) -> float:
    """Void volume fraction (ASTM D2734), from the density deficit.

    Returns a signed value.  A small negative result is not negative porosity;
    it means the constituent densities or the assumed fibre content are
    slightly off, and a panel record that produces one is telling the shop to
    re-check its inputs rather than to celebrate.
    """

    if theoretical_density_g_cm3 <= 0:
        raise ValueError("theoretical density must be positive")
    return (theoretical_density_g_cm3 - measured_density_g_cm3) / theoretical_density_g_cm3


def resin_mass_fraction_from_digestion(
    *,
    specimen_mass_g: float,
    residue_fibre_mass_g: float,
) -> float:
    """Resin mass fraction by matrix digestion (ASTM D3171 Procedure B)."""

    if specimen_mass_g <= 0:
        raise ValueError("specimen mass must be positive")
    if not 0.0 < residue_fibre_mass_g <= specimen_mass_g:
        raise ValueError("fibre residue must be positive and no larger than the specimen")
    return 1.0 - residue_fibre_mass_g / specimen_mass_g


def density_from_immersion(
    *,
    dry_mass_g: float,
    immersed_mass_g: float,
    fluid_density_g_cm3: float = 0.9970,
) -> float:
    """Density by water immersion (ASTM D792), g/cm^3.

    The 0.9970 default is water at 25 degC.  Using 1.0000 introduces a 0.3 %
    density error, which reads as 0.3 % of spurious void content — a fifth of
    the whole acceptance limit, produced by a rounding nobody records.
    """

    displaced = dry_mass_g - immersed_mass_g
    if displaced <= 0:
        raise ValueError("immersed mass must be less than dry mass")
    return dry_mass_g * fluid_density_g_cm3 / displaced


# --------------------------------------------------------------------------
# Debulk model
# --------------------------------------------------------------------------

#: Interply air fraction in an as-laid stack before any debulk.  Engineering
#: target; DOE-2 measures it.
INITIAL_ENTRAPPED_AIR = 0.055
#: Fraction of remaining entrapped air removed per debulk cycle.
DEBULK_REMOVAL_EFFICIENCY = 0.55
#: Air fraction no amount of room-temperature debulking removes: it needs the
#: resin to be mobile, which means the flow dwell in the cure cycle.
DEBULK_AIR_FLOOR = 0.004


def entrapped_air_after_debulks(cycles: int) -> float:
    """Predicted entrapped air fraction after ``cycles`` debulks.

    Geometric decay to a floor.  The shape matters more than the constants:
    the first debulk does most of the work, the third does little, and no
    number of debulks reaches zero — which is why the cure cycle's flow dwell
    exists and why "debulk more" is not the answer to a porosity problem.
    """

    if cycles < 0:
        raise ValueError("debulk cycles must be non-negative")
    above_floor = max(INITIAL_ENTRAPPED_AIR - DEBULK_AIR_FLOOR, 0.0)
    return DEBULK_AIR_FLOOR + above_floor * (1.0 - DEBULK_REMOVAL_EFFICIENCY) ** cycles


def required_debulk_cycles(target_void_fraction: float, *, limit: int = 12) -> int:
    """Fewest debulks whose predicted entrapped air meets a target."""

    if target_void_fraction <= DEBULK_AIR_FLOOR:
        return limit
    for cycles in range(limit + 1):
        if entrapped_air_after_debulks(cycles) <= target_void_fraction:
            return cycles
    return limit


def debulk_schedule(ply_count: int, *, plies_per_debulk: int = 3) -> tuple[int, ...]:
    """Ply numbers after which a debulk is taken.

    A debulk after the first ply is not tradition either: the first ply
    against the tool decides the moulded surface, and an unbagged first ply
    bridges every radius in the tool.
    """

    if ply_count <= 0:
        raise ValueError("ply count must be positive")
    if plies_per_debulk <= 0:
        raise ValueError("plies per debulk must be positive")
    points = [1] if ply_count > 1 else []
    points.extend(
        ply for ply in range(plies_per_debulk, ply_count, plies_per_debulk) if ply > 1
    )
    points.append(ply_count)  # final debulk before bagging for cure
    return tuple(sorted(set(points)))


# --------------------------------------------------------------------------
# Panel records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PanelRecord:
    """What a shop measures on a cured panel or a cut-up coupon."""

    panel_id: str
    part_id: str
    material: str
    ply_count: int
    #: Mean cured thickness from a caliper map, mm.
    measured_thickness_mm: float
    #: Density by immersion, g/cm^3.
    measured_density_g_cm3: float
    #: Optional digestion result; when present it replaces the assumed fibre
    #: content in the void calculation, which is the more defensible route.
    digestion_resin_mass_fraction: float | None = None
    cure_cycle_id: str = ""
    debulk_cycles: int = 0
    operator: str = ""
    note: str = ""


@dataclass(frozen=True)
class PanelResult:
    panel_id: str
    part_id: str
    fibre_volume_fraction: float
    void_fraction: float
    theoretical_density_g_cm3: float
    measured_density_g_cm3: float
    cured_ply_thickness_mm: float
    nominal_cured_ply_thickness_mm: float
    thickness_deviation_fraction: float
    void_limit: float
    checks: tuple[dict[str, object], ...]
    accepted: bool
    #: Stiffness knockdown implied by the measured fibre content relative to
    #: nominal.  A panel can be inside every limit and still be 6 % softer
    #: than the model assumed, and the stress analyst needs to hear that.
    stiffness_ratio_vs_nominal: float


def evaluate_panel(record: PanelRecord) -> PanelResult:
    """Accept or reject one panel against the constituent-content limits."""

    mat: PlyMaterial = lookup_material(record.material)
    vf = fibre_volume_fraction(
        ply_count=record.ply_count,
        fibre_areal_weight_gsm=mat.fibre_areal_weight_gsm,
        thickness_mm=record.measured_thickness_mm,
        fibre_density_g_cm3=mat.fibre_density_g_cm3,
    )
    if record.digestion_resin_mass_fraction is not None:
        # Digestion gives mass fractions; converting to a volume fraction
        # needs the densities, and doing it this way removes the dependence
        # on an assumed areal weight.
        resin_wf = record.digestion_resin_mass_fraction
        fibre_wf = 1.0 - resin_wf
        specific_volume = fibre_wf / mat.fibre_density_g_cm3 + resin_wf / mat.resin_density_g_cm3
        vf_for_density = (fibre_wf / mat.fibre_density_g_cm3) / specific_volume
    else:
        vf_for_density = vf

    theoretical = theoretical_density_g_cm3(
        fibre_volume_fraction=vf_for_density,
        fibre_density_g_cm3=mat.fibre_density_g_cm3,
        resin_density_g_cm3=mat.resin_density_g_cm3,
    )
    voids = void_fraction(
        measured_density_g_cm3=record.measured_density_g_cm3,
        theoretical_density_g_cm3=theoretical,
    )
    cpt = record.measured_thickness_mm / record.ply_count
    nominal_cpt = mat.cured_ply_thickness_mm
    deviation = cpt / nominal_cpt - 1.0
    void_limit = (
        MAX_VOID_FRACTION_CRITICAL
        if record.part_id in CRITICAL_PART_IDS
        else MAX_VOID_FRACTION_GENERAL
    )

    checks = (
        {
            "name": "void_fraction",
            "actual": round(voids, 5),
            "limit": void_limit,
            "comparison": "<=",
            "passed": voids <= void_limit,
            "consequence": "interlaminar and compression strength fall with porosity",
        },
        {
            "name": "void_fraction_not_negative",
            "actual": round(voids, 5),
            "limit": -0.002,
            "comparison": ">=",
            "passed": voids >= -0.002,
            "consequence": "negative porosity is impossible; the inputs disagree",
        },
        {
            "name": "fibre_volume_fraction",
            "actual": round(vf, 4),
            "limit": [MIN_FIBRE_VOLUME_FRACTION, MAX_FIBRE_VOLUME_FRACTION],
            "comparison": "within",
            "passed": MIN_FIBRE_VOLUME_FRACTION <= vf <= MAX_FIBRE_VOLUME_FRACTION,
            "consequence": "resin-rich is heavy and soft; starved hides dry fibre",
        },
        {
            "name": "cured_ply_thickness_mm",
            "actual": round(cpt, 4),
            "limit": round(nominal_cpt, 4),
            "comparison": f"+/-{CPT_TOLERANCE_FRACTION:.0%}",
            "passed": abs(deviation) <= CPT_TOLERANCE_FRACTION,
            "consequence": "thickness feeds the tolerance stack and the mass budget",
        },
    )

    return PanelResult(
        panel_id=record.panel_id,
        part_id=record.part_id,
        fibre_volume_fraction=round(vf, 4),
        void_fraction=round(voids, 5),
        theoretical_density_g_cm3=round(theoretical, 4),
        measured_density_g_cm3=record.measured_density_g_cm3,
        cured_ply_thickness_mm=round(cpt, 4),
        nominal_cured_ply_thickness_mm=nominal_cpt,
        thickness_deviation_fraction=round(deviation, 4),
        void_limit=void_limit,
        checks=checks,
        accepted=all(check["passed"] for check in checks),
        stiffness_ratio_vs_nominal=round(vf / mat.nominal_fibre_volume_fraction, 4),
    )


#: A worked example panel, kept in the module so the arithmetic is exercised
#: by CI and so a technician has a filled-in record to copy.  The numbers are
#: a *plausible* first article, not a measurement: it is deliberately a
#: slightly thick, slightly porous panel of the kind a first cure produces.
EXAMPLE_PANEL = PanelRecord(
    panel_id="PNL-EXAMPLE-001",
    part_id="CS-400",
    material="PW-C-193",
    ply_count=8,
    measured_thickness_mm=1.664,
    measured_density_g_cm3=1.527,
    cure_cycle_id="CC-180-STD",
    debulk_cycles=3,
    operator="example record; not a measurement",
    note="illustrative first-article panel used to exercise the acceptance path",
)


def snapshot() -> dict[str, object]:
    result = evaluate_panel(EXAMPLE_PANEL)
    return {
        "limits": {
            "max_void_fraction_general": MAX_VOID_FRACTION_GENERAL,
            "max_void_fraction_critical": MAX_VOID_FRACTION_CRITICAL,
            "fibre_volume_fraction_band": [
                MIN_FIBRE_VOLUME_FRACTION,
                MAX_FIBRE_VOLUME_FRACTION,
            ],
            "cpt_tolerance_fraction": CPT_TOLERANCE_FRACTION,
            "critical_parts": sorted(CRITICAL_PART_IDS),
        },
        "debulk_model": {
            "initial_entrapped_air": INITIAL_ENTRAPPED_AIR,
            "removal_efficiency_per_cycle": DEBULK_REMOVAL_EFFICIENCY,
            "floor": DEBULK_AIR_FLOOR,
            "basis": "engineering target; DOE-2 replaces these constants",
            "air_after_cycles": {
                str(cycles): round(entrapped_air_after_debulks(cycles), 5)
                for cycles in range(6)
            },
            "cycles_for_general_limit": required_debulk_cycles(MAX_VOID_FRACTION_GENERAL),
            "cycles_for_critical_limit": required_debulk_cycles(MAX_VOID_FRACTION_CRITICAL),
            "schedule_for_8_ply": debulk_schedule(8),
        },
        "example_panel": {**asdict(EXAMPLE_PANEL), "result": asdict(result)},
    }


def main() -> int:
    print(json.dumps(snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
