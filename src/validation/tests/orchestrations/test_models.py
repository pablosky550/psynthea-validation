from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
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

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=2)
DIGEST = "a" * 64


def _cohort(**overrides: object) -> CohortConfig:
    values: dict[str, object] = {
        "population": 10_000,
        "seed": 42,
        "modules": ("hypertension",),
        "reference_date": date(2026, 7, 14),
        "min_age": 18,
        "max_age": 90,
        "parameters": {"profile": {"country": "ES"}},
    }
    values.update(overrides)
    return CohortConfig(**values)  # type: ignore[arg-type]


def _simulator(kind: SimulatorKind, **overrides: object) -> SimulatorConfig:
    values: dict[str, object] = {
        "kind": kind,
        "command": ("python", "-m", kind.value),
        "working_directory": Path(f"repos/{kind.value}"),
        "output_subdirectory": kind.value,
        "timeout_seconds": 600.0,
        "environment": {"PYTHONHASHSEED": "0"},
        "arguments": {"export": {"csv": True}},
        "expected_output_files": ("csv/patients.csv",),
    }
    values.update(overrides)
    return SimulatorConfig(**values)  # type: ignore[arg-type]


def _config(**overrides: object) -> ExperimentConfig:
    values: dict[str, object] = {
        "id": "hypertension-equivalence",
        "name": "Hypertension equivalence",
        "cohort": _cohort(),
        "simulators": (
            _simulator(SimulatorKind.SYNTHEA),
            _simulator(SimulatorKind.PSYNTHEA),
        ),
        "output_root": Path("runs"),
        "report_formats": (ReportFormat.HTML, ReportFormat.PDF),
        "description": "Deterministic comparison.",
        "tags": ("phase-2b", "hypertension"),
        "metadata": {"protocol": {"version": 1}},
    }
    values.update(overrides)
    return ExperimentConfig(**values)  # type: ignore[arg-type]


def _artifact(identifier: str = "validation.metrics", **overrides: object) -> ArtifactReference:
    values: dict[str, object] = {
        "id": identifier,
        "kind": ArtifactKind.VALIDATION_RESULT,
        "path": Path("validation/metrics.json"),
        "media_type": "application/json",
        "created_at": NOW,
        "sha256": DIGEST,
        "size_bytes": 128,
        "producer": "validation_engine",
        "metadata": {"schema": {"version": 1}},
    }
    values.update(overrides)
    return ArtifactReference(**values)  # type: ignore[arg-type]


def _run(kind: SimulatorKind, **overrides: object) -> SimulatorRunResult:
    artifact = _artifact(
        f"{kind.value}.patients",
        kind=ArtifactKind.SIMULATOR_OUTPUT,
        path=Path(f"{kind.value}/csv/patients.csv"),
        producer=f"{kind.value}_runner",
    )
    values: dict[str, object] = {
        "id": f"run.{kind.value}",
        "simulator": kind,
        "status": ExecutionStatus.SUCCEEDED,
        "command": ("python", "-m", kind.value),
        "working_directory": Path(f"repos/{kind.value}"),
        "started_at": NOW,
        "finished_at": LATER,
        "duration_seconds": 2.0,
        "return_code": 0,
        "artifacts": (artifact,),
        "metadata": {"version": "test"},
    }
    values.update(overrides)
    return SimulatorRunResult(**values)  # type: ignore[arg-type]


def _stage(stage: ExperimentStage, **overrides: object) -> PipelineStageResult:
    artifact = _artifact(
        f"stage.{stage.value}",
        kind=ArtifactKind.OTHER,
        path=Path(f"stages/{stage.value}.json"),
        producer=stage.value,
    )
    values: dict[str, object] = {
        "id": f"stage.{stage.value}",
        "stage": stage,
        "status": ExecutionStatus.SUCCEEDED,
        "started_at": NOW,
        "finished_at": LATER,
        "duration_seconds": 2.0,
        "artifacts": (artifact,),
        "summary": f"Completed {stage.value}.",
    }
    values.update(overrides)
    return PipelineStageResult(**values)  # type: ignore[arg-type]


def _required_stages() -> tuple[PipelineStageResult, ...]:
    return tuple(
        _stage(stage)
        for stage in (
            ExperimentStage.WORKSPACE_INITIALIZATION,
            ExperimentStage.COHORT_LOADING,
            ExperimentStage.COHORT_NORMALIZATION,
            ExperimentStage.VALIDATION,
            ExperimentStage.KNOWLEDGE_ENRICHMENT,
            ExperimentStage.REPORT_GENERATION,
            ExperimentStage.MANIFEST_FINALIZATION,
        )
    )


def _successful_result(**overrides: object) -> ExperimentResult:
    runs = (_run(SimulatorKind.SYNTHEA), _run(SimulatorKind.PSYNTHEA))
    stages = _required_stages()
    artifacts = tuple(
        artifact
        for item in (*runs, *stages)
        for artifact in item.artifacts
    )
    values: dict[str, object] = {
        "experiment_id": "hypertension-equivalence",
        "run_id": "run-20260714-001",
        "status": ExecutionStatus.SUCCEEDED,
        "config": _config(),
        "workspace": Path("runs/hypertension-equivalence/run-20260714-001"),
        "simulator_runs": runs,
        "stage_results": stages,
        "artifacts": artifacts,
        "started_at": NOW,
        "finished_at": LATER,
        "duration_seconds": 2.0,
        "metadata": {"git": {"commit": "abc123"}},
    }
    values.update(overrides)
    return ExperimentResult(**values)  # type: ignore[arg-type]


def test_cohort_normalizes_deduplicates_and_deep_freezes_values() -> None:
    parameters = {"profile": {"regions": ["Madrid"]}}
    cohort = _cohort(modules=("hypertension", "hypertension"), parameters=parameters)
    parameters["profile"]["regions"].append("Galicia")

    assert cohort.modules == ("hypertension",)
    assert cohort.parameters["profile"]["regions"] == ("Madrid",)
    with pytest.raises(TypeError):
        cohort.parameters["new"] = True


def test_cohort_rejects_invalid_population_age_window_seed_and_mapping_keys() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        _cohort(population=0)
    with pytest.raises(ValueError, match="min_age must not exceed"):
        _cohort(min_age=91, max_age=90)
    with pytest.raises(ValueError, match="signed 64-bit"):
        _cohort(seed=2**63)
    with pytest.raises(TypeError, match="mapping keys must be strings"):
        _cohort(parameters={1: "invalid"})


def test_simulator_config_normalizes_values_and_exposes_immutable_mappings() -> None:
    config = _simulator(
        SimulatorKind.SYNTHEA,
        command=(" ./gradlew ", "run", "run"),
        expected_output_files=("csv/patients.csv", "csv/patients.csv"),
    )

    assert config.command == ("./gradlew", "run")
    assert config.expected_output_files == ("csv/patients.csv",)
    assert config.timeout_seconds == 600.0
    with pytest.raises(TypeError):
        config.environment["JAVA_HOME"] = "/tmp/java"


def test_simulator_config_rejects_unsafe_expected_output_paths_and_raw_enum() -> None:
    with pytest.raises(ValueError, match="must not escape"):
        _simulator(SimulatorKind.SYNTHEA, expected_output_files=("../patients.csv",))
    with pytest.raises(ValueError, match="relative to the experiment workspace"):
        _simulator(SimulatorKind.SYNTHEA, expected_output_files=("/tmp/patients.csv",))
    with pytest.raises(TypeError, match="SimulatorKind"):
        SimulatorConfig(
            kind="synthea",  # type: ignore[arg-type]
            command=("python", "-m", "synthea"),
            working_directory=Path("repos/synthea"),
            output_subdirectory="synthea",
        )


def test_experiment_config_requires_exactly_one_of_each_simulator() -> None:
    with pytest.raises(ValueError, match="exactly one Synthea"):
        _config(simulators=(_simulator(SimulatorKind.SYNTHEA),))
    with pytest.raises(ValueError, match="exactly one Synthea"):
        _config(
            simulators=(
                _simulator(SimulatorKind.SYNTHEA),
                _simulator(SimulatorKind.SYNTHEA, output_subdirectory="synthea-2"),
            )
        )


def test_experiment_config_normalizes_report_formats_tags_and_lookup() -> None:
    config = _config(
        report_formats=(ReportFormat.HTML, ReportFormat.HTML, ReportFormat.PDF),
        tags=(" phase-2b ", "phase-2b"),
    )

    assert config.report_formats == (ReportFormat.HTML, ReportFormat.PDF)
    assert config.tags == ("phase-2b",)
    assert config.simulator(SimulatorKind.PSYNTHEA).kind is SimulatorKind.PSYNTHEA
    with pytest.raises(TypeError, match="SimulatorKind"):
        config.simulator("psynthea")  # type: ignore[arg-type]


def test_artifact_normalizes_datetime_digest_and_freezes_metadata() -> None:
    local = datetime(2026, 7, 14, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    metadata = {"schema": {"columns": ["person_id"]}}
    artifact = _artifact(created_at=local, sha256="A" * 64, metadata=metadata)
    metadata["schema"]["columns"].append("birthdate")

    assert artifact.created_at == NOW
    assert artifact.sha256 == DIGEST
    assert artifact.metadata["schema"]["columns"] == ("person_id",)


def test_artifact_rejects_missing_or_naive_time_unsafe_path_and_incomplete_digest() -> None:
    with pytest.raises(TypeError, match="created_at must be a datetime"):
        _artifact(created_at=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        _artifact(created_at=datetime(2026, 7, 14, 10, 0))
    with pytest.raises(ValueError, match="must not escape"):
        _artifact(path=Path("../secret.json"))
    with pytest.raises(ValueError, match="size_bytes is required"):
        _artifact(size_bytes=None)


def test_successful_simulator_run_accepts_zero_duration_and_is_immutable() -> None:
    run = _run(
        SimulatorKind.SYNTHEA,
        finished_at=NOW,
        duration_seconds=0.0,
    )

    assert run.duration_seconds == 0.0
    with pytest.raises(FrozenInstanceError):
        run.status = ExecutionStatus.FAILED  # type: ignore[misc]


def test_simulator_run_enforces_status_specific_contracts() -> None:
    with pytest.raises(ValueError, match="return_code == 0"):
        _run(SimulatorKind.SYNTHEA, return_code=1)
    with pytest.raises(ValueError, match="requires error_message"):
        _run(
            SimulatorKind.SYNTHEA,
            status=ExecutionStatus.FAILED,
            return_code=1,
        )
    with pytest.raises(ValueError, match="non-terminal simulator run"):
        _run(
            SimulatorKind.SYNTHEA,
            status=ExecutionStatus.RUNNING,
            finished_at=None,
            duration_seconds=None,
            return_code=0,
        )
    with pytest.raises(ValueError, match="cannot contain execution timing"):
        _run(
            SimulatorKind.SYNTHEA,
            status=ExecutionStatus.SKIPPED,
            return_code=None,
            started_at=NOW,
            finished_at=None,
            duration_seconds=None,
        )


def test_pipeline_stage_enforces_failure_and_pending_contracts() -> None:
    with pytest.raises(ValueError, match="requires error_message"):
        _stage(ExperimentStage.VALIDATION, status=ExecutionStatus.FAILED)
    pending = _stage(
        ExperimentStage.VALIDATION,
        status=ExecutionStatus.PENDING,
        started_at=None,
        finished_at=None,
        duration_seconds=None,
        artifacts=(),
        summary=None,
    )
    assert pending.status is ExecutionStatus.PENDING


def test_models_reject_duplicate_artifact_ids() -> None:
    artifact = _artifact()
    with pytest.raises(ValueError, match="duplicate id"):
        _run(SimulatorKind.SYNTHEA, artifacts=(artifact, artifact))
    with pytest.raises(ValueError, match="duplicate id"):
        _stage(ExperimentStage.VALIDATION, artifacts=(artifact, artifact))


def test_successful_experiment_exposes_runs_stages_and_artifact_filters() -> None:
    result = _successful_result()

    assert result.synthea_run is not None
    assert result.psynthea_run is not None
    assert result.stage(ExperimentStage.VALIDATION) is not None
    assert result.stage(ExperimentStage.SYNTHEA_EXECUTION) is None
    assert len(result.artifacts_of_kind(ArtifactKind.SIMULATOR_OUTPUT)) == 2


def test_successful_experiment_requires_both_successful_simulator_runs() -> None:
    only_synthea = (_run(SimulatorKind.SYNTHEA),)
    with pytest.raises(ValueError, match="both simulators"):
        _successful_result(simulator_runs=only_synthea)

    failed = _run(
        SimulatorKind.PSYNTHEA,
        status=ExecutionStatus.FAILED,
        return_code=1,
        error_message="Execution failed.",
    )
    with pytest.raises(ValueError, match="unsuccessful simulator runs"):
        _successful_result(simulator_runs=(_run(SimulatorKind.SYNTHEA), failed))


def test_successful_experiment_requires_every_mandatory_stage() -> None:
    stages = tuple(
        stage
        for stage in _required_stages()
        if stage.stage is not ExperimentStage.REPORT_GENERATION
    )
    with pytest.raises(ValueError, match="missing required pipeline stages"):
        _successful_result(stage_results=stages)


def test_successful_experiment_rejects_incomplete_or_failed_stage() -> None:
    stages = list(_required_stages())
    stages[-2] = _stage(
        ExperimentStage.REPORT_GENERATION,
        status=ExecutionStatus.FAILED,
        error_message="Renderer failed.",
    )
    with pytest.raises(ValueError, match="incomplete pipeline stages"):
        _successful_result(stage_results=tuple(stages))


def test_successful_experiment_requires_complete_consistent_artifact_catalogue() -> None:
    result = _successful_result()
    missing = result.artifacts[1:]
    with pytest.raises(ValueError, match="missing nested artefacts"):
        _successful_result(artifacts=missing)

    replacement = _artifact(
        result.artifacts[0].id,
        kind=result.artifacts[0].kind,
        path=Path("different/path.json"),
    )
    inconsistent = (replacement, *result.artifacts[1:])
    with pytest.raises(ValueError, match="inconsistent artefact references"):
        _successful_result(artifacts=inconsistent)


def test_experiment_result_rejects_identity_mismatch_duplicate_kinds_and_duplicate_stages() -> None:
    with pytest.raises(ValueError, match="must match config.id"):
        _successful_result(experiment_id="different")
    run = _run(SimulatorKind.SYNTHEA)
    with pytest.raises(ValueError, match="at most one result per simulator"):
        ExperimentResult(
            experiment_id="hypertension-equivalence",
            run_id="duplicate-runs",
            status=ExecutionStatus.RUNNING,
            config=_config(),
            workspace=Path("runs/duplicate-runs"),
            simulator_runs=(run, _run(SimulatorKind.SYNTHEA, id="run.synthea.2")),
            started_at=NOW,
        )
    stage = _stage(ExperimentStage.VALIDATION)
    with pytest.raises(ValueError, match="at most one result per experiment stage"):
        ExperimentResult(
            experiment_id="hypertension-equivalence",
            run_id="duplicate-stages",
            status=ExecutionStatus.RUNNING,
            config=_config(),
            workspace=Path("runs/duplicate-stages"),
            stage_results=(stage, _stage(ExperimentStage.VALIDATION, id="stage.validation.2")),
            started_at=NOW,
        )


def test_failed_experiment_requires_error_and_running_experiment_forbids_it() -> None:
    with pytest.raises(ValueError, match="failed experiment requires error_message"):
        ExperimentResult(
            experiment_id="hypertension-equivalence",
            run_id="failed-run",
            status=ExecutionStatus.FAILED,
            config=_config(),
            workspace=Path("runs/failed-run"),
            started_at=NOW,
            finished_at=LATER,
        )
    with pytest.raises(ValueError, match="non-terminal experiment"):
        ExperimentResult(
            experiment_id="hypertension-equivalence",
            run_id="running-run",
            status=ExecutionStatus.RUNNING,
            config=_config(),
            workspace=Path("runs/running-run"),
            started_at=NOW,
            error_message="Not terminal yet.",
        )


def test_execution_windows_reject_naive_reversed_or_negative_times() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _run(SimulatorKind.SYNTHEA, started_at=datetime(2026, 7, 14, 10, 0))
    with pytest.raises(ValueError, match="must not precede"):
        _run(SimulatorKind.SYNTHEA, started_at=LATER, finished_at=NOW)
    with pytest.raises(ValueError, match="non-negative"):
        _run(SimulatorKind.SYNTHEA, duration_seconds=-0.1)


def test_public_lookup_methods_reject_raw_enums() -> None:
    result = _successful_result()
    with pytest.raises(TypeError, match="ExperimentStage"):
        result.stage("validation")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ArtifactKind"):
        result.artifacts_of_kind("report")  # type: ignore[arg-type]