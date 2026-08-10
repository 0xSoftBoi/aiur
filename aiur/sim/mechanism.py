"""Capture-mechanism interface for the CARRIER-P0 digital twin.

The twin was written around one mechanism — funnel, probe, sliding fork
keeper — with its geometry baked into the engine.  That is fine for
verifying the article being built and useless for asking whether it is the
right article.  A twin that can only simulate the design you already chose
cannot tell you to choose differently.

This module is the seam.  A mechanism owns everything between "the probe is
somewhere near the dock" and "capture is confirmed and the aircraft may
disarm": the acceptance envelope, the retention physics, the sensed truth,
and the release path.  Everything else in the twin — vehicles, sensing,
disturbances, guidance, faults, gates — is architecture-agnostic and is
reused unchanged across candidates.

The point is comparison under the *unknowns*, not under nominal conditions.
Every candidate captures cleanly when the probe arrives centred and the
sensors are honest.  They differ in how they degrade as the seated lateral
offset grows past the ±0.35 mm nobody has measured, as positioning noise
rises, and as faults land — and that is what decides which one is worth
printing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .bodies import DroneBody
from .dock_physics import DockCommands, DockStepResult, ProbePhase
from .vec import Vec3


@runtime_checkable
class CaptureMechanism(Protocol):
    """What the engine requires of any capture architecture.

    Deliberately small.  Anything a mechanism needs beyond this — jaws,
    detents, latches, magnets — is its own business, so long as it reports
    the same truth-versus-indication distinction the safety case rests on:
    what physically happened, and separately what the sensors said.
    """

    #: Where the probe is relative to the mechanism, in the common taxonomy.
    probe_phase: ProbePhase

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        drone: DroneBody | None,
        commands: DockCommands,
    ) -> DockStepResult:
        """Advance one fixed timestep and report truth plus indication."""

    def reset_controller(self) -> None:
        """Model a controller brownout: logic restarts, mechanism does not."""

    def seed_seated(self, drone: DroneBody, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Place a probe at the seat for scenarios that start captured.

        Exists so the engine's pre-roll does not reach into mechanism
        internals.  A mechanism that cannot be seeded this way cannot host
        the launch-then-recover scenarios, which is itself a finding.
        """


@runtime_checkable
class MechanismSpec(Protocol):
    """Describes a candidate for the design study, beyond its physics.

    Capture rate alone ranks nothing: a mechanism that captures perfectly
    with four actuators and eleven parts is not obviously better than one
    that captures well with none.  These are the terms a trade study needs
    and simulation cannot supply.
    """

    #: Short stable key used in reports and filenames.
    key: str
    name: str
    #: One line on how it works.
    summary: str
    #: Parts a technician must fabricate or buy, beyond the probe.
    part_count: int
    #: Powered actuators.  Zero means retention survives a dead battery.
    actuator_count: int
    #: Independent sensed channels feeding capture truth.
    sensed_channels: int
    #: Estimated carried mass, dock side.  An engineering target.
    est_dock_mass_g: float
    #: Estimated carried mass, aircraft side.  An engineering target.
    est_probe_mass_g: float
    #: Honest statement of what this architecture is bad at.
    known_weaknesses: tuple[str, ...]

    def build(self, dt_s: float): ...
