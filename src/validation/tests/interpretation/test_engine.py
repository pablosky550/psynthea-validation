from __future__ import annotations

from datetime import UTC, datetime

import pytest

from validation.interpretation.engine import (
    DEFAULT_INTERPRETATION_RULES,
    ENGINE_VERSION,
    EngineConfigurationError,
    InterpretationEngine,
    InterpretationEngineConfig,
)
from validation.interpretation.evidence import EvidenceCatalog
from validation.interpretation.models import (
    Confidence,
    EvidenceAvailability,
    EvidenceReference,
    EvidenceRole,
    EvidenceStrength,
    EvidenceValue,
    FindingStatus,
    InterpretationFinding,
    Severity,
)
from validation.interpretation.rules.base import (
    DerivedEvidence,
    Inference,
    InterpretationRule,
    PipelineStage,
    RuleContext,
    RuleDependency,
    RuleExecutionError,
    RuleExecutionStatus,
    RuleOutcome,
    StageStatus,
    ValidationDimension,
)


def metric(metric_id: str, value: object) -> EvidenceValue:
    return EvidenceValue(
        metric_id=metric_id,
        name=metric_id,
        availability=EvidenceAvailability.AVAILABLE,
        value=value,
        source="test",
    )


def finding(rule: InterpretationRule, metric_id: str, suffix: str = "PASS") -> InterpretationFinding:
    return InterpretationFinding(
        finding_id=f"{rule.rule_id}.{suffix}",
        rule_id=rule.rule_id,
        domain=rule.domain,
        title=f"{rule.rule_id} finding",
        status=FindingStatus.PASS,
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        evidence_strength=EvidenceStrength.STRONG,
        observation="Observed evidence is available.",
        interpretation="The test rule completed deterministically.",
        impact="No research-use restriction is introduced.",
        evidence=(EvidenceReference(metric_id, EvidenceRole.PRIMARY),),
        confidence_score=0.9,
    )


class ProducerRule(InterpretationRule):
    rule_id = "TEST.PRODUCER"
    domain = "test"
    description = "Produce derived evidence."
    dimension = ValidationDimension.STRUCTURAL
    required_stages = (PipelineStage.INGESTION,)

    def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
        source = context.evidence.require("input.value")
        derived = EvidenceValue(
            metric_id="derived.double",
            name="Double input",
            availability=EvidenceAvailability.AVAILABLE,
            value=int(source.value) * 2,
            source=self.rule_id,
        )
        return RuleOutcome(
            findings=(finding(self, source.metric_id),),
            inferences=(
                Inference(
                    inference_id="TEST.PRODUCER.INFERENCE",
                    statement="A deterministic derived metric was calculated.",
                    evidence=(EvidenceReference(source.metric_id),),
                    rationale="The value is input multiplied by two.",
                    confidence=1.0,
                ),
            ),
            derived_evidence=(
                DerivedEvidence(
                    value=derived,
                    formula="input.value * 2",
                    source_metric_ids=(source.metric_id,),
                ),
            ),
        )


class ConsumerRule(InterpretationRule):
    rule_id = "TEST.CONSUMER"
    domain = "test"
    description = "Consume derived evidence."
    dimension = ValidationDimension.STATISTICAL
    dependencies = (RuleDependency("TEST.PRODUCER"),)

    def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
        derived = context.evidence.require("derived.double")
        assert derived.value == 6
        assert context.prior_evaluations["TEST.PRODUCER"].status is RuleExecutionStatus.COMPLETED
        return RuleOutcome(findings=(finding(self, derived.metric_id),))


class IndependentRule(InterpretationRule):
    rule_id = "TEST.INDEPENDENT"
    domain = "test"
    description = "Independent rule."
    dimension = ValidationDimension.CLINICAL

    def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
        return RuleOutcome(findings=(finding(self, "input.value"),))


def config(**kwargs: object) -> InterpretationEngineConfig:
    defaults = {
        "validation_id": "validation-001",
        "pipeline_run_id": "run-001",
        "module_name": "hypertension",
        "stages": {PipelineStage.INGESTION: StageStatus.COMPLETED},
        "metadata": {"seed": 42},
    }
    defaults.update(kwargs)
    return InterpretationEngineConfig(**defaults)


def test_engine_orders_dependencies_stably_and_propagates_derived_evidence() -> None:
    engine = InterpretationEngine((ConsumerRule(), IndependentRule(), ProducerRule()))

    execution = engine.execute(EvidenceCatalog((metric("input.value", 3),)), config=config())

    assert execution.execution_order == (
        "TEST.INDEPENDENT",
        "TEST.PRODUCER",
        "TEST.CONSUMER",
    )
    assert tuple(item.rule_id for item in execution.evaluations) == execution.execution_order
    assert execution.report.evidence_by_id()["derived.double"].value == 6
    assert [item.finding_id for item in execution.report.findings] == [
        "TEST.INDEPENDENT.PASS",
        "TEST.PRODUCER.PASS",
        "TEST.CONSUMER.PASS",
    ]


def test_run_returns_report_with_complete_audit_metadata() -> None:
    engine = InterpretationEngine((ProducerRule(), ConsumerRule()))

    report = engine.run(EvidenceCatalog((metric("input.value", 3),)), config=config())

    assert report.report_id == "validation-001.interpretation"
    assert report.pipeline_run_id == "run-001"
    assert report.module_name == "hypertension"
    assert report.engine_version == ENGINE_VERSION
    assert report.metadata["seed"] == 42
    assert report.metadata["engine"]["execution_order"] == (
        "TEST.PRODUCER",
        "TEST.CONSUMER",
    )
    assert len(report.metadata["rule_evaluations"]) == 2
    assert report.overall_status is FindingStatus.PASS
    assert report.research_use_allowed is True


def test_engine_retains_non_completed_evaluations_without_fabricating_findings() -> None:
    engine = InterpretationEngine((ProducerRule(), ConsumerRule()))
    cfg = config(stages={PipelineStage.INGESTION: StageStatus.NOT_RUN})

    execution = engine.execute(EvidenceCatalog((metric("input.value", 3),)), config=cfg)

    assert execution.evaluation("TEST.PRODUCER").status is RuleExecutionStatus.NOT_EVALUATED
    assert execution.evaluation("TEST.CONSUMER").status is RuleExecutionStatus.BLOCKED_DEPENDENCY
    assert execution.report.findings == ()
    assert execution.report.evidence == (metric("input.value", 3),)
    assert execution.report.overall_status is FindingStatus.NOT_APPLICABLE


def test_engine_rejects_duplicate_rule_identifiers() -> None:
    with pytest.raises(EngineConfigurationError, match="Duplicate rule identifiers"):
        InterpretationEngine((ProducerRule(), ProducerRule()))


def test_engine_rejects_absent_required_dependencies() -> None:
    with pytest.raises(EngineConfigurationError, match="Required rule dependencies are absent"):
        InterpretationEngine((ConsumerRule(),))


def test_engine_rejects_dependency_cycles() -> None:
    class RuleA(InterpretationRule):
        rule_id = "TEST.A"
        domain = "test"
        description = "A"
        dimension = ValidationDimension.STRUCTURAL
        dependencies = (RuleDependency("TEST.B"),)

        def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
            return RuleOutcome(findings=(finding(self, "input.value"),))

    class RuleB(InterpretationRule):
        rule_id = "TEST.B"
        domain = "test"
        description = "B"
        dimension = ValidationDimension.STRUCTURAL
        dependencies = (RuleDependency("TEST.A"),)

        def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
            return RuleOutcome(findings=(finding(self, "input.value"),))

    with pytest.raises(EngineConfigurationError, match="contains a cycle"):
        InterpretationEngine((RuleA(), RuleB()))


def test_engine_never_converts_rule_implementation_errors_into_findings() -> None:
    class BrokenRule(InterpretationRule):
        rule_id = "TEST.BROKEN"
        domain = "test"
        description = "Broken implementation."
        dimension = ValidationDimension.STRUCTURAL

        def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
            raise RuntimeError("implementation defect")

    engine = InterpretationEngine((BrokenRule(),))
    with pytest.raises(RuleExecutionError, match="implementation defect"):
        engine.run(EvidenceCatalog((metric("input.value", 3),)), config=config())


def test_engine_rejects_derived_metric_collision_across_rules() -> None:
    class SecondProducerRule(InterpretationRule):
        rule_id = "TEST.SECOND_PRODUCER"
        domain = "test"
        description = "Colliding derived evidence."
        dimension = ValidationDimension.STRUCTURAL
        dependencies = (RuleDependency("TEST.PRODUCER"),)

        def interpret(self, context: RuleContext, evidence: dict[str, EvidenceValue]) -> RuleOutcome:
            duplicate = EvidenceValue(
                metric_id="derived.double",
                name="Collision",
                availability=EvidenceAvailability.AVAILABLE,
                value=999,
            )
            return RuleOutcome(
                findings=(finding(self, "input.value"),),
                derived_evidence=(
                    DerivedEvidence(
                        value=duplicate,
                        formula="collision",
                        source_metric_ids=("input.value",),
                    ),
                ),
            )

    engine = InterpretationEngine((ProducerRule(), SecondProducerRule()))
    with pytest.raises(Exception, match="overwrite existing evidence metrics|Duplicate evidence"):
        engine.run(EvidenceCatalog((metric("input.value", 3),)), config=config())


def test_engine_config_validates_identifiers_stages_and_metadata() -> None:
    with pytest.raises(ValueError, match="pipeline_run_id"):
        config(pipeline_run_id="bad id")
    with pytest.raises(TypeError, match="stages keys"):
        config(stages={"ingestion": StageStatus.COMPLETED})
    with pytest.raises(TypeError, match="metadata"):
        config(metadata=[("seed", 42)])


def test_default_registry_contains_every_completed_rule_family_and_is_constructible() -> None:
    engine = InterpretationEngine()
    rule_ids = set(engine.execution_order)

    assert len(DEFAULT_INTERPRETATION_RULES) == 15
    assert len(rule_ids) == 15
    assert "STRUCT.EVIDENCE_INTEGRITY" in rule_ids
    assert "STAT.READINESS" in rule_ids
    assert "CLINICAL.SIGNAL_PRESERVATION" in rule_ids
    assert "SPANISH.EVIDENCE_INTEGRITY" in rule_ids


def test_execution_object_exposes_duration_and_safe_lookup() -> None:
    engine = InterpretationEngine((IndependentRule(),))
    execution = engine.execute(EvidenceCatalog((metric("input.value", 3),)), config=config())

    assert execution.duration_seconds >= 0.0
    assert execution.evaluation("TEST.INDEPENDENT") is execution.evaluations[0]
    assert execution.evaluation("TEST.UNKNOWN") is None
    assert execution.started_at.tzinfo is UTC
    assert execution.completed_at.tzinfo is UTC