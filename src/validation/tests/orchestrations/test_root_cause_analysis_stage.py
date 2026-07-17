"""Integration tests for the orchestration root-cause stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from json import loads
from pathlib import Path

import pytest

from validation.interpretation.models import InterpretationReport
from validation.orchestration.adapters.root_cause import RootCauseRequestSource
from validation.orchestration.models import (
    ArtifactKind,
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    ExperimentResult,
    ExperimentStage,
    PipelineStageResult,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.orchestration.orchestrator import OrchestrationContext
from validation.orchestration.stages.root_cause import (
    RootCauseStageHandler,
    RootCauseStagePayload,
)
from validation.orchestration.workspace import ExperimentWorkspace
from validation.root_cause.engine import EngineInputs


_FIXED_TIME = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
_LATER = datetime(2026, 7, 16, 10, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _StaticInputProvider:
    payload: RootCauseStagePayload

    def load(self, context: OrchestrationContext) -> RootCauseStagePayload:
        assert context.run_id == "run-001"
        return self.payload


def _config(tmp_path: Path) -> ExperimentConfig:
    synthea_directory = tmp_path / "synthea"
    psynthea_directory = tmp_path / "psynthea"
    synthea_directory.mkdir()
    psynthea_directory.mkdir()

    return ExperimentConfig(
        id="hypertension-validation",
        name="Hypertension equivalence validation",
        cohort=CohortConfig(
            population=100,
            seed=42,
            modules=("hypertension",),
            reference_date=date(2026, 1, 1),
        ),
        simulators=(
            SimulatorConfig(
                kind=SimulatorKind.SYNTHEA,
                command=("synthea",),
                working_directory=synthea_directory,
                output_subdirectory="cohort",
            ),
            SimulatorConfig(
                kind=SimulatorKind.PSYNTHEA,
                command=("psynthea",),
                working_directory=psynthea_directory,
                output_subdirectory="cohort",
            ),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.JSON,),
    )


def _simulator_run(simulator: SimulatorKind) -> SimulatorRunResult:
    return SimulatorRunResult(
        id=f"run.{simulator.value}",
        simulator=simulator,
        status=ExecutionStatus.SUCCEEDED,
        command=(simulator.value,),
        working_directory=Path("/tmp"),
        started_at=_FIXED_TIME,
        finished_at=_LATER,
        duration_seconds=60.0,
        return_code=0,
    )


def _stage_result(
    stage: ExperimentStage,
    *,
    artifacts=(),
) -> PipelineStageResult:
    return PipelineStageResult(
        id=f"stage.{stage.value}",
        stage=stage,
        status=ExecutionStatus.SUCCEEDED,
        started_at=_FIXED_TIME,
        finished_at=_LATER,
        duration_seconds=60.0,
        artifacts=tuple(artifacts),
    )


def _context(tmp_path: Path) -> tuple[
    ExperimentWorkspace,
    OrchestrationContext,
    RootCauseStagePayload,
]:
    config = _config(tmp_path)
    workspace = ExperimentWorkspace.create(
        config,
        "run-001",
        created_at=_FIXED_TIME,
    )

    validation_path = workspace.write_json(
        "validation/results.json",
        {"status": "pass"},
    )
    knowledge_path = workspace.write_json(
        "knowledge/interpretation.json",
        {"findings": []},
    )

    validation_artifact = workspace.artifact_reference(
        artifact_id="validation.result",
        kind=ArtifactKind.VALIDATION_RESULT,
        path=validation_path,
        media_type="application/json",
        producer="validation_stage",
        created_at=_FIXED_TIME,
    )
    knowledge_artifact = workspace.artifact_reference(
        artifact_id="knowledge.result",
        kind=ArtifactKind.KNOWLEDGE_RESULT,
        path=knowledge_path,
        media_type="application/json",
        producer="knowledge_stage",
        created_at=_FIXED_TIME,
    )

    simulator_runs = tuple(
        _simulator_run(simulator)
        for simulator in (
            SimulatorKind.SYNTHEA,
            SimulatorKind.PSYNTHEA,
        )
    )
    stage_results = (
        _stage_result(ExperimentStage.COHORT_LOADING),
        _stage_result(ExperimentStage.COHORT_NORMALIZATION),
        _stage_result(
            ExperimentStage.VALIDATION,
            artifacts=(validation_artifact,),
        ),
        _stage_result(
            ExperimentStage.KNOWLEDGE_ENRICHMENT,
            artifacts=(knowledge_artifact,),
        ),
    )

    experiment = ExperimentResult(
        experiment_id=config.id,
        run_id="run-001",
        status=ExecutionStatus.RUNNING,
        config=config,
        workspace=workspace.root,
        simulator_runs=simulator_runs,
        stage_results=stage_results,
        artifacts=(validation_artifact, knowledge_artifact),
        started_at=_FIXED_TIME,
    )
    report = InterpretationReport(
        report_id="interpretation.report",
        pipeline_run_id=experiment.run_id,
        findings=(),
        evidence=(),
        generated_at=_FIXED_TIME,
        engine_version="test-engine",
        module_name="hypertension",
    )
    payload = RootCauseStagePayload(
        request_source=RootCauseRequestSource(
            experiment_result=experiment,
            interpretation_report=report,
        ),
        engine_inputs=EngineInputs(
            evidence_sources=(),
            artifacts=(
                validation_artifact,
                knowledge_artifact,
            ),
        ),
    )
    context = OrchestrationContext(
        config=config,
        workspace=workspace,
        run_id=experiment.run_id,
        simulator_runs=simulator_runs,
        stage_results=stage_results,
        artifacts=(validation_artifact, knowledge_artifact),
    )
    return workspace, context, payload


def test_stage_executes_engine_and_persists_canonical_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, context, payload = _context(tmp_path)

    request = type("Request", (), {"id": "root-cause.request"})()
    report = type(
        "Report",
        (),
        {
            "id": "root-cause.report",
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

    output = RootCauseStageHandler(
        input_provider=_StaticInputProvider(payload),
        clock=lambda: _FIXED_TIME,
    ).execute(context)

    assert len(output.artifacts) == 2
    assert output.artifacts[0].kind is ArtifactKind.ROOT_CAUSE_RESULT
    assert output.artifacts[1].kind is ArtifactKind.REPORT
    assert output.metadata["root_cause_status"] == "not_applicable"
    assert output.metadata["signal_count"] == 0
    assert output.metadata["candidate_count"] == 0
    assert output.metadata["finding_count"] == 0

    json_path = workspace.root / output.artifacts[0].path
    markdown_path = workspace.root / output.artifacts[1].path

    assert json_path.read_text(encoding="utf-8") == (
        '{"status":"not_applicable"}\n'
    )
    assert markdown_path.read_text(encoding="utf-8") == (
        "# Root Cause\n\nnot_applicable\n"
    )
    assert output.artifacts[0].sha256 is not None
    assert output.artifacts[1].sha256 is not None


def test_stage_rejects_naive_clock_values(tmp_path: Path) -> None:
    _, context, payload = _context(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        RootCauseStageHandler(
            input_provider=_StaticInputProvider(payload),
            clock=lambda: datetime(2026, 7, 16, 10, 0),
        ).execute(context)