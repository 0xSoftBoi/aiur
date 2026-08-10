import unittest

from aiur.adoption_loop import (
    ADOPTION_LOOP,
    AdoptionStage,
    TICKETS,
    TicketStatus,
    snapshot,
    ticket_by_id,
    validate_adoption_loop,
)


class AdoptionLoopTests(unittest.TestCase):
    def test_registry_is_structurally_valid(self) -> None:
        self.assertEqual(validate_adoption_loop(), ())

    def test_every_stage_is_reachable_and_has_an_exit(self) -> None:
        sources = {edge.source for edge in ADOPTION_LOOP}
        self.assertEqual(sources, set(AdoptionStage))

    def test_disposition_only_reachable_through_review(self) -> None:
        into_disposition = {
            edge.source
            for edge in ADOPTION_LOOP
            if edge.target is AdoptionStage.DISPOSITION
        }
        self.assertEqual(into_disposition, {AdoptionStage.REVIEW})

    def test_ticket_ids_are_unique_ordered_and_resolvable(self) -> None:
        ids = [ticket.ticket_id for ticket in TICKETS]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        for ticket_id in ids:
            self.assertEqual(ticket_by_id(ticket_id).ticket_id, ticket_id)

    def test_unknown_ticket_raises(self) -> None:
        with self.assertRaises(KeyError):
            ticket_by_id("ADOPT-999")

    def test_closed_tickets_require_evidence(self) -> None:
        for ticket in TICKETS:
            if ticket.status in (
                TicketStatus.CLOSED,
                TicketStatus.DELIVERED_AWAITING_HARDWARE,
            ):
                self.assertTrue(
                    ticket.evidence.strip(),
                    f"{ticket.ticket_id} closed without evidence",
                )

    def test_snapshot_reports_validity_and_counts(self) -> None:
        data = snapshot()
        self.assertTrue(data["valid"])
        self.assertEqual(sum(data["status_counts"].values()), len(TICKETS))


if __name__ == "__main__":
    unittest.main()
