"""Deterministic simulated flight of the STRATO-P0 package.

This is the twin for the observation article: the ascent physics from
``aiur.strato``, a layered wind field with seeded gusts, a thermal and
battery model, and the real ``FlightSupervisor`` and ``IndependentTimer``
stepped every second.  It writes the same flight-log and manifest shape the
real package will, so ``aiur.s0_evidence`` reduces a simulated flight and a
flown one identically — and so the S0-C gate can be run in CI against the
software before any balloon is filled.

A simulated flight is software evidence, never flight evidence.  Every
manifest it writes carries ``evidence_kind: simulated`` and the reducer
carries that field into the verdict so nobody mistakes one for the other.

Scenarios inject the faults the hazard log cares about: a GNSS dropout, a
telemetry blackout, a balloon that never bursts, and a payload computer that
freezes mid-ascent.  The fault cases are what the supervisor is for, and the
tests assert the outcome the hazard log expects, not merely that the code
ran.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .flight_supervisor import (
    FlightInputs,
    FlightLimits,
    FlightState,
    FlightSupervisor,
    IndependentTimer,
)
from .strato import (
    SoundingBalloon,
    parachute_descent_rate_m_s,
    standard_atmosphere,
)

FLIGHT_LOG_FIELDS: tuple[str, ...] = (
    "t_s",
    "gnss_valid",
    "altitude_m",
    "x_km",
    "y_km",
    "state",
    "cutdown",
    "timer_fired",
    "beacon_only",
    "frame_captured",
    "geotagged",
    "telemetry_sent",
    "telemetry_received",
    "battery_v",
    "internal_temp_c",
    "reason",
)


@dataclass(frozen=True)
class WindLayer:
    top_m: float
    vx_m_s: float
    vy_m_s: float


#: A benign mid-latitude profile: light surface wind, a jet between 10 and
#: 20 km, easterlies above.  A launch-day sounding replaces this.
DEFAULT_WIND: tuple[WindLayer, ...] = (
    WindLayer(3_000.0, 3.0, 1.0),
    WindLayer(10_000.0, 8.0, 2.0),
    WindLayer(20_000.0, 25.0, 5.0),
    WindLayer(47_000.0, -6.0, -1.0),
)


@dataclass(frozen=True)
class FlightScenario:
    name: str = "nominal"
    seed: int = 1
    balloon: SoundingBalloon = field(default_factory=SoundingBalloon)
    limits: FlightLimits = field(default_factory=FlightLimits)
    canopy_area_m2: float = 0.73
    wind: tuple[WindLayer, ...] = DEFAULT_WIND
    gust_sigma_m_s: float = 2.0
    tick_s: float = 1.0
    #: Seconds on the ground between arming and release.
    ground_hold_s: float = 120.0
    battery_initial_v: float = 6.2
    battery_sag_v_per_h: float = 0.25
    #: Fraction of the ambient-to-cabin temperature difference that reaches
    #: the electronics through the insulation; an allocation until S0-A.
    insulation_leak: float = 0.35
    #: Fault injection.  Windows are (start_s, duration_s).
    gnss_dropout: tuple[float, float] | None = None
    telemetry_blackout: tuple[float, float] | None = None
    #: The balloon never bursts and floats off at its burst altitude.
    no_burst: bool = False
    #: The payload computer stops stepping the supervisor from this time.
    computer_freeze_at_s: float | None = None
    ground_terminate_at_s: float | None = None
    #: Seconds the log keeps running after touchdown, so the supervisor's
    #: landed detection (a held near-zero rate) is exercised, not assumed.
    post_landing_s: float = 180.0
    #: Hard stop so a scenario cannot run forever.
    max_sim_s: float = 8.0 * 3600.0


@dataclass(frozen=True)
class FlightResult:
    scenario: FlightScenario
    rows: list[dict[str, object]]
    max_altitude_m: float
    burst_altitude_m: float | None
    landing_x_km: float
    landing_y_km: float
    landed: bool
    termination_reason: str | None
    timer_fired: bool


def _wind_at(wind: tuple[WindLayer, ...], altitude_m: float) -> tuple[float, float]:
    for layer in wind:
        if altitude_m < layer.top_m:
            return layer.vx_m_s, layer.vy_m_s
    return wind[-1].vx_m_s, wind[-1].vy_m_s


def _in_window(window: tuple[float, float] | None, t: float) -> bool:
    return window is not None and window[0] <= t < window[0] + window[1]


def run_flight(scenario: FlightScenario) -> FlightResult:
    """Fly one scenario and return the log.

    Ascent follows the constant-gas-mass balloon until burst (or forever, for
    a float-off), descent follows the parachute at local density, and the
    package is stepped through the real supervisor every tick.
    """

    if scenario.tick_s <= 0:
        raise ValueError("tick must be positive")
    rng = random.Random(scenario.seed)
    balloon = scenario.balloon
    limits = scenario.limits
    burst_altitude = balloon.burst_altitude_m()
    package_mass = balloon.payload_mass_kg

    supervisor = FlightSupervisor(limits)
    timer = IndependentTimer(limits.max_mission_s)

    t = 0.0
    altitude = 0.0
    x_km = 0.0
    y_km = 0.0
    under_balloon = True
    burst_at: float | None = None
    max_altitude = 0.0
    rows: list[dict[str, object]] = []
    last_capture_s: float | None = None
    last_telemetry_s: float | None = None
    supervisor_frozen = False
    last_output = None
    landed = False
    landed_at_s: float | None = None

    while t <= scenario.max_sim_s:
        armed = t >= 0.0  # pin pulled at t = 0, on the ground
        released = t >= scenario.ground_hold_s
        gnss_valid = not _in_window(scenario.gnss_dropout, t)
        ambient = standard_atmosphere(min(altitude, 47_000.0)).temperature_c
        internal_temp = 20.0 + (ambient - 20.0) * scenario.insulation_leak
        battery_v = scenario.battery_initial_v - scenario.battery_sag_v_per_h * t / 3600.0
        range_km = math.hypot(x_km, y_km)

        timer_fired = timer.step(t, armed)

        if scenario.computer_freeze_at_s is not None and t >= scenario.computer_freeze_at_s:
            supervisor_frozen = True
        inputs = FlightInputs(
            arm_pin_pulled=armed,
            gnss_valid=gnss_valid,
            altitude_m=altitude if gnss_valid else None,
            range_from_launch_km=range_km if gnss_valid else None,
            battery_v=battery_v,
            internal_temp_c=internal_temp,
            ground_terminate=(
                scenario.ground_terminate_at_s is not None and t >= scenario.ground_terminate_at_s
            ),
        )
        if not supervisor_frozen:
            last_output = supervisor.step(t, inputs)
        output = last_output
        assert output is not None

        cutdown = output.cutdown or timer_fired
        if under_balloon and released and cutdown:
            under_balloon = False
        if under_balloon and released and not scenario.no_burst and altitude >= burst_altitude:
            under_balloon = False
            burst_at = altitude

        # Imaging and telemetry, as the supervisor commands them.  A frozen
        # computer captures nothing and sends nothing; the beacon is a
        # separate device and is modelled as the timer's sibling here.
        frame = False
        geotagged = False
        if not supervisor_frozen and output.capture_period_s is not None and released:
            if last_capture_s is None or t - last_capture_s >= output.capture_period_s:
                frame = True
                geotagged = output.geotag
                last_capture_s = t
        telemetry_sent = False
        if last_telemetry_s is None or t - last_telemetry_s >= output.telemetry_period_s:
            telemetry_sent = True
            last_telemetry_s = t
        telemetry_received = telemetry_sent and not _in_window(scenario.telemetry_blackout, t)

        rows.append(
            {
                "t_s": round(t, 1),
                "gnss_valid": int(gnss_valid),
                "altitude_m": round(altitude, 1) if gnss_valid else "",
                "x_km": round(x_km, 3) if gnss_valid else "",
                "y_km": round(y_km, 3) if gnss_valid else "",
                "state": output.state.value if not supervisor_frozen else "frozen",
                "cutdown": int(cutdown),
                "timer_fired": int(timer_fired),
                "beacon_only": int(output.beacon_only),
                "frame_captured": int(frame),
                "geotagged": int(geotagged),
                "telemetry_sent": int(telemetry_sent),
                "telemetry_received": int(telemetry_received),
                "battery_v": round(battery_v, 3),
                "internal_temp_c": round(internal_temp, 2),
                "reason": output.reason or "",
            }
        )

        if landed and landed_at_s is not None and t - landed_at_s >= scenario.post_landing_s:
            break

        # Advance the physics.
        dt = scenario.tick_s
        if released and not landed:
            if under_balloon:
                if scenario.no_burst and altitude >= burst_altitude:
                    vz = 0.0  # float-off: the balloon holds its burst altitude
                else:
                    vz = balloon.ascent_rate_at_m_s(min(altitude, 46_900.0))
            else:
                vz = -parachute_descent_rate_m_s(
                    package_mass, scenario.canopy_area_m2, altitude_m=min(altitude, 47_000.0)
                )
            vx, vy = _wind_at(scenario.wind, altitude)
            vx += rng.gauss(0.0, scenario.gust_sigma_m_s)
            vy += rng.gauss(0.0, scenario.gust_sigma_m_s)
            altitude = max(0.0, altitude + vz * dt)
            x_km += vx * dt / 1000.0
            y_km += vy * dt / 1000.0
            max_altitude = max(max_altitude, altitude)
            if not under_balloon and altitude <= 0.0:
                landed = True
                landed_at_s = t + dt
        t += dt

    return FlightResult(
        scenario=scenario,
        rows=rows,
        max_altitude_m=max_altitude,
        burst_altitude_m=burst_at,
        landing_x_km=x_km,
        landing_y_km=y_km,
        landed=landed,
        termination_reason=supervisor.termination_reason,
        timer_fired=timer.fired,
    )


def predict_landing(scenario: FlightScenario) -> tuple[float, float]:
    """Pre-launch landing prediction: the same flight with no gusts.

    This is what gets committed before release; the flown landing is judged
    against it (S0-FLT-003).
    """

    calm = replace(scenario, gust_sigma_m_s=0.0, gnss_dropout=None, telemetry_blackout=None)
    result = run_flight(calm)
    return result.landing_x_km, result.landing_y_km


SCENARIOS: dict[str, FlightScenario] = {
    "nominal": FlightScenario(),
    "gnss-dropout": FlightScenario(name="gnss-dropout", gnss_dropout=(1800.0, 240.0)),
    "gnss-lost": FlightScenario(name="gnss-lost", gnss_dropout=(1800.0, 3600.0)),
    "blackout": FlightScenario(name="blackout", telemetry_blackout=(2400.0, 200.0)),
    "float-off": FlightScenario(name="float-off", no_burst=True),
    "computer-freeze": FlightScenario(
        name="computer-freeze", no_burst=True, computer_freeze_at_s=2400.0
    ),
    "ground-terminate": FlightScenario(name="ground-terminate", ground_terminate_at_s=3000.0),
}


def write_flight(result: FlightResult, out_dir: Path, *, run_id: str, git_commit: str) -> None:
    """Write the flight log and manifest in the shape the reducer expects."""

    out_dir.mkdir(parents=True, exist_ok=True)
    predicted_x, predicted_y = predict_landing(result.scenario)
    log_path = out_dir / f"{run_id}-flight-log.csv"
    with log_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FLIGHT_LOG_FIELDS)
        writer.writeheader()
        writer.writerows(result.rows)
    manifest = {
        "run_id": run_id,
        "article_rev": "Rev-A/sim",
        "git_commit": git_commit,
        "evidence_kind": "simulated",
        "scenario": result.scenario.name,
        "seed": result.scenario.seed,
        "predicted_landing_x_km": round(predicted_x, 3),
        "predicted_landing_y_km": round(predicted_y, 3),
        "airspace_coordination_ref": "SIM-NO-AIRSPACE (simulated flight; nothing was launched)",
        "recovered": result.landed,
        "recovery_x_km": round(result.landing_x_km, 3),
        "recovery_y_km": round(result.landing_y_km, 3),
        "storage_checksum_verified": result.landed,
        "third_party_contacts": 0,
        "max_altitude_m": round(result.max_altitude_m, 1),
        "burst_altitude_m": (
            round(result.burst_altitude_m, 1) if result.burst_altitude_m is not None else None
        ),
        "termination_reason": result.termination_reason,
        "timer_fired": result.timer_fired,
    }
    (out_dir / f"{run_id}-flight-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def write_simulated_termination_trials(out_dir: Path, *, trials: int = 10) -> Path:
    """Termination-trial rows for the simulated article.

    Real S0 evidence comes from a bench; these rows exist so the simulated
    S0-C chain is complete end to end.  Every row says so.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sim-termination-trials.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["trial_id", "kind", "computer_powered", "fired", "notes"])
        for index in range(1, trials + 1):
            supervisor = FlightSupervisor()
            supervisor.step(0.0, FlightInputs(True, True, 100.0, 0.0))
            output = supervisor.step(1.0, FlightInputs(True, True, 100.0, 0.0, ground_terminate=True))
            writer.writerow([f"T{index:02d}", "termination", 1, int(output.cutdown), "simulated"])
        timer = IndependentTimer(10.0)
        timer.step(0.0, True)
        fired = timer.step(10.0, True)
        writer.writerow(["T-OFF", "termination", 0, int(fired), "simulated: computer off, timer path"])
        for index in range(1, 11):
            writer.writerow([f"L{index:02d}", "link", 1, 1, "simulated"])
    return path


def _summary(result: FlightResult) -> dict[str, object]:
    return {
        "scenario": result.scenario.name,
        "ticks": len(result.rows),
        "max_altitude_m": round(result.max_altitude_m, 1),
        "burst_altitude_m": result.burst_altitude_m,
        "landed": result.landed,
        "landing_km": [round(result.landing_x_km, 2), round(result.landing_y_km, 2)],
        "termination_reason": result.termination_reason,
        "timer_fired": result.timer_fired,
        "geotagged_frames_above_threshold": sum(
            1
            for row in result.rows
            if row["frame_captured"] and row["geotagged"] and row["altitude_m"] != ""
            and float(row["altitude_m"]) >= result.scenario.limits.stratosphere_threshold_m
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate a STRATO-P0 flight.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="nominal")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--flights", type=int, default=1, help="flights to write, seeds seed..seed+n-1")
    parser.add_argument("--out", type=Path, default=None, help="directory for logs and manifests")
    parser.add_argument("--git-commit", default="unknown")
    args = parser.parse_args(argv)

    base = SCENARIOS[args.scenario]
    seed = base.seed if args.seed is None else args.seed
    summaries = []
    for index in range(args.flights):
        scenario = replace(base, seed=seed + index)
        result = run_flight(scenario)
        summaries.append(_summary(result))
        if args.out is not None:
            run_id = f"{scenario.name}-{scenario.seed}"
            write_flight(result, args.out, run_id=run_id, git_commit=args.git_commit)
    if args.out is not None:
        write_simulated_termination_trials(args.out)
    print(json.dumps(summaries if len(summaries) > 1 else summaries[0], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
