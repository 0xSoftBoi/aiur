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
# Each profile is (altitude_km, speed_m_s, direction_from_deg).  The shape that
# matters is universal at mid-latitudes: a tropospheric jet near 10-12 km, a
# minimum-wind layer near 18-21 km, and winds that build again above it.  The
# *level* depends on season and percentile.  Values are [estimate] anchored on
# the published envelope (docs/strato/references.md, "winds"): typically
# 5-15 m/s in the 18-22 km layer, 95th percentile under ~26 m/s outside
# winter, and 99th percentile 35-53 m/s in the worst season.  Replace with
# ERA5 or IGRA statistics for the actual site before committing to a flight.

WIND_PROFILES: dict[str, tuple[tuple[float, float, float], ...]] = {
    # 50N continental site, June-August.  The stratosphere is in its summer
    # easterly regime and the minimum-wind layer is at its calmest.
    "midlat-summer-p50": (
        (0, 3, 250), (1.5, 6, 255), (5, 12, 265), (9, 19, 270), (11.5, 22, 270),
        (14, 13, 270), (16, 8, 275), (18, 6, 300), (20, 6, 80), (22, 8, 90),
        (25, 11, 90), (30, 16, 90),
    ),
    "midlat-summer-p90": (
        (0, 7, 250), (1.5, 12, 255), (5, 22, 265), (9, 34, 270), (11.5, 40, 270),
        (14, 24, 270), (16, 15, 275), (18, 12, 290), (20, 12, 80), (22, 14, 90),
        (25, 18, 90), (30, 24, 90),
    ),
    # 50N, December-February.  Stronger jet, and the polar-night jet reaches
    # down into the 20 km layer: there is no calm layer to hide in.
    "midlat-winter-p50": (
        (0, 4, 240), (1.5, 9, 250), (5, 20, 265), (9, 32, 270), (11, 36, 270),
        (14, 24, 270), (16, 17, 270), (18, 15, 270), (20, 15, 270), (22, 18, 270),
        (25, 24, 270), (30, 35, 270),
    ),
    "midlat-winter-p90": (
        (0, 9, 240), (1.5, 16, 250), (5, 34, 265), (9, 55, 270), (11, 62, 270),
        (14, 40, 270), (16, 30, 270), (18, 27, 270), (20, 28, 270), (22, 32, 270),
        (25, 40, 270), (30, 55, 270),
    ),
    # Shoulder seasons: the stratospheric wind reverses and passes through
    # near-zero ("turnaround"), the classic long-duration balloon window.
    "midlat-turnaround-p50": (
        (0, 3, 250), (1.5, 7, 255), (5, 15, 265), (9, 24, 270), (11.5, 28, 270),
        (14, 16, 270), (16, 9, 270), (18, 6, 270), (20, 5, 250), (22, 5, 120),
        (25, 5, 100), (30, 8, 90),
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
        if name not in WIND_PROFILES:
            raise KeyError(f"unknown wind profile {name!r}")
        self.name = name
        self.scale = scale
        self.veer_deg = veer_deg
        self._rows = WIND_PROFILES[name]

    def at(self, altitude_m: float) -> Wind:
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
