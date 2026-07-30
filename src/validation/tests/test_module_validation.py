"""
Tests for independent-module functional comparability classification.
"""

from __future__ import annotations

import pandas as pd

import validation.comparison.module_validation as module_validation
from validation.comparison.module_validation import (
    ModuleValidationIssueType,
    ModuleValidationStatus,
    validate_independent_module,
)
from validation.constants import (
    AGE_COLUMN,
    CONDITION_CODE_COLUMN,
    CONDITION_DESCRIPTION_COLUMN,
    CONDITION_PATIENT_COLUMN,
    CONDITION_START_COLUMN,
    CONDITION_STOP_COLUMN,
    ENCOUNTER_CLASS_COLUMN,
    ENCOUNTER_PATIENT_COLUMN,
    MEDICATION_CODE_COLUMN,
    MEDICATION_DESCRIPTION_COLUMN,
    MEDICATION_DISPENSES_COLUMN,
    MEDICATION_PATIENT_COLUMN,
    MEDICATION_START_COLUMN,
    MEDICATION_STOP_COLUMN,
    OBSERVATION_CODE_COLUMN,
    OBSERVATION_DESCRIPTION_COLUMN,
    OBSERVATION_DATE_COLUMN,
    OBSERVATION_PATIENT_COLUMN,
    OBSERVATION_UNITS_COLUMN,
    OBSERVATION_VALUE_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    PATIENT_GENDER_COLUMN,
    PATIENT_ID_COLUMN,
    PROCEDURE_BASE_COST_COLUMN,
    PROCEDURE_CODE_COLUMN,
    PROCEDURE_DESCRIPTION_COLUMN,
    PROCEDURE_PATIENT_COLUMN,
    PROCEDURE_START_COLUMN,
    PROCEDURE_STOP_COLUMN,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.models import ValidationCohort


def _patients() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {PATIENT_ID_COLUMN: "P1", PATIENT_GENDER_COLUMN: "M", PATIENT_BIRTHDATE_COLUMN: "1980-01-01", AGE_COLUMN: 44},
            {PATIENT_ID_COLUMN: "P2", PATIENT_GENDER_COLUMN: "F", PATIENT_BIRTHDATE_COLUMN: "1990-01-01", AGE_COLUMN: 34},
            {PATIENT_ID_COLUMN: "P3", PATIENT_GENDER_COLUMN: "F", PATIENT_BIRTHDATE_COLUMN: "1975-01-01", AGE_COLUMN: 49},
        ]
    )


def _encounters() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {ENCOUNTER_PATIENT_COLUMN: "P1", ENCOUNTER_CLASS_COLUMN: "ambulatory", "ENCOUNTER": "E1"},
            {ENCOUNTER_PATIENT_COLUMN: "P2", ENCOUNTER_CLASS_COLUMN: "emergency", "ENCOUNTER": "E2"},
        ]
    )


def _conditions(code: str = "59621000", description: str = "Hypertension") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: code,
                CONDITION_DESCRIPTION_COLUMN: description,
                CONDITION_START_COLUMN: "2015-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
                "ENCOUNTER": "E1",
            },
            {
                CONDITION_PATIENT_COLUMN: "P2",
                CONDITION_CODE_COLUMN: "195967001",
                CONDITION_DESCRIPTION_COLUMN: "Asthma",
                CONDITION_START_COLUMN: "2016-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
                "ENCOUNTER": "E2",
            },
        ]
    )


def _medications() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                MEDICATION_PATIENT_COLUMN: "P1",
                MEDICATION_CODE_COLUMN: "314076",
                MEDICATION_DESCRIPTION_COLUMN: "Lisinopril",
                MEDICATION_START_COLUMN: "2015-01-02",
                MEDICATION_STOP_COLUMN: pd.NA,
                MEDICATION_DISPENSES_COLUMN: 12,
                "ENCOUNTER": "E1",
            }
        ]
    )


def _procedures() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                PROCEDURE_PATIENT_COLUMN: "P1",
                PROCEDURE_CODE_COLUMN: "710824005",
                PROCEDURE_DESCRIPTION_COLUMN: "Referral to specialist",
                PROCEDURE_START_COLUMN: "2015-01-03",
                PROCEDURE_STOP_COLUMN: "2015-01-03",
                PROCEDURE_BASE_COST_COLUMN: 100.0,
                "ENCOUNTER": "E1",
            }
        ]
    )


def _observations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                OBSERVATION_PATIENT_COLUMN: "P1",
                OBSERVATION_CODE_COLUMN: "8480-6",
                OBSERVATION_DESCRIPTION_COLUMN: "Systolic Blood Pressure",
                OBSERVATION_DATE_COLUMN: "2015-01-01",
                OBSERVATION_VALUE_COLUMN: "150",
                OBSERVATION_UNITS_COLUMN: "mmHg",
                "ENCOUNTER": "E1",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P2",
                OBSERVATION_CODE_COLUMN: "8310-5",
                OBSERVATION_DESCRIPTION_COLUMN: "Body temperature",
                OBSERVATION_DATE_COLUMN: "2016-01-01",
                OBSERVATION_VALUE_COLUMN: "37.2",
                OBSERVATION_UNITS_COLUMN: "Cel",
                "ENCOUNTER": "E2",
            },
        ]
    )


def _empty_like(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _cohort(
    *,
    source: str,
    conditions: pd.DataFrame | None = None,
    observations: pd.DataFrame | None = None,
) -> ValidationCohort:
    return ValidationCohort(
        source=source,
        patients=_patients(),
        encounters=_encounters(),
        conditions=_conditions() if conditions is None else conditions,
        medications=_medications(),
        procedures=_procedures(),
        observations=_observations() if observations is None else observations,
    )


def test_module_validation_marks_comparable_module() -> None:
    result = validate_independent_module(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA),
        expected_condition_terms=["hypertension", "59621000"],
        expected_observation_terms=["blood pressure", "8480-6"],
    )

    summary = result.summary.iloc[0]

    assert summary["status"] == ModuleValidationStatus.COMPARABLE.value
    assert bool(summary["valid_for_comparison"])
    assert result.issues.empty


def test_module_validation_marks_psynthea_functional_failure_when_conditions_empty() -> None:
    empty_conditions = _empty_like(
        [CONDITION_PATIENT_COLUMN, CONDITION_CODE_COLUMN, CONDITION_DESCRIPTION_COLUMN]
    )

    result = validate_independent_module(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA, conditions=empty_conditions),
        expected_condition_terms=["hypertension"],
    )

    summary = result.summary.iloc[0]

    assert summary["status"] == ModuleValidationStatus.PSYNTHEA_FUNCTIONAL_FAILURE.value
    assert not bool(summary["valid_for_comparison"])
    assert ModuleValidationIssueType.MISSING_CORE_CLINICAL_SIGNAL.value in set(result.issues["issue"])


def test_module_validation_marks_reference_empty_when_synthea_has_no_signal() -> None:
    empty_conditions = _empty_like(
        [CONDITION_PATIENT_COLUMN, CONDITION_CODE_COLUMN, CONDITION_DESCRIPTION_COLUMN]
    )

    result = validate_independent_module(
        module_name="rare_module",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA, conditions=empty_conditions),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA),
    )

    assert result.summary.iloc[0]["status"] == ModuleValidationStatus.REFERENCE_EMPTY.value


def test_module_validation_marks_partial_when_optional_observations_empty() -> None:
    empty_observations = _empty_like(
        [OBSERVATION_PATIENT_COLUMN, OBSERVATION_CODE_COLUMN, OBSERVATION_DESCRIPTION_COLUMN]
    )

    result = validate_independent_module(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA, observations=empty_observations),
    )

    assert result.summary.iloc[0]["status"] == ModuleValidationStatus.PARTIALLY_COMPARABLE.value
    assert ModuleValidationIssueType.PSYNTHEA_TABLE_EMPTY.value in set(result.issues["issue"])


def test_module_validation_records_absent_expected_signal_without_false_failure() -> None:
    result = validate_independent_module(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA),
        expected_condition_terms=["nonexistent expected disease"],
    )

    assert result.summary.iloc[0]["status"] == ModuleValidationStatus.COMPARABLE.value

    condition_signal = result.clinical_signal.set_index("domain").loc["conditions"]
    assert condition_signal["expected_signal_detected_synthea"] is False
    assert condition_signal["expected_signal_detected_psynthea"] is False


def test_module_validation_reports_code_similarity_metrics() -> None:
    divergent_conditions = _conditions(code="44054006", description="Diabetes mellitus type 2")

    result = validate_independent_module(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA, conditions=divergent_conditions),
    )

    condition_similarity = result.distributional_similarity.set_index("domain").loc["conditions"]

    assert condition_similarity["jaccard_similarity"] < 1.0
    assert condition_similarity["jensen_shannon_divergence"] >= 0.0


def test_jensen_shannon_divergence_clamps_tiny_negative_roundoff(
    monkeypatch,
) -> None:
    """A tiny negative round-off must not abort the validation pipeline."""

    monkeypatch.setattr(
        module_validation,
        "_kl_divergence",
        lambda distribution, reference: -1e-16,
    )

    result = module_validation._jensen_shannon_divergence(
        {"A": 50, "B": 50},
        {"A": 50, "B": 50},
    )

    assert result == 0.0


def test_jensen_shannon_divergence_rejects_materially_negative_value(
    monkeypatch,
) -> None:
    """Materially negative divergence remains a visible invariant failure."""

    monkeypatch.setattr(
        module_validation,
        "_kl_divergence",
        lambda distribution, reference: -1e-4,
    )

    try:
        module_validation._jensen_shannon_divergence(
            {"A": 50, "B": 50},
            {"A": 50, "B": 50},
        )
    except ValueError as error:
        assert "materially negative" in str(error)
    else:
        raise AssertionError("Expected materially negative divergence to fail")
