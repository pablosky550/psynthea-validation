"""
Descriptive validation metrics.

This package exposes the public metric calculators used by the
validation pipeline. Each metric module keeps one responsibility and
this package only provides a stable import surface.
"""

from .demographics import (
    DemographicMetrics,
    calculate_demographics,
)

from .encounters import (
    EncounterMetrics,
    calculate_encounters,
)

from .clinical import (
    ClinicalMetrics,
    DiseaseMetrics,
    calculate_clinical,
)

from .medications import (
    MedicationMetrics,
    MedicationProfileMetrics,
    calculate_medications,
)

from .procedures import (
    ProcedureMetrics,
    ProcedureProfileMetrics,
    calculate_procedures,
)

from .observations import (
    ObservationMetrics,
    ObservationProfileMetrics,
    calculate_observations,
)

from .quality import (
    DataQualityMetrics,
    calculate_quality,
)

from .cohorts import (
    CohortProfileMetrics,
    calculate_cohort_profile,
)

__all__ = [
    "DemographicMetrics",
    "calculate_demographics",

    "EncounterMetrics",
    "calculate_encounters",

    "ClinicalMetrics",
    "DiseaseMetrics",
    "calculate_clinical",

    "MedicationMetrics",
    "MedicationProfileMetrics",
    "calculate_medications",

    "ProcedureMetrics",
    "ProcedureProfileMetrics",
    "calculate_procedures",

    "ObservationMetrics",
    "ObservationProfileMetrics",
    "calculate_observations",

    "DataQualityMetrics",
    "calculate_quality",

    "CohortProfileMetrics",
    "calculate_cohort_profile",
]