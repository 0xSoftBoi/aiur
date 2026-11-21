"""Avionics netlist checker.

The harness is data: ``hardware/strato/avionics/{components,ports,connections}.csv``.
This module is the review that would otherwise happen by squinting at a
wiring diagram.  It checks, mechanically, the things that end flights:

* every wire lands on a declared port, and single-use ports are used once;
* every powered part sees a voltage inside its rating;
* every rail carries its peak load with margin, every wire its current, and
  no long run drops more than 5 % of its rail;
* no two devices share an I2C address on a bus;
* every part is rated for the temperature of the place it is mounted;
* the flight-termination system shares **no conductor** with the autopilot -
  not a rail, not a bus, not a ground-referenced signal.  The only permitted
  crossings are radio and an opto-isolated heartbeat.

``python -m aiur.strato.harness`` prints the review; ``--svg`` writes the
wiring diagram; ``--check-budget`` fails if the mass/power totals have
drifted from what the sizing model assumes.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "hardware", "strato", "avionics"))

#: Copper resistance, ohm per metre [physics / AWG tables].
AWG_OHM_PER_M = {14: 0.00829, 16: 0.01317, 18: 0.02095, 20: 0.03331, 22: 0.05296,
                 24: 0.08422, 26: 0.1339, 28: 0.2129}
#: Chassis-wiring ampacity at sea level, A.  Derated at altitude because a
#: wire in 5 kPa air sheds heat mostly by radiation [estimate: x0.6].
AWG_AMPACITY = {14: 32, 16: 22, 18: 16, 20: 11, 22: 7, 24: 3.5, 26: 2.2, 28: 1.4}
ALTITUDE_AMPACITY_DERATE = 0.6
RAIL_MARGIN = 0.70
MAX_DROP_FRACTION = 0.05

#: Worst-case temperature of each mounting location, C.
LOCATION_TEMP_C = {"bay": 0.0, "stern-pod": -20.0, "ftu-box": -20.0, "external": -65.0,
                   "bay-lid": -30.0, "spine-bottom": -65.0, "payload": -30.0}

SINGLE_USE = {"uart", "pwm", "gpio", "analog", "rf", "phase", "opto"}
#: Kinds that conduct between two systems.  Radio and opto do not.
CONDUCTIVE = {"power", "uart", "i2c", "pwm", "gpio", "analog", "onewire", "phase", "can", "spi"}

#: Groups whose mass the sizing model derives itself.
SIZED_ELSEWHERE = {"recovery", "option"}
SIZED_ROWS = {"BAT", "BAT_P", "MOTOR", "PROP", "ESC", "SRV_GY", "SRV_GP"}


def _read(name: str, data_dir: str) -> list[dict]:
    with open(os.path.join(data_dir, name), newline="") as fh:
        return list(csv.DictReader(fh))


def load(data_dir: str = DATA) -> dict:
    comps = {r["id"]: r for r in _read("components.csv", data_dir)}
    ports = {(r["component"], r["port"]): r for r in _read("ports.csv", data_dir)}
    conns = _read("connections.csv", data_dir)
    for c in comps.values():
        for k in ("qty", "mass_g", "unit_usd", "v_min", "v_max", "power_w_avg",
                  "power_w_peak", "temp_min_c"):
            c[k] = float(c[k])
    return {"components": comps, "ports": ports, "connections": conns}


def review(data: dict, tier: str = "S2", propulsion_peak_a: float = 9.0) -> dict:
    comps, ports, conns = data["components"], data["ports"], data["connections"]
    errors: list[str] = []
    warnings: list[str] = []
    in_tier = {cid for cid, c in comps.items() if tier in c["tiers"].split()}

    used = defaultdict(int)
    rail_load = defaultdict(float)
    rail_source = {}
    i2c = defaultdict(dict)
    graph = defaultdict(set)

    def sink_peak_a(cid: str, volts: float) -> float:
        if cid == "ESC":
            return propulsion_peak_a
        c = comps[cid]
        return c["power_w_peak"] * c["qty"] / volts if volts > 0 else 0.0

    for cn in conns:
        a, b = (cn["from"], cn["from_port"]), (cn["to"], cn["to_port"])
        if cn["from"] not in in_tier or cn["to"] not in in_tier:
            continue
        for end in (a, b):
            if end[0] not in comps:
                errors.append(f"{cn['net']}: unknown component {end[0]}")
            elif end not in ports:
                errors.append(f"{cn['net']}: {end[0]} has no port {end[1]}")
        if a not in ports or b not in ports:
            continue
        pa, pb = ports[a], ports[b]
        kind = cn["kind"]
        for end, p in ((a, pa), (b, pb)):
            if p["kind"] in SINGLE_USE:
                used[end] += 1
        if kind in CONDUCTIVE:
            graph[cn["from"]].add(cn["to"])
            graph[cn["to"]].add(cn["from"])
        if kind == "power":
            volts = float(pa["volts"])
            sink = comps[cn["to"]]
            if not (sink["v_min"] <= volts <= sink["v_max"]):
                errors.append(f"{cn['net']}: {cn['to']} rated {sink['v_min']:g}-{sink['v_max']:g} V "
                              f"is fed {volts:g} V from {cn['from']}")
            amps = sink_peak_a(cn["to"], volts)
            # Loads fed through a pass-through (PM) count against the upstream source too.
            rail_load[a] += amps
            rail_source[a] = float(pa["capacity_a"])
            awg = int(cn["awg"])
            length = float(cn["length_m"])
            cap = AWG_AMPACITY[awg] * ALTITUDE_AMPACITY_DERATE
            if amps > cap:
                errors.append(f"{cn['net']}: {amps:.1f} A to {cn['to']} on {awg} AWG "
                              f"(limit {cap:.1f} A at altitude)")
            drop = 2.0 * length * AWG_OHM_PER_M[awg] * amps
            if drop > MAX_DROP_FRACTION * volts:
                errors.append(f"{cn['net']}: {drop:.2f} V drop to {cn['to']} over {length:g} m of "
                              f"{awg} AWG at {amps:.1f} A ({100*drop/volts:.0f} % of {volts:g} V)")
        if kind == "i2c" and cn["i2c_addr"]:
            bus = i2c[cn["net"]]
            if cn["i2c_addr"] in bus:
                errors.append(f"{cn['net']}: I2C address {cn['i2c_addr']} used by both "
                              f"{bus[cn['i2c_addr']]} and {cn['to']}")
            bus[cn["i2c_addr"]] = cn["to"]

    for end, n in used.items():
        if n > 1:
            errors.append(f"{end[0]}.{end[1]} is a single-use port wired {n} times")
    # Downstream loads of a pass-through source: PM feeds everything on VBAT.
    for pm, bat, bec in (("PM", "BAT", "BEC5"), ("PM_P", "BAT_P", "BEC_POD")):
        if (pm, "BAT_OUT") in rail_load:
            rail_load[(bat, "MAIN")] = rail_load[(pm, "BAT_OUT")] + \
                rail_load.get((bec, "5V"), 0.0) * 5.0 / 22.2
    for src, amps in rail_load.items():
        cap = rail_source.get(src, 0.0)
        if cap and amps > RAIL_MARGIN * cap:
            errors.append(f"{src[0]}.{src[1]}: peak load {amps:.1f} A exceeds "
                          f"{RAIL_MARGIN:.0%} of its {cap:g} A rating")

    # Temperature
    for cid in sorted(in_tier):
        c = comps[cid]
        ambient = LOCATION_TEMP_C.get(c["location"])
        if ambient is None:
            warnings.append(f"{cid}: unknown location {c['location']!r}")
        elif c["temp_min_c"] > ambient:
            errors.append(f"{cid} ({c['part']}) is rated to {c['temp_min_c']:g} C but "
                          f"{c['location']} reaches {ambient:g} C")
        elif c["temp_min_c"] > ambient - 10:
            warnings.append(f"{cid}: only {ambient - c['temp_min_c']:g} C of cold margin in {c['location']}")

    # Independence of termination
    term = {cid for cid in in_tier if comps[cid]["group"] == "termination"}
    seen = set()
    stack = list(term)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph[n] - seen)
    leak = sorted(seen - term)
    if leak:
        errors.append("termination system is conductively connected to: " + ", ".join(leak))
    crossings = [cn["net"] for cn in conns if cn["from"] in in_tier and cn["to"] in in_tier
                 and (cn["from"] in term) != (cn["to"] in term)]

    # Budgets
    mass = power_avg = power_peak = cost = 0.0
    all_cost = 0.0
    for cid in in_tier:
        c = comps[cid]
        all_cost += c["unit_usd"] * c["qty"]
        if c["group"] in SIZED_ELSEWHERE or cid in SIZED_ROWS:
            continue
        mass += c["mass_g"] * c["qty"]
        cost += c["unit_usd"] * c["qty"]
        # Heaters are sized by the thermal model; the FTU runs on its own cells.
        if cid.startswith("HTR") or c["group"] == "termination":
            continue
        power_avg += c["power_w_avg"] * c["qty"]
        power_peak += c["power_w_peak"] * c["qty"]
    # Wire mass from the netlist: copper + insulation ~ 1.6x copper [estimate].
    wire_g = 0.0
    for cn in conns:
        if cn["from"] in in_tier and cn["to"] in in_tier and cn["awg"] not in ("", "0"):
            awg = int(cn["awg"])
            area_mm2 = 0.012668 * 92 ** ((36 - awg) / 19.5)
            cores = {"power": 2, "phase": 3, "can": 3, "spi": 4, "analog": 2}.get(cn["kind"], 1)
            wire_g += float(cn["length_m"]) * area_mm2 * 8.96 * 1.6 * cores
    return {
        "tier": tier, "errors": errors, "warnings": warnings,
        "fixed_avionics_mass_kg": round(mass / 1000.0, 3),
        "fixed_avionics_power_w": round(power_avg, 2),
        "fixed_avionics_peak_w": round(power_peak, 2),
        "fixed_avionics_usd": round(cost, 0), "all_listed_parts_usd": round(all_cost, 0),
        "wire_mass_kg": round(wire_g / 1000.0, 3),
        "components": len(in_tier),
        "connections": sum(1 for cn in conns if cn["from"] in in_tier and cn["to"] in in_tier),
        "termination_crossings": crossings,
        "rail_peak_a": {f"{k[0]}.{k[1]}": round(v, 2) for k, v in rail_load.items()},
    }


# --- diagram -----------------------------------------------------------------

_KIND_COLOUR = {"power": "#c0392b", "uart": "#2471a3", "i2c": "#1e8449", "pwm": "#b9770e",
                "gpio": "#7d3c98", "analog": "#566573", "onewire": "#148f77",
                "rf": "#99a3a4", "phase": "#922b21", "opto": "#d4ac0d", "can": "#e74c3c",
                "spi": "#2e86c1"}
_COLUMNS = ["external", "ftu-box", "bay-lid", "bay", "spine-bottom", "stern-pod"]


def wiring_svg(data: dict, tier: str = "S2") -> str:
    comps, conns = data["components"], data["connections"]
    in_tier = [cid for cid, c in comps.items() if tier in c["tiers"].split()]
    cols = defaultdict(list)
    for cid in in_tier:
        loc = comps[cid]["location"]
        cols[loc if loc in _COLUMNS else "bay"].append(cid)
    # The bay is dense: split it over two columns.
    bay = cols.pop("bay", [])
    half = (len(bay) + 1) // 2
    layout = []
    for name in _COLUMNS:
        if name == "bay":
            layout.append(("bay (heated, foam)", bay[:half]))
            layout.append(("bay (cont.)", bay[half:]))
        elif cols.get(name):
            layout.append((name, cols[name]))
    bw, bh, gx, gy = 190, 34, 70, 12
    pos = {}
    width = len(layout) * (bw + gx) + gx
    height = max(len(ids) for _, ids in layout) * (bh + gy) + 110
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           f'font-family="Helvetica,Arial,sans-serif" font-size="11">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="{gx}" y="24" font-size="15" font-weight="bold">STRATO {tier} avionics harness'
           f' - generated from hardware/strato/avionics/*.csv</text>']
    for i, (name, ids) in enumerate(layout):
        x = gx + i * (bw + gx)
        out.append(f'<text x="{x}" y="52" font-weight="bold" fill="#333">{name}</text>')
        for j, cid in enumerate(ids):
            y = 64 + j * (bh + gy)
            pos[cid] = (x, y)
    lines = []
    for n, cn in enumerate(conns):
        if cn["from"] not in pos or cn["to"] not in pos:
            continue
        (x0, y0), (x1, y1) = pos[cn["from"]], pos[cn["to"]]
        col = _KIND_COLOUR.get(cn["kind"], "#000")
        off = (n % 7 - 3) * 3
        if x0 == x1:
            xa = x0 + bw
            lines.append(f'<path d="M{xa},{y0+bh/2+off} C{xa+28+abs(off)},{y0+bh/2} '
                         f'{xa+28+abs(off)},{y1+bh/2} {xa},{y1+bh/2+off}" fill="none" '
                         f'stroke="{col}" stroke-width="1.3" opacity="0.8"/>')
        else:
            xa, xb = (x0 + bw, x1) if x1 > x0 else (x0, x1 + bw)
            mid = (xa + xb) / 2
            dash = ' stroke-dasharray="4 3"' if cn["kind"] in ("rf", "opto") else ""
            lines.append(f'<path d="M{xa},{y0+bh/2+off} C{mid},{y0+bh/2+off} {mid},{y1+bh/2+off} '
                         f'{xb},{y1+bh/2+off}" fill="none" stroke="{col}" stroke-width="1.3" '
                         f'opacity="0.8"{dash}/>')
    out.extend(lines)
    for cid, (x, y) in pos.items():
        c = comps[cid]
        fill = {"termination": "#fdecea", "power": "#fff6e0", "propulsion": "#eaf2fb",
                "recovery": "#eef7ee"}.get(c["group"], "#f4f4f4")
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="4" fill="{fill}" '
                   f'stroke="#555"/>')
        out.append(f'<text x="{x+6}" y="{y+14}" font-weight="bold">{cid}</text>')
        label = c["name"][:34].replace("&", "and")
        out.append(f'<text x="{x+6}" y="{y+27}" fill="#444" font-size="9.5">{label}</text>')
    lx = gx
    ly = height - 22
    for kind, col in _KIND_COLOUR.items():
        out.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+22}" y2="{ly}" stroke="{col}" stroke-width="2.5"/>')
        out.append(f'<text x="{lx+26}" y="{ly+4}">{kind}</text>')
        lx += 92
    out.append("</svg>")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    data = load()
    tier = "S1" if "--tier=S1" in argv else "S2"
    rep = review(data, tier)
    if "--svg" in argv:
        path = argv[argv.index("--svg") + 1]
        with open(path, "w") as fh:
            fh.write(wiring_svg(data, tier))
        print(f"wrote {path}")
        return 0
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
    else:
        print(f"STRATO {tier} harness review: {rep['components']} components, "
              f"{rep['connections']} connections")
        print(f"  fixed avionics  {rep['fixed_avionics_mass_kg']:.3f} kg, "
              f"{rep['fixed_avionics_power_w']:.1f} W average, ${rep['fixed_avionics_usd']:.0f}")
        print(f"  harness wire    {rep['wire_mass_kg']:.3f} kg")
        print(f"  rail peaks      {rep['rail_peak_a']}")
        print(f"  termination crossings: {rep['termination_crossings']}")
        for w in rep["warnings"]:
            print(f"  warn  {w}")
        for e in rep["errors"]:
            print(f"  ERROR {e}")
        print("  PASS" if not rep["errors"] else f"  FAIL ({len(rep['errors'])} errors)")
    if "--check-budget" in argv:
        from .sizing import Avionics
        av = Avionics()
        bad = []
        if abs(av.mass_kg - rep["fixed_avionics_mass_kg"] - rep["wire_mass_kg"] * 0) > 0.05 * av.mass_kg:
            bad.append(f"mass: sizing assumes {av.mass_kg} kg, netlist totals "
                       f"{rep['fixed_avionics_mass_kg']} kg")
        if abs(av.power_w - rep["fixed_avionics_power_w"]) > 0.08 * av.power_w:
            bad.append(f"power: sizing assumes {av.power_w} W, netlist totals "
                       f"{rep['fixed_avionics_power_w']} W")
        for b in bad:
            print("  BUDGET DRIFT " + b)
        if bad:
            return 2
        print("  budget matches sizing.Avionics")
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
