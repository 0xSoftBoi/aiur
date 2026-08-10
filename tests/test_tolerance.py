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
from hardware.dock.cad.generate_rev_a import CURRENT, REV_A


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

    def test_nominals_track_the_current_cad_revision(self) -> None:
        """The stack must describe the article that would be built.

        A stack pinned to a superseded revision is worse than no stack: it
        reports margins for geometry nobody is printing.
        """

        expected = {
            "funnel_throat_radius": CURRENT.funnel_throat_diameter_mm / 2.0,
            "probe_head_max_radius": CURRENT.probe_head_diameter_mm / 2.0,
            "probe_head_seat_radius": CURRENT.probe_head_seat_diameter_mm / 2.0,
            "probe_head_bore_radius": CURRENT.probe_head_bore_diameter_mm / 2.0,
            "probe_mast_radius": CURRENT.probe_mast_diameter_mm / 2.0,
            "keeper_slot_half_width": CURRENT.keeper_slot_width_mm / 2.0,
            "keeper_tine_reach": CURRENT.keeper_tine_reach_mm,
            "keeper_open_travel": CURRENT.keeper_open_travel_mm,
        }
        found = {dimension.name: dimension.nominal_mm for dimension in DIMENSIONS}
        for name, nominal in expected.items():
            with self.subTest(dimension=name):
                self.assertAlmostEqual(found[name], nominal, places=9)

    def test_as_built_nominals_track_the_current_cad_revision(self) -> None:
        """The measurement sheet must describe the part that gets printed.

        This is the operator-facing table behind
        hardware/dock/as-built-template.csv.  When it drifted to a superseded
        revision, a technician measuring a *correct* Rev-B seat recorded a
        3.0 mm deviation and the golden-article rules escalated a good
        article to re-qualification.  Stale nominals here fail good hardware,
        which is worse than failing loudly.
        """

        expected = {
            "funnel_throat_diameter": CURRENT.funnel_throat_diameter_mm,
            "probe_head_max_diameter": CURRENT.probe_head_diameter_mm,
            "probe_head_seat_diameter": CURRENT.probe_head_seat_diameter_mm,
            "probe_head_bore_diameter": CURRENT.probe_head_bore_diameter_mm,
            "probe_mast_diameter": CURRENT.probe_mast_diameter_mm,
            "keeper_slot_width": CURRENT.keeper_slot_width_mm,
            "keeper_tine_reach": CURRENT.keeper_tine_reach_mm,
            "keeper_open_travel": CURRENT.keeper_open_travel_mm,
        }
        found = {f.feature: f.nominal_mm for f in AS_BUILT_FEATURES}
        for feature, nominal in expected.items():
            with self.subTest(feature=feature):
                self.assertIn(feature, found)
                self.assertAlmostEqual(found[feature], nominal, places=9)

    def test_every_as_built_feature_is_checked_by_the_guard_above(self) -> None:
        """A new measurement row must not escape the revision check.

        One row legitimately has no CAD counterpart: the seated lateral
        offset is an assembly outcome measured on the built article, not a
        feature anyone prints.  It is exempted by name so the exemption is a
        decision rather than an omission.
        """

        guarded = {
            "funnel_throat_diameter",
            "probe_head_max_diameter",
            "probe_head_seat_diameter",
            "probe_head_bore_diameter",
            "probe_mast_diameter",
            "keeper_slot_width",
            "keeper_tine_reach",
            "keeper_open_travel",
        }
        assembly_only = {"seated_probe_lateral_offset"}
        self.assertEqual(
            {f.feature for f in AS_BUILT_FEATURES}, guarded | assembly_only
        )

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

    def test_chain_verdict_closes_on_the_current_revision(self) -> None:
        verdict = chain_verdict()
        self.assertTrue(verdict.passed, verdict)
        self.assertEqual(verdict.critical_failures, ())
        self.assertEqual(verdict.advisory_failures, ())

    def test_retention_ledge_closes_with_margin(self) -> None:
        # The ledge is set by the head's seat cylinder against the keeper slot.
        # Rev-A used Ø6 against a 4.2 mm slot and went line-to-line at worst
        # case; Rev-B's Ø9 seat against a 5.2 mm slot holds the minimum.
        result = evaluate_stack(KEEPER_HEAD_OVERLAP)
        self.assertTrue(result.critical)
        self.assertAlmostEqual(result.nominal_mm, 1.80, places=9)
        self.assertAlmostEqual(result.worst_case_mm, 0.975, places=9)
        self.assertTrue(result.passes_worst_case)
        self.assertTrue(result.passes_rss)

        # The margin does not depend on the assumed lateral datum: delete that
        # contributor entirely and the ledge only improves.
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
        self.assertAlmostEqual(worst_case_mm(without_offset), 1.325, places=9)
        self.assertTrue(evaluate_stack(without_offset).passes_worst_case)

    def test_slot_clearance_is_still_dominated_by_the_lateral_assumption(self) -> None:
        # It passes now, but the dominant contributor is still the one number
        # nobody has measured, so the margin is only as good as that target.
        result = evaluate_stack(SLOT_MAST_CLEARANCE)
        self.assertAlmostEqual(result.nominal_mm, 1.10, places=9)
        self.assertAlmostEqual(result.worst_case_mm, 0.475, places=9)
        self.assertTrue(result.passes_worst_case)
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
        self.assertAlmostEqual(worst_case_mm(without_offset), 0.825, places=9)
        self.assertTrue(evaluate_stack(without_offset).passes_worst_case)

    def test_keeper_release_clearance_closes_with_margin(self) -> None:
        result = evaluate_stack(stack_by_name("keeper_release_clearance"))
        self.assertTrue(result.critical)
        # 13.0 mm of stroke against 5.0 mm of tine reach plus a 6.0 mm head
        # radius: the keeper now uncovers the head, not just the mast.
        self.assertAlmostEqual(result.nominal_mm, 2.0, places=9)
        self.assertAlmostEqual(result.worst_case_mm, 1.15, places=9)
        self.assertTrue(result.passes_worst_case)
        self.assertGreater(CURRENT.keeper_open_travel_mm, EXACT_RELEASE_TRAVEL_MM)

    def test_rev_a_could_not_release_and_is_kept_as_evidence(self) -> None:
        """Regression: the defect that forced the revision must stay visible.

        Rev-A's tines reached 8.0 mm past the axis, needing 13.62 mm of stroke
        against the 11.0 mm its CAD declared — a number no geometry consumed.
        The keeper uncovered the mast but not the head, so a captured aircraft
        could not be released, and emergency release is a P0-A gate criterion.
        If this ever stops failing, someone has quietly changed Rev-A.
        """

        self.assertGreater(REV_A.release_travel_shortfall_mm(), 0.0)
        self.assertAlmostEqual(REV_A.exact_release_travel_mm(), 13.6205, places=4)
        self.assertLess(CURRENT.release_travel_shortfall_mm(), 0.0)


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
                # A minimum the real geometry cannot meet, so the stack fails
                # by construction rather than by depending on the live numbers.
                minimum_mm=KEEPER_HEAD_OVERLAP.minimum_mm + 10.0,
                minimum_rationale="deliberately unreachable, for this test",
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
        "probe_head_seat_diameter": 9.20,
        "keeper_slot_width": 5.05,
        "probe_head_bore_diameter": 3.05,
        "probe_mast_diameter": 3.00,
        "seated_probe_lateral_offset": 0.08,
    }

    def test_measurements_convert_to_stack_dimensions(self) -> None:
        values = measured_dimensions(self.MEASURED)
        self.assertAlmostEqual(values["probe_head_seat_radius"], 4.60, places=9)
        self.assertAlmostEqual(values["keeper_slot_half_width"], 2.525, places=9)
        # The head-to-mast float is derived from the measured bore and mast.
        self.assertAlmostEqual(values["probe_head_to_mast_float"], 0.025, places=9)

    def test_a_measured_article_beats_the_predicted_stack(self) -> None:
        article = as_built(KEEPER_HEAD_OVERLAP, measured_dimensions(self.MEASURED))
        result = evaluate_stack(article)
        # 4.60 seat - 2.525 slot - 0.025 float - 0.08 offset.
        self.assertAlmostEqual(result.nominal_mm, 1.97, places=9)
        # Four contributors at one caliper resolution each, except the derived
        # head-to-mast float, which carries two readings' worth.
        self.assertAlmostEqual(
            result.worst_case_mm, 1.97 - 5 * CALIPER_UNCERTAINTY_MM, places=9
        )
        self.assertTrue(result.passes_worst_case)
        # Measuring the article buys real margin over the prediction: the
        # predicted stack must carry every assumed process tolerance, while a
        # measured one carries only caliper resolution.
        self.assertGreater(
            result.worst_case_mm, evaluate_stack(KEEPER_HEAD_OVERLAP).worst_case_mm
        )

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
        # Measure the seat undersize; every other contributor keeps its
        # predicted band, so the stack cannot improve past the prediction by
        # more than that one contributor's tolerance.
        partial = as_built(KEEPER_HEAD_OVERLAP, {"probe_head_seat_radius": 4.30})
        predicted = worst_case_mm(KEEPER_HEAD_OVERLAP)
        self.assertLess(worst_case_mm(partial), predicted)
        self.assertGreater(
            worst_case_mm(partial), predicted - 0.20 - CALIPER_UNCERTAINTY_MM
        )

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
        self.assertTrue(payload["verdict"]["passed"])
        self.assertEqual(len(payload["stacks"]), len(STACKS))
        self.assertEqual(len(payload["open_findings"]), len(OPEN_FINDINGS))
        self.assertEqual(payload["as_built_columns"], list(AS_BUILT_COLUMNS))
        for stack in payload["stacks"]:
            self.assertIn("minimum_rationale", stack)
            self.assertIn("dominant_contributor", stack)


if __name__ == "__main__":
    unittest.main()
