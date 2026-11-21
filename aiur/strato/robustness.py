"""Which unmeasured number could break the design?

Every coefficient tagged [estimate] is a bench test that has not happened.
This module pushes each one to a pessimistic and an optimistic bound, one at
a time, and reports what moves: the size and mass the mission closes at, the
power to cruise, the handling margins, and the ascent.  The ranking is the
order in which to spend bench time.

Bounds are judgement, stated in ``CASES`` so they can be argued with.

    python -m aiur.strato.robustness
"""

from __future__ import annotations

import dataclasses
import json
import sys

from . import propulsion, sizing
from .ascent import config_from_design, simulate
from .flight6dof import Airframe, handling_report
from .materials import FILMS
from .thermal import FilmOptics

DESIGN = "S2-dayloiter"


def _size(**patch) -> dict:
    """Size S2 with module-level estimates patched, then restore them."""

    saved = {}
    film_key = "lldpe-20um"
    try:
        for name, value in patch.items():
            if name == "film_density_scale":
                f = FILMS["lldpe-20um"]
                FILMS["_robust"] = dataclasses.replace(
                    f, areal_density_kg_m2=f.areal_density_kg_m2 * value)
                film_key = "_robust"
            elif name == "film_allowable":
                f = FILMS[film_key]
                FILMS["_robust"] = dataclasses.replace(f, allowable_fraction=value)
                film_key = "_robust"
            elif name == "LOW_RE_LD_SCALE":
                saved[(propulsion, name)] = getattr(propulsion, name)
                setattr(propulsion, name, value)
            elif name == "avionics_scale":
                pass
            else:
                saved[(sizing, name)] = getattr(sizing, name)
                setattr(sizing, name, value)
        av = sizing.Avionics()
        if "avionics_scale" in patch:
            k = patch["avionics_scale"]
            av = dataclasses.replace(av, mass_kg=av.mass_kg * k, power_w=av.power_w * k)
        dp = sizing.size_hull(sizing.MISSIONS[DESIGN], film_key, av=av, volume_limit_m3=20_000.0)
    finally:
        for (mod, name), value in saved.items():
            setattr(mod, name, value)
        FILMS.pop("_robust", None)
    return {"closed": dp.closed, "gross_kg": round(dp.mass_kg["gross"], 2),
            "volume_m3": round(dp.geometry["volume_m3"]),
            "length_m": round(dp.geometry["length_m"], 1),
            "cruise_w": round(dp.propulsion["cruise_electrical_w"]),
            "dash_w": round(dp.propulsion["dash_electrical_w"]),
            "array_m2": round(dp.energy["array_m2"], 2),
            "hoop_margin": round(dp.structure["film_allowable_n_per_m"]
                                 / dp.structure["hoop_load_n_per_m"], 2), "_dp": dp}


#: (label, what it is, pessimistic patch, optimistic patch)
SIZING_CASES = [
    ("film areal density", "20 um film as delivered, incl. gauge tolerance",
     {"film_density_scale": 1.20}, {"film_density_scale": 0.92}),
    ("appendage drag", "fins, pods, rigging, wrinkles as a fraction of hull drag (0.8)",
     {"APPENDAGE_DRAG_FRACTION": 1.6}, {"APPENDAGE_DRAG_FRACTION": 0.5}),
    ("low-Re propeller L/D", "section lift-to-drag at blade Re ~3e4",
     {"LOW_RE_LD_SCALE": 0.6}, {"LOW_RE_LD_SCALE": 1.4}),
    ("fin areal mass", "0.115 kg/m2 from the patterns",
     {"FIN_AREAL_KG_M2": 0.17}, {"FIN_AREAL_KG_M2": 0.09}),
    ("avionics mass and power", "netlist totals, several rows are estimates",
     {"avionics_scale": 1.5}, {"avionics_scale": 0.9}),
    ("film sustained allowable", "fraction of short-term strength usable with seams, cold",
     {"film_allowable": 0.10}, {"film_allowable": 0.30}),
    ("trim ballast fraction", "3 % of gross",
     {"TRIM_BALLAST_FRACTION": 0.06}, {"TRIM_BALLAST_FRACTION": 0.02}),
    ("lobing film factor", "extra gore width to recover polygon volume loss",
     {"LOBING_FILM_FACTOR": 1.03}, {"LOBING_FILM_FACTOR": 1.0}),
]

HANDLING_CASES = [
    ("fin lift slope", "2.2/rad on an inflated low-aspect fin",
     {"fin_lift_slope": 1.4}, {"fin_lift_slope": 2.8}),
    ("hull crossflow drag", "Cd 1.0 on hull strips",
     {"crossflow_cd": 0.6}, {"crossflow_cd": 1.3}),
    ("thrust response lag", "0.6 s motor/prop time constant",
     {"thrust_lag_s": 2.0}, {"thrust_lag_s": 0.3}),
    ("gimbal slew rate", "60 deg/s servo in the cold",
     {"gimbal_rate_rad_s": 0.26}, {"gimbal_rate_rad_s": 2.0}),
    ("CG depth", "equipment hangs 0.25 m below the hull",
     {"cg_scale": 0.6}, {"cg_scale": 1.4}),
]

ASCENT_CASES = [
    ("ascent drag of slack hull", "Cd 0.65 on the bubble",
     {"ascent_cd": 1.1}, {"ascent_cd": 0.45}),
    ("film solar absorptance", "0.03 for clean 20 um LLDPE; dust and sealant raise it",
     {"optics": FilmOptics(0.12, 0.18)}, {"optics": FilmOptics(0.02, 0.18)}),
    ("film IR emittance", "0.18; thin film is partly IR-transparent",
     {"optics": FilmOptics(0.03, 0.40)}, {"optics": FilmOptics(0.03, 0.10)}),
    ("cold cloud deck below", "Earth IR 220 W/m2; 150 over high cloud",
     {"earth_ir_w_m2": 140.0}, {"earth_ir_w_m2": 290.0}),
]


def _handling(dp, **over) -> dict:
    cg_scale = over.pop("cg_scale", 1.0)
    af = Airframe.from_design(dp, **over)
    if cg_scale != 1.0:
        af = Airframe.from_design(dp, cg_below_cv_m=af.cg_below_cv_m * cg_scale, **over)
    r = handling_report(af, dp.mission["cruise_airspeed_m_s"])
    return {"open_loop_s": r["open_loop_time_to_10deg_yaw_s"],
            "turn_overshoot_deg": r["step90_overshoot_deg"],
            "turn_saturated": r["step90_gimbal_saturated_fraction"],
            "gust_heading_rms_deg": r["gust1.5_rms_heading_error_deg"],
            "completed": r["step90_completed"] and r["gust1.5_completed"]}


def _ascent(dp, **over) -> dict:
    s = simulate(config_from_design(dp, **over), record_every_s=1e9).summary
    return {"time_to_float_min": s["time_to_float_min"], "float_sd_m": s["float_sd_m"],
            "max_supertemp_k": s["max_gas_supertemp_k"], "min_supertemp_k": s["min_gas_supertemp_k"],
            "ballast_used_kg": s["ballast_used_kg"], "landing_km": s["landing_range_km"]}


def run() -> dict:
    base = _size()
    dp = base.pop("_dp")
    out = {"baseline": {"sizing": base, "handling": _handling(dp), "ascent": _ascent(dp)},
           "sizing": [], "handling": [], "ascent": []}
    for label, what, bad, good in SIZING_CASES:
        b, g = _size(**bad), _size(**good)
        b.pop("_dp"), g.pop("_dp")
        out["sizing"].append({"estimate": label, "what": what, "pessimistic": b, "optimistic": g,
                              "gross_swing_pct": round(100 * (b["gross_kg"] - base["gross_kg"])
                                                       / base["gross_kg"], 1)})
    for label, what, bad, good in HANDLING_CASES:
        out["handling"].append({"estimate": label, "what": what,
                                "pessimistic": _handling(dp, **dict(bad)),
                                "optimistic": _handling(dp, **dict(good))})
    for label, what, bad, good in ASCENT_CASES:
        out["ascent"].append({"estimate": label, "what": what, "pessimistic": _ascent(dp, **bad),
                              "optimistic": _ascent(dp, **good)})
    out["sizing"].sort(key=lambda r: -abs(r["gross_swing_pct"]))
    return out


def main(argv: list[str]) -> int:
    res = run()
    if "--json" in argv:
        print(json.dumps(res, indent=2))
        return 0
    b = res["baseline"]
    print(f"baseline S2: {b['sizing']}")
    print("\nSIZING - pessimistic bound of each estimate, ranked by mass swing")
    for r in res["sizing"]:
        p = r["pessimistic"]
        print(f"  {r['estimate']:26s} {r['gross_swing_pct']:+6.1f} %  -> {p['gross_kg']:6.2f} kg, "
              f"{p['volume_m3']:4d} m3, cruise {p['cruise_w']:3d} W, hoop margin {p['hoop_margin']:.2f}"
              f"{'' if p['closed'] else '  DOES NOT CLOSE'}")
    print(f"\nHANDLING - baseline {b['handling']}")
    for r in res["handling"]:
        print(f"  {r['estimate']:26s} pessimistic {r['pessimistic']}")
    print(f"\nASCENT - baseline {b['ascent']}")
    for r in res["ascent"]:
        print(f"  {r['estimate']:26s} pessimistic {r['pessimistic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
