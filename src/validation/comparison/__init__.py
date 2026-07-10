"""Public comparison API for scientific cohort validation.

This package exposes the high-level comparison workflows used to evaluate
functional, descriptive and statistical equivalence between cohorts generated
by Synthea Java and psynthea.

Low-level metrics, data loading, plotting and report generation remain in their
dedicated modules.
"""

from __future__ import annotations

from .java_vs_psynthea import (
    CodedEventComparison,
    DomainComparison,
    JavaVsPsyntheaComparison,
    MetricComparison,
    compare_java_vs_psynthea,
)
from .module_validation import (
    ModuleClinicalSignal,
    ModuleSimilarityResult,
    ModuleTableStatus,
    ModuleValidationIssue,
    ModuleValidationIssueType,
    ModuleValidationResult,
    ModuleValidationStatus,
    validate_independent_module,
)
from .spanish_validation import (
    SpanishAdaptationValidation,
    SpanishValidationIndicator,
    validate_spanish_adaptation,
)
from .statistical_comparison import (
    ModuleStatisticalComparisonResult,
    StatisticalComparisonScope,
    compare_module_statistics,
)

__all__ = [
    # Descriptive Java-versus-psynthea comparison.
    "MetricComparison",
    "DomainComparison",
    "CodedEventComparison",
    "JavaVsPsyntheaComparison",
    "compare_java_vs_psynthea",

    # Independent clinical-module validation.
    "ModuleValidationStatus",
    "ModuleValidationIssueType",
    "ModuleValidationIssue",
    "ModuleTableStatus",
    "ModuleClinicalSignal",
    "ModuleSimilarityResult",
    "ModuleValidationResult",
    "validate_independent_module",

    # Spanish healthcare-system adaptation.
    "SpanishValidationIndicator",
    "SpanishAdaptationValidation",
    "validate_spanish_adaptation",

    # Inferential statistical comparison.
    "StatisticalComparisonScope",
    "ModuleStatisticalComparisonResult",
    "compare_module_statistics",
]