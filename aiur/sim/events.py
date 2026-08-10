"""Discrete event taxonomy shared by the digital-twin modules.

Events are the twin's primary evidence stream: campaign reducers count them
to produce the exact metrics the gate evaluator consumes.  Every safety-
relevant occurrence must surface here as an event, never only as a log line.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventKind(str, Enum):
    # Mechanical dock events.
    FUNNEL_INSERTION = "funnel_insertion"
    PROBE_SEATED = "probe_seated"
    PROBE_WITHDRAWN = "probe_withdrawn"
    CAPTURE_CONFIRMED = "capture_confirmed"
    FALSE_CAPTURE_CONFIRMED = "false_capture_confirmed"
    RELEASED = "released"
    DROPPED_AIRCRAFT = "dropped_aircraft"

    # Contact / strike events.
    PROP_FUNNEL_CONTACT = "prop_funnel_contact"
    OVERSPEED_CONTACT = "overspeed_contact"
    ENVELOPE_STRIKE = "envelope_strike"

    # Guidance / supervision events.
    ABORT = "abort"
    UNSAFE_DISARM = "unsafe_disarm"
    SAFE_LANDING = "safe_landing"

    # Multi-aircraft events.
    SEPARATION_VIOLATION = "separation_violation"
    SIMULTANEOUS_DOCK_APPROACH = "simultaneous_dock_approach"

    # Episode bookkeeping.
    FAULT_INJECTED = "fault_injected"
    EPISODE_TIMEOUT = "episode_timeout"


#: Event kinds that immediately classify an episode as unsafe.  A safe twin
#: campaign must produce zero of these regardless of injected faults.
UNSAFE_EVENT_KINDS = frozenset(
    {
        EventKind.PROP_FUNNEL_CONTACT,
        EventKind.OVERSPEED_CONTACT,
        EventKind.ENVELOPE_STRIKE,
        EventKind.UNSAFE_DISARM,
        EventKind.DROPPED_AIRCRAFT,
        EventKind.SEPARATION_VIOLATION,
        EventKind.SIMULTANEOUS_DOCK_APPROACH,
    }
)


@dataclass(frozen=True)
class Event:
    kind: EventKind
    t_s: float
    #: Which aircraft the event concerns; None for carrier/dock-level events.
    drone_index: int | None = None
    detail: str = ""
