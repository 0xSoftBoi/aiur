"""Film and lift-gas thermal balance.

A balloon's lift follows its gas temperature, and the gas temperature follows
the film.  By day the film absorbs sunlight and Earth's infrared and runs
warmer than the air ("superheat"); at night it radiates to space and runs
colder ("supercooling").  For a zero-pressure cell that swing is the whole
overnight problem: cooling by 5 % of absolute temperature removes 5 % of the
lift.

The film has negligible heat capacity, so it is solved quasi-steadily; the
gas is a single lumped node.  Fluxes and coefficients are [estimate] in the
ranges used by published balloon thermal codes (see references, "thermal").
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .atmosphere import Air, SIGMA_SB, direct_irradiance_w_m2


@dataclass(frozen=True)
class RadiativeEnvironment:
    """Radiation seen by a body at float."""

    #: Upwelling thermal IR from Earth and lower atmosphere, W/m2.
    earth_ir_w_m2: float = 220.0
    #: Downwelling IR from the thin atmosphere above, W/m2.
    sky_ir_w_m2: float = 15.0
    #: Planetary albedo for reflected sunlight.
    albedo: float = 0.30


@dataclass(frozen=True)
class FilmOptics:
    solar_absorptance: float
    ir_emittance: float


def external_h_w_m2k(air: Air, length_m: float, airspeed_m_s: float,
                     delta_t_k: float = 10.0) -> float:
    """External convection coefficient: the larger of forced and natural.

    Forced: turbulent flat-plate average, Nu = 0.037 Re^0.8 Pr^(1/3).
    Natural: sphere/large-body, Nu = 0.13 Ra^(1/3)  [physics correlations].
    """

    k = air.conductivity_w_mk
    nu = air.viscosity_pa_s / air.density_kg_m3
    re = max(airspeed_m_s, 0.0) * length_m / nu
    forced = 0.037 * re**0.8 * 0.89 * k / length_m if re > 0 else 0.0
    beta = 1.0 / air.temperature_k
    alpha = nu / 0.71
    ra = 9.81 * beta * max(abs(delta_t_k), 0.5) * length_m**3 / (nu * alpha)
    natural = 0.13 * ra ** (1.0 / 3.0) * k / length_m
    return max(forced, natural)


def film_temperature_k(air: Air, optics: FilmOptics, gas_temperature_k: float,
                       sun_w_m2: float, sun_elevation_deg: float,
                       h_ext: float, h_int: float,
                       env: RadiativeEnvironment = RadiativeEnvironment()) -> float:
    """Quasi-steady mean film temperature of a convex cell.

    Per unit of total surface area S: the sun sees S/4 (mean projected area of
    a convex body); the lower half sees Earth and the upper half sees sky.
    """

    a, e = optics.solar_absorptance, optics.ir_emittance
    el = max(0.0, math.sin(math.radians(max(sun_elevation_deg, 0.0))))
    solar = a * sun_w_m2 * (0.25 + 0.5 * env.albedo * el * 0.5)
    ir_in = e * 0.5 * (env.earth_ir_w_m2 + env.sky_ir_w_m2)

    def net(tf: float) -> float:
        return (solar + ir_in - e * SIGMA_SB * tf**4
                + h_ext * (air.temperature_k - tf) + h_int * (gas_temperature_k - tf))

    lo, hi = 120.0, 420.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if net(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def equilibrium_supertemperature_k(air: Air, optics: FilmOptics, length_m: float,
                                   airspeed_m_s: float, sun_elevation_deg: float,
                                   h_int: float = 2.5,
                                   env: RadiativeEnvironment = RadiativeEnvironment()) -> float:
    """Steady gas-minus-ambient temperature at float.

    At equilibrium the gas sits at film temperature, so the internal
    coefficient drops out and this is purely the film balance.
    """

    sun = direct_irradiance_w_m2(air.altitude_m, sun_elevation_deg)
    tg = air.temperature_k
    for _ in range(6):
        h_ext = external_h_w_m2k(air, length_m, airspeed_m_s, tg - air.temperature_k)
        tg = film_temperature_k(air, optics, tg, sun, sun_elevation_deg, h_ext, 0.0, env)
    return tg - air.temperature_k


def bay_heater_power_w(internal_w: float, target_k: float, ambient_k: float,
                       box_area_m2: float, insulation_m: float,
                       k_insulation: float = 0.030) -> float:
    """Extra heater power to hold an insulated avionics bay at ``target_k``.

    Conduction through foam is the only loss path modelled; at 5 kPa the
    outer-surface convection is so weak that the foam, not the film
    coefficient, sets the answer.  XPS foam k = 0.030 W/mK [cited].
    """

    loss = k_insulation * box_area_m2 * (target_k - ambient_k) / insulation_m
    return max(0.0, loss - internal_w)
