"""Standard atmosphere, wind climatology and gusts for the STRATO models.

The standard atmosphere is the 1976 US Standard / ISO 2533 model to 51 km
[physics].  Winds are *not* standard anywhere: the profiles below are
engineering climatology tables assembled from published HAPS and radiosonde
statistics (docs/strato/references.md, "winds").  They are the single most
load-bearing input to whether a small airship can hold station, and the
tables say so explicitly by carrying a percentile label - a design that
closes on the median profile and not on the 90th has an availability, not a
capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

G0 = 9.80665  #: m/s2, standard gravity [physics]
R_AIR = 287.05287  #: J/(kg K) [physics]
GAMMA_AIR = 1.4
R_EARTH = 6_356_766.0  #: m, radius used by the standard atmosphere [physics]
SIGMA_SB = 5.670374e-8  #: W/(m2 K4) [physics]
R_UNIVERSAL = 8.314462618  #: J/(mol K) [physics]
M_AIR = 0.0289644  #: kg/mol [physics]

#: (geopotential base m, base temperature K, lapse K/m) [physics]
_LAYERS = (
    (0.0, 288.15, -0.0065),
    (11_000.0, 216.65, 0.0),
    (20_000.0, 216.65, 0.0010),
    (32_000.0, 228.65, 0.0028),
    (47_000.0, 270.65, 0.0),
    (51_000.0, 270.65, -0.0028),
)
_P0 = 101_325.0


def _base_pressures() -> tuple[float, ...]:
    out = [_P0]
    for i in range(len(_LAYERS) - 1):
        h0, t0, lapse = _LAYERS[i]
        h1 = _LAYERS[i + 1][0]
        p0 = out[-1]
        if lapse == 0.0:
            out.append(p0 * math.exp(-G0 * (h1 - h0) / (R_AIR * t0)))
        else:
            t1 = t0 + lapse * (h1 - h0)
            out.append(p0 * (t1 / t0) ** (-G0 / (lapse * R_AIR)))
    return tuple(out)


_PB = _base_pressures()


@dataclass(frozen=True)
class Air:
    """Ambient air state at one altitude."""

    altitude_m: float
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float

    @property
    def viscosity_pa_s(self) -> float:
        """Sutherland's law [physics]."""

        t = self.temperature_k
        return 1.458e-6 * t**1.5 / (t + 110.4)

    @property
    def speed_of_sound_m_s(self) -> float:
        return math.sqrt(GAMMA_AIR * R_AIR * self.temperature_k)

    @property
    def conductivity_w_mk(self) -> float:
        """Thermal conductivity of air, Sutherland-form fit [physics]."""

        t = self.temperature_k
        return 2.64638e-3 * t**1.5 / (t + 245.4 * 10 ** (-12.0 / t))

    def dynamic_pressure_pa(self, airspeed_m_s: float) -> float:
        return 0.5 * self.density_kg_m3 * airspeed_m_s * airspeed_m_s


def isa(altitude_m: float, delta_t_k: float = 0.0) -> Air:
    """Standard atmosphere at geometric altitude, with an optional day offset.

    ``delta_t_k`` shifts temperature at constant pressure (the usual hot/cold
    day convention), so density moves inversely.
    """

    z = max(-500.0, min(altitude_m, 60_000.0))
    h = R_EARTH * z / (R_EARTH + z)
    idx = 0
    for i, layer in enumerate(_LAYERS):
        if h >= layer[0]:
            idx = i
    h0, t0, lapse = _LAYERS[idx]
    p0 = _PB[idx]
    t = t0 + lapse * (h - h0)
    if lapse == 0.0:
        p = p0 * math.exp(-G0 * (h - h0) / (R_AIR * t0))
    else:
        p = p0 * (t / t0) ** (-G0 / (lapse * R_AIR))
    t_day = t + delta_t_k
    return Air(altitude_m, t_day, p, p / (R_AIR * t_day))


def gravity(altitude_m: float) -> float:
    return G0 * (R_EARTH / (R_EARTH + altitude_m)) ** 2


def pressure_altitude_m(pressure_pa: float) -> float:
    """Invert the standard atmosphere: the altitude a barometer reports."""

    lo, hi = -500.0, 55_000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if isa(mid).pressure_pa > pressure_pa:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --- winds -------------------------------------------------------------------
# Each profile is (altitude_km, speed_m_s, direction_from_deg).  The first
# revision of these tables was estimated from published ranges; it was 30-70 %
# too pessimistic for summer at 20-22 km and 20-25 % too optimistic for winter.
# They are now measured.

WIND_PROFILES: dict[str, tuple[tuple[float, float, float], ...]] = {
    # [cited] Computed by tools/strato_winds.py from NOAA IGRA v2 radiosondes,
    # 2005 onward: the mean of per-station percentiles at Kyiv, Lindenberg,
    # Praha-Libus and Legionowo (about 58,000 soundings; docs/strato/winds.md).
    # Speeds are percentiles of wind speed at each level; directions are the
    # vector-mean bearing.  Two cautions: a stack of per-level 90th
    # percentiles is windier than any real 90th-percentile day (it overstates
    # ascent drift by 10-14 %), and the summer bearing near 20 km is a
    # reversal layer whose mean vector is ~1 m/s, so do not read it as a
    # forecast.
    "midlat-summer-p50": (
        (0, 2.2, 275), (1, 5.9, 275), (2, 7.2, 270), (3, 8.6, 270), (5, 10.8, 265),
        (7, 13.5, 265), (9, 17.1, 265), (10, 18.9, 265), (11, 19.4, 265),
        (12, 17.8, 265), (13, 15.1, 265), (14, 13, 260), (15, 11, 255), (16, 9.2, 255),
        (17, 7.4, 250), (18, 5.8, 245), (19, 4.9, 225), (20, 4.5, 170), (21, 4.3, 120),
        (22, 4.8, 105), (24, 6.1, 100), (26, 7.7, 95), (28, 8.2, 100), (30, 9, 95),
    ),
    "midlat-summer-p90": (
        (0, 4.2, 275), (1, 11.6, 275), (2, 13.2, 270), (3, 15.7, 270), (5, 20.4, 265),
        (7, 26.4, 265), (9, 33.9, 265), (10, 36.7, 265), (11, 36.8, 265),
        (12, 32.9, 265), (13, 27.7, 265), (14, 23.9, 260), (15, 20.1, 255),
        (16, 16.6, 255), (17, 13.7, 250), (18, 10.6, 245), (19, 8.3, 225),
        (20, 7.2, 170), (21, 7.6, 120), (22, 8, 105), (24, 10.2, 100), (26, 11.8, 95),
        (28, 12.5, 100), (30, 13.8, 95),
    ),
    # Winter over Europe has no minimum-wind layer at all: about 18 m/s from
    # 13 to 19 km and rising above.
    "midlat-winter-p50": (
        (0, 3, 245), (1, 9.6, 270), (2, 10.4, 280), (3, 11.8, 285), (5, 15.7, 285),
        (7, 20.2, 290), (9, 23.6, 295), (10, 23.5, 295), (11, 22, 295), (12, 20.1, 295),
        (13, 18.9, 290), (14, 18.1, 290), (15, 18, 290), (16, 18.1, 285),
        (17, 18.1, 285), (18, 18.6, 285), (19, 19.1, 285), (20, 20.2, 285),
        (21, 21.2, 280), (22, 22.6, 280), (24, 26.5, 280), (26, 30.8, 280),
        (28, 36.2, 275), (30, 42.1, 275),
    ),
    "midlat-winter-p90": (
        (0, 5.8, 245), (1, 18.9, 270), (2, 19.7, 280), (3, 21.9, 285), (5, 29.1, 285),
        (7, 38.5, 290), (9, 45.7, 295), (10, 45.8, 295), (11, 42.7, 295),
        (12, 37.1, 295), (13, 32.8, 290), (14, 30.9, 290), (15, 30.7, 290),
        (16, 30.8, 285), (17, 31.6, 285), (18, 33, 285), (19, 34.7, 285),
        (20, 36.8, 285), (21, 39.2, 280), (22, 42, 280), (24, 48.2, 280),
        (26, 55.9, 280), (28, 63.3, 275), (30, 73.3, 275),
    ),
    # May and September only.  The full spring and autumn seasons have long
    # tails (20 km p90 of 18-20 m/s) and are not this calm.
    "midlat-turnaround-p50": (
        (0, 2.2, 270), (1, 6.7, 265), (2, 7.5, 265), (3, 8.6, 270), (5, 11, 270),
        (7, 14.2, 270), (9, 17.6, 270), (10, 18.9, 275), (11, 18.1, 275),
        (12, 15.7, 275), (13, 13.2, 275), (14, 11.3, 270), (15, 9.8, 270),
        (16, 8.5, 265), (17, 7.5, 265), (18, 6.5, 265), (19, 5.8, 265), (20, 5.3, 265),
        (21, 5.1, 265), (22, 5, 270), (24, 5.1, 140), (26, 5.5, 115), (28, 6.4, 200),
        (30, 7.3, 240),
    ),
    "calm": ((0, 0.0, 270), (30, 0.0, 270)),
}


@dataclass(frozen=True)
class Wind:
    """Horizontal wind vector in local North-East axes (m/s, blowing *toward*)."""

    north_m_s: float
    east_m_s: float

    @property
    def speed_m_s(self) -> float:
        return math.hypot(self.north_m_s, self.east_m_s)


class WindProfile:
    """Piecewise-linear wind profile, optionally scaled and rotated.

    ``scale`` multiplies speed at every level and ``veer_deg`` rotates the
    whole profile; the Monte Carlo draws both, which is a crude but honest
    stand-in for day-to-day variability around a climatological shape.
    """

    def __init__(self, name: str = "midlat-summer-p50", scale: float = 1.0,
                 veer_deg: float = 0.0) -> None:
        self.name = name
        self.scale = scale
        self.veer_deg = veer_deg
        self._day = None
        if name.startswith("day:"):
            # "day:<station>:<index>" - one real sounding, see real_days().
            _, station, index = name.split(":")
            data = _load_days(station)
            self._day = data["days"][int(index)]
            self._day_km = data["altitude_km"]
            self._rows = ()
            return
        if name not in WIND_PROFILES:
            raise KeyError(f"unknown wind profile {name!r}")
        self._rows = WIND_PROFILES[name]

    def _at_day(self, altitude_m: float) -> Wind:
        km, u, v = self._day_km, self._day["u"], self._day["v"]
        zk = min(max(altitude_m / 1000.0, km[0]), km[-1])
        i = min(int(zk - km[0]), len(km) - 2)
        f = zk - km[i]
        east = (u[i] + f * (u[i + 1] - u[i])) / 10.0
        north = (v[i] + f * (v[i + 1] - v[i])) / 10.0
        return _rot(Wind(north * self.scale, east * self.scale), self.veer_deg)

    def at(self, altitude_m: float) -> Wind:
        if self._day is not None:
            return self._at_day(altitude_m)
        zk = altitude_m / 1000.0
        rows = self._rows
        if zk <= rows[0][0]:
            spd, direction = rows[0][1], rows[0][2]
        elif zk >= rows[-1][0]:
            spd, direction = rows[-1][1], rows[-1][2]
        else:
            for (z0, s0, d0), (z1, s1, d1) in zip(rows, rows[1:]):
                if z0 <= zk <= z1:
                    f = (zk - z0) / (z1 - z0)
                    # Interpolate the vector, not speed and bearing: a profile
                    # that reverses passes through calm rather than swinging
                    # a full-strength wind around the compass.
                    n0, e0 = _from_dir(s0, d0)
                    n1, e1 = _from_dir(s1, d1)
                    n, e = n0 + f * (n1 - n0), e0 + f * (e1 - e0)
                    return _rot(Wind(n * self.scale, e * self.scale), self.veer_deg)
            raise AssertionError("unreachable")
        n, e = _from_dir(spd, direction)
        return _rot(Wind(n * self.scale, e * self.scale), self.veer_deg)

    def speed(self, altitude_m: float) -> float:
        return self.at(altitude_m).speed_m_s

    def min_wind_layer(self, lo_m: float = 14_000.0, hi_m: float = 26_000.0,
                       step_m: float = 250.0) -> tuple[float, float]:
        """Altitude and speed of the calmest level in a band."""

        best = (lo_m, self.speed(lo_m))
        z = lo_m
        while z <= hi_m:
            s = self.speed(z)
            if s < best[1]:
                best = (z, s)
            z += step_m
        return best


_DAYS_CACHE: dict = {}


def _load_days(station: str) -> dict:
    if station not in _DAYS_CACHE:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                            f"wind_days_{station}.json")
        with open(path) as fh:
            _DAYS_CACHE[station] = json.load(fh)
    return _DAYS_CACHE[station]


def real_days(station: str = "GMM00010393", season: str | None = None,
              months: tuple | None = None) -> list[str]:
    """Profile names for the real soundings on file, optionally filtered.

    Each is one day that actually happened (wind at every kilometre to
    24 km).  Flying these instead of stacked percentile profiles gives the
    Monte Carlo real vertical structure: a windy jet does not imply a windy
    stratosphere, and the two are stacked in the percentile tables.
    """

    out = []
    for i, d in enumerate(_load_days(station)["days"]):
        if season and d["season"] != season:
            continue
        if months and int(d["date"][5:7]) not in months:
            continue
        out.append(f"day:{station}:{i}")
    return out


def _from_dir(speed: float, from_deg: float) -> tuple[float, float]:
    """Meteorological 'from' bearing to a 'toward' N/E vector."""

    rad = math.radians(from_deg)
    return -speed * math.cos(rad), -speed * math.sin(rad)


def _rot(w: Wind, deg: float) -> Wind:
    if deg == 0.0:
        return w
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return Wind(w.north_m_s * c - w.east_m_s * s, w.north_m_s * s + w.east_m_s * c)


class Gust:
    """Three-axis Ornstein-Uhlenbeck gust, the same form the P0 twin uses.

    Stratospheric turbulence is weak but not absent: gravity-wave breaking and
    shear layers give RMS velocities of order 0.3-1 m/s with correlation times
    of tens of seconds [estimate].  The long correlation time is what matters
    to an airship, whose own response time is L/U.
    """

    def __init__(self, sigma_m_s: float = 0.5, tau_s: float = 20.0,
                 vertical_ratio: float = 0.4, seed: int = 0) -> None:
        self.sigma = sigma_m_s
        self.tau = tau_s
        self.vertical_ratio = vertical_ratio
        self._rng = random.Random(seed)
        self.value = [0.0, 0.0, 0.0]
        self.rate = [0.0, 0.0, 0.0]

    def step(self, dt: float) -> tuple[float, float, float]:
        if self.sigma <= 0.0:
            return (0.0, 0.0, 0.0)
        a = math.exp(-dt / self.tau)
        b = math.sqrt(max(0.0, 1.0 - a * a))
        for i in range(3):
            s = self.sigma * (self.vertical_ratio if i == 2 else 1.0)
            new = a * self.value[i] + b * s * self._rng.gauss(0.0, 1.0)
            self.rate[i] = (new - self.value[i]) / dt
            self.value[i] = new
        return (self.value[0], self.value[1], self.value[2])


# --- sun ---------------------------------------------------------------------

SOLAR_CONSTANT = 1361.0  #: W/m2 at 1 AU [physics]


def solar_elevation_deg(latitude_deg: float, day_of_year: int, hour_local_solar: float) -> float:
    """Solar elevation from latitude, day number and local solar time [physics]."""

    decl = math.radians(23.44) * math.sin(2.0 * math.pi * (284 + day_of_year) / 365.0)
    lat = math.radians(latitude_deg)
    hour_angle = math.radians(15.0 * (hour_local_solar - 12.0))
    s = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, s))))


def direct_irradiance_w_m2(altitude_m: float, elevation_deg: float) -> float:
    """Direct-beam irradiance on a sun-normal surface.

    Beer-Lambert with a clear-sky broadband optical depth that scales with the
    overlying air mass [estimate: tau0 = 0.32 at sea level].  At 20 km only
    5.5 % of the atmosphere is above the vehicle, so the answer is within a
    few percent of the solar constant whenever the sun is above the horizon -
    including, importantly, for some time after ground sunset.
    """

    # The horizon dips below the astronomical horizontal with altitude.
    dip = math.degrees(math.acos(R_EARTH / (R_EARTH + max(0.0, altitude_m))))
    if elevation_deg <= -dip:
        return 0.0
    el = max(elevation_deg, 0.5)
    air_mass = 1.0 / (math.sin(math.radians(el)) + 0.50572 * (el + 6.07995) ** -1.6364)
    tau = 0.32 * isa(altitude_m).pressure_pa / _P0
    return SOLAR_CONSTANT * math.exp(-tau * air_mass)
