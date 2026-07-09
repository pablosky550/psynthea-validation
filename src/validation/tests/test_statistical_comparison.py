"""
Tests for module-level statistical comparison orchestration.
"""

from __future__ import annotations

import pandas as pd

from validation.comparison.module_validation import ModuleValidationStatus
from validation.comparison.statistical_comparison import compare_module_statistics
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
            {ENCOUNTER_PATIENT_COLUMN: "P1", ENCOUNTER_CLASS_COLUMN: "outpatient", "ENCOUNTER": "E2"},
            {ENCOUNTER_PATIENT_COLUMN: "P2", ENCOUNTER_CLASS_COLUMN: "emergency", "ENCOUNTER": "E3"},
        ]
    )


def _conditions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "59621000",
                CONDITION_DESCRIPTION_COLUMN: "Hypertension",
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
                "ENCOUNTER": "E3",
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
                PROCEDURE_DESCRIPTION_COLUMN: "Assessment of health needs",
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
                "ENCOUNTER": "E3",
            },
        ]
    )


def _empty_like(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _cohort(*, source: str, conditions: pd.DataFrame | None = None) -> ValidationCohort:
    return ValidationCohort(
        source=source,
        patients=_patients(),
        encounters=_encounters(),
        conditions=_conditions() if conditions is None else conditions,
        medications=_medications(),
        procedures=_procedures(),
        observations=_observations(),
    )


def test_statistical_comparison_runs_for_comparable_module() -> None:
    result = compare_module_statistics(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA),
        expected_condition_terms=["hypertension"],
        top_n_codes=5,
    )

    summary = result.summary.iloc[0]

    assert summary["validation_status"] == ModuleValidationStatus.COMPARABLE.value
    assert bool(summary["valid_for_statistical_comparison"])
    assert not result.continuous_tests.empty
    assert not result.categorical_tests.empty
    assert not result.prevalence_tests.empty
    assert not result.distribution_tests.empty
    assert "adjusted_p_value" in result.prevalence_tests.columns


def test_statistical_comparison_skips_non_comparable_module() -> None:
    empty_conditions = _empty_like(
        [CONDITION_PATIENT_COLUMN, CONDITION_CODE_COLUMN, CONDITION_DESCRIPTION_COLUMN]
    )

    result = compare_module_statistics(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA, conditions=empty_conditions),
        expected_condition_terms=["hypertension"],
        top_n_codes=5,
    )

    summary = result.summary.iloc[0]

    assert summary["validation_status"] == ModuleValidationStatus.PSYNTHEA_FUNCTIONAL_FAILURE.value
    assert bool(summary["skipped"])
    assert result.continuous_tests.empty
    assert result.prevalence_tests.empty


def test_statistical_comparison_supports_partially_comparable_modules() -> None:
    result = compare_module_statistics(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA),
        expected_condition_terms=["hypertension"],
        top_n_codes=1,
    )

    assert result.summary.iloc[0]["validation_status"] == ModuleValidationStatus.COMPARABLE.value
    assert set(result.distribution_tests["domain"]).issuperset({"conditions"})


def test_statistical_comparison_applies_fdr_to_prevalence_tests() -> None:
    result = compare_module_statistics(
        module_name="hypertension",
        synthea_cohort=_cohort(source=SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(source=SOURCE_PSYNTHEA),
        expected_condition_terms=["hypertension"],
        top_n_codes=5,
    )

    assert "adjusted_p_value" in result.prevalence_tests.columns
    assert "significant_after_fdr" in result.prevalence_tests.columns
    assert result.prevalence_tests["adjusted_p_value"].notna().all()
