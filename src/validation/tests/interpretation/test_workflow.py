from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
import pytest

from validation.comparison.module_validation import ModuleValidationResult
from validation.models import ValidationCohort
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
    EvidenceRequirement,
    PipelineStage,
    RuleContext,
    RuleOutcome,
    StageStatus,
    StructuralRule,
)
from validation.interpretation.workflow import (
    InterpretationInput,
    InterpretationWorkflow,
    InterpretationWorkflowConfig,
    InterpretationWorkflowError,
    WorkflowArtifacts,
)


@dataclass(frozen=True)
class _Source:
    value: int
    metric_id: str = "workflow.metric"


class _Adapter:
    def supports(self, source: object) -> bool:
        return isinstance(source, _Source)

    def extract(self, source: object, *, strict: bool = True) -> EvidenceCatalog:
        assert isinstance(source, _Source)
        return EvidenceCatalog(
            (
                EvidenceValue(
                    metric_id=source.metric_id,
                    name="Workflow metric",
                    availability=EvidenceAvailability.AVAILABLE,
                    value=source.value,
                    source="workflow-test",
                ),
            )
        )


class _PassRule(StructuralRule):
    rule_id = "WORKFLOW.PASS"
    domain = "workflow"
    description = "Exercise the end-to-end interpretation workflow."
    requirements = (EvidenceRequirement(metric_id="workflow.metric"),)
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("workflow",)

    def interpret(self, context: RuleContext, evidence: dict[str, object]) -> RuleOutcome:
        reference = EvidenceReference(
            metric_id="workflow.metric",
            role=EvidenceRole.PRIMARY,
        )
        finding = InterpretationFinding(
            finding_id="WORKFLOW.PASS.FINDING",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Workflow input was interpreted",
            status=FindingStatus.PASS,
            severity=Severity.INFO,
            confidence=Confidence.VERY_HIGH,
            evidence_strength=EvidenceStrength.VERY_STRONG,
            observation="The canonical workflow metric is available.",
            interpretation="The workflow completed all configured scientific layers.",
            impact="The test execution is internally complete.",
            evidence=(reference,),
            recommendations=(
                Recommendation(
                    recommendation_id="WORKFLOW.REVIEW",
                    action="Review the completed workflow output.",
                    priority=RecommendationPriority.LOW,
                    rationale="Human review remains part of scientific governance.",
                    expected_outcome="The output is acknowledged by a reviewer.",
                    verification="Record the review decision.",
                    blocking=False,
                ),
            ),
            tags=("workflow",),
            confidence_score=0.99,
            blocks_research_use=False,
        )
        return RuleOutcome(findings=(finding,))


def _workflow() -> InterpretationWorkflow:
    return InterpretationWorkflow(
        engine=InterpretationEngine((_PassRule(),)),
        registry=EvidenceRegistry((_Adapter(),)),
    )


def _config(**kwargs: object) -> InterpretationWorkflowConfig:
    defaults = {
        "validation_id": "workflow-validation",
        "pipeline_run_id": "workflow-run",
        "module_name": "hypertension",
    }
    defaults.update(kwargs)
    return InterpretationWorkflowConfig(**defaults)


def test_end_to_end_workflow_builds_all_products() -> None:
    result = _workflow().run(
        (
            InterpretationInput(
                stage=PipelineStage.FUNCTIONAL_VALIDATION,
                source=_Source(7),
                label="functional",
            ),
        ),
        config=_config(),
    )

    assert result.evidence.require("workflow.metric").value == 7
    assert result.execution.report.report_id == "workflow-validation.interpretation"
    assert result.summary.overall_status is FindingStatus.PASS
    assert result.recommendation_plan.source_recommendation_count == 1
    assert result.document.summary is result.summary
    assert result.stage_statuses[PipelineStage.INGESTION] is StageStatus.COMPLETED
    assert result.stage_statuses[PipelineStage.FUNCTIONAL_VALIDATION] is StageStatus.COMPLETED
    assert len(result.workflow_fingerprint) == 64
    assert result.artifacts is None


def test_run_and_write_emits_synchronized_report_bundle(tmp_path: Path) -> None:
    result = _workflow().run_and_write(
        (
            InterpretationInput(
                stage=PipelineStage.FUNCTIONAL_VALIDATION,
                source=_Source(2),
            ),
        ),
        config=_config(),
        output_directory=tmp_path,
        stem="workflow_result",
    )

    assert result.artifacts is not None
    assert result.artifacts.markdown_report == tmp_path / "workflow_result.md"
    assert result.artifacts.json_report == tmp_path / "workflow_result.json"
    assert result.artifacts.markdown_report.exists()
    assert result.artifacts.json_report.exists()
    assert "Workflow input was interpreted" in result.artifacts.markdown_report.read_text()


def test_required_normalization_failure_is_explicit() -> None:
    with pytest.raises(InterpretationWorkflowError, match="Required input"):
        _workflow().run(
            (
                InterpretationInput(
                    stage=PipelineStage.FUNCTIONAL_VALIDATION,
                    source=object(),
                    label="unsupported",
                ),
            ),
            config=_config(),
        )


def test_optional_failed_input_does_not_mark_stage_completed() -> None:
    result = _workflow().run(
        (
            InterpretationInput(
                stage=PipelineStage.FUNCTIONAL_VALIDATION,
                source=_Source(1),
            ),
            InterpretationInput(
                stage=PipelineStage.STATISTICAL_VALIDATION,
                source=object(),
                required=False,
            ),
        ),
        config=_config(),
    )

    assert result.stage_statuses[PipelineStage.FUNCTIONAL_VALIDATION] is StageStatus.COMPLETED
    assert result.stage_statuses[PipelineStage.STATISTICAL_VALIDATION] is StageStatus.NOT_RUN
    assert len(result.input_manifest) == 2
    assert result.input_manifest[1]["normalization_status"] == "failed"
    assert result.input_manifest[1]["error_type"]


def test_duplicate_stage_inputs_are_rejected() -> None:
    with pytest.raises(InterpretationWorkflowError, match="one canonical output"):
        _workflow().run(
            (
                InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(1)),
                InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(2)),
            ),
            config=_config(),
        )


def test_metric_collision_across_stages_is_rejected() -> None:
    with pytest.raises(InterpretationWorkflowError, match="cannot be merged safely"):
        _workflow().run(
            (
                InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(1)),
                InterpretationInput(PipelineStage.STATISTICAL_VALIDATION, _Source(2)),
            ),
            config=_config(),
        )


def test_stage_override_cannot_contradict_successful_input() -> None:
    with pytest.raises(InterpretationWorkflowError, match="successfully normalized input"):
        _workflow().run(
            (
                InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(1)),
            ),
            config=_config(
                stage_overrides={
                    PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.FAILED
                }
            ),
        )



def test_stage_override_cannot_fabricate_completed_stage() -> None:
    with pytest.raises(ValueError, match="controlled exclusively"):
        _config(
            stage_overrides={
                PipelineStage.STATISTICAL_VALIDATION: StageStatus.COMPLETED
            }
        )


def test_manifest_records_successful_normalization_status() -> None:
    result = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(4)),),
        config=_config(),
    )
    entry = result.input_manifest[0]
    assert entry["normalization_status"] == "completed"
    assert entry["error_type"] is None
    assert entry["metric_ids_fingerprint"]

def test_config_deep_freezes_metadata_and_rejects_reserved_keys() -> None:
    nested = {"team": ["IRYCIS"]}
    config = _config(metadata=nested)
    nested["team"].append("changed")
    assert config.metadata["team"] == ("IRYCIS",)

    with pytest.raises(ValueError, match="reserved"):
        _config(metadata={"workflow": {}})


def test_result_serialization_is_complete_and_consistent() -> None:
    result = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(3)),),
        config=_config(),
    )
    payload = result.to_dict()

    assert payload["workflow_fingerprint"] == result.workflow_fingerprint
    assert payload["stage_statuses"]["ingestion"] == "completed"
    assert payload["summary"]["report_id"] == result.execution.report.report_id
    assert payload["recommendation_plan"]["report_id"] == result.execution.report.report_id
    assert payload["document"]["summary"]["report_id"] == result.execution.report.report_id


def test_real_module_validation_result_is_normalized_by_default_registry() -> None:
    table_status = pd.DataFrame(
        [
            {
                "table": "patients",
                "required": True,
                "synthea_available": True,
                "psynthea_available": True,
                "synthea_rows": 10,
                "psynthea_rows": 10,
                "synthea_empty": False,
                "psynthea_empty": False,
                "blocking_issue": False,
                "row_difference": 0,
                "relative_row_difference": 0.0,
            }
        ]
    )
    result = ModuleValidationResult(
        module_name="hypertension",
        synthea_cohort=ValidationCohort(source="synthea"),
        psynthea_cohort=ValidationCohort(source="psynthea"),
        table_status=table_status,
        clinical_signal=pd.DataFrame(),
        distributional_similarity=pd.DataFrame(),
        issues=pd.DataFrame(),
        summary=pd.DataFrame(
            [
                {
                    "module_name": "hypertension",
                    "status": "comparable",
                    "status_reason": "ok",
                    "synthea_functional": True,
                    "psynthea_functional": True,
                    "valid_for_comparison": True,
                    "blocking_issue_count": 0,
                    "warning_count": 0,
                    "synthea_condition_count": 0,
                    "psynthea_condition_count": 0,
                    "synthea_observation_count": 0,
                    "psynthea_observation_count": 0,
                    "mean_distributional_similarity": None,
                    "mean_jensen_shannon_divergence": None,
                }
            ]
        ),
    )

    workflow = InterpretationWorkflow(
        engine=InterpretationEngine((_PassRule(),)),
    )
    # The custom rule does not consume these metrics; this assertion verifies the
    # real pipeline adapter and workflow manifest without fabricating an adapter.
    execution = workflow.run(
        (
            InterpretationInput(
                PipelineStage.FUNCTIONAL_VALIDATION,
                result,
                label="module-validation",
            ),
        ),
        config=_config(),
    )

    assert len(execution.evidence) > 0
    assert execution.input_manifest[0]["source_type"].endswith("ModuleValidationResult")
    assert execution.stage_statuses[PipelineStage.FUNCTIONAL_VALIDATION] is StageStatus.COMPLETED


def test_workflow_fingerprint_changes_when_evidence_value_changes() -> None:
    first = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(1)),),
        config=_config(),
    )
    second = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(2)),),
        config=_config(),
    )

    assert first.evidence_catalog_fingerprint != second.evidence_catalog_fingerprint
    assert first.workflow_fingerprint != second.workflow_fingerprint


def test_result_rejects_tampered_evidence_fingerprint() -> None:
    result = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(3)),),
        config=_config(),
    )

    with pytest.raises(ValueError, match="canonical evidence content"):
        replace(result, evidence_catalog_fingerprint="0" * 64)


def test_result_rejects_tampered_workflow_fingerprint() -> None:
    result = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(3)),),
        config=_config(),
    )

    with pytest.raises(ValueError, match="workflow result content"):
        replace(result, workflow_fingerprint="0" * 64)


def test_manifest_records_full_evidence_fingerprint() -> None:
    result = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(4)),),
        config=_config(),
    )

    entry = result.input_manifest[0]
    assert len(entry["evidence_fingerprint"]) == 64
    assert entry["evidence_fingerprint"] == result.evidence_catalog_fingerprint


def test_artifact_metadata_detects_post_write_tampering(tmp_path: Path) -> None:
    result = _workflow().run_and_write(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(5)),),
        config=_config(),
        output_directory=tmp_path,
        stem="integrity",
    )
    assert result.artifacts is not None
    result.artifacts.markdown_report.write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity metadata"):
        WorkflowArtifacts(
            markdown_report=result.artifacts.markdown_report,
            json_report=result.artifacts.json_report,
            markdown_sha256=result.artifacts.markdown_sha256,
            json_sha256=result.artifacts.json_sha256,
            markdown_size_bytes=result.artifacts.markdown_size_bytes,
            json_size_bytes=result.artifacts.json_size_bytes,
        )


def test_result_requires_complete_stage_status_map() -> None:
    result = _workflow().run(
        (InterpretationInput(PipelineStage.FUNCTIONAL_VALIDATION, _Source(6)),),
        config=_config(),
    )
    reduced = dict(result.stage_statuses)
    reduced.pop(PipelineStage.REPORTING)

    with pytest.raises(ValueError, match="every PipelineStage"):
        replace(result, stage_statuses=reduced)