"""Architecture trade study for the CARRIER-P0 capture interface.

The programme has one capture architecture and was about to print it.  This
module asks the question that should be asked before metal or plastic is
committed: of the mechanisms we could build, which one buys the most, and
what does each one cost?

The ranking metric is deliberately not nominal capture rate.  Every
mechanism captures when the probe arrives centred with honest sensors —
that measures the scenario, not the design.  What separates them is how
much *terminal positioning error* each can absorb, because that error
budget is what sets the sensor the programme must buy:

  * docs/verticals derives SHARED-001, GNSS-independent terminal relative
    navigation, as the hardest requirement every non-laboratory vertical
    inherits;
  * docs/digital-twin.md's degraded-sensor sweep shows the baseline funnel
    is sized for millimetre-grade positioning.

So an architecture that still captures at ten times the positioning noise
is not a marginal improvement.  It changes which sensor exists, which
changes which verticals are reachable.  That is worth more than a few
percent of capture rate, and it is invisible if you only test at nominal.

Three axes, deliberately few, each tied to something the programme does not
know:

  ``noise``   positioning noise, scaled from the Lighthouse-grade estimate.
              Answers "how good must the sensor be".
  ``wind``    mean air speed.  Answers "can this ever leave the laboratory".
  ``fault``   the injected-fault menu.  Answers "does it stay safe when
              something breaks", which is pass/fail, not a rate.

Simulation cannot rank a design on its own.  A mechanism that captures
perfectly with four actuators and eleven parts is not obviously better than
one that captures well with none, so :class:`MechanismSpec` carries the
terms the twin cannot compute — parts, actuators, sensed channels, mass —
and the report puts them next to the simulated results rather than hiding
them behind a single score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from typing import Callable, Iterable, Sequence

from .campaign import run_episode
from .credibility import wilson_interval
from .disturbances import outdoor_breeze
from .engine import EpisodeConfig, EpisodeOutcome
from .faults import sample_fault_plan
from .scenarios import _scenario_rng, degraded_sensor_case, sil_p0b

#: Positioning-noise multiples of the Lighthouse-grade estimate.  1.0 is the
#: laboratory instrument; 10 is roughly consumer/vision grade; 30 approaches
#: the funnel's own radius, where geometry runs out.
NOISE_SCALES: tuple[float, ...] = (1.0, 3.0, 10.0, 30.0)

#: Mean wind, m/s.  Indoor still air through the level where the baseline
#: carrier is already known to be unflyable.
WIND_LEVELS_M_S: tuple[float, ...] = (0.0, 0.5, 1.0)

#: Capture rate below which an architecture is treated as having collapsed
#: at that condition.  Chosen to sit under the SIL gates' 95% requirement
#: with room to spare, so "collapsed" means unusable rather than marginal.
COLLAPSE_RATE_PCT = 50.0


@dataclass(frozen=True)
class ConditionResult:
    axis: str
    level: float
    episodes: int
    capture_rate_pct: float
    ci_low_pct: float
    ci_high_pct: float
    unsafe_episodes: int


@dataclass(frozen=True)
class ArchitectureResult:
    key: str
    name: str
    summary: str
    #: Highest noise scale still capturing above the collapse threshold.
    #: The headline number: it is the positioning budget the design buys.
    noise_tolerance: float
    #: Highest mean wind still capturing above the threshold.
    wind_tolerance_m_s: float
    nominal_capture_rate_pct: float
    fault_episodes: int
    unsafe_fault_outcomes: int
    conditions: tuple[ConditionResult, ...]
    # Costs the twin cannot simulate.
    part_count: int
    actuator_count: int
    sensed_channels: int
    est_dock_mass_g: float
    est_probe_mass_g: float
    known_weaknesses: tuple[str, ...]

    @property
    def safe(self) -> bool:
        """No injected fault produced an unsafe outcome, at any level."""

        return self.unsafe_fault_outcomes == 0 and all(
            condition.unsafe_episodes == 0 for condition in self.conditions
        )


def _episodes(
    build: Callable[[EpisodeConfig, float], object] | None,
    *,
    seeds: Iterable[int],
    noise_scale: float = 1.0,
    wind_m_s: float = 0.0,
    with_fault: bool = False,
) -> tuple[int, int, int]:
    """Run one condition; return (episodes, captures, unsafe)."""

    captures = unsafe = total = 0
    for seed in seeds:
        # Retune FDIR to the sensor, exactly as degraded-sensor-sweep does.
        # Without it the study ranks architectures by how well each happens
        # to suit the default guidance tuning, which is a fact about the
        # defaults and not about the mechanism: the baseline reads as
        # collapsing at 3x noise untuned and surviving 10x tuned, and the
        # tuned number is the one a real integration would see.
        config = degraded_sensor_case(seed, noise_scale)
        if wind_m_s > 0.0:
            config = replace(config, air=outdoor_breeze(wind_m_s))
        if with_fault:
            config = replace(
                config, fault_plan=sample_fault_plan(_scenario_rng(seed))
            )
        if build is not None:
            config = replace(config, mechanism_factory=build)
        result = run_episode(config, seed)
        total += 1
        if result.outcome is EpisodeOutcome.SUCCESS:
            captures += 1
        if result.unsafe_events:
            unsafe += 1
    return total, captures, unsafe


def evaluate_architecture(
    spec,
    *,
    episodes_per_condition: int = 24,
    seed: int = 1,
) -> ArchitectureResult:
    """Run one architecture across every axis and reduce it to a row."""

    build = None if spec.key == "baseline" else (lambda cfg, dt, s=spec: s.build(dt))
    seeds = range(seed, seed + episodes_per_condition)
    conditions: list[ConditionResult] = []

    def record(axis: str, level: float, **kwargs) -> ConditionResult:
        total, captures, unsafe = _episodes(build, seeds=seeds, **kwargs)
        low, high = wilson_interval(captures, total)
        condition = ConditionResult(
            axis=axis,
            level=level,
            episodes=total,
            capture_rate_pct=round(100.0 * captures / total, 2),
            ci_low_pct=round(100.0 * low, 2),
            ci_high_pct=round(100.0 * high, 2),
            unsafe_episodes=unsafe,
        )
        conditions.append(condition)
        return condition

    for scale in NOISE_SCALES:
        record("noise", scale, noise_scale=scale)
    for wind in WIND_LEVELS_M_S:
        if wind == 0.0:
            continue
        record("wind", wind, wind_m_s=wind)
    fault = record("fault", 1.0, with_fault=True)

    noise_rows = [c for c in conditions if c.axis == "noise"]
    wind_rows = [c for c in conditions if c.axis == "wind"]
    tolerated_noise = [c.level for c in noise_rows if c.capture_rate_pct >= COLLAPSE_RATE_PCT]
    tolerated_wind = [c.level for c in wind_rows if c.capture_rate_pct >= COLLAPSE_RATE_PCT]
    nominal = next(c for c in noise_rows if c.level == 1.0)

    return ArchitectureResult(
        key=spec.key,
        name=spec.name,
        summary=spec.summary,
        noise_tolerance=max(tolerated_noise) if tolerated_noise else 0.0,
        wind_tolerance_m_s=max(tolerated_wind) if tolerated_wind else 0.0,
        nominal_capture_rate_pct=nominal.capture_rate_pct,
        fault_episodes=fault.episodes,
        unsafe_fault_outcomes=fault.unsafe_episodes,
        conditions=tuple(conditions),
        part_count=spec.part_count,
        actuator_count=spec.actuator_count,
        sensed_channels=spec.sensed_channels,
        est_dock_mass_g=spec.est_dock_mass_g,
        est_probe_mass_g=spec.est_probe_mass_g,
        known_weaknesses=tuple(spec.known_weaknesses),
    )


def run_study(
    specs: Sequence,
    *,
    episodes_per_condition: int = 24,
    seed: int = 1,
) -> dict[str, object]:
    """Evaluate every candidate and return a comparable report.

    No single score is emitted, on purpose.  Collapsing "captures at ten
    times the noise" and "has no actuators" and "weighs 40 g more" into one
    number would bury exactly the trade the reader has to make, and would
    let a weighting chosen here decide a hardware programme.  The report
    ranks by positioning tolerance because that is the requirement the
    verticals hinge on, and prints the rest alongside.
    """

    results = [
        evaluate_architecture(
            spec, episodes_per_condition=episodes_per_condition, seed=seed
        )
        for spec in specs
    ]
    ranked = sorted(
        results,
        key=lambda r: (r.safe, r.noise_tolerance, r.nominal_capture_rate_pct),
        reverse=True,
    )
    return {
        "study": "capture-architecture trade",
        "episodes_per_condition": episodes_per_condition,
        "seed": seed,
        "collapse_threshold_pct": COLLAPSE_RATE_PCT,
        "ranked_by": (
            "safety first, then positioning-noise tolerance, then nominal "
            "capture rate. Cost terms are reported, never folded into a score."
        ),
        # ``safe`` is a property, so asdict() would drop it — and it is the
        # first key the ranking sorts on.  A report that ranks safety first
        # and then does not say which candidates are safe is worse than
        # useless: it looks authoritative while withholding the finding.
        "architectures": [
            {**asdict(result), "safe": result.safe} for result in ranked
        ],
        "caveats": [
            "Simulation only. No candidate has been built or measured, and "
            "the twin's NASA-STD-7009B validation factor is level 1 for all "
            "of them equally.",
            "Alternative mechanisms carry surrogate physics of the same "
            "fidelity as the baseline's, so a comparison between them is "
            "fairer than any single absolute number.",
            "Cost terms (parts, actuators, mass) are engineering estimates "
            "supplied by each candidate, not measurements.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Capture-architecture trade study")
    parser.add_argument("--episodes", type=int, default=24)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    from .architectures import CANDIDATES

    print(
        json.dumps(
            run_study(CANDIDATES, episodes_per_condition=args.episodes, seed=args.seed),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
