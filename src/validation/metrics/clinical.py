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
from typing import TYPE_CHECKING, Any

import pandas as pd

from validation.models import ValidationCohort
from validation.utils import prepare_patients

if TYPE_CHECKING:
    from validation.metrics.cohorts import ObservationWindow

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
class DiseaseEpidemiologyMetrics:
    """Observation-window epidemiology for one clinical condition."""

    code: str
    display: str

    eligible_patients: int
    prevalent_patients: int
    incident_patients: int
    at_risk_patients: int

    period_prevalence: float
    cumulative_incidence: float

    mean_incident_onset_age: float
    median_incident_onset_age: float
    min_incident_onset_age: float
    max_incident_onset_age: float


@dataclass(slots=True)
class ClinicalEpidemiologyMetrics:
    """Condition epidemiology for a closed observation window."""

    observation_start: pd.Timestamp
    observation_end: pd.Timestamp

    eligible_patients: int
    prevalent_patients: int
    incident_patients: int

    diseases: list[DiseaseEpidemiologyMetrics]


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

    epidemiology: ClinicalEpidemiologyMetrics | None = None

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


def _first_display_value(
    conditions: pd.DataFrame,
    code: Any,
) -> str:
    """Return the first non-null display label for a condition code."""

    if CONDITION_DESCRIPTION_COLUMN not in conditions.columns:
        return str(code)

    display_values = conditions[CONDITION_DESCRIPTION_COLUMN].dropna()

    if display_values.empty:
        return str(code)

    return str(display_values.iloc[0])


def _normalise_condition_dates(
    conditions: pd.DataFrame,
) -> pd.DataFrame:
    """Return a copy with canonical condition timestamps normalised."""

    normalised = conditions.copy()

    for column in (
        CONDITION_START_COLUMN,
        CONDITION_STOP_COLUMN,
    ):
        normalised[column] = pd.to_datetime(
            normalised[column],
            errors="coerce",
            utc=True,
        ).dt.tz_convert(None)

    return normalised


def _incident_onset_age(
    incident_conditions: pd.DataFrame,
    patients: pd.DataFrame,
) -> pd.Series:
    """Calculate age at first incident onset for each patient."""

    if incident_conditions.empty:
        return pd.Series(dtype="float64")

    first_onsets = (
        incident_conditions
        .dropna(
            subset=[
                CONDITION_PATIENT_COLUMN,
                CONDITION_START_COLUMN,
            ]
        )
        .groupby(CONDITION_PATIENT_COLUMN, as_index=False)
        [CONDITION_START_COLUMN]
        .min()
    )

    patient_birthdates = patients[
        [
            PATIENT_ID_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
        ]
    ].copy()
    patient_birthdates[PATIENT_BIRTHDATE_COLUMN] = pd.to_datetime(
        patient_birthdates[PATIENT_BIRTHDATE_COLUMN],
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)

    first_onsets = first_onsets.merge(
        patient_birthdates,
        left_on=CONDITION_PATIENT_COLUMN,
        right_on=PATIENT_ID_COLUMN,
        how="left",
    )

    onset_age = (
        first_onsets[CONDITION_START_COLUMN]
        .sub(first_onsets[PATIENT_BIRTHDATE_COLUMN])
        .dt.days
        .div(365.25)
    )

    return onset_age.where(onset_age.ge(0))


def calculate_clinical_epidemiology(
    cohort: ValidationCohort,
    observation_window: "ObservationWindow",
) -> ClinicalEpidemiologyMetrics:
    """
    Compute condition epidemiology for one explicit observation window.

    Temporal membership and disease-specific populations at risk are delegated
    to ``validation.metrics.cohorts``. This function only converts those
    selections into epidemiological measures.
    """

    from validation.metrics.cohorts import build_temporal_condition_cohorts

    temporal = build_temporal_condition_cohorts(
        cohort,
        observation_window,
    )

    conditions = cohort.conditions

    if conditions is None or conditions.empty:
        return ClinicalEpidemiologyMetrics(
            observation_start=observation_window.start,
            observation_end=observation_window.end,
            eligible_patients=temporal.n_eligible_patients,
            prevalent_patients=0,
            incident_patients=0,
            diseases=[],
        )

    patients = cohort.patients
    if patients is None:
        patients = pd.DataFrame(
            columns=[
                PATIENT_ID_COLUMN,
                PATIENT_BIRTHDATE_COLUMN,
            ]
        )

    prevalent_conditions = _normalise_condition_dates(
        temporal.prevalent_conditions
    )
    incident_conditions = _normalise_condition_dates(
        temporal.incident_conditions
    )

    observed_codes = sorted(
        {
            str(code)
            for code in conditions[CONDITION_CODE_COLUMN].dropna().tolist()
        }
    )

    diseases: list[DiseaseEpidemiologyMetrics] = []
    incident_patient_ids_across_diseases: set[Any] = set()

    for code in observed_codes:
        all_disease_conditions = conditions.loc[
            conditions[CONDITION_CODE_COLUMN].astype("string").eq(code)
        ]
        prevalent_disease_conditions = prevalent_conditions.loc[
            prevalent_conditions[CONDITION_CODE_COLUMN]
            .astype("string")
            .eq(code)
        ]
        incident_disease_conditions = incident_conditions.loc[
            incident_conditions[CONDITION_CODE_COLUMN]
            .astype("string")
            .eq(code)
        ]

        at_risk_patient_ids = temporal.at_risk_patient_ids_by_condition.get(
            code,
            frozenset(),
        )
        prevalent_patient_ids = frozenset(
            prevalent_disease_conditions[CONDITION_PATIENT_COLUMN]
            .dropna()
            .tolist()
        )
        raw_incident_patient_ids = frozenset(
            incident_disease_conditions[CONDITION_PATIENT_COLUMN]
            .dropna()
            .tolist()
        )
        incident_patient_ids = raw_incident_patient_ids.intersection(
            at_risk_patient_ids
        )
        incident_patient_ids_across_diseases.update(incident_patient_ids)

        incident_at_risk_conditions = incident_disease_conditions.loc[
            incident_disease_conditions[CONDITION_PATIENT_COLUMN].isin(
                incident_patient_ids
            )
        ]
        onset_age = _incident_onset_age(
            incident_at_risk_conditions,
            patients,
        )

        diseases.append(
            DiseaseEpidemiologyMetrics(
                code=code,
                display=_first_display_value(
                    all_disease_conditions,
                    code,
                ),
                eligible_patients=temporal.n_eligible_patients,
                prevalent_patients=len(prevalent_patient_ids),
                incident_patients=len(incident_patient_ids),
                at_risk_patients=len(at_risk_patient_ids),
                period_prevalence=_safe_fraction(
                    len(prevalent_patient_ids),
                    temporal.n_eligible_patients,
                ),
                cumulative_incidence=_safe_fraction(
                    len(incident_patient_ids),
                    len(at_risk_patient_ids),
                ),
                mean_incident_onset_age=onset_age.mean(),
                median_incident_onset_age=onset_age.median(),
                min_incident_onset_age=onset_age.min(),
                max_incident_onset_age=onset_age.max(),
            )
        )

    return ClinicalEpidemiologyMetrics(
        observation_start=observation_window.start,
        observation_end=observation_window.end,
        eligible_patients=temporal.n_eligible_patients,
        prevalent_patients=temporal.n_prevalent_patients,
        incident_patients=len(incident_patient_ids_across_diseases),
        diseases=diseases,
    )


# =============================================================================
# Public API
# =============================================================================

def calculate_clinical(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    *,
    observation_window: "ObservationWindow | None" = None,
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

    observation_window
        Optional closed interval used to calculate explicit epidemiological
        metrics. Descriptive metrics remain based on the full condition table.

    Returns
    -------
    ClinicalMetrics
    """

    if cohort.conditions is None or cohort.conditions.empty:
        metrics = _empty_clinical_metrics(cohort)

        if observation_window is not None:
            metrics.epidemiology = calculate_clinical_epidemiology(
                cohort,
                observation_window,
            )

        return metrics

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
    # Optional observation-window epidemiology
    # -------------------------------------------------------------------------

    epidemiology = (
        calculate_clinical_epidemiology(
            cohort,
            observation_window,
        )
        if observation_window is not None
        else None
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
        epidemiology=epidemiology,
    )