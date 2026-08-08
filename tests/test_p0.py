import unittest

from aiur.p0 import (
    CarrierSpec,
    DockEnvelope,
    baseline_p0_budget,
    gross_static_lift_kg,
    payload_margin_kg,
    payload_mass_kg,
)


class CarrierP0Tests(unittest.TestCase):
    def test_ideal_buoyancy_is_not_payload_rating(self) -> None:
        carrier = CarrierSpec()
        ideal = gross_static_lift_kg(carrier.envelope_volume_m3)
        self.assertGreater(ideal, carrier.rated_payload_kg)

    def test_baseline_budget_keeps_large_payload_reserve(self) -> None:
        carrier = CarrierSpec()
        items = baseline_p0_budget()
        self.assertAlmostEqual(payload_mass_kg(items), 0.3994, places=4)
        self.assertAlmostEqual(payload_margin_kg(carrier, items), 0.6006, places=4)

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
