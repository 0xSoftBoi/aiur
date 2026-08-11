"""Air-motion disturbance models for the CARRIER-P0 digital twin.

Indoor drafts and outdoor wind are both modeled as a mean flow plus a
first-order Gauss-Markov (Ornstein-Uhlenbeck) fluctuation per axis.  The
process is driven by an injected ``random.Random`` so an episode replays
bit-identically from its seed.

Parameter provenance: all values here are engineering estimates until the
twin is calibrated against measured flight data (see docs/digital-twin.md).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from .vec import Vec3


@dataclass(frozen=True)
class AirModelParams:
    """Mean flow plus per-axis fluctuation statistics.

    ``sigma_m_s`` is the stationary standard deviation of each axis of the
    fluctuating component; ``correlation_time_s`` sets how quickly gust
    energy decorrelates.  Vertical fluctuation is scaled separately because
    indoor drafts and outdoor gusts are both strongly anisotropic.
    """

    mean_wind: Vec3 = Vec3()
    sigma_m_s: float = 0.03
    vertical_sigma_scale: float = 0.5
    correlation_time_s: float = 5.0

    def __post_init__(self) -> None:
        if self.sigma_m_s < 0:
            raise ValueError("sigma must be non-negative")
        if self.vertical_sigma_scale < 0:
            raise ValueError("vertical sigma scale must be non-negative")
        if self.correlation_time_s <= 0:
            raise ValueError("correlation time must be positive")


#: Still indoor air with weak HVAC drafts.  Engineering estimate.
INDOOR_CALM = AirModelParams(sigma_m_s=0.03)

#: Indoor air with a deliberate draft source (open door / fan).  Engineering estimate.
INDOOR_DRAFTY = AirModelParams(mean_wind=Vec3(0.15, 0.0, 0.0), sigma_m_s=0.10)


def outdoor_breeze(mean_speed_m_s: float, *, turbulence_fraction: float = 0.25) -> AirModelParams:
    """Outdoor wind preset used by the outdoor-gust-sweep campaign.

    A simple engineering surrogate, not a certified turbulence spectrum:
    fluctuation sigma is a fixed fraction of mean speed, with a shorter
    correlation time than indoor drafts.
    """

    if mean_speed_m_s < 0:
        raise ValueError("mean speed must be non-negative")
    return AirModelParams(
        mean_wind=Vec3(mean_speed_m_s, 0.0, 0.0),
        sigma_m_s=mean_speed_m_s * turbulence_fraction,
        vertical_sigma_scale=0.4,
        correlation_time_s=2.0,
    )


@dataclass(frozen=True)
class CarrierWakeParams:
    """Position-dependent downwash under the carrier's belly dock.

    The scene-wide :class:`AirModel` is spatially uniform; it cannot express
    the one air disturbance that has historically decided aerial recovery —
    the carrier's own wake in the exact volume where capture happens. Every
    mature programme, from the 1930s Sparrowhawk trapeze through the McDonnell
    XF-85 Goblin to DARPA Gremlins' nine near-miss contacts, spent its
    difficulty budget on the mothership's wake, not on the mechanism. A
    buoyant carrier at sub-metre-per-second closing speed has far less of it
    than a C-130, which is the strongest argument for the LTA platform — but
    "less" is not "none", and the twin was silent on it.

    Modelled here as a downward bubble centred on the dock: peak downwash at
    the throat, falling off as a Gaussian horizontally and below. The drone
    approaches the funnel from beneath, so this pushes it *away from the seat*
    at exactly the wrong moment. It is an engineering estimate for an unbuilt
    vehicle, not a measured field, and it is OFF by default (``downwash_m_s``
    zero), so every existing episode is byte-identical.

    Not modelled, and flagged rather than faked: the recirculation
    *turbulence* wake adds on top of the mean downwash (a real second-order
    effect), and the asymmetry of a carrier under way. This is the mean
    field only.
    """

    #: Peak downward air velocity at the dock throat, m/s. Zero disables it.
    downwash_m_s: float = 0.0
    #: Horizontal Gaussian falloff scale, m.
    radius_m: float = 0.30
    #: Vertical Gaussian falloff scale below the dock, m.
    vertical_scale_m: float = 0.40

    def __post_init__(self) -> None:
        if self.downwash_m_s < 0:
            raise ValueError("downwash must be non-negative")
        if self.radius_m <= 0 or self.vertical_scale_m <= 0:
            raise ValueError("wake falloff scales must be positive")

    @property
    def enabled(self) -> bool:
        return self.downwash_m_s > 0.0

    def velocity_at(self, drone_position: Vec3, dock_center: Vec3) -> Vec3:
        """Downwash air velocity the drone sees at its position near the dock."""

        if not self.enabled:
            return Vec3()
        dx = drone_position.x - dock_center.x
        dy = drone_position.y - dock_center.y
        dz = drone_position.z - dock_center.z
        radial = math.exp(-(dx * dx + dy * dy) / (2.0 * self.radius_m * self.radius_m))
        vertical = math.exp(-(dz * dz) / (2.0 * self.vertical_scale_m * self.vertical_scale_m))
        return Vec3(0.0, 0.0, -self.downwash_m_s * radial * vertical)


class AirModel:
    """Stateful seeded air-motion process sampled once per simulation step."""

    def __init__(self, params: AirModelParams, rng: random.Random) -> None:
        self.params = params
        self._rng = rng
        self._fluctuation = Vec3()
        #: Multiplier applied to sigma while a gust fault is active.
        self.gust_multiplier = 1.0

    def step(self, dt_s: float) -> Vec3:
        """Advance the process one step and return the current air velocity."""

        if dt_s <= 0:
            raise ValueError("dt must be positive")

        p = self.params
        alpha = math.exp(-dt_s / p.correlation_time_s)
        # Stationary-variance-preserving discrete OU update.  Note: the
        # gust multiplier scales the drive term, so realized gust variance
        # ramps toward (multiplier * sigma)^2 with time constant tau/2 — a
        # short gust window delivers a ramped fraction of its nominal
        # intensity, which is physically reasonable for gust onset.
        drive = p.sigma_m_s * self.gust_multiplier * math.sqrt(1.0 - alpha * alpha)
        self._fluctuation = Vec3(
            self._fluctuation.x * alpha + drive * self._rng.gauss(0.0, 1.0),
            self._fluctuation.y * alpha + drive * self._rng.gauss(0.0, 1.0),
            self._fluctuation.z * alpha
            + drive * p.vertical_sigma_scale * self._rng.gauss(0.0, 1.0),
        )
        return p.mean_wind + self._fluctuation
