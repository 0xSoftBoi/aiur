"""Envelope sizing: gas physics, hull geometry, catalog, and selection."""

import math
import unittest

from aiur.envelope import (
    DEFAULT_PROFILE,
    FILL_PURITY,
    P0_ARTICLE,
    P0_SEMI_MINOR_M,
    PU_50_UM,
    PU_100_UM,
    RC_ZEPPELIN_INDOOR,
    CarrierMassModel,
    Envelope,
    ReservePolicy,
    air_density_kg_m3,
    article_by_length,
    helium_density_kg_m3,
    length_sweep,
    net_lift_kg_per_m3,
    p0_envelope,
    select_article,
    spheroid_semi_minor_m,
)
from aiur.p0 import (
    CarrierSpec,
    baseline_p0_budget,
    payload_mass_kg,
    reserve_policy,
    selected_article,
)


class GasPhysicsTests(unittest.TestCase):
    def test_densities_match_the_standard_tables(self) -> None:
        # ISA sea level air at 15 C; helium's tabulated 0.1664 kg/m3 is at 20 C.
        self.assertAlmostEqual(air_density_kg_m3(15.0), 1.225, places=2)
        self.assertAlmostEqual(helium_density_kg_m3(20.0), 0.1664, places=3)

    def test_pure_helium_lifts_about_a_kilogram_per_cubic_metre(self) -> None:
        self.assertAlmostEqual(net_lift_kg_per_m3(15.0), 1.056, places=2)
        self.assertAlmostEqual(net_lift_kg_per_m3(20.0), 1.038, places=2)
        # Warmer air is thinner, so a room lifts less than ISA.
        self.assertLess(net_lift_kg_per_m3(20.0), net_lift_kg_per_m3(15.0))

    def test_impurity_scales_lift_linearly(self) -> None:
        pure = net_lift_kg_per_m3(20.0)
        self.assertAlmostEqual(net_lift_kg_per_m3(20.0, purity=0.5), 0.5 * pure)
        self.assertAlmostEqual(net_lift_kg_per_m3(20.0, purity=FILL_PURITY),
                               FILL_PURITY * pure)

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            net_lift_kg_per_m3(purity=0.0)
        with self.assertRaises(ValueError):
            net_lift_kg_per_m3(purity=1.5)
        with self.assertRaises(ValueError):
            air_density_kg_m3(-300.0)
        with self.assertRaises(ValueError):
            air_density_kg_m3(20.0, pressure_pa=0.0)


class HullProfileTests(unittest.TestCase):
    def test_profile_closes_at_nose_and_holds_max_section(self) -> None:
        p = DEFAULT_PROFILE
        self.assertEqual(p.radius_frac(0.0), 0.0)
        self.assertEqual(p.radius_frac(1.0), 0.0)
        self.assertAlmostEqual(p.radius_frac(p.max_section_frac), 1.0)
        # The tail tapers to the tail-cone fitting radius, not to a point.
        self.assertAlmostEqual(p.radius_frac(1.0 - 1e-9), p.tail_radius_frac, places=5)

    def test_prismatic_coefficient_is_in_the_airship_band(self) -> None:
        cp = DEFAULT_PROFILE.prismatic_coefficient()
        self.assertGreater(cp, 0.60)
        self.assertLess(cp, 0.70)

    def test_wetted_area_is_bounded_by_the_cylinder(self) -> None:
        # S / (2 pi R L) is below 1 for any closed body inside its cylinder,
        # and above the prismatic coefficient's square root region for one
        # that actually encloses that volume.
        for fineness in (2.0, 3.0, 5.0):
            coefficient = DEFAULT_PROFILE.wetted_area_coefficient(fineness)
            self.assertLess(coefficient, 1.0)
            self.assertGreater(coefficient, 0.5)


class EnvelopeTests(unittest.TestCase):
    def test_from_volume_round_trips(self) -> None:
        envelope = Envelope.from_volume(3.5, 4.0)
        self.assertAlmostEqual(envelope.volume_m3, 4.0, places=9)
        self.assertAlmostEqual(envelope.fineness_ratio, 3.5 / envelope.diameter_m)

    def test_surface_area_scales_with_length_squared(self) -> None:
        small = Envelope.from_fineness(2.0, 3.0)
        large = Envelope.from_fineness(4.0, 3.0)
        self.assertAlmostEqual(large.surface_area_m2 / small.surface_area_m2, 4.0, places=6)
        self.assertAlmostEqual(large.volume_m3 / small.volume_m3, 8.0, places=6)

    def test_spheroid_matches_the_previous_twin_constants(self) -> None:
        # The 4.5 m / 5.5 m3 article was carried in the twin as a
        # 2.25 x 0.764 x 0.764 m spheroid; the derivation must reproduce it.
        self.assertAlmostEqual(spheroid_semi_minor_m(4.5, 5.5), 0.764, places=3)

    def test_invalid_geometry_raises(self) -> None:
        with self.assertRaises(ValueError):
            Envelope(0.0, 1.0)
        with self.assertRaises(ValueError):
            Envelope.from_volume(3.0, -1.0)
        with self.assertRaises(ValueError):
            Envelope.from_fineness(3.0, 0.0)
        with self.assertRaises(ValueError):
            spheroid_semi_minor_m(3.0, 0.0)


class MassModelTests(unittest.TestCase):
    def test_film_areal_density(self) -> None:
        # 100 um of 1.2 g/cm3 polyurethane is 120 g/m2 before construction.
        self.assertAlmostEqual(PU_100_UM.areal_density_kg_m2 / PU_100_UM.construction_factor,
                               0.120, places=6)
        self.assertAlmostEqual(PU_50_UM.areal_density_kg_m2, 0.5 * PU_100_UM.areal_density_kg_m2)

    def test_vendor_ratings_sit_below_the_physics_ceiling(self) -> None:
        """Rated payload must never exceed what the gas can lift after the
        envelope; a catalog entry that did would be a transcription error."""

        for article in RC_ZEPPELIN_INDOOR:
            envelope = Envelope.from_volume(article.length_m, article.helium_volume_m3)
            model = CarrierMassModel(envelope)
            with self.subTest(article=article.model):
                self.assertLess(article.rated_payload_kg, model.gross_lift_kg)
                if model.net_lift_kg > 0:
                    self.assertLess(article.rated_payload_kg, model.net_lift_kg)

    def test_net_lift_grows_monotonically_with_length(self) -> None:
        rows = length_sweep((1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5), fineness_ratio=3.0)
        nets = [row["net_lift_kg"] for row in rows]
        self.assertEqual(nets, sorted(nets))
        # Skin scales with L^2 and gas with L^3: below ~3 m at this fineness
        # and film the hull cannot lift its own systems.
        self.assertLess(rows[0]["net_lift_kg"], 0.0)
        self.assertGreater(rows[-1]["net_lift_kg"], 1.0)

    def test_toy_scale_needs_the_lighter_film_and_lighter_systems(self) -> None:
        heavy = length_sweep((2.0,), fineness_ratio=2.5)[0]
        light = length_sweep((2.0,), fineness_ratio=2.5, material=PU_50_UM,
                             systems_mass_kg=0.15)[0]
        self.assertLess(heavy["net_lift_kg"], 0.0)
        self.assertGreater(light["net_lift_kg"], 0.0)
        # ...and even then a 2 m toy nets well under the 180 g P0 dock.
        self.assertLess(light["net_lift_kg"], 0.18)


class SelectionTests(unittest.TestCase):
    def test_reserve_policy_minimum_rating_is_the_closing_boundary(self) -> None:
        policy = ReservePolicy(fraction_of_rating=0.10, floor_kg=0.05)
        for carried in (0.05, 0.30, 0.4254, 0.90):
            minimum = policy.minimum_rating_kg(carried)
            with self.subTest(carried=carried):
                self.assertTrue(policy.closes(minimum, carried))
                self.assertFalse(policy.closes(minimum - 1e-6, carried))

    def test_reserve_floor_wins_when_the_fraction_is_small(self) -> None:
        policy = ReservePolicy(fraction_of_rating=0.10, floor_kg=0.08)
        self.assertEqual(policy.required_reserve_kg(0.5), 0.08)
        self.assertEqual(policy.required_reserve_kg(1.0), 0.10)

    def test_policy_validation(self) -> None:
        with self.assertRaises(ValueError):
            ReservePolicy(fraction_of_rating=1.0)
        with self.assertRaises(ValueError):
            ReservePolicy(floor_kg=-0.01)
        with self.assertRaises(ValueError):
            ReservePolicy().minimum_rating_kg(-1.0)

    def test_catalog_is_sorted_and_self_consistent(self) -> None:
        lengths = [a.length_m for a in RC_ZEPPELIN_INDOOR]
        self.assertEqual(lengths, sorted(lengths))
        for article in RC_ZEPPELIN_INDOOR:
            self.assertLessEqual(article.rated_payload_low_kg, article.rated_payload_kg)
            self.assertGreater(article.helium_volume_m3, 0.0)

    def test_selection_picks_the_smallest_closing_article(self) -> None:
        policy = ReservePolicy(fraction_of_rating=0.10, floor_kg=0.0477)
        self.assertEqual(select_article(0.4254, policy).length_m, 3.5)
        self.assertEqual(select_article(0.4254, policy, conservative=True).length_m, 4.5)
        self.assertEqual(select_article(0.05, policy).length_m, 1.5)
        self.assertIsNone(select_article(1.5, policy))

    def test_article_lookup(self) -> None:
        self.assertEqual(article_by_length(4.5).helium_volume_m3, 5.5)
        with self.assertRaises(KeyError):
            article_by_length(7.0)


class P0ArticleTests(unittest.TestCase):
    """The reference article is derived from the budget, not declared."""

    def test_p0_article_is_the_selected_article(self) -> None:
        self.assertEqual(selected_article().length_m, P0_ARTICLE.length_m)
        self.assertEqual(CarrierSpec().envelope_length_m, P0_ARTICLE.length_m)
        self.assertEqual(CarrierSpec().rated_payload_kg, P0_ARTICLE.rated_payload_kg)

    def test_baseline_budget_closes_under_the_reserve_rule(self) -> None:
        carried = payload_mass_kg(baseline_p0_budget())
        policy = reserve_policy()
        self.assertTrue(policy.closes(P0_ARTICLE.rated_payload_kg, carried))
        # The reserve is set by the aircraft step, not the fraction, at this
        # rating: 47.7 g against 50 g.  Both are below the 74.6 g margin.
        self.assertAlmostEqual(policy.floor_kg, 0.0477, places=4)
        self.assertAlmostEqual(policy.required_reserve_kg(0.5), 0.05, places=4)

    def test_vendor_low_figure_falls_back_to_the_4_5_m_article(self) -> None:
        self.assertEqual(selected_article(conservative=True).length_m, 4.5)

    def test_p0_hull_geometry(self) -> None:
        envelope = p0_envelope()
        self.assertAlmostEqual(envelope.volume_m3, P0_ARTICLE.helium_volume_m3, places=9)
        self.assertAlmostEqual(P0_SEMI_MINOR_M, 0.739, places=3)
        # A fat indoor hull, but still an airship rather than a balloon.
        self.assertGreater(envelope.fineness_ratio, 2.0)
        self.assertLess(envelope.fineness_ratio, 3.0)
        self.assertTrue(math.isclose(envelope.length_m, 3.5))


if __name__ == "__main__":
    unittest.main()
