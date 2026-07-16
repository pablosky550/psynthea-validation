from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

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
    OrchestrationContext,
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
    def __init__(
        self,
        kind: SimulatorKind,
        *,
        fail: bool = False,
    ) -> None:
        self.kind = kind
        self.fail = fail

    def run(
        self,
        *,
        experiment,
        workspace,
        run_id,
    ) -> SimulatorRunResult:
        started = datetime.now(UTC)
        path = workspace.write_text(
            Path("simulators")
            / self.kind.value
            / "raw"
            / f"{self.kind.value}.csv",
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
            status=(
                ExecutionStatus.FAILED
                if self.fail
                else ExecutionStatus.SUCCEEDED
            ),
            command=(self.kind.value,),
            working_directory=(
                experiment.simulator(self.kind).working_directory
            ),
            started_at=started,
            finished_at=finished,
            duration_seconds=0.0,
            return_code=1 if self.fail else 0,
            artifacts=(artifact,),
            error_message=(
                f"{self.kind.value} failed"
                if self.fail
                else None
            ),
        )


@dataclass
class RecordingHandler:
    stage: ExperimentStage
    calls: list[ExperimentStage]
    fail: bool = False
    duplicate_id: str | None = None
    metadata: dict[str, Any] | None = None

    def execute(
        self,
        context: OrchestrationContext,
    ) -> StageOutput:
        self.calls.append(self.stage)

        if self.fail:
            raise RuntimeError("stage exploded")

        if self.stage is ExperimentStage.ROOT_CAUSE_ANALYSIS:
            path = context.workspace.write_text(
                "root_cause/root_cause_result.json",
                '{"status":"not_applicable","findings":[]}\n',
            )
            artifact = context.workspace.artifact_reference(
                artifact_id=(
                    self.duplicate_id
                    or "root_cause.result"
                ),
                kind=ArtifactKind.ROOT_CAUSE_RESULT,
                path=path,
                media_type="application/json",
                producer="root_cause_engine",
            )

            root_cause_metadata = {
                "root_cause_status": "not_applicable",
                "finding_count": 0,
            }
            if self.metadata:
                root_cause_metadata.update(self.metadata)

            return StageOutput(
                artifacts=(artifact,),
                summary="Root-cause analysis completed.",
                metadata=root_cause_metadata,
            )

        path = context.workspace.write_text(
            f"stages/{self.stage.value}.json",
            "{}\n",
        )
        artifact = context.workspace.artifact_reference(
            artifact_id=(
                self.duplicate_id
                or f"{self.stage.value}.result"
            ),
            kind=_artifact_kind_for_stage(self.stage),
            path=path,
            media_type="application/json",
            producer=self.stage.value,
        )

        return StageOutput(
            artifacts=(artifact,),
            summary=f"{self.stage.value} completed.",
            metadata=dict(self.metadata or {}),
        )


def make_handlers(
    *,
    fail_stage: ExperimentStage | None = None,
    duplicate_stage: ExperimentStage | None = None,
    duplicate_id: str | None = None,
    calls: list[ExperimentStage] | None = None,
) -> tuple[RecordingHandler, ...]:
    calls = calls if calls is not None else []
    stages = (
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.ROOT_CAUSE_ANALYSIS,
        ExperimentStage.REPORT_GENERATION,
    )

    return tuple(
        RecordingHandler(
            stage=stage,
            calls=calls,
            fail=stage is fail_stage,
            duplicate_id=(
                duplicate_id
                if stage is duplicate_stage
                else None
            ),
        )
        for stage in stages
    )


def runner_factory(
    *,
    fail_kind: SimulatorKind | None = None,
):
    def factory(config):
        return FakeRunner(
            config.kind,
            fail=config.kind is fail_kind,
        )

    return factory


def test_successful_experiment_runs_complete_pipeline_and_manifest(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(calls=calls),
        runner_factory=runner_factory(),
        orchestrator_version="2.0.0",
    )

    execution = orchestrator.execute(
        config,
        run_id="run-001",
    )

    assert execution.result.status is ExecutionStatus.SUCCEEDED
    assert [
        run.simulator
        for run in execution.result.simulator_runs
    ] == [
        SimulatorKind.SYNTHEA,
        SimulatorKind.PSYNTHEA,
    ]
    assert calls == [
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.ROOT_CAUSE_ANALYSIS,
        ExperimentStage.REPORT_GENERATION,
    ]
    assert execution.manifest is not None
    assert (
        execution.result.workspace / "manifest.json"
    ).is_file()
    assert execution.manifest.sha256 is not None
    assert len(execution.result.artifacts) == 8

    root_cause_artifacts = tuple(
        artifact
        for artifact in execution.result.artifacts
        if artifact.kind is ArtifactKind.ROOT_CAUSE_RESULT
    )
    assert len(root_cause_artifacts) == 1


def test_simulator_failure_skips_all_dependent_stages_and_writes_manifest(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(calls=calls),
        runner_factory=runner_factory(
            fail_kind=SimulatorKind.SYNTHEA
        ),
    )

    execution = orchestrator.execute(
        config,
        run_id="run-failed",
    )

    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.result.error_message == "synthea failed"
    assert calls == []

    external = {
        item.stage: item.status
        for item in execution.result.stage_results
        if item.stage
        in {
            ExperimentStage.COHORT_LOADING,
            ExperimentStage.COHORT_NORMALIZATION,
            ExperimentStage.VALIDATION,
            ExperimentStage.KNOWLEDGE_ENRICHMENT,
            ExperimentStage.ROOT_CAUSE_ANALYSIS,
            ExperimentStage.REPORT_GENERATION,
        }
    }
    assert set(external.values()) == {
        ExecutionStatus.SKIPPED
    }
    assert execution.manifest is not None


def test_policy_can_stop_before_second_simulator(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(
            fail_kind=SimulatorKind.SYNTHEA
        ),
        policy=OrchestrationPolicy(
            continue_simulators_after_failure=False
        ),
    )

    execution = orchestrator.execute(
        config,
        run_id="run-stop",
    )

    assert [
        item.simulator
        for item in execution.result.simulator_runs
    ] == [SimulatorKind.SYNTHEA]
    assert execution.result.status is ExecutionStatus.FAILED


def test_stage_exception_becomes_failed_stage_and_stops_downstream(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(
            fail_stage=ExperimentStage.VALIDATION,
            calls=calls,
        ),
        runner_factory=runner_factory(),
    )

    execution = orchestrator.execute(
        config,
        run_id="run-stage-failure",
    )

    assert execution.result.status is ExecutionStatus.FAILED
    failed = next(
        item
        for item in execution.result.stage_results
        if item.stage is ExperimentStage.VALIDATION
    )
    assert failed.status is ExecutionStatus.FAILED
    assert failed.error_message == (
        "RuntimeError: stage exploded"
    )
    assert calls == [
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
    ]

    downstream = {
        item.stage: item.status
        for item in execution.result.stage_results
    }
    assert (
        downstream[ExperimentStage.KNOWLEDGE_ENRICHMENT]
        is ExecutionStatus.SKIPPED
    )
    assert (
        downstream[ExperimentStage.ROOT_CAUSE_ANALYSIS]
        is ExecutionStatus.SKIPPED
    )
    assert (
        downstream[ExperimentStage.REPORT_GENERATION]
        is ExecutionStatus.SKIPPED
    )


def test_duplicate_artifact_id_across_stages_is_rejected(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    handlers = list(make_handlers())
    handlers[0].duplicate_id = "shared.artifact"
    handlers[1].duplicate_id = "shared.artifact"
    orchestrator = ExperimentOrchestrator(
        tuple(handlers),
        runner_factory=runner_factory(),
    )

    with pytest.raises(
        OrchestrationIntegrityError,
        match="produced more than once",
    ):
        orchestrator.execute(
            config,
            run_id="run-duplicate",
        )


def test_invalid_stage_artifact_hash_fails_loudly(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    @dataclass
    class TamperingHandler:
        stage: ExperimentStage

        def execute(
            self,
            context: OrchestrationContext,
        ) -> StageOutput:
            path = context.workspace.write_text(
                "cohort_loading/result.json",
                "{}",
            )
            artifact = context.workspace.artifact_reference(
                artifact_id="tampered",
                kind=ArtifactKind.NORMALIZED_DATASET,
                path=path,
                media_type="application/json",
            )
            path.write_text(
                "changed",
                encoding="utf-8",
            )
            return StageOutput(
                artifacts=(artifact,)
            )

    handlers = list(make_handlers())
    handlers[0] = TamperingHandler(
        ExperimentStage.COHORT_LOADING
    )
    orchestrator = ExperimentOrchestrator(
        tuple(handlers),
        runner_factory=runner_factory(),
    )

    with pytest.raises(
        OrchestrationStageError,
        match="invalid SHA-256",
    ):
        orchestrator.execute(
            config,
            run_id="run-tamper",
        )


def test_manifest_can_be_disabled_for_failed_experiment(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(
            fail_kind=SimulatorKind.SYNTHEA
        ),
        policy=OrchestrationPolicy(
            write_manifest_on_failure=False
        ),
    )

    execution = orchestrator.execute(
        config,
        run_id="run-no-manifest",
    )

    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.manifest is None
    assert not (
        execution.result.workspace / "manifest.json"
    ).exists()


def test_reserved_handler_metadata_cannot_override_handler_identity(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    handlers = list(make_handlers())
    handlers[0].metadata = {
        "handler": "forged",
        "custom": 1,
    }
    orchestrator = ExperimentOrchestrator(
        tuple(handlers),
        runner_factory=runner_factory(),
    )

    execution = orchestrator.execute(
        config,
        run_id="run-metadata",
    )

    loading = next(
        item
        for item in execution.result.stage_results
        if item.stage is ExperimentStage.COHORT_LOADING
    )
    assert loading.metadata["handler"] == "RecordingHandler"
    assert loading.metadata["custom"] == 1


def test_auto_run_id_uses_injected_clock(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    fixed = datetime(
        2026,
        7,
        14,
        10,
        30,
        15,
        123456,
        tzinfo=UTC,
    )
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(),
        clock=lambda: fixed,
    )

    execution = orchestrator.execute(config)

    assert execution.result.run_id.startswith(
        "run-20260714T103015123456Z-"
    )


def test_handler_registration_requires_all_external_stages() -> None:
    handlers = make_handlers()[:-1]

    with pytest.raises(
        ValueError,
        match="Missing required stage handler",
    ):
        ExperimentOrchestrator(
            handlers,
            runner_factory=runner_factory(),
        )


@pytest.mark.parametrize(
    "stage",
    (
        ExperimentStage.WORKSPACE_INITIALIZATION,
        ExperimentStage.MANIFEST_FINALIZATION,
    ),
)
def test_internal_stage_handler_registration_is_rejected(
    stage: ExperimentStage,
) -> None:
    handler = RecordingHandler(
        stage=stage,
        calls=[],
    )

    with pytest.raises(
        ValueError,
        match=(
            "managed internally and cannot be registered "
            "as an external handler"
        ),
    ):
        ExperimentOrchestrator(
            handlers=(handler,),
            runner_factory=runner_factory(),
            orchestrator_version="2.0.0",
        )


def test_non_protocol_runner_from_factory_is_rejected(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=lambda config: object(),
    )

    with pytest.raises(
        OrchestrationIntegrityError,
        match="RunnerAdapter",
    ):
        orchestrator.execute(
            config,
            run_id="run-bad-runner",
        )


def test_manifest_failure_is_raised_as_finalization_error(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    class BrokenManifest:
        def write(self, *args, **kwargs):
            from validation.orchestration.manifest import (
                ManifestIntegrityError,
            )

            raise ManifestIntegrityError("broken")

    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(),
        manifest_factory=(
            lambda *args, **kwargs: BrokenManifest()
        ),
    )

    with pytest.raises(
        OrchestrationFinalizationError
    ):
        orchestrator.execute(
            config,
            run_id="run-broken-manifest",
        )


def test_root_cause_runs_after_knowledge_and_before_report(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    calls: list[ExperimentStage] = []
    orchestrator = ExperimentOrchestrator(
        make_handlers(calls=calls),
        runner_factory=runner_factory(),
        orchestrator_version="2.0.0",
    )

    execution = orchestrator.execute(
        config,
        run_id="root-cause-order",
    )

    assert execution.result.status is ExecutionStatus.SUCCEEDED
    assert calls == [
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.ROOT_CAUSE_ANALYSIS,
        ExperimentStage.REPORT_GENERATION,
    ]

    knowledge_index = calls.index(
        ExperimentStage.KNOWLEDGE_ENRICHMENT
    )
    root_cause_index = calls.index(
        ExperimentStage.ROOT_CAUSE_ANALYSIS
    )
    report_index = calls.index(
        ExperimentStage.REPORT_GENERATION
    )

    assert knowledge_index < root_cause_index < report_index


def test_root_cause_artifact_is_added_to_experiment_result(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(),
        orchestrator_version="2.0.0",
    )

    execution = orchestrator.execute(
        config,
        run_id="root-cause-artifact",
    )

    root_cause_artifacts = tuple(
        artifact
        for artifact in execution.result.artifacts
        if artifact.kind is ArtifactKind.ROOT_CAUSE_RESULT
    )
    assert len(root_cause_artifacts) == 1

    root_cause_stage = next(
        stage
        for stage in execution.result.stage_results
        if stage.stage
        is ExperimentStage.ROOT_CAUSE_ANALYSIS
    )

    assert (
        root_cause_stage.status
        is ExecutionStatus.SUCCEEDED
    )
    assert (
        root_cause_artifacts[0]
        in root_cause_stage.artifacts
    )


def test_manifest_contains_root_cause_stage_and_artifact(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        make_handlers(),
        runner_factory=runner_factory(),
        orchestrator_version="2.0.0",
    )

    execution = orchestrator.execute(
        config,
        run_id="root-cause-manifest",
    )

    assert execution.manifest is not None

    manifest_path = (
        execution.result.workspace
        / execution.manifest.path
    )
    payload = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    stages = {
        item["stage"]: item
        for item in payload["result"]["stage_results"]
    }
    assert (
        stages["root_cause_analysis"]["status"]
        == "succeeded"
    )

    artifact_kinds = {
        item["kind"]
        for item in payload["result"]["artifacts"]
    }
    assert "root_cause_result" in artifact_kinds


def _artifact_kind_for_stage(
    stage: ExperimentStage,
) -> ArtifactKind:
    mapping = {
        ExperimentStage.COHORT_LOADING:
            ArtifactKind.SIMULATOR_OUTPUT,
        ExperimentStage.COHORT_NORMALIZATION:
            ArtifactKind.NORMALIZED_DATASET,
        ExperimentStage.VALIDATION:
            ArtifactKind.VALIDATION_RESULT,
        ExperimentStage.KNOWLEDGE_ENRICHMENT:
            ArtifactKind.KNOWLEDGE_RESULT,
        ExperimentStage.REPORT_GENERATION:
            ArtifactKind.REPORT,
    }

    try:
        return mapping[stage]
    except KeyError as exc:
        raise ValueError(
            "No test artifact kind configured for stage "
            f"{stage.value!r}."
        ) from exc