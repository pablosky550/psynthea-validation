"""Tests for the orchestration-to-root-cause request adapter."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from validation.interpretation.models import InterpretationReport
from validation.orchestration.adapters.root_cause import (
    RootCauseRequestAdapter,
    RootCauseRequestSource,
)
from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExecutionStatus,
    ExperimentResult,
    ExperimentStage,
    PipelineStageResult,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.root_cause.exceptions import (
    RootCauseInputError,
    RootCauseIntegrityError,
)


NOW = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 15, 10, 1, tzinfo=UTC)
SHA256 = "a" * 64


def _artifact(
    *,
    artifact_id: str,
    kind: ArtifactKind,
    media_type: str = "application/json",
    sha256: str | None = SHA256,
    size_bytes: int | None = 100,
) -> ArtifactReference:
    return ArtifactReference(
        id=artifact_id,
        kind=kind,
        path=Path(f"artifacts/{artifact_id}.json"),
        media_type=media_type,
        created_at=NOW,
        sha256=sha256,
        size_bytes=size_bytes,
        producer="test",
    )


def _stage(
    stage: ExperimentStage,
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
    artifacts: tuple[ArtifactReference, ...] = (),
) -> PipelineStageResult:
    if status is ExecutionStatus.SKIPPED:
        return PipelineStageResult(
            id=f"stage.{stage.value}",
            stage=stage,
            status=status,
            artifacts=artifacts,
        )

    return PipelineStageResult(
        id=f"stage.{stage.value}",
        stage=stage,
        status=status,
        started_at=NOW,
        finished_at=LATER,
        duration_seconds=60.0,
        artifacts=artifacts,
        error_message=(
            "Controlled stage failure."
            if status is ExecutionStatus.FAILED
            else None
        ),
    )


def _simulator_run(
    simulator: SimulatorKind,
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
) -> SimulatorRunResult:
    return SimulatorRunResult(
        id=f"run.{simulator.value}",
        simulator=simulator,
        status=status,
        command=("python", "-m", simulator.value),
        working_directory=Path("/tmp"),
        started_at=NOW,
        finished_at=LATER,
        duration_seconds=60.0,
        return_code=0 if status is ExecutionStatus.SUCCEEDED else 1,
        error_message=(
            None
            if status is ExecutionStatus.SUCCEEDED
            else "Controlled simulator failure."
        ),
    )

def _experiment_result(
    *,
    config,
    validation_artifact: ArtifactReference | None = None,
    knowledge_artifact: ArtifactReference | None = None,
    stage_overrides: dict[
        ExperimentStage,
        ExecutionStatus,
    ] | None = None,
    simulator_overrides: dict[
        SimulatorKind,
        ExecutionStatus,
    ] | None = None,
) -> ExperimentResult:
    stage_overrides = stage_overrides or {}
    simulator_overrides = simulator_overrides or {}

    validation_artifact = validation_artifact or _artifact(
        artifact_id="validation.result",
        kind=ArtifactKind.VALIDATION_RESULT,
    )
    knowledge_artifact = knowledge_artifact or _artifact(
        artifact_id="knowledge.result",
        kind=ArtifactKind.KNOWLEDGE_RESULT,
    )

    stages = (
        _stage(
            ExperimentStage.COHORT_LOADING,
            status=stage_overrides.get(
                ExperimentStage.COHORT_LOADING,
                ExecutionStatus.SUCCEEDED,
            ),
        ),
        _stage(
            ExperimentStage.COHORT_NORMALIZATION,
            status=stage_overrides.get(
                ExperimentStage.COHORT_NORMALIZATION,
                ExecutionStatus.SUCCEEDED,
            ),
        ),
        _stage(
            ExperimentStage.VALIDATION,
            status=stage_overrides.get(
                ExperimentStage.VALIDATION,
                ExecutionStatus.SUCCEEDED,
            ),
            artifacts=(validation_artifact,),
        ),
        _stage(
            ExperimentStage.KNOWLEDGE_ENRICHMENT,
            status=stage_overrides.get(
                ExperimentStage.KNOWLEDGE_ENRICHMENT,
                ExecutionStatus.SUCCEEDED,
            ),
            artifacts=(knowledge_artifact,),
        ),
    )

    simulator_runs = tuple(
        _simulator_run(
            simulator,
            status=simulator_overrides.get(
                simulator,
                ExecutionStatus.SUCCEEDED,
            ),
        )
        for simulator in (
            SimulatorKind.SYNTHEA,
            SimulatorKind.PSYNTHEA,
        )
    )

    return ExperimentResult(
        experiment_id=config.id,
        run_id="run-001",
        status=ExecutionStatus.RUNNING,
        config=config,
        workspace=Path("/tmp/experiment"),
        simulator_runs=simulator_runs,
        stage_results=stages,
        started_at=NOW,
    )

def test_builds_canonical_root_cause_request(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(config=experiment_config)

    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    source = RootCauseRequestSource(
        experiment_result=experiment,
        interpretation_report=report,
        max_candidates=25,
        execute_verifications=True,
        strict_integrity=True,
        metadata={"source": "orchestrator"},
    )

    request = RootCauseRequestAdapter().build(
        source,
        created_at=NOW,
    )

    assert request.id == (
        f"root-cause.{experiment.experiment_id}.{experiment.run_id}"
    )
    assert request.experiment_id == experiment.experiment_id
    assert request.run_id == experiment.run_id
    assert request.validation_result_ids == ("validation.result",)
    assert request.artifact_ids == (
        "knowledge.result",
        "validation.result",
    )
    assert request.max_candidates == 25
    assert request.execute_verifications is True
    assert request.strict_integrity is True
    assert request.created_at == NOW
    assert request.metadata["adapter"] == "RootCauseRequestAdapter"
    assert request.metadata["source"] == "orchestrator"

def test_maps_upstream_domain_identifiers(
    experiment_config,
    interpretation_report: InterpretationReport,
    investigation_case,
    knowledge_entry,
) -> None:
    experiment = _experiment_result(config=experiment_config)
    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    source = RootCauseRequestSource(
        experiment_result=experiment,
        interpretation_report=report,
        investigation_cases=(investigation_case,),
        knowledge_entries=(knowledge_entry,),
    )

    request = RootCauseRequestAdapter().build(
        source,
        created_at=NOW,
    )

    assert request.interpretation_finding_ids == tuple(
        sorted(finding.finding_id for finding in report.findings)
    )
    assert request.investigation_case_ids == (
        investigation_case.id,
    )
    assert request.knowledge_entry_ids == (
        knowledge_entry.id,
    )

def test_rejects_missing_validation_artifact(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(config=experiment_config)

    stages = tuple(
        replace(stage, artifacts=())
        if stage.stage is ExperimentStage.VALIDATION
        else stage
        for stage in experiment.stage_results
    )
    experiment = replace(
        experiment,
        stage_results=stages,
    )

    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseInputError,
        match="persisted validation and knowledge artefacts",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert "validation_result" in exc_info.value.context[
        "missing_artifact_kinds"
    ]

def test_rejects_missing_knowledge_artifact(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(config=experiment_config)

    stages = tuple(
        replace(stage, artifacts=())
        if stage.stage is ExperimentStage.KNOWLEDGE_ENRICHMENT
        else stage
        for stage in experiment.stage_results
    )
    experiment = replace(
        experiment,
        stage_results=stages,
    )

    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseInputError,
        match="persisted validation and knowledge artefacts",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert "knowledge_result" in exc_info.value.context[
        "missing_artifact_kinds"
    ]

@pytest.mark.parametrize(
    "kind",
    [
        ArtifactKind.VALIDATION_RESULT,
        ArtifactKind.KNOWLEDGE_RESULT,
    ],
)
def test_rejects_incompatible_artifact_media_type(
    experiment_config,
    interpretation_report: InterpretationReport,
    kind: ArtifactKind,
) -> None:
    incompatible = _artifact(
        artifact_id=f"{kind.value}.csv",
        kind=kind,
        media_type="text/csv",
    )

    experiment = _experiment_result(
        config=experiment_config,
        validation_artifact=(
            incompatible
            if kind is ArtifactKind.VALIDATION_RESULT
            else None
        ),
        knowledge_artifact=(
            incompatible
            if kind is ArtifactKind.KNOWLEDGE_RESULT
            else None
        ),
    )

    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseInputError,
        match="unsupported media type",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert exc_info.value.context["artifact_id"] == incompatible.id
    assert exc_info.value.context["media_type"] == "text/csv"

def test_rejects_artifact_without_sha256(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    validation_artifact = _artifact(
        artifact_id="validation.result",
        kind=ArtifactKind.VALIDATION_RESULT,
        sha256=None,
        size_bytes=None,
    )

    experiment = _experiment_result(
        config=experiment_config,
        validation_artifact=validation_artifact,
    )
    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseIntegrityError,
        match="SHA-256",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert exc_info.value.context["artifact_id"] == "validation.result"

def test_rejects_interpretation_report_from_different_run(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(config=experiment_config)

    incompatible_report = replace(
        interpretation_report,
        pipeline_run_id="different-run",
    )

    with pytest.raises(
        RootCauseIntegrityError,
        match="pipeline_run_id",
    ):
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=incompatible_report,
            ),
            created_at=NOW,
        )

def test_rejects_missing_upstream_stage(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(config=experiment_config)

    experiment = replace(
        experiment,
        stage_results=tuple(
            stage
            for stage in experiment.stage_results
            if stage.stage is not ExperimentStage.VALIDATION
        ),
    )
    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseInputError,
        match="missing required upstream stages",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert exc_info.value.context["missing_stages"] == (
        "validation",
    )

def test_rejects_failed_upstream_stage(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(
        config=experiment_config,
        stage_overrides={
            ExperimentStage.KNOWLEDGE_ENRICHMENT:
                ExecutionStatus.FAILED,
        },
    )
    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseInputError,
        match="upstream scientific stages",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert exc_info.value.context["stage_statuses"] == {
        "knowledge_enrichment": "failed",
    }

def test_rejects_missing_simulator_run(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    experiment = _experiment_result(config=experiment_config)
    experiment = replace(
        experiment,
        simulator_runs=tuple(
            run
            for run in experiment.simulator_runs
            if run.simulator is not SimulatorKind.PSYNTHEA
        ),
    )
    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseInputError,
        match="both Synthea and Psynthea",
    ) as exc_info:
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

    assert exc_info.value.context["missing_simulators"] == (
        "psynthea",
    )

def test_rejects_conflicting_artifact_references(
    experiment_config,
    interpretation_report: InterpretationReport,
) -> None:
    first = _artifact(
        artifact_id="validation.result",
        kind=ArtifactKind.VALIDATION_RESULT,
    )
    conflicting = ArtifactReference(
        id=first.id,
        kind=ArtifactKind.VALIDATION_RESULT,
        path=Path("other/validation.json"),
        media_type="application/json",
        created_at=NOW,
        sha256="b" * 64,
        size_bytes=200,
        producer="other",
    )

    experiment = _experiment_result(
        config=experiment_config,
        validation_artifact=first,
    )
    experiment = replace(
        experiment,
        artifacts=(conflicting,),
    )

    report = replace(
        interpretation_report,
        pipeline_run_id=experiment.run_id,
    )

    with pytest.raises(
        RootCauseIntegrityError,
        match="Conflicting artefact references",
    ):
        RootCauseRequestAdapter().build(
            RootCauseRequestSource(
                experiment_result=experiment,
                interpretation_report=report,
            ),
            created_at=NOW,
        )

