"""
Clinical validation metrics.

This module computes descriptive clinical metrics from a ValidationCohort.

While demographics describe who the patients are and encounters describe
how they interact with the healthcare system, this module characterises
their clinical profile.

The resulting metrics quantify disease prevalence, age at onset,
disease duration, recurrence and multimorbidity.

No statistical hypothesis testing, plotting or report generation should
be implemented in this module.
"""

from dataclasses import dataclass

import pandas as pd

from validation.models import ValidationCohort
from validation.utils import prepare_patients

from validation.constants import (
    PATIENT_ID_COLUMN,
    PATIENT_GENDER_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    CONDITION_PATIENT_COLUMN,
    CONDITION_CODE_COLUMN,
    CONDITION_DESCRIPTION_COLUMN,
    CONDITION_START_COLUMN,
    CONDITION_STOP_COLUMN,
)

# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class DiseaseMetrics:
    """
    Descriptive metrics for a single clinical condition.
    """

    # -------------------------------------------------------------------------
    # Disease identification
    # -------------------------------------------------------------------------

    code: str
    display: str

    # -------------------------------------------------------------------------
    # Epidemiology
    # -------------------------------------------------------------------------

    n_patients: int
    prevalence: float

    # -------------------------------------------------------------------------
    # Age at onset
    # -------------------------------------------------------------------------

    mean_onset_age: float
    median_onset_age: float

    min_onset_age: float
    max_onset_age: float

    # -------------------------------------------------------------------------
    # Sex distribution
    # -------------------------------------------------------------------------

    male_count: int
    female_count: int

    male_fraction: float
    female_fraction: float

    # -------------------------------------------------------------------------
    # Disease duration
    # -------------------------------------------------------------------------

    mean_duration_days: float
    median_duration_days: float

    # -------------------------------------------------------------------------
    # Recurrence
    # -------------------------------------------------------------------------

    n_episodes: int
    recurrence_rate: float


@dataclass(slots=True)
class ClinicalMetrics:
    """
    Clinical profile of an entire synthetic cohort.
    """

    # -------------------------------------------------------------------------
    # Global burden of disease
    # -------------------------------------------------------------------------

    n_conditions: int

    patients_with_conditions: int
    healthy_patients: int

    multimorbid_patients: int

    mean_conditions_per_patient: float
    median_conditions_per_patient: float
    std_conditions_per_patient: float

    # -------------------------------------------------------------------------
    # Cohort-level distributions
    # -------------------------------------------------------------------------

    conditions_per_patient: pd.DataFrame

    top_conditions: pd.DataFrame

    # -------------------------------------------------------------------------
    # Disease-level metrics
    # -------------------------------------------------------------------------

    diseases: list[DiseaseMetrics]

# =============================================================================
# Helpers
# =============================================================================

def _safe_fraction(
    numerator: int,
    denominator: int,
) -> float:
    """
    Return a safe fraction avoiding division by zero.
    """

    if denominator == 0:
        return 0.0

    return numerator / denominator


def _empty_clinical_metrics(
    cohort: ValidationCohort,
) -> ClinicalMetrics:
    """
    Return empty clinical metrics for cohorts without conditions.
    """

    return ClinicalMetrics(

        n_conditions=0,

        patients_with_conditions=0,
        healthy_patients=cohort.n_patients,

        multimorbid_patients=0,

        mean_conditions_per_patient=0.0,
        median_conditions_per_patient=0.0,
        std_conditions_per_patient=0.0,

        conditions_per_patient=pd.DataFrame(
            columns=[
                CONDITION_PATIENT_COLUMN,
                "conditions",
            ]
        ),

        top_conditions=pd.DataFrame(
            columns=[
                CONDITION_CODE_COLUMN,
                CONDITION_DESCRIPTION_COLUMN,
                "count",
            ]
        ),

        diseases=[],
    )


# =============================================================================
# Public API
# =============================================================================

def calculate_clinical(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
) -> ClinicalMetrics:
    """
    Compute descriptive clinical condition metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate patient age and open disease duration.

    top_n
        Number of most frequent conditions returned in top_conditions.

    Returns
    -------
    ClinicalMetrics
    """

    if cohort.conditions is None or cohort.conditions.empty:
        return _empty_clinical_metrics(cohort)

    patients = prepare_patients(
        cohort.patients,
        reference_date,
    )

    conditions = cohort.conditions.copy()

    conditions[CONDITION_START_COLUMN] = pd.to_datetime(
        conditions[CONDITION_START_COLUMN],
        errors="coerce",
    )

    conditions[CONDITION_STOP_COLUMN] = pd.to_datetime(
        conditions[CONDITION_STOP_COLUMN],
        errors="coerce",
    )

    # -------------------------------------------------------------------------
    # Conditions per patient
    # -------------------------------------------------------------------------

    conditions_per_patient = (
        conditions
        .groupby(CONDITION_PATIENT_COLUMN)
        [CONDITION_CODE_COLUMN]
        .nunique()
        .rename("conditions")
        .reset_index()
    )

    all_patient_condition_counts = (
        patients[[PATIENT_ID_COLUMN]]
        .merge(
            conditions_per_patient,
            left_on=PATIENT_ID_COLUMN,
            right_on=CONDITION_PATIENT_COLUMN,
            how="left",
        )
        ["conditions"]
        .fillna(0)
    )

    # -------------------------------------------------------------------------
    # Global burden of disease
    # -------------------------------------------------------------------------

    patients_with_conditions = int(
        (all_patient_condition_counts > 0).sum()
    )

    healthy_patients = (
        cohort.n_patients
        - patients_with_conditions
    )

    multimorbid_patients = int(
        (all_patient_condition_counts >= 2).sum()
    )

    # -------------------------------------------------------------------------
    # Top conditions
    # -------------------------------------------------------------------------

    top_conditions = (
        conditions
        .groupby(
            [
                CONDITION_CODE_COLUMN,
                CONDITION_DESCRIPTION_COLUMN,
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="count")
        .sort_values(
            "count",
            ascending=False,
        )
        .head(top_n)
        .reset_index(drop=True)
    )

    # -------------------------------------------------------------------------
    # Disease-level metrics
    # -------------------------------------------------------------------------

    diseases: list[DiseaseMetrics] = []

    patient_demographics = patients[
        [
            PATIENT_ID_COLUMN,
            PATIENT_GENDER_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
        ]
    ]

    for code, disease_conditions in conditions.groupby(
        CONDITION_CODE_COLUMN,
        dropna=False,
    ):
        disease_conditions = disease_conditions.merge(
            patient_demographics,
            left_on=CONDITION_PATIENT_COLUMN,
            right_on=PATIENT_ID_COLUMN,
            how="left",
        )

        start = disease_conditions[CONDITION_START_COLUMN]
        stop = disease_conditions[CONDITION_STOP_COLUMN]

        birthdate = pd.to_datetime(
            disease_conditions[PATIENT_BIRTHDATE_COLUMN],
            errors="coerce",
        )

        onset_age = (
            (start - birthdate).dt.days / 365.25
        )

        duration_days = (
            stop
            .fillna(reference_date)
            .sub(start)
            .dt.days
        )

        patient_episode_counts = (
            disease_conditions
            .groupby(CONDITION_PATIENT_COLUMN)
            .size()
        )

        n_patients = int(patient_episode_counts.size)
        n_episodes = int(len(disease_conditions))

        male_count = int(
            (
                disease_conditions[PATIENT_GENDER_COLUMN]
                == "M"
            ).sum()
        )

        female_count = int(
            (
                disease_conditions[PATIENT_GENDER_COLUMN]
                == "F"
            ).sum()
        )

        recurrent_patients = int(
            (patient_episode_counts > 1).sum()
        )

        display_values = (
            disease_conditions[CONDITION_DESCRIPTION_COLUMN]
            .dropna()
        )

        display = (
            str(display_values.iloc[0])
            if not display_values.empty
            else str(code)
        )

        diseases.append(
            DiseaseMetrics(

                code=str(code),
                display=display,

                n_patients=n_patients,
                prevalence=_safe_fraction(
                    n_patients,
                    cohort.n_patients,
                ),

                mean_onset_age=onset_age.mean(),
                median_onset_age=onset_age.median(),

                min_onset_age=onset_age.min(),
                max_onset_age=onset_age.max(),

                male_count=male_count,
                female_count=female_count,

                male_fraction=_safe_fraction(
                    male_count,
                    n_episodes,
                ),
                female_fraction=_safe_fraction(
                    female_count,
                    n_episodes,
                ),

                mean_duration_days=duration_days.mean(),
                median_duration_days=duration_days.median(),

                n_episodes=n_episodes,
                recurrence_rate=_safe_fraction(
                    recurrent_patients,
                    n_patients,
                ),
            )
        )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    return ClinicalMetrics(

        n_conditions=len(conditions),

        patients_with_conditions=patients_with_conditions,
        healthy_patients=healthy_patients,

        multimorbid_patients=multimorbid_patients,

        mean_conditions_per_patient=all_patient_condition_counts.mean(),
        median_conditions_per_patient=all_patient_condition_counts.median(),
        std_conditions_per_patient=all_patient_condition_counts.std(),

        conditions_per_patient=conditions_per_patient,

        top_conditions=top_conditions,

        diseases=diseases,
    )