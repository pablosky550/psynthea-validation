"""Execution-level integration test for the canonical scientific pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from validation.interpretation.models import InterpretationReport
from validation.interpretation.workflow import InterpretationWorkflowResult
from validation.orchestration.composition import build_experiment_orchestrator
from validation.orchestration.models import (
    ArtifactKind,
    ExecutionStatus,
    ExperimentStage,
)
from validation.orchestration.orchestrator import StageOutput
from validation.orchestration.scientific_pipeline import build_scientific_pipeline
from validation.tests.orchestrations.test_endtoend import (
    CohortLoadingHandler,
    CohortNormalizationHandler,
    ReportHandler,
    ValidationHandler,
    _config,
    _runner_factory,
)


_FIXED_TIME = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _interpretation(*, run_id: str) -> InterpretationWorkflowResult:
    report = InterpretationReport(
        report_id="interpretation.hypertension",
        pipeline_run_id=run_id,
        findings=(),
        evidence=(),
        generated_at=_FIXED_TIME,
        engine_version="integration-test",
        module_name="Hypertension",
    )
    result = object.__new__(InterpretationWorkflowResult)
    execution = type("Execution", (), {"report": report})()
    object.__setattr__(result, "execution", execution)
    object.__setattr__(result, "workflow_fingerprint", "workflow-fingerprint")
    object.__setattr__(
        result,
        "evidence_catalog_fingerprint",
        "evidence-fingerprint",
    )
    return result


def test_orchestrator_executes_knowledge_store_root_cause_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumed: dict[str, object] = {}

    def execute_knowledge(self, context):
        interpretation = _interpretation(run_id=context.run_id)
        self.product_store.publish_interpretation(
            run_id=context.run_id,
            result=interpretation,
        )
        consumed["published"] = interpretation

        path = context.workspace.write_json(
            "knowledge/knowledge_result.json",
            {"module_name": "Hypertension"},
        )
        artifact = context.workspace.artifact_reference(
            artifact_id="knowledge.result",
            kind=ArtifactKind.KNOWLEDGE_RESULT,
            path=path,
            media_type="application/json",
            producer="knowledge_stage",
            created_at=_FIXED_TIME,
        )
        return StageOutput(
            artifacts=(artifact,),
            summary="Scientific interpretation completed.",
        )

    original_load = (
        "validation.orchestration.stages.root_cause_input."
        "StoredRootCauseStageInputProvider.load"
    )

    from validation.orchestration.stages.root_cause_input import (
        StoredRootCauseStageInputProvider,
    )

    real_load = StoredRootCauseStageInputProvider.load

    def load_and_capture(self, context):
        payload = real_load(self, context)
        consumed["report"] = payload.request_source.interpretation_report
        consumed["artifact_ids"] = tuple(
            artifact.id for artifact in payload.engine_inputs.artifacts
        )
        return payload

    request = type("Request", (), {"id": "root-cause.request"})()
    report = type(
        "Report",
        (),
        {
            "id": "root-cause.report",
            "generated_at": _FIXED_TIME,
            "status": type("Status", (), {"value": "not_applicable"})(),
            "confidence": type("Confidence", (), {"value": "none"})(),
            "findings": (),
            "signals": (),
            "candidates": (),
            "verifications": (),
            "reproduction_plans": (),
        },
    )()
    engine_result = type(
        "EngineResult",
        (),
        {"report": report, "schema_version": 2},
    )()
    document = type(
        "Document",
        (),
        {"document_fingerprint": "a" * 64},
    )()

    monkeypatch.setattr(
        "validation.orchestration.stages.knowledge."
        "KnowledgeStageHandler.execute",
        execute_knowledge,
    )
    monkeypatch.setattr(original_load, load_and_capture)
    monkeypatch.setattr(
        "validation.orchestration.stages.root_cause."
        "RootCauseRequestAdapter.build",
        lambda self, source, *, created_at=None: request,
    )
    monkeypatch.setattr(
        "validation.orchestration.stages.root_cause."
        "RootCauseEngine.run",
        lambda self, supplied_request, inputs: engine_result,
    )
    monkeypatch.setattr(
        "validation.orchestration.stages.root_cause."
        "build_root_cause_document",
        lambda result, **kwargs: document,
    )
    monkeypatch.setattr(
        "validation.orchestration.stages.root_cause."
        "render_json_report",
        lambda supplied_document: '{"status":"not_applicable"}\n',
    )
    monkeypatch.setattr(
        "validation.orchestration.stages.root_cause."
        "render_markdown_report",
        lambda supplied_document: "# Root Cause\n\nnot_applicable\n",
    )

    scientific_pipeline = build_scientific_pipeline(
        module_name="Hypertension",
        knowledge_clock=lambda: _FIXED_TIME,
        root_cause_clock=lambda: _FIXED_TIME,
        provider_metadata={"integration": "scientific-pipeline"},
    )
    orchestrator = build_experiment_orchestrator(
        cohort_loading_handler=CohortLoadingHandler(),
        cohort_normalization_handler=CohortNormalizationHandler(),
        validation_handler=ValidationHandler(),
        scientific_pipeline=scientific_pipeline,
        report_generation_handler=ReportHandler(),
        runner_factory=_runner_factory,
        orchestrator_version="2.0.0",
        clock=lambda: _FIXED_TIME,
        monotonic_clock=lambda: 100.0,
    )

    execution = orchestrator.execute(
        _config(tmp_path),
        run_id="scientific-run-001",
    )
    result = execution.result

    assert result.status is ExecutionStatus.SUCCEEDED
    stage_by_name = {item.stage: item for item in result.stage_results}
    assert stage_by_name[
        ExperimentStage.KNOWLEDGE_ENRICHMENT
    ].status is ExecutionStatus.SUCCEEDED
    assert stage_by_name[
        ExperimentStage.ROOT_CAUSE_ANALYSIS
    ].status is ExecutionStatus.SUCCEEDED
    assert stage_by_name[
        ExperimentStage.REPORT_GENERATION
    ].status is ExecutionStatus.SUCCEEDED

    published = consumed["published"]
    assert consumed["report"] is published.execution.report
    assert "knowledge.result" in consumed["artifact_ids"]
    assert any(
        artifact.kind is ArtifactKind.ROOT_CAUSE_RESULT
        for artifact in result.artifacts
    )

    with pytest.raises(LookupError, match="No interpretation"):
        scientific_pipeline.product_store.interpretation(
            run_id=result.run_id,
            module_name="Hypertension",
        )