"""
Healthcare utilisation metrics.

This module computes descriptive encounter statistics from a ValidationCohort.

The resulting metrics quantify how patients interact with the simulated
healthcare system and provide the basis for healthcare utilisation
validation.

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
    ENCOUNTER_PATIENT_COLUMN,
    ENCOUNTER_CLASS_COLUMN,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class EncounterMetrics:
    """
    Descriptive healthcare utilisation metrics.
    """

    # -------------------------------------------------------------------------
    # Cohort utilisation
    # -------------------------------------------------------------------------

    n_encounters: int

    mean_encounters_per_patient: float
    median_encounters_per_patient: float
    std_encounters_per_patient: float

    min_encounters_per_patient: int
    max_encounters_per_patient: int

    patients_without_encounters: int

    # -------------------------------------------------------------------------
    # Encounter distributions
    # -------------------------------------------------------------------------

    encounters_per_patient: pd.DataFrame
    encounter_type_distribution: pd.DataFrame

    # -------------------------------------------------------------------------
    # Demographic distributions
    # -------------------------------------------------------------------------

    encounters_by_age_band: pd.DataFrame
    encounters_by_sex: pd.DataFrame


# =============================================================================
# Public API
# =============================================================================

def calculate_encounters(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> EncounterMetrics:
    """
    Compute healthcare utilisation metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate patient age.

    Returns
    -------
    EncounterMetrics
    """

    patients = prepare_patients(
        cohort.patients,
        reference_date,
    )

    encounters = cohort.encounters.copy()

    # -------------------------------------------------------------------------
    # Encounters per patient
    # -------------------------------------------------------------------------

    encounters_per_patient = (
        encounters
        .groupby(ENCOUNTER_PATIENT_COLUMN)
        .size()
        .rename("encounters")
        .reset_index()
    )

    counts = encounters_per_patient["encounters"]

    # -------------------------------------------------------------------------
    # Encounter type distribution
    # -------------------------------------------------------------------------

    encounter_type_distribution = (
        encounters[ENCOUNTER_CLASS_COLUMN]
        .value_counts()
        .rename_axis("encounter_type")
        .reset_index(name="count")
    )

    # -------------------------------------------------------------------------
    # Encounters by age band
    # -------------------------------------------------------------------------

    encounters_by_age_band = (
        encounters
        .merge(
            patients[
                [
                    PATIENT_ID_COLUMN,
                    "AGE_BAND",
                ]
            ],
            left_on=ENCOUNTER_PATIENT_COLUMN,
            right_on=PATIENT_ID_COLUMN,
            how="left",
        )
        .groupby(
            "AGE_BAND",
            observed=False,
        )
        .size()
        .reset_index(name="count")
    )

    # -------------------------------------------------------------------------
    # Encounters by sex
    # -------------------------------------------------------------------------

    encounters_by_sex = (
        encounters
        .merge(
            patients[
                [
                    PATIENT_ID_COLUMN,
                    PATIENT_GENDER_COLUMN,
                ]
            ],
            left_on=ENCOUNTER_PATIENT_COLUMN,
            right_on=PATIENT_ID_COLUMN,
            how="left",
        )
        .groupby(PATIENT_GENDER_COLUMN)
        .size()
        .reset_index(name="count")
    )

    # -------------------------------------------------------------------------
    # Patients without encounters
    # -------------------------------------------------------------------------

    patients_without_encounters = (
        cohort.n_patients
        - len(encounters_per_patient)
    )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    return EncounterMetrics(

        n_encounters=len(encounters),

        mean_encounters_per_patient=counts.mean(),
        median_encounters_per_patient=counts.median(),
        std_encounters_per_patient=counts.std(),

        min_encounters_per_patient=int(counts.min()),
        max_encounters_per_patient=int(counts.max()),

        patients_without_encounters=patients_without_encounters,

        encounters_per_patient=encounters_per_patient,

        encounter_type_distribution=encounter_type_distribution,

        encounters_by_age_band=encounters_by_age_band,

        encounters_by_sex=encounters_by_sex,
    )