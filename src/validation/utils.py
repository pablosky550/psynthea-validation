"""
Shared utility functions.

Utility functions are reusable operations shared across multiple
validation modules.

Utilities must remain generic and must never contain validation,
statistical or plotting logic.
"""

from __future__ import annotations

import pandas as pd

from validation.constants import (
    AGE_BAND_COLUMN,
    AGE_BANDS,
    AGE_COLUMN,
    AGE_LABELS,
    PATIENT_BIRTHDATE_COLUMN,
)


def prepare_patients(
    patients: pd.DataFrame,
    reference_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Prepare the patient table for downstream analyses.

    This function enriches the patient table with derived demographic
    variables that are reused throughout the validation framework.

    The original DataFrame is never modified.

    Parameters
    ----------
    patients
        Patient table.

    reference_date
        Reference date used to calculate patient age.

    Returns
    -------
    pandas.DataFrame
        Copy of the patient table with additional derived columns.
    """

    patients = patients.copy()

    birthdate = pd.to_datetime(
        patients[PATIENT_BIRTHDATE_COLUMN],
        errors="coerce",
    )

    patients[AGE_COLUMN] = (
        (pd.Timestamp(reference_date) - birthdate).dt.days / 365.25
    )

    patients[AGE_BAND_COLUMN] = pd.cut(
        patients[AGE_COLUMN],
        bins=AGE_BANDS,
        labels=AGE_LABELS,
        right=False,
    )

    return patients


def safe_fraction(
    numerator: int,
    denominator: int,
) -> float:
    """
    Return a safe fraction avoiding division by zero.
    """

    if denominator == 0:
        return 0.0

    return numerator / denominator


def coerce_datetime_columns(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """
    Return a copy with selected columns converted to datetime.
    """

    result = dataframe.copy()

    for column in columns:
        if column in result.columns:
            result[column] = pd.to_datetime(
                result[column],
                errors="coerce",
            )

    return result


def coerce_numeric_column(
    dataframe: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.DataFrame:
    """
    Return a copy with a selected column converted to numeric.
    """

    result = dataframe.copy()

    if column in result.columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )
    else:
        result[column] = default

    return result


def calculate_age_years(
    event_date: pd.Series,
    birthdate: pd.Series,
) -> pd.Series:
    """
    Calculate age in years at a given event date.
    """

    return (
        event_date
        .sub(birthdate)
        .dt.days
        / 365.25
    )


def calculate_duration_days(
    start: pd.Series,
    stop: pd.Series,
    reference_date: pd.Timestamp,
) -> pd.Series:
    """
    Calculate duration in days, using reference_date for open intervals.
    """

    return (
        stop
        .fillna(pd.Timestamp(reference_date))
        .sub(start)
        .dt.days
    )


def count_distinct_events_per_patient(
    events: pd.DataFrame,
    patient_column: str,
    code_column: str,
    output_column: str,
) -> pd.DataFrame:
    """
    Count distinct event codes per patient.
    """

    return (
        events
        .groupby(patient_column)
        [code_column]
        .nunique()
        .rename(output_column)
        .reset_index()
    )


def align_patient_event_counts(
    patients: pd.DataFrame,
    event_counts: pd.DataFrame,
    patient_id_column: str,
    event_patient_column: str,
    count_column: str,
) -> pd.Series:
    """
    Align per-patient event counts with the full patient cohort.
    """

    return (
        patients[[patient_id_column]]
        .merge(
            event_counts,
            left_on=patient_id_column,
            right_on=event_patient_column,
            how="left",
        )
        [count_column]
        .fillna(0)
    )


def top_events(
    events: pd.DataFrame,
    code_column: str,
    description_column: str,
    count_column: str,
    top_n: int,
) -> pd.DataFrame:
    """
    Return the most frequent coded events.
    """

    return (
        events
        .groupby(
            [
                code_column,
                description_column,
            ],
            dropna=False,
        )
        .size()
        .reset_index(name=count_column)
        .sort_values(
            count_column,
            ascending=False,
        )
        .head(top_n)
        .reset_index(drop=True)
    )


def first_display_value(
    dataframe: pd.DataFrame,
    description_column: str,
    fallback: object,
) -> str:
    """
    Return the first non-null display value or a fallback.
    """

    values = dataframe[description_column].dropna()

    if values.empty:
        return str(fallback)

    return str(values.iloc[0])
