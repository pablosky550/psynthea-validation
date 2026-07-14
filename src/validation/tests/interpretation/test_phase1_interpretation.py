"""Phase 1 end-to-end acceptance tests for the interpretation subsystem.

These tests validate the public workflow boundary rather than duplicating the
unit tests of individual scientific rules.  The acceptance fixture exercises
all interpretation dimensions through the complete production chain:

    EvidenceRegistry -> EvidenceCatalog -> InterpretationWorkflow
    -> InterpretationEngine -> deterministic rules -> summary
    -> recommendation plan -> report document -> persisted Markdown/JSON bundle

The scenarios intentionally cover release-critical outcomes:

* PASS: every scientific dimension completes and research use is allowed;
* FAIL: a blocking epidemiological discrepancy propagates to the final report;
* INCONCLUSIVE: missing canonical evidence blocks dependent rules and prevents
  an unsafe equivalence conclusion;
* artifact integrity: synchronized reports have verified content hashes;
* determinism: timestamp-free scientific payloads and registry order remain
  stable across equivalent executions.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import loads
from pathlib import Path
from typing import Final

from validation.interpretation.engine import InterpretationEngine
from validation.interpretation.evidence import EvidenceCatalog, EvidenceRegistry
from validation.interpretation.models import (
    Confidence,
    EvidenceAvailability,
    EvidenceReference,
    EvidenceRole,
    EvidenceStrength,
    EvidenceValue,
    FindingStatus,
    InterpretationFinding,
    Recommendation,
    RecommendationPriority,
    Severity,
)
from validation.interpretation.rules.base import (
    ClinicalRule,
    EpidemiologicalRule,
    EvidenceRequirement,
    PipelineStage,
    RuleContext,
    RuleDependency,
    RuleOutcome,
    StageStatus,
    StatisticalRule,
    StructuralRule,
)
from validation.interpretation.rules.spanish_adaptation import SpanishAdaptationRule
from validation.interpretation.workflow import (
    InterpretationInput,
    InterpretationWorkflow,
    InterpretationWorkflowConfig,
)


# ---------------------------------------------------------------------------
# Canonical acceptance sources and normalization adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _AcceptanceSource:
    """One pipeline-stage output used by the black-box acceptance workflow."""

    metric_id: str
    value: bool | float | None
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE
    source_name: str = "phase1-acceptance"

    def __post_init__(self) -> None:
        if self.availability is EvidenceAvailability.AVAILABLE and self.value is None:
            raise ValueError("Available acceptance evidence must contain a value.")
        if self.availability is not EvidenceAvailability.AVAILABLE and self.value is not None:
            raise ValueError("Unavailable acceptance evidence must use value=None.")


@dataclass(frozen=True, slots=True)
class _CompositeAcceptanceSource:
    """One canonical stage output containing multiple normalized metrics."""

    values: tuple[_AcceptanceSource, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("Composite acceptance source must not be empty.")


class _AcceptanceAdapter:
    """Normalize acceptance sources through the production registry contract."""

    def supports(self, source: object) -> bool:
        return isinstance(source, (_AcceptanceSource, _CompositeAcceptanceSource))

    def extract(
        self,
        source: object,
        *,
        strict: bool = True,
    ) -> EvidenceCatalog:
        if isinstance(source, _AcceptanceSource):
            values = (source,)
        elif isinstance(source, _CompositeAcceptanceSource):
            values = source.values
        else:  # pragma: no cover - guarded by EvidenceRegistry.supports
            raise TypeError(f"Unsupported acceptance source: {type(source).__name__}.")

        return EvidenceCatalog(
            tuple(
                EvidenceValue(
                    metric_id=item.metric_id,
                    name=item.metric_id.replace(".", " ").title(),
                    availability=item.availability,
                    value=item.value,
                    source=item.source_name,
                    metadata={"acceptance_fixture": True, "strict": strict},
                )
                for item in values
            )
        )


# ---------------------------------------------------------------------------
# Acceptance rules: one per scientific dimension, with real dependencies
# ---------------------------------------------------------------------------


def _reference(metric_id: str) -> EvidenceReference:
    return EvidenceReference(metric_id=metric_id, role=EvidenceRole.PRIMARY)


def _finding(
    *,
    rule_id: str,
    domain: str,
    metric_id: str,
    passed: bool,
    title: str,
    blocking: bool,
) -> InterpretationFinding:
    status = FindingStatus.PASS if passed else FindingStatus.FAIL
    severity = Severity.INFO if passed else Severity.CRITICAL
    recommendations: tuple[Recommendation, ...] = ()
    if not passed:
        recommendations = (
            Recommendation(
                recommendation_id=f"{rule_id}.REMEDIATE",
                action=f"Resolve the blocking discrepancy reported by {rule_id}.",
                priority=RecommendationPriority.URGENT,
                rationale="The acceptance signal failed its deterministic release gate.",
                expected_outcome="The acceptance signal evaluates to true on rerun.",
                verification=f"Confirm that {metric_id} is available and equals true.",
                owner="Validation engineering",
                blocking=blocking,
            ),
        )
    return InterpretationFinding(
        finding_id=f"{rule_id}.{'PASS' if passed else 'FAIL'}",
        rule_id=rule_id,
        domain=domain,
        title=title,
        status=status,
        severity=severity,
        confidence=Confidence.VERY_HIGH,
        evidence_strength=EvidenceStrength.VERY_STRONG,
        observation=f"Canonical acceptance evidence {metric_id!r} equals {passed!r}.",
        interpretation=(
            "The scientific release gate is satisfied."
            if passed
            else "The scientific release gate is not satisfied."
        ),
        impact=(
            "This dimension does not block Phase 1 acceptance."
            if passed
            else "Phase 1 cannot be accepted for research use until remediated."
        ),
        evidence=(_reference(metric_id),),
        recommendations=recommendations,
        limitations=("This fixture validates integration contracts, not domain calibration.",),
        tags=("phase1", "acceptance", domain),
        confidence_score=0.99,
        clinically_relevant=domain in {"clinical", "epidemiological"},
        blocks_research_use=blocking and not passed,
    )


class _AcceptanceStructuralRule(StructuralRule):
    rule_id = "ACCEPT.STRUCTURAL"
    domain = "structural"
    description = "Validate the structural acceptance gate."
    requirements = (EvidenceRequirement(metric_id="accept.structural"),)
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("phase1", "acceptance")

    def interpret(self, context: RuleContext, evidence: dict[str, object]) -> RuleOutcome:
        metric = evidence["accept.structural"]
        return RuleOutcome(
            findings=(
                _finding(
                    rule_id=self.rule_id,
                    domain=self.domain,
                    metric_id=metric.metric_id,
                    passed=metric.value is True,
                    title="Structural pipeline acceptance",
                    blocking=True,
                ),
            )
        )


class _AcceptanceStatisticalRule(StatisticalRule):
    rule_id = "ACCEPT.STATISTICAL"
    domain = "statistical"
    description = "Validate the statistical acceptance gate."
    requirements = (EvidenceRequirement(metric_id="accept.statistical"),)
    dependencies = (RuleDependency(rule_id="ACCEPT.STRUCTURAL"),)
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("phase1", "acceptance")

    def interpret(self, context: RuleContext, evidence: dict[str, object]) -> RuleOutcome:
        metric = evidence["accept.statistical"]
        return RuleOutcome(
            findings=(
                _finding(
                    rule_id=self.rule_id,
                    domain=self.domain,
                    metric_id=metric.metric_id,
                    passed=metric.value is True,
                    title="Statistical equivalence acceptance",
                    blocking=True,
                ),
            )
        )


class _AcceptanceClinicalRule(ClinicalRule):
    rule_id = "ACCEPT.CLINICAL"
    domain = "clinical"
    description = "Validate the clinical acceptance gate."
    requirements = (EvidenceRequirement(metric_id="accept.clinical"),)
    dependencies = (RuleDependency(rule_id="ACCEPT.STRUCTURAL"),)
    required_stages = (PipelineStage.CLINICAL_VALIDATION,)
    tags = ("phase1", "acceptance")

    def interpret(self, context: RuleContext, evidence: dict[str, object]) -> RuleOutcome:
        metric = evidence["accept.clinical"]
        return RuleOutcome(
            findings=(
                _finding(
                    rule_id=self.rule_id,
                    domain=self.domain,
                    metric_id=metric.metric_id,
                    passed=metric.value is True,
                    title="Clinical coherence acceptance",
                    blocking=True,
                ),
            )
        )


class _AcceptanceEpidemiologicalRule(EpidemiologicalRule):
    rule_id = "ACCEPT.EPIDEMIOLOGICAL"
    domain = "epidemiological"
    description = "Validate the epidemiological acceptance gate."
    requirements = (EvidenceRequirement(metric_id="accept.epidemiological"),)
    dependencies = (
        RuleDependency(rule_id="ACCEPT.STATISTICAL"),
        RuleDependency(rule_id="ACCEPT.CLINICAL"),
    )
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("phase1", "acceptance")

    def interpret(self, context: RuleContext, evidence: dict[str, object]) -> RuleOutcome:
        metric = evidence["accept.epidemiological"]
        return RuleOutcome(
            findings=(
                _finding(
                    rule_id=self.rule_id,
                    domain=self.domain,
                    metric_id=metric.metric_id,
                    passed=metric.value is True,
                    title="Epidemiological preservation acceptance",
                    blocking=True,
                ),
            )
        )


class _AcceptanceSpanishRule(SpanishAdaptationRule):
    rule_id = "ACCEPT.SPANISH_ADAPTATION"
    domain = "spanish_adaptation"
    description = "Validate the Spanish adaptation acceptance gate."
    requirements = (EvidenceRequirement(metric_id="accept.spanish"),)
    dependencies = (
        RuleDependency(rule_id="ACCEPT.CLINICAL"),
        RuleDependency(rule_id="ACCEPT.EPIDEMIOLOGICAL"),
    )
    required_stages = (PipelineStage.SPANISH_ADAPTATION,)
    tags = ("phase1", "acceptance")

    def interpret(self, context: RuleContext, evidence: dict[str, object]) -> RuleOutcome:
        metric = evidence["accept.spanish"]
        return RuleOutcome(
            findings=(
                _finding(
                    rule_id=self.rule_id,
                    domain=self.domain,
                    metric_id=metric.metric_id,
                    passed=metric.value is True,
                    title="Spanish adaptation acceptance",
                    blocking=True,
                ),
            )
        )


_ACCEPTANCE_RULES: Final = (
    _AcceptanceStructuralRule(),
    _AcceptanceStatisticalRule(),
    _AcceptanceClinicalRule(),
    _AcceptanceEpidemiologicalRule(),
    _AcceptanceSpanishRule(),
)
_EXPECTED_EXECUTION_ORDER: Final = tuple(rule.rule_id for rule in _ACCEPTANCE_RULES)


def _workflow() -> InterpretationWorkflow:
    return InterpretationWorkflow(
        engine=InterpretationEngine(_ACCEPTANCE_RULES),
        registry=EvidenceRegistry((_AcceptanceAdapter(),)),
    )


def _inputs(
    *,
    epidemiological: bool | None = True,
    epidemiological_availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
) -> tuple[InterpretationInput, ...]:
    # The workflow accepts one canonical output per stage.  The statistical
    # output legitimately contributes both statistical and epidemiological
    # evidence, mirroring the real comparison pipeline.
    return (
        InterpretationInput(
            PipelineStage.FUNCTIONAL_VALIDATION,
            _AcceptanceSource("accept.structural", True),
            label="functional",
        ),
        InterpretationInput(
            PipelineStage.STATISTICAL_VALIDATION,
            _CompositeAcceptanceSource(
                (
                    _AcceptanceSource("accept.statistical", True),
                    _AcceptanceSource(
                        "accept.epidemiological",
                        epidemiological,
                        availability=epidemiological_availability,
                    ),
                )
            ),
            label="statistical",
        ),
        InterpretationInput(
            PipelineStage.CLINICAL_VALIDATION,
            _AcceptanceSource("accept.clinical", True),
            label="clinical",
        ),
        InterpretationInput(
            PipelineStage.SPANISH_ADAPTATION,
            _AcceptanceSource("accept.spanish", True),
            label="spanish",
        ),
    )


def _configured_workflow_and_inputs(
    **kwargs: object,
) -> tuple[InterpretationWorkflow, tuple[InterpretationInput, ...]]:
    return _workflow(), _inputs(**kwargs)


def _config(run_id: str = "phase1-e2e-run") -> InterpretationWorkflowConfig:
    return InterpretationWorkflowConfig(
        validation_id="phase1-acceptance",
        pipeline_run_id=run_id,
        module_name="hypertension",
        research_use=True,
        metadata={"acceptance_suite": "phase1", "release_gate": True},
    )


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Release acceptance scenarios
# ---------------------------------------------------------------------------


def test_phase1_pass_scenario_completes_every_layer_and_allows_research_use(
    tmp_path: Path,
) -> None:
    workflow, inputs = _configured_workflow_and_inputs()
    result = workflow.run_and_write(
        inputs,
        config=_config(),
        output_directory=tmp_path,
        stem="phase1_acceptance_pass",
    )

    assert result.execution.execution_order == _EXPECTED_EXECUTION_ORDER
    assert result.summary.overall_status is FindingStatus.PASS
    assert result.execution.report.overall_status is FindingStatus.PASS
    assert result.research_use_ready is True
    assert result.execution.research_use_ready is True
    assert result.summary.research_use_ready is True
    assert not result.recommendation_plan.blocking_items

    assert len(result.evidence) == 5
    assert all(value.is_available for value in result.evidence)
    assert all(
        result.stage_statuses[stage] is StageStatus.COMPLETED
        for stage in (
            PipelineStage.INGESTION,
            PipelineStage.FUNCTIONAL_VALIDATION,
            PipelineStage.STATISTICAL_VALIDATION,
            PipelineStage.CLINICAL_VALIDATION,
            PipelineStage.SPANISH_ADAPTATION,
        )
    )

    assert result.artifacts is not None
    assert result.artifacts.markdown_report.exists()
    assert result.artifacts.json_report.exists()
    assert _sha256(result.artifacts.markdown_report) == result.artifacts.markdown_sha256
    assert _sha256(result.artifacts.json_report) == result.artifacts.json_sha256

    markdown = result.artifacts.markdown_report.read_text(encoding="utf-8")
    payload = loads(result.artifacts.json_report.read_text(encoding="utf-8"))
    assert "Epidemiological preservation acceptance" in markdown
    assert payload["summary"]["overall_status"] == "pass"
    assert payload["summary"]["research_use_ready"] is True


def test_phase1_fail_scenario_propagates_blocking_epidemiology_to_all_products(
    tmp_path: Path,
) -> None:
    workflow, inputs = _configured_workflow_and_inputs(epidemiological=False)
    result = workflow.run_and_write(
        inputs,
        config=_config("phase1-e2e-fail"),
        output_directory=tmp_path,
        stem="phase1_acceptance_fail",
    )

    assert result.summary.overall_status is FindingStatus.FAIL
    assert result.execution.report.overall_status is FindingStatus.FAIL
    assert result.research_use_ready is False
    assert result.execution.research_use_ready is False
    assert result.summary.research_use_ready is False

    epidemiological = next(
        item for item in result.execution.evaluations
        if item.rule_id == "ACCEPT.EPIDEMIOLOGICAL"
    )
    assert epidemiological.findings[0].status is FindingStatus.FAIL
    assert epidemiological.findings[0].blocks_research_use is True
    assert result.recommendation_plan.blocking_items
    assert any(
        "ACCEPT.EPIDEMIOLOGICAL.REMEDIATE" in item.source_recommendation_ids
        for item in result.recommendation_plan.blocking_items
    )

    spanish = next(
        item for item in result.execution.evaluations
        if item.rule_id == "ACCEPT.SPANISH_ADAPTATION"
    )
    # Dependencies require successful execution, not a PASS finding.  The
    # Spanish rule therefore still executes, while the global FAIL remains
    # dominated by the blocking epidemiological finding.
    assert spanish.status.value == "completed"
    assert spanish.findings[0].status is FindingStatus.PASS

    assert result.artifacts is not None
    markdown = result.artifacts.markdown_report.read_text(encoding="utf-8")
    payload = loads(result.artifacts.json_report.read_text(encoding="utf-8"))
    assert "ACCEPT.EPIDEMIOLOGICAL.REMEDIATE" in markdown
    assert payload["summary"]["overall_status"] == "fail"
    assert payload["summary"]["research_use_ready"] is False


def test_phase1_inconclusive_scenario_never_converts_missing_evidence_to_zero() -> None:
    workflow, inputs = _configured_workflow_and_inputs(
        epidemiological=None,
        epidemiological_availability=EvidenceAvailability.NOT_COMPUTED,
    )
    result = workflow.run(inputs, config=_config("phase1-e2e-inconclusive"))

    metric = result.evidence.require("accept.epidemiological")
    assert metric.availability is EvidenceAvailability.NOT_COMPUTED
    assert metric.value is None
    assert metric.is_zero is False

    epidemiological = next(
        item for item in result.execution.evaluations
        if item.rule_id == "ACCEPT.EPIDEMIOLOGICAL"
    )
    assert epidemiological.status.value == "insufficient_evidence"
    assert not epidemiological.findings

    spanish = next(
        item for item in result.execution.evaluations
        if item.rule_id == "ACCEPT.SPANISH_ADAPTATION"
    )
    assert spanish.status.value == "blocked_dependency"
    assert result.summary.overall_status is FindingStatus.INCONCLUSIVE
    assert result.research_use_ready is False
    assert result.recommendation_plan.blocking_items
    incomplete_rules = {
        rule_id
        for item in result.recommendation_plan.blocking_items
        for rule_id in item.incomplete_rule_ids
    }
    assert incomplete_rules == {
        "ACCEPT.EPIDEMIOLOGICAL",
        "ACCEPT.SPANISH_ADAPTATION",
    }


def test_equivalent_runs_preserve_scientific_order_and_content_fingerprints() -> None:
    workflow_a, inputs_a = _configured_workflow_and_inputs()
    workflow_b, inputs_b = _configured_workflow_and_inputs()
    first = workflow_a.run(inputs_a, config=_config("phase1-e2e-deterministic"))
    second = workflow_b.run(inputs_b, config=_config("phase1-e2e-deterministic"))

    assert first.execution.execution_order == second.execution.execution_order
    assert first.evidence_catalog_fingerprint == second.evidence_catalog_fingerprint
    assert first.recommendation_plan.fingerprint == second.recommendation_plan.fingerprint
    assert first.summary.overall_status is second.summary.overall_status
    assert first.summary.research_use_ready is second.summary.research_use_ready
    assert tuple(item.status for item in first.execution.evaluations) == tuple(
        item.status for item in second.execution.evaluations
    )
    assert tuple(
        finding.finding_id for finding in first.execution.report.findings
    ) == tuple(
        finding.finding_id for finding in second.execution.report.findings
    )

    # Document and workflow fingerprints intentionally include generated-at
    # timestamps.  Their values may differ across runs even when every
    # scientific decision is deterministic.
    assert len(first.workflow_fingerprint) == 64
    assert len(second.workflow_fingerprint) == 64


def test_default_engine_registry_contains_epidemiology_in_release_order() -> None:
    engine = InterpretationEngine()
    rule_ids = tuple(rule.rule_id for rule in engine.rules)

    epidemiological_positions = tuple(
        index for index, rule in enumerate(engine.rules) if isinstance(rule, EpidemiologicalRule)
    )
    statistical_positions = tuple(
        index for index, rule in enumerate(engine.rules) if isinstance(rule, StatisticalRule)
    )
    spanish_positions = tuple(
        index for index, rule in enumerate(engine.rules) if isinstance(rule, SpanishAdaptationRule)
    )

    assert epidemiological_positions
    assert statistical_positions
    assert spanish_positions
    assert max(statistical_positions) < min(epidemiological_positions)
    assert max(epidemiological_positions) < min(spanish_positions)
    assert len(rule_ids) == len(set(rule_ids))