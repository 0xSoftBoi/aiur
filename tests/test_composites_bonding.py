"""Bonded-joint checks.

The shear-lag tests are anchored on equilibrium: whatever the distribution
looks like, integrating the adhesive shear across the overlap must return
the applied load. That is an identity, so it catches an error in the
constants of the Volkersen solution that comparing against a remembered
number would not.

The rest of the file is about the design rules, which are the substance of
bonded-joint work. Most of them are tested by constructing a joint that
breaks them and requiring the evaluation to say so.
"""

import math
import unittest
from dataclasses import replace

from aiur.composites import bonding
from aiur.composites.bonding import (
    ADHEREND_FAILURE_FACTOR,
    BOND_FACTOR_OF_SAFETY,
    BondedJoint,
    FILM_ADHESIVE,
    JOINTS,
    JointType,
    MAX_BONDLINE_MM,
    SATURATION_MULTIPLE,
    adherend_capacity_n_per_mm,
    adhesive,
    evaluate_joint,
    joint,
    load_transfer_length_mm,
    peak_shear_mpa,
    saturation_overlap_mm,
    shear_lag_parameter,
    shear_stress_mpa,
    snapshot,
    stress_concentration,
)


class ShearLagTest(unittest.TestCase):
    def setUp(self):
        self.omega = shear_lag_parameter(
            shear_modulus_mpa=700.0,
            bondline_mm=0.20,
            stiffness_1_n_mm=2438.0,
            stiffness_2_n_mm=2438.0,
        )

    def test_shear_distribution_integrates_to_the_applied_load(self):
        # Equilibrium: the adhesive transfers exactly what was applied.
        load, overlap = 10.0, 20.0
        steps = 20001
        positions = [
            -overlap / 2.0 + index * overlap / (steps - 1) for index in range(steps)
        ]
        values = [
            shear_stress_mpa(
                position, load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega
            )
            for position in positions
        ]
        # Simpson's rule over an even number of intervals.
        step = overlap / (steps - 1)
        total = values[0] + values[-1]
        total += 4.0 * sum(values[1:-1:2])
        total += 2.0 * sum(values[2:-1:2])
        integral = total * step / 3.0
        self.assertAlmostEqual(load, integral, places=6)

    def test_shear_peaks_at_the_ends_of_a_balanced_overlap(self):
        load, overlap = 10.0, 20.0
        centre = shear_stress_mpa(
            0.0, load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega
        )
        end = shear_stress_mpa(
            overlap / 2.0, load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega
        )
        self.assertGreater(end, centre)

    def test_balanced_joint_is_symmetric(self):
        load, overlap = 10.0, 20.0
        left = shear_stress_mpa(
            -6.0, load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega
        )
        right = shear_stress_mpa(
            6.0, load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega
        )
        self.assertAlmostEqual(left, right, places=9)

    def test_stiffness_imbalance_moves_the_peak_to_one_end(self):
        load, overlap = 10.0, 20.0
        left = shear_stress_mpa(
            -overlap / 2.0, load_n_per_mm=load, overlap_mm=overlap,
            omega_per_mm=self.omega, stiffness_ratio=100.0,
        )
        right = shear_stress_mpa(
            overlap / 2.0, load_n_per_mm=load, overlap_mm=overlap,
            omega_per_mm=self.omega, stiffness_ratio=100.0,
        )
        self.assertGreater(right, left)

    def test_bonding_to_a_rigid_adherend_doubles_the_peak(self):
        # The reason balanced adherends are preferred: all of the strain
        # mismatch ends up at one end of the overlap.
        load, overlap = 10.0, 40.0
        balanced = peak_shear_mpa(
            load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega
        )
        rigid = peak_shear_mpa(
            load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega,
            stiffness_ratio=1e6,
        )
        self.assertAlmostEqual(2.0, rigid / balanced, places=3)

    def test_peak_shear_matches_the_distribution_at_the_end(self):
        load, overlap = 10.0, 20.0
        from_distribution = shear_stress_mpa(
            overlap / 2.0, load_n_per_mm=load, overlap_mm=overlap,
            omega_per_mm=self.omega, stiffness_ratio=50.0,
        )
        self.assertAlmostEqual(
            from_distribution,
            peak_shear_mpa(
                load_n_per_mm=load, overlap_mm=overlap, omega_per_mm=self.omega,
                stiffness_ratio=50.0,
            ),
            places=9,
        )

    def test_omega_rises_with_adhesive_modulus_and_falls_with_bondline(self):
        stiffer = shear_lag_parameter(
            shear_modulus_mpa=1400.0, bondline_mm=0.20,
            stiffness_1_n_mm=2438.0, stiffness_2_n_mm=2438.0,
        )
        thicker = shear_lag_parameter(
            shear_modulus_mpa=700.0, bondline_mm=0.40,
            stiffness_1_n_mm=2438.0, stiffness_2_n_mm=2438.0,
        )
        self.assertGreater(stiffer, self.omega)
        self.assertLess(thicker, self.omega)

    def test_omega_scales_as_the_inverse_root_of_bondline(self):
        thicker = shear_lag_parameter(
            shear_modulus_mpa=700.0, bondline_mm=0.80,
            stiffness_1_n_mm=2438.0, stiffness_2_n_mm=2438.0,
        )
        self.assertAlmostEqual(2.0, self.omega / thicker, places=9)

    def test_position_outside_the_overlap_is_refused(self):
        with self.assertRaises(ValueError):
            shear_stress_mpa(
                20.0, load_n_per_mm=1.0, overlap_mm=20.0, omega_per_mm=self.omega
            )

    def test_non_positive_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            shear_lag_parameter(
                shear_modulus_mpa=0.0, bondline_mm=0.2,
                stiffness_1_n_mm=1.0, stiffness_2_n_mm=1.0,
            )
        with self.assertRaises(ValueError):
            load_transfer_length_mm(0.0)


class OverlapSaturationTest(unittest.TestCase):
    """The finding: a long overlap is not a strong one."""

    def setUp(self):
        self.omega = shear_lag_parameter(
            shear_modulus_mpa=700.0, bondline_mm=0.20,
            stiffness_1_n_mm=1219.0, stiffness_2_n_mm=1e9,
        )

    def test_capacity_saturates_with_overlap(self):
        def capacity(overlap):
            return FILM_ADHESIVE.shear_strength_mpa / peak_shear_mpa(
                load_n_per_mm=1.0, overlap_mm=overlap, omega_per_mm=self.omega
            )

        short = capacity(saturation_overlap_mm(self.omega))
        long = capacity(10.0 * saturation_overlap_mm(self.omega))
        self.assertAlmostEqual(1.0, long / short, places=2)

    def test_doubling_a_saturated_overlap_adds_under_one_percent(self):
        def capacity(overlap):
            return 1.0 / peak_shear_mpa(
                load_n_per_mm=1.0, overlap_mm=overlap, omega_per_mm=self.omega
            )

        base = saturation_overlap_mm(self.omega) * 2.0
        self.assertLess(capacity(2.0 * base) / capacity(base) - 1.0, 0.01)

    def test_short_overlap_does_still_gain_from_length(self):
        def capacity(overlap):
            return 1.0 / peak_shear_mpa(
                load_n_per_mm=1.0, overlap_mm=overlap, omega_per_mm=self.omega
            )

        tiny = 0.2 * load_transfer_length_mm(self.omega)
        self.assertGreater(capacity(2.0 * tiny) / capacity(tiny), 1.5)

    def test_stress_concentration_grows_linearly_once_saturated(self):
        # tau_max/tau_avg -> omega L / 2, so it tracks length exactly.
        long = 20.0 * load_transfer_length_mm(self.omega)
        self.assertAlmostEqual(
            self.omega * long / 2.0,
            stress_concentration(overlap_mm=long, omega_per_mm=self.omega),
            places=6,
        )

    def test_saturation_length_is_a_multiple_of_the_transfer_length(self):
        self.assertAlmostEqual(
            SATURATION_MULTIPLE * load_transfer_length_mm(self.omega),
            saturation_overlap_mm(self.omega),
            places=12,
        )


class JointRegistryTest(unittest.TestCase):
    def test_every_joint_qualifies_by_a_stated_route(self):
        report = snapshot()
        self.assertTrue(report["valid"], report["failing_checks"])
        self.assertEqual([], report["critical_failures"])

    def test_joint_ids_are_unique(self):
        ids = [item.joint_id for item in JOINTS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_joint_and_adhesive_are_refused(self):
        with self.assertRaises(KeyError):
            joint("BJ-999")
        with self.assertRaises(KeyError):
            adhesive("NOT-AN-ADHESIVE")

    def test_boom_root_reaches_adherend_first_failure(self):
        result = evaluate_joint(joint("BJ-200"))
        self.assertGreaterEqual(result["adherend_first_ratio"], ADHEREND_FAILURE_FACTOR)
        route = next(c for c in result["checks"] if c["name"] == "qualification_route")
        self.assertEqual("adherend-first", route["actual"])

    def test_boom_root_needs_its_thicker_bondline_to_get_there(self):
        # A thicker bondline makes this joint stronger, which is the
        # counterintuitive result worth protecting with a test.
        at_nominal = evaluate_joint(replace(joint("BJ-200"), bondline_mm=0.20))
        self.assertLess(at_nominal["adherend_first_ratio"], ADHEREND_FAILURE_FACTOR)
        self.assertGreater(
            evaluate_joint(joint("BJ-200"))["capacity_n_per_mm"],
            at_nominal["capacity_n_per_mm"],
        )

    def test_thick_adherend_joints_cannot_out_strength_their_adherend(self):
        # The reason the rule has two branches: no bondline inside the
        # process band gets these joints there.
        for joint_id in ("BJ-100", "BJ-300"):
            result = evaluate_joint(joint(joint_id))
            self.assertFalse(result["adherend_first_achievable"], joint_id)
            self.assertGreater(
                result["bondline_for_adherend_first_mm"], MAX_BONDLINE_MM, joint_id
            )
            route = next(c for c in result["checks"] if c["name"] == "qualification_route")
            self.assertEqual("load margin + proof test", route["actual"])

    def test_a_joint_with_neither_route_is_rejected(self):
        stranded = replace(joint("BJ-300"), proof_test_factor=0.0)
        result = evaluate_joint(stranded)
        self.assertFalse(result["passed"])
        route = next(c for c in result["checks"] if c["name"] == "qualification_route")
        self.assertFalse(route["passed"])
        self.assertEqual("none", route["actual"])

    def test_critical_joint_without_a_proof_test_is_rejected(self):
        result = evaluate_joint(replace(joint("BJ-300"), proof_test_factor=0.0))
        check = next(
            c for c in result["checks"] if c["name"] == "critical_joint_is_proof_tested"
        )
        self.assertFalse(check["passed"])

    def test_critical_single_lap_is_rejected(self):
        result = evaluate_joint(
            replace(joint("BJ-300"), joint_type=JointType.SINGLE_LAP)
        )
        check = next(
            c for c in result["checks"] if c["name"] == "not_single_lap_when_critical"
        )
        self.assertFalse(check["passed"])
        self.assertIn("peel", check["consequence"])

    def test_non_critical_single_lap_is_allowed_but_halves_the_capacity(self):
        double = evaluate_joint(joint("BJ-100"))
        single = evaluate_joint(replace(joint("BJ-100"), joint_type=JointType.SINGLE_LAP))
        self.assertTrue(
            next(c for c in single["checks"] if c["name"] == "not_single_lap_when_critical")[
                "passed"
            ]
        )
        self.assertLess(single["capacity_n_per_mm"], double["capacity_n_per_mm"])

    def test_out_of_band_bondline_is_rejected(self):
        result = evaluate_joint(replace(joint("BJ-100"), bondline_mm=0.9))
        check = next(c for c in result["checks"] if c["name"] == "bondline_thickness_mm")
        self.assertFalse(check["passed"])

    def test_adhesive_with_an_unbuildable_bondline_is_refused(self):
        with self.assertRaises(ValueError):
            replace(FILM_ADHESIVE, nominal_bondline_mm=1.5)

    def test_every_joint_carries_far_more_than_its_design_load(self):
        # The point of the module's closing argument: strength is not what
        # threatens these bonds.
        for item in JOINTS:
            result = evaluate_joint(item)
            margin = next(
                c for c in result["checks"] if c["name"] == "margin_on_design_load"
            )
            self.assertGreater(margin["actual"], BOND_FACTOR_OF_SAFETY)

    def test_most_of_each_overlap_is_inert(self):
        for joint_id in ("BJ-100", "BJ-200"):
            result = evaluate_joint(joint(joint_id))
            self.assertGreater(result["overlap_beyond_saturation_mm"], 0.0, joint_id)

    def test_every_joint_explains_its_overlap(self):
        for item in JOINTS:
            self.assertTrue(item.overlap_rationale, item.joint_id)

    def test_adherend_capacity_comes_from_the_laminate_model(self):
        from aiur.composites.schedules import schedule

        laminate = schedule("CS-200").laminate()
        self.assertAlmostEqual(
            laminate.response(n_per_mm=(1.0, 0.0, 0.0)).first_ply_failure_ratio,
            adherend_capacity_n_per_mm("CS-200"),
            places=9,
        )

    def test_snapshot_names_the_governing_risk(self):
        self.assertIn("kissing bond", snapshot()["governing_risk"])

    def test_surface_preparations_state_their_contamination_risk(self):
        for preparation in bonding.SURFACE_PREPARATIONS:
            self.assertTrue(preparation.contamination_risk)
            self.assertTrue(preparation.note)


if __name__ == "__main__":
    unittest.main()
