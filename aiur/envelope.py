"""Envelope sizing for the CARRIER-P0 lifting body.

The carried mass on P0 is not the aircraft.  A guarded Crazyflie 2.1
Brushless with its positioning deck and capture probe is under 50 g; the
active dock, the carrier-side localization, and the wiring reserve are
roughly 330 g between them.  So "size the carrier for this drone" is really
"size the carrier for the smallest carried mass that still recovers this
drone", and the envelope that results is far smaller than a 4.5 m hull.

Three things live here:

* **Physics.**  Ideal-gas densities, net helium lift per cubic metre as a
  function of temperature and purity, and a body-of-revolution hull whose
  profile is the one drawn in ``tools/carrier_model.py`` — volume, wetted
  area, and fineness ratio all come from the same curve, so the twin, the
  renders, and this budget cannot drift apart.
* **A vendor catalog.**  The RC-Zeppelin indoor ladder the program buys from,
  with the payload rating each article is sold with.  Rated payload is the
  ceiling flight hardware is budgeted against (docs/prototype-p0.md); the
  physics is a sanity bound, never a substitute.
* **A selection rule.**  The smallest catalog article whose rated payload
  covers the carried mass plus an explicit reserve.  The reserve is not a
  feeling: it has to absorb at least the dead-weight step of one aircraft
  being captured or released, and a fixed fraction of the rating for ballast
  trim and the vendor's own rounding.

Every coefficient that is not a physical constant or a vendor figure is an
engineering allocation and is labelled as one.  Run ``python -m
aiur.envelope`` for the current numbers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Iterable, Sequence


# --- gas physics --------------------------------------------------------------
#: Specific gas constants, J/(kg K).
R_AIR = 287.05
R_HELIUM = 2077.1

STANDARD_PRESSURE_PA = 101_325.0
#: ISA sea level, matching the constants in aiur/p0.py.
ISA_TEMPERATURE_C = 15.0
#: An indoor hall in use.  The article flies at room temperature, not ISA.
ROOM_TEMPERATURE_C = 20.0
#: Fill purity assumed for a fresh fill from an industrial cylinder that has
#: displaced the air in a new envelope.  Balloon-grade mixtures and a topped
#: up envelope are worse; measured free lift on delivery decides.  Allocation.
FILL_PURITY = 0.97


def gas_density_kg_m3(specific_gas_constant: float, temperature_c: float,
                      pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    if temperature_c <= -273.15:
        raise ValueError("temperature must be above absolute zero")
    if pressure_pa <= 0:
        raise ValueError("pressure must be positive")
    return pressure_pa / (specific_gas_constant * (temperature_c + 273.15))


def air_density_kg_m3(temperature_c: float = ISA_TEMPERATURE_C,
                      pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    return gas_density_kg_m3(R_AIR, temperature_c, pressure_pa)


def helium_density_kg_m3(temperature_c: float = ISA_TEMPERATURE_C,
                         pressure_pa: float = STANDARD_PRESSURE_PA) -> float:
    return gas_density_kg_m3(R_HELIUM, temperature_c, pressure_pa)


def net_lift_kg_per_m3(temperature_c: float = ROOM_TEMPERATURE_C,
                       pressure_pa: float = STANDARD_PRESSURE_PA,
                       purity: float = 1.0) -> float:
    """Static lift of one cubic metre of lifting gas, before any structure.

    Impurity is modelled as air mixed into the helium by volume, which is
    what a leaky fill or a topped-up envelope actually is: the net lift of
    the mixture scales linearly with purity.
    """

    if not 0.0 < purity <= 1.0:
        raise ValueError("purity must be in (0, 1]")
    rho_air = air_density_kg_m3(temperature_c, pressure_pa)
    rho_he = helium_density_kg_m3(temperature_c, pressure_pa)
    return purity * (rho_air - rho_he)


# --- hull geometry -------------------------------------------------------------
@dataclass(frozen=True)
class HullProfile:
    """GNVR-style body of revolution: elliptical nose, maximum section forward
    of mid-body, and an aft body that leaves the maximum section with zero
    slope and tapers to a finite tail-cone radius.

    These are the shape parameters ``tools/carrier_model.py`` draws.  They were
    chosen so the hull reads as an airship and lands at a prismatic
    coefficient inside the 0.6–0.7 band real hulls occupy; they are not from
    a drag study.
    """

    max_section_frac: float = 0.25
    aft_power: float = 2.5
    aft_fullness: float = 0.70
    tail_radius_frac: float = 0.035

    def radius_frac(self, x_frac: float) -> float:
        """Local radius over maximum radius at station ``x_frac`` in [0, 1]."""

        if x_frac <= 0.0 or x_frac >= 1.0:
            return 0.0
        x_max = self.max_section_frac
        if x_frac < x_max:
            u = (x_max - x_frac) / x_max
            return math.sqrt(max(0.0, 1.0 - u * u))
        t = (x_frac - x_max) / (1.0 - x_max)
        k = 1.0 - self.tail_radius_frac ** (1.0 / self.aft_fullness)
        return max(0.0, 1.0 - k * t ** self.aft_power) ** self.aft_fullness

    def prismatic_coefficient(self, steps: int = 4000) -> float:
        """Volume over the circumscribing cylinder: V / (pi R^2 L)."""

        dx = 1.0 / steps
        return sum(self.radius_frac((i + 0.5) * dx) ** 2 for i in range(steps)) * dx

    def wetted_area_coefficient(self, fineness_ratio: float, steps: int = 4000) -> float:
        """Surface area over 2 pi R L, which depends on fineness through the
        slope term of the surface-of-revolution integral."""

        if fineness_ratio <= 0:
            raise ValueError("fineness ratio must be positive")
        # dr/dx in physical units is (R/L) f'(xi) and R/L = 1 / (2 FR).
        slope_scale = 1.0 / (2.0 * fineness_ratio)
        dx = 1.0 / steps
        total = 0.0
        for i in range(steps):
            x0, x1 = i * dx, (i + 1) * dx
            f0, f1 = self.radius_frac(x0), self.radius_frac(x1)
            f_mid = 0.5 * (f0 + f1)
            df = (f1 - f0) / dx * slope_scale
            total += f_mid * math.sqrt(1.0 + df * df) * dx
        return total


DEFAULT_PROFILE = HullProfile()


@dataclass(frozen=True)
class Envelope:
    """A hull of given length and maximum diameter on a fixed profile."""

    length_m: float
    diameter_m: float
    profile: HullProfile = DEFAULT_PROFILE

    def __post_init__(self) -> None:
        if self.length_m <= 0 or self.diameter_m <= 0:
            raise ValueError("length and diameter must be positive")

    @property
    def fineness_ratio(self) -> float:
        return self.length_m / self.diameter_m

    @property
    def volume_m3(self) -> float:
        r = self.diameter_m / 2.0
        return self.profile.prismatic_coefficient() * math.pi * r * r * self.length_m

    @property
    def surface_area_m2(self) -> float:
        r = self.diameter_m / 2.0
        coefficient = self.profile.wetted_area_coefficient(self.fineness_ratio)
        return coefficient * 2.0 * math.pi * r * self.length_m

    @classmethod
    def from_volume(cls, length_m: float, volume_m3: float,
                    profile: HullProfile = DEFAULT_PROFILE) -> "Envelope":
        """The diameter that makes this profile enclose ``volume_m3``."""

        if length_m <= 0 or volume_m3 <= 0:
            raise ValueError("length and volume must be positive")
        cp = profile.prismatic_coefficient()
        radius = math.sqrt(volume_m3 / (cp * math.pi * length_m))
        return cls(length_m, 2.0 * radius, profile)

    @classmethod
    def from_fineness(cls, length_m: float, fineness_ratio: float,
                      profile: HullProfile = DEFAULT_PROFILE) -> "Envelope":
        if fineness_ratio <= 0:
            raise ValueError("fineness ratio must be positive")
        return cls(length_m, length_m / fineness_ratio, profile)


def spheroid_semi_minor_m(length_m: float, volume_m3: float) -> float:
    """Semi-minor axis of the prolate spheroid with this length and volume.

    The digital twin and the site model both use a volume-matched spheroid
    for the keep-out ellipsoid because it is the shape a strike check can
    evaluate in closed form; this is the one place that derivation lives.
    """

    if length_m <= 0 or volume_m3 <= 0:
        raise ValueError("length and volume must be positive")
    return math.sqrt(volume_m3 / ((4.0 / 3.0) * math.pi * (length_m / 2.0)))


# --- mass model ----------------------------------------------------------------
@dataclass(frozen=True)
class EnvelopeMaterial:
    """Film areal density.  Thickness times polymer density, plus a factor
    for seams, load tapes, valves and printing that a bare film figure
    leaves out."""

    name: str
    film_thickness_um: float
    #: Polyurethane film, ~1.2 g/cm^3.
    polymer_density_kg_m3: float = 1200.0
    #: Seams, hoop tapes, fill valve, nose fitting.  Allocation.
    construction_factor: float = 1.15

    @property
    def areal_density_kg_m2(self) -> float:
        return (self.film_thickness_um * 1e-6 * self.polymer_density_kg_m3
                * self.construction_factor)


#: The vendor's indoor envelope film, 100 micron polyurethane.
PU_100_UM = EnvelopeMaterial("polyurethane 100 um", 100.0)
#: The vendor's lightest indoor envelope, on the 1.5 m article.
PU_50_UM = EnvelopeMaterial("polyurethane 50 um", 50.0)


@dataclass(frozen=True)
class CarrierMassModel:
    """Physics net lift of a hull after its own envelope, fins and systems.

    ``systems_mass_kg`` covers what the vendor's RTF article carries that is
    not the envelope: gondola, two vectored motors and a tail motor, ESC,
    receiver, and a 2500 mAh battery.  It is an allocation, not a weighed
    figure, and it does not shrink much with hull size.
    """

    envelope: Envelope
    material: EnvelopeMaterial = PU_100_UM
    #: Tail-surface area as a fraction of hull wetted area.  Allocation.
    fin_area_fraction: float = 0.10
    #: Fins are film over a frame; the frame roughly doubles the film.
    fin_areal_density_kg_m2: float = 2.0 * PU_100_UM.areal_density_kg_m2
    systems_mass_kg: float = 0.60
    lift_kg_per_m3: float = net_lift_kg_per_m3(ROOM_TEMPERATURE_C, purity=FILL_PURITY)

    @property
    def gross_lift_kg(self) -> float:
        return self.envelope.volume_m3 * self.lift_kg_per_m3

    @property
    def envelope_mass_kg(self) -> float:
        return self.envelope.surface_area_m2 * self.material.areal_density_kg_m2

    @property
    def fin_mass_kg(self) -> float:
        return (self.envelope.surface_area_m2 * self.fin_area_fraction
                * self.fin_areal_density_kg_m2)

    @property
    def net_lift_kg(self) -> float:
        """What is left for payload and ballast.  A physics ceiling."""

        return (self.gross_lift_kg - self.envelope_mass_kg - self.fin_mass_kg
                - self.systems_mass_kg)


# --- vendor catalog ------------------------------------------------------------
@dataclass(frozen=True)
class VendorArticle:
    """One purchasable airship and the figures it is sold with.

    ``rated_payload_kg`` is the highest figure the vendor quotes for the
    article; ``rated_payload_low_kg`` the lowest, where the vendor's own pages
    disagree or quote a range.  Selection can be run against either.
    """

    vendor: str
    model: str
    length_m: float
    helium_volume_m3: float
    rated_payload_kg: float
    rated_payload_low_kg: float
    film_thickness_um: float
    price_usd_rtf: float | None
    source: str
    note: str = ""


RC_ZEPPELIN_INDOOR_URL = "https://www.rc-zeppelin.com/indoor-rc-blimps.html"
RC_ZEPPELIN_PRICE_URL = "https://www.rc-zeppelin.com/price-list.html"

#: Vendor figures as published on the pages cited, read 2026-09-14.  The
#: vendor publishes length and helium volume, not diameter; the 3 m and 3.5 m
#: articles share one "~4 m3" figure and the 4.5 m article is quoted at both
#: "750 g" (catalog) and "up to 1 kg" (product page, docs/prototype-p0.md).
RC_ZEPPELIN_INDOOR: tuple[VendorArticle, ...] = (
    VendorArticle("RC-Zeppelin", "1.5 m indoor", 1.5, 1.0, 0.10, 0.10, 50.0, 1640.0,
                  RC_ZEPPELIN_INDOOR_URL, "50 um envelope; lift capacity up to 100 g"),
    VendorArticle("RC-Zeppelin", "2 m indoor", 2.0, 2.5, 0.20, 0.20, 100.0, 1880.0,
                  RC_ZEPPELIN_INDOOR_URL,
                  "vendor quotes volume but no payload; 200 g is an interpolation "
                  "between the 1.5 m and 3 m ratings, not a vendor figure"),
    VendorArticle("RC-Zeppelin", "3 m indoor", 3.0, 4.0, 0.40, 0.30, 100.0, 2450.0,
                  RC_ZEPPELIN_INDOOR_URL, "vendor: 300 to 400 g; volume shared with 3.5 m"),
    VendorArticle("RC-Zeppelin", "3.5 m indoor", 3.5, 4.0, 0.50, 0.40, 100.0, 2644.0,
                  RC_ZEPPELIN_INDOOR_URL, "vendor: up to 500 g (catalog: 400 to 500 g)"),
    VendorArticle("RC-Zeppelin", "B100-I-450-VT 4.5 m indoor", 4.5, 5.5, 1.00, 0.75, 100.0,
                  2820.0, "https://www.rc-zeppelin.com/4.5m-indoor-RC-Blimp.html",
                  "product page: up to 1 kg; catalog page: 750 g"),
    VendorArticle("RC-Zeppelin", "5 m indoor", 5.0, 6.5, 1.20, 1.20, 100.0, 3230.0,
                  RC_ZEPPELIN_PRICE_URL, "1.2 kg payload capacity"),
)


# --- selection -----------------------------------------------------------------
@dataclass(frozen=True)
class ReservePolicy:
    """How much rated payload must remain after the carried allocation.

    ``fraction_of_rating`` absorbs ballast-trim granularity and the vendor's
    rounding; ``floor_kg`` is the largest single dead-weight step the vehicle
    sees in a cycle, which on P0 is one aircraft with its deck and probe
    leaving or arriving.  The reserve is the larger of the two.
    """

    fraction_of_rating: float = 0.10
    floor_kg: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.fraction_of_rating < 1.0:
            raise ValueError("reserve fraction must be in [0, 1)")
        if self.floor_kg < 0:
            raise ValueError("reserve floor must be non-negative")

    def required_reserve_kg(self, rated_payload_kg: float) -> float:
        return max(self.fraction_of_rating * rated_payload_kg, self.floor_kg)

    def minimum_rating_kg(self, carried_mass_kg: float) -> float:
        """Smallest rating that closes: rating >= carried + reserve(rating)."""

        if carried_mass_kg < 0:
            raise ValueError("carried mass must be non-negative")
        return max(carried_mass_kg / (1.0 - self.fraction_of_rating),
                   carried_mass_kg + self.floor_kg)

    def closes(self, rated_payload_kg: float, carried_mass_kg: float) -> bool:
        # A microgram of slack, so a rating computed by ``minimum_rating_kg``
        # closes by construction instead of by floating-point luck.
        margin = rated_payload_kg - carried_mass_kg
        return margin + 1e-9 >= self.required_reserve_kg(rated_payload_kg)


def select_article(
    carried_mass_kg: float,
    policy: ReservePolicy,
    catalog: Sequence[VendorArticle] = RC_ZEPPELIN_INDOOR,
    *,
    conservative: bool = False,
) -> VendorArticle | None:
    """Smallest article (by length) whose rating closes the carried mass.

    ``conservative`` selects against the lowest payload figure the vendor
    quotes instead of the highest.  ``None`` means nothing in the catalog
    closes.
    """

    for article in sorted(catalog, key=lambda a: a.length_m):
        rating = article.rated_payload_low_kg if conservative else article.rated_payload_kg
        if policy.closes(rating, carried_mass_kg):
            return article
    return None


def article_by_length(length_m: float,
                      catalog: Sequence[VendorArticle] = RC_ZEPPELIN_INDOOR) -> VendorArticle:
    for article in catalog:
        if math.isclose(article.length_m, length_m):
            return article
    raise KeyError(f"no catalog article of length {length_m} m")


# --- the P0 article ------------------------------------------------------------
#: The reference flight article: the smallest catalog airship that closes the
#: two-aircraft P0 budget under the reserve policy.  ``aiur.p0`` re-derives
#: this selection from the live budget and tests that it lands here.
P0_ARTICLE = article_by_length(3.5)

#: Volume-matched prolate spheroid semi-axes for the twin's keep-out
#: ellipsoid and the site model.  The vendor does not publish diameter.
P0_SEMI_MAJOR_M = P0_ARTICLE.length_m / 2.0
P0_SEMI_MINOR_M = spheroid_semi_minor_m(P0_ARTICLE.length_m, P0_ARTICLE.helium_volume_m3)


def p0_envelope() -> Envelope:
    """The P0 hull on the drawn profile, at the vendor's length and volume."""

    return Envelope.from_volume(P0_ARTICLE.length_m, P0_ARTICLE.helium_volume_m3)


# --- studies -------------------------------------------------------------------
def length_sweep(
    lengths_m: Iterable[float],
    *,
    fineness_ratio: float,
    material: EnvelopeMaterial = PU_100_UM,
    systems_mass_kg: float = 0.60,
) -> list[dict[str, float]]:
    """Physics net lift versus hull length at fixed fineness and film.

    This is the TOY-004/005 question from docs/verticals/toys.md — at what
    length does an envelope stop lifting a dock — answered with the same
    model, so the toy study and the P0 article share one set of assumptions.
    """

    rows = []
    for length in lengths_m:
        envelope = Envelope.from_fineness(length, fineness_ratio)
        model = CarrierMassModel(envelope, material, systems_mass_kg=systems_mass_kg)
        rows.append({
            "length_m": round(length, 3),
            "diameter_m": round(envelope.diameter_m, 3),
            "volume_m3": round(envelope.volume_m3, 3),
            "surface_area_m2": round(envelope.surface_area_m2, 3),
            "gross_lift_kg": round(model.gross_lift_kg, 3),
            "envelope_mass_kg": round(model.envelope_mass_kg, 3),
            "net_lift_kg": round(model.net_lift_kg, 3),
        })
    return rows


def _article_row(article: VendorArticle) -> dict[str, object]:
    envelope = Envelope.from_volume(article.length_m, article.helium_volume_m3)
    model = CarrierMassModel(
        envelope,
        PU_50_UM if article.film_thickness_um < 75.0 else PU_100_UM,
    )
    physics = model.net_lift_kg
    return {
        **asdict(article),
        "profile_diameter_m": round(envelope.diameter_m, 3),
        "fineness_ratio": round(envelope.fineness_ratio, 2),
        "surface_area_m2": round(envelope.surface_area_m2, 2),
        "gross_lift_kg": round(model.gross_lift_kg, 3),
        "physics_net_lift_kg": round(physics, 3),
        "rating_over_physics": round(article.rated_payload_kg / physics, 2) if physics > 0 else None,
    }


def _summary() -> dict[str, object]:
    # Imported here: aiur.p0 imports this module for the article.
    from .p0 import (
        aircraft_dead_weight_step_kg,
        baseline_p0_budget,
        payload_mass_kg,
        reserve_policy,
    )

    items = baseline_p0_budget()
    carried = payload_mass_kg(items)
    policy = reserve_policy()
    envelope = p0_envelope()
    chosen = select_article(carried, policy)
    chosen_conservative = select_article(carried, policy, conservative=True)
    return {
        "lift_physics": {
            "air_density_20c_kg_m3": round(air_density_kg_m3(ROOM_TEMPERATURE_C), 4),
            "helium_density_20c_kg_m3": round(helium_density_kg_m3(ROOM_TEMPERATURE_C), 4),
            "net_lift_pure_20c_kg_m3": round(net_lift_kg_per_m3(ROOM_TEMPERATURE_C), 4),
            "net_lift_fill_purity_kg_m3": round(
                net_lift_kg_per_m3(ROOM_TEMPERATURE_C, purity=FILL_PURITY), 4),
            "fill_purity_assumed": FILL_PURITY,
        },
        "p0_article": {
            **asdict(P0_ARTICLE),
            "profile_diameter_m": round(envelope.diameter_m, 3),
            "profile_fineness_ratio": round(envelope.fineness_ratio, 2),
            "prismatic_coefficient": round(envelope.profile.prismatic_coefficient(), 3),
            "surface_area_m2": round(envelope.surface_area_m2, 2),
            "spheroid_semi_axes_m": [round(P0_SEMI_MAJOR_M, 3), round(P0_SEMI_MINOR_M, 3),
                                     round(P0_SEMI_MINOR_M, 3)],
        },
        "selection": {
            "carried_mass_kg": round(carried, 4),
            "reserve_policy": asdict(policy),
            "minimum_rating_kg": round(policy.minimum_rating_kg(carried), 4),
            "aircraft_dead_weight_step_kg": round(aircraft_dead_weight_step_kg(), 4),
            "selected_against_vendor_high_figure": chosen.model if chosen else None,
            "selected_against_vendor_low_figure": (
                chosen_conservative.model if chosen_conservative else None),
        },
        "catalog": [_article_row(a) for a in RC_ZEPPELIN_INDOOR],
        "length_sweep_fineness_3": length_sweep(
            (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5), fineness_ratio=3.0),
        "toy_sweep_50um_fineness_2_5_systems_150g": length_sweep(
            (1.0, 1.25, 1.5, 1.75, 2.0), fineness_ratio=2.5, material=PU_50_UM,
            systems_mass_kg=0.15),
    }


if __name__ == "__main__":
    print(json.dumps(_summary(), indent=2))
