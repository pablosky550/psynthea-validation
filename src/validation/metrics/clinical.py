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