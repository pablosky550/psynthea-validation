from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path

import pandas as pd
import pytest

from validation.constants import (
    AGE_BAND_COLUMN,
    AGE_COLUMN,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.models import ValidationCohort
from validation.orchestration.models import (
    ArtifactKind,
    CohortConfig,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
)
from validation.orchestration.stages.cohort_normalization import (
    CohortNormalizationError,
    CohortNormalizationStageHandler,
    normalize_validation_cohort,
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
        id="hypertension-normalization",
        name="Hypertension normalization",
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


def _write_raw_cohort(
    workspace: ExperimentWorkspace,
    simulator: SimulatorKind,
    *,
    offset: int,
) -> dict:
    output_directory = (
        workspace.simulator_raw_directory(
            simulator
        )
        / "cohort"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    patients_path = workspace.write_text(
        workspace.relative(
            output_directory / "patients.csv"
        ),
        (
            "id,gender,birthdate\n"
            f" {offset + 2} ,male,1960-01-01\n"
            f" {offset + 1} ,female,1970-01-01\n"
        ),
    )

    conditions_path = workspace.write_text(
        workspace.relative(
            output_directory / "conditions.csv"
        ),
        (
            "patient,code,start,stop,description\n"
            f"{offset + 1},38341003.0,"
            "2020-01-01,, Hypertension \n"
        ),
    )

    artifacts = []

    for table_name, path in (
        ("patients", patients_path),
        ("conditions", conditions_path),
    ):
        artifact = workspace.artifact_reference(
            artifact_id=(
                f"{simulator.value}.{table_name}"
            ),
            kind=ArtifactKind.SIMULATOR_OUTPUT,
            path=path,
            media_type="text/csv",
            producer="test_runner",
            created_at=_FIXED_TIME,
        )

        artifacts.append(artifact)

    table_payloads = {
        "patients": {
            "present": True,
            "filename": "patients.csv",
            "rows": 2,
            "columns": [
                "id",
                "gender",
                "birthdate",
            ],
            "artifact_id": artifacts[0].id,
            "path": artifacts[0].path.as_posix(),
            "sha256": artifacts[0].sha256,
            "size_bytes": artifacts[0].size_bytes,
        },
        "conditions": {
            "present": True,
            "filename": "conditions.csv",
            "rows": 1,
            "columns": [
                "patient",
                "code",
                "start",
                "stop",
                "description",
            ],
            "artifact_id": artifacts[1].id,
            "path": artifacts[1].path.as_posix(),
            "sha256": artifacts[1].sha256,
            "size_bytes": artifacts[1].size_bytes,
        },
    }

    for table_name in (
        "encounters",
        "medications",
        "procedures",
        "observations",
    ):
        table_payloads[table_name] = {
            "present": False,
            "filename": f"{table_name}.csv",
            "rows": 0,
            "columns": [],
            "artifact_id": None,
            "path": None,
            "sha256": None,
            "size_bytes": None,
        }

    source = (
        SOURCE_SYNTHEA
        if simulator is SimulatorKind.SYNTHEA
        else SOURCE_PSYNTHEA
    )

    return {
        "simulator": simulator.value,
        "source": source,
        "output_path": workspace.relative(
            output_directory
        ).as_posix(),
        "summary": {
            "source": source,
            "patients": 2,
            "encounters": 0,
            "conditions": 1,
            "medications": 0,
            "procedures": 0,
            "observations": 0,
        },
        "tables": table_payloads,
    }


def _context(
    tmp_path: Path,
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

    synthea_payload = _write_raw_cohort(
        workspace,
        SimulatorKind.SYNTHEA,
        offset=0,
    )

    psynthea_payload = _write_raw_cohort(
        workspace,
        SimulatorKind.PSYNTHEA,
        offset=100,
    )

    loading_manifest = {
        "schema_version": "1.0",
        "experiment_id": config.id,
        "run_id": "run-001",
        "generated_at": _FIXED_TIME.isoformat(),
        "requested_population": 2,
        "cohorts": {
            "synthea": synthea_payload,
            "psynthea": psynthea_payload,
        },
    }

    manifest_path = workspace.write_json(
        "loaded/cohort_loading_manifest.json",
        loading_manifest,
    )

    loading_artifact = (
        workspace.artifact_reference(
            artifact_id=(
                f"{config.id}:run-001:"
                "cohort-loading"
            ),
            kind=(
                ArtifactKind.COHORT_LOAD_RESULT
            ),
            path=manifest_path,
            media_type="application/json",
            producer="cohort_loading_stage",
            created_at=_FIXED_TIME,
        )
    )

    context = OrchestrationContext(
        config=config,
        workspace=workspace,
        run_id="run-001",
        simulator_runs=(),
        stage_results=(),
        artifacts=(loading_artifact,),
    )

    return workspace, context


def test_normalize_validation_cohort_creates_canonical_patient_fields() -> None:
    cohort = ValidationCohort(
        source=SOURCE_SYNTHEA,
        patients=pd.DataFrame(
            [
                {
                    "id": " 2 ",
                    "gender": "male",
                    "birthdate": "1960-01-01",
                },
                {
                    "id": " 1 ",
                    "gender": "female",
                    "birthdate": "1970-01-01",
                },
            ]
        ),
    )

    normalized = normalize_validation_cohort(
        cohort,
        date(2026, 1, 1),
    )

    assert list(
        normalized.patients["Id"]
    ) == ["1", "2"]

    assert list(
        normalized.patients["GENDER"]
    ) == ["F", "M"]

    assert AGE_COLUMN in (
        normalized.patients.columns
    )
    assert AGE_BAND_COLUMN in (
        normalized.patients.columns
    )

    assert (
        normalized.patients["BIRTHDATE"]
        .tolist()
        == ["1970-01-01", "1960-01-01"]
    )


def test_normalize_validation_cohort_normalizes_codes_and_text() -> None:
    cohort = ValidationCohort(
        source=SOURCE_SYNTHEA,
        patients=pd.DataFrame(
            [
                {
                    "Id": "p1",
                    "GENDER": "F",
                    "BIRTHDATE": "1970-01-01",
                }
            ]
        ),
        conditions=pd.DataFrame(
            [
                {
                    "patient": "p1",
                    "code": "38341003.0",
                    "start": "2020-01-01",
                    "description": " Hypertension ",
                }
            ]
        ),
    )

    normalized = normalize_validation_cohort(
        cohort,
        date(2026, 1, 1),
    )

    condition = (
        normalized.conditions.iloc[0]
    )

    assert condition["PATIENT"] == "p1"
    assert condition["CODE"] == "38341003"
    assert (
        condition["DESCRIPTION"]
        == "Hypertension"
    )
    assert condition["START"] == "2020-01-01"


def test_normalize_validation_cohort_does_not_mutate_input() -> None:
    patients = pd.DataFrame(
        [
            {
                "id": " p1 ",
                "gender": "female",
                "birthdate": "1970-01-01",
            }
        ]
    )

    original = patients.copy(deep=True)

    normalize_validation_cohort(
        ValidationCohort(
            source=SOURCE_SYNTHEA,
            patients=patients,
        ),
        date(2026, 1, 1),
    )

    pd.testing.assert_frame_equal(
        patients,
        original,
    )


def test_normalize_validation_cohort_rejects_duplicate_patients() -> None:
    cohort = ValidationCohort(
        source=SOURCE_SYNTHEA,
        patients=pd.DataFrame(
            [
                {
                    "Id": "p1",
                    "GENDER": "F",
                    "BIRTHDATE": "1970-01-01",
                },
                {
                    "Id": "p1",
                    "GENDER": "M",
                    "BIRTHDATE": "1960-01-01",
                },
            ]
        ),
    )

    with pytest.raises(
        CohortNormalizationError,
        match="Duplicate patient",
    ):
        normalize_validation_cohort(
            cohort,
            date(2026, 1, 1),
        )


def test_normalize_validation_cohort_rejects_unknown_patient_reference() -> None:
    cohort = ValidationCohort(
        source=SOURCE_SYNTHEA,
        patients=pd.DataFrame(
            [
                {
                    "Id": "p1",
                    "GENDER": "F",
                    "BIRTHDATE": "1970-01-01",
                }
            ]
        ),
        conditions=pd.DataFrame(
            [
                {
                    "PATIENT": "unknown",
                    "CODE": "38341003",
                    "START": "2020-01-01",
                }
            ]
        ),
    )

    with pytest.raises(
        CohortNormalizationError,
        match="unknown patient",
    ):
        normalize_validation_cohort(
            cohort,
            date(2026, 1, 1),
        )


def test_normalize_validation_cohort_rejects_invalid_date() -> None:
    cohort = ValidationCohort(
        source=SOURCE_SYNTHEA,
        patients=pd.DataFrame(
            [
                {
                    "Id": "p1",
                    "GENDER": "F",
                    "BIRTHDATE": "not-a-date",
                }
            ]
        ),
    )

    with pytest.raises(
        CohortNormalizationError,
        match="invalid date",
    ):
        normalize_validation_cohort(
            cohort,
            date(2026, 1, 1),
        )


def test_stage_persists_normalized_datasets_and_manifest(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    output = CohortNormalizationStageHandler(
        clock=lambda: _FIXED_TIME
    ).execute(context)

    datasets = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.NORMALIZED_DATASET
    ]

    manifests = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.COHORT_NORMALIZATION_RESULT
    ]

    assert len(datasets) == 12
    assert len(manifests) == 1

    synthea_patients = pd.read_csv(
        workspace.resolve(
            Path(
                "normalized/synthea/"
                "patients.csv"
            )
        ),
        dtype={"Id": "string"},
    )

    assert list(
        synthea_patients["Id"]
    ) == ["1", "2"]

    assert list(
        synthea_patients["GENDER"]
    ) == ["F", "M"]

    manifest_payload = json.loads(
        workspace.resolve(
            manifests[0].path
        ).read_text()
    )

    assert (
        manifest_payload["schema_version"]
        == "1.0"
    )
    assert (
        manifest_payload["reference_date"]
        == "2026-01-01"
    )
    assert set(
        manifest_payload["cohorts"]
    ) == {
        "synthea",
        "psynthea",
    }

    assert output.metadata[
        "patient_counts"
    ] == {
        "synthea": 2,
        "psynthea": 2,
    }


def test_stage_rejects_modified_source_after_loading(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    patients_path = workspace.resolve(
        "simulators/synthea/raw/"
        "cohort/patients.csv"
    )

    patients_path.write_text(
        (
            "id,gender,birthdate\n"
            "tampered,F,1970-01-01\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        CohortNormalizationError,
        match="changed after loading",
    ):
        CohortNormalizationStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(context)


def test_stage_requires_exactly_one_loading_manifest(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    context_without_manifest = (
        OrchestrationContext(
            config=context.config,
            workspace=workspace,
            run_id=context.run_id,
            simulator_runs=(),
            stage_results=(),
            artifacts=(),
        )
    )

    with pytest.raises(
        CohortNormalizationError,
        match="exactly one",
    ):
        CohortNormalizationStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(
            context_without_manifest
        )


def test_stage_requires_timezone_aware_clock(
    tmp_path: Path,
) -> None:
    _, context = _context(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        CohortNormalizationStageHandler(
            clock=lambda: datetime(
                2026,
                7,
                16,
                8,
                0,
            )
        ).execute(context)