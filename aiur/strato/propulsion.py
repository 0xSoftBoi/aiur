"""Propeller and motor at stratospheric density.

A propeller that works at sea level is the wrong propeller at 20 km: density
is 14 times lower, so for the same thrust the disc must be large and the
blade Reynolds number collapses to a few tens of thousands, where section
lift-to-drag is 15-30 rather than 80.  The model is actuator-disc induced
efficiency times a profile efficiency that depends on blade Reynolds number
[physics + estimate], which is enough to size the disc, the shaft power and
the RPM, and to reject a propeller whose tips go transonic.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .atmosphere import Air


@dataclass(frozen=True)
class Propeller:
    diameter_m: float
    blades: int = 2
    #: Mean chord / radius.
    chord_ratio: float = 0.14
    #: Design advance ratio J = V / (n D) at cruise.
    design_advance_ratio: float = 0.55
    mass_kg: float = 0.0
    usd: float = 0.0

    @property
    def disc_area_m2(self) -> float:
        return math.pi * self.diameter_m**2 / 4.0

    def operating_point(self, air: Air, thrust_n: float, airspeed_m_s: float) -> dict:
        """Shaft power, RPM, efficiency and tip Mach for a thrust at a speed."""

        rho = air.density_kg_m3
        a_disc = self.disc_area_m2
        v = max(airspeed_m_s, 0.0)
        t = max(thrust_n, 1e-6)
        # Actuator disc: T = 2 rho A (v + vi) vi
        vi = 0.5 * (-v + math.sqrt(v * v + 2.0 * t / (rho * a_disc)))
        ideal_power = t * (v + vi)
        # Rotational speed: hold design advance ratio in cruise; at low speed
        # the tip speed needed to make the thrust sets RPM instead.
        radius = 0.5 * self.diameter_m
        chord = self.chord_ratio * radius
        n_cruise = v / (self.design_advance_ratio * self.diameter_m) if v > 0.1 else 0.0
        # Blade-loading bound: T ~ 0.5 rho (0.75 Vtip)^2 * blade area * CL_mean
        cl_mean = 0.55
        blade_area = self.blades * chord * radius
        vtip_needed = math.sqrt(t / (0.5 * rho * blade_area * cl_mean)) / 0.75
        n = max(n_cruise, vtip_needed / (math.pi * self.diameter_m))
        vtip = math.pi * self.diameter_m * n
        v_rel = math.hypot(0.75 * vtip, v + vi)
        reynolds = rho * v_rel * chord / air.viscosity_pa_s
        # Section L/D vs Reynolds number for thin cambered low-Re sections
        # [estimate fitted to published low-Re airfoil data: ~12 at 1e4,
        # ~28 at 5e4, ~45 at 2e5].
        l_over_d = max(6.0, min(60.0, 12.0 * (reynolds / 1e4) ** 0.45))
        # Profile efficiency of an element at the 3/4 radius.
        phi = math.atan2(v + vi, 0.75 * vtip)
        eps = 1.0 / l_over_d
        profile = math.tan(phi) / math.tan(phi + eps) if phi > 1e-3 else 0.3
        profile = max(0.2, min(0.98, profile))
        # Swirl and tip losses [estimate].
        shaft_power = ideal_power / (profile * 0.94)
        eta = t * v / shaft_power if shaft_power > 0 else 0.0
        return {
            "thrust_n": t, "airspeed_m_s": v, "shaft_power_w": shaft_power,
            "efficiency": eta, "rpm": n * 60.0, "tip_speed_m_s": vtip,
            "tip_mach": math.hypot(vtip, v) / air.speed_of_sound_m_s,
            "blade_reynolds": reynolds, "induced_velocity_m_s": vi,
            "torque_nm": shaft_power / (2.0 * math.pi * n) if n > 0 else 0.0,
        }


@dataclass(frozen=True)
class Motor:
    """Brushless outrunner, simple three-constant model."""

    name: str
    kv_rpm_per_v: float
    resistance_ohm: float
    no_load_current_a: float
    mass_kg: float
    #: Continuous dissipation it can reject in still sea-level air, W.
    sea_level_dissipation_w: float
    usd: float

    def electrical(self, rpm: float, torque_nm: float, bus_v: float) -> dict:
        kt = 60.0 / (2.0 * math.pi * self.kv_rpm_per_v)
        current = torque_nm / kt + self.no_load_current_a
        volts = rpm / self.kv_rpm_per_v + current * self.resistance_ohm
        p_in = volts * current
        p_out = torque_nm * rpm * 2.0 * math.pi / 60.0
        return {
            "current_a": current, "voltage_v": volts, "input_w": p_in,
            "efficiency": p_out / p_in if p_in > 0 else 0.0,
            "loss_w": p_in - p_out, "duty": volts / bus_v,
            "feasible": volts <= bus_v * 0.95,
        }

    def dissipation_limit_w(self, air: Air) -> float:
        """Heat the motor can shed at altitude.

        Convection scales roughly with density^0.6 in the forced regime; what
        is left is radiation, which does not care about density.  At 20 km a
        motor keeps about a third of its sea-level rating [estimate].
        """

        conv = 0.75 * self.sea_level_dissipation_w * (air.density_kg_m3 / 1.225) ** 0.6
        rad = 0.25 * self.sea_level_dissipation_w
        return conv + rad


#: Large, slow, low-kV multirotor motors are the COTS match for a big thin-air
#: propeller.  Figures are [cited] vendor data where a model is named.
MOTORS = {
    "5008-170kv": Motor("5008 170 kV outrunner", 170.0, 0.190, 0.35, 0.128, 55.0, 55.0),
    "6007-160kv": Motor("6007 160 kV outrunner", 160.0, 0.120, 0.50, 0.185, 80.0, 75.0),
    "8108-100kv": Motor("8108 100 kV outrunner", 100.0, 0.110, 0.60, 0.240, 110.0, 110.0),
    "8318-100kv": Motor("8318 100 kV outrunner", 100.0, 0.060, 0.90, 0.630, 220.0, 190.0),
}

ESC_EFFICIENCY = 0.95


def paschen_margin(bus_v: float, air: Air) -> float:
    """Ratio of the Paschen minimum (~327 V in air) to bus voltage [physics].

    Below ~327 V a gap in air cannot sustain a glow discharge at *any*
    pressure-distance product, so a 6S-12S bus is immune by construction and
    the stratosphere imposes no corona derating.  High-voltage buses lose
    this for free; a low-voltage bus keeps it.
    """

    return 327.0 / bus_v
