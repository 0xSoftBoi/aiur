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
    #: A bias that grows linearly instead of stepping.  The step version is
    #: always caught by the jump detector, so it can only ever demonstrate the
    #: defence working; this one is the case docs/digital-twin.md finding 3
    #: actually describes, and without it the twin cannot reproduce its own
    #: most serious residual.  ``magnitude`` is the ramp rate in m/s.
    POSE_BIAS_RAMP = "pose_bias_ramp"
    SEAT_SWITCH_STUCK_OPEN = "seat_switch_stuck_open"
    SEAT_SWITCH_STUCK_CLOSED = "seat_switch_stuck_closed"
    # The S2 channel was unfalsifiable until these existed: the injector only
    # ever reached the seat switch, so no campaign at any sample size could
    # produce a stuck keeper switch, and half of the S1 AND S2 interlock had
    # never been tested by the twin that certifies it.
    KEEPER_SWITCH_STUCK_OPEN = "keeper_switch_stuck_open"
    KEEPER_SWITCH_STUCK_CLOSED = "keeper_switch_stuck_closed"
    KEEPER_SERVO_JAM = "keeper_servo_jam"
    #: Controller brownout/reset.  The mechanism keeps its state; the
    #: controller loses its own and must re-derive it from the switches.
    CONTROLLER_RESET = "controller_reset"
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
        self._reset_done: set[int] = set()

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
        keeper_fault = SwitchFault.NONE
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
            elif spec.kind is FaultKind.POSE_BIAS_RAMP:
                grown = spec.magnitude * (t_s - spec.t_start_s)
                sensor.bias = Vec3(grown, 0.0, 0.0)
            elif spec.kind is FaultKind.SEAT_SWITCH_STUCK_OPEN:
                seat_fault = SwitchFault.STUCK_OPEN
            elif spec.kind is FaultKind.SEAT_SWITCH_STUCK_CLOSED:
                seat_fault = SwitchFault.STUCK_CLOSED
            elif spec.kind is FaultKind.KEEPER_SWITCH_STUCK_OPEN:
                keeper_fault = SwitchFault.STUCK_OPEN
            elif spec.kind is FaultKind.KEEPER_SWITCH_STUCK_CLOSED:
                keeper_fault = SwitchFault.STUCK_CLOSED
            elif spec.kind is FaultKind.KEEPER_SERVO_JAM:
                servo_jam = True
            elif spec.kind is FaultKind.CONTROLLER_RESET:
                # Edge-triggered: one reset per activation, not a controller
                # that is held in reset for the whole window.
                if index not in self._reset_done:
                    self._reset_done.add(index)
                    targets.dock.reset_controller()
            elif spec.kind is FaultKind.GUST:
                targets.air.gust_multiplier = spec.magnitude
            elif spec.kind is FaultKind.BATTERY_SAG:
                performance = spec.magnitude
                drain = 2.0

        targets.dock.seat_switch.fault = seat_fault
        targets.dock.keeper_switch.fault = keeper_fault
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
    # POSE_BIAS_RAMP is deliberately NOT in this menu.  It is not omitted to
    # keep gates green: the twin demonstrates that a slow enough ramp walks the
    # aircraft into the funnel rim, which is accepted residual SIL-005, and a
    # gate that samples an accepted residual a few percent of the time fails at
    # random without adding information.  The residual is characterised by the
    # dedicated nav-bias-ramp-sweep study instead, which is where its numbers
    # live.  Any change to that acceptance must revisit this line.
    FaultKind.SEAT_SWITCH_STUCK_OPEN,
    FaultKind.SEAT_SWITCH_STUCK_CLOSED,
    FaultKind.KEEPER_SWITCH_STUCK_OPEN,
    FaultKind.KEEPER_SWITCH_STUCK_CLOSED,
    FaultKind.KEEPER_SERVO_JAM,
    FaultKind.CONTROLLER_RESET,
    FaultKind.GUST,
    FaultKind.BATTERY_SAG,
)


#: Correlated fault pairs drawn from the common-mode analysis in
#: docs/common-mode.md.  Single-fault Monte Carlo cannot find a defect that
#: needs two things to be wrong at once, and treating S1 and S2 as independent
#: is quantitatively wrong: published common-cause fractions put beta at
#: roughly 0.01-0.10 with good prevention, and these two channels share part
#: design, lot, harness, supply, mounting, debounce code, and controller.
#: Each entry names the coupling that makes the pair plausible, so a reviewer
#: can argue with the physics rather than with a list.
CORRELATED_PAIRS: tuple[tuple[str, FaultKind, FaultKind], ...] = (
    (
        "shared harness/connector loses both switch channels",
        FaultKind.SEAT_SWITCH_STUCK_OPEN,
        FaultKind.KEEPER_SWITCH_STUCK_OPEN,
    ),
    (
        "same switch part design and lot fail the same way",
        FaultKind.SEAT_SWITCH_STUCK_CLOSED,
        FaultKind.KEEPER_SWITCH_STUCK_CLOSED,
    ),
    (
        "shared bracket displacement misreads the keeper and binds the servo",
        FaultKind.KEEPER_SWITCH_STUCK_CLOSED,
        FaultKind.KEEPER_SERVO_JAM,
    ),
    (
        "servo stall collapses the shared rail and resets the controller",
        FaultKind.KEEPER_SERVO_JAM,
        FaultKind.CONTROLLER_RESET,
    ),
    (
        "battery sag degrades both the aircraft and its pose solution",
        FaultKind.BATTERY_SAG,
        FaultKind.POSE_BIAS,
    ),
    (
        "gust excites the airframe and interrupts the optical pose reference",
        FaultKind.GUST,
        FaultKind.POSE_DROPOUT,
    ),
    (
        # Not a coupling: two independent faults.  It is on this list because
        # the safety case has no defence against the combination, which is a
        # different and worse property than being correlated.
        "seat switch stuck closed while a pose bias masks the position error",
        FaultKind.SEAT_SWITCH_STUCK_CLOSED,
        FaultKind.POSE_BIAS_RAMP,
    ),
)


def _spec_for(kind: FaultKind, rng: random.Random, start: float) -> FaultSpec:
    """Build one fault spec with a kind-appropriate window and magnitude."""

    if kind in (FaultKind.POSE_DROPOUT, FaultKind.DOCK_POSE_DROPOUT):
        return FaultSpec(kind, start, duration_s=rng.uniform(0.3, 2.5))
    if kind is FaultKind.POSE_BIAS:
        return FaultSpec(
            kind,
            start,
            duration_s=rng.uniform(2.0, 10.0),
            magnitude=rng.uniform(0.03, 0.15),
        )
    if kind is FaultKind.POSE_BIAS_RAMP:
        # Rates well under the jump detector's per-step threshold, so the ramp
        # is genuinely invisible to it rather than trivially caught.
        return FaultSpec(
            kind,
            start,
            duration_s=rng.uniform(10.0, 60.0),
            magnitude=rng.uniform(0.01, 0.20),
        )
    if kind is FaultKind.GUST:
        return FaultSpec(
            kind,
            start,
            duration_s=rng.uniform(1.0, 5.0),
            magnitude=rng.uniform(3.0, 8.0),
        )
    if kind is FaultKind.BATTERY_SAG:
        return FaultSpec(kind, start, magnitude=rng.uniform(0.6, 0.85))
    if kind is FaultKind.CONTROLLER_RESET:
        # Edge-triggered inside the injector; the window only has to be open
        # long enough to contain the restart.
        return FaultSpec(kind, start, duration_s=0.5)
    return FaultSpec(kind, start)


def sample_correlated_fault_plan(rng: random.Random) -> tuple[FaultSpec, ...]:
    """Draw one coupled fault pair from :data:`CORRELATED_PAIRS`.

    Both faults open close together in time, because a shared cause does not
    politely stagger its effects.  The offset is small and random rather than
    zero so the pair also exercises ordering.
    """

    _, first, second = rng.choice(CORRELATED_PAIRS)
    start = rng.uniform(2.0, 9.0)
    return (
        _spec_for(first, rng, start),
        _spec_for(second, rng, start + rng.uniform(0.0, 1.0)),
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
