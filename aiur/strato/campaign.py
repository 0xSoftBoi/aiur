"""Monte Carlo over the things a launch crew does not control.

A single ascent run is an anecdote.  This draws the wind (season, strength,
direction), the fill error, the mass tolerance, the radiative environment and
a small rate of hardware faults, flies each draw through ``ascent.simulate``
and reports distributions: does it reach float, how high, how far away does
it come down.  The same seed gives the same campaign, byte for byte.

    python -m aiur.strato.campaign --design S1-touch/hull --flights 200 --seed 1
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys

from .ascent import config_from_design, simulate

SEASONS = {
    "summer": (("midlat-summer-p50", 0.7), ("midlat-summer-p90", 0.3)),
    "turnaround": (("midlat-turnaround-p50", 0.8), ("midlat-summer-p90", 0.2)),
    "winter": (("midlat-winter-p50", 0.7), ("midlat-winter-p90", 0.3)),
}


def _pct(values: list, q: float):
    if not values:
        return None
    s = sorted(values)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def run(design_key: str, flights: int = 200, seed: int = 1, season: str = "summer",
        valve_fault_rate: float = 0.02, float_hours: float = 1.0,
        free_lift: float | None = None, real_days_station: str | None = None,
        max_range_m: float | None = None) -> dict:
    from .sizing import ladder
    dp = ladder()[design_key]
    if free_lift is not None:
        dp.mission["free_lift_fraction"] = free_lift
    rng = random.Random(seed)
    rows = []
    day_names = None
    if real_days_station:
        from .atmosphere import real_days
        code = {"summer": "JJA", "winter": "DJF", "spring": "MAM", "autumn": "SON"}.get(season)
        day_names = real_days(real_days_station, code) if code else \
            real_days(real_days_station, months=(5, 9))
    for i in range(flights):
        fault = rng.random() < valve_fault_rate
        if day_names:
            # A real day needs no scale or veer: its variability is its own.
            wind, scale, veer = rng.choice(day_names), 1.0, 0.0
        else:
            names, weights = zip(*SEASONS[season])
            wind = rng.choices(names, weights)[0]
            scale, veer = math.exp(rng.gauss(0.0, 0.25)), rng.gauss(0.0, 30.0)
        cfg = config_from_design(
            dp, wind=wind,
            wind_scale=scale,
            wind_veer_deg=veer,
            gas_fill_error=rng.gauss(0.0, 0.03),
            earth_ir_w_m2=rng.uniform(150.0, 280.0),
            launch_hour=rng.uniform(4.5, 8.0),
            float_duration_s=float_hours * 3600.0,
            valve_fail_closed=fault,
        )
        cfg.dry_mass_kg *= 1.0 + rng.gauss(0.0, 0.02)
        res = simulate(cfg, record_every_s=1e9)
        s = res.summary
        rows.append({"i": i, "wind": wind, "scale": round(cfg.wind_scale, 2),
                     "valve_fault": fault, **s})
    reached = [r for r in rows if r["reached_float"]]
    held = [r for r in reached if r["float_mean_m"] and r["float_mean_m"] > 18_000.0
            and not r["burst"]]
    summary = {
        "design": design_key, "flights": flights, "seed": seed, "season": season,
        "winds": f"real soundings, {real_days_station}" if real_days_station
        else "stacked percentile profiles",
        "station_error_end_km_p50": _pct([r["station_error_end_km"] for r in reached
                                          if r.get("station_error_end_km") is not None], 0.5),
        "reached_float": len(reached) / flights,
        "held_above_18km_for_dwell": len(held) / flights,
        "burst": sum(r["burst"] for r in rows) / flights,
        "valve_faults_injected": sum(r["valve_fault"] for r in rows),
        "time_to_float_min_p50": _pct([r["time_to_float_min"] for r in reached], 0.5),
        "time_to_float_min_p90": _pct([r["time_to_float_min"] for r in reached], 0.9),
        "max_altitude_m_p10": _pct([r["max_altitude_m"] for r in rows], 0.1),
        "max_altitude_m_p50": _pct([r["max_altitude_m"] for r in rows], 0.5),
        "float_mean_m_p50": _pct([r["float_mean_m"] for r in reached], 0.5),
        "landing_range_km_p50": _pct([r["landing_range_km"] for r in rows], 0.5),
        "landing_range_km_p90": _pct([r["landing_range_km"] for r in rows], 0.9),
        "landing_range_km_max": max(r["landing_range_km"] for r in rows),
        "ballast_used_kg_p90": _pct([r["ballast_used_kg"] for r in rows], 0.9),
    }
    return {"summary": summary, "flights": rows}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--design", default="S1-touch/hull")
    ap.add_argument("--flights", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--season", default="summer",
                    choices=sorted(set(SEASONS) | {"spring", "autumn"}))
    ap.add_argument("--real-days", metavar="STATION", nargs="?", const="GMM00010393",
                    default=None, help="fly real soundings (default station Lindenberg) "
                    "instead of stacked percentile profiles")
    ap.add_argument("--free-lift", type=float, default=None,
                    help="override launch free lift fraction")
    ap.add_argument("--full", action="store_true", help="include every flight row")
    a = ap.parse_args(argv)
    out = run(a.design, a.flights, a.seed, a.season, free_lift=a.free_lift,
              real_days_station=a.real_days)
    print(json.dumps(out if a.full else out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
