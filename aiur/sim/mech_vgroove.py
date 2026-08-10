"""V-trough and over-centre latch: a capture architecture for the design study.

The baseline (``aiur.sim.dock_physics``) is a Ø180 mm funnel, a round probe
head, and a servo-driven sliding fork.  Its retention is *held* by the
actuator's commanded position, so every power-loss and controller-restart
story in docs/dock-fmeca.md has to be defended in software — FM-KP-09,
FM-CH-06, and the whole fail-locked branch of ``DockController`` exist
because a commanded-open keeper is a dropped aircraft.

This candidate attacks that from the mechanism side:

* the probe carries a transverse **cross-bar** instead of a round head;
* the dock is a shallow **V-trough**, so lateral error across the groove is
  converted into centring by two flat flanks rather than by a deep cone;
* the latch is an **over-centre bail** that snaps past dead centre onto a
  stop.  Past centre it is bistable — the toggle spring holds it closed with
  no power at all — so a flat battery, an unmated servo connector, or a
  brownout mid-cruise cannot open it.

What it gives up is stated in the model, not in the prose.  A V constrains
two translations by geometry and leaves rotation about the vertical almost
free, so the cross-bar must arrive roughly aligned in yaw or it wedges on
the converging flanks and never reaches the seat.  The baseline has no such
requirement: a round head in a cone does not care which way the aircraft is
pointing.  That asymmetry is the whole trade, and it is modelled here rather
than argued.

Physics status, in the same spirit as ``dock_physics``: every number below
is an **engineering-estimate surrogate** pending bench measurement.  None of
it is a vendor figure.  The two places where it is weakest are called out at
the point of use — the yaw model (there is no yaw state anywhere else in the
twin, see :attr:`VGrooveGeometry.nominal_yaw_error_rad`) and the over-centre
force budget (:attr:`OverCentreLatchParams.release_force_margin`, a ratio
that stands in for a force-gauge measurement nobody has taken).

Contract notes, because a candidate that quietly changes the contract is not
a comparison:

* The latch logic is the **real** ``aiur.dock_controller.DockController``,
  un-mocked, exactly as the baseline runs it.  A candidate that ships its own
  latch state machine would be comparing two experiments at once.
* Truth and indication are separate.  ``keeper_closed_truth`` is the physical
  question *is the bail across the trough under the bar*; ``reported_s2`` is
  what a switch on the over-centre stop says.  They are deliberately allowed
  to disagree, which is how ``FALSE_CAPTURE_CONFIRMED`` can be emitted at all.
* The seat plane is pinned to ``EpisodeConfig.dock_geometry`` (100 mm above
  the dock reference, 50 mm probe height).  The shared guidance stack derives
  its seat-confirm and seat-plausibility gates from that field, so a
  candidate that moved the seat would be testing a detuned supervisor rather
  than a different mechanism.  The consequence is that this module can only
  make the dock *shallower* (35 mm of trough instead of 100 mm of cone), not
  *closer*, and the resulting mass saving is an estimate carried by
  :data:`SPEC`, not a simulated result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from ..dock_controller import DockController, DockInputs, KeeperCommand
from .bodies import DroneBody
from .dock_physics import DockCommands, DockStepResult, ProbePhase
from .events import Event, EventKind
from .sensors import Switch
from .vec import Vec3


@dataclass(frozen=True)
class VGrooveGeometry:
    """Trough and cross-bar geometry.  Every value is an engineering target.

    The trough is a shallow prism: a V across the groove (hard centring, the
    axis the architecture is good at) and a much gentler taper along the
    groove (weak centring, because a bar lying in a V slides freely along its
    own axis — that is what a V-block *is*).  Modelling those two axes with
    one radius, as the baseline funnel does, would hide the anisotropy that
    is this candidate's defining property.
    """

    #: Seat height above the dock reference point.  Pinned to the baseline's
    #: ``DockGeometry.seat_travel_m`` on purpose; see the module docstring.
    seat_travel_m: float = 0.100
    #: Cross-bar height above the aircraft reference point.
    probe_height_m: float = 0.050
    #: Depth of the trough below the seat.  The headline geometric claim: a V
    #: needs 35 mm where the Ø180 mm cone needs 100 mm, because two flanks
    #: centre in one axis without needing a full cone of approach.
    trough_depth_m: float = 0.035

    #: Half-width across the groove at the mouth (the flared entry).  This is
    #: not a free choice: it follows from the depth.  55 mm of half-width over
    #: 35 mm of depth is a flank about 56 deg off vertical, already shallow;
    #: widening it to the funnel's 90 mm at the same depth would need 68 deg,
    #: which no longer centres anything.  A shallower dock *is* a narrower
    #: mouth, and the unsafe-event count under wind is what that costs.
    trough_mouth_half_width_m: float = 0.055
    #: Half-length along the groove at the mouth.  Larger than the width:
    #: the trough is a slot, not a hole.
    trough_mouth_half_length_m: float = 0.075
    #: Half-width across the groove at the seat — the bar's slot clearance.
    #: 3.5 mm on a Ø4 mm bar, i.e. 1.5 mm per side, the same order as the
    #: Rev-B keeper-slot target in docs/dock-deletion-review.md.
    trough_seat_half_width_m: float = 0.0035
    #: Half-length along the groove at the seat.  Deliberately 3.4× the
    #: width: along-groove position is the axis the V does *not* fix, and the
    #: model must not pretend otherwise.
    trough_seat_half_length_m: float = 0.012
    #: Band outside the mouth where a plane crossing means the guarded prop
    #: disc meets the trough structure.  The V dock is physically smaller
    #: than the Ø180 mm funnel, so this band starts closer in — a real cost
    #: of the shallow-and-light claim, not a modelling convenience.
    rim_annulus_m: float = 0.045

    #: Cross-bar length.  Long enough to bridge the V flanks with margin,
    #: short enough to stay inside a 37 g aircraft's footprint.
    crossbar_length_m: float = 0.045
    crossbar_radius_m: float = 0.002

    #: Seat hysteresis before the physical seat switch drops out.
    seat_hysteresis_m: float = 0.004
    #: Above this closing speed the bar bounces out instead of entering.
    bounce_speed_m_s: float = 0.30
    #: Relative descent that lifts an unlatched bar out of the trough.  A V
    #: seat is pure gravity registration: it has no axial retention at all,
    #: which is why this is ~0 rather than the baseline's 0.05 m/s collet
    #: figure.  docs/dock-deletion-review.md shows the baseline's collet
    #: changes no outcome in indoor calm air, so the difference is honest
    #: rather than punitive.
    unseat_speed_m_s: float = 0.0005

    #: How far below the seat the bail sweeps.  The bail passes *under* the
    #: bar and traps it against the V apex.
    bail_plane_below_seat_m: float = 0.014
    #: Latch position at which the bail's leading edge first occupies the
    #: trough.  From here on the bar cannot leave without the latch moving:
    #: this is the abort-transparency cost, made mechanical.
    bail_in_throat_position: float = 0.30

    #: Rate at which the converging flanks derotate a yawed bar while it
    #: bears on them.  MODELLING ASSUMPTION with no measurement behind it:
    #: ~3.4 °/s represents a heavily damped pull-in against the aircraft's
    #: own yaw hold.  It is the single most influential invented number in
    #: this module and the first thing a bench test should replace.
    yaw_align_rate_rad_s: float = 0.06
    #: Beyond this yaw the flank contact self-locks (a shallow wedge with
    #: friction does not slide) and no derotation happens at all, so the bar
    #: can never reach the seat.  Engineering estimate.
    yaw_wedge_limit_rad: float = 0.35
    #: Yaw error the aircraft is assumed to arrive with.  MODELLING
    #: ASSUMPTION: the twin has no yaw state — no yaw dynamics, no yaw
    #: sensing, no yaw command — so this is a scenario parameter with a
    #: stated default rather than a derived quantity.  5° is a plausible
    #: residual heading-hold error for a Crazyflie-class aircraft on an
    #: external optical reference; it is not measured, and it is held
    #: constant through an approach because nothing in the twin would move
    #: it.  Sweep it (see :func:`vgroove_factory`) rather than trusting it.
    nominal_yaw_error_rad: float = 0.087

    def __post_init__(self) -> None:
        if self.trough_depth_m <= 0 or self.trough_depth_m >= self.seat_travel_m:
            raise ValueError("trough depth must be positive and inside the seat travel")
        if self.trough_seat_half_width_m >= self.trough_mouth_half_width_m:
            raise ValueError("the trough must converge across the groove")
        if self.trough_seat_half_length_m >= self.trough_mouth_half_length_m:
            raise ValueError("the trough must converge along the groove")
        if self.bail_plane_below_seat_m <= 0:
            raise ValueError("the bail must sweep below the seat")
        if self.crossbar_radius_m >= self.trough_seat_half_width_m:
            raise ValueError("the bar must fit the seat slot when aligned")
        if self.yaw_align_rate_rad_s < 0 or self.yaw_wedge_limit_rad <= 0:
            raise ValueError("yaw model parameters must be non-negative")

    # -- derived planes ---------------------------------------------------

    @property
    def mouth_z_m(self) -> float:
        """Height of the trough mouth above the dock reference point."""

        return self.seat_travel_m - self.trough_depth_m

    @property
    def bail_plane_z_m(self) -> float:
        return self.seat_travel_m - self.bail_plane_below_seat_m

    # -- trough section ---------------------------------------------------

    def half_width_at(self, height_m: float) -> float:
        """Across-groove half-width at ``height_m`` above the mouth."""

        fraction = min(1.0, max(0.0, height_m / self.trough_depth_m))
        taper = self.trough_mouth_half_width_m - self.trough_seat_half_width_m
        return self.trough_seat_half_width_m + taper * (1.0 - fraction)

    def half_length_at(self, height_m: float) -> float:
        """Along-groove half-length at ``height_m`` above the mouth."""

        fraction = min(1.0, max(0.0, height_m / self.trough_depth_m))
        taper = self.trough_mouth_half_length_m - self.trough_seat_half_length_m
        return self.trough_seat_half_length_m + taper * (1.0 - fraction)

    def bar_half_span_m(self, yaw_error_rad: float) -> float:
        """Across-groove half-extent of the bar at a given yaw error.

        A bar aligned with the groove occupies only its own radius; a yawed
        bar sweeps its own length across the groove.  This one line is the
        entire reason the architecture cares about heading.
        """

        swept = 0.5 * self.crossbar_length_m * abs(math.sin(yaw_error_rad))
        return swept + self.crossbar_radius_m

    def max_height_for_yaw(self, yaw_error_rad: float) -> float:
        """Highest point in the trough a bar at this yaw can reach.

        Equal to the full depth when the bar fits the seat slot; otherwise
        the height at which the converging flanks close on the bar's swept
        span.  Returns metres above the mouth plane.
        """

        span = self.bar_half_span_m(yaw_error_rad)
        if span <= self.trough_seat_half_width_m:
            return self.trough_depth_m
        taper = self.trough_mouth_half_width_m - self.trough_seat_half_width_m
        fraction = (span - self.trough_seat_half_width_m) / taper
        return max(0.0, self.trough_depth_m * (1.0 - fraction))

    @property
    def yaw_seat_limit_rad(self) -> float:
        """Largest yaw error that still lets the bar reach the seat."""

        clearance = self.trough_seat_half_width_m - self.crossbar_radius_m
        ratio = min(1.0, 2.0 * clearance / self.crossbar_length_m)
        return math.asin(ratio)


@dataclass(frozen=True)
class OverCentreLatchParams:
    """Toggle-latch parameters.  Engineering targets, no vendor data.

    Positions are normalised linkage travel: 0.0 fully open, 1.0 hard against
    the closed stop.  Three thresholds matter and they are deliberately in
    this order:

    ``engage_position`` < ``centre_position`` < ``switch_trip_position``

    * below ``engage_position`` the bail is not under the bar — nothing is
      retained;
    * between engage and centre the bail *is* under the bar but the linkage
      has **not** passed dead centre, so the toggle spring would drive it
      back open if the drive lost authority.  This band is the mechanical
      form of fault-tree branch G1-2a ("keeper never reached stable closed
      geometry") and the model must be able to sit in it;
    * ``switch_trip_position`` is after centre, so the status switch cannot
      indicate closed before the latch is actually bistable.  That ordering
      is a design rule, exactly like p0a-fabrication.md's "S2 senses the
      mechanism, not the horn"; setting it earlier reproduces FM-SN-08 and
      the model will then emit ``FALSE_CAPTURE_CONFIRMED``, which is the
      point of keeping truth and indication apart.
    """

    #: Open-to-closed travel time with no spring effects.  Engineering
    #: estimate of the same order as the baseline's 0.35 s servo, chosen so
    #: the comparison is not decided by actuator speed.
    travel_time_s: float = 0.30
    centre_position: float = 0.90
    #: Half-width of the band around dead centre where the toggle spring
    #: opposes motion in both directions.
    band_half_width: float = 0.06
    #: Rate multiplier while crossing that band: going over centre takes
    #: force, so it takes time.
    over_centre_rate_scale: float = 0.30
    #: Rate multiplier when the spring is helping (past centre toward a
    #: stable end).  This is the audible snap of a real toggle latch.
    spring_assist_rate_scale: float = 2.5

    engage_position: float = 0.75
    switch_trip_position: float = 0.95
    open_clear_position: float = 0.05

    #: How much harder it is to back the latch over centre while it carries a
    #: retained aircraft: the hanging load preloads the toggle spring.
    #: Engineering estimate.
    reverse_load_factor: float = 1.35
    #: Drive force available to reverse the toggle, as a multiple of the
    #: unloaded peak toggle force.  ENGINEERING TARGET standing in for a
    #: force-gauge measurement.  Release under load succeeds if and only if
    #: this is at least ``reverse_load_factor`` — the Rev-A defect (a keeper
    #: that could not release a captured aircraft) is exactly this
    #: inequality failing, so the model is built to be able to fail it.
    release_force_margin: float = 1.8

    def __post_init__(self) -> None:
        if self.travel_time_s <= 0:
            raise ValueError("travel time must be positive")
        if not 0.0 < self.centre_position < 1.0:
            raise ValueError("dead centre must lie inside the travel")
        if self.band_half_width <= 0:
            raise ValueError("the over-centre band must have width")
        if not self.engage_position < self.centre_position < self.switch_trip_position:
            raise ValueError(
                "engage < centre < switch trip: the status switch must not "
                "indicate closed before the latch is bistable"
            )
        if min(self.over_centre_rate_scale, self.spring_assist_rate_scale) <= 0:
            raise ValueError("rate scales must be positive")
        if self.reverse_load_factor < 1.0 or self.release_force_margin <= 0:
            raise ValueError("force ratios must be physical")


class OverCentreLatch:
    """Bistable toggle linkage with an injectable jam and a power flag.

    Two things distinguish it from ``sensors.KeeperServo``:

    1. **Bistability.** With no drive authority the toggle spring carries the
       linkage to whichever stable end it has already passed.  Past centre
       that means *closed*, which is the property the whole candidate exists
       for; short of centre it means *open*, which is the failure mode the
       property costs.  A servo simply stops where it is.
    2. **A force budget on the way back.** Reversing over centre under load
       can stall.  The baseline's servo has no such notion, so its model can
       never reproduce Rev-A's release defect; this one can.
    """

    def __init__(self, params: OverCentreLatchParams | None = None) -> None:
        self.params = params if params is not None else OverCentreLatchParams()
        self._rate_per_s = 1.0 / self.params.travel_time_s
        #: 0.0 fully open, 1.0 hard against the closed stop.
        self.position = 0.0
        #: Mechanical jam: the linkage cannot move at all.  Named to match
        #: the baseline servo so the shared fault injector reaches it.
        self.jammed = False
        #: False models a dead actuator — lost supply, unmated connector,
        #: flat battery.  The twin's shared fault menu has no such fault, so
        #: this is driven directly by this module's tests; see SPEC's
        #: known_weaknesses.
        self.powered = True
        #: True on any step where a commanded release could not cross dead
        #: centre against the retained load.
        self.release_stalled = False

    # -- truth ------------------------------------------------------------

    @property
    def over_centre(self) -> bool:
        """Past dead centre: the latch now holds itself with no power."""

        return self.position > self.params.centre_position

    @property
    def engaged(self) -> bool:
        """Retention truth: the bail is across the trough under the bar."""

        return self.position >= self.params.engage_position

    @property
    def physically_closed(self) -> bool:
        """What a switch on the over-centre stop can actually sense."""

        return self.position >= self.params.switch_trip_position

    @property
    def physically_open(self) -> bool:
        return self.position <= self.params.open_clear_position

    # -- motion -----------------------------------------------------------

    def step(self, dt_s: float, close_commanded: bool, loaded: bool = False) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        p = self.params
        self.release_stalled = False
        if self.jammed:
            return

        if not self.powered:
            # No drive authority: the toggle spring decides, and it always
            # decides for the nearer stable end.
            target = 1.0 if self.over_centre else 0.0
            self._advance(target, self._rate_per_s * p.spring_assist_rate_scale, dt_s)
            return

        target = 1.0 if close_commanded else 0.0
        if self.position == target:
            return
        closing = target > self.position
        in_band = abs(self.position - p.centre_position) <= p.band_half_width

        if in_band:
            rate = self._rate_per_s * p.over_centre_rate_scale
            if not closing and loaded:
                if p.release_force_margin < p.reverse_load_factor:
                    # The drive cannot pull the toggle back over centre with
                    # an aircraft hanging on it.  Nothing moves, the latch
                    # stays engaged, and the aircraft stays stuck — reported,
                    # never silently released.
                    self.release_stalled = True
                    return
                rate /= p.reverse_load_factor
        elif (closing and self.over_centre) or (
            not closing and self.position < p.centre_position
        ):
            rate = self._rate_per_s * p.spring_assist_rate_scale
        else:
            rate = self._rate_per_s
        self._advance(target, rate, dt_s)

    def _advance(self, target: float, rate_per_s: float, dt_s: float) -> None:
        delta = rate_per_s * dt_s
        if self.position < target:
            self.position = min(target, self.position + delta)
        else:
            self.position = max(target, self.position - delta)


@dataclass(frozen=True)
class VGrooveStepResult(DockStepResult):
    """Baseline result plus this architecture's own truth channels.

    A subclass rather than a parallel type: the engine, the guidance stack,
    and the campaign reducers all consume ``DockStepResult`` and must keep
    working unchanged.  Everything added here is **truth**, visible to tests
    and to nothing that flies — the controller still sees two booleans.
    """

    latch_position: float = 0.0
    latch_over_centre: bool = False
    #: Yaw error remaining between the cross-bar and the groove axis.
    bar_yaw_error_rad: float = 0.0
    #: How high the bar actually is above the trough mouth.
    bar_height_above_mouth_m: float = 0.0
    #: The bail is across the trough over a bar that is in it: the aircraft
    #: physically cannot abort until the latch retracts.
    abort_blocked: bool = False
    #: A commanded release could not cross dead centre against the load.
    release_stalled: bool = False


class VGrooveMechanism:
    """One V-trough dock with an over-centre bail, serving one probe.

    Satisfies ``aiur.sim.mechanism.CaptureMechanism``.  The mechanical model
    is a surrogate of the same fidelity as ``dock_physics.DockAssembly`` so
    the two can be compared without one of them flattering itself:

    * a cross-bar crossing the mouth plane inside the trough opening enters;
    * crossing it in the surrounding structural band is scored as
      propeller/structure contact, the unsafe near-miss class;
    * crossing faster than the bounce threshold does not enter;
    * inside the trough the flanks constrain the bar across the groove hard
      and along the groove weakly, and a yawed bar can only rise until the
      flanks close on its swept span.
    """

    def __init__(
        self,
        geometry: VGrooveGeometry | None = None,
        latch_params: OverCentreLatchParams | None = None,
        *,
        dt_s: float,
        controller: DockController | None = None,
        yaw_error_rad: float | None = None,
    ) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self.geometry = geometry if geometry is not None else VGrooveGeometry()
        self._dt_s = dt_s
        self.controller = controller if controller is not None else DockController()
        self.latch = OverCentreLatch(latch_params)
        self.seat_switch = Switch(dt_s=dt_s)
        self.keeper_switch = Switch(dt_s=dt_s)
        self.probe_phase = ProbePhase.FREE

        self._initial_yaw_rad = (
            self.geometry.nominal_yaw_error_rad
            if yaw_error_rad is None
            else float(yaw_error_rad)
        )
        #: Live yaw error of the bar relative to the groove axis.
        self.bar_yaw_error_rad = self._initial_yaw_rad

        self._was_confirmed = False
        self._prev_rel_z: float | None = None
        self._prev_engaged = False
        self._bail_was_across = False
        self._bar_above_bail = False
        self._abort_blocked = False

    # -- fault-injector compatibility -------------------------------------

    @property
    def servo(self) -> OverCentreLatch:
        """Alias so ``aiur.sim.faults`` reaches this architecture unchanged.

        The shared injector writes ``dock.servo.jammed`` and reads
        ``dock.servo.physically_closed``.  Renaming the attribute here would
        make this candidate silently untestable under the existing fault
        menu, which would flatter it in exactly the campaign that is supposed
        to expose it.
        """

        return self.latch

    # -- CaptureMechanism interface ---------------------------------------

    def seed_seated(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Place a bar at the seat for scenarios that start captured.

        Yaw is zeroed because a bar physically lying in the V *is* aligned
        with it — there is no seated state at large yaw to seed.
        """

        self.probe_phase = ProbePhase.SEATED
        self.bar_yaw_error_rad = 0.0
        self._prev_rel_z = self.geometry.seat_travel_m
        self._bar_above_bail = True
        self._seat(drone, dock_center, dock_velocity)

    def reset_controller(self) -> None:
        """Model a controller brownout: the logic restarts, the latch does not.

        The interesting asymmetry versus the baseline lives here.  Both
        mechanisms keep their physical state across a reset; the difference
        is what the restarted controller can *do* about it.  A restarted
        controller that commands OPEN drives a servo open, but it can only
        drive this latch open if the actuator still has authority — see
        ``OverCentreLatch.powered``.
        """

        self.controller = type(self.controller)(
            lock_timeout_s=self.controller.lock_timeout_s,
            release_timeout_s=self.controller.release_timeout_s,
        )
        self._was_confirmed = False

    # -- mechanical truth -------------------------------------------------

    def _bar_center(self, drone: DroneBody) -> Vec3:
        return drone.position + Vec3(0.0, 0.0, self.geometry.probe_height_m)

    def _place(self, drone: DroneBody, dock_center: Vec3, rel: Vec3) -> None:
        drone.position = (
            dock_center + rel - Vec3(0.0, 0.0, self.geometry.probe_height_m)
        )

    def _seat(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Pin a seated bar to the apex of the V."""

        self._place(drone, dock_center, Vec3(0.0, 0.0, self.geometry.seat_travel_m))
        drone.velocity = dock_velocity

    def _hold_at_seat(
        self,
        drone: DroneBody,
        dock_center: Vec3,
        dock_velocity: Vec3,
        floor_z: float | None,
    ) -> None:
        """Seat contact for an armed aircraft against an open bail.

        The V centres the bar and the apex is a hard stop upward, but
        downward motion stays free unless the bail is already across — which
        is precisely the abort-transparency cost this architecture pays.
        """

        g = self.geometry
        rel = self._bar_center(drone) - dock_center
        z = min(rel.z, g.seat_travel_m)
        vertical = drone.velocity.z
        if vertical - dock_velocity.z > 0.0:
            vertical = dock_velocity.z
        if floor_z is not None and z <= floor_z:
            z = floor_z
            if vertical - dock_velocity.z < 0.0:
                vertical = dock_velocity.z
        self._place(drone, dock_center, Vec3(0.0, 0.0, z))
        drone.velocity = dock_velocity.lateral().with_z(vertical)

    def _constrain_to_trough(
        self,
        drone: DroneBody,
        dock_center: Vec3,
        dock_velocity: Vec3,
        height_m: float,
    ) -> None:
        """Apply the anisotropic flank constraint to a bar inside the trough."""

        g = self.geometry
        rel = self._bar_center(drone) - dock_center
        allow_x = g.half_length_at(height_m)
        allow_y = g.half_width_at(height_m)
        x = max(-allow_x, min(allow_x, rel.x))
        y = max(-allow_y, min(allow_y, rel.y))
        if x != rel.x or y != rel.y:
            self._place(drone, dock_center, Vec3(x, y, rel.z))
            # The flank absorbs lateral relative velocity.
            drone.velocity = dock_velocity.lateral().with_z(drone.velocity.z)

    def _derotate(self, dt_s: float) -> None:
        """Let the converging flanks pull a yawed bar toward the groove axis.

        Only while the bar bears on the flanks, and only below the wedge
        limit: past that angle the contact self-locks and the bar is stuck
        wherever it stopped, which is the modelled failure this architecture
        is supposed to own.
        """

        g = self.geometry
        yaw = self.bar_yaw_error_rad
        if yaw == 0.0 or abs(yaw) > g.yaw_wedge_limit_rad:
            return
        reduced = max(0.0, abs(yaw) - g.yaw_align_rate_rad_s * dt_s)
        self.bar_yaw_error_rad = math.copysign(reduced, yaw) if reduced else 0.0

    # -- step -------------------------------------------------------------

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        drone: DroneBody | None,
        commands: DockCommands,
    ) -> VGrooveStepResult:
        """Advance mechanics, switches, the real controller, and the latch."""

        g = self.geometry
        events: list[Event] = []
        contact_speed: float | None = None
        seat_truth = False
        self._abort_blocked = False
        height_m = 0.0

        if drone is None:
            self.probe_phase = ProbePhase.FREE
            self._prev_rel_z = None
            self._bail_was_across = False
            self._bar_above_bail = False
            self.bar_yaw_error_rad = self._initial_yaw_rad
        else:
            rel = self._bar_center(drone) - dock_center
            closing = (drone.velocity - dock_velocity).z

            # Snapshot what the bail found when it entered the trough: a bar
            # already above the sweep plane gets trapped, a bar below it gets
            # locked out.  Edge-triggered for the same reason the baseline
            # snapshots its keeper — mid-travel geometry decides the outcome.
            bail_across = self.latch.position >= g.bail_in_throat_position
            if bail_across and not self._bail_was_across:
                self._bar_above_bail = rel.z >= g.bail_plane_z_m
            elif not bail_across:
                self._bar_above_bail = False
            self._bail_was_across = bail_across

            if self.probe_phase is ProbePhase.FREE:
                crossed_up = (
                    self._prev_rel_z is not None
                    and self._prev_rel_z < g.mouth_z_m
                    and rel.z >= g.mouth_z_m
                )
                if crossed_up:
                    inside = _elliptical(
                        rel.x,
                        rel.y,
                        g.trough_mouth_half_length_m,
                        g.trough_mouth_half_width_m,
                    )
                    in_structure = _elliptical(
                        rel.x,
                        rel.y,
                        g.trough_mouth_half_length_m + g.rim_annulus_m,
                        g.trough_mouth_half_width_m + g.rim_annulus_m,
                    )
                    if inside:
                        contact_speed = closing
                        if closing > g.bounce_speed_m_s:
                            events.append(
                                Event(
                                    EventKind.OVERSPEED_CONTACT,
                                    now_s,
                                    detail=f"closing={closing:.3f}",
                                )
                            )
                            # Restitution in the dock frame, not the world frame.
                            drone.velocity = drone.velocity.with_z(
                                dock_velocity.z - 0.5 * closing
                            )
                        else:
                            self.probe_phase = ProbePhase.INSERTED
                            events.append(
                                Event(
                                    EventKind.FUNNEL_INSERTION,
                                    now_s,
                                    detail=(
                                        f"closing={closing:.3f} "
                                        f"yaw={self.bar_yaw_error_rad:.3f}"
                                    ),
                                )
                            )
                    elif in_structure:
                        events.append(
                            Event(
                                EventKind.PROP_FUNNEL_CONTACT,
                                now_s,
                                detail=(
                                    f"across={abs(rel.y):.3f} along={abs(rel.x):.3f}"
                                ),
                            )
                        )
                        drone.velocity = drone.velocity.with_z(
                            dock_velocity.z - max(0.05, 0.5 * closing)
                        )

            elif self.probe_phase is ProbePhase.INSERTED:
                if rel.z < g.mouth_z_m:
                    self.probe_phase = ProbePhase.FREE
                    self._bar_above_bail = False
                    self.bar_yaw_error_rad = self._initial_yaw_rad
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="clear_of_trough")
                    )
                else:
                    height_m = rel.z - g.mouth_z_m
                    self._constrain_to_trough(drone, dock_center, dock_velocity, height_m)

                    # Two independent ceilings, plus a floor when the bail has
                    # already closed over the bar.
                    yaw_ceiling = g.mouth_z_m + g.max_height_for_yaw(
                        self.bar_yaw_error_rad
                    )
                    ceiling = min(g.seat_travel_m, yaw_ceiling)
                    if bail_across and not self._bar_above_bail:
                        ceiling = min(ceiling, g.bail_plane_z_m)
                    floor = g.bail_plane_z_m if (bail_across and self._bar_above_bail) else None

                    rel = self._bar_center(drone) - dock_center
                    z = rel.z
                    vertical = drone.velocity.z
                    if z > ceiling:
                        z = ceiling
                        if vertical - dock_velocity.z > 0.0:
                            vertical = dock_velocity.z
                    if floor is not None and z < floor:
                        z = floor
                        if vertical - dock_velocity.z < 0.0:
                            vertical = dock_velocity.z
                    if z != rel.z or vertical != drone.velocity.z:
                        self._place(drone, dock_center, Vec3(rel.x, rel.y, z))
                        drone.velocity = drone.velocity.with_z(vertical)
                    self._abort_blocked = floor is not None
                    height_m = z - g.mouth_z_m

                    # Bearing on the converging flanks is what derotates the
                    # bar; a bar floating in the middle of the mouth is not
                    # touching anything.
                    if z >= yaw_ceiling - 1e-4 and yaw_ceiling < g.seat_travel_m:
                        self._derotate(self._dt_s)

                    if z >= g.seat_travel_m - 1e-9:
                        self.probe_phase = ProbePhase.SEATED
                        self._seat(drone, dock_center, dock_velocity)
                        events.append(
                            Event(
                                EventKind.PROBE_SEATED,
                                now_s,
                                detail=f"yaw={self.bar_yaw_error_rad:.4f}",
                            )
                        )

            elif self.probe_phase is ProbePhase.SEATED:
                trapped = bail_across and self._bar_above_bail
                self._abort_blocked = trapped and not self.latch.engaged
                pulling_out = (
                    drone.armed
                    and (drone.velocity - dock_velocity).z < -g.unseat_speed_m_s
                )
                slid_out = drone.armed and rel.z < g.bail_plane_z_m
                if (pulling_out or slid_out) and not self.latch.engaged and not trapped:
                    self.probe_phase = ProbePhase.INSERTED
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="unseated")
                    )
                elif not drone.armed or self.latch.engaged:
                    self._seat(drone, dock_center, dock_velocity)
                else:
                    self._hold_at_seat(
                        drone,
                        dock_center,
                        dock_velocity,
                        g.bail_plane_z_m if trapped else None,
                    )
                height_m = (self._bar_center(drone) - dock_center).z - g.mouth_z_m

            rel = self._bar_center(drone) - dock_center
            seat_truth = (
                self.probe_phase is ProbePhase.SEATED
                and rel.z >= g.seat_travel_m - g.seat_hysteresis_m
            )
            self._prev_rel_z = rel.z

        # -- truth versus indication -------------------------------------
        # Truth is "the bail is across the trough under the bar"; indication
        # is "a switch on the over-centre stop says so".  They are separate
        # objects on purpose, and the design intends the switch to trip late.
        keeper_truth = self.latch.engaged
        reported_s1 = self.seat_switch.step(seat_truth)
        reported_s2 = self.keeper_switch.step(self.latch.physically_closed)

        output = self.controller.step(
            now_s,
            DockInputs(
                seat_switch=reported_s1,
                keeper_closed_switch=reported_s2,
                capture_enable=commands.capture_enable,
                release_request=commands.release_request,
                emergency_release=commands.emergency_release,
                reset_fault=commands.reset_fault,
            ),
        )
        close_commanded = output.keeper_command is KeeperCommand.CLOSE
        loaded = (
            drone is not None
            and not drone.armed
            and self.probe_phase is ProbePhase.SEATED
            and self.latch.engaged
        )
        self.latch.step(self._dt_s, close_commanded, loaded)

        if output.capture_confirmed and not self._was_confirmed:
            if seat_truth and keeper_truth:
                events.append(Event(EventKind.CAPTURE_CONFIRMED, now_s))
            else:
                events.append(
                    Event(
                        EventKind.FALSE_CAPTURE_CONFIRMED,
                        now_s,
                        detail="controller confirmed without mechanical capture",
                    )
                )
        if self._was_confirmed and not output.capture_confirmed:
            events.append(Event(EventKind.RELEASED, now_s))
        self._was_confirmed = output.capture_confirmed

        # A disarmed aircraft relies entirely on the mechanism.  Edge
        # triggered on retention truth, not on the switch, and only for an
        # aircraft actually in the trough.
        if (
            drone is not None
            and not drone.armed
            and self.probe_phase is ProbePhase.SEATED
            and self._prev_engaged
            and not keeper_truth
            and not commands.release_request
            and not commands.emergency_release
        ):
            events.append(Event(EventKind.DROPPED_AIRCRAFT, now_s))
        self._prev_engaged = keeper_truth

        return VGrooveStepResult(
            probe_phase=self.probe_phase,
            seat_truth=seat_truth,
            keeper_closed_truth=keeper_truth,
            reported_s1=reported_s1,
            reported_s2=reported_s2,
            controller=output,
            contact_closing_speed_m_s=contact_speed,
            events=tuple(events),
            latch_position=self.latch.position,
            latch_over_centre=self.latch.over_centre,
            bar_yaw_error_rad=self.bar_yaw_error_rad,
            bar_height_above_mouth_m=height_m,
            abort_blocked=self._abort_blocked,
            release_stalled=self.latch.release_stalled,
        )


def _elliptical(x: float, y: float, semi_x: float, semi_y: float) -> bool:
    """True when (x, y) lies inside the axis-aligned ellipse.

    The trough opening is a slot, so acceptance is genuinely elliptical
    rather than circular; using a radius here would erase the one geometric
    fact that separates this candidate from the baseline funnel.
    """

    return (x / semi_x) ** 2 + (y / semi_y) ** 2 <= 1.0


#: Honest statement of what this architecture is bad at.  Written before the
#: smoke test, kept afterwards, and each entry is exercised by a test in
#: tests/test_mech_vgroove.py — a weakness nobody can reproduce is marketing.
KNOWN_WEAKNESSES: tuple[str, ...] = (
    "Yaw-sensitive. A V constrains two translations and leaves rotation "
    "about the vertical nearly free, so the cross-bar must arrive within "
    "~4 deg of the groove axis to seat, and wedges permanently past ~20 deg. "
    "The baseline funnel has no heading requirement at all.",
    "The yaw model is invented. The twin has no yaw state, so arrival yaw is "
    "a scenario parameter with a stated 5 deg default and the flank pull-in "
    "rate (0.06 rad/s) is an engineering guess. Both need a bench "
    "measurement before any capture-rate number here is quotable.",
    "Two sensed channels, neither of which senses a bar. S1 reports the seat, "
    "S2 reports the over-centre stop; a bail closing on an empty trough still "
    "reads closed, so the empty-throat cut set (dock-fmeca TOP-2 / G2-1) is "
    "inherited from the baseline unchanged.",
    "Bistability only starts at dead centre. Between engagement and centre "
    "the bail is under the bar but the toggle spring would drive it open, so "
    "a power loss in that ~0.05 s window drops the aircraft. That is fault-"
    "tree branch G1-2a, moved rather than removed.",
    "Abort opacity is worse than the baseline's. From the moment the bail "
    "enters the trough the aircraft is mechanically trapped and can only "
    "leave by commanded release, which is the force asymmetry "
    "docs/dock-deletion-review.md warns about, in its sharpest form.",
    "Smaller mouth, and it costs unsafe events under wind. The trough "
    "opening is 110 x 150 mm against the funnel's 180 mm circle, so arrivals "
    "the funnel swallows become propeller/structure contacts. Measured on "
    "this model: sil-p0b at 1.0 m/s mean wind gives 6 PROP_FUNNEL_CONTACT "
    "episodes in 40 (seeds 8, 19, 26, 28, 34, 37) against zero for the "
    "baseline over the same seeds; indoor calm is clean for both. On the "
    "current model this candidate is not safe outside still air, and that is "
    "the strongest single argument against printing it.",
    "Acceptance depends on which way the dock is pointed. The mouth is an "
    "ellipse, not a circle, so the tolerated approach error differs by 1.4x "
    "between along-groove and across-groove. Rotating the mean wind from "
    "along the groove to across it moves the 0.5 m/s wind case from zero "
    "unsafe episodes to one in 40. The baseline funnel has no orientation.",
    "The dead-battery advantage is unmeasurable in the shared campaign. "
    "aiur/sim/faults.py has no actuator-power-loss fault, only a jam, so the "
    "one property this architecture is built around is exercised by this "
    "module's own tests and by nothing in the SIL gates.",
    "No axial retention before the latch. A V seat is gravity registration "
    "with zero pull-out resistance, so an unlatched bar leaves on any "
    "downward relative motion.",
    "S2 releases 20% of travel before the bail does. The switch senses the "
    "over-centre stop, so it reports open as soon as the linkage leaves that "
    "stop while the bail is still across the bar. A release that stalls at "
    "the toggle therefore reads to the controller as a completed release on "
    "an aircraft that is still held, and the controller does not even fault "
    "because its release timeout needs the switch to stay made. This is "
    "dock-fmeca FM-KP-04's undetected band, in the release direction; the "
    "A0 measurement that action A6 asks for sizes it.",
)


@dataclass(frozen=True)
class VGrooveSpec:
    """Design-study entry for the V-trough / over-centre-latch candidate."""

    key: str = "vgroove"
    name: str = "V-trough with over-centre latch"
    summary: str = (
        "A probe cross-bar drops into a shallow V-trough that centres it by "
        "geometry; an over-centre bail snaps past dead centre beneath it and "
        "holds with no power. Cheap in depth and mass, expensive in heading "
        "accuracy."
    )
    #: Trough body, bail, toggle spring, drive crank, pivot pin set,
    #: actuator, actuator bracket, two switches, one switch bracket.
    part_count: int = 10
    #: Still one powered actuator.  The bistability removes the need for
    #: *holding* power, not for the actuator — and MechanismSpec's own
    #: comment ties "retention survives a dead battery" to a zero here, so
    #: this row understates the candidate.  Said plainly rather than gamed.
    actuator_count: int = 1
    sensed_channels: int = 2
    #: Engineering target: a 35 mm trough in place of the CAD manifest's
    #: 52.58 g funnel, plus bail, spring, crank, pins, the 18 g actuator
    #: already carried in the repo's dock BOM, its bracket, and two switches.
    #: No part has been weighed, here or in the baseline.
    est_dock_mass_g: float = 58.0
    #: Engineering target for a 45 mm cross-bar and mast, inside the
    #: <=8 g aircraft-side probe budget in docs/dock-deletion-review.md.
    est_probe_mass_g: float = 4.5
    known_weaknesses: tuple[str, ...] = KNOWN_WEAKNESSES

    geometry: VGrooveGeometry = field(default_factory=VGrooveGeometry)
    latch_params: OverCentreLatchParams = field(default_factory=OverCentreLatchParams)
    #: None means "use the geometry's stated default arrival yaw".
    yaw_error_rad: float | None = None

    def build(self, dt_s: float) -> VGrooveMechanism:
        """Return a ready mechanism for one episode."""

        return VGrooveMechanism(
            self.geometry,
            self.latch_params,
            dt_s=dt_s,
            yaw_error_rad=self.yaw_error_rad,
        )


SPEC = VGrooveSpec()


def vgroove_factory(
    *,
    yaw_error_rad: float | None = None,
    geometry: VGrooveGeometry | None = None,
    latch_params: OverCentreLatchParams | None = None,
):
    """Build an ``EpisodeConfig.mechanism_factory`` for this architecture.

    Exists because arrival yaw is the parameter this candidate lives and dies
    by, and the engine's factory signature ``(config, dt_s)`` has nowhere to
    put it.  Sweeping yaw is the honest way to report the architecture, so
    the sweep has to be easy.
    """

    def build(config, dt_s: float) -> VGrooveMechanism:
        return VGrooveMechanism(
            geometry,
            latch_params,
            dt_s=dt_s,
            yaw_error_rad=yaw_error_rad,
        )

    return build
