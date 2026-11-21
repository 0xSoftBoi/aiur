"""Trade studies: the sweeps that picked the design.

Each function answers one question the design log asks, with the sizing
closure as the judge.  ``python -m aiur.strato.trades`` prints all of them.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys

from .atmosphere import WIND_PROFILES, WindProfile, isa
from .cost import unit_cost
from .materials import FILMS, Tube
from .sizing import (MISSIONS, Mission, air_beam, carbon_boom, sealed_beam_pressure_at_altitude,
                     size_hull, size_tandem, station_keeping_availability)


def _row(dp) -> dict:
    g = dp.geometry
    return {"closed": dp.closed, "volume_m3": round(g.get("volume_m3", 0), 0),
            "length_m": round(g.get("length_m", g.get("boom_length_m", 0)), 1),
            "gross_kg": round(dp.mass_kg.get("gross", 0), 1),
            "film_kg": round(dp.mass_kg.get("envelope_film", dp.mass_kg.get("latex_cells", 0)), 1),
            "cruise_w": round(dp.propulsion.get("cruise_electrical_w", 0), 0),
            "launch_nm3": round(dp.lift.get("launch_gas_nm3", 0), 1)}


def film_trade(mission_key: str = "S2-dayloiter") -> dict:
    """Which envelope film?  Mass closes on areal density, money on price."""

    out = {}
    for key in FILMS:
        dp = size_hull(MISSIONS[mission_key], key, volume_limit_m3=50_000.0)
        r = _row(dp)
        if dp.closed:
            r["envelope_usd"] = round(dp.geometry["surface_area_m2"] * 1.18 * FILMS[key].usd_per_m2, 0)
            r["cold_ok"] = FILMS[key].min_temp_k <= 200.0
        out[key] = r
    return out


def rev_a_scaled_p0() -> dict:
    """Rev A: scale the indoor P0 blimp (TPU envelope, air ballonet) up.

    A ballonet that keeps the hull taut from the ground to 20 km must fill
    93 % of it at launch, and published practice adds ~40 % of hull mass for
    one [cited: NASA TM-2007-214861 allowances].  The closure says what that
    costs.
    """

    out = {}
    for film, label in (("tpu-50um", "TPU 50 um + ballonet"),
                        ("nylon-tpu-70gsm", "TPU-coated ripstop + ballonet")):
        f = FILMS[film]
        heavy = dataclasses.replace(f, areal_density_kg_m2=f.areal_density_kg_m2 * 1.4)
        FILMS["_rev_a"] = heavy
        dp = size_hull(MISSIONS["S1-touch"], "_rev_a", volume_limit_m3=100_000.0)
        del FILMS["_rev_a"]
        r = _row(dp)
        r["ballonet_fraction_at_launch"] = round(
            1.0 - isa(20_000).density_kg_m3 / isa(0).density_kg_m3, 3)
        out[label] = r
    out["flaccid-launch LLDPE 20 um (rev B)"] = _row(size_hull(MISSIONS["S1-touch"], "lldpe-20um"))
    return out


def altitude_trade(mission_key: str = "S2-dayloiter") -> dict:
    """How high?  Thinner air costs volume; the wind minimum is the prize."""

    out = {}
    base = MISSIONS[mission_key]
    summer, winter = WindProfile("midlat-summer-p50"), WindProfile("midlat-winter-p50")
    for alt_km in (14, 16, 18, 20, 22, 24):
        m = dataclasses.replace(base, float_altitude_m=alt_km * 1000.0)
        r = _row(size_hull(m, "lldpe-20um", volume_limit_m3=50_000.0))
        r["summer_p50_wind"] = round(summer.speed(alt_km * 1000.0), 1)
        r["winter_p50_wind"] = round(winter.speed(alt_km * 1000.0), 1)
        r["air_density"] = round(isa(alt_km * 1000.0).density_kg_m3, 4)
        out[f"{alt_km} km"] = r
    return out


def gas_trade() -> dict:
    out = {}
    for key in ("S1-touch", "S2-dayloiter"):
        for gas in ("hydrogen", "helium"):
            m = dataclasses.replace(MISSIONS[key], gas=gas)
            dp = size_hull(m, "lldpe-20um")
            r = _row(dp)
            r["gas_usd_per_launch"] = round(dp.lift["launch_gas_usd"], 0)
            out[f"{key} / {gas}"] = r
    return out


def speed_trade() -> dict:
    """What does airspeed cost, and what does it buy in availability?"""

    out = {}
    for cruise in (3.0, 6.0, 9.0, 12.0, 15.0):
        m = dataclasses.replace(MISSIONS["S2-dayloiter"], cruise_airspeed_m_s=cruise,
                                dash_airspeed_m_s=cruise * 1.6)
        dp = size_hull(m, "lldpe-20um", volume_limit_m3=50_000.0, series=12)
        r = _row(dp)
        av = station_keeping_availability(cruise, 20_000.0)
        r["holds"] = [k.replace("midlat-", "") for k, v in av.items() if v["holds"]]
        out[f"{cruise:g} m/s"] = r
    return out


def payload_trade() -> dict:
    out = {}
    for kg in (0.5, 1.0, 2.0, 5.0, 10.0, 20.0):
        m = dataclasses.replace(MISSIONS["S2-dayloiter"], payload_kg=kg, payload_w=5.0 * kg)
        dp = size_hull(m, "lldpe-20um")
        r = _row(dp)
        r["payload_fraction"] = round(kg / dp.mass_kg["gross"], 2)
        r["unit_usd_at_100"] = unit_cost(dp, 100)["unit_usd"]
        out[f"{kg:g} kg"] = r
    return out


def overnight_trade() -> dict:
    """How to survive the night: ballast, or hold the gas in?"""

    out = {}
    m = MISSIONS["S3-diurnal"]
    for label, film, sp in (("zero-pressure LLDPE 38 um + ballast", "lldpe-38um", False),
                            ("superpressure LLDPE 38 um", "lldpe-38um", True),
                            ("superpressure PE/EVOH 30 um", "pe-evoh-30um", True),
                            ("superpressure BoPET 12 um", "pet-12um", True),
                            ("superpressure UHMWPE 18 g/m2", "dcf-18gsm", True)):
        dp = size_hull(m, film, superpressure=sp, volume_limit_m3=100_000.0)
        r = _row(dp)
        r["plies_needed"] = round(dp.geometry.get("film_plies_equiv", 0), 2)
        r["design_dp_pa"] = round(dp.structure.get("design_pressure_pa", 0), 0)
        r["ballast_kg_per_night"] = round(dp.mass_kg.get("ballast", 0), 2)
        if dp.closed:
            r["unit_usd_first"] = unit_cost(dp, 1)["unit_usd"]
        out[label] = r
    return out


def airframe_trade() -> dict:
    """What should carry bending: a beam, or the hull's own pressure?

    For one bending moment, compare an inflated fabric beam, a carbon tube,
    and the hull acting as a pressurised tube.  The air-beam wins on mass
    over carbon, and the hull wins over both by orders of magnitude, because
    wrinkling moment goes as p r^3.  Hence: the hull is the air frame; beams
    are for the fins and for the tandem's boom.
    """

    dp = size_hull(MISSIONS["S2-dayloiter"], "lldpe-20um")
    length = dp.geometry["length_m"]
    moment = dp.structure["distributed_bending_nm"]
    concentrated = (dp.mass_kg["gross"] - dp.mass_kg["envelope_film"]) * 9.81 * length / 8.0
    out = {"hull_length_m": round(length, 1),
           "bending_if_load_spread_along_spine_nm": round(moment, 0),
           "bending_if_single_gondola_nm": round(concentrated, 0),
           "hull_wrinkle_capacity_at_relief_nm": round(dp.structure["hull_wrinkle_moment_nm"], 0),
           "options_for_single_gondola_moment": {}}
    ab = air_beam(concentrated, length)
    cb = carbon_boom(concentrated, length)
    out["options_for_single_gondola_moment"] = {
        "air-beam keel": {"mass_kg": round(ab["mass_kg"], 2), "radius_m": round(ab["radius_m"], 3),
                          "gauge_kpa": round(ab["gauge_pressure_pa"] / 1000.0, 1)},
        "carbon tube keel": {"mass_kg": round(cb["mass_kg"], 2), "od_mm": cb["od_m"] * 1000},
        "hull pressure alone": {"mass_kg": 0.0,
                                "pressure_needed_pa": round(
                                    2 * concentrated * 1.5 / (math.pi * (dp.geometry["diameter_m"] / 2) ** 3), 1)},
    }
    out["sealed_fin_beam_gauge_kpa_by_altitude"] = {
        f"{z} km": round(sealed_beam_pressure_at_altitude(3_000.0, z * 1000.0) / 1000.0, 1)
        for z in (0, 5, 10, 15, 20)}
    return out


def architecture_trade() -> dict:
    out = {}
    for label, dp in (("tandem 2 x 1200 g latex", size_tandem(MISSIONS["S1-touch"], "1200g")),
                      ("tandem 2 x 1600 g latex", size_tandem(MISSIONS["S1-touch"], "1600g")),
                      ("hull LLDPE 20 um", size_hull(MISSIONS["S1-touch"], "lldpe-20um"))):
        r = _row(dp)
        r["dash_w"] = round(dp.propulsion["dash_electrical_w"], 0)
        r["suspended_kg"] = round(dp.mass_kg["gross"] - dp.mass_kg.get(
            "latex_cells", dp.mass_kg.get("envelope_film", 0)), 1)
        r["unit_usd_first"] = unit_cost(dp, 1)["unit_usd"]
        r["unit_usd_at_1000"] = unit_cost(dp, 1000)["unit_usd"]
        out[label] = r
    return out


ALL = {"rev_a_scaled_p0": rev_a_scaled_p0, "architecture": architecture_trade,
       "film": film_trade, "altitude": altitude_trade, "gas": gas_trade, "speed": speed_trade,
       "payload": payload_trade, "overnight": overnight_trade, "airframe": airframe_trade}


def main(argv: list[str]) -> int:
    res = {k: f() for k, f in ALL.items()}
    if "--json" in argv:
        print(json.dumps(res, indent=2))
        return 0
    for name, table in res.items():
        print(f"=== {name}: {ALL[name].__doc__.strip().splitlines()[0] if ALL[name].__doc__ else ''}")
        for k, v in table.items():
            print(f"  {k:40s} {v}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
