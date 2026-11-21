"""Unit cost, cost per flight, and the production learning curve.

The question is not what one prototype costs.  It is what the hundredth and
thousandth cost, and what a *flight* costs once recovery odds are included -
because a stratospheric vehicle that lands 100 km downrange is reusable only
with some probability, and the film is single-use regardless.

Parts come from the avionics table and the sized design.  Labour hours and
learning rates are [estimate]; the structure follows the Ukrainian pattern in
which purchased parts are ~90 % of unit cost at volume and the factory is
split by skill (film sealing / electronics / final assembly).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sys

from .harness import load, review

LABOUR_USD_PER_H = 18.0
FILM_PURCHASE_FACTOR = 1.38


@dataclass(frozen=True)
class Learning:
    """Wright's law: each doubling of cumulative units multiplies by ``rate``."""

    labour_rate: float = 0.82
    parts_rate: float = 0.94

    def factor(self, units: int, rate: float) -> float:
        return units ** math.log2(rate)


def unit_cost(dp, units: int = 1, learning: Learning = Learning()) -> dict:
    """Bill of cost for one vehicle at cumulative production ``units``."""

    data = load()
    tier = "S2" if dp.mission["name"].startswith(("S2", "S3", "S4")) else "S1"
    rep = review(data, tier)
    g, m, p, e = dp.geometry, dp.mass_kg, dp.propulsion, dp.energy
    parts: dict = {}
    labour_h: dict = {}
    if dp.architecture == "hull":
        from .materials import FILMS
        film = next(f for f in FILMS.values() if f.name == g["film"])
        # Purchased roll area over hull area.  A gore fills ~73 % of its
        # bounding rectangle and nests poorly; 1.38 is the best case on a
        # well-matched roll, not the 1.18 first assumed.  [patterns.py]
        area = g["surface_area_m2"] * g["film_plies_equiv"] * FILM_PURCHASE_FACTOR
        parts["envelope film"] = area * film.usd_per_m2
        parts["seam tape, load patches, fittings"] = 60.0 + 0.9 * g["surface_area_m2"]
        # Spar fabric dominates: ~1 m2 of coated ripstop per m2 of fin.
        parts["fins (film + air-beam fabric + valves)"] = 14.0 * g["fin_area_total_m2"] + 40.0
        net = dp.structure.get("net") or {}
        if net:
            parts["tendon net (UHMWPE line + sleeve tape)"] = 0.22 * net["tendon_length_m"]
        parts["spine webbing, rigging, pods"] = 6.0 * g["length_m"] + 70.0
        # Sealing: gore length x gores; a bar sealer does ~1.2 m/min incl. handling.
        # Fin seam scales with hull length (4.1 x L from the patterns).
        seam_m = 12 * g["length_m"] * 1.1 + 4.1 * g["length_m"]
        labour_h["cut and seal envelope"] = seam_m / 1.2 / 60.0 * 2.2 + 4.0
        labour_h["fins"] = 6.0
        if net:
            labour_h["lay and tape tendon net"] = net["tendon_length_m"] / 2.0 / 60.0
        reusable_fraction_env = 0.0
    else:
        from .materials import LATEX
        balloon = next(b for b in LATEX.values() if b.name == g["balloon"])
        parts["latex cells x2"] = 2 * balloon.usd
        parts["neck valves x2"] = 2 * 35.0
        parts["boom"] = dp.structure["boom"].get("usd", 90.0)
        parts["rigging, pods"] = 60.0
        labour_h["boom and rigging"] = 5.0
        reusable_fraction_env = 0.0
    parts["propulsion (motor, prop, ESC, gimbal)"] = p["usd"]
    parts["battery packs"] = e["pack_usd"]
    if e["array_usd"]:
        parts["solar array"] = e["array_usd"]
    parts["avionics + termination (netlist)"] = rep["all_listed_parts_usd"] - 0.0
    parts["harness, connectors, foam bay"] = 55.0
    parts["recovery (parachute, reflector)"] = 0.0  # already in the netlist total
    labour_h["avionics assembly + harness"] = 7.0
    labour_h["integration + acceptance test"] = 8.0
    parts_total = sum(parts.values()) * learning.factor(units, learning.parts_rate)
    labour_total_h = sum(labour_h.values()) * learning.factor(units, learning.labour_rate)
    labour_usd = labour_total_h * LABOUR_USD_PER_H
    overhead = 0.15 * (parts_total + labour_usd)
    total = parts_total + labour_usd + overhead
    consumable = sum(v for k, v in parts.items()
                     if k.startswith(("envelope", "seam", "latex"))) \
        * learning.factor(units, learning.parts_rate)
    return {
        "units": units, "parts": {k: round(v, 0) for k, v in parts.items() if v},
        "parts_usd": round(parts_total, 0), "labour_h": round(labour_total_h, 1),
        "labour_usd": round(labour_usd, 0), "overhead_usd": round(overhead, 0),
        "unit_usd": round(total, 0), "parts_share": round(parts_total / total, 2),
        "single_use_usd": round(consumable, 0),
        "gas_usd": round(dp.lift.get("launch_gas_usd", 0.0), 0),
    }


def cost_per_flight(dp, units: int, recovery_probability: float = 0.7,
                    refurb_usd: float = 60.0, crew_h: float = 14.0) -> dict:
    """Expected marginal cost of one flight, amortising recovered hardware."""

    u = unit_cost(dp, units)
    reusable = u["unit_usd"] - u["single_use_usd"]
    # Expected hardware consumed: the single-use part every time, the rest
    # whenever recovery fails.
    hardware = u["single_use_usd"] + (1.0 - recovery_probability) * reusable \
        + recovery_probability * refurb_usd
    ops = crew_h * LABOUR_USD_PER_H + 120.0  # chase vehicle, fuel
    return {"units": units, "recovery_probability": recovery_probability,
            "hardware_usd": round(hardware, 0), "gas_usd": u["gas_usd"],
            "operations_usd": round(ops, 0),
            "per_flight_usd": round(hardware + u["gas_usd"] + ops, 0),
            "per_flight_helium_usd": round(hardware + u["gas_usd"] * 28.0 / 1.6 + ops, 0)}


def main(argv: list[str]) -> int:
    from .sizing import ladder
    pts = ladder()
    out = {}
    for key in ("S1-touch/tandem", "S1-touch/hull", "S2-dayloiter/hull",
                "S3-diurnal/hull-superpressure"):
        dp = pts[key]
        out[key] = {"unit": {n: unit_cost(dp, n) for n in (1, 10, 100, 1000)},
                    "flight": {n: cost_per_flight(dp, n) for n in (1, 100, 1000)}}
    if "--json" in argv:
        print(json.dumps(out, indent=2))
        return 0
    for key, v in out.items():
        print(f"=== {key}")
        first = v["unit"][1]
        for k, usd in first["parts"].items():
            print(f"    {k:42s} ${usd:6.0f}")
        print("  unit cost:  " + "   ".join(
            f"#{n}: ${c['unit_usd']:.0f} ({c['labour_h']:.0f} h, parts {100*c['parts_share']:.0f} %)"
            for n, c in v["unit"].items()))
        print("  per flight: " + "   ".join(
            f"#{n}: ${c['per_flight_usd']:.0f} (He: ${c['per_flight_helium_usd']:.0f})"
            for n, c in v["flight"].items()))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
