"""Generate parity vectors for the flight-termination firmware.

The FTU firmware (``firmware/ftu/src/geofence.cpp``) carries a C++ port of
``aiur.strato.guidance.Geofence.must_terminate``.  A port that is merely
"reviewed" drifts; this tool makes the Python the oracle.  It calls the real
``Geofence`` on boundary, special-value and random inputs and writes inputs
and expected outputs to a CSV, which ``firmware/ftu/host/ftu_host_test``
replays through the C++.  One mismatch fails the build.

Rows (first field is the kind):

* ``D,name,value`` - a default read from the Python by introspection (the
  dataclass fields and the ``must_terminate`` argument defaults).  The C++
  defaults must equal these, so changing a threshold in ``guidance.py``
  without changing the firmware is caught here, not in flight.
* ``V,argc,max_range,max_alt,max_flight,min_descent,range,alt,flight,
  commanded,link_lost,link_timeout,terminate,reason`` - one call.  ``argc``
  (3..6) is how many positional arguments were actually passed, so the C++
  default arguments are exercised too.
* ``P,pressure_pa,altitude_m`` - ``aiur.strato.atmosphere.pressure_altitude_m``
  for the barometer conversion.  That one is a tolerance check, not bit
  parity: the firmware inverts the standard atmosphere in closed form, the
  Python by bisection.

Floats are written with ``float.hex()``: exact, and ``strtod`` reads it back
bit for bit.  NaN and infinities are written as ``nan`` / ``inf`` / ``-inf``.

Stdlib only and deterministic (fixed seed): the same file every run.

    python tools/ftu_vectors.py [--out firmware/ftu/host/build/vectors.csv]
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import itertools
import math
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from aiur.strato.atmosphere import pressure_altitude_m  # noqa: E402
from aiur.strato.guidance import Geofence  # noqa: E402

DEFAULT_OUT = os.path.join(REPO, "firmware", "ftu", "host", "build", "vectors.csv")
SEED = 0xF7_2026

#: Values that break naive ports: signed zeros, the ends of the double range,
#: infinities and NaN (which compares false to everything, so in the reference
#: a NaN measurement never trips its own criterion).
SPECIALS = [0.0, -0.0, 5e-324, -5e-324, 1.0, -1.0, 1.7976931348623157e308,
            -1.7976931348623157e308, math.inf, -math.inf, math.nan]


def fmt(x: float) -> str:
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return float(x).hex()


def around(x: float) -> list:
    """A threshold, its two neighbouring doubles, and a coarser bracket."""

    return [x, math.nextafter(x, math.inf), math.nextafter(x, -math.inf),
            x * (1 + 1e-12), x * (1 - 1e-12), x + 1.0, x - 1.0]


class Writer:
    def __init__(self, handle) -> None:
        self.handle = handle
        self.count = 0
        self.by_reason: dict = {}

    def vector(self, limits: tuple, range_m: float, alt_m: float, flight_s: float,
               commanded: bool = False, link_lost_s: float = 0.0,
               link_timeout_s: float = 3.0 * 3600.0, argc: int = 6) -> None:
        fence = Geofence(*limits)
        args = [float(range_m), float(alt_m), float(flight_s), bool(commanded),
                float(link_lost_s), float(link_timeout_s)]
        # Call with exactly argc positional arguments; the rest take the
        # Python defaults, which is what is recorded as "expected".
        terminate, reason = fence.must_terminate(*args[:argc])
        if not isinstance(terminate, bool) or not isinstance(reason, str):
            raise TypeError("Geofence.must_terminate changed its return type")
        row = ["V", str(argc)] + [fmt(float(v)) for v in limits] + \
              [fmt(args[0]), fmt(args[1]), fmt(args[2]), "1" if args[3] else "0",
               fmt(args[4]), fmt(args[5]), "1" if terminate else "0", reason]
        self.handle.write(",".join(row) + "\n")
        self.count += 1
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1


def write_defaults(handle) -> tuple:
    fields = {f.name: f.default for f in dataclasses.fields(Geofence)}
    for name, value in fields.items():
        handle.write(f"D,{name},{fmt(float(value))}\n")
    sig = inspect.signature(Geofence.must_terminate)
    handle.write(f"D,link_timeout_s,{fmt(float(sig.parameters['link_timeout_s'].default))}\n")
    handle.write(f"D,link_lost_s,{fmt(float(sig.parameters['link_lost_s'].default))}\n")
    handle.write(f"D,commanded,{fmt(float(bool(sig.parameters['commanded'].default)))}\n")
    order = [f.name for f in dataclasses.fields(Geofence)]
    expected = ["max_range_m", "max_altitude_m", "max_flight_s", "min_descent_altitude_m"]
    if order != expected:
        raise RuntimeError(f"Geofence fields changed: {order}; update the firmware and this tool")
    return tuple(float(fields[n]) for n in expected)


def generate(handle, n_random: int) -> Writer:
    rng = random.Random(SEED)
    out = Writer(handle)
    default = write_defaults(handle)
    dr, da, df, _ = default
    dl = 3.0 * 3600.0

    limit_sets = [default,
                  (50_000.0, 20_000.0, 4.0 * 3600.0, 0.0),
                  (1.0, 1.0, 1.0, 0.0),
                  (0.0, 0.0, 0.0, 0.0),
                  (-10.0, -10.0, -10.0, -10.0),
                  (math.inf, math.inf, math.inf, 0.0),
                  (math.nan, 27_000.0, 57_600.0, 0.0),
                  (150_000.0, math.nan, 57_600.0, 0.0),
                  (150_000.0, 27_000.0, math.nan, 0.0),
                  (1e-300, 1e300, 5e-324, 0.0)]

    # 1. Boundaries: each criterion alone, at and one ulp either side of its
    #    limit, the others nominal.  The reference uses strict '>'.
    for lim in limit_sets:
        r, a, f, _ = lim
        for v in around(r) if math.isfinite(r) else [r]:
            for argc in (3, 6):
                out.vector(lim, v, 0.0 if a > 0 else a - 1, 0.0 if f > 0 else f - 1, argc=argc)
        for v in around(a) if math.isfinite(a) else [a]:
            for argc in (3, 6):
                out.vector(lim, 0.0 if r > 0 else r - 1, v, 0.0 if f > 0 else f - 1, argc=argc)
        for v in around(f) if math.isfinite(f) else [f]:
            for argc in (3, 6):
                out.vector(lim, 0.0 if r > 0 else r - 1, 0.0 if a > 0 else a - 1, v, argc=argc)
    for timeout in (dl, 0.0, 1.0, 60.0, 86_400.0, 1e-9, math.inf, math.nan):
        for v in (around(timeout) if math.isfinite(timeout) else [timeout]) + [0.0, -1.0]:
            out.vector(default, 0.0, 0.0, 0.0, False, v, timeout)
            out.vector(default, 0.0, 0.0, 0.0, False, v, argc=5)  # default timeout

    # 2. Precedence: every combination of the five criteria tripped or not,
    #    on several limit sets and every arity that can express it.
    for lim in limit_sets[:5]:
        r, a, f, _ = lim
        for bits in itertools.product((False, True), repeat=5):
            cmd, over_r, over_a, over_f, over_l = bits
            args = (r + 10.0 if over_r else r - 10.0,
                    a + 10.0 if over_a else a - 10.0,
                    f + 10.0 if over_f else f - 10.0,
                    cmd,
                    dl + 10.0 if over_l else dl - 10.0,
                    dl)
            for argc in (3, 4, 5, 6):
                out.vector(lim, *args, argc=argc)

    # 3. Special values in every position (all pairs of positions, all pairs
    #    of specials), then random draws of fully special inputs.
    for i, j in itertools.combinations(range(5), 2):
        for x, y in itertools.product(SPECIALS, repeat=2):
            vals = [100.0, 100.0, 100.0, 100.0, 1e9]  # nominal: nothing trips
            vals[i], vals[j] = x, y
            out.vector(default, vals[0], vals[1], vals[2], False, vals[3], vals[4])
    for _ in range(3000):
        vals = [rng.choice(SPECIALS) for _ in range(5)]
        lim = tuple(rng.choice(SPECIALS + [dr, da, df]) for _ in range(3)) + (0.0,)
        out.vector(lim, vals[0], vals[1], vals[2], rng.random() < 0.1, vals[3], vals[4],
                   argc=rng.choice((3, 4, 5, 6)))

    # 4. Random, default limits, each input drawn around its own threshold so
    #    that every reason is common rather than rare.
    def near(x: float) -> float:
        kind = rng.random()
        if kind < 0.45:
            return rng.uniform(0.0, 0.98 * x)       # comfortably inside
        if kind < 0.75:
            return x * (1.0 + rng.gauss(0.0, 1e-9))  # on the edge
        if kind < 0.95:
            return rng.uniform(x, 3.0 * x)          # outside
        return -rng.uniform(0.0, x)                 # negative (below ground, clock error)

    for _ in range(n_random):
        out.vector(default, near(dr), near(da), near(df), rng.random() < 0.05, near(dl), dl,
                   argc=rng.choice((3, 4, 5, 6)))

    # 5. Random limits as well, log-uniform over twelve decades.
    def loguniform() -> float:
        return 10.0 ** rng.uniform(-3.0, 9.0)

    for _ in range(n_random // 3):
        lim = (loguniform(), loguniform(), loguniform(), rng.uniform(-100.0, 1000.0))
        timeout = loguniform()
        out.vector(lim, lim[0] * rng.uniform(0.0, 2.0), lim[1] * rng.uniform(0.0, 2.0),
                   lim[2] * rng.uniform(0.0, 2.0), rng.random() < 0.02,
                   timeout * rng.uniform(0.0, 2.0), timeout)

    # Barometer conversion, 8.7 hPa (the firmware's 32 km layer edge is at
    # 8.68 hPa) to 1050 hPa.
    n_p = 400
    for k in range(n_p):
        p = 870.0 * (105_000.0 / 870.0) ** (k / (n_p - 1))
        handle.write(f"P,{fmt(p)},{fmt(pressure_altitude_m(p))}\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--random", type=int, default=18_000,
                    help="random default-limit vectors (a third as many again use random limits)")
    args = ap.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="ascii", newline="\n") as handle:
        handle.write("# generated by tools/ftu_vectors.py from aiur.strato.guidance.Geofence; "
                     "do not edit\n")
        out = generate(handle, args.random)
    if out.count < 20_000:
        print(f"only {out.count} vectors; the gate is 20,000", file=sys.stderr)
        return 1
    reasons = ", ".join(f"{k or '(none)'}={v}" for k, v in sorted(out.by_reason.items()))
    print(f"{out.count} vectors -> {os.path.relpath(args.out, REPO)}")
    print(f"by expected reason: {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
