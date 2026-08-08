"""Monte Carlo campaign runner for the CARRIER-P0 digital twin.

A campaign runs many seeded episodes of one scenario and reduces them to the
exact metric names the SIL gates consume — the same reduction discipline the
P0-A bench evidence pipeline uses, applied to simulation instead of CSVs.

Fault policy: a deterministic slice of every gate campaign runs with an
injected fault plan.  Fault episodes are excluded from the capture-rate
statistic (a correctly refused recovery is good behavior) but are held to
the absolute safety zeros: any unsafe outcome under fault fails the gate.

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

from .engine import EpisodeConfig, EpisodeOutcome, EpisodeResult, run_episode
from .events import EventKind
from .gates import evaluate_sil_gate
from .scenarios import (
    degraded_sensor_case,
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


def _count_events(results: Iterable[EpisodeResult], kind: EventKind) -> int:
    return sum(1 for result in results for event in result.events if event.kind is kind)


def run_campaign(
    scenario: str,
    *,
    episodes: int = 200,
    seed: int = 1,
    fault_fraction: float = 0.25,
) -> CampaignResult:
    """Run one gate campaign and reduce it to a SIL gate verdict."""

    if scenario not in GATE_SCENARIOS:
        raise KeyError(f"unknown gate scenario: {scenario}")
    if episodes <= 0:
        raise ValueError("episodes must be positive")
    if not 0.0 <= fault_fraction < 1.0:
        raise ValueError("fault fraction must be in [0, 1)")

    builder, gate_id = GATE_SCENARIOS[scenario]
    # int(x + 0.5) instead of round(): banker's rounding at bin edges can
    # silently produce zero fault episodes in small campaigns.
    fault_count = int(episodes * fault_fraction + 0.5)
    nominal_count = episodes - fault_count

    nominal_results: list[EpisodeResult] = []
    fault_results: list[EpisodeResult] = []
    for index in range(episodes):
        episode_seed = seed + index
        with_fault = index >= nominal_count
        config = builder(episode_seed, with_fault=with_fault)
        result = run_episode(config, episode_seed)
        (fault_results if with_fault else nominal_results).append(result)

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

    return CampaignResult(
        scenario=scenario,
        gate_id=gate_id,
        episodes=episodes,
        metrics=metrics,
        outcome_counts=outcome_counts,
        unsafe_details=unsafe_details,
        verdict_passed=verdict.passed,
        verdict=asdict(verdict),
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
    elif study == "degraded-sensor-sweep":
        bins = SENSOR_NOISE_SCALES
        case = degraded_sensor_case
        bin_label = "noise_scale"
    else:
        raise KeyError(f"unknown sweep study: {study}")

    rows: list[dict[str, float | int]] = []
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
        rows.append(
            {
                bin_label: bin_value,
                "episodes": episodes_per_bin,
                "capture_rate_pct": round(100.0 * successes / episodes_per_bin, 2),
                "unsafe_episodes": unsafe,
                "mean_aborts": round(
                    sum(r.aborts for r in results) / episodes_per_bin, 2
                ),
            }
        )
    return {"study": study, "bins": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a digital-twin campaign")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=sorted(GATE_SCENARIOS) + ["outdoor-gust-sweep", "degraded-sensor-sweep"],
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
