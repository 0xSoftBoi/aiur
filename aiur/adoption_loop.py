"""Executable remediation loop for the engineering-practice adoption program.

The 2026-08-08 practice survey (docs/engineering-practice-survey.md) produced
an adoption table.  This module is that table as program state: every "yes"
row is a ticket, every ticket moves through a closed loop, and CI validates
the structure the same way it validates the CARRIER-P0 engineering loop —
a ticket never closes without named evidence.

The loop deliberately mirrors ``aiur.loop_graph``: plan and research feed
implementation, implementation must pass verification and an independent
review, and disposition either closes the ticket with evidence or sends it
back to the stage that can fix what failed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json


class AdoptionStage(str, Enum):
    TICKET = "ticket"
    RESEARCH = "research"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW = "review"
    DISPOSITION = "disposition"


@dataclass(frozen=True)
class AdoptionEdge:
    source: AdoptionStage
    target: AdoptionStage
    event: str


ADOPTION_LOOP: tuple[AdoptionEdge, ...] = (
    AdoptionEdge(AdoptionStage.TICKET, AdoptionStage.RESEARCH, "ticket_scoped"),
    AdoptionEdge(
        AdoptionStage.RESEARCH,
        AdoptionStage.IMPLEMENT,
        "implementation_basis_cited",
    ),
    AdoptionEdge(AdoptionStage.IMPLEMENT, AdoptionStage.VERIFY, "deliverables_exist"),
    AdoptionEdge(AdoptionStage.VERIFY, AdoptionStage.REVIEW, "tests_and_gates_green"),
    AdoptionEdge(AdoptionStage.REVIEW, AdoptionStage.DISPOSITION, "review_findings_resolved"),
    AdoptionEdge(AdoptionStage.DISPOSITION, AdoptionStage.TICKET, "closed_with_evidence"),
    AdoptionEdge(AdoptionStage.DISPOSITION, AdoptionStage.RESEARCH, "basis_was_wrong"),
    AdoptionEdge(AdoptionStage.DISPOSITION, AdoptionStage.IMPLEMENT, "implementation_rework"),
)


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    #: Software/document deliverables complete and verified; a physical step
    #: (fabrication, bench time) remains before the practice is fully live.
    DELIVERED_AWAITING_HARDWARE = "delivered_awaiting_hardware"
    CLOSED = "closed"


@dataclass(frozen=True)
class AdoptionTicket:
    ticket_id: str
    title: str
    source_practice: str
    deliverables: tuple[str, ...]
    verification: str
    status: TicketStatus = TicketStatus.OPEN
    #: Required for CLOSED / DELIVERED_AWAITING_HARDWARE: commit, test, or
    #: document that closes the ticket.  Empty means not closed.
    evidence: str = ""


TICKETS: tuple[AdoptionTicket, ...] = (
    AdoptionTicket(
        "ADOPT-001",
        "P0-A gate upgrade: loaded releases, force margins, derived life test",
        "AIAA S-114A / NASA-STD-5017B margin and life-test practice",
        (
            "loop_graph P0-A criteria: loaded emergency releases, keeper force margin at Vmin, derived cycle count with run-in trending",
            "hardware/dock/p0a-bench.md procedure update",
            "p0a_evidence reducer + CSV templates extended to the new metrics",
        ),
        "existing suite green; reducer round-trips the new template columns",
    ),
    AdoptionTicket(
        "ADOPT-002",
        "Bench fault-insertion unit and hardware fault quotas",
        "automotive HIL fault-insertion practice (ISO 26262)",
        (
            "fault-insertion relay board spec in the fabrication packet (S1/S2/servo lines)",
            "expected-safe-response table pairing every insertable fault with a requirement",
            "P0-A/P0-B gate criteria for hardware fault quotas",
        ),
        "gate evaluation tests cover the new criteria",
    ),
    AdoptionTicket(
        "ADOPT-003",
        "Hazard log with signed residual-risk acceptance",
        "MIL-STD-882E hazard tracking",
        (
            "aiur/hazards.py: severity x probability matrix, hazard registry, residual acceptance with name/date/scope",
            "seed hazard set (~10) including the double-fault residual",
            "CI test: no anonymous residual acceptance",
        ),
        "hazard validation test green; double-fault residual carries a signature",
    ),
    AdoptionTicket(
        "ADOPT-004",
        "Dock FMECA, fault tree, and common-mode analysis",
        "MIL-STD-1629A FMECA, NASA FTA practice, ARP4761 common-cause",
        (
            "docs/dock-fmeca.md: worksheet over the capture chain with severity/detection per mode",
            "fault trees for the two catastrophic top events",
            "common-mode table naming correlated fault pairs for the twin",
        ),
        "every FMECA mode maps to a twin fault kind, a hardware insertion, or a labeled gap",
    ),
    AdoptionTicket(
        "ADOPT-005",
        "Correlated-pair and power-fault injection in the twin",
        "common-cause findings + electrical brownout review",
        (
            "faults.py: correlated-pair plans drawn from the common-mode table",
            "controller-reset/brownout fault kind exercising latch-state loss during LOCKING",
            "campaign quota for correlated-pair episodes; safety zeros unchanged",
        ),
        "SIL gates still pass; new fault kinds produce zero unsafe outcomes",
    ),
    AdoptionTicket(
        "ADOPT-006",
        "Machine-checked requirement closure matrix",
        "NASA VCRM / automotive DVP&R",
        (
            "aiur/requirements.py: registry of shalls with method (T/A/I/D), stage, criterion link, status, closing evidence",
            "seeded from the P0 docs' existing requirements",
            "CI test: method-less or silently-open requirements fail",
        ),
        "closure matrix validation green; snapshot lists open vs closed",
    ),
    AdoptionTicket(
        "ADOPT-007",
        "SIL report credibility and uncertainty block + TLYF exception ledgers",
        "NASA-STD-7009B credibility factors, TOR-2010(8591)-6 test-like-you-fly",
        (
            "campaign reports carry a credibility block (validation level, factor notes) and Wilson intervals on rates",
            "docs/tlyf-exceptions.md: per-article ledger of what bench/rig/tether do not reproduce",
        ),
        "campaign JSON contains the block; intervals verified against a known case",
    ),
    AdoptionTicket(
        "ADOPT-008",
        "Dock electrical evidence packet",
        "WCCA/derating practice, switch contact wetting current, workmanship standards",
        (
            "derating + worst-case table for servo, switches, harness",
            "gold-contact switch BOM line with sized pull-ups",
            "harness workmanship rules and rail-transient scope procedure in the fabrication packet",
        ),
        "tables cite datasheet values or are labeled targets; BOM updated",
    ),
    AdoptionTicket(
        "ADOPT-009",
        "Battery standard operating procedure",
        "UN 38.3 / IEC 62133-2 practice",
        (
            "docs/battery-sop.md: charge, storage, transport, retirement, containment rules",
            "pack identity and cycle count added to the promotion-contract telemetry list",
        ),
        "SOP exists; promotion contract updated",
    ),
    AdoptionTicket(
        "ADOPT-010",
        "Kill-path independence verification",
        "range-safety practice (RCC 319 philosophy at indoor scale)",
        (
            "kill-path requirements: dedicated power, function with autonomy computer off",
            "pre-session end-to-end check and injected-fault exercise in the test procedure",
            "P0-B/P0-C gate criteria for kill-path verification",
        ),
        "gate criteria present; procedure steps enumerated",
    ),
    AdoptionTicket(
        "ADOPT-011",
        "Test cards, TRR checklist, and abort phraseology",
        "flight-test practice (FTSC), NPR 7123.1 TRR",
        (
            "docs/test-cards.md: per-run card template with mini hazard analysis and stop rules",
            "one-page TRR checklist gating every hardware campaign",
            "named abort caller and phraseology distinct from kill",
        ),
        "templates exist and are referenced from the gate ladder docs",
    ),
    AdoptionTicket(
        "ADOPT-012",
        "Capture-chain tolerance stack, as-built records, golden article",
        "ASME Y14.5 stack practice + consumer-hw golden samples",
        (
            "executable worst-case/RSS stack of the capture chain at FDM tolerances",
            "as-built measurement template per printed article",
            "golden-article freeze rule on P0-A pass; parametric CAD variant fan for competing geometries",
        ),
        "stack test green and shows positive worst-case clearance or a labeled redesign flag",
    ),
    AdoptionTicket(
        "ADOPT-013",
        "Dock deletion review before Rev-B",
        "iterative-hardware practice (delete the part)",
        (
            "decision memo: does the collet earn its place beside a positive keeper; can one discriminating sensor replace S2 plus the Rev-B addition",
            "explicit keep/delete/merge disposition per part with rationale",
        ),
        "memo exists with a disposition for every questioned part",
    ),
)


@dataclass(frozen=True)
class AdoptionVerdict:
    valid: bool
    errors: tuple[str, ...]


def ticket_by_id(ticket_id: str) -> AdoptionTicket:
    for ticket in TICKETS:
        if ticket.ticket_id == ticket_id:
            return ticket
    raise KeyError(f"unknown adoption ticket: {ticket_id}")


def validate_adoption_loop() -> tuple[str, ...]:
    """Structural errors in the remediation loop and ticket registry."""

    errors: list[str] = []

    adjacency: dict[AdoptionStage, set[AdoptionStage]] = {s: set() for s in AdoptionStage}
    for edge in ADOPTION_LOOP:
        adjacency[edge.source].add(edge.target)
    seen: set[AdoptionStage] = set()
    pending = [AdoptionStage.TICKET]
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(adjacency[node] - seen)
    if seen != set(AdoptionStage):
        missing = sorted(s.value for s in set(AdoptionStage) - seen)
        errors.append(f"stages unreachable from ticket: {', '.join(missing)}")

    outgoing = {stage: 0 for stage in AdoptionStage}
    for edge in ADOPTION_LOOP:
        outgoing[edge.source] += 1
    dead = sorted(s.value for s, n in outgoing.items() if n == 0)
    if dead:
        errors.append(f"stages with no outgoing path: {', '.join(dead)}")

    # A ticket may only close through disposition after verify + review; the
    # structural proxy is that no edge shortcuts implement -> disposition.
    for edge in ADOPTION_LOOP:
        if edge.target is AdoptionStage.DISPOSITION and edge.source not in (
            AdoptionStage.REVIEW,
        ):
            errors.append(
                f"disposition has an unsafe shortcut from {edge.source.value}"
            )

    ids = [t.ticket_id for t in TICKETS]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        errors.append("ticket ids must be unique and ordered")
    for ticket in TICKETS:
        if not ticket.deliverables:
            errors.append(f"{ticket.ticket_id} has no deliverables")
        if (
            ticket.status
            in (TicketStatus.CLOSED, TicketStatus.DELIVERED_AWAITING_HARDWARE)
            and not ticket.evidence.strip()
        ):
            errors.append(f"{ticket.ticket_id} is closed without evidence")

    return tuple(errors)


def snapshot() -> dict[str, object]:
    errors = validate_adoption_loop()
    counts: dict[str, int] = {}
    for ticket in TICKETS:
        counts[ticket.status.value] = counts.get(ticket.status.value, 0) + 1
    return {
        "valid": not errors,
        "errors": list(errors),
        "status_counts": counts,
        "edges": [
            {"source": e.source.value, "target": e.target.value, "event": e.event}
            for e in ADOPTION_LOOP
        ],
        "tickets": [asdict(t) for t in TICKETS],
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
