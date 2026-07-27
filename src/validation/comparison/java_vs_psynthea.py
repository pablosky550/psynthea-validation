"""
Java vs psynthea cohort comparison.

This module compares two already-loaded ValidationCohort objects using the
cohort-level descriptive metrics produced during Phase 1.

The comparison layer answers what changed between Synthea Java and psynthea.
It does not load CSV files, compute low-level metrics, run statistical tests,
create plots or generate reports.

Statistical inference is intentionally left to validation.statistics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from validation.metrics.cohorts import (
    CohortProfileMetrics,
    ObservationWindow,
    calculate_cohort_profile,
)
from validation.models import ValidationCohort


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class MetricComparison:
    """
    Difference for one scalar validation metric.
    """

    domain: str
    metric: str

    synthea_value: float | int | str | None
    psynthea_value: float | int | str | None

    absolute_difference: float | None
    relative_difference: float | None


@dataclass(slots=True)
class DomainComparison:
    """
    Tabular comparison for one validation domain.
    """

    domain: str
    metrics: pd.DataFrame


@dataclass(slots=True)
class CodedEventComparison:
    """
    Comparison of coded clinical items between both generators.
    """

    domain: str
    code_column: str
    display_column: str
    metrics: pd.DataFrame


@dataclass(slots=True)
class JavaVsPsyntheaComparison:
    """
    Complete descriptive comparison between Synthea Java and psynthea.
    """

    synthea_profile: CohortProfileMetrics
    psynthea_profile: CohortProfileMetrics

    table_counts: DomainComparison
    demographics: DomainComparison | None
    encounters: DomainComparison | None
    clinical: DomainComparison | None
    epidemiology: DomainComparison | None
    disease_epidemiology: CodedEventComparison | None
    medications: DomainComparison | None
    procedures: DomainComparison | None
    observations: DomainComparison | None

    top_conditions: CodedEventComparison | None
    top_medications: CodedEventComparison | None
    top_procedures: CodedEventComparison | None
    top_observations: CodedEventComparison | None

    summary: pd.DataFrame


# =============================================================================
# Scalar comparison helpers
# =============================================================================

def _as_number(
    value: Any,
) -> float | None:
    """
    Return a float when a value can be treated as numeric.
    """

    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, bool):
        return float(value)

    if isinstance(value, int | float):
        return float(value)

    return None


def _absolute_difference(
    synthea_value: Any,
    psynthea_value: Any,
) -> float | None:
    """
    Return psynthea minus Synthea for numeric values.
    """

    synthea_number = _as_number(synthea_value)
    psynthea_number = _as_number(psynthea_value)

    if synthea_number is None or psynthea_number is None:
        return None

    return psynthea_number - synthea_number


def _relative_difference(
    synthea_value: Any,
    psynthea_value: Any,
) -> float | None:
    """
    Return the relative difference against the Synthea Java value.
    """

    synthea_number = _as_number(synthea_value)
    absolute_difference = _absolute_difference(
        synthea_value,
        psynthea_value,
    )

    if synthea_number in (None, 0.0):
        return None

    if absolute_difference is None:
        return None

    return absolute_difference / synthea_number


def _metric_comparison(
    domain: str,
    metric: str,
    synthea_value: Any,
    psynthea_value: Any,
) -> MetricComparison:
    """
    Build a scalar metric comparison object.
    """

    return MetricComparison(
        domain=domain,
        metric=metric,
        synthea_value=synthea_value,
        psynthea_value=psynthea_value,
        absolute_difference=_absolute_difference(
            synthea_value,
            psynthea_value,
        ),
        relative_difference=_relative_difference(
            synthea_value,
            psynthea_value,
        ),
    )


def _comparison_table(
    rows: list[MetricComparison],
) -> pd.DataFrame:
    """
    Convert scalar metric comparisons into a stable DataFrame.
    """

    return pd.DataFrame(
        [
            asdict(row)
            for row in rows
        ],
        columns=[
            "domain",
            "metric",
            "synthea_value",
            "psynthea_value",
            "absolute_difference",
            "relative_difference",
        ],
    )


def _domain_comparison(
    domain: str,
    metrics: list[tuple[str, Any, Any]],
) -> DomainComparison:
    """
    Build a DomainComparison from metric tuples.
    """

    rows = [
        _metric_comparison(
            domain,
            metric,
            synthea_value,
            psynthea_value,
        )
        for metric, synthea_value, psynthea_value in metrics
    ]

    return DomainComparison(
        domain=domain,
        metrics=_comparison_table(rows),
    )


# =============================================================================
# Coded-event comparison helpers
# =============================================================================

def _empty_coded_event_comparison(
    domain: str,
    code_column: str,
    display_column: str,
) -> CodedEventComparison:
    """
    Return an empty coded-event comparison with the canonical schema.
    """

    return CodedEventComparison(
        domain=domain,
        code_column=code_column,
        display_column=display_column,
        metrics=pd.DataFrame(
            columns=[
                code_column,
                display_column,
                "synthea_count",
                "psynthea_count",
                "absolute_difference",
                "relative_difference",
            ]
        ),
    )


def _compare_count_distributions(
    domain: str,
    synthea_distribution: pd.DataFrame | None,
    psynthea_distribution: pd.DataFrame | None,
    code_column: str,
    display_column: str,
    count_column: str = "count",
) -> CodedEventComparison | None:
    """
    Align and compare coded count distributions.

    The output keeps the union of codes observed in either generator so
    generator-specific events are visible instead of being dropped by an
    inner join.
    """

    if synthea_distribution is None or psynthea_distribution is None:
        return None

    if synthea_distribution.empty and psynthea_distribution.empty:
        return _empty_coded_event_comparison(
            domain,
            code_column,
            display_column,
        )

    required_columns = {
        code_column,
        display_column,
        count_column,
    }

    if not required_columns.issubset(synthea_distribution.columns):
        return None

    if not required_columns.issubset(psynthea_distribution.columns):
        return None

    synthea_counts = synthea_distribution[
        [
            code_column,
            display_column,
            count_column,
        ]
    ].rename(
        columns={
            count_column: "synthea_count",
            display_column: "synthea_display",
        }
    )

    psynthea_counts = psynthea_distribution[
        [
            code_column,
            display_column,
            count_column,
        ]
    ].rename(
        columns={
            count_column: "psynthea_count",
            display_column: "psynthea_display",
        }
    )

    merged = synthea_counts.merge(
        psynthea_counts,
        on=code_column,
        how="outer",
    )

    merged["synthea_count"] = merged["synthea_count"].fillna(0).astype(int)
    merged["psynthea_count"] = merged["psynthea_count"].fillna(0).astype(int)

    merged[display_column] = merged["synthea_display"].combine_first(
        merged["psynthea_display"]
    )

    merged["absolute_difference"] = (
        merged["psynthea_count"]
        - merged["synthea_count"]
    )

    merged["relative_difference"] = merged.apply(
        lambda row: _relative_difference(
            row["synthea_count"],
            row["psynthea_count"],
        ),
        axis=1,
    )

    output = (
        merged[
            [
                code_column,
                display_column,
                "synthea_count",
                "psynthea_count",
                "absolute_difference",
                "relative_difference",
            ]
        ]
        .sort_values(
            [
                "psynthea_count",
                "synthea_count",
            ],
            ascending=False,
        )
        .reset_index(drop=True)
    )

    return CodedEventComparison(
        domain=domain,
        code_column=code_column,
        display_column=display_column,
        metrics=output,
    )


# =============================================================================
# Domain builders
# =============================================================================

def _compare_table_counts(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison:
    """
    Compare canonical table sizes.
    """

    synthea_counts = synthea_profile.table_counts
    psynthea_counts = psynthea_profile.table_counts

    return _domain_comparison(
        "table_counts",
        [
            (
                "patients",
                synthea_counts.patients,
                psynthea_counts.patients,
            ),
            (
                "encounters",
                synthea_counts.encounters,
                psynthea_counts.encounters,
            ),
            (
                "conditions",
                synthea_counts.conditions,
                psynthea_counts.conditions,
            ),
            (
                "medications",
                synthea_counts.medications,
                psynthea_counts.medications,
            ),
            (
                "procedures",
                synthea_counts.procedures,
                psynthea_counts.procedures,
            ),
            (
                "observations",
                synthea_counts.observations,
                psynthea_counts.observations,
            ),
        ],
    )


def _compare_demographics(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """
    Compare demographic scalar metrics.
    """

    synthea = synthea_profile.demographics
    psynthea = psynthea_profile.demographics

    if synthea is None or psynthea is None:
        return None

    return _domain_comparison(
        "demographics",
        [
            ("n_patients", synthea.n_patients, psynthea.n_patients),
            ("mean_age", synthea.mean_age, psynthea.mean_age),
            ("median_age", synthea.median_age, psynthea.median_age),
            ("std_age", synthea.std_age, psynthea.std_age),
            ("variance_age", synthea.variance_age, psynthea.variance_age),
            ("min_age", synthea.min_age, psynthea.min_age),
            ("max_age", synthea.max_age, psynthea.max_age),
            ("p05_age", synthea.p05_age, psynthea.p05_age),
            ("p25_age", synthea.p25_age, psynthea.p25_age),
            ("p50_age", synthea.p50_age, psynthea.p50_age),
            ("p75_age", synthea.p75_age, psynthea.p75_age),
            ("p95_age", synthea.p95_age, psynthea.p95_age),
            ("male_count", synthea.male_count, psynthea.male_count),
            ("female_count", synthea.female_count, psynthea.female_count),
            ("male_fraction", synthea.male_fraction, psynthea.male_fraction),
            ("female_fraction", synthea.female_fraction, psynthea.female_fraction),
        ],
    )


def _compare_encounters(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """
    Compare healthcare utilisation scalar metrics.
    """

    synthea = synthea_profile.encounters
    psynthea = psynthea_profile.encounters

    if synthea is None or psynthea is None:
        return None

    return _domain_comparison(
        "encounters",
        [
            ("n_encounters", synthea.n_encounters, psynthea.n_encounters),
            (
                "mean_encounters_per_patient",
                synthea.mean_encounters_per_patient,
                psynthea.mean_encounters_per_patient,
            ),
            (
                "median_encounters_per_patient",
                synthea.median_encounters_per_patient,
                psynthea.median_encounters_per_patient,
            ),
            (
                "std_encounters_per_patient",
                synthea.std_encounters_per_patient,
                psynthea.std_encounters_per_patient,
            ),
            (
                "min_encounters_per_patient",
                synthea.min_encounters_per_patient,
                psynthea.min_encounters_per_patient,
            ),
            (
                "max_encounters_per_patient",
                synthea.max_encounters_per_patient,
                psynthea.max_encounters_per_patient,
            ),
            (
                "patients_without_encounters",
                synthea.patients_without_encounters,
                psynthea.patients_without_encounters,
            ),
        ],
    )


def _compare_clinical(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """
    Compare clinical burden scalar metrics.
    """

    synthea = synthea_profile.clinical
    psynthea = psynthea_profile.clinical

    if synthea is None or psynthea is None:
        return None

    return _domain_comparison(
        "clinical",
        [
            ("n_conditions", synthea.n_conditions, psynthea.n_conditions),
            (
                "patients_with_conditions",
                synthea.patients_with_conditions,
                psynthea.patients_with_conditions,
            ),
            ("healthy_patients", synthea.healthy_patients, psynthea.healthy_patients),
            (
                "multimorbid_patients",
                synthea.multimorbid_patients,
                psynthea.multimorbid_patients,
            ),
            (
                "mean_conditions_per_patient",
                synthea.mean_conditions_per_patient,
                psynthea.mean_conditions_per_patient,
            ),
            (
                "median_conditions_per_patient",
                synthea.median_conditions_per_patient,
                psynthea.median_conditions_per_patient,
            ),
            (
                "std_conditions_per_patient",
                synthea.std_conditions_per_patient,
                psynthea.std_conditions_per_patient,
            ),
        ],
    )



def _compare_epidemiology(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """Compare observation-window epidemiology at cohort level."""

    synthea_clinical = synthea_profile.clinical
    psynthea_clinical = psynthea_profile.clinical

    if synthea_clinical is None or psynthea_clinical is None:
        return None

    synthea = synthea_clinical.epidemiology
    psynthea = psynthea_clinical.epidemiology

    if synthea is None and psynthea is None:
        return None

    if synthea is None or psynthea is None:
        raise ValueError(
            "Observation-window epidemiology must be available for both "
            "simulators or for neither simulator."
        )

    if (
        synthea.observation_start != psynthea.observation_start
        or synthea.observation_end != psynthea.observation_end
    ):
        raise ValueError(
            "Synthea and psynthea epidemiology were calculated using "
            "different observation windows."
        )

    return _domain_comparison(
        "epidemiology",
        [
            (
                "eligible_patients",
                synthea.eligible_patients,
                psynthea.eligible_patients,
            ),
            (
                "prevalent_patients",
                synthea.prevalent_patients,
                psynthea.prevalent_patients,
            ),
            (
                "incident_patients",
                synthea.incident_patients,
                psynthea.incident_patients,
            ),
        ],
    )


def _disease_epidemiology_frame(profile: CohortProfileMetrics) -> pd.DataFrame:
    """Return disease epidemiology with one deterministic row per code."""

    clinical = profile.clinical
    epidemiology = clinical.epidemiology if clinical is not None else None

    columns = [
        "CODE",
        "DESCRIPTION",
        "eligible_patients",
        "prevalent_patients",
        "incident_patients",
        "at_risk_patients",
        "period_prevalence",
        "cumulative_incidence",
        "mean_incident_onset_age",
        "median_incident_onset_age",
        "min_incident_onset_age",
        "max_incident_onset_age",
    ]

    if epidemiology is None:
        return pd.DataFrame(columns=columns)

    rows = [
        {
            "CODE": disease.code,
            "DESCRIPTION": disease.display,
            "eligible_patients": disease.eligible_patients,
            "prevalent_patients": disease.prevalent_patients,
            "incident_patients": disease.incident_patients,
            "at_risk_patients": disease.at_risk_patients,
            "period_prevalence": disease.period_prevalence,
            "cumulative_incidence": disease.cumulative_incidence,
            "mean_incident_onset_age": disease.mean_incident_onset_age,
            "median_incident_onset_age": disease.median_incident_onset_age,
            "min_incident_onset_age": disease.min_incident_onset_age,
            "max_incident_onset_age": disease.max_incident_onset_age,
        }
        for disease in epidemiology.diseases
    ]

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("CODE", kind="stable")
        .reset_index(drop=True)
    )


def _compare_disease_epidemiology(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> CodedEventComparison | None:
    """Compare disease-specific denominators and epidemiological rates."""

    synthea = _disease_epidemiology_frame(synthea_profile)
    psynthea = _disease_epidemiology_frame(psynthea_profile)

    synthea_available = (
        synthea_profile.clinical is not None
        and synthea_profile.clinical.epidemiology is not None
    )
    psynthea_available = (
        psynthea_profile.clinical is not None
        and psynthea_profile.clinical.epidemiology is not None
    )

    if not synthea_available and not psynthea_available:
        return None

    if synthea_available != psynthea_available:
        raise ValueError(
            "Disease epidemiology must be available for both simulators or "
            "for neither simulator."
        )

    value_columns = [
        "eligible_patients",
        "prevalent_patients",
        "incident_patients",
        "at_risk_patients",
        "period_prevalence",
        "cumulative_incidence",
        "mean_incident_onset_age",
        "median_incident_onset_age",
        "min_incident_onset_age",
        "max_incident_onset_age",
    ]

    merged = synthea.merge(
        psynthea,
        on="CODE",
        how="outer",
        suffixes=("_synthea", "_psynthea"),
    )

    synthea_display = merged.get("DESCRIPTION_synthea")
    psynthea_display = merged.get("DESCRIPTION_psynthea")
    merged["DESCRIPTION"] = synthea_display.combine_first(psynthea_display)

    output = merged[["CODE", "DESCRIPTION"]].copy()
    for metric in value_columns:
        synthea_column = f"{metric}_synthea"
        psynthea_column = f"{metric}_psynthea"
        output[synthea_column] = merged.get(synthea_column)
        output[psynthea_column] = merged.get(psynthea_column)
        output[f"{metric}_absolute_difference"] = (
            output[psynthea_column] - output[synthea_column]
        )
        output[f"{metric}_relative_difference"] = output.apply(
            lambda row: _relative_difference(
                row[synthea_column],
                row[psynthea_column],
            ),
            axis=1,
        )

    output = output.sort_values("CODE", kind="stable").reset_index(drop=True)

    return CodedEventComparison(
        domain="disease_epidemiology",
        code_column="CODE",
        display_column="DESCRIPTION",
        metrics=output,
    )

def _compare_medications(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """
    Compare medication exposure scalar metrics.
    """

    synthea = synthea_profile.medications
    psynthea = psynthea_profile.medications

    if synthea is None or psynthea is None:
        return None

    return _domain_comparison(
        "medications",
        [
            (
                "n_medication_orders",
                synthea.n_medication_orders,
                psynthea.n_medication_orders,
            ),
            (
                "n_distinct_medications",
                synthea.n_distinct_medications,
                psynthea.n_distinct_medications,
            ),
            (
                "patients_with_medications",
                synthea.patients_with_medications,
                psynthea.patients_with_medications,
            ),
            (
                "patients_without_medications",
                synthea.patients_without_medications,
                psynthea.patients_without_medications,
            ),
            (
                "polypharmacy_patients",
                synthea.polypharmacy_patients,
                psynthea.polypharmacy_patients,
            ),
            (
                "mean_medications_per_patient",
                synthea.mean_medications_per_patient,
                psynthea.mean_medications_per_patient,
            ),
            (
                "median_medications_per_patient",
                synthea.median_medications_per_patient,
                psynthea.median_medications_per_patient,
            ),
            (
                "std_medications_per_patient",
                synthea.std_medications_per_patient,
                psynthea.std_medications_per_patient,
            ),
        ],
    )


def _compare_procedures(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """
    Compare procedure utilisation scalar metrics.
    """

    synthea = synthea_profile.procedures
    psynthea = psynthea_profile.procedures

    if synthea is None or psynthea is None:
        return None

    return _domain_comparison(
        "procedures",
        [
            ("n_procedures", synthea.n_procedures, psynthea.n_procedures),
            (
                "n_distinct_procedures",
                synthea.n_distinct_procedures,
                psynthea.n_distinct_procedures,
            ),
            (
                "patients_with_procedures",
                synthea.patients_with_procedures,
                psynthea.patients_with_procedures,
            ),
            (
                "patients_without_procedures",
                synthea.patients_without_procedures,
                psynthea.patients_without_procedures,
            ),
            (
                "mean_procedures_per_patient",
                synthea.mean_procedures_per_patient,
                psynthea.mean_procedures_per_patient,
            ),
            (
                "median_procedures_per_patient",
                synthea.median_procedures_per_patient,
                psynthea.median_procedures_per_patient,
            ),
            (
                "std_procedures_per_patient",
                synthea.std_procedures_per_patient,
                psynthea.std_procedures_per_patient,
            ),
        ],
    )


def _compare_observations(
    synthea_profile: CohortProfileMetrics,
    psynthea_profile: CohortProfileMetrics,
) -> DomainComparison | None:
    """
    Compare observation volume scalar metrics.
    """

    synthea = synthea_profile.observations
    psynthea = psynthea_profile.observations

    if synthea is None or psynthea is None:
        return None

    return _domain_comparison(
        "observations",
        [
            ("n_observations", synthea.n_observations, psynthea.n_observations),
            (
                "n_distinct_observations",
                synthea.n_distinct_observations,
                psynthea.n_distinct_observations,
            ),
            (
                "patients_with_observations",
                synthea.patients_with_observations,
                psynthea.patients_with_observations,
            ),
            (
                "patients_without_observations",
                synthea.patients_without_observations,
                psynthea.patients_without_observations,
            ),
            (
                "mean_observations_per_patient",
                synthea.mean_observations_per_patient,
                psynthea.mean_observations_per_patient,
            ),
            (
                "median_observations_per_patient",
                synthea.median_observations_per_patient,
                psynthea.median_observations_per_patient,
            ),
            (
                "std_observations_per_patient",
                synthea.std_observations_per_patient,
                psynthea.std_observations_per_patient,
            ),
            (
                "high_utilisation_patients",
                synthea.high_utilisation_patients,
                psynthea.high_utilisation_patients,
            ),
        ],
    )


def _build_summary(
    comparisons: list[DomainComparison | None],
) -> pd.DataFrame:
    """
    Concatenate available scalar comparison tables.
    """

    tables = [
        comparison.metrics
        for comparison in comparisons
        if comparison is not None and not comparison.metrics.empty
    ]

    if not tables:
        return _comparison_table([])

    return pd.concat(
        tables,
        ignore_index=True,
    )


# =============================================================================
# Public API
# =============================================================================

def compare_java_vs_psynthea(
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    include_quality: bool = True,
    observation_window: ObservationWindow | None = None,
) -> JavaVsPsyntheaComparison:
    """
    Compare Synthea Java and psynthea cohorts descriptively.

    Parameters
    ----------
    synthea_cohort
        Cohort generated by the original Java implementation.

    psynthea_cohort
        Cohort generated by the Python implementation.

    reference_date
        Date used to calculate ages and open clinical durations.

    top_n
        Number of top coded events calculated by the underlying cohort
        profile metrics.

    include_quality
        Whether structural/data-quality metrics should be included in the
        cohort profiles when available.

    observation_window
        Optional closed observation window applied identically to both
        simulators for epidemiological condition metrics.

    Returns
    -------
    JavaVsPsyntheaComparison
    """

    synthea_profile = calculate_cohort_profile(
        synthea_cohort,
        reference_date,
        top_n=top_n,
        include_quality=include_quality,
        observation_window=observation_window,
    )

    psynthea_profile = calculate_cohort_profile(
        psynthea_cohort,
        reference_date,
        top_n=top_n,
        include_quality=include_quality,
        observation_window=observation_window,
    )

    table_counts = _compare_table_counts(
        synthea_profile,
        psynthea_profile,
    )
    demographics = _compare_demographics(
        synthea_profile,
        psynthea_profile,
    )
    encounters = _compare_encounters(
        synthea_profile,
        psynthea_profile,
    )
    clinical = _compare_clinical(
        synthea_profile,
        psynthea_profile,
    )
    epidemiology = _compare_epidemiology(
        synthea_profile,
        psynthea_profile,
    )
    disease_epidemiology = _compare_disease_epidemiology(
        synthea_profile,
        psynthea_profile,
    )
    medications = _compare_medications(
        synthea_profile,
        psynthea_profile,
    )
    procedures = _compare_procedures(
        synthea_profile,
        psynthea_profile,
    )
    observations = _compare_observations(
        synthea_profile,
        psynthea_profile,
    )

    top_conditions = _compare_count_distributions(
        domain="top_conditions",
        synthea_distribution=(
            synthea_profile.clinical.top_conditions
            if synthea_profile.clinical is not None
            else None
        ),
        psynthea_distribution=(
            psynthea_profile.clinical.top_conditions
            if psynthea_profile.clinical is not None
            else None
        ),
        code_column="CODE",
        display_column="DESCRIPTION",
    )

    top_medications = _compare_count_distributions(
        domain="top_medications",
        synthea_distribution=(
            synthea_profile.medications.top_medications
            if synthea_profile.medications is not None
            else None
        ),
        psynthea_distribution=(
            psynthea_profile.medications.top_medications
            if psynthea_profile.medications is not None
            else None
        ),
        code_column="CODE",
        display_column="DESCRIPTION",
    )

    top_procedures = _compare_count_distributions(
        domain="top_procedures",
        synthea_distribution=(
            synthea_profile.procedures.top_procedures
            if synthea_profile.procedures is not None
            else None
        ),
        psynthea_distribution=(
            psynthea_profile.procedures.top_procedures
            if psynthea_profile.procedures is not None
            else None
        ),
        code_column="CODE",
        display_column="DESCRIPTION",
    )

    top_observations = _compare_count_distributions(
        domain="top_observations",
        synthea_distribution=(
            synthea_profile.observations.top_observations
            if synthea_profile.observations is not None
            else None
        ),
        psynthea_distribution=(
            psynthea_profile.observations.top_observations
            if psynthea_profile.observations is not None
            else None
        ),
        code_column="CODE",
        display_column="DESCRIPTION",
    )

    scalar_comparisons = [
        table_counts,
        demographics,
        encounters,
        clinical,
        epidemiology,
        medications,
        procedures,
        observations,
    ]

    return JavaVsPsyntheaComparison(
        synthea_profile=synthea_profile,
        psynthea_profile=psynthea_profile,
        table_counts=table_counts,
        demographics=demographics,
        encounters=encounters,
        clinical=clinical,
        epidemiology=epidemiology,
        disease_epidemiology=disease_epidemiology,
        medications=medications,
        procedures=procedures,
        observations=observations,
        top_conditions=top_conditions,
        top_medications=top_medications,
        top_procedures=top_procedures,
        top_observations=top_observations,
        summary=_build_summary(scalar_comparisons),
    )