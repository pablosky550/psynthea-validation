"""
Independent-module validation for Synthea Java vs psynthea.

This module evaluates whether a single clinical module can be compared between
Synthea Java and psynthea using already-loaded ValidationCohort objects.

It is intentionally output-driven. It does not execute Synthea, execute
psynthea, patch modules, load CSV files, generate plots or write reports.

The goal is to distinguish statistical/clinical divergence from functional
failures such as missing tables, empty observations, absent diagnoses or
partially executed modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import log2, sqrt
from typing import Iterable, Mapping, Sequence

import pandas as pd

from validation.constants import (
    CONDITION_CODE_COLUMN,
    CONDITION_DESCRIPTION_COLUMN,
    MEDICATION_CODE_COLUMN,
    MEDICATION_DESCRIPTION_COLUMN,
    OBSERVATION_CODE_COLUMN,
    OBSERVATION_DESCRIPTION_COLUMN,
    PROCEDURE_CODE_COLUMN,
    PROCEDURE_DESCRIPTION_COLUMN,
)
from validation.models import ValidationCohort

__all__ = [
    "ModuleClinicalSignal",
    "ModuleValidationIssue",
    "ModuleValidationIssueType",
    "ModuleValidationStatus",
    "ModuleSimilarityResult",
    "ModuleTableStatus",
    "ModuleValidationResult",
    "validate_independent_module",
]


# =============================================================================
# Configuration
# =============================================================================

_CORE_TABLES = [
    "patients",
    "encounters",
    "conditions",
    "medications",
    "procedures",
    "observations",
]

_CODE_COLUMNS: Mapping[str, str] = {
    "conditions": CONDITION_CODE_COLUMN,
    "medications": MEDICATION_CODE_COLUMN,
    "procedures": PROCEDURE_CODE_COLUMN,
    "observations": OBSERVATION_CODE_COLUMN,
}

_DESCRIPTION_COLUMNS: Mapping[str, str] = {
    "conditions": CONDITION_DESCRIPTION_COLUMN,
    "medications": MEDICATION_DESCRIPTION_COLUMN,
    "procedures": PROCEDURE_DESCRIPTION_COLUMN,
    "observations": OBSERVATION_DESCRIPTION_COLUMN,
}

_DEFAULT_REQUIRED_TABLES = [
    "patients",
    "encounters",
    "conditions",
]

_DEFAULT_SIGNAL_TABLES = [
    "conditions",
    "medications",
    "procedures",
    "observations",
]

_TABLE_STATUS_COLUMNS = [
    "module_name",
    "table",
    "synthea_available",
    "psynthea_available",
    "synthea_rows",
    "psynthea_rows",
    "synthea_empty",
    "psynthea_empty",
    "row_difference",
    "relative_row_difference",
    "required",
    "blocking_issue",
]

_SIGNAL_COLUMNS = [
    "module_name",
    "domain",
    "synthea_signal_count",
    "psynthea_signal_count",
    "shared_code_count",
    "synthea_only_code_count",
    "psynthea_only_code_count",
    "expected_signal_detected_synthea",
    "expected_signal_detected_psynthea",
    "expected_terms",
    "required",
    "blocking_issue",
]

_SIMILARITY_COLUMNS = [
    "module_name",
    "domain",
    "synthea_total",
    "psynthea_total",
    "shared_code_count",
    "synthea_only_code_count",
    "psynthea_only_code_count",
    "jaccard_similarity",
    "overlap_coefficient",
    "jensen_shannon_divergence",
    "valid_for_distributional_comparison",
    "required",
    "blocking_issue",
]

_ISSUE_COLUMNS = [
    "module_name",
    "severity",
    "domain",
    "issue",
    "details",
]

_SUMMARY_COLUMNS = [
    "module_name",
    "status",
    "status_reason",
    "synthea_functional",
    "psynthea_functional",
    "valid_for_comparison",
    "blocking_issue_count",
    "warning_count",
    "synthea_condition_count",
    "psynthea_condition_count",
    "synthea_observation_count",
    "psynthea_observation_count",
    "mean_distributional_similarity",
    "mean_jensen_shannon_divergence",
]


# =============================================================================
# Models
# =============================================================================

class ModuleValidationStatus(str, Enum):
    """
    Final functional comparability classification for an independently executed module.
    """

    COMPARABLE = "comparable"
    PARTIALLY_COMPARABLE = "partially_comparable"
    NOT_COMPARABLE = "not_comparable"
    REFERENCE_EMPTY = "reference_empty"
    PSYNTHEA_FUNCTIONAL_FAILURE = "psynthea_functional_failure"


class ModuleValidationIssueType(str, Enum):
    """
    Normalized issue codes emitted by module-level validation.

    These values are intentionally stable because report generation and tests
    should not depend on free-text messages.
    """

    REQUIRED_TABLE_MISSING_OR_EMPTY = "required_table_missing_or_empty"
    PSYNTHEA_TABLE_EMPTY = "psynthea_table_empty"
    SYNTHEA_TABLE_EMPTY = "synthea_table_empty"
    MISSING_CORE_CLINICAL_SIGNAL = "missing_core_clinical_signal"
    REFERENCE_CLINICAL_SIGNAL_EMPTY = "reference_clinical_signal_empty"
    EXPECTED_SIGNAL_MISSING_IN_PSYNTHEA = "expected_signal_missing_in_psynthea"
    DISTRIBUTION_NOT_COMPARABLE = "distribution_not_comparable"
    LOW_CODE_OVERLAP = "low_code_overlap"
    HIGH_DISTRIBUTIONAL_DIVERGENCE = "high_distributional_divergence"

@dataclass(slots=True)
class ModuleValidationIssue:
    """
    Normalized validation issue.

    The ``issue`` field stores the stable enum value so downstream reports can
    filter and aggregate issues without parsing human-readable text.
    """

    module_name: str
    severity: str
    domain: str
    issue: str
    details: str


@dataclass(slots=True)
class ModuleTableStatus:
    """
    Availability and row-count status for one output table.
    """

    module_name: str
    table: str

    synthea_available: bool
    psynthea_available: bool

    synthea_rows: int
    psynthea_rows: int

    synthea_empty: bool
    psynthea_empty: bool

    row_difference: int
    relative_row_difference: float | None

    required: bool
    blocking_issue: bool


@dataclass(slots=True)
class ModuleClinicalSignal:
    """
    Clinical signal detected for one coded output domain.
    """

    module_name: str
    domain: str

    synthea_signal_count: int
    psynthea_signal_count: int

    shared_code_count: int
    synthea_only_code_count: int
    psynthea_only_code_count: int

    expected_signal_detected_synthea: bool | None
    expected_signal_detected_psynthea: bool | None
    expected_terms: str | None

    required: bool
    blocking_issue: bool


@dataclass(slots=True)
class ModuleSimilarityResult:
    """
    Distributional similarity for one coded output domain.
    """

    module_name: str
    domain: str

    synthea_total: int
    psynthea_total: int

    shared_code_count: int
    synthea_only_code_count: int
    psynthea_only_code_count: int

    jaccard_similarity: float | None
    overlap_coefficient: float | None
    jensen_shannon_divergence: float | None

    valid_for_distributional_comparison: bool
    required: bool
    blocking_issue: bool


@dataclass(slots=True)
class ModuleValidationResult:
    """
    Complete validation result for one independently generated module.
    """

    module_name: str
    synthea_cohort: ValidationCohort
    psynthea_cohort: ValidationCohort

    table_status: pd.DataFrame
    clinical_signal: pd.DataFrame
    distributional_similarity: pd.DataFrame
    issues: pd.DataFrame
    summary: pd.DataFrame


# =============================================================================
# Public API
# =============================================================================

def validate_independent_module(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    *,
    required_tables: Sequence[str] | None = None,
    required_signal_domains: Sequence[str] | None = None,
    expected_condition_terms: Sequence[str] | None = None,
    expected_medication_terms: Sequence[str] | None = None,
    expected_procedure_terms: Sequence[str] | None = None,
    expected_observation_terms: Sequence[str] | None = None,
) -> ModuleValidationResult:
    """
    Validate one module-level Synthea Java vs psynthea comparison.

    Parameters
    ----------
    module_name:
        Human-readable module identifier, for example ``"hypertension"``.
    synthea_cohort:
        Output generated by Synthea Java for the module under evaluation.
    psynthea_cohort:
        Output generated by psynthea for the same module.
    required_tables:
        Tables that must exist and be non-empty in both generators for the
        comparison to be considered valid. By default, patients, encounters and
        conditions are required.
    required_signal_domains:
        Coded clinical domains that define the module's minimum functional
        signal. Defaults to conditions for backward compatibility.
    expected_*_terms:
        Optional module-specific expected clinical codes or text fragments.
        Terms are matched against CODE and DESCRIPTION columns when available.

    Returns
    -------
    ModuleValidationResult
        Structured validation result with table completeness, clinical signal,
        distributional similarity, detected issues and a one-row summary.
    """

    required = list(required_tables or _DEFAULT_REQUIRED_TABLES)
    required_signals = _normalise_required_signal_domains(required_signal_domains)
    expected_terms = {
        "conditions": list(expected_condition_terms or []),
        "medications": list(expected_medication_terms or []),
        "procedures": list(expected_procedure_terms or []),
        "observations": list(expected_observation_terms or []),
    }

    table_status = _table_status_table(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        required,
    )
    clinical_signal = _clinical_signal_table(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        expected_terms,
        required_signals,
    )
    distributional_similarity = _distributional_similarity_table(
        module_name,
        synthea_cohort,
        psynthea_cohort,
        required_signals,
    )
    issues = _issue_table(
        module_name,
        table_status,
        clinical_signal,
        distributional_similarity,
    )
    summary = _summary_table(
        module_name,
        table_status,
        clinical_signal,
        distributional_similarity,
        issues,
    )

    return ModuleValidationResult(
        module_name=module_name,
        synthea_cohort=synthea_cohort,
        psynthea_cohort=psynthea_cohort,
        table_status=table_status,
        clinical_signal=clinical_signal,
        distributional_similarity=distributional_similarity,
        issues=issues,
        summary=summary,
    )


# =============================================================================
# Table completeness
# =============================================================================

def _table_status_table(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    required_tables: Sequence[str],
) -> pd.DataFrame:
    """
    Build availability and row-count diagnostics for core CSV tables.
    """

    rows = [
        _table_status(
            module_name,
            table,
            _get_table(synthea_cohort, table),
            _get_table(psynthea_cohort, table),
            table in required_tables,
        )
        for table in _CORE_TABLES
    ]
    return _dataclass_table(rows, _TABLE_STATUS_COLUMNS)


def _table_status(
    module_name: str,
    table: str,
    synthea_table: pd.DataFrame | None,
    psynthea_table: pd.DataFrame | None,
    required: bool,
) -> ModuleTableStatus:
    """
    Build status for one table.
    """

    synthea_rows = _row_count(synthea_table)
    psynthea_rows = _row_count(psynthea_table)
    row_difference = psynthea_rows - synthea_rows

    return ModuleTableStatus(
        module_name=module_name,
        table=table,
        synthea_available=synthea_table is not None,
        psynthea_available=psynthea_table is not None,
        synthea_rows=synthea_rows,
        psynthea_rows=psynthea_rows,
        synthea_empty=synthea_rows == 0,
        psynthea_empty=psynthea_rows == 0,
        row_difference=row_difference,
        relative_row_difference=_safe_ratio(row_difference, synthea_rows),
        required=required,
        blocking_issue=required and (synthea_rows == 0 or psynthea_rows == 0),
    )


# =============================================================================
# Clinical signal
# =============================================================================

def _clinical_signal_table(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    expected_terms: Mapping[str, Sequence[str]],
    required_signal_domains: set[str],
) -> pd.DataFrame:
    """
    Build clinical-signal diagnostics for coded clinical domains.
    """

    rows = [
        _clinical_signal(
            module_name,
            domain,
            _get_table(synthea_cohort, domain),
            _get_table(psynthea_cohort, domain),
            expected_terms.get(domain, []),
            domain in required_signal_domains,
        )
        for domain in _DEFAULT_SIGNAL_TABLES
    ]
    return _dataclass_table(rows, _SIGNAL_COLUMNS)


def _clinical_signal(
    module_name: str,
    domain: str,
    synthea_table: pd.DataFrame | None,
    psynthea_table: pd.DataFrame | None,
    expected_terms: Sequence[str],
    required: bool,
) -> ModuleClinicalSignal:
    """
    Detect whether one coded clinical domain contains comparable signal.
    """

    synthea_codes = _code_set(synthea_table, domain)
    psynthea_codes = _code_set(psynthea_table, domain)
    shared_codes = synthea_codes & psynthea_codes

    expected_synthea = _expected_terms_detected(
        synthea_table,
        domain,
        expected_terms,
    )
    expected_psynthea = _expected_terms_detected(
        psynthea_table,
        domain,
        expected_terms,
    )

    return ModuleClinicalSignal(
        module_name=module_name,
        domain=domain,
        synthea_signal_count=_row_count(synthea_table),
        psynthea_signal_count=_row_count(psynthea_table),
        shared_code_count=len(shared_codes),
        synthea_only_code_count=len(synthea_codes - psynthea_codes),
        psynthea_only_code_count=len(psynthea_codes - synthea_codes),
        expected_signal_detected_synthea=expected_synthea,
        expected_signal_detected_psynthea=expected_psynthea,
        expected_terms=", ".join(expected_terms) if expected_terms else None,
        required=required,
        blocking_issue=required and _row_count(psynthea_table) == 0,
    )


# =============================================================================
# Distributional similarity
# =============================================================================

def _distributional_similarity_table(
    module_name: str,
    synthea_cohort: ValidationCohort,
    psynthea_cohort: ValidationCohort,
    required_signal_domains: set[str],
) -> pd.DataFrame:
    """
    Compare coded distributions for core clinical domains.
    """

    rows = [
        _distributional_similarity(
            module_name,
            domain,
            _get_table(synthea_cohort, domain),
            _get_table(psynthea_cohort, domain),
            domain in required_signal_domains,
        )
        for domain in _DEFAULT_SIGNAL_TABLES
    ]
    return _dataclass_table(rows, _SIMILARITY_COLUMNS)


def _distributional_similarity(
    module_name: str,
    domain: str,
    synthea_table: pd.DataFrame | None,
    psynthea_table: pd.DataFrame | None,
    required: bool,
) -> ModuleSimilarityResult:
    """
    Compare one coded event distribution.
    """

    synthea_distribution = _code_distribution(synthea_table, domain)
    psynthea_distribution = _code_distribution(psynthea_table, domain)

    synthea_codes = set(synthea_distribution)
    psynthea_codes = set(psynthea_distribution)
    shared_codes = synthea_codes & psynthea_codes
    union_codes = synthea_codes | psynthea_codes

    synthea_total = sum(synthea_distribution.values())
    psynthea_total = sum(psynthea_distribution.values())
    valid = synthea_total > 0 and psynthea_total > 0

    return ModuleSimilarityResult(
        module_name=module_name,
        domain=domain,
        synthea_total=synthea_total,
        psynthea_total=psynthea_total,
        shared_code_count=len(shared_codes),
        synthea_only_code_count=len(synthea_codes - psynthea_codes),
        psynthea_only_code_count=len(psynthea_codes - synthea_codes),
        jaccard_similarity=_jaccard_similarity(synthea_codes, psynthea_codes),
        overlap_coefficient=_overlap_coefficient(synthea_codes, psynthea_codes),
        jensen_shannon_divergence=(
            _jensen_shannon_divergence(
                synthea_distribution,
                psynthea_distribution,
            )
            if valid and union_codes
            else None
        ),
        valid_for_distributional_comparison=valid,
        required=required,
        blocking_issue=required and not valid,
    )


# =============================================================================
# Issues and summary
# =============================================================================

def _issue_table(
    module_name: str,
    table_status: pd.DataFrame,
    clinical_signal: pd.DataFrame,
    distributional_similarity: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a normalized table of blocking issues and warnings.
    """

    rows: list[dict[str, object]] = []

    for row in table_status.itertuples(index=False):
        if row.blocking_issue:
            rows.append(
                _issue_row(
                    module_name,
                    "blocking",
                    row.table,
                    ModuleValidationIssueType.REQUIRED_TABLE_MISSING_OR_EMPTY.value,
                    (
                        f"Synthea rows={row.synthea_rows}; "
                        f"psynthea rows={row.psynthea_rows}"
                    ),
                )
            )
        elif row.synthea_rows > 0 and row.psynthea_rows == 0:
            rows.append(
                _issue_row(
                    module_name,
                    "warning",
                    row.table,
                    ModuleValidationIssueType.PSYNTHEA_TABLE_EMPTY.value,
                    "Synthea produced rows but psynthea did not.",
                )
            )
        elif row.synthea_rows == 0 and row.psynthea_rows > 0:
            rows.append(
                _issue_row(
                    module_name,
                    "warning",
                    row.table,
                    ModuleValidationIssueType.SYNTHEA_TABLE_EMPTY.value,
                    "psynthea produced rows but Synthea did not.",
                )
            )

    for row in clinical_signal.itertuples(index=False):
        if row.required and row.synthea_signal_count == 0:
            rows.append(
                _issue_row(
                    module_name,
                    "blocking",
                    row.domain,
                    ModuleValidationIssueType.REFERENCE_CLINICAL_SIGNAL_EMPTY.value,
                    f"Synthea produced no reference {row.domain} for the module.",
                )
            )

        if row.blocking_issue:
            rows.append(
                _issue_row(
                    module_name,
                    "blocking",
                    row.domain,
                    ModuleValidationIssueType.MISSING_CORE_CLINICAL_SIGNAL.value,
                    f"psynthea produced no required {row.domain} for the module.",
                )
            )

        if row.expected_signal_detected_synthea is True and row.expected_signal_detected_psynthea is False:
            rows.append(
                _issue_row(
                    module_name,
                    "warning",
                    row.domain,
                    ModuleValidationIssueType.EXPECTED_SIGNAL_MISSING_IN_PSYNTHEA.value,
                    f"Expected terms: {row.expected_terms}",
                )
            )

    for row in distributional_similarity.itertuples(index=False):
        if row.blocking_issue:
            rows.append(
                _issue_row(
                    module_name,
                    "blocking",
                    row.domain,
                    ModuleValidationIssueType.DISTRIBUTION_NOT_COMPARABLE.value,
                    "At least one generator produced no coded events.",
                )
            )

    if not rows:
        return pd.DataFrame(columns=_ISSUE_COLUMNS)

    return pd.DataFrame(rows, columns=_ISSUE_COLUMNS)


def _summary_table(
    module_name: str,
    table_status: pd.DataFrame,
    clinical_signal: pd.DataFrame,
    distributional_similarity: pd.DataFrame,
    issues: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build one-row module validation summary.
    """

    blocking_issue_count = int((issues["severity"] == "blocking").sum()) if not issues.empty else 0
    warning_count = int((issues["severity"] == "warning").sum()) if not issues.empty else 0

    synthea_functional = _all_required_tables_non_empty(
        table_status,
        "synthea_rows",
    )
    psynthea_functional = _all_required_tables_non_empty(
        table_status,
        "psynthea_rows",
    )
    status, status_reason = _classify_module_status(
        synthea_functional=synthea_functional,
        psynthea_functional=psynthea_functional,
        issues=issues,
        clinical_signal=clinical_signal,
    )

    comparable_similarity = distributional_similarity[
        distributional_similarity["valid_for_distributional_comparison"]
    ]

    summary = {
        "module_name": module_name,
        "status": status.value,
        "status_reason": status_reason,
        "synthea_functional": synthea_functional,
        "psynthea_functional": psynthea_functional,
        "valid_for_comparison": status in {
            ModuleValidationStatus.COMPARABLE,
            ModuleValidationStatus.PARTIALLY_COMPARABLE,
        },
        "blocking_issue_count": blocking_issue_count,
        "warning_count": warning_count,
        "synthea_condition_count": _domain_count(clinical_signal, "conditions", "synthea_signal_count"),
        "psynthea_condition_count": _domain_count(clinical_signal, "conditions", "psynthea_signal_count"),
        "synthea_observation_count": _domain_count(clinical_signal, "observations", "synthea_signal_count"),
        "psynthea_observation_count": _domain_count(clinical_signal, "observations", "psynthea_signal_count"),
        "mean_distributional_similarity": _series_mean(
            comparable_similarity["jaccard_similarity"],
        ),
        "mean_jensen_shannon_divergence": _series_mean(
            comparable_similarity["jensen_shannon_divergence"],
        ),
    }

    return pd.DataFrame([summary], columns=_SUMMARY_COLUMNS)


# =============================================================================
# Generic helpers
# =============================================================================

def _get_table(
    cohort: ValidationCohort,
    table: str,
) -> pd.DataFrame | None:
    """
    Return a cohort table by canonical attribute name.
    """

    value = getattr(cohort, table, None)
    if isinstance(value, pd.DataFrame):
        return value
    return None


def _row_count(
    table: pd.DataFrame | None,
) -> int:
    """
    Return number of rows for an optional DataFrame.
    """

    return 0 if table is None else int(len(table))


def _code_set(
    table: pd.DataFrame | None,
    domain: str,
) -> set[str]:
    """
    Return the set of non-null clinical codes for a table.
    """

    if table is None:
        return set()

    code_column = _CODE_COLUMNS.get(domain)
    if code_column not in table.columns:
        return set()

    return {
        str(value).strip()
        for value in table[code_column].dropna().tolist()
        if str(value).strip()
    }


def _code_distribution(
    table: pd.DataFrame | None,
    domain: str,
) -> dict[str, int]:
    """
    Return code frequency distribution for one domain.
    """

    if table is None:
        return {}

    code_column = _CODE_COLUMNS.get(domain)
    if code_column not in table.columns:
        return {}

    counts = table[code_column].dropna().astype(str).str.strip().value_counts()
    return {
        code: int(count)
        for code, count in counts.items()
        if code
    }


def _expected_terms_detected(
    table: pd.DataFrame | None,
    domain: str,
    expected_terms: Sequence[str],
) -> bool | None:
    """
    Return whether expected module-specific terms are present.
    """

    terms = [term.strip().lower() for term in expected_terms if term.strip()]
    if not terms:
        return None

    if table is None or table.empty:
        return False

    searchable_columns = [
        column
        for column in [
            _CODE_COLUMNS.get(domain),
            _DESCRIPTION_COLUMNS.get(domain),
        ]
        if column in table.columns
    ]

    if not searchable_columns:
        return False

    text_parts: list[str] = []
    for column in searchable_columns:
        text_parts.extend(
            table[column]
            .dropna()
            .astype(str)
            .str.lower()
            .tolist()
        )

    text = " ".join(text_parts)
    return any(term in text for term in terms)


def _safe_ratio(
    numerator: float | int,
    denominator: float | int,
) -> float | None:
    """
    Return numerator / denominator when possible.
    """

    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _jaccard_similarity(
    left: set[str],
    right: set[str],
) -> float | None:
    """
    Return set-level Jaccard similarity.
    """

    union = left | right
    if not union:
        return None
    return len(left & right) / len(union)


def _overlap_coefficient(
    left: set[str],
    right: set[str],
) -> float | None:
    """
    Return overlap coefficient between two code sets.
    """

    smallest = min(len(left), len(right))
    if smallest == 0:
        return None
    return len(left & right) / smallest


def _jensen_shannon_divergence(
    left: Mapping[str, int],
    right: Mapping[str, int],
) -> float | None:
    """
    Return Jensen-Shannon divergence between two code distributions.
    """

    keys = sorted(set(left) | set(right))
    if not keys:
        return None

    left_total = sum(left.values())
    right_total = sum(right.values())
    if left_total == 0 or right_total == 0:
        return None

    p = [left.get(key, 0) / left_total for key in keys]
    q = [right.get(key, 0) / right_total for key in keys]
    m = [(p_i + q_i) / 2 for p_i, q_i in zip(p, q)]

    divergence = (
        0.5 * _kl_divergence(p, m)
        + 0.5 * _kl_divergence(q, m)
    )

    # Jensen-Shannon divergence is mathematically non-negative. Floating-point
    # cancellation can nevertheless produce a tiny negative value for nearly
    # identical empirical distributions (for example, -1e-17). Passing that
    # value directly to math.sqrt raises ``ValueError: math domain error`` and
    # aborts the complete validation pipeline. Clamp only numerical underflow;
    # a materially negative value indicates an implementation/data invariant
    # violation and must not be silently hidden.
    if divergence < 0.0:
        if divergence >= -1e-12:
            divergence = 0.0
        else:
            raise ValueError(
                "Jensen-Shannon divergence became materially negative: "
                f"{divergence!r}"
            )

    return sqrt(divergence)


def _kl_divergence(
    distribution: Sequence[float],
    reference: Sequence[float],
) -> float:
    """
    Return Kullback-Leibler divergence using base-2 logarithms.
    """

    total = 0.0
    for value, reference_value in zip(distribution, reference):
        if value == 0:
            continue
        total += value * log2(value / reference_value)
    return total


def _issue_row(
    module_name: str,
    severity: str,
    domain: str,
    issue: str,
    details: str,
) -> dict[str, object]:
    """
    Build a normalized issue row.
    """

    return asdict(
        ModuleValidationIssue(
            module_name=module_name,
            severity=severity,
            domain=domain,
            issue=issue,
            details=details,
        )
    )


def _classify_module_status(
    *,
    synthea_functional: bool,
    psynthea_functional: bool,
    issues: pd.DataFrame,
    clinical_signal: pd.DataFrame,
) -> tuple[ModuleValidationStatus, str]:
    """
    Classify whether a module can be compared, and why.

    The classification intentionally separates a missing Synthea reference signal
    from a psynthea functional failure. This is critical when psynthea v1.0 skips
    unimplemented states or produces empty clinical outputs.
    """

    issue_values = set(issues["issue"]) if not issues.empty else set()
    has_blocking = bool((issues["severity"] == "blocking").any()) if not issues.empty else False

    if (
        not synthea_functional
        or ModuleValidationIssueType.REFERENCE_CLINICAL_SIGNAL_EMPTY.value in issue_values
    ):
        return (
            ModuleValidationStatus.REFERENCE_EMPTY,
            "Synthea Java did not produce the minimum reference clinical signal required for this module.",
        )

    if (
        not psynthea_functional
        or ModuleValidationIssueType.MISSING_CORE_CLINICAL_SIGNAL.value in issue_values
    ):
        return (
            ModuleValidationStatus.PSYNTHEA_FUNCTIONAL_FAILURE,
            "psynthea did not produce the minimum clinical output required for module-level comparison.",
        )

    if has_blocking:
        return (
            ModuleValidationStatus.NOT_COMPARABLE,
            "Blocking validation issues prevent a scientifically valid module comparison.",
        )

    if issue_values:
        return (
            ModuleValidationStatus.PARTIALLY_COMPARABLE,
            "The module produced comparable core signal, but optional domains or warnings require restricted interpretation.",
        )

    return (
        ModuleValidationStatus.COMPARABLE,
        "Both generators produced the required clinical signal and no validation issues were detected.",
    )


def _normalise_required_signal_domains(
    domains: Sequence[str] | None,
) -> set[str]:
    """Validate and normalize configured coded signal domains."""

    configured = tuple(domains or ("conditions",))
    normalized = {str(domain).strip().casefold() for domain in configured}
    invalid = normalized.difference(_DEFAULT_SIGNAL_TABLES)
    if invalid:
        values = ", ".join(sorted(invalid))
        raise ValueError(f"Unsupported required signal domain(s): {values}")
    if not normalized:
        raise ValueError("At least one required signal domain must be configured.")
    return normalized


def _all_required_tables_non_empty(
    table_status: pd.DataFrame,
    count_column: str,
) -> bool:
    """
    Return whether all required tables have at least one row.
    """

    required_rows = table_status[table_status["required"]]
    if required_rows.empty:
        return True
    return bool((required_rows[count_column] > 0).all())


def _domain_count(
    clinical_signal: pd.DataFrame,
    domain: str,
    column: str,
) -> int:
    """
    Return one count from the clinical signal table.
    """

    rows = clinical_signal[clinical_signal["domain"] == domain]
    if rows.empty:
        return 0
    return int(rows.iloc[0][column])


def _series_mean(
    values: Iterable[float | None],
) -> float | None:
    """
    Return the mean of non-null numeric values.
    """

    series = pd.Series(list(values)).dropna()
    if series.empty:
        return None
    return float(series.mean())


def _dataclass_table(
    rows: Sequence[object],
    columns: Sequence[str],
) -> pd.DataFrame:
    """
    Convert dataclass rows into a stable DataFrame.
    """

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([asdict(row) for row in rows], columns=columns)
