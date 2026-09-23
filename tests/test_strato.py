import math
import unittest

from aiur.strato import (
    ATMOSPHERE_CEILING_M,
    PAYLOAD_PACKAGE_ALLOCATION_KG,
    REGULATORY_SINGLE_PACKAGE_KG,
    SEA_LEVEL_AIR_DENSITY_KG_M3,
    STRATOSPHERE_THRESHOLD_M,
    FloatPowerBudget,
    LiftingGas,
    Optic,
    SoundingBalloon,
    StratoP0Targets,
    baseline_strato_budget,
    canopy_area_for_landing_m2,
    envelope_volume_for_float_m3,
    float_altitude_m,
    gas_mass_kg,
    horizon_distance_m,
    horizon_ground_range_m,
    lifting_gas_density_kg_m3,
    net_lift_per_m3_kg,
    parachute_descent_rate_m_s,
    payload_allocation_margin_kg,
    payload_mass_kg,
    regulatory_exemption_check,
    sounding_battery_wh,
    standard_atmosphere,
    visible_cap_area_km2,
)


class StandardAtmosphereTests(unittest.TestCase):
    """Anchors against the 1976 U.S. Standard Atmosphere tables (geometric altitude)."""

    def assertWithin(self, value: float, expected: float, tolerance: float) -> None:
        self.assertLess(
            abs(value - expected) / expected,
            tolerance,
            f"{value} is not within {tolerance:.1%} of {expected}",
        )

    def test_sea_level_matches_the_standard(self) -> None:
        state = standard_atmosphere(0.0)
        self.assertAlmostEqual(state.temperature_k, 288.15)
        self.assertAlmostEqual(state.pressure_pa, 101325.0)
        self.assertWithin(state.density_kg_m3, 1.2250, 0.001)
        self.assertWithin(SEA_LEVEL_AIR_DENSITY_KG_M3, 1.2250, 0.001)

    def test_tabulated_points_through_the_stratosphere(self) -> None:
        # Table values for geometric altitude: 11 km, 20 km, 32 km.
        self.assertWithin(standard_atmosphere(11_000.0).pressure_pa, 22_700.0, 0.002)
        self.assertWithin(standard_atmosphere(20_000.0).pressure_pa, 5_529.3, 0.002)
        self.assertWithin(standard_atmosphere(20_000.0).density_kg_m3, 0.088910, 0.002)
        self.assertWithin(standard_atmosphere(32_000.0).pressure_pa, 889.06, 0.003)
        self.assertAlmostEqual(standard_atmosphere(20_000.0).temperature_k, 216.65, places=2)
        self.assertAlmostEqual(standard_atmosphere(20_000.0).temperature_c, -56.5, places=1)

    def test_density_and_pressure_fall_monotonically(self) -> None:
        previous = standard_atmosphere(0.0)
        for altitude in range(500, int(ATMOSPHERE_CEILING_M) + 1, 500):
            state = standard_atmosphere(float(altitude))
            self.assertLess(state.pressure_pa, previous.pressure_pa)
            self.assertLess(state.density_kg_m3, previous.density_kg_m3)
            previous = state

    def test_out_of_range_altitudes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            standard_atmosphere(-1.0)
        with self.assertRaises(ValueError):
            standard_atmosphere(ATMOSPHERE_CEILING_M + 1.0)


class LiftTests(unittest.TestCase):
    def test_helium_lift_fraction_is_the_molar_mass_ratio(self) -> None:
        # With gas at ambient temperature and pressure, lift per m^3 is
        # rho_air * (1 - M_gas / M_air) at every altitude.
        for altitude in (0.0, 10_000.0, 20_000.0, 30_000.0):
            state = standard_atmosphere(altitude)
            expected = state.density_kg_m3 * (1.0 - 0.0040026 / 0.0289644)
            self.assertAlmostEqual(net_lift_per_m3_kg(altitude), expected, places=9)

    def test_hydrogen_lifts_more_than_helium(self) -> None:
        self.assertGreater(
            net_lift_per_m3_kg(20_000.0, LiftingGas.HYDROGEN),
            net_lift_per_m3_kg(20_000.0, LiftingGas.HELIUM),
        )

    def test_superpressure_makes_the_gas_denser(self) -> None:
        self.assertGreater(
            lifting_gas_density_kg_m3(20_000.0, superpressure_pa=500.0),
            lifting_gas_density_kg_m3(20_000.0),
        )
        with self.assertRaises(ValueError):
            lifting_gas_density_kg_m3(20_000.0, superpressure_pa=-1.0)

    def test_float_solver_inverts_envelope_sizing(self) -> None:
        volume = envelope_volume_for_float_m3(3.0, STRATOSPHERE_THRESHOLD_M)
        self.assertAlmostEqual(float_altitude_m(volume, 3.0), STRATOSPHERE_THRESHOLD_M, places=1)
        # A 3 kg float article at 20 km needs an envelope in the tens of m^3,
        # not hundreds: the number a founder should have in their head.
        self.assertGreater(volume, 30.0)
        self.assertLess(volume, 50.0)
        self.assertGreater(gas_mass_kg(volume, STRATOSPHERE_THRESHOLD_M), 0.0)

    def test_float_solver_rejects_impossible_articles(self) -> None:
        with self.assertRaises(ValueError):
            float_altitude_m(1.0, 100.0)  # cannot leave the ground
        with self.assertRaises(ValueError):
            float_altitude_m(1_000_000.0, 0.001)  # never stops climbing


class SoundingBalloonTests(unittest.TestCase):
    def test_reference_article_bursts_with_margin_over_the_threshold(self) -> None:
        balloon = SoundingBalloon()
        burst = balloon.burst_altitude_m()
        self.assertGreaterEqual(burst, StratoP0Targets().min_burst_altitude_m)
        self.assertGreater(burst, STRATOSPHERE_THRESHOLD_M + 5_000.0)
        self.assertLess(burst, ATMOSPHERE_CEILING_M)

    def test_diameter_at_burst_is_the_burst_diameter(self) -> None:
        balloon = SoundingBalloon()
        self.assertAlmostEqual(
            balloon.diameter_at_m(balloon.burst_altitude_m()), balloon.burst_diameter_m, places=4
        )

    def test_launch_ascent_rate_is_in_the_sounding_band(self) -> None:
        rate = SoundingBalloon().ascent_rate_at_m_s(0.0)
        self.assertGreater(rate, 3.0)
        self.assertLess(rate, 7.0)

    def test_ascent_rate_creeps_up_with_altitude(self) -> None:
        balloon = SoundingBalloon()
        self.assertGreater(balloon.ascent_rate_at_m_s(25_000.0), balloon.ascent_rate_at_m_s(0.0))

    def test_time_to_burst_is_an_hour_and_a_half_class_flight(self) -> None:
        balloon = SoundingBalloon()
        minutes = balloon.time_to_burst_s() / 60.0
        self.assertGreater(minutes, 60.0)
        self.assertLess(minutes, 150.0)
        self.assertGreater(balloon.time_above_stratosphere_threshold_s(), 0.0)
        self.assertLess(balloon.time_above_stratosphere_threshold_s(), balloon.time_to_burst_s())

    def test_more_payload_lowers_the_burst_altitude(self) -> None:
        light = SoundingBalloon(payload_mass_kg=0.5)
        heavy = SoundingBalloon(payload_mass_kg=1.5)
        self.assertGreater(light.burst_altitude_m(), heavy.burst_altitude_m())

    def test_gas_mass_is_conserved_between_launch_and_burst(self) -> None:
        balloon = SoundingBalloon()
        burst = balloon.burst_altitude_m()
        volume_at_burst = math.pi * balloon.burst_diameter_m**3 / 6.0
        self.assertAlmostEqual(
            gas_mass_kg(volume_at_burst, burst), balloon.gas_mass_kg(), places=4
        )

    def test_invalid_balloons_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SoundingBalloon(free_lift_kg=0.0).launch_volume_m3()
        with self.assertRaises(ValueError):
            SoundingBalloon(burst_diameter_m=0.5).burst_altitude_m()


class DescentTests(unittest.TestCase):
    def test_canopy_sizing_inverts_descent_rate(self) -> None:
        mass = payload_mass_kg(baseline_strato_budget())
        area = canopy_area_for_landing_m2(mass, 5.0)
        self.assertAlmostEqual(parachute_descent_rate_m_s(mass, area), 5.0, places=6)

    def test_descent_is_faster_in_thin_air(self) -> None:
        self.assertGreater(
            parachute_descent_rate_m_s(0.85, 0.7, altitude_m=STRATOSPHERE_THRESHOLD_M),
            parachute_descent_rate_m_s(0.85, 0.7),
        )

    def test_invalid_descent_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parachute_descent_rate_m_s(0.0, 0.7)
        with self.assertRaises(ValueError):
            canopy_area_for_landing_m2(0.85, 0.0)


class ObservationGeometryTests(unittest.TestCase):
    def test_horizon_from_twenty_kilometres_is_five_hundred_kilometres(self) -> None:
        distance = horizon_distance_m(STRATOSPHERE_THRESHOLD_M)
        self.assertGreater(distance, 500_000.0)
        self.assertLess(distance, 510_000.0)
        self.assertLess(horizon_ground_range_m(STRATOSPHERE_THRESHOLD_M), distance)
        self.assertEqual(horizon_distance_m(0.0), 0.0)

    def test_visible_cap_grows_with_altitude(self) -> None:
        self.assertGreater(visible_cap_area_km2(30_000.0), visible_cap_area_km2(20_000.0))
        self.assertGreater(visible_cap_area_km2(STRATOSPHERE_THRESHOLD_M), 700_000.0)

    def test_reference_optic_meets_the_gsd_target(self) -> None:
        optic = Optic()
        gsd = optic.nadir_gsd_m(STRATOSPHERE_THRESHOLD_M)
        self.assertLessEqual(gsd, StratoP0Targets().max_nadir_gsd_m_at_threshold)
        self.assertAlmostEqual(gsd, 1.9375, places=3)
        # The stock Camera Module 3 optic fails the target: that is the point
        # of checking the optic before buying it.
        stock = Optic(focal_length_m=0.00474, pixel_pitch_m=1.4e-6)
        self.assertGreater(
            stock.nadir_gsd_m(STRATOSPHERE_THRESHOLD_M),
            StratoP0Targets().max_nadir_gsd_m_at_threshold,
        )
        self.assertAlmostEqual(optic.off_nadir_gsd_m(STRATOSPHERE_THRESHOLD_M, 0.0), gsd)
        self.assertGreater(optic.off_nadir_gsd_m(STRATOSPHERE_THRESHOLD_M, 45.0), gsd)

    def test_swath_and_slant_range(self) -> None:
        optic = Optic()
        across, along = optic.swath_m(STRATOSPHERE_THRESHOLD_M)
        self.assertAlmostEqual(across, 7_858.75, places=6)
        self.assertGreater(across, along)
        self.assertAlmostEqual(
            optic.slant_range_m(STRATOSPHERE_THRESHOLD_M, 60.0), 40_000.0, places=6
        )
        with self.assertRaises(ValueError):
            optic.slant_range_m(STRATOSPHERE_THRESHOLD_M, 90.0)


class PowerTests(unittest.TestCase):
    def test_sounding_battery_carries_margin_and_cold_derate(self) -> None:
        targets = StratoP0Targets()
        nominal = targets.payload_load_w * targets.sounding_flight_hours
        budget = sounding_battery_wh(targets.payload_load_w, targets.sounding_flight_hours)
        self.assertGreaterEqual(budget, 1.5 * nominal)
        self.assertAlmostEqual(budget, nominal * 1.5 / 0.6, places=6)
        with self.assertRaises(ValueError):
            sounding_battery_wh(4.0, 3.0, margin_factor=0.9)

    def test_float_reference_closes_and_a_dark_winter_does_not(self) -> None:
        self.assertTrue(FloatPowerBudget().closes())
        winter = FloatPowerBudget(sun_hours=6.0, night_hours=18.0, battery_wh=120.0)
        self.assertFalse(winter.closes())
        self.assertLess(winter.battery_margin(), 1.0)


class MassAndRegulatoryTests(unittest.TestCase):
    def test_baseline_allocation_leaves_margin_under_the_program_ceiling(self) -> None:
        items = baseline_strato_budget()
        self.assertAlmostEqual(payload_mass_kg(items), 0.85, places=4)
        self.assertAlmostEqual(payload_allocation_margin_kg(items), 0.15, places=4)
        self.assertLess(PAYLOAD_PACKAGE_ALLOCATION_KG, REGULATORY_SINGLE_PACKAGE_KG)

    def test_regulatory_ceiling_is_four_pounds(self) -> None:
        self.assertAlmostEqual(REGULATORY_SINGLE_PACKAGE_KG, 1.8144, places=4)

    def test_exemption_check_flags_each_limb(self) -> None:
        self.assertEqual(regulatory_exemption_check([0.85], separation_force_n=100.0), ())
        heavy = regulatory_exemption_check([2.0], separation_force_n=100.0)
        self.assertEqual(len(heavy), 1)
        self.assertIn("single-package ceiling", heavy[0])
        combined = regulatory_exemption_check([1.8, 1.8, 1.8, 1.8], separation_force_n=100.0)
        self.assertTrue(any("combined" in reason for reason in combined))
        strong_line = regulatory_exemption_check([0.85], separation_force_n=300.0)
        self.assertTrue(any("separates" in reason for reason in strong_line))
        with self.assertRaises(ValueError):
            regulatory_exemption_check([], separation_force_n=100.0)


if __name__ == "__main__":
    unittest.main()
