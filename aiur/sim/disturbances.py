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
