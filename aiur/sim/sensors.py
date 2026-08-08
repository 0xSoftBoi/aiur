"""Sensor and actuator models for the CARRIER-P0 digital twin.

The twin models the measurement chain, not just truth: the guidance stack
only ever sees ``PoseMeasurement`` objects with noise, latency, and dropouts,
and the real ``DockController`` only ever sees debounced switch outputs that
can be forced into stuck faults.

Noise figures for the Lighthouse-grade preset are engineering estimates of
millimeter-class external optical positioning; they must be replaced by
measured residuals during twin calibration (docs/digital-twin.md).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import random

from .vec import Vec3


@dataclass(frozen=True)
class PoseSensorParams:
    """Timing note: latency and debounce are modeled on the simulation grid
    (rounded to whole steps at the engine dt), so choose values that are
    integer multiples of dt to get exact behavior."""

    position_sigma_m: float = 0.003
    velocity_sigma_m_s: float = 0.010
    latency_s: float = 0.04
    #: Probability per second of a short spontaneous dropout.
    dropout_rate_per_s: float = 0.02
    dropout_duration_s: float = 0.15

    def __post_init__(self) -> None:
        if min(self.position_sigma_m, self.velocity_sigma_m_s) < 0:
            raise ValueError("noise sigmas must be non-negative")
        if self.latency_s < 0:
            raise ValueError("latency must be non-negative")
        if self.dropout_rate_per_s < 0 or self.dropout_duration_s < 0:
            raise ValueError("dropout parameters must be non-negative")


#: External optical (Lighthouse-class) reference.  Engineering estimate.
LIGHTHOUSE_GRADE = PoseSensorParams()

#: Consumer-grade terminal navigation (toy vertical study).  Engineering estimate.
TOY_GRADE = PoseSensorParams(
    position_sigma_m=0.030,
    velocity_sigma_m_s=0.060,
    latency_s=0.10,
    dropout_rate_per_s=0.10,
    dropout_duration_s=0.30,
)


def scaled_sensor(base: PoseSensorParams, noise_scale: float) -> PoseSensorParams:
    """Scale position/velocity noise for the degraded-sensor-sweep campaign."""

    if noise_scale <= 0:
        raise ValueError("noise scale must be positive")
    return PoseSensorParams(
        position_sigma_m=base.position_sigma_m * noise_scale,
        velocity_sigma_m_s=base.velocity_sigma_m_s * noise_scale,
        latency_s=base.latency_s,
        dropout_rate_per_s=base.dropout_rate_per_s,
        dropout_duration_s=base.dropout_duration_s,
    )


@dataclass(frozen=True)
class PoseMeasurement:
    position: Vec3
    velocity: Vec3
    valid: bool
    age_s: float


class PoseSensor:
    """Noisy, delayed, dropout-prone pose source for one body."""

    def __init__(self, params: PoseSensorParams, rng: random.Random, dt_s: float) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self.params = params
        self._rng = rng
        self._dt_s = dt_s
        delay_steps = max(0, round(params.latency_s / dt_s))
        self._buffer: deque[tuple[Vec3, Vec3]] = deque(maxlen=delay_steps + 1)
        self._outage_remaining_s = 0.0
        #: Held true by the fault injector for scheduled outages.
        self.forced_outage = False
        #: Additive position bias injected by the fault injector.
        self.bias = Vec3()
        self._last_position = Vec3()
        self._last_velocity = Vec3()
        self._age_s = float("inf")

    def _noisy(self, sigma: float) -> Vec3:
        return Vec3(
            self._rng.gauss(0.0, sigma),
            self._rng.gauss(0.0, sigma),
            self._rng.gauss(0.0, sigma),
        )

    def step(self, true_position: Vec3, true_velocity: Vec3) -> PoseMeasurement:
        p = self.params
        self._buffer.append((true_position, true_velocity))
        delayed_position, delayed_velocity = self._buffer[0]

        if self._outage_remaining_s > 0.0:
            self._outage_remaining_s -= self._dt_s
        elif self._rng.random() < p.dropout_rate_per_s * self._dt_s:
            self._outage_remaining_s = p.dropout_duration_s

        valid = self._outage_remaining_s <= 0.0 and not self.forced_outage
        if valid:
            self._last_position = delayed_position + self.bias + self._noisy(p.position_sigma_m)
            self._last_velocity = delayed_velocity + self._noisy(p.velocity_sigma_m_s)
            self._age_s = p.latency_s
        else:
            self._age_s += self._dt_s

        return PoseMeasurement(
            position=self._last_position,
            velocity=self._last_velocity,
            valid=valid,
            age_s=self._age_s,
        )


class SwitchFault(str, Enum):
    NONE = "none"
    STUCK_OPEN = "stuck_open"
    STUCK_CLOSED = "stuck_closed"


class Switch:
    """Debounced physical switch with injectable stuck faults."""

    def __init__(self, *, debounce_s: float = 0.02, dt_s: float = 0.02) -> None:
        if debounce_s < 0 or dt_s <= 0:
            raise ValueError("invalid switch timing")
        self._debounce_steps = max(1, round(debounce_s / dt_s))
        self._pending_state = False
        self._pending_count = 0
        self._output = False
        self.fault = SwitchFault.NONE

    def step(self, physical_state: bool) -> bool:
        if physical_state != self._output:
            if physical_state == self._pending_state:
                self._pending_count += 1
            else:
                self._pending_state = physical_state
                self._pending_count = 1
            if self._pending_count >= self._debounce_steps:
                self._output = physical_state
        else:
            self._pending_count = 0

        if self.fault is SwitchFault.STUCK_OPEN:
            return False
        if self.fault is SwitchFault.STUCK_CLOSED:
            return True
        return self._output


class KeeperServo:
    """Keeper actuator with finite travel time and an injectable jam."""

    def __init__(self, *, travel_time_s: float = 0.35) -> None:
        if travel_time_s <= 0:
            raise ValueError("travel time must be positive")
        self._rate_per_s = 1.0 / travel_time_s
        #: 0.0 fully open, 1.0 fully closed.
        self.position = 0.0
        self.jammed = False

    def step(self, dt_s: float, close_commanded: bool) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        if self.jammed:
            return
        target = 1.0 if close_commanded else 0.0
        delta = self._rate_per_s * dt_s
        if self.position < target:
            self.position = min(target, self.position + delta)
        else:
            self.position = max(target, self.position - delta)

    @property
    def physically_closed(self) -> bool:
        return self.position >= 0.95

    @property
    def physically_open(self) -> bool:
        return self.position <= 0.05
