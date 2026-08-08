"""Monte Carlo campaign runner for the CARRIER-P0 digital twin.

A campaign runs many seeded episodes of one scenario and reduces them to the
exact metric names the SIL gates consume — the same reduction discipline the
P0-A bench evidence pipeline uses, applied to simulation instead of CSVs.

Fault policy: a deterministic slice of every gate campaign runs with an
injected fault plan.  Fault episodes are excluded from the capture-rate
statistic (a correctly refused recovery is good behavior) but are held to
the absolute safety zeros: any unsafe outcome under fault fails the gate.

Reporting policy: every report carries a ``credibility`` block built by
:mod:`aiur.sim.credibility` — NASA-STD-7009B factor levels against declared
thresholds, the [M&S 32] warning list, and Wilson intervals on the rate
metrics.  A point estimate travels further than its caveats, so the caveats
travel inside the same JSON.

Run from the command line::

    python -m aiur.sim.campaign --scenario sil-p0b --episodes 200 --seed 1
    python -m aiur.sim.campaign --scenario outdoor-gust-sweep --episodes-per-bin 30

Gate scenarios exit 0 only when the SIL gate passes; sweep studies always
exit 0 — they are engineering studies, not gates.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from typing import Callable, Iterable

from .credibility import (
    TWIN_CREDIBILITY,
    RateInterval,
    credibility_block,
)
from .engine import EpisodeConfig, EpisodeOutcome, EpisodeResult, run_episode
from .events import EventKind
from .gates import evaluate_sil_gate
from .scenarios import (
    degraded_sensor_case,
    nav_bias_ramp_case,
    outdoor_gust_case,
    sil_p0b,
    sil_p0c,
    sil_p0d,
)

GATE_SCENARIOS: dict[str, tuple[Callable[..., EpisodeConfig], str]] = {
    "sil-p0b": (sil_p0b, "SIL-B"),
    "sil-p0c": (sil_p0c, "SIL-C"),
    "sil-p0d": (sil_p0d, "SIL-D"),
}

#: Sweep studies referenced by the vertical concept docs (docs/verticals/).
OUTDOOR_GUST_BINS_M_S: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
SENSOR_NOISE_SCALES: tuple[float, ...] = (1.0, 3.0, 10.0, 30.0)

#: Ramp rates for the nav-bias-ramp study.  Chosen to straddle the jump
#: detector's per-step threshold: the slow end is invisible to it, the fast
#: end trips it, and the interesting answer is in between.
NAV_BIAS_RAMP_RATES_M_S: tuple[float, ...] = (0.0, 0.005, 0.01, 0.02, 0.05, 0.10)


@dataclass(frozen=True)
class CampaignResult:
    scenario: str
    gate_id: str
    episodes: int
    metrics: dict[str, float | int]
    outcome_counts: dict[str, int]
    unsafe_details: tuple[str, ...]
    verdict_passed: bool
    verdict: dict[str, object]
    #: NASA-STD-7009B disclosure block: assessed credibility levels and
    #: their gaps to the declared thresholds, the [M&S 32] warnings, and the
    #: [M&S 33]/[M&S 34] uncertainty estimate for the rate metrics above.
    credibility: dict[str, object]


def _count_events(results: Iterable[EpisodeResult], kind: EventKind) -> int:
    return sum(1 for result in results for event in result.events if event.kind is kind)


def run_campaign(
    scenario: str,
    *,
    episodes: int = 200,
    seed: int = 1,
    fault_fraction: float = 0.25,
    correlated_fraction: float = 0.4,
) -> CampaignResult:
    """Run one gate campaign and reduce it to a SIL gate verdict."""

    if scenario not in GATE_SCENARIOS:
        raise KeyError(f"unknown gate scenario: {scenario}")
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    if not 0.0 <= fault_fraction < 1.0:
        raise ValueError("fault fraction must be in [0, 1)")
    if not 0.0 <= correlated_fraction <= 1.0:
        raise ValueError("correlated fraction must be in [0, 1]")

    builder, gate_id = GATE_SCENARIOS[scenario]
    # int(x + 0.5) instead of round(): banker's rounding at bin edges can
    # silently produce zero fault episodes in small campaigns.
    fault_count = int(episodes * fault_fraction + 0.5)
    nominal_count = episodes - fault_count
    # A slice of the fault budget goes to coupled pairs from the common-mode
    # analysis.  Single-fault sampling structurally cannot reach a defect that
    # needs two things wrong at once, and the twin's own worst finding is
    # exactly that shape.
    correlated_count = int(fault_count * correlated_fraction + 0.5)
    single_fault_end = episodes - correlated_count

    nominal_results: list[EpisodeResult] = []
    fault_results: list[EpisodeResult] = []
    correlated_results: list[EpisodeResult] = []
    for index in range(episodes):
        episode_seed = seed + index
        correlated = index >= single_fault_end
        with_fault = index >= nominal_count and not correlated
        config = builder(
            episode_seed, with_fault=with_fault, correlated_fault=correlated
        )
        result = run_episode(config, episode_seed)
        if correlated:
            correlated_results.append(result)
        elif with_fault:
            fault_results.append(result)
        else:
            nominal_results.append(result)
    # Coupled pairs are fault episodes for every purpose except the sampler
    # that produced them.
    fault_results = fault_results + correlated_results

    every = nominal_results + fault_results
    nominal_successes = sum(
        1 for result in nominal_results if result.outcome is EpisodeOutcome.SUCCESS
    )
    success_rate_pct = (
        100.0 * nominal_successes / len(nominal_results) if nominal_results else 0.0
    )
    contact_speeds = [
        result.max_contact_closing_m_s
        for result in every
        if result.max_contact_closing_m_s is not None
    ]

    # A fault episode only counts toward the gate quota if its fault
    # actually activated before the episode ended — a window that never
    # opened tested nothing.
    activated_faults = sum(
        1
        for result in fault_results
        if any(event.kind is EventKind.FAULT_INJECTED for event in result.events)
    )
    metrics: dict[str, float | int] = {
        "episodes": episodes,
        "fault_episodes": activated_faults,
        "max_contact_closing_m_s": max(contact_speeds) if contact_speeds else 0.0,
        "prop_funnel_contacts": _count_events(every, EventKind.PROP_FUNNEL_CONTACT),
        "overspeed_contacts": _count_events(every, EventKind.OVERSPEED_CONTACT),
        "envelope_strikes": _count_events(every, EventKind.ENVELOPE_STRIKE),
        "unsafe_fault_outcomes": sum(
            1 for result in fault_results if result.outcome is EpisodeOutcome.UNSAFE
        ),
        # Reported for dock-integrity visibility, not gated: the controller
        # announcing a capture with no aircraft in the mechanism.
        "false_capture_confirmations": _count_events(
            every, EventKind.FALSE_CAPTURE_CONFIRMED
        ),
    }
    if gate_id == "SIL-D":
        metrics["sequence_success_rate_pct"] = round(success_rate_pct, 2)
        metrics["separation_violations"] = _count_events(
            every, EventKind.SEPARATION_VIOLATION
        )
        metrics["simultaneous_dock_approaches"] = _count_events(
            every, EventKind.SIMULTANEOUS_DOCK_APPROACH
        )
    else:
        metrics["nominal_capture_rate_pct"] = round(success_rate_pct, 2)

    # Nominal episodes must also be unsafe-free; surface them the loud way.
    unsafe_details = tuple(
        f"seed={seed + i} outcome={result.outcome.value} "
        f"events={[e.kind.value for e in result.unsafe_events]}"
        for i, result in enumerate(every)
        if result.outcome is EpisodeOutcome.UNSAFE
    )
    nominal_unsafe = sum(
        1 for result in nominal_results if result.outcome is EpisodeOutcome.UNSAFE
    )
    metrics["unsafe_nominal_episodes"] = nominal_unsafe
    if nominal_unsafe:
        # An unsafe nominal episode must never hide inside the capture-rate
        # statistic: fold it into the gated zero-criterion so the gate fails
        # even if the event taxonomy grows faster than this reducer.
        metrics["unsafe_fault_outcomes"] = (
            int(metrics["unsafe_fault_outcomes"]) + nominal_unsafe
        )

    verdict = evaluate_sil_gate(gate_id, metrics)
    outcome_counts: dict[str, int] = {}
    for result in every:
        outcome_counts[result.outcome.value] = (
            outcome_counts.get(result.outcome.value, 0) + 1
        )

    # The rate metric is a binomial proportion over the fault-free episodes,
    # so its sampling uncertainty is computable exactly where the gate reads
    # it — a 6-episode campaign and a 200-episode campaign both report a
    # percentage, and only the interval tells them apart.
    rate_metric = (
        "sequence_success_rate_pct"
        if gate_id == "SIL-D"
        else "nominal_capture_rate_pct"
    )
    rate_intervals = (
        (RateInterval(rate_metric, nominal_successes, len(nominal_results)),)
        if nominal_results
        else ()
    )
    credibility = credibility_block(
        TWIN_CREDIBILITY,
        rate_intervals=rate_intervals,
        no_estimate_reason=(
            "the campaign ran no fault-free episodes, so the reported rate "
            "is a placeholder zero rather than an estimate"
        ),
        # A failed or unevaluable gate criterion is an unachieved acceptance
        # criterion in [M&S 32]a terms; report it as one.
        unachieved_acceptance_criteria=tuple(verdict.failed_criteria)
        + tuple(f"metric {name} was not reported" for name in verdict.missing_metrics),
    )

    return CampaignResult(
        scenario=scenario,
        gate_id=gate_id,
        episodes=episodes,
        metrics=metrics,
        outcome_counts=outcome_counts,
        unsafe_details=unsafe_details,
        verdict_passed=verdict.passed,
        verdict=asdict(verdict),
        credibility=credibility,
    )


def run_sweep(
    study: str,
    *,
    episodes_per_bin: int = 30,
    seed: int = 1,
) -> dict[str, object]:
    """Run one sweep study and return capture statistics per bin."""

    if episodes_per_bin <= 0:
        raise ValueError("episodes per bin must be positive")

    if study == "outdoor-gust-sweep":
        bins: tuple[float, ...] = OUTDOOR_GUST_BINS_M_S
        case = outdoor_gust_case
        bin_label = "mean_wind_m_s"
        domain_limit = 0.0
        domain_limit_text = (
            "the twin is declared for indoor still air with zero mean flow"
        )
    elif study == "nav-bias-ramp-sweep":
        bins = NAV_BIAS_RAMP_RATES_M_S
        case = nav_bias_ramp_case
        bin_label = "ramp_rate_m_s"
        domain_limit = 0.0
        domain_limit_text = (
            "the twin is declared for an unbiased relative-navigation "
            "solution; every non-zero ramp is outside it by construction, "
            "which is the point of the study"
        )
    elif study == "degraded-sensor-sweep":
        bins = SENSOR_NOISE_SCALES
        case = degraded_sensor_case
        bin_label = "noise_scale"
        domain_limit = 1.0
        domain_limit_text = (
            "the twin is declared for external optical positioning at the "
            "Lighthouse-grade sigma of 3 mm (noise_scale 1.0)"
        )
    else:
        raise KeyError(f"unknown sweep study: {study}")

    rows: list[dict[str, float | int]] = []
    intervals: list[RateInterval] = []
    for bin_index, bin_value in enumerate(bins):
        results = [
            run_episode(
                case(seed + bin_index * episodes_per_bin + i, bin_value),
                seed + bin_index * episodes_per_bin + i,
            )
            for i in range(episodes_per_bin)
        ]
        successes = sum(1 for r in results if r.outcome is EpisodeOutcome.SUCCESS)
        unsafe = sum(1 for r in results if r.outcome is EpisodeOutcome.UNSAFE)
        # A sweep bin is small by design, so its point estimate is the most
        # over-read number the twin produces: 30/30 and 300/300 both print
        # 100.0.  Carry the interval next to the point in the same row.
        interval = RateInterval(
            f"capture_rate_pct[{bin_label}={bin_value}]",
            successes,
            episodes_per_bin,
        )
        intervals.append(interval)
        ci_low, ci_high = interval.bounds
        rows.append(
            {
                bin_label: bin_value,
                "episodes": episodes_per_bin,
                "capture_rate_pct": round(100.0 * successes / episodes_per_bin, 2),
                "ci_low_pct": round(100.0 * ci_low, 2),
                "ci_high_pct": round(100.0 * ci_high, 2),
                "unsafe_episodes": unsafe,
                "mean_aborts": round(
                    sum(r.aborts for r in results) / episodes_per_bin, 2
                ),
            }
        )

    return {
        "study": study,
        "bins": rows,
        "credibility": credibility_block(
            TWIN_CREDIBILITY,
            rate_intervals=intervals,
            # Sweeps exist to push the model past where it is declared to
            # apply; that is the study's purpose and also an [M&S 32]c
            # occurrence, so it is reported rather than assumed understood.
            outside_declared_domain=tuple(
                f"{bin_label}={value} — {domain_limit_text}"
                for value in bins
                if value > domain_limit
            ),
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a digital-twin campaign")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=sorted(GATE_SCENARIOS)
        + ["outdoor-gust-sweep", "degraded-sensor-sweep", "nav-bias-ramp-sweep"],
    )
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--episodes-per-bin", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--fault-fraction", type=float, default=0.25)
    args = parser.parse_args(argv)

    # Bad arguments must exit 2 via argparse, never share exit code 1 with
    # a legitimately failed gate.
    try:
        if args.scenario in GATE_SCENARIOS:
            campaign = run_campaign(
                args.scenario,
                episodes=args.episodes,
                seed=args.seed,
                fault_fraction=args.fault_fraction,
            )
            print(json.dumps(asdict(campaign), indent=2, sort_keys=True))
            return 0 if campaign.verdict_passed else 1

        print(
            json.dumps(
                run_sweep(
                    args.scenario,
                    episodes_per_bin=args.episodes_per_bin,
                    seed=args.seed,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (KeyError, ValueError) as exc:
        parser.error(str(exc))
        raise AssertionError("unreachable")  # parser.error raises SystemExit


if __name__ == "__main__":
    raise SystemExit(main())
