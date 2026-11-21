"""Flat patterns for the film hull: gores, closures, fins, cut list.

``sizing.py`` says how big the hull is.  This module turns that into things a
person can mark out with a tape measure, cut and seal.

Method
------
*Gore development* [physics].  The hull is a body of revolution with meridian
``r(x)`` from ``hull.profile``.  Cut into ``N`` identical gores along
meridians, each gore is developed onto the flat by keeping the meridional arc
length ``s`` along its centreline and giving it the half-width

    h(s) = pi r(s) / N

so that the N gores together carry the full circumference at every station.
``s`` is integrated numerically on a grid clustered at both ends (the nose is
blunt, dr/dx is infinite there).  N times the flat gore area equals the area
of the surface of revolution identically; the check against
``Hull.surface_area_m2`` is therefore a check of the numerics only.

*Why the built hull is not the drawn hull* [physics].  A flat gore is a
developable surface; a body of revolution is not.  An inextensible film gore
can only bend one way, so the exact isometric shape it takes is a strip that
curves along the meridian and is straight across: the cross-section is a
regular N-gon whose *perimeter* is the design circumference.  Its area is
``(pi/N)/tan(pi/N)`` of the circle's, so the hull encloses less gas than
sized.  The film area is unchanged (it is what was cut).  Real 20 um LLDPE
stretches about 1 % at the 20 Pa hoop load, so pressure rounds the polygon
part of the way out; the polygon is the lower bound on volume and the smooth
hull the upper bound.  ``lobing_table`` reports the bound for several N and
the width scale that would buy the volume back.

*Closures* [engineering judgement].  Gores cannot run to a point: N seam
allowances pile up and nothing can be sealed.  Each gore is cut off square
where its net width falls to ``tip_width_m`` (60 mm).  The nose is closed by a
flat disc ("nose cap") whose radius is the meridional arc from the apex to the
cut plus an overlap; laid on the blunt nose its misfit strain is about
(s/rho)^2/6, reported.  The profile ends at a finite tail radius
(``hull.TAIL_RADIUS_FRAC``), closed by a flat tail disc with a collar.

*Roll nesting* [engineering judgement].  Gores are laid lengthwise on the
roll, neighbours staggered along the roll and/or turned head-to-tail; the
lateral pitch is the smallest that keeps cut edges ``cut_gap_m`` apart.  The
search is over pieces abreast, stagger, orientation, and whether pieces run
in continuous lanes or separate rows (see ``nest``).  Pieces stay parallel
to the roll edge.  A gore wider than the
roll is split along its centreline into two half-gores (one extra straight
seam each); the smallest N that avoids the split is reported.

*Fins* [estimate].  Four fins at 45 deg.  Planform: straight trailing edge
normal to the hull axis, tip parallel to the axis, all taper in the leading
edge, taper ratio 0.55, exposed aspect ratio (span / mean chord) 1.0, root cut
to the hull meridian, area centroid at 0.86 L (the tail arm
``sizing._hull_stability`` assumes).  Two air-beam spars on the 25 % and 75 %
chord lines.  Spar diameter is *pressure*-limited, not fabric-limited: the
wrinkling moment of a tube is pi p r^3 / 2 (``sizing.air_beam``), the beam is
only at its 3 kPa ground gauge when the dynamic pressure is highest (launch
and first climb), and ``sizing.sealed_beam_pressure_at_altitude`` capped by
the 10 kPa relief gives the pressure at float.  See ``fin_design``.

Provenance of every number that is not geometry is tagged ``[physics]``,
``[cited]`` or ``[estimate]`` at the point of use, as elsewhere in
``aiur.strato``.

Usage
-----
    python -m aiur.strato.patterns                       # every hull design
    python -m aiur.strato.patterns --design S1-touch/hull --gores 16
    python -m aiur.strato.patterns --roll-width 1.5 --out /tmp/patterns
"""

from __future__ import annotations

import argparse
import bisect
import csv
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import sys

from .atmosphere import G0, isa
from .gas import GASES
from .hull import Hull, profile
from .materials import FILMS
from .sizing import air_beam, ladder, sealed_beam_pressure_at_altitude

# --- constants taken from elsewhere in the project ---------------------------
#: docs/strato/hardware.md "Structure": spar ground gauge and relief setting.
SPAR_GROUND_GAUGE_PA = 3_000.0
SPAR_RELIEF_PA = 10_000.0
#: materials.FILMS["nylon-tpu-70gsm"]: the air-beam fabric.
SPAR_FABRIC_KEY = "nylon-tpu-70gsm"
#: cost.py: "a bar sealer does ~1.2 m/min incl. handling".
SEAL_RATE_M_PER_MIN = 1.2
#: cost.py: film purchased = hull area x 1.18 ("gore waste").
COST_MODEL_FILM_FACTOR = 1.18
#: sizing._hull_stability: fin centre of pressure at 0.86 L.
FIN_STATION_FRAC = 0.86

LOBING_N = (8, 12, 16, 24)
ROLL_WIDTHS_M = (1.5, 2.0, 3.0)


@dataclass(frozen=True)
class Options:
    """Pattern-making choices.  Lengths in metres."""

    n_gores: int = 12                 # hardware.md
    seam_allowance_m: float = 0.015   # each edge, fin seam [task default]
    roll_width_m: float = 2.0         # usable single-ply sheet width
    station_pitch_m: float = 0.5
    patch_pitch_m: float = 1.5        # hardware.md, along the keel line
    tip_width_m: float = 0.060        # net gore width at the cut-off [estimate]
    cap_overlap_m: float = 0.030      # cap/disc overlap onto the gores [estimate]
    cut_gap_m: float = 0.020          # knife room between nested pieces [estimate]
    patch_diameter_m: float = 0.150   # taped load patch [estimate]
    port_diameter_m: float = 0.100    # relief/fill port, minimum [estimate]
    port_area_margin: float = 3.0     # on the orifice area the climb needs [estimate]
    port_station_frac: float = 0.25   # of L: the maximum section
    rip_station_frac: float = 0.30    # of L, crown gore [estimate]
    keel_span_frac: tuple = (0.08, 0.92)  # of L covered by load patches [estimate]
    fin_taper: float = 0.55           # [estimate]
    fin_aspect: float = 1.0           # span / mean chord, exposed [estimate]
    fin_flange_m: float = 0.030       # root flange onto the hull [estimate]
    spar_lap_m: float = 0.020         # welded lap on the spar tube [estimate]
    fin_incidence_deg: float = 15.0   # design incidence in gusts/sway [estimate]
    compensate_lobing: bool = False   # widen gores to recover polygon volume


# --- meridian ----------------------------------------------------------------

class Meridian:
    """Arc-length table of the hull meridian: s <-> (x, r)."""

    def __init__(self, hull: Hull, n: int = 6000):
        self.hull = hull
        length, radius = hull.length_m, hull.radius_m
        xs, rs = [], []
        for i in range(n + 1):
            xi = 0.5 * (1.0 - math.cos(math.pi * i / n))
            # profile() returns 0 at xi >= 1; the hull really ends at the
            # tail radius, so evaluate just inside.
            xi_eval = min(xi, 1.0 - 1e-12)
            xs.append(xi * length)
            rs.append(radius * profile(xi_eval) if i else 0.0)
        ss = [0.0]
        for i in range(1, n + 1):
            ss.append(ss[-1] + math.hypot(xs[i] - xs[i - 1], rs[i] - rs[i - 1]))
        self.x, self.r, self.s = xs, rs, ss
        self.length_s = ss[-1]
        self.tail_radius_m = rs[-1]

    def _interp(self, key: list, val: list, q: float) -> float:
        if q <= key[0]:
            return val[0]
        if q >= key[-1]:
            return val[-1]
        i = bisect.bisect_right(key, q)
        f = (q - key[i - 1]) / (key[i] - key[i - 1])
        return val[i - 1] + f * (val[i] - val[i - 1])

    def r_at_s(self, s: float) -> float:
        return self._interp(self.s, self.r, s)

    def x_at_s(self, s: float) -> float:
        return self._interp(self.s, self.x, s)

    def s_at_x(self, x: float) -> float:
        return self._interp(self.x, self.s, x)

    def drds(self, s: float) -> float:
        e = 1e-3
        a, b = max(0.0, s - e), min(self.length_s, s + e)
        return (self.r_at_s(b) - self.r_at_s(a)) / (b - a)

    def surface_area(self) -> float:
        """Surface of revolution plus the flat tail disc, m2."""

        a = 0.0
        for i in range(1, len(self.s)):
            a += math.pi * (self.r[i] + self.r[i - 1]) * (self.s[i] - self.s[i - 1])
        return a + math.pi * self.tail_radius_m**2

    def volume(self) -> float:
        v = 0.0
        for i in range(1, len(self.x)):
            r0, r1 = self.r[i - 1], self.r[i]
            v += math.pi / 3.0 * (r0 * r0 + r0 * r1 + r1 * r1) * (self.x[i] - self.x[i - 1])
        return v


# --- gore --------------------------------------------------------------------

@dataclass
class Gore:
    n: int
    width_scale: float
    allowance_m: float
    s_nose_cut: float
    s_tail_cut: float
    #: dense samples between the cuts: (s, half-width net, half-width cut)
    samples: list = field(default_factory=list)
    net_area_m2: float = 0.0          # between the cuts, one gore, no allowance
    full_area_m2: float = 0.0         # apex to tail, one gore, no allowance
    cut_area_m2: float = 0.0          # between the cuts incl. allowance
    edge_length_m: float = 0.0        # one seam line, between the cuts
    centre_length_m: float = 0.0
    max_half_width_m: float = 0.0
    max_half_width_cut_m: float = 0.0


def gore_half_width(mer: Meridian, n: int, s: float, scale: float = 1.0) -> float:
    return scale * math.pi * mer.r_at_s(s) / n


def develop_gore(mer: Meridian, opts: Options, width_scale: float = 1.0,
                 step_m: float = 0.01) -> Gore:
    n, a = opts.n_gores, opts.seam_allowance_m
    h = lambda s: gore_half_width(mer, n, s, width_scale)
    s_max = mer.s[max(range(len(mer.r)), key=lambda i: mer.r[i])]

    def cut(lo: float, hi: float) -> float:
        # bisection for 2 h(s) = tip width on a monotonic branch
        target = 0.5 * opts.tip_width_m
        f_lo = h(lo) - target
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if (h(mid) - target) * f_lo > 0.0:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    s_nose = cut(0.0, s_max)
    s_tail = mer.length_s if h(mer.length_s) >= 0.5 * opts.tip_width_m else cut(mer.length_s, s_max)
    g = Gore(n, width_scale, a, s_nose, s_tail)
    count = max(2, int(math.ceil((s_tail - s_nose) / step_m)))
    ds = (s_tail - s_nose) / count
    for i in range(count + 1):
        s = s_nose + i * ds
        hw = h(s)
        slope = width_scale * math.pi / n * mer.drds(s)
        # Offset so the allowance is `a` measured normal to the seam line.
        g.samples.append((s, hw, hw + a * math.hypot(1.0, slope)))
    for (s0, h0, c0), (s1, h1, c1) in zip(g.samples, g.samples[1:]):
        g.net_area_m2 += (h0 + h1) * (s1 - s0)
        g.cut_area_m2 += (c0 + c1) * (s1 - s0)
        g.edge_length_m += math.hypot(s1 - s0, h1 - h0)
    g.centre_length_m = s_tail - s_nose
    for i in range(1, len(mer.s)):
        g.full_area_m2 += width_scale * math.pi / n * (mer.r[i] + mer.r[i - 1]) \
            * (mer.s[i] - mer.s[i - 1])
    g.max_half_width_m = max(p[1] for p in g.samples)
    g.max_half_width_cut_m = max(p[2] for p in g.samples)
    return g


def station_table(mer: Meridian, gore: Gore, opts: Options, tol_m: float = 0.002) -> list[dict]:
    """Rows for marking out by hand.

    A row every ``station_pitch_m`` of arc from the apex datum, the two cut
    stations, and 0.1 m infill wherever a straight line between neighbouring
    0.5 m stations would miss the true edge by more than ``tol_m``.
    """

    def row(s: float, kind: str) -> dict:
        hw = gore_half_width(mer, gore.n, s, gore.width_scale)
        slope = gore.width_scale * math.pi / gore.n * mer.drds(s)
        return {"kind": kind, "s_m": s, "x_m": mer.x_at_s(s), "radius_m": mer.r_at_s(s),
                "half_width_m": hw,
                "half_width_with_allowance_m": hw + gore.allowance_m * math.hypot(1.0, slope)}

    pitch = opts.station_pitch_m
    marks = [gore.s_nose_cut]
    k = math.floor(gore.s_nose_cut / pitch) + 1
    while k * pitch < gore.s_tail_cut - 1e-9:
        marks.append(k * pitch)
        k += 1
    marks.append(gore.s_tail_cut)
    rows = []
    for a, b in zip(marks, marks[1:]):
        kind = "nose_cut" if a == marks[0] else "station"
        rows.append(row(a, kind))
        ha = gore_half_width(mer, gore.n, a, gore.width_scale)
        hb = gore_half_width(mer, gore.n, b, gore.width_scale)
        worst = 0.0
        for j in range(1, 20):
            s = a + (b - a) * j / 20
            lin = ha + (hb - ha) * j / 20
            worst = max(worst, abs(gore_half_width(mer, gore.n, s, gore.width_scale) - lin))
        if worst > tol_m:
            s = math.floor(a / 0.1 + 1e-9) * 0.1 + 0.1
            while s < b - 1e-6:
                rows.append(row(s, "infill"))
                s += 0.1
    rows.append(row(marks[-1], "tail_cut"))
    return rows


# --- lobing ------------------------------------------------------------------

def lobing(mer: Meridian, n: int) -> dict:
    """Polygon (inextensible-film) hull built from N flat gores of design width.

    Each gore centreline keeps arc length s and sits at the apothem
    a(s) = r(s) (pi/N)/tan(pi/N); the seams sit at the circumradius.  This is
    an exact isometric embedding of the flat gore, so film area is unchanged
    and only the enclosed volume and the overall length differ.
    """

    t = math.pi / n
    c = t / math.tan(t)
    vol = length = 0.0
    for i in range(1, len(mer.s)):
        ds = mer.s[i] - mer.s[i - 1]
        if ds <= 0.0:
            continue
        da = c * (mer.r[i] - mer.r[i - 1])
        dx = math.sqrt(max(0.0, ds * ds - da * da))
        r0, r1 = mer.r[i - 1], mer.r[i]
        vol += math.pi * c * (r0 * r0 + r0 * r1 + r1 * r1) / 3.0 * dx
        length += dx
    v_smooth = mer.volume()
    ratio = vol / v_smooth
    scale = (1.0 / ratio) ** 0.5
    r_max = max(mer.r)
    return {
        "n_gores": n,
        "section_area_ratio": c,
        "volume_ratio": ratio,
        "volume_error_pct": 100.0 * (ratio - 1.0),
        "surface_area_error_pct": 0.0,
        "length_error_pct": 100.0 * (length / mer.x[-1] - 1.0),
        "max_flat_depth_mm": 1000.0 * r_max * t * (1.0 / math.sin(t) - 1.0 / math.tan(t)),
        "seam_radius_excess_pct": 100.0 * (t / math.sin(t) - 1.0),
        "width_scale_to_recover_volume": scale,
        "extra_film_to_recover_volume_pct": 100.0 * (scale - 1.0),
        "gore_max_width_m": 2.0 * math.pi * r_max / n,
    }


def lobing_table(mer: Meridian, ns=LOBING_N) -> list[dict]:
    return [lobing(mer, n) for n in ns]


# --- roll nesting ------------------------------------------------------------

def _pitch(lo: list, hi: list, fa: bool, fb: bool, shift: int, gap: float,
           periodic: bool) -> float:
    """Smallest lateral offset of piece/lane b from piece/lane a.

    b is displaced ``shift`` grid steps along the roll.  A flipped piece is
    rotated 180 deg.  ``periodic``: each lane is an endless stream of pieces
    laid end to end; otherwise a and b are single pieces in one row.
    """

    n = len(lo) - 1
    period = n + 1
    best = -1e9
    rng = range(period) if periodic else range(max(0, shift), min(n, n + shift) + 1)
    for i in rng:
        j = (i - shift) % period if periodic else i - shift
        ha = lo[n - i] if fa else hi[i]
        lb = hi[n - j] if fb else lo[j]
        if ha + lb > best:
            best = ha + lb
    return best + gap


def nest(lo: list, hi: list, grid_m: float, count: int, roll_width_m: float,
         gap_m: float, max_abreast: int = 12) -> dict | None:
    """Lay `count` identical pieces lengthwise on a roll.

    ``lo``/``hi`` are the piece's extents left and right of its reference
    line, sampled every ``grid_m`` along its length.  Two layouts are tried:

    * "lanes": pieces end to end in parallel lanes, neighbouring lanes
      staggered and/or turned head-to-tail (stagger costs roll once);
    * "rows": separate rows of m pieces, staggered within the row (stagger
      costs roll every row, but pieces overlap less so more fit abreast).

    Returns the layout needing the least roll, or None if a single piece is
    wider than the roll.
    """

    n = len(lo) - 1
    piece_len = n * grid_m
    if max(lo) + max(hi) > roll_width_m + 1e-9:
        return None
    best = None
    step = max(1, n // 50)
    for periodic in (True, False):
        shifts = range(0, n + 1, step) if periodic else range(-(n // 2), n // 2 + 1, step)
        for alternate in (False, True):
            for shift in shifts:
                p_ab = _pitch(lo, hi, False, alternate, shift, gap_m, periodic)
                p_ba = _pitch(lo, hi, alternate, False, -shift, gap_m, periodic)
                stagger = (min(shift, n + 1 - shift) if periodic else abs(shift)) * grid_m
                for m in range(1, max_abreast + 1):
                    width = max(lo)
                    for k in range(1, m):
                        width += p_ab if k % 2 else p_ba
                    last_flipped = alternate and (m % 2 == 0)
                    width += max(lo) if last_flipped else max(hi)
                    if width > roll_width_m + 1e-9:
                        break
                    rows = math.ceil(count / m)
                    if m == 1:
                        total = rows * (piece_len + gap_m)
                    elif periodic:
                        total = rows * (piece_len + gap_m) + stagger
                    else:
                        total = rows * (piece_len + stagger + gap_m)
                    cand = {"layout": "lanes" if periodic else "rows",
                            "abreast": m, "head_to_tail": alternate and m > 1,
                            "stagger_m": stagger if m > 1 else 0.0,
                            "band_width_m": width, "rows": rows,
                            "roll_length_m": total,
                            "pitch_m": [p_ab, p_ba] if m > 1 else []}
                    key = (round(total, 6), round(width, 6))
                    if best is None or key < best[0]:
                        best = (key, cand)
    return best[1] if best else None


def nest_gores(mer: Meridian, gore: Gore, hull_area_m2: float, roll_width_m: float,
               opts: Options, extra_area_m2: float = 0.0) -> dict:
    """Roll layout for the N gores; splits them lengthwise if they do not fit."""

    grid = 0.02
    count = max(2, int(round(gore.centre_length_m / grid)))
    grid = gore.centre_length_m / count
    cuts = []
    for i in range(count + 1):
        s = gore.s_nose_cut + i * grid
        j = min(len(gore.samples) - 1, int(round((s - gore.s_nose_cut)
                                                  / gore.centre_length_m * (len(gore.samples) - 1))))
        cuts.append(gore.samples[j][2])
    full_width = 2.0 * gore.max_half_width_cut_m
    out = {"roll_width_m": roll_width_m, "gore_cut_width_m": full_width,
           "fits_one_width": full_width <= roll_width_m, "split": False}
    pieces, piece_area = gore.n, gore.cut_area_m2
    layout = nest(cuts, cuts, grid, pieces, roll_width_m, opts.cut_gap_m)
    if layout is None:
        out["split"] = True
        a = gore.allowance_m
        pieces, piece_area = 2 * gore.n, 0.5 * gore.cut_area_m2 + a * gore.centre_length_m
        layout = nest([a] * len(cuts), cuts, grid, pieces, roll_width_m, opts.cut_gap_m)
    # Smallest even N whose whole gore fits this roll.
    n_fit = gore.n
    r_max = max(mer.r)
    while 2.0 * (gore.width_scale * math.pi * r_max / n_fit + gore.allowance_m) > roll_width_m:
        n_fit += 2
    out["min_gores_unsplit"] = n_fit
    if layout is None:
        out.update({"feasible": False, "note": "half-gore still wider than the roll: raise N"})
        return out
    roll_area = layout["roll_length_m"] * roll_width_m
    used = pieces * piece_area + extra_area_m2
    # What other gore counts would buy on this roll (allowance kept, cut
    # stations taken as unchanged: good to a fraction of a percent).
    a = gore.allowance_m
    scan = []
    for n_alt in range(8, 34, 2):
        alt = [(c - a) * gore.n / n_alt + a for c in cuts]
        lay = nest(alt, alt, grid, n_alt, roll_width_m, opts.cut_gap_m)
        if lay:
            scan.append((lay["roll_length_m"] * roll_width_m / hull_area_m2, n_alt, lay["abreast"]))
    if scan:
        f_best, n_best, m_best = min(scan)
        out["best_gore_count_for_roll"] = {"n_gores": n_best, "abreast": m_best,
                                           "film_factor_vs_hull_area": f_best}
    if not out["split"]:
        half = nest([a] * len(cuts), cuts, grid, 2 * gore.n, roll_width_m, opts.cut_gap_m)
        if half and half["roll_length_m"] < layout["roll_length_m"] - 1e-6:
            out["split_alternative"] = {
                "abreast": half["abreast"], "roll_length_m": half["roll_length_m"],
                "film_factor_vs_hull_area": half["roll_length_m"] * roll_width_m / hull_area_m2,
                "extra_seam_m": gore.n * gore.centre_length_m}
    out["waste_fraction_on_band_width"] = 1.0 - used / (layout["roll_length_m"] * layout["band_width_m"])
    out.update({
        "feasible": True, "pieces": pieces, **layout,
        "roll_area_m2": roll_area, "piece_area_m2": used,
        "waste_fraction": 1.0 - used / roll_area,
        "film_factor_vs_hull_area": roll_area / hull_area_m2,
        "cost_model_film_factor": COST_MODEL_FILM_FACTOR,
        "film_factor_difference": roll_area / hull_area_m2 - COST_MODEL_FILM_FACTOR,
    })
    return out


# --- fins --------------------------------------------------------------------

@dataclass
class Fin:
    area_m2: float                 # design exposed area, one fin
    pattern_area_m2: float         # as cut (design area + spar take-up)
    root_chord_m: float
    tip_chord_m: float
    span_m: float                  # tip height above the hull at mid root chord
    le_sweep_deg: float
    x_le_m: float                  # root leading edge station
    x_te_m: float                  # trailing edge station
    x_tip_le_m: float
    y_tip_m: float                 # tip radius from the hull axis
    centroid_x_m: float
    centroid_height_m: float       # of exposed area above the root line
    root_arc_m: float
    perimeter_seal_m: float        # LE + tip + TE
    spars: list = field(default_factory=list)
    spar: dict = field(default_factory=dict)
    skin_chord_takeup: float = 0.0
    mass_kg: dict = field(default_factory=dict)
    clock_deg: tuple = (45.0, 135.0, 225.0, 315.0)
    root_on: str = ""

    def top(self, x: float, hull: Hull) -> float:
        if x >= self.x_tip_le_m:
            return self.y_tip_m
        y0 = hull.radius_at(self.x_le_m)
        f = (x - self.x_le_m) / (self.x_tip_le_m - self.x_le_m)
        return y0 + f * (self.y_tip_m - y0)


def _fin_planform(hull: Hull, area: float, opts: Options) -> Fin:
    length = hull.length_m
    c_mean = math.sqrt(area / opts.fin_aspect)
    c_r = 2.0 * c_mean / (1.0 + opts.fin_taper)
    c_t = opts.fin_taper * c_r
    steps = 400

    def build(x_te: float) -> Fin:
        x_le, x_tl = x_te - c_r, x_te - c_t

        def integrals(y_tip: float) -> tuple[float, float, float]:
            fin = Fin(area, area, c_r, c_t, 0.0, 0.0, x_le, x_te, x_tl, y_tip, 0.0, 0.0, 0.0, 0.0)
            a = mx = my = 0.0
            dx = c_r / steps
            for i in range(steps):
                x = x_le + (i + 0.5) * dx
                hgt = max(0.0, fin.top(x, hull) - hull.radius_at(x))
                a += hgt * dx
                mx += hgt * x * dx
                my += 0.5 * hgt * hgt * dx
            return a, mx, my

        lo, hi = hull.radius_at(x_te), hull.radius_m + 4.0 * c_r
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if integrals(mid)[0] < area:
                lo = mid
            else:
                hi = mid
        y_tip = 0.5 * (lo + hi)
        a, mx, my = integrals(y_tip)
        x_mid = x_te - 0.5 * c_r
        root_arc = 0.0
        dx = c_r / steps
        for i in range(steps):
            x0, x1 = x_le + i * dx, x_le + (i + 1) * dx
            root_arc += math.hypot(dx, hull.radius_at(x1) - hull.radius_at(x0))
        le_len = math.hypot(x_tl - x_le, y_tip - hull.radius_at(x_le))
        te_len = y_tip - hull.radius_at(x_te)
        return Fin(area, a, c_r, c_t, y_tip - hull.radius_at(x_mid),
                   math.degrees(math.atan2(x_tl - x_le, y_tip - hull.radius_at(x_le))),
                   x_le, x_te, x_tl, y_tip, mx / a, my / a, root_arc,
                   le_len + c_t + te_len)

    # Slide the fin until its area centroid sits at 0.86 L, but keep the
    # trailing edge on the hull ahead of the tail disc.
    x_te = FIN_STATION_FRAC * length + 0.4 * c_r
    fin = build(x_te)
    for _ in range(30):
        x_te = min(0.985 * length, x_te + FIN_STATION_FRAC * length - fin.centroid_x_m)
        fin = build(x_te)
    return fin


def fin_design(hull: Hull, dp, opts: Options) -> Fin:
    """Planform, spar tubes and mass of one of the four fins.

    Spar sizing argument.  Normal force on a fin is q C_N A with
    C_N = 2.2/rad x design incidence (the lift slope ``sizing._hull_stability``
    uses) [estimate].  It acts at the area centroid; the two spars share the
    root moment equally [estimate].  Two cases:

    * launch / first climb: q = rho0 w^2 / 2 at the ascent rate set by free
      lift on the launch bubble (sphere, C_D 0.47), beam at ground gauge;
    * float dash: q at float altitude and dash airspeed, beam at
      min(relief, sealed-beam pressure at altitude).

    The tube must not wrinkle: pi p r^3 / 2 >= 1.5 M  [physics, margin as in
    ``air_beam``].  Hoop load at the relief setting is checked against the
    fabric allowable (ultimate / 4, as ``air_beam``).
    """

    g = dp.geometry
    area1 = g["fin_area_total_m2"] / 4.0
    mission = dp.mission
    alt = mission.get("float_altitude_m", 20_000.0)
    dash = mission.get("dash_airspeed_m_s", 10.0)
    cn = 2.2 * math.radians(opts.fin_incidence_deg)
    # Ascent rate from free lift on the launch bubble [estimate].
    free_n = dp.lift.get("free_lift_n")
    v0 = dp.lift.get("launch_gas_nm3")
    if free_n and v0:
        frontal = math.pi * (3.0 * v0 / (4.0 * math.pi)) ** (2.0 / 3.0)
        ascent = math.sqrt(2.0 * free_n / (1.225 * 0.47 * frontal))
    else:
        ascent = 5.0
    q_launch = 0.5 * 1.225 * ascent**2
    q_float = isa(alt).dynamic_pressure_pa(dash)
    p_float = min(SPAR_RELIEF_PA, sealed_beam_pressure_at_altitude(SPAR_GROUND_GAUGE_PA, alt))
    fabric = FILMS[SPAR_FABRIC_KEY]
    n_allow = fabric.ultimate_n_per_m / 4.0

    def size(fin: Fin) -> dict:
        cases = {}
        for name, q, p in (("launch", q_launch, SPAR_GROUND_GAUGE_PA),
                           ("float_dash", q_float, p_float)):
            force = q * cn * fin.area_m2
            moment = 0.5 * force * fin.centroid_height_m
            r = (2.0 * 1.5 * moment / (math.pi * p)) ** (1.0 / 3.0)
            cases[name] = {"q_pa": q, "gauge_pa": p, "fin_force_n": force,
                           "moment_per_spar_nm": moment, "radius_required_m": r}
        gov = max(cases, key=lambda k: cases[k]["radius_required_m"])
        d = math.ceil(2.0 * cases[gov]["radius_required_m"] / 0.01) * 0.01
        m_launch = cases["launch"]["moment_per_spar_nm"]
        d_relief = 2.0 * (2.0 * 1.5 * m_launch / (math.pi * SPAR_RELIEF_PA)) ** (1.0 / 3.0)
        ideal = air_beam(cases[gov]["moment_per_spar_nm"], fin.span_m)
        return {"diameter_m": d, "governing_case": gov, "cases": cases,
                "ascent_rate_m_s": ascent, "design_cn": cn,
                "hoop_at_relief_n_per_m": SPAR_RELIEF_PA * d / 2.0,
                "fabric_allowable_n_per_m": n_allow,
                "hoop_ok": SPAR_RELIEF_PA * d / 2.0 <= n_allow,
                "sealed_gauge_at_float_pa": sealed_beam_pressure_at_altitude(
                    SPAR_GROUND_GAUGE_PA, alt),
                "diameter_if_filled_to_relief_on_ground_m": d_relief,
                "fabric_limited_ideal": {"diameter_m": 2.0 * ideal["radius_m"],
                                         "gauge_pressure_pa": ideal["gauge_pressure_pa"]},
                "flat_width_m": math.pi * d + opts.spar_lap_m}

    fin = _fin_planform(hull, area1, opts)
    spar = size(fin)
    # Skin take-up: the skin runs LE seam -> over spar 1 -> over spar 2 -> TE
    # seam, which is longer than the chord.  Cut the planform larger by that
    # ratio (evaluated at the mean chord) so the inflated fin has the area.
    r = 0.5 * spar["diameter_m"]
    c = 0.5 * (fin.root_chord_m + fin.tip_chord_m)
    edge = 0.25 * c
    if edge > r:
        path = 2.0 * (math.sqrt(edge * edge - r * r) + r * math.asin(r / edge)) + 0.5 * c
        takeup = path / c - 1.0
    else:
        takeup = math.pi / 2.0 - 1.0
    fin = _fin_planform(hull, area1 * (1.0 + takeup), opts)
    fin.area_m2 = area1
    fin.skin_chord_takeup = takeup
    fin.spar = spar
    d = spar["diameter_m"]
    for frac in (0.25, 0.75):
        x0 = fin.x_le_m + frac * fin.root_chord_m
        x1 = fin.x_tip_le_m + frac * fin.tip_chord_m
        y0, y1 = hull.radius_at(x0), fin.y_tip_m
        ln = math.hypot(x1 - x0, y1 - y0)
        fin.spars.append({"chord_fraction": frac, "root_xy_m": (x0, y0), "tip_xy_m": (x1, y1),
                          "length_m": ln,
                          # pillow ends: flat-sealed, half a diameter each [estimate]
                          "pattern_length_m": ln + d, "pattern_width_m": spar["flat_width_m"]})
    film = _film_for(dp)
    skin = 2.0 * fin.pattern_area_m2 * film.areal_density_kg_m2
    spars = sum(s["pattern_length_m"] * s["pattern_width_m"] for s in fin.spars) \
        * fabric.areal_density_kg_m2 * 1.10          # weld lap and tape, as air_beam
    valves = 2 * 0.010                               # fill + relief per spar pair [estimate]
    fin.mass_kg = {"skin_film": skin, "spars": spars, "valves": valves,
                   "one_fin": skin + spars + valves, "four_fins": 4.0 * (skin + spars + valves),
                   "sizing_budget_four_fins": dp.mass_kg.get("fins")}
    pitch = 360.0 / opts.n_gores
    off = (45.0 - 0.5 * pitch) % pitch
    if min(off, pitch - off) < 1e-6:
        fin.root_on = "seam"
    elif min(45.0 % pitch, pitch - 45.0 % pitch) < 1e-6:
        fin.root_on = "gore centreline"
    else:
        d_seam = min(off, pitch - off)
        fin.root_on = f"{d_seam:.2f} deg off the nearest seam"
    return fin


def _film_for(dp):
    name = dp.geometry.get("film")
    for f in FILMS.values():
        if f.name == name:
            return f
    return FILMS["lldpe-20um"]


# --- drawing -----------------------------------------------------------------

LAYERS = {  # name: (DXF colour index, SVG stroke, dashed)
    "CUT": (7, "#000000", False),
    "SEAL": (1, "#c00000", True),
    "CENTRE": (8, "#808080", True),
    "STATION": (5, "#0050c0", False),
    "KEEL_GORE_ONLY": (3, "#008000", False),
    "CROWN_GORE_ONLY": (6, "#b000b0", False),
    "FIN_ROOT": (30, "#d07000", False),
    "SPAR": (4, "#008090", True),
    "TEXT": (7, "#000000", False),
}


class Drawing:
    """1:1 drawing in millimetres, y up; writes SVG and ASCII R12 DXF."""

    def __init__(self, title: str):
        self.title = title
        self.items: list[tuple] = []

    def polyline(self, layer: str, pts: list, closed: bool = False) -> None:
        self.items.append(("poly", layer, [(float(x), float(y)) for x, y in pts], closed))

    def line(self, layer: str, x0, y0, x1, y1) -> None:
        self.polyline(layer, [(x0, y0), (x1, y1)])

    def circle(self, layer: str, x, y, r) -> None:
        self.items.append(("circle", layer, float(x), float(y), float(r)))

    def text(self, layer: str, x, y, height, string: str, angle: float = 0.0) -> None:
        self.items.append(("text", layer, float(x), float(y), float(height), string, angle))

    def bounds(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        for it in self.items:
            if it[0] == "poly":
                xs += [p[0] for p in it[2]]
                ys += [p[1] for p in it[2]]
            elif it[0] == "circle":
                xs += [it[2] - it[4], it[2] + it[4]]
                ys += [it[3] - it[4], it[3] + it[4]]
            else:
                xs += [it[2], it[2] + 0.6 * it[4] * len(it[5]) * abs(math.cos(math.radians(it[6])))]
                ys += [it[3], it[3] + it[4] + 0.6 * it[4] * len(it[5]) * abs(math.sin(math.radians(it[6])))]
        return min(xs), min(ys), max(xs), max(ys)

    def svg(self) -> str:
        x0, y0, x1, y1 = self.bounds()
        m = 20.0
        w, h = x1 - x0 + 2 * m, y1 - y0 + 2 * m
        fx = lambda x: x - x0 + m
        fy = lambda y: y1 - y + m
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.1f}mm" height="{h:.1f}mm" '
               f'viewBox="0 0 {w:.1f} {h:.1f}">',
               f'<title>{_xml(self.title)}</title>',
               f'<!-- 1:1, user unit = 1 mm. Generated by aiur.strato.patterns -->',
               f'<rect x="0" y="0" width="{w:.1f}" height="{h:.1f}" fill="#ffffff"/>']
        for name, (_, colour, dashed) in LAYERS.items():
            members = [it for it in self.items if it[1] == name]
            if not members:
                continue
            dash = ' stroke-dasharray="6 4"' if dashed else ""
            out.append(f'<g id="{name}" fill="none" stroke="{colour}" stroke-width="1" '
                       f'vector-effect="non-scaling-stroke"{dash}>')
            for it in members:
                if it[0] == "poly":
                    pts = " ".join(f"{fx(x):.2f},{fy(y):.2f}" for x, y in it[2])
                    tag = "polygon" if it[3] else "polyline"
                    out.append(f'<{tag} points="{pts}" vector-effect="non-scaling-stroke"/>')
                elif it[0] == "circle":
                    out.append(f'<circle cx="{fx(it[2]):.2f}" cy="{fy(it[3]):.2f}" r="{it[4]:.2f}" '
                               f'vector-effect="non-scaling-stroke"/>')
                else:
                    _, _, x, y, hgt, s, ang = it
                    tr = f' transform="rotate({-ang:.1f} {fx(x):.2f} {fy(y):.2f})"' if ang else ""
                    out.append(f'<text x="{fx(x):.2f}" y="{fy(y):.2f}" font-size="{hgt:.1f}" '
                               f'font-family="sans-serif" fill="{colour}" stroke="none"{tr}>'
                               f'{_xml(s)}</text>')
            out.append("</g>")
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def dxf(self) -> str:
        x0, y0, x1, y1 = self.bounds()
        o: list[str] = []

        def w(code: int, value) -> None:
            o.append(f"{code:>3}")
            o.append(f"{value:.4f}" if isinstance(value, float) else str(value))

        w(0, "SECTION"); w(2, "HEADER")
        w(9, "$ACADVER"); w(1, "AC1009")
        w(9, "$EXTMIN"); w(10, x0); w(20, y0)
        w(9, "$EXTMAX"); w(10, x1); w(20, y1)
        w(0, "ENDSEC")
        w(0, "SECTION"); w(2, "TABLES")
        w(0, "TABLE"); w(2, "LTYPE"); w(70, 1)
        w(0, "LTYPE"); w(2, "CONTINUOUS"); w(70, 0); w(3, "Solid line"); w(72, 65); w(73, 0); w(40, 0.0)
        w(0, "ENDTAB")
        w(0, "TABLE"); w(2, "LAYER"); w(70, len(LAYERS))
        for name, (colour, _, _) in LAYERS.items():
            w(0, "LAYER"); w(2, name); w(70, 0); w(62, colour); w(6, "CONTINUOUS")
        w(0, "ENDTAB")
        w(0, "ENDSEC")
        w(0, "SECTION"); w(2, "ENTITIES")
        for it in self.items:
            if it[0] == "poly":
                w(0, "POLYLINE"); w(8, it[1]); w(66, 1); w(70, 1 if it[3] else 0)
                w(10, 0.0); w(20, 0.0); w(30, 0.0)
                for x, y in it[2]:
                    w(0, "VERTEX"); w(8, it[1]); w(10, x); w(20, y); w(30, 0.0)
                w(0, "SEQEND"); w(8, it[1])
            elif it[0] == "circle":
                w(0, "CIRCLE"); w(8, it[1]); w(10, it[2]); w(20, it[3]); w(30, 0.0); w(40, it[4])
            else:
                _, layer, x, y, hgt, s, ang = it
                w(0, "TEXT"); w(8, layer); w(10, x); w(20, y); w(30, 0.0); w(40, hgt)
                w(1, s.encode("ascii", "replace").decode("ascii"))
                if ang:
                    w(50, float(ang))
        w(0, "ENDSEC")
        w(0, "EOF")
        return "\n".join(o) + "\n"


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


MM = 1000.0


def draw_gore(key: str, mer: Meridian, gore: Gore, marks: dict, closures: dict,
              opts: Options) -> Drawing:
    d = Drawing(f"{key} gore, N={gore.n}, 1:1 mm")
    top = [(s * MM, c * MM) for s, _, c in gore.samples]
    bot = [(s * MM, -c * MM) for s, _, c in reversed(gore.samples)]
    d.polyline("CUT", top + bot, closed=True)
    d.polyline("SEAL", [(s * MM, h * MM) for s, h, _ in gore.samples])
    d.polyline("SEAL", [(s * MM, -h * MM) for s, h, _ in gore.samples])
    d.line("CENTRE", 0.0, 0.0, gore.s_tail_cut * MM, 0.0)
    hmax = gore.max_half_width_cut_m * MM
    # datum
    d.line("STATION", 0.0, -40.0, 0.0, 40.0)
    d.text("STATION", 5.0, 45.0, 12.0, "s=0 DATUM (theoretical nose apex)", 90.0)
    k = math.floor(gore.s_nose_cut / opts.station_pitch_m) + 1
    while k * opts.station_pitch_m < gore.s_tail_cut:
        s = k * opts.station_pitch_m
        hw = gore_half_width(mer, gore.n, s, gore.width_scale) * MM
        d.line("STATION", s * MM, -hw, s * MM, hw)
        d.text("STATION", s * MM + 4.0, 4.0, 12.0, f"s {s:.1f} m  half {hw:.0f}")
        k += 1
    for s in marks["load_patches_s_m"]:
        d.circle("KEEL_GORE_ONLY", s * MM, 0.0, 0.5 * opts.patch_diameter_m * MM)
        d.line("KEEL_GORE_ONLY", s * MM - 30, 0.0, s * MM + 30, 0.0)
        d.line("KEEL_GORE_ONLY", s * MM, -30.0, s * MM, 30.0)
    ps = marks["port_s_m"]
    pd = marks["port_diameter_m"] * MM
    d.circle("KEEL_GORE_ONLY", ps * MM, 0.0, 0.5 * pd)
    d.text("KEEL_GORE_ONLY", ps * MM - 60, -0.5 * pd - 30, 14.0,
           f"RELIEF/FILL PORT dia {pd:.0f} (keel gore only)")
    d.text("KEEL_GORE_ONLY", marks["load_patches_s_m"][0] * MM - 60,
           0.5 * opts.patch_diameter_m * MM + 10, 14.0, "LOAD PATCH (keel gore only)")
    r0, r1 = marks["rip_s_m"]
    d.line("CROWN_GORE_ONLY", r0 * MM, 0.0, r1 * MM, 0.0)
    d.line("CROWN_GORE_ONLY", r0 * MM, -25.0, r0 * MM, 25.0)
    d.line("CROWN_GORE_ONLY", r1 * MM, -25.0, r1 * MM, 25.0)
    d.text("CROWN_GORE_ONLY", r0 * MM, 30.0, 14.0, "RIP LINE / HOT WIRE (crown gore only)")
    if marks.get("fin_root_s_m"):
        f0, f1 = marks["fin_root_s_m"]
        for s, label in ((f0, "FIN ROOT LE"), (f1, "FIN ROOT TE")):
            hw = gore_half_width(mer, gore.n, s, gore.width_scale) * MM
            for sign in (1.0, -1.0):
                d.line("FIN_ROOT", s * MM, sign * (hw - 25.0), s * MM, sign * (hw + 25.0))
            d.text("FIN_ROOT", s * MM + 4.0, hw + 30.0, 12.0, label + " (" + marks["fin_root_on"] + ")")
    # closures below the gore
    y = -hmax - 80.0
    rn = closures["nose_cap"]["cut_radius_m"] * MM
    d.circle("CUT", rn, y - rn, rn)
    d.circle("SEAL", rn, y - rn, closures["nose_cap"]["seal_radius_m"] * MM)
    d.text("TEXT", 2 * rn + 20, y - rn, 16.0, f"NOSE CAP x1  R {rn:.0f} mm")
    rt = closures["tail_disc"]["cut_radius_m"] * MM
    cx = 2 * rn + 600.0 + rt
    d.circle("CUT", cx, y - rt, rt)
    d.circle("SEAL", cx, y - rt, closures["tail_disc"]["seal_radius_m"] * MM)
    d.text("TEXT", cx + rt + 20, y - rt, 16.0, f"TAIL DISC x1  R {rt:.0f} mm")
    d.text("TEXT", 0.0, hmax + 60.0, 30.0,
           f"{key}  GORE x{gore.n}  1:1 mm  allowance {gore.allowance_m*MM:.0f} mm  "
           f"cut length {gore.centre_length_m*MM:.0f}  max cut width {2*hmax:.0f}")
    return d


def draw_fin(key: str, hull: Hull, fin: Fin, opts: Options) -> Drawing:
    d = Drawing(f"{key} fin, 1:1 mm")
    a, fl = opts.seam_allowance_m, opts.fin_flange_m
    x0 = fin.x_le_m
    steps = 120
    root = [(fin.x_le_m + (fin.x_te_m - fin.x_le_m) * i / steps) for i in range(steps + 1)]
    X = lambda x: (x - x0) * MM
    seal = [(X(x), hull.radius_at(x) * MM) for x in root]
    seal += [(X(fin.x_te_m), fin.y_tip_m * MM), (X(fin.x_tip_le_m), fin.y_tip_m * MM)]
    d.polyline("SEAL", seal, closed=True)
    sw = math.radians(fin.le_sweep_deg)
    cut = [(X(x), (hull.radius_at(x) - fl) * MM) for x in root]
    cut += [(X(fin.x_te_m + a), (hull.radius_at(fin.x_te_m) - fl) * MM),
            (X(fin.x_te_m + a), (fin.y_tip_m + a) * MM),
            (X(fin.x_tip_le_m - a * math.tan(0.5 * (math.pi / 2 - sw))), (fin.y_tip_m + a) * MM),
            (X(fin.x_le_m - a / math.cos(sw) - fl * math.tan(sw)),
             (hull.radius_at(fin.x_le_m) - fl) * MM)]
    d.polyline("CUT", cut, closed=True)
    for sp in fin.spars:
        (xa, ya), (xb, yb) = sp["root_xy_m"], sp["tip_xy_m"]
        d.line("SPAR", X(xa), ya * MM, X(xb), yb * MM)
        d.text("SPAR", X(xa) + 10, ya * MM + 40, 14.0,
               f"spar {int(100*sp['chord_fraction'])}% chord  L {sp['length_m']*MM:.0f}", 80.0)
    ybase = min(p[1] for p in cut)
    d.text("TEXT", 0.0, fin.y_tip_m * MM + 60.0, 24.0,
           f"{key}  FIN SKIN x8 (2 per fin)  1:1 mm  root chord {fin.root_chord_m*MM:.0f}  "
           f"tip {fin.tip_chord_m*MM:.0f}  root LE at hull x {fin.x_le_m:.3f} m")
    d.text("TEXT", 0.0, ybase + 10.0, 14.0, "ROOT FLANGE (cut line follows hull meridian)")
    y = ybase - 60.0
    for sp in fin.spars:
        wdt, ln = sp["pattern_width_m"] * MM, sp["pattern_length_m"] * MM
        d.polyline("CUT", [(0, y), (ln, y), (ln, y - wdt), (0, y - wdt)], closed=True)
        d.line("SEAL", 0.0, y - opts.spar_lap_m * MM, ln, y - opts.spar_lap_m * MM)
        d.text("TEXT", 20.0, y - 0.5 * wdt, 16.0,
               f"SPAR TUBE {int(100*sp['chord_fraction'])}% x4  {ln:.0f} x {wdt:.0f}  "
               f"dia {fin.spar['diameter_m']*MM:.0f}  (TPU-nylon)")
        y -= wdt + 40.0
    return d


# --- assembly of one design --------------------------------------------------

def build(key: str, dp, opts: Options = Options()) -> dict:
    """Everything for one hull design: numbers, tables and drawings."""

    g = dp.geometry
    hull = Hull(g["volume_m3"], g["fineness"])
    mer = Meridian(hull)
    film = _film_for(dp)
    n = opts.n_gores
    lob = lobing(mer, n)
    scale = lob["width_scale_to_recover_volume"] if opts.compensate_lobing else 1.0
    gore = develop_gore(mer, opts, scale)

    # -- check 1: flat gore area x N against the sizing model's hull area
    flat_total = n * develop_gore(mer, opts, 1.0).full_area_m2 + math.pi * mer.tail_radius_m**2
    checks = {
        "flat_gore_area_x_n_plus_tail_disc_m2": flat_total,
        "hull_surface_area_m2": hull.surface_area_m2,
        "area_agreement_pct": 100.0 * (flat_total / hull.surface_area_m2 - 1.0),
        "meridian_volume_m3": mer.volume(), "hull_volume_m3": hull.volume_m3,
        "volume_agreement_pct": 100.0 * (mer.volume() / hull.volume_m3 - 1.0),
        "geometry_matches_design_point": abs(hull.length_m - g["length_m"]) < 1e-6 * g["length_m"],
    }

    # -- closures
    r_nose = mer.r_at_s(gore.s_nose_cut)
    x_nose = mer.x_at_s(gore.s_nose_cut)
    rho_nose = hull.radius_m**2 / (0.25 * hull.length_m)   # ellipse b^2/a [physics]
    r_tail = mer.r_at_s(gore.s_tail_cut)
    x_tail = mer.x_at_s(gore.s_tail_cut)
    lost_tail = sum(math.pi * (0.5 * (mer.r[i] + mer.r[i - 1])) ** 2 * (mer.x[i] - mer.x[i - 1])
                    for i in range(1, len(mer.x)) if mer.x[i] > x_tail)
    closures = {
        "nose_cap": {
            "type": "flat disc laid over the gore tips, taped/sealed on a ring",
            "gore_cut_s_m": gore.s_nose_cut, "gore_cut_x_m": x_nose,
            "hull_radius_at_cut_m": r_nose, "seal_radius_m": gore.s_nose_cut,
            "cut_radius_m": gore.s_nose_cut + opts.cap_overlap_m,
            "nose_curvature_radius_m": rho_nose,
            "misfit_strain_pct": 100.0 * (gore.s_nose_cut / rho_nose) ** 2 / 6.0,
            "ring_seam_m": 2.0 * math.pi * r_nose,
        },
        "tail_disc": {
            "type": "flat disc with collar; gore ends pleated onto the collar and taped",
            "gore_cut_s_m": gore.s_tail_cut, "gore_cut_x_m": x_tail,
            "hull_radius_at_cut_m": r_tail, "profile_tail_radius_m": mer.tail_radius_m,
            "seal_radius_m": r_tail, "cut_radius_m": r_tail + opts.cap_overlap_m,
            "volume_lost_m3": lost_tail, "ring_seam_m": 2.0 * math.pi * r_tail,
        },
    }
    cap_area = math.pi * (closures["nose_cap"]["cut_radius_m"] ** 2
                          + closures["tail_disc"]["cut_radius_m"] ** 2)

    # -- marks on the keel and crown gores
    length = hull.length_m
    s_lo, s_hi = mer.s_at_x(opts.keel_span_frac[0] * length), mer.s_at_x(opts.keel_span_frac[1] * length)
    count = int(math.floor((s_hi - s_lo) / opts.patch_pitch_m)) + 1
    start = 0.5 * (s_lo + s_hi) - 0.5 * (count - 1) * opts.patch_pitch_m
    patches = [start + i * opts.patch_pitch_m for i in range(count)]
    # port: nearest mid-point between two patches to the maximum section
    s_port_nom = mer.s_at_x(opts.port_station_frac * length)
    mids = [0.5 * (a + b) for a, b in zip(patches, patches[1:])] or [s_port_nom]
    s_port = min(mids, key=lambda s: abs(s - s_port_nom))
    rip_len = max(0.5, 0.2 * hull.diameter_m)               # [estimate]
    s_rip = mer.s_at_x(opts.rip_station_frac * length)
    suspended_n = (dp.mass_kg.get("gross", 0.0) - dp.mass_kg.get("envelope_film", 0.0)
                   - dp.mass_kg.get("seams_patches", 0.0)) * G0
    allow = film.allowable_n_per_m * g.get("film_plies_equiv", 1.0)
    # Relief port flow check [physics: orifice, C_d 0.6]: gas that must leave
    # as the full hull keeps climbing, against the relief pressure.
    alt = dp.mission.get("float_altitude_m", 20_000.0)
    air = isa(alt)
    gas = GASES[dp.mission.get("gas", "hydrogen")]
    rho_gas = gas.density(air.pressure_pa, air.temperature_k)
    relief = dp.structure.get("relief_pressure_pa", 20.0)
    fin = fin_design(hull, dp, opts)
    climb = fin.spar["ascent_rate_m_s"]
    scale_h = 287.05 * air.temperature_k / G0
    vent_flow = hull.volume_m3 * climb / scale_h
    vent_area = vent_flow / (0.6 * math.sqrt(2.0 * relief / rho_gas))
    port_d = max(opts.port_diameter_m, math.ceil(
        math.sqrt(4.0 * opts.port_area_margin * vent_area / math.pi) / 0.01) * 0.01)
    marks = {
        "gore_centres_clock_deg": "0 (crown), then every %.1f; keel gore at 180" % (360.0 / n),
        "load_patches_s_m": patches,
        "load_patches_x_m": [mer.x_at_s(s) for s in patches],
        "load_patch_count": count,
        "load_per_patch_n": suspended_n / count,
        "patch_edge_capacity_n": math.pi * opts.patch_diameter_m * allow,
        "port_s_m": s_port, "port_x_m": mer.x_at_s(s_port),
        "port_diameter_m": port_d,
        "port_area_required_m2": vent_area,
        "port_area_margin": math.pi * port_d**2 / 4.0 / vent_area,
        "port_flow_basis": {"climb_m_s": climb, "relief_pa": relief, "vent_flow_m3_s": vent_flow},
        "rip_s_m": [s_rip - 0.5 * rip_len, s_rip + 0.5 * rip_len],
        "rip_x_m": [mer.x_at_s(s_rip - 0.5 * rip_len), mer.x_at_s(s_rip + 0.5 * rip_len)],
        "rip_length_m": rip_len,
        "fin_root_s_m": [mer.s_at_x(fin.x_le_m), mer.s_at_x(fin.x_te_m)],
        "fin_root_on": fin.root_on,
    }

    # -- nesting
    hull_area = hull.surface_area_m2
    widths = sorted(set(ROLL_WIDTHS_M) | {opts.roll_width_m})
    nesting = {f"{w:.2f}": nest_gores(mer, gore, hull_area, w, opts, cap_area) for w in widths}
    chosen = nesting[f"{opts.roll_width_m:.2f}"]

    # fin skins on the same roll (reported separately; cost.py prices fins apart)
    a = opts.seam_allowance_m
    grid = 0.02
    cnt = int(math.ceil((fin.root_chord_m + 2 * a) / grid))
    ys_bot, ys_top = [], []
    for i in range(cnt + 1):
        x = min(fin.x_te_m, max(fin.x_le_m, fin.x_le_m - a + i * grid))
        ys_bot.append(hull.radius_at(x) - opts.fin_flange_m)
        ys_top.append(fin.top(x, hull) + a / math.cos(math.radians(fin.le_sweep_deg)))
    ref = min(ys_bot)
    fin_skin_area = 2.0 * fin.pattern_area_m2 + (fin.perimeter_seal_m * a + fin.root_arc_m
                                                 * opts.fin_flange_m) * 2.0
    fin_nest = nest([-(b - ref) for b in ys_bot], [t - ref for t in ys_top], grid, 8,
                    opts.roll_width_m, opts.cut_gap_m)
    fin_roll = None
    if fin_nest:
        fin_roll = {**fin_nest, "roll_area_m2": fin_nest["roll_length_m"] * opts.roll_width_m,
                    "skin_cut_area_m2": 4.0 * fin_skin_area}
        fin_roll["waste_fraction"] = 1.0 - fin_roll["skin_cut_area_m2"] / fin_roll["roll_area_m2"]

    # -- seams, tape, time
    split = bool(chosen.get("split"))
    d_spar = fin.spar["diameter_m"]
    seams = {
        "gore_meridional_heat_seal_m": n * gore.edge_length_m,
        "gore_split_centre_heat_seal_m": n * gore.centre_length_m if split else 0.0,
        "nose_cap_ring_m": closures["nose_cap"]["ring_seam_m"],
        "tail_disc_ring_m": closures["tail_disc"]["ring_seam_m"],
        "fin_perimeter_heat_seal_m": 4.0 * fin.perimeter_seal_m,
        "fin_root_to_hull_m": 4.0 * 2.0 * fin.root_arc_m,
        "spar_longitudinal_weld_m": 4.0 * sum(s["pattern_length_m"] for s in fin.spars),
        "spar_end_weld_m": 4.0 * 2 * 2 * (0.5 * math.pi * d_spar),
    }
    seams["hull_total_m"] = sum(seams[k] for k in (
        "gore_meridional_heat_seal_m", "gore_split_centre_heat_seal_m",
        "nose_cap_ring_m", "tail_disc_ring_m"))
    seams["fin_total_m"] = sum(seams[k] for k in (
        "fin_perimeter_heat_seal_m", "fin_root_to_hull_m",
        "spar_longitudinal_weld_m", "spar_end_weld_m"))
    seams["total_m"] = seams["hull_total_m"] + seams["fin_total_m"]
    tape = {
        "load_patches_m": count * 4 * 0.20,     # four 200 mm strips per patch [estimate]
        "nose_cap_ring_m": closures["nose_cap"]["ring_seam_m"],
        "tail_collar_m": closures["tail_disc"]["ring_seam_m"] * 2.0,
        "port_reinforcement_m": math.pi * (port_d + 0.05),
        "rip_line_m": 2.0 * rip_len,
        "fin_root_m": 4.0 * 2.0 * fin.root_arc_m,
    }
    tape["total_m"] = sum(tape.values())
    cost_seam_m = 12 * g["length_m"] * 1.1 + 4 * 14.0          # cost.py, verbatim
    cost_hours = cost_seam_m / SEAL_RATE_M_PER_MIN / 60.0 * 2.2 + 4.0
    hull_h_raw = seams["hull_total_m"] / SEAL_RATE_M_PER_MIN / 60.0
    labour = {
        "seal_rate_m_per_min": SEAL_RATE_M_PER_MIN,
        "hull_seam_m": seams["hull_total_m"], "fin_seam_m": seams["fin_total_m"],
        "hull_sealing_h_at_rate": hull_h_raw,
        "fin_sealing_h_at_rate": seams["fin_total_m"] / SEAL_RATE_M_PER_MIN / 60.0,
        "hull_cut_and_seal_h_cost_formula": hull_h_raw * 2.2 + 4.0,
        "cost_model_seam_m": cost_seam_m,
        "cost_model_hull_seam_m": 12 * g["length_m"] * 1.1,
        "cost_model_fin_seam_m": 4 * 14.0,
        "cost_model_cut_and_seal_h": cost_hours,
        "cost_model_fin_h": 6.0,
        "seam_m_vs_cost_model_pct": 100.0 * (seams["total_m"] / cost_seam_m - 1.0),
        "hull_seam_vs_cost_model_pct": 100.0 * (seams["hull_total_m"] / (12 * g["length_m"] * 1.1) - 1.0),
        "fin_seam_vs_cost_model_pct": 100.0 * (seams["fin_total_m"] / 56.0 - 1.0),
    }
    labour["cut_and_seal_h_same_formula_all_seams"] = \
        seams["total_m"] / SEAL_RATE_M_PER_MIN / 60.0 * 2.2 + 4.0

    # -- film totals and cut list
    gore_pieces = chosen.get("pieces", n)
    spar_fabric = 4.0 * sum(s["pattern_length_m"] * s["pattern_width_m"] for s in fin.spars)
    film_totals = {
        "hull_smooth_area_m2": hull_area,
        "gores_net_area_m2": n * gore.net_area_m2,
        "gores_cut_area_m2": n * gore.cut_area_m2
        + (2 * n * gore.allowance_m * gore.centre_length_m if split else 0.0),
        "closures_cut_area_m2": cap_area,
        "seam_allowance_overhead_pct": 100.0 * (n * gore.cut_area_m2 / (n * gore.net_area_m2) - 1.0),
        "fin_skin_cut_area_m2": 4.0 * fin_skin_area,
        "spar_fabric_area_m2": spar_fabric,
        "hull_roll_length_m": chosen.get("roll_length_m"),
        "hull_roll_area_m2": chosen.get("roll_area_m2"),
        "fin_roll_length_m": fin_roll["roll_length_m"] if fin_roll else None,
    }
    rows = [
        {"piece": "half-gore" if split else "gore", "material": film.name, "qty": gore_pieces,
         "length_mm": gore.centre_length_m * MM,
         "width_mm": (gore.max_half_width_cut_m + (gore.allowance_m if split else gore.max_half_width_cut_m)) * MM,
         "area_each_m2": (0.5 * gore.cut_area_m2 + gore.allowance_m * gore.centre_length_m) if split
         else gore.cut_area_m2,
         "drawing": "gore.svg / gore.dxf / gore_stations.csv",
         "note": f"seam allowance {gore.allowance_m*MM:.0f} mm each edge; 1 keel, 1 crown, rest plain"},
        {"piece": "nose cap", "material": film.name, "qty": 1,
         "length_mm": 2 * closures["nose_cap"]["cut_radius_m"] * MM,
         "width_mm": 2 * closures["nose_cap"]["cut_radius_m"] * MM,
         "area_each_m2": math.pi * closures["nose_cap"]["cut_radius_m"] ** 2,
         "drawing": "gore.svg", "note": "disc, from offcut; double it for the nose fitting"},
        {"piece": "tail disc", "material": film.name, "qty": 1,
         "length_mm": 2 * closures["tail_disc"]["cut_radius_m"] * MM,
         "width_mm": 2 * closures["tail_disc"]["cut_radius_m"] * MM,
         "area_each_m2": math.pi * closures["tail_disc"]["cut_radius_m"] ** 2,
         "drawing": "gore.svg", "note": "disc + collar, from offcut"},
        {"piece": "load patch", "material": "PE/polyester tape 48 mm", "qty": count,
         "length_mm": opts.patch_diameter_m * MM, "width_mm": opts.patch_diameter_m * MM,
         "area_each_m2": math.pi * opts.patch_diameter_m**2 / 4.0, "drawing": "gore.svg (KEEL_GORE_ONLY)",
         "note": f"every {opts.patch_pitch_m} m of keel arc; {suspended_n/count:.1f} N each"},
        {"piece": "port reinforcement ring", "material": film.name + " x2", "qty": 1,
         "length_mm": (port_d + 0.10) * MM, "width_mm": (port_d + 0.10) * MM,
         "area_each_m2": math.pi * (port_d + 0.10) ** 2 / 4.0,
         "drawing": "gore.svg (KEEL_GORE_ONLY)", "note": f"port {port_d*MM:.0f} mm"},
        {"piece": "fin skin", "material": film.name, "qty": 8,
         "length_mm": (fin.root_chord_m + 2 * a) * MM,
         "width_mm": (max(ys_top) - ref) * MM, "area_each_m2": fin_skin_area / 2.0,
         "drawing": "fin.svg / fin.dxf", "note": "2 per fin, mirror pairs are identical"},
    ]
    for sp in fin.spars:
        rows.append({"piece": f"spar tube {int(100*sp['chord_fraction'])}% chord",
                     "material": FILMS[SPAR_FABRIC_KEY].name, "qty": 4,
                     "length_mm": sp["pattern_length_m"] * MM, "width_mm": sp["pattern_width_m"] * MM,
                     "area_each_m2": sp["pattern_length_m"] * sp["pattern_width_m"],
                     "drawing": "fin.svg / fin.dxf",
                     "note": f"dia {d_spar*MM:.0f} mm, lap {opts.spar_lap_m*MM:.0f} mm, pillow ends"})
    pieces_total = sum(r["qty"] for r in rows)

    summary = {
        "design": key, "slug": key.replace("/", "_"),
        "options": asdict(opts),
        "film": {"name": film.name, "seam_method": film.seam,
                 "plies_equiv": g.get("film_plies_equiv", 1.0)},
        "hull": {"volume_m3": hull.volume_m3, "length_m": hull.length_m,
                 "diameter_m": hull.diameter_m, "fineness": hull.fineness,
                 "surface_area_m2": hull_area, "meridian_length_m": mer.length_s},
        "gore": {"n": n, "width_scale": scale, "nose_cut_s_m": gore.s_nose_cut,
                 "tail_cut_s_m": gore.s_tail_cut, "cut_length_m": gore.centre_length_m,
                 "max_net_width_m": 2 * gore.max_half_width_m,
                 "max_cut_width_m": 2 * gore.max_half_width_cut_m,
                 "net_area_m2": gore.net_area_m2, "cut_area_m2": gore.cut_area_m2,
                 "seam_line_length_m": gore.edge_length_m,
                 "seam_minus_centre_mm": (gore.edge_length_m - gore.centre_length_m) * MM},
        "checks": checks, "closures": closures, "marks": marks,
        "lobing": lobing_table(mer, sorted(set(LOBING_N) | {n})),
        "lobing_chosen": lob,
        "nesting": nesting, "fin_nesting": fin_roll,
        "fin": {k: v for k, v in asdict(fin).items()},
        "seams_m": seams, "tape_m": tape, "labour": labour,
        "film_totals": film_totals, "pieces_total": pieces_total,
    }
    return {"summary": summary, "cutlist": rows,
            "stations": station_table(mer, gore, opts),
            "gore_drawing": draw_gore(key, mer, gore, marks, closures, opts),
            "fin_drawing": draw_fin(key, hull, fin, opts)}


def write(result: dict, out_dir: Path) -> Path:
    s = result["summary"]
    d = out_dir / s["slug"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "gore.svg").write_text(result["gore_drawing"].svg(), encoding="utf-8")
    (d / "gore.dxf").write_text(result["gore_drawing"].dxf(), encoding="ascii")
    (d / "fin.svg").write_text(result["fin_drawing"].svg(), encoding="utf-8")
    (d / "fin.dxf").write_text(result["fin_drawing"].dxf(), encoding="ascii")
    with (d / "gore_stations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "s_mm", "x_mm", "radius_mm", "half_width_mm",
                    "half_width_with_allowance_mm"])
        for r in result["stations"]:
            w.writerow([r["kind"]] + [f"{r[k]*MM:.1f}" for k in (
                "s_m", "x_m", "radius_m", "half_width_m", "half_width_with_allowance_m")])
    with (d / "cutlist.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["piece", "material", "qty", "length_mm", "width_mm", "area_each_m2", "drawing", "note"]
        w = csv.writer(f)
        w.writerow(cols)
        for r in result["cutlist"]:
            w.writerow([r["piece"], r["material"], r["qty"], f"{r['length_mm']:.0f}",
                        f"{r['width_mm']:.0f}", f"{r['area_each_m2']:.4f}", r["drawing"], r["note"]])
    (d / "summary.json").write_text(json.dumps(s, indent=2, sort_keys=True, default=_round) + "\n",
                                    encoding="utf-8")
    return d


def _round(o):
    return str(o)


def _rounded(o):
    if isinstance(o, float):
        return round(o, 5)
    if isinstance(o, dict):
        return {k: _rounded(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_rounded(v) for v in o]
    return o


def report(result: dict) -> str:
    s = result["summary"]
    h, g, c, lab = s["hull"], s["gore"], s["checks"], s["labour"]
    f = s["fin"]
    lines = [f"=== {s['design']}   {h['length_m']:.2f} m x {h['diameter_m']:.2f} m, "
             f"{h['volume_m3']:.0f} m3, {h['surface_area_m2']:.1f} m2 of {s['film']['name']} "
             f"({s['film']['seam_method']})",
             f"  gore x{g['n']}: cut {g['cut_length_m']:.3f} m long, {g['max_net_width_m']*MM:.0f} mm net / "
             f"{g['max_cut_width_m']*MM:.0f} mm cut wide; seam line {g['seam_line_length_m']:.3f} m",
             f"  check: N x flat area + tail disc = {c['flat_gore_area_x_n_plus_tail_disc_m2']:.3f} m2 vs "
             f"Hull {c['hull_surface_area_m2']:.3f} m2 ({c['area_agreement_pct']:+.3f} %); "
             f"volume {c['volume_agreement_pct']:+.3f} %",
             f"  closures: nose cap R {s['closures']['nose_cap']['cut_radius_m']*MM:.0f} mm "
             f"(misfit {s['closures']['nose_cap']['misfit_strain_pct']:.2f} %), tail disc R "
             f"{s['closures']['tail_disc']['cut_radius_m']*MM:.0f} mm",
             "  lobing (polygon bound):  N   dV %   dA %   dL %   flat depth mm   +film to recover %"]
    for row in s["lobing"]:
        lines.append(f"                          {row['n_gores']:2d}  {row['volume_error_pct']:+5.2f}  "
                     f"{row['surface_area_error_pct']:+5.2f}  {row['length_error_pct']:+5.2f}  "
                     f"{row['max_flat_depth_mm']:10.0f}   {row['extra_film_to_recover_volume_pct']:+6.2f}")
    lines.append("  roll nesting:  width  fits  split  abreast  h2t  stagger  roll m   waste   "
                 "film/hull  vs 1.18   min N unsplit")
    for wkey, r in s["nesting"].items():
        if not r.get("feasible"):
            lines.append(f"                 {wkey:>5}  no    -- {r.get('note','')}")
            continue
        lines.append(f"                 {wkey:>5}  {'yes' if r['fits_one_width'] else 'no ':3}   "
                     f"{'yes' if r['split'] else 'no ':3}    {r['abreast']:2d}     "
                     f"{'yes' if r['head_to_tail'] else 'no ':3}  {r['stagger_m']:5.1f}  {r['roll_length_m']:7.1f}  "
                     f"{100*r['waste_fraction']:5.1f} %   {r['film_factor_vs_hull_area']:.3f}    "
                     f"{r['film_factor_difference']:+.3f}   {r['min_gores_unsplit']}"
                     + (f"   best N {r['best_gore_count_for_roll']['n_gores']} -> "
                        f"{r['best_gore_count_for_roll']['film_factor_vs_hull_area']:.3f}"
                        if r.get("best_gore_count_for_roll") else "")
                     + (f"   or split -> {r['split_alternative']['film_factor_vs_hull_area']:.3f}"
                        if r.get("split_alternative") else ""))
    lines.append(f"  marks: {s['marks']['load_patch_count']} load patches ({s['marks']['load_per_patch_n']:.1f} N "
                 f"each, edge capacity {s['marks']['patch_edge_capacity_n']:.0f} N), port at x "
                 f"{s['marks']['port_x_m']:.2f} m dia {s['marks']['port_diameter_m']*MM:.0f} mm (area margin x{s['marks']['port_area_margin']:.1f}), rip "
                 f"{s['marks']['rip_length_m']:.2f} m at x {s['marks']['rip_x_m'][0]:.2f} m")
    lines.append(f"  fin x4: {f['area_m2']:.2f} m2 each, root {f['root_chord_m']:.2f} tip {f['tip_chord_m']:.2f} "
                 f"span {f['span_m']:.2f} m, LE sweep {f['le_sweep_deg']:.0f} deg, root x "
                 f"{f['x_le_m']:.2f}-{f['x_te_m']:.2f} m (on {f['root_on']}), centroid "
                 f"{f['centroid_x_m']/h['length_m']:.3f} L")
    sp = f["spar"]
    lines.append(f"  spars x8: dia {sp['diameter_m']*MM:.0f} mm ({sp['governing_case']} governs, "
                 f"M {sp['cases'][sp['governing_case']]['moment_per_spar_nm']:.1f} N m/spar), flat width "
                 f"{sp['flat_width_m']*MM:.0f} mm; fins {f['mass_kg']['four_fins']:.2f} kg vs "
                 f"{f['mass_kg']['sizing_budget_four_fins']} kg budgeted")
    sm = s["seams_m"]
    lines.append(f"  seams: hull {sm['hull_total_m']:.0f} m (cost.py {lab['cost_model_hull_seam_m']:.0f} m, "
                 f"{lab['hull_seam_vs_cost_model_pct']:+.0f} %), fins {sm['fin_total_m']:.0f} m (cost.py 56 m, "
                 f"{lab['fin_seam_vs_cost_model_pct']:+.0f} %); tape {s['tape_m']['total_m']:.0f} m; "
                 f"{s['pieces_total']} pieces")
    lines.append(f"  sealing at 1.2 m/min: hull {lab['hull_sealing_h_at_rate']:.1f} h + fins "
                 f"{lab['fin_sealing_h_at_rate']:.1f} h bar time; cut+seal by cost.py formula "
                 f"{lab['cut_and_seal_h_same_formula_all_seams']:.1f} h vs cost.py "
                 f"{lab['cost_model_cut_and_seal_h']:.1f} h")
    return "\n".join(lines)


def hull_designs(points: dict | None = None) -> dict:
    """Every design point in the ladder whose architecture is a film hull."""

    points = ladder() if points is None else points
    return {k: v for k, v in points.items()
            if getattr(v, "architecture", "") == "hull" and v.geometry.get("volume_m3")}


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(prog="python -m aiur.strato.patterns", description=__doc__.split("\n")[0])
    ap.add_argument("--design", action="append",
                    help="design key or slug, e.g. S1-touch/hull (repeatable; default: all hulls)")
    ap.add_argument("--gores", type=int, default=Options.n_gores, help="number of gores (even, >= 6)")
    ap.add_argument("--roll-width", type=float, default=Options.roll_width_m,
                    help="usable single-ply film width, m")
    ap.add_argument("--allowance", type=float, default=Options.seam_allowance_m * MM,
                    help="seam allowance per edge, mm")
    ap.add_argument("--compensate-lobing", action="store_true",
                    help="widen gores so the polygon hull holds the design volume")
    ap.add_argument("--out", type=Path, default=root / "hardware" / "strato" / "patterns")
    ap.add_argument("--json", action="store_true", help="print summaries as JSON")
    args = ap.parse_args(argv)
    if args.gores < 6 or args.gores % 2:
        ap.error("--gores must be even and at least 6 (keel and crown must be gore centres)")
    opts = Options(n_gores=args.gores, roll_width_m=args.roll_width,
                   seam_allowance_m=args.allowance / MM, compensate_lobing=args.compensate_lobing)
    designs = hull_designs()
    if args.design:
        wanted = {d.replace("_", "/") for d in args.design} | set(args.design)
        designs = {k: v for k, v in designs.items() if k in wanted or k.replace("/", "_") in wanted}
        if not designs:
            ap.error("no hull design matches; available: " + ", ".join(hull_designs()))
    status = 0
    summaries = {}
    for key, dp in designs.items():
        result = build(key, dp, opts)
        result["summary"] = _rounded(result["summary"])
        path = write(result, args.out)
        summaries[key] = result["summary"]
        if not args.json:
            print(report(result))
            print(f"  -> {path}")
            print()
        if abs(result["summary"]["checks"]["area_agreement_pct"]) > 1.0:
            print(f"! {key}: flat gore area disagrees with Hull.surface_area_m2 by more than 1 %",
                  file=sys.stderr)
            status = 1
    if args.json:
        print(json.dumps(summaries, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
