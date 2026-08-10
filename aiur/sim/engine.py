"""Deterministic episode engine for the CARRIER-P0 digital twin.

One episode is one scripted mission (launch, sortie, recover, land) executed
at a fixed 50 Hz step under seeded process noise.  The engine owns truth:
vehicle states, mechanical dock truth, envelope geometry, and separation.
The guidance stack sees sensor measurements and reported dock feedback, so
every sensing pathology the twin models actually reaches the software under
test.  One deliberate exception: battery state is fed as truth (no gauge
model), so the battery-reserve supervisor is exercised with perfect
knowledge.

Determinism contract: identical (config, seed) pairs must produce identical
results, byte for byte.  All randomness flows from per-subsystem
``random.Random`` children of the episode seed; the engine never touches
wall-clock time.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import random

from ..dock_controller import DockState
from .bodies import (
    CarrierBody,
    CarrierParams,
    DroneBody,
    DroneParams,
    KinematicRig,
    RigParams,
)
from .disturbances import AirModel, AirModelParams, INDOOR_CALM
from .dock_physics import DockAssembly, DockCommands, DockGeometry, DockStepResult
from .events import Event, EventKind, UNSAFE_EVENT_KINDS
from .faults import FaultInjector, FaultSpec, FaultTargets
from .guidance import (
    FleetSequencer,
    GuidanceParams,
    GuidancePhase,
    MissionMode,
    TerminalGuidance,
)
from .sensors import LIGHTHOUSE_GRADE, PoseSensor, PoseSensorParams
from .vec import Vec3, ZERO


class Platform(str, Enum):
    RIG = "rig"
    CARRIER = "carrier"


class ScriptAction(str, Enum):
    LAUNCH_SORTIE = "launch_sortie"
    RECOVER = "recover"
    GROUND_LAND = "ground_land"


@dataclass(frozen=True)
class ScriptStep:
    drone_index: int
    action: ScriptAction


@dataclass(frozen=True)
class DroneSetup:
    start_position: Vec3
    mission: MissionMode = MissionMode.RECOVER_ONLY
    station: Vec3 = ZERO
    sortie_waypoints: tuple[Vec3, ...] = ()
    start_captured: bool = False


@dataclass(frozen=True)
class EpisodeConfig:
    platform: Platform
    platform_position: Vec3
    drones: tuple[DroneSetup, ...]
    script: tuple[ScriptStep, ...]
    dt_s: float = 0.02
    max_duration_s: float = 180.0
    air: AirModelParams = INDOOR_CALM
    drone_sensor: PoseSensorParams = LIGHTHOUSE_GRADE
    dock_sensor: PoseSensorParams = LIGHTHOUSE_GRADE
    drone_params: DroneParams = DroneParams()
    carrier_params: CarrierParams = CarrierParams()
    rig_params: RigParams = RigParams()
    dock_geometry: DockGeometry = DockGeometry()
    guidance: GuidanceParams = GuidanceParams()
    fault_plan: tuple[FaultSpec, ...] = ()
    fault_target_drone: int = 0
    min_separation_m: float = 0.30
    tethered: bool = True
    record_telemetry: bool = False


class EpisodeOutcome(str, Enum):
    SUCCESS = "success"
    SAFE_INCOMPLETE = "safe_incomplete"
    TIMEOUT = "timeout"
    UNSAFE = "unsafe"


@dataclass(frozen=True)
class TelemetryRow:
    """Promotion-contract-aligned time-synchronized recovery telemetry."""

    t_s: float
    drone_index: int
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    estimate_valid: bool
    rel_vx_m_s: float
    rel_vy_m_s: float
    rel_vz_m_s: float
    cmd_vx_m_s: float
    cmd_vy_m_s: float
    cmd_vz_m_s: float
    seat_switch_s1: bool
    keeper_command: str
    keeper_switch_s2: bool
    armed: bool
    guidance_phase: str
    dock_state: str
    last_abort_reason: str


@dataclass(frozen=True)
class EpisodeResult:
    outcome: EpisodeOutcome
    script_completed: bool
    duration_s: float
    captures: int
    aborts: int
    max_contact_closing_m_s: float | None
    fault_injected: bool
    events: tuple[Event, ...]
    telemetry: tuple[TelemetryRow, ...] = ()

    @property
    def unsafe_events(self) -> tuple[Event, ...]:
        return tuple(e for e in self.events if e.kind in UNSAFE_EVENT_KINDS)


def _child_rng(master: random.Random) -> random.Random:
    """Draw one child RNG from the episode master.

    Draw-order contract: children are consumed in construction order (air,
    rig if present, dock sensor, then drone sensors by index).  The order is
    append-only — inserting a draw before existing subsystems re-seeds
    everything after it and silently changes every campaign result.
    """

    return random.Random(master.getrandbits(64))


class _EpisodeRunner:
    def __init__(self, config: EpisodeConfig, seed: int) -> None:
        self.config = config
        master = random.Random(seed)
        self.air = AirModel(config.air, _child_rng(master))

        if config.platform is Platform.RIG:
            self.platform: CarrierBody | KinematicRig = KinematicRig(
                config.rig_params, config.platform_position, _child_rng(master)
            )
        else:
            self.platform = CarrierBody(
                config.carrier_params,
                config.platform_position,
                tether_anchor=Vec3(
                    config.platform_position.x, config.platform_position.y, 0.0
                )
                if config.tethered
                else None,
            )

        self.dock = DockAssembly(config.dock_geometry, dt_s=config.dt_s)
        self.dock_sensor = PoseSensor(config.dock_sensor, _child_rng(master), config.dt_s)

        # On a carrier platform the guidance stack gets the hull geometry it
        # needs for the proximity-evasion reflex; a bench rig has no hull.
        guidance_params = config.guidance
        if config.platform is Platform.CARRIER:
            guidance_params = replace(
                guidance_params,
                carrier_center_from_dock_m=-config.carrier_params.dock_offset_m,
                envelope_semi_axes_m=config.carrier_params.envelope_semi_axes_m,
            )

        self.drones: list[DroneBody] = []
        self.drone_sensors: list[PoseSensor] = []
        self.guidances: list[TerminalGuidance] = []
        for index, setup in enumerate(config.drones):
            drone = DroneBody(config.drone_params, setup.start_position)
            self.drones.append(drone)
            self.drone_sensors.append(
                PoseSensor(config.drone_sensor, _child_rng(master), config.dt_s)
            )
            self.guidances.append(
                TerminalGuidance(
                    guidance_params,
                    drone_index=index,
                    probe_height_m=config.dock_geometry.probe_height_m,
                    seat_travel_m=config.dock_geometry.seat_travel_m,
                    mission=setup.mission,
                    station=setup.station,
                    sortie_waypoints=setup.sortie_waypoints,
                )
            )

        self.sequencer = FleetSequencer(self.guidances)
        self.injector = FaultInjector(
            config.fault_plan,
            FaultTargets(
                drone_sensors=self.drone_sensors,
                dock_sensor=self.dock_sensor,
                dock=self.dock,
                air=self.air,
                drones=self.drones,
                target_drone=config.fault_target_drone,
            ),
        )

        self.events: list[Event] = []
        self.telemetry: list[TelemetryRow] = []
        self._last_meas: list = []
        self.engaged: int | None = None
        self.last_dock_result: DockStepResult | None = None
        self.max_contact_closing: float | None = None
        self.captures = 0
        self.aborts = 0
        self.script_index = 0
        self.safe_failed = False
        self._strike_latched: set[int] = set()
        self._separation_latched: set[tuple[int, int]] = set()
        self._simultaneous_latched = False
        self._last_abort_reason = ""

        for index, setup in enumerate(config.drones):
            if setup.start_captured:
                self._preroll_capture(index)

    # -- setup helpers ----------------------------------------------------

    def _preroll_capture(self, index: int) -> None:
        """Walk the real controller through a legitimate pre-episode capture."""

        from .dock_physics import ProbePhase

        geometry = self.config.dock_geometry
        dock_center = self.platform.dock_center()
        drone = self.drones[index]
        drone.position = dock_center + Vec3(
            0.0, 0.0, geometry.seat_travel_m - geometry.probe_height_m
        )
        drone.velocity = self.platform.dock_velocity()
        self.dock.probe_phase = ProbePhase.SEATED
        self.engaged = index

        t = -5.0
        while t < -self.config.dt_s / 2.0:
            result = self.dock.step(
                t,
                dock_center,
                self.platform.dock_velocity(),
                drone,
                DockCommands(capture_enable=True),
            )
            self.last_dock_result = result
            t += self.config.dt_s
        if self.last_dock_result is None or not self.last_dock_result.controller.capture_confirmed:
            raise RuntimeError("pre-roll capture failed; dock geometry inconsistent")

    # -- per-step logic ---------------------------------------------------

    def _current_step(self) -> ScriptStep | None:
        if self.script_index < len(self.config.script):
            return self.config.script[self.script_index]
        return None

    def _manage_script(self, now_s: float) -> None:
        step = self._current_step()
        if step is None:
            return
        guidance = self.guidances[step.drone_index]
        if step.action is ScriptAction.RECOVER:
            self.sequencer.authorize(step.drone_index)
        elif step.action is ScriptAction.GROUND_LAND:
            # Only redirect an aircraft that is in a free-flight phase; a
            # vehicle mid-capture or attached to the dock must finish or
            # abort through its own supervisor, never be yanked to LAND.
            if guidance.phase in (
                GuidancePhase.STATION_HOLD,
                GuidancePhase.SORTIE,
                GuidancePhase.DEPART,
                GuidancePhase.RENDEZVOUS,
                GuidancePhase.ALIGN,
                GuidancePhase.ABORT_DESCEND,
            ):
                guidance.phase = GuidancePhase.LAND

    def _advance_script(self, now_s: float) -> None:
        step = self._current_step()
        if step is None:
            return
        guidance = self.guidances[step.drone_index]
        done = False
        if step.action is ScriptAction.LAUNCH_SORTIE:
            done = guidance.phase is GuidancePhase.STATION_HOLD
        elif step.action is ScriptAction.RECOVER:
            if guidance.phase is GuidancePhase.CAPTURED:
                done = True
            elif guidance.phase in (GuidancePhase.LANDED, GuidancePhase.STATION_HOLD) and (
                guidance.dock_untrusted or guidance.phase is GuidancePhase.LANDED
            ):
                # The aircraft disposed of itself safely without capturing.
                self.safe_failed = True
                done = True
        elif step.action is ScriptAction.GROUND_LAND:
            done = guidance.phase is GuidancePhase.LANDED
        if done:
            self.sequencer.release(step.drone_index)
            self.script_index += 1

    def _select_engaged(self) -> None:
        from .dock_physics import ProbePhase

        if self.dock.probe_phase is not ProbePhase.FREE:
            return
        # A disarmed aircraft clear of the mechanism (probe FREE) is no
        # longer the dock's concern — e.g. it safe-landed on the floor.
        if self.engaged is not None and not self.drones[self.engaged].armed:
            self.engaged = None
        step = self._current_step()
        if step is not None and step.action in (
            ScriptAction.LAUNCH_SORTIE,
            ScriptAction.RECOVER,
        ):
            self.engaged = step.drone_index

    def _check_truth_invariants(self, now_s: float) -> None:
        config = self.config
        floor_z = config.guidance.floor_z_m

        # Envelope strikes (carrier platform only; a bench rig has no hull).
        for index, drone in enumerate(self.drones):
            if index in self._strike_latched:
                continue
            # Semi-axis inflation is not an exact Minkowski sum with the
            # drone sphere; pad by the worst-case flank gap (~7 mm for
            # these axes) so the surrogate is conservative.
            distance = self.platform.envelope_normalized_distance(
                drone.position, inflate_m=config.drone_params.body_radius_m + 0.008
            )
            if distance < 1.0:
                self._strike_latched.add(index)
                self.events.append(Event(EventKind.ENVELOPE_STRIKE, now_s, index))

        # Pairwise separation between flying aircraft.
        for i in range(len(self.drones)):
            for j in range(i + 1, len(self.drones)):
                if (i, j) in self._separation_latched:
                    continue
                a, b = self.drones[i], self.drones[j]
                flying = (
                    a.armed
                    and b.armed
                    and a.position.z > floor_z + 0.15
                    and b.position.z > floor_z + 0.15
                )
                if flying and (a.position - b.position).norm() < config.min_separation_m:
                    self._separation_latched.add((i, j))
                    self.events.append(
                        Event(
                            EventKind.SEPARATION_VIOLATION,
                            now_s,
                            detail=f"pair=({i},{j})",
                        )
                    )

        if not self._simultaneous_latched:
            audit = self.sequencer.audit(now_s)
            if audit:
                self._simultaneous_latched = True
                self.events.extend(audit)

    def _apply_disarm(self, index: int, phase: GuidancePhase, now_s: float) -> None:
        drone = self.drones[index]
        if not drone.armed:
            return
        if phase is GuidancePhase.CAPTURED:
            result = self.last_dock_result
            mechanically_held = (
                index == self.engaged
                and result is not None
                and result.seat_truth
                and result.keeper_closed_truth
            )
            if not mechanically_held:
                self.events.append(
                    Event(
                        EventKind.UNSAFE_DISARM,
                        now_s,
                        index,
                        "disarm without mechanical capture",
                    )
                )
        elif phase is GuidancePhase.LANDED:
            if drone.position.z > self.config.guidance.floor_z_m + 0.15:
                self.events.append(
                    Event(EventKind.UNSAFE_DISARM, now_s, index, "disarm in free air")
                )
        drone.disarm()

    # -- main loop --------------------------------------------------------

    def run(self) -> EpisodeResult:
        config = self.config
        dt = config.dt_s
        step_count = int(round(config.max_duration_s / dt))
        telemetry_stride = max(1, int(round(0.1 / dt)))
        now_s = 0.0
        unsafe = False

        for step_index in range(step_count):
            now_s = step_index * dt

            # Faults are injected before any subsystem consumes its fault
            # channel this step, including the air model's gust multiplier.
            self.events.extend(self.injector.step(now_s))
            air_velocity = self.air.step(dt)
            self.platform.step(dt, air_velocity)
            dock_center = self.platform.dock_center()
            dock_velocity = self.platform.dock_velocity()

            self._manage_script(now_s)
            self._select_engaged()

            dock_meas = self.dock_sensor.step(dock_center, dock_velocity)
            decisions = []
            self._last_meas = []
            for index, guidance in enumerate(self.guidances):
                drone = self.drones[index]
                meas = self.drone_sensors[index].step(drone.position, drone.velocity)
                self._last_meas.append(meas)
                feedback = self.last_dock_result if index == self.engaged else None
                decision = guidance.step(
                    now_s, dt, meas, dock_meas, feedback, drone.remaining_flight_s
                )
                for event in decision.events:
                    if event.kind is EventKind.ABORT:
                        self.aborts += 1
                        self._last_abort_reason = event.detail
                self.events.extend(decision.events)
                decisions.append(decision)

            for index, decision in enumerate(decisions):
                drone = self.drones[index]
                if drone.armed:
                    drone.step(dt, decision.velocity_cmd, air_velocity)

            engaged_drone = self.drones[self.engaged] if self.engaged is not None else None
            commands = (
                decisions[self.engaged].dock_commands
                if self.engaged is not None
                else DockCommands()
            )
            result = self.dock.step(now_s, dock_center, dock_velocity, engaged_drone, commands)
            self.last_dock_result = result
            self.events.extend(result.events)
            for event in result.events:
                if event.kind is EventKind.CAPTURE_CONFIRMED:
                    self.captures += 1
            if result.contact_closing_speed_m_s is not None:
                previous = self.max_contact_closing
                self.max_contact_closing = (
                    result.contact_closing_speed_m_s
                    if previous is None
                    else max(previous, result.contact_closing_speed_m_s)
                )

            for index, decision in enumerate(decisions):
                if decision.disarm:
                    self._apply_disarm(index, decision.phase, now_s)

            self._check_truth_invariants(now_s)
            self._advance_script(now_s)

            if config.record_telemetry and step_index % telemetry_stride == 0:
                self._record_telemetry(now_s, dock_center, dock_velocity, decisions)

            if any(event.kind in UNSAFE_EVENT_KINDS for event in self.events):
                unsafe = True
                break
            if self.script_index >= len(config.script):
                break
        else:
            self.events.append(Event(EventKind.EPISODE_TIMEOUT, now_s))

        script_completed = self.script_index >= len(config.script) and not self.safe_failed
        if unsafe:
            outcome = EpisodeOutcome.UNSAFE
        elif script_completed:
            outcome = EpisodeOutcome.SUCCESS
        elif self.safe_failed:
            outcome = EpisodeOutcome.SAFE_INCOMPLETE
        else:
            outcome = EpisodeOutcome.TIMEOUT

        return EpisodeResult(
            outcome=outcome,
            script_completed=script_completed,
            duration_s=now_s,
            captures=self.captures,
            aborts=self.aborts,
            max_contact_closing_m_s=self.max_contact_closing,
            fault_injected=bool(self.injector.plan),
            events=tuple(self.events),
            telemetry=tuple(self.telemetry),
        )

    def _record_telemetry(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        decisions: list,
    ) -> None:
        step = self._current_step()
        if step is not None:
            index = step.drone_index
        else:
            index = self.engaged if self.engaged is not None else 0
        drone = self.drones[index]
        geometry = self.config.dock_geometry
        probe_tip = drone.position + Vec3(0.0, 0.0, geometry.probe_height_m)
        rel = dock_center - probe_tip
        rel_v = dock_velocity - drone.velocity
        decision = decisions[index]
        result = self.last_dock_result
        self.telemetry.append(
            TelemetryRow(
                t_s=round(now_s, 3),
                drone_index=index,
                rel_x_m=rel.x,
                rel_y_m=rel.y,
                rel_z_m=rel.z,
                estimate_valid=(
                    self._last_meas[index].valid if index < len(self._last_meas) else False
                ),
                rel_vx_m_s=rel_v.x,
                rel_vy_m_s=rel_v.y,
                rel_vz_m_s=rel_v.z,
                cmd_vx_m_s=decision.velocity_cmd.x,
                cmd_vy_m_s=decision.velocity_cmd.y,
                cmd_vz_m_s=decision.velocity_cmd.z,
                seat_switch_s1=result.reported_s1 if result else False,
                keeper_command=result.controller.keeper_command.value if result else "open",
                keeper_switch_s2=result.reported_s2 if result else False,
                armed=drone.armed,
                guidance_phase=decision.phase.value,
                dock_state=result.controller.state.value if result else DockState.OPEN.value,
                last_abort_reason=self._last_abort_reason,
            )
        )


def run_episode(config: EpisodeConfig, seed: int) -> EpisodeResult:
    """Run one deterministic episode of the given scenario configuration."""

    return _EpisodeRunner(config, seed).run()
