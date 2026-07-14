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
    RootCauseHypothesis,
    Severity,
)
from validation.interpretation.recommendations import (
    ActionPlanConfiguration,
    RecommendationPlan,
    build_recommendation_plan,
)
from validation.interpretation.rules.base import (
    ApplicabilityDecision,
    PipelineStage,
    RuleEvaluation,
    RuleExecutionStatus,
    StageAssessment,
    StageStatus,
    ValidationDimension,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def evidence() -> EvidenceValue:
    return EvidenceValue(
        metric_id="metric.one",
        name="Metric one",
        availability=EvidenceAvailability.AVAILABLE,
        value=1,
    )


def recommendation(
    recommendation_id: str,
    *,
    action: str = "Regenerate the affected outputs.",
    priority: RecommendationPriority = RecommendationPriority.HIGH,
    blocking: bool = False,
    owner: str | None = None,
    rationale: str = "The outputs are incomplete.",
    related_hypothesis_ids: tuple[str, ...] = (),
) -> Recommendation:
    return Recommendation(
        recommendation_id=recommendation_id,
        action=action,
        priority=priority,
        rationale=rationale,
        expected_outcome="Comparable outputs are available.",
        verification="Re-run validation and confirm the issue is resolved.",
        owner=owner,
        blocking=blocking,
        related_hypothesis_ids=related_hypothesis_ids,
    )


def finding(
    finding_id: str,
    *,
    rule_id: str,
    recommendations: tuple[Recommendation, ...] = (),
    status: FindingStatus = FindingStatus.WARNING,
    severity: Severity = Severity.MODERATE,
    hypotheses: tuple[RootCauseHypothesis, ...] = (),
    blocks_research_use: bool | None = None,
) -> InterpretationFinding:
    return InterpretationFinding(
        finding_id=finding_id,
        rule_id=rule_id,
        domain="structural",
        title=f"Finding {finding_id}",
        status=status,
        severity=severity,
        confidence=Confidence.HIGH,
        evidence_strength=EvidenceStrength.STRONG,
        observation="An issue was observed.",
        interpretation="The issue requires review.",
        impact="Validation may be affected.",
        evidence=(EvidenceReference("metric.one", EvidenceRole.PRIMARY),),
        recommendations=recommendations,
        hypotheses=hypotheses,
        blocks_research_use=(
            any(item.blocking for item in recommendations)
            if blocks_research_use is None
            else blocks_research_use
        ),
    )


def evaluation(
    rule_id: str,
    findings: tuple[InterpretationFinding, ...] = (),
    *,
    status: RuleExecutionStatus = RuleExecutionStatus.COMPLETED,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule_id,
        dimension=ValidationDimension.STRUCTURAL,
        status=status,
        findings=findings,
        inferences=(),
        derived_evidence=(),
        requirements=(),
        dependencies=(),
        stages=(
            StageAssessment(
                PipelineStage.INGESTION,
                StageStatus.COMPLETED,
                "Ingestion completed.",
            ),
        ),
        applicability=ApplicabilityDecision.applicable(),
        started_at=NOW,
        completed_at=NOW,
        notes=(),
    )


def execution(*evaluations: RuleEvaluation) -> EngineExecution:
    findings = tuple(item for ev in evaluations for item in ev.findings)
    report = InterpretationReport(
        report_id="validation.interpretation",
        pipeline_run_id="run-001",
        findings=findings,
        evidence=(evidence(),),
        generated_at=NOW,
        module_name="hypertension",
        metadata={"engine": {"registry_fingerprint": "abc123"}},
    )
    return EngineExecution(
        report=report,
        evaluations=tuple(evaluations),
        execution_order=tuple(ev.rule_id for ev in evaluations),
        started_at=NOW,
        completed_at=NOW,
    )


def test_configuration_rejects_invalid_maximum() -> None:
    with pytest.raises(ValueError):
        ActionPlanConfiguration(maximum_items=0)
    with pytest.raises(TypeError):
        ActionPlanConfiguration(maximum_items=True)


def test_builds_one_item_per_distinct_action() -> None:
    first = finding("F.1", rule_id="RULE.1", recommendations=(recommendation("R.1"),))
    second = finding(
        "F.2",
        rule_id="RULE.2",
        recommendations=(recommendation("R.2", action="Inspect mappings."),),
    )
    plan = build_recommendation_plan(execution(evaluation("RULE.1", (first,)), evaluation("RULE.2", (second,))))
    assert len(plan.items) == 2
    assert plan.source_recommendation_count == 2


def test_consolidates_only_case_and_whitespace_equivalent_actions() -> None:
    first = finding(
        "F.1",
        rule_id="RULE.1",
        recommendations=(recommendation("R.1", action="Regenerate   the affected outputs."),),
    )
    second = finding(
        "F.2",
        rule_id="RULE.2",
        recommendations=(recommendation("R.2", action="  regenerate the affected outputs. "),),
    )
    plan = build_recommendation_plan(execution(evaluation("RULE.1", (first,)), evaluation("RULE.2", (second,))))
    assert len(plan.items) == 1
    assert set(plan.items[0].source_recommendation_ids) == {"R.1", "R.2"}


def test_does_not_merge_differently_worded_actions() -> None:
    first = finding("F.1", rule_id="RULE.1", recommendations=(recommendation("R.1", action="Regenerate outputs."),))
    second = finding("F.2", rule_id="RULE.2", recommendations=(recommendation("R.2", action="Regenerate and inspect outputs."),))
    plan = build_recommendation_plan(execution(evaluation("RULE.1", (first,)), evaluation("RULE.2", (second,))))
    assert len(plan.items) == 2


def test_priority_and_blocking_only_escalate() -> None:
    low = recommendation("R.1", priority=RecommendationPriority.LOW, blocking=False)
    urgent = recommendation("R.2", priority=RecommendationPriority.URGENT, blocking=True)
    plan = build_recommendation_plan(
        execution(
            evaluation("RULE.1", (finding("F.1", rule_id="RULE.1", recommendations=(low,)),)),
            evaluation("RULE.2", (finding("F.2", rule_id="RULE.2", recommendations=(urgent,), status=FindingStatus.FAIL, severity=Severity.CRITICAL),)),
        )
    )
    item = plan.items[0]
    assert item.priority is RecommendationPriority.URGENT
    assert item.blocking is True


def test_owner_conflicts_are_preserved() -> None:
    first = recommendation("R.1", owner="Data Engineering")
    second = recommendation("R.2", owner="Clinical Validation")
    plan = build_recommendation_plan(
        execution(
            evaluation("RULE.1", (finding("F.1", rule_id="RULE.1", recommendations=(first,)),)),
            evaluation("RULE.2", (finding("F.2", rule_id="RULE.2", recommendations=(second,)),)),
        )
    )
    assert plan.items[0].has_owner_conflict
    assert plan.owner_conflicts == (plan.items[0],)


def test_incomplete_rule_generates_blocking_review_action() -> None:
    plan = build_recommendation_plan(
        execution(evaluation("RULE.INCOMPLETE", status=RuleExecutionStatus.INSUFFICIENT_EVIDENCE))
    )
    assert len(plan.items) == 1
    assert plan.items[0].blocking
    assert plan.items[0].incomplete_rule_ids == ("RULE.INCOMPLETE",)
    assert plan.incomplete_rule_count == 1


def test_incomplete_rule_actions_can_be_disabled() -> None:
    plan = build_recommendation_plan(
        execution(evaluation("RULE.INCOMPLETE", status=RuleExecutionStatus.NOT_EVALUATED)),
        configuration=ActionPlanConfiguration(include_incomplete_rule_actions=False),
    )
    assert plan.items == ()
    assert plan.incomplete_rule_count == 1


def test_filters_low_priority_and_non_blocking_items() -> None:
    low = finding(
        "F.LOW",
        rule_id="RULE.LOW",
        recommendations=(recommendation("R.LOW", priority=RecommendationPriority.LOW),),
    )
    high = finding(
        "F.HIGH",
        rule_id="RULE.HIGH",
        recommendations=(recommendation("R.HIGH", action="Resolve blocker.", blocking=True),),
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
    )
    plan = build_recommendation_plan(
        execution(evaluation("RULE.LOW", (low,)), evaluation("RULE.HIGH", (high,))),
        configuration=ActionPlanConfiguration(include_low_priority=False, include_non_blocking=False),
    )
    assert [item.action for item in plan.items] == ["Resolve blocker."]


def test_maximum_items_applies_after_priority_sorting() -> None:
    low = finding("F.L", rule_id="RULE.L", recommendations=(recommendation("R.L", action="Low action.", priority=RecommendationPriority.LOW),))
    urgent = finding("F.U", rule_id="RULE.U", recommendations=(recommendation("R.U", action="Urgent action.", priority=RecommendationPriority.URGENT, blocking=True),), status=FindingStatus.FAIL, severity=Severity.CRITICAL)
    plan = build_recommendation_plan(
        execution(evaluation("RULE.L", (low,)), evaluation("RULE.U", (urgent,))),
        configuration=ActionPlanConfiguration(maximum_items=1),
    )
    assert len(plan.items) == 1
    assert plan.items[0].action == "Urgent action."


def test_plan_order_is_deterministic() -> None:
    a = finding("F.A", rule_id="RULE.A", recommendations=(recommendation("R.A", action="Action A."),))
    b = finding("F.B", rule_id="RULE.B", recommendations=(recommendation("R.B", action="Action B."),))
    first = build_recommendation_plan(execution(evaluation("RULE.A", (a,)), evaluation("RULE.B", (b,))))
    second = build_recommendation_plan(execution(evaluation("RULE.B", (b,)), evaluation("RULE.A", (a,))))
    assert [item.action for item in first.items] == [item.action for item in second.items]


def test_fingerprint_is_stable() -> None:
    item = finding("F.1", rule_id="RULE.1", recommendations=(recommendation("R.1"),))
    plan = build_recommendation_plan(execution(evaluation("RULE.1", (item,))))
    assert plan.fingerprint == plan.fingerprint
    assert plan.to_dict()["fingerprint"] == plan.fingerprint


def test_metadata_is_frozen_and_reserved_keys_rejected() -> None:
    nested = {"tags": ["a"]}
    plan = build_recommendation_plan(execution(), metadata=nested)
    nested["tags"].append("b")
    assert plan.metadata["tags"] == ("a",)
    with pytest.raises(ValueError):
        build_recommendation_plan(execution(), metadata={"source_report_id": "x"})


def test_priority_counts_and_blocking_items_are_consistent() -> None:
    urgent = finding("F.U", rule_id="RULE.U", recommendations=(recommendation("R.U", priority=RecommendationPriority.URGENT, blocking=True),), status=FindingStatus.FAIL, severity=Severity.CRITICAL)
    plan = build_recommendation_plan(execution(evaluation("RULE.U", (urgent,))))
    assert plan.priority_counts["urgent"] == 1
    assert len(plan.blocking_items) == 1
    assert plan.to_dict()["blocking_item_count"] == 1


def test_rejects_non_execution_input() -> None:
    with pytest.raises(TypeError):
        build_recommendation_plan(object())  # type: ignore[arg-type]



def test_blocking_finding_escalates_non_blocking_recommendation() -> None:
    rec = recommendation(
        "R.BLOCK",
        priority=RecommendationPriority.LOW,
        blocking=False,
    )
    source = finding(
        "F.BLOCK",
        rule_id="RULE.BLOCK",
        recommendations=(rec,),
        status=FindingStatus.FAIL,
        severity=Severity.CRITICAL,
        blocks_research_use=True,
    )
    plan = build_recommendation_plan(execution(evaluation("RULE.BLOCK", (source,))))
    assert plan.items[0].blocking is True
    assert plan.items[0].priority is RecommendationPriority.HIGH
    assert plan.items[0].metadata["source_blocks_research_use"] is True


def test_duplicate_recommendation_identifiers_are_rejected_globally() -> None:
    first = finding(
        "F.1",
        rule_id="RULE.1",
        recommendations=(recommendation("R.DUP"),),
    )
    second = finding(
        "F.2",
        rule_id="RULE.2",
        recommendations=(recommendation("R.DUP", action="Inspect mappings."),),
    )
    with pytest.raises(ValueError, match="global provenance"):
        build_recommendation_plan(
            execution(evaluation("RULE.1", (first,)), evaluation("RULE.2", (second,)))
        )


def test_related_hypothesis_identifiers_are_qualified_by_finding() -> None:
    hypothesis_one = RootCauseHypothesis(
        hypothesis_id="H.1",
        statement="First possible cause.",
        plausibility=Confidence.MODERATE,
        rationale="Supported by the first finding.",
    )
    hypothesis_two = RootCauseHypothesis(
        hypothesis_id="H.1",
        statement="Second possible cause.",
        plausibility=Confidence.MODERATE,
        rationale="Supported by the second finding.",
    )
    first = finding(
        "F.1",
        rule_id="RULE.1",
        recommendations=(recommendation("R.1", related_hypothesis_ids=("H.1",)),),
        hypotheses=(hypothesis_one,),
    )
    second = finding(
        "F.2",
        rule_id="RULE.2",
        recommendations=(recommendation("R.2", related_hypothesis_ids=("H.1",)),),
        hypotheses=(hypothesis_two,),
    )
    plan = build_recommendation_plan(
        execution(evaluation("RULE.1", (first,)), evaluation("RULE.2", (second,)))
    )
    assert plan.items[0].related_hypothesis_ids == ("F.1:H.1", "F.2:H.1")


def test_plan_reports_actions_omitted_by_maximum_items() -> None:
    first = finding(
        "F.1",
        rule_id="RULE.1",
        recommendations=(recommendation("R.1", action="First action."),),
    )
    second = finding(
        "F.2",
        rule_id="RULE.2",
        recommendations=(recommendation("R.2", action="Second action."),),
    )
    plan = build_recommendation_plan(
        execution(evaluation("RULE.1", (first,)), evaluation("RULE.2", (second,))),
        configuration=ActionPlanConfiguration(maximum_items=1),
    )
    assert plan.candidate_item_count == 2
    assert plan.omitted_item_count == 1
    assert plan.to_dict()["has_omitted_actions"] is True


def test_plan_count_invariants_are_enforced() -> None:
    with pytest.raises(ValueError, match="omitted_item_count"):
        RecommendationPlan(
            report_id="report",
            pipeline_run_id="run",
            module_name="module",
            items=(),
            source_recommendation_count=0,
            candidate_item_count=1,
            omitted_item_count=0,
            incomplete_rule_count=0,
            configuration=ActionPlanConfiguration(),
        )