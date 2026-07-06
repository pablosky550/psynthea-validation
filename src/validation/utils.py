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
    AGE_BANDS,
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
        patients[PATIENT_BIRTHDATE_COLUMN]
    )

    patients["AGE"] = (
        (reference_date - birthdate).dt.days / 365.25
    )

    patients["AGE_BAND"] = pd.cut(
        patients["AGE"],
        bins=AGE_BANDS,
        labels=AGE_LABELS,
        right=False,
    )

    return patients