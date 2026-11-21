#!/usr/bin/env python3
"""Attribute Gazebo-vs-flight6dof differences to individual terms.

    python3 ros2_ws/src/aiur_description/scripts/gz_fins_diagnose.py [--gz-csv DIR]

Run from the repository root (it imports ``aiur.strato`` and
``tools/strato_export.py``).  No Gazebo or ROS is needed.

The in-repo 6-DoF is flown open loop with its aerodynamic terms swapped, one
at a time, for re-implementations of what the Gazebo systems compute
(LighterThanAirDynamics.cc and LiftDrag.cc, gz-sim8).  With every term swapped
the result should reproduce the Gazebo run; each single swap then says how
much of the difference that term carries.  ``flight6dof.forces`` is replaced
at run time only; nothing in ``aiur/strato`` is edited.
"""
import argparse
import csv
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import strato_export as ex  # noqa: E402
from aiur.strato import flight6dof as f6  # noqa: E402
from aiur.strato.sizing import ladder  # noqa: E402

ORIGINAL_FORCES = f6.forces


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 0 else (0.0, 0.0, 0.0)


def lift_drag(rho, s, vel, om):
    """LiftDrag.cc Update(), lines 293-506, for one surface.  Body FRD axes
    (a 180 degree roll from the link frame, so cross products carry over)."""

    cp, fwd, up = s["cp"], s["forward"], s["upward"]
    v = f6._add(vel, f6._cross(om, cp))
    speed = math.sqrt(_dot(v, v))
    if speed <= 0.01 or _dot(fwd, v) <= 0.0:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    vi = _unit(v)
    span = _unit(f6._cross(fwd, up))
    sin_sweep = max(-1.0, min(1.0, _dot(span, vi)))
    cos2 = 1.0 - sin_sweep * sin_sweep
    v_ld = f6._add(v, f6._scale(span, -_dot(v, span)))
    drag_dir = f6._scale(_unit(v_ld), -1.0)
    lift_i = _unit(f6._cross(span, v_ld))
    alpha = math.acos(max(-1.0, min(1.0, _dot(lift_i, up))))
    if _dot(lift_i, fwd) < 0.0:
        alpha = -alpha
    q = 0.5 * rho * _dot(v_ld, v_ld)
    a_s = s["alpha_stall"]
    if alpha > a_s:
        cl = max(0.0, (s["cla"] * a_s + s["cla_stall"] * (alpha - a_s)) * cos2)
        cd = (s["cda"] * a_s + s["cda_stall"] * (alpha - a_s)) * cos2
    elif alpha < -a_s:
        cl = min(0.0, (-s["cla"] * a_s + s["cla_stall"] * (alpha + a_s)) * cos2)
        cd = (-s["cda"] * a_s + s["cda_stall"] * (alpha + a_s)) * cos2
    else:
        cl = s["cla"] * alpha * cos2
        cd = s["cda"] * alpha * cos2
    force = f6._add(f6._scale(lift_i, cl * q * s["area"]),
                    f6._scale(drag_dir, abs(cd) * q * s["area"]))
    return force, f6._cross(cp, force)


def make_forces(opt: dict):
    """A drop-in for flight6dof.forces with selected terms as Gazebo has them.

    opt keys: ``coriolis2`` (the LTA plugin's added-mass terms on top of the
    physics engine's), ``axial`` (plugin axial drag), ``hull`` (None = strips,
    else a dict from lta_coefficients), ``fins`` (plugin LiftDrag surfaces).
    """

    def forces(af, st, ctl):
        if not any(opt.get(k) for k in ("coriolis2", "axial", "hull", "fins")):
            return ORIGINAL_FORCES(af, st, ctl)
        # Start from the original with the swapped parts switched off.
        saved = (af.crossflow_cd, af.fin_area_total_m2, af.drag_multiplier)
        if opt.get("hull"):
            af.crossflow_cd = 0.0
        if opt.get("fins"):
            af.fin_area_total_m2 = 0.0
        if opt.get("axial"):
            af.drag_multiplier = 0.0
        try:
            force, moment = ORIGINAL_FORCES(af, st, ctl)
        finally:
            af.crossflow_cd, af.fin_area_total_m2, af.drag_multiplier = saved
        force, moment = list(force), list(moment)
        rho = af.air.density_kg_m3
        u, v, w = st.vel
        p, q, r = st.rate
        if opt.get("axial"):
            # LighterThanAirDynamics.cc l.436-441: total dynamic pressure,
            # cos^2 of the pitch-plane incidence only, always along -x.
            qd = 0.5 * rho * (u * u + v * v + w * w)
            aoa = math.atan2(-w, u)
            force[0] += -qd * opt["axial"] * math.cos(aoa) ** 2
        if opt.get("hull"):
            # l.382-420: one velocity point, eps_v aft of the origin.
            c = opt["hull"]
            xp = -c["eps_v"]
            vp, wp = v + r * xp, w - q * xp
            cross = math.hypot(vp, wp)
            qd = 0.5 * rho * (u * u + cross * cross)
            g = math.atan2(cross, u)
            fmag = qd * (-c["fi"] * math.sin(2 * g) + c["fv"] * math.sin(g) ** 2)
            mmag = qd * (-c["mi"] * math.sin(2 * g) + c["mv"] * math.sin(g) ** 2)
            if cross > 1e-12:
                ny, nz = vp / cross, wp / cross
                force[1] += -fmag * ny
                force[2] += -fmag * nz
                moment[1] += mmag * nz
                moment[2] += -mmag * ny
        if opt.get("coriolis2"):
            # l.192-217 and 423-433: -w x (A11 v) and -w x (A22 w), which the
            # physics engine has already applied through <fluid_added_mass>.
            a11v = tuple(af.a11[i] * st.vel[i] for i in range(3))
            a22w = tuple(af.a22[i] * st.rate[i] for i in range(3))
            fa, ma = f6._cross(st.rate, a11v), f6._cross(st.rate, a22w)
            for i in range(3):
                force[i] -= fa[i]
                moment[i] -= ma[i]
        if opt.get("fins"):
            for s in opt["fins"]:
                fo, mo = lift_drag(rho, s, st.vel, st.rate)
                for i in range(3):
                    force[i] += fo[i]
                    moment[i] += mo[i]
        return tuple(force), tuple(moment)

    return forces


def frd_surfaces(af):
    """fin_surfaces() from the generator, link (FLU) -> body (FRD) axes."""

    flip = lambda a: (a[0], -a[1], -a[2])  # noqa: E731
    return [{**s, "cp": flip(s["cp"]), "upward": flip(s["upward"]), "forward": flip(s["forward"])}
            for s in ex.fin_surfaces(af)]


def fly(af, opt, vel, thrust, duration, axis, dt=0.01):
    f6.forces = make_forces(opt)
    try:
        res = f6.run(af, duration, lambda t, s: 0.0, vel[0], controlled=False,
                     initial=f6.State(vel=tuple(vel), thrust_n=thrust), dt=dt, record_s=dt)
    finally:
        f6.forces = ORIGINAL_FORCES
    key, sign = ("pitch_deg", 1.0) if axis == "pitch" else ("yaw_deg", -1.0)
    rows = res["rows"]
    t10 = next((r["t"] for r in rows if abs(r[key]) >= 10.0), None)
    peak = max((sign * r[key] for r in rows), key=abs)
    last = rows[-1]
    return {"t10": t10, "peak": peak, "end": sign * last[key],
            "V": math.sqrt(last["u"] ** 2 + last["v"] ** 2 + last["w"] ** 2)}


def gz_metrics(path, axis):
    rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(open(path))]
    key, sign = ("pitch_deg", 1.0) if axis == "pitch" else ("yaw_deg", -1.0)
    t10 = next((r["t"] for r in rows if abs(r[key]) >= 10.0), None)
    last = rows[-1]
    return {"t10": t10, "peak": max((sign * r[key] for r in rows), key=abs),
            "end": sign * last[key], "V": math.sqrt(last["u"] ** 2 + last["v"] ** 2 + last["w"] ** 2)}


def fmt(m):
    t10 = "  none" if m["t10"] is None else f"{m['t10']:6.2f}"
    return f"t10 {t10} s  peak {m['peak']:8.2f} deg  end {m['end']:8.2f} deg  V_end {m['V']:5.2f} m/s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gz-csv", default=None, help="directory of gz_fins_run.py --csv logs")
    ap.add_argument("--cases", nargs="*", default=["yaw2", "pitch2"])
    ap.add_argument("--eps-sweep", action="store_true",
                    help="only: emulated 'li-nahon' yaw2 against the separation station")
    args = ap.parse_args()
    dp = ladder()[ex.FIN_STUDY_DESIGN]
    name = ex.slug(ex.FIN_STUDY_DESIGN)
    cruise = dp.mission["cruise_airspeed_m_s"]
    d2 = math.radians(2.0)
    setups = {"yaw2": ("yaw", (cruise * math.cos(d2), cruise * math.sin(d2), 0.0), 0.0, 60.0),
              "pitch2": ("pitch", (cruise * math.cos(d2), 0.0, cruise * math.sin(d2)), 0.0, 60.0),
              "cruise": ("yaw", (cruise * math.cos(d2), cruise * math.sin(d2), 0.0),
                         dp.propulsion["drag_cruise_n"], 240.0)}
    for ratio in ex.FIN_STUDY_RATIOS:
        af = f6.Airframe.from_design(
            dp, fin_area_total_m2=ratio * dp.geometry["volume_m3"] ** (2 / 3))
        re = af.air.density_kg_m3 * 6.0 * af.hull.length_m / af.air.viscosity_pa_s
        axial = af.hull.drag_coefficient(re) * af.drag_multiplier * af.hull.reference_area_m2
        eq, ln = ex.lta_coefficients(af, "equivalent"), ex.lta_coefficients(af, "li-nahon")
        fins = frd_surfaces(af)
        zero = dict(eq, fv=0.0, mv=0.0)
        all_eq = {"coriolis2": True, "axial": axial, "hull": eq, "fins": fins}
        if args.eps_sweep:
            axis, vel, thrust, dur = setups["yaw2"]
            length, munk = af.hull.length_m, (af.a11[1] - af.a11[0]) / af.air.density_kg_m3
            for frac in (0.70, 0.80, ln["eps_station_m"] / length, 0.88, 0.92, 0.96, 1.0):
                c = ex.lta_coefficients(af, "li-nahon", frac * length)
                m = fly(af, dict(all_eq, hull=c), vel, thrust, dur, axis)
                print(f"DIAG fins {ratio:.2f} yaw2 eps_v {frac:.3f} L  Munk moment kept "
                      f"{1 - c['mi'] / munk:.2f}  {fmt(m)}")
            continue
        variants = [
            ("flight6dof as written", {}),
            ("  + plugin repeats added-mass Coriolis", {"coriolis2": True}),
            ("  + plugin axial drag", {"axial": axial}),
            ("  + hull crossflow at one point, not strips", {"hull": eq}),
            ("  + fins by LiftDrag", {"fins": fins}),
            ("all four = emulated Gazebo 'equivalent'", all_eq),
            ("  equivalent + Munk reduction (moment_inviscid)",
             dict(all_eq, hull=dict(eq, mi=ln["mi"]))),
            ("  equivalent + nose lift (force_inviscid)",
             dict(all_eq, hull=dict(eq, fi=ln["fi"]))),
            ("  equivalent, viscous terms -> afterbody only",
             dict(all_eq, hull=dict(zero, fv=ln["fv"], mv=ln["mv"], eps_v=ln["eps_v"]))),
            ("all = emulated Gazebo 'li-nahon'", dict(all_eq, hull=ln)),
        ]
        for cid in args.cases:
            axis, vel, thrust, dur = setups[cid]
            print(f"DIAG fins {ratio:.2f} {cid}")
            for label, opt in variants:
                print(f"DIAG   {label:50s} {fmt(fly(af, opt, vel, thrust, dur, axis))}")
            if args.gz_csv:
                for hm in ("equivalent", "li-nahon"):
                    p = os.path.join(args.gz_csv, f"fins{int(round(ratio * 100)):03d}_{hm}_{cid}.csv")
                    if os.path.exists(p):
                        print(f"DIAG   {'Gazebo ' + repr(hm):50s} {fmt(gz_metrics(p, axis))}")


if __name__ == "__main__":
    main()
