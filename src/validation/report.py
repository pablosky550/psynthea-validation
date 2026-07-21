"""Research-facing reporting for module-level validation results.

The reporting layer converts already-computed functional and statistical
comparison outputs into deterministic, traceable and module-specific summaries.
It never loads simulator outputs, executes statistical tests, recalculates
p-values or invents clinical conclusions that are not supported by persisted
comparison evidence.

Every narrative statement emitted by this module is derived from the supplied
``ModuleStatisticalComparisonResult``.  Modules with different evidence therefore
produce different findings, priorities and conclusions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import pandas as pd

from validation.comparison.statistical_comparison import (
    ModuleStatisticalComparisonResult,
)

__all__ = [
    "ModuleFinding",
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

_REPORT_SUMMARY_COLUMNS: Final = [
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

_TOP_PREVALENCE_COLUMNS: Final = [
    "domain",
    "code",
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
    "p_value",
    "adjusted_p_value",
    "significant_after_fdr",
]

_SIGNIFICANT_TEST_COLUMNS: Final = [
    "scope",
    "domain_or_metric",
    "test_name",
    "statistic",
    "p_value",
    "adjusted_p_value",
    "effect_size",
    "effect_size_type",
    "significant_after_fdr",
    "notes",
]

_FINDING_COLUMNS: Final = [
    "severity",
    "category",
    "endpoint",
    "finding",
    "synthea_value",
    "psynthea_value",
    "absolute_difference",
    "relative_difference",
    "test_name",
    "p_value",
    "adjusted_p_value",
]

_DECISION_PASS: Final = "pass"
_DECISION_WARNING: Final = "warning"
_DECISION_FAIL: Final = "fail"
_DECISION_SKIPPED: Final = "skipped"

_SEVERITY_ORDER: Final[Mapping[str, int]] = {
    "critical": 0,
    "high": 1,
    "moderate": 2,
    "low": 3,
    "informational": 4,
}


# =============================================================================
# Models
# =============================================================================


@dataclass(frozen=True, slots=True)
class ModuleFinding:
    """One evidence-backed, module-specific report finding."""

    severity: str
    category: str
    endpoint: str
    finding: str
    evidence: str
    recommendation: str


@dataclass(slots=True)
class ModuleReport:
    """Report-ready representation of one module comparison."""

    module_name: str
    decision: str
    summary: pd.DataFrame
    significant_tests: pd.DataFrame
    top_prevalence_differences: pd.DataFrame
    notes: list[str]
    comparison: ModuleStatisticalComparisonResult
    findings: tuple[ModuleFinding, ...] = ()
    findings_table: pd.DataFrame | None = None
    conclusion: str = ""


@dataclass(slots=True)
class ValidationReport:
    """Report-ready representation of a complete validation run."""

    generated_at: datetime
    modules: list[ModuleReport]
    summary: pd.DataFrame
    overall_decision: str = _DECISION_SKIPPED
    conclusion: str = ""


# =============================================================================
# Public API
# =============================================================================


def build_module_report(
    comparison: ModuleStatisticalComparisonResult,
    *,
    top_n_prevalence_differences: int = 10,
) -> ModuleReport:
    """Build an evidence-driven report for one module comparison."""

    if not isinstance(comparison, ModuleStatisticalComparisonResult):
        raise TypeError(
            "comparison must be a ModuleStatisticalComparisonResult."
        )
    if (
        isinstance(top_n_prevalence_differences, bool)
        or not isinstance(top_n_prevalence_differences, int)
        or top_n_prevalence_differences <= 0
    ):
        raise ValueError(
            "top_n_prevalence_differences must be a positive integer."
        )

    decision = _module_decision(comparison)
    summary = _module_summary_table(comparison, decision)
    significant_tests = _significant_tests_table(comparison)
    prevalence = _top_prevalence_differences(
        comparison.prevalence_tests,
        top_n=top_n_prevalence_differences,
    )
    findings, findings_table = _module_findings(comparison)
    notes = _module_notes(comparison, decision, findings)
    conclusion = _module_conclusion(
        comparison,
        decision=decision,
        findings=findings,
    )

    return ModuleReport(
        module_name=comparison.module_name,
        decision=decision,
        summary=summary,
        significant_tests=significant_tests,
        top_prevalence_differences=prevalence,
        notes=notes,
        comparison=comparison,
        findings=findings,
        findings_table=findings_table,
        conclusion=conclusion,
    )


def build_validation_report(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    *,
    generated_at: datetime | None = None,
    top_n_prevalence_differences: int = 10,
) -> ValidationReport:
    """Build a complete report from one or more independent module results."""

    if isinstance(comparisons, (str, bytes)) or not isinstance(
        comparisons, Sequence
    ):
        raise TypeError("comparisons must be a sequence.")

    modules = [
        build_module_report(
            comparison,
            top_n_prevalence_differences=top_n_prevalence_differences,
        )
        for comparison in comparisons
    ]
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")

    summary = _validation_summary_table(modules)
    overall_decision = _overall_decision(modules)

    return ValidationReport(
        generated_at=timestamp.astimezone(UTC),
        modules=modules,
        summary=summary,
        overall_decision=overall_decision,
        conclusion=_validation_conclusion(modules, overall_decision),
    )


def render_markdown_report(report: ValidationReport) -> str:
    """Render a deterministic Markdown report with module-specific analysis."""

    if not isinstance(report, ValidationReport):
        raise TypeError("report must be a ValidationReport.")

    sections = [
        "# Psynthea Validation Report",
        "",
        f"Generated at: {report.generated_at.isoformat()}",
        "",
        f"Overall decision: **{report.overall_decision.upper()}**",
        "",
        report.conclusion,
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
    """Write a Markdown validation report atomically enough for local use."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_markdown_report(report), encoding="utf-8")
    return destination


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
        "valid_for_statistical_comparison": base.get(
            "valid_for_statistical_comparison"
        ),
        "skipped": base.get("skipped"),
        "skip_reason": base.get("skip_reason"),
        "total_test_count": _total_test_count(base),
        "significant_test_count": _safe_int(
            base.get("significant_test_count")
        ),
        "significant_after_fdr_count": _safe_int(
            base.get("significant_after_fdr_count")
        ),
        "mean_jensen_shannon_divergence": base.get(
            "mean_jensen_shannon_divergence"
        ),
    }
    return pd.DataFrame([row], columns=_REPORT_SUMMARY_COLUMNS)


def _validation_summary_table(
    modules: Sequence[ModuleReport],
) -> pd.DataFrame:
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
        _significant_standard_tests(
            comparison.continuous_tests,
            label_column="metric",
        ),
        _significant_standard_tests(
            comparison.categorical_tests,
            label_column="domain",
        ),
        _significant_standard_tests(
            comparison.distribution_tests,
            label_column="domain",
        ),
        _significant_prevalence_tests(comparison.prevalence_tests),
    ]
    populated = [frame for frame in frames if not frame.empty]
    if not populated:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    result = pd.concat(populated, ignore_index=True)
    return _ensure_columns(result, _SIGNIFICANT_TEST_COLUMNS)


def _top_prevalence_differences(
    prevalence_tests: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    if prevalence_tests.empty:
        return pd.DataFrame(columns=_TOP_PREVALENCE_COLUMNS)

    frame = prevalence_tests.copy()
    difference = _numeric_series(frame, "absolute_difference")
    frame["_absolute_magnitude"] = difference.abs()
    ordered = frame.sort_values(
        ["_absolute_magnitude", "domain", "code"],
        ascending=[False, True, True],
        kind="mergesort",
    ).head(top_n)
    return _ensure_columns(ordered, _TOP_PREVALENCE_COLUMNS).reset_index(
        drop=True
    )


# =============================================================================
# Evidence-derived findings
# =============================================================================


def _module_findings(
    comparison: ModuleStatisticalComparisonResult,
) -> tuple[tuple[ModuleFinding, ...], pd.DataFrame]:
    findings: list[ModuleFinding] = []
    rows: list[dict[str, Any]] = []

    findings.extend(_functional_findings(comparison, rows))
    findings.extend(_prevalence_findings(comparison.prevalence_tests, rows))
    findings.extend(_continuous_findings(comparison.continuous_tests, rows))
    findings.extend(_categorical_findings(comparison.categorical_tests, rows))
    findings.extend(_distribution_findings(comparison.distribution_tests, rows))

    findings = _deduplicate_findings(findings)
    findings.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(item.severity, 99),
            item.category,
            item.endpoint,
            item.finding,
        )
    )

    table = pd.DataFrame(rows)
    if table.empty:
        table = pd.DataFrame(columns=_FINDING_COLUMNS)
    else:
        table = _ensure_columns(table, _FINDING_COLUMNS)
        table["_severity_order"] = table["severity"].map(
            _SEVERITY_ORDER
        ).fillna(99)
        table = (
            table.sort_values(
                ["_severity_order", "category", "endpoint"],
                kind="mergesort",
            )
            .drop(columns="_severity_order")
            .drop_duplicates(
                subset=["category", "endpoint", "finding"],
                keep="first",
            )
            .reset_index(drop=True)
        )

    return tuple(findings), table


def _functional_findings(
    comparison: ModuleStatisticalComparisonResult,
    rows: list[dict[str, Any]],
) -> list[ModuleFinding]:
    findings: list[ModuleFinding] = []
    validation = comparison.validation

    table_status = getattr(validation, "table_status", pd.DataFrame())
    if isinstance(table_status, pd.DataFrame) and not table_status.empty:
        for _, row in table_status.iterrows():
            domain = _text(row.get("table"), "clinical output")
            synthea_rows = _safe_int(row.get("synthea_rows"))
            psynthea_rows = _safe_int(row.get("psynthea_rows"))
            required = _safe_bool(row.get("required"))
            relative = _safe_float(row.get("relative_row_difference"))

            if synthea_rows > 0 and psynthea_rows == 0:
                severity = "critical" if required else "high"
                message = (
                    f"Psynthea produced no {domain} records while Synthea "
                    f"produced {synthea_rows}."
                )
                evidence = (
                    f"Synthea={synthea_rows}; Psynthea=0; relative "
                    "difference=-100.0%."
                )
                recommendation = (
                    f"Trace {domain} state execution and exporter retention, "
                    "then repeat the comparison with identical seeds."
                )
                findings.append(
                    ModuleFinding(
                        severity,
                        "functional_output",
                        domain,
                        message,
                        evidence,
                        recommendation,
                    )
                )
                rows.append(
                    _finding_row(
                        severity=severity,
                        category="functional_output",
                        endpoint=domain,
                        finding=message,
                        synthea_value=synthea_rows,
                        psynthea_value=psynthea_rows,
                        absolute_difference=psynthea_rows - synthea_rows,
                        relative_difference=-1.0,
                    )
                )
                continue

            if relative is not None and abs(relative) >= 0.20:
                severity = "high" if abs(relative) >= 0.50 else "moderate"
                direction = "more" if relative > 0 else "fewer"
                message = (
                    f"Psynthea produced {abs(relative):.1%} {direction} "
                    f"{domain} records than Synthea."
                )
                evidence = (
                    f"Synthea={synthea_rows}; Psynthea={psynthea_rows}; "
                    f"relative difference={relative:+.1%}."
                )
                recommendation = (
                    f"Inspect generation and retention paths affecting {domain}, "
                    "then assess stability across independent seeds."
                )
                findings.append(
                    ModuleFinding(
                        severity,
                        "functional_output",
                        domain,
                        message,
                        evidence,
                        recommendation,
                    )
                )
                rows.append(
                    _finding_row(
                        severity=severity,
                        category="functional_output",
                        endpoint=domain,
                        finding=message,
                        synthea_value=synthea_rows,
                        psynthea_value=psynthea_rows,
                        absolute_difference=psynthea_rows - synthea_rows,
                        relative_difference=relative,
                    )
                )

    issues = getattr(validation, "issues", pd.DataFrame())
    if isinstance(issues, pd.DataFrame) and not issues.empty:
        for _, row in issues.iterrows():
            severity = _normalize_severity(row.get("severity"))
            domain = _text(row.get("domain"), "module")
            issue = _text(row.get("issue"), "functional issue")
            details = _text(row.get("details"), issue)
            findings.append(
                ModuleFinding(
                    severity,
                    "functional_validation",
                    domain,
                    details,
                    f"Functional validator issue: {issue}.",
                    f"Resolve the {domain} validation issue and regenerate evidence.",
                )
            )

    return findings


def _prevalence_findings(
    frame: pd.DataFrame,
    rows: list[dict[str, Any]],
) -> list[ModuleFinding]:
    findings: list[ModuleFinding] = []
    if frame.empty:
        return findings

    for _, row in frame.iterrows():
        significant_fdr = _safe_bool(row.get("significant_after_fdr"))
        if not significant_fdr:
            continue

        domain = _text(row.get("domain"), "prevalence")
        code = _text(row.get("code"), "unknown-code")
        endpoint = f"{domain}:{code}"
        synthea = _safe_float(row.get("synthea_prevalence"))
        psynthea = _safe_float(row.get("psynthea_prevalence"))
        absolute = _safe_float(row.get("absolute_difference"))
        relative = _safe_float(row.get("relative_difference"))
        adjusted = _safe_float(row.get("adjusted_p_value"))
        test_name = _text(row.get("test_name"), "prevalence test")

        magnitude = abs(absolute or 0.0)
        severity = "high" if magnitude >= 0.10 else "moderate"
        message = _prevalence_message(endpoint, synthea, psynthea, absolute)
        evidence = _prevalence_evidence(row)
        recommendation = (
            f"Audit cohort denominator, code mapping and transition probabilities "
            f"for {endpoint}; confirm the result across independent seeds."
        )
        findings.append(
            ModuleFinding(
                severity,
                "prevalence",
                endpoint,
                message,
                evidence,
                recommendation,
            )
        )
        rows.append(
            _finding_row(
                severity=severity,
                category="prevalence",
                endpoint=endpoint,
                finding=message,
                synthea_value=synthea,
                psynthea_value=psynthea,
                absolute_difference=absolute,
                relative_difference=relative,
                test_name=test_name,
                p_value=_safe_float(row.get("p_value")),
                adjusted_p_value=adjusted,
            )
        )

    return findings


def _continuous_findings(
    frame: pd.DataFrame,
    rows: list[dict[str, Any]],
) -> list[ModuleFinding]:
    findings: list[ModuleFinding] = []
    if frame.empty or "significant" not in frame.columns:
        return findings

    significant = frame[frame["significant"].fillna(False)]
    for metric, metric_rows in significant.groupby("metric", dropna=False):
        metric_name = _text(metric, "continuous endpoint")
        strongest = _strongest_test(metric_rows)
        test_name = _text(strongest.get("test_name"), "statistical test")
        statistic = _safe_float(strongest.get("statistic"))
        p_value = _safe_float(strongest.get("p_value"))
        effect = _safe_float(strongest.get("effect_size"))
        effect_type = _effect_size_type(test_name)
        severity = _effect_severity(effect, test_name)

        message = (
            f"The distribution of {metric_name} differs between simulators "
            f"according to {test_name}."
        )
        evidence = _test_evidence(
            test_name=test_name,
            statistic=statistic,
            p_value=p_value,
            effect_size=effect,
            effect_size_type=effect_type,
            n_synthea=_safe_int(strongest.get("n_synthea")),
            n_psynthea=_safe_int(strongest.get("n_psynthea")),
        )
        recommendation = (
            f"Inspect the generation logic underlying {metric_name} and compare "
            "patient-level distributions across several seeds."
        )
        findings.append(
            ModuleFinding(
                severity,
                "continuous_distribution",
                metric_name,
                message,
                evidence,
                recommendation,
            )
        )
        rows.append(
            _finding_row(
                severity=severity,
                category="continuous_distribution",
                endpoint=metric_name,
                finding=message,
                test_name=test_name,
                p_value=p_value,
            )
        )

    return findings


def _categorical_findings(
    frame: pd.DataFrame,
    rows: list[dict[str, Any]],
) -> list[ModuleFinding]:
    findings: list[ModuleFinding] = []
    if frame.empty or "significant" not in frame.columns:
        return findings

    for _, row in frame[frame["significant"].fillna(False)].iterrows():
        domain = _text(row.get("domain"), "categorical endpoint")
        test_name = _text(row.get("test_name"), "categorical test")
        effect = _safe_float(row.get("effect_size"))
        severity = _effect_severity(effect, test_name)
        message = (
            f"The categorical composition of {domain} differs between "
            "Synthea and Psynthea."
        )
        evidence = _test_evidence(
            test_name=test_name,
            statistic=_safe_float(row.get("statistic")),
            p_value=_safe_float(row.get("p_value")),
            effect_size=effect,
            effect_size_type=_effect_size_type(test_name),
            n_synthea=_safe_int(row.get("n_synthea")),
            n_psynthea=_safe_int(row.get("n_psynthea")),
        )
        findings.append(
            ModuleFinding(
                severity,
                "categorical_distribution",
                domain,
                message,
                evidence,
                f"Compare category mappings and generation frequencies for {domain}.",
            )
        )
        rows.append(
            _finding_row(
                severity=severity,
                category="categorical_distribution",
                endpoint=domain,
                finding=message,
                test_name=test_name,
                p_value=_safe_float(row.get("p_value")),
            )
        )

    return findings


def _distribution_findings(
    frame: pd.DataFrame,
    rows: list[dict[str, Any]],
) -> list[ModuleFinding]:
    findings: list[ModuleFinding] = []
    if frame.empty:
        return findings

    for _, row in frame.iterrows():
        significant = _safe_bool(row.get("significant"))
        jsd = _safe_float(row.get("jensen_shannon_divergence"))
        if not significant and (jsd is None or jsd < 0.20):
            continue

        domain = _text(row.get("domain"), "distribution")
        test_name = _text(row.get("test_name"), "distribution test")
        severity = (
            "high" if jsd is not None and jsd >= 0.50 else "moderate"
        )
        message = (
            f"The code-frequency distribution for {domain} is discordant "
            "between simulators."
        )
        evidence_parts = []
        if jsd is not None:
            evidence_parts.append(f"Jensen–Shannon divergence={jsd:.3f}")
        p_value = _safe_float(row.get("p_value"))
        if p_value is not None:
            evidence_parts.append(f"p={_format_probability(p_value)}")
        evidence = "; ".join(evidence_parts) or "Distributional discordance recorded."

        findings.append(
            ModuleFinding(
                severity,
                "code_distribution",
                domain,
                message,
                evidence + ".",
                f"Review shared and simulator-specific codes in {domain}.",
            )
        )
        rows.append(
            _finding_row(
                severity=severity,
                category="code_distribution",
                endpoint=domain,
                finding=message,
                test_name=test_name,
                p_value=p_value,
            )
        )

    return findings


# =============================================================================
# Decisions and conclusions
# =============================================================================


def _module_decision(
    comparison: ModuleStatisticalComparisonResult,
) -> str:
    summary = _first_row(comparison.summary)
    if _safe_bool(summary.get("skipped")):
        return _DECISION_SKIPPED
    if not _safe_bool(summary.get("valid_for_statistical_comparison")):
        return _DECISION_FAIL

    blocking = _functional_blocking_count(comparison)
    significant_fdr = _safe_int(summary.get("significant_after_fdr_count"))
    significant = _safe_int(summary.get("significant_test_count"))

    if blocking > 0 or significant_fdr > 0:
        return _DECISION_FAIL
    if significant > 0 or _functional_warning_count(comparison) > 0:
        return _DECISION_WARNING
    return _DECISION_PASS


def _overall_decision(modules: Sequence[ModuleReport]) -> str:
    if not modules:
        return _DECISION_SKIPPED
    decisions = {module.decision for module in modules}
    if _DECISION_FAIL in decisions:
        return _DECISION_FAIL
    if _DECISION_WARNING in decisions:
        return _DECISION_WARNING
    if decisions == {_DECISION_SKIPPED}:
        return _DECISION_SKIPPED
    return _DECISION_PASS


def _module_notes(
    comparison: ModuleStatisticalComparisonResult,
    decision: str,
    findings: Sequence[ModuleFinding],
) -> list[str]:
    summary = _first_row(comparison.summary)
    if decision == _DECISION_SKIPPED:
        return [
            str(
                summary.get("skip_reason")
                or "Statistical comparison was skipped because its prerequisites were not met."
            )
        ]

    notes: list[str] = []
    fdr_count = _safe_int(summary.get("significant_after_fdr_count"))
    nominal_count = _safe_int(summary.get("significant_test_count"))

    if fdr_count:
        notes.append(
            f"{fdr_count} prevalence comparison(s) remained significant after FDR correction."
        )
    elif nominal_count:
        notes.append(
            f"{nominal_count} unadjusted test(s) were nominally significant, but no prevalence comparison remained significant after FDR correction."
        )

    severity_counts = _finding_severity_counts(findings)
    for severity in ("critical", "high", "moderate"):
        count = severity_counts.get(severity, 0)
        if count:
            notes.append(
                f"The evidence-derived assessment contains {count} {severity} finding(s)."
            )

    if not notes:
        notes.append(
            "No material divergence was identified by the configured functional and statistical comparisons."
        )
    return notes


def _module_conclusion(
    comparison: ModuleStatisticalComparisonResult,
    *,
    decision: str,
    findings: Sequence[ModuleFinding],
) -> str:
    module = comparison.module_name
    if decision == _DECISION_SKIPPED:
        reason = _first_row(comparison.summary).get("skip_reason")
        return (
            f"No conclusion can be drawn for {module} because the statistical "
            f"comparison was skipped{': ' + str(reason) if reason else '.'}"
        )
    if decision == _DECISION_PASS:
        return (
            f"No material functional or statistical discordance was detected "
            f"for {module} under the evaluated cohort and seed. This supports "
            "compatibility for this run, not universal equivalence across seeds, "
            "populations or versions."
        )

    principal = [
        finding
        for finding in findings
        if finding.severity in {"critical", "high"}
    ][:3]
    if not principal:
        principal = list(findings[:3])
    endpoints = ", ".join(finding.endpoint for finding in principal)
    qualifier = "material" if decision == _DECISION_FAIL else "potential"
    return (
        f"{module} shows {qualifier} discordance between Synthea and Psynthea"
        + (f", principally affecting {endpoints}" if endpoints else "")
        + ". Equivalence is not demonstrated for this run; the identified "
        "endpoints require correction or replication before research use."
    )


def _validation_conclusion(
    modules: Sequence[ModuleReport],
    overall_decision: str,
) -> str:
    if not modules:
        return "No module comparisons were available; no scientific conclusion can be drawn."

    names = ", ".join(module.module_name for module in modules)
    failed = [module.module_name for module in modules if module.decision == _DECISION_FAIL]
    warned = [module.module_name for module in modules if module.decision == _DECISION_WARNING]

    if overall_decision == _DECISION_FAIL:
        return (
            f"Equivalence was not demonstrated for {', '.join(failed)}. "
            f"The report evaluated {names} using their own persisted functional "
            "and statistical evidence; failed modules should not be treated as "
            "research-equivalent until discrepancies are resolved and replicated."
        )
    if overall_decision == _DECISION_WARNING:
        return (
            f"No FDR-confirmed failure was identified, but {', '.join(warned)} "
            "contains unresolved nominal or functional warnings. Additional "
            "seed-level replication is required before asserting equivalence."
        )
    if overall_decision == _DECISION_PASS:
        return (
            f"The evaluated evidence did not identify material discordance in {names}. "
            "This conclusion is restricted to the configured cohort, seed and software versions."
        )
    return "All configured module comparisons were skipped; equivalence was not evaluated."


# =============================================================================
# Markdown rendering
# =============================================================================


def _module_markdown_sections(module: ModuleReport) -> list[str]:
    findings_table = module.findings_table
    if findings_table is None:
        findings_table = pd.DataFrame(columns=_FINDING_COLUMNS)

    sections = [
        "",
        f"## Module: {module.module_name}",
        "",
        f"Decision: **{module.decision.upper()}**",
        "",
        module.conclusion,
        "",
        "### Summary",
        "",
        _markdown_table(module.summary),
        "",
        "### Evidence-derived findings",
        "",
        _markdown_table(findings_table),
        "",
        "### Interpretation notes",
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

    if module.findings:
        sections.extend(["", "### Prioritised actions", ""])
        for index, finding in enumerate(module.findings, start=1):
            sections.extend(
                [
                    f"{index}. **{finding.endpoint} — {finding.severity.upper()}**",
                    f"   - Finding: {finding.finding}",
                    f"   - Evidence: {finding.evidence}",
                    f"   - Action: {finding.recommendation}",
                ]
            )
    return sections


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows available._"
    display = frame.copy().map(_format_value)
    return display.to_markdown(index=False)


def _markdown_list(values: Sequence[str]) -> list[str]:
    return [f"- {value}" for value in values] if values else ["- No notes."]


# =============================================================================
# Statistical-table adapters
# =============================================================================


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

    significant["domain_or_metric"] = significant.get(
        label_column,
        pd.Series(index=significant.index, dtype="object"),
    )
    significant["adjusted_p_value"] = pd.NA
    significant["significant_after_fdr"] = pd.NA
    significant["effect_size_type"] = significant.get(
        "test_name",
        pd.Series(index=significant.index, dtype="object"),
    ).map(_effect_size_type)
    return _ensure_columns(significant, _SIGNIFICANT_TEST_COLUMNS)


def _significant_prevalence_tests(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "significant_after_fdr" not in frame.columns:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    significant = frame[frame["significant_after_fdr"].fillna(False)].copy()
    if significant.empty:
        return pd.DataFrame(columns=_SIGNIFICANT_TEST_COLUMNS)

    significant["domain_or_metric"] = (
        significant.get("domain", "").astype(str)
        + ":"
        + significant.get("code", "").astype(str)
    )
    significant["effect_size"] = significant.get("risk_ratio")
    significant["effect_size_type"] = "risk_ratio"
    return _ensure_columns(significant, _SIGNIFICANT_TEST_COLUMNS)


# =============================================================================
# Generic helpers
# =============================================================================


def _first_row(frame: pd.DataFrame) -> dict[str, Any]:
    return {} if frame.empty else frame.iloc[0].to_dict()


def _total_test_count(row: Mapping[str, Any]) -> int:
    return sum(
        _safe_int(row.get(column))
        for column in (
            "continuous_test_count",
            "categorical_test_count",
            "prevalence_test_count",
            "distribution_test_count",
        )
    )


def _functional_blocking_count(
    comparison: ModuleStatisticalComparisonResult,
) -> int:
    summary = getattr(comparison.validation, "summary", pd.DataFrame())
    return _safe_int(_first_row(summary).get("blocking_issue_count"))


def _functional_warning_count(
    comparison: ModuleStatisticalComparisonResult,
) -> int:
    summary = getattr(comparison.validation, "summary", pd.DataFrame())
    return _safe_int(_first_row(summary).get("warning_count"))


def _strongest_test(frame: pd.DataFrame) -> Mapping[str, Any]:
    ranked = frame.copy()
    ranked["_p"] = _numeric_series(ranked, "p_value").fillna(float("inf"))
    ranked["_effect"] = _numeric_series(ranked, "effect_size").abs().fillna(-1.0)
    return (
        ranked.sort_values(
            ["_p", "_effect", "test_name"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .iloc[0]
        .to_dict()
    )


def _effect_size_type(test_name: Any) -> str | None:
    normalized = str(test_name or "").strip().lower()
    if "kolmogorov" in normalized or normalized in {"ks", "ks_test"}:
        return "ks_statistic"
    if "mann" in normalized or "whitney" in normalized:
        return "rank_biserial_correlation"
    if "welch" in normalized or "t_test" in normalized or "t-test" in normalized:
        return "standardized_mean_difference"
    if "chi" in normalized:
        return "cramers_v"
    if "proportion" in normalized:
        return "risk_ratio"
    return None


def _effect_severity(effect: float | None, test_name: str) -> str:
    if effect is None:
        return "moderate"
    magnitude = abs(effect)
    kind = _effect_size_type(test_name)
    if kind == "ks_statistic":
        return "high" if magnitude >= 0.30 else "moderate"
    if kind in {"standardized_mean_difference", "rank_biserial_correlation"}:
        return "high" if magnitude >= 0.50 else "moderate"
    if kind == "cramers_v":
        return "high" if magnitude >= 0.30 else "moderate"
    return "high" if magnitude >= 0.50 else "moderate"


def _test_evidence(
    *,
    test_name: str,
    statistic: float | None,
    p_value: float | None,
    effect_size: float | None,
    effect_size_type: str | None,
    n_synthea: int,
    n_psynthea: int,
) -> str:
    parts = [f"test={test_name}"]
    if statistic is not None:
        parts.append(f"statistic={statistic:.4g}")
    if p_value is not None:
        parts.append(f"p={_format_probability(p_value)}")
    if effect_size is not None and effect_size_type != "ks_statistic":
        label = effect_size_type or "effect_size"
        parts.append(f"{label}={effect_size:.4g}")
    if n_synthea or n_psynthea:
        parts.append(f"n={n_synthea}/{n_psynthea}")
    return "; ".join(parts) + "."


def _prevalence_message(
    endpoint: str,
    synthea: float | None,
    psynthea: float | None,
    absolute: float | None,
) -> str:
    if synthea is None or psynthea is None:
        return f"Prevalence differs significantly for {endpoint} after FDR correction."
    difference = absolute if absolute is not None else psynthea - synthea
    direction = "higher" if difference > 0 else "lower"
    return (
        f"Psynthea prevalence for {endpoint} is {direction} than Synthea "
        f"({psynthea:.1%} vs {synthea:.1%}; difference {difference:+.1%})."
    )


def _prevalence_evidence(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    risk_ratio = _safe_float(row.get("risk_ratio"))
    rr_low = _safe_float(row.get("risk_ratio_ci_lower"))
    rr_high = _safe_float(row.get("risk_ratio_ci_upper"))
    odds_ratio = _safe_float(row.get("odds_ratio"))
    adjusted = _safe_float(row.get("adjusted_p_value"))

    if risk_ratio is not None:
        item = f"risk ratio={risk_ratio:.3g}"
        if rr_low is not None and rr_high is not None:
            item += f" (95% CI {rr_low:.3g}–{rr_high:.3g})"
        parts.append(item)
    elif odds_ratio is not None:
        parts.append(f"odds ratio={odds_ratio:.3g}")
    if adjusted is not None:
        parts.append(f"FDR-adjusted p={_format_probability(adjusted)}")
    return "; ".join(parts) + "."


def _finding_row(**values: Any) -> dict[str, Any]:
    return {column: values.get(column) for column in _FINDING_COLUMNS}


def _deduplicate_findings(
    findings: Sequence[ModuleFinding],
) -> list[ModuleFinding]:
    result: list[ModuleFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding.category, finding.endpoint, finding.finding)
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return result


def _finding_severity_counts(
    findings: Sequence[ModuleFinding],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def _ensure_columns(
    frame: pd.DataFrame,
    columns: Sequence[str],
) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result[list(columns)]


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        if pd.isna(value):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip()
    return normalized or fallback


def _normalize_severity(value: Any) -> str:
    normalized = _text(value, "moderate").lower()
    aliases = {
        "blocking": "critical",
        "error": "high",
        "warning": "moderate",
        "info": "informational",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _SEVERITY_ORDER else "moderate"


def _format_probability(value: float) -> str:
    return f"{value:.2e}" if value < 0.001 else f"{value:.4f}"


def _format_value(value: object) -> object:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        if 0 < abs(value) < 0.001:
            return f"{value:.2e}"
        return f"{value:.4f}"
    return value