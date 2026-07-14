from __future__ import annotations

from datetime import UTC, datetime
from typing import Mapping

import pytest

from validation.interpretation.evidence import EvidenceCatalog, extract_scalar
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
    ApplicabilityDecision,
    DependencyPolicy,
    DerivedEvidence,
    EvidenceRequirement,
    Inference,
    PipelineStage,
    RuleContext,
    RuleDependency,
    RuleExecutionStatus,
    RuleInvariantError,
    RuleOutcome,
    StageStatus,
    StatisticalRule,
    StructuralRule,
    ValidationDimension,
)


def _finding(*, rule_id: str, metric_id: str, domain: str = "observations") -> InterpretationFinding:
    return InterpretationFinding(
        finding_id=f"{rule_id}.001",
        rule_id=rule_id,
        domain=domain,
        title="Observation coverage",
        status=FindingStatus.WARNING,
        severity=Severity.MODERATE,
        confidence=Confidence.HIGH,
        evidence_strength=EvidenceStrength.STRONG,
        observation="Psynthea generated zero observation rows.",
        interpretation="Observation coverage differs between implementations.",
        impact="Functional equivalence cannot be confirmed for observations.",
        evidence=(EvidenceReference(metric_id=metric_id, role=EvidenceRole.PRIMARY, rationale="Direct evidence."),),
    )


def _context(
    *values: EvidenceValue,
    stages: Mapping[PipelineStage, StageStatus] | None = None,
    prior_evaluations=None,
) -> RuleContext:
    return RuleContext(
        validation_id="run-001",
        module_name="hypertension",
        evidence=EvidenceCatalog(tuple(values)),
        evaluated_at=datetime(2026, 7, 13, 10, 0, tzinfo=UTC),
        stages=stages or {},
        prior_evaluations=prior_evaluations or {},
    )


class ObservationCoverageRule(StructuralRule):
    rule_id = "OBS.COVERAGE"
    domain = "observations"
    description = "Interpret observation coverage."
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    requirements = (EvidenceRequirement("obs.count"),)

    def interpret(self, context: RuleContext, evidence: Mapping[str, EvidenceValue]) -> RuleOutcome:
        reference = EvidenceReference(metric_id="obs.count", role=EvidenceRole.PRIMARY, rationale="Observed count.")
        return RuleOutcome(
            findings=(_finding(rule_id=self.rule_id, metric_id="obs.count"),),
            inferences=(
                Inference(
                    inference_id="OBS.COVERAGE.ZERO",
                    statement="No observation rows were generated.",
                    evidence=(reference,),
                    rationale="The normalized count is exactly zero.",
                    confidence=1.0,
                ),
            ),
        )


class RelativeDifferenceRule(StatisticalRule):
    rule_id = "OBS.RELATIVE_DIFFERENCE"
    domain = "observations"
    description = "Derive and interpret the relative count difference."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    dependencies = (
        RuleDependency(
            "OBS.COVERAGE",
            policy=DependencyPolicy.REQUIRE_FINDINGS,
            rationale="Coverage must be assessed first.",
        ),
    )
    requirements = (
        EvidenceRequirement("synthea.obs.count"),
        EvidenceRequirement("psynthea.obs.count"),
    )

    def interpret(self, context: RuleContext, evidence: Mapping[str, EvidenceValue]) -> RuleOutcome:
        synthea = int(evidence["synthea.obs.count"].value)
        psynthea = int(evidence["psynthea.obs.count"].value)
        relative = (psynthea - synthea) / synthea
        derived = EvidenceValue(
            metric_id="derived.obs.relative_difference",
            name="Observation relative difference",
            availability=EvidenceAvailability.AVAILABLE,
            value=relative,
            unit="ratio",
            source=self.rule_id,
        )
        return RuleOutcome(
            findings=(_finding(rule_id=self.rule_id, metric_id=derived.metric_id),),
            derived_evidence=(
                DerivedEvidence(
                    value=derived,
                    formula="(psynthea - synthea) / synthea",
                    source_metric_ids=("synthea.obs.count", "psynthea.obs.count"),
                ),
            ),
        )


def test_dimension_is_inherited_from_specialized_rule_base() -> None:
    assert ObservationCoverageRule.dimension is ValidationDimension.STRUCTURAL
    assert RelativeDifferenceRule.dimension is ValidationDimension.STATISTICAL


def test_required_pipeline_stage_not_run_yields_not_evaluated() -> None:
    count = extract_scalar(0, metric_id="obs.count", name="Observation count")

    evaluation = ObservationCoverageRule().run(_context(count))

    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.findings == ()
    assert evaluation.stages[0].status is StageStatus.NOT_RUN


def test_completed_stage_allows_rule_execution_with_inference() -> None:
    count = extract_scalar(0, metric_id="obs.count", name="Observation count")

    evaluation = ObservationCoverageRule().run(
        _context(count, stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED})
    )

    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert evaluation.inferences[0].inference_id == "OBS.COVERAGE.ZERO"
    assert evaluation.findings[0].status is FindingStatus.WARNING


def test_missing_required_evidence_is_inconclusive_at_execution_level() -> None:
    evaluation = ObservationCoverageRule().run(
        _context(stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED})
    )

    assert evaluation.status is RuleExecutionStatus.INSUFFICIENT_EVIDENCE
    assert evaluation.findings == ()
    assert evaluation.requirements[0].satisfied is False


def test_required_dependency_blocks_downstream_rule() -> None:
    synthea = extract_scalar(10, metric_id="synthea.obs.count", name="Synthea count")
    psynthea = extract_scalar(0, metric_id="psynthea.obs.count", name="Psynthea count")

    evaluation = RelativeDifferenceRule().run(
        _context(
            synthea,
            psynthea,
            stages={PipelineStage.STATISTICAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    assert evaluation.status is RuleExecutionStatus.BLOCKED_DEPENDENCY
    assert evaluation.dependencies[0].satisfied is False


def test_satisfied_dependency_allows_derived_evidence() -> None:
    coverage_count = extract_scalar(0, metric_id="obs.count", name="Observation count")
    coverage_eval = ObservationCoverageRule().run(
        _context(
            coverage_count,
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )
    synthea = extract_scalar(10, metric_id="synthea.obs.count", name="Synthea count")
    psynthea = extract_scalar(0, metric_id="psynthea.obs.count", name="Psynthea count")

    evaluation = RelativeDifferenceRule().run(
        _context(
            synthea,
            psynthea,
            stages={PipelineStage.STATISTICAL_VALIDATION: StageStatus.COMPLETED},
            prior_evaluations={coverage_eval.rule_id: coverage_eval},
        )
    )

    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert evaluation.derived_evidence[0].value.value == -1.0
    assert evaluation.findings[0].evidence[0].metric_id == "derived.obs.relative_difference"


def test_derived_evidence_cannot_overwrite_input_metric() -> None:
    class OverwriteRule(StructuralRule):
        rule_id = "TEST.OVERWRITE"
        domain = "observations"
        description = "Invalid derived evidence overwrite."
        requirements = (EvidenceRequirement("obs.count"),)

        def interpret(self, context, evidence):
            derived = EvidenceValue(
                metric_id="obs.count",
                name="Overwrite",
                availability=EvidenceAvailability.AVAILABLE,
                value=1,
            )
            return RuleOutcome(
                findings=(_finding(rule_id=self.rule_id, metric_id="obs.count"),),
                derived_evidence=(DerivedEvidence(derived, "1", ("obs.count",)),),
            )

    count = extract_scalar(0, metric_id="obs.count", name="Observation count")
    with pytest.raises(RuleInvariantError, match="must not overwrite"):
        OverwriteRule().run(_context(count))


def test_inference_cannot_reference_unknown_metric() -> None:
    class UnknownInferenceRule(StructuralRule):
        rule_id = "TEST.UNKNOWN_INFERENCE"
        domain = "observations"
        description = "Invalid inference evidence."
        requirements = (EvidenceRequirement("obs.count"),)

        def interpret(self, context, evidence):
            return RuleOutcome(
                findings=(_finding(rule_id=self.rule_id, metric_id="obs.count"),),
                inferences=(
                    Inference(
                        inference_id="TEST.UNKNOWN",
                        statement="Unknown evidence was used.",
                        evidence=(EvidenceReference("missing.metric", EvidenceRole.PRIMARY, "Missing."),),
                        rationale="Invalid test inference.",
                    ),
                ),
            )

    count = extract_scalar(0, metric_id="obs.count", name="Observation count")
    with pytest.raises(RuleInvariantError, match="Inference references unknown"):
        UnknownInferenceRule().run(_context(count))


def test_applicability_remains_separate_from_evidence_and_dependencies() -> None:
    class NotApplicableRule(ObservationCoverageRule):
        rule_id = "OBS.COVERAGE.NA"

        def applicability(self, context, evidence):
            return ApplicabilityDecision.not_applicable("Module has no observation states.")

    count = extract_scalar(0, metric_id="obs.count", name="Observation count")
    evaluation = NotApplicableRule().run(
        _context(count, stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED})
    )

    assert evaluation.status is RuleExecutionStatus.NOT_APPLICABLE
    assert evaluation.applicability.reason == "Module has no observation states."


def test_rule_cannot_depend_on_itself() -> None:
    with pytest.raises(ValueError, match="cannot depend on itself"):

        class RecursiveRule(StructuralRule):
            rule_id = "TEST.RECURSIVE"
            domain = "test"
            description = "Invalid recursive dependency."
            dependencies = (RuleDependency("TEST.RECURSIVE"),)

            def interpret(self, context, evidence):
                raise AssertionError


def test_serialization_includes_dimension_stages_dependencies_and_inferences() -> None:
    count = extract_scalar(0, metric_id="obs.count", name="Observation count")
    evaluation = ObservationCoverageRule().run(
        _context(count, stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED})
    )

    payload = evaluation.to_dict()

    assert payload["dimension"] == "structural"
    assert payload["stages"][0]["stage"] == "functional_validation"
    assert payload["inferences"][0]["inference_id"] == "OBS.COVERAGE.ZERO"
    assert payload["duration_seconds"] >= 0