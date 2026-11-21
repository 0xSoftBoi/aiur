"""Envelope films and structural materials.

Areal density and strength are what size a stratospheric envelope; price per
square metre is what decides whether it can be built in quantity.  Strength is
carried as a *running* load (N per metre of width at break) because that is
how film is tested and how hoop load is computed.

Every entry is [cited] or [estimate] per docs/strato/references.md.  The
``allowable_fraction`` is the knock-down from short-term ultimate to a
sustained working load: thin polymer films creep and their seams are weaker
than parent film, so the usable fraction is small.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Film:
    name: str
    areal_density_kg_m2: float
    ultimate_n_per_m: float
    usd_per_m2: float
    #: Lowest temperature at which the film stays ductile, K.
    min_temp_k: float
    #: Solar absorptance and thermal-IR emittance of the inflated cell.
    solar_absorptance: float
    ir_emittance: float
    #: Hydrogen permeance, litres per m2 per day per atmosphere at ~20 C.
    h2_permeance_l_m2_day_atm: float
    #: Fraction of ultimate usable as sustained membrane load incl. seams.
    allowable_fraction: float = 0.25
    seam: str = "heat seal"
    note: str = ""

    @property
    def allowable_n_per_m(self) -> float:
        return self.ultimate_n_per_m * self.allowable_fraction


FILMS: dict[str, Film] = {
    # Balloon-grade linear low-density polyethylene.  The material of every
    # zero-pressure scientific balloon; ductile to below -80 C.
    "lldpe-20um": Film("LLDPE balloon film 20 um", 0.0184, 500.0, 0.45, 180.0,
                       0.03, 0.18, 9.0, 0.20, "impulse heat seal",
                       "StratoFilm-class; commodity co-ex is the cheap stand-in"),
    "lldpe-38um": Film("LLDPE balloon film 38 um", 0.0350, 950.0, 0.80, 180.0,
                       0.04, 0.27, 5.0, 0.20, "impulse heat seal"),
    # Co-extruded PE/EVOH/PE: the 'foil balloon' barrier family without metal.
    "pe-evoh-30um": Film("PE/EVOH/PE barrier 30 um", 0.0290, 900.0, 1.20, 200.0,
                         0.04, 0.30, 0.3, 0.22, "impulse heat seal",
                         "EVOH loses barrier when wet; dry stratosphere suits it"),
    # Biaxial PET: strong and stiff, poor tear, needs taped/adhesive seams.
    "pet-12um": Film("BoPET 12 um", 0.0167, 2000.0, 0.50, 200.0,
                     0.06, 0.35, 1.2, 0.15, "adhesive tape",
                     "strong but notch-sensitive; pinholes on folding"),
    "pet-al-12um": Film("Aluminised BoPET 12 um", 0.0170, 2000.0, 0.60, 200.0,
                        0.12, 0.05, 0.4, 0.15, "adhesive tape",
                        "alpha/epsilon > 2: runs hot in sun"),
    # Thermoplastic polyurethane: the P0 indoor envelope material.
    "tpu-50um": Film("TPU film 50 um", 0.0600, 2000.0, 3.50, 230.0,
                     0.25, 0.85, 4.0, 0.25, "RF or heat weld",
                     "glass transition near -40 C: marginal in the stratosphere"),
    # Coated ripstop: real airship fabric at the light end.
    "nylon-tpu-70gsm": Film("TPU-coated 20D nylon ripstop", 0.0700, 9000.0, 9.00, 215.0,
                            0.30, 0.85, 3.0, 0.25, "heat weld + tape",
                            "weldable, tear-stopped; the low-altitude trainer skin"),
    # Ultra-high-molecular-weight PE laminate (Dyneema composite fabric).
    "dcf-18gsm": Film("UHMWPE laminate 18 g/m2", 0.0180, 7900.0, 38.0, 180.0,
                      0.10, 0.40, 0.8, 0.20, "bonded tape",
                      "PET-faced UHMWPE grid; superb strength/mass, expensive"),
    "dcf-34gsm": Film("UHMWPE laminate 34 g/m2", 0.0340, 15000.0, 45.0, 180.0,
                      0.10, 0.45, 0.6, 0.20, "bonded tape"),
}


@dataclass(frozen=True)
class LatexBalloon:
    """COTS meteorological sounding balloon [cited: vendor burst tables]."""

    name: str
    mass_kg: float
    burst_diameter_m: float
    usd: float
    #: Internal overpressure from the stretched skin, Pa [estimate].
    skin_pressure_pa: float = 120.0

    @property
    def burst_volume_m3(self) -> float:
        return 3.14159265 / 6.0 * self.burst_diameter_m**3


LATEX: dict[str, LatexBalloon] = {
    "600g": LatexBalloon("600 g sounding balloon", 0.6, 6.0, 55.0),
    "1200g": LatexBalloon("1200 g sounding balloon", 1.2, 8.6, 110.0),
    "1600g": LatexBalloon("1600 g sounding balloon", 1.6, 10.5, 160.0),
    "2000g": LatexBalloon("2000 g sounding balloon", 2.0, 10.5, 230.0),
    "3000g": LatexBalloon("3000 g sounding balloon", 3.0, 13.0, 420.0),
}


@dataclass(frozen=True)
class Tube:
    """Pultruded carbon tube, the cheap straight structural member."""

    od_m: float
    wall_m: float
    density_kg_m3: float = 1600.0
    modulus_pa: float = 110e9
    allowable_pa: float = 400e6
    usd_per_m: float = 9.0

    @property
    def mass_per_m(self) -> float:
        import math
        return math.pi * (self.od_m - self.wall_m) * self.wall_m * self.density_kg_m3

    @property
    def second_moment_m4(self) -> float:
        import math
        return math.pi / 64.0 * (self.od_m**4 - (self.od_m - 2 * self.wall_m) ** 4)

    @property
    def allowable_moment_nm(self) -> float:
        return self.allowable_pa * self.second_moment_m4 / (self.od_m / 2.0)

    @property
    def ei_nm2(self) -> float:
        return self.modulus_pa * self.second_moment_m4
