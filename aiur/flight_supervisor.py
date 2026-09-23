"""Hardware-agnostic flight supervisor for the STRATO-P0 observation package.

The package has exactly one actuator, the flight-termination cutdown, and
the supervisor's whole job is to decide when to fire it, what the imager and
the radios should be doing meanwhile, and to fail toward "come down inside
the prediction" whenever it is unsure.  It is the balloon-side counterpart
of ``aiur.dock_controller``: a small deterministic state machine that the
S0-A bench exercises with recorded inputs and the twin exercises with a
simulated ascent, so the logic that flies is the logic that was tested.

Two principles carried over from the dock controller:

* **Physical truth beats inference.**  The package arms only on a valid
  GNSS fix, declares ascent only on measured altitude gain, and declares
  descent only on a sustained measured descent rate.  It never infers a
  phase from the mission clock alone.
* **The safety path is outside the software it protects.**  The
  ``IndependentTimer`` is the model of a hardware cutdown timer on its own
  cell.  It is started by the same physical arming pin, it knows nothing
  else, and it fires whether or not this supervisor is still running.
  S0-A demonstrates the real one with the payload computer powered off.

Termination is latched: once commanded it is never withdrawn, because a
half-severed line is worse than a severed one.  There is no emergency
*un*-terminate, and there is deliberately no way for a software fault to
clear the cutdown output once asserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FlightState(str, Enum):
    #: On the ground, arming pin inserted: cutdown inhibited by hardware.
    SAFE = "safe"
    #: Pin pulled, valid fix, waiting to see the package climb.
    ARMED = "armed"
    ASCENT = "ascent"
    #: Above the stratospheric threshold.
    STRATOSPHERE = "stratosphere"
    #: Cutdown commanded; waiting to see a sustained descent.
    TERMINATING = "terminating"
    DESCENT = "descent"
    LANDED = "landed"


@dataclass(frozen=True)
class FlightLimits:
    """Every number the supervisor decides against, in one place.

    Values are engineering targets from docs/prototype-strato-p0.md; the
    stratospheric threshold mirrors ``aiur.strato.STRATOSPHERE_THRESHOLD_M``.
    """

    stratosphere_threshold_m: float = 20_000.0
    #: Float-off protection.  The reference article bursts near 33.8 km; a
    #: balloon still climbing through this altitude did not burst and will
    #: float away otherwise.
    ceiling_m: float = 36_000.0
    #: Geofence radius around the launch point.  Beyond it the pre-launch
    #: prediction is wrong and the flight is ended where it still can be.
    #: Set per launch at >= 1.5x the predicted landing range for the day's
    #: sounding; the default covers the reference wind profile in
    #: ``aiur.strato_sim`` (~72 km predicted).
    max_range_km: float = 120.0
    #: Mission clock limit from arming; the independent timer uses the same
    #: value.  ~3x the predicted 90 min ascent.
    max_mission_s: float = 3.0 * 3600.0
    #: An ascending package whose position has been unknown this long is
    #: brought down: HAZ-014's precondition is a balloon nobody can track.
    gnss_loss_terminate_s: float = 600.0
    #: Altitude gain over the launch point that counts as "released".
    release_detect_gain_m: float = 30.0
    #: Filtered vertical rate at or below which the package is descending,
    #: and how long it must persist before descent is declared.
    descent_rate_m_s: float = -2.0
    descent_hold_s: float = 30.0
    #: Landed: near the launch altitude with a near-zero rate for this long.
    landed_altitude_band_m: float = 500.0
    landed_rate_band_m_s: float = 0.5
    landed_hold_s: float = 120.0
    #: Below this bus voltage the package drops to beacon-only to keep the
    #: tracker alive; 4 x L91 cells at ~1.1 V each.
    low_battery_v: float = 4.4
    #: Below this internal temperature the imager is switched off and its
    #: power goes to survival; an engineering target until S0-A measures the
    #: real camera behaviour in the cold.
    camera_min_temp_c: float = -30.0
    #: Imaging cadence below / above the threshold, and telemetry cadence
    #: normal / beacon-only.
    capture_period_low_s: float = 10.0
    capture_period_high_s: float = 5.0
    telemetry_period_s: float = 30.0
    beacon_period_s: float = 120.0
    #: Smoothing factor for the vertical-rate filter (fraction of new sample).
    rate_filter_gain: float = 0.2

    def validate(self) -> None:
        if self.ceiling_m <= self.stratosphere_threshold_m:
            raise ValueError("ceiling must be above the stratospheric threshold")
        if min(self.max_range_km, self.max_mission_s, self.gnss_loss_terminate_s) <= 0:
            raise ValueError("range, mission, and GNSS-loss limits must be positive")
        if self.descent_rate_m_s >= 0:
            raise ValueError("descent rate threshold must be negative")
        if min(self.descent_hold_s, self.landed_hold_s) <= 0:
            raise ValueError("hold times must be positive")
        if not 0.0 < self.rate_filter_gain <= 1.0:
            raise ValueError("rate filter gain must be in (0, 1]")


@dataclass(frozen=True)
class FlightInputs:
    """What the supervisor sees on one tick."""

    #: True once the physical arming pin has been pulled at the launch site.
    arm_pin_pulled: bool
    gnss_valid: bool
    altitude_m: float | None = None
    range_from_launch_km: float | None = None
    battery_v: float = 6.0
    internal_temp_c: float = 20.0
    #: A termination command received from the ground station.
    ground_terminate: bool = False


@dataclass(frozen=True)
class FlightOutput:
    state: FlightState
    #: Cutdown output.  Latched once asserted; hardware-inhibited in SAFE.
    cutdown: bool
    #: Imager off, radios at beacon cadence.
    beacon_only: bool
    #: Seconds between captures, or None when the imager is off.
    capture_period_s: float | None
    telemetry_period_s: float
    #: Whether a frame captured now would carry a valid position tag.
    geotag: bool
    #: Why the last transition happened (termination reason in particular).
    reason: str | None


class IndependentTimer:
    """Model of the hardware cutdown timer on its own cell.

    It has one input, the arming pin, and one output.  It starts counting
    the first time the pin is seen pulled and fires when the mission limit
    elapses.  It cannot be reset, delayed, or inhibited by anything else,
    which is the point: it works when the payload computer does not.
    """

    def __init__(self, max_mission_s: float) -> None:
        if max_mission_s <= 0:
            raise ValueError("mission limit must be positive")
        self.max_mission_s = max_mission_s
        self.armed_at_s: float | None = None
        self.fired = False

    def step(self, now_s: float, arm_pin_pulled: bool) -> bool:
        if self.armed_at_s is None and arm_pin_pulled:
            self.armed_at_s = now_s
        if self.armed_at_s is not None and now_s - self.armed_at_s >= self.max_mission_s:
            self.fired = True
        return self.fired


class FlightSupervisor:
    """Deterministic state machine for the observation package."""

    def __init__(self, limits: FlightLimits | None = None) -> None:
        self.limits = limits or FlightLimits()
        self.limits.validate()
        self.state = FlightState.SAFE
        self.reason: str | None = None
        #: Why the cutdown was asserted; kept separately because later
        #: transitions (descent, landing) overwrite ``reason``.
        self.termination_reason: str | None = None
        self.cutdown_latched = False
        self.armed_at_s: float | None = None
        self.launch_altitude_m: float | None = None
        self.max_altitude_m: float | None = None
        self._last_now_s: float | None = None
        self._last_fix: tuple[float, float] | None = None
        self._last_fix_s: float | None = None
        self._rate_m_s: float | None = None
        self._descending_since_s: float | None = None
        self._still_since_s: float | None = None

    # ------------------------------------------------------------------
    def _transition(self, state: FlightState, reason: str | None = None) -> None:
        self.state = state
        self.reason = reason

    def _terminate(self, reason: str) -> None:
        self.cutdown_latched = True
        self.termination_reason = reason
        self._transition(FlightState.TERMINATING, reason)

    def _update_fix(self, now_s: float, inputs: FlightInputs) -> None:
        if not inputs.gnss_valid or inputs.altitude_m is None:
            return
        altitude = inputs.altitude_m
        if self._last_fix is not None:
            last_s, last_alt = self._last_fix
            dt = now_s - last_s
            if dt > 0:
                instant = (altitude - last_alt) / dt
                gain = self.limits.rate_filter_gain
                self._rate_m_s = (
                    instant if self._rate_m_s is None else (1 - gain) * self._rate_m_s + gain * instant
                )
        self._last_fix = (now_s, altitude)
        self._last_fix_s = now_s
        if self.max_altitude_m is None or altitude > self.max_altitude_m:
            self.max_altitude_m = altitude

    def _gnss_loss_s(self, now_s: float) -> float:
        if self._last_fix_s is None:
            return now_s - (self.armed_at_s if self.armed_at_s is not None else now_s)
        return now_s - self._last_fix_s

    def _descent_seen(self, now_s: float) -> bool:
        if self._rate_m_s is None or self._rate_m_s > self.limits.descent_rate_m_s:
            self._descending_since_s = None
            return False
        if self._descending_since_s is None:
            self._descending_since_s = now_s
        return now_s - self._descending_since_s >= self.limits.descent_hold_s

    def _landed_seen(self, now_s: float, inputs: FlightInputs) -> bool:
        if (
            not inputs.gnss_valid
            or inputs.altitude_m is None
            or self.launch_altitude_m is None
            or self._rate_m_s is None
            or abs(inputs.altitude_m - self.launch_altitude_m) > self.limits.landed_altitude_band_m
            or abs(self._rate_m_s) > self.limits.landed_rate_band_m_s
        ):
            self._still_since_s = None
            return False
        if self._still_since_s is None:
            self._still_since_s = now_s
        return now_s - self._still_since_s >= self.limits.landed_hold_s

    def _termination_reason(self, now_s: float, inputs: FlightInputs) -> str | None:
        """First termination trigger that applies, in priority order."""

        limits = self.limits
        if inputs.ground_terminate:
            return "ground command"
        if self.armed_at_s is not None and now_s - self.armed_at_s >= limits.max_mission_s:
            return "mission clock limit"
        if inputs.gnss_valid and inputs.altitude_m is not None and inputs.altitude_m >= limits.ceiling_m:
            return "ceiling: balloon did not burst"
        if (
            inputs.gnss_valid
            and inputs.range_from_launch_km is not None
            and inputs.range_from_launch_km > limits.max_range_km
        ):
            return "geofence: outside the predicted range"
        if self._gnss_loss_s(now_s) >= limits.gnss_loss_terminate_s:
            return "position unknown too long"
        return None

    def _output(self, inputs: FlightInputs) -> FlightOutput:
        limits = self.limits
        in_flight = self.state in (
            FlightState.ASCENT,
            FlightState.STRATOSPHERE,
            FlightState.TERMINATING,
            FlightState.DESCENT,
        )
        beacon_only = (
            self.state is FlightState.LANDED or inputs.battery_v < limits.low_battery_v
        )
        camera_on = (
            in_flight and not beacon_only and inputs.internal_temp_c >= limits.camera_min_temp_c
        )
        above = (
            inputs.gnss_valid
            and inputs.altitude_m is not None
            and inputs.altitude_m >= limits.stratosphere_threshold_m
        )
        capture_period = None
        if camera_on:
            capture_period = limits.capture_period_high_s if above else limits.capture_period_low_s
        return FlightOutput(
            state=self.state,
            # Hardware inhibit: nothing fires while the pin is in.
            cutdown=self.cutdown_latched and self.state is not FlightState.SAFE,
            beacon_only=beacon_only,
            capture_period_s=capture_period,
            telemetry_period_s=limits.beacon_period_s if beacon_only else limits.telemetry_period_s,
            geotag=bool(inputs.gnss_valid),
            reason=self.reason,
        )

    # ------------------------------------------------------------------
    def step(self, now_s: float, inputs: FlightInputs) -> FlightOutput:
        """Advance the state machine using a monotonic timestamp."""

        if self._last_now_s is not None and now_s < self._last_now_s:
            raise ValueError("now_s must be monotonic")
        self._last_now_s = now_s
        limits = self.limits

        self._update_fix(now_s, inputs)

        if self.state is FlightState.SAFE:
            if not inputs.arm_pin_pulled:
                return self._output(inputs)
            if not inputs.gnss_valid or inputs.altitude_m is None:
                # No fix, no arm: the geofence and the landing band are both
                # measured from the launch point, and a package that does
                # not know where it started cannot know where it is allowed.
                self._transition(FlightState.SAFE, "arming requires a GNSS fix")
                return self._output(inputs)
            self.armed_at_s = now_s
            self.launch_altitude_m = inputs.altitude_m
            self._transition(FlightState.ARMED, "armed on a valid fix")
            return self._output(inputs)

        if self.state is FlightState.ARMED:
            if not inputs.arm_pin_pulled:
                # Pin re-inserted on the ground: disarm.  Only possible here;
                # once the package has climbed, nobody can reach the pin.
                self.armed_at_s = None
                self._transition(FlightState.SAFE, "disarmed on the ground")
                return self._output(inputs)
            reason = self._termination_reason(now_s, inputs)
            if reason is not None:
                self._terminate(reason)
                return self._output(inputs)
            assert self.launch_altitude_m is not None
            if (
                inputs.gnss_valid
                and inputs.altitude_m is not None
                and inputs.altitude_m - self.launch_altitude_m >= limits.release_detect_gain_m
            ):
                self._transition(FlightState.ASCENT, "measured climb over the launch point")
            return self._output(inputs)

        if self.state in (FlightState.ASCENT, FlightState.STRATOSPHERE):
            reason = self._termination_reason(now_s, inputs)
            if reason is not None:
                self._terminate(reason)
                return self._output(inputs)
            if self._descent_seen(now_s):
                self._transition(FlightState.DESCENT, "sustained descent: burst")
                return self._output(inputs)
            if (
                self.state is FlightState.ASCENT
                and inputs.gnss_valid
                and inputs.altitude_m is not None
                and inputs.altitude_m >= limits.stratosphere_threshold_m
            ):
                self._transition(FlightState.STRATOSPHERE, "crossed the stratospheric threshold")
            return self._output(inputs)

        if self.state is FlightState.TERMINATING:
            if self._descent_seen(now_s):
                self._transition(FlightState.DESCENT, f"descending after termination: {self.reason}")
            return self._output(inputs)

        if self.state is FlightState.DESCENT:
            if inputs.ground_terminate and not self.cutdown_latched:
                # Harmless on a descending package and it shortens a line
                # that may still be tangled with the remnant; honour it.
                self.cutdown_latched = True
                self.termination_reason = "ground command during descent"
                self.reason = self.termination_reason
            if self._landed_seen(now_s, inputs):
                self._transition(FlightState.LANDED, "at rest near the launch altitude")
            return self._output(inputs)

        # LANDED is terminal: beacon until someone picks the package up.
        return self._output(inputs)
