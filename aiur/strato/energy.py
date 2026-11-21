"""Solar array and cold battery.

The array lies on the upper hull, so it never faces the sun squarely; the
battery sits at -56 C ambient and must be kept warm or it delivers a fraction
of its rated energy.  Both effects are first-order for a small vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .atmosphere import direct_irradiance_w_m2, solar_elevation_deg


@dataclass(frozen=True)
class SolarArray:
    name: str
    #: Cell efficiency at 25 C under AM1.5.
    efficiency: float
    areal_density_kg_m2: float
    usd_per_m2: float
    #: Relative power gain per kelvin below 25 C.
    temp_coeff_per_k: float = 0.0030
    #: Fraction of AM1.5 efficiency retained under the AM0 spectrum.
    am0_factor: float = 0.90


ARRAYS = {
    # Back-contact mono-Si cells laminated in thin ETFE/PET, no glass.
    "mono-si-laminate": SolarArray("Back-contact Si cells in film laminate",
                                   0.225, 0.85, 260.0),
    # Flexible CIGS on polyimide or steel foil.
    "cigs-flex": SolarArray("Flexible CIGS", 0.165, 0.45, 420.0),
}


def array_power_w_per_m2(array: SolarArray, altitude_m: float, elevation_deg: float,
                         cell_temp_k: float = 250.0, tilt_spread_deg: float = 35.0) -> float:
    """Output per square metre of array draped over the top of a hull.

    The array wraps +/- ``tilt_spread_deg`` around the top; with the sun at
    elevation ``el`` the mean cosine over that arc is sin(el) * sinc-like
    factor for a heading-averaged vehicle.  Averaging over heading is the
    honest assumption for a vehicle that points into the wind, not the sun.
    """

    sun = direct_irradiance_w_m2(altitude_m, elevation_deg)
    if sun <= 0.0:
        return 0.0
    el = math.radians(max(elevation_deg, 0.0))
    spread = math.radians(tilt_spread_deg)
    # Panels tilted by phi in [-spread, spread] about the roll axis, sun at
    # random azimuth: mean cos(incidence) clipped at zero ~ sin(el)*sin(s)/s
    # plus a cos(el) term that averages to (2/pi)*(1-cos(s))/s over azimuth.
    mean_cos = (math.sin(el) * math.sin(spread) / spread
                + math.cos(el) * (2.0 / math.pi) * (1.0 - math.cos(spread)) / spread * 0.5)
    eff = array.efficiency * array.am0_factor * (
        1.0 + array.temp_coeff_per_k * (298.15 - cell_temp_k))
    return sun * mean_cos * eff * 0.95  # 5 % wiring/MPPT [estimate]


def daily_array_energy_wh_per_m2(array: SolarArray, altitude_m: float, latitude_deg: float,
                                 day_of_year: int) -> tuple[float, float]:
    """(Wh per m2 per day, hours with usable sun)."""

    total = 0.0
    lit = 0.0
    step_h = 0.1
    h = 0.0
    while h < 24.0:
        el = solar_elevation_deg(latitude_deg, day_of_year, h)
        p = array_power_w_per_m2(array, altitude_m, el)
        if p > 5.0:
            lit += step_h
        total += p * step_h
        h += step_h
    return total, lit


@dataclass(frozen=True)
class Cell:
    """Cylindrical Li-ion cell [cited: vendor datasheets]."""

    name: str
    capacity_ah: float
    nominal_v: float
    mass_kg: float
    max_continuous_a: float
    usd: float

    @property
    def energy_wh(self) -> float:
        return self.capacity_ah * self.nominal_v

    def capacity_fraction(self, cell_temp_c: float) -> float:
        """Deliverable fraction of rated energy vs cell temperature.

        Piecewise fit to published low-rate discharge curves for high-energy
        21700 cells [estimate]: 100 % at 25 C, ~88 % at 0 C, ~70 % at -20 C,
        ~35 % at -40 C.  The lesson is not the exact curve; it is that an
        unheated pack at -56 C is nearly useless, so the bay is insulated.
        """

        pts = ((-50.0, 0.10), (-40.0, 0.35), (-20.0, 0.70), (0.0, 0.88),
               (25.0, 1.0), (45.0, 1.0))
        t = cell_temp_c
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        for (t0, f0), (t1, f1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                return f0 + (f1 - f0) * (t - t0) / (t1 - t0)
        return 1.0


CELLS = {
    "21700-5.0Ah": Cell("21700 5.0 Ah high-energy (Samsung 50S class)",
                        5.0, 3.6, 0.069, 25.0, 5.5),
    "21700-4.5Ah": Cell("21700 4.5 Ah high-power (Molicel P45B class)",
                        4.5, 3.6, 0.070, 45.0, 6.5),
}


@dataclass(frozen=True)
class Pack:
    cell: Cell
    series: int
    parallel: int
    #: Strip, wire, wrap, connector, balance lead: fraction of cell mass.
    overhead: float = 0.12

    @property
    def nominal_v(self) -> float:
        return self.series * self.cell.nominal_v

    @property
    def mass_kg(self) -> float:
        return self.series * self.parallel * self.cell.mass_kg * (1.0 + self.overhead)

    @property
    def cells(self) -> int:
        return self.series * self.parallel

    def usable_wh(self, cell_temp_c: float = 15.0, depth_of_discharge: float = 0.85) -> float:
        return (self.cells * self.cell.energy_wh
                * self.cell.capacity_fraction(cell_temp_c) * depth_of_discharge)

    @property
    def usd(self) -> float:
        return self.cells * self.cell.usd * 1.25  # strip, wrap, lead, labour [estimate]


def pack_for_energy(cell: Cell, series: int, energy_wh: float,
                    cell_temp_c: float = 15.0) -> Pack:
    """Smallest S x P pack that delivers ``energy_wh`` usable."""

    p = 1
    while Pack(cell, series, p).usable_wh(cell_temp_c) < energy_wh and p < 400:
        p += 1
    return Pack(cell, series, p)
