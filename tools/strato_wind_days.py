"""Export a sample of real individual soundings for the Monte Carlo.

`strato_winds.py` reduces a station's record to percentile tables.  A stack
of per-level 90th percentiles is not a day that ever happened, and it
overstates ascent drift.  This writes a deterministic sample of *actual*
soundings - wind at each kilometre from the surface to 24 km - so
`aiur.strato.campaign --real-days` can fly real days instead.

    python tools/strato_wind_days.py --station GMM00010393 --cache <dir>

Only soundings with wind at every level from 0 to 24 km are kept, which
biases the sample slightly toward days when the balloon survived (see
docs/strato/winds.md on survivorship).  Stdlib only; reuses the parser in
strato_winds.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import strato_winds as sw  # noqa: E402

SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
          6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
TOP_KM = 24


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--station", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--per-season", type=int, default=200)
    ap.add_argument("--start-year", type=int, default=2005)
    ap.add_argument("--out-dir", default=os.path.join(HERE, "..", "aiur", "strato", "data"))
    a = ap.parse_args(argv)
    path = sw.fetch(a.station, a.cache)
    idx = [i for i, km in enumerate(sw.BINS_KM) if km <= TOP_KM]
    by_season: dict = {s: [] for s in ("DJF", "MAM", "JJA", "SON")}
    total = 0
    for date, hour, profile in sw.read_soundings(path, a.start_year, 9999):
        total += 1
        bins = sw.interp_bins(profile)
        if any(bins[i] is None for i in idx):
            continue
        d = date.isoformat()
        month = date.month
        by_season[SEASON[month]].append({
            "date": d, "hour": hour,
            "u": [round(bins[i][0] * 10) for i in idx],
            "v": [round(bins[i][1] * 10) for i in idx]})
    days = []
    counts = {}
    for season, rows in by_season.items():
        counts[season] = len(rows)
        step = max(1, len(rows) // a.per_season)
        for r in rows[::step][:a.per_season]:
            r["season"] = season
            days.append(r)
    out = {"meta": {"station": a.station, "source": "NOAA NCEI IGRA v2",
                    "units": "tenths of m/s; u eastward, v northward (wind blowing toward)",
                    "soundings_read": total, "complete_to_24km_by_season": counts,
                    "sample_per_season": a.per_season,
                    "sampling": "every k-th complete sounding in date order"},
           "altitude_km": [sw.BINS_KM[i] for i in idx], "days": days}
    dest = os.path.join(a.out_dir, f"wind_days_{a.station}.json")
    with open(dest, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"{dest}: {len(days)} soundings, {os.path.getsize(dest)//1024} kB; complete by season {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
