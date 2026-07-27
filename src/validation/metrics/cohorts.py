"""
Cohort definition and cohort-level validation metrics.

This module has two complementary responsibilities:

1. define explicit temporal cohorts used by epidemiological analyses;
2. compose descriptive metric domains into a complete cohort profile.

Temporal cohort construction is intentionally performed before metric
calculation. Lower-level metric modules should receive an already selected
population or event table instead of silently applying observation-window
rules inside individual calculators.

No statistical hypothesis testing, plotting or report generation should be
implemented in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

import pandas as pd

from validation.constants import (
    CONDITION_CODE_COLUMN,
    CONDITION_PATIENT_COLUMN,
    CONDITION_START_COLUMN,
    CONDITION_STOP_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    PATIENT_ID_COLUMN,
)
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
from validation.models import ValidationCohort


# =============================================================================
# Temporal cohort models
# =============================================================================

@dataclass(frozen=True, slots=True)
class ObservationWindow:
    """
    Closed observation interval used by epidemiological analyses.

    Both boundaries are inclusive. Timestamps are normalised to timezone-naive
    UTC values so comparisons remain deterministic across CSV loaders and
    simulator outputs.
    """

    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        start = _normalise_timestamp(
            self.start,
            field_name="start",
        )
        end = _normalise_timestamp(
            self.end,
            field_name="end",
        )

        if start > end:
            raise ValueError(
                "Observation window start must be earlier than or equal to end."
            )

        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def contains(self, values: pd.Series) -> pd.Series:
        """
        Return a boolean mask for timestamps inside the closed interval.
        """

        timestamps = _normalise_datetime_series(values)

        return timestamps.between(
            self.start,
            self.end,
            inclusive="both",
        ).fillna(False)

    def overlaps(
        self,
        starts: pd.Series,
        stops: pd.Series,
    ) -> pd.Series:
        """
        Return a mask for event intervals overlapping the observation window.

        Missing stop dates are treated as open-ended events. Missing start dates
        are never considered observable because temporal membership cannot be
        established reliably.
        """

        normalised_starts = _normalise_datetime_series(starts)
        normalised_stops = _normalise_datetime_series(stops)

        starts_before_window_end = normalised_starts.le(self.end)
        stops_after_window_start = (
            normalised_stops.isna()
            | normalised_stops.ge(self.start)
        )

        return (
            normalised_starts.notna()
            & starts_before_window_end
            & stops_after_window_start
        ).fillna(False)


@dataclass(slots=True)
class TemporalConditionCohorts:
    """
    Explicit condition cohorts derived for one observation window.

    ``prevalent_conditions`` contains condition episodes overlapping the
    observation window. ``incident_conditions`` contains episodes whose onset
    occurs inside the window. ``at_risk_patient_ids_by_condition`` contains the
    eligible denominator for each condition code after excluding patients with
    a documented onset before the window.
    """

    window: ObservationWindow

    eligible_patient_ids: frozenset[Any]
    prevalent_patient_ids: frozenset[Any]
    incident_patient_ids: frozenset[Any]

    prevalent_conditions: pd.DataFrame
    incident_conditions: pd.DataFrame

    at_risk_patient_ids_by_condition: dict[str, frozenset[Any]]

    @property
    def n_eligible_patients(self) -> int:
        """Return the number of patients eligible for observation."""

        return len(self.eligible_patient_ids)

    @property
    def n_prevalent_patients(self) -> int:
        """Return patients with at least one prevalent condition episode."""

        return len(self.prevalent_patient_ids)

    @property
    def n_incident_patients(self) -> int:
        """Return patients with at least one incident condition episode."""

        return len(self.incident_patient_ids)


# =============================================================================
# Cohort profile models
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
# Temporal cohort helpers
# =============================================================================

def _normalise_timestamp(
    value: Any,
    *,
    field_name: str,
) -> pd.Timestamp:
    """
    Convert one timestamp to a timezone-naive UTC value.
    """

    timestamp = pd.to_datetime(
        value,
        errors="coerce",
        utc=True,
    )

    if pd.isna(timestamp):
        raise ValueError(
            f"Observation window {field_name} must be a valid timestamp."
        )

    return pd.Timestamp(timestamp).tz_convert(None)


def _normalise_datetime_series(
    values: pd.Series,
) -> pd.Series:
    """
    Convert a timestamp series to timezone-naive UTC values.
    """

    return pd.to_datetime(
        values,
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)


def _empty_like(
    table: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Return an empty copy preserving the source table schema when possible.
    """

    if table is None:
        return pd.DataFrame()

    return table.iloc[0:0].copy()


def _require_columns(
    table: pd.DataFrame,
    required_columns: set[str],
    *,
    table_name: str,
) -> None:
    """
    Raise a clear error when a canonical table misses required columns.
    """

    missing_columns = sorted(
        required_columns.difference(table.columns)
    )

    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(
            f"{table_name} table is missing required column(s): {missing}."
        )


def select_eligible_patient_ids(
    cohort: ValidationCohort,
    window: ObservationWindow,
    *,
    deathdate_column: str = "DEATHDATE",
) -> frozenset[Any]:
    """
    Select patients observable during the requested window.

    Eligibility requires a valid patient identifier. When birth date is
    available, patients born after the window are excluded. When death date is
    available, patients who died before the window are excluded. Missing death
    dates are interpreted as alive/open observation.
    """

    patients = cohort.patients

    if patients is None or patients.empty:
        return frozenset()

    _require_columns(
        patients,
        {PATIENT_ID_COLUMN},
        table_name="patients",
    )

    eligible = patients[PATIENT_ID_COLUMN].notna()

    if PATIENT_BIRTHDATE_COLUMN in patients.columns:
        birthdates = _normalise_datetime_series(
            patients[PATIENT_BIRTHDATE_COLUMN]
        )
        eligible &= birthdates.notna() & birthdates.le(window.end)

    if deathdate_column in patients.columns:
        deathdates = _normalise_datetime_series(
            patients[deathdate_column]
        )
        eligible &= deathdates.isna() | deathdates.ge(window.start)

    return frozenset(
        patients.loc[
            eligible,
            PATIENT_ID_COLUMN,
        ].tolist()
    )


def select_prevalent_conditions(
    cohort: ValidationCohort,
    window: ObservationWindow,
    *,
    eligible_patient_ids: frozenset[Any] | None = None,
) -> pd.DataFrame:
    """
    Select condition episodes that overlap the observation window.
    """

    conditions = cohort.conditions

    if conditions is None or conditions.empty:
        return _empty_like(conditions)

    _require_columns(
        conditions,
        {
            CONDITION_PATIENT_COLUMN,
            CONDITION_START_COLUMN,
            CONDITION_STOP_COLUMN,
        },
        table_name="conditions",
    )

    eligible_ids = (
        select_eligible_patient_ids(cohort, window)
        if eligible_patient_ids is None
        else eligible_patient_ids
    )

    if not eligible_ids:
        return _empty_like(conditions)

    mask = (
        conditions[CONDITION_PATIENT_COLUMN].isin(eligible_ids)
        & window.overlaps(
            conditions[CONDITION_START_COLUMN],
            conditions[CONDITION_STOP_COLUMN],
        )
    )

    return conditions.loc[mask].copy()


def select_incident_conditions(
    cohort: ValidationCohort,
    window: ObservationWindow,
    *,
    eligible_patient_ids: frozenset[Any] | None = None,
) -> pd.DataFrame:
    """
    Select condition episodes whose onset occurs inside the window.
    """

    conditions = cohort.conditions

    if conditions is None or conditions.empty:
        return _empty_like(conditions)

    _require_columns(
        conditions,
        {
            CONDITION_PATIENT_COLUMN,
            CONDITION_START_COLUMN,
        },
        table_name="conditions",
    )

    eligible_ids = (
        select_eligible_patient_ids(cohort, window)
        if eligible_patient_ids is None
        else eligible_patient_ids
    )

    if not eligible_ids:
        return _empty_like(conditions)

    mask = (
        conditions[CONDITION_PATIENT_COLUMN].isin(eligible_ids)
        & window.contains(conditions[CONDITION_START_COLUMN])
    )

    return conditions.loc[mask].copy()


def calculate_at_risk_patient_ids_by_condition(
    cohort: ValidationCohort,
    window: ObservationWindow,
    *,
    eligible_patient_ids: frozenset[Any] | None = None,
) -> dict[str, frozenset[Any]]:
    """
    Calculate disease-specific incidence denominators.

    For each observed condition code, the at-risk population is the eligible
    population excluding patients with a documented onset before the start of
    the observation window. Conditions first observed inside the window do not
    remove a patient from the baseline denominator.
    """

    conditions = cohort.conditions

    if conditions is None or conditions.empty:
        return {}

    _require_columns(
        conditions,
        {
            CONDITION_PATIENT_COLUMN,
            CONDITION_CODE_COLUMN,
            CONDITION_START_COLUMN,
        },
        table_name="conditions",
    )

    eligible_ids = (
        select_eligible_patient_ids(cohort, window)
        if eligible_patient_ids is None
        else eligible_patient_ids
    )

    if not eligible_ids:
        return {}

    working = conditions.loc[
        conditions[CONDITION_PATIENT_COLUMN].isin(eligible_ids),
        [
            CONDITION_PATIENT_COLUMN,
            CONDITION_CODE_COLUMN,
            CONDITION_START_COLUMN,
        ],
    ].copy()

    working[CONDITION_START_COLUMN] = _normalise_datetime_series(
        working[CONDITION_START_COLUMN]
    )
    working = working.loc[
        working[CONDITION_CODE_COLUMN].notna()
        & working[CONDITION_START_COLUMN].notna()
        & working[CONDITION_START_COLUMN].le(window.end)
    ]

    at_risk_by_condition: dict[str, frozenset[Any]] = {}

    for code, disease_conditions in working.groupby(
        CONDITION_CODE_COLUMN,
        sort=True,
        dropna=True,
    ):
        historical_patient_ids = frozenset(
            disease_conditions.loc[
                disease_conditions[CONDITION_START_COLUMN].lt(window.start),
                CONDITION_PATIENT_COLUMN,
            ].tolist()
        )

        at_risk_by_condition[str(code)] = frozenset(
            eligible_ids.difference(historical_patient_ids)
        )

    return at_risk_by_condition


def build_temporal_condition_cohorts(
    cohort: ValidationCohort,
    window: ObservationWindow,
) -> TemporalConditionCohorts:
    """
    Build all condition cohorts required by temporal epidemiological metrics.
    """

    eligible_patient_ids = select_eligible_patient_ids(
        cohort,
        window,
    )

    prevalent_conditions = select_prevalent_conditions(
        cohort,
        window,
        eligible_patient_ids=eligible_patient_ids,
    )
    incident_conditions = select_incident_conditions(
        cohort,
        window,
        eligible_patient_ids=eligible_patient_ids,
    )

    prevalent_patient_ids = _patient_ids_from_conditions(
        prevalent_conditions
    )
    incident_patient_ids = _patient_ids_from_conditions(
        incident_conditions
    )

    return TemporalConditionCohorts(
        window=window,
        eligible_patient_ids=eligible_patient_ids,
        prevalent_patient_ids=prevalent_patient_ids,
        incident_patient_ids=incident_patient_ids,
        prevalent_conditions=prevalent_conditions,
        incident_conditions=incident_conditions,
        at_risk_patient_ids_by_condition=(
            calculate_at_risk_patient_ids_by_condition(
                cohort,
                window,
                eligible_patient_ids=eligible_patient_ids,
            )
        ),
    )


def _patient_ids_from_conditions(
    conditions: pd.DataFrame,
) -> frozenset[Any]:
    """
    Extract unique non-null patient identifiers from a condition table.
    """

    if (
        conditions.empty
        or CONDITION_PATIENT_COLUMN not in conditions.columns
    ):
        return frozenset()

    return frozenset(
        conditions.loc[
            conditions[CONDITION_PATIENT_COLUMN].notna(),
            CONDITION_PATIENT_COLUMN,
        ].tolist()
    )


# =============================================================================
# Cohort profile helpers
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
# Public cohort profile API
# =============================================================================

def calculate_cohort_profile(
    cohort: ValidationCohort,
    reference_date: pd.Timestamp,
    top_n: int = 20,
    include_quality: bool = True,
    observation_window: ObservationWindow | None = None,
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

    observation_window
        Optional closed calendar window used to compute epidemiological
        condition metrics. Descriptive metrics remain cohort-wide.

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
            observation_window=observation_window,
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