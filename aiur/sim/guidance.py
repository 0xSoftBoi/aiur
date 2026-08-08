"""Terminal guidance and safety supervision for the CARRIER-P0 digital twin.

Implements the runtime recovery loop from docs/engineering-loop.md: sense →
estimate → safety supervisor → guidance/dock state → velocity and latch
commands.  The supervisor is authoritative: guidance may only pursue capture
while every safety predicate holds, and every departure from nominal is an
explicit ``ABORT`` event with a machine-readable reason.

Safety predicates enforced here:

* pose validity — stale relative state first commands a hold, then a blind
  descent away from the dock (down is always away from the envelope);
* approach corridor — a cone opening downward from the funnel entrance;
* closing-speed limits — commanded speed is profiled well under the hard
  limit, and a measured overspeed aborts the approach;
* dock sensor plausibility — a reported seat switch is believed only when
  the estimated probe position could physically be at the seat, so a stuck
  switch can never talk the vehicle into disarming in free air;
* battery reserve — a vehicle that cannot finish an approach with reserve
  lands instead of loitering until it falls.

All numeric values are engineering targets consistent with
docs/prototype-p0.md; none are measured performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..dock_controller import DockState
from .dock_physics import DockCommands, DockStepResult
from .events import Event, EventKind
from .sensors import PoseMeasurement
from .vec import Vec3, ZERO


class GuidancePhase(str, Enum):
    STATION_HOLD = "station_hold"
    RENDEZVOUS = "rendezvous"
    ALIGN = "align"
    TERMINAL = "terminal"
    SEATED_WAIT = "seated_wait"
    CAPTURED = "captured"
    LAUNCH_RELEASE = "launch_release"
    DEPART = "depart"
    SORTIE = "sortie"
    ABORT_DESCEND = "abort_descend"
    LAND = "land"
    LANDED = "landed"


#: Phases that count as an active approach to the dock.  The fleet sequencer
#: must never observe two aircraft in these phases at once.
APPROACH_PHASES = frozenset(
    {
        GuidancePhase.RENDEZVOUS,
        GuidancePhase.ALIGN,
        GuidancePhase.TERMINAL,
        GuidancePhase.SEATED_WAIT,
    }
)


@dataclass(frozen=True)
class GuidanceParams:
    standoff_below_entrance_m: float = 0.55
    rendezvous_capture_radius_m: float = 0.10
    max_transit_speed_m_s: float = 0.50
    transit_kp_per_s: float = 0.8

    align_radius_m: float = 0.030
    align_hold_s: float = 1.0

    terminal_speed_m_s: float = 0.08
    creep_speed_m_s: float = 0.03
    hard_closing_limit_m_s: float = 0.20
    lateral_kp_per_s: float = 1.2
    max_lateral_speed_m_s: float = 0.35
    corridor_base_m: float = 0.060
    corridor_slope: float = 0.35

    pose_hold_timeout_s: float = 0.5
    blind_descent_speed_m_s: float = 0.15
    seat_plausibility_m: float = 0.060
    #: Tight confirm distance for enabling capture and for disarm: the
    #: estimated probe tip must be this close to the seat.  Sized to
    #: discriminate a truly seated probe from one blocked by the keeper
    #: (keeper_capture_window_m below the seat) at Lighthouse-grade noise.
    seat_confirm_m: float = 0.015
    #: Watchdog: capture enabled but no confirmed capture within this time
    #: means the dock cannot be trusted; safe the aircraft.
    lock_wait_timeout_s: float = 4.0
    #: Watchdog: estimated at-seat but the seat switch stays silent.
    seat_silent_timeout_s: float = 3.0
    #: A single-step measurement jump above this is a navigation anomaly.
    pose_jump_threshold_m: float = 0.030
    #: Plausible own-motion speeds used to scale the jump threshold across a
    #: measurement gap, so a bias that arises during a dropout is still
    #: caught on recovery instead of the comparison being skipped.
    pose_gap_speed_precise_m_s: float = 0.20
    pose_gap_speed_transit_m_s: float = 0.60
    #: Approach quarantine after a detected navigation anomaly.
    pose_quarantine_s: float = 20.0
    #: Time constant of the low-pass filter behind threshold decisions
    #: (align complete, corridor, seat confirm).  Commands track the raw
    #: estimate; noisy sensors must not flap the decision logic.
    estimate_filter_tau_s: float = 0.4
    #: Integral gain for wind rejection on the approach loops.  A pure P
    #: loop leaves a steady-state offset under mean wind that can exceed the
    #: rendezvous/align thresholds, so the approach would never converge.
    wind_integral_gain_per_s: float = 0.2
    wind_integral_limit_m_s: float = 0.35
    battery_reserve_s: float = 60.0
    floor_z_m: float = 0.0

    #: Carrier envelope geometry for the proximity-evasion reflex, wired in
    #: by the engine on carrier platforms; None on bench rigs.
    carrier_center_from_dock_m: Vec3 | None = None
    envelope_semi_axes_m: Vec3 | None = None
    #: Evade when the normalized (inflated) ellipsoid distance drops below
    #: this.  A seated aircraft sits at about 1.23; approach paths stay
    #: below the hull, so 1.15 only trips when the carrier drifts onto an
    #: aircraft that should be clear of it.
    envelope_avoid_threshold: float = 1.15
    envelope_avoid_inflate_m: float = 0.15
    envelope_avoid_speed_m_s: float = 0.60
    envelope_avoid_descent_m_s: float = 0.30


class MissionMode(str, Enum):
    RECOVER_ONLY = "recover_only"
    LAUNCH_SORTIE_RECOVER = "launch_sortie_recover"


@dataclass(frozen=True)
class GuidanceDecision:
    phase: GuidancePhase
    velocity_cmd: Vec3
    dock_commands: DockCommands
    disarm: bool
    events: tuple[Event, ...]


@dataclass
class _Estimate:
    """Relative state of the probe tip with respect to the funnel entrance."""

    valid: bool
    #: Probe depth below the entrance plane (positive = below, not inserted).
    below_entrance_m: float
    lateral_error_m: float
    lateral_vector: Vec3
    closing_speed_m_s: float
    dock_velocity: Vec3


class TerminalGuidance:
    """Guidance, dock commanding, and safety supervision for one aircraft."""

    def __init__(
        self,
        params: GuidanceParams,
        *,
        drone_index: int,
        probe_height_m: float,
        seat_travel_m: float,
        mission: MissionMode = MissionMode.RECOVER_ONLY,
        station: Vec3 = ZERO,
        sortie_waypoints: tuple[Vec3, ...] = (),
    ) -> None:
        self.params = params
        self.drone_index = drone_index
        self._probe_height = probe_height_m
        self._seat_travel = seat_travel_m
        self.mission = mission
        self.station = station
        self._waypoints = list(sortie_waypoints)
        self.phase = (
            GuidancePhase.LAUNCH_RELEASE
            if mission is MissionMode.LAUNCH_SORTIE_RECOVER
            else GuidancePhase.STATION_HOLD
        )
        self.approach_authorized = False
        self.abort_count = 0
        self.dock_untrusted = False
        self.land_reason = ""
        self._align_ok_s = 0.0
        self._pose_invalid_s = 0.0
        self._last_estimate: _Estimate | None = None
        self._quarantine_s = 0.0
        self._ever_meas_valid = False
        self._meas_gap_s = 0.0
        self._last_valid_position = ZERO
        self._seated_wait_s = 0.0
        self._seat_silent_s = 0.0
        self._emergency_release = False
        self._request_dock_reset = False
        self._dock_fault_aborts = 0
        self._capture_enable_latched = False
        self._wind_integral = ZERO
        self._filt_rel: Vec3 | None = None
        self._filt_closing = 0.0

    # -- estimation -------------------------------------------------------

    def _estimate(
        self,
        drone_meas: PoseMeasurement,
        dock_meas: PoseMeasurement,
    ) -> _Estimate:
        valid = drone_meas.valid and dock_meas.valid
        probe_tip = drone_meas.position + Vec3(0.0, 0.0, self._probe_height)
        rel = dock_meas.position - probe_tip
        closing = (drone_meas.velocity - dock_meas.velocity).z
        return _Estimate(
            valid=valid,
            below_entrance_m=rel.z,
            lateral_error_m=rel.lateral_norm(),
            lateral_vector=rel.lateral(),
            closing_speed_m_s=closing,
            dock_velocity=dock_meas.velocity,
        )

    # -- helpers ----------------------------------------------------------

    def _goto(self, target: Vec3, drone_meas: PoseMeasurement, speed: float) -> Vec3:
        error = target - drone_meas.position
        return (error * self.params.transit_kp_per_s).clamped(speed)

    def _entrance_target(self, dock_meas: PoseMeasurement, below_m: float) -> Vec3:
        """Drone-center position putting the probe tip below_m under the entrance."""

        return dock_meas.position - Vec3(0.0, 0.0, self._probe_height + below_m)

    def _abort(self, now_s: float, reason: str, events: list[Event]) -> None:
        self.abort_count += 1
        self._align_ok_s = 0.0
        self._seated_wait_s = 0.0
        self._seat_silent_s = 0.0
        self._capture_enable_latched = False
        self.phase = GuidancePhase.ABORT_DESCEND
        events.append(Event(EventKind.ABORT, now_s, self.drone_index, reason))

    def _lateral_track(self, est: _Estimate) -> Vec3:
        p = self.params
        cmd = est.dock_velocity.lateral() + est.lateral_vector * p.lateral_kp_per_s
        return cmd.clamped(p.max_lateral_speed_m_s)

    def _integrate_wind(self, dt_s: float, error: Vec3) -> Vec3:
        """Advance the shared approach integrator and return its value.

        Conditional integration: the integrator only winds inside the
        near-target regime so a long transit cannot saturate it.
        """

        p = self.params
        if error.norm() <= 0.5:
            self._wind_integral = (
                self._wind_integral + error * (p.wind_integral_gain_per_s * dt_s)
            ).clamped(p.wind_integral_limit_m_s)
        return self._wind_integral

    def _envelope_proximity(self, position: Vec3, dock_meas: PoseMeasurement) -> float:
        """Normalized inflated-ellipsoid distance to the estimated hull."""

        p = self.params
        if p.carrier_center_from_dock_m is None or p.envelope_semi_axes_m is None:
            return float("inf")
        center = dock_meas.position + p.carrier_center_from_dock_m
        rel = position - center
        a = p.envelope_semi_axes_m
        inflate = p.envelope_avoid_inflate_m
        return (
            (rel.x / (a.x + inflate)) ** 2
            + (rel.y / (a.y + inflate)) ** 2
            + (rel.z / (a.z + inflate)) ** 2
        ) ** 0.5

    def _filtered_seat_distance_m(self) -> float | None:
        if self._filt_rel is None:
            return None
        return (self._filt_rel + Vec3(0.0, 0.0, self._seat_travel)).norm()

    # -- main step --------------------------------------------------------

    def step(
        self,
        now_s: float,
        dt_s: float,
        drone_meas: PoseMeasurement,
        dock_meas: PoseMeasurement,
        dock_feedback: DockStepResult | None,
        remaining_flight_s: float,
    ) -> GuidanceDecision:
        p = self.params
        events: list[Event] = []
        dock_cmd = DockCommands()
        disarm = False

        est = self._estimate(drone_meas, dock_meas)
        if est.valid:
            self._pose_invalid_s = 0.0
            self._last_estimate = est
            # Low-pass the relative state for threshold decisions.
            alpha = min(1.0, dt_s / p.estimate_filter_tau_s)
            rel = est.lateral_vector.with_z(est.below_entrance_m)
            if self._filt_rel is None:
                self._filt_rel = rel
                self._filt_closing = est.closing_speed_m_s
            else:
                self._filt_rel = self._filt_rel * (1.0 - alpha) + rel * alpha
                self._filt_closing += alpha * (est.closing_speed_m_s - self._filt_closing)
        else:
            self._pose_invalid_s += dt_s

        # -- supervisor: navigation-anomaly (jump) detector ---------------
        # A discontinuity in the drone's own pose means the navigation
        # solution cannot be trusted for terminal work; abort and quarantine
        # the approach.  Across a measurement gap the comparison is not
        # skipped — the threshold is widened by the distance the vehicle
        # could plausibly have flown, so a bias that arises *during* a
        # dropout is still caught on recovery.  Known residual risk: a bias
        # that ramps in slowly, or hides under a long gap at transit speed,
        # is undetectable from this single source (see docs/digital-twin.md).
        self._quarantine_s = max(0.0, self._quarantine_s - dt_s)
        if drone_meas.valid:
            if self._ever_meas_valid:
                gap_speed = (
                    p.pose_gap_speed_precise_m_s
                    if self.phase
                    in (
                        GuidancePhase.ALIGN,
                        GuidancePhase.TERMINAL,
                        GuidancePhase.SEATED_WAIT,
                        GuidancePhase.ABORT_DESCEND,
                    )
                    else p.pose_gap_speed_transit_m_s
                )
                allowed = p.pose_jump_threshold_m + gap_speed * self._meas_gap_s
                jump = (drone_meas.position - self._last_valid_position).norm()
                if jump > allowed:
                    self._quarantine_s = p.pose_quarantine_s
                    if self.phase in APPROACH_PHASES:
                        self._abort(now_s, "pose_jump_detected", events)
            self._last_valid_position = drone_meas.position
            self._meas_gap_s = 0.0
            self._ever_meas_valid = True
        else:
            self._meas_gap_s += dt_s

        reported_s1 = dock_feedback.reported_s1 if dock_feedback else False
        controller_state = dock_feedback.controller.state if dock_feedback else DockState.OPEN
        capture_confirmed = (
            dock_feedback.controller.capture_confirmed if dock_feedback else False
        )
        filt_seat_m = self._filtered_seat_distance_m()
        seat_plausible = filt_seat_m is not None and filt_seat_m <= p.seat_plausibility_m

        # -- supervisor: dock sensor plausibility ------------------------
        # A seat report with the probe demonstrably far from the seat means
        # the dock's sensing cannot be trusted.  Never enable capture on it.
        if (
            reported_s1
            and filt_seat_m is not None
            and filt_seat_m > 2.0 * p.seat_plausibility_m
            and self.phase in APPROACH_PHASES
        ):
            if not self.dock_untrusted:
                self.dock_untrusted = True
                self._abort(now_s, "dock_seat_sensor_implausible", events)

        # -- supervisor: battery reserve ---------------------------------
        finishing = self.phase in (GuidancePhase.SEATED_WAIT, GuidancePhase.CAPTURED)
        if (
            remaining_flight_s <= p.battery_reserve_s
            and not finishing
            and self.phase
            not in (GuidancePhase.LAND, GuidancePhase.LANDED, GuidancePhase.CAPTURED)
        ):
            self.phase = GuidancePhase.LAND
            self.land_reason = "low_battery"

        # -- supervisor: pose validity ------------------------------------
        if not est.valid and self.phase in APPROACH_PHASES:
            probe_inserted = self._filt_rel is not None and self._filt_rel.z < 0.0
            if probe_inserted and self.phase in (
                GuidancePhase.TERMINAL,
                GuidancePhase.SEATED_WAIT,
            ):
                # Inside the funnel the taper constrains the probe; continue
                # the creep on dead reckoning.  This is the mechanical-capture
                # tolerance the funnel exists to provide.
                pass
            elif self._pose_invalid_s <= p.pose_hold_timeout_s:
                return GuidanceDecision(self.phase, ZERO, dock_cmd, False, tuple(events))
            else:
                self._abort(now_s, "relative_pose_invalid", events)

        # -- phase logic --------------------------------------------------
        cmd = ZERO

        if self.phase is GuidancePhase.STATION_HOLD:
            cmd = self._goto(self.station, drone_meas, p.max_transit_speed_m_s)
            if (
                self.approach_authorized
                and not self.dock_untrusted
                and self._quarantine_s <= 0.0
            ):
                self.phase = GuidancePhase.RENDEZVOUS

        elif self.phase is GuidancePhase.RENDEZVOUS:
            if not self.approach_authorized:
                self.phase = GuidancePhase.STATION_HOLD
            else:
                target = self._entrance_target(dock_meas, p.standoff_below_entrance_m)
                error = target - drone_meas.position
                cmd = self._goto(target, drone_meas, p.max_transit_speed_m_s)
                cmd = cmd + self._integrate_wind(dt_s, error)
                if error.norm() <= p.rendezvous_capture_radius_m:
                    self.phase = GuidancePhase.ALIGN

        elif self.phase is GuidancePhase.ALIGN:
            if not self.approach_authorized:
                self.phase = GuidancePhase.STATION_HOLD
            else:
                vertical_err = est.below_entrance_m - p.standoff_below_entrance_m
                vz = est.dock_velocity.z + max(-0.10, min(0.10, vertical_err * 0.5))
                integral = self._integrate_wind(
                    dt_s, est.lateral_vector.with_z(vertical_err)
                )
                cmd = self._lateral_track(est).with_z(vz) + integral
                filt_lateral = (
                    self._filt_rel.lateral_norm() if self._filt_rel is not None else est.lateral_error_m
                )
                if filt_lateral <= p.align_radius_m:
                    self._align_ok_s += dt_s
                else:
                    self._align_ok_s = 0.0
                if self._align_ok_s >= p.align_hold_s:
                    self.phase = GuidancePhase.TERMINAL

        elif self.phase is GuidancePhase.TERMINAL:
            depth = self._filt_rel.z if self._filt_rel is not None else est.below_entrance_m
            # Supervisor: corridor and overspeed apply while still below the
            # entrance plane; past it, the funnel owns lateral containment.
            # Decisions run on the filtered estimate so sensor noise cannot
            # flap an abort.
            if est.valid and depth > 0.0 and self._filt_rel is not None:
                allowed = p.corridor_base_m + p.corridor_slope * depth
                if self._filt_rel.lateral_norm() > allowed:
                    self._abort(now_s, "corridor_violation", events)
                elif self._filt_closing > p.hard_closing_limit_m_s:
                    self._abort(now_s, "closing_overspeed", events)
            if self.phase is GuidancePhase.TERMINAL:
                closing = max(p.creep_speed_m_s, min(p.terminal_speed_m_s, 0.6 * depth))
                integral = self._integrate_wind(dt_s, est.lateral_vector.with_z(0.0))
                cmd = (
                    self._lateral_track(est).with_z(est.dock_velocity.z + closing)
                    + integral
                )
                # Watchdog: estimated at-seat but the seat switch says
                # nothing — the dock's sensing is broken; safe the aircraft.
                at_seat = filt_seat_m is not None and filt_seat_m <= p.seat_confirm_m
                if at_seat and not reported_s1:
                    self._seat_silent_s += dt_s
                    if self._seat_silent_s >= p.seat_silent_timeout_s:
                        self.dock_untrusted = True
                        self._abort(now_s, "seat_switch_silent", events)
                else:
                    self._seat_silent_s = 0.0
                if self.phase is GuidancePhase.TERMINAL and reported_s1 and seat_plausible:
                    self.phase = GuidancePhase.SEATED_WAIT
                    self._seated_wait_s = 0.0

        elif self.phase is GuidancePhase.SEATED_WAIT:
            # Keep gentle seating pressure while the real controller drives
            # the keeper.  Capture may only be enabled here, and both the
            # enable and the disarm require the tight seat confirm: the
            # estimated probe tip must actually be at the seat, so a stuck
            # seat switch can never talk the vehicle into disarming early.
            cmd = est.dock_velocity + Vec3(0.0, 0.0, p.creep_speed_m_s)
            self._seated_wait_s += dt_s
            seat_confirmed = filt_seat_m is not None and filt_seat_m <= p.seat_confirm_m
            if not reported_s1 or not seat_plausible:
                self._abort(now_s, "seat_lost_before_lock", events)
            elif controller_state in (DockState.FAULT_OPEN, DockState.FAULT_LOCKED):
                # One dock fault earns one retry; a second means the dock is
                # broken, not unlucky.  The retry must clear the latched
                # controller fault on the way out (FAULT_OPEN resets only
                # with reset_fault while both switches read open, which
                # holds once the probe is back at the standoff).
                self._dock_fault_aborts += 1
                if self._dock_fault_aborts >= 2:
                    self.dock_untrusted = True
                else:
                    self._request_dock_reset = True
                self._abort(now_s, f"dock_fault_{controller_state.value}", events)
            elif self._seated_wait_s >= p.lock_wait_timeout_s:
                # The keeper had every chance to close on a confirmed seat.
                # Whatever is wrong (jam, blocked throat, lying switch), the
                # dock cannot be trusted; open it and leave.
                self.dock_untrusted = True
                self._emergency_release = True
                self._abort(now_s, "dock_lock_watchdog", events)
            else:
                # The tight confirm gates the first assertion; once locking
                # has started the enable is latched so measurement noise
                # cannot flap the controller out of LOCKING.
                if seat_confirmed:
                    self._capture_enable_latched = True
                dock_cmd = DockCommands(capture_enable=self._capture_enable_latched)
                if capture_confirmed and seat_confirmed:
                    self.phase = GuidancePhase.CAPTURED
                    disarm = True

        elif self.phase is GuidancePhase.CAPTURED:
            cmd = ZERO

        elif self.phase is GuidancePhase.LAUNCH_RELEASE:
            dock_cmd = DockCommands(release_request=True)
            if dock_feedback is not None and not dock_feedback.reported_s2:
                self.phase = GuidancePhase.DEPART

        elif self.phase is GuidancePhase.DEPART:
            cmd = Vec3(0.0, 0.0, -p.blind_descent_speed_m_s)
            if est.valid and est.below_entrance_m > 0.4:
                self.phase = (
                    GuidancePhase.SORTIE if self._waypoints else GuidancePhase.STATION_HOLD
                )

        elif self.phase is GuidancePhase.SORTIE:
            if not self._waypoints:
                self.phase = GuidancePhase.STATION_HOLD
            else:
                target = self._waypoints[0]
                cmd = self._goto(target, drone_meas, p.max_transit_speed_m_s)
                if (target - drone_meas.position).norm() <= 0.10:
                    self._waypoints.pop(0)
                    if not self._waypoints:
                        self.phase = GuidancePhase.STATION_HOLD

        elif self.phase is GuidancePhase.ABORT_DESCEND:
            # Keep the keeper commanded open while backing out of a dock we
            # declared untrustworthy, so a wrongly closed keeper releases;
            # after a transient dock fault, clear the latched controller
            # fault instead so the single permitted retry can actually work.
            if self._emergency_release:
                dock_cmd = DockCommands(emergency_release=True)
            elif self._request_dock_reset:
                dock_cmd = DockCommands(reset_fault=True)
            target = self._entrance_target(dock_meas, p.standoff_below_entrance_m)
            if est.valid:
                cmd = self._goto(target, drone_meas, p.max_transit_speed_m_s)
                if (target - drone_meas.position).norm() <= p.rendezvous_capture_radius_m:
                    if self.dock_untrusted or not self.approach_authorized:
                        self._emergency_release = False
                        self._request_dock_reset = False
                        self.phase = GuidancePhase.STATION_HOLD
                    elif self._quarantine_s <= 0.0:
                        self._request_dock_reset = False
                        self.phase = GuidancePhase.RENDEZVOUS
                    # Otherwise loiter at the standoff until quarantine ends.
            else:
                cmd = Vec3(0.0, 0.0, -p.blind_descent_speed_m_s)

        elif self.phase is GuidancePhase.LAND:
            cmd = Vec3(0.0, 0.0, -p.blind_descent_speed_m_s)
            if drone_meas.valid and drone_meas.position.z <= p.floor_z_m + 0.10:
                self.phase = GuidancePhase.LANDED
                disarm = True
                events.append(
                    Event(
                        EventKind.SAFE_LANDING,
                        now_s,
                        self.drone_index,
                        self.land_reason or "commanded",
                    )
                )

        elif self.phase is GuidancePhase.LANDED:
            cmd = ZERO

        # -- supervisor: carrier-proximity evasion ------------------------
        # A drifting carrier can overrun an aircraft that is merely holding
        # station.  Any aircraft not intentionally under the dock evades a
        # hull that gets too close: laterally away plus a descent, since the
        # envelope is always above.
        if (
            self.phase
            in (
                GuidancePhase.STATION_HOLD,
                GuidancePhase.RENDEZVOUS,
                GuidancePhase.ALIGN,
                GuidancePhase.DEPART,
                GuidancePhase.SORTIE,
                GuidancePhase.ABORT_DESCEND,
                GuidancePhase.LAND,
            )
            and drone_meas.valid
            and dock_meas.valid
        ):
            proximity = self._envelope_proximity(drone_meas.position, dock_meas)
            if proximity < p.envelope_avoid_threshold:
                if self.phase in APPROACH_PHASES:
                    self._abort(now_s, "carrier_proximity", events)
                assert p.carrier_center_from_dock_m is not None
                center = dock_meas.position + p.carrier_center_from_dock_m
                away = (drone_meas.position - center).lateral()
                norm = away.norm()
                direction = away * (1.0 / norm) if norm > 1e-6 else Vec3(1.0, 0.0, 0.0)
                cmd = (direction * p.envelope_avoid_speed_m_s).with_z(
                    -p.envelope_avoid_descent_m_s
                )

        return GuidanceDecision(self.phase, cmd, dock_cmd, disarm, tuple(events))


class FleetSequencer:
    """Grants the single dock-approach token and audits the invariant.

    The sequencer is deliberately simple: exactly one aircraft may hold the
    approach authorization.  It additionally *audits* the fleet every step —
    if two aircraft are ever observed in approach phases simultaneously, that
    is recorded as a ``SIMULTANEOUS_DOCK_APPROACH`` event (a P0-D gate
    violation), not silently corrected.
    """

    def __init__(self, guidances: list[TerminalGuidance]) -> None:
        self._guidances = guidances
        self._token_holder: int | None = None

    @property
    def token_holder(self) -> int | None:
        return self._token_holder

    def authorize(self, drone_index: int) -> bool:
        """Grant the approach token if it is free (or already held by caller)."""

        if self._token_holder in (None, drone_index):
            self._token_holder = drone_index
            for guidance in self._guidances:
                guidance.approach_authorized = guidance.drone_index == drone_index
            return True
        return False

    def release(self, drone_index: int) -> None:
        if self._token_holder == drone_index:
            self._token_holder = None
            for guidance in self._guidances:
                guidance.approach_authorized = False

    def audit(self, now_s: float) -> tuple[Event, ...]:
        approaching = [
            g.drone_index for g in self._guidances if g.phase in APPROACH_PHASES
        ]
        if len(approaching) > 1:
            return (
                Event(
                    EventKind.SIMULTANEOUS_DOCK_APPROACH,
                    now_s,
                    detail=f"drones={approaching}",
                ),
            )
        return ()
