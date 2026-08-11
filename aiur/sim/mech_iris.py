"""Three-jaw iris capture candidate for the CARRIER-P0 recovery dock.

The Rev-A baseline (``aiur/sim/dock_physics.py``) retains the probe with a
sliding fork whose slot is caught between two coupled requirements: wide
enough to clear a Ø3 mm mast that the Ø16 mm throat lets wander ±2.0 mm, and
narrow enough that a Ø12 mm head cannot pull through.  ``docs/dock-deletion-
review.md`` quantifies the gap — the throat permits a probe position the fork
cannot close on, by a factor of 3.3 — and the whole spring-collet argument
exists to close it.

This module asks whether the coupling can simply be removed.  Three jaws
closing radially and symmetrically have a closed diameter that is set by the
jaws' own stop, not by the acceptance opening: the jaws *center* the mast as
they close instead of requiring it to arrive pre-registered.  If that works,
the registration requirement disappears, the collet has nothing left to do,
and the fork's slot-width trade goes with it.  Symmetric closure also removes
the one-sided side load a fork puts on the mast (FM-PR-01).

What it costs is three linkages off one actuator: more parts, more mass, and
a jam mode the fork does not have — one jaw that does not reach its stop.
That mode is modeled explicitly, and the mechanism must not claim capture on
partial closure.

Sensing architecture, stated once, plainly, because the safety case rests on
it:

* **S1** — seat switch, unchanged from the baseline.  One physical fact: a
  probe reached the seat.
* **S2** — three per-jaw *band* switches wired in series into one channel.
  Each senses jaw position on the jaw itself (never on the linkage or the
  servo horn — FM-SN-09) and is made only while that jaw sits inside a
  narrow reach band.  An empty jaw set overruns the band to its own stop; a
  jaw resting on the Ø12 mm head has not reached it; only a jaw stopped on
  the Ø3 mm mast sits inside it.  This is the "keeper travel-stop difference
  between empty and mast-present" S2′ candidate from the deletion review,
  which radial closure makes natural rather than contrived.

That is **two** independent sensed channels feeding the capture Boolean, the
same as Rev-A.  Three switches on one channel are not three channels; see
:data:`SPEC` for what is and is not claimed.

Physics status: engineering-estimate surrogate, in the same spirit and to the
same standard as ``dock_physics.py``.  Funnel acceptance, insertion, rim
contact and overspeed are deliberately identical to the baseline so the two
candidates differ only where the architectures differ.  Jaw kinematics,
mast centering, and the retention criterion are first-principles geometry on
Rev-A's documented dimensions (Ø16 throat, Ø12 head, Ø3 mast); no vendor
figure is invented, and nothing here has been measured.

What the twin says so far, so nobody has to re-derive it.  Seven cells, 360
episodes, seeds 1..n, this mechanism swapped in via ``mechanism_factory``
against the same scenarios run with the Rev-A baseline:

===================  =========================================  ========
Cell                 Outcomes (identical for both mechanisms)   Captures
===================  =========================================  ========
sil-p0b nominal      80 success                                 80
sil-p0b fault        42 safe-incomplete, 35 success, 3 timeout  35
sil-p0b correlated   46 safe-incomplete, 12 success, 2 timeout  12
sil-p0c nominal      40 success                                 40
sil-p0c fault        23 safe-incomplete, 17 success             17
sil-p0d nominal      30 success                                 30
sil-p0d fault        17 safe-incomplete, 13 success             13
===================  =========================================  ========

Zero unsafe events and zero false capture confirmations in every cell, for
both mechanisms.  The iris reproduces the baseline's counts cell for cell.

The honest reading is that at Lighthouse-grade indoor navigation, capture
rate does not discriminate between these two architectures at all — which is
consistent with the deletion review's finding that the funnel, not the
keeper, is doing the work in this regime.  What discriminates them is the
empty-throat claim, the registration requirement, the part count, and the
new timing coupling this candidate introduces; none of those is visible in a
capture-rate number, and a trade study that ranked on capture rate alone
would call this a tie.  Model results, not vehicle performance; the twin
remains uncalibrated.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

from ..dock_controller import DockController, DockInputs, KeeperCommand
from .bodies import DroneBody
from .dock_physics import DockCommands, DockGeometry, DockStepResult, ProbePhase
from .events import Event, EventKind
from .sensors import KeeperServo, Switch
from .vec import Vec3

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from .engine import EpisodeConfig


#: Three jaws is not a parameter.  The mast-centering solution below uses the
#: fact that three unit vectors at 120° sum to zero and satisfy
#: ``sum(o_i o_i^T) = 1.5 I``; a different count needs a different solver, so
#: the constant is named rather than silently assumed.
JAW_COUNT = 3


def _jaw_directions() -> tuple[Vec3, ...]:
    """Outward radial unit vectors of the jaw tips, evenly spaced."""

    return tuple(
        Vec3(math.cos(2.0 * math.pi * i / JAW_COUNT), math.sin(2.0 * math.pi * i / JAW_COUNT), 0.0)
        for i in range(JAW_COUNT)
    )


_DIRECTIONS = _jaw_directions()


@dataclass(frozen=True)
class IrisGeometry:
    """Iris-candidate geometry.  Every value is an engineering target.

    Funnel numbers are copied from :class:`~aiur.sim.dock_physics.DockGeometry`
    on purpose: the study compares retention architectures, and a candidate
    that quietly enlarged its own funnel would be comparing funnels.
    """

    # -- shared with the baseline, deliberately -------------------------
    funnel_entrance_radius_m: float = 0.090
    rim_annulus_m: float = 0.060
    seat_travel_m: float = 0.100
    seat_hysteresis_m: float = 0.004
    probe_height_m: float = 0.050
    bounce_speed_m_s: float = 0.30
    #: Relative descent that pulls an armed probe off an unretained seat.
    #: The iris has no passive first-capture element (the deletion review
    #: deletes the collet), so this is seat friction only.
    unseat_speed_m_s: float = 0.05

    # -- probe, from the Rev-A drawing ----------------------------------
    #: Ø3 mm mast.
    mast_radius_m: float = 0.0015
    #: Ø12 mm head.
    head_radius_m: float = 0.0060
    #: Axial height of the head.  Sets the window in which a jaw closing
    #: early lands on the head instead of the mast.
    head_height_m: float = 0.0060

    # -- jaw set --------------------------------------------------------
    #: Jaw plane below the seat: the jaws grip directly under the head's
    #: seat shoulder, which is the whole point of the architecture.
    jaw_below_seat_m: float = 0.012
    #: Jaw tip radius with the iris fully open.  Clears the Ø16 mm throat,
    #: so the acceptance opening is the throat's, not the jaws'.
    jaw_open_reach_m: float = 0.0080
    #: Jaw tip radius at the empty full-close stop.  The jaws do not quite
    #: meet; a hard tip-to-tip stop would be a wear surface for no gain.
    jaw_closed_reach_m: float = 0.0005
    #: Bias on the head-passes-the-opening test.  Signed so the model errs
    #: toward "the head can escape", never toward claiming retention.  Sized
    #: so that a single jaw closed with the other two open is scored as NOT
    #: retaining, with margin, rather than landing on the threshold.
    retention_margin_m: float = 0.0008

    # -- S2' band switch, one per jaw -----------------------------------
    #: Outer make point: the jaw has closed inside the Ø12 mm head, so it is
    #: not resting on a head that never reached the seat.
    band_outer_reach_m: float = 0.0026
    #: Inner break point: below this the jaw has overrun past where a Ø3 mm
    #: mast would have stopped it, i.e. the jaw plane is empty.
    band_inner_reach_m: float = 0.0009
    #: Debounce on each jaw's band switch.  This is NOT a noise filter: it
    #: is the discrimination itself.  An empty jaw sweeps *through* the band
    #: on its way to the closed stop, so the switch must be slower than that
    #: transit or an empty close reports as a mast-present close.  See
    #: :meth:`IrisGeometry.empty_band_transit_s`; the margin is thin and is
    #: listed as a weakness rather than presented as a design feature.
    jaw_switch_debounce_s: float = 0.14
    #: Full-stroke time of the single actuator driving all three linkages.
    jaw_travel_time_s: float = 0.35
    #: Truth-side threshold for calling the jaws out of synchronisation,
    #: as a fraction of full stroke.
    jaw_sync_tolerance: float = 0.05

    def __post_init__(self) -> None:
        if self.jaw_closed_reach_m >= self.jaw_open_reach_m:
            raise ValueError("jaws must close inward")
        if not (
            self.jaw_closed_reach_m
            < self.band_inner_reach_m
            < self.mast_radius_m
            < self.band_outer_reach_m
            < self.head_radius_m
        ):
            # If this ordering breaks, the band no longer distinguishes
            # empty / mast / head and S2' is not a discriminator at all.
            raise ValueError("band must bracket the mast and exclude head and empty stops")
        if self.jaw_travel_time_s <= 0 or self.jaw_switch_debounce_s < 0:
            raise ValueError("jaw timing must be positive")

    @property
    def jaw_stroke_m(self) -> float:
        return self.jaw_open_reach_m - self.jaw_closed_reach_m

    @property
    def jaw_tip_speed_m_s(self) -> float:
        return self.jaw_stroke_m / self.jaw_travel_time_s

    @property
    def empty_band_transit_s(self) -> float:
        """How long an *empty* jaw spends inside the band as it closes.

        The band switch must be debounced longer than this or the mechanism
        reports a mast-present closure while the throat is empty.  The ratio
        of :attr:`jaw_switch_debounce_s` to this number is the entire
        empty-throat discrimination margin, and it scales with actuator
        speed: a slow or sagging servo shrinks it toward one.
        """

        return (self.band_outer_reach_m - self.band_inner_reach_m) / self.jaw_tip_speed_m_s

    @property
    def jaw_plane_z_m(self) -> float:
        """Height of the jaw plane above the funnel entrance."""

        return self.seat_travel_m - self.jaw_below_seat_m

    def reach_at(self, closure: float) -> float:
        """Jaw tip radius at a closure fraction (0 fully open, 1 fully closed)."""

        return self.jaw_open_reach_m - closure * self.jaw_stroke_m

    def closure_at(self, reach_m: float) -> float:
        """Closure fraction at which a jaw tip sits at ``reach_m``."""

        return (self.jaw_open_reach_m - reach_m) / self.jaw_stroke_m


@dataclass(frozen=True)
class IrisStepResult(DockStepResult):
    """A :class:`DockStepResult` plus the jaw detail the engine cannot use.

    The engine, guidance, and campaign reducers consume only the base
    fields, so the iris is a drop-in candidate.  The extra fields exist so
    tests and design-study reporting can see *why* a step went the way it
    did without reaching into mechanism internals — and, critically, so
    truth and indication stay side by side and separately falsifiable.
    """

    #: Truth: per-jaw closure fraction, 0 open, 1 at the empty closed stop.
    jaw_closures: tuple[float, ...] = ()
    #: Truth: per-jaw tip radius.
    jaw_reaches_m: tuple[float, ...] = ()
    #: Indication: per-jaw band switch, debounced, faultable.
    jaw_reported: tuple[bool, ...] = ()
    #: Truth: largest circle that still fits through the jaw opening.
    jaw_opening_m: float = 0.0
    #: Truth: the head is entirely above the jaw plane.
    head_above_jaws: bool = False
    #: Truth: jaws are within tolerance of each other.
    jaws_synchronized: bool = True
    #: Indication: a lag *visible from the switches alone* — some jaw in
    #: band, some not.  Deliberately not derived from truth; see
    #: :data:`SPEC` for the cases it does not cover.
    jaw_lag_reported: bool = False
    #: Truth: probe axis offset from the dock axis at the jaw plane.
    mast_offset_m: float = 0.0


class IrisMechanism:
    """Funnel acceptance with three-jaw radial retention.

    Satisfies :class:`~aiur.sim.mechanism.CaptureMechanism`.  Runs the real
    :class:`~aiur.dock_controller.DockController` un-mocked, exactly as the
    baseline does, because a candidate evaluated against a mock controller
    would be evaluated against software that will never fly.
    """

    def __init__(
        self,
        geometry: IrisGeometry | None = None,
        *,
        dt_s: float,
        controller: DockController | None = None,
    ) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self.geometry = geometry if geometry is not None else IrisGeometry()
        self._dt_s = dt_s
        self.controller = controller if controller is not None else DockController()

        # One actuator, three linkages.  The servo is the drive ring; the
        # jaws are its output and are tracked separately, because the whole
        # question this candidate raises is what happens when they differ.
        self.servo = KeeperServo(travel_time_s=self.geometry.jaw_travel_time_s)
        self.seat_switch = Switch(dt_s=dt_s)
        self.jaw_switches = [
            Switch(debounce_s=self.geometry.jaw_switch_debounce_s, dt_s=dt_s)
            for _ in range(JAW_COUNT)
        ]
        #: The series S2 decode line.  Named to match the baseline so the
        #: shared fault injector can reach it; a fault here is a common-mode
        #: fault on the whole channel, which is the honest model of a shared
        #: harness, pull-up rail, or decode defect.
        self.keeper_switch = Switch(dt_s=dt_s)

        #: Truth state of the jaw train.
        self.jaw_closure = [0.0] * JAW_COUNT
        #: Injectable defect: the furthest a linkage will close.  This is the
        #: lagging-jaw mode the architecture adds over a single fork.
        self.jaw_close_limit = [1.0] * JAW_COUNT
        #: Injectable defect: the furthest a linkage will retract.  This is
        #: the iris analogue of the Rev-A keeper that could not release.
        self.jaw_open_limit = [0.0] * JAW_COUNT

        self.probe_phase = ProbePhase.FREE
        self._was_confirmed = False
        self._prev_rel_z: float | None = None
        self._prev_grip_truth = False

    # -- interface ---------------------------------------------------------

    def seed_seated(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Place a probe at the seat for scenarios that start captured.

        The jaws are left open on purpose: the engine's pre-roll then walks
        the real controller through a genuine seat → lock → confirm sequence
        instead of being handed a capture it never made.
        """

        g = self.geometry
        self.probe_phase = ProbePhase.SEATED
        self._prev_rel_z = g.seat_travel_m
        # Seeded probes arrive nominally centered; the interesting question
        # is what closure does to an off-center probe, and that is set up by
        # a scenario, not smuggled in by the seeder.
        tip = dock_center + Vec3(0.0, 0.0, g.seat_travel_m)
        drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
        drone.velocity = dock_velocity

    def reset_controller(self) -> None:
        """Model a controller brownout: the logic restarts, the iris does not.

        Jaw positions, servo travel, and switch state all survive, because a
        power blip does not move hardware.  For this architecture that is a
        sharper test than for the baseline: the restarted controller must
        decide what it is holding from S1 and a series S2 that means
        "mast between all three jaws", which is a stronger fact than Rev-A's
        "the fork reached its stop" — but it is still only two channels.
        """

        self.controller = type(self.controller)(
            lock_timeout_s=self.controller.lock_timeout_s,
            release_timeout_s=self.controller.release_timeout_s,
        )
        self._was_confirmed = False

    # -- mechanical truth --------------------------------------------------

    def _probe_tip(self, drone: DroneBody) -> Vec3:
        return drone.position + Vec3(0.0, 0.0, self.geometry.probe_height_m)

    def _funnel_allowed_radius(self, depth_m: float) -> float:
        """Taper: allowed lateral offset shrinks from entrance to throat.

        Identical to the baseline, including the 2.0 mm floor, which is the
        Ø16 mm throat's own radial clearance — the number the deletion
        review says the Rev-A fork cannot absorb and this candidate must.
        """

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
            tip = dock_center + Vec3(rel.x * scale, rel.y * scale, rel.z)
            drone.position = tip - Vec3(0.0, 0.0, self.geometry.probe_height_m)
            drone.velocity = dock_velocity.lateral().with_z(drone.velocity.z)

    def _seat(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Pin a seated probe axially, WITHOUT centering it laterally.

        The baseline pins a seated probe to the dock axis, which is fair for
        an architecture that has a spring collet to do the centering.  The
        iris has none — the deletion review deletes it — so lateral position
        is owned by the funnel throat and by jaw closure.  Re-centering here
        would hand this candidate its headline claim for free.
        """

        g = self.geometry
        rel = self._probe_tip(drone) - dock_center
        tip = dock_center + Vec3(rel.x, rel.y, g.seat_travel_m)
        drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
        drone.velocity = dock_velocity
        self._constrain_to_funnel(drone, dock_center, dock_velocity)

    def _hold_at_seat(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Seat contact for an armed aircraft against an open iris.

        The seat is a hard stop upward; downward relative motion stays free,
        or a commanded departure could never build pull-out velocity.
        Lateral position is preserved for the same reason as in
        :meth:`_seat`: with no collet, nothing here centers the probe.
        """

        g = self.geometry
        rel = self._probe_tip(drone) - dock_center
        clamped_z = min(rel.z, g.seat_travel_m)
        tip = dock_center + Vec3(rel.x, rel.y, clamped_z)
        drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
        vertical = drone.velocity.z
        if vertical - dock_velocity.z > 0.0:
            vertical = dock_velocity.z
        drone.velocity = dock_velocity.lateral().with_z(vertical)
        self._constrain_to_funnel(drone, dock_center, dock_velocity)

    # -- jaw geometry ------------------------------------------------------

    @property
    def jaw_reaches_m(self) -> tuple[float, ...]:
        return tuple(self.geometry.reach_at(c) for c in self.jaw_closure)

    @property
    def jaw_opening_m(self) -> float:
        """Radius of the largest circle that fits through the jaw opening.

        For three half-planes ``x·o_i <= R_i`` with the ``o_i`` at 120°, the
        Chebyshev radius is ``mean(R_i)``: summing the three constraints
        kills the ``x`` term because the directions sum to zero.  So one
        lagging jaw is partly compensated by the other two, and the
        retention test is a statement about the jaw set, not about any one
        jaw — which is exactly the property a three-jaw claim needs.
        """

        return sum(self.jaw_reaches_m) / JAW_COUNT

    @property
    def head_can_pass(self) -> bool:
        g = self.geometry
        return self.jaw_opening_m >= g.head_radius_m - g.retention_margin_m

    def _jaw_in_band(self, index: int) -> bool:
        g = self.geometry
        reach = g.reach_at(self.jaw_closure[index])
        return g.band_inner_reach_m <= reach <= g.band_outer_reach_m

    def _head_above_jaws(self, drone: DroneBody | None, dock_center: Vec3) -> bool:
        if drone is None or self.probe_phase is ProbePhase.FREE:
            return False
        g = self.geometry
        rel_z = (self._probe_tip(drone) - dock_center).z
        return rel_z - g.head_height_m >= g.jaw_plane_z_m

    def _contact_radius_m(self, drone: DroneBody | None, dock_center: Vec3) -> float | None:
        """What the closing jaws meet in their own plane, if anything.

        Three cases, and the middle one is why the band switch discriminates:
        the mast (Ø3), the head (Ø12) if the probe stalled with its head in
        the jaw plane, or nothing at all if the probe is below the jaws or
        absent.  A jaw stopped by each of those sits at a different reach.

        The head case is gated on the jaws still being open enough to admit
        it.  A head cannot occupy a plane the jaws have already closed
        inside: pressed against their underside it is an obstruction, not a
        thing they are resting on, and it cannot cam them back open.  Without
        that gate a rising probe would push a closed iris open, which is the
        opposite of retention.
        """

        if drone is None or self.probe_phase is ProbePhase.FREE:
            return None
        g = self.geometry
        rel_z = (self._probe_tip(drone) - dock_center).z
        if rel_z - g.head_height_m > g.jaw_plane_z_m:
            return g.mast_radius_m
        if rel_z >= g.jaw_plane_z_m and self.head_can_pass:
            return g.head_radius_m
        return None

    def _resolve_contact(
        self, desired: list[float], contact_radius_m: float, offset: Vec3, allowed_m: float
    ) -> tuple[list[float], Vec3]:
        """Close the jaws onto a rigid cylinder and let them center it.

        This is the candidate's central mechanism and the reason it might
        beat a fork, so the surrogate is written out rather than tuned:

        * Each jaw would like to reach ``R_i = reach(desired_i)``.
        * The cylinder axis must satisfy ``d·o_i <= R_i - r`` for every jaw.
          Because the three directions sum to zero, that set is non-empty
          exactly when ``mean(R_i) >= r``.
        * While it is non-empty the jaws merely *push* the cylinder — the
          axis is projected into the set and the jaws reach their targets.
          This is the centering: the acceptance opening is the throat's,
          and closure walks the mast to the axis from wherever it started.
        * When it is empty the jaws are gripping.  The drive ring is
          deliberately compliant (it is what lets three jaws converge on an
          off-axis mast at all), so the interference is shared equally: each
          jaw gives up the same reach, and the axis lands at the unique
          point where all three touch.

        The funnel throat is a hard wall the jaws cannot push a probe
        through, so the resolved axis is clamped to ``allowed_m`` and the
        jaws are re-limited against the clamped position.
        """

        g = self.geometry
        reaches = [g.reach_at(c) for c in desired]
        share = (sum(reaches) - JAW_COUNT * contact_radius_m) / JAW_COUNT

        if share <= 0.0:
            # Gripping: solve d·o_i = R_i - share - r directly.  With three
            # unit vectors at 120°, sum(o_i o_i^T) = 1.5 I, so the inverse is
            # the 2/3-scaled sum, and the residuals sum to zero by
            # construction, which makes the system consistent.
            residual = [reaches[i] - share - contact_radius_m for i in range(JAW_COUNT)]
            solved = Vec3()
            for i in range(JAW_COUNT):
                solved = solved + _DIRECTIONS[i] * (residual[i] * 2.0 / 3.0)
            offset = solved
        else:
            # Not yet gripping: project the axis into the feasible triangle.
            # Cyclic projection onto three half-planes; a handful of passes
            # is ample for a triangle this well conditioned.
            for _ in range(8):
                moved = False
                for i in range(JAW_COUNT):
                    over = (
                        offset.x * _DIRECTIONS[i].x + offset.y * _DIRECTIONS[i].y
                    ) - (reaches[i] - contact_radius_m)
                    if over > 0.0:
                        offset = offset - _DIRECTIONS[i] * over
                        moved = True
                if not moved:
                    break

        lateral = offset.lateral_norm()
        if lateral > allowed_m and lateral > 0.0:
            offset = offset * (allowed_m / lateral)

        closures = []
        for i in range(JAW_COUNT):
            projected = offset.x * _DIRECTIONS[i].x + offset.y * _DIRECTIONS[i].y
            limit = g.closure_at(contact_radius_m + projected)
            closures.append(max(0.0, min(desired[i], limit)))
        return closures, offset

    def _advance_jaws(
        self, drone: DroneBody | None, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Step the jaw train one tick behind the drive ring."""

        g = self.geometry
        step = self._dt_s / g.jaw_travel_time_s
        desired: list[float] = []
        for i in range(JAW_COUNT):
            target = min(self.servo.position, self.jaw_close_limit[i])
            target = max(target, self.jaw_open_limit[i])
            current = self.jaw_closure[i]
            if current < target:
                desired.append(min(target, current + step))
            else:
                desired.append(max(target, current - step))

        contact = self._contact_radius_m(drone, dock_center)
        if contact is None or drone is None:
            self.jaw_closure = desired
            return

        rel = self._probe_tip(drone) - dock_center
        allowed = self._funnel_allowed_radius(rel.z)
        closures, offset = self._resolve_contact(desired, contact, rel.lateral(), allowed)
        self.jaw_closure = closures

        moved = (offset - rel.lateral()).lateral_norm()
        if moved > 1e-12:
            tip = dock_center + offset.with_z(rel.z)
            drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
            # The jaws impose the lateral motion; they do not leave the
            # aircraft with lateral velocity relative to the dock.
            drone.velocity = dock_velocity.lateral().with_z(drone.velocity.z)

    # -- main step ---------------------------------------------------------

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        drone: DroneBody | None,
        commands: DockCommands,
    ) -> IrisStepResult:
        """Advance mechanics, switches, the real controller, and the drive."""

        g = self.geometry
        events: list[Event] = []
        contact_speed: float | None = None
        seat_truth = False
        jaws_tight = not self.head_can_pass

        if drone is None:
            self.probe_phase = ProbePhase.FREE
            self._prev_rel_z = None
        else:
            rel = self._probe_tip(drone) - dock_center
            closing = (drone.velocity - dock_velocity).z

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
                head_above = self._head_above_jaws(drone, dock_center)
                if rel.z < 0.0:
                    self.probe_phase = ProbePhase.FREE
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="clear_of_funnel")
                    )
                elif jaws_tight and not head_above and rel.z > g.jaw_plane_z_m:
                    # Closed jaws are an obstruction to a head that has not
                    # reached them.  No snapshot and no latch: the head is
                    # blocked exactly while the opening is smaller than it
                    # is, which is also the retention rule, so the two can
                    # never disagree.
                    tip = dock_center + Vec3(rel.x, rel.y, g.jaw_plane_z_m)
                    drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
                    if (drone.velocity - dock_velocity).z > 0.0:
                        drone.velocity = drone.velocity.with_z(dock_velocity.z)
                    self._constrain_to_funnel(drone, dock_center, dock_velocity)
                elif rel.z >= g.seat_travel_m:
                    self.probe_phase = ProbePhase.SEATED
                    self._seat(drone, dock_center, dock_velocity)
                    events.append(Event(EventKind.PROBE_SEATED, now_s))
                else:
                    self._constrain_to_funnel(drone, dock_center, dock_velocity)

            elif self.probe_phase is ProbePhase.SEATED:
                retained = jaws_tight and self._head_above_jaws(drone, dock_center)
                pulling_out = (
                    drone.armed
                    and (drone.velocity - dock_velocity).z < -g.unseat_speed_m_s
                )
                slid_out = drone.armed and rel.z < g.jaw_plane_z_m
                if (pulling_out or slid_out) and not retained:
                    self.probe_phase = ProbePhase.INSERTED
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="unseated")
                    )
                elif not drone.armed or retained:
                    self._seat(drone, dock_center, dock_velocity)
                else:
                    self._hold_at_seat(drone, dock_center, dock_velocity)

            rel = self._probe_tip(drone) - dock_center
            seat_truth = (
                self.probe_phase is ProbePhase.SEATED
                and rel.z >= g.seat_travel_m - g.seat_hysteresis_m
            )
            self._prev_rel_z = rel.z

        # -- truth, then indication, never the other way round ------------
        head_above = self._head_above_jaws(drone, dock_center)
        grip_truth = jaws_tight and head_above
        closures = tuple(self.jaw_closure)
        reaches = self.jaw_reaches_m
        synchronized = max(closures) - min(closures) <= g.jaw_sync_tolerance

        jaw_reported = tuple(
            switch.step(self._jaw_in_band(i)) for i, switch in enumerate(self.jaw_switches)
        )
        reported_s1 = self.seat_switch.step(seat_truth)
        reported_s2 = self.keeper_switch.step(all(jaw_reported))
        jaw_lag_reported = any(jaw_reported) and not all(jaw_reported)

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

        if output.capture_confirmed and not self._was_confirmed:
            if seat_truth and grip_truth:
                events.append(Event(EventKind.CAPTURE_CONFIRMED, now_s))
            else:
                events.append(
                    Event(
                        EventKind.FALSE_CAPTURE_CONFIRMED,
                        now_s,
                        detail="controller confirmed without three-jaw retention",
                    )
                )
        if self._was_confirmed and not output.capture_confirmed:
            events.append(Event(EventKind.RELEASED, now_s))
        self._was_confirmed = output.capture_confirmed

        # A disarmed aircraft relies entirely on the mechanism.  Jaws that
        # were gripping a seated probe and open with no release commanded
        # have dropped it.  Edge-triggered, and only for an aircraft that is
        # actually in the iris.
        if (
            drone is not None
            and not drone.armed
            and self.probe_phase is ProbePhase.SEATED
            and self._prev_grip_truth
            and not grip_truth
            and not commands.release_request
            and not commands.emergency_release
        ):
            events.append(Event(EventKind.DROPPED_AIRCRAFT, now_s))
        self._prev_grip_truth = grip_truth

        result = IrisStepResult(
            probe_phase=self.probe_phase,
            seat_truth=seat_truth,
            keeper_closed_truth=grip_truth,
            reported_s1=reported_s1,
            reported_s2=reported_s2,
            controller=output,
            contact_closing_speed_m_s=contact_speed,
            events=tuple(events),
            jaw_closures=closures,
            jaw_reaches_m=reaches,
            jaw_reported=jaw_reported,
            jaw_opening_m=self.jaw_opening_m,
            head_above_jaws=head_above,
            jaws_synchronized=synchronized,
            jaw_lag_reported=jaw_lag_reported,
            mast_offset_m=(
                (self._probe_tip(drone) - dock_center).lateral_norm()
                if drone is not None
                else 0.0
            ),
        )

        # The drive ring and the jaw train advance after the controller has
        # spoken, matching the baseline's causality: a command issued this
        # step moves hardware for the next one.
        close_commanded = output.keeper_command is KeeperCommand.CLOSE
        self.servo.step(self._dt_s, close_commanded)
        self._advance_jaws(drone, dock_center, dock_velocity)

        return result


@dataclass(frozen=True)
class IrisSpec:
    """Design-study entry for the three-jaw iris.

    Satisfies :class:`~aiur.sim.mechanism.MechanismSpec`.
    """

    key: str
    name: str
    summary: str
    part_count: int
    actuator_count: int
    sensed_channels: int
    est_dock_mass_g: float
    est_probe_mass_g: float
    known_weaknesses: tuple[str, ...]
    geometry: IrisGeometry = IrisGeometry()

    def build(self, dt_s: float) -> IrisMechanism:
        return IrisMechanism(self.geometry, dt_s=dt_s)


SPEC = IrisSpec(
    key="iris",
    name="Three-jaw iris keeper",
    summary=(
        "Same Ø180 mm funnel as Rev-A; retention by three jaws closing "
        "radially under the probe head's seat, driven from one actuator "
        "through a compliant ring, with a per-jaw band switch that is made "
        "only while the jaw rests on the Ø3 mm mast."
    ),
    # Funnel, 3 jaws, 3 pivot pins, 3 links, drive ring, ring retainer,
    # servo crank, servo, 3 jaw band switches, seat switch, 4 switch
    # brackets, base plate.  Roughly double the Rev-A fork's count.
    part_count=23,
    actuator_count=1,
    # S1 and the series S2'.  Three switches, ONE channel.
    sensed_channels=2,
    # Engineering targets, geometry-derived in the same style as the CAD
    # manifest's solid-PETG estimates; the 18 g XL330 is the only vendor
    # figure in the number.  Nothing has been weighed.
    est_dock_mass_g=106.0,
    est_probe_mass_g=6.0,
    known_weaknesses=(
        "Two sensed channels, not three.  The three per-jaw band switches "
        "are wired in series into one S2' channel because the real "
        "DockController takes two booleans, and they share bracket family, "
        "linkage datum, harness, pull-up rail and switch lot.  Capture "
        "confirmation is therefore S1 AND S2', exactly Rev-A's arithmetic; "
        "the claim that improves is what S2' means, not how many opinions "
        "there are.",
        "S2' senses 'a Ø3 mm cylinder is between all three jaws', which is "
        "not 'a head is above the jaws'.  A fractured mast (FM-PR-02) or a "
        "head worn undersize and pulled through (FM-PR-03) leaves the mast "
        "in the jaws and still confirms capture.  The seated-but-unretained "
        "residual is narrowed, not closed.",
        "The empty-throat discrimination is a TIMING property, not a "
        "geometric one.  An empty jaw sweeps through the band on its way to "
        "its stop; only a debounce longer than that transit rejects it.  At "
        "the nominal 0.35 s stroke the margin is 1.76x, and it shrinks "
        "linearly with actuator speed: a sagging or slow servo (0.8 s "
        "stroke was a live cell in the deletion review) re-opens a "
        "transient false S2' on an empty close.  This is a requirement the "
        "fork does not have.",
        "The band debounce is squeezed from both ends: it must exceed the "
        "empty transit (0.079 s) and still let S2' arrive inside the "
        "controller's 1.0 s lock timeout (0.73 s at nominal stroke).  A "
        "switch datum, an actuator stroke time and a software timeout are "
        "therefore coupled across three subsystems, and none of the three "
        "owners would see the coupling in their own document.",
        "A lagging jaw is reliably detected only as the ABSENCE of S2', "
        "which is safe but uninformative.  The per-jaw switches give a "
        "positive 'jaw N lags' diagnosis only when at least one jaw holds "
        "the band; when one linkage binds early, the other two overrun past "
        "the displaced mast and every switch reads open, so the mechanism "
        "knows something is wrong and not which jaw.",
        "Three linkages off one actuator roughly doubles the dock-side part "
        "count against a fork with guides and an end stop, and adds three "
        "pivot wear surfaces, three backlash paths and three switch datums "
        "to a printed assembly.  Every one of them is a new "
        "FM-SN-11-class bracket-shift mode, and the count is itself an "
        "estimate off a sketch, not a BOM.",
        "COUNTING CONVENTION, because part_count is about to be compared "
        "across candidates and the conventions do not match.  The 23 here "
        "counts every discrete piece a technician handles — each jaw, pivot "
        "pin, link, bracket and fastener-bearing member separately.  At the "
        "coarser 'distinct part type' granularity the baseline entry in "
        "aiur/sim/architectures.py uses (5 for funnel + fork + servo + two "
        "switches) the iris is about 10: funnel, jaw, pivot pin, link, "
        "drive ring, crank, servo, jaw switch, seat switch, base plate. "
        "Reading 23 against 5 overstates the penalty by roughly two; "
        "reading 10 against 5 is the like-for-like comparison.  Neither "
        "number is a BOM, and the trade study must normalise the convention "
        "before it ranks anything on this axis.",
        "Jaw contact-angle wedging under load is NOT modeled.  Release is "
        "assumed to be geometry-limited, i.e. the under-head face is "
        "undercut so retention load reacts axially and cannot self-lock. "
        "That is a design intent, not a result; the iris analogue of the "
        "Rev-A release defect is a jaw contact angle that jams under the "
        "0.468 N hanging load, and this model cannot find it.  It is "
        "exercised only as an injected jaw_open_limit defect.",
        "Mast centering assumes a rigid mast and a perfectly compliant "
        "drive ring sharing interference equally between jaws.  A real ring "
        "has finite compliance and finite friction, so the centering "
        "authority — the whole reason this candidate exists — is an "
        "engineering estimate that A0 must measure before the claim stands.",
        "A disarmed aircraft that loses grip is still pinned to the seat by "
        "fiat, exactly as in dock_physics.py, so DROPPED_AIRCRAFT is scored "
        "as an event and not as a fall.  Kept deliberately identical to the "
        "baseline so the two candidates are comparable, but it means "
        "neither model tests what happens after the drop.",
        "The shared fault injector reaches seat_switch, keeper_switch and "
        "servo only.  Per-jaw switch faults and per-jaw linkage binds are "
        "exercised by this module's own tests, not by campaign fault plans, "
        "so campaign statistics under-sample this architecture's specific "
        "failure space.",
    ),
)


def iris_mechanism_factory(config: "EpisodeConfig", dt_s: float) -> IrisMechanism:
    """Build an iris sized to an episode's shared dock geometry.

    The engine hands guidance ``probe_height_m`` and ``seat_travel_m`` from
    ``config.dock_geometry``, so a mechanism that used its own numbers would
    be aimed at by a guidance stack pointing somewhere else.  The funnel,
    seat and probe dimensions therefore come from the config; only the jaw
    train is this candidate's own.
    """

    shared: DockGeometry = config.dock_geometry
    base = SPEC.geometry
    geometry = IrisGeometry(
        funnel_entrance_radius_m=shared.funnel_entrance_radius_m,
        rim_annulus_m=shared.rim_annulus_m,
        seat_travel_m=shared.seat_travel_m,
        seat_hysteresis_m=shared.seat_hysteresis_m,
        probe_height_m=shared.probe_height_m,
        bounce_speed_m_s=shared.bounce_speed_m_s,
        unseat_speed_m_s=shared.collet_pullout_speed_m_s,
        mast_radius_m=base.mast_radius_m,
        head_radius_m=base.head_radius_m,
        head_height_m=base.head_height_m,
        jaw_below_seat_m=base.jaw_below_seat_m,
        jaw_open_reach_m=base.jaw_open_reach_m,
        jaw_closed_reach_m=base.jaw_closed_reach_m,
        retention_margin_m=base.retention_margin_m,
        band_outer_reach_m=base.band_outer_reach_m,
        band_inner_reach_m=base.band_inner_reach_m,
        jaw_switch_debounce_s=base.jaw_switch_debounce_s,
        jaw_travel_time_s=base.jaw_travel_time_s,
        jaw_sync_tolerance=base.jaw_sync_tolerance,
    )
    return IrisMechanism(geometry, dt_s=dt_s)
