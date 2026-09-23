import dataclasses
import unittest

from aiur.s0_readiness import (
    ITEMS,
    ClosedBy,
    ItemStatus,
    ReadinessItem,
    item_by_id,
    ladder,
    next_software_items,
    snapshot,
    software_done,
    topological_order,
    validate_readiness,
)


def _with(item_id: str, **changes: object) -> tuple[ReadinessItem, ...]:
    return tuple(
        dataclasses.replace(item, **changes) if item.id == item_id else item for item in ITEMS
    )


class ReadinessGraphTests(unittest.TestCase):
    def test_register_validates_clean(self) -> None:
        self.assertEqual(validate_readiness(), ())

    def test_order_respects_dependencies(self) -> None:
        order = topological_order()
        position = {item_id: index for index, item_id in enumerate(order)}
        for item in ITEMS:
            for dep in item.depends_on:
                self.assertLess(position[dep], position[item.id], f"{dep} must precede {item.id}")

    def test_hardware_items_cannot_be_closed_by_a_commit(self) -> None:
        errors = validate_readiness(_with("HW-S0A", status=ItemStatus.CLOSED))
        self.assertTrue(any("cannot supply" in error for error in errors))

    def test_closed_items_need_existing_evidence(self) -> None:
        errors = validate_readiness(_with("SW-MODEL", evidence=("aiur/does_not_exist.py",)))
        self.assertTrue(any("does not exist" in error for error in errors))

    def test_open_items_need_a_next_action(self) -> None:
        errors = validate_readiness(_with("HW-S0C", next_action=" "))
        self.assertIn("HW-S0C is open without a next action", errors)

    def test_cycles_are_caught(self) -> None:
        errors = validate_readiness(_with("SW-MODEL", depends_on=("SW-GATES",)))
        self.assertTrue(any("cycle" in error for error in errors))

    def test_flight_gate_waits_on_every_software_item_it_needs(self) -> None:
        deps = item_by_id("HW-S0C").depends_on
        self.assertIn("SW-PREDICT", deps)
        self.assertIn("SW-GROUND-MERGE", deps)
        self.assertIn("HW-S0B", deps)

    def test_next_items_are_open_software_with_closed_dependencies(self) -> None:
        for item in next_software_items():
            self.assertIs(item.status, ItemStatus.OPEN)
            self.assertIs(item.closed_by, ClosedBy.SOFTWARE)
            for dep in item.depends_on:
                self.assertIs(item_by_id(dep).status, ItemStatus.CLOSED)

    def test_software_done_tracks_open_software_items(self) -> None:
        open_software = [
            i for i in ITEMS if i.status is ItemStatus.OPEN and i.closed_by is ClosedBy.SOFTWARE
        ]
        self.assertEqual(software_done(), not open_software)
        all_closed = tuple(
            dataclasses.replace(i, status=ItemStatus.CLOSED) if i.closed_by is ClosedBy.SOFTWARE else i
            for i in ITEMS
        )
        self.assertTrue(software_done(all_closed))
        self.assertFalse(software_done(_with("SW-MODEL", status=ItemStatus.OPEN)))

    def test_ladder_and_snapshot(self) -> None:
        text = ladder()
        self.assertIn("[x] SW-MODEL", text)
        self.assertIn("HW-S0C", text)
        data = snapshot()
        self.assertTrue(data["valid"])
        self.assertEqual(len(data["items"]), len(ITEMS))
        self.assertEqual(data["software_done"], software_done())


if __name__ == "__main__":
    unittest.main()
