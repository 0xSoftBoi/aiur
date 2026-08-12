"""Classical laminate theory checks.

The value of these tests is that most of them do not compare against a
number this repository chose.  They compare against results that classical
laminate theory is *required* to reproduce — an isotropic material coming
back isotropic, a single unidirectional ply returning its own modulus, a
quasi-isotropic laminate satisfying the isotropic shear identity — so an
error in the transformation, the integration or the inversion has nowhere to
hide.
"""

import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from aiur.composites import clt
from aiur.composites.clt import (
    Laminate,
    Ply,
    bending_strain_at_radius,
    invert,
    max_strain_index,
    minimum_stow_radius_mm,
    reduced_stiffness,
    solve,
    transformed_expansion,
    transformed_stiffness,
    tsai_wu_index,
    tsai_wu_strength_ratio,
)
from aiur.composites.materials import MATERIALS, UD_CARBON_IM, material


class LinearAlgebraTest(unittest.TestCase):
    def test_solve_matches_hand_worked_system(self):
        matrix = [[2.0, 1.0], [1.0, 3.0]]
        self.assertEqual([1.0, 2.0], solve(matrix, [4.0, 7.0]))

    def test_solve_needs_pivoting(self):
        # A zero in the first pivot position: only partial pivoting survives.
        matrix = [[0.0, 1.0], [1.0, 0.0]]
        self.assertEqual([2.0, 3.0], solve(matrix, [3.0, 2.0]))

    def test_invert_round_trips(self):
        matrix = [[4.0, 1.0, 2.0], [1.0, 5.0, 3.0], [2.0, 3.0, 6.0]]
        inverse = invert(matrix)
        for i in range(3):
            for j in range(3):
                product = sum(matrix[i][k] * inverse[k][j] for k in range(3))
                self.assertAlmostEqual(1.0 if i == j else 0.0, product, places=10)

    def test_singular_matrix_is_refused(self):
        with self.assertRaises(ValueError):
            solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])


class IsotropicDegenerateCaseTest(unittest.TestCase):
    """An isotropic ply must produce an isotropic laminate at any angles.

    This is the strongest single check available on the transformation and
    integration: if any term of Qbar, A, B or D is wrong, the laminate stops
    being isotropic and the identities below fail.
    """

    MODULUS = 70_000.0
    POISSON = 0.33
    CTE = 23e-6

    def setUp(self):
        self.isotropic = replace(
            UD_CARBON_IM,
            name="TEST-ISO",
            e1_mpa=self.MODULUS,
            e2_mpa=self.MODULUS,
            g12_mpa=self.MODULUS / (2.0 * (1.0 + self.POISSON)),
            nu12=self.POISSON,
            alpha1_per_k=self.CTE,
            alpha2_per_k=self.CTE,
            alpha3_per_k=self.CTE,
            shrink1=0.0,
            shrink2=0.0,
            shrink3=0.0,
            cured_ply_thickness_mm=1.0,
        )
        # Registered into the real registry for the duration of the test, so
        # the laminate code under test is exercised through its ordinary
        # lookup path rather than through a special case built for testing.
        patcher = patch.dict(MATERIALS, {self.isotropic.name: self.isotropic})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_engineering_constants_are_angle_independent(self):
        laminate = Laminate.from_angles("TEST-ISO", [0.0, 37.0, -12.0, 90.0])
        constants = laminate.engineering_constants()
        self.assertAlmostEqual(self.MODULUS, constants["ex_mpa"], places=6)
        self.assertAlmostEqual(self.MODULUS, constants["ey_mpa"], places=6)
        self.assertAlmostEqual(
            self.MODULUS / (2.0 * (1.0 + self.POISSON)), constants["gxy_mpa"], places=6
        )
        self.assertAlmostEqual(self.POISSON, constants["nuxy"], places=9)

    def test_laminate_cte_equals_ply_cte(self):
        laminate = Laminate.from_angles("TEST-ISO", [0.0, 55.0, -20.0, 90.0])
        cte = laminate.cte_per_k()
        self.assertAlmostEqual(self.CTE, cte[0], places=12)
        self.assertAlmostEqual(self.CTE, cte[1], places=12)
        self.assertAlmostEqual(0.0, cte[2], places=14)


class UnidirectionalRecoveryTest(unittest.TestCase):
    def test_zero_degree_ply_returns_its_own_constants(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0])
        constants = laminate.engineering_constants()
        self.assertAlmostEqual(UD_CARBON_IM.e1_mpa, constants["ex_mpa"], places=6)
        self.assertAlmostEqual(UD_CARBON_IM.e2_mpa, constants["ey_mpa"], places=6)
        self.assertAlmostEqual(UD_CARBON_IM.g12_mpa, constants["gxy_mpa"], places=6)
        self.assertAlmostEqual(UD_CARBON_IM.nu12, constants["nuxy"], places=9)

    def test_ninety_degree_ply_swaps_the_axes(self):
        laminate = Laminate.from_angles("UD-C-IM", [90.0])
        constants = laminate.engineering_constants()
        self.assertAlmostEqual(UD_CARBON_IM.e2_mpa, constants["ex_mpa"], places=6)
        self.assertAlmostEqual(UD_CARBON_IM.e1_mpa, constants["ey_mpa"], places=6)
        self.assertAlmostEqual(UD_CARBON_IM.nu21, constants["nuxy"], places=9)

    def test_zero_degree_ply_returns_its_own_cte(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0])
        cte = laminate.cte_per_k()
        self.assertAlmostEqual(UD_CARBON_IM.alpha1_per_k, cte[0], places=12)
        self.assertAlmostEqual(UD_CARBON_IM.alpha2_per_k, cte[1], places=12)

    def test_reduced_stiffness_is_symmetric_and_positive_definite(self):
        q = reduced_stiffness(UD_CARBON_IM)
        self.assertAlmostEqual(q[0][1], q[1][0], places=9)
        self.assertGreater(q[0][0], 0.0)
        self.assertGreater(q[0][0] * q[1][1] - q[0][1] ** 2, 0.0)

    def test_transformation_at_zero_is_the_identity(self):
        q = reduced_stiffness(UD_CARBON_IM)
        qbar = transformed_stiffness(UD_CARBON_IM, 0.0)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(q[i][j], qbar[i][j], places=6)

    def test_transformation_at_ninety_swaps_the_diagonal(self):
        q = reduced_stiffness(UD_CARBON_IM)
        qbar = transformed_stiffness(UD_CARBON_IM, 90.0)
        self.assertAlmostEqual(q[1][1], qbar[0][0], places=6)
        self.assertAlmostEqual(q[0][0], qbar[1][1], places=6)
        self.assertAlmostEqual(0.0, qbar[0][2], places=6)

    def test_expansion_transform_carries_the_engineering_shear_factor(self):
        expansion = transformed_expansion(UD_CARBON_IM, 45.0)
        expected_shear = 2.0 * 0.5 * (UD_CARBON_IM.alpha1_per_k - UD_CARBON_IM.alpha2_per_k)
        self.assertAlmostEqual(expected_shear, expansion[2], places=14)


class QuasiIsotropicTest(unittest.TestCase):
    """A balanced, symmetric quasi-isotropic laminate is in-plane isotropic."""

    def setUp(self):
        self.laminate = Laminate.from_angles(
            "UD-C-IM", [0.0, 45.0, -45.0, 90.0, 90.0, -45.0, 45.0, 0.0]
        )

    def test_in_plane_moduli_are_equal(self):
        constants = self.laminate.engineering_constants()
        self.assertAlmostEqual(constants["ex_mpa"], constants["ey_mpa"], places=6)

    def test_shear_modulus_satisfies_the_isotropic_identity(self):
        constants = self.laminate.engineering_constants()
        expected = constants["ex_mpa"] / (2.0 * (1.0 + constants["nuxy"]))
        self.assertAlmostEqual(expected, constants["gxy_mpa"], delta=1e-6 * expected)

    def test_cte_is_isotropic_in_plane(self):
        cte = self.laminate.cte_per_k()
        self.assertAlmostEqual(cte[0], cte[1], places=12)
        self.assertAlmostEqual(0.0, cte[2], places=14)

    def test_orientation_fractions_sum_to_one(self):
        fractions = self.laminate.orientation_fractions()
        self.assertAlmostEqual(1.0, sum(fractions.values()), places=12)
        self.assertAlmostEqual(0.25, fractions["0"], places=12)
        self.assertAlmostEqual(0.25, fractions["90"], places=12)
        self.assertAlmostEqual(0.50, fractions["45"], places=12)


class SymmetryAndCouplingTest(unittest.TestCase):
    def test_symmetric_laminate_has_no_coupling(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0, 90.0, 90.0, 0.0])
        self.assertTrue(laminate.is_symmetric())
        self.assertFalse(laminate.is_coupled())
        for row in laminate.b_matrix():
            for value in row:
                self.assertAlmostEqual(0.0, value, places=6)

    def test_unsymmetric_cross_ply_curves_when_cooled(self):
        # The bimetallic-strip case: the classic demonstration that B matters.
        laminate = Laminate.from_angles("UD-C-IM", [0.0, 90.0])
        self.assertFalse(laminate.is_symmetric())
        self.assertTrue(laminate.is_coupled())
        curvature = laminate.thermal_curvature_per_k()
        self.assertGreater(abs(curvature[0]), 1e-6)
        # Equal and opposite: a cross-ply saddles symmetrically.
        self.assertAlmostEqual(curvature[0], -curvature[1], places=9)

    def test_symmetric_laminate_has_no_thermal_curvature(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0, 90.0, 90.0, 0.0])
        for value in laminate.thermal_curvature_per_k():
            self.assertAlmostEqual(0.0, value, places=15)

    def test_balance_requires_a_mirror_angle_partner(self):
        self.assertTrue(Laminate.from_angles("UD-C-IM", [45.0, -45.0]).is_balanced())
        self.assertFalse(Laminate.from_angles("UD-C-IM", [45.0, 45.0]).is_balanced())
        self.assertFalse(
            Laminate.from_angles("UD-C-IM", [45.0, 45.0, -45.0]).is_balanced()
        )

    def test_woven_ply_at_45_is_self_balanced(self):
        # The weave already carries tows at +45 and -45; demanding a partner
        # ply would add thickness for nothing.
        laminate = Laminate.from_angles("PW-C-193", [45.0, 45.0])
        self.assertTrue(laminate.is_balanced())
        self.assertAlmostEqual(0.0, laminate.a_matrix()[0][2], places=6)

    def test_unbalanced_laminate_shears_under_tension(self):
        laminate = Laminate.from_angles("UD-C-IM", [30.0, 30.0])
        self.assertGreater(abs(laminate.a_matrix()[0][2]), 1.0)

    def test_contiguous_run_counts_only_unidirectional_plies(self):
        # A fabric ply interrupts a tape block: half its fibre is crosswise.
        with_fabric = Laminate.from_top_down(
            [Ply("UD-C-IM", 0.0), Ply("PW-C-193", 0.0), Ply("UD-C-IM", 0.0)]
        )
        self.assertEqual(1, with_fabric.max_contiguous_same_angle())
        bare_tape = Laminate.from_angles("UD-C-IM", [0.0, 0.0, 0.0])
        self.assertEqual(3, bare_tape.max_contiguous_same_angle())


class GeometryTest(unittest.TestCase):
    def test_z_boundaries_span_the_thickness_symmetrically(self):
        laminate = Laminate.from_angles("PW-C-193", [0.0, 45.0, 45.0, 0.0])
        boundaries = laminate.z_boundaries()
        self.assertEqual(5, len(boundaries))
        self.assertAlmostEqual(-laminate.thickness_mm / 2.0, boundaries[0], places=12)
        self.assertAlmostEqual(laminate.thickness_mm / 2.0, boundaries[-1], places=12)

    def test_top_down_construction_reverses_the_stack(self):
        top_down = [Ply("PW-C-193", 0.0), Ply("PW-C-193", 45.0)]
        laminate = Laminate.from_top_down(top_down)
        self.assertEqual(45.0, laminate.plies[0].angle_deg)
        self.assertEqual(0.0, laminate.plies[-1].angle_deg)

    def test_areal_mass_matches_the_sum_of_plies(self):
        laminate = Laminate.from_angles("PW-C-193", [0.0, 45.0])
        expected = 2.0 * material("PW-C-193").areal_mass_g_m2
        self.assertAlmostEqual(expected, laminate.areal_mass_g_m2, places=6)

    def test_empty_laminate_is_refused(self):
        with self.assertRaises(ValueError):
            Laminate([])


class LoadResponseTest(unittest.TestCase):
    def test_single_ply_stress_matches_the_hand_calculation(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0])
        thickness = laminate.thickness_mm
        response = laminate.response(n_per_mm=(100.0, 0.0, 0.0))
        expected_stress = 100.0 / thickness
        self.assertAlmostEqual(expected_stress, response.plies[0].stress_12_mpa[0], places=6)
        self.assertAlmostEqual(
            expected_stress / UD_CARBON_IM.e1_mpa,
            response.plies[0].strain_12[0],
            places=12,
        )

    def test_strength_ratio_is_the_load_multiplier_to_failure(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0])
        thickness = laminate.thickness_mm
        response = laminate.response(n_per_mm=(100.0, 0.0, 0.0))
        applied = 100.0 / thickness
        self.assertAlmostEqual(
            UD_CARBON_IM.xt_mpa / applied, response.first_ply_failure_ratio, delta=0.05
        )

    def test_scaling_the_load_by_the_strength_ratio_reaches_failure(self):
        laminate = Laminate.from_angles("PW-C-193", [0.0, 45.0, 45.0, 0.0])
        response = laminate.response(n_per_mm=(120.0, 30.0, 15.0))
        ratio = response.first_ply_failure_ratio
        scaled = laminate.response(
            n_per_mm=(120.0 * ratio, 30.0 * ratio, 15.0 * ratio)
        )
        self.assertAlmostEqual(1.0, scaled.max_tsai_wu, places=6)

    def test_cooldown_alone_produces_stress(self):
        laminate = Laminate.from_angles("UD-C-IM", [0.0, 90.0, 90.0, 0.0])
        response = laminate.response(delta_t_k=-155.0)
        # No external load, and the transverse plies are nonetheless loaded.
        transverse = max(abs(ply.stress_12_mpa[1]) for ply in response.plies)
        self.assertGreater(transverse, 10.0)

    def test_thermal_stresses_self_equilibrate(self):
        # With no applied load the through-thickness force resultant of the
        # residual stress field must integrate back to zero.
        laminate = Laminate.from_angles("UD-C-IM", [0.0, 90.0, 90.0, 0.0])
        response = laminate.response(delta_t_k=-155.0)
        boundaries = laminate.z_boundaries()
        total = 0.0
        for index, ply in enumerate(laminate.plies):
            thickness = boundaries[index + 1] - boundaries[index]
            states = [state for state in response.plies if state.index == index]
            mean_stress = sum(state.stress_12_mpa[0] for state in states) / len(states)
            angle = math.radians(ply.angle_deg)
            total += mean_stress * math.cos(angle) ** 2 * thickness
            mean_transverse = sum(state.stress_12_mpa[1] for state in states) / len(states)
            total += mean_transverse * math.sin(angle) ** 2 * thickness
        self.assertAlmostEqual(0.0, total, delta=1e-6)

    def test_cylindrical_edge_condition_is_stiffer_than_free(self):
        laminate = Laminate.from_angles("PW-C-193", [45.0, 0.0, 0.0, 45.0])
        free = laminate.response(m_per_mm=(5.0, 0.0, 0.0), edge="free")
        cylindrical = laminate.response(m_per_mm=(5.0, 0.0, 0.0), edge="cylindrical")
        self.assertGreater(abs(free.curvature[0]), abs(cylindrical.curvature[0]))
        self.assertAlmostEqual(0.0, cylindrical.curvature[1], places=14)
        self.assertGreater(
            cylindrical.first_ply_failure_ratio, free.first_ply_failure_ratio
        )

    def test_unknown_edge_condition_is_refused(self):
        laminate = Laminate.from_angles("PW-C-193", [0.0])
        with self.assertRaises(ValueError):
            laminate.response(edge="clamped")

    def test_mixed_solve_honours_the_restraint(self):
        laminate = Laminate.from_angles("PW-C-193", [45.0, 0.0, 0.0, 45.0])
        solution = laminate.mixed_solve([10.0, 0.0, 0.0, 0.0, 0.0, 0.0], restrained=(1,))
        self.assertAlmostEqual(0.0, solution[1], places=14)

    def test_both_faces_of_each_ply_are_evaluated(self):
        laminate = Laminate.from_angles("PW-C-193", [0.0, 45.0, 45.0, 0.0])
        response = laminate.response(m_per_mm=(2.0, 0.0, 0.0))
        self.assertEqual(2 * laminate.ply_count, len(response.plies))


class FailureCriteriaTest(unittest.TestCase):
    def test_tsai_wu_reaches_unity_at_uniaxial_tensile_strength(self):
        index = tsai_wu_index(UD_CARBON_IM, (UD_CARBON_IM.xt_mpa, 0.0, 0.0))
        self.assertAlmostEqual(1.0, index, places=9)

    def test_tsai_wu_reaches_unity_at_uniaxial_compressive_strength(self):
        index = tsai_wu_index(UD_CARBON_IM, (-UD_CARBON_IM.xc_mpa, 0.0, 0.0))
        self.assertAlmostEqual(1.0, index, places=9)

    def test_tsai_wu_reaches_unity_at_shear_strength(self):
        index = tsai_wu_index(UD_CARBON_IM, (0.0, 0.0, UD_CARBON_IM.s12_mpa))
        self.assertAlmostEqual(1.0, index, places=9)

    def test_tsai_wu_is_insensitive_to_shear_sign(self):
        positive = tsai_wu_index(UD_CARBON_IM, (100.0, 10.0, 40.0))
        negative = tsai_wu_index(UD_CARBON_IM, (100.0, 10.0, -40.0))
        self.assertAlmostEqual(positive, negative, places=12)

    def test_strength_ratio_of_unit_index_is_one(self):
        ratio = tsai_wu_strength_ratio(UD_CARBON_IM, (UD_CARBON_IM.xt_mpa, 0.0, 0.0))
        self.assertAlmostEqual(1.0, ratio, places=9)

    def test_strength_ratio_is_not_the_square_root_of_the_index(self):
        # The distinction the module exists to preserve: with a linear term
        # present, R is not simply 1/sqrt(index).
        stress = (0.4 * UD_CARBON_IM.xt_mpa, 0.0, 0.0)
        index = tsai_wu_index(UD_CARBON_IM, stress)
        ratio = tsai_wu_strength_ratio(UD_CARBON_IM, stress)
        self.assertAlmostEqual(2.5, ratio, places=6)
        self.assertNotAlmostEqual(1.0 / math.sqrt(index), ratio, places=3)

    def test_zero_stress_never_fails(self):
        self.assertEqual(math.inf, tsai_wu_strength_ratio(UD_CARBON_IM, (0.0, 0.0, 0.0)))

    def test_max_strain_index_uses_the_matching_sign_allowable(self):
        tension = max_strain_index(UD_CARBON_IM, (UD_CARBON_IM.xt_mpa / UD_CARBON_IM.e1_mpa, 0.0, 0.0))
        self.assertAlmostEqual(1.0, tension, places=9)
        compression = max_strain_index(
            UD_CARBON_IM, (-UD_CARBON_IM.xc_mpa / UD_CARBON_IM.e1_mpa, 0.0, 0.0)
        )
        self.assertAlmostEqual(1.0, compression, places=9)


class StowageTest(unittest.TestCase):
    def test_bending_strain_is_half_thickness_over_radius(self):
        self.assertAlmostEqual(0.01, bending_strain_at_radius(1.0, 50.0), places=12)

    def test_thinner_laminate_stows_tighter(self):
        thin = Laminate.from_angles("PW-C-80", [45.0, 45.0])
        thick = Laminate.from_angles("PW-C-193", [45.0, 45.0])
        self.assertLess(minimum_stow_radius_mm(thin), minimum_stow_radius_mm(thick))

    def test_high_modulus_fibre_needs_a_larger_stow_radius_per_thickness(self):
        # The reason the boom is forbidden high-modulus tape: its strain
        # allowable is less than half the woven material's.
        high_modulus = Laminate.from_angles("UD-C-HM", [0.0] * 2)
        woven = Laminate.from_angles("PW-C-80", [45.0, 45.0])
        hm_ratio = minimum_stow_radius_mm(high_modulus) / high_modulus.thickness_mm
        woven_ratio = minimum_stow_radius_mm(woven) / woven.thickness_mm
        self.assertGreater(hm_ratio, 2.0 * woven_ratio)

    def test_stow_radius_scales_with_the_knockdown(self):
        laminate = Laminate.from_angles("PW-C-80", [45.0, 45.0])
        full = minimum_stow_radius_mm(laminate, knockdown=1.0)
        half = minimum_stow_radius_mm(laminate, knockdown=0.5)
        self.assertAlmostEqual(2.0 * full, half, places=9)

    def test_invalid_geometry_is_refused(self):
        with self.assertRaises(ValueError):
            bending_strain_at_radius(1.0, 0.0)
        with self.assertRaises(ValueError):
            bending_strain_at_radius(0.0, 10.0)


class DescriptionTest(unittest.TestCase):
    def test_symmetric_even_stack_uses_the_s_shorthand(self):
        laminate = Laminate.from_angles("PW-C-193", [45.0, 0.0, 0.0, 45.0])
        self.assertEqual("[45/0]s (PW-C-193)", laminate.describe())

    def test_unsymmetric_stack_is_written_out_in_full(self):
        laminate = Laminate.from_angles("PW-C-193", [45.0, 0.0])
        self.assertEqual("[45/0] (PW-C-193)", laminate.describe())


if __name__ == "__main__":
    unittest.main()
