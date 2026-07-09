"""
Tests for the Java vs psynthea descriptive comparison layer.

These tests verify the comparison contract using small in-memory cohorts.
They do not execute Synthea or psynthea and do not depend on external CSVs.
"""

from __future__ import annotations

import pandas as pd

from validation.comparison.java_vs_psynthea import compare_java_vs_psynthea
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
            {
                PATIENT_ID_COLUMN: "P1",
                PATIENT_GENDER_COLUMN: "M",
                PATIENT_BIRTHDATE_COLUMN: "1980-01-01",
                AGE_COLUMN: 44,
            },
            {
                PATIENT_ID_COLUMN: "P2",
                PATIENT_GENDER_COLUMN: "F",
                PATIENT_BIRTHDATE_COLUMN: "1990-01-01",
                AGE_COLUMN: 34,
            },
            {
                PATIENT_ID_COLUMN: "P3",
                PATIENT_GENDER_COLUMN: "F",
                PATIENT_BIRTHDATE_COLUMN: "1975-01-01",
                AGE_COLUMN: 49,
            },
        ]
    )


def _encounters() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {ENCOUNTER_PATIENT_COLUMN: "P1", ENCOUNTER_CLASS_COLUMN: "ambulatory"},
            {ENCOUNTER_PATIENT_COLUMN: "P1", ENCOUNTER_CLASS_COLUMN: "outpatient"},
            {ENCOUNTER_PATIENT_COLUMN: "P2", ENCOUNTER_CLASS_COLUMN: "emergency"},
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
            },
            {
                CONDITION_PATIENT_COLUMN: "P2",
                CONDITION_CODE_COLUMN: "195967001",
                CONDITION_DESCRIPTION_COLUMN: "Asthma",
                CONDITION_START_COLUMN: "2016-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
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
            }
        ]
    )


def _cohort(source: str, *, conditions: pd.DataFrame | None = None) -> ValidationCohort:
    return ValidationCohort(
        source=source,
        patients=_patients(),
        encounters=_encounters(),
        conditions=_conditions() if conditions is None else conditions,
        medications=_medications(),
        procedures=_procedures(),
        observations=_observations(),
    )


def test_compare_java_vs_psynthea_returns_complete_result_model() -> None:
    result = compare_java_vs_psynthea(
        synthea_cohort=_cohort(SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(SOURCE_PSYNTHEA),
        reference_date=pd.Timestamp("2024-01-01"),
        top_n=5,
    )

    assert result.synthea_profile.source == SOURCE_SYNTHEA
    assert result.psynthea_profile.source == SOURCE_PSYNTHEA
    assert result.demographics is not None
    assert result.encounters is not None
    assert result.clinical is not None
    assert result.medications is not None
    assert result.procedures is not None
    assert result.observations is not None
    assert not result.summary.empty


def test_compare_java_vs_psynthea_reports_table_count_differences() -> None:
    psynthea_conditions = pd.concat(
        [_conditions(), _conditions().iloc[[0]]],
        ignore_index=True,
    )

    result = compare_java_vs_psynthea(
        synthea_cohort=_cohort(SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(SOURCE_PSYNTHEA, conditions=psynthea_conditions),
        reference_date=pd.Timestamp("2024-01-01"),
        top_n=5,
    )

    table_counts = result.table_counts.metrics.set_index("metric")

    assert table_counts.loc["conditions", "synthea_value"] == 2
    assert table_counts.loc["conditions", "psynthea_value"] == 3
    assert table_counts.loc["conditions", "absolute_difference"] == 1
    assert table_counts.loc["conditions", "relative_difference"] == 0.5


def test_compare_java_vs_psynthea_aligns_coded_event_distributions_by_union() -> None:
    psynthea_conditions = pd.DataFrame(
        [
            {
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "44054006",
                CONDITION_DESCRIPTION_COLUMN: "Diabetes mellitus type 2",
                CONDITION_START_COLUMN: "2017-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
            }
        ]
    )

    result = compare_java_vs_psynthea(
        synthea_cohort=_cohort(SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(SOURCE_PSYNTHEA, conditions=psynthea_conditions),
        reference_date=pd.Timestamp("2024-01-01"),
        top_n=10,
    )

    assert result.top_conditions is not None

    top_conditions = result.top_conditions.metrics.set_index("CODE")

    assert "59621000" in top_conditions.index
    assert "195967001" in top_conditions.index
    assert "44054006" in top_conditions.index
    assert top_conditions.loc["44054006", "synthea_count"] == 0
    assert top_conditions.loc["44054006", "psynthea_count"] == 1


def test_compare_java_vs_psynthea_summary_uses_stable_schema() -> None:
    result = compare_java_vs_psynthea(
        synthea_cohort=_cohort(SOURCE_SYNTHEA),
        psynthea_cohort=_cohort(SOURCE_PSYNTHEA),
        reference_date=pd.Timestamp("2024-01-01"),
        top_n=5,
    )

    assert list(result.summary.columns) == [
        "domain",
        "metric",
        "synthea_value",
        "psynthea_value",
        "absolute_difference",
        "relative_difference",
    ]
    assert set(result.summary["domain"]).issuperset(
        {
            "table_counts",
            "demographics",
            "encounters",
            "clinical",
            "medications",
            "procedures",
            "observations",
        }
    )
