"""Fault injection for the CARRIER-P0 digital twin.

Faults are first-class scenario inputs, not test-only hacks: every SIL gate
requires a quota of fault episodes, and the safety criterion is that **no
injected fault ever produces an unsafe event** — aborting a recovery is an
acceptable outcome, striking the envelope or dropping an aircraft is not.

Each fault has an activation window.  Latching hardware faults (stuck
switches, jammed servos) use an infinite duration by default because real
mechanisms do not heal mid-flight.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import random

from .bodies import DroneBody
from .disturbances import AirModel
from .dock_physics import DockAssembly
from .events import Event, EventKind
from .sensors import PoseSensor, SwitchFault
from .vec import Vec3


class FaultKind(str, Enum):
    POSE_DROPOUT = "pose_dropout"
    DOCK_POSE_DROPOUT = "dock_pose_dropout"
    POSE_BIAS = "pose_bias"
    SEAT_SWITCH_STUCK_OPEN = "seat_switch_stuck_open"
    SEAT_SWITCH_STUCK_CLOSED = "seat_switch_stuck_closed"
    KEEPER_SERVO_JAM = "keeper_servo_jam"
    GUST = "gust"
    BATTERY_SAG = "battery_sag"


@dataclass(frozen=True)
class FaultSpec:
    kind: FaultKind
    t_start_s: float
    duration_s: float = math.inf
    #: Kind-specific magnitude: bias meters, gust multiplier, or performance scale.
    magnitude: float = 1.0

    def active(self, t_s: float) -> bool:
        return self.t_start_s <= t_s < self.t_start_s + self.duration_s


@dataclass
class FaultTargets:
    """Handles the injector needs to reach into the simulated article."""

    drone_sensors: list[PoseSensor]
    dock_sensor: PoseSensor
    dock: DockAssembly
    air: AirModel
    drones: list[DroneBody]
    #: Index of the aircraft the plan stresses (the active mission aircraft).
    target_drone: int = 0


class FaultInjector:
    """Applies a fault plan to the article once per simulation step."""

    def __init__(self, plan: tuple[FaultSpec, ...], targets: FaultTargets) -> None:
        if plan and not 0 <= targets.target_drone < len(targets.drones):
            raise ValueError(
                f"fault target drone {targets.target_drone} does not exist"
            )
        self._plan = plan
        self._targets = targets
        self._announced: set[int] = set()

    @property
    def plan(self) -> tuple[FaultSpec, ...]:
        return self._plan

    def step(self, t_s: float) -> tuple[Event, ...]:
        if not self._plan:
            return ()
        targets = self._targets
        events: list[Event] = []
        drone = targets.drones[targets.target_drone]
        sensor = targets.drone_sensors[targets.target_drone]

        # Reset transient channels, then apply every active fault.
        sensor.forced_outage = False
        sensor.bias = Vec3()
        targets.dock_sensor.forced_outage = False
        targets.air.gust_multiplier = 1.0
        seat_fault = SwitchFault.NONE
        servo_jam = False
        performance = 1.0
        drain = 1.0

        for index, spec in enumerate(self._plan):
            if not spec.active(t_s):
                continue
            if index not in self._announced:
                self._announced.add(index)
                events.append(
                    Event(EventKind.FAULT_INJECTED, t_s, detail=spec.kind.value)
                )

            if spec.kind is FaultKind.POSE_DROPOUT:
                sensor.forced_outage = True
            elif spec.kind is FaultKind.DOCK_POSE_DROPOUT:
                targets.dock_sensor.forced_outage = True
            elif spec.kind is FaultKind.POSE_BIAS:
                sensor.bias = Vec3(spec.magnitude, 0.0, 0.0)
            elif spec.kind is FaultKind.SEAT_SWITCH_STUCK_OPEN:
                seat_fault = SwitchFault.STUCK_OPEN
            elif spec.kind is FaultKind.SEAT_SWITCH_STUCK_CLOSED:
                seat_fault = SwitchFault.STUCK_CLOSED
            elif spec.kind is FaultKind.KEEPER_SERVO_JAM:
                servo_jam = True
            elif spec.kind is FaultKind.GUST:
                targets.air.gust_multiplier = spec.magnitude
            elif spec.kind is FaultKind.BATTERY_SAG:
                performance = spec.magnitude
                drain = 2.0

        targets.dock.seat_switch.fault = seat_fault
        targets.dock.servo.jammed = servo_jam
        drone.performance_scale = performance
        drone.drain_multiplier = drain
        return tuple(events)


#: The catalogue sampled for fault episodes.  Windows are chosen to open
#: inside the approach/terminal timeframe of a nominal recovery (~20 s for
#: SIL-P0-B) so a "fault episode" actually experiences its fault — the
#: campaign reducer additionally counts only episodes whose fault activated.
_FAULT_MENU: tuple[FaultKind, ...] = (
    FaultKind.POSE_DROPOUT,
    FaultKind.DOCK_POSE_DROPOUT,
    FaultKind.POSE_BIAS,
    FaultKind.SEAT_SWITCH_STUCK_OPEN,
    FaultKind.SEAT_SWITCH_STUCK_CLOSED,
    FaultKind.KEEPER_SERVO_JAM,
    FaultKind.GUST,
    FaultKind.BATTERY_SAG,
)


def sample_fault_plan(rng: random.Random) -> tuple[FaultSpec, ...]:
    """Draw one deterministic fault plan for a fault episode."""

    kind = rng.choice(_FAULT_MENU)
    # The fastest nominal recovery (SIL-P0-B) completes around 19 s, so a
    # window opening by 10 s is guaranteed to activate in every scenario.
    start = rng.uniform(2.0, 10.0)
    if kind in (FaultKind.POSE_DROPOUT, FaultKind.DOCK_POSE_DROPOUT):
        return (FaultSpec(kind, start, duration_s=rng.uniform(0.3, 2.5)),)
    if kind is FaultKind.POSE_BIAS:
        return (
            FaultSpec(
                kind,
                start,
                duration_s=rng.uniform(2.0, 10.0),
                magnitude=rng.uniform(0.03, 0.15),
            ),
        )
    if kind is FaultKind.GUST:
        return (
            FaultSpec(
                kind,
                start,
                duration_s=rng.uniform(1.0, 5.0),
                magnitude=rng.uniform(3.0, 8.0),
            ),
        )
    if kind is FaultKind.BATTERY_SAG:
        return (FaultSpec(kind, start, magnitude=rng.uniform(0.6, 0.85)),)
    # Latching mechanism faults.
    return (FaultSpec(kind, start),)
