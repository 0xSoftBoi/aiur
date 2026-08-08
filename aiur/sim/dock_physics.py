"""Mechanical capture model for the CARRIER-P0 recovery dock.

This module is the twin's hardware-in-the-loop seam: the funnel, probe,
collet, and keeper are simulated, but the latch logic is the **real**
``aiur.dock_controller.DockController`` — the same state machine that runs
on the bench article.  The controller sees only debounced switch outputs;
capture truth and reported capture are tracked separately so sensor faults
produce the same ambiguity classes the P0-A bench gate hunts.

Geometry values mirror the documented Rev-A engineering targets
(180 mm funnel entrance).  Contact and centering behavior are simplified
engineering surrogates pending calibration against bench measurements:

* A probe crossing the entrance plane inside the funnel radius inserts and
  is guided toward the axis by the taper.
* Crossing the plane in the rim annulus just outside the funnel radius is
  scored as propeller/funnel contact — the unsafe near-miss class.
* Crossing faster than the bounce threshold does not insert.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..dock_controller import DockController, DockInputs, DockOutput, KeeperCommand
from .bodies import DroneBody
from .events import Event, EventKind
from .sensors import KeeperServo, Switch
from .vec import Vec3


class ProbePhase(str, Enum):
    FREE = "free"
    INSERTED = "inserted"
    SEATED = "seated"


@dataclass(frozen=True)
class DockGeometry:
    """Rev-A derived geometry.  All values are engineering targets."""

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
    #: Relative descent speed that pulls the probe out of the open collet.
    collet_pullout_speed_m_s: float = 0.05
    #: If the probe head is within this distance of the seat when the keeper
    #: closes, the keeper cams under the head and completes the capture.
    #: Below it, a closing keeper blocks the throat instead.
    keeper_capture_window_m: float = 0.030


@dataclass(frozen=True)
class DockCommands:
    """Per-step commands from the guidance stack to the dock."""

    capture_enable: bool = False
    release_request: bool = False
    emergency_release: bool = False
    reset_fault: bool = False


@dataclass(frozen=True)
class DockStepResult:
    probe_phase: ProbePhase
    seat_truth: bool
    keeper_closed_truth: bool
    reported_s1: bool
    reported_s2: bool
    controller: DockOutput
    contact_closing_speed_m_s: float | None
    events: tuple[Event, ...]


class DockAssembly:
    """One funnel/collet/keeper dock serving one probe at a time."""

    def __init__(
        self,
        geometry: DockGeometry,
        *,
        dt_s: float,
        controller: DockController | None = None,
    ) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self.geometry = geometry
        self._dt_s = dt_s
        self.controller = controller if controller is not None else DockController()
        self.servo = KeeperServo()
        self.seat_switch = Switch(dt_s=dt_s)
        self.keeper_switch = Switch(dt_s=dt_s)
        self.probe_phase = ProbePhase.FREE
        self._was_confirmed = False
        self._prev_rel_z: float | None = None
        self._last_close_commanded = False
        self._keeper_was_engaged = False
        self._probe_above_keeper = False
        self._prev_keeper_truth = False

    def reset_controller(self) -> None:
        """Model a controller brownout: the logic restarts, the mechanism does not.

        Everything physical — probe position, servo travel, switch state —
        survives, because a power blip does not move hardware.  Only the
        controller's own state is lost, which is precisely the condition under
        which it must re-derive what it is holding from the switches alone.
        """

        self.controller = type(self.controller)(
            lock_timeout_s=self.controller.lock_timeout_s,
            release_timeout_s=self.controller.release_timeout_s,
        )
        self._was_confirmed = False

    # -- mechanical truth -------------------------------------------------

    def _probe_tip(self, drone: DroneBody) -> Vec3:
        return drone.position + Vec3(0.0, 0.0, self.geometry.probe_height_m)

    def _funnel_allowed_radius(self, depth_m: float) -> float:
        """Taper: allowed lateral offset shrinks linearly from entrance to seat."""

        g = self.geometry
        fraction = max(0.0, 1.0 - depth_m / g.seat_travel_m)
        return g.funnel_entrance_radius_m * fraction + 0.002

    def _constrain_to_funnel(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Apply the funnel wall constraint to an inserted probe."""

        rel = self._probe_tip(drone) - dock_center
        allowed = self._funnel_allowed_radius(rel.z)
        lateral = rel.lateral_norm()
        if lateral > allowed and lateral > 0.0:
            scale = allowed / lateral
            corrected = Vec3(rel.x * scale, rel.y * scale, rel.z)
            tip = dock_center + corrected
            drone.position = tip - Vec3(0.0, 0.0, self.geometry.probe_height_m)
            # The wall absorbs lateral relative velocity.
            drone.velocity = dock_velocity.lateral().with_z(drone.velocity.z)

    def _seat(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Pin a seated probe to the seat position."""

        g = self.geometry
        tip = dock_center + Vec3(0.0, 0.0, g.seat_travel_m)
        drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
        drone.velocity = dock_velocity

    def _hold_at_seat(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Seat contact for an armed aircraft against an open keeper.

        The collet centers the probe laterally and the seat is a hard stop
        upward, but downward relative motion stays free — otherwise a
        commanded departure could never build the pull-out velocity.
        """

        g = self.geometry
        rel_z = (self._probe_tip(drone) - dock_center).z
        clamped_z = min(rel_z, g.seat_travel_m)
        tip = dock_center + Vec3(0.0, 0.0, clamped_z)
        drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
        vertical = drone.velocity.z
        if vertical - dock_velocity.z > 0.0:
            vertical = dock_velocity.z
        drone.velocity = dock_velocity.lateral().with_z(vertical)

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        drone: DroneBody | None,
        commands: DockCommands,
    ) -> DockStepResult:
        """Advance mechanics, switches, the real controller, and the servo."""

        g = self.geometry
        events: list[Event] = []
        contact_speed: float | None = None
        seat_truth = False

        if drone is None:
            self.probe_phase = ProbePhase.FREE
            self._prev_rel_z = None
            self._keeper_was_engaged = False
            self._probe_above_keeper = False
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
                            # Restitution in the dock frame, not the world frame.
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
                blocking_z = g.seat_travel_m - g.keeper_capture_window_m
                keeper_engaged = (
                    self._last_close_commanded and self.servo.position > 0.5
                )
                if keeper_engaged and not self._keeper_was_engaged:
                    # Snapshot the geometry at the moment the keeper reaches
                    # the throat: above it, the keeper cams under the probe
                    # head; below it, the keeper is an obstruction.
                    self._probe_above_keeper = rel.z >= blocking_z
                self._keeper_was_engaged = keeper_engaged

                if rel.z < 0.0:
                    self.probe_phase = ProbePhase.FREE
                    self._keeper_was_engaged = False
                    self._probe_above_keeper = False
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="clear_of_funnel")
                    )
                elif keeper_engaged and self._probe_above_keeper:
                    self.probe_phase = ProbePhase.SEATED
                    self._keeper_was_engaged = False
                    self._probe_above_keeper = False
                    self._seat(drone, dock_center, dock_velocity)
                    events.append(
                        Event(EventKind.PROBE_SEATED, now_s, detail="keeper_cam")
                    )
                elif keeper_engaged:
                    # Blocked: the probe cannot rise past the closed keeper.
                    if rel.z > blocking_z:
                        tip = dock_center + Vec3(rel.x, rel.y, blocking_z)
                        drone.position = tip - Vec3(0.0, 0.0, g.probe_height_m)
                        if (drone.velocity - dock_velocity).z > 0.0:
                            drone.velocity = drone.velocity.with_z(dock_velocity.z)
                    self._constrain_to_funnel(drone, dock_center, dock_velocity)
                elif rel.z >= g.seat_travel_m:
                    self.probe_phase = ProbePhase.SEATED
                    self._keeper_was_engaged = False
                    self._probe_above_keeper = False
                    self._seat(drone, dock_center, dock_velocity)
                    events.append(Event(EventKind.PROBE_SEATED, now_s))
                else:
                    self._constrain_to_funnel(drone, dock_center, dock_velocity)

            elif self.probe_phase is ProbePhase.SEATED:
                pulling_out = (
                    drone.armed
                    and (drone.velocity - dock_velocity).z < -g.collet_pullout_speed_m_s
                )
                slid_out = (
                    drone.armed
                    and rel.z < g.seat_travel_m - g.keeper_capture_window_m
                )
                if (pulling_out or slid_out) and not self.servo.physically_closed:
                    self.probe_phase = ProbePhase.INSERTED
                    events.append(
                        Event(EventKind.PROBE_WITHDRAWN, now_s, detail="unseated")
                    )
                elif not drone.armed or self.servo.physically_closed:
                    self._seat(drone, dock_center, dock_velocity)
                else:
                    self._hold_at_seat(drone, dock_center, dock_velocity)

            rel = self._probe_tip(drone) - dock_center
            seat_truth = (
                self.probe_phase is ProbePhase.SEATED
                and rel.z >= g.seat_travel_m - g.seat_hysteresis_m
            )
            self._prev_rel_z = rel.z

        keeper_truth = self.servo.physically_closed
        reported_s1 = self.seat_switch.step(seat_truth)
        reported_s2 = self.keeper_switch.step(keeper_truth)

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
        self.servo.step(self._dt_s, close_commanded)
        self._last_close_commanded = close_commanded

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

        # A disarmed aircraft relies entirely on the mechanism: a keeper that
        # was physically closed on a seated probe and falls open with no
        # release commanded has dropped its aircraft.  Edge-triggered, and
        # only for an aircraft that is actually in the mechanism — a drone
        # that disarmed on the floor is not the dock's to drop.
        if (
            drone is not None
            and not drone.armed
            and self.probe_phase is ProbePhase.SEATED
            and self._prev_keeper_truth
            and not keeper_truth
            and not commands.release_request
            and not commands.emergency_release
        ):
            events.append(Event(EventKind.DROPPED_AIRCRAFT, now_s))
        self._prev_keeper_truth = keeper_truth

        return DockStepResult(
            probe_phase=self.probe_phase,
            seat_truth=seat_truth,
            keeper_closed_truth=keeper_truth,
            reported_s1=reported_s1,
            reported_s2=reported_s2,
            controller=output,
            contact_closing_speed_m_s=contact_speed,
            events=tuple(events),
        )
