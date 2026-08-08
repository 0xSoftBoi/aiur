import json
import math
import unittest
from pathlib import Path

from aiur.tolerance import (
    AS_BUILT_COLUMNS,
    AS_BUILT_FEATURES,
    CALIPER_UNCERTAINTY_MM,
    DERIVED_DIMENSIONS,
    DIMENSIONS,
    EXACT_RELEASE_TRAVEL_MM,
    FDM_TOLERANCE_LARGE_MM,
    FDM_TOLERANCE_SMALL_MM,
    KEEPER_HEAD_OVERLAP,
    KEEPER_SLOT_HALF_WIDTH,
    OPEN_FINDINGS,
    SLOT_MAST_CLEARANCE,
    STACKS,
    Dimension,
    OpenFinding,
    Stack,
    as_built,
    chain_verdict,
    dominant_contributor,
    evaluate_all,
    evaluate_stack,
    fdm_tolerance_mm,
    measured_dimensions,
    nominal_mm,
    rss_mm,
    snapshot,
    stack_by_name,
    validate_stacks,
    worst_case_mm,
)
from hardware.dock.cad.generate_rev_a import REV_A


REPO_ROOT = Path(__file__).resolve().parents[1]

# Hand-worked two-term stack. Clearance = outer - inner, so the clearance closes
# when outer shrinks (its minus tolerance) and when inner grows (its plus).
HAND_OUTER = Dimension("hand_outer", 10.0, 0.20, 0.10, "machined", "hand example")
HAND_INNER = Dimension("hand_inner", 4.0, 0.30, 0.05, "machined", "hand example")
HAND_STACK = Stack(
    name="hand_worked_example",
    description="Two-term stack used to pin the sign convention.",
    contributors=((HAND_OUTER, 1), (HAND_INNER, -1)),
    minimum_mm=1.0,
    minimum_rationale="Arbitrary minimum for the worked example.",
    critical=False,
)


class ToleranceModelTests(unittest.TestCase):
    def test_stack_definitions_are_structurally_valid(self) -> None:
        self.assertEqual(validate_stacks(), ())

    def test_nominals_track_the_rev_a_cad(self) -> None:
        expected = {
            "funnel_throat_radius": REV_A.funnel_throat_diameter_mm / 2.0,
            "probe_head_max_radius": REV_A.probe_head_diameter_mm / 2.0,
            "probe_head_bore_radius": REV_A.probe_head_bore_diameter_mm / 2.0,
            "probe_mast_radius": REV_A.probe_mast_diameter_mm / 2.0,
            "keeper_slot_half_width": REV_A.keeper_slot_width_mm / 2.0,
            "keeper_open_travel": REV_A.keeper_nominal_open_travel_mm,
        }
        found = {dimension.name: dimension.nominal_mm for dimension in DIMENSIONS}
        for name, nominal in expected.items():
            with self.subTest(dimension=name):
                self.assertAlmostEqual(found[name], nominal, places=9)

    def test_sign_convention_matches_hand_computation(self) -> None:
        self.assertAlmostEqual(nominal_mm(HAND_STACK), 6.0, places=9)
        # Closing direction: outer at minimum (-0.10) and inner at maximum (+0.30).
        self.assertAlmostEqual(worst_case_mm(HAND_STACK), 5.60, places=9)
        self.assertAlmostEqual(
            rss_mm(HAND_STACK), 6.0 - math.sqrt(0.10**2 + 0.30**2), places=9
        )

        result = evaluate_stack(HAND_STACK)
        self.assertAlmostEqual(result.worst_case_margin_mm, 4.60, places=9)
        self.assertTrue(result.passes_worst_case)

        # The opening direction is the mirror image: outer at max, inner at min.
        opening = HAND_OUTER.max_mm - HAND_INNER.min_mm
        self.assertAlmostEqual(opening, 6.25, places=9)
        self.assertEqual(dominant_contributor(HAND_STACK), ("hand_inner", 0.30))

    def test_rss_is_never_worse_than_the_worst_case(self) -> None:
        for stack in STACKS + (HAND_STACK,):
            with self.subTest(stack=stack.name):
                self.assertGreaterEqual(rss_mm(stack), worst_case_mm(stack))
                self.assertLessEqual(rss_mm(stack), nominal_mm(stack))

    def test_fdm_tolerance_grows_with_feature_size(self) -> None:
        self.assertEqual(fdm_tolerance_mm(12.0), FDM_TOLERANCE_SMALL_MM)
        self.assertEqual(fdm_tolerance_mm(49.9), FDM_TOLERANCE_SMALL_MM)
        self.assertEqual(fdm_tolerance_mm(50.0), FDM_TOLERANCE_LARGE_MM)
        self.assertEqual(fdm_tolerance_mm(180.0), FDM_TOLERANCE_LARGE_MM)

    def test_printed_internal_features_carry_the_undersize_asymmetry(self) -> None:
        self.assertAlmostEqual(KEEPER_SLOT_HALF_WIDTH.plus_tol_mm, 0.15, places=9)
        self.assertAlmostEqual(KEEPER_SLOT_HALF_WIDTH.minus_tol_mm, 0.25, places=9)


class CaptureChainVerdictTests(unittest.TestCase):
    def test_entry_clearance_passes_worst_case(self) -> None:
        result = evaluate_stack(stack_by_name("probe_head_entry_clearance"))
        self.assertFalse(result.critical)
        self.assertTrue(result.passes_worst_case)
        self.assertAlmostEqual(result.worst_case_mm, 1.60, places=9)
        self.assertGreater(result.worst_case_margin_mm, 0.0)

    def test_open_findings_are_exactly_the_stacks_that_fail_worst_case(self) -> None:
        failing = {
            result.name for result in evaluate_all() if not result.passes_worst_case
        }
        self.assertEqual(failing, {finding.stack for finding in OPEN_FINDINGS})

    def test_chain_verdict_fails_while_findings_are_open(self) -> None:
        verdict = chain_verdict()
        self.assertFalse(verdict.passed)
        self.assertEqual(
            set(verdict.critical_failures),
            {
                "keeper_slot_mast_clearance",
                "keeper_head_overlap",
                "keeper_release_clearance",
            },
        )
        self.assertEqual(verdict.advisory_failures, ())

    def test_retention_ledge_is_undersized_in_the_geometry_itself(self) -> None:
        # Rev-A's ledge is set by the head's Ø6 lower cylinder against the
        # 4.2 mm slot: 0.9 mm per side, 0.8 mm after the head-to-mast float.
        result = evaluate_stack(KEEPER_HEAD_OVERLAP)
        self.assertTrue(result.critical)
        self.assertAlmostEqual(result.nominal_mm, 0.80, places=9)
        self.assertAlmostEqual(result.worst_case_mm, -0.025, places=9)
        self.assertFalse(result.passes_worst_case)
        self.assertFalse(result.passes_rss)

        # Not an artifact of the assumed lateral offset: delete that
        # contributor entirely and the ledge is still short of the minimum.
        without_offset = Stack(
            name="keeper_head_overlap_perfect_datum",
            description="Overlap with a perfect lateral datum.",
            contributors=tuple(
                (dimension, sign)
                for dimension, sign in KEEPER_HEAD_OVERLAP.contributors
                if dimension.name != "seated_probe_lateral_offset"
            ),
            minimum_mm=KEEPER_HEAD_OVERLAP.minimum_mm,
            minimum_rationale=KEEPER_HEAD_OVERLAP.minimum_rationale,
            critical=True,
        )
        self.assertAlmostEqual(worst_case_mm(without_offset), 0.325, places=9)
        self.assertFalse(evaluate_stack(without_offset).passes_worst_case)

    def test_slot_clearance_failure_is_driven_by_the_lateral_assumption(self) -> None:
        result = evaluate_stack(SLOT_MAST_CLEARANCE)
        self.assertAlmostEqual(result.nominal_mm, 0.60, places=9)
        self.assertAlmostEqual(result.worst_case_mm, -0.025, places=9)
        self.assertFalse(result.passes_worst_case)
        self.assertEqual(
            dominant_contributor(SLOT_MAST_CLEARANCE)[0],
            "seated_probe_lateral_offset",
        )

        without_offset = Stack(
            name="keeper_slot_mast_clearance_perfect_datum",
            description="Slot clearance with a perfect lateral datum.",
            contributors=tuple(
                (dimension, sign)
                for dimension, sign in SLOT_MAST_CLEARANCE.contributors
                if dimension.name != "seated_probe_lateral_offset"
            ),
            minimum_mm=SLOT_MAST_CLEARANCE.minimum_mm,
            minimum_rationale=SLOT_MAST_CLEARANCE.minimum_rationale,
            critical=True,
        )
        self.assertAlmostEqual(worst_case_mm(without_offset), 0.325, places=9)
        self.assertTrue(evaluate_stack(without_offset).passes_worst_case)

    def test_keeper_release_clearance_is_negative_at_nominal(self) -> None:
        result = evaluate_stack(stack_by_name("keeper_release_clearance"))
        self.assertTrue(result.critical)
        # 11.0 mm of declared travel against 8.0 mm of tine reach plus a
        # 6.0 mm head radius: the keeper uncovers the mast, not the head.
        self.assertAlmostEqual(result.nominal_mm, -3.0, places=9)
        self.assertAlmostEqual(result.worst_case_mm, -3.85, places=9)
        self.assertLess(result.rss_mm, 0.0)
        self.assertGreater(EXACT_RELEASE_TRAVEL_MM, REV_A.keeper_nominal_open_travel_mm)
        self.assertAlmostEqual(EXACT_RELEASE_TRAVEL_MM, 13.6205, places=4)


class StackValidationTests(unittest.TestCase):
    def test_fabricated_failing_stack_is_detected(self) -> None:
        ledge = Dimension("fabricated_ledge", 1.0, 0.1, 0.1, "FDM printed", "test")
        offset = Dimension("fabricated_offset", 0.9, 0.1, 0.1, "FDM printed", "test")
        stack = Stack(
            name="fabricated_failure",
            description="Deliberately short stack.",
            contributors=((ledge, 1), (offset, -1)),
            minimum_mm=0.2,
            minimum_rationale="Deliberately unreachable minimum.",
            critical=True,
        )
        result = evaluate_stack(stack)
        self.assertAlmostEqual(result.nominal_mm, 0.10, places=9)
        self.assertAlmostEqual(result.worst_case_mm, -0.10, places=9)
        self.assertFalse(result.passes_worst_case)
        self.assertFalse(result.passes_rss)
        self.assertLess(result.worst_case_margin_mm, 0.0)
        self.assertEqual(
            chain_verdict((result,)).critical_failures, ("fabricated_failure",)
        )

    def test_an_unrecorded_failing_stack_is_a_registry_error(self) -> None:
        # The record of open findings has to track the arithmetic: a stack that
        # stops closing must show up as an error rather than as silence.
        broken = STACKS + (
            Stack(
                name="unrecorded_failure",
                description="A failing stack with no finding written for it.",
                contributors=KEEPER_HEAD_OVERLAP.contributors,
                minimum_mm=KEEPER_HEAD_OVERLAP.minimum_mm,
                minimum_rationale=KEEPER_HEAD_OVERLAP.minimum_rationale,
                critical=True,
            ),
        )
        errors = validate_stacks(broken, OPEN_FINDINGS)
        self.assertIn(
            "unrecorded_failure fails worst case with no open finding recorded",
            errors,
        )

    def test_a_stale_finding_is_a_registry_error(self) -> None:
        stale = OPEN_FINDINGS + (
            OpenFinding(
                stack="probe_head_entry_clearance",
                summary="Stale: this stack passes worst case today.",
                driver="none",
                options=(),
            ),
        )
        self.assertIn(
            "probe_head_entry_clearance is recorded as an open finding but now passes",
            validate_stacks(STACKS, stale),
        )

    def test_every_stack_documents_its_minimum(self) -> None:
        for stack in STACKS:
            with self.subTest(stack=stack.name):
                self.assertGreater(stack.minimum_mm, 0.0)
                self.assertIn("Engineering target", stack.minimum_rationale)
                self.assertGreater(len(stack.description), 40)

    def test_sign_must_be_plus_or_minus_one(self) -> None:
        dimension = Dimension("a", 1.0, 0.1, 0.1, "machined", "test")
        other = Dimension("b", 0.5, 0.1, 0.1, "machined", "test")
        with self.assertRaises(ValueError):
            Stack("bad_sign", "", ((dimension, 0), (other, -1)), 0.1, "", False)
        with self.assertRaises(ValueError):
            Stack("bad_sign", "", ((dimension, 2), (other, -1)), 0.1, "", False)

    def test_malformed_stacks_are_rejected(self) -> None:
        dimension = Dimension("a", 1.0, 0.1, 0.1, "machined", "test")
        other = Dimension("b", 0.5, 0.1, 0.1, "machined", "test")
        with self.assertRaises(ValueError):
            Stack("too_short", "", ((dimension, 1),), 0.1, "", False)
        with self.assertRaises(ValueError):
            Stack("duplicate", "", ((dimension, 1), (dimension, -1)), 0.1, "", False)
        with self.assertRaises(ValueError):
            Stack("negative_min", "", ((dimension, 1), (other, -1)), -0.1, "", False)

    def test_tolerances_are_magnitudes(self) -> None:
        with self.assertRaises(ValueError):
            Dimension("negative", 1.0, -0.1, 0.1, "machined", "test")


class AsBuiltRecordTests(unittest.TestCase):
    MEASURED = {
        "probe_head_seat_diameter": 6.20,
        "keeper_slot_width": 4.05,
        "probe_head_bore_diameter": 3.05,
        "probe_mast_diameter": 3.00,
        "seated_probe_lateral_offset": 0.08,
    }

    def test_measurements_convert_to_stack_dimensions(self) -> None:
        values = measured_dimensions(self.MEASURED)
        self.assertAlmostEqual(values["probe_head_seat_radius"], 3.10, places=9)
        self.assertAlmostEqual(values["keeper_slot_half_width"], 2.025, places=9)
        # The head-to-mast float is derived from the measured bore and mast.
        self.assertAlmostEqual(values["probe_head_to_mast_float"], 0.025, places=9)

    def test_a_measured_article_can_close_a_stack_the_prediction_cannot(self) -> None:
        article = as_built(KEEPER_HEAD_OVERLAP, measured_dimensions(self.MEASURED))
        result = evaluate_stack(article)
        # 3.10 seat - 2.025 slot - 0.025 float - 0.08 offset.
        self.assertAlmostEqual(result.nominal_mm, 0.97, places=9)
        # Four contributors at one caliper resolution each, except the derived
        # head-to-mast float, which carries two readings' worth.
        self.assertAlmostEqual(
            result.worst_case_mm, 0.97 - 5 * CALIPER_UNCERTAINTY_MM, places=9
        )
        self.assertTrue(result.passes_worst_case)
        # The predicted stack for the same geometry does not close.
        self.assertFalse(evaluate_stack(KEEPER_HEAD_OVERLAP).passes_worst_case)

    def test_derived_fits_carry_both_measurements_uncertainty(self) -> None:
        article = as_built(KEEPER_HEAD_OVERLAP, measured_dimensions(self.MEASURED))
        bands = {
            dimension.name: dimension.plus_tol_mm
            for dimension, _ in article.contributors
        }
        self.assertIn("probe_head_to_mast_float", DERIVED_DIMENSIONS)
        self.assertAlmostEqual(
            bands["probe_head_to_mast_float"], 2 * CALIPER_UNCERTAINTY_MM, places=9
        )
        self.assertAlmostEqual(
            bands["probe_head_seat_radius"], CALIPER_UNCERTAINTY_MM, places=9
        )

    def test_unmeasured_dimensions_keep_their_predicted_tolerance(self) -> None:
        partial = as_built(KEEPER_HEAD_OVERLAP, {"probe_head_seat_radius": 3.00})
        # Only one contributor tightened, so the stack cannot improve past the
        # prediction by more than that contributor's tolerance.
        self.assertGreater(worst_case_mm(partial), worst_case_mm(KEEPER_HEAD_OVERLAP))
        self.assertLess(worst_case_mm(partial), 0.5)

    def test_unknown_measurements_are_rejected(self) -> None:
        with self.assertRaises(KeyError):
            measured_dimensions({"funnel_colour": 1.0})
        with self.assertRaises(KeyError):
            as_built(KEEPER_HEAD_OVERLAP, {"not_a_dimension": 1.0})

    def test_template_header_matches_the_documented_schema(self) -> None:
        path = REPO_ROOT / "hardware" / "dock" / "as-built-template.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(tuple(lines[0].split(",")), AS_BUILT_COLUMNS)
        # Header only: no fabricated measurements ship with the template.
        self.assertEqual([line for line in lines[1:] if line.strip()], [])

    def test_every_as_built_feature_maps_to_a_stack_dimension(self) -> None:
        dimensions = {
            dimension.name
            for stack in STACKS
            for dimension, _ in stack.contributors
        }
        mapped = {feature.dimension for feature in AS_BUILT_FEATURES}
        # Bore and mast feed the derived float rather than a stack directly.
        self.assertTrue(dimensions <= mapped | {"probe_head_to_mast_float"})
        self.assertIn("probe_head_bore_radius", mapped)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_json_serialisable_and_reports_the_findings(self) -> None:
        payload = json.loads(json.dumps(snapshot()))
        self.assertTrue(payload["valid"])
        self.assertFalse(payload["verdict"]["passed"])
        self.assertEqual(len(payload["stacks"]), len(STACKS))
        self.assertEqual(len(payload["open_findings"]), len(OPEN_FINDINGS))
        self.assertEqual(payload["as_built_columns"], list(AS_BUILT_COLUMNS))
        for stack in payload["stacks"]:
            self.assertIn("minimum_rationale", stack)
            self.assertIn("dominant_contributor", stack)


if __name__ == "__main__":
    unittest.main()
