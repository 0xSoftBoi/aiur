"""Passive snap-detent capture candidate for the CARRIER-P0 recovery dock.

Architecture under evaluation: **no actuator at all**.  The funnel and probe
are unchanged from the baseline; the sliding fork keeper and its XL330 are
deleted and replaced by a sprung detent printed into the throat.  The probe
head pushes the detent aside on the way in, the detent springs back behind
it, and release is by commanded thrust — the aircraft simply flies out.

Why it is worth simulating.  Zero actuators means zero actuator failure
modes.  Three of the programme's worst findings cannot exist here: the servo
stall (FM-KP-*), the shared-rail brownout that resets the controller while
the keeper is loaded, and the Rev-A keeper that could not release.  Retention
survives a dead battery by construction, not by fail-locked logic.  It is
also the lightest and lowest part-count candidate by a wide margin.

Why it must be modelled honestly, and this is the crux.  The deletion review
(docs/dock-deletion-review.md, "The case for deleting it") computed that a
passive backstop must hold more than the docked aircraft's weight — 47.7 g,
0.468 N — while staying under the 0.074 N of precision-approach control force
if it is not to fight an abort.  Those differ by 6.3x.  This module implements
the detent as a swept ``retention_force_n`` so the study can look for the
window rather than being told there is none.

What the model then says, and it is stronger than the review's 6.3x, because
it is arithmetic rather than a ratio of two estimates:

    A passive detent under a below-slung dock is held closed by the
    aircraft's weight and opened by the aircraft's weight.  The aircraft
    hangs from the detent, so the retention force must exceed W to hold it;
    to escape, the aircraft can at best unload its propellers to zero thrust,
    which applies exactly W at the same detent face.  Hold requires
    R*f > W.  Release requires R*f <= W.  No R satisfies both, for any
    friction factor f, at any retention force.

That is :func:`window_is_empty`, and it is proved in the tests rather than
asserted here.  The only modelled escapes are propellers that can push down
(``reverse_thrust_n``; stock Crazyflie 2.1 Brushless props are unidirectional)
or an aircraft-side release actuator — which is not an actuator-free
architecture, it is an actuator moved onto the 37 g budget.

Sensing, stated plainly.  With no actuator there is no keeper-closed channel,
and no honest substitute for one:

* A detent-position switch cannot discriminate.  The detent's rest position
  is the same whether it is holding a head or has never been touched, so such
  a switch senses "nothing is deflecting me", which is true of an empty dock.
  That is the empty-throat failure of finding 5 in its purest form, so this
  module does not fit one.
* Capture confirmation therefore means exactly: *the seat switch S1 has read
  closed continuously for the confirm dwell*.  One switch, one physical fact,
  no second opinion.  ``capture_confirmed = S1``, not ``S1 AND S2``.
* The safety claim that is weaker, precisely: the baseline's claim is "no
  single navigation fault and no single sensor fault produces a confirmed
  capture on an empty dock".  This architecture keeps the first half and
  loses the second.  A single stuck-actuated S1 confirms a capture with an
  empty throat, and the only thing standing between that and a disarm in free
  air is the supervisor's navigation plausibility gate — which is a single
  navigation source, which is the thing findings 3 and 5 say cannot be
  trusted.  The programme's only irreversible action ends up behind one
  switch AND one estimator, with no mechanical channel that a lie has to get
  past.  The deletion review rejected exactly this collapse for the baseline
  ("A single sensor cannot be two independent channels; that is arithmetic").

Physics fidelity.  Every number below is an engineering-estimate surrogate in
the same spirit as ``dock_physics.py``, and where a choice was available it
was made in the candidate's favour, so that a candidate which still fails is
failing for structural reasons rather than pessimistic tuning.  The funnel
entrance, rim annulus, bounce speed, seat travel and taper are deliberately
identical to :class:`~aiur.sim.dock_physics.DockGeometry` so contact metrics
are comparable across architectures.  Nothing here is a vendor figure; no
detent has been printed, sprung, or pulled with a gauge.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..dock_controller import DockOutput, DockState, KeeperCommand
from .bodies import DroneBody
from .dock_physics import DockCommands, DockGeometry, DockStepResult, ProbePhase
from .events import Event, EventKind
from .sensors import Switch, SwitchFault
from .vec import Vec3

#: Standard gravity.  This is the only capture architecture in the study whose
#: physics turns on it: with no actuator, weight is simultaneously the load
#: that must be held and the only force available to get free of it.
G_M_S2 = 9.80665

#: Relative vertical speed below which the aircraft is not treated as
#: demanding a descent.  Above numerical noise, far below the guidance
#: blind-descent command (0.15 m/s).
_DESCENT_DEADBAND_M_S = 0.005


@dataclass(frozen=True)
class PassiveDetentGeometry:
    """Funnel geometry shared with the baseline, plus the detent's own.

    The funnel numbers are copied rather than imported so this candidate can
    be swept independently, but they are deliberately the same values: the
    trade study compares mechanisms, and a candidate with a quietly larger
    mouth would win the rim-contact metric for a reason that has nothing to
    do with its latch.
    """

    funnel_entrance_radius_m: float = 0.090
    #: Rim annulus beyond the funnel radius where a plane crossing means the
    #: guarded prop disc meets the funnel edge.
    rim_annulus_m: float = 0.060
    #: Probe travel from entrance plane to seat.
    seat_travel_m: float = 0.100
    #: Seat hysteresis before the physical seat switch drops out.
    seat_hysteresis_m: float = 0.004
    #: Probe tip height above the aircraft reference point.
    probe_height_m: float = 0.050
    #: Above this closing speed the probe bounces instead of inserting.
    bounce_speed_m_s: float = 0.30
    #: Travel over which the head deflects the detent fingers before it
    #: reaches the seat.  The insertion force must be supplied over this last
    #: stretch; a probe that cannot supply it stalls here, short of the seat,
    #: which is why S1 stays silent and the approach times out safely.
    detent_engage_travel_m: float = 0.002
    #: Radial deflection of the detent member as the head passes.  Sets how
    #: much kinetic energy a moving probe can trade for insertion force.
    detent_throw_m: float = 0.0015
    #: Slack between the seat face and the detent's retaining face once
    #: snapped.  A disarmed aircraft sags by this much when its weight
    #: transfers from the seat to the detent.  It matters because S1 is the
    #: only channel: sag beyond ``seat_hysteresis_m`` drops the seat switch at
    #: the exact moment the capture becomes real.
    detent_backlash_m: float = 0.0015

    def __post_init__(self) -> None:
        if min(
            self.funnel_entrance_radius_m,
            self.rim_annulus_m,
            self.seat_travel_m,
            self.probe_height_m,
        ) <= 0:
            raise ValueError("geometry lengths must be positive")
        if min(self.detent_engage_travel_m, self.detent_throw_m) <= 0:
            raise ValueError("detent engagement geometry must be positive")
        if self.detent_backlash_m < 0:
            raise ValueError("backlash must be non-negative")
        if self.detent_engage_travel_m >= self.seat_travel_m:
            raise ValueError("detent must sit inside the funnel travel")

    @property
    def detent_plane_m(self) -> float:
        """Depth at which the head first meets the detent fingers."""

        return self.seat_travel_m - self.detent_engage_travel_m

    @classmethod
    def from_dock_geometry(
        cls, geometry: DockGeometry, **overrides: float
    ) -> "PassiveDetentGeometry":
        """Mirror an episode's funnel geometry so guidance aims at the same seat.

        The guidance stack is handed ``probe_height_m`` and ``seat_travel_m``
        from ``EpisodeConfig.dock_geometry``; a mechanism that disagreed with
        those would be measured flying at the wrong target rather than on its
        own merits.
        """

        return cls(
            funnel_entrance_radius_m=geometry.funnel_entrance_radius_m,
            rim_annulus_m=geometry.rim_annulus_m,
            seat_travel_m=geometry.seat_travel_m,
            seat_hysteresis_m=geometry.seat_hysteresis_m,
            probe_height_m=geometry.probe_height_m,
            bounce_speed_m_s=geometry.bounce_speed_m_s,
            **overrides,
        )


@dataclass(frozen=True)
class PassiveDetentParams:
    """Force model for the detent.  All engineering estimates, none measured.

    Defaults are the sizing a competent designer would actually choose:
    ``retention_force_n`` at the docked weight, because anything less drops
    the aircraft the moment it disarms, which is an unsafe event and not a
    trade.  The insertion ratio is a conventional asymmetric detent.  Every
    other default is set to whatever is most generous to this candidate.
    """

    #: The swept parameter.  Default is the review's backstop threshold:
    #: 47.7 g of docked aircraft and probe, 0.468 N.
    retention_force_n: float = 0.468
    #: Insertion resistance as a fraction of retention force.  1.0 is a
    #: symmetric ball detent; a chamfered lead-in with a steep retaining face
    #: gets to roughly 0.35; a one-way barb approaches 0.  Engineering
    #: estimate — this is the ratio measurement 2 of the review's evidence
    #: table would settle in an afternoon with a force gauge.
    insertion_force_ratio: float = 0.35
    #: Breakaway penalty on the loaded retaining face (stiction, gall, print
    #: layer lines).  Default 1.0 — no penalty — because that is the most
    #: favourable assumption available to this candidate.  Any measured value
    #: above 1.0 only widens the gap the module already reports.
    release_friction_factor: float = 1.0
    #: Docked aircraft plus probe allocation (hardware/dock/p0a-bench.md).
    docked_mass_kg: float = 0.0477
    #: Flying aircraft mass, for the precision-approach force budget.
    drone_mass_kg: float = 0.037
    #: Precision-approach acceleration ceiling from ``DroneParams``.  Times
    #: the aircraft mass this is the 0.074 N the deletion review calls the
    #: abort-transparency bound.
    approach_accel_ceiling_m_s2: float = 2.0
    #: Fraction of its own weight a hanging aircraft can convert into pull-out
    #: force by unloading its propellers.  1.0 = it can cut thrust entirely.
    unload_fraction: float = 1.0
    #: Time to spin down from hover thrust to zero once a descent is
    #: commanded.  Until it elapses only the control-authority term is
    #: available, which is what makes a stiff detent non-transparent to an
    #: abort rather than merely slow.  Engineering estimate.
    thrust_unload_s: float = 0.30
    #: Downward thrust the propellers can produce.  Zero for the stock
    #: unidirectional Crazyflie stack.  Set positive only to study a
    #: bidirectional-ESC variant — it is the single parameter that can open
    #: the hold/release window at all.
    reverse_thrust_n: float = 0.0
    #: How long S1 must read closed before capture is confirmed.  With one
    #: channel, persistence is the only evidence available; it buys debounce
    #: margin and nothing else, and specifically it does not buy independence.
    confirm_dwell_s: float = 0.20
    #: How long the supervisor waits for the seat switch to open after a
    #: release is commanded before declaring the dock stuck.  There is no
    #: actuator to help, so this is a diagnostic, not a recovery.
    release_timeout_s: float = 1.0

    def __post_init__(self) -> None:
        if self.retention_force_n < 0:
            raise ValueError("retention force must be non-negative")
        if self.insertion_force_ratio < 0:
            raise ValueError("insertion ratio must be non-negative")
        if self.release_friction_factor <= 0:
            raise ValueError("friction factor must be positive")
        if min(self.docked_mass_kg, self.drone_mass_kg) <= 0:
            raise ValueError("masses must be positive")
        if not 0.0 <= self.unload_fraction <= 1.0:
            raise ValueError("unload fraction is a fraction of weight")
        if self.reverse_thrust_n < 0:
            raise ValueError("reverse thrust must be non-negative")
        if min(self.confirm_dwell_s, self.release_timeout_s) <= 0:
            raise ValueError("supervisor timings must be positive")
        if self.thrust_unload_s < 0:
            raise ValueError("unload time must be non-negative")

    # -- derived force budget --------------------------------------------

    @property
    def hanging_weight_n(self) -> float:
        """Weight the detent carries once the aircraft disarms: 0.468 N."""

        return self.docked_mass_kg * G_M_S2

    @property
    def approach_control_force_n(self) -> float:
        """Net force a precision-approaching aircraft can command: 0.074 N."""

        return self.drone_mass_kg * self.approach_accel_ceiling_m_s2

    @property
    def insertion_force_n(self) -> float:
        return self.retention_force_n * self.insertion_force_ratio

    @property
    def breakaway_force_n(self) -> float:
        """Force needed at the detent face to move the head back past it."""

        return self.retention_force_n * self.release_friction_factor


def retention_window_n(params: PassiveDetentParams) -> tuple[float, float]:
    """Return ``(hold_min_n, release_max_n)`` for a passive detent.

    ``hold_min_n`` is the retention force that must be *exceeded* for an
    unpowered aircraft not to fall out.  ``release_max_n`` is the largest
    retention force a commanded departure can still break out of.  The pair
    is the whole argument about this architecture, computed rather than
    asserted, so a reader can put their own numbers in and check it.
    """

    friction = params.release_friction_factor
    hold_min = params.hanging_weight_n / friction
    release_max = (
        params.hanging_weight_n * params.unload_fraction + params.reverse_thrust_n
    ) / friction
    return hold_min, release_max


def window_is_empty(params: PassiveDetentParams) -> bool:
    """True when no retention force both holds the aircraft and lets it go.

    With unidirectional propellers this is unconditionally true, and not by
    coincidence: the same weight appears on both sides of the inequality.
    """

    hold_min, release_max = retention_window_n(params)
    return release_max <= hold_min


def admissible_retention_for_insertion(
    params: PassiveDetentParams,
    geometry: PassiveDetentGeometry,
    closing_speed_m_s: float,
    performance_scale: float = 1.0,
) -> float:
    """Largest retention force a probe closing at this speed can push past.

    Force available is the aircraft's control authority plus the kinetic
    energy it can spend deflecting the detent over its throw.  The kinetic
    term is real but small at the guidance stack's 0.03 m/s terminal creep;
    it is included because leaving it out would understate the candidate.
    """

    if params.insertion_force_ratio <= 0.0:
        return float("inf")
    thrust = params.approach_control_force_n * performance_scale
    kinetic = (
        0.5
        * params.drone_mass_kg
        * max(0.0, closing_speed_m_s) ** 2
        / geometry.detent_throw_m
    )
    return (thrust + kinetic) / params.insertion_force_ratio


@dataclass(frozen=True)
class PassiveDiagnostics:
    """Per-step mechanism truth the ``DockStepResult`` contract has no field for.

    Exposed on the mechanism rather than smuggled into the shared result type,
    so the engine contract stays exactly what every other candidate returns.
    """

    detent_engaged: bool
    #: The head reached the detent and could not push past it.
    insertion_blocked: bool
    #: A descent was demanded and the detent refused to let go.
    release_blocked: bool
    #: Seconds of continuously demanded descent, for the thrust-unload model.
    unload_s: float
    required_breakaway_n: float
    available_pullout_n: float


class _AbsentSwitch:
    """The keeper-closed channel this architecture does not have.

    ``FaultInjector`` unconditionally assigns a fault to ``keeper_switch``
    every step, so the attribute must exist.  It reads False forever, and
    injecting a stuck keeper switch here changes nothing.  That is not a free
    pass: it means a whole class of the campaign's fault coverage is
    structurally inapplicable, so a like-for-like fault-episode comparison
    against the baseline flatters this candidate.  Compare per fault kind.
    """

    def __init__(self) -> None:
        self.fault = SwitchFault.NONE

    def step(self, physical_state: bool) -> bool:
        return False


class _AbsentActuator:
    """Stand-in for the actuator this architecture deletes.

    ``FaultInjector`` writes ``jammed`` and the ``KEEPER_CLOSED`` fault
    trigger reads ``physically_closed``.  Jamming is a no-op — there is
    nothing to jam, which is the candidate's headline strength.
    ``physically_closed`` is mapped to detent engagement so that faults
    conditioned on "the mechanism is holding something" still fire; without
    that mapping the controller-reset fault would silently never arm and this
    candidate would look robust because it was never tested.
    """

    def __init__(self, dock: "PassiveDetentDock") -> None:
        self._dock = dock
        self.jammed = False
        self.position = 0.0

    @property
    def physically_closed(self) -> bool:
        return self._dock.detent_engaged

    @property
    def physically_open(self) -> bool:
        return not self._dock.detent_engaged


class PassiveConfirmSupervisor:
    """Capture confirmation from a single sensed channel.

    This is deliberately **not** ``aiur.dock_controller.DockController``, and
    the substitution is itself a study result rather than a convenience.  The
    flight controller's contract is built on two things this architecture does
    not have: a keeper it can command, and a second switch to check the first
    against.  Feeding it ``keeper_closed_switch = seat_switch`` would satisfy
    its type signature and fake the independence its entire safety argument
    rests on.  So adopting this architecture means deleting the qualified
    latch state machine and its bench evidence and writing a new one — a cost
    that belongs in the trade next to the deleted servo.

    What survives from the flight controller: the state vocabulary (so gates,
    telemetry and reports keep working), the rule that confirmation is a
    sensed fact rather than a command, and fail-locked behaviour after
    capture.  Fail-locked is not a design choice here; a passive dock has no
    other mode.

    Restart handling is told to the supervisor explicitly (``restarted=True``)
    instead of inferred from the switches, because with one channel there is
    nothing to infer from.  Real firmware reads this from its reset-cause
    register.  The baseline distinguishes "stuck mechanism" from "aircraft I
    was holding before I rebooted" by reading the keeper switch against the
    seat; that discrimination is simply unavailable here.
    """

    def __init__(
        self,
        *,
        confirm_dwell_s: float = 0.20,
        release_timeout_s: float = 1.0,
        restarted: bool = False,
    ) -> None:
        if confirm_dwell_s <= 0 or release_timeout_s <= 0:
            raise ValueError("timings must be positive")
        self.confirm_dwell_s = confirm_dwell_s
        self.release_timeout_s = release_timeout_s
        self.state = DockState.OPEN
        self.fault_reason: str | None = None
        self._restarted = restarted
        self._entered_at_s: float | None = None
        self._last_now_s: float | None = None

    def _transition(
        self, state: DockState, now_s: float, fault_reason: str | None = None
    ) -> None:
        self.state = state
        self._entered_at_s = now_s
        self.fault_reason = fault_reason

    def _elapsed(self, now_s: float) -> float:
        if self._entered_at_s is None:
            return 0.0
        return now_s - self._entered_at_s

    def _output(self, seat_switch: bool) -> DockOutput:
        return DockOutput(
            state=self.state,
            # There is no actuator.  The field is reported OPEN forever and
            # must never be read as evidence of anything; it exists because
            # the telemetry schema is shared across architectures.
            keeper_command=KeeperCommand.OPEN,
            capture_confirmed=self.state is DockState.CAPTURED and seat_switch,
            fault_reason=self.fault_reason,
        )

    def step(
        self,
        now_s: float,
        seat_switch: bool,
        commands: DockCommands,
    ) -> DockOutput:
        """Advance the confirmation logic on one switch and the commands."""

        if self._last_now_s is not None and now_s < self._last_now_s:
            raise ValueError("now_s must be monotonic")
        self._last_now_s = now_s

        if self._restarted:
            # One boot-time decision.  An occupied seat after a restart is
            # assumed to be an aircraft, because assuming otherwise is the
            # mistake that drops one — and unlike the baseline, assuming
            # "holding" costs nothing mechanically, since there is nothing to
            # command open.  The cost is entirely in indication: a stuck-
            # actuated S1 confirms a capture of nothing on every restart.
            self._restarted = False
            if seat_switch:
                self._transition(DockState.CAPTURED, now_s, "seat_occupied_at_restart")
                return self._output(seat_switch)

        if commands.emergency_release:
            # Authority to *declare* a release.  It moves no hardware: the
            # aircraft still has to fly itself out, and if the detent is
            # stiffer than the aircraft's pull-out force it will not.
            if self.state is not DockState.RELEASING:
                self._transition(DockState.RELEASING, now_s)
            return self._output(seat_switch)

        if self.state is DockState.OPEN:
            if commands.capture_enable and seat_switch:
                self._transition(DockState.LOCKING, now_s)

        elif self.state is DockState.LOCKING:
            # Nothing is locking.  The dwell is the only evidence a single
            # channel can accumulate: that the seat report is persistent
            # rather than a bounce.
            if not commands.capture_enable or not seat_switch:
                self._transition(DockState.FAULT_OPEN, now_s, "seat_lost_during_dwell")
            elif self._elapsed(now_s) >= self.confirm_dwell_s:
                self._transition(DockState.CAPTURED, now_s)

        elif self.state is DockState.CAPTURED:
            if commands.release_request:
                self._transition(DockState.RELEASING, now_s)
            elif not seat_switch:
                # The baseline would fail locked to avoid dropping an
                # aircraft.  Here it is not a decision: the mechanism is
                # already locked and cannot be told otherwise.  The state is
                # recorded so the loss of the only channel is visible.
                self._transition(
                    DockState.FAULT_LOCKED, now_s, "seat_lost_after_capture"
                )

        elif self.state is DockState.RELEASING:
            if not seat_switch:
                self._transition(DockState.OPEN, now_s)
            elif self._elapsed(now_s) >= self.release_timeout_s:
                self._transition(
                    DockState.FAULT_LOCKED, now_s, "release_timeout_no_actuator"
                )

        elif self.state is DockState.FAULT_OPEN:
            if commands.reset_fault and not seat_switch:
                self._transition(DockState.OPEN, now_s)

        elif self.state is DockState.FAULT_LOCKED:
            if commands.reset_fault and seat_switch:
                self._transition(DockState.CAPTURED, now_s)

        return self._output(seat_switch)


class PassiveDetentDock:
    """One funnel with a sprung detent and no actuator, serving one probe.

    Truth versus indication is kept exactly as in ``dock_physics.py``:
    ``detent_engaged`` and ``seat_truth`` are what the mechanism is doing,
    ``reported_s1`` is what the one switch says, and they are allowed to
    disagree.  ``keeper_closed_truth`` in the shared result carries detent
    engagement — the truth field means "the mechanism is physically retaining
    the head", which is the question the engine's disarm check is asking.
    ``reported_s2`` is False forever, because there is no such sensor.
    """

    def __init__(
        self,
        geometry: PassiveDetentGeometry | None = None,
        params: PassiveDetentParams | None = None,
        *,
        dt_s: float,
    ) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self.geometry = geometry if geometry is not None else PassiveDetentGeometry()
        self.params = params if params is not None else PassiveDetentParams()
        self._dt_s = dt_s
        self.supervisor = PassiveConfirmSupervisor(
            confirm_dwell_s=self.params.confirm_dwell_s,
            release_timeout_s=self.params.release_timeout_s,
        )
        #: Alias so tooling written against the baseline finds the logic.
        self.controller = self.supervisor
        self.seat_switch = Switch(dt_s=dt_s)
        #: Named for the fault injector, which writes to it every step.
        self.keeper_switch = _AbsentSwitch()
        self.servo = _AbsentActuator(self)
        self.probe_phase = ProbePhase.FREE
        self.detent_engaged = False
        self.last_diagnostics = PassiveDiagnostics(
            detent_engaged=False,
            insertion_blocked=False,
            release_blocked=False,
            unload_s=0.0,
            required_breakaway_n=self.params.breakaway_force_n,
            available_pullout_n=0.0,
        )
        self._prev_rel_z: float | None = None
        self._was_confirmed = False
        self._dropped = False
        self._unload_s = 0.0

    # -- CaptureMechanism protocol ----------------------------------------

    def seed_seated(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Place a probe at the seat with the detent snapped behind it.

        Scenarios that start captured assert the mechanical state rather than
        earning it, exactly as the baseline does; the pre-roll then walks the
        supervisor through a legitimate confirmation from the seat switch.
        """

        self.probe_phase = ProbePhase.SEATED
        self.detent_engaged = True
        self._prev_rel_z = self.geometry.seat_travel_m
        self._seat(drone, dock_center, dock_velocity)

    def reset_controller(self) -> None:
        """Model a controller brownout.

        This is the case the passive architecture exists to win.  In the
        baseline a brownout arrives with the servo mid-travel on a shared
        rail, and the controller has to re-derive what it is holding.  Here
        the mechanism is a spring: nothing about retention is electrical, so
        a reset cannot change what is held, only what is believed about it.
        The supervisor is rebuilt and told it restarted.
        """

        self.supervisor = PassiveConfirmSupervisor(
            confirm_dwell_s=self.supervisor.confirm_dwell_s,
            release_timeout_s=self.supervisor.release_timeout_s,
            restarted=True,
        )
        self.controller = self.supervisor
        self._was_confirmed = False

    @property
    def holds_unpowered(self) -> bool:
        """Can the detent hold an aircraft that has stopped flying?

        The single question the whole candidate turns on, kept as a property
        so tests and the study read the same expression the physics uses.
        """

        return self.params.breakaway_force_n > self.params.hanging_weight_n

    # -- mechanical truth --------------------------------------------------

    def _probe_tip(self, drone: DroneBody) -> Vec3:
        return drone.position + Vec3(0.0, 0.0, self.geometry.probe_height_m)

    def _funnel_allowed_radius(self, depth_m: float) -> float:
        """Taper: allowed lateral offset shrinks linearly toward the throat."""

        g = self.geometry
        fraction = max(0.0, 1.0 - depth_m / g.seat_travel_m)
        return g.funnel_entrance_radius_m * fraction + 0.002

    def _constrain_to_funnel(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        rel = self._probe_tip(drone) - dock_center
        allowed = self._funnel_allowed_radius(rel.z)
        lateral = rel.lateral_norm()
        if lateral > allowed and lateral > 0.0:
            scale = allowed / lateral
            corrected = Vec3(rel.x * scale, rel.y * scale, rel.z)
            tip = dock_center + corrected
            drone.position = tip - Vec3(0.0, 0.0, self.geometry.probe_height_m)
            drone.velocity = dock_velocity.lateral().with_z(drone.velocity.z)

    def _set_rel_z(self, drone: DroneBody, dock_center: Vec3, rel_z: float) -> None:
        rel = self._probe_tip(drone) - dock_center
        tip = dock_center + Vec3(rel.x, rel.y, rel_z)
        drone.position = tip - Vec3(0.0, 0.0, self.geometry.probe_height_m)

    def _seat(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Pin a seated probe hard against the seat."""

        self._set_rel_z(drone, dock_center, self.geometry.seat_travel_m)
        drone.velocity = dock_velocity

    def _hang_on_detent(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Let a retained aircraft sag onto the detent's retaining face.

        The weight transfer that happens the instant the aircraft disarms.
        It is a millimetre-scale motion and it matters only because S1 is the
        only channel: sag past the seat switch's hysteresis silences the one
        sensor at the exact moment the capture becomes load-bearing.
        """

        g = self.geometry
        self._set_rel_z(drone, dock_center, g.seat_travel_m - g.detent_backlash_m)
        drone.velocity = dock_velocity

    def _hold_against_seat(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Armed aircraft inside the retained band: seat above, detent below."""

        g = self.geometry
        rel_z = (self._probe_tip(drone) - dock_center).z
        clamped = min(g.seat_travel_m, max(g.seat_travel_m - g.detent_backlash_m, rel_z))
        self._set_rel_z(drone, dock_center, clamped)
        vertical = drone.velocity.z
        relative = vertical - dock_velocity.z
        if relative > 0.0 and rel_z >= g.seat_travel_m:
            vertical = dock_velocity.z
        if relative < 0.0 and rel_z <= g.seat_travel_m - g.detent_backlash_m:
            vertical = dock_velocity.z
        drone.velocity = dock_velocity.lateral().with_z(vertical)

    # -- force model -------------------------------------------------------

    def _pullout_force_available_n(self, drone: DroneBody) -> float:
        """Downward force the aircraft can apply at the detent face.

        Disarmed, that is its weight and nothing else.  Armed, it is the
        precision-approach control authority until the propellers have had
        time to spin down, and then the larger of that and a full unload —
        larger, not the sum, because at zero thrust the control term does not
        also exist.  Reverse thrust is added only if the study asks for
        propellers that can push.
        """

        p = self.params
        if not drone.armed:
            return p.hanging_weight_n
        available = p.approach_control_force_n * drone.performance_scale
        if self._unload_s >= p.thrust_unload_s:
            available = max(
                available, p.hanging_weight_n * p.unload_fraction + p.reverse_thrust_n
            )
        return available

    def _insertion_force_available_n(
        self, drone: DroneBody, closing_m_s: float
    ) -> float:
        p = self.params
        thrust = p.approach_control_force_n * drone.performance_scale
        kinetic = (
            0.5
            * p.drone_mass_kg
            * max(0.0, closing_m_s) ** 2
            / self.geometry.detent_throw_m
        )
        return thrust + kinetic

    # -- main step ---------------------------------------------------------

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        drone: DroneBody | None,
        commands: DockCommands,
    ) -> DockStepResult:
        """Advance mechanics, the seat switch, and the confirmation logic."""

        g = self.geometry
        events: list[Event] = []
        contact_speed: float | None = None
        seat_truth = False
        insertion_blocked = False
        release_blocked = False
        available = 0.0

        if drone is None:
            self.probe_phase = ProbePhase.FREE
            self.detent_engaged = False
            self._prev_rel_z = None
            self._unload_s = 0.0
        else:
            rel = self._probe_tip(drone) - dock_center
            closing = (drone.velocity - dock_velocity).z

            # Descent demand drives the propeller spin-down model.  It is read
            # from achieved relative velocity rather than from the command
            # because the mechanism only ever sees the body.
            if closing < -_DESCENT_DEADBAND_M_S:
                self._unload_s += self._dt_s
            else:
                self._unload_s = 0.0

            available = self._pullout_force_available_n(drone)
            holds = available < self.params.breakaway_force_n

            if self.probe_phase is ProbePhase.FREE:
                crossed_up = (
                    self._prev_rel_z is not None
                    and self._prev_rel_z < 0.0
                    and rel.z >= 0.0
                )
                if crossed_up:
                    lateral = rel.lateral_norm()
                    if lateral <= g.funnel_entrance_radius_m:
                        if closing > g.bounce_speed_m_s:
                            contact_speed = closing
                            events.append(
                                Event(
                                    EventKind.OVERSPEED_CONTACT,
                                    now_s,
                                    detail=f"closing={closing:.3f}",
                                )
                            )
                            drone.velocity = drone.velocity.with_z(
                                dock_velocity.z - 0.5 * closing
                            )
                        else:
                            contact_speed = closing
                            self.probe_phase = ProbePhase.INSERTED
                            events.append(
                                Event(
                                    EventKind.FUNNEL_INSERTION,
                                    now_s,
                                    detail=f"closing={closing:.3f}",
                                )
                            )
                    elif lateral <= g.funnel_entrance_radius_m + g.rim_annulus_m:
                        events.append(
                            Event(
                                EventKind.PROP_FUNNEL_CONTACT,
                                now_s,
                                detail=f"lateral={lateral:.3f}",
                            )
                        )
                        drone.velocity = drone.velocity.with_z(
                            dock_velocity.z - max(0.05, 0.5 * closing)
                        )

            elif self.probe_phase is ProbePhase.INSERTED:
                if rel.z < 0.0:
                    self.probe_phase = ProbePhase.FREE
                    self.detent_engaged = False
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="clear_of_funnel")
                    )
                else:
                    if rel.z >= g.detent_plane_m:
                        push = (
                            self._insertion_force_available_n(drone, closing)
                            if drone.armed
                            else 0.0
                        )
                        if push < self.params.insertion_force_n:
                            # Stalled against the detent, short of the seat.
                            # S1 never makes, so the supervisor never sees a
                            # capture and the aircraft's own watchdog takes it
                            # away.  Failing to capture is a safe outcome; it
                            # is failing to *say so* that is not.
                            insertion_blocked = True
                            self._set_rel_z(drone, dock_center, g.detent_plane_m)
                            if closing > 0.0:
                                drone.velocity = drone.velocity.with_z(dock_velocity.z)
                            rel = self._probe_tip(drone) - dock_center
                    if rel.z >= g.seat_travel_m and not insertion_blocked:
                        self.probe_phase = ProbePhase.SEATED
                        self.detent_engaged = True
                        self._seat(drone, dock_center, dock_velocity)
                        events.append(
                            Event(EventKind.PROBE_SEATED, now_s, detail="detent_snap")
                        )
                    else:
                        self._constrain_to_funnel(drone, dock_center, dock_velocity)

            elif self.probe_phase is ProbePhase.SEATED:
                descending = closing < -_DESCENT_DEADBAND_M_S
                if not holds and not drone.armed:
                    # The detent is softer than the aircraft it is holding.
                    # This is the failure the review predicts for any
                    # abort-transparent spring, and it is an unsafe event.
                    # The fall itself is not modelled: a disarmed body is not
                    # integrated by the engine, and the episode terminates on
                    # the unsafe event, so nothing after the release matters.
                    self.detent_engaged = False
                    self.probe_phase = ProbePhase.INSERTED
                    if not self._dropped:
                        self._dropped = True
                        events.append(
                            Event(
                                EventKind.DROPPED_AIRCRAFT,
                                now_s,
                                detail=(
                                    f"breakaway={self.params.breakaway_force_n:.3f}N "
                                    f"<= weight={available:.3f}N"
                                ),
                            )
                        )
                elif not holds and descending:
                    self.detent_engaged = False
                    self.probe_phase = ProbePhase.INSERTED
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="detent_released")
                    )
                elif not drone.armed:
                    self._hang_on_detent(drone, dock_center, dock_velocity)
                else:
                    release_blocked = descending
                    self._hold_against_seat(drone, dock_center, dock_velocity)

            rel = self._probe_tip(drone) - dock_center
            seat_truth = (
                self.probe_phase is ProbePhase.SEATED
                and rel.z >= g.seat_travel_m - g.seat_hysteresis_m
            )
            self._prev_rel_z = rel.z

        reported_s1 = self.seat_switch.step(seat_truth)
        # Detent engagement is a real physical fact that no sensor in this
        # architecture reads.  It is offered to the absent channel and comes
        # back False, every step, on purpose: reporting False is not a
        # placeholder for a sensor that might be fitted later, it is the
        # architecture, and it is exactly the gap in the safety claim.
        reported_s2 = self.keeper_switch.step(self.detent_engaged)

        output = self.supervisor.step(now_s, reported_s1, commands)

        if output.capture_confirmed and not self._was_confirmed:
            if seat_truth and self.detent_engaged:
                events.append(Event(EventKind.CAPTURE_CONFIRMED, now_s))
                if not self.holds_unpowered and not self._dropped:
                    # The weight transfer, scored at the instant the
                    # confirmation authorises it rather than one step later.
                    #
                    # This is not a prediction and it is not the mechanism
                    # flattering itself in the other direction.  The guidance
                    # contract is `if capture_confirmed and seat_confirmed:
                    # disarm` (guidance.py), so the motors stop in the same
                    # step this event is emitted, and the engine ends the
                    # episode in that same step because the RECOVER script
                    # item completes on GuidancePhase.CAPTURED.  A drop
                    # deferred by one step is a drop that is never reported,
                    # and a candidate that looks safe because its unsafe
                    # event landed after the last step is worse than useless.
                    # The armed->disarmed path below still fires in scenarios
                    # that keep running; this guard is why the same event
                    # cannot be counted twice.
                    self._dropped = True
                    events.append(
                        Event(
                            EventKind.DROPPED_AIRCRAFT,
                            now_s,
                            detail=(
                                f"confirmed capture with breakaway="
                                f"{self.params.breakaway_force_n:.3f}N <= weight="
                                f"{self.params.hanging_weight_n:.3f}N"
                            ),
                        )
                    )
            else:
                events.append(
                    Event(
                        EventKind.FALSE_CAPTURE_CONFIRMED,
                        now_s,
                        detail="confirmed from the seat channel alone",
                    )
                )
        if self._was_confirmed and not output.capture_confirmed:
            events.append(Event(EventKind.RELEASED, now_s))
        self._was_confirmed = output.capture_confirmed

        self.last_diagnostics = PassiveDiagnostics(
            detent_engaged=self.detent_engaged,
            insertion_blocked=insertion_blocked,
            release_blocked=release_blocked,
            unload_s=self._unload_s,
            required_breakaway_n=self.params.breakaway_force_n,
            available_pullout_n=available,
        )

        return DockStepResult(
            probe_phase=self.probe_phase,
            seat_truth=seat_truth,
            keeper_closed_truth=self.detent_engaged,
            reported_s1=reported_s1,
            reported_s2=reported_s2,
            controller=output,
            contact_closing_speed_m_s=contact_speed,
            events=tuple(events),
        )


@dataclass(frozen=True)
class PassiveDetentSpec:
    """Trade-study entry for the passive snap-detent candidate."""

    key: str = "passive"
    name: str = "Passive snap-detent (no actuator)"
    summary: str = (
        "The baseline 180 mm funnel with the keeper and its servo deleted: a "
        "sprung detent printed into the throat snaps behind the probe head, "
        "and release is by commanded thrust — the aircraft flies out."
    )
    #: Funnel, printed detent ring, S1 seat switch.  Nothing else.
    part_count: int = 3
    actuator_count: int = 0
    sensed_channels: int = 1
    #: Funnel 52.6 g (CAD-manifest geometry estimate) plus a few grams of
    #: detent ring and switch.  Engineering target; nothing weighed.
    est_dock_mass_g: float = 57.0
    #: Same probe as the baseline, plus a retaining groove.
    est_probe_mass_g: float = 2.0
    known_weaknesses: tuple[str, ...] = (
        "The hold/release window is empty, and not marginally: the aircraft "
        "hangs from the detent, so retention must exceed its weight, while "
        "the most force it can apply to escape is that same weight unloaded "
        "off its propellers. Hold needs R*f > W and release needs R*f <= W. "
        "No retention force satisfies both, at any friction factor.",
        "Sized to hold the 0.468 N docked weight with a conventional 0.35 "
        "insertion ratio, the detent needs 0.164 N to enter, against the "
        "0.085 N a 37 g aircraft has (0.074 N of precision-approach "
        "authority plus the kinetic credit of its 0.03 m/s terminal creep). "
        "The probe cannot get in at all, so this candidate does not capture "
        "at its own honest sizing. Entry needs a lead-in asymmetry under "
        "0.18, which is a near one-way barb.",
        "One sensed channel: capture_confirmed = S1, not S1 AND S2. On the "
        "empty-throat cut set this is no worse than Rev-A — a stuck-actuated "
        "S1 confirms a capture on nothing in both — but the Rev-B fix has no "
        "counterpart here. S2', sensing 'keeper closed with a mast in the "
        "slot', closes that cut set mechanically for the baseline at zero "
        "added parts; a dock with no keeper has nothing to put the "
        "discrimination on, so finding 5 stays open permanently. The "
        "deletion review rejected exactly this collapse to one channel, on "
        "the grounds that one sensor cannot be two.",
        "Nothing senses retention, so weight transfer can silence the only "
        "channel. The detent holds at its retaining face, not against the "
        "seat, so a disarming aircraft sags by the detent backlash; sag past "
        "the seat switch's 4 mm hysteresis drops S1 at the instant the "
        "capture becomes load-bearing, and the system then reports a release "
        "while physically holding the aircraft. Rev-B would have to hold "
        "backlash under the switch hysteresis as a gated tolerance.",
        "No commanded release. Every release path — nominal, abort, and "
        "emergency — is the aircraft flying itself out. An aircraft that has "
        "lost thrust authority, or is already disarmed, cannot be released "
        "by anything at all, and the P0-A gate's >=10 emergency-release "
        "trials have no article to run against.",
        "Adopting it deletes the qualified DockController and its bench "
        "evidence. Its contract needs a commandable keeper and a second "
        "channel; a passive dock has neither, so the latch state machine has "
        "to be rewritten and re-argued. That cost belongs next to the "
        "deleted servo, not hidden behind it.",
        "Detent retention force is unmeasurable in flight and drifts with "
        "print variation, spring set after cycling, and temperature. There "
        "is no channel that would notice, so degradation is only ever "
        "discovered by an aircraft falling.",
        "Three of the twin's eleven fault kinds (both keeper-switch stucks "
        "and the servo jam) are structurally inert here, so a like-for-like "
        "fault-episode comparison overstates its robustness. The correct "
        "comparison is per fault kind, not per campaign.",
        "Abort transparency is unreachable by a factor of about 6: a detent "
        "stiff enough to matter is one the supervisor has to spin the "
        "propellers down to escape, so an abort inside the throat is delayed "
        "and then uncontrolled rather than flown.",
    )

    def build(self, dt_s: float) -> PassiveDetentDock:
        """Return a ready mechanism at the honest default sizing."""

        return PassiveDetentDock(
            PassiveDetentGeometry(), PassiveDetentParams(), dt_s=dt_s
        )


SPEC = PassiveDetentSpec()


def passive_mechanism_factory(
    params: PassiveDetentParams | None = None,
    geometry_overrides: dict | None = None,
):
    """Build an ``EpisodeConfig.mechanism_factory`` for a chosen detent sizing.

    The study sweeps ``retention_force_n``; this is the seam that lets it,
    while keeping the funnel geometry locked to whatever the episode told the
    guidance stack to aim at.
    """

    chosen = params if params is not None else PassiveDetentParams()
    overrides = dict(geometry_overrides or {})

    def build(config, dt_s: float) -> PassiveDetentDock:
        geometry = PassiveDetentGeometry.from_dock_geometry(
            config.dock_geometry, **overrides
        )
        # Keep the force budget consistent with the episode's aircraft: a
        # heavier vehicle or a different acceleration ceiling changes both
        # sides of the trade, and reading them from the config keeps the
        # mechanism honest when the study varies the airframe.
        tuned = replace(
            chosen,
            drone_mass_kg=config.drone_params.mass_kg,
            approach_accel_ceiling_m_s2=config.drone_params.max_accel_m_s2,
        )
        return PassiveDetentDock(geometry, tuned, dt_s=dt_s)

    return build
