"""
Observation validation metrics.

This module computes descriptive observation metrics from a ValidationCohort.

The resulting metrics quantify observation utilisation, age at observation,
numeric value distributions, missing values, repeated observations and high
observation utilisation.

No statistical hypothesis testing, plotting or report generation should
be implemented in this module.
"""

from dataclasses import dataclass

import pandas as pd

from validation.models import ValidationCohort
from validation.utils import prepare_patients

_NUMERIC_VALUE_COLUMN = "NUMERIC_VALUE"

from validation.constants import (
    PATIENT_ID_COLUMN,
    PATIENT_GENDER_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    OBSERVATION_PATIENT_COLUMN,
    OBSERVATION_CODE_COLUMN,
    OBSERVATION_DESCRIPTION_COLUMN,
    OBSERVATION_DATE_COLUMN,
    OBSERVATION_VALUE_COLUMN,
    OBSERVATION_UNITS_COLUMN,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class ObservationMetrics:
    """
    Descriptive metrics for a single clinical observation.
    """

    code: str
    display: str

    n_patients: int
    observation_prevalence: float

    n_observations: int

    mean_age_at_observation: float
    median_age_at_observation: float
    min_age_at_observation: float
    max_age_at_observation: float

    male_patients: int
    female_patients: int

    male_patient_fraction: float
    female_patient_fraction: float

    numeric_observations: int
    non_numeric_observations: int

    missing_value_count: int
    missing_value_fraction: float

    mean_value: float
    median_value: float
    std_value: float
    min_value: float
    max_value: float

    repeat_patients: int
    repeat_rate: float

    most_common_unit: str | None


@dataclass(slots=True)
class ObservationProfileMetrics:
    """
    Observation profile of an entire synthetic cohort.
    """

    n_observations: int
    n_distinct_observations: int

    patients_with_observations: int
    patients_without_observations: int

    high_utilisation_patients: int

    mean_observations_per_patient: float
    median_observations_per_patient: float
    std_observations_per_patient: float

    observations_per_patient: pd.DataFrame

    top_observations: pd.DataFrame
    numeric_observations: pd.DataFrame

    observations: list[ObservationMetrics]


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


def _empty_observation_metrics(
    cohort: ValidationCohort,
) -> ObservationProfileMetrics:
    """
    Return empty observation metrics for cohorts without observations.
    """

    return ObservationProfileMetrics(

        n_observations=0,
        n_distinct_observations=0,

        patients_with_observations=0,
        patients_without_observations=cohort.n_patients,

        high_utilisation_patients=0,

        mean_observations_per_patient=0.0,
        median_observations_per_patient=0.0,
        std_observations_per_patient=0.0,

        observations_per_patient=pd.DataFrame(
            columns=[
                OBSERVATION_PATIENT_COLUMN,
                "observations",
            ]
        ),

        top_observations=pd.DataFrame(
            columns=[
                OBSERVATION_CODE_COLUMN,
                OBSERVATION_DESCRIPTION_COLUMN,
                "count",
            ]
        ),

        numeric_observations=pd.DataFrame(
            columns=[
                OBSERVATION_CODE_COLUMN,
                OBSERVATION_DESCRIPTION_COLUMN,
                "numeric_count",
            ]
        ),

        observations=[],
    )


def _most_common_unit(
    observation_events: pd.DataFrame,
) -> str | None:
    """
    Return the most common unit for an observation group.
    """

    if OBSERVATION_UNITS_COLUMN not in observation_events.columns:
        return None

    unit_counts = (
        observation_events[OBSERVATION_UNITS_COLUMN]
        .dropna()
        .astype(str)
        .value_counts()
    )

    if unit_counts.empty:
        return None

    return str(unit_counts.index[0])


# =============================================================================
# Public API
# =============================================================================

def calculate_observations(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    high_utilisation_threshold: int = 100,
) -> ObservationProfileMetrics:
    """
    Compute descriptive clinical observation metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate patient age.

    top_n
        Number of most frequent observations returned in top_observations
        and numeric_observations.

    high_utilisation_threshold
        Minimum number of observation records used to classify a patient
        as having high observation utilisation.

    Returns
    -------
    ObservationProfileMetrics
    """

    if cohort.observations is None or cohort.observations.empty:
        return _empty_observation_metrics(cohort)

    patients = prepare_patients(
        cohort.patients,
        reference_date,
    )

    observations = cohort.observations.copy()

    observations[OBSERVATION_DATE_COLUMN] = pd.to_datetime(
        observations[OBSERVATION_DATE_COLUMN],
        errors="coerce",
    )

    if OBSERVATION_VALUE_COLUMN in observations.columns:
        observations[_NUMERIC_VALUE_COLUMN] = pd.to_numeric(
            observations[OBSERVATION_VALUE_COLUMN],
            errors="coerce",
        )
    else:
        observations[OBSERVATION_VALUE_COLUMN] = pd.NA
        observations[_NUMERIC_VALUE_COLUMN] = pd.NA

    # -------------------------------------------------------------------------
    # Observations per patient
    # -------------------------------------------------------------------------

    observations_per_patient = (
        observations
        .groupby(OBSERVATION_PATIENT_COLUMN)
        .size()
        .rename("observations")
        .reset_index()
    )

    all_patient_observation_counts = (
        patients[[PATIENT_ID_COLUMN]]
        .merge(
            observations_per_patient,
            left_on=PATIENT_ID_COLUMN,
            right_on=OBSERVATION_PATIENT_COLUMN,
            how="left",
        )
        ["observations"]
        .fillna(0)
    )

    # -------------------------------------------------------------------------
    # Global observation burden
    # -------------------------------------------------------------------------

    patients_with_observations = int(
        (all_patient_observation_counts > 0).sum()
    )

    patients_without_observations = (
        cohort.n_patients
        - patients_with_observations
    )

    high_utilisation_patients = int(
        (
            all_patient_observation_counts
            >= high_utilisation_threshold
        ).sum()
    )

    # -------------------------------------------------------------------------
    # Top observations
    # -------------------------------------------------------------------------

    top_observations = (
        observations
        .groupby(
            [
                OBSERVATION_CODE_COLUMN,
                OBSERVATION_DESCRIPTION_COLUMN,
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
    # Numeric observations
    # -------------------------------------------------------------------------

    numeric_observations = (
        observations[observations[_NUMERIC_VALUE_COLUMN].notna()]
        .groupby(
            [
                OBSERVATION_CODE_COLUMN,
                OBSERVATION_DESCRIPTION_COLUMN,
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="numeric_count")
        .sort_values(
            "numeric_count",
            ascending=False,
        )
        .head(top_n)
        .reset_index(drop=True)
    )

    # -------------------------------------------------------------------------
    # Observation-level metrics
    # -------------------------------------------------------------------------

    observation_metrics: list[ObservationMetrics] = []

    patient_demographics = patients[
        [
            PATIENT_ID_COLUMN,
            PATIENT_GENDER_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
        ]
    ]

    for code, observation_events in observations.groupby(
        OBSERVATION_CODE_COLUMN,
        dropna=False,
    ):
        observation_events = observation_events.merge(
            patient_demographics,
            left_on=OBSERVATION_PATIENT_COLUMN,
            right_on=PATIENT_ID_COLUMN,
            how="left",
        )

        date = observation_events[OBSERVATION_DATE_COLUMN]

        birthdate = pd.to_datetime(
            observation_events[PATIENT_BIRTHDATE_COLUMN],
            errors="coerce",
        )

        age_at_observation = (
            (date - birthdate).dt.days / 365.25
        )

        age_at_observation = age_at_observation.where(
            age_at_observation >= 0
        )

        patient_observation_counts = (
            observation_events
            .groupby(OBSERVATION_PATIENT_COLUMN)
            .size()
        )

        observation_patients = (
            observation_events
            .drop_duplicates(OBSERVATION_PATIENT_COLUMN)
        )

        n_patients = int(patient_observation_counts.size)
        n_observations = int(len(observation_events))

        male_patients = int(
            (
                observation_patients[PATIENT_GENDER_COLUMN]
                == "M"
            ).sum()
        )

        female_patients = int(
            (
                observation_patients[PATIENT_GENDER_COLUMN]
                == "F"
            ).sum()
        )

        value = observation_events[OBSERVATION_VALUE_COLUMN]
        numeric_value = observation_events[_NUMERIC_VALUE_COLUMN]

        value_missing = (
            value.isna()
            | value.astype(str).str.strip().eq("")
        )

        missing_value_count = int(value_missing.sum())
        numeric_observation_count = int(numeric_value.notna().sum())
        non_numeric_observation_count = int(
            n_observations
            - numeric_observation_count
            - missing_value_count
        )

        repeat_patients = int(
            (patient_observation_counts > 1).sum()
        )

        display_values = (
            observation_events[OBSERVATION_DESCRIPTION_COLUMN]
            .dropna()
        )

        display = (
            str(display_values.iloc[0])
            if not display_values.empty
            else str(code)
        )

        observation_metrics.append(
            ObservationMetrics(

                code=str(code),
                display=display,

                n_patients=n_patients,
                observation_prevalence=_safe_fraction(
                    n_patients,
                    cohort.n_patients,
                ),

                n_observations=n_observations,

                mean_age_at_observation=age_at_observation.mean(),
                median_age_at_observation=age_at_observation.median(),
                min_age_at_observation=age_at_observation.min(),
                max_age_at_observation=age_at_observation.max(),

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

                numeric_observations=numeric_observation_count,
                non_numeric_observations=non_numeric_observation_count,

                missing_value_count=missing_value_count,
                missing_value_fraction=_safe_fraction(
                    missing_value_count,
                    n_observations,
                ),

                mean_value=numeric_value.mean(),
                median_value=numeric_value.median(),
                std_value=numeric_value.std(),
                min_value=numeric_value.min(),
                max_value=numeric_value.max(),

                repeat_patients=repeat_patients,
                repeat_rate=_safe_fraction(
                    repeat_patients,
                    n_patients,
                ),

                most_common_unit=_most_common_unit(observation_events),
            )
        )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    return ObservationProfileMetrics(

        n_observations=len(observations),
        n_distinct_observations=int(
            observations[OBSERVATION_CODE_COLUMN].nunique(dropna=True)
        ),

        patients_with_observations=patients_with_observations,
        patients_without_observations=patients_without_observations,

        high_utilisation_patients=high_utilisation_patients,

        mean_observations_per_patient=all_patient_observation_counts.mean(),
        median_observations_per_patient=all_patient_observation_counts.median(),
        std_observations_per_patient=all_patient_observation_counts.std(),

        observations_per_patient=observations_per_patient,

        top_observations=top_observations,
        numeric_observations=numeric_observations,

        observations=observation_metrics,
    )
