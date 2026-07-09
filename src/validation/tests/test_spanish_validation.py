"""
Tests for Spanish/SNS adaptation validation indicators.
"""

from __future__ import annotations

import pandas as pd

from validation.comparison.spanish_validation import validate_spanish_adaptation
from validation.constants import (
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
)
from validation.models import ValidationCohort


def _spanish_like_cohort() -> ValidationCohort:
    return ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=pd.DataFrame(
            [
                {PATIENT_ID_COLUMN: "P1", PATIENT_GENDER_COLUMN: "M", PATIENT_BIRTHDATE_COLUMN: "1980-01-01"},
                {PATIENT_ID_COLUMN: "P2", PATIENT_GENDER_COLUMN: "F", PATIENT_BIRTHDATE_COLUMN: "1990-01-01"},
            ]
        ),
        encounters=pd.DataFrame(
            [
                {
                    ENCOUNTER_PATIENT_COLUMN: "P1",
                    ENCOUNTER_CLASS_COLUMN: "primary care ambulatory",
                    "DESCRIPTION": "Centro de salud - Atención Primaria",
                    "START": "2020-01-01",
                    "ENCOUNTER": "E1",
                },
                {
                    ENCOUNTER_PATIENT_COLUMN: "P1",
                    ENCOUNTER_CLASS_COLUMN: "specialist outpatient",
                    "DESCRIPTION": "Derivación a cardiología",
                    "START": "2020-02-01",
                    "ENCOUNTER": "E2",
                },
                {
                    ENCOUNTER_PATIENT_COLUMN: "P2",
                    ENCOUNTER_CLASS_COLUMN: "emergency inpatient",
                    "DESCRIPTION": "Urgencias hospitalarias con ingreso",
                    "START": "2020-03-01",
                    "ENCOUNTER": "E3",
                },
            ]
        ),
        conditions=pd.DataFrame(
            [
                {
                    CONDITION_PATIENT_COLUMN: "P1",
                    CONDITION_CODE_COLUMN: "59621000",
                    CONDITION_DESCRIPTION_COLUMN: "Hypertension",
                    CONDITION_START_COLUMN: "2020-01-01",
                    CONDITION_STOP_COLUMN: pd.NA,
                    "ENCOUNTER": "E1",
                }
            ]
        ),
        medications=pd.DataFrame(
            [
                {
                    MEDICATION_PATIENT_COLUMN: "P1",
                    MEDICATION_CODE_COLUMN: "314076",
                    MEDICATION_DESCRIPTION_COLUMN: "Lisinopril",
                    MEDICATION_START_COLUMN: "2020-01-02",
                    MEDICATION_STOP_COLUMN: pd.NA,
                    MEDICATION_DISPENSES_COLUMN: 12,
                    "ENCOUNTER": "E1",
                }
            ]
        ),
        procedures=pd.DataFrame(
            [
                {
                    PROCEDURE_PATIENT_COLUMN: "P1",
                    PROCEDURE_CODE_COLUMN: "710824005",
                    PROCEDURE_DESCRIPTION_COLUMN: "Referral to specialist",
                    PROCEDURE_START_COLUMN: "2020-01-15",
                    PROCEDURE_STOP_COLUMN: "2020-01-15",
                    PROCEDURE_BASE_COST_COLUMN: 100.0,
                    "ENCOUNTER": "E2",
                }
            ]
        ),
        observations=pd.DataFrame(
            [
                {
                    OBSERVATION_PATIENT_COLUMN: "P1",
                    OBSERVATION_CODE_COLUMN: "8480-6",
                    OBSERVATION_DESCRIPTION_COLUMN: "Systolic Blood Pressure",
                    OBSERVATION_DATE_COLUMN: "2020-01-01",
                    OBSERVATION_VALUE_COLUMN: "150",
                    OBSERVATION_UNITS_COLUMN: "mmHg",
                    "ENCOUNTER": "E1",
                }
            ]
        ),
    )


def test_spanish_validation_detects_primary_care_and_specialist_flow() -> None:
    result = validate_spanish_adaptation(_spanish_like_cohort())

    primary_care = result.primary_care.set_index("indicator")
    healthcare_flow = result.healthcare_flow.set_index("indicator")
    assert primary_care.loc["primary_care_encounters", "value"] >= 1
    assert healthcare_flow.loc["patients_with_encounters", "value"] >= 1


def test_spanish_validation_detects_referrals_urgencies_and_hospitalisation() -> None:
    result = validate_spanish_adaptation(_spanish_like_cohort())

    referrals = result.referrals.set_index("indicator")
    healthcare_flow = result.healthcare_flow.set_index("indicator")

    assert referrals.loc["referral_like_encounters", "value"] >= 1
    assert referrals.loc["referral_like_procedures", "value"] >= 1
    assert healthcare_flow.loc["emergency_encounters", "value"] >= 1
    assert healthcare_flow.loc["inpatient_encounters", "value"] >= 1


def test_spanish_validation_checks_clinical_context_linkage() -> None:
    result = validate_spanish_adaptation(_spanish_like_cohort())

    clinical_context = result.clinical_context.set_index("indicator")

    assert clinical_context.loc["conditions_linked_to_encounters", "fraction"] == 1.0
    assert clinical_context.loc["medications_linked_to_encounters", "fraction"] == 1.0
    assert clinical_context.loc["procedures_linked_to_encounters", "fraction"] == 1.0
    assert clinical_context.loc["observations_linked_to_encounters", "fraction"] == 1.0


def test_spanish_validation_returns_stable_summary() -> None:
    result = validate_spanish_adaptation(_spanish_like_cohort())

    assert not result.summary.empty
    assert set(result.summary["domain"]).issuperset(
        {"primary_care", "referrals", "healthcare_flow", "clinical_context"}
    )
