"""Deep-cup capture candidate for the CARRIER-P0 architecture trade study.

The baseline converts a lateral position error into a probe-centring push
with a Ø180 mm funnel and then demands millimetre coincidence at a Ø16 mm
throat.  ``docs/verticals`` calls that inherited demand SHARED-001 and names
it the hardest requirement every non-laboratory vertical carries.  This
candidate attacks it from the other end: delete the throat, delete the
probe, and make the *dock* big enough to swallow the aircraft's whole upper
structure, so that final registration is a centimetre problem instead of a
millimetre one.

How it works
------------
A downward-opening cup, Ø300 mm bore with a Ø350 mm flared mouth, hangs
below the carrier rail.  The aircraft flies up into it.  A crown plate on a
compliant pad closes the top of the bore and gives the seat switch
something to sense; a single latch bar pivots across the full bore, sweeps
under the aircraft's belly hoop, and traps it between bar and pad.  Two
independent switches report the two facts the real ``DockController``
consumes: crown at the pad (S1) and latch at its closed stop (S2).  The
controller is the un-mocked ``aiur.dock_controller.DockController``, exactly
as in :mod:`aiur.sim.dock_physics`, so the same latch logic is under test.

What it buys, and what it costs
-------------------------------
Mechanically the cup accepts the aircraft anywhere within ±72.5 mm of the
bore axis, against the baseline's ±2.0 mm of throat freedom.  That is the
whole argument for building it.

Everything else about the architecture is worse, and the model is written
so that shows up rather than hides:

* **Every wall is a rotor wall.**  The baseline deliberately keeps the
  rotor plane below the funnel lip (``hardware/dock/p0a-bench.md``
  clearance check: 77.5 mm swept radius against a 90 mm mouth leaves
  12.5 mm).  A deep cup cannot: the guarded rotor disc goes *inside*.  So
  the cup has no benign contact surface at all — what the funnel scores as
  a centring push, this scores as ``PROP_FUNNEL_CONTACT``.  Worse, the
  mouth swallows the crown cap 40 mm before the rotor plane reaches the
  rim, so a bad approach is already committed by the time it is rejected.
* **No passive retention whatsoever.**  There is no collet, no throat, no
  friction: between seat arrival and latch closure the aircraft holds
  itself against the pad on thrust alone, and any sustained relative
  descent unseats it.  An unpowered aircraft with the latch open falls out
  of the cup, and this model lets it fall rather than pinning it to the
  seat by fiat.
* **Mass.**  See the table below.  A cup that swallows a 100 mm-diagonal
  aircraft is roughly 0.11 m² of shell plus a full-diameter deck, and no
  wall thickness makes that fit a 180 g dock allocation.

Mass estimate (engineering target, geometry-derived, nothing weighed)
--------------------------------------------------------------------
Same method as the CAD manifest's funnel figure: lateral area x wall
thickness x solid PETG at 1.27 g/cm^3.  No vendor mass appears here except
the XL330, which the programme already carries.

===========================================  ==================  =======
Item                                         Geometry            est. g
===========================================  ==================  =======
Cup barrel                                   Ø300 x 120, 1.0 mm    144
Mouth flare                                  Ø350->Ø300 / 20 mm     50
Three hoop stiffening ribs                   6 x 1.5 mm on Ø300     32
Crown deck (spoked, ~35% of a Ø300 disc)     2.5 mm                 79
Latch bar + pivot boss + far catch           300 mm, 18 x 6 mm      49
XL330-M288-T                                 vendor                 18
Servo bracket, horn, link                    --                     10
Crown plate + TPU pad + three posts          Ø120 plate             39
S1, S2, brackets, harness                    --                     15
Rail mount flange and fasteners              --                     18
**Total, dock side**                                              **454**
===========================================  ==================  =======

That is 2.5x the 180 g dock allocation and 45% of the carrier's 1.0 kg
rated payload, against 75 g for the baseline dock.  Shrinking the bore to
the baseline funnel's Ø180 still lands near 280 g — the barrel and deck do
not disappear — and drops guarded-rotor clearance to 12.5 mm, which deletes
the only reason to build the thing.  **Acceptance and mass are the same
number**, and that is the finding this candidate exists to produce.

Aircraft side: a Ø40 x 1 mm crown cap (~2 g) giving the seat switch a datum,
and a Ø110 belly hoop tied to the frame (~4 g) for the latch bar to bear on.
No mast, no head — 6 g against the programme's ≤8 g probe budget.

What the twin says when it is asked
-----------------------------------
Model results, not vehicle performance.  ``sil_p0b`` seeds 1-24, the trade
study's own wind axis over 12 seeds, the retuned degraded-sensor sweep over
40 seeds, and ``sil_p0c`` over 12 seeds — deep cup against the baseline:

=====================================  ==============  ===================
Condition                              baseline        deep cup
=====================================  ==============  ===================
sil_p0b nominal                        24/24, safe     23/24, safe
sil_p0b, one sampled fault             14/24, safe     12/24, safe
sil_p0b, one correlated pair           7/24, safe      6/24, safe
trade study, 0.5 m/s wind              100%, safe      67%, safe
trade study, 1.0 m/s wind              58%, safe       0%, **5/12 UNSAFE**
degraded sensor, 1x / 3x noise         100% / 100%     87.5% / 95%
degraded sensor, 10x / 30x noise       100% / 72.5%    100% / 72.5%
sil_p0c launch/sortie/recover          12/12, safe     10/12, **2 UNSAFE**
=====================================  ==============  ===================

Five readings, and the last three are what decide it.

1. It captures.  The architecture works, and on the bench-rig recovery
   scenario it is safe under nominal, single-fault and correlated-fault
   conditions.
2. **It buys nothing on the axis it was proposed for.**  The deep cup was
   supposed to trade millimetre terminal navigation for centimetre.  It does
   not, because the binding constraint is not the mechanism: the supervisor
   enables capture and authorises disarm on ``GuidanceParams.seat_confirm_m``
   — a 15 mm *navigation* distance to a point, sized for a throat.  A funnel
   satisfies it by physically centring the probe; a straight bore keeps
   whatever offset the approach arrived with, so the cup is refused captures
   it would mechanically have made and loses 1-2 seeds in 24.  Relaxing that
   constant to 25 mm restores 24/24 — and weakens the finding-2 plausibility
   gate that stops a stuck seat switch disarming an aircraft in free air.
   The requirement lives in software, and swapping the mechanism does not
   move it.
3. **Wind is the sharpest form of the contact defect.**  At 1.0 m/s mean
   wind the deep cup captures nothing and strikes in 5 episodes out of 12,
   where the baseline captures 58% and strikes none; even 0.5 m/s costs a
   third of the captures against the baseline's none.  The funnel absorbs a
   lateral excursion as a centring push.  The cup has no benign surface to
   absorb it with, so the identical excursion is a rotor strike.  Whatever
   else this candidate is, it is strictly more fragile to disturbance than
   the article it was proposed to replace.
4. **It is unsafe on the P0-C launch, with no fault injected.**  In DEPART
   the guidance stack's carrier-proximity reflex commands 0.6 m/s laterally
   while the aircraft is still 60 mm inside the cup.  The baseline receives
   the identical command and survives it because the funnel taper clamps the
   probe to a few millimetres of the axis on the way out; a straight bore has
   no such veto, so the guarded rotors reach the bore wall at ~93 mm and the
   twin scores ``PROP_FUNNEL_CONTACT``.  Two seeds in twelve.  Note what that
   says about the baseline as much as about this candidate: the funnel is
   silently overriding a guidance command that should not be issued, and
   nobody wrote that down as a requirement.
5. Note also that :mod:`aiur.sim.design_study` runs only ``sil_p0b``, which
   is a bench rig with no hull and therefore no evasion reflex.  The trade
   study alone would have reported this architecture clean.  That is a gap
   in the harness, reported here rather than worked around.

Datum convention
----------------
The twin's shared guidance computes the aircraft's capture datum as
``DockGeometry.probe_height_m`` above the aircraft reference point and
drives it to ``seat_travel_m`` above the entrance plane, and
:mod:`aiur.sim.design_study` runs every candidate against the *default*
``DockGeometry``.  Those numbers belong to the harness, not to this
mechanism, so the cup adopts them unchanged: crown 50 mm above the
reference point, seat 100 mm above the rim.  The consequence is that the
modelled aircraft sits with its rotor plane 60 mm inside the bore, which is
the regime the contact model has to get right.  The mass table above is
computed from the physical 140 mm bore depth, not from the modelled 100 mm
seat, so it is not flattered by the adopted datum.

Physics status
--------------
Engineering-estimate surrogate, same fidelity and same spirit as
``dock_physics.py``: plane-crossing acceptance, a depth-dependent wall
radius, a cam window on the latch, and a static release margin.  Nothing
here is calibrated, no candidate has been built, and no number below is a
measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..dock_controller import DockController, DockInputs, KeeperCommand
from .bodies import DroneBody
from .dock_physics import DockCommands, DockStepResult, ProbePhase
from .events import Event, EventKind
from .sensors import KeeperServo, Switch
from .vec import Vec3

#: Standard gravity.  Used only so an unretained, unpowered aircraft
#: actually falls out of the cup instead of being pinned there — the
#: baseline pins it, and docs/dock-deletion-review.md calls that out as a
#: model that never tests the retention claim it makes.
GRAVITY_M_S2 = 9.81


@dataclass(frozen=True)
class CupGeometry:
    """Deep-cup geometry.  Every value is an engineering target.

    The two radii that matter are ``bore_radius_m`` and
    ``prop_swept_radius_m``: their difference is the entire acceptance
    envelope of the architecture, and it is also, through the barrel area,
    the entire mass of the architecture.
    """

    #: Flared mouth, outer radius.  Ø350 mm.
    rim_radius_m: float = 0.175
    #: Straight bore the aircraft occupies.  Ø300 mm.
    bore_radius_m: float = 0.150
    #: Depth over which the mouth flare closes down to the bore.
    lead_in_m: float = 0.020
    #: Conservative radial swept extent of the guarded rotor disc:
    #: 50 mm motor-centre radius + 27.5 mm prop radius, per
    #: hardware/dock/p0a-bench.md.  Vendor-derived geometry, not a mass.
    prop_swept_radius_m: float = 0.0775
    #: Crown cap on top of the airframe; the only thing inside the cup
    #: during the first 40 mm of entry.
    cap_radius_m: float = 0.020

    #: Aircraft datum heights, all relative to the aircraft reference point.
    #: ``crown_height_m`` is inherited from the shared harness (see module
    #: docstring); the other two place the rotor plane and the belly hoop
    #: relative to it.
    crown_height_m: float = 0.050
    rotor_below_crown_m: float = 0.040
    belly_below_crown_m: float = 0.070

    #: Crown travel from the rim plane to the deck pad.  Inherited.
    seat_depth_m: float = 0.100
    #: Seat hysteresis before the crown switch's physical input drops out.
    #: Sized to cover ``latch_settle_m`` with margin, because the aircraft
    #: settles onto the bar the moment the latch takes the load.
    seat_hysteresis_m: float = 0.006
    #: Height of the latch bar's upper bearing face above the rim when
    #: closed.  Sits 2 mm below the belly hoop at the nominal seat.
    latch_face_m: float = 0.028
    #: The bar's leading ramp will lift a low aircraft this far into the
    #: seat.  Below that the ramp root meets the belly hoop instead, which
    #: is a contact, not a capture.
    latch_cam_lift_m: float = 0.018
    #: Pad compression once the load transfers from thrust to the bar.
    latch_settle_m: float = 0.002

    #: Off-axis limit of the *sensed* seat.  The crown plate floats on
    #: three posts with one centre switch, so an off-centre crown tips the
    #: plate instead of translating it and the switch does not make.  This
    #: is deliberately narrower than the bore: the sensing envelope, not
    #: the mechanical one, is what the architecture can actually claim.
    crown_switch_radius_m: float = 0.035

    #: Closing speed above which arrival at the deck pad is a strike rather
    #: than a seating.  Above the guidance stack's 0.20 m/s hard limit, so
    #: it only fires once the supervisor has already been defeated.
    seat_impact_speed_m_s: float = 0.30
    #: Sustained relative descent that unseats an unlatched aircraft.  This
    #: is a numerical criterion, NOT a passive retention force: the deep cup
    #: has no collet and holds nothing before the bar closes.
    unseat_speed_m_s: float = 0.020
    #: Crown drop below the seat that counts as unseated.
    unseat_drop_m: float = 0.008

    #: Latch bar span, pivot to far catch.  Two bore radii.
    latch_span_m: float = 0.300
    #: Opening torque allowance at the pivot.  An engineering placeholder
    #: for a sized drivetrain, deliberately not a vendor stall figure.
    latch_open_torque_n_m: float = 0.20
    #: Sliding friction between the belly hoop and the bar's bearing face.
    latch_friction_coeff: float = 0.35
    latch_bearing_arm_m: float = 0.008
    latch_pivot_radius_m: float = 0.004
    #: Overturning moment the printed pivot boss is assumed to take before
    #: the bar tips in its bearing and binds.  Engineering allowance.
    pivot_moment_allow_n_m: float = 0.90

    def __post_init__(self) -> None:
        if self.bore_radius_m <= self.prop_swept_radius_m:
            raise ValueError("bore must clear the guarded rotor disc")
        if self.rim_radius_m < self.bore_radius_m:
            raise ValueError("mouth cannot be narrower than the bore")
        if self.latch_face_m >= self.seat_depth_m - self.belly_below_crown_m + 0.010:
            raise ValueError("latch face would foul the seated belly hoop")

    @property
    def prop_clearance_m(self) -> float:
        """Lateral offset at which the rotor disc meets the bore wall.

        The headline acceptance number, and the one the mass scales with.
        """

        return self.bore_radius_m - self.prop_swept_radius_m


class DeepCupAssembly:
    """One deep cup with a single over-top latch bar, serving one aircraft.

    Truth and indication are tracked separately throughout, for the same
    reason ``DockAssembly`` does it: a mechanism that cannot be wrong about
    itself cannot be tested.  Three facts are kept apart here where the
    baseline only needs two:

    * ``seat_truth`` — the crown is physically against the deck pad;
    * ``latch_closed_truth`` — the bar reached its closed stop, which is
      what S2 senses and is true whether or not anything is under it;
    * the retention truth reported as ``DockStepResult.keeper_closed_truth``
      — the bar is closed *and* swept under the belly hoop.  The engine uses
      that field as its mechanical-hold predicate for ``UNSAFE_DISARM``, so
      it must mean retention rather than actuator position.
    """

    def __init__(
        self,
        geometry: CupGeometry,
        *,
        dt_s: float,
        controller: DockController | None = None,
    ) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self.geometry = geometry
        self._dt_s = dt_s
        self.controller = controller if controller is not None else DockController()
        # Named ``servo`` / ``seat_switch`` / ``keeper_switch`` because
        # aiur.sim.faults reaches for exactly those attributes.  Here they
        # are the latch actuator, the crown switch and the latch-closed
        # switch; the fault menu applies unchanged.
        self.servo = KeeperServo(travel_time_s=0.45)
        self.seat_switch = Switch(dt_s=dt_s)
        self.keeper_switch = Switch(dt_s=dt_s)
        self.probe_phase = ProbePhase.FREE
        #: Latest actuator-position truth, kept separate from retention.
        self.latch_closed_truth = False
        #: Bench screening load carried by the bar on top of the aircraft's
        #: own weight, in newtons.  Episodes never set it; it exists so the
        #: P0-A loaded-release screen can be *run* against this model rather
        #: than only asserted in prose.
        self.external_load_n = 0.0
        #: True while the retained load has tipped the bar in its pivot
        #: bearing.  A bound bar cannot open, which is the Rev-A defect this
        #: architecture has to prove it does not repeat.
        self.latch_bound = False

        self._was_confirmed = False
        self._prev_crown_z: float | None = None
        self._latch_was_engaged = False
        self._latch_under_belly = False
        self._latch_cam_lift = False
        #: Crown height the closed bar blocks the aircraft at, when it did
        #: not end up under the belly hoop.  ``None`` means it did.
        self._latch_block_crown_z: float | None = None
        self._prev_retained = False
        self._prop_contact_latched = False
        self._carry_offset: Vec3 | None = None

    # -- static design checks ---------------------------------------------

    def release_force_margin(self, retained_load_n: float) -> float:
        """Torque margin on commanding the latch open under load.

        The programme's Rev-A defect was a keeper that could not release a
        captured aircraft, so this is the number the architecture has to
        answer.  A pivoting bar carries the retention load *normal* to its
        direction of travel, so opening is opposed only by friction at the
        bearing face and the pivot — no component of the load resists the
        motion.  That is this architecture's one clean mechanical win over
        a fork sliding in loaded guides.

        Static estimate against an assumed torque allowance, not a
        measurement, and it says nothing about the bar bowing under load;
        see :meth:`pivot_moment_margin` for the mode that actually bites.
        """

        g = self.geometry
        opposing = (
            g.latch_friction_coeff
            * max(0.0, retained_load_n)
            * (g.latch_bearing_arm_m + g.latch_pivot_radius_m)
        )
        if opposing <= 0.0:
            return float("inf")
        return g.latch_open_torque_n_m / opposing

    def pivot_moment_margin(
        self, retained_load_n: float, *, far_catch_engaged: bool = True
    ) -> float:
        """Margin against the pivot boss tipping under an off-pivot load.

        A full-bore bar puts the retained load up to half a span away from
        its pivot.  With the far catch engaged the bar is supported at both
        ends and the boss reacts a much smaller share; while the bar is
        still travelling — which is exactly when its cam ramp is lifting an
        aircraft — it is a 150 mm cantilever.  Crude lever-arm surrogate,
        stated so the number can be argued with.
        """

        g = self.geometry
        lever = g.latch_span_m / (4.0 if far_catch_engaged else 2.0)
        moment = max(0.0, retained_load_n) * lever
        if moment <= 0.0:
            return float("inf")
        return g.pivot_moment_allow_n_m / moment

    @property
    def latch_bind_load_n(self) -> float:
        """Retained load above which the bar tips in its bearing and stops.

        Below it the bar moves in both directions and release works; above
        it the bar cannot open *or* close, which is what the P0-A loaded
        emergency-release trials exist to find.  The modelled aircraft
        weighs 0.36 N, so an episode never reaches this — only a bench run
        with :attr:`external_load_n` set does.
        """

        g = self.geometry
        return g.pivot_moment_allow_n_m / (g.latch_span_m / 4.0)

    # -- interface ---------------------------------------------------------

    def seed_seated(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Place an aircraft at the seat, for scenarios that start captured."""

        g = self.geometry
        self.probe_phase = ProbePhase.SEATED
        self._prev_crown_z = g.seat_depth_m
        self._prop_contact_latched = False
        drone.position = Vec3(
            dock_center.x,
            dock_center.y,
            dock_center.z + g.seat_depth_m - g.crown_height_m,
        )
        drone.velocity = dock_velocity

    def reset_controller(self) -> None:
        """Model a controller brownout: the logic restarts, the cup does not.

        Bar position, servo travel, switch state and the aircraft all
        survive, because a power blip does not move hardware.  Only the
        controller's own memory is lost, which is the condition under which
        it must re-derive what it is holding from two switches — and for
        this architecture S2 cannot tell it whether the bore is occupied.
        """

        self.controller = type(self.controller)(
            lock_timeout_s=self.controller.lock_timeout_s,
            release_timeout_s=self.controller.release_timeout_s,
        )
        self._was_confirmed = False

    # -- geometry helpers --------------------------------------------------

    def _crown(self, drone: DroneBody) -> Vec3:
        return drone.position + Vec3(0.0, 0.0, self.geometry.crown_height_m)

    def _wall_radius(self, depth_m: float) -> float:
        """Inner wall radius at a given depth above the rim plane."""

        g = self.geometry
        if depth_m <= 0.0:
            return g.rim_radius_m
        if depth_m >= g.lead_in_m:
            return g.bore_radius_m
        fraction = depth_m / g.lead_in_m
        return g.rim_radius_m + (g.bore_radius_m - g.rim_radius_m) * fraction

    def _set_crown_z(self, drone: DroneBody, dock_center: Vec3, crown_z: float) -> None:
        """Move the aircraft vertically only; the cup does not centre it."""

        drone.position = Vec3(
            drone.position.x,
            drone.position.y,
            dock_center.z + crown_z - self.geometry.crown_height_m,
        )

    # -- mechanical truth --------------------------------------------------

    def _wall_interaction(
        self,
        now_s: float,
        drone: DroneBody,
        dock_center: Vec3,
        dock_velocity: Vec3,
        events: list[Event],
    ) -> None:
        """Constrain the aircraft to the bore, scoring rotor contact honestly.

        Two regimes, and the difference between them is the architecture's
        central hazard.  While only the crown cap is inside, the wall is a
        benign Ø260 mm containment — this is the wide acceptance the design
        is bought for.  Once the rotor plane crosses the rim the same wall
        becomes a strike boundary at ``prop_clearance_m``, and it is checked
        every step rather than only at the crossing, because an aircraft
        that drifts into the wall at depth has done exactly the same damage
        as one that entered badly.
        """

        g = self.geometry
        crown_rel = self._crown(drone) - dock_center
        lateral = crown_rel.lateral_norm()
        rotor_depth = crown_rel.z - g.rotor_below_crown_m
        if rotor_depth >= 0.0:
            allowed = self._wall_radius(rotor_depth) - g.prop_swept_radius_m
            strike = True
        else:
            allowed = self._wall_radius(crown_rel.z) - g.cap_radius_m
            strike = False

        if lateral <= allowed or lateral <= 0.0:
            return

        if strike and not self._prop_contact_latched:
            self._prop_contact_latched = True
            events.append(
                Event(
                    EventKind.PROP_FUNNEL_CONTACT,
                    now_s,
                    detail=f"rotor_wall lateral={lateral:.3f} depth={rotor_depth:.3f}",
                )
            )
        scale = allowed / lateral
        crown = dock_center + Vec3(crown_rel.x * scale, crown_rel.y * scale, crown_rel.z)
        drone.position = crown - Vec3(0.0, 0.0, g.crown_height_m)
        drone.velocity = dock_velocity.lateral().with_z(drone.velocity.z)

    def _retain(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Hold the aircraft between the closed bar and the crown pad.

        The lateral offset at the moment of capture is *preserved*, not
        centred away: an aircraft caught 40 mm off axis is carried 40 mm off
        axis.  That is the point of the architecture and it is also why the
        crown switch has to be able to see an off-centre seat.
        """

        g = self.geometry
        if self._carry_offset is None:
            crown_rel = self._crown(drone) - dock_center
            self._carry_offset = Vec3(
                crown_rel.x, crown_rel.y, g.seat_depth_m - g.latch_settle_m
            )
        crown = dock_center + self._carry_offset
        drone.position = crown - Vec3(0.0, 0.0, g.crown_height_m)
        drone.velocity = dock_velocity

    def _hold_at_seat(
        self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3
    ) -> None:
        """Seat contact for an armed aircraft against an open latch.

        The pad is a hard stop upward; downward relative motion stays free,
        because nothing holds the aircraft there.  Lateral velocity is left
        alone — unlike the baseline collet, a straight bore does not centre.
        """

        g = self.geometry
        crown_rel = self._crown(drone) - dock_center
        self._set_crown_z(drone, dock_center, min(crown_rel.z, g.seat_depth_m))
        vertical = drone.velocity.z
        if vertical - dock_velocity.z > 0.0:
            vertical = dock_velocity.z
        drone.velocity = drone.velocity.with_z(vertical)

    def _freefall(self, drone: DroneBody) -> None:
        """Let an unpowered, unretained aircraft fall out of the cup."""

        dt = self._dt_s
        drone.velocity = drone.velocity + Vec3(0.0, 0.0, -GRAVITY_M_S2 * dt)
        drone.position = drone.position + drone.velocity * dt

    def _update_latch_engagement(
        self, now_s: float, crown_z: float, belly_z: float, events: list[Event]
    ) -> bool:
        """Snapshot what the bar found when it swept across the bore.

        Taken once, on the rising edge, exactly as the baseline snapshots
        whether the fork is above or below the probe head.  Four outcomes,
        and the last has no baseline equivalent: this bar crosses the whole
        bore, so when its plane falls *between* the belly hoop and the crown
        it is sweeping through the airframe rather than under it.

        Engagement is read off the actuator's *position* alone, not off the
        position and the command together.  The baseline reads both, which
        is harmless there and wrong here: a bar that has bound under load
        stays physically under the aircraft after the controller commands it
        open, and the whole point of the loaded-release check is to catch
        exactly that state.
        """

        g = self.geometry
        engaged = self.servo.position > 0.5
        if engaged and not self._latch_was_engaged:
            self._latch_cam_lift = False
            if belly_z >= g.latch_face_m:
                # Clean sweep: the bar passes under the whole aircraft.
                self._latch_under_belly = True
                self._latch_block_crown_z = None
            elif belly_z >= g.latch_face_m - g.latch_cam_lift_m:
                # The leading ramp lifts a low aircraft into the pad.
                self._latch_under_belly = True
                self._latch_cam_lift = True
                self._latch_block_crown_z = None
            elif crown_z <= g.latch_face_m or self.probe_phase is ProbePhase.FREE:
                # The bar closed above the whole aircraft, or across an
                # empty cup.  Nothing is retained and nothing was struck; the
                # bar is now an obstruction the aircraft cannot climb past.
                self._latch_under_belly = False
                self._latch_block_crown_z = g.latch_face_m
            else:
                # The bar plane is inside the airframe.
                self._latch_under_belly = False
                self._latch_block_crown_z = crown_z
                events.append(
                    Event(
                        EventKind.PROP_FUNNEL_CONTACT,
                        now_s,
                        detail=(
                            f"latch_swept_into_airframe belly={belly_z:.3f} "
                            f"crown={crown_z:.3f}"
                        ),
                    )
                )
        if not engaged:
            self._latch_under_belly = False
            self._latch_cam_lift = False
            self._latch_block_crown_z = None
            self._carry_offset = None
        self._latch_was_engaged = engaged
        return engaged

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        drone: DroneBody | None,
        commands: DockCommands,
    ) -> DockStepResult:
        """Advance mechanics, switches, the real controller, and the actuator."""

        g = self.geometry
        events: list[Event] = []
        contact_speed: float | None = None
        seat_truth = False
        retained = False

        if drone is None:
            self.probe_phase = ProbePhase.FREE
            self._prev_crown_z = None
            self._latch_was_engaged = self.servo.position > 0.5
            self._latch_under_belly = False
            self._latch_cam_lift = False
            self._latch_block_crown_z = None
            self._carry_offset = None
            self._prop_contact_latched = False
        else:
            crown_rel = self._crown(drone) - dock_center
            lateral = crown_rel.lateral_norm()
            closing = (drone.velocity - dock_velocity).z
            belly_z = crown_rel.z - g.belly_below_crown_m
            latch_engaged = self._update_latch_engagement(
                now_s, crown_rel.z, belly_z, events
            )

            if self.probe_phase is ProbePhase.FREE:
                crossed_up = (
                    self._prev_crown_z is not None
                    and self._prev_crown_z < 0.0
                    and crown_rel.z >= 0.0
                )
                if crossed_up:
                    cap_allowed = self._wall_radius(0.0) - g.cap_radius_m
                    if lateral <= cap_allowed:
                        # The cap enters over a very wide window.  Note that
                        # this says nothing about whether the rotor disc,
                        # 40 mm behind it, will clear the rim.
                        self.probe_phase = ProbePhase.INSERTED
                        self._prop_contact_latched = False
                        contact_speed = closing
                        events.append(
                            Event(
                                EventKind.FUNNEL_INSERTION,
                                now_s,
                                detail=f"closing={closing:.3f} lateral={lateral:.3f}",
                            )
                        )
                    elif lateral <= g.rim_radius_m + g.prop_swept_radius_m:
                        # Climbing into the mouth ring: guards meet the flare.
                        events.append(
                            Event(
                                EventKind.PROP_FUNNEL_CONTACT,
                                now_s,
                                detail=f"mouth_ring lateral={lateral:.3f}",
                            )
                        )
                        drone.velocity = drone.velocity.with_z(
                            dock_velocity.z - max(0.05, 0.5 * closing)
                        )

            elif self.probe_phase is ProbePhase.INSERTED:
                if crown_rel.z < 0.0:
                    self.probe_phase = ProbePhase.FREE
                    self._prop_contact_latched = False
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="clear_of_cup")
                    )
                else:
                    self._wall_interaction(
                        now_s, drone, dock_center, dock_velocity, events
                    )
                    crown_rel = self._crown(drone) - dock_center
                    if latch_engaged and self._latch_under_belly:
                        self._retain(drone, dock_center, dock_velocity)
                        self.probe_phase = ProbePhase.SEATED
                        events.append(
                            Event(
                                EventKind.PROBE_SEATED,
                                now_s,
                                detail="latch_cam" if self._latch_cam_lift else "latch_closed",
                            )
                        )
                    elif latch_engaged:
                        # The bar is across the bore and is not under the
                        # aircraft: it blocks any further climb, either at
                        # its own face (it closed above the aircraft) or
                        # wherever it jammed into the airframe.
                        blocking_z = self._latch_block_crown_z
                        if blocking_z is not None and crown_rel.z > blocking_z:
                            self._set_crown_z(drone, dock_center, blocking_z)
                            if (drone.velocity - dock_velocity).z > 0.0:
                                drone.velocity = drone.velocity.with_z(dock_velocity.z)
                        if not drone.armed:
                            self._freefall(drone)
                    elif not drone.armed:
                        self._freefall(drone)
                    elif crown_rel.z >= g.seat_depth_m:
                        self.probe_phase = ProbePhase.SEATED
                        if closing > g.seat_impact_speed_m_s:
                            contact_speed = closing
                            events.append(
                                Event(
                                    EventKind.OVERSPEED_CONTACT,
                                    now_s,
                                    detail=f"deck_pad closing={closing:.3f}",
                                )
                            )
                        self._hold_at_seat(drone, dock_center, dock_velocity)
                        events.append(Event(EventKind.PROBE_SEATED, now_s))

            elif self.probe_phase is ProbePhase.SEATED:
                self._wall_interaction(now_s, drone, dock_center, dock_velocity, events)
                crown_rel = self._crown(drone) - dock_center
                if latch_engaged and self._latch_under_belly:
                    self._retain(drone, dock_center, dock_velocity)
                elif not drone.armed:
                    # Nothing passive holds this aircraft.  It falls.
                    self.probe_phase = ProbePhase.INSERTED
                    self._freefall(drone)
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="unretained_fall")
                    )
                else:
                    pulling_out = (
                        drone.velocity - dock_velocity
                    ).z < -g.unseat_speed_m_s
                    slid_out = crown_rel.z < g.seat_depth_m - g.unseat_drop_m
                    if pulling_out or slid_out:
                        self.probe_phase = ProbePhase.INSERTED
                        events.append(
                            Event(EventKind.PROBE_WITHDRAWN, now_s, detail="unseated")
                        )
                    else:
                        self._hold_at_seat(drone, dock_center, dock_velocity)

            crown_rel = self._crown(drone) - dock_center
            seat_truth = (
                self.probe_phase is ProbePhase.SEATED
                and crown_rel.z >= g.seat_depth_m - g.seat_hysteresis_m
            )
            retained = (
                self.servo.physically_closed
                and self._latch_under_belly
                and self.probe_phase is not ProbePhase.FREE
            )
            # Indication, not truth: the floating crown plate tips under an
            # off-centre load and its single centre switch stops making,
            # which is why the sensed envelope is narrower than the bore.
            crown_switch_input = (
                seat_truth and crown_rel.lateral_norm() <= g.crown_switch_radius_m
            )
            self._prev_crown_z = crown_rel.z

        if drone is None:
            crown_switch_input = False

        self.latch_closed_truth = self.servo.physically_closed
        reported_s1 = self.seat_switch.step(crown_switch_input)
        reported_s2 = self.keeper_switch.step(self.latch_closed_truth)

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
        # Release under load is the requirement this architecture must
        # answer, so the load is coupled to the actuator rather than left as
        # a static assertion: past the bind load the bar has tipped in its
        # bearing and the servo cannot move it either way.
        retained_load_n = 0.0
        if retained and drone is not None:
            retained_load_n = drone.params.mass_kg * GRAVITY_M_S2 + self.external_load_n
        self.latch_bound = (
            retained_load_n > 0.0 and self.pivot_moment_margin(retained_load_n) < 1.0
        )
        if not self.latch_bound:
            self.servo.step(self._dt_s, close_commanded)

        if output.capture_confirmed and not self._was_confirmed:
            if seat_truth and retained:
                events.append(Event(EventKind.CAPTURE_CONFIRMED, now_s))
            else:
                events.append(
                    Event(
                        EventKind.FALSE_CAPTURE_CONFIRMED,
                        now_s,
                        detail="controller confirmed without physical retention",
                    )
                )
        if self._was_confirmed and not output.capture_confirmed:
            events.append(Event(EventKind.RELEASED, now_s))
        self._was_confirmed = output.capture_confirmed

        # An unpowered aircraft depends entirely on the bar.  A bar that was
        # under the belly hoop and is no longer, with no release commanded,
        # has dropped its aircraft.  Edge-triggered, and only while the
        # aircraft is still the cup's to drop.
        if (
            drone is not None
            and not drone.armed
            and self.probe_phase is not ProbePhase.FREE
            and self._prev_retained
            and not retained
            and not commands.release_request
            and not commands.emergency_release
        ):
            events.append(Event(EventKind.DROPPED_AIRCRAFT, now_s))
        self._prev_retained = retained

        return DockStepResult(
            probe_phase=self.probe_phase,
            seat_truth=seat_truth,
            keeper_closed_truth=retained,
            reported_s1=reported_s1,
            reported_s2=reported_s2,
            controller=output,
            contact_closing_speed_m_s=contact_speed,
            events=tuple(events),
        )


@dataclass(frozen=True)
class DeepCupSpec:
    """Trade-study entry for the deep cup with a single over-top latch."""

    key: str = "deepcup"
    name: str = "Deep cup + single over-top latch bar"
    summary: str = (
        "A Ø300 mm bore, 140 mm deep cup swallows the aircraft's whole upper "
        "structure; a single latch bar pivots across the full bore under the "
        "belly hoop and traps it against a compliant crown pad.  Retention "
        "acceptance is ±72.5 mm of bore axis instead of ±2.0 mm of throat, "
        "and the price is that the guarded rotor disc is inside the cup."
    )
    part_count: int = 8
    actuator_count: int = 1
    sensed_channels: int = 2
    #: Geometry-derived engineering target; see the module docstring table.
    est_dock_mass_g: float = 454.0
    #: Crown cap plus belly hoop.  No mast, no head.
    est_probe_mass_g: float = 6.0
    known_weaknesses: tuple[str, ...] = (
        "Mass is disqualifying on the stated budget: 454 g dock-side against "
        "a 180 g allocation (2.5x) and 45% of the carrier's 1.0 kg rated "
        "payload, versus 75 g for the baseline dock.  Shrinking the bore to "
        "the funnel's Ø180 still lands near 280 g and cuts guarded-rotor "
        "clearance to 12.5 mm, which deletes the reason to build it.  "
        "Acceptance and mass are the same number.",
        "Every wall is a rotor wall.  The baseline keeps the rotor plane "
        "below the funnel lip on purpose; a deep cup cannot, so there is no "
        "benign contact surface anywhere in the mechanism.  Worse, the mouth "
        "swallows the crown cap 40 mm before the rotor plane reaches the "
        "rim, so a bad approach is committed before it is rejected — the "
        "funnel's 60 mm rim annulus at least rejects early.  Measured cost "
        "in the trade study's own wind axis: at 1.0 m/s mean wind the cup "
        "captures 0/12 and strikes 5/12, where the baseline captures 58% "
        "and strikes none.",
        "Unsafe on the P0-C launch departure with no fault injected, 2 seeds "
        "in 12.  The guidance stack's carrier-proximity reflex commands "
        "0.6 m/s laterally while the aircraft is still 60 mm inside the cup; "
        "the baseline gets the same command and survives it because the "
        "funnel taper physically clamps the probe on the way out, and a "
        "straight bore cannot.  The trade study's own harness runs only the "
        "bench-rig sil_p0b, which has no hull and no reflex, so it never "
        "sees this.",
        "Zero passive retention.  No collet, no throat, no friction: for the "
        "whole 0.45 s of latch travel the aircraft holds itself against the "
        "pad on thrust, and any sustained relative descent unseats it.  An "
        "unpowered aircraft with the bar open falls out of the cup.",
        "The sensed envelope is narrower than the mechanical one and is the "
        "binding number: the crown plate floats on three posts with one "
        "centre switch, so a seat is only *reported* within ±35 mm of the "
        "bore axis while the cup mechanically accepts ±72.5 mm.  Three "
        "switches at 120° would close the gap and cost two parts.",
        "Two sensed channels, no more independent than the baseline's.  S2 "
        "senses the bar at its closed stop and the bar spans the whole bore, "
        "so it closes identically on an occupied and an empty cup: FMECA "
        "FM-KP-03's empty-cup cut set transfers unchanged.  No third channel "
        "is faked here, so the claim is exactly as strong as Rev-A's — no "
        "single navigation fault confirms a capture on an empty cup, but a "
        "stuck-actuated crown switch plus a masked navigation error still "
        "does.",
        "The latch sweeps through the volume the aircraft occupies.  The "
        "baseline fork crosses a throat where only a Ø3 mm mast can be; this "
        "bar crosses the full bore under the airframe, and closing it more "
        "than 18 mm below the seat drives the ramp root into the belly hoop. "
        "Not reachable on honest sensing, reachable with a stuck crown "
        "switch and a navigation error, and the baseline has no equivalent.",
        "Release passes at flight loads and fails the bench screen.  A "
        "pivoting bar carries the load normal to its travel, so friction "
        "margin is ~10 at 5 N — but the pivot boss reacts the load up to "
        "half a span away, and the modelled moment margin is 2.4 with the "
        "far catch engaged and 1.2 while the bar is still travelling, "
        "against the programme's >=2.0 convention.  The unsupported window "
        "is exactly when the cam ramp is lifting an aircraft.",
        "A compliant pad sits in the sensing path.  It takes up the 2 mm of "
        "settle between deck and closed bar and keeps S1 made.  It is not in "
        "the retention path, but a pad that takes a set turns every good "
        "capture into S1 chatter and a fail-locked dock — and the deletion "
        "review has already refused to put an uncharacterised compliant part "
        "near this mechanism.",
        "Retention loads react through an aircraft-side belly hoop bonded "
        "around the airframe rather than through a mast into the frame.  "
        "Nobody has said whether a 37 g Crazyflie takes 5 N that way.",
        "The mechanism's acceptance is not the system's acceptance.  "
        "GuidanceParams.seat_confirm_m (15 mm) gates capture-enable and "
        "disarm off the navigation estimate, so the shared supervisor caps "
        "this candidate at the baseline's positioning requirement however "
        "wide the cup is.  Realising the benefit needs that constant raised, "
        "which weakens the finding-2 plausibility gate that stops a stuck "
        "seat switch disarming an aircraft in free air.  That trade is a "
        "software decision this module cannot make, and it is the single "
        "most important thing the deep cup revealed.",
    )

    def build(self, dt_s: float) -> DeepCupAssembly:
        return DeepCupAssembly(CupGeometry(), dt_s=dt_s)


SPEC = DeepCupSpec()


def mechanism_factory(config, dt_s: float) -> DeepCupAssembly:
    """Factory in the shape ``EpisodeConfig.mechanism_factory`` is called with.

    The engine passes ``(config, dt_s)``; :class:`MechanismSpec` takes only
    ``dt_s``.  Nothing in this candidate depends on the episode config, so
    the config is accepted and ignored rather than silently constraining the
    protocol.
    """

    return SPEC.build(dt_s)
