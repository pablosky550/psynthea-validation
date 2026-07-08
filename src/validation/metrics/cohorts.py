"""
Cohort-level validation metrics.

This module composes the descriptive metric domains computed from a
ValidationCohort into a single cohort profile.

Lower-level metric modules remain responsible for their own clinical or
utilisation logic. This module only orchestrates those calculators and
returns a structured snapshot of the cohort.

No statistical hypothesis testing, plotting or report generation should
be implemented in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

import pandas as pd

from validation.models import ValidationCohort
from validation.metrics.clinical import ClinicalMetrics, calculate_clinical
from validation.metrics.demographics import DemographicMetrics, calculate_demographics
from validation.metrics.encounters import EncounterMetrics, calculate_encounters
from validation.metrics.medications import (
    MedicationProfileMetrics,
    calculate_medications,
)
from validation.metrics.observations import (
    ObservationProfileMetrics,
    calculate_observations,
)
from validation.metrics.procedures import (
    ProcedureProfileMetrics,
    calculate_procedures,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class CohortTableCounts:
    """
    Row counts for the canonical cohort tables.
    """

    patients: int
    encounters: int
    conditions: int
    medications: int
    procedures: int
    observations: int


@dataclass(slots=True)
class CohortCompletenessMetrics:
    """
    Availability of canonical tables required by the validation domains.
    """

    has_patients: bool
    has_encounters: bool
    has_conditions: bool
    has_medications: bool
    has_procedures: bool
    has_observations: bool

    available_tables: int
    missing_tables: int

    missing_table_names: list[str]


@dataclass(slots=True)
class CohortProfileMetrics:
    """
    Complete descriptive validation profile for one synthetic cohort.
    """

    source: str
    reference_date: pd.Timestamp

    table_counts: CohortTableCounts
    completeness: CohortCompletenessMetrics

    demographics: DemographicMetrics | None
    encounters: EncounterMetrics | None
    clinical: ClinicalMetrics | None
    medications: MedicationProfileMetrics | None
    procedures: ProcedureProfileMetrics | None
    observations: ObservationProfileMetrics | None

    quality: Any | None

    summary: pd.DataFrame


# =============================================================================
# Helpers
# =============================================================================

def _get_table(
    cohort: ValidationCohort,
    name: str,
) -> pd.DataFrame | None:
    """
    Return a cohort table by name when it exists.
    """

    return getattr(
        cohort,
        name,
        None,
    )


def _has_table(
    cohort: ValidationCohort,
    name: str,
) -> bool:
    """
    Return whether a cohort table exists and contains at least one row.
    """

    table = _get_table(
        cohort,
        name,
    )

    return table is not None and not table.empty


def _table_count(
    cohort: ValidationCohort,
    name: str,
) -> int:
    """
    Return the number of rows in a cohort table.
    """

    table = _get_table(
        cohort,
        name,
    )

    if table is None:
        return 0

    return int(len(table))


def _calculate_completeness(
    cohort: ValidationCohort,
) -> CohortCompletenessMetrics:
    """
    Compute table availability metrics for the cohort.
    """

    table_names = [
        "patients",
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
    ]

    availability = {
        table_name: _has_table(
            cohort,
            table_name,
        )
        for table_name in table_names
    }

    missing_table_names = [
        table_name
        for table_name, is_available in availability.items()
        if not is_available
    ]

    return CohortCompletenessMetrics(

        has_patients=availability["patients"],
        has_encounters=availability["encounters"],
        has_conditions=availability["conditions"],
        has_medications=availability["medications"],
        has_procedures=availability["procedures"],
        has_observations=availability["observations"],

        available_tables=int(
            sum(availability.values())
        ),
        missing_tables=len(missing_table_names),

        missing_table_names=missing_table_names,
    )


def _calculate_table_counts(
    cohort: ValidationCohort,
) -> CohortTableCounts:
    """
    Compute row counts for all supported cohort tables.
    """

    return CohortTableCounts(
        patients=_table_count(
            cohort,
            "patients",
        ),
        encounters=_table_count(
            cohort,
            "encounters",
        ),
        conditions=_table_count(
            cohort,
            "conditions",
        ),
        medications=_table_count(
            cohort,
            "medications",
        ),
        procedures=_table_count(
            cohort,
            "procedures",
        ),
        observations=_table_count(
            cohort,
            "observations",
        ),
    )


def _build_summary(
    cohort: ValidationCohort,
    table_counts: CohortTableCounts,
    completeness: CohortCompletenessMetrics,
) -> pd.DataFrame:
    """
    Build a compact tabular summary of the cohort profile.
    """

    rows = [
        {
            "metric": "source",
            "value": cohort.source,
        },
        {
            "metric": "patients",
            "value": table_counts.patients,
        },
        {
            "metric": "encounters",
            "value": table_counts.encounters,
        },
        {
            "metric": "conditions",
            "value": table_counts.conditions,
        },
        {
            "metric": "medications",
            "value": table_counts.medications,
        },
        {
            "metric": "procedures",
            "value": table_counts.procedures,
        },
        {
            "metric": "observations",
            "value": table_counts.observations,
        },
        {
            "metric": "available_tables",
            "value": completeness.available_tables,
        },
        {
            "metric": "missing_tables",
            "value": completeness.missing_tables,
        },
    ]

    return pd.DataFrame(rows)


def _load_quality_calculator() -> Callable[..., Any] | None:
    """
    Return the quality calculator when the quality module is available.

    The quality domain is optional here because this file is only a
    composition layer. If quality.py is not installed yet, cohort profile
    generation must continue for the remaining descriptive domains.
    """

    try:
        quality_module = import_module(
            "validation.metrics.quality"
        )
    except ModuleNotFoundError:
        return None

    calculator = getattr(
        quality_module,
        "calculate_quality",
        None,
    )

    if callable(calculator):
        return calculator

    return None


# =============================================================================
# Public API
# =============================================================================

def calculate_cohort_profile(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    include_quality: bool = True,
) -> CohortProfileMetrics:
    """
    Compute the complete descriptive validation profile for one cohort.

    Parameters
    ----------
    cohort
        Validation cohort.

    reference_date
        Date used to calculate age and open clinical event duration.

    top_n
        Number of most frequent clinical items returned by domain-level
        metrics where applicable.

    include_quality
        Whether to include the structural/data-quality domain when the
        quality module is available.

    Returns
    -------
    CohortProfileMetrics
    """

    table_counts = _calculate_table_counts(cohort)
    completeness = _calculate_completeness(cohort)

    demographics = (
        calculate_demographics(
            cohort,
            reference_date,
        )
        if _has_table(
            cohort,
            "patients",
        )
        else None
    )

    encounters = (
        calculate_encounters(
            cohort,
            reference_date,
        )
        if _has_table(
            cohort,
            "patients",
        )
        and _has_table(
            cohort,
            "encounters",
        )
        else None
    )

    clinical = (
        calculate_clinical(
            cohort,
            reference_date,
            top_n=top_n,
        )
        if _has_table(
            cohort,
            "patients",
        )
        and hasattr(
            cohort,
            "conditions",
        )
        else None
    )

    medications = (
        calculate_medications(
            cohort,
            reference_date,
            top_n=top_n,
        )
        if _has_table(
            cohort,
            "patients",
        )
        and hasattr(
            cohort,
            "medications",
        )
        else None
    )

    procedures = (
        calculate_procedures(
            cohort,
            reference_date,
            top_n=top_n,
        )
        if _has_table(
            cohort,
            "patients",
        )
        and hasattr(
            cohort,
            "procedures",
        )
        else None
    )

    observations = (
        calculate_observations(
            cohort,
            reference_date,
            top_n=top_n,
        )
        if _has_table(
            cohort,
            "patients",
        )
        and hasattr(
            cohort,
            "observations",
        )
        else None
    )

    quality = None

    if include_quality:
        calculate_quality = _load_quality_calculator()

        if calculate_quality is not None:
            quality = calculate_quality(cohort)

    return CohortProfileMetrics(

        source=cohort.source,
        reference_date=pd.Timestamp(reference_date),

        table_counts=table_counts,
        completeness=completeness,

        demographics=demographics,
        encounters=encounters,
        clinical=clinical,
        medications=medications,
        procedures=procedures,
        observations=observations,

        quality=quality,

        summary=_build_summary(
            cohort,
            table_counts,
            completeness,
        ),
    )
