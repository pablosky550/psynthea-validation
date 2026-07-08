"""
Data quality validation metrics.

This module computes structural and completeness metrics from a
ValidationCohort.

The resulting metrics quantify table availability, row counts, missing
values, duplicate rows and duplicate patient identifiers.

No statistical hypothesis testing, plotting or report generation should
be implemented in this module.
"""

from dataclasses import dataclass

import pandas as pd

from validation.models import ValidationCohort
from validation.constants import (
    PATIENT_ID_COLUMN,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class TableQualityMetrics:
    """
    Structural quality metrics for a single cohort table.
    """

    table_name: str

    is_available: bool
    is_empty: bool

    n_rows: int
    n_columns: int

    missing_values: int
    missing_fraction: float

    duplicate_rows: int
    duplicate_row_fraction: float


@dataclass(slots=True)
class DataQualityMetrics:
    """
    Structural data quality profile of an entire synthetic cohort.
    """

    n_tables: int
    available_tables: int
    empty_tables: int
    missing_tables: int

    total_rows: int
    total_cells: int

    total_missing_values: int
    overall_missing_fraction: float

    duplicate_patient_ids: int
    duplicate_patient_id_fraction: float

    tables: pd.DataFrame
    table_metrics: list[TableQualityMetrics]


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


def _canonical_table_names() -> list[str]:
    """
    Return the canonical cohort tables inspected by quality metrics.
    """

    return [
        "patients",
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
    ]


def _get_table(
    cohort: ValidationCohort,
    table_name: str,
) -> pd.DataFrame | None:
    """
    Return a cohort table by name when it exists.
    """

    return getattr(
        cohort,
        table_name,
        None,
    )


def _calculate_table_quality(
    table_name: str,
    table: pd.DataFrame | None,
) -> TableQualityMetrics:
    """
    Compute structural quality metrics for one table.
    """

    if table is None:
        return TableQualityMetrics(
            table_name=table_name,

            is_available=False,
            is_empty=True,

            n_rows=0,
            n_columns=0,

            missing_values=0,
            missing_fraction=0.0,

            duplicate_rows=0,
            duplicate_row_fraction=0.0,
        )

    n_rows = int(len(table))
    n_columns = int(len(table.columns))
    total_cells = n_rows * n_columns

    missing_values = int(
        table.isna().sum().sum()
    )

    duplicate_rows = int(
        table.duplicated().sum()
    )

    return TableQualityMetrics(
        table_name=table_name,

        is_available=not table.empty,
        is_empty=table.empty,

        n_rows=n_rows,
        n_columns=n_columns,

        missing_values=missing_values,
        missing_fraction=_safe_fraction(
            missing_values,
            total_cells,
        ),

        duplicate_rows=duplicate_rows,
        duplicate_row_fraction=_safe_fraction(
            duplicate_rows,
            n_rows,
        ),
    )


def _calculate_duplicate_patient_ids(
    cohort: ValidationCohort,
) -> int:
    """
    Return the number of duplicated patient identifiers.
    """

    patients = cohort.patients

    if patients is None or patients.empty:
        return 0

    if PATIENT_ID_COLUMN not in patients.columns:
        return 0

    return int(
        patients[PATIENT_ID_COLUMN]
        .duplicated()
        .sum()
    )


def _table_metrics_to_frame(
    table_metrics: list[TableQualityMetrics],
) -> pd.DataFrame:
    """
    Convert table-level quality metrics to a tabular representation.
    """

    return pd.DataFrame(
        [
            {
                "table_name": metric.table_name,
                "is_available": metric.is_available,
                "is_empty": metric.is_empty,
                "n_rows": metric.n_rows,
                "n_columns": metric.n_columns,
                "missing_values": metric.missing_values,
                "missing_fraction": metric.missing_fraction,
                "duplicate_rows": metric.duplicate_rows,
                "duplicate_row_fraction": metric.duplicate_row_fraction,
            }
            for metric in table_metrics
        ]
    )


# =============================================================================
# Public API
# =============================================================================

def calculate_quality(
    cohort: ValidationCohort,
) -> DataQualityMetrics:
    """
    Compute structural data quality metrics.

    Parameters
    ----------
    cohort
        Validation cohort.

    Returns
    -------
    DataQualityMetrics
    """

    table_metrics = [
        _calculate_table_quality(
            table_name,
            _get_table(
                cohort,
                table_name,
            ),
        )
        for table_name in _canonical_table_names()
    ]

    tables = _table_metrics_to_frame(table_metrics)

    available_tables = int(
        tables["is_available"].sum()
    )

    empty_tables = int(
        tables["is_empty"].sum()
    )

    missing_tables = int(
        (~tables["is_available"]).sum()
    )

    total_rows = int(
        tables["n_rows"].sum()
    )

    total_cells = int(
        (tables["n_rows"] * tables["n_columns"]).sum()
    )

    total_missing_values = int(
        tables["missing_values"].sum()
    )

    duplicate_patient_ids = _calculate_duplicate_patient_ids(cohort)

    return DataQualityMetrics(
        n_tables=len(table_metrics),
        available_tables=available_tables,
        empty_tables=empty_tables,
        missing_tables=missing_tables,

        total_rows=total_rows,
        total_cells=total_cells,

        total_missing_values=total_missing_values,
        overall_missing_fraction=_safe_fraction(
            total_missing_values,
            total_cells,
        ),

        duplicate_patient_ids=duplicate_patient_ids,
        duplicate_patient_id_fraction=_safe_fraction(
            duplicate_patient_ids,
            cohort.n_patients,
        ),

        tables=tables,
        table_metrics=table_metrics,
    )
