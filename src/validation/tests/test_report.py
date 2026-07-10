"""
Tests for validation report generation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.report import (
    build_module_report,
    build_validation_report,
    render_markdown_report,
    write_markdown_report,
)


class _ValidationStub:
    pass


def _comparison(
    *,
    skipped: bool = False,
    significant_test_count: int = 0,
    significant_after_fdr_count: int = 0,
) -> ModuleStatisticalComparisonResult:
    summary = pd.DataFrame(
        [
            {
                "module_name": "hypertension",
                "validation_status": "comparable",
                "valid_for_statistical_comparison": not skipped,
                "skipped": skipped,
                "skip_reason": "not comparable" if skipped else None,
                "continuous_test_count": 1,
                "categorical_test_count": 1,
                "prevalence_test_count": 2,
                "distribution_test_count": 1,
                "significant_test_count": significant_test_count,
                "significant_after_fdr_count": significant_after_fdr_count,
                "mean_jensen_shannon_divergence": 0.01,
            }
        ]
    )
    prevalence = pd.DataFrame(
        [
            {
                "module_name": "hypertension",
                "scope": "prevalence",
                "domain": "conditions",
                "code": "59621000",
                "synthea_prevalence": 0.20,
                "psynthea_prevalence": 0.30,
                "absolute_difference": 0.10,
                "relative_difference": 0.50,
                "test_name": "proportion_z_test",
                "statistic": 2.1,
                "p_value": 0.02,
                "adjusted_p_value": 0.04,
                "significant": True,
                "significant_after_fdr": significant_after_fdr_count > 0,
                "notes": None,
            },
            {
                "module_name": "hypertension",
                "scope": "prevalence",
                "domain": "medications",
                "code": "314076",
                "synthea_prevalence": 0.10,
                "psynthea_prevalence": 0.12,
                "absolute_difference": 0.02,
                "relative_difference": 0.20,
                "test_name": "proportion_z_test",
                "statistic": 0.5,
                "p_value": 0.61,
                "adjusted_p_value": 0.61,
                "significant": False,
                "significant_after_fdr": False,
                "notes": None,
            },
        ]
    )

    continuous = pd.DataFrame(
        [
            {
                "module_name": "hypertension",
                "scope": "continuous",
                "metric": "age",
                "test_name": "ks_test",
                "statistic": 0.1,
                "p_value": 0.9,
                "effect_size": None,
                "significant": False,
                "notes": None,
            }
        ]
    )

    return ModuleStatisticalComparisonResult(
        module_name="hypertension",
        validation=_ValidationStub(),
        continuous_tests=continuous,
        categorical_tests=pd.DataFrame(),
        prevalence_tests=prevalence,
        distribution_tests=pd.DataFrame(),
        summary=summary,
    )


def test_build_module_report_marks_pass_without_significant_tests() -> None:
    report = build_module_report(_comparison())

    assert report.decision == "pass"
    assert report.summary.iloc[0]["total_test_count"] == 5
    assert report.significant_tests.empty
    assert report.top_prevalence_differences.iloc[0]["code"] == "59621000"


def test_build_module_report_marks_warning_for_unadjusted_significance() -> None:
    report = build_module_report(_comparison(significant_test_count=1))

    assert report.decision == "warning"
    assert "unadjusted" in report.notes[0]


def test_build_module_report_marks_fail_for_fdr_significance() -> None:
    report = build_module_report(
        _comparison(
            significant_test_count=1,
            significant_after_fdr_count=1,
        )
    )

    assert report.decision == "fail"
    assert not report.significant_tests.empty


def test_build_module_report_marks_skipped_comparisons() -> None:
    report = build_module_report(_comparison(skipped=True))

    assert report.decision == "skipped"
    assert report.notes == ["not comparable"]


def test_render_markdown_report_contains_core_sections() -> None:
    report = build_validation_report(
        [_comparison()],
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    markdown = render_markdown_report(report)

    assert "# Psynthea Validation Report" in markdown
    assert "## Executive Summary" in markdown
    assert "## Module: hypertension" in markdown
    assert "Decision: **PASS**" in markdown


def test_write_markdown_report_creates_parent_directories(tmp_path: Path) -> None:
    report = build_validation_report([_comparison()])
    output_path = tmp_path / "nested" / "report.md"

    returned = write_markdown_report(report, output_path)

    assert returned == output_path
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("# Psynthea Validation Report")
