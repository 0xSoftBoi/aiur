"""Fault cases on the unified plant: what does each failure cost?

The P0 twin's rule applies: a fault is acceptable when the outcome is safe,
not when the mission survives.  Here "safe" means the vehicle stays inside
the range fence or is cut down by it, never exceeds the altitude ceiling,
and comes down under parachute.

    python -m aiur.strato.faults
"""

from __future__ import annotations

import json
import sys

from .mission6 import MissionOptions, UnifiedSim
from .sizing import ladder

CASES = {
    "nominal": {},
    "motor fails 10 min into float": {"motor_fail_at_s": 5500.0},
    "motor never starts": {"motor_fail_at_s": 0.0},
    "gimbal jams 10 min into float": {"gimbal_jam_at_s": 5500.0},
    "gimbal jams before hull takes shape": {"gimbal_jam_at_s": 3000.0},
    "gusts 3x (1.5 m/s RMS)": {"gust_sigma_m_s": 1.5},
    "overfilled 8 %": {"_cfg": {"gas_fill_error": 0.08}},
    "underfilled 8 %": {"_cfg": {"gas_fill_error": -0.08}},
    "90th-percentile summer wind": {"_cfg": {"wind": "midlat-summer-p90"}},
}


def run(design: str = "S2-dayloiter/hull") -> dict:
    dp = ladder()[design]
    out = {}
    for name, kw in CASES.items():
        kw = dict(kw)
        cfg = kw.pop("_cfg", {})
        res = UnifiedSim(dp, MissionOptions(**kw), **cfg).run()
        safe = (res["final_phase"] == "LANDED" and res["landing_range_km"] <= 215.0
                and (res["float_mean_m"] or 0) < 27_000.0)
        out[name] = {
            "reached_float": res["reached_float"], "float_mean_m": res["float_mean_m"],
            "float_sd_m": res["float_sd_m"], "max_pitch_deg": res["max_pitch_deg"],
            "station_change_km": None if res["station_error_end_km"] is None else round(
                res["station_error_end_km"] - res["station_error_start_km"], 1),
            "ballast_used_kg": res["ballast_used_kg"],
            "landing_range_km": res["landing_range_km"],
            "ended": res["events"][-2]["event"] if len(res["events"]) > 1 else "",
            "safe": safe,
        }
    return out


def main(argv: list[str]) -> int:
    design = next((a for a in argv if not a.startswith("--")), "S2-dayloiter/hull")
    res = run(design)
    if "--json" in argv:
        print(json.dumps(res, indent=2))
        return 0
    print(f"fault cases, {design}")
    for name, r in res.items():
        print(f"  {name:38s} float {str(r['float_mean_m']):>6} m  sd {str(r['float_sd_m']):>4}  "
              f"pitch<= {r['max_pitch_deg']:5.1f}  station {str(r['station_change_km']):>6} km  "
              f"ballast {r['ballast_used_kg']:.2f}  lands {r['landing_range_km']:6.1f} km  "
              f"{'SAFE' if r['safe'] else 'UNSAFE'}  [{r['ended']}]")
    return 0 if all(r["safe"] for r in res.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
