"""
Shared pytest fixtures for the validation test suite.

The fixtures define a small deterministic synthetic cohort that exercises
all metric domains without relying on external CSV files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from validation.constants import (
    SOURCE_PSYNTHEA,
    PATIENT_ID_COLUMN,
    PATIENT_GENDER_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    ENCOUNTER_PATIENT_COLUMN,
    ENCOUNTER_CLASS_COLUMN,
    CONDITION_PATIENT_COLUMN,
    CONDITION_CODE_COLUMN,
    CONDITION_DESCRIPTION_COLUMN,
    CONDITION_START_COLUMN,
    CONDITION_STOP_COLUMN,
    MEDICATION_PATIENT_COLUMN,
    MEDICATION_CODE_COLUMN,
    MEDICATION_DESCRIPTION_COLUMN,
    MEDICATION_START_COLUMN,
    MEDICATION_STOP_COLUMN,
    MEDICATION_DISPENSES_COLUMN,
    PROCEDURE_PATIENT_COLUMN,
    PROCEDURE_CODE_COLUMN,
    PROCEDURE_DESCRIPTION_COLUMN,
    PROCEDURE_START_COLUMN,
    PROCEDURE_STOP_COLUMN,
    PROCEDURE_BASE_COST_COLUMN,
    OBSERVATION_PATIENT_COLUMN,
    OBSERVATION_CODE_COLUMN,
    OBSERVATION_DESCRIPTION_COLUMN,
    OBSERVATION_DATE_COLUMN,
    OBSERVATION_VALUE_COLUMN,
    OBSERVATION_UNITS_COLUMN,
)
from validation.models import ValidationCohort


@pytest.fixture
def reference_date() -> pd.Timestamp:
    """
    Fixed reference date used to make age and duration tests deterministic.
    """

    return pd.Timestamp("2024-01-01")


@pytest.fixture
def patients_dataframe() -> pd.DataFrame:
    """
    Minimal patient table with multiple ages and both binary sex labels.

    P4 intentionally has no clinical activity in some domains so tests can
    verify patients-without-event calculations.
    """

    return pd.DataFrame(
        [
            {
                PATIENT_ID_COLUMN: "P1",
                PATIENT_GENDER_COLUMN: "M",
                PATIENT_BIRTHDATE_COLUMN: "1980-01-01",
            },
            {
                PATIENT_ID_COLUMN: "P2",
                PATIENT_GENDER_COLUMN: "F",
                PATIENT_BIRTHDATE_COLUMN: "1990-06-15",
            },
            {
                PATIENT_ID_COLUMN: "P3",
                PATIENT_GENDER_COLUMN: "M",
                PATIENT_BIRTHDATE_COLUMN: "2010-03-20",
            },
            {
                PATIENT_ID_COLUMN: "P4",
                PATIENT_GENDER_COLUMN: "F",
                PATIENT_BIRTHDATE_COLUMN: "1945-09-10",
            },
        ]
    )


@pytest.fixture
def encounters_dataframe() -> pd.DataFrame:
    """
    Encounter table covering repeated utilisation and encounter classes.
    """

    return pd.DataFrame(
        [
            {
                ENCOUNTER_PATIENT_COLUMN: "P1",
                ENCOUNTER_CLASS_COLUMN: "ambulatory",
            },
            {
                ENCOUNTER_PATIENT_COLUMN: "P1",
                ENCOUNTER_CLASS_COLUMN: "outpatient",
            },
            {
                ENCOUNTER_PATIENT_COLUMN: "P2",
                ENCOUNTER_CLASS_COLUMN: "ambulatory",
            },
            {
                ENCOUNTER_PATIENT_COLUMN: "P2",
                ENCOUNTER_CLASS_COLUMN: "emergency",
            },
            {
                ENCOUNTER_PATIENT_COLUMN: "P3",
                ENCOUNTER_CLASS_COLUMN: "wellness",
            },
            {
                ENCOUNTER_PATIENT_COLUMN: "P3",
                ENCOUNTER_CLASS_COLUMN: "ambulatory",
            },
        ]
    )


@pytest.fixture
def conditions_dataframe() -> pd.DataFrame:
    """
    Condition table covering prevalence, recurrence and multimorbidity.

    P1 has recurrent hypertension and diabetes.
    P2 has asthma.
    P3 and P4 are condition-free for healthy-patient calculations.
    """

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
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "59621000",
                CONDITION_DESCRIPTION_COLUMN: "Hypertension",
                CONDITION_START_COLUMN: "2018-01-01",
                CONDITION_STOP_COLUMN: "2018-06-01",
            },
            {
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "44054006",
                CONDITION_DESCRIPTION_COLUMN: "Diabetes mellitus type 2",
                CONDITION_START_COLUMN: "2017-03-15",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                CONDITION_PATIENT_COLUMN: "P2",
                CONDITION_CODE_COLUMN: "195967001",
                CONDITION_DESCRIPTION_COLUMN: "Asthma",
                CONDITION_START_COLUMN: "2000-05-01",
                CONDITION_STOP_COLUMN: pd.NA,
            },
        ]
    )


@pytest.fixture
def medications_dataframe() -> pd.DataFrame:
    """
    Medication table covering active, stopped and repeat prescriptions.
    """

    return pd.DataFrame(
        [
            {
                MEDICATION_PATIENT_COLUMN: "P1",
                MEDICATION_CODE_COLUMN: "314076",
                MEDICATION_DESCRIPTION_COLUMN: "Lisinopril 10 MG Oral Tablet",
                MEDICATION_START_COLUMN: "2015-01-02",
                MEDICATION_STOP_COLUMN: pd.NA,
                MEDICATION_DISPENSES_COLUMN: 12,
            },
            {
                MEDICATION_PATIENT_COLUMN: "P1",
                MEDICATION_CODE_COLUMN: "314076",
                MEDICATION_DESCRIPTION_COLUMN: "Lisinopril 10 MG Oral Tablet",
                MEDICATION_START_COLUMN: "2018-01-10",
                MEDICATION_STOP_COLUMN: "2018-06-10",
                MEDICATION_DISPENSES_COLUMN: 5,
            },
            {
                MEDICATION_PATIENT_COLUMN: "P1",
                MEDICATION_CODE_COLUMN: "860975",
                MEDICATION_DESCRIPTION_COLUMN: "Metformin 500 MG Oral Tablet",
                MEDICATION_START_COLUMN: "2017-03-20",
                MEDICATION_STOP_COLUMN: pd.NA,
                MEDICATION_DISPENSES_COLUMN: 20,
            },
            {
                MEDICATION_PATIENT_COLUMN: "P2",
                MEDICATION_CODE_COLUMN: "312615",
                MEDICATION_DESCRIPTION_COLUMN: "Albuterol 0.09 MG/ACTUAT Inhalant",
                MEDICATION_START_COLUMN: "2000-05-02",
                MEDICATION_STOP_COLUMN: pd.NA,
                MEDICATION_DISPENSES_COLUMN: 8,
            },
            {
                MEDICATION_PATIENT_COLUMN: "P3",
                MEDICATION_CODE_COLUMN: "313782",
                MEDICATION_DESCRIPTION_COLUMN: "Acetaminophen 325 MG Oral Tablet",
                MEDICATION_START_COLUMN: "2020-01-01",
                MEDICATION_STOP_COLUMN: "2020-01-10",
                MEDICATION_DISPENSES_COLUMN: 1,
            },
        ]
    )


@pytest.fixture
def procedures_dataframe() -> pd.DataFrame:
    """
    Procedure table covering duration, cost and repeated procedures.
    """

    return pd.DataFrame(
        [
            {
                PROCEDURE_PATIENT_COLUMN: "P1",
                PROCEDURE_CODE_COLUMN: "710824005",
                PROCEDURE_DESCRIPTION_COLUMN: "Assessment of health and social care needs",
                PROCEDURE_START_COLUMN: "2015-01-01",
                PROCEDURE_STOP_COLUMN: "2015-01-01",
                PROCEDURE_BASE_COST_COLUMN: 100.0,
            },
            {
                PROCEDURE_PATIENT_COLUMN: "P1",
                PROCEDURE_CODE_COLUMN: "710824005",
                PROCEDURE_DESCRIPTION_COLUMN: "Assessment of health and social care needs",
                PROCEDURE_START_COLUMN: "2018-01-01",
                PROCEDURE_STOP_COLUMN: "2018-01-01",
                PROCEDURE_BASE_COST_COLUMN: 100.0,
            },
            {
                PROCEDURE_PATIENT_COLUMN: "P2",
                PROCEDURE_CODE_COLUMN: "430193006",
                PROCEDURE_DESCRIPTION_COLUMN: "Medication reconciliation",
                PROCEDURE_START_COLUMN: "2000-05-01",
                PROCEDURE_STOP_COLUMN: "2000-05-01",
                PROCEDURE_BASE_COST_COLUMN: 75.0,
            },
            {
                PROCEDURE_PATIENT_COLUMN: "P3",
                PROCEDURE_CODE_COLUMN: "73761001",
                PROCEDURE_DESCRIPTION_COLUMN: "Colonoscopy",
                PROCEDURE_START_COLUMN: "2021-09-01",
                PROCEDURE_STOP_COLUMN: "2021-09-02",
                PROCEDURE_BASE_COST_COLUMN: 500.0,
            },
            {
                PROCEDURE_PATIENT_COLUMN: "P4",
                PROCEDURE_CODE_COLUMN: "169230002",
                PROCEDURE_DESCRIPTION_COLUMN: "Routine health check",
                PROCEDURE_START_COLUMN: "2022-01-01",
                PROCEDURE_STOP_COLUMN: pd.NA,
                PROCEDURE_BASE_COST_COLUMN: 50.0,
            },
        ]
    )


@pytest.fixture
def observations_dataframe() -> pd.DataFrame:
    """
    Observation table covering numeric, non-numeric and missing values.
    """

    return pd.DataFrame(
        [
            {
                OBSERVATION_PATIENT_COLUMN: "P1",
                OBSERVATION_CODE_COLUMN: "8480-6",
                OBSERVATION_DESCRIPTION_COLUMN: "Systolic Blood Pressure",
                OBSERVATION_DATE_COLUMN: "2015-01-01",
                OBSERVATION_VALUE_COLUMN: "150",
                OBSERVATION_UNITS_COLUMN: "mmHg",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P1",
                OBSERVATION_CODE_COLUMN: "8480-6",
                OBSERVATION_DESCRIPTION_COLUMN: "Systolic Blood Pressure",
                OBSERVATION_DATE_COLUMN: "2018-01-01",
                OBSERVATION_VALUE_COLUMN: "145",
                OBSERVATION_UNITS_COLUMN: "mmHg",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P1",
                OBSERVATION_CODE_COLUMN: "8462-4",
                OBSERVATION_DESCRIPTION_COLUMN: "Diastolic Blood Pressure",
                OBSERVATION_DATE_COLUMN: "2015-01-01",
                OBSERVATION_VALUE_COLUMN: "95",
                OBSERVATION_UNITS_COLUMN: "mmHg",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P2",
                OBSERVATION_CODE_COLUMN: "72166-2",
                OBSERVATION_DESCRIPTION_COLUMN: "Tobacco smoking status",
                OBSERVATION_DATE_COLUMN: "2000-05-01",
                OBSERVATION_VALUE_COLUMN: "Never smoker",
                OBSERVATION_UNITS_COLUMN: pd.NA,
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P2",
                OBSERVATION_CODE_COLUMN: "8302-2",
                OBSERVATION_DESCRIPTION_COLUMN: "Body Height",
                OBSERVATION_DATE_COLUMN: "2020-01-01",
                OBSERVATION_VALUE_COLUMN: "165",
                OBSERVATION_UNITS_COLUMN: "cm",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P3",
                OBSERVATION_CODE_COLUMN: "29463-7",
                OBSERVATION_DESCRIPTION_COLUMN: "Body Weight",
                OBSERVATION_DATE_COLUMN: "2020-01-01",
                OBSERVATION_VALUE_COLUMN: "",
                OBSERVATION_UNITS_COLUMN: "kg",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P3",
                OBSERVATION_CODE_COLUMN: "8310-5",
                OBSERVATION_DESCRIPTION_COLUMN: "Body temperature",
                OBSERVATION_DATE_COLUMN: "2020-01-01",
                OBSERVATION_VALUE_COLUMN: "37.2",
                OBSERVATION_UNITS_COLUMN: "Cel",
            },
            {
                OBSERVATION_PATIENT_COLUMN: "P4",
                OBSERVATION_CODE_COLUMN: "72166-2",
                OBSERVATION_DESCRIPTION_COLUMN: "Tobacco smoking status",
                OBSERVATION_DATE_COLUMN: "2022-01-01",
                OBSERVATION_VALUE_COLUMN: pd.NA,
                OBSERVATION_UNITS_COLUMN: pd.NA,
            },
        ]
    )


@pytest.fixture
def validation_cohort(
    patients_dataframe: pd.DataFrame,
    encounters_dataframe: pd.DataFrame,
    conditions_dataframe: pd.DataFrame,
    medications_dataframe: pd.DataFrame,
    procedures_dataframe: pd.DataFrame,
    observations_dataframe: pd.DataFrame,
) -> ValidationCohort:
    """
    Fully populated validation cohort used by metric tests.
    """

    return ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=patients_dataframe,
        encounters=encounters_dataframe,
        conditions=conditions_dataframe,
        medications=medications_dataframe,
        procedures=procedures_dataframe,
        observations=observations_dataframe,
    )


@pytest.fixture
def empty_optional_tables_cohort(
    patients_dataframe: pd.DataFrame,
) -> ValidationCohort:
    """
    Cohort with patients only, used to test empty-domain behaviour.
    """

    return ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=patients_dataframe,
        encounters=pd.DataFrame(),
        conditions=pd.DataFrame(),
        medications=pd.DataFrame(),
        procedures=pd.DataFrame(),
        observations=pd.DataFrame(),
    )
