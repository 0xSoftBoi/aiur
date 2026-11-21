"""Hull geometry, added mass and aerodynamic derivatives.

The hull is a body of revolution on the same low-drag profile the P0 renders
use (``tools/carrier_model.py``): an elliptical nose to the maximum section at
0.25 L and a power-law afterbody.  Here the fineness ratio is a free variable,
because at stratospheric Reynolds numbers and with envelope mass dominating
the budget the best fineness is not the sea-level answer.

Aerodynamics follow the standard airship decomposition [cited: Lamb 1918 for
added mass; Munk 1924 for the unstable moment; Allen & Perkins 1951 for
viscous crossflow; Jones & DeLaurier 1983 for the assembly]:

* potential flow gives added mass and the destabilising Munk moment;
* viscous crossflow on the afterbody gives lift and damping;
* fins give the stabilising and control forces;
* axial drag is a volumetric coefficient with a Reynolds-number correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

MAX_SECTION_X = 0.25
AFT_POWER = 2.5
AFT_FULLNESS = 0.70
TAIL_RADIUS_FRAC = 0.035


def profile(xi: float) -> float:
    """Radius / max radius at fractional station ``xi`` measured from the nose."""

    if xi <= 0.0 or xi >= 1.0:
        return 0.0
    if xi < MAX_SECTION_X:
        u = (MAX_SECTION_X - xi) / MAX_SECTION_X
        return math.sqrt(max(0.0, 1.0 - u * u))
    t = (xi - MAX_SECTION_X) / (1.0 - MAX_SECTION_X)
    k = 1.0 - TAIL_RADIUS_FRAC ** (1.0 / AFT_FULLNESS)
    return max(0.0, 1.0 - k * t**AFT_POWER) ** AFT_FULLNESS


@lru_cache(maxsize=None)
def _shape_integrals(fineness: float, n: int = 2000) -> tuple[float, float, float, float]:
    """(volume coeff, area coeff, centroid fraction, radius-of-gyration^2 coeff)."""

    d = 1.0 / n
    vol = area = mom = iyy = 0.0
    slope_scale = 0.5 / fineness  # R/L
    for i in range(n):
        x0, x1 = i * d, (i + 1) * d
        r0, r1 = profile(x0), profile(x1)
        rm = 0.5 * (r0 + r1)
        xm = 0.5 * (x0 + x1)
        vol += rm * rm * d
        ds = math.hypot(d, (r1 - r0) * slope_scale)
        area += rm * ds
        mom += rm * rm * xm * d
        iyy += rm * rm * xm * xm * d
    return vol, area, mom / vol, iyy / vol


@dataclass(frozen=True)
class Hull:
    """A sized hull.  ``x`` stations are metres aft of the nose."""

    volume_m3: float
    fineness: float

    @property
    def diameter_m(self) -> float:
        cv = _shape_integrals(self.fineness)[0]
        # V = pi R^2 L cv,  L = fineness * 2R
        return 2.0 * (self.volume_m3 / (2.0 * math.pi * self.fineness * cv)) ** (1.0 / 3.0)

    @property
    def radius_m(self) -> float:
        return 0.5 * self.diameter_m

    @property
    def length_m(self) -> float:
        return self.fineness * self.diameter_m

    @property
    def surface_area_m2(self) -> float:
        ca = _shape_integrals(self.fineness)[1]
        return 2.0 * math.pi * self.radius_m * self.length_m * ca

    @property
    def prismatic_coefficient(self) -> float:
        return _shape_integrals(self.fineness)[0]

    @property
    def centre_of_volume_m(self) -> float:
        """Centre of buoyancy, metres aft of the nose."""

        return _shape_integrals(self.fineness)[2] * self.length_m

    @property
    def reference_area_m2(self) -> float:
        return self.volume_m3 ** (2.0 / 3.0)

    def radius_at(self, x_m: float) -> float:
        return self.radius_m * profile(x_m / self.length_m)

    def stations(self, count: int = 24) -> list[tuple[float, float, float]]:
        """(x from nose, local radius, strip length) for strip integration."""

        dx = self.length_m / count
        return [((i + 0.5) * dx, self.radius_at((i + 0.5) * dx), dx) for i in range(count)]

    # --- potential flow ------------------------------------------------------
    def lamb_factors(self) -> tuple[float, float, float]:
        """Lamb's inertia factors (k1 axial, k2 lateral, k' rotational).

        Evaluated for the prolate spheroid of the same fineness [cited: Lamb,
        Hydrodynamics art. 114-115].  k1 falls and k2 rises toward 1 as the
        body gets slimmer; (k2 - k1) sets the Munk moment.
        """

        f = max(self.fineness, 1.0001)
        e = math.sqrt(1.0 - 1.0 / (f * f))
        ln = math.log((1.0 + e) / (1.0 - e))
        alpha0 = 2.0 * (1.0 - e * e) / e**3 * (0.5 * ln - e)
        beta0 = 1.0 / (e * e) - (1.0 - e * e) / (2.0 * e**3) * ln
        k1 = alpha0 / (2.0 - alpha0)
        k2 = beta0 / (2.0 - beta0)
        kp = e**4 * (beta0 - alpha0) / (
            (2.0 - e * e) * (2.0 * e * e - (2.0 - e * e) * (beta0 - alpha0)))
        return k1, k2, kp

    def displaced_inertia_coeff(self) -> float:
        """Transverse radius of gyration squared of the displaced air, m2."""

        _, _, cx, cxx = _shape_integrals(self.fineness)
        length = self.length_m
        about_cv = (cxx - cx * cx) * length * length
        return about_cv + 0.25 * self.radius_m**2 * 0.6

    # --- viscous -------------------------------------------------------------
    def drag_coefficient(self, reynolds: float, roughness_factor: float = 1.25) -> float:
        """Volumetric drag coefficient C_DV (referenced to V^(2/3)).

        Hoerner's streamlined-body form [cited: Fluid-Dynamic Drag, 6-16]:
        skin friction times a fineness form factor, converted from wetted to
        volumetric reference.  Friction is blended between laminar and
        turbulent across transition - a clean, slow, stratospheric hull sits
        at Re ~ 1e6 where that blend matters by a factor of two, so it is
        modelled rather than assumed.  ``roughness_factor`` covers seams,
        wrinkles in thin film, load patches and rigging [estimate].
        """

        re = max(reynolds, 1e3)
        cf_lam = 1.328 / math.sqrt(re)
        cf_turb = 0.455 / (math.log10(re) ** 2.58)
        # Transition band 3e5 .. 3e6 on length Reynolds number.
        w = min(1.0, max(0.0, (math.log10(re) - 5.5) / 1.0))
        cf = (1.0 - w) * cf_lam + w * cf_turb
        fr = self.fineness
        form = 1.0 + 1.5 / fr**1.5 + 7.0 / fr**3
        return roughness_factor * cf * form * self.surface_area_m2 / self.reference_area_m2

    def drag_n(self, density: float, airspeed: float, viscosity: float,
               extra_cd_area_m2: float = 0.0) -> float:
        if airspeed <= 0.0:
            return 0.0
        re = density * airspeed * self.length_m / viscosity
        q = 0.5 * density * airspeed * airspeed
        return q * (self.drag_coefficient(re) * self.reference_area_m2 + extra_cd_area_m2)


def sphere_drag_coefficient(reynolds: float) -> float:
    """Sphere drag through the drag crisis [cited: Hoerner 3-8; Achenbach 1972].

    A big balloon at float sits right on the crisis (Re ~ 3e5), which is why
    the coefficient is a function and not the textbook 0.47.  A tethered or
    rigged sphere has trips everywhere, so the supercritical floor is taken
    at a conservative 0.25 rather than the smooth-sphere 0.1.
    """

    re = max(reynolds, 1.0)
    if re < 2.0e5:
        return 0.47
    if re > 5.0e5:
        return 0.25
    f = (math.log10(re) - math.log10(2.0e5)) / (math.log10(5.0e5) - math.log10(2.0e5))
    return 0.47 + f * (0.25 - 0.47)
