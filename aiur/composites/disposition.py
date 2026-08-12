"""Defect disposition: deciding what to do with the part that came out wrong.

Some parts come out of the bag wrong.  A shop's answer to that is usually a
conversation, and the conversation usually turns on how the part looks and
how far behind schedule the programme is.  This module makes it an
arithmetic question instead: given a defect of a stated kind, size and
location, what does it cost the part, and does the part still meet its
requirements.

Four defects get real analysis here, because they are the four that cannot
be judged by eye.

**Delamination** is sized by *sublaminate buckling*.  The plies above a
delamination form a small plate bonded around its edge; under in-plane
compression that plate buckles, and once it buckles the delamination grows.
The critical size follows from the sublaminate's own bending stiffness,
which classical laminate theory already provides.

The result inverts the intuition the name invites.  A **shallow**
delamination is far worse than a deep one: the sublaminate above a
near-surface delamination is one thin ply with almost no bending stiffness,
so it buckles at a radius of under a millimetre in the throat cup, while the
same delamination at mid-thickness tolerates several. The dangerous case is
the one hardest to detect and easiest to write off as cosmetic, so the
acceptance limits here are **depth-dependent** and the shallow limit is the
tight one.

**Fibre waviness** — a wrinkle or marcel — is sized by compressive kinking.
A composite in compression fails by microbuckling of fibres that are already
slightly misaligned, so an added wrinkle adds directly to that misalignment
and the strength falls roughly as ``1/(gamma_y + theta)``.  The numbers are
brutal and correct: a 1-degree wrinkle costs a quarter of the compressive
strength and a 2-degree wrinkle costs 42 %.  This is why a wrinkle is a
structural defect rather than a cosmetic one, and why a shop that "rolls
them out" is doing something else.

**Porosity** is dispositioned against the acceptance limits in
:mod:`aiur.composites.process`, which are themselves an industry convention
this programme has adopted rather than derived — so the disposition says
that, rather than implying the limit is a measurement.

**Ply misorientation** is sized by the laminate's rotational stiffness
envelope, the same calculation the conical throat cup is designed around.
A laminate that is in-plane isotropic barely notices a misplaced ply; a
unidirectional-dominated one loses stiffness in proportion.

Repair is the other half.  A scarf repair's required taper follows from the
same shear-lag physics as any bonded joint: the parent laminate's stress
divided by the adhesive's shear strength.  That gives 1:13 for the tine,
against the 1:20 to 1:50 that shops actually cut — and the gap is not
conservatism for its own sake.  It is peel, which the shear calculation does
not see; the outer plies of a scarf carrying more than their share; and a
repair being made by hand in worse conditions than the original.

One rule sits above all of it: **a repair to a critical part needs the same
qualification the original part needed.**  A bonded repair to the retention
path is a bonded joint on the retention path, and inherits every control in
PS-400 including the proof test.  Programmes that treat repair as a shop
activity rather than an engineering one discover this the hard way.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math

from .clt import Laminate
from .flatpattern import rotational_envelope
from .materials import material as lookup_material
from .process import (
    CRITICAL_PART_IDS,
    MAX_VOID_FRACTION_CRITICAL,
    MAX_VOID_FRACTION_GENERAL,
)
from .schedules import schedule

#: Buckling coefficient for a clamped circular plate under uniform in-plane
#: compression: ``N_cr = 14.68 D / a^2``.  Clamped is the right edge
#: condition for a delamination — the sublaminate is continuous with the
#: parent all the way round its boundary — and it is the *less* conservative
#: of the two standard cases, which is stated rather than left implicit.
CLAMPED_CIRCULAR_BUCKLING_COEFFICIENT = 14.68

#: Initial fibre misalignment already present in a well-made laminate, rad.
#: It is what makes a real composite's compressive strength finite, and an
#: added wrinkle adds to it rather than replacing it.  Engineering target.
INITIAL_MISALIGNMENT_RAD = math.radians(1.5)

#: Taper ratios for a scarf repair.  The computed requirement comes out near
#: 1:13; shops cut 1:20 to 1:50, and the difference is peel, load
#: distribution across the scarf, and the conditions a repair is made in.
MIN_SCARF_RATIO = 20.0

#: Knockdown applied to any bonded repair relative to a factory bond, to
#: account for the surface preparation and cure a repair actually gets.
#: Engineering target; CP-09's surface-preparation arm is what replaces it.
REPAIR_BOND_KNOCKDOWN = 0.7


class DefectType(str, Enum):
    DELAMINATION = "delamination"
    POROSITY = "porosity"
    FIBRE_WAVINESS = "fibre_waviness"
    PLY_MISORIENTATION = "ply_misorientation"
    FOREIGN_OBJECT = "foreign_object"
    SURFACE_DAMAGE = "surface_damage"


class Disposition(str, Enum):
    ACCEPT = "accept"
    #: Acceptable once a named analysis has been run and recorded.
    ACCEPT_WITH_ANALYSIS = "accept_with_analysis"
    REPAIR = "repair"
    SCRAP = "scrap"


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


def sublaminate(laminate: Laminate, plies_above: int) -> Laminate:
    """The plies outboard of a delamination, as their own laminate.

    ``plies_above`` counts from the tool surface, which is ``plies[0]``.
    """

    if not 0 < plies_above < laminate.ply_count:
        raise ValueError("a delamination lies between plies, not outside the laminate")
    return Laminate(laminate.plies[:plies_above])


def critical_delamination_radius_mm(
    laminate: Laminate,
    *,
    plies_above: int,
    compressive_strain: float,
) -> float:
    """Radius at which a delaminated sublaminate buckles, mm.

    A clamped circular plate of radius ``a`` buckles at ``N_cr = 14.68 D /
    a^2``.  Setting that against the running load the sublaminate carries at
    the applied strain and solving for ``a`` gives the size at which the
    delamination starts to grow.
    """

    if compressive_strain <= 0:
        return math.inf
    sub = sublaminate(laminate, plies_above)
    bending = sub.d_matrix()[0][0]
    extensional = sub.a_matrix()[0][0]
    return math.sqrt(
        CLAMPED_CIRCULAR_BUCKLING_COEFFICIENT * bending / (extensional * compressive_strain)
    )


def waviness_knockdown(wrinkle_angle_deg: float, *, material_name: str) -> float:
    """Compressive strength remaining after an added fibre wave, as a fraction.

    Compressive failure of a fibre composite is microbuckling into a kink
    band, and the strength scales as ``1 / (gamma_y + theta)`` where
    ``gamma_y`` is the matrix shear yield strain and ``theta`` the fibre
    misalignment.  A well-made laminate already carries an initial
    misalignment; a wrinkle adds to it.
    """

    if wrinkle_angle_deg < 0:
        raise ValueError("wrinkle angle must be non-negative")
    mat = lookup_material(material_name)
    shear_yield_strain = mat.s12_mpa / mat.g12_mpa
    baseline = shear_yield_strain + INITIAL_MISALIGNMENT_RAD
    return baseline / (baseline + math.radians(wrinkle_angle_deg))


def scarf_ratio_required(
    *, parent_stress_mpa: float, adhesive_shear_strength_mpa: float
) -> float:
    """Taper ratio ``L/t`` for a scarf repair to carry the parent laminate.

    A scarf at a shallow angle turns the parent's axial stress into adhesive
    shear of about ``sigma / ratio``, so the ratio required is simply the
    stress divided by the adhesive's strength.
    """

    if adhesive_shear_strength_mpa <= 0:
        raise ValueError("adhesive shear strength must be positive")
    return parent_stress_mpa / adhesive_shear_strength_mpa


def parent_stress_mpa(part_id: str) -> float:
    """Axial stress in a part's laminate at its own first-ply failure, MPa."""

    laminate = schedule(part_id).laminate()
    running_load = laminate.response(n_per_mm=(1.0, 0.0, 0.0)).first_ply_failure_ratio
    return running_load / laminate.thickness_mm


def governing_compressive_strain(part_id: str) -> float:
    """Largest compressive surface strain the part sees in its load cases."""

    item = schedule(part_id)
    laminate = item.laminate()
    worst = 0.0
    for case in item.load_cases:
        response = laminate.response(
            n_per_mm=case.n_per_mm,
            m_per_mm=case.m_per_mm,
            delta_t_k=case.delta_t_k,
            shrinkage_fraction=case.shrinkage_fraction,
            edge=case.edge,
        )
        for ply in response.plies:
            worst = max(worst, -min(ply.strain_xy[0], 0.0))
    return worst


# --------------------------------------------------------------------------
# Defect records and disposition
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DefectRecord:
    """A defect as an inspector records it."""

    defect_id: str
    part_id: str
    serial: str
    defect_type: DefectType
    #: Largest in-plane dimension, mm.  For porosity, unused.
    size_mm: float = 0.0
    #: Plies between the tool surface and the defect, for a delamination.
    plies_above: int = 0
    #: Void volume fraction, for porosity.
    void_fraction: float = 0.0
    #: Out-of-plane wave angle, degrees, for waviness.
    wrinkle_angle_deg: float = 0.0
    #: Orientation error, degrees, for a misplaced ply.
    misorientation_deg: float = 0.0
    location: str = ""
    note: str = ""


@dataclass(frozen=True)
class DispositionResult:
    defect_id: str
    part_id: str
    defect_type: str
    critical_part: bool
    disposition: str
    #: The computed quantity the disposition turned on.
    governing_quantity: str
    actual: float | str
    limit: float | str
    rationale: str
    repair_scheme: str = ""


def _delamination(record: DefectRecord, critical: bool) -> DispositionResult:
    laminate = schedule(record.part_id).laminate()
    plies_above = max(record.plies_above, 1)
    strain = governing_compressive_strain(record.part_id)
    critical_radius = critical_delamination_radius_mm(
        laminate, plies_above=plies_above, compressive_strain=strain
    )
    radius = record.size_mm / 2.0

    if critical:
        # The retention path is single-load-path and its failure drops an
        # aircraft. A delamination there is rejected whatever the buckling
        # arithmetic says, because the arithmetic describes this defect and
        # the defect is evidence that the process produced others.
        return DispositionResult(
            record.defect_id, record.part_id, record.defect_type.value, True,
            Disposition.SCRAP.value,
            "delamination on a critical part",
            record.size_mm,
            0.0,
            (
                "No delamination is accepted on the retention path. The "
                f"sublaminate would not buckle below a {critical_radius:.1f} mm "
                "radius, so this is not a strength decision: a delamination is "
                "evidence of a process escape on a part whose failure drops a "
                "captured aircraft, and one found is not evidence the others "
                "are absent."
            ),
        )

    if radius >= critical_radius:
        return DispositionResult(
            record.defect_id, record.part_id, record.defect_type.value, False,
            Disposition.REPAIR.value,
            "delamination radius vs sublaminate buckling",
            round(radius, 2), round(critical_radius, 2),
            (
                f"The {plies_above}-ply sublaminate above this delamination "
                f"buckles at a {critical_radius:.1f} mm radius under the part's "
                f"governing compressive strain of {strain:.4f}. Past that the "
                "delamination grows under load."
            ),
            repair_scheme=(
                f"scarf repair at 1:{MIN_SCARF_RATIO:g} through the affected plies"
            ),
        )

    return DispositionResult(
        record.defect_id, record.part_id, record.defect_type.value, False,
        Disposition.ACCEPT_WITH_ANALYSIS.value,
        "delamination radius vs sublaminate buckling",
        round(radius, 2), round(critical_radius, 2),
        (
            f"Below the {critical_radius:.1f} mm buckling radius for a "
            f"{plies_above}-ply sublaminate. Acceptance is conditional on "
            "recording the size and depth: a shallower delamination of the same "
            "size would not pass, because the sublaminate above it has almost "
            "no bending stiffness."
        ),
    )


def _porosity(record: DefectRecord, critical: bool) -> DispositionResult:
    limit = MAX_VOID_FRACTION_CRITICAL if critical else MAX_VOID_FRACTION_GENERAL
    if record.void_fraction <= limit:
        return DispositionResult(
            record.defect_id, record.part_id, record.defect_type.value, critical,
            Disposition.ACCEPT.value,
            "void fraction", round(record.void_fraction, 4), limit,
            (
                "Inside the acceptance limit. That limit is an industry "
                "convention this programme has adopted, not one it has derived: "
                "CP-04 measures short-beam strength against porosity and is what "
                "turns it into a limit with a basis."
            ),
        )
    return DispositionResult(
        record.defect_id, record.part_id, record.defect_type.value, critical,
        Disposition.SCRAP.value,
        "void fraction", round(record.void_fraction, 4), limit,
        (
            "Porosity is distributed through the laminate, so there is nothing "
            "local to repair. It is also not a strength question alone: this "
            "panel's cure or debulk went wrong, and the finding belongs against "
            "the process, not just the part."
        ),
    )


def _waviness(record: DefectRecord, critical: bool) -> DispositionResult:
    laminate = schedule(record.part_id).laminate()
    material_name = laminate.plies[0].material
    remaining = waviness_knockdown(record.wrinkle_angle_deg, material_name=material_name)
    # A wrinkle is tolerable only where the compressive margin can absorb it.
    item = schedule(record.part_id)
    worst_ratio = min(
        (
            laminate.response(
                n_per_mm=case.n_per_mm, m_per_mm=case.m_per_mm,
                delta_t_k=case.delta_t_k, shrinkage_fraction=case.shrinkage_fraction,
                edge=case.edge,
            ).first_ply_failure_ratio
            / case.min_strength_ratio
        )
        for case in item.load_cases
    )
    survives = worst_ratio * remaining >= 1.0

    if critical or not survives:
        return DispositionResult(
            record.defect_id, record.part_id, record.defect_type.value, critical,
            Disposition.SCRAP.value,
            "compressive strength remaining after kinking knockdown",
            round(remaining, 3), 1.0,
            (
                f"A {record.wrinkle_angle_deg:g} degree wave leaves "
                f"{remaining:.0%} of the compressive strength. Out-of-plane "
                "waviness cannot be repaired — the fibre is already where it is "
                "— and on a critical part it is not accepted at any angle."
            ),
        )
    return DispositionResult(
        record.defect_id, record.part_id, record.defect_type.value, critical,
        Disposition.ACCEPT_WITH_ANALYSIS.value,
        "compressive strength remaining after kinking knockdown",
        round(remaining, 3), round(1.0 / worst_ratio, 3),
        (
            f"A {record.wrinkle_angle_deg:g} degree wave leaves {remaining:.0%} "
            f"of compressive strength, and this part carries {worst_ratio:.1f} "
            "times its requirement, so the margin absorbs it. The knockdown is "
            "recorded against the part, not forgiven."
        ),
    )


def _misorientation(record: DefectRecord, critical: bool) -> DispositionResult:
    laminate = schedule(record.part_id).laminate()
    envelope = rotational_envelope(
        laminate, span_deg=max(record.misorientation_deg, 1.0), step_deg=0.5
    )
    nominal = laminate.engineering_constants()["ex_mpa"]
    # The largest *deviation* either way, not only the loss.  A misplaced ply
    # that happens to stiffen the axial direction has still moved the part
    # away from what was analysed, and reporting only a one-sided loss would
    # have returned a reassuring zero for exactly that case.
    loss = max(
        abs(envelope["ex_min_mpa"] - nominal), abs(envelope["ex_max_mpa"] - nominal)
    ) / nominal
    if critical:
        return DispositionResult(
            record.defect_id, record.part_id, record.defect_type.value, True,
            Disposition.SCRAP.value,
            "stiffness loss from misorientation", round(loss, 4), 0.0,
            (
                "A misplaced ply on the retention path is not accepted. The "
                f"computed stiffness deviation is {loss:.1%}, which is small — and "
                "the reason for rejection is that the error was not caught at "
                "the layup hold point, so nothing establishes what else the "
                "stack contains."
            ),
        )
    return DispositionResult(
        record.defect_id, record.part_id, record.defect_type.value, False,
        Disposition.ACCEPT_WITH_ANALYSIS.value,
        "stiffness loss from misorientation", round(loss, 4), 0.10,
        (
            f"A {record.misorientation_deg:g} degree error moves axial stiffness "
            f"by {loss:.1%} on this laminate. A near-isotropic stack barely "
            "notices; a unidirectional-dominated one would not survive the same "
            "error, which is why this is computed per part rather than tabulated."
        ),
    )


def _foreign_object_or_surface(record: DefectRecord, critical: bool) -> DispositionResult:
    if record.defect_type is DefectType.FOREIGN_OBJECT:
        return DispositionResult(
            record.defect_id, record.part_id, record.defect_type.value, critical,
            Disposition.SCRAP.value,
            "foreign object in the laminate", record.size_mm, 0.0,
            (
                "A foreign object is a planar inclusion with no adhesion across "
                "it — a delamination that was built in. It cannot be removed "
                "without cutting the laminate open."
            ),
        )
    return DispositionResult(
        record.defect_id, record.part_id, record.defect_type.value, critical,
        Disposition.REPAIR.value if record.size_mm > 5.0 else Disposition.ACCEPT.value,
        "surface damage extent", record.size_mm, 5.0,
        (
            "Surface damage confined to the sacrificial glass ply is cosmetic "
            "and is filled. Damage into the carbon is structural, and is scarfed "
            "and patched to the plies it reaches."
        ),
        repair_scheme="resin fill for glass-only damage; scarf and patch into carbon",
    )


_HANDLERS = {
    DefectType.DELAMINATION: _delamination,
    DefectType.POROSITY: _porosity,
    DefectType.FIBRE_WAVINESS: _waviness,
    DefectType.PLY_MISORIENTATION: _misorientation,
    DefectType.FOREIGN_OBJECT: _foreign_object_or_surface,
    DefectType.SURFACE_DAMAGE: _foreign_object_or_surface,
}


def disposition(record: DefectRecord) -> DispositionResult:
    """Disposition one recorded defect."""

    critical = record.part_id in CRITICAL_PART_IDS
    handler = _HANDLERS[record.defect_type]
    return handler(record, critical)


def repair_scheme(part_id: str, *, adhesive_shear_strength_mpa: float = 35.0) -> dict:
    """The scarf repair this part would need, and why practice cuts deeper."""

    laminate = schedule(part_id).laminate()
    stress = parent_stress_mpa(part_id)
    computed = scarf_ratio_required(
        parent_stress_mpa=stress, adhesive_shear_strength_mpa=adhesive_shear_strength_mpa
    )
    specified = max(MIN_SCARF_RATIO, computed)
    return {
        "part_id": part_id,
        "laminate_thickness_mm": round(laminate.thickness_mm, 3),
        "parent_stress_mpa": round(stress, 1),
        "computed_scarf_ratio": round(computed, 1),
        "specified_scarf_ratio": round(specified, 1),
        "scarf_length_mm": round(specified * laminate.thickness_mm, 1),
        "repair_bond_knockdown": REPAIR_BOND_KNOCKDOWN,
        "critical_part": part_id in CRITICAL_PART_IDS,
        "qualification": (
            "A repair to a critical part is a bonded joint on the retention "
            "path and inherits every control in PS-400, including the proof "
            "test. It is not a shop activity."
            if part_id in CRITICAL_PART_IDS
            else "Repair per PS-400; surface preparation and bondline recorded."
        ),
        "note": (
            f"Shear alone asks for 1:{computed:.0f}. The specified "
            f"1:{specified:.0f} covers peel, which the shear calculation does "
            "not see; the outer plies of a scarf carrying more than their "
            "share; and a repair being made by hand in worse conditions than "
            "the original part."
        ),
    }


#: Worked examples, kept so the paths are exercised in CI and so a reviewer
#: can see what each disposition looks like.  These are illustrative records,
#: not findings against real hardware.
EXAMPLE_DEFECTS: tuple[DefectRecord, ...] = (
    DefectRecord(
        "NCR-EX-001", "CS-100", "CS-100-SN002", DefectType.DELAMINATION,
        size_mm=4.0, plies_above=3, location="mid-cone, 40 mm from the throat",
        note="found by tap test after demould",
    ),
    DefectRecord(
        "NCR-EX-002", "CS-100", "CS-100-SN003", DefectType.DELAMINATION,
        size_mm=4.0, plies_above=1, location="under the outer glass ply",
        note="same size as NCR-EX-001, one ply deep instead of three",
    ),
    DefectRecord(
        "NCR-EX-003", "CS-300", "CS-300-SN001", DefectType.FIBRE_WAVINESS,
        wrinkle_angle_deg=2.0, size_mm=25.0, location="over the rail radius",
    ),
    DefectRecord(
        "NCR-EX-004", "CS-100", "CS-100-SN004", DefectType.PLY_MISORIENTATION,
        misorientation_deg=8.0, location="ply 3 laid off the zero mark",
    ),
    DefectRecord(
        "NCR-EX-005", "CS-400", "CS-400-SN002", DefectType.DELAMINATION,
        size_mm=2.0, plies_above=4, location="tine root",
    ),
    DefectRecord(
        "NCR-EX-006", "CS-300", "CS-300-SN002", DefectType.POROSITY,
        void_fraction=0.031, location="throughout",
    ),
)


def snapshot() -> dict[str, object]:
    results = [disposition(record) for record in EXAMPLE_DEFECTS]
    return {
        "units": {"length": "mm", "angle": "deg"},
        "critical_parts": sorted(CRITICAL_PART_IDS),
        "constants": {
            "clamped_circular_buckling_coefficient": CLAMPED_CIRCULAR_BUCKLING_COEFFICIENT,
            "initial_misalignment_deg": round(math.degrees(INITIAL_MISALIGNMENT_RAD), 2),
            "min_scarf_ratio": MIN_SCARF_RATIO,
            "repair_bond_knockdown": REPAIR_BOND_KNOCKDOWN,
        },
        "waviness_knockdown_curve": {
            f"{angle:g}deg": round(waviness_knockdown(angle, material_name="PW-C-193"), 3)
            for angle in (0.5, 1.0, 2.0, 3.0, 5.0)
        },
        "delamination_limits": [
            {
                "part_id": part_id,
                "governing_compressive_strain": round(governing_compressive_strain(part_id), 5),
                "critical_radius_mm": {
                    f"{depth}_plies_above": round(
                        critical_delamination_radius_mm(
                            schedule(part_id).laminate(),
                            plies_above=depth,
                            compressive_strain=governing_compressive_strain(part_id),
                        ),
                        2,
                    )
                    for depth in (1, schedule(part_id).laminate().ply_count // 2)
                },
            }
            for part_id in ("CS-100", "CS-300", "CS-400")
        ],
        "repair_schemes": [repair_scheme(part_id) for part_id in ("CS-100", "CS-300", "CS-400")],
        "example_dispositions": [asdict(result) for result in results],
    }


def main() -> int:
    print(json.dumps(snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
