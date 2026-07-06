"""
Demographic validation metrics.

This module computes descriptive demographic statistics from a ValidationCohort.

The resulting metrics are used by statistical analyses, visualisations
and validation reports.

No statistical testing, plotting or report generation should be implemented
in this module.
"""

from dataclasses import dataclass

import pandas as pd

from validation.models import ValidationCohort

from validation.constants import AGE_BANDS, AGE_LABELS




# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class DemographicMetrics:
    """
    Descriptive demographic metrics of a synthetic cohort.
    """

    # Cohort size
    n_patients: int

    # Age summary
    mean_age: float
    median_age: float
    std_age: float
    variance_age: float

    min_age: float
    max_age: float

    # Percentiles
    p05_age: float
    p10_age: float
    p25_age: float
    p50_age: float
    p75_age: float
    p90_age: float
    p95_age: float

    # Sex
    male_count: int
    female_count: int

    male_fraction: float
    female_fraction: float

    # Distributions
    age_distribution: pd.DataFrame
    age_band_distribution: pd.DataFrame
    population_pyramid: pd.DataFrame


# =============================================================================
# Public API
# =============================================================================

def calculate_demographics(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> DemographicMetrics:
    """
    Compute descriptive demographic metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate patient age.

    Returns
    -------
    DemographicMetrics
    """

    patients = cohort.patients.copy()

    birthdate = pd.to_datetime(patients["BIRTHDATE"])

    patients["AGE"] = (
        (reference_date - birthdate).dt.days / 365.25
    )

    age = patients["AGE"]

    # -------------------------------------------------------------------------
    # Sex
    # -------------------------------------------------------------------------

    male = (patients["GENDER"] == "M").sum()
    female = (patients["GENDER"] == "F").sum()

    # -------------------------------------------------------------------------
    # Age distribution
    # -------------------------------------------------------------------------

    age_distribution = (
        age
        .round()
        .astype(int)
        .value_counts()
        .sort_index()
        .rename_axis("age")
        .reset_index(name="count")
    )

    # -------------------------------------------------------------------------
    # Age bands
    # -------------------------------------------------------------------------

    patients["AGE_BAND"] = pd.cut(
        age,
        bins=AGE_BANDS,
        labels=AGE_LABELS,
        right=False,
    )

    age_band_distribution = (
        patients["AGE_BAND"]
        .value_counts()
        .sort_index()
        .rename_axis("age_band")
        .reset_index(name="count")
    )

    # -------------------------------------------------------------------------
    # Population pyramid
    # -------------------------------------------------------------------------

    population_pyramid = (
        patients
        .groupby(
            [
                "AGE_BAND",
                "GENDER",
            ],
            observed=False,
        )
        .size()
        .reset_index(name="count")
    )

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    return DemographicMetrics(

        n_patients=len(patients),

        mean_age=age.mean(),
        median_age=age.median(),
        std_age=age.std(),
        variance_age=age.var(),

        min_age=age.min(),
        max_age=age.max(),

        p05_age=age.quantile(0.05),
        p10_age=age.quantile(0.10),
        p25_age=age.quantile(0.25),
        p50_age=age.quantile(0.50),
        p75_age=age.quantile(0.75),
        p90_age=age.quantile(0.90),
        p95_age=age.quantile(0.95),

        male_count=male,
        female_count=female,

        male_fraction=male / len(patients),
        female_fraction=female / len(patients),

        age_distribution=age_distribution,
        age_band_distribution=age_band_distribution,
        population_pyramid=population_pyramid,
    )