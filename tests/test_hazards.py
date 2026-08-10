import unittest
from dataclasses import replace

from aiur.hazards import (
    ACCEPTANCE_THRESHOLD,
    HAZARDS,
    AcceptanceAuthority,
    Hazard,
    HazardStatus,
    Probability,
    ResidualAcceptance,
    RiskLevel,
    Severity,
    acceptance_required,
    hazard_by_id,
    open_items,
    required_authority,
    risk_code,
    risk_level,
    snapshot,
    validate_hazards,
)


def signed(**overrides: str) -> ResidualAcceptance:
    """A complete acceptance record, for testing the machinery only.

    Deliberately fictional: no acceptance in ``HAZARDS`` is signed, and the
    name below exists so the validator can be shown accepting a good record
    without a fabricated signature entering the registry.
    """

    fields = {
        "accepted_by": "A. Example",
        "role": "Safety Observer",
        "date": "2026-08-08",
        "scope": "indoor tethered P0 single-fault regime",
        "rationale": "test fixture; not a real acceptance",
    }
    fields.update(overrides)
    return ResidualAcceptance(**fields)


def sample_hazard(**overrides: object) -> Hazard:
    """A structurally valid hazard used to exercise one rule at a time."""

    fields: dict[str, object] = {
        "id": "HAZ-900",
        "title": "sample",
        "description": "sample hazard for validator tests",
        "cause": "sample cause",
        "effect": "sample effect",
        "severity": Severity.MARGINAL,
        "probability": Probability.OCCASIONAL,
        "mitigations": ("sample mitigation",),
        "verification": "P0-A criterion structural_failures",
        "residual_severity": Severity.MARGINAL,
        "residual_probability": Probability.REMOTE,
        "acceptance": None,
        "status": HazardStatus.MITIGATION_SELECTED,
    }
    fields.update(overrides)
    return Hazard(**fields)  # type: ignore[arg-type]


class RiskMatrixTests(unittest.TestCase):
    """Table III spot-checks against MIL-STD-882E w/Change 1, doc p.13."""

    def test_high_cells(self) -> None:
        for code in ("1A", "1B", "1C", "2A", "2B"):
            with self.subTest(code=code):
                self.assertIs(self._level(code), RiskLevel.HIGH)

    def test_serious_cells(self) -> None:
        for code in ("1D", "2C", "3A", "3B"):
            with self.subTest(code=code):
                self.assertIs(self._level(code), RiskLevel.SERIOUS)

    def test_medium_cells(self) -> None:
        for code in ("1E", "2D", "2E", "3C", "3D", "3E", "4A", "4B"):
            with self.subTest(code=code):
                self.assertIs(self._level(code), RiskLevel.MEDIUM)

    def test_low_cells(self) -> None:
        for code in ("4C", "4D", "4E"):
            with self.subTest(code=code):
                self.assertIs(self._level(code), RiskLevel.LOW)

    def test_probability_f_row_is_eliminated_for_every_severity(self) -> None:
        for severity in Severity:
            with self.subTest(severity=severity):
                self.assertIs(
                    risk_level(severity, Probability.ELIMINATED),
                    RiskLevel.ELIMINATED,
                )

    def test_every_cell_of_the_matrix_is_defined(self) -> None:
        for severity in Severity:
            for probability in Probability:
                with self.subTest(code=risk_code(severity, probability)):
                    self.assertIsInstance(risk_level(severity, probability), RiskLevel)

    def test_risk_code_is_the_standard_rac_spelling(self) -> None:
        self.assertEqual(risk_code(Severity.CATASTROPHIC, Probability.FREQUENT), "1A")
        self.assertEqual(risk_code(Severity.CRITICAL, Probability.OCCASIONAL), "2C")

    def test_verbatim_table_text_is_carried_with_the_levels(self) -> None:
        self.assertIn(
            "permanent total disability",
            Severity.CATASTROPHIC.mishap_result_criteria,
        )
        self.assertEqual(
            Probability.OCCASIONAL.specific_individual_item,
            "Likely to occur sometime in the life of an item.",
        )

    @staticmethod
    def _level(code: str) -> RiskLevel:
        return risk_level(Severity(int(code[0])), Probability(code[1]))


class AcceptanceLadderTests(unittest.TestCase):
    def test_authority_escalates_with_risk(self) -> None:
        self.assertIs(
            required_authority(RiskLevel.LOW),
            AcceptanceAuthority.TEST_CONDUCTOR,
        )
        self.assertIs(
            required_authority(RiskLevel.MEDIUM),
            AcceptanceAuthority.SAFETY_OBSERVER_AND_TEST_CONDUCTOR,
        )
        self.assertIs(
            required_authority(RiskLevel.SERIOUS),
            AcceptanceAuthority.PROGRAM_LEAD,
        )
        self.assertIs(
            required_authority(RiskLevel.HIGH),
            AcceptanceAuthority.NOT_ACCEPTABLE,
        )

    def test_acceptance_is_required_only_above_low(self) -> None:
        self.assertIs(ACCEPTANCE_THRESHOLD, RiskLevel.LOW)
        self.assertFalse(acceptance_required(RiskLevel.ELIMINATED))
        self.assertFalse(acceptance_required(RiskLevel.LOW))
        self.assertTrue(acceptance_required(RiskLevel.MEDIUM))
        self.assertTrue(acceptance_required(RiskLevel.SERIOUS))


class ValidatorTests(unittest.TestCase):
    def test_the_sample_hazard_is_itself_valid(self) -> None:
        self.assertEqual(validate_hazards((sample_hazard(),)), ())

    def test_anonymous_acceptance_is_rejected(self) -> None:
        for field in ("accepted_by", "role", "date", "scope", "rationale"):
            with self.subTest(missing=field):
                hazard = sample_hazard(acceptance=signed(**{field: "   "}))
                errors = validate_hazards((hazard,))
                self.assertTrue(
                    any(f"no {field}" in error for error in errors),
                    f"missing {field} was not reported: {errors}",
                )

    def test_a_properly_signed_acceptance_validates(self) -> None:
        hazard = sample_hazard(acceptance=signed())
        self.assertEqual(validate_hazards((hazard,)), ())
        self.assertEqual(validate_hazards((hazard,), require_acceptance=True), ())
        self.assertEqual(open_items((hazard,)), ())

    def test_acceptance_date_must_be_iso(self) -> None:
        hazard = sample_hazard(acceptance=signed(date="8 August 2026"))
        errors = validate_hazards((hazard,))
        self.assertTrue(any("not an ISO-8601 date" in error for error in errors))

    def test_high_residual_cannot_be_accepted(self) -> None:
        hazard = sample_hazard(
            severity=Severity.CATASTROPHIC,
            probability=Probability.FREQUENT,
            residual_severity=Severity.CATASTROPHIC,
            residual_probability=Probability.PROBABLE,
            acceptance=signed(role="Program Lead"),
        )
        self.assertIs(hazard.residual_risk, RiskLevel.HIGH)
        errors = validate_hazards((hazard,))
        self.assertTrue(
            any("must be mitigated, not accepted" in error for error in errors),
            errors,
        )

    def test_high_residual_blocks_exposure_even_unaccepted(self) -> None:
        hazard = sample_hazard(
            severity=Severity.CATASTROPHIC,
            probability=Probability.FREQUENT,
            residual_severity=Severity.CATASTROPHIC,
            residual_probability=Probability.PROBABLE,
        )
        errors = validate_hazards((hazard,), require_acceptance=True)
        self.assertTrue(any("cannot be exposed to people" in e for e in errors), errors)
        item = open_items((hazard,))[0]
        self.assertIs(item.required_authority, AcceptanceAuthority.NOT_ACCEPTABLE)

    def test_residual_risk_worse_than_initial_is_rejected(self) -> None:
        hazard = sample_hazard(
            severity=Severity.NEGLIGIBLE,
            probability=Probability.REMOTE,
            residual_severity=Severity.CRITICAL,
            residual_probability=Probability.REMOTE,
        )
        errors = validate_hazards((hazard,))
        self.assertTrue(any("residual severity" in error for error in errors), errors)
        self.assertTrue(any("residual risk" in error for error in errors), errors)

    def test_residual_probability_worse_than_initial_is_rejected(self) -> None:
        hazard = sample_hazard(
            probability=Probability.REMOTE,
            residual_probability=Probability.FREQUENT,
        )
        errors = validate_hazards((hazard,))
        self.assertTrue(
            any("residual probability" in error for error in errors), errors
        )

    def test_duplicate_ids_are_rejected(self) -> None:
        pair = (sample_hazard(), sample_hazard())
        self.assertIn("hazard ids must be unique", validate_hazards(pair))

    def test_unsorted_ids_are_rejected(self) -> None:
        pair = (sample_hazard(id="HAZ-902"), sample_hazard(id="HAZ-901"))
        self.assertIn("hazard ids must be listed in sorted order", validate_hazards(pair))

    def test_verification_must_point_at_something_that_exists(self) -> None:
        hazard = sample_hazard(verification="the team will keep an eye on it")
        errors = validate_hazards((hazard,))
        self.assertTrue(any("names no known" in error for error in errors), errors)

    def test_eliminated_status_and_probability_f_must_agree(self) -> None:
        mismatch = sample_hazard(status=HazardStatus.ELIMINATED)
        self.assertTrue(
            any("must be set together" in e for e in validate_hazards((mismatch,)))
        )

        eliminated = sample_hazard(
            residual_probability=Probability.ELIMINATED,
            status=HazardStatus.ELIMINATED,
        )
        self.assertEqual(validate_hazards((eliminated,)), ())
        self.assertEqual(open_items((eliminated,)), ())

    def test_a_mitigated_hazard_needs_a_mitigation(self) -> None:
        hazard = sample_hazard(mitigations=())
        errors = validate_hazards((hazard,))
        self.assertTrue(any("with no mitigation" in error for error in errors), errors)

    def test_empty_required_text_is_rejected(self) -> None:
        hazard = sample_hazard(cause="  ")
        self.assertIn("HAZ-900 has an empty cause", validate_hazards((hazard,)))


class RegistryTests(unittest.TestCase):
    def test_registry_is_structurally_valid(self) -> None:
        self.assertEqual(validate_hazards(), ())

    def test_registry_covers_the_expected_hazard_count(self) -> None:
        self.assertGreaterEqual(len(HAZARDS), 10)

    def test_no_hazard_carries_a_high_residual(self) -> None:
        for hazard in HAZARDS:
            with self.subTest(hazard=hazard.id):
                self.assertIsNot(hazard.residual_risk, RiskLevel.HIGH)

    def test_the_double_fault_residual_is_logged_and_unsigned(self) -> None:
        """Twin finding 5 is in the log, and nobody has signed for it.

        This is the honest state of the program: the acceptance machinery
        exists, the residual is named, and the signature is missing.  If
        this test ever fails because ``acceptance`` became non-None, a
        human made a decision and this test should be updated to check that
        decision's scope, not deleted.
        """

        hazard = hazard_by_id("HAZ-001")
        self.assertIn("empty dock", hazard.title)
        self.assertTrue(acceptance_required(hazard.residual_risk))
        self.assertIsNone(hazard.acceptance)
        self.assertFalse(hazard.is_accepted)
        self.assertIn("HAZ-001", [item.hazard_id for item in open_items()])

    def test_the_single_source_navigation_bias_residual_is_logged(self) -> None:
        hazard = hazard_by_id("HAZ-002")
        self.assertIn("SIL-005", hazard.verification)
        self.assertTrue(acceptance_required(hazard.residual_risk))
        self.assertIsNone(hazard.acceptance)

    def test_registry_currently_has_no_signed_residuals(self) -> None:
        """No fabricated sign-offs are committed."""

        self.assertEqual([h.id for h in HAZARDS if h.is_accepted], [])

    def test_pre_exposure_check_currently_fails_for_every_open_residual(self) -> None:
        """CI proves the residuals are unaccepted rather than assuming it."""

        needing = [h.id for h in HAZARDS if acceptance_required(h.residual_risk)]
        self.assertTrue(needing)

        errors = validate_hazards(require_acceptance=True)
        self.assertEqual(len(errors), len(needing))
        for hazard_id in needing:
            with self.subTest(hazard=hazard_id):
                self.assertTrue(any(error.startswith(hazard_id) for error in errors))

        self.assertEqual([item.hazard_id for item in open_items()], needing)

    def test_low_residual_needs_no_acceptance(self) -> None:
        low = [h for h in HAZARDS if h.residual_risk is RiskLevel.LOW]
        self.assertTrue(low, "the log should contain at least one LOW residual")
        for hazard in low:
            with self.subTest(hazard=hazard.id):
                self.assertNotIn(hazard.id, [i.hazard_id for i in open_items()])

    def test_signing_one_registry_hazard_clears_only_that_open_item(self) -> None:
        """The machinery works end to end without committing a signature."""

        hazard = hazard_by_id("HAZ-001")
        signed_registry = tuple(
            replace(h, acceptance=signed()) if h.id == hazard.id else h
            for h in HAZARDS
        )
        self.assertEqual(validate_hazards(signed_registry), ())
        remaining = [item.hazard_id for item in open_items(signed_registry)]
        self.assertNotIn("HAZ-001", remaining)
        self.assertEqual(len(remaining), len(open_items()) - 1)

    def test_every_hazard_mitigation_is_verified_by_something_named(self) -> None:
        for hazard in HAZARDS:
            with self.subTest(hazard=hazard.id):
                self.assertTrue(hazard.mitigations)
                self.assertTrue(hazard.verification.strip())

    def test_unknown_hazard_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            hazard_by_id("HAZ-000")

    def test_snapshot_reports_both_validation_modes(self) -> None:
        data = snapshot()
        self.assertTrue(data["valid"])
        self.assertEqual(data["errors"], [])
        self.assertTrue(data["pre_exposure_errors"])
        self.assertEqual(data["profile"]["accepted"], 0)
        self.assertEqual(data["matrix"]["C"]["2"], "serious")


if __name__ == "__main__":
    unittest.main()
