import unittest

from aiur.p0 import (
    CarrierSpec,
    DockEnvelope,
    aircraft_dead_weight_step_kg,
    baseline_p0_budget,
    gross_static_lift_kg,
    payload_margin_kg,
    payload_mass_kg,
    reserve_policy,
    selected_article,
)


class CarrierP0Tests(unittest.TestCase):
    def test_ideal_buoyancy_is_not_payload_rating(self) -> None:
        carrier = CarrierSpec()
        ideal = gross_static_lift_kg(carrier.envelope_volume_m3)
        self.assertGreater(ideal, carrier.rated_payload_kg)

    def test_baseline_budget_keeps_the_required_payload_reserve(self) -> None:
        carrier = CarrierSpec()
        items = baseline_p0_budget()
        self.assertAlmostEqual(payload_mass_kg(items), 0.4254, places=4)
        # 3.5 m article rated at 500 g: 74.6 g remains, against a required
        # reserve of 50 g (10% of rating) and a 47.7 g aircraft step.
        self.assertAlmostEqual(payload_margin_kg(carrier, items), 0.0746, places=4)
        self.assertGreaterEqual(
            payload_margin_kg(carrier, items),
            reserve_policy(items).required_reserve_kg(carrier.rated_payload_kg),
        )

    def test_reference_article_is_the_smallest_that_closes(self) -> None:
        # Guard against the budget quietly outgrowing the vehicle: if an
        # allocation grows, this is the test that says "buy the bigger one".
        chosen = selected_article()
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.length_m, CarrierSpec().envelope_length_m)

    def test_aircraft_step_counts_only_per_aircraft_items(self) -> None:
        # Airframe + guards, positioning deck, and probe: 37 + 2.7 + 8 g.
        self.assertAlmostEqual(aircraft_dead_weight_step_kg(), 0.0477, places=4)

    def test_capture_accepts_state_inside_envelope(self) -> None:
        dock = DockEnvelope()
        self.assertTrue(
            dock.can_attempt_capture(
                lateral_x_m=0.040,
                lateral_y_m=0.030,
                closing_speed_m_s=0.10,
            )
        )

    def test_capture_rejects_excess_lateral_error(self) -> None:
        dock = DockEnvelope()
        self.assertFalse(
            dock.can_attempt_capture(
                lateral_x_m=0.091,
                lateral_y_m=0.0,
                closing_speed_m_s=0.10,
            )
        )

    def test_capture_rejects_excess_closing_speed(self) -> None:
        dock = DockEnvelope()
        self.assertFalse(
            dock.can_attempt_capture(
                lateral_x_m=0.0,
                lateral_y_m=0.0,
                closing_speed_m_s=0.21,
            )
        )


if __name__ == "__main__":
    unittest.main()
