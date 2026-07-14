from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from validation.orchestration.manifest import ExperimentManifest
from validation.orchestration.models import (
    ArtifactKind,
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    ExperimentStage,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.orchestration.orchestrator import (
    ExperimentOrchestrator,
    OrchestrationFinalizationError,
    OrchestrationIntegrityError,
    OrchestrationPolicy,
    OrchestrationStageError,
    StageOutput,
)


def make_config(tmp_path: Path) -> ExperimentConfig:
    synthea_dir = tmp_path / "synthea"
    psynthea_dir = tmp_path / "psynthea"
    synthea_dir.mkdir()
    psynthea_dir.mkdir()
    return ExperimentConfig(
        id="hypertension-validation",
        name="Hypertension equivalence",
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
                working_directory=synthea_dir,
                output_subdirectory="cohort",
            ),
            SimulatorConfig(
                kind=SimulatorKind.PSYNTHEA,
                command=("psynthea",),
                working_directory=psynthea_dir,
                output_subdirectory="cohort",
            ),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.HTML,),
    )


class FakeRunner:
    def __init__(self, kind: SimulatorKind, *, fail: bool = False) -> None:
        self.kind = kind
        self.fail = fail

    def run(self, *, experiment, workspace, run_id):
        started = datetime.now(UTC)
        path = workspace.write_text(
            Path("simulators") / self.kind.value / "raw" / f"{self.kind.value}.csv",
            "patient_id\n1\n",
        )
        artifact = workspace.artifact_reference(
            artifact_id=f"{self.kind.value}.cohort",
            kind=ArtifactKind.SIMULATOR_OUTPUT,
            path=path,
            media_type="text/csv",
            producer=f"{self.kind.value}_runner",
        )
        finished = datetime.now(UTC)
        return SimulatorRunResult(
            id=f"{experiment.id}:{run_id}:{self.kind.value}",
            simulator=self.kind,
            status=ExecutionStatus.FAILED if self.fail else ExecutionStatus.SUCCEEDED,
            command=(self.kind.value,),
            working_directory=experiment.simulator(self.kind).working_directory,
            started_at=started,
            finished_at=finished,
            duration_seconds=0.0,
            return_code=1 if self.fail else 0,
            artifacts=(artifact,),
            error_message=f"{self.kind.value} failed" if self.fail else None,
        )


@dataclass
class RecordingHandler:
    stage: ExperimentStage
    calls: list[ExperimentStage]
    fail: bool = False
    duplicate_id: str | None = None
    metadata: dict[str, Any] | None = None

    def execute(self, context):
        self.calls.append(self.stage)
        if self.fail:
            raise RuntimeError("stage exploded")
        relative = Path(self.stage.value) / "result.json"
        path = context.workspace.write_text(relative, "{}\n")
        artifact = context.workspace.artifact_reference(
            artifact_id=self.duplicate_id or f"stage.{self.stage.value}",
            kind=(
                ArtifactKind.REPORT
                if self.stage is ExperimentStage.REPORT_GENERATION
                else ArtifactKind.VALIDATION_RESULT
            ),
            path=path,
            media_type="application/json",
            producer=self.stage.value,
        )
        return StageOutput(
            artifacts=(artifact,),
            summary=f"completed {self.stage.value}",
            metadata=self.metadata or {},
        )


def make_handlers(
    *,
    fail_stage: ExperimentStage | None = None,
    duplicate_stage: ExperimentStage | None = None,
    duplicate_id: str | None = None,
    calls: list[ExperimentStage] | None = None,
):
    calls = calls if calls is not None else []
    stages = (
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.REPORT_GENERATION,
    )
    return tuple(
        RecordingHandler(
            stage,
            calls,
            fail=stage is fail_stage,
            duplicate_id=duplicate_id if stage is duplicate_stage else None,
        )
        for stage in stages
    )


def runner_factory(*, fail_kind: SimulatorKind | None = None):
    def factory(config):
        return FakeRunner(config.kind, fail=config.kind is fail_kind)

    return factory


def test_successful_experiment_runs_complete_pipeline_and_manifest(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(calls=calls),
        runner_factory=runner_factory(),
        orchestrator_version="2.0.0",
    )

    execution = orchestrator.execute(config, run_id="run-001")

    assert execution.result.status is ExecutionStatus.SUCCEEDED
    assert [run.simulator for run in execution.result.simulator_runs] == [
        SimulatorKind.SYNTHEA,
        SimulatorKind.PSYNTHEA,
    ]
    assert calls == [
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.REPORT_GENERATION,
    ]
    assert execution.manifest is not None
    assert (execution.result.workspace / "manifest.json").is_file()
    manifest = ExperimentManifest(
        type("WorkspaceProxy", (), {})  # pragma: no cover
    ) if False else None
    assert execution.manifest.sha256 is not None
    assert len(execution.result.artifacts) == 7


def test_simulator_failure_skips_all_dependent_stages_and_writes_manifest(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(calls=calls),
        runner_factory=runner_factory(fail_kind=SimulatorKind.SYNTHEA),
    )

    execution = orchestrator.execute(config, run_id="run-failed")

    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.result.error_message == "synthea failed"
    assert calls == []
    external = {
        item.stage: item.status
        for item in execution.result.stage_results
        if item.stage in {
            ExperimentStage.COHORT_LOADING,
            ExperimentStage.COHORT_NORMALIZATION,
            ExperimentStage.VALIDATION,
            ExperimentStage.KNOWLEDGE_ENRICHMENT,
            ExperimentStage.REPORT_GENERATION,
        }
    }
    assert set(external.values()) == {ExecutionStatus.SKIPPED}
    assert execution.manifest is not None


def test_policy_can_stop_before_second_simulator(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(fail_kind=SimulatorKind.SYNTHEA),
        policy=OrchestrationPolicy(continue_simulators_after_failure=False),
    )

    execution = orchestrator.execute(config, run_id="run-stop")

    assert [item.simulator for item in execution.result.simulator_runs] == [
        SimulatorKind.SYNTHEA
    ]
    assert execution.result.status is ExecutionStatus.FAILED


def test_stage_exception_becomes_failed_stage_and_stops_downstream(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(
            fail_stage=ExperimentStage.VALIDATION,
            calls=calls,
        ),
        runner_factory=runner_factory(),
    )

    execution = orchestrator.execute(config, run_id="run-stage-failure")

    assert execution.result.status is ExecutionStatus.FAILED
    failed = next(
        item
        for item in execution.result.stage_results
        if item.stage is ExperimentStage.VALIDATION
    )
    assert failed.status is ExecutionStatus.FAILED
    assert failed.error_message == "RuntimeError: stage exploded"
    assert calls == [
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
    ]
    downstream = {
        item.stage: item.status for item in execution.result.stage_results
    }
    assert downstream[ExperimentStage.KNOWLEDGE_ENRICHMENT] is ExecutionStatus.SKIPPED
    assert downstream[ExperimentStage.REPORT_GENERATION] is ExecutionStatus.SKIPPED


def test_duplicate_artifact_id_across_stages_is_rejected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    handlers = list(make_handlers())
    handlers[0].duplicate_id = "shared.artifact"
    handlers[1].duplicate_id = "shared.artifact"
    orchestrator = ExperimentOrchestrator(
        tuple(handlers),
        runner_factory=runner_factory(),
    )

    with pytest.raises(OrchestrationIntegrityError, match="produced more than once"):
        orchestrator.execute(config, run_id="run-duplicate")


def test_invalid_stage_artifact_hash_fails_loudly(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    @dataclass
    class TamperingHandler:
        stage: ExperimentStage

        def execute(self, context):
            path = context.workspace.write_text("cohort_loading/result.json", "{}")
            artifact = context.workspace.artifact_reference(
                artifact_id="tampered",
                kind=ArtifactKind.NORMALIZED_DATASET,
                path=path,
                media_type="application/json",
            )
            path.write_text("changed", encoding="utf-8")
            return StageOutput(artifacts=(artifact,))

    handlers = list(make_handlers())
    handlers[0] = TamperingHandler(ExperimentStage.COHORT_LOADING)
    orchestrator = ExperimentOrchestrator(
        tuple(handlers),
        runner_factory=runner_factory(),
    )

    with pytest.raises(OrchestrationStageError, match="invalid SHA-256"):
        orchestrator.execute(config, run_id="run-tamper")


def test_manifest_can_be_disabled_for_failed_experiment(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(fail_kind=SimulatorKind.SYNTHEA),
        policy=OrchestrationPolicy(write_manifest_on_failure=False),
    )

    execution = orchestrator.execute(config, run_id="run-no-manifest")

    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.manifest is None
    assert not (execution.result.workspace / "manifest.json").exists()


def test_reserved_handler_metadata_cannot_override_handler_identity(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    handlers = list(make_handlers())
    handlers[0].metadata = {"handler": "forged", "custom": 1}
    orchestrator = ExperimentOrchestrator(
        tuple(handlers),
        runner_factory=runner_factory(),
    )

    execution = orchestrator.execute(config, run_id="run-metadata")

    loading = next(
        item
        for item in execution.result.stage_results
        if item.stage is ExperimentStage.COHORT_LOADING
    )
    assert loading.metadata["handler"] == "RecordingHandler"
    assert loading.metadata["custom"] == 1


def test_auto_run_id_uses_injected_clock(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    fixed = datetime(2026, 7, 14, 10, 30, 15, 123456, tzinfo=UTC)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(),
        clock=lambda: fixed,
    )

    execution = orchestrator.execute(config)

    assert execution.result.run_id.startswith("run-20260714T103015123456Z-")


def test_handler_registration_requires_all_external_stages(tmp_path: Path) -> None:
    handlers = make_handlers()[:-1]
    with pytest.raises(ValueError, match="Missing required stage handler"):
        ExperimentOrchestrator(handlers, runner_factory=runner_factory())


def test_internal_stage_handler_registration_is_rejected() -> None:
    handler = RecordingHandler(
        ExperimentStage.WORKSPACE_INITIALIZATION,
        [],
    )
    with pytest.raises(ValueError, match="managed internally"):
        ExperimentOrchestrator((handler,))


def test_non_protocol_runner_from_factory_is_rejected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=lambda config: object(),
    )

    with pytest.raises(OrchestrationIntegrityError, match="RunnerAdapter"):
        orchestrator.execute(config, run_id="run-bad-runner")


def test_manifest_failure_is_raised_as_finalization_error(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    class BrokenManifest:
        def write(self, *args, **kwargs):
            from validation.orchestration.manifest import ManifestIntegrityError
            raise ManifestIntegrityError("broken")

    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(),
        manifest_factory=lambda *args, **kwargs: BrokenManifest(),
    )

    with pytest.raises(OrchestrationFinalizationError):
        orchestrator.execute(config, run_id="run-broken-manifest")