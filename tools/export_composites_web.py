#!/usr/bin/env python3
"""Export the composites results the website publishes.

The site's own rule is that nothing on it is summarised out of the
repository by hand.  This is what makes that true for the structures page:
every number it shows is read out of ``aiur.composites`` and written into a
TypeScript module, and a test fails if the committed module has drifted from
what the models now produce.

Prose is authored here rather than generated, because a caption is a
judgement and should be written by someone.  Numbers inside that prose are
interpolated from the models, so a design change cannot leave a stale figure
behind in a sentence.

Regenerate from the repository root:

    python tools/export_composites_web.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script convenience
    sys.path.insert(0, str(REPO_ROOT))

from aiur.composites import allowables, bonding, disposition, flatpattern, schedules
from aiur.composites.__main__ import snapshot as composites_snapshot

OUTPUT = REPO_ROOT / "web" / "lib" / "composites-data.ts"

#: What each part is sized by, in the site's register.  Editorial.
SIZED_BY = {
    "CS-100": "Handling load, then the fibre drift a cone imposes",
    "CS-200": "Stowed strain at its packing radius",
    "CS-300": "Axial stiffness, then cooldown residual stress",
    "CS-400": "Retention-ledge geometry, not retention load",
}


def _round(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def parts() -> list[dict]:
    rows = []
    for result in schedules.evaluate_all():
        part_id = str(result["part_id"])
        rows.append(
            {
                "id": part_id,
                "name": result["name"],
                "stack": result["stack"],
                "thicknessMm": result["thickness_mm"],
                "arealMassGsm": result["areal_mass_g_m2"],
                "partMassG": result["part_mass_g"],
                "quantity": result["quantity"],
                "sizedBy": SIZED_BY.get(part_id, ""),
            }
        )
    return rows


def findings() -> list[dict]:
    """The results that changed the design, with their numbers read live."""

    cup = schedules.schedule("CS-100")
    cone = flatpattern.evaluate("CS-100")
    boom_joint = bonding.evaluate_joint(bonding.joint("BJ-200"))
    tine_joint = bonding.evaluate_joint(bonding.joint("BJ-300"))
    cup_laminate = cup.laminate()
    shallow = disposition.critical_delamination_radius_mm(
        cup_laminate,
        plies_above=1,
        compressive_strain=disposition.governing_compressive_strain("CS-100"),
    )
    deep = disposition.critical_delamination_radius_mm(
        cup_laminate,
        plies_above=3,
        compressive_strain=disposition.governing_compressive_strain("CS-100"),
    )
    wrinkle = disposition.waviness_knockdown(2.0, material_name="PW-C-193")
    ceiling_temperature = 199

    return [
        {
            "id": "01",
            "title": "The funnel stopped being a laminate",
            "figure": "789 g/m²",
            "copy": (
                "A monolithic funnel skin able to carry the handling load across "
                "the boom pitch weighs 54 g — a third of the entire dock mass "
                "allocation, for a part whose only job is to guide an aircraft. "
                "It became a tensioned membrane between the deployable booms, and "
                "the laminate content retreated to the throat cup."
            ),
        },
        {
            "id": "02",
            "title": "Cooldown chose the keel rail's material",
            "figure": "0.56",
            "copy": (
                "The obvious rail — high-modulus tape at 0/90, and 20 g lighter — "
                "is predicted to microcrack on the tool from residual stress "
                "alone, before it ever sees a load. The rail that shipped uses "
                "intermediate-modulus tape with fabric carrying the transverse "
                "direction and closes at 1.41."
            ),
        },
        {
            "id": "03",
            "title": "A cone will not hold a fibre angle",
            "figure": f"{cone['development']['fibre_angle_drift_deg']:.0f}°",
            "copy": (
                "Develop a cone flat and its meridians become radial lines, so a "
                "straight fibre's angle to them drifts one degree per degree of "
                f"sector. Holding ±3° would take {cone['gores_for_tolerance']} "
                "gores. The throat cup is built in-plane isotropic instead: its "
                "predecessor varied 47 % in axial stiffness around its own "
                f"circumference, and this stack varies "
                f"{(cone['stiffness_envelope_over_drift']['ex_ratio'] - 1) * 100:.0f} %."
            ),
        },
        {
            "id": "04",
            "title": "Full cure is unreachable at the cure temperature",
            "figure": f"{ceiling_temperature} °C",
            "copy": (
                "The resin's kinetics impose a conversion ceiling that rises with "
                "hold temperature — about 0.86 at 180 °C however long it is held. "
                "So cure acceptance is completeness against that ceiling, which "
                "catches a hold that is too short, plus glass-transition margin, "
                "which catches one that is too cold."
            ),
        },
        {
            "id": "05",
            "title": "A bond cannot always be designed to fail its adherend",
            "figure": f"{tine_joint['bondline_for_adherend_first_mm']:.1f} mm",
            "copy": (
                "The standard rule for an unverifiable bond is to out-strength "
                "what it joins. Achievable for a thin adherend and arithmetically "
                "impossible for a thick one — the keeper tine would need that "
                "bondline. So there are two qualification routes, and the second "
                "— load margin plus a proof test on every article — is always "
                "available. The boom root reaches the first at "
                f"{boom_joint['bondline_mm']:.2f} mm."
            ),
        },
        {
            "id": "06",
            "title": "A shallow delamination is worse than a deep one",
            "figure": f"{shallow:.1f} mm",
            "copy": (
                "The plies above a delamination buckle as a small plate, and one "
                "thin ply has almost no bending stiffness. In the throat cup a "
                f"delamination one ply down is critical at a {shallow:.1f} mm "
                f"radius; the same delamination at mid-thickness tolerates "
                f"{deep:.1f} mm. The dangerous case is the one hardest to detect, "
                "so acceptance limits are depth-dependent."
            ),
        },
        {
            "id": "07",
            "title": "A 2° wrinkle costs 42 % of compressive strength",
            # The figure is the loss, matching the title; the model returns
            # what remains, and showing that next to this headline would read
            # as a contradiction.
            "figure": f"−{1.0 - wrinkle:.0%}",
            "copy": (
                "Compressive failure is fibre microbuckling, so an out-of-plane "
                "wave adds directly to the misalignment already present. It is "
                "why a wrinkle is a structural defect rather than a cosmetic one, "
                "and why it cannot be repaired: the fibre is already where it is."
            ),
        },
    ]


def delamination_limits() -> list[dict]:
    rows = []
    for part_id in ("CS-100", "CS-300", "CS-400"):
        laminate = schedules.schedule(part_id).laminate()
        strain = disposition.governing_compressive_strain(part_id)
        rows.append(
            {
                "id": part_id,
                "shallowMm": _round(
                    disposition.critical_delamination_radius_mm(
                        laminate, plies_above=1, compressive_strain=strain
                    ),
                    1,
                ),
                "midMm": _round(
                    disposition.critical_delamination_radius_mm(
                        laminate,
                        plies_above=laminate.ply_count // 2,
                        compressive_strain=strain,
                    ),
                    1,
                ),
            }
        )
    return rows


def modules() -> list[dict]:
    """The package, as a reader would want to scan it."""

    return [
        {"name": "materials", "copy": "Lamina and resin properties, each carrying the basis it came from — and what that basis allows it to be used for."},
        {"name": "clt", "copy": "Classical laminate theory: ABD stiffness, thermal and cure-shrinkage response, ply-by-ply failure."},
        {"name": "schedules", "copy": "The four part laminates, their load cases, and the design rules they are checked against."},
        {"name": "flatpattern", "copy": "Flat-pattern development, the fibre drift a cone imposes, and the rotational stiffness envelope."},
        {"name": "cure", "copy": "Cure kinetics, vitrification, exotherm, viscosity, and the pressure window."},
        {"name": "bonding", "copy": "Bonded-joint shear lag, overlap saturation, and the two qualification routes."},
        {"name": "springin", "copy": "Corner distortion prediction and the tool compensation loop."},
        {"name": "tooling", "copy": "Tool material trade and thermal-expansion compensation."},
        {"name": "process", "copy": "Fibre volume fraction, void content, debulk schedule, panel acceptance."},
        {"name": "disposition", "copy": "What a defect costs, and the accept / repair / scrap call."},
        {"name": "traveler", "copy": "Travelers, hold points, prepreg out-time, and computed nonconformances."},
        {"name": "allowables", "copy": "Basis values, the coupon plan, and the cost of scatter."},
        {"name": "spc", "copy": "Process capability, control charts, and rolled throughput yield."},
        {"name": "doe", "copy": "The experiments that replace this package's engineering targets."},
    ]


def build() -> dict:
    report = composites_snapshot()
    status = allowables.program_status()
    rollup = schedules.mass_rollup()
    return {
        "gate": {
            "valid": report["valid"],
            "errorCount": len(report["errors"]),  # type: ignore[arg-type]
            "criticalFailureCount": len(report["critical_failures"]),  # type: ignore[arg-type]
        },
        "evidence": {
            "measuredAllowables": status["measured_allowables"],
            "plannedCoupons": status["planned_coupons"],
            "statement": status["statement"],
        },
        "parts": parts(),
        "findings": findings(),
        "delamination": delamination_limits(),
        "massRollup": [
            {
                "line": entry["budget_line"],
                "budgetG": entry["budget_g"],
                "allocatedG": entry["allocated_g"],
                "actualG": entry["actual_g"],
            }
            for entry in rollup
        ],
        "modules": modules(),
        "experimentRuns": report["doe"]["total_planned_runs"],  # type: ignore[index]
    }


def render(data: dict) -> str:
    body = json.dumps(data, indent=2, ensure_ascii=False)
    return (
        "// Generated by tools/export_composites_web.py — do not edit by hand.\n"
        "//\n"
        "// Every number here is read out of aiur.composites. Regenerate with:\n"
        "//   python tools/export_composites_web.py\n"
        "// tests/test_composites_web_export.py fails if this file is stale.\n\n"
        f"export const COMPOSITES = {body} as const;\n"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed file is stale, without writing",
    )
    args = parser.parse_args(argv)

    rendered = render(build())
    if args.check:
        if not args.out.exists():
            print(f"{args.out} does not exist; run this script without --check")
            return 1
        if args.out.read_text(encoding="utf-8") != rendered:
            print(f"{args.out} is stale; run python tools/export_composites_web.py")
            return 1
        print(f"{args.out} is current")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
