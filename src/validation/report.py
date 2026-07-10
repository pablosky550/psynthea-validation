"""
Reporting layer for module-level validation results.

This module converts functional and statistical comparison outputs into a
human-readable validation report.

It intentionally does not compute metrics, run statistical tests, load cohort
files, generate plots or execute simulators. It only formats already-computed
results produced by the comparison layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult

__all__ = [
    "ModuleReport",
    "ValidationReport",
    "build_module_report",
    "build_validation_report",
    "render_markdown_report",
    "write_markdown_report",
]


# =============================================================================
# Configuration
# =============================================================================

_REPORT_SUMMARY_COLUMNS = [
    "module_name",
    "validation_status",
    "decision",
    "valid_for_statistical_comparison",
    "skipped",
    "skip_reason",
    "total_test_count",
    "significant_test_count",
    "significant_after_fdr_count",
    "mean_jensen_shannon_divergence",
]

_TOP_PREVALENCE_COLUMNS = [
    "domain",
    "code",
    "synthea_prevalence",
    "psynthea_prevalence",
    "absolute_difference",
    "relative_difference",
    "p_value",
    "adjusted_p_value",
    "significant_after_fdr",
]

_SIGNIFICANT_TEST_COLUMNS = [
    "scope",
    "domain_or_metric",
    "test_name",
    "statistic",
    "p_value",
    "effect_size",
    "notes",
]

_DECISION_PASS = "pass"
_DECISION_WARNING = "warning"
_DECISION_FAIL = "fail"
_DECISION_SKIPPED = "skipped"


# =============================================================================
# Models
# =============================================================================


@dataclass(slots=True)
class ModuleReport:
    """
    Report-ready representation of one module comparison.

    The object contains only derived presentation tables. It keeps the original
    comparison result available for traceability but never mutates it.
    """

    module_name: str
    decision: str
    summary: pd.DataFrame
    significant_tests: pd.DataFrame
    top_prevalence_differences: pd.DataFrame
    notes: list[str]
    comparison: ModuleStatisticalComparisonResult


@dataclass(slots=True)
class ValidationReport:
    """
    Report-ready representation of a complete validation run.
    """

    generated_at: datetime
    modules: list[ModuleReport]
    summary: pd.DataFrame


# =============================================================================
# Public API
# =============================================================================


def build_module_report(
    comparison: ModuleStatisticalComparisonResult,
    *,
    top_n_prevalence_differences: int = 10,
) -> ModuleReport:
    """
    Build a report-ready summary for one statistical comparison result.
    """

    decision = _module_decision(comparison)
    summary = _module_summary_table(comparison, decision)
    significant_tests = _significant_tests_table(comparison)
    top_prevalence_differences = _top_prevalence_differences(
        comparison.prevalence_tests,
        top_n=top_n_prevalence_differences,
    )
    notes = _module_notes(comparison, decision)

    return ModuleReport(
        module_name=comparison.module_name,
        decision=decision,
        summary=summary,
        significant_tests=significant_tests,
        top_prevalence_differences=top_prevalence_differences,
        notes=notes,
        comparison=comparison,
    )


def build_validation_report(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    *,
    generated_at: datetime | None = None,
    top_n_prevalence_differences: int = 10,
) -> ValidationReport:
    """
    Build a report-ready object from one or more module comparisons.
    """

    modules = [
        build_module_report(
            comparison,
            top_n_prevalence_differences=top_n_prevalence_differences,
        )
        for comparison in comparisons
    ]

    summary = _validation_summary_table(modules)

    return ValidationReport(
        generated_at=generated_at or datetime.now(UTC),
        modules=modules,
        summary=summary,
    )


def render_markdown_report(report: ValidationReport) -> str:
    """
    Render a validation report as Markdown.
    """

    sections = [
        "# Psynthea Validation Report",
        "",
        f"Generated at: {report.generated_at.isoformat()}",
        "",
        "## Executive Summary",
        "",
        _markdown_table(report.summary),
    ]

    for module in report.modules:
        sections.extend(_module_markdown_sections(module))

    return "\n".join(sections).rstrip() + "\n"


def write_markdown_report(
    report: ValidationReport,
    output_path: str | Path,
) -> Path:
    """
    Write a Markdown validation report to disk.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown_report(report), encoding="utf-8")
    return output_path


# =============================================================================
# Summary construction
# =============================================================================


def _module_summary_table(
    comparison: ModuleStatisticalComparisonResult,
    decision: str,
) -> pd.DataFrame:
    base = _first_row(comparison.summary)

    row = {
        "module_name": comparison.module_name,
        "validation_status": base.get("validation_status"),
        "decision": decision,
        "valid_for_statistical_comparison": base.get("valid_for_statistical_comparison"),
        "skipped": base.get("skipped"),
        "skip_reason": base.get("skip_reason"),
        "total_test_count": _total_test_count(base),
        "significant_test_count": base.get("significant_test_count", 0),
        "significant_after_fdr_count": base.get("significant_after_fdr_count", 0),
        "mean_jensen_shannon_divergence": base.get("mean_jensen_shannon_divergence"),
    }

    return pd.DataFrame([row], columns=_REPORT_SUMMARY_COLUMNS)


def _validation_summary_table(modules: Sequence[ModuleReport]) -> pd.DataFrame:
    if not modules:
        return pd.DataFrame(columns=_REPORT_SUMMARY_COLUMNS)

    return pd.concat(
        [module.summary for module in modules],
        ignore_index=True,
    )


def _significant_tests_table(
    comparison: ModuleStatisticalComparisonResult,
) -> pd.DataFrame:
    frames = [
        _significant_standard_tests(comparison.continuous_tests, label_column="metric"),
        _significant_standard_tests(comparison.categorical_tests, label_column="domain"),
        _significant_standard_tests(comparison.distribution_tests, label_column="domain"),
        _significant_prevalence_tests(comparison.prevalence_tests),
    ]

    rows = [frame for frame in frames if not frame.empty]
    if not rows:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    return pd.concat(rows, ignore_index=True)[_SIGNIFICANT_TEST_COLUMNS]


def _top_prevalence_differences(
    prevalence_tests: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    if prevalence_tests.empty:
        return pd.DataFrame(columns=_TOP_PREVALENCE_COLUMNS)

    frame = prevalence_tests.copy()
    frame["_absolute_magnitude"] = frame["absolute_difference"].abs()

    return (
        frame.sort_values("_absolute_magnitude", ascending=False)
        .head(top_n)
        [_TOP_PREVALENCE_COLUMNS]
        .reset_index(drop=True)
    )


# =============================================================================
# Decision rules
# =============================================================================


def _module_decision(comparison: ModuleStatisticalComparisonResult) -> str:
    summary = _first_row(comparison.summary)

    if bool(summary.get("skipped", False)):
        return _DECISION_SKIPPED

    if not bool(summary.get("valid_for_statistical_comparison", False)):
        return _DECISION_FAIL

    significant_after_fdr = int(summary.get("significant_after_fdr_count", 0) or 0)
    significant_tests = int(summary.get("significant_test_count", 0) or 0)

    if significant_after_fdr > 0:
        return _DECISION_FAIL

    if significant_tests > 0:
        return _DECISION_WARNING

    return _DECISION_PASS


def _module_notes(
    comparison: ModuleStatisticalComparisonResult,
    decision: str,
) -> list[str]:
    summary = _first_row(comparison.summary)
    notes: list[str] = []

    if decision == _DECISION_SKIPPED:
        notes.append(str(summary.get("skip_reason") or "Statistical comparison was skipped."))

    if decision == _DECISION_WARNING:
        notes.append("One or more unadjusted statistical tests were significant; FDR-adjusted prevalence tests did not remain significant.")

    if decision == _DECISION_FAIL:
        notes.append("At least one FDR-adjusted prevalence comparison remained significant or the module was not statistically comparable.")

    if not notes:
        notes.append("No statistically relevant divergence was detected by the configured comparison layer.")

    return notes


# =============================================================================
# Markdown rendering
# =============================================================================


def _module_markdown_sections(module: ModuleReport) -> list[str]:
    sections = [
        "",
        f"## Module: {module.module_name}",
        "",
        f"Decision: **{module.decision.upper()}**",
        "",
        "### Summary",
        "",
        _markdown_table(module.summary),
        "",
        "### Notes",
        "",
        *_markdown_list(module.notes),
        "",
        "### Significant tests",
        "",
        _markdown_table(module.significant_tests),
        "",
        "### Largest prevalence differences",
        "",
        _markdown_table(module.top_prevalence_differences),
    ]
    return sections


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows available._"

    display = frame.copy()
    display = display.map(_format_value)
    return display.to_markdown(index=False)


def _markdown_list(values: Sequence[str]) -> list[str]:
    if not values:
        return ["- No notes."]

    return [f"- {value}" for value in values]


# =============================================================================
# Generic helpers
# =============================================================================


def _first_row(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {}

    return frame.iloc[0].to_dict()


def _total_test_count(row: dict) -> int:
    return int(row.get("continuous_test_count", 0) or 0) + int(row.get("categorical_test_count", 0) or 0) + int(row.get("prevalence_test_count", 0) or 0) + int(row.get("distribution_test_count", 0) or 0)


def _significant_standard_tests(
    frame: pd.DataFrame,
    *,
    label_column: str,
) -> pd.DataFrame:
    if frame.empty or "significant" not in frame.columns:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    significant = frame[frame["significant"].fillna(False)].copy()
    if significant.empty:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    significant["domain_or_metric"] = significant[label_column]
    return significant.assign(
        effect_size=significant.get("effect_size"),
    )[
        [
            "scope",
            "domain_or_metric",
            "test_name",
            "statistic",
            "p_value",
            "effect_size",
            "notes",
        ]
    ]


def _significant_prevalence_tests(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "significant_after_fdr" not in frame.columns:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    significant = frame[frame["significant_after_fdr"].fillna(False)].copy()
    if significant.empty:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    significant["domain_or_metric"] = significant["domain"].astype(str) + ":" + significant["code"].astype(str)
    significant["effect_size"] = significant["absolute_difference"]

    return significant[
        [
            "scope",
            "domain_or_metric",
            "test_name",
            "statistic",
            "p_value",
            "effect_size",
            "notes",
        ]
    ]


def _format_value(value: object) -> object:
    if pd.isna(value):
        return ""

    if isinstance(value, float):
        return f"{value:.4f}"

    return value
