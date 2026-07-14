"""Tests for conservative interpretation execution summaries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from validation.interpretation.engine import EngineExecution
from validation.interpretation.models import (
    Confidence,
    EvidenceAvailability,
    EvidenceReference,
    EvidenceRole,
    EvidenceStrength,
    EvidenceValue,
    FindingStatus,
    InterpretationFinding,
    InterpretationReport,
    Recommendation,
    RecommendationPriority,
    Severity,
)
from validation.interpretation.rules.base import (
    ApplicabilityDecision,
    RuleEvaluation,
    RuleExecutionStatus,
    ValidationDimension,
)
from validation.interpretation.summary import (
    SummaryConfiguration,
    build_interpretation_summary,
)

NOW = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)


def _evidence(metric_id: str = "metric.one") -> EvidenceValue:
    return EvidenceValue(
        metric_id=metric_id,
        name=metric_id,
        availability=EvidenceAvailability.AVAILABLE,
        value=1,
    )


def _finding(
    finding_id: str,
    *,
    rule_id: str,
    status: FindingStatus,
    severity: Severity,
    blocks: bool = False,
    recommendation_priority: RecommendationPriority | None = None,
) -> InterpretationFinding:
    recommendations = ()
    if recommendation_priority is not None:
        recommendations = (
            Recommendation(
                recommendation_id=f"{finding_id}.REC",
                action="Review the affected validation output.",
                priority=recommendation_priority,
                rationale="The finding requires a traceable corrective action.",
                expected_outcome="The affected validation output is resolved.",
                verification="Re-run the validation and confirm resolution.",
                blocking=blocks,
            ),
        )
    return InterpretationFinding(
        finding_id=finding_id,
        rule_id=rule_id,
        domain="test",
        title=finding_id,
        status=status,
        severity=severity,
        confidence=Confidence.HIGH,
        evidence_strength=(
            EvidenceStrength.STRONG
            if status not in {FindingStatus.INCONCLUSIVE}
            else EvidenceStrength.INSUFFICIENT
        ),
        observation="Observed validation evidence.",
        interpretation="Deterministic interpretation of the evidence.",
        impact="Potential impact on validation use.",
        evidence=(
            EvidenceReference(metric_id="metric.one", role=EvidenceRole.PRIMARY),
        ),
        recommendations=recommendations,
        blocks_research_use=blocks,
        created_at=NOW,
    )


def _evaluation(
    rule_id: str,
    dimension: ValidationDimension,
    *,
    status: RuleExecutionStatus = RuleExecutionStatus.COMPLETED,
    findings: tuple[InterpretationFinding, ...] = (),
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule_id,
        dimension=dimension,
        status=status,
        findings=findings,
        inferences=(),
        derived_evidence=(),
        requirements=(),
        dependencies=(),
        stages=(),
        applicability=(
            ApplicabilityDecision.not_applicable("Not applicable to this module.")
            if status is RuleExecutionStatus.NOT_APPLICABLE
            else ApplicabilityDecision.applicable()
        ),
        started_at=NOW,
        completed_at=NOW,
    )


def _execution(evaluations: tuple[RuleEvaluation, ...]) -> EngineExecution:
    findings = tuple(
        finding for evaluation in evaluations for finding in evaluation.findings
    )
    report = InterpretationReport(
        report_id="report.one",
        pipeline_run_id="run.one",
        module_name="hypertension",
        findings=findings,
        evidence=(_evidence(),),
        generated_at=NOW,
    )
    return EngineExecution(
        report=report,
        evaluations=evaluations,
        execution_order=tuple(item.rule_id for item in evaluations),
        started_at=NOW,
        completed_at=NOW,
    )


def test_summary_configuration_rejects_invalid_limits() -> None:
    with pytest.raises(TypeError):
        SummaryConfiguration(maximum_priority_findings=True)
    with pytest.raises(ValueError):
        SummaryConfiguration(maximum_priority_findings=-1)


def test_builds_dimension_summaries_in_enum_order() -> None:
    structural = _evaluation(
        "STRUCT.ONE",
        ValidationDimension.STRUCTURAL,
        findings=(
            _finding(
                "F.STRUCT",
                rule_id="STRUCT.ONE",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
        ),
    )
    statistical = _evaluation(
        "STAT.ONE",
        ValidationDimension.STATISTICAL,
        findings=(
            _finding(
                "F.STAT",
                rule_id="STAT.ONE",
                status=FindingStatus.WARNING,
                severity=Severity.MODERATE,
            ),
        ),
    )

    summary = build_interpretation_summary(_execution((statistical, structural)))

    assert [item.dimension for item in summary.dimensions] == [
        ValidationDimension.STRUCTURAL,
        ValidationDimension.STATISTICAL,
    ]
    assert summary.dimension(ValidationDimension.STRUCTURAL).status is FindingStatus.PASS
    assert summary.dimension(ValidationDimension.STATISTICAL).status is FindingStatus.WARNING


def test_fail_takes_precedence_within_dimension() -> None:
    evaluation = _evaluation(
        "CLIN.ONE",
        ValidationDimension.CLINICAL,
        findings=(
            _finding(
                "F.PASS",
                rule_id="CLIN.ONE",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
            _finding(
                "F.FAIL",
                rule_id="CLIN.ONE",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                blocks=True,
            ),
        ),
    )

    dimension = build_interpretation_summary(_execution((evaluation,))).dimensions[0]

    assert dimension.status is FindingStatus.FAIL
    assert dimension.maximum_severity is Severity.HIGH
    assert dimension.blocking_finding_count == 1
    assert not dimension.research_use_ready


def test_incomplete_rule_makes_dimension_inconclusive() -> None:
    completed = _evaluation(
        "STAT.PASS",
        ValidationDimension.STATISTICAL,
        findings=(
            _finding(
                "F.PASS",
                rule_id="STAT.PASS",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
        ),
    )
    incomplete = _evaluation(
        "STAT.MISSING",
        ValidationDimension.STATISTICAL,
        status=RuleExecutionStatus.INSUFFICIENT_EVIDENCE,
    )

    dimension = build_interpretation_summary(
        _execution((completed, incomplete))
    ).dimensions[0]

    assert dimension.status is FindingStatus.INCONCLUSIVE
    assert dimension.incomplete_rule_count == 1
    assert not dimension.research_use_ready


def test_all_non_applicable_rules_produce_not_applicable_dimension() -> None:
    evaluation = _evaluation(
        "SNS.NA",
        ValidationDimension.SPANISH_ADAPTATION,
        status=RuleExecutionStatus.NOT_APPLICABLE,
    )

    dimension = build_interpretation_summary(_execution((evaluation,))).dimensions[0]

    assert dimension.status is FindingStatus.NOT_APPLICABLE
    assert dimension.research_use_ready


def test_priority_findings_are_deterministic_and_blockers_first() -> None:
    evaluation = _evaluation(
        "CLIN.PRIORITY",
        ValidationDimension.CLINICAL,
        findings=(
            _finding(
                "F.WARNING",
                rule_id="CLIN.PRIORITY",
                status=FindingStatus.WARNING,
                severity=Severity.MODERATE,
            ),
            _finding(
                "F.FAIL.NONBLOCK",
                rule_id="CLIN.PRIORITY",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
            ),
            _finding(
                "F.BLOCK",
                rule_id="CLIN.PRIORITY",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                blocks=True,
            ),
            _finding(
                "F.PASS",
                rule_id="CLIN.PRIORITY",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
        ),
    )

    summary = build_interpretation_summary(
        _execution((evaluation,)),
        configuration=SummaryConfiguration(maximum_priority_findings=2),
    )

    assert [item.finding_id for item in summary.priority_findings] == [
        "F.BLOCK",
        "F.FAIL.NONBLOCK",
    ]


def test_pass_findings_can_be_included_explicitly() -> None:
    evaluation = _evaluation(
        "STRUCT.PASS",
        ValidationDimension.STRUCTURAL,
        findings=(
            _finding(
                "F.PASS",
                rule_id="STRUCT.PASS",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
        ),
    )

    default_summary = build_interpretation_summary(_execution((evaluation,)))
    configured = build_interpretation_summary(
        _execution((evaluation,)),
        configuration=SummaryConfiguration(include_pass_findings_in_priority=True),
    )

    assert default_summary.priority_findings == ()
    assert configured.priority_findings[0].finding_id == "F.PASS"


def test_recommendation_counts_preserve_priority_levels() -> None:
    evaluation = _evaluation(
        "STRUCT.REC",
        ValidationDimension.STRUCTURAL,
        findings=(
            _finding(
                "F.REC",
                rule_id="STRUCT.REC",
                status=FindingStatus.FAIL,
                severity=Severity.CRITICAL,
                blocks=True,
                recommendation_priority=RecommendationPriority.URGENT,
            ),
        ),
    )

    summary = build_interpretation_summary(_execution((evaluation,)))

    assert summary.recommendation_priority_counts["urgent"] == 1
    assert summary.dimensions[0].recommendation_priority_counts["urgent"] == 1


def test_summary_reports_execution_limitations() -> None:
    incomplete = _evaluation(
        "STAT.BLOCKED",
        ValidationDimension.STATISTICAL,
        status=RuleExecutionStatus.BLOCKED_DEPENDENCY,
    )

    summary = build_interpretation_summary(_execution((incomplete,)))

    assert summary.incomplete_rule_count == 1
    assert not summary.research_use_ready
    assert any("did not complete" in item for item in summary.limitations)
    assert any("inconclusive" in item for item in summary.limitations)


def test_blocking_findings_are_reflected_in_global_summary() -> None:
    evaluation = _evaluation(
        "STRUCT.FAIL",
        ValidationDimension.STRUCTURAL,
        findings=(
            _finding(
                "F.BLOCK",
                rule_id="STRUCT.FAIL",
                status=FindingStatus.FAIL,
                severity=Severity.CRITICAL,
                blocks=True,
            ),
        ),
    )

    summary = build_interpretation_summary(_execution((evaluation,)))

    assert summary.overall_status is FindingStatus.FAIL
    assert summary.maximum_severity is Severity.CRITICAL
    assert summary.blocking_finding_count == 1
    assert not summary.research_use_ready
    assert any("block" in item for item in summary.limitations)


def test_to_dict_is_stable_and_serializable() -> None:
    evaluation = _evaluation(
        "STRUCT.ONE",
        ValidationDimension.STRUCTURAL,
        findings=(
            _finding(
                "F.ONE",
                rule_id="STRUCT.ONE",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
        ),
    )

    payload = build_interpretation_summary(_execution((evaluation,))).to_dict()

    assert payload["report_id"] == "report.one"
    assert payload["overall_status"] == "pass"
    assert payload["dimensions"][0]["dimension"] == "structural"
    assert isinstance(payload["finding_status_counts"], dict)


def test_summary_rejects_non_execution_input() -> None:
    with pytest.raises(TypeError):
        build_interpretation_summary(object())