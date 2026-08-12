"""Process capability and yield tracking for the composites cell.

Repeatability is a measurable quantity, and most composite shops do not
measure it.  They measure conformance — parts pass or fail — which answers
"did this part work" and cannot answer "will the next twenty".  Those are
different questions, and only the second one lets a program commit to a
build schedule.

Two tools, both standard, both applied here to the specific quantities that
decide whether a CARRIER-P0 laminate is what its stress model assumed:

**Capability.**  ``Cp`` compares the width of the specification to the width
of the process; ``Cpk`` also accounts for where the process is *centred*.
The gap between them is the most useful diagnostic in the set: a process
with high ``Cp`` and low ``Cpk`` is precise and mis-aimed, which is a
half-day of adjustment.  A process with low ``Cp`` is simply too variable,
which is weeks of work.  Telling them apart before starting is the whole
point.

**Control charts.**  Capability describes a stable process.  A process that
is drifting has no single capability, so the control chart comes first: it
detects the drift, and only then does the capability number mean anything.
The limits here are the classical Shewhart X-bar and R limits with the
usual subgroup constants.

The quantities tracked are cured ply thickness, void fraction and part mass,
because between them they capture consolidation, porosity and resin content
— and because all three are cheap.  A shop that measures nothing else still
knows whether it is in control.

Yield is tracked as **rolled throughput yield** rather than final yield, on
purpose.  A cell with five 95 %-yielding steps reports 95 % five times and
delivers 77 %, and the difference is the rework that nobody budgeted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Sequence

from .allowables import mean, standard_deviation

#: Capability floor for a controlled process.  1.33 is the ordinary
#: manufacturing target; 1.0 means the specification and the process are the
#: same width, so a third of a percent of parts fail on arithmetic alone.
MIN_CPK = 1.33
#: Capability floor for a characteristic on a critical part.
MIN_CPK_CRITICAL = 1.67

#: Shewhart subgroup constants for X-bar and R charts, indexed by subgroup
#: size.  Standard tabulated values.
SUBGROUP_CONSTANTS: dict[int, tuple[float, float, float, float]] = {
    # n: (A2, D3, D4, d2)
    2: (1.880, 0.0, 3.267, 1.128),
    3: (1.023, 0.0, 2.574, 1.693),
    4: (0.729, 0.0, 2.282, 2.059),
    5: (0.577, 0.0, 2.114, 2.326),
    6: (0.483, 0.0, 2.004, 2.534),
}


@dataclass(frozen=True)
class Capability:
    characteristic: str
    n: int
    mean: float
    standard_deviation: float
    lower_spec: float | None
    upper_spec: float | None
    cp: float | None
    cpk: float
    #: Expected fraction outside specification if the process stays as it is.
    expected_defect_rate: float
    meets_target: bool
    diagnosis: str


def _normal_tail(z: float) -> float:
    """Upper tail of the standard normal, via the error function."""

    return 0.5 * math.erfc(z / math.sqrt(2.0))


def capability(
    values: Sequence[float],
    *,
    characteristic: str,
    lower_spec: float | None = None,
    upper_spec: float | None = None,
    target_cpk: float = MIN_CPK,
) -> Capability:
    """Compute ``Cp`` / ``Cpk`` and the defect rate they imply."""

    if lower_spec is None and upper_spec is None:
        raise ValueError("at least one specification limit is required")
    if lower_spec is not None and upper_spec is not None and upper_spec <= lower_spec:
        raise ValueError("upper specification must exceed lower")

    average = mean(values)
    sigma = standard_deviation(values)
    if sigma <= 0:
        raise ValueError("a capability index needs non-zero variation")

    cp = None
    if lower_spec is not None and upper_spec is not None:
        cp = (upper_spec - lower_spec) / (6.0 * sigma)

    candidates = []
    if upper_spec is not None:
        candidates.append((upper_spec - average) / (3.0 * sigma))
    if lower_spec is not None:
        candidates.append((average - lower_spec) / (3.0 * sigma))
    cpk = min(candidates)

    defect_rate = 0.0
    if upper_spec is not None:
        defect_rate += _normal_tail((upper_spec - average) / sigma)
    if lower_spec is not None:
        defect_rate += _normal_tail((average - lower_spec) / sigma)

    if cp is not None and cp >= target_cpk and cpk < target_cpk:
        diagnosis = (
            "precise but off-centre: the spread fits the specification, the mean "
            "does not sit in it. Adjust the process setting, do not widen the spec."
        )
    elif cpk >= target_cpk:
        diagnosis = "capable"
    else:
        diagnosis = (
            "too variable: centring the process would not make it capable. The "
            "variation itself has to be reduced."
        )

    return Capability(
        characteristic=characteristic,
        n=len(values),
        mean=round(average, 5),
        standard_deviation=round(sigma, 6),
        lower_spec=lower_spec,
        upper_spec=upper_spec,
        cp=None if cp is None else round(cp, 3),
        cpk=round(cpk, 3),
        expected_defect_rate=round(defect_rate, 6),
        meets_target=cpk >= target_cpk,
        diagnosis=diagnosis,
    )


@dataclass(frozen=True)
class ControlChart:
    characteristic: str
    subgroup_size: int
    subgroups: int
    grand_mean: float
    mean_range: float
    xbar_upper: float
    xbar_lower: float
    range_upper: float
    range_lower: float
    #: Estimate of process sigma from the ranges, which is the within-subgroup
    #: variation and therefore the process's own noise rather than its drift.
    sigma_from_range: float
    out_of_control_subgroups: tuple[int, ...]
    in_control: bool


def control_chart(subgroups: Sequence[Sequence[float]], *, characteristic: str) -> ControlChart:
    """Shewhart X-bar and R limits from a set of equal-sized subgroups."""

    if not subgroups:
        raise ValueError("at least one subgroup is required")
    size = len(subgroups[0])
    if any(len(group) != size for group in subgroups):
        raise ValueError("all subgroups must be the same size")
    if size not in SUBGROUP_CONSTANTS:
        raise ValueError(f"no constants for subgroup size {size}; use 2 to 6")

    a2, d3, d4, d2 = SUBGROUP_CONSTANTS[size]
    means = [mean(group) for group in subgroups]
    ranges = [max(group) - min(group) for group in subgroups]
    grand = mean(means)
    mean_range = mean(ranges)

    xbar_upper = grand + a2 * mean_range
    xbar_lower = grand - a2 * mean_range
    range_upper = d4 * mean_range
    range_lower = d3 * mean_range

    offenders = tuple(
        index
        for index, (average, spread) in enumerate(zip(means, ranges))
        if not (xbar_lower <= average <= xbar_upper) or not (range_lower <= spread <= range_upper)
    )
    return ControlChart(
        characteristic=characteristic,
        subgroup_size=size,
        subgroups=len(subgroups),
        grand_mean=round(grand, 5),
        mean_range=round(mean_range, 5),
        xbar_upper=round(xbar_upper, 5),
        xbar_lower=round(xbar_lower, 5),
        range_upper=round(range_upper, 5),
        range_lower=round(range_lower, 5),
        sigma_from_range=round(mean_range / d2, 6),
        out_of_control_subgroups=offenders,
        in_control=not offenders,
    )


# --------------------------------------------------------------------------
# Yield
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessStep:
    """One step in the composites cell, with its first-pass yield."""

    step_id: str
    name: str
    units_started: int
    units_passed_first_time: int
    #: Units recovered by rework. They count as delivered, not as yield.
    units_reworked: int = 0

    @property
    def first_pass_yield(self) -> float:
        if self.units_started <= 0:
            raise ValueError(f"{self.step_id}: units started must be positive")
        return self.units_passed_first_time / self.units_started

    @property
    def units_out(self) -> int:
        return self.units_passed_first_time + self.units_reworked


def rolled_throughput_yield(steps: Sequence[ProcessStep]) -> float:
    """Probability a unit passes every step first time."""

    product = 1.0
    for step in steps:
        product *= step.first_pass_yield
    return product


def yield_report(steps: Sequence[ProcessStep]) -> dict[str, object]:
    """Where the yield actually goes, worst step first."""

    if not steps:
        raise ValueError("no steps")
    rty = rolled_throughput_yield(steps)
    final = steps[-1].units_out / steps[0].units_started
    ranked = sorted(steps, key=lambda step: step.first_pass_yield)
    return {
        "rolled_throughput_yield": round(rty, 4),
        "final_yield_including_rework": round(final, 4),
        # The gap between the two is rework: work that was done twice and
        # counted once, and the number a build schedule is broken by.
        "hidden_rework_fraction": round(final - rty, 4),
        "worst_step": {
            "step_id": ranked[0].step_id,
            "name": ranked[0].name,
            "first_pass_yield": round(ranked[0].first_pass_yield, 4),
        },
        "steps": [
            {
                **asdict(step),
                "first_pass_yield": round(step.first_pass_yield, 4),
                "units_out": step.units_out,
            }
            for step in steps
        ],
    }


#: An illustrative cell record.  These are *not* measurements — the cell does
#: not exist yet — but the shape is what the traveler data will reduce to,
#: and keeping a worked example in the module means the arithmetic is
#: exercised by CI rather than by a spreadsheet nobody has opened since.
EXAMPLE_CELL: tuple[ProcessStep, ...] = (
    ProcessStep("OP-10", "kit cutting", 40, 39, 1),
    ProcessStep("OP-20", "layup and debulk", 40, 34, 4),
    ProcessStep("OP-30", "bag and cure", 40, 37, 1),
    ProcessStep("OP-40", "trim and machine", 40, 36, 3),
    ProcessStep("OP-50", "inspection", 40, 38, 0),
)

#: Illustrative cured-ply-thickness measurements, mm, against the +-10 %
#: specification the process module holds on a 0.199 mm nominal ply.
EXAMPLE_CPT_SUBGROUPS: tuple[tuple[float, ...], ...] = (
    (0.204, 0.208, 0.203, 0.206),
    (0.207, 0.205, 0.209, 0.204),
    (0.210, 0.206, 0.208, 0.211),
    (0.205, 0.203, 0.207, 0.206),
    (0.209, 0.212, 0.208, 0.210),
    (0.206, 0.204, 0.205, 0.208),
)


def snapshot() -> dict[str, object]:
    flat = [value for group in EXAMPLE_CPT_SUBGROUPS for value in group]
    nominal = 0.199
    cpt_capability = capability(
        flat,
        characteristic="cured ply thickness (mm)",
        lower_spec=nominal * 0.90,
        upper_spec=nominal * 1.10,
    )
    chart = control_chart(EXAMPLE_CPT_SUBGROUPS, characteristic="cured ply thickness (mm)")
    return {
        "targets": {"min_cpk": MIN_CPK, "min_cpk_critical": MIN_CPK_CRITICAL},
        "status": (
            "no production data exists; the records below are illustrative and "
            "exercise the arithmetic. They are replaced by traveler data as soon "
            "as the cell runs."
        ),
        "example_capability": asdict(cpt_capability),
        "example_control_chart": asdict(chart),
        "example_yield": yield_report(EXAMPLE_CELL),
    }


def main() -> int:
    print(json.dumps(snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
