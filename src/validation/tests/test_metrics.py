"""
Descriptive metric tests.

These tests validate the public metric calculators using the deterministic
synthetic cohort defined in conftest.py.
"""

from __future__ import annotations

import pandas as pd
import pytest

from validation.metrics import (
    ClinicalMetrics,
    CohortProfileMetrics,
    DataQualityMetrics,
    DemographicMetrics,
    EncounterMetrics,
    MedicationProfileMetrics,
    ObservationProfileMetrics,
    ProcedureProfileMetrics,
    calculate_clinical,
    calculate_cohort_profile,
    calculate_demographics,
    calculate_encounters,
    calculate_medications,
    calculate_observations,
    calculate_procedures,
    calculate_quality,
)
from validation.models import ValidationCohort


# =============================================================================
# Demographics
# =============================================================================

def test_calculate_demographics(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Demographic metrics describe cohort size, age and sex distributions.
    """

    metrics = calculate_demographics(
        validation_cohort,
        reference_date,
    )

    assert isinstance(metrics, DemographicMetrics)

    assert metrics.n_patients == 4

    assert metrics.male_count == 2
    assert metrics.female_count == 2

    assert metrics.male_fraction == pytest.approx(0.5)
    assert metrics.female_fraction == pytest.approx(0.5)

    assert metrics.age_distribution["count"].sum() == 4
    assert metrics.age_band_distribution["count"].sum() == 4
    assert metrics.population_pyramid["count"].sum() == 4


# =============================================================================
# Encounters
# =============================================================================

def test_calculate_encounters(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Encounter metrics quantify healthcare utilisation.
    """

    metrics = calculate_encounters(
        validation_cohort,
        reference_date,
    )

    assert isinstance(metrics, EncounterMetrics)

    assert metrics.n_encounters == 6

    assert metrics.mean_encounters_per_patient == pytest.approx(2.0)
    assert metrics.median_encounters_per_patient == pytest.approx(2.0)

    assert metrics.min_encounters_per_patient == 2
    assert metrics.max_encounters_per_patient == 2

    assert metrics.patients_without_encounters == 1

    assert metrics.encounters_per_patient["encounters"].sum() == 6
    assert metrics.encounter_type_distribution["count"].sum() == 6
    assert metrics.encounters_by_age_band["count"].sum() == 6
    assert metrics.encounters_by_sex["count"].sum() == 6


# =============================================================================
# Clinical
# =============================================================================

def test_calculate_clinical(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Clinical metrics quantify condition burden and disease-level profiles.
    """

    metrics = calculate_clinical(
        validation_cohort,
        reference_date,
    )

    assert isinstance(metrics, ClinicalMetrics)

    assert metrics.n_conditions == 4

    assert metrics.patients_with_conditions == 2
    assert metrics.healthy_patients == 2
    assert metrics.multimorbid_patients == 1

    assert metrics.mean_conditions_per_patient == pytest.approx(0.75)

    assert len(metrics.diseases) == 3
    assert metrics.top_conditions["count"].sum() == 4

    hypertension = next(
        disease
        for disease in metrics.diseases
        if disease.display == "Hypertension"
    )

    assert hypertension.n_patients == 1
    assert hypertension.n_episodes == 2
    assert hypertension.prevalence == pytest.approx(0.25)
    assert hypertension.recurrence_rate == pytest.approx(1.0)


def test_calculate_clinical_empty_conditions(
    empty_optional_tables_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Clinical metrics return a stable empty object when no conditions exist.
    """

    metrics = calculate_clinical(
        empty_optional_tables_cohort,
        reference_date,
    )

    assert isinstance(metrics, ClinicalMetrics)

    assert metrics.n_conditions == 0
    assert metrics.patients_with_conditions == 0
    assert metrics.healthy_patients == 4
    assert metrics.multimorbid_patients == 0
    assert metrics.diseases == []


# =============================================================================
# Medications
# =============================================================================

def test_calculate_medications(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Medication metrics quantify medication exposure and repeat prescribing.
    """

    metrics = calculate_medications(
        validation_cohort,
        reference_date,
    )

    assert isinstance(metrics, MedicationProfileMetrics)

    assert metrics.n_medication_orders == 5
    assert metrics.n_distinct_medications == 4

    assert metrics.patients_with_medications == 3
    assert metrics.patients_without_medications == 1
    assert metrics.polypharmacy_patients == 0

    assert metrics.mean_medications_per_patient == pytest.approx(1.0)

    lisinopril = next(
        medication
        for medication in metrics.medications
        if medication.display == "Lisinopril 10 MG Oral Tablet"
    )

    assert lisinopril.n_patients == 1
    assert lisinopril.n_orders == 2
    assert lisinopril.active_orders == 1
    assert lisinopril.recurrent_patients == 1
    assert lisinopril.recurrence_rate == pytest.approx(1.0)
    assert lisinopril.total_dispenses == pytest.approx(17.0)


def test_calculate_medications_empty_medications(
    empty_optional_tables_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Medication metrics return a stable empty object when no medications exist.
    """

    metrics = calculate_medications(
        empty_optional_tables_cohort,
        reference_date,
    )

    assert isinstance(metrics, MedicationProfileMetrics)

    assert metrics.n_medication_orders == 0
    assert metrics.n_distinct_medications == 0
    assert metrics.patients_with_medications == 0
    assert metrics.patients_without_medications == 4
    assert metrics.medications == []


# =============================================================================
# Procedures
# =============================================================================

def test_calculate_procedures(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Procedure metrics quantify procedure utilisation and repeated procedures.
    """

    metrics = calculate_procedures(
        validation_cohort,
        reference_date,
    )

    assert isinstance(metrics, ProcedureProfileMetrics)

    assert metrics.n_procedures == 5
    assert metrics.n_distinct_procedures == 4

    assert metrics.patients_with_procedures == 4
    assert metrics.patients_without_procedures == 0
    assert metrics.high_utilisation_patients == 0

    assessment = next(
        procedure
        for procedure in metrics.procedures
        if procedure.display == "Assessment of health and social care needs"
    )

    assert assessment.n_patients == 1
    assert assessment.n_procedures == 2
    assert assessment.repeat_patients == 1
    assert assessment.repeat_rate == pytest.approx(1.0)
    assert assessment.total_base_cost == pytest.approx(200.0)


def test_calculate_procedures_empty_procedures(
    empty_optional_tables_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Procedure metrics return a stable empty object when no procedures exist.
    """

    metrics = calculate_procedures(
        empty_optional_tables_cohort,
        reference_date,
    )

    assert isinstance(metrics, ProcedureProfileMetrics)

    assert metrics.n_procedures == 0
    assert metrics.n_distinct_procedures == 0
    assert metrics.patients_with_procedures == 0
    assert metrics.patients_without_procedures == 4
    assert metrics.procedures == []


# =============================================================================
# Observations
# =============================================================================

def test_calculate_observations(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Observation metrics quantify utilisation, numeric values and missingness.
    """

    metrics = calculate_observations(
        validation_cohort,
        reference_date,
    )

    assert isinstance(metrics, ObservationProfileMetrics)

    assert metrics.n_observations == 8
    assert metrics.n_distinct_observations == 6

    assert metrics.patients_with_observations == 4
    assert metrics.patients_without_observations == 0
    assert metrics.high_utilisation_patients == 0

    systolic = next(
        observation
        for observation in metrics.observations
        if observation.display == "Systolic Blood Pressure"
    )

    assert systolic.n_patients == 1
    assert systolic.n_observations == 2
    assert systolic.numeric_observations == 2
    assert systolic.repeat_patients == 1
    assert systolic.repeat_rate == pytest.approx(1.0)
    assert systolic.mean_value == pytest.approx(147.5)
    assert systolic.most_common_unit == "mmHg"

    smoking_status = next(
        observation
        for observation in metrics.observations
        if observation.display == "Tobacco smoking status"
    )

    assert smoking_status.n_observations == 2
    assert smoking_status.numeric_observations == 0
    assert smoking_status.non_numeric_observations == 1
    assert smoking_status.missing_value_count == 1


def test_calculate_observations_empty_observations(
    empty_optional_tables_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Observation metrics return a stable empty object when no observations exist.
    """

    metrics = calculate_observations(
        empty_optional_tables_cohort,
        reference_date,
    )

    assert isinstance(metrics, ObservationProfileMetrics)

    assert metrics.n_observations == 0
    assert metrics.n_distinct_observations == 0
    assert metrics.patients_with_observations == 0
    assert metrics.patients_without_observations == 4
    assert metrics.observations == []


# =============================================================================
# Quality
# =============================================================================

def test_calculate_quality(
    validation_cohort: ValidationCohort,
) -> None:
    """
    Quality metrics quantify canonical table availability and structure.
    """

    metrics = calculate_quality(validation_cohort)

    assert isinstance(metrics, DataQualityMetrics)

    assert metrics.n_tables == 6
    assert metrics.available_tables == 6
    assert metrics.empty_tables == 0
    assert metrics.missing_tables == 0

    assert metrics.total_rows == 32
    assert metrics.duplicate_patient_ids == 0

    assert set(metrics.tables["table_name"]) == {
        "patients",
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
    }


def test_calculate_quality_empty_optional_tables(
    empty_optional_tables_cohort: ValidationCohort,
) -> None:
    """
    Empty optional tables are reported as unavailable/empty by quality metrics.
    """

    metrics = calculate_quality(empty_optional_tables_cohort)

    assert isinstance(metrics, DataQualityMetrics)

    assert metrics.n_tables == 6
    assert metrics.available_tables == 1
    assert metrics.empty_tables == 5
    assert metrics.missing_tables == 5

    assert metrics.total_rows == 4
    assert metrics.duplicate_patient_ids == 0


# =============================================================================
# Cohort profile
# =============================================================================

def test_calculate_cohort_profile(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Cohort profile composes all descriptive metric domains.
    """

    profile = calculate_cohort_profile(
        validation_cohort,
        reference_date,
    )

    assert isinstance(profile, CohortProfileMetrics)

    assert profile.source == validation_cohort.source
    assert profile.reference_date == reference_date

    assert profile.table_counts.patients == 4
    assert profile.table_counts.encounters == 6
    assert profile.table_counts.conditions == 4
    assert profile.table_counts.medications == 5
    assert profile.table_counts.procedures == 5
    assert profile.table_counts.observations == 8

    assert profile.completeness.available_tables == 6
    assert profile.completeness.missing_tables == 0
    assert profile.completeness.missing_table_names == []

    assert isinstance(profile.demographics, DemographicMetrics)
    assert isinstance(profile.encounters, EncounterMetrics)
    assert isinstance(profile.clinical, ClinicalMetrics)
    assert isinstance(profile.medications, MedicationProfileMetrics)
    assert isinstance(profile.procedures, ProcedureProfileMetrics)
    assert isinstance(profile.observations, ObservationProfileMetrics)
    assert isinstance(profile.quality, DataQualityMetrics)

    assert set(profile.summary["metric"]) == {
        "source",
        "patients",
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
        "available_tables",
        "missing_tables",
    }


def test_calculate_cohort_profile_without_quality(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Cohort profile can be generated without the quality domain.
    """

    profile = calculate_cohort_profile(
        validation_cohort,
        reference_date,
        include_quality=False,
    )

    assert isinstance(profile, CohortProfileMetrics)
    assert profile.quality is None


def test_calculate_cohort_profile_empty_optional_tables(
    empty_optional_tables_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Cohort profile remains stable when optional clinical tables are empty.
    """

    profile = calculate_cohort_profile(
        empty_optional_tables_cohort,
        reference_date,
    )

    assert isinstance(profile, CohortProfileMetrics)

    assert profile.table_counts.patients == 4
    assert profile.table_counts.encounters == 0
    assert profile.table_counts.conditions == 0
    assert profile.table_counts.medications == 0
    assert profile.table_counts.procedures == 0
    assert profile.table_counts.observations == 0

    assert profile.completeness.available_tables == 1
    assert profile.completeness.missing_tables == 5

    assert isinstance(profile.demographics, DemographicMetrics)
    assert profile.encounters is None

    assert isinstance(profile.clinical, ClinicalMetrics)
    assert isinstance(profile.medications, MedicationProfileMetrics)
    assert isinstance(profile.procedures, ProcedureProfileMetrics)
    assert isinstance(profile.observations, ObservationProfileMetrics)
    assert isinstance(profile.quality, DataQualityMetrics)

# =============================================================================
# Cohort profile compatibility
# =============================================================================

def test_calculate_cohort_profile_preserves_descriptive_metric_contract(
    validation_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Temporal cohort support must not alter the existing descriptive profile.
    """

    profile = calculate_cohort_profile(
        validation_cohort,
        reference_date,
    )

    assert isinstance(profile, CohortProfileMetrics)
    assert profile.source == validation_cohort.source
    assert profile.reference_date == reference_date

    assert profile.table_counts.patients == 4
    assert profile.table_counts.encounters == 6
    assert profile.table_counts.conditions == 4
    assert profile.table_counts.medications == 5
    assert profile.table_counts.procedures == 5
    assert profile.table_counts.observations == 8

    assert profile.completeness.available_tables == 6
    assert profile.completeness.missing_tables == 0
    assert profile.completeness.missing_table_names == []

    assert isinstance(profile.demographics, DemographicMetrics)
    assert isinstance(profile.encounters, EncounterMetrics)
    assert isinstance(profile.clinical, ClinicalMetrics)
    assert isinstance(profile.medications, MedicationProfileMetrics)
    assert isinstance(profile.procedures, ProcedureProfileMetrics)
    assert isinstance(profile.observations, ObservationProfileMetrics)
    assert isinstance(profile.quality, DataQualityMetrics)

    assert profile.summary["metric"].tolist() == [
        "source",
        "patients",
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
        "available_tables",
        "missing_tables",
    ]


def test_calculate_cohort_profile_reports_empty_optional_tables_without_failure(
    empty_optional_tables_cohort: ValidationCohort,
    reference_date: pd.Timestamp,
) -> None:
    """
    Empty optional tables remain explicit in completeness and domain metrics.
    """

    profile = calculate_cohort_profile(
        empty_optional_tables_cohort,
        reference_date,
    )

    assert isinstance(profile, CohortProfileMetrics)

    assert profile.table_counts.patients == 4
    assert profile.table_counts.encounters == 0
    assert profile.table_counts.conditions == 0
    assert profile.table_counts.medications == 0
    assert profile.table_counts.procedures == 0
    assert profile.table_counts.observations == 0

    assert profile.completeness.available_tables == 1
    assert profile.completeness.missing_tables == 5
    assert profile.completeness.missing_table_names == [
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
    ]

    assert profile.clinical is not None
    assert profile.clinical.n_conditions == 0
    assert profile.clinical.healthy_patients == 4

    assert profile.medications is not None
    assert profile.medications.n_medication_orders == 0

    assert profile.procedures is not None
    assert profile.procedures.n_procedures == 0

    assert profile.observations is not None
    assert profile.observations.n_observations == 0