"""
Statistical comparison layer for independently validated modules.

This module connects functional module validation with inferential statistics.
It applies statistical tests only when a module has enough usable output and
records skipped analyses explicitly when psynthea v1.0 or the Synthea reference
run does not provide comparable data.

It does not execute generators, load CSV files, patch psynthea, plot figures or
write reports. It consumes already-loaded ValidationCohort objects and, when
available, a ModuleValidationResult produced by module_validation.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from validation.comparison.module_validation import (
    ModuleValidationResult,
    ModuleValidationStatus,
    validate_independent_module,
)
from validation.constants import (
    AGE_COLUMN,
    CONDITION_CODE_COLUMN,
    CONDITION_PATIENT_COLUMN,
    DEFAULT_SIGNIFICANCE_LEVEL,
    ENCOUNTER_CLASS_COLUMN,
    ENCOUNTER_PATIENT_COLUMN,
    MEDICATION_CODE_COLUMN,
    MEDICATION_PATIENT_COLUMN,
    OBSERVATION_CODE_COLUMN,
    OBSERVATION_PATIENT_COLUMN,
    PATIENT_GENDER_COLUMN,
    PATIENT_ID_COLUMN,
    PROCEDURE_CODE_COLUMN,
    PROCEDURE_PATIENT_COLUMN,
)
from validation.models import ValidationCohort
from validation.statistics import (
    StatisticalTestResult,
    benjamini_hochberg,
    binary_association,
    chi_square_test,
    fisher_exact_test,
    jensen_shannon_divergence,
    kolmogorov_smirnov_test,
    mann_whitney_u_test,
    proportion_z_test,
    welch_t_test,
)

__all__ = [
    "ModuleStatisticalComparisonResult",
    "StatisticalComparisonScope",
    "compare_module_statistics",
]


# =============================================================================
# Configuration
# =============================================================================


class StatisticalComparisonScope(str, Enum):
    """Analysis scope used in the statistical comparison output."""

    CONTINUOUS = "continuous"
    CATEGORICAL = "categorical"
    PREVALENCE = "prevalence"
    CODE_DISTRIBUTION = "code_distribution"
    SKIPPED = "skipped"


_CONTINUOUS_COLUMNS = [
    "module_name",
    "scope",
    "metric",
    "test_name",
    "statistic",
    "p_value",
    "effect_size",
    "significant",
    "n_synthea",
    "n_psynthea",
    "notes",
]

_CATEGORICAL_COLUMNS = [
    "module_name",
    "scope",
    "domain",
    "test_name",
    "statistic",
    "p_value",
    "effect_size",
    "significant",
    "n_synthea",
    "n_psynthea",
    "notes",
]

_PREVALENCE_COLUMNS = [
    "module_name",
    "scope",
    "domain",
    "code",
    "synthea_events",
    "synthea_total",
    "psynthea_events",
    "psynthea_total",
    "synthea_prevalence",
    "psynthea_prevalence",
    "absolute_difference",
    "relative_difference",
    "risk_ratio",
    "risk_ratio_ci_lower",
    "risk_ratio_ci_upper",
    "odds_ratio",
    "odds_ratio_ci_lower",
    "odds_ratio_ci_upper",
    "test_name",
    "statistic",
    "p_value",
    "adjusted_p_value",
    "significant",
    "significant_after_fdr",
    "notes",
]

_DISTRIBUTION_COLUMNS = [
    "module_name",
    "scope",
    "domain",
    "test_name",
    "statistic",
    "p_value",
    "effect_size",
    "jensen_shannon_divergence",
    "significant",
    "n_synthea",
    "n_psynthea",
    "notes",
]

_SUMMARY_COLUMNS = [
    "module_name",
    "validation_status",
    "valid_for_statistical_comparison",
    "skipped",
    "skip_reason",
    "continuous_test_count",
    "categorical_test_count",
    "prevalence_test_count",
    "distribution_test_count",
    "significant_test_count",
    "significant_after_fdr_count",
    "mean_jensen_shannon_divergence",
]

_CODE_DOMAINS: Mapping[str, tuple[str, str]] = {
    "conditions": (CONDITION_CODE_COLUMN, CONDITION_PATIENT_COLUMN),
    "medications": (MEDICATION_CODE_COLUMN, MEDICATION_PATIENT_COLUMN),
    "procedures": (PROCEDURE_CODE_COLUMN, PROCEDURE_PATIENT_COLUMN),
    "observations": (OBSERVATION_CODE_COLUMN, OBSERVATION_PATIENT_COLUMN),
}

_PATIENT_COUNT_METRICS: Mapping[str, tuple[str, str]] = {
    "encounters_per_patient": ("encounters", ENCOUNTER_PATIENT_COLUMN),
    "conditions_per_patient": ("conditions", CONDITION_PATIENT_COLUMN),
    "medications_per_patient": ("medications", MEDICATION_PATIENT_COLUMN),
    "procedures_per_patient": ("procedures", PROCEDURE_PATIENT_COLUMN),
    "observations_per_patient": ("observations", OBSERVATION_PATIENT_COLUMN),
}


# =============================================================================
# Models
# =============================================================================


@dataclass(slots=True)
class ModuleStatisticalComparisonResult:
    """Complete statistical comparison for one independently validated module."""

    module_name: str
    validation: ModuleValidationResult
    continuous_tests: pd.DataFrame
    categorical_tests: pd.DataFrame
    prevalence_tests: pd.DataFrame
    distribution_tests: pd.DataFrame
    summary: pd.DataFrame


# =============================================================================
# Public API
# =============================================================================


def compare_module_statistics(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    *,
    module_validation: ModuleValidationResult | None = None,
    expected_condition_terms: Sequence[str] | None = None,
    expected_medication_terms: Sequence[str] | None = None,
    expected_procedure_terms: Sequence[str] | None = None,
    expected_observation_terms: Sequence[str] | None = None,
    top_n_codes: int = 25,
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> ModuleStatisticalComparisonResult:
    """
    Run statistical comparison for one module when functional output allows it.

    If no ModuleValidationResult is provided, the function first performs the
    independent-module validation using the same cohorts and expected terms.
    Statistical testing is skipped for non-comparable module states.
    """

    validation = module_validation or validate_independent_module(
        module_name=module_name,
        synthea_cohort=synthea_cohort,
        psynthea_cohort=psynthea_cohort,
        expected_condition_terms=expected_condition_terms,
        expected_medication_terms=expected_medication_terms,
        expected_procedure_terms=expected_procedure_terms,
        expected_observation_terms=expected_observation_terms,
    )

    validation_status = _validation_status(validation)
    valid = validation_status in {
        ModuleValidationStatus.COMPARABLE.value,
        ModuleValidationStatus.PARTIALLY_COMPARABLE.value,
    }

    if not valid:
        skip_reason = _validation_skip_reason(validation)
        return ModuleStatisticalComparisonResult(
            module_name=module_name,
            validation=validation,
            continuous_tests=pd.DataFrame(columns=_CONTINUOUS_COLUMNS),
            categorical_tests=pd.DataFrame(columns=_CATEGORICAL_COLUMNS),
            prevalence_tests=pd.DataFrame(columns=_PREVALENCE_COLUMNS),
            distribution_tests=pd.DataFrame(columns=_DISTRIBUTION_COLUMNS),
            summary=_summary_table(
                module_name,
                validation_status,
                valid_for_statistical_comparison=False,
                skipped=True,
                skip_reason=skip_reason,
                continuous_tests=pd.DataFrame(columns=_CONTINUOUS_COLUMNS),
                categorical_tests=pd.DataFrame(columns=_CATEGORICAL_COLUMNS),
                prevalence_tests=pd.DataFrame(columns=_PREVALENCE_COLUMNS),
                distribution_tests=pd.DataFrame(columns=_DISTRIBUTION_COLUMNS),
            ),
        )

    continuous_tests = _continuous_tests(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        alpha=alpha,
    )
    categorical_tests = _categorical_tests(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        alpha=alpha,
    )
    prevalence_tests = _prevalence_tests(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        top_n_codes=top_n_codes,
        alpha=alpha,
    )
    distribution_tests = _distribution_tests(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        alpha=alpha,
    )

    return ModuleStatisticalComparisonResult(
        module_name=module_name,
        validation=validation,
        continuous_tests=continuous_tests,
        categorical_tests=categorical_tests,
        prevalence_tests=prevalence_tests,
        distribution_tests=distribution_tests,
        summary=_summary_table(
            module_name,
            validation_status,
            valid_for_statistical_comparison=True,
            skipped=False,
            skip_reason=None,
            continuous_tests=continuous_tests,
            categorical_tests=categorical_tests,
            prevalence_tests=prevalence_tests,
            distribution_tests=distribution_tests,
        ),
    )


# =============================================================================
# Continuous analyses
# =============================================================================


def _continuous_tests(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    *,
    alpha: float,
) -> pd.DataFrame:
    rows: list[dict] = []

    age_left = _numeric_column(synthea_cohort.patients, AGE_COLUMN)
    age_right = _numeric_column(psynthea_cohort.patients, AGE_COLUMN)
    rows.extend(_continuous_metric_rows(module_name, "age", age_left, age_right, alpha))

    patient_ids = _patient_universe(synthea_cohort, psynthea_cohort)
    for metric, (table_name, patient_column) in _PATIENT_COUNT_METRICS.items():
        left = _per_patient_counts(_get_table(synthea_cohort, table_name), patient_column, patient_ids["synthea"])
        right = _per_patient_counts(_get_table(psynthea_cohort, table_name), patient_column, patient_ids["psynthea"])
        rows.extend(_continuous_metric_rows(module_name, metric, left, right, alpha))

    return pd.DataFrame(rows, columns=_CONTINUOUS_COLUMNS)


def _continuous_metric_rows(
    module_name: str,
    metric: str,
    synthea_values: Sequence[float],
    psynthea_values: Sequence[float],
    alpha: float,
) -> list[dict]:
    tests = [
        kolmogorov_smirnov_test(synthea_values, psynthea_values, alpha=alpha),
        mann_whitney_u_test(synthea_values, psynthea_values, alpha=alpha),
        welch_t_test(synthea_values, psynthea_values, alpha=alpha),
    ]
    return [
        _test_row(
            module_name=module_name,
            scope=StatisticalComparisonScope.CONTINUOUS.value,
            label_column="metric",
            label=metric,
            result=result,
        )
        for result in tests
    ]


# =============================================================================
# Categorical analyses
# =============================================================================


def _categorical_tests(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    *,
    alpha: float,
) -> pd.DataFrame:
    rows: list[dict] = []

    rows.extend(
        _categorical_domain_rows(
            module_name,
            "gender",
            _category_counts(synthea_cohort.patients, PATIENT_GENDER_COLUMN),
            _category_counts(psynthea_cohort.patients, PATIENT_GENDER_COLUMN),
            alpha,
        )
    )
    rows.extend(
        _categorical_domain_rows(
            module_name,
            "encounter_class",
            _category_counts(synthea_cohort.encounters, ENCOUNTER_CLASS_COLUMN),
            _category_counts(psynthea_cohort.encounters, ENCOUNTER_CLASS_COLUMN),
            alpha,
        )
    )

    return pd.DataFrame(rows, columns=_CATEGORICAL_COLUMNS)


def _categorical_domain_rows(
    module_name: str,
    domain: str,
    synthea_counts: Mapping[str, int],
    psynthea_counts: Mapping[str, int],
    alpha: float,
) -> list[dict]:
    table = _aligned_count_table(synthea_counts, psynthea_counts)
    if table is None:
        result = StatisticalTestResult(
            test_name="chi_square",
            statistic=None,
            p_value=None,
            alpha=alpha,
            significant=None,
            notes="No comparable categories available.",
        )
    else:
        result = fisher_exact_test(table, alpha=alpha) if table.shape == (2, 2) and table.min() < 5 else chi_square_test(table, alpha=alpha)

    return [
        _test_row(
            module_name=module_name,
            scope=StatisticalComparisonScope.CATEGORICAL.value,
            label_column="domain",
            label=domain,
            result=result,
        )
    ]


# =============================================================================
# Prevalence analyses
# =============================================================================


def _prevalence_tests(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    *,
    top_n_codes: int,
    alpha: float,
) -> pd.DataFrame:
    rows: list[dict] = []

    for domain, (code_column, patient_column) in _CODE_DOMAINS.items():
        left_table = _get_table(synthea_cohort, domain)
        right_table = _get_table(psynthea_cohort, domain)
        codes = _top_codes(left_table, right_table, code_column, top_n_codes)
        for code in codes:
            rows.append(
                _prevalence_row(
                    module_name,
                    domain,
                    code,
                    left_table,
                    right_table,
                    synthea_cohort.n_patients,
                    psynthea_cohort.n_patients,
                    code_column,
                    patient_column,
                    alpha,
                )
            )

    frame = pd.DataFrame(rows, columns=_PREVALENCE_COLUMNS)
    if frame.empty:
        return frame

    correction = benjamini_hochberg(frame["p_value"].tolist(), alpha=alpha)
    frame["adjusted_p_value"] = correction.adjusted_p_values
    frame["significant_after_fdr"] = correction.rejected
    return frame


def _prevalence_row(
    module_name: str,
    domain: str,
    code: str,
    synthea_table: pd.DataFrame | None,
    psynthea_table: pd.DataFrame | None,
    synthea_total: int,
    psynthea_total: int,
    code_column: str,
    patient_column: str,
    alpha: float,
) -> dict:
    synthea_events = _patients_with_code(synthea_table, code_column, patient_column, code)
    psynthea_events = _patients_with_code(psynthea_table, code_column, patient_column, code)
    test = proportion_z_test(
        synthea_events,
        synthea_total,
        psynthea_events,
        psynthea_total,
        alpha=alpha,
    )
    association = binary_association(
        synthea_events,
        synthea_total,
        psynthea_events,
        psynthea_total,
    )

    synthea_prev = _safe_ratio(synthea_events, synthea_total)
    psynthea_prev = _safe_ratio(psynthea_events, psynthea_total)
    abs_diff = None if synthea_prev is None or psynthea_prev is None else psynthea_prev - synthea_prev

    return {
        "module_name": module_name,
        "scope": StatisticalComparisonScope.PREVALENCE.value,
        "domain": domain,
        "code": code,
        "synthea_events": synthea_events,
        "synthea_total": synthea_total,
        "psynthea_events": psynthea_events,
        "psynthea_total": psynthea_total,
        "synthea_prevalence": synthea_prev,
        "psynthea_prevalence": psynthea_prev,
        "absolute_difference": abs_diff,
        "relative_difference": _safe_ratio(abs_diff, synthea_prev),
        "risk_ratio": association.risk_ratio,
        "risk_ratio_ci_lower": _ci_lower(association.risk_ratio_ci),
        "risk_ratio_ci_upper": _ci_upper(association.risk_ratio_ci),
        "odds_ratio": association.odds_ratio,
        "odds_ratio_ci_lower": _ci_lower(association.odds_ratio_ci),
        "odds_ratio_ci_upper": _ci_upper(association.odds_ratio_ci),
        "test_name": test.test_name,
        "statistic": test.statistic,
        "p_value": test.p_value,
        "adjusted_p_value": None,
        "significant": test.significant,
        "significant_after_fdr": False,
        "notes": test.notes,
    }


# =============================================================================
# Coded distribution analyses
# =============================================================================


def _distribution_tests(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    *,
    alpha: float,
) -> pd.DataFrame:
    rows: list[dict] = []

    for domain, (code_column, _) in _CODE_DOMAINS.items():
        left = _code_counts(_get_table(synthea_cohort, domain), code_column)
        right = _code_counts(_get_table(psynthea_cohort, domain), code_column)
        table = _aligned_count_table(left, right)
        js = jensen_shannon_divergence(left, right)

        if table is None:
            result = StatisticalTestResult(
                test_name="chi_square",
                statistic=None,
                p_value=None,
                alpha=alpha,
                notes="No comparable coded distribution available.",
            )
        else:
            result = chi_square_test(table, alpha=alpha)

        row = _test_row(
            module_name=module_name,
            scope=StatisticalComparisonScope.CODE_DISTRIBUTION.value,
            label_column="domain",
            label=domain,
            result=result,
        )
        row["jensen_shannon_divergence"] = js
        rows.append(row)

    return pd.DataFrame(rows, columns=_DISTRIBUTION_COLUMNS)


# =============================================================================
# Summary
# =============================================================================


def _summary_table(
    module_name: str,
    validation_status: str,
    *,
    valid_for_statistical_comparison: bool,
    skipped: bool,
    skip_reason: str | None,
    continuous_tests: pd.DataFrame,
    categorical_tests: pd.DataFrame,
    prevalence_tests: pd.DataFrame,
    distribution_tests: pd.DataFrame,
) -> pd.DataFrame:
    significant_count = sum(
        _significant_count(frame)
        for frame in [continuous_tests, categorical_tests, distribution_tests]
    ) + _significant_count(prevalence_tests)

    significant_after_fdr_count = (
        int(
            prevalence_tests["significant_after_fdr"]
            .astype("boolean")
            .fillna(False)
            .sum()
        )
        if not prevalence_tests.empty and "significant_after_fdr" in prevalence_tests.columns
        else 0
    )

    summary = {
        "module_name": module_name,
        "validation_status": validation_status,
        "valid_for_statistical_comparison": valid_for_statistical_comparison,
        "skipped": skipped,
        "skip_reason": skip_reason,
        "continuous_test_count": len(continuous_tests),
        "categorical_test_count": len(categorical_tests),
        "prevalence_test_count": len(prevalence_tests),
        "distribution_test_count": len(distribution_tests),
        "significant_test_count": significant_count,
        "significant_after_fdr_count": significant_after_fdr_count,
        "mean_jensen_shannon_divergence": _series_mean(
            distribution_tests["jensen_shannon_divergence"]
            if "jensen_shannon_divergence" in distribution_tests.columns
            else []
        ),
    }
    return pd.DataFrame([summary], columns=_SUMMARY_COLUMNS)


# =============================================================================
# Generic helpers
# =============================================================================


def _validation_status(validation: ModuleValidationResult) -> str:
    if validation.summary.empty or "status" not in validation.summary.columns:
        return ModuleValidationStatus.NOT_COMPARABLE.value
    return str(validation.summary.iloc[0]["status"])


def _validation_skip_reason(validation: ModuleValidationResult) -> str:
    if validation.summary.empty or "status_reason" not in validation.summary.columns:
        return "Module validation did not provide a comparable status."
    return str(validation.summary.iloc[0]["status_reason"])


def _test_row(
    *,
    module_name: str,
    scope: str,
    label_column: str,
    label: str,
    result: StatisticalTestResult,
) -> dict:
    row = {
        "module_name": module_name,
        "scope": scope,
        label_column: label,
        "test_name": result.test_name,
        "statistic": result.statistic,
        "p_value": result.p_value,
        "effect_size": result.effect_size,
        "significant": result.significant,
        "n_synthea": result.n_synthea,
        "n_psynthea": result.n_psynthea,
        "notes": result.notes,
    }
    return row


def _get_table(cohort: ValidationCohort, table_name: str) -> pd.DataFrame | None:
    value = getattr(cohort, table_name, None)
    return value if isinstance(value, pd.DataFrame) else None


def _numeric_column(table: pd.DataFrame | None, column: str) -> list[float]:
    if table is None or column not in table.columns:
        return []
    return pd.to_numeric(table[column], errors="coerce").dropna().astype(float).tolist()


def _category_counts(table: pd.DataFrame | None, column: str) -> dict[str, int]:
    if table is None or column not in table.columns:
        return {}
    counts = table[column].dropna().astype(str).str.strip().value_counts()
    return {str(key): int(value) for key, value in counts.items() if str(key)}


def _code_counts(table: pd.DataFrame | None, code_column: str) -> dict[str, int]:
    return _category_counts(table, code_column)


def _aligned_count_table(left: Mapping[str, int], right: Mapping[str, int]) -> np.ndarray | None:
    keys = sorted(set(left) | set(right))
    if not keys:
        return None
    table = np.asarray(
        [
            [left.get(key, 0) for key in keys],
            [right.get(key, 0) for key in keys],
        ],
        dtype=int,
    )
    if table.sum() == 0 or np.any(table.sum(axis=0) == 0) or np.any(table.sum(axis=1) == 0):
        table = table[:, table.sum(axis=0) > 0]
    if table.size == 0 or table.shape[1] < 2 or np.any(table.sum(axis=1) == 0):
        return None
    return table


def _patient_universe(
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
) -> dict[str, list[str]]:
    return {
        "synthea": _patient_ids(synthea_cohort),
        "psynthea": _patient_ids(psynthea_cohort),
    }


def _patient_ids(cohort: ValidationCohort) -> list[str]:
    if cohort.patients is None or PATIENT_ID_COLUMN not in cohort.patients.columns:
        return [str(index) for index in range(cohort.n_patients)]
    return cohort.patients[PATIENT_ID_COLUMN].dropna().astype(str).tolist()


def _per_patient_counts(
    table: pd.DataFrame | None,
    patient_column: str,
    patient_ids: Sequence[str],
) -> list[int]:
    if not patient_ids:
        return []
    if table is None or patient_column not in table.columns:
        return [0 for _ in patient_ids]
    counts = table[patient_column].dropna().astype(str).value_counts()
    return [int(counts.get(str(patient_id), 0)) for patient_id in patient_ids]


def _top_codes(
    synthea_table: pd.DataFrame | None,
    psynthea_table: pd.DataFrame | None,
    code_column: str,
    top_n_codes: int,
) -> list[str]:
    combined = _code_counts(synthea_table, code_column)
    for code, count in _code_counts(psynthea_table, code_column).items():
        combined[code] = combined.get(code, 0) + count
    return [code for code, _ in sorted(combined.items(), key=lambda item: item[1], reverse=True)[:top_n_codes]]


def _patients_with_code(
    table: pd.DataFrame | None,
    code_column: str,
    patient_column: str,
    code: str,
) -> int:
    if table is None or code_column not in table.columns or patient_column not in table.columns:
        return 0
    mask = table[code_column].dropna().astype(str) == str(code)
    return int(table.loc[mask, patient_column].dropna().astype(str).nunique())


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return float(numerator) / float(denominator)


def _ci_lower(ci) -> float | None:
    return None if ci is None else ci.lower


def _ci_upper(ci) -> float | None:
    return None if ci is None else ci.upper


def _significant_count(frame: pd.DataFrame) -> int:
    if frame.empty or "significant" not in frame.columns:
        return 0
    return int(
        frame["significant"]
        .astype("boolean")
        .fillna(False)
        .sum()
    )


def _series_mean(values) -> float | None:
    series = pd.Series(list(values)).dropna()
    if series.empty:
        return None
    return float(series.mean())
