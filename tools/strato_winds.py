#!/usr/bin/env python3
"""Wind climatology for the stratospheric airship from real radiosonde data.

Downloads one station's period-of-record file from NOAA NCEI IGRA v2
(Integrated Global Radiosonde Archive), parses the 00Z/12Z soundings and
writes ``aiur/strato/data/winds_<station>.json`` with:

* wind-speed percentiles and vector-mean wind in 1 km bins, 0-30 km, per
  season, per month and for the whole year, with sample counts;
* the design numbers: minimum-wind layer (14-26 km), station-keeping
  availability at 18/20/22 km, horizontal drift during a constant-rate ascent
  to 20 km, and day-to-day persistence of the 20 km wind.

Standard library only.  Re-runnable::

    python tools/strato_winds.py --station UPM00033345 --cache <dir>

The cache directory holds the raw zip; keep it outside the repository.  No
custom request headers are set (urllib's default User-Agent only).

Method (also recorded in each JSON file's ``meta.method``):

* Heights are geopotential metres above mean sea level.  Levels that carry a
  reported height use it.  Pressure levels without one are placed by
  interpolating height linearly in ln(p) between the sounding's own
  height-bearing levels; outside that range the ICAO standard-atmosphere
  height difference from the nearest height-bearing level is used.
* IGRA wind speed is tenths of m/s; -9999 (missing) and -8888 (removed by QA)
  are dropped; levels without both wind speed and direction are dropped.
* Each sounding contributes at most one value per bin: its (u, v) linearly
  interpolated to the bin altitude between the two bracketing wind levels,
  provided those are no more than ``MAX_GAP_M`` apart.  Bin k is the wind at
  k km above sea level.  The surface wind is used for the bin whose altitude
  is within 500 m below the lowest level.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import math
import os
import sys
import urllib.request
import zipfile

SOURCE_URL = ("https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/"
              "access/data-por/{station}-data.txt.zip")

PERCENTILES = (10, 50, 75, 90, 95, 99)
BINS_KM = tuple(range(0, 31))
MAX_GAP_M = 3500.0            # widest gap between wind levels we interpolate across
SEASONS = {"DJF": (12, 1, 2), "MAM": (3, 4, 5), "JJA": (6, 7, 8), "SON": (9, 10, 11)}
THRESHOLDS_M_S = (3, 6, 9, 12, 15)
AVAIL_ALT_KM = (18, 20, 22)
LAYER_LO_KM, LAYER_HI_KM = 14, 26
LAYER_MUST_REACH_KM = 24      # a sounding must cover 14..24 km to enter the layer search
ASCENT_TOP_M = 20_000.0
ASCENT_RATE_M_S = 3.9
PERSIST_LAGS_DAYS = (1, 2, 3)
PERSIST_THRESHOLDS = (6, 9)

MISSING = (-9999, -8888)


# --- standard atmosphere (only used to place levels that report no height) ---

def _isa_altitude_m(p_pa: float) -> float:
    """ICAO standard-atmosphere geopotential altitude for a pressure."""

    g, r = 9.80665, 287.05287
    if p_pa >= 22632.06:                                   # troposphere
        return 44330.77 * (1.0 - (p_pa / 101325.0) ** 0.190263)
    if p_pa >= 5474.889:                                   # isothermal, 11-20 km
        return 11000.0 + (r * 216.65 / g) * math.log(22632.06 / p_pa)
    if p_pa >= 868.0187:                                   # +1 K/km, 20-32 km
        return 20000.0 + 216.65 / 0.001 * ((5474.889 / p_pa) ** (r * 0.001 / g) - 1.0)
    return 32000.0 + 228.65 / 0.0028 * ((868.0187 / p_pa) ** (r * 0.0028 / g) - 1.0)


# --- download ----------------------------------------------------------------

def fetch(station: str, cache: str) -> str:
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, f"{station}-data.txt.zip")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    url = SOURCE_URL.format(station=station)
    print(f"downloading {url}", file=sys.stderr)
    tmp = path + ".part"
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    os.replace(tmp, path)
    return path


# --- parsing -----------------------------------------------------------------

def _int(field: str) -> int:
    try:
        return int(field)
    except ValueError:
        return -9999


def _levels_to_profile(rows):
    """rows: (p_pa, gph_m, wdir, wspd_tenths) -> sorted [(z_m, u, v)], toward-vector.

    u is the eastward and v the northward component of the air motion.
    """

    anchors = sorted((math.log(p), z) for p, z, _, _ in rows
                     if p not in MISSING and p > 0 and z not in MISSING)
    # drop anchors that are not monotonic (height must fall as ln p rises)
    clean = []
    for lp, z in anchors:
        if clean and (lp <= clean[-1][0] or z >= clean[-1][1]):
            continue
        clean.append((lp, z))
    anchors = clean
    out = []
    for p, z, wdir, wspd in rows:
        if wdir in MISSING or wspd in MISSING or wspd < 0 or not 0 <= wdir <= 360:
            continue
        if z in MISSING:
            if p in MISSING or p <= 0 or not anchors:
                continue
            lp = math.log(p)
            if lp >= anchors[-1][0]:                       # below lowest anchor
                ref = anchors[-1]
                z = ref[1] + _isa_altitude_m(p) - _isa_altitude_m(math.exp(ref[0]))
            elif lp <= anchors[0][0]:                      # above highest anchor
                ref = anchors[0]
                z = ref[1] + _isa_altitude_m(p) - _isa_altitude_m(math.exp(ref[0]))
            else:
                lo, hi = 0, len(anchors) - 1
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if anchors[mid][0] <= lp:
                        lo = mid
                    else:
                        hi = mid
                (l0, z0), (l1, z1) = anchors[lo], anchors[hi]
                z = z0 + (z1 - z0) * (lp - l0) / (l1 - l0)
        if not -500.0 <= z <= 45_000.0:
            continue
        spd = wspd / 10.0
        if spd > 150.0:
            continue
        rad = math.radians(wdir)
        out.append((float(z), -spd * math.sin(rad), -spd * math.cos(rad)))
    out.sort()
    dedup = []
    for lvl in out:
        if dedup and lvl[0] - dedup[-1][0] < 1.0:
            continue
        dedup.append(lvl)
    return dedup


def read_soundings(zip_path: str, start_year: int, end_year: int):
    """Yield (date, hour, profile) for 00Z/12Z soundings (23Z/11Z count as the
    following 00Z/12Z when that slot is otherwise empty)."""

    seen = set()
    stats = {"headers": 0, "selected": 0, "with_wind": 0}
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        if len(names) != 1:
            raise SystemExit(f"unexpected archive contents: {zf.namelist()!r}")
        with zf.open(names[0]) as raw:
            fh = io.TextIOWrapper(raw, encoding="ascii", errors="replace")
            line = fh.readline()
            while line:
                if not line.startswith("#"):
                    line = fh.readline()
                    continue
                stats["headers"] += 1
                year, month, day, hour = (_int(line[13:17]), _int(line[18:20]),
                                          _int(line[21:23]), _int(line[24:26]))
                numlev = _int(line[32:36])
                want = start_year - 1 <= year <= end_year and hour in (0, 12, 11, 23)
                slot = None
                if want:
                    try:
                        date = _dt.date(year, month, day)
                    except ValueError:
                        want = False
                if want:
                    if hour == 23:
                        date, hour = date + _dt.timedelta(days=1), 0
                    elif hour == 11:
                        hour = 12
                    slot = (date, hour)
                    want = (start_year <= date.year <= end_year) and slot not in seen
                rows = []
                for _ in range(max(numlev, 0)):
                    rec = fh.readline()
                    if not rec or rec.startswith("#"):
                        line = rec
                        break
                    if want:
                        rows.append((_int(rec[9:15]), _int(rec[16:21]),
                                     _int(rec[40:45]), _int(rec[46:51])))
                else:
                    line = fh.readline()
                if not want:
                    continue
                stats["selected"] += 1
                profile = _levels_to_profile(rows)
                if len(profile) < 2:
                    continue
                seen.add(slot)
                stats["with_wind"] += 1
                yield slot[0], slot[1], profile
    read_soundings.last_stats = stats


def station_position(zip_path: str):
    """Latitude/longitude from the last header in the file (degrees)."""

    lat = lon = None
    with zipfile.ZipFile(zip_path) as zf:
        name = [n for n in zf.namelist() if n.endswith(".txt")][0]
        with zf.open(name) as raw:
            for bline in raw:
                if bline[:1] == b"#":
                    text = bline.decode("ascii", "replace")
                    la, lo = _int(text[55:62]), _int(text[63:71])
                    if la not in MISSING and lo not in MISSING:
                        lat, lon = la / 1e4, lo / 1e4
    return lat, lon


# --- per-sounding reductions -------------------------------------------------

def interp_bins(profile):
    """Wind (u, v) at each integer-km altitude, or None."""

    out = [None] * len(BINS_KM)
    j = 0
    n = len(profile)
    z_low = profile[0][0]
    for i, km in enumerate(BINS_KM):
        z = km * 1000.0
        if z < z_low:
            if z_low - z <= 500.0:
                out[i] = (profile[0][1], profile[0][2])
            continue
        while j + 1 < n and profile[j + 1][0] <= z:
            j += 1
        if j + 1 >= n:
            if profile[j][0] == z:
                out[i] = (profile[j][1], profile[j][2])
            break
        z0, u0, v0 = profile[j]
        z1, u1, v1 = profile[j + 1]
        if z1 - z0 > MAX_GAP_M:
            continue
        f = (z - z0) / (z1 - z0)
        out[i] = (u0 + f * (u1 - u0), v0 + f * (v1 - v0))
    return out


def ascent_drift(profile):
    """Horizontal displacement (east_km, north_km) of a balloon rising at a
    constant rate from the lowest level to ASCENT_TOP_M, or None."""

    if profile[0][0] > 1500.0 or profile[-1][0] < ASCENT_TOP_M:
        return None
    su = sv = 0.0
    for (z0, u0, v0), (z1, u1, v1) in zip(profile, profile[1:]):
        if z0 >= ASCENT_TOP_M:
            break
        if z1 - z0 > MAX_GAP_M:
            return None
        if z1 > ASCENT_TOP_M:
            f = (ASCENT_TOP_M - z0) / (z1 - z0)
            u1, v1, z1 = u0 + f * (u1 - u0), v0 + f * (v1 - v0), ASCENT_TOP_M
        dz = z1 - z0
        su += 0.5 * (u0 + u1) * dz
        sv += 0.5 * (v0 + v1) * dz
    return su / ASCENT_RATE_M_S / 1000.0, sv / ASCENT_RATE_M_S / 1000.0


# --- statistics --------------------------------------------------------------

def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q / 100.0
    lo = int(math.floor(k))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def r1(x):
    return None if x is None else round(x, 1)


def bearing_from(u, v):
    """Meteorological direction the wind blows FROM, degrees."""
    return math.degrees(math.atan2(-u, -v)) % 360.0


def bearing_toward(u, v):
    return math.degrees(math.atan2(u, v)) % 360.0


def corr(pairs):
    n = len(pairs)
    if n < 30:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in pairs) / math.sqrt(sxx * syy)


def bin_table(records):
    """records: list of per-sounding bin lists -> table dict."""

    n, p, vs, vd, ms = [], [], [], [], []
    for i in range(len(BINS_KM)):
        vals = [r[i] for r in records if r[i] is not None]
        n.append(len(vals))
        if not vals:
            p.append(None), vs.append(None), vd.append(None), ms.append(None)
            continue
        spd = sorted(math.hypot(u, v) for u, v in vals)
        mu = sum(u for u, _ in vals) / len(vals)
        mv = sum(v for _, v in vals) / len(vals)
        p.append([r1(pct(spd, q)) for q in PERCENTILES])
        ms.append(r1(sum(spd) / len(spd)))
        vs.append(r1(math.hypot(mu, mv)))
        vd.append(round(bearing_from(mu, mv)))
    return {"n": n, "speed_pct": p, "mean_speed": ms,
            "vmean_speed": vs, "vmean_from_deg": vd}


def design_table(recs, drifts):
    """recs: per-sounding bin lists; drifts: list of (east_km, north_km)."""

    out = {}
    # (a) minimum-wind layer -------------------------------------------------
    lo, hi = LAYER_LO_KM, LAYER_HI_KM
    best = None
    for km in range(lo, hi + 1):
        spd = sorted(math.hypot(*r[km]) for r in recs if r[km] is not None)
        if len(spd) < 30:
            continue
        p50 = pct(spd, 50)
        if best is None or p50 < best[1]:
            best = (km, p50, pct(spd, 90), len(spd))
    alts, mins = [], []
    for r in recs:
        if any(r[km] is None for km in range(lo, LAYER_MUST_REACH_KM + 1)):
            continue
        s, km = min((math.hypot(*r[km]), km) for km in range(lo, hi + 1)
                    if r[km] is not None)
        alts.append(km)
        mins.append(s)
    alts.sort(), mins.sort()
    out["min_wind_layer"] = {
        "climatological": None if best is None else {
            "alt_km": best[0], "p50": r1(best[1]), "p90": r1(best[2]), "n": best[3]},
        "per_sounding": {
            "n": len(mins), "alt_km_p25": pct(alts, 25), "alt_km_p50": pct(alts, 50),
            "alt_km_p75": pct(alts, 75), "min_speed_p50": r1(pct(mins, 50)),
            "min_speed_p90": r1(pct(mins, 90))},
    }
    # (b) availability -------------------------------------------------------
    avail = {}
    for km in AVAIL_ALT_KM:
        spd = [math.hypot(*r[km]) for r in recs if r[km] is not None]
        avail[str(km)] = {"n": len(spd), "frac_below": [
            round(sum(s < t for s in spd) / len(spd), 3) if spd else None
            for t in THRESHOLDS_M_S]}
    best_spd = [min(math.hypot(*r[km]) for km in range(18, 23))
                for r in recs if all(r[km] is not None for km in range(18, 23))]
    avail["best_of_18_22"] = {"n": len(best_spd), "frac_below": [
        round(sum(s < t for s in best_spd) / len(best_spd), 3) if best_spd else None
        for t in THRESHOLDS_M_S]}
    out["availability"] = avail
    # (c) ascent drift -------------------------------------------------------
    dist = sorted(math.hypot(e, n) for e, n in drifts)
    if dist:
        me = sum(e for e, _ in drifts) / len(drifts)
        mn = sum(n for _, n in drifts) / len(drifts)
        mb = bearing_toward(me, mn)
        within = sum(1 for e, n in drifts
                     if abs((bearing_toward(e, n) - mb + 180) % 360 - 180) <= 45)
        octants = [0] * 8
        for e, n in drifts:
            octants[int(((bearing_toward(e, n) + 22.5) % 360) // 45)] += 1
        out["ascent_drift"] = {
            "n": len(dist),
            "dist_km": {f"p{q}": r1(pct(dist, q)) for q in (10, 50, 75, 90, 95, 99)},
            "dist_km_max": r1(dist[-1]),
            "frac_over_km": {str(k): round(sum(d > k for d in dist) / len(dist), 3)
                             for k in (50, 100, 150, 200)},
            "vmean_dist_km": r1(math.hypot(me, mn)),
            "vmean_bearing_toward_deg": round(mb),
            "frac_within_45deg_of_vmean": round(within / len(drifts), 3),
            "bearing_toward_octant_frac_N_NE_E_SE_S_SW_W_NW": [
                round(c / len(drifts), 3) for c in octants],
        }
    else:
        out["ascent_drift"] = {"n": 0}
    return out


def persistence(series, months):
    """series: {slot_index: (u, v)} with two slots per day -> lag statistics.

    Anomalies are taken from the calendar-month mean so the seasonal cycle
    does not masquerade as persistence."""

    by_month = {}
    for slot, (u, v) in series.items():
        by_month.setdefault(months[slot], []).append((u, v, math.hypot(u, v)))
    clim = {m: tuple(sum(x[i] for x in vals) / len(vals) for i in range(3))
            for m, vals in by_month.items()}
    out = {}
    groups = dict(SEASONS)
    groups["ALL"] = tuple(range(1, 13))
    for name, mset in groups.items():
        res = {"lag_days": list(PERSIST_LAGS_DAYS), "n_pairs": [], "r_u": [], "r_v": [],
               "r_speed": [], "rms_vector_change_m_s": []}
        cond = {str(t): {"base": None, "p_still_below": []} for t in PERSIST_THRESHOLDS}
        cur = [math.hypot(*series[s]) for s in series if months[s] in mset]
        for t in PERSIST_THRESHOLDS:
            cond[str(t)]["base"] = (round(sum(x < t for x in cur) / len(cur), 3)
                                    if cur else None)
        for lag in PERSIST_LAGS_DAYS:
            pu, pv, ps, dv = [], [], [], []
            hits = {t: [0, 0] for t in PERSIST_THRESHOLDS}
            for s, (u0, v0) in series.items():
                if months[s] not in mset:
                    continue
                nxt = series.get(s + 2 * lag)
                if nxt is None:
                    continue
                u1, v1 = nxt
                c0, c1 = clim[months[s]], clim[months[s + 2 * lag]]
                s0, s1 = math.hypot(u0, v0), math.hypot(u1, v1)
                pu.append((u0 - c0[0], u1 - c1[0]))
                pv.append((v0 - c0[1], v1 - c1[1]))
                ps.append((s0 - c0[2], s1 - c1[2]))
                dv.append((u1 - u0) ** 2 + (v1 - v0) ** 2)
                for t in PERSIST_THRESHOLDS:
                    if s0 < t:
                        hits[t][0] += 1
                        hits[t][1] += s1 < t
            res["n_pairs"].append(len(pu))
            for key, pairs in (("r_u", pu), ("r_v", pv), ("r_speed", ps)):
                c = corr(pairs)
                res[key].append(None if c is None else round(c, 2))
            res["rms_vector_change_m_s"].append(
                r1(math.sqrt(sum(dv) / len(dv))) if dv else None)
            for t in PERSIST_THRESHOLDS:
                a, b = hits[t]
                cond[str(t)]["p_still_below"].append(round(b / a, 3) if a >= 20 else None)
        res["below_threshold_m_s"] = cond
        out[name] = res
    return out


# --- driver ------------------------------------------------------------------

def build(station: str, zip_path: str, start_year: int, end_year: int) -> dict:
    recs_by_month = {m: [] for m in range(1, 13)}
    drift_by_month = {m: [] for m in range(1, 13)}
    series, slot_month = {}, {}
    first = last = None
    per_year = {}
    top_alt = []
    epoch = _dt.date(2000, 1, 1)
    for date, hour, profile in read_soundings(zip_path, start_year, end_year):
        bins = interp_bins(profile)
        if all(b is None for b in bins):
            continue
        recs_by_month[date.month].append(bins)
        d = ascent_drift(profile)
        if d is not None:
            drift_by_month[date.month].append(d)
        if bins[20] is not None:
            slot = (date - epoch).days * 2 + (1 if hour == 12 else 0)
            series[slot] = bins[20]
            slot_month[slot] = date.month
        first = date if first is None or date < first else first
        last = date if last is None or date > last else last
        per_year[date.year] = per_year.get(date.year, 0) + 1
        top_alt.append(profile[-1][0])
    # months for lagged slots that may not exist as soundings
    for s in list(series):
        for lag in PERSIST_LAGS_DAYS:
            t = s + 2 * lag
            if t not in slot_month:
                slot_month[t] = (epoch + _dt.timedelta(days=t // 2)).month
    total = sum(len(v) for v in recs_by_month.values())
    if total == 0:
        raise SystemExit("no usable soundings in the requested period")
    top_alt.sort()
    lat, lon = station_position(zip_path)

    def gather(months):
        recs, drifts = [], []
        for m in months:
            recs.extend(recs_by_month[m])
            drifts.extend(drift_by_month[m])
        return recs, drifts

    seasons, design = {}, {}
    groups = dict(SEASONS)
    groups["ALL"] = tuple(range(1, 13))
    for name, months in groups.items():
        recs, drifts = gather(months)
        seasons[name] = bin_table(recs)
        seasons[name]["soundings"] = len(recs)
        design[name] = design_table(recs, drifts)
    months_out, design_month = {}, {}
    for m in range(1, 13):
        recs, drifts = gather((m,))
        months_out[f"{m:02d}"] = bin_table(recs)
        months_out[f"{m:02d}"]["soundings"] = len(recs)
        dm = design_table(recs, drifts)
        design_month[f"{m:02d}"] = {
            "availability_20km_frac_below": dm["availability"]["20"]["frac_below"],
            "availability_best_of_18_22_frac_below":
                dm["availability"]["best_of_18_22"]["frac_below"],
            "ascent_drift_n": dm["ascent_drift"].get("n"),
            "ascent_drift_km_p50_p90_p95": [
                dm["ascent_drift"].get("dist_km", {}).get(k) for k in ("p50", "p90", "p95")],
        }
    pers = persistence(series, slot_month)
    for name in design:
        design[name]["persistence_20km"] = pers[name]

    stats = getattr(read_soundings, "last_stats", {})
    return {
        "meta": {
            "station": station,
            "lat_deg": lat, "lon_deg": lon,
            "source": "NOAA NCEI Integrated Global Radiosonde Archive (IGRA) v2",
            "source_url": SOURCE_URL.format(station=station),
            "date_first": first.isoformat(), "date_last": last.isoformat(),
            "hours_utc": [0, 12],
            "soundings_used": total,
            "soundings_per_year": {str(y): per_year[y] for y in sorted(per_year)},
            "soundings_reaching_km": {str(k): sum(t >= k * 1000 for t in top_alt)
                                      for k in (16, 18, 20, 22, 24, 26, 28, 30)},
            "top_altitude_km_p10_p50_p90": [r1(pct(top_alt, q) / 1000) for q in (10, 50, 90)],
            "headers_in_file": stats.get("headers"),
            "units": "speeds m/s; directions degrees the wind blows FROM; "
                     "drift bearings degrees TOWARD; altitudes km above mean sea level",
            "method": [
                "00Z and 12Z soundings only (11Z/23Z labels count as the 12Z/00Z slot "
                "when it is otherwise empty); one value per sounding per bin.",
                "Height: reported geopotential height where present; otherwise "
                "interpolated in ln(p) between the sounding's own height-bearing "
                "levels, or offset from the nearest one by the ICAO standard-atmosphere "
                "height difference.",
                "Wind: IGRA tenths of m/s -> m/s; -9999 and -8888 dropped; levels "
                "without both speed and direction dropped.",
                f"Bin k = wind vector linearly interpolated to k km between bracketing "
                f"wind levels no more than {MAX_GAP_M:.0f} m apart; the surface wind "
                "fills the bin within 500 m below the lowest level.",
                "speed_pct columns are percentiles " + ",".join(map(str, PERCENTILES))
                + " of scalar speed; vmean_* is the vector-mean wind.",
                f"min_wind_layer searched over {LAYER_LO_KM}-{LAYER_HI_KM} km; the "
                f"per-sounding search needs every bin {LAYER_LO_KM}-{LAYER_MUST_REACH_KM} km.",
                f"availability frac_below thresholds: {list(THRESHOLDS_M_S)} m/s.",
                f"ascent_drift: trapezoidal integral of the sounding's own wind from its "
                f"lowest level to {ASCENT_TOP_M / 1000:.0f} km at a constant "
                f"{ASCENT_RATE_M_S} m/s climb; soundings that stop short are excluded.",
                "persistence_20km: correlation of anomalies from the calendar-month mean "
                "between soundings exactly N days apart (same hour); p_still_below = "
                "P(speed < T at day+N | speed < T today).",
                "Caveat: bins above the typical burst height are survivor-biased "
                "(see soundings_reaching_km and per-bin n).",
            ],
        },
        "altitude_km": list(BINS_KM),
        "percentiles": list(PERCENTILES),
        "seasons": seasons,
        "months": months_out,
        "design": design,
        "design_by_month": design_month,
    }


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.join(os.path.dirname(here), "aiur", "strato", "data")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--station", required=True, help="IGRA v2 id, e.g. UPM00033345")
    ap.add_argument("--cache", required=True,
                    help="directory for the downloaded zip (keep it outside the repo)")
    ap.add_argument("--out-dir", default=default_out)
    ap.add_argument("--start-year", type=int, default=2005)
    ap.add_argument("--end-year", type=int, default=9999)
    args = ap.parse_args(argv)
    if not args.station.isalnum():
        raise SystemExit("station id must be alphanumeric")
    zip_path = fetch(args.station, args.cache)
    data = build(args.station, zip_path, args.start_year, args.end_year)
    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir, f"winds_{args.station}.json")
    with open(out, "w", encoding="ascii") as fh:
        json.dump(data, fh, separators=(",", ":"))
        fh.write("\n")
    m = data["meta"]
    print(f"{args.station}: {m['soundings_used']} soundings "
          f"{m['date_first']}..{m['date_last']} -> {out} "
          f"({os.path.getsize(out) / 1000:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
