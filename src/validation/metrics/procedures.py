"""
Procedure validation metrics.

This module computes descriptive procedure metrics from a ValidationCohort.

The resulting metrics quantify procedure utilisation, age at procedure,
procedure duration, repeated procedures and high procedure utilisation.

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
    PROCEDURE_PATIENT_COLUMN,
    PROCEDURE_CODE_COLUMN,
    PROCEDURE_DESCRIPTION_COLUMN,
    PROCEDURE_START_COLUMN,
    PROCEDURE_STOP_COLUMN,
    PROCEDURE_BASE_COST_COLUMN,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class ProcedureMetrics:
    """
    Descriptive metrics for a single procedure.
    """

    code: str
    display: str

    n_patients: int
    utilisation_prevalence: float

    n_procedures: int

    mean_age_at_procedure: float
    median_age_at_procedure: float
    min_age_at_procedure: float
    max_age_at_procedure: float

    male_patients: int
    female_patients: int

    male_patient_fraction: float
    female_patient_fraction: float

    mean_duration_days: float
    median_duration_days: float

    repeat_patients: int
    repeat_rate: float

    total_base_cost: float
    mean_base_cost: float


@dataclass(slots=True)
class ProcedureProfileMetrics:
    """
    Procedure profile of an entire synthetic cohort.
    """

    n_procedures: int
    n_distinct_procedures: int

    patients_with_procedures: int
    patients_without_procedures: int

    high_utilisation_patients: int

    mean_procedures_per_patient: float
    median_procedures_per_patient: float
    std_procedures_per_patient: float

    procedures_per_patient: pd.DataFrame

    top_procedures: pd.DataFrame

    procedures: list[ProcedureMetrics]


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


def _empty_procedure_metrics(
    cohort: ValidationCohort,
) -> ProcedureProfileMetrics:
    """
    Return empty procedure metrics for cohorts without procedures.
    """

    return ProcedureProfileMetrics(

        n_procedures=0,
        n_distinct_procedures=0,

        patients_with_procedures=0,
        patients_without_procedures=cohort.n_patients,

        high_utilisation_patients=0,

        mean_procedures_per_patient=0.0,
        median_procedures_per_patient=0.0,
        std_procedures_per_patient=0.0,

        procedures_per_patient=pd.DataFrame(
            columns=[
                PROCEDURE_PATIENT_COLUMN,
                "procedures",
            ]
        ),

        top_procedures=pd.DataFrame(
            columns=[
                PROCEDURE_CODE_COLUMN,
                PROCEDURE_DESCRIPTION_COLUMN,
                "count",
            ]
        ),

        procedures=[],
    )


# =============================================================================
# Public API
# =============================================================================

def calculate_procedures(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    high_utilisation_threshold: int = 10,
) -> ProcedureProfileMetrics:
    """
    Compute descriptive procedure metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate patient age and open procedure duration.

    top_n
        Number of most frequent procedures returned in top_procedures.

    high_utilisation_threshold
        Minimum number of procedure records used to classify a patient
        as having high procedure utilisation.

    Returns
    -------
    ProcedureProfileMetrics
    """

    if cohort.procedures is None or cohort.procedures.empty:
        return _empty_procedure_metrics(cohort)

    patients = prepare_patients(
        cohort.patients,
        reference_date,
    )

    procedures = cohort.procedures.copy()

    procedures[PROCEDURE_START_COLUMN] = pd.to_datetime(
        procedures[PROCEDURE_START_COLUMN],
        errors="coerce",
    )

    if PROCEDURE_STOP_COLUMN in procedures.columns:
        procedures[PROCEDURE_STOP_COLUMN] = pd.to_datetime(
            procedures[PROCEDURE_STOP_COLUMN],
            errors="coerce",
        )
    else:
        procedures[PROCEDURE_STOP_COLUMN] = pd.NaT

    if PROCEDURE_BASE_COST_COLUMN in procedures.columns:
        procedures[PROCEDURE_BASE_COST_COLUMN] = pd.to_numeric(
            procedures[PROCEDURE_BASE_COST_COLUMN],
            errors="coerce",
        )
    else:
        procedures[PROCEDURE_BASE_COST_COLUMN] = 0.0

    # -------------------------------------------------------------------------
    # Procedures per patient
    # -------------------------------------------------------------------------

    procedures_per_patient = (
        procedures
        .groupby(PROCEDURE_PATIENT_COLUMN)
        .size()
        .rename("procedures")
        .reset_index()
    )

    all_patient_procedure_counts = (
        patients[[PATIENT_ID_COLUMN]]
        .merge(
            procedures_per_patient,
            left_on=PATIENT_ID_COLUMN,
            right_on=PROCEDURE_PATIENT_COLUMN,
            how="left",
        )
        ["procedures"]
        .fillna(0)
    )

    # -------------------------------------------------------------------------
    # Global procedure burden
    # -------------------------------------------------------------------------

    patients_with_procedures = int(
        (all_patient_procedure_counts > 0).sum()
    )

    patients_without_procedures = (
        cohort.n_patients
        - patients_with_procedures
    )

    high_utilisation_patients = int(
        (
            all_patient_procedure_counts
            >= high_utilisation_threshold
        ).sum()
    )

    # -------------------------------------------------------------------------
    # Top procedures
    # -------------------------------------------------------------------------

    top_procedures = (
        procedures
        .groupby(
            [
                PROCEDURE_CODE_COLUMN,
                PROCEDURE_DESCRIPTION_COLUMN,
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
    # Procedure-level metrics
    # -------------------------------------------------------------------------

    procedure_metrics: list[ProcedureMetrics] = []

    patient_demographics = patients[
        [
            PATIENT_ID_COLUMN,
            PATIENT_GENDER_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
        ]
    ]

    for code, procedure_events in procedures.groupby(
        PROCEDURE_CODE_COLUMN,
        dropna=False,
    ):
        procedure_events = procedure_events.merge(
            patient_demographics,
            left_on=PROCEDURE_PATIENT_COLUMN,
            right_on=PATIENT_ID_COLUMN,
            how="left",
        )

        start = procedure_events[PROCEDURE_START_COLUMN]
        stop = procedure_events[PROCEDURE_STOP_COLUMN]

        birthdate = pd.to_datetime(
            procedure_events[PATIENT_BIRTHDATE_COLUMN],
            errors="coerce",
        )

        age_at_procedure = (
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

        patient_procedure_counts = (
            procedure_events
            .groupby(PROCEDURE_PATIENT_COLUMN)
            .size()
        )

        procedure_patients = (
            procedure_events
            .drop_duplicates(PROCEDURE_PATIENT_COLUMN)
        )

        n_patients = int(patient_procedure_counts.size)
        n_procedures = int(len(procedure_events))

        male_patients = int(
            (
                procedure_patients[PATIENT_GENDER_COLUMN]
                == "M"
            ).sum()
        )

        female_patients = int(
            (
                procedure_patients[PATIENT_GENDER_COLUMN]
                == "F"
            ).sum()
        )

        repeat_patients = int(
            (patient_procedure_counts > 1).sum()
        )

        display_values = (
            procedure_events[PROCEDURE_DESCRIPTION_COLUMN]
            .dropna()
        )

        display = (
            str(display_values.iloc[0])
            if not display_values.empty
            else str(code)
        )

        base_cost = procedure_events[PROCEDURE_BASE_COST_COLUMN]

        procedure_metrics.append(
            ProcedureMetrics(

                code=str(code),
                display=display,

                n_patients=n_patients,
                utilisation_prevalence=_safe_fraction(
                    n_patients,
                    cohort.n_patients,
                ),

                n_procedures=n_procedures,

                mean_age_at_procedure=age_at_procedure.mean(),
                median_age_at_procedure=age_at_procedure.median(),
                min_age_at_procedure=age_at_procedure.min(),
                max_age_at_procedure=age_at_procedure.max(),

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

                repeat_patients=repeat_patients,
                repeat_rate=_safe_fraction(
                    repeat_patients,
                    n_patients,
                ),

                total_base_cost=base_cost.fillna(0.0).sum(),
                mean_base_cost=base_cost.mean() if not base_cost.dropna().empty else 0.0,
            )
        )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    return ProcedureProfileMetrics(

        n_procedures=len(procedures),
        n_distinct_procedures=int(
            procedures[PROCEDURE_CODE_COLUMN].nunique(dropna = True)
        ),

        patients_with_procedures=patients_with_procedures,
        patients_without_procedures=patients_without_procedures,

        high_utilisation_patients=high_utilisation_patients,

        mean_procedures_per_patient=all_patient_procedure_counts.mean(),
        median_procedures_per_patient=all_patient_procedure_counts.median(),
        std_procedures_per_patient=all_patient_procedure_counts.std(),

        procedures_per_patient=procedures_per_patient,

        top_procedures=top_procedures,

        procedures=procedure_metrics,
    )