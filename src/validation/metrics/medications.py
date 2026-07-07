"""
Medication validation metrics.

This module computes descriptive medication metrics from a ValidationCohort.

The resulting metrics quantify medication exposure, treatment duration,
active prescriptions, repeat prescriptions and polypharmacy.

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
    MEDICATION_PATIENT_COLUMN,
    MEDICATION_CODE_COLUMN,
    MEDICATION_DESCRIPTION_COLUMN,
    MEDICATION_START_COLUMN,
    MEDICATION_STOP_COLUMN,
    MEDICATION_DISPENSES_COLUMN,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class MedicationMetrics:
    """
    Descriptive metrics for a single medication.
    """

    code: str
    display: str

    n_patients: int
    exposure_prevalence: float

    n_orders: int
    active_orders: int

    mean_start_age: float
    median_start_age: float
    min_start_age: float
    max_start_age: float

    male_patients: int
    female_patients: int

    male_patient_fraction: float
    female_patient_fraction: float

    mean_duration_days: float
    median_duration_days: float

    recurrent_patients: int
    recurrence_rate: float

    total_dispenses: float
    mean_dispenses_per_order: float


@dataclass(slots=True)
class MedicationProfileMetrics:
    """
    Medication profile of an entire synthetic cohort.
    """

    n_medication_orders: int
    n_distinct_medications: int

    patients_with_medications: int
    patients_without_medications: int

    polypharmacy_patients: int

    mean_medications_per_patient: float
    median_medications_per_patient: float
    std_medications_per_patient: float

    medications_per_patient: pd.DataFrame

    top_medications: pd.DataFrame
    active_medications: pd.DataFrame

    medications: list[MedicationMetrics]


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


def _empty_medication_metrics(
    cohort: ValidationCohort,
) -> MedicationProfileMetrics:
    """
    Return empty medication metrics for cohorts without medications.
    """

    return MedicationProfileMetrics(

        n_medication_orders=0,
        n_distinct_medications=0,

        patients_with_medications=0,
        patients_without_medications=cohort.n_patients,

        polypharmacy_patients=0,

        mean_medications_per_patient=0.0,
        median_medications_per_patient=0.0,
        std_medications_per_patient=0.0,

        medications_per_patient=pd.DataFrame(
            columns=[
                MEDICATION_PATIENT_COLUMN,
                "medications",
            ]
        ),

        top_medications=pd.DataFrame(
            columns=[
                MEDICATION_CODE_COLUMN,
                MEDICATION_DESCRIPTION_COLUMN,
                "count",
            ]
        ),

        active_medications=pd.DataFrame(
            columns=[
                MEDICATION_CODE_COLUMN,
                MEDICATION_DESCRIPTION_COLUMN,
                "active_count",
            ]
        ),

        medications=[],
    )


# =============================================================================
# Public API
# =============================================================================

def calculate_medications(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    polypharmacy_threshold: int = 5,
) -> MedicationProfileMetrics:
    """
    Compute descriptive medication metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate patient age and open treatment duration.

    top_n
        Number of most frequent medications returned in top_medications.

    polypharmacy_threshold
        Minimum number of distinct medications used to classify a patient
        as having polypharmacy.

    Returns
    -------
    MedicationProfileMetrics
    """

    if cohort.medications is None or cohort.medications.empty:
        return _empty_medication_metrics(cohort)

    patients = prepare_patients(
        cohort.patients,
        reference_date,
    )

    medications = cohort.medications.copy()

    medications[MEDICATION_START_COLUMN] = pd.to_datetime(
        medications[MEDICATION_START_COLUMN],
        errors="coerce",
    )

    medications[MEDICATION_STOP_COLUMN] = pd.to_datetime(
        medications[MEDICATION_STOP_COLUMN],
        errors="coerce",
    )

    if MEDICATION_DISPENSES_COLUMN in medications.columns:
        medications[MEDICATION_DISPENSES_COLUMN] = pd.to_numeric(
            medications[MEDICATION_DISPENSES_COLUMN],
            errors="coerce",
        )
    else:
        medications[MEDICATION_DISPENSES_COLUMN] = 0.0

    # -------------------------------------------------------------------------
    # Medications per patient
    # -------------------------------------------------------------------------

    medications_per_patient = (
        medications
        .groupby(MEDICATION_PATIENT_COLUMN)
        [MEDICATION_CODE_COLUMN]
        .nunique()
        .rename("medications")
        .reset_index()
    )

    all_patient_medication_counts = (
        patients[[PATIENT_ID_COLUMN]]
        .merge(
            medications_per_patient,
            left_on=PATIENT_ID_COLUMN,
            right_on=MEDICATION_PATIENT_COLUMN,
            how="left",
        )
        ["medications"]
        .fillna(0)
    )

    # -------------------------------------------------------------------------
    # Global medication burden
    # -------------------------------------------------------------------------

    patients_with_medications = int(
        (all_patient_medication_counts > 0).sum()
    )

    patients_without_medications = (
        cohort.n_patients
        - patients_with_medications
    )

    polypharmacy_patients = int(
        (
            all_patient_medication_counts
            >= polypharmacy_threshold
        ).sum()
    )

    # -------------------------------------------------------------------------
    # Top medications
    # -------------------------------------------------------------------------

    top_medications = (
        medications
        .groupby(
            [
                MEDICATION_CODE_COLUMN,
                MEDICATION_DESCRIPTION_COLUMN,
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
    # Active medications
    # -------------------------------------------------------------------------

    active_medications = (
        medications[
            medications[MEDICATION_STOP_COLUMN].isna()
            | (
                medications[MEDICATION_STOP_COLUMN]
                > reference_date
            )
        ]
        .groupby(
            [
                MEDICATION_CODE_COLUMN,
                MEDICATION_DESCRIPTION_COLUMN,
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="active_count")
        .sort_values(
            "active_count",
            ascending=False,
        )
        .head(top_n)
        .reset_index(drop=True)
    )

    # -------------------------------------------------------------------------
    # Medication-level metrics
    # -------------------------------------------------------------------------

    medication_metrics: list[MedicationMetrics] = []

    patient_demographics = patients[
        [
            PATIENT_ID_COLUMN,
            PATIENT_GENDER_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
        ]
    ]

    for code, medication_orders in medications.groupby(
        MEDICATION_CODE_COLUMN,
        dropna=False,
    ):
        medication_orders = medication_orders.merge(
            patient_demographics,
            left_on=MEDICATION_PATIENT_COLUMN,
            right_on=PATIENT_ID_COLUMN,
            how="left",
        )

        start = medication_orders[MEDICATION_START_COLUMN]
        stop = medication_orders[MEDICATION_STOP_COLUMN]

        birthdate = pd.to_datetime(
            medication_orders[PATIENT_BIRTHDATE_COLUMN],
            errors="coerce",
        )

        start_age = (
            (start - birthdate).dt.days / 365.25
        )

        duration_days = (
            stop
            .fillna(reference_date)
            .sub(start)
            .dt.days
        )

        duration_days = duration_days.where(
            duration_days >= 0
        )

        patient_order_counts = (
            medication_orders
            .groupby(MEDICATION_PATIENT_COLUMN)
            .size()
        )

        exposed_patients = (
            medication_orders
            .drop_duplicates(MEDICATION_PATIENT_COLUMN)
        )

        n_patients = int(patient_order_counts.size)
        n_orders = int(len(medication_orders))

        active_orders = int(
            (
                stop.isna()
                | (stop > reference_date)
            ).sum()
        )

        male_patients = int(
            (
                exposed_patients[PATIENT_GENDER_COLUMN]
                == "M"
            ).sum()
        )

        female_patients = int(
            (
                exposed_patients[PATIENT_GENDER_COLUMN]
                == "F"
            ).sum()
        )

        recurrent_patients = int(
            (patient_order_counts > 1).sum()
        )

        display_values = (
            medication_orders[MEDICATION_DESCRIPTION_COLUMN]
            .dropna()
        )

        display = (
            str(display_values.iloc[0])
            if not display_values.empty
            else str(code)
        )

        dispenses = medication_orders[MEDICATION_DISPENSES_COLUMN]

        medication_metrics.append(
            MedicationMetrics(

                code=str(code),
                display=display,

                n_patients=n_patients,
                exposure_prevalence=_safe_fraction(
                    n_patients,
                    cohort.n_patients,
                ),

                n_orders=n_orders,
                active_orders=active_orders,

                mean_start_age=start_age.mean(),
                median_start_age=start_age.median(),
                min_start_age=start_age.min(),
                max_start_age=start_age.max(),

                male_patients=male_patients,
                female_patients=female_patients,

                male_patient_fraction=_safe_fraction(
                    male_patients,
                    n_patients,
                ),
                female_patient_fraction=_safe_fraction(
                    female_patients,
                    n_patients,
                ),

                mean_duration_days=duration_days.mean(),
                median_duration_days=duration_days.median(),

                recurrent_patients=recurrent_patients,
                recurrence_rate=_safe_fraction(
                    recurrent_patients,
                    n_patients,
                ),

                total_dispenses=dispenses.sum(),
                mean_dispenses_per_order=dispenses.mean(),
            )
        )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    return MedicationProfileMetrics(

        n_medication_orders=len(medications),
        n_distinct_medications=int(
            medications[MEDICATION_CODE_COLUMN].nunique()
        ),

        patients_with_medications=patients_with_medications,
        patients_without_medications=patients_without_medications,

        polypharmacy_patients=polypharmacy_patients,

        mean_medications_per_patient=all_patient_medication_counts.mean(),
        median_medications_per_patient=all_patient_medication_counts.median(),
        std_medications_per_patient=all_patient_medication_counts.std(),

        medications_per_patient=medications_per_patient,

        top_medications=top_medications,
        active_medications=active_medications,

        medications=medication_metrics,
    )