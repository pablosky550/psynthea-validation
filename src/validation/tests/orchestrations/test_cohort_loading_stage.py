from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path

import pandas as pd
import pytest

from validation.constants import (
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.models import ValidationCohort
from validation.orchestration.models import (
    ArtifactKind,
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
)
from validation.orchestration.stages.cohort_loading import (
    CohortLoadingError,
    CohortLoadingStageHandler,
)
from validation.orchestration.workspace import (
    ExperimentWorkspace,
)


_FIXED_TIME = datetime(
    2026,
    7,
    16,
    8,
    0,
    tzinfo=UTC,
)


def _config(
    tmp_path: Path,
) -> ExperimentConfig:
    synthea_home = (
        tmp_path / "external" / "synthea"
    )
    psynthea_home = (
        tmp_path / "external" / "psynthea"
    )

    synthea_home.mkdir(parents=True)
    psynthea_home.mkdir(parents=True)

    return ExperimentConfig(
        id="hypertension-loading",
        name="Hypertension loading",
        cohort=CohortConfig(
            population=2,
            seed=42,
            modules=("hypertension",),
            reference_date=date(2026, 1, 1),
        ),
        simulators=(
            SimulatorConfig(
                kind=SimulatorKind.SYNTHEA,
                command=("synthea",),
                working_directory=synthea_home,
                output_subdirectory="cohort",
            ),
            SimulatorConfig(
                kind=SimulatorKind.PSYNTHEA,
                command=("psynthea",),
                working_directory=psynthea_home,
                output_subdirectory="cohort",
            ),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.JSON,),
    )


def _workspace_and_context(
    tmp_path: Path,
    *,
    include_psynthea: bool = True,
    psynthea_status: ExecutionStatus = (
        ExecutionStatus.SUCCEEDED
    ),
    duplicate_patients: bool = False,
) -> tuple[
    ExperimentWorkspace,
    OrchestrationContext,
]:
    config = _config(tmp_path)

    workspace = ExperimentWorkspace.create(
        config,
        "run-001",
        created_at=_FIXED_TIME,
    )

    runs = [
        _run(
            workspace,
            config,
            SimulatorKind.SYNTHEA,
            offset=0,
            duplicate_patients=(
                duplicate_patients
            ),
        )
    ]

    if include_psynthea:
        runs.append(
            _run(
                workspace,
                config,
                SimulatorKind.PSYNTHEA,
                offset=100,
                status=psynthea_status,
            )
        )

    context = OrchestrationContext(
        config=config,
        workspace=workspace,
        run_id="run-001",
        simulator_runs=tuple(runs),
        stage_results=(),
        artifacts=tuple(
            artifact
            for run in runs
            for artifact in run.artifacts
        ),
    )

    return workspace, context


def _run(
    workspace: ExperimentWorkspace,
    config: ExperimentConfig,
    simulator: SimulatorKind,
    *,
    offset: int,
    status: ExecutionStatus = (
        ExecutionStatus.SUCCEEDED
    ),
    duplicate_patients: bool = False,
) -> SimulatorRunResult:
    output_dir = (
        workspace.simulator_raw_directory(
            simulator
        )
        / "cohort"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    patients_path = workspace.write_text(
        workspace.relative(
            output_dir / "patients.csv"
        ),
        (
            "Id,GENDER,BIRTHDATE\n"
            f"{offset + 1},F,1970-01-01\n"
            f"{offset + 2},M,1960-01-01\n"
        ),
    )

    conditions_path = workspace.write_text(
        workspace.relative(
            output_dir / "conditions.csv"
        ),
        (
            "PATIENT,CODE,START,STOP,DESCRIPTION\n"
            f"{offset + 1},38341003,"
            "2020-01-01,,Hypertension\n"
        ),
    )

    artifacts = [
        workspace.artifact_reference(
            artifact_id=(
                f"{simulator.value}.patients"
            ),
            kind=ArtifactKind.SIMULATOR_OUTPUT,
            path=patients_path,
            media_type="text/csv",
            producer="test_runner",
            created_at=_FIXED_TIME,
        ),
        workspace.artifact_reference(
            artifact_id=(
                f"{simulator.value}.conditions"
            ),
            kind=ArtifactKind.SIMULATOR_OUTPUT,
            path=conditions_path,
            media_type="text/csv",
            producer="test_runner",
            created_at=_FIXED_TIME,
        ),
    ]

    if duplicate_patients:
        duplicate_dir = (
            output_dir / "duplicate"
        )
        duplicate_dir.mkdir()

        duplicate_path = (
            workspace.write_text(
                workspace.relative(
                    duplicate_dir
                    / "patients.csv"
                ),
                (
                    "Id,GENDER,BIRTHDATE\n"
                    "999,F,1980-01-01\n"
                ),
            )
        )

        artifacts.append(
            workspace.artifact_reference(
                artifact_id=(
                    f"{simulator.value}."
                    "patients.duplicate"
                ),
                kind=(
                    ArtifactKind.SIMULATOR_OUTPUT
                ),
                path=duplicate_path,
                media_type="text/csv",
                producer="test_runner",
                created_at=_FIXED_TIME,
            )
        )

    return SimulatorRunResult(
        id=(
            f"{config.id}:run-001:"
            f"{simulator.value}"
        ),
        simulator=simulator,
        status=status,
        command=(simulator.value,),
        working_directory=(
            config.simulator(
                simulator
            ).working_directory
        ),
        started_at=_FIXED_TIME,
        finished_at=_FIXED_TIME,
        duration_seconds=0.0,
        return_code=(
            0
            if status
            is ExecutionStatus.SUCCEEDED
            else 1
        ),
        artifacts=tuple(artifacts),
        error_message=(
            None
            if status
            is ExecutionStatus.SUCCEEDED
            else "failed"
        ),
    )


def test_handler_loads_both_cohorts_and_persists_manifest(
    tmp_path: Path,
) -> None:
    workspace, context = (
        _workspace_and_context(tmp_path)
    )

    handler = CohortLoadingStageHandler(
        clock=lambda: _FIXED_TIME
    )

    output = handler.execute(context)

    assert len(output.artifacts) == 1

    artifact = output.artifacts[0]

    assert (
        artifact.kind
        is ArtifactKind.COHORT_LOAD_RESULT
    )
    assert artifact.created_at == _FIXED_TIME

    assert output.metadata[
        "patient_counts"
    ] == {
        "synthea": 2,
        "psynthea": 2,
    }

    payload = json.loads(
        workspace.resolve(
            artifact.path
        ).read_text()
    )

    assert payload["schema_version"] == "1.0"
    assert payload["requested_population"] == 2

    assert (
        payload["cohorts"]["synthea"]["source"]
        == SOURCE_SYNTHEA
    )
    assert (
        payload["cohorts"]["psynthea"]["source"]
        == SOURCE_PSYNTHEA
    )

    assert (
        payload["cohorts"]["synthea"]
        ["tables"]["patients"]["rows"]
        == 2
    )
    assert (
        payload["cohorts"]["synthea"]
        ["tables"]["conditions"]["rows"]
        == 1
    )
    assert (
        payload["cohorts"]["synthea"]
        ["tables"]["encounters"]["present"]
        is False
    )


def test_handler_uses_injected_loaders(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path
    )

    calls: list[
        tuple[SimulatorKind, Path]
    ] = []

    def loader(
        simulator: SimulatorKind,
        source: str,
    ):
        def load(
            path: str | Path,
        ) -> ValidationCohort:
            path = Path(path)

            calls.append(
                (simulator, path)
            )

            return ValidationCohort(
                source=source,
                output_path=path,
                patients=pd.DataFrame(
                    [{"Id": "p1"}]
                ),
                conditions=pd.DataFrame(
                    [
                        {
                            "PATIENT": "p1",
                            "CODE": 38341003,
                        }
                    ]
                ),
            )

        return load

    handler = CohortLoadingStageHandler(
        loaders={
            SimulatorKind.SYNTHEA: loader(
                SimulatorKind.SYNTHEA,
                SOURCE_SYNTHEA,
            ),
            SimulatorKind.PSYNTHEA: loader(
                SimulatorKind.PSYNTHEA,
                SOURCE_PSYNTHEA,
            ),
        },
        clock=lambda: _FIXED_TIME,
    )

    handler.execute(context)

    assert [
        item[0] for item in calls
    ] == [
        SimulatorKind.SYNTHEA,
        SimulatorKind.PSYNTHEA,
    ]


def test_handler_rejects_missing_simulator_run(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path,
        include_psynthea=False,
    )

    with pytest.raises(
        CohortLoadingError,
        match="Missing simulator run",
    ):
        CohortLoadingStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(context)


def test_handler_rejects_failed_simulator_run(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path,
        psynthea_status=(
            ExecutionStatus.FAILED
        ),
    )

    with pytest.raises(
        CohortLoadingError,
        match="requires successful",
    ):
        CohortLoadingStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(context)


def test_handler_rejects_duplicate_canonical_csv(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path,
        duplicate_patients=True,
    )

    with pytest.raises(
        CohortLoadingError,
        match="duplicate canonical",
    ):
        CohortLoadingStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(context)


def test_handler_rejects_loader_with_wrong_source(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path
    )

    def wrong_loader(
        path: str | Path,
    ) -> ValidationCohort:
        return ValidationCohort(
            source="wrong",
            output_path=Path(path),
            patients=pd.DataFrame(
                [{"Id": "p1"}]
            ),
        )

    handler = CohortLoadingStageHandler(
        loaders={
            SimulatorKind.SYNTHEA: (
                wrong_loader
            ),
            SimulatorKind.PSYNTHEA: (
                wrong_loader
            ),
        },
        clock=lambda: _FIXED_TIME,
    )

    with pytest.raises(
        CohortLoadingError,
        match="returned source",
    ):
        handler.execute(context)


def test_handler_rejects_empty_patient_table(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path
    )

    def empty_loader(
        source: str,
    ):
        def load(
            path: str | Path,
        ) -> ValidationCohort:
            return ValidationCohort(
                source=source,
                output_path=Path(path),
                patients=pd.DataFrame(),
            )

        return load

    handler = CohortLoadingStageHandler(
        loaders={
            SimulatorKind.SYNTHEA: (
                empty_loader(
                    SOURCE_SYNTHEA
                )
            ),
            SimulatorKind.PSYNTHEA: (
                empty_loader(
                    SOURCE_PSYNTHEA
                )
            ),
        },
        clock=lambda: _FIXED_TIME,
    )

    with pytest.raises(
        CohortLoadingError,
        match="zero patients",
    ):
        handler.execute(context)


def test_handler_requires_timezone_aware_clock(
    tmp_path: Path,
) -> None:
    _, context = _workspace_and_context(
        tmp_path
    )

    handler = CohortLoadingStageHandler(
        clock=lambda: datetime(
            2026,
            7,
            16,
            8,
            0,
        )
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        handler.execute(context)


def test_handler_requires_exact_loader_set() -> None:
    with pytest.raises(
        ValueError,
        match="exactly one loader",
    ):
        CohortLoadingStageHandler(
            loaders={
                SimulatorKind.SYNTHEA: (
                    lambda path: None
                )
            }
        )