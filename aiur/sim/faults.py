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


class FaultTrigger(str, Enum):
    """What decides when a fault opens."""

    #: ``t_start_s`` is the moment it fires.
    TIME = "time"
    #: ``t_start_s`` is the earliest it may fire; it actually fires on the
    #: first step at or after that time where the keeper is physically closed.
    #: Some faults are meaningless until the mechanism is doing something —
    #: restarting a controller whose dock is open is indistinguishable from
    #: not restarting it — and episode length varies by a factor of five
    #: across the gate scenarios, so no fixed clock time can serve them all.
    KEEPER_CLOSED = "keeper_closed"


@dataclass(frozen=True)
class FaultSpec:
    kind: FaultKind
    t_start_s: float
    duration_s: float = math.inf
    #: Kind-specific magnitude: bias meters, gust multiplier, or performance scale.
    magnitude: float = 1.0
    trigger: FaultTrigger = FaultTrigger.TIME

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
        self._armed_at: dict[int, float] = {}

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
            if spec.trigger is FaultTrigger.KEEPER_CLOSED:
                # Arm on the condition, then run for the declared duration
                # from the moment it armed.
                if index not in self._armed_at:
                    if t_s >= spec.t_start_s and targets.dock.servo.physically_closed:
                        self._armed_at[index] = t_s
                    else:
                        continue
                if t_s >= self._armed_at[index] + spec.duration_s:
                    continue
            elif not spec.active(t_s):
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


#: The approach/terminal phase of a nominal recovery.  Most faults have to
#: open here to reach the behaviour they test.
_EARLY_WINDOW = (2.0, 10.0)

def _start_window(kind: FaultKind) -> tuple[float, float]:
    """Earliest and latest a fault may open.

    Condition-triggered faults use this as an earliest-time floor rather than
    a firing time; see :class:`FaultTrigger`.
    """

    return _EARLY_WINDOW


def _shared_window(first: FaultKind, second: FaultKind) -> tuple[float, float]:
    """One window in which a coupled pair can both be meaningful.

    A shared cause does not fire its effects at unrelated times, so the pair
    gets one start.  Condition-triggered members treat it as a floor and wait
    for their condition, so the windows always intersect.
    """

    lo = max(_start_window(first)[0], _start_window(second)[0])
    hi = min(_start_window(first)[1], _start_window(second)[1])
    return (lo, hi) if lo < hi else _EARLY_WINDOW


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
        # Fires on the keeper actually closing rather than on a clock time, so
        # it lands where it tests something in every scenario.
        return FaultSpec(
            kind, start, duration_s=0.5, trigger=FaultTrigger.KEEPER_CLOSED
        )
    return FaultSpec(kind, start)


def sample_correlated_fault_plan(rng: random.Random) -> tuple[FaultSpec, ...]:
    """Draw one coupled fault pair from :data:`CORRELATED_PAIRS`.

    Both faults open close together in time, because a shared cause does not
    politely stagger its effects.  The offset is small and random rather than
    zero so the pair also exercises ordering.
    """

    _, first, second = rng.choice(CORRELATED_PAIRS)
    lo, hi = _shared_window(first, second)
    start = rng.uniform(lo, max(lo, hi - 1.0))
    return (
        _spec_for(first, rng, start),
        _spec_for(second, rng, start + rng.uniform(0.0, 1.0)),
    )


def sample_fault_plan(rng: random.Random) -> tuple[FaultSpec, ...]:
    """Draw one deterministic fault plan for a fault episode."""

    kind = rng.choice(_FAULT_MENU)
    start = rng.uniform(*_start_window(kind))
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
