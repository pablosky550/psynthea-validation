"""
Core validation framework tests.

These tests cover the canonical cohort model, CSV loaders and shared
utility functions used by the metric modules.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from validation.constants import (
    AGE_BAND_COLUMN,
    AGE_COLUMN,
    CSV_FILES,
    CONDITION_CODE_COLUMN,
    CONDITION_PATIENT_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    PATIENT_ID_COLUMN,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.loaders import load_psynthea, load_synthea
from validation.models import ValidationCohort
from validation.utils import (
    align_patient_event_counts,
    calculate_age_years,
    calculate_duration_days,
    coerce_datetime_columns,
    coerce_numeric_column,
    count_distinct_events_per_patient,
    first_display_value,
    prepare_patients,
    safe_fraction,
    top_events,
)


# =============================================================================
# ValidationCohort
# =============================================================================


def test_validation_cohort_counts(validation_cohort: ValidationCohort) -> None:
    """
    ValidationCohort exposes consistent row counts for all canonical tables.
    """

    assert validation_cohort.n_patients == 4
    assert validation_cohort.n_encounters == 6
    assert validation_cohort.n_conditions == 4
    assert validation_cohort.n_medications == 5
    assert validation_cohort.n_procedures == 5
    assert validation_cohort.n_observations == 8



def test_validation_cohort_summary(validation_cohort: ValidationCohort) -> None:
    """
    summary returns a compact, stable representation of the cohort.
    """

    assert validation_cohort.summary == {
        "source": SOURCE_PSYNTHEA,
        "patients": 4,
        "encounters": 6,
        "conditions": 4,
        "medications": 5,
        "procedures": 5,
        "observations": 8,
    }



def test_validation_cohort_none_tables_have_zero_counts() -> None:
    """
    Missing optional tables are represented as zero counts.
    """

    cohort = ValidationCohort(source=SOURCE_PSYNTHEA)

    assert cohort.n_patients == 0
    assert cohort.n_encounters == 0
    assert cohort.n_conditions == 0
    assert cohort.n_medications == 0
    assert cohort.n_procedures == 0
    assert cohort.n_observations == 0


# =============================================================================
# Loaders
# =============================================================================


def test_load_psynthea_reads_available_csv_tables(
    tmp_path: Path,
    patients_dataframe: pd.DataFrame,
    encounters_dataframe: pd.DataFrame,
    conditions_dataframe: pd.DataFrame,
    medications_dataframe: pd.DataFrame,
    procedures_dataframe: pd.DataFrame,
    observations_dataframe: pd.DataFrame,
) -> None:
    """
    load_psynthea loads all canonical CSV files into a ValidationCohort.
    """

    tables = {
        "patients": patients_dataframe,
        "encounters": encounters_dataframe,
        "conditions": conditions_dataframe,
        "medications": medications_dataframe,
        "procedures": procedures_dataframe,
        "observations": observations_dataframe,
    }

    for table_name, dataframe in tables.items():
        dataframe.to_csv(
            tmp_path / CSV_FILES[table_name],
            index=False,
        )

    cohort = load_psynthea(tmp_path)

    assert cohort.source == SOURCE_PSYNTHEA
    assert cohort.output_path == tmp_path
    assert cohort.n_patients == len(patients_dataframe)
    assert cohort.n_encounters == len(encounters_dataframe)
    assert cohort.n_conditions == len(conditions_dataframe)
    assert cohort.n_medications == len(medications_dataframe)
    assert cohort.n_procedures == len(procedures_dataframe)
    assert cohort.n_observations == len(observations_dataframe)



def test_load_synthea_uses_synthea_source(
    tmp_path: Path,
    patients_dataframe: pd.DataFrame,
) -> None:
    """
    load_synthea tags the cohort as produced by Synthea Java.
    """

    patients_dataframe.to_csv(
        tmp_path / CSV_FILES["patients"],
        index=False,
    )

    cohort = load_synthea(tmp_path)

    assert cohort.source == SOURCE_SYNTHEA
    assert cohort.output_path == tmp_path
    assert cohort.n_patients == len(patients_dataframe)
    assert cohort.n_encounters == 0
    assert cohort.n_conditions == 0
    assert cohort.n_medications == 0
    assert cohort.n_procedures == 0
    assert cohort.n_observations == 0



def test_loader_requires_patients_csv(tmp_path: Path) -> None:
    """
    patients.csv is the only mandatory canonical input table.
    """

    with pytest.raises(FileNotFoundError):
        load_psynthea(tmp_path)


# =============================================================================
# Utilities
# =============================================================================


def test_prepare_patients_adds_age_columns(
    patients_dataframe: pd.DataFrame,
    reference_date: pd.Timestamp,
) -> None:
    """
    prepare_patients returns a copy enriched with age and age band columns.
    """

    prepared = prepare_patients(
        patients_dataframe,
        reference_date,
    )

    assert AGE_COLUMN in prepared.columns
    assert AGE_BAND_COLUMN in prepared.columns
    assert AGE_COLUMN not in patients_dataframe.columns
    assert AGE_BAND_COLUMN not in patients_dataframe.columns

    p1_age = prepared.loc[
        prepared[PATIENT_ID_COLUMN] == "P1",
        AGE_COLUMN,
    ].iloc[0]

    assert p1_age == pytest.approx(44.0, abs=0.01)



def test_safe_fraction() -> None:
    """
    safe_fraction avoids division by zero while preserving normal division.
    """

    assert safe_fraction(2, 4) == 0.5
    assert safe_fraction(1, 0) == 0.0



def test_coerce_datetime_columns() -> None:
    """
    coerce_datetime_columns converts existing columns and ignores missing ones.
    """

    dataframe = pd.DataFrame(
        {
            "date": ["2020-01-01", "not-a-date"],
            "value": [1, 2],
        }
    )

    result = coerce_datetime_columns(
        dataframe,
        ["date", "missing"],
    )

    assert pd.api.types.is_datetime64_any_dtype(result["date"])
    assert result["date"].isna().sum() == 1
    assert result["value"].tolist() == [1, 2]



def test_coerce_numeric_column() -> None:
    """
    coerce_numeric_column converts existing columns and creates absent columns.
    """

    dataframe = pd.DataFrame({"value": ["1.5", "bad"]})

    converted = coerce_numeric_column(dataframe, "value")
    with_default = coerce_numeric_column(dataframe, "missing", default=7.0)

    assert converted["value"].iloc[0] == 1.5
    assert pd.isna(converted["value"].iloc[1])
    assert with_default["missing"].eq(7.0).all()



def test_calculate_age_years() -> None:
    """
    calculate_age_years returns elapsed years between birth and event dates.
    """

    event_date = pd.to_datetime(pd.Series(["2020-01-01"]))
    birthdate = pd.to_datetime(pd.Series(["2000-01-01"]))

    age = calculate_age_years(event_date, birthdate)

    assert age.iloc[0] == pytest.approx(20.0, abs=0.01)



def test_calculate_duration_days(reference_date: pd.Timestamp) -> None:
    """
    calculate_duration_days uses reference_date for open intervals.
    """

    start = pd.to_datetime(pd.Series(["2020-01-01", "2020-01-01"]))
    stop = pd.to_datetime(pd.Series(["2020-01-10", pd.NaT]))

    duration = calculate_duration_days(
        start,
        stop,
        reference_date,
    )

    assert duration.iloc[0] == 9
    assert duration.iloc[1] == 1461



def test_count_distinct_events_per_patient(
    conditions_dataframe: pd.DataFrame,
) -> None:
    """
    count_distinct_events_per_patient counts unique codes, not rows.
    """

    counts = count_distinct_events_per_patient(
        events=conditions_dataframe,
        patient_column=CONDITION_PATIENT_COLUMN,
        code_column=CONDITION_CODE_COLUMN,
        output_column="conditions",
    )

    p1_count = counts.loc[
        counts[CONDITION_PATIENT_COLUMN] == "P1",
        "conditions",
    ].iloc[0]

    assert p1_count == 2



def test_align_patient_event_counts(
    patients_dataframe: pd.DataFrame,
    conditions_dataframe: pd.DataFrame,
) -> None:
    """
    align_patient_event_counts preserves all patients and fills missing counts.
    """

    event_counts = count_distinct_events_per_patient(
        events=conditions_dataframe,
        patient_column=CONDITION_PATIENT_COLUMN,
        code_column=CONDITION_CODE_COLUMN,
        output_column="conditions",
    )

    aligned = align_patient_event_counts(
        patients=patients_dataframe,
        event_counts=event_counts,
        patient_id_column=PATIENT_ID_COLUMN,
        event_patient_column=CONDITION_PATIENT_COLUMN,
        count_column="conditions",
    )

    assert aligned.tolist() == [2.0, 1.0, 0.0, 0.0]



def test_top_events(conditions_dataframe: pd.DataFrame) -> None:
    """
    top_events returns the most frequent coded concepts in descending order.
    """

    result = top_events(
        events=conditions_dataframe,
        code_column=CONDITION_CODE_COLUMN,
        description_column="DESCRIPTION",
        count_column="count",
        top_n=1,
    )

    assert len(result) == 1
    assert result.loc[0, CONDITION_CODE_COLUMN] == "59621000"
    assert result.loc[0, "count"] == 2



def test_first_display_value(conditions_dataframe: pd.DataFrame) -> None:
    """
    first_display_value returns the first non-null display or fallback.
    """

    display = first_display_value(
        conditions_dataframe,
        description_column="DESCRIPTION",
        fallback="fallback",
    )

    missing_display = first_display_value(
        pd.DataFrame({"DESCRIPTION": [pd.NA]}),
        description_column="DESCRIPTION",
        fallback="fallback",
    )

    assert display == "Hypertension"
    assert missing_display == "fallback"
