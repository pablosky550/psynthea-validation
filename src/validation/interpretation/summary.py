"""Conservative synthesis of interpretation-engine executions.

The summary layer turns a complete :class:`EngineExecution` into a compact,
machine-readable overview suitable for report rendering and run-to-run review.
It never reinterprets raw evidence, recomputes statistics or invents a composite
validation score.

Scientific safety rules
-----------------------

* A failed, blocked or insufficiently evaluated rule is never hidden by passes.
* ``research_use_ready`` requires complete execution and no blocking findings.
* Dimensions are summarized from rule evaluations, not inferred from names.
* Severity and scientific status remain separate concepts.
* Priority findings are selected deterministically and remain traceable to the
  original :class:`InterpretationFinding` objects.
* No weighted average or opaque overall grade is produced.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from validation.interpretation.engine import EngineExecution
from validation.interpretation.models import (
    FindingStatus,
    InterpretationFinding,
    RecommendationPriority,
    Severity,
)
from validation.interpretation.rules.base import (
    RuleEvaluation,
    RuleExecutionStatus,
    ValidationDimension,
)

__all__ = [
    "DimensionSummary",
    "InterpretationSummary",
    "SummaryConfiguration",
    "build_interpretation_summary",
]


_STATUS_PRECEDENCE: Final = {
    FindingStatus.FAIL: 0,
    FindingStatus.INCONCLUSIVE: 1,
    FindingStatus.WARNING: 2,
    FindingStatus.PASS: 3,
    FindingStatus.NOT_EVALUATED: 4,
    FindingStatus.NOT_APPLICABLE: 5,
}

_SEVERITY_PRECEDENCE: Final = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MODERATE: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

_INCOMPLETE_EXECUTION_STATUSES: Final = frozenset(
    {
        RuleExecutionStatus.INSUFFICIENT_EVIDENCE,
        RuleExecutionStatus.BLOCKED_DEPENDENCY,
        RuleExecutionStatus.NOT_EVALUATED,
    }
)


def _freeze_mapping(value: Mapping[str, int]) -> Mapping[str, int]:
    return MappingProxyType(dict(value))


def _status_counts(findings: Sequence[InterpretationFinding]) -> Mapping[str, int]:
    counts = {status.value: 0 for status in FindingStatus}
    for finding in findings:
        counts[finding.status.value] += 1
    return _freeze_mapping(counts)


def _severity_counts(findings: Sequence[InterpretationFinding]) -> Mapping[str, int]:
    counts = {severity.value: 0 for severity in Severity}
    for finding in findings:
        counts[finding.severity.value] += 1
    return _freeze_mapping(counts)


def _execution_counts(evaluations: Sequence[RuleEvaluation]) -> Mapping[str, int]:
    counts = {status.value: 0 for status in RuleExecutionStatus}
    for evaluation in evaluations:
        counts[evaluation.status.value] += 1
    return _freeze_mapping(counts)


def _recommendation_counts(
    findings: Sequence[InterpretationFinding],
) -> Mapping[str, int]:
    counts = {priority.value: 0 for priority in RecommendationPriority}
    for finding in findings:
        for recommendation in finding.recommendations:
            counts[recommendation.priority.value] += 1
    return _freeze_mapping(counts)


def _maximum_severity(findings: Sequence[InterpretationFinding]) -> Severity:
    if not findings:
        return Severity.INFO
    return min(
        (finding.severity for finding in findings),
        key=_SEVERITY_PRECEDENCE.__getitem__,
    )


def _dimension_status(
    evaluations: Sequence[RuleEvaluation],
    findings: Sequence[InterpretationFinding],
) -> FindingStatus:
    statuses = {finding.status for finding in findings}
    if FindingStatus.FAIL in statuses:
        return FindingStatus.FAIL

    if any(item.status in _INCOMPLETE_EXECUTION_STATUSES for item in evaluations):
        return FindingStatus.INCONCLUSIVE

    if FindingStatus.INCONCLUSIVE in statuses:
        return FindingStatus.INCONCLUSIVE
    if FindingStatus.WARNING in statuses:
        return FindingStatus.WARNING
    if FindingStatus.PASS in statuses:
        return FindingStatus.PASS

    if evaluations and all(
        item.status is RuleExecutionStatus.NOT_APPLICABLE for item in evaluations
    ):
        return FindingStatus.NOT_APPLICABLE

    return FindingStatus.NOT_EVALUATED


def _overall_status(
    evaluations: Sequence[RuleEvaluation],
    findings: Sequence[InterpretationFinding],
) -> FindingStatus:
    """Return a conservative execution-level scientific status.

    ``InterpretationReport.overall_status`` only aggregates findings and cannot
    account for rules that never produced findings because they were blocked,
    skipped or lacked evidence.  The summary therefore derives its own status
    from both evaluations and findings.
    """

    statuses = {finding.status for finding in findings}
    if FindingStatus.FAIL in statuses:
        return FindingStatus.FAIL
    if any(item.status in _INCOMPLETE_EXECUTION_STATUSES for item in evaluations):
        return FindingStatus.INCONCLUSIVE
    if FindingStatus.INCONCLUSIVE in statuses:
        return FindingStatus.INCONCLUSIVE
    if FindingStatus.WARNING in statuses:
        return FindingStatus.WARNING
    if FindingStatus.PASS in statuses:
        return FindingStatus.PASS
    if evaluations and all(
        item.status is RuleExecutionStatus.NOT_APPLICABLE for item in evaluations
    ):
        return FindingStatus.NOT_APPLICABLE
    return FindingStatus.NOT_EVALUATED


def _priority_key(finding: InterpretationFinding) -> tuple[int, int, int, str]:
    return (
        0 if finding.blocks_research_use else 1,
        _STATUS_PRECEDENCE[finding.status],
        _SEVERITY_PRECEDENCE[finding.severity],
        finding.finding_id,
    )


@dataclass(frozen=True, slots=True)
class SummaryConfiguration:
    """Deterministic presentation policy for one summary build."""

    maximum_priority_findings: int = 10
    include_pass_findings_in_priority: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_priority_findings, bool)
            or not isinstance(self.maximum_priority_findings, int)
        ):
            raise TypeError("maximum_priority_findings must be an integer.")
        if self.maximum_priority_findings < 0:
            raise ValueError("maximum_priority_findings must be non-negative.")
        if not isinstance(self.include_pass_findings_in_priority, bool):
            raise TypeError("include_pass_findings_in_priority must be a bool.")


@dataclass(frozen=True, slots=True)
class DimensionSummary:
    """Auditable summary of all rules belonging to one validation dimension."""

    dimension: ValidationDimension
    status: FindingStatus
    maximum_severity: Severity
    rule_count: int
    finding_count: int
    blocking_finding_count: int
    incomplete_rule_count: int
    research_use_ready: bool
    execution_status_counts: Mapping[str, int]
    finding_status_counts: Mapping[str, int]
    severity_counts: Mapping[str, int]
    recommendation_priority_counts: Mapping[str, int]
    rule_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, ValidationDimension):
            raise TypeError("dimension must be a ValidationDimension member.")
        if not isinstance(self.status, FindingStatus):
            raise TypeError("status must be a FindingStatus member.")
        if not isinstance(self.maximum_severity, Severity):
            raise TypeError("maximum_severity must be a Severity member.")
        for field_name in (
            "rule_count",
            "finding_count",
            "blocking_finding_count",
            "incomplete_rule_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        if not isinstance(self.research_use_ready, bool):
            raise TypeError("research_use_ready must be a bool.")

        rule_ids = tuple(self.rule_ids)
        finding_ids = tuple(self.finding_ids)
        if len(rule_ids) != self.rule_count:
            raise ValueError("rule_count must equal the number of rule_ids.")
        if len(finding_ids) != self.finding_count:
            raise ValueError("finding_count must equal the number of finding_ids.")
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule_ids must be unique within a dimension.")
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding_ids must be unique within a dimension.")
        object.__setattr__(self, "rule_ids", rule_ids)
        object.__setattr__(self, "finding_ids", finding_ids)

        for field_name in (
            "execution_status_counts",
            "finding_status_counts",
            "severity_counts",
            "recommendation_priority_counts",
        ):
            mapping = getattr(self, field_name)
            if not isinstance(mapping, Mapping):
                raise TypeError(f"{field_name} must be a mapping.")
            object.__setattr__(self, field_name, _freeze_mapping(mapping))

        expected_ready = (
            self.rule_count > 0
            and self.incomplete_rule_count == 0
            and self.blocking_finding_count == 0
            and self.status
            not in {
                FindingStatus.FAIL,
                FindingStatus.INCONCLUSIVE,
                FindingStatus.NOT_EVALUATED,
            }
        )
        if self.research_use_ready is not expected_ready:
            raise ValueError(
                "research_use_ready is inconsistent with dimension execution and findings."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "status": self.status.value,
            "maximum_severity": self.maximum_severity.value,
            "rule_count": self.rule_count,
            "finding_count": self.finding_count,
            "blocking_finding_count": self.blocking_finding_count,
            "incomplete_rule_count": self.incomplete_rule_count,
            "research_use_ready": self.research_use_ready,
            "execution_status_counts": dict(self.execution_status_counts),
            "finding_status_counts": dict(self.finding_status_counts),
            "severity_counts": dict(self.severity_counts),
            "recommendation_priority_counts": dict(
                self.recommendation_priority_counts
            ),
            "rule_ids": list(self.rule_ids),
            "finding_ids": list(self.finding_ids),
        }


@dataclass(frozen=True, slots=True)
class InterpretationSummary:
    """Compact, lossless overview derived from one engine execution."""

    report_id: str
    pipeline_run_id: str
    module_name: str | None
    overall_status: FindingStatus
    maximum_severity: Severity
    research_use_ready: bool
    rule_count: int
    finding_count: int
    evidence_count: int
    blocking_finding_count: int
    incomplete_rule_count: int
    execution_status_counts: Mapping[str, int]
    finding_status_counts: Mapping[str, int]
    severity_counts: Mapping[str, int]
    recommendation_priority_counts: Mapping[str, int]
    dimensions: tuple[DimensionSummary, ...]
    priority_findings: tuple[InterpretationFinding, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.overall_status, FindingStatus):
            raise TypeError("overall_status must be a FindingStatus member.")
        if not isinstance(self.maximum_severity, Severity):
            raise TypeError("maximum_severity must be a Severity member.")
        if not isinstance(self.research_use_ready, bool):
            raise TypeError("research_use_ready must be a bool.")
        for field_name in (
            "rule_count",
            "finding_count",
            "evidence_count",
            "blocking_finding_count",
            "incomplete_rule_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")

        dimensions = tuple(self.dimensions)
        if not all(isinstance(item, DimensionSummary) for item in dimensions):
            raise TypeError("dimensions must contain DimensionSummary values only.")
        dimension_names = [item.dimension for item in dimensions]
        if len(dimension_names) != len(set(dimension_names)):
            raise ValueError("dimensions must not contain duplicate validation dimensions.")
        object.__setattr__(self, "dimensions", dimensions)

        priority_findings = tuple(self.priority_findings)
        if not all(isinstance(item, InterpretationFinding) for item in priority_findings):
            raise TypeError(
                "priority_findings must contain InterpretationFinding values only."
            )
        priority_ids = [item.finding_id for item in priority_findings]
        if len(priority_ids) != len(set(priority_ids)):
            raise ValueError("priority_findings must not contain duplicates.")
        object.__setattr__(self, "priority_findings", priority_findings)

        limitations = tuple(self.limitations)
        if not all(isinstance(item, str) and item.strip() for item in limitations):
            raise TypeError("limitations must contain non-empty strings only.")
        normalized_limitations = tuple(
            dict.fromkeys(item.strip() for item in limitations)
        )
        object.__setattr__(self, "limitations", normalized_limitations)

        for field_name in (
            "execution_status_counts",
            "finding_status_counts",
            "severity_counts",
            "recommendation_priority_counts",
        ):
            mapping = getattr(self, field_name)
            if not isinstance(mapping, Mapping):
                raise TypeError(f"{field_name} must be a mapping.")
            object.__setattr__(self, field_name, _freeze_mapping(mapping))

        if tuple(item.dimension for item in dimensions) != tuple(
            sorted((item.dimension for item in dimensions), key=list(ValidationDimension).index)
        ):
            raise ValueError("dimensions must follow ValidationDimension declaration order.")

        dimension_statuses = {item.status for item in dimensions}
        if FindingStatus.FAIL in dimension_statuses:
            expected_overall_status = FindingStatus.FAIL
        elif FindingStatus.INCONCLUSIVE in dimension_statuses:
            expected_overall_status = FindingStatus.INCONCLUSIVE
        elif FindingStatus.WARNING in dimension_statuses:
            expected_overall_status = FindingStatus.WARNING
        elif FindingStatus.PASS in dimension_statuses:
            expected_overall_status = FindingStatus.PASS
        elif dimensions and dimension_statuses == {FindingStatus.NOT_APPLICABLE}:
            expected_overall_status = FindingStatus.NOT_APPLICABLE
        else:
            expected_overall_status = FindingStatus.NOT_EVALUATED
        if self.overall_status is not expected_overall_status:
            raise ValueError(
                "overall_status is inconsistent with dimension-level scientific status."
            )

        if self.rule_count != sum(item.rule_count for item in dimensions):
            raise ValueError("rule_count must equal the sum of dimension rule counts.")
        if self.finding_count != sum(item.finding_count for item in dimensions):
            raise ValueError("finding_count must equal the sum of dimension finding counts.")
        if self.blocking_finding_count != sum(
            item.blocking_finding_count for item in dimensions
        ):
            raise ValueError(
                "blocking_finding_count must equal the sum of dimension blocking counts."
            )
        if self.incomplete_rule_count != sum(
            item.incomplete_rule_count for item in dimensions
        ):
            raise ValueError(
                "incomplete_rule_count must equal the sum of dimension incomplete counts."
            )
        if sum(self.execution_status_counts.values()) != self.rule_count:
            raise ValueError("execution_status_counts must sum to rule_count.")
        if sum(self.finding_status_counts.values()) != self.finding_count:
            raise ValueError("finding_status_counts must sum to finding_count.")
        if sum(self.severity_counts.values()) != self.finding_count:
            raise ValueError("severity_counts must sum to finding_count.")

        all_finding_ids = {
            finding_id for item in dimensions for finding_id in item.finding_ids
        }
        if not set(priority_ids).issubset(all_finding_ids):
            raise ValueError("priority_findings must reference findings present in dimensions.")

        expected_ready = (
            self.finding_count > 0
            and self.incomplete_rule_count == 0
            and self.blocking_finding_count == 0
            and self.overall_status
            not in {
                FindingStatus.FAIL,
                FindingStatus.INCONCLUSIVE,
                FindingStatus.NOT_EVALUATED,
            }
        )
        if self.research_use_ready is not expected_ready:
            raise ValueError(
                "research_use_ready is inconsistent with execution completeness and findings."
            )

    def dimension(self, dimension: ValidationDimension) -> DimensionSummary | None:
        if not isinstance(dimension, ValidationDimension):
            raise TypeError("dimension must be a ValidationDimension member.")
        return next((item for item in self.dimensions if item.dimension is dimension), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "pipeline_run_id": self.pipeline_run_id,
            "module_name": self.module_name,
            "overall_status": self.overall_status.value,
            "maximum_severity": self.maximum_severity.value,
            "research_use_ready": self.research_use_ready,
            "rule_count": self.rule_count,
            "finding_count": self.finding_count,
            "evidence_count": self.evidence_count,
            "blocking_finding_count": self.blocking_finding_count,
            "incomplete_rule_count": self.incomplete_rule_count,
            "execution_status_counts": dict(self.execution_status_counts),
            "finding_status_counts": dict(self.finding_status_counts),
            "severity_counts": dict(self.severity_counts),
            "recommendation_priority_counts": dict(
                self.recommendation_priority_counts
            ),
            "dimensions": [item.to_dict() for item in self.dimensions],
            "priority_findings": [item.to_dict() for item in self.priority_findings],
            "limitations": list(self.limitations),
        }


def _build_dimension_summary(
    dimension: ValidationDimension,
    evaluations: Sequence[RuleEvaluation],
) -> DimensionSummary:
    ordered_evaluations = tuple(evaluations)
    findings = tuple(
        finding for evaluation in ordered_evaluations for finding in evaluation.findings
    )
    status = _dimension_status(ordered_evaluations, findings)
    incomplete_count = sum(
        item.status in _INCOMPLETE_EXECUTION_STATUSES for item in ordered_evaluations
    )
    blocking_count = sum(item.blocks_research_use for item in findings)
    ready = (
        bool(ordered_evaluations)
        and incomplete_count == 0
        and blocking_count == 0
        and status
        not in {
            FindingStatus.FAIL,
            FindingStatus.INCONCLUSIVE,
            FindingStatus.NOT_EVALUATED,
        }
    )

    return DimensionSummary(
        dimension=dimension,
        status=status,
        maximum_severity=_maximum_severity(findings),
        rule_count=len(ordered_evaluations),
        finding_count=len(findings),
        blocking_finding_count=blocking_count,
        incomplete_rule_count=incomplete_count,
        research_use_ready=ready,
        execution_status_counts=_execution_counts(ordered_evaluations),
        finding_status_counts=_status_counts(findings),
        severity_counts=_severity_counts(findings),
        recommendation_priority_counts=_recommendation_counts(findings),
        rule_ids=tuple(item.rule_id for item in ordered_evaluations),
        finding_ids=tuple(item.finding_id for item in findings),
    )


def build_interpretation_summary(
    execution: EngineExecution,
    *,
    configuration: SummaryConfiguration | None = None,
) -> InterpretationSummary:
    """Build a deterministic conservative summary from one engine execution."""

    if not isinstance(execution, EngineExecution):
        raise TypeError("execution must be an EngineExecution.")
    configuration = configuration or SummaryConfiguration()
    if not isinstance(configuration, SummaryConfiguration):
        raise TypeError("configuration must be a SummaryConfiguration or None.")

    by_dimension: dict[ValidationDimension, list[RuleEvaluation]] = defaultdict(list)
    for evaluation in execution.evaluations:
        by_dimension[evaluation.dimension].append(evaluation)

    dimension_summaries = tuple(
        _build_dimension_summary(dimension, by_dimension[dimension])
        for dimension in ValidationDimension
        if dimension in by_dimension
    )

    findings = execution.report.findings
    priority_statuses = {
        FindingStatus.FAIL,
        FindingStatus.INCONCLUSIVE,
        FindingStatus.WARNING,
    }
    if configuration.include_pass_findings_in_priority:
        priority_statuses.add(FindingStatus.PASS)
    candidates = tuple(
        finding for finding in findings if finding.status in priority_statuses
    )
    priority_findings = tuple(
        sorted(candidates, key=_priority_key)[
            : configuration.maximum_priority_findings
        ]
    )

    limitations: list[str] = []
    if execution.incomplete_evaluations:
        limitations.append(
            f"{len(execution.incomplete_evaluations)} rule(s) did not complete with an "
            "evaluated or explicitly non-applicable result."
        )
    if not findings:
        limitations.append("The execution produced no scientific findings.")
    if execution.report.blocking_findings:
        limitations.append(
            f"{len(execution.report.blocking_findings)} finding(s) explicitly block "
            "downstream research use."
        )
    if any(
        item.status is FindingStatus.INCONCLUSIVE for item in dimension_summaries
    ):
        limitations.append(
            "At least one validation dimension remains inconclusive."
        )

    return InterpretationSummary(
        report_id=execution.report.report_id,
        pipeline_run_id=execution.report.pipeline_run_id,
        module_name=execution.report.module_name,
        overall_status=_overall_status(execution.evaluations, findings),
        maximum_severity=_maximum_severity(findings),
        research_use_ready=execution.research_use_ready,
        rule_count=len(execution.evaluations),
        finding_count=len(findings),
        evidence_count=len(execution.report.evidence),
        blocking_finding_count=len(execution.report.blocking_findings),
        incomplete_rule_count=len(execution.incomplete_evaluations),
        execution_status_counts=_execution_counts(execution.evaluations),
        finding_status_counts=_status_counts(findings),
        severity_counts=_severity_counts(findings),
        recommendation_priority_counts=_recommendation_counts(findings),
        dimensions=dimension_summaries,
        priority_findings=priority_findings,
        limitations=tuple(limitations),
    )