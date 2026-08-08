"""NASA-STD-7009B credibility scoring and results-uncertainty reporting.

A campaign report that prints "97.5% capture rate" and stops invites the
reader to treat a model claim as a hardware claim.  NASA-STD-7009B (2024)
exists for exactly that failure mode: it sets no pass thresholds — section
4.3.6 says the Standard "levies no requirements with respect to what levels
to achieve (the sufficiency threshold levels), merely that the levels be
determined and reported" — so the decision maker, not the analyst, weighs
the simulation.

This module implements the reporting side of that discipline for the aiur
twin:

* the eleven credibility factors of the **B** revision, split across the two
  assessments it defines — M&S Capability Assessment [M&S 48] (5 factors)
  and M&S Results Assessment [M&S 31] (6 factors) — each carrying the
  achieved level, the program-declared threshold ([M&S 43e]) and the gap
  between them, which [M&S 50] and [M&S 35] require to be reported;
* the explicit warning list of [M&S 32] (occurrences a-h);
* the results-uncertainty estimate of [M&S 33] plus the description of the
  process that produced it required by [M&S 34], as Wilson score intervals
  on the campaign's binomial rate metrics.

Scaling statement: CARRIER-P0 is a civilian indoor prototype.  There is no
technical authority, no independent M&S review, and nothing here is a claim
of compliance with NASA-STD-7009B.  What is adopted is the standard's
disclosure structure, because the failure it prevents — a model quietly
acquiring authority it never earned — is size-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

#: Cited edition.  Level tables referenced below are Appendix E of this
#: document; only the wording actually transcribed into this repository is
#: quoted, and factor scores that rest on an untranscribed table say so.
STANDARD = "NASA-STD-7009B (2024), Standard for Models and Simulations"

#: Verbatim level-0 definition, identical for every factor (Appendix E).
LEVEL_0_DEFINITION = "Insufficient evidence."

#: Levels are 0-4 and discrete: "The assessment of each factor level is a
#: discrete step function, with no intentions for partial credit at any
#: given level" (Appendix E.4.1/E.3.1).  A fractional or out-of-range level
#: is therefore not a conservative approximation, it is a category error.
MIN_LEVEL = 0
MAX_LEVEL = 4

#: Verbatim gating rule for the Validation factor (Appendix E.3.4, Table 9).
VALIDATION_GATING_RULE = (
    'For the validation factor, an assessment of any level above "1" is not '
    'permitted unless the conditions for "1" are satisfied, i.e., the model '
    "has to be conceptually validated before it is empirically validated."
)


class Assessment(str, Enum):
    """The two assessments the B revision replaced the A-revision scale with.

    The A revision's Development / Operations / Supporting-Evidence
    categories are deliberately absent: scoring against them and citing
    7009B would be citing a document that no longer says that.
    """

    #: Development-phase record per [M&S 48]; reported per [M&S 50].
    CAPABILITY = "m_s_capability_assessment"
    #: Use-phase record per [M&S 31]; reported per [M&S 35].
    RESULTS = "m_s_results_assessment"


class CredibilityFactor(str, Enum):
    """The eleven 7009B factors, in the order the standard lists them."""

    # M&S Capability Assessment [M&S 48] a-e.
    DATA_PEDIGREE = "m_s_data_pedigree"
    VERIFICATION = "m_s_verification"
    VALIDATION = "m_s_validation"
    DEVELOPMENT_TECHNICAL_REVIEW = "m_s_development_technical_review"
    DEVELOPMENT_PROCESS_PRODUCT_MANAGEMENT = (
        "m_s_development_process_product_management"
    )
    # M&S Results Assessment [M&S 31] a-f.
    USE_ASSESSMENT = "m_s_use_assessment"
    INPUT_PEDIGREE = "m_s_input_pedigree"
    UNCERTAINTY_CHARACTERIZATION = "m_s_uncertainty_characterization"
    RESULTS_ROBUSTNESS = "m_s_results_robustness"
    USE_ANALYSIS_TECHNICAL_REVIEW = "m_s_use_analysis_technical_review"
    USE_PROCESS_PRODUCT_MANAGEMENT = "m_s_use_process_product_management"

    @property
    def assessment(self) -> Assessment:
        return _FACTOR_METADATA[self][0]

    @property
    def display_name(self) -> str:
        return _FACTOR_METADATA[self][1]

    @property
    def level_table(self) -> str:
        """Appendix E table that defines this factor's level ladder."""

        return _FACTOR_METADATA[self][2]


#: (assessment, standard's factor name, level table) per factor.
_FACTOR_METADATA: dict[CredibilityFactor, tuple[Assessment, str, str]] = {
    CredibilityFactor.DATA_PEDIGREE: (
        Assessment.CAPABILITY,
        "M&S Data Pedigree",
        "Table 7",
    ),
    CredibilityFactor.VERIFICATION: (
        Assessment.CAPABILITY,
        "M&S Verification",
        "Table 8",
    ),
    CredibilityFactor.VALIDATION: (
        Assessment.CAPABILITY,
        "M&S Validation",
        "Table 9",
    ),
    CredibilityFactor.DEVELOPMENT_TECHNICAL_REVIEW: (
        Assessment.CAPABILITY,
        "M&S Development Technical Review",
        "Table 10",
    ),
    CredibilityFactor.DEVELOPMENT_PROCESS_PRODUCT_MANAGEMENT: (
        Assessment.CAPABILITY,
        "M&S Development Process/Product Management",
        "Table 11",
    ),
    CredibilityFactor.USE_ASSESSMENT: (
        Assessment.RESULTS,
        "M&S Use Assessment",
        "Table 15",
    ),
    CredibilityFactor.INPUT_PEDIGREE: (
        Assessment.RESULTS,
        "M&S Input Pedigree",
        "Table 16",
    ),
    CredibilityFactor.UNCERTAINTY_CHARACTERIZATION: (
        Assessment.RESULTS,
        "M&S Uncertainty Characterization",
        "Table 17",
    ),
    CredibilityFactor.RESULTS_ROBUSTNESS: (
        Assessment.RESULTS,
        "M&S Results Robustness",
        "Table 18",
    ),
    CredibilityFactor.USE_ANALYSIS_TECHNICAL_REVIEW: (
        Assessment.RESULTS,
        "M&S Use/Analysis Technical Review",
        "Table 19",
    ),
    CredibilityFactor.USE_PROCESS_PRODUCT_MANAGEMENT: (
        Assessment.RESULTS,
        "M&S Use Process/Product Management",
        "Table 20",
    ),
}

CREDIBILITY_FACTORS: tuple[CredibilityFactor, ...] = tuple(CredibilityFactor)


@dataclass(frozen=True)
class FactorScore:
    """One factor's achieved level against the level the program declared.

    ``justification`` is mandatory because an unjustified level is the exact
    thing this module exists to prevent: a number that looks like evidence.
    ``evidence`` names what a reader can go and check; it may be empty only
    at level 0, whose definition is literally "Insufficient evidence."
    """

    factor: CredibilityFactor
    level: int
    threshold: int
    justification: str
    evidence: tuple[str, ...] = ()
    #: Only consulted for the Validation factor, where Table 9 forbids any
    #: level above 1 unless the level-1 (conceptual validation) conditions
    #: hold.  Declaring it asserts: intended use clearly stated and
    #: understood, conceptual model/requirements/specifications correct and
    #: sufficient for the problem.
    level_1_conditions_met: bool = False

    def __post_init__(self) -> None:
        for name, value in (("level", self.level), ("threshold", self.threshold)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int in 0-4, not {value!r}")
            if not MIN_LEVEL <= value <= MAX_LEVEL:
                raise ValueError(f"{name} must be in {MIN_LEVEL}-{MAX_LEVEL}")
        if not self.justification.strip():
            raise ValueError(
                f"{self.factor.value}: a credibility level without a "
                "justification is a number pretending to be evidence"
            )
        if self.level > MIN_LEVEL and not any(
            item.strip() for item in self.evidence
        ):
            raise ValueError(
                f"{self.factor.value}: level {self.level} must name its "
                f"supporting evidence (level 0 is {LEVEL_0_DEFINITION!r})"
            )
        if (
            self.factor is CredibilityFactor.VALIDATION
            and self.level > 1
            and not self.level_1_conditions_met
        ):
            raise ValueError(
                "validation level above 1 without the level-1 conditions: "
                + VALIDATION_GATING_RULE
            )

    @property
    def gap(self) -> int:
        """Achieved minus declared threshold; negative is a deficiency."""

        return self.level - self.threshold

    @property
    def meets_threshold(self) -> bool:
        return self.gap >= 0

    def as_dict(self) -> dict[str, object]:
        return {
            "factor": self.factor.value,
            "name": self.factor.display_name,
            "assessment": self.factor.assessment.value,
            "level_table": self.factor.level_table,
            "level": self.level,
            "threshold": self.threshold,
            "gap": self.gap,
            "meets_threshold": self.meets_threshold,
            "justification": self.justification,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class CredibilityAssessment:
    """A complete scoring of all eleven factors for one M&S.

    Completeness is enforced rather than encouraged: [M&S 48] and [M&S 31]
    require a record "according to each of the following factors", so a
    partial scoring is not a weaker assessment — it is not an assessment,
    and omitting the factor that scores worst is the obvious abuse.
    """

    subject: str
    scored_on: str
    threshold_basis: str
    scores: tuple[FactorScore, ...]

    def __post_init__(self) -> None:
        seen = [score.factor for score in self.scores]
        if len(seen) != len(set(seen)):
            raise ValueError("a factor may be scored only once")
        missing = [f.value for f in CREDIBILITY_FACTORS if f not in set(seen)]
        if missing:
            raise ValueError(f"unscored credibility factors: {', '.join(missing)}")

    def score_for(self, factor: CredibilityFactor) -> FactorScore:
        for score in self.scores:
            if score.factor is factor:
                return score
        raise KeyError(f"unscored factor: {factor.value}")

    def for_assessment(self, assessment: Assessment) -> tuple[FactorScore, ...]:
        """Scores of one assessment, in the standard's listing order."""

        ordered = {score.factor: score for score in self.scores}
        return tuple(
            ordered[factor]
            for factor in CREDIBILITY_FACTORS
            if factor.assessment is assessment
        )

    def deficiencies(self) -> tuple[FactorScore, ...]:
        """Factors below their declared threshold ([M&S 50]/[M&S 35] gaps)."""

        ordered = {score.factor: score for score in self.scores}
        return tuple(
            ordered[factor]
            for factor in CREDIBILITY_FACTORS
            if not ordered[factor].meets_threshold
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "standard": STANDARD,
            "subject": self.subject,
            "scored_on": self.scored_on,
            "threshold_basis": self.threshold_basis,
            "capability_assessment": [
                score.as_dict() for score in self.for_assessment(Assessment.CAPABILITY)
            ],
            "results_assessment": [
                score.as_dict() for score in self.for_assessment(Assessment.RESULTS)
            ],
            "gaps": [
                {
                    "factor": score.factor.value,
                    "name": score.factor.display_name,
                    "level": score.level,
                    "threshold": score.threshold,
                    "gap": score.gap,
                }
                for score in self.deficiencies()
            ],
        }


#: The domain of use the twin is declared for.  Everything here is a
#: declaration, not a validated envelope — the twin has no empirical
#: referent at all — but naming it is what makes "this episode ran outside
#: it" a checkable statement instead of a feeling.
DECLARED_DOMAIN: tuple[str, ...] = (
    "indoor still air: zero mean flow, gust sigma <= 0.03 m/s (INDOOR_CALM)",
    "external optical relative positioning at sigma ~3 mm, 40 ms latency "
    "(LIGHTHOUSE_GRADE)",
    "one 4.5 m tethered carrier or bench rig, one active 180 mm funnel dock",
    "one or two Crazyflie-class ~37 g aircraft, sequential dock use",
    "closing speeds within the P0 capture envelope (<= 0.20 m/s)",
    "at most one injected fault per episode",
)

#: Outstanding M&S defects/problems, reported under [M&S 32]h.  These are
#: the known-missing physics of docs/digital-twin.md, restated with their
#: qualitative impact because [M&S 32] requires every warning to carry at
#: least a qualitative estimate of impact.
KNOWN_MODEL_DEFECTS: tuple[str, ...] = (
    "vehicle attitude dynamics are not modeled. Impact: funnel-lip to "
    "rotor-plane clearance under tilt cannot be assessed in the twin",
    "propeller downwash recirculating off the hull during terminal approach "
    "is not modeled. Impact: terminal-approach disturbance is optimistic by "
    "an unquantified amount",
    "aero interaction between aircraft is not modeled. Impact: SIL-D "
    "separation results are optimistic",
    "envelope deformation is not modeled. Impact: the keep-out ellipsoid is "
    "rigid where the real envelope is not",
    "positioning error is modeled as white noise plus injectable bias, with "
    "no systematic (non-white) error structure. Impact: the slow-bias "
    "residual of docs/digital-twin.md finding 3 cannot be sized in the twin",
    "the carrier trim transient on capture/release is not modeled: a 37 g "
    "aircraft changes carrier dead weight by ~0.36 N, more than the modeled "
    "0.3 N vertical thrust budget. Impact: the twin assumes a re-trim the "
    "real vehicle must actually perform every cycle",
)

#: Standing waiver reported under [M&S 32]g.
SCOPE_WAIVER = (
    "CARRIER-P0 applies NASA-STD-7009B's disclosure discipline by choice, "
    "scaled to a civilian indoor prototype. There is no technical "
    "authority, no independent M&S review board, and no formal acceptance "
    "of these assessments; every level below is self-assessed by the model's "
    "own authors. Impact: the credibility assessment is itself unreviewed "
    "evidence and should be read as a disclosure, not a certification."
)

_NO_EMPIRICAL_VALIDATION = (
    "no empirical validation: the M&S Validation factor stands at level {level} "
    "with zero referent measurements — the twin has never been compared "
    "against dock or flight hardware. Impact: every rate, closing speed and "
    "margin in this report is a statement about the model; the corresponding "
    "hardware value is unbounded by this evidence."
)


def warnings_for(
    assessment: CredibilityAssessment,
    *,
    unachieved_acceptance_criteria: Sequence[str] = (),
    violated_assumptions: Sequence[str] = (),
    outside_declared_domain: Sequence[str] = (),
    execution_warnings: Sequence[str] = (),
    use_issues: Sequence[str] = (),
    model_defects: Sequence[str] = KNOWN_MODEL_DEFECTS,
) -> tuple[str, ...]:
    """Build the [M&S 32] explicit-warning list for one result set.

    4.3.8.1 [M&S 32] enumerates eight occurrences (a-h) that must be flagged
    explicitly when results go to a decision maker, each "accompanied by at
    least a qualitative estimate of the impact of the occurrence".  The
    mapping used here:

    ==== ==============================================================
    a    factor levels below the thresholds declared per [M&S 43e], plus
         any caller-supplied unmet acceptance criterion (a failed gate
         criterion is an unachieved acceptance criterion)
    b    violated M&S assumptions
    c    exceeded M&S limits — episodes run outside :data:`DECLARED_DOMAIN`
    d    execution warnings/errors from the run
    e    unfavorable appropriateness-to-use outcome — carried permanently
         while the twin has no empirical referent
    f    setup/utilization issues
    g    waivers — the standing scope waiver above
    h    outstanding M&S defects — the known-missing physics
    ==== ==============================================================

    Occurrences e, g and h are unconditional today by construction: an
    uncalibrated model with a known-missing-physics list always has them,
    and a warning list that can silently become empty is how a caveat gets
    lost between the analyst and the decision.
    """

    warnings: list[str] = []

    for score in assessment.deficiencies():
        warnings.append(
            f"[M&S 32 a] unachieved acceptance criterion: {score.factor.display_name} "
            f"assessed at level {score.level}, below the declared threshold "
            f"{score.threshold} ([M&S 43e], {score.factor.level_table}). "
            f"Impact: this result is being used with {-score.gap} level(s) less "
            "credibility than the program itself declared it needs."
        )
    for text in unachieved_acceptance_criteria:
        warnings.append(
            f"[M&S 32 a] unachieved acceptance criterion: {text}. "
            "Impact: the campaign does not close its gate and is not "
            "promotion evidence."
        )
    for text in violated_assumptions:
        warnings.append(
            f"[M&S 32 b] violated assumption: {text}. "
            "Impact: results depending on that assumption are unsupported."
        )
    for text in outside_declared_domain:
        warnings.append(
            f"[M&S 32 c] M&S limit exceeded: {text}. "
            "Impact: those episodes ran outside the twin's declared domain of "
            "use; read them as exploratory model behaviour, never as gate "
            "evidence."
        )
    for text in execution_warnings:
        warnings.append(
            f"[M&S 32 d] execution warning: {text}. "
            "Impact: the run did not execute as intended and its statistics "
            "may not describe the intended scenario."
        )

    validation = assessment.score_for(CredibilityFactor.VALIDATION)
    if validation.level <= 1:
        warnings.append(
            "[M&S 32 e] " + _NO_EMPIRICAL_VALIDATION.format(level=validation.level)
        )

    for text in use_issues:
        warnings.append(
            f"[M&S 32 f] setup/utilization issue: {text}. "
            "Impact: the reported configuration may not be the configuration "
            "that ran."
        )
    warnings.append(f"[M&S 32 g] waiver: {SCOPE_WAIVER}")
    for text in model_defects:
        warnings.append(f"[M&S 32 h] outstanding M&S defect: {text}")
    return tuple(warnings)


def wilson_interval(
    successes: int,
    trials: int,
    z: float = 1.96,
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, as a (low, high) pair.

    With ``p̂ = successes/trials`` and standard-normal quantile ``z``
    (1.96 for a 95% two-sided interval)::

        center     = (p̂ + z²/2n) / (1 + z²/n)
        half_width = z/(1 + z²/n) · sqrt( p̂(1-p̂)/n + z²/4n² )

    Wilson rather than the normal-approximation (Wald) interval because
    every interval this program cares about sits next to p̂ = 1: a
    30-episode sweep bin at 30/30 has a Wald interval of exactly zero width,
    which is worse than reporting nothing.  Wilson stays inside [0, 1] and
    behaves at both endpoints; Brown, Cai & DasGupta (2001) recommend it
    over Wald generally.

    The interval covers Monte Carlo sampling error only.  It says nothing
    about whether the model is right — that is the Validation factor's job,
    and it is at level 1.
    """

    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= successes <= trials:
        raise ValueError("successes must be in 0..trials")
    if z <= 0:
        raise ValueError("z must be positive")

    n = float(trials)
    p_hat = successes / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denominator
    half_width = (z / denominator) * math.sqrt(
        p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n)
    )
    # Clamp: the algebra keeps the interval inside [0, 1], floating point
    # does not always agree at p̂ = 0 or 1.
    return (max(0.0, center - half_width), min(1.0, center + half_width))


@dataclass(frozen=True)
class RateInterval:
    """One reported rate metric with its Wilson interval, in percent.

    Percent because that is the unit the SIL gates and the reports already
    use; keeping the raw counts alongside it means a reader can recompute
    the interval instead of trusting this class.
    """

    metric: str
    successes: int
    trials: int
    z: float = 1.96

    def __post_init__(self) -> None:
        wilson_interval(self.successes, self.trials, self.z)  # validates

    @property
    def bounds(self) -> tuple[float, float]:
        return wilson_interval(self.successes, self.trials, self.z)

    @property
    def point(self) -> float:
        return self.successes / self.trials

    def as_dict(self) -> dict[str, object]:
        low, high = self.bounds
        return {
            "metric": self.metric,
            "successes": self.successes,
            "trials": self.trials,
            "point_pct": round(100.0 * self.point, 2),
            "ci_low_pct": round(100.0 * low, 2),
            "ci_high_pct": round(100.0 * high, 2),
            "method": "Wilson score interval",
            "z": self.z,
        }


#: [M&S 33]a — quantitative estimate of results uncertainty.
UNCERTAINTY_STATEMENT = (
    "Quantitative estimate ([M&S 33]a): rate metrics carry two-sided 95% "
    "Wilson score intervals (z=1.96) computed from the episode counts that "
    "produced them. The interval bounds Monte Carlo sampling error under the "
    "model's own assumptions and nothing else: it does not cover model-form "
    "error, parameter uncertainty (no input distribution is defined for any "
    "modeled coefficient), or the missing physics listed in the warnings. A "
    "narrow interval therefore means the campaign was large, not that the "
    "twin is right."
)

#: [M&S 34] — description of the process used to obtain the estimate.
UNCERTAINTY_PROCESS = (
    "Process ([M&S 34]): each episode is one seeded, independent Bernoulli "
    "trial of the scenario; the campaign reducer counts successes over "
    "fault-free episodes only, and aiur.sim.credibility.wilson_interval "
    "converts (successes, trials) to the interval. Determinism makes the "
    "estimate reproducible: identical (config, seed) pairs replay the same "
    "episodes byte for byte."
)


def uncertainty_block(
    intervals: Sequence[RateInterval],
    *,
    no_estimate_reason: str = "",
) -> dict[str, object]:
    """Assemble the [M&S 33]/[M&S 34] uncertainty section of a report.

    When no rate could be estimated, [M&S 33]c is satisfied explicitly — "a
    clear statement that no quantitative estimate or qualitative description
    of uncertainty is available" — rather than by omitting the section.
    """

    if intervals:
        statement = UNCERTAINTY_STATEMENT
    else:
        reason = no_estimate_reason or "no rate metric was estimable"
        statement = (
            "No quantitative estimate or qualitative description of results "
            f"uncertainty is available ([M&S 33]c): {reason}."
        )
    return {
        "statement": statement,
        "process": UNCERTAINTY_PROCESS,
        "rate_intervals": [interval.as_dict() for interval in intervals],
    }


def credibility_block(
    assessment: CredibilityAssessment,
    *,
    rate_intervals: Sequence[RateInterval] = (),
    no_estimate_reason: str = "",
    unachieved_acceptance_criteria: Sequence[str] = (),
    violated_assumptions: Sequence[str] = (),
    outside_declared_domain: Sequence[str] = (),
    execution_warnings: Sequence[str] = (),
    use_issues: Sequence[str] = (),
) -> dict[str, object]:
    """Format the whole disclosure block for embedding in a report dict.

    One block carries what 4.3.8 says a decision maker needs beyond the
    results themselves: the assessed levels and their gaps ([M&S 50],
    [M&S 35]), the explicit warnings ([M&S 32]), and the uncertainty
    estimate with its process ([M&S 33], [M&S 34]).
    """

    block = assessment.as_dict()
    block["declared_domain"] = list(DECLARED_DOMAIN)
    block["warnings"] = list(
        warnings_for(
            assessment,
            unachieved_acceptance_criteria=unachieved_acceptance_criteria,
            violated_assumptions=violated_assumptions,
            outside_declared_domain=outside_declared_domain,
            execution_warnings=execution_warnings,
            use_issues=use_issues,
        )
    )
    block["uncertainty"] = uncertainty_block(
        rate_intervals, no_estimate_reason=no_estimate_reason
    )
    return block


#: Honest scoring of the aiur twin as of 2026-08-08.  Every level below is
#: argued from what exists in this repository today; where the level table
#: itself is not transcribed here (Tables 10, 11, 15, 19, 20), the
#: justification says so and the score is deliberately conservative.
TWIN_CREDIBILITY = CredibilityAssessment(
    subject="aiur CARRIER-P0 digital twin (aiur/sim)",
    scored_on="2026-08-08",
    threshold_basis=(
        "Thresholds are declared per [M&S 43e] for the only decision the "
        "twin currently supports: may this software revision consume bench "
        "or flight time on the P0-B/P0-C articles? They are program "
        "judgement for an indoor civilian prototype, not levels imposed by "
        "any authority, and they must be re-declared before the twin is "
        "used for a different decision — predicting a hardware capture "
        "rate, for one, which it may not support at any threshold until the "
        "calibration ledger's replay step has run. Two asymmetries are "
        "deliberate: the development-side process threshold is set at what a "
        "prototype of this size can actually hold (version control, CI, a "
        "determinism contract), while the use-side process threshold is set "
        "one level higher because the hardware promotion contract in "
        "docs/engineering-loop.md already demands run identity on every test "
        "record, and twin results that gate hardware should not be held to a "
        "looser records rule than the hardware."
    ),
    scores=(
        FactorScore(
            factor=CredibilityFactor.DATA_PEDIGREE,
            level=1,
            threshold=2,
            justification=(
                "Sources of the development data are known and written down, "
                "but no dynamic coefficient traces to a measurement of the "
                "real dock: the calibration ledger's provenance states are "
                "'vendor' or 'estimate', never 'measured'. Table 7's level 2 "
                "additionally requires uncertainties in the data to be at "
                "least estimated, and no parameter here carries an "
                "uncertainty at all, so the level is 1."
            ),
            evidence=(
                "docs/digital-twin.md calibration ledger: vendor/estimate/"
                "measured provenance states, no 'measured' entry exists yet",
                "aiur/sim/disturbances.py and aiur/sim/sensors.py module "
                "docstrings label every preset an engineering estimate",
                "aiur/sim/dock_physics.py geometry follows the Rev-A build "
                "definition in hardware/dock/p0a-bench.md, which is itself "
                "'build definition, not measured hardware'",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.VERIFICATION,
            level=2,
            threshold=3,
            justification=(
                "Table 8 level 2: 'The model is correctly implemented as "
                "determined by documented verification practices, which "
                "evaluate all components, features, capabilities, and "
                "couplings of the model.' The unit suite exercises vectors, "
                "disturbances, bodies, sensors, dock mechanics, guidance, "
                "engine and campaign reduction, the real DockController runs "
                "un-mocked inside the twin, and the determinism contract is "
                "machine-checked. Level 3 is not claimed: there is no "
                "rigorous numerical-error estimate (no time-step convergence "
                "study) and the program has specified no numerical-error "
                "requirements for one to satisfy."
            ),
            evidence=(
                "tests/test_sim_physics.py, tests/test_sim_sensors_dock.py, "
                "tests/test_sim_guidance.py, tests/test_sim_campaign.py",
                "aiur/sim/engine.py drives aiur.dock_controller.DockController "
                "directly; docs/digital-twin.md 'What is real and what is "
                "modeled'",
                "determinism test: identical (config, seed) reproduces an "
                "episode's events, outcome and contact speeds exactly",
                "CI runs the SIL-B campaign at full size on every push",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.VALIDATION,
            level=1,
            threshold=2,
            level_1_conditions_met=True,
            justification=(
                "Conceptual validation only, per Table 9 level 1: the "
                "intended use is clearly stated (kill unsafe software and "
                "absurd concepts cheaply, not predict hardware success "
                "rates), and the conceptual model, its scope boundary and "
                "its missing physics are written down. There are zero "
                "empirical referent points — the twin has never been "
                "compared against dock or flight hardware — so no favorable "
                "comparison exists and Table 9 level 2 is unreachable by "
                "construction, not by judgement. The threshold of 2 closes "
                "when the calibration ledger's replay step runs against P0-A "
                "and P0-B measurements."
            ),
            evidence=(
                "docs/digital-twin.md status line: 'executable SIL stage, "
                "uncalibrated against flight hardware'",
                "docs/digital-twin.md calibration ledger steps 1-4, "
                "including the FAIL_MODEL disposition on divergence",
                "hardware/dock/fault-insertion.md: mode-by-mode comparison "
                "of twin faults against bench trials is defined but not run",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.DEVELOPMENT_TECHNICAL_REVIEW,
            level=0,
            threshold=1,
            justification=(
                "No technical review of the twin's development has been held "
                "by anyone independent of its authors, so the level is 0, "
                f"{LEVEL_0_DEFINITION!r} The adoption loop's review step "
                "reviews remediation tickets, not the model's development. "
                "Table 10's level wording is not transcribed in this "
                "repository; this score rests on the factor name and the "
                "verbatim level-0 definition only."
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.DEVELOPMENT_PROCESS_PRODUCT_MANAGEMENT,
            level=1,
            threshold=1,
            justification=(
                "Version control, CI on every push, a written determinism "
                "contract and a documented parameter-provenance scheme "
                "exist. There is no configuration-management plan for the "
                "twin as a product, no model release identity, and no "
                "change-control path for model parameters. Table 11's level "
                "wording is not transcribed here, so the score is the "
                "program's own reading of the factor name and is kept low "
                "deliberately."
            ),
            evidence=(
                "CI runs the SIL gates on every push (README.md)",
                "docs/digital-twin.md determinism contract and calibration "
                "ledger provenance states",
                "docs/adoption-plan.md remediation loop: no ticket closes "
                "without named evidence",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.USE_ASSESSMENT,
            level=1,
            threshold=2,
            justification=(
                "The proposed use of each result set is stated — SIL gates "
                "gate bench time, sweep studies feed the vertical concept "
                "docs — and the twin's own documentation states plainly what "
                "it may not be used for. The appropriateness of the M&S to "
                "those uses has never been assessed by anyone but its "
                "authors, and campaign reports carried no use statement at "
                "all before this block existed. Table 15's level wording is "
                "not transcribed here; program's own reading."
            ),
            evidence=(
                "aiur/sim/gates.py: 'A passed SIL gate is a statement about "
                "the model, not the vehicle'",
                "docs/digital-twin.md: 'A SIL pass is necessary to proceed, "
                "never sufficient'",
                "docs/verticals/ studies cite the sweeps as concept "
                "evidence, not performance predictions",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.INPUT_PEDIGREE,
            level=1,
            threshold=2,
            justification=(
                "Table 16 level 1 describes the twin's inputs exactly: "
                "'Some input data are known and traceable to informal "
                "documentation. Sources of all significant input data are "
                "known. Uncertainties in input data may not even be "
                "estimated.' Scenario start dispersions, air-model sigmas "
                "and sensor sigmas are engineering estimates with named "
                "sources and no estimated uncertainty. Level 2 requires "
                "uncertainties in all data to be at least estimated."
            ),
            evidence=(
                "aiur/sim/scenarios.py jitter radii and station geometry",
                "aiur/sim/sensors.py LIGHTHOUSE_GRADE: 3 mm sigma, 40 ms "
                "latency, 2%/s dropout — engineering estimates",
                "aiur/sim/disturbances.py INDOOR_CALM: 0.03 m/s sigma — "
                "engineering estimate",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.UNCERTAINTY_CHARACTERIZATION,
            level=1,
            threshold=2,
            justification=(
                "Seeded Monte Carlo with the Wilson intervals in this block "
                "quantifies sampling uncertainty in the reported rates, and "
                "the two sweeps are a reduced-dimension look at two input "
                "variables. Input uncertainty is not propagated: no "
                "parameter distribution is defined for any modeled "
                "coefficient and sources are not classified aleatory versus "
                "epistemic, both of which Table 17 level 2 requires. Table "
                "17 level 1 — 'Sources of input uncertainty are identified "
                "with qualitative estimates of the uncertainty. Their impact "
                "on output uncertainties and uncertainty propagation are not "
                "addressed.' — is the honest level."
            ),
            evidence=(
                "aiur/sim/credibility.wilson_interval on every campaign rate "
                "metric and every sweep bin",
                "outdoor-gust-sweep and degraded-sensor-sweep: reduced-"
                "dimension propagation of two input variables",
                "docs/digital-twin.md known-missing-physics list: the "
                "qualitative side of the same question",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.RESULTS_ROBUSTNESS,
            level=2,
            threshold=3,
            justification=(
                "Table 18 level 2: 'Sensitivity of the M&S results for the "
                "RWS is quantitatively known for a few variables and "
                "parameters. Only a few (or none) of the most sensitive "
                "variables and parameters are identified. Sensitivities of "
                "combinations of variables and parameters are not known.' "
                "Sensitivity is quantified for exactly two variables — mean "
                "wind and pose-noise scale — far under the E.4.5 guideline "
                "of 'few' (<20% of potential variables/parameters), and no "
                "combination sweep exists."
            ),
            evidence=(
                "outdoor-gust-sweep: capture rate 100% calm, ~90% at 0.5 "
                "m/s, ~10% at 1.0 m/s, 0% at and above 1.5 m/s (seed 1, 30 "
                "episodes/bin)",
                "degraded-sensor-sweep: 100% at 10x Lighthouse noise, ~63% "
                "at 30x (seed 1, 30 episodes/bin)",
                "no sweep exists for dock motion amplitude, latency, "
                "debounce, servo travel time or their combinations",
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.USE_ANALYSIS_TECHNICAL_REVIEW,
            level=0,
            threshold=1,
            justification=(
                "No campaign analysis has been reviewed by anyone "
                "independent of the analyst, so the level is 0, "
                f"{LEVEL_0_DEFINITION!r} Table 19's level wording is not "
                "transcribed in this repository; this score rests on the "
                "factor name and the verbatim level-0 definition only."
            ),
        ),
        FactorScore(
            factor=CredibilityFactor.USE_PROCESS_PRODUCT_MANAGEMENT,
            level=1,
            threshold=2,
            justification=(
                "Results are reproducible from (config, seed) and CI reruns "
                "the SIL-B campaign on every push, so a result is traceable "
                "to code. There is no record binding a report to a model "
                "release, an analyst or a decision — the campaign report "
                "does not even carry the seed that produced it — which is "
                "what the records of Appendix A ([M&S 38]) would expect. "
                "Table 20's level wording is not transcribed here; program's "
                "own reading."
            ),
            evidence=(
                "aiur/sim/campaign.py emits scenario, gate id, metrics and "
                "verdict as JSON",
                "docs/digital-twin.md determinism contract: any episode in a "
                "report can be replayed exactly from its seed",
                "docs/engineering-loop.md promotion contract defines the "
                "hardware-side record this twin-side one does not yet match",
            ),
        ),
    ),
)
