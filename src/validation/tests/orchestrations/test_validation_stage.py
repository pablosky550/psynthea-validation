from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path

import pandas as pd
import pytest

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
from validation.orchestration.stages.validation import (
    ValidationStageError,
    ValidationStageHandler,
)
from validation.orchestration.workspace import (
    ExperimentWorkspace,
)

from validation.comparison.statistical_comparison import (
        compare_module_statistics,
    )

from validation.constants import (
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
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
        id="hypertension-validation",
        name="Hypertension validation",
        cohort=CohortConfig(
            population=4,
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
        metadata={
            "validation": {
                "alpha": 0.05,
                "top_n_codes": 10,
                "modules": {
                    "hypertension": {
                        "expected_condition_terms": [
                            "hypertension"
                        ]
                    }
                },
            }
        },
    )


def _write_table(
    workspace: ExperimentWorkspace,
    relative_path: Path,
    dataframe: pd.DataFrame,
):
    path = workspace.write_text(
        relative_path,
        dataframe.to_csv(
            index=False,
            lineterminator="\n",
            na_rep="",
        ),
    )

    return workspace.artifact_reference(
        artifact_id=(
            "normalized:"
            + relative_path.as_posix()
            .replace("/", ":")
        ),
        kind=ArtifactKind.NORMALIZED_DATASET,
        path=path,
        media_type="text/csv",
        producer="cohort_normalization_stage",
        created_at=_FIXED_TIME,
    )


def _cohort_tables(
    simulator: SimulatorKind,
) -> dict[str, pd.DataFrame]:
    prefix = (
        "s"
        if simulator is SimulatorKind.SYNTHEA
        else "p"
    )

    patients = pd.DataFrame(
        [
            {
                "Id": f"{prefix}1",
                "GENDER": "F",
                "BIRTHDATE": "1970-01-01",
                "AGE": 56.0,
                "AGE_BAND": "50-59",
            },
            {
                "Id": f"{prefix}2",
                "GENDER": "M",
                "BIRTHDATE": "1960-01-01",
                "AGE": 66.0,
                "AGE_BAND": "60-69",
            },
            {
                "Id": f"{prefix}3",
                "GENDER": "F",
                "BIRTHDATE": "1980-01-01",
                "AGE": 46.0,
                "AGE_BAND": "40-49",
            },
            {
                "Id": f"{prefix}4",
                "GENDER": "M",
                "BIRTHDATE": "1950-01-01",
                "AGE": 76.0,
                "AGE_BAND": "70-79",
            },
        ]
    )

    encounters = pd.DataFrame(
        [
            {
                "Id": f"e-{prefix}-1",
                "PATIENT": f"{prefix}1",
                "START": "2020-01-01",
                "STOP": "2020-01-01",
                "ENCOUNTERCLASS": "ambulatory",
                "CODE": "185349003",
                "DESCRIPTION": "Encounter",
            },
            {
                "Id": f"e-{prefix}-2",
                "PATIENT": f"{prefix}2",
                "START": "2020-01-01",
                "STOP": "2020-01-01",
                "ENCOUNTERCLASS": "ambulatory",
                "CODE": "185349003",
                "DESCRIPTION": "Encounter",
            },
        ]
    )

    conditions = pd.DataFrame(
        [
            {
                "PATIENT": f"{prefix}1",
                "CODE": "38341003",
                "START": "2020-01-01",
                "STOP": "",
                "DESCRIPTION": "Hypertension",
            },
            {
                "PATIENT": f"{prefix}2",
                "CODE": "38341003",
                "START": "2020-01-01",
                "STOP": "",
                "DESCRIPTION": "Hypertension",
            },
        ]
    )

    return {
        "patients": patients,
        "encounters": encounters,
        "conditions": conditions,
        "medications": pd.DataFrame(
            columns=[
                "PATIENT",
                "CODE",
                "START",
                "STOP",
                "DESCRIPTION",
                "DISPENSES",
            ]
        ),
        "procedures": pd.DataFrame(
            columns=[
                "PATIENT",
                "CODE",
                "START",
                "STOP",
                "DESCRIPTION",
                "BASE_COST",
            ]
        ),
        "observations": pd.DataFrame(
            columns=[
                "PATIENT",
                "CODE",
                "DATE",
                "DESCRIPTION",
                "VALUE",
                "UNITS",
            ]
        ),
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

    cohorts_payload = {}

    artifacts = []

    for simulator in SimulatorKind:
        tables_payload = {}

        for table_name, dataframe in (
            _cohort_tables(simulator).items()
        ):
            relative_path = (
                Path("normalized")
                / simulator.value
                / f"{table_name}.csv"
            )

            artifact = _write_table(
                workspace,
                relative_path,
                dataframe,
            )

            artifacts.append(artifact)

            tables_payload[table_name] = {
                "artifact_id": artifact.id,
                "path": artifact.path.as_posix(),
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
                "rows": len(dataframe),
                "columns": list(
                    dataframe.columns
                ),
            }

            source = (
                SOURCE_SYNTHEA
                if simulator is SimulatorKind.SYNTHEA
                else SOURCE_PSYNTHEA
            )

            cohorts_payload[
                simulator.value
            ] = {
                "simulator": simulator.value,
                "source": source,
                "summary": {
                    "source": source,
                    "patients": 4,
                    "encounters": 2,
                    "conditions": 2,
                    "medications": 0,
                    "procedures": 0,
                    "observations": 0,
                },
                "tables": tables_payload,
            }
    manifest_payload = {
        "schema_version": "1.0",
        "experiment_id": config.id,
        "run_id": "run-001",
        "generated_at": _FIXED_TIME.isoformat(),
        "reference_date": "2026-01-01",
        "source_loading_artifact": {
            "artifact_id": "loading",
            "path": (
                "loaded/"
                "cohort_loading_manifest.json"
            ),
            "sha256": None,
            "size_bytes": None,
        },
        "cohorts": cohorts_payload,
    }

    manifest_path = workspace.write_json(
        (
            "normalized/"
            "cohort_normalization_manifest.json"
        ),
        manifest_payload,
    )

    manifest_artifact = (
        workspace.artifact_reference(
            artifact_id=(
                f"{config.id}:run-001:"
                "cohort-normalization"
            ),
            kind=(
                ArtifactKind.COHORT_NORMALIZATION_RESULT
            ),
            path=manifest_path,
            media_type="application/json",
            producer="cohort_normalization_stage",
            created_at=_FIXED_TIME,
        )
    )

    return (
        workspace,
        OrchestrationContext(
            config=config,
            workspace=workspace,
            run_id="run-001",
            simulator_runs=(),
            stage_results=(),
            artifacts=(
                *artifacts,
                manifest_artifact,
            ),
        ),
    )


def test_stage_executes_real_validation_and_persists_result(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    output = ValidationStageHandler(
        clock=lambda: _FIXED_TIME
    ).execute(context)

    validation_results = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.VALIDATION_RESULT
    ]

    evidence = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.EVIDENCE
    ]

    assert len(validation_results) == 1
    assert len(evidence) == 10

    result_payload = json.loads(
        workspace.resolve(
            validation_results[0].path
        ).read_text()
    )

    assert (
        result_payload["schema_version"]
        == "1.0"
    )
    assert (
        result_payload["experiment_id"]
        == context.config.id
    )
    assert (
        result_payload["run_id"]
        == context.run_id
    )

    assert (
        result_payload["aggregate"]
        ["module_count"]
        == 1
    )

    assert (
        result_payload["modules"][0]
        ["module_name"]
        == "hypertension"
    )

    assert (
        result_payload["configuration"]
        ["alpha"]
        == 0.05
    )
    assert result_payload["configuration"]["reference_date"] == "2026-01-01"
    assert result_payload["configuration"]["observation_start_date"] is None
    assert result_payload["configuration"]["observation_end_date"] is None

    cohort_comparison = result_payload["cohort_comparison"]
    assert cohort_comparison["demographics"]["age_summary"]
    assert cohort_comparison["demographics"]["age_groups"]
    assert cohort_comparison["demographics"]["sex_distribution"]
    assert cohort_comparison["epidemiology"] is None
    assert cohort_comparison["summary"]

    assert (
        output.metadata["module_count"]
        == 1
    )


def test_stage_uses_configured_validation_settings(
    tmp_path: Path,
) -> None:
    _, context = _context(
        tmp_path
    )

    calls = []

    def comparator(**kwargs):
        calls.append(kwargs)
        return compare_module_statistics(
            **kwargs
        )


    ValidationStageHandler(
        comparator=comparator,
        clock=lambda: _FIXED_TIME,
    ).execute(context)

    assert len(calls) == 1
    assert calls[0]["module_name"] == (
        "hypertension"
    )
    assert calls[0]["alpha"] == 0.05
    assert calls[0]["top_n_codes"] == 10
    assert calls[0][
        "expected_condition_terms"
    ] == ("hypertension",)


def test_stage_rejects_missing_normalization_manifest(
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
            artifacts=tuple(
                artifact
                for artifact
                in context.artifacts
                if artifact.kind
                is not (
                    ArtifactKind
                    .COHORT_NORMALIZATION_RESULT
                )
            ),
        )
    )

    with pytest.raises(
        ValidationStageError,
        match="exactly one",
    ):
        ValidationStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(
            context_without_manifest
        )


def test_stage_rejects_modified_normalized_dataset(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    patients_path = workspace.resolve(
        "normalized/synthea/patients.csv"
    )

    patients_path.write_text(
        (
            "Id,GENDER,BIRTHDATE,AGE,AGE_BAND\n"
            "tampered,F,1970-01-01,56,50-59\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationStageError,
        match="changed",
    ):
        ValidationStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(context)


def test_stage_rejects_invalid_alpha(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    invalid_config = ExperimentConfig(
        id=context.config.id,
        name=context.config.name,
        cohort=context.config.cohort,
        simulators=context.config.simulators,
        output_root=context.config.output_root,
        report_formats=(
            context.config.report_formats
        ),
        metadata={
            "validation": {
                "alpha": 2.0
            }
        },
    )

    invalid_context = OrchestrationContext(
        config=invalid_config,
        workspace=workspace,
        run_id=context.run_id,
        simulator_runs=(),
        stage_results=(),
        artifacts=context.artifacts,
    )

    with pytest.raises(
        ValidationStageError,
        match="alpha",
    ):
        ValidationStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(invalid_context)


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
        ValidationStageHandler(
            clock=lambda: datetime(
                2026,
                7,
                16,
                8,
                0,
            )
        ).execute(context)