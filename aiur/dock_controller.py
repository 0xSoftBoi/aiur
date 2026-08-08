"""Hardware-agnostic latch controller for the CARRIER-P0 recovery dock.

P0-A exercises this logic on the bench with two independent physical inputs:
one switch for a seated probe and one for a closed positive keeper.  A capture
is never inferred from servo command alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DockState(str, Enum):
    OPEN = "open"
    LOCKING = "locking"
    CAPTURED = "captured"
    RELEASING = "releasing"
    FAULT_OPEN = "fault_open"
    FAULT_LOCKED = "fault_locked"


class KeeperCommand(str, Enum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class DockInputs:
    seat_switch: bool
    keeper_closed_switch: bool
    capture_enable: bool = False
    release_request: bool = False
    emergency_release: bool = False
    reset_fault: bool = False


@dataclass(frozen=True)
class DockOutput:
    state: DockState
    keeper_command: KeeperCommand
    capture_confirmed: bool
    fault_reason: str | None


class DockController:
    """Small deterministic state machine for the positive keeper.

    Pre-capture faults fail open so a vehicle can abort.  Once a capture has
    been confirmed, sensor disagreement fails locked so software does not drop
    a docked aircraft.  Emergency release always has authority to command open.

    An unexpectedly closed keeper is read against the seat rather than against
    history.  A controller that finds the keeper closed while it believes the
    dock is open cannot know whether it is looking at a stuck mechanism or at
    an aircraft it was holding before it restarted, and the two mistakes do
    not cost the same: assuming "empty" drops a docked aircraft, while
    assuming "holding" only asks an operator to command a release.  So the
    seat decides.  Closed keeper over an occupied seat fails locked; closed
    keeper over an empty seat fails open, because nothing can be dropped.
    This is the same fail-locked principle the running machine already applies
    after capture, extended to the case where the machine has lost its memory.
    Without it, a brownout during a docked cruise commands the keeper open.
    """

    def __init__(
        self,
        *,
        lock_timeout_s: float = 1.0,
        release_timeout_s: float = 1.0,
    ) -> None:
        if lock_timeout_s <= 0 or release_timeout_s <= 0:
            raise ValueError("timeouts must be positive")

        self.lock_timeout_s = lock_timeout_s
        self.release_timeout_s = release_timeout_s
        self.state = DockState.OPEN
        self.fault_reason: str | None = None
        self._entered_at_s: float | None = None
        self._last_now_s: float | None = None

    def _transition(
        self,
        state: DockState,
        now_s: float,
        fault_reason: str | None = None,
    ) -> None:
        self.state = state
        self._entered_at_s = now_s
        self.fault_reason = fault_reason

    def _elapsed(self, now_s: float) -> float:
        if self._entered_at_s is None:
            return 0.0
        return now_s - self._entered_at_s

    def _output(self, inputs: DockInputs) -> DockOutput:
        close_states = {
            DockState.LOCKING,
            DockState.CAPTURED,
            DockState.FAULT_LOCKED,
        }
        command = (
            KeeperCommand.CLOSE if self.state in close_states else KeeperCommand.OPEN
        )
        confirmed = (
            self.state is DockState.CAPTURED
            and inputs.seat_switch
            and inputs.keeper_closed_switch
        )
        return DockOutput(
            state=self.state,
            keeper_command=command,
            capture_confirmed=confirmed,
            fault_reason=self.fault_reason,
        )

    def step(self, now_s: float, inputs: DockInputs) -> DockOutput:
        """Advance the state machine using a monotonic timestamp."""

        if self._last_now_s is not None and now_s < self._last_now_s:
            raise ValueError("now_s must be monotonic")
        self._last_now_s = now_s

        # This is the only command that can intentionally open a fault-locked dock.
        if inputs.emergency_release:
            if self.state is not DockState.RELEASING:
                self._transition(DockState.RELEASING, now_s)
            return self._output(inputs)

        if self.state is DockState.OPEN:
            if inputs.keeper_closed_switch and inputs.seat_switch:
                # A closed keeper over an occupied seat may be holding an
                # aircraft, and this controller has no record of closing it —
                # the signature of a restart mid-cruise.  Hold.  The rule is
                # deliberately about what the switches say rather than about
                # how many steps have elapsed: a first-observation trigger is
                # defeated by a single stale sample or by any input that
                # short-circuits ahead of it, and a protection that can be
                # skipped by sample ordering is not a protection.
                self._transition(
                    DockState.FAULT_LOCKED,
                    now_s,
                    "keeper_closed_over_occupied_seat",
                )
            elif inputs.keeper_closed_switch:
                # Closed keeper, empty seat: nothing can be held, so this is a
                # genuine mechanism anomaly and failing open is still right.
                self._transition(
                    DockState.FAULT_OPEN,
                    now_s,
                    "keeper_reports_closed_while_open",
                )
            elif inputs.capture_enable and inputs.seat_switch:
                self._transition(DockState.LOCKING, now_s)

        elif self.state is DockState.LOCKING:
            if not inputs.capture_enable or not inputs.seat_switch:
                self._transition(
                    DockState.FAULT_OPEN,
                    now_s,
                    "probe_lost_during_lock",
                )
            elif inputs.keeper_closed_switch:
                self._transition(DockState.CAPTURED, now_s)
            elif self._elapsed(now_s) >= self.lock_timeout_s:
                self._transition(DockState.FAULT_OPEN, now_s, "lock_timeout")

        elif self.state is DockState.CAPTURED:
            if inputs.release_request:
                self._transition(DockState.RELEASING, now_s)
            elif not inputs.seat_switch or not inputs.keeper_closed_switch:
                self._transition(
                    DockState.FAULT_LOCKED,
                    now_s,
                    "capture_sensor_disagreement",
                )

        elif self.state is DockState.RELEASING:
            if (
                inputs.keeper_closed_switch
                and self._elapsed(now_s) >= self.release_timeout_s
            ):
                self._transition(DockState.FAULT_OPEN, now_s, "release_timeout")
            elif not inputs.keeper_closed_switch and not inputs.seat_switch:
                self._transition(DockState.OPEN, now_s)

        elif self.state is DockState.FAULT_OPEN:
            if (
                inputs.reset_fault
                and not inputs.seat_switch
                and not inputs.keeper_closed_switch
            ):
                self._transition(DockState.OPEN, now_s)

        elif self.state is DockState.FAULT_LOCKED:
            # A normal release request is intentionally ignored here.  The operator
            # must either recover trustworthy sensor state or use emergency release.
            if (
                inputs.reset_fault
                and inputs.seat_switch
                and inputs.keeper_closed_switch
            ):
                self._transition(DockState.CAPTURED, now_s)

        return self._output(inputs)

