"""Designed experiments for the CARRIER-P0 composites process.

Every other module in this package leans on at least one number that is an
engineering target rather than a measurement, and each of those targets is
named where it is used.  This module is the plan that converts them.  It is
short on purpose: four experiments, each answering a question that something
downstream is currently guessing at, ordered so that the guess blocking the
most work is settled first.

The designs are two-level factorials, which is the right instrument for this
job and not an obvious one.  A shop faced with a porosity problem naturally
changes one thing at a time — more debulks this week, higher vacuum next —
and one-factor-at-a-time has two defects that matter here.  It cannot see
interactions, and porosity is *made of* interactions: the effect of pressure
timing depends entirely on how much air the debulks left behind.  And it is
inefficient — a factorial estimates every main effect using every run, so a
sixteen-run factorial resolves three factors and their interactions more
precisely than forty-eight runs of one-at-a-time.

Two disciplines make the difference between a designed experiment and a batch
of parts:

**Randomised run order.**  Tool wear, ambient humidity, operator learning and
the ageing of a prepreg roll all drift over the days a campaign takes.  Run
the low settings on Monday and the high settings on Friday and the experiment
measures the week.  Randomisation converts that drift from a bias into noise,
and the order here is generated from a recorded seed so it is reproducible
and cannot be quietly "improved" on the floor.

**Stated power.**  An experiment that cannot resolve an effect worth acting
on is worth neither the material nor the oven time.
:func:`minimum_detectable_effect` gives the smallest effect a design can
distinguish from noise, and every experiment below carries the number.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Sequence

#: Standard normal deviate at 95 % two-sided confidence, used for the
#: minimum-detectable-effect estimate.  A normal approximation rather than a
#: t quantile: at the run counts here it is within about 10 %, and the number
#: it produces is a planning figure, not an inference.
_Z_95 = 1.959964


@dataclass(frozen=True)
class Factor:
    """One controlled variable, at two levels."""

    name: str
    low: str
    high: str
    units: str
    rationale: str


@dataclass(frozen=True)
class Response:
    """One measured outcome, and what it feeds."""

    name: str
    method: str
    units: str
    feeds: str


@dataclass(frozen=True)
class Experiment:
    """A designed experiment with a question, a design, and a consumer."""

    doe_id: str
    question: str
    #: The specific assumption in this package that the experiment replaces.
    replaces: str
    factors: tuple[Factor, ...]
    responses: tuple[Response, ...]
    replicates: int = 2
    #: Runs made at the centre of the design space, which detect curvature —
    #: a factorial alone assumes the response is planar between its levels.
    centre_points: int = 0
    #: Assumed run-to-run standard deviation of the primary response, in the
    #: primary response's units. An engineering target; the first replicate
    #: set measures it and the plan is re-sized.
    assumed_sigma: float = 0.0
    blocking: str = ""
    note: str = ""

    @property
    def factor_count(self) -> int:
        return len(self.factors)

    @property
    def runs(self) -> int:
        return 2 ** self.factor_count * self.replicates + self.centre_points


def design_matrix(factor_count: int, replicates: int = 1) -> tuple[tuple[int, ...], ...]:
    """Full-factorial design in coded units, ``-1`` and ``+1``.

    Standard order: the first factor alternates fastest.  Standard order is
    for reading, never for running — see :func:`run_order`.
    """

    if factor_count < 1:
        raise ValueError("a design needs at least one factor")
    if replicates < 1:
        raise ValueError("at least one replicate is required")
    rows = []
    for _ in range(replicates):
        for index in range(2 ** factor_count):
            rows.append(
                tuple(1 if (index >> position) & 1 else -1 for position in range(factor_count))
            )
    return tuple(rows)


def run_order(run_count: int, seed: int) -> tuple[int, ...]:
    """Reproducible randomised run order.

    A deterministic shuffle from a recorded seed: the order is random with
    respect to the design and identical every time the plan is regenerated,
    so the traveler and the plan cannot disagree about which run was which.
    Uses the standard library's Mersenne Twister through an explicit
    ``Random`` instance, so it neither depends on nor disturbs global state.
    """

    from random import Random

    order = list(range(run_count))
    Random(seed).shuffle(order)
    return tuple(order)


def minimum_detectable_effect(
    *, sigma: float, runs: int, confidence_z: float = _Z_95
) -> float:
    """Smallest factor effect distinguishable from noise, in response units.

    In a two-level factorial an effect is the difference between the mean of
    the half of the runs at the high level and the mean of the half at the
    low level, so its standard error is ``2 sigma / sqrt(N)``.
    """

    if sigma < 0:
        raise ValueError("sigma must be non-negative")
    if runs < 2:
        raise ValueError("at least two runs are required")
    return confidence_z * 2.0 * sigma / math.sqrt(runs)


def main_effects(
    design: Sequence[Sequence[int]], responses: Sequence[float]
) -> tuple[float, ...]:
    """Main effect of each factor: mean at ``+1`` minus mean at ``-1``."""

    if len(design) != len(responses):
        raise ValueError("design and response lengths differ")
    if not design:
        raise ValueError("no runs")
    factor_count = len(design[0])
    effects = []
    for column in range(factor_count):
        high = [value for row, value in zip(design, responses) if row[column] > 0]
        low = [value for row, value in zip(design, responses) if row[column] < 0]
        if not high or not low:
            raise ValueError(f"factor {column} is not varied")
        effects.append(sum(high) / len(high) - sum(low) / len(low))
    return tuple(effects)


def interaction_effect(
    design: Sequence[Sequence[int]],
    responses: Sequence[float],
    factor_a: int,
    factor_b: int,
) -> float:
    """Two-factor interaction, computed on the product column.

    An interaction that rivals a main effect means the two factors cannot be
    set independently — which is the finding, not a complication.
    """

    products = [row[factor_a] * row[factor_b] for row in design]
    return main_effects([(value,) for value in products], responses)[0]


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

DOE_1 = Experiment(
    doe_id="DOE-1",
    question=(
        "What are this lot's cure kinetics, and how far does a part on its tool "
        "lag the oven?"
    ),
    replaces=(
        "the handbook kinetic, DiBenedetto and viscosity constants in "
        "aiur.composites.materials, and the assumed oven film coefficient in "
        "aiur.composites.cure"
    ),
    factors=(
        Factor("heating rate", "1", "5", "degC/min",
               "the DSC scan rate set needed to fit an activation energy"),
        Factor("tool thermal mass", "bare panel", "6 mm aluminium tool", "-",
               "the cure model predicts the tool dominates the lag; this measures it"),
    ),
    responses=(
        Response("degree of cure", "DSC residual exotherm", "-",
                 "the conversion ceiling and completeness criteria in cure.py"),
        Response("glass transition", "DSC or DMA", "degC",
                 "the service-margin acceptance criterion"),
        Response("part-to-air lag", "instrumented panel, part thermocouples", "K",
                 "whether a cure recipe can be run as written"),
        Response("minimum viscosity and gel time", "rheometer", "Pa.s, min",
                 "the pressure application window on the traveler"),
    ),
    replicates=2,
    assumed_sigma=0.02,
    note=(
        "Runs first because everything else is downstream of it. Until it "
        "runs, every cure cycle in this package is a starting point for a "
        "trial rather than a qualified process."
    ),
)

DOE_2 = Experiment(
    doe_id="DOE-2",
    question="What actually controls porosity in this cell?",
    replaces=(
        "the debulk model constants in aiur.composites.process, and the "
        "assumption that the computed pressure window is the right one"
    ),
    factors=(
        Factor("debulk cycles", "1", "3", "count",
               "the model predicts sharply diminishing returns; the third debulk "
               "is either the difference between accept and reject or it is pure cost"),
        Factor("pressure application", "at 60 degC", "at the computed flow window", "-",
               "the traveler's most time-critical instruction, currently justified "
               "only by a model"),
        Factor("vacuum level", "-70", "-95", "kPa gauge",
               "separates air removal from resin mobility as the governing mechanism"),
    ),
    responses=(
        Response("void fraction", "ASTM D2734 from density", "-",
                 "the acceptance limit in process.py"),
        Response("cured ply thickness", "micrometer map", "mm",
                 "the fibre volume fraction and the mass budget"),
        Response("short-beam strength", "ASTM D2344", "MPa",
                 "converts a void fraction into a strength consequence"),
    ),
    replicates=2,
    centre_points=2,
    assumed_sigma=0.004,
    blocking="one panel set per day, blocked by day to absorb ambient humidity",
    note=(
        "The interaction between debulk count and pressure timing is the "
        "result this experiment exists for: if pressure timing only matters "
        "when the stack is under-debulked, the cheap fix is debulks and the "
        "traveler's hardest instruction can be relaxed."
    ),
)

DOE_3 = Experiment(
    doe_id="DOE-3",
    question="How much does a moulded corner move, and what moves it?",
    replaces=(
        "the zero tool-interaction allowance in aiur.composites.springin and the "
        "assumed post-gel shrinkage fraction in aiur.composites.schedules"
    ),
    factors=(
        Factor("cure temperature", "120", "180", "degC",
               "separates the thermal component of spring-in from the chemical one, "
               "which no single-temperature experiment can do"),
        Factor("tool material", "aluminium", "carbon tooling laminate", "-",
               "tool-part interaction scales with the CTE mismatch at the interface"),
        Factor("release system", "semi-permanent", "film", "-",
               "the interface shear that drives tool-part interaction"),
    ),
    responses=(
        Response("moulded angle deviation", "CMM against the compensated nominal", "deg",
                 "the spring-in compensation applied to every tool"),
        Response("flat-panel warp", "surface plate and feeler", "mm",
                 "the tool-interaction term, which spring-in theory does not predict"),
    ),
    replicates=2,
    assumed_sigma=0.08,
    note=(
        "The two responses are separated deliberately. Radford's model "
        "predicts corner angle and says nothing about warp in a flat panel, "
        "so warp is the clean measurement of the tool-interaction term."
    ),
)

DOE_4 = Experiment(
    doe_id="DOE-4",
    question="How repeatable is ply placement, and does it matter?",
    replaces=(
        "the assumption implicit in every laminate schedule that a ply laid at "
        "45 degrees is at 45 degrees"
    ),
    factors=(
        Factor("cutting method", "hand shears to a marked pattern", "template", "-",
               "the cheapest available process control, if it earns its cost"),
        Factor("operator", "operator A", "operator B", "-",
               "operator-to-operator variation is a real component of scatter and "
               "is almost never measured"),
    ),
    responses=(
        Response("fibre orientation error", "photographed ply against a reference grid", "deg",
                 "the coefficient of variation that sets the coupon count in allowables.py"),
        Response("tensile modulus", "ASTM D3039", "GPa",
                 "converts an orientation error into a stiffness consequence"),
    ),
    replicates=3,
    assumed_sigma=0.8,
    note=(
        "A two-degree mean orientation error is worth about one percent of "
        "modulus and is not the point. The point is the spread: scatter is "
        "what drives coupon count, and coupon count is what a qualification "
        "campaign costs."
    ),
)

EXPERIMENTS: tuple[Experiment, ...] = (DOE_1, DOE_2, DOE_3, DOE_4)


def plan(experiment: Experiment, *, seed: int = 1) -> dict[str, object]:
    """Expand an experiment into a runnable, randomised run sheet."""

    design = design_matrix(experiment.factor_count, experiment.replicates)
    total_runs = len(design) + experiment.centre_points
    order = run_order(total_runs, seed)
    rows = []
    for position, run_index in enumerate(order):
        if run_index < len(design):
            coded = design[run_index]
            settings = {
                factor.name: (factor.high if level > 0 else factor.low)
                for factor, level in zip(experiment.factors, coded)
            }
        else:
            coded = tuple(0 for _ in experiment.factors)
            settings = {factor.name: "centre" for factor in experiment.factors}
        rows.append(
            {
                "run_order": position + 1,
                "design_row": run_index + 1,
                "coded": list(coded),
                "settings": settings,
            }
        )
    return {
        "doe_id": experiment.doe_id,
        "seed": seed,
        "runs": total_runs,
        "factorial_runs": len(design),
        "centre_points": experiment.centre_points,
        "minimum_detectable_effect": (
            round(
                minimum_detectable_effect(sigma=experiment.assumed_sigma, runs=total_runs), 5
            )
            if experiment.assumed_sigma > 0
            else None
        ),
        "assumed_sigma": experiment.assumed_sigma,
        "run_sheet": rows,
    }


def validate_experiments() -> list[str]:
    """Every experiment must name what it replaces and be able to see it."""

    errors: list[str] = []
    seen: set[str] = set()
    for experiment in EXPERIMENTS:
        if experiment.doe_id in seen:
            errors.append(f"{experiment.doe_id}: duplicate id")
        seen.add(experiment.doe_id)
        if not experiment.replaces:
            errors.append(
                f"{experiment.doe_id}: does not name the assumption it replaces; an "
                "experiment with no consumer is a hobby"
            )
        if not experiment.factors:
            errors.append(f"{experiment.doe_id}: no factors")
        if not experiment.responses:
            errors.append(f"{experiment.doe_id}: no responses")
        if experiment.replicates < 2:
            errors.append(
                f"{experiment.doe_id}: fewer than two replicates leaves no estimate of "
                "run-to-run variation, so no effect can be called significant"
            )
        for response in experiment.responses:
            if not response.feeds:
                errors.append(
                    f"{experiment.doe_id}: response {response.name!r} does not say what "
                    "it feeds"
                )
    return errors


def snapshot(seed: int = 1) -> dict[str, object]:
    errors = validate_experiments()
    return {
        "valid": not errors,
        "errors": errors,
        "total_planned_runs": sum(experiment.runs for experiment in EXPERIMENTS),
        "experiments": [
            {
                **asdict(experiment),
                "runs": experiment.runs,
                "plan": plan(experiment, seed=seed),
            }
            for experiment in EXPERIMENTS
        ],
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
