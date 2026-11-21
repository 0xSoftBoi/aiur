"""Regenerate the STRATO figures in docs/strato/img from the models.

    python tools/strato_plots.py

Needs matplotlib (the models themselves do not).  Colours are the first
slots of the validated categorical palette, assigned in fixed order; one
y-axis per chart; two or more series always get a legend.
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from aiur.strato import campaign, trades  # noqa: E402
from aiur.strato.ascent import config_from_design, simulate  # noqa: E402
from aiur.strato.cost import unit_cost  # noqa: E402
from aiur.strato.flight6dof import Airframe, handling_report, station_keep  # noqa: E402
from aiur.strato.sizing import ladder  # noqa: E402

OUT = os.path.join(REPO, "docs", "strato", "img")
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "lines.linewidth": 2.0, "legend.frameon": False, "figure.dpi": 140,
})


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name))
    plt.close(fig)
    print("wrote", name)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    pts = ladder()

    # 1. ascent profiles
    fig, ax = plt.subplots(figsize=(8, 4.2))
    runs = {}
    for i, key in enumerate(("S1-touch/tandem", "S1-touch/hull", "S2-dayloiter/hull")):
        res = simulate(config_from_design(pts[key]), record_every_s=60)
        runs[key] = res
        ax.plot([r["t_s"] / 60 for r in res.series], [r["alt_m"] / 1000 for r in res.series],
                color=SERIES[i], label=key)
    ax.axhspan(9, 13, color=GRID, alpha=0.6, lw=0)
    ax.text(2, 11, "jet stream", color=MUTED, va="center", fontsize=9)
    ax.set_xlabel("minutes after launch")
    ax.set_ylabel("altitude, km")
    ax.set_title("Launch to landing: one hour at float, summer median wind")
    ax.legend(loc="lower center", ncol=3)
    save(fig, "ascent-profiles.png")

    # 2. ground track of the S2 flight
    res = runs["S2-dayloiter/hull"]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    phases = [("ASCENT", "climb"), ("FLOAT_ENTRY", "float entry"),
              ("STATION_KEEP", "powered at float"), ("DESCENT", "parachute")]
    for i, (ph, label) in enumerate(phases):
        rows = [r for r in res.series if r["phase"] == ph]
        ax.plot([r["east_m"] / 1000 for r in rows], [r["north_m"] / 1000 for r in rows],
                color=SERIES[i], label=label)
    ax.plot([0], [0], marker="o", color=INK, ms=7, ls="none")
    ax.annotate("launch", (0, 0), textcoords="offset points", xytext=(6, 8), color=MUTED)
    ax.set_xlabel("east of launch, km")
    ax.set_ylabel("north of launch, km")
    ax.set_title("S2 ground track: the jet carries it east, the float-level easterly brings it back")
    ax.legend(loc="best", ncol=2)
    ax.set_aspect("equal", adjustable="datalim")
    save(fig, "ground-track-s2.png")

    # 3. altitude trade
    alt = trades.altitude_trade()
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    xs = [int(k.split()[0]) for k in alt]
    axes[0].bar(xs, [v["volume_m3"] for v in alt.values()], width=1.3, color=SERIES[0])
    for x, v in zip(xs, alt.values()):
        axes[0].text(x, v["volume_m3"] + 8, f"{v['volume_m3']:.0f}", ha="center", color=MUTED, fontsize=9)
    axes[0].set_xlabel("float altitude, km")
    axes[0].set_ylabel("hull volume, m3")
    axes[0].set_title("Volume to carry 2 kg")
    axes[1].plot(xs, [v["summer_p50_wind"] for v in alt.values()], color=SERIES[0], marker="o",
                 label="summer median")
    axes[1].plot(xs, [v["winter_p50_wind"] for v in alt.values()], color=SERIES[1], marker="o",
                 label="winter median")
    axes[1].axhline(6, color=MUTED, lw=1, ls="--")
    axes[1].text(14.1, 6.5, "S2 sustained airspeed 6 m/s", color=MUTED, fontsize=9)
    axes[1].set_xlabel("float altitude, km")
    axes[1].set_ylabel("wind speed, m/s")
    axes[1].set_title("Wind to beat")
    axes[1].legend(loc="upper right")
    save(fig, "altitude-trade.png")

    # 4. handling vs fin size
    dp = pts["S2-dayloiter/hull"]
    ref = dp.geometry["volume_m3"] ** (2 / 3)
    labels, sat, gust = [], [], []
    for ratio in (0.30, 0.45, 0.60, 0.75):
        rep = handling_report(Airframe.from_design(dp, fin_area_total_m2=ratio * ref), 6.0)
        labels.append(f"{ratio:.2f}")
        sat.append(100 * rep["step90_gimbal_saturated_fraction"])
        gust.append(rep["gust1.5_rms_heading_error_deg"])
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    axes[0].bar(labels, sat, color=SERIES[0], width=0.6)
    for i, v in enumerate(sat):
        axes[0].text(i, v + 1.5, f"{v:.0f} %", ha="center", color=MUTED, fontsize=9)
    axes[0].set_xlabel("total fin area / V^(2/3)")
    axes[0].set_ylabel("gimbal saturated, % of manoeuvre")
    axes[0].set_title("90 degree heading step")
    axes[1].bar(labels, gust, color=SERIES[0], width=0.6)
    for i, v in enumerate(gust):
        axes[1].text(i, v + 0.15, f"{v:.1f}", ha="center", color=MUTED, fontsize=9)
    axes[1].set_xlabel("total fin area / V^(2/3)")
    axes[1].set_ylabel("RMS heading error, deg")
    axes[1].set_title("Heading hold in 1.5 m/s gusts")
    save(fig, "handling-vs-fins.png")

    # 5. Monte Carlo: free lift (small multiples, shared axes)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True, sharex=True)
    for ax, fl in zip(axes, (0.15, 0.45)):
        out = campaign.run("S1-touch/hull", 150, 1, "summer", free_lift=fl)
        ok = [r["landing_range_km"] for r in out["flights"] if r["reached_float"]]
        lost = [r["landing_range_km"] for r in out["flights"] if not r["reached_float"]]
        bins = [i * 12.5 for i in range(18)]
        ax.hist([ok, lost], bins=bins, stacked=True, color=[SERIES[0], SERIES[1]],
                label=["reached float", "range fence before float"], edgecolor=SURFACE, linewidth=1.5)
        ax.set_title(f"free lift {fl:.0%}: {100*out['summary']['reached_float']:.0f} % reach float")
        ax.set_xlabel("landing distance from launch, km")
    axes[0].set_ylabel("flights of 150")
    axes[1].legend(loc="upper right")
    save(fig, "montecarlo-free-lift.png")

    # 6. cost learning curve
    fig, ax = plt.subplots(figsize=(8, 4))
    units = [1, 3, 10, 30, 100, 300, 1000]
    for i, key in enumerate(("S1-touch/tandem", "S1-touch/hull", "S2-dayloiter/hull")):
        ax.plot(units, [unit_cost(pts[key], n)["unit_usd"] for n in units], color=SERIES[i],
                marker="o", label=key)
    ax.set_xscale("log")
    ax.set_ylim(0, None)
    ax.set_xlabel("cumulative units built")
    ax.set_ylabel("unit cost, USD")
    ax.set_title("Unit cost falls to about $950-1,200 by the thousandth vehicle")
    ax.legend(loc="upper right")
    save(fig, "cost-learning.png")

    # 7. station keeping
    af = Airframe.from_design(dp)
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, wind in enumerate((3.0, 5.0, 6.0, 8.0)):
        r = station_keep(af, 6.0, (0.0, -wind, 0.0), (0.0, -1500.0, 0.0))
        ax.plot([x["t"] / 60 for x in r["rows"]], [x["dist_m"] / 1000 for x in r["rows"]],
                color=SERIES[i], label=f"wind {wind:g} m/s")
    ax.set_xlabel("minutes")
    ax.set_ylabel("distance from station, km")
    ax.set_title("6-DoF station-keeping at a 6 m/s airspeed limit, starting 1.5 km downwind")
    ax.legend(loc="upper left")
    save(fig, "station-keeping.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
