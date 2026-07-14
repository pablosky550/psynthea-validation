"""End-to-end acceptance test for the complete Phase 2B experiment pipeline.

The test traverses the real orchestration application flow:

    ExperimentConfig
        -> ExperimentWorkspace
        -> Synthea runner adapter
        -> psynthea runner adapter
        -> cohort loading
        -> cohort normalization
        -> Validation Engine adapter
        -> Scientific Knowledge Engine adapter
        -> report adapter
        -> ExperimentResult
        -> canonical manifest

Only external systems are replaced by deterministic test doubles. Workspace
creation, artifact hashing, stage coordination, result invariants and manifest
persistence use the production Phase 2B implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
from pathlib import Path
from typing import Any

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
    StageOutput,
)
from validation.orchestration.workspace import ExperimentWorkspace


_FIXED_TIME = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)


def _config(tmp_path: Path) -> ExperimentConfig:
    synthea_home = tmp_path / "external" / "synthea"
    psynthea_home = tmp_path / "external" / "psynthea"
    synthea_home.mkdir(parents=True)
    psynthea_home.mkdir(parents=True)

    return ExperimentConfig(
        id="hypertension-equivalence",
        name="Hypertension equivalence experiment",
        description="Phase 2B end-to-end acceptance experiment.",
        cohort=CohortConfig(
            population=4,
            seed=42,
            modules=("hypertension",),
            reference_date=date(2026, 1, 1),
            min_age=40,
            max_age=80,
        ),
        simulators=(
            SimulatorConfig(
                kind=SimulatorKind.SYNTHEA,
                command=("synthea",),
                working_directory=synthea_home,
                output_subdirectory="cohort",
                expected_output_files=("patients.csv", "conditions.csv"),
            ),
            SimulatorConfig(
                kind=SimulatorKind.PSYNTHEA,
                command=("psynthea",),
                working_directory=psynthea_home,
                output_subdirectory="cohort",
                expected_output_files=("patients.csv", "conditions.csv"),
            ),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.HTML, ReportFormat.JSON),
        tags=("phase-2b", "acceptance"),
    )


class DeterministicRunner:
    """External-simulator double that still persists real workspace artifacts."""

    def __init__(self, config: SimulatorConfig) -> None:
        self.kind = config.kind
        self.config = config

    def run(
        self,
        *,
        experiment: ExperimentConfig,
        workspace: ExperimentWorkspace,
        run_id: str,
    ) -> SimulatorRunResult:
        started_at = _FIXED_TIME
        raw_dir = workspace.simulator_raw_directory(self.kind) / self.config.output_subdirectory
        raw_dir.mkdir(parents=True, exist_ok=False)

        offset = 0 if self.kind is SimulatorKind.SYNTHEA else 100
        patients = (
            "patient_id,age,sex\n"
            f"{offset + 1},52,F\n"
            f"{offset + 2},61,M\n"
            f"{offset + 3},67,F\n"
            f"{offset + 4},74,M\n"
        )
        conditions = (
            "patient_id,code,onset_age\n"
            f"{offset + 1},38341003,50\n"
            f"{offset + 3},38341003,65\n"
        )

        patient_path = workspace.write_text(
            workspace.relative(raw_dir / "patients.csv"),
            patients,
        )
        condition_path = workspace.write_text(
            workspace.relative(raw_dir / "conditions.csv"),
            conditions,
        )

        artifacts = (
            workspace.artifact_reference(
                artifact_id=f"{self.kind.value}.patients",
                kind=ArtifactKind.SIMULATOR_OUTPUT,
                path=patient_path,
                media_type="text/csv",
                producer=f"{self.kind.value}_runner",
            ),
            workspace.artifact_reference(
                artifact_id=f"{self.kind.value}.conditions",
                kind=ArtifactKind.SIMULATOR_OUTPUT,
                path=condition_path,
                media_type="text/csv",
                producer=f"{self.kind.value}_runner",
            ),
        )

        return SimulatorRunResult(
            id=f"{experiment.id}:{run_id}:{self.kind.value}",
            simulator=self.kind,
            status=ExecutionStatus.SUCCEEDED,
            command=(self.kind.value, "--population", str(experiment.cohort.population)),
            working_directory=self.config.working_directory,
            started_at=started_at,
            finished_at=started_at,
            duration_seconds=0.0,
            return_code=0,
            artifacts=artifacts,
            metadata={
                "population": experiment.cohort.population,
                "seed": experiment.cohort.seed,
            },
        )


@dataclass(frozen=True)
class CohortLoadingHandler:
    stage: ExperimentStage = ExperimentStage.COHORT_LOADING

    def execute(self, context) -> StageOutput:
        simulator_artifacts = [
            artifact
            for run in context.simulator_runs
            for artifact in run.artifacts
            if artifact.kind is ArtifactKind.SIMULATOR_OUTPUT
        ]
        index = {
            "simulators": {
                run.simulator.value: [artifact.path.as_posix() for artifact in run.artifacts]
                for run in context.simulator_runs
            },
            "artifact_count": len(simulator_artifacts),
        }
        path = context.workspace.write_json("normalized/cohort_index.json", index)
        artifact = context.workspace.artifact_reference(
            artifact_id="cohort.index",
            kind=ArtifactKind.NORMALIZED_DATASET,
            path=path,
            media_type="application/json",
            producer=self.stage.value,
        )
        return StageOutput(
            artifacts=(artifact,),
            summary="Simulator cohort files indexed.",
            metadata={"source_artifact_count": len(simulator_artifacts)},
        )


@dataclass(frozen=True)
class CohortNormalizationHandler:
    stage: ExperimentStage = ExperimentStage.COHORT_NORMALIZATION

    def execute(self, context) -> StageOutput:
        normalized = {
            "schema": "validation.cohort.v1",
            "population": context.config.cohort.population,
            "seed": context.config.cohort.seed,
            "simulators": ["synthea", "psynthea"],
            "variables": ["age", "sex", "condition", "onset_age"],
        }
        path = context.workspace.write_json(
            "normalized/cohort_normalized.json",
            normalized,
        )
        artifact = context.workspace.artifact_reference(
            artifact_id="cohort.normalized",
            kind=ArtifactKind.NORMALIZED_DATASET,
            path=path,
            media_type="application/json",
            producer=self.stage.value,
        )
        return StageOutput(
            artifacts=(artifact,),
            summary="Both cohorts normalized to the shared validation schema.",
        )


@dataclass(frozen=True)
class ValidationHandler:
    stage: ExperimentStage = ExperimentStage.VALIDATION

    def execute(self, context) -> StageOutput:
        result = {
            "status": "PASS",
            "population": {
                "synthea": context.config.cohort.population,
                "psynthea": context.config.cohort.population,
            },
            "metrics": {
                "age_ks_p_value": 1.0,
                "sex_chi_square_p_value": 1.0,
                "hypertension_prevalence_absolute_difference": 0.0,
                "cohens_d": 0.0,
            },
        }
        path = context.workspace.write_json("validation/results.json", result)
        artifact = context.workspace.artifact_reference(
            artifact_id="validation.results",
            kind=ArtifactKind.VALIDATION_RESULT,
            path=path,
            media_type="application/json",
            producer="validation_engine",
        )
        return StageOutput(
            artifacts=(artifact,),
            summary="Validation Engine completed with PASS.",
            metadata={"decision": "PASS"},
        )


@dataclass(frozen=True)
class KnowledgeHandler:
    stage: ExperimentStage = ExperimentStage.KNOWLEDGE_ENRICHMENT

    def execute(self, context) -> StageOutput:
        knowledge = {
            "detection_signals": [],
            "matched_rules": [],
            "validated_knowledge_entries": [],
            "interpretation": "No clinically relevant divergence detected.",
        }
        path = context.workspace.write_json("knowledge/assessment.json", knowledge)
        artifact = context.workspace.artifact_reference(
            artifact_id="knowledge.assessment",
            kind=ArtifactKind.KNOWLEDGE_RESULT,
            path=path,
            media_type="application/json",
            producer="scientific_knowledge_engine",
        )
        return StageOutput(
            artifacts=(artifact,),
            summary="Scientific knowledge enrichment completed.",
            metadata={"candidate_causes": 0},
        )


@dataclass(frozen=True)
class ReportHandler:
    stage: ExperimentStage = ExperimentStage.REPORT_GENERATION

    def execute(self, context) -> StageOutput:
        html = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Hypertension validation</title></head>
<body>
<h1>Hypertension equivalence experiment</h1>
<p>Decision: PASS</p>
<p>No clinically relevant divergence detected.</p>
</body>
</html>
"""
        html_path = context.workspace.write_text("report/report.html", html)
        json_path = context.workspace.write_json(
            "report/report.json",
            {
                "experiment_id": context.config.id,
                "run_id": context.run_id,
                "decision": "PASS",
                "artifact_count_before_report": len(context.artifacts),
            },
        )
        return StageOutput(
            artifacts=(
                context.workspace.artifact_reference(
                    artifact_id="report.html",
                    kind=ArtifactKind.REPORT,
                    path=html_path,
                    media_type="text/html",
                    producer="scientific_reporter",
                ),
                context.workspace.artifact_reference(
                    artifact_id="report.json",
                    kind=ArtifactKind.REPORT,
                    path=json_path,
                    media_type="application/json",
                    producer="scientific_reporter",
                ),
            ),
            summary="Scientific report generated.",
            metadata={"formats": ("html", "json")},
        )


def _runner_factory(config: SimulatorConfig) -> DeterministicRunner:
    return DeterministicRunner(config)


def test_complete_phase_2b_experiment_end_to_end(tmp_path: Path) -> None:
    config = _config(tmp_path)
    orchestrator = ExperimentOrchestrator(
        (
            CohortLoadingHandler(),
            CohortNormalizationHandler(),
            ValidationHandler(),
            KnowledgeHandler(),
            ReportHandler(),
        ),
        runner_factory=_runner_factory,
        orchestrator_version="2.0.0",
        clock=lambda: _FIXED_TIME,
        monotonic_clock=lambda: 100.0,
    )

    execution = orchestrator.execute(config, run_id="acceptance-run-001")
    result = execution.result

    # Final domain result.
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.error_message is None
    assert result.experiment_id == config.id
    assert result.run_id == "acceptance-run-001"
    assert result.duration_seconds == 0.0

    # Both simulators ran under the exact same scientific cohort contract.
    assert [run.simulator for run in result.simulator_runs] == [
        SimulatorKind.SYNTHEA,
        SimulatorKind.PSYNTHEA,
    ]
    assert all(run.status is ExecutionStatus.SUCCEEDED for run in result.simulator_runs)
    assert all(run.metadata["population"] == 4 for run in result.simulator_runs)
    assert all(run.metadata["seed"] == 42 for run in result.simulator_runs)

    # Every canonical orchestration stage was recorded exactly once.
    expected_stages = {
        ExperimentStage.WORKSPACE_INITIALIZATION,
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.REPORT_GENERATION,
        ExperimentStage.MANIFEST_FINALIZATION,
    }
    assert {stage.stage for stage in result.stage_results} == expected_stages
    assert all(
        stage.status is ExecutionStatus.SUCCEEDED
        for stage in result.stage_results
    )

    # The global artifact catalogue contains simulator, normalized, validation,
    # knowledge and report products, but not its own self-referential manifest.
    assert len(result.artifacts) == 10
    assert len({artifact.id for artifact in result.artifacts}) == 10
    assert len({artifact.path for artifact in result.artifacts}) == 10
    assert all(artifact.sha256 for artifact in result.artifacts)
    assert all(artifact.size_bytes is not None for artifact in result.artifacts)

    workspace = ExperimentWorkspace.open(config, "acceptance-run-001")
    expected_files = {
        "simulators/synthea/raw/cohort/patients.csv",
        "simulators/synthea/raw/cohort/conditions.csv",
        "simulators/psynthea/raw/cohort/patients.csv",
        "simulators/psynthea/raw/cohort/conditions.csv",
        "normalized/cohort_index.json",
        "normalized/cohort_normalized.json",
        "validation/results.json",
        "knowledge/assessment.json",
        "report/report.html",
        "report/report.json",
        "manifest.json",
    }
    assert expected_files.issubset(
        {
            path.relative_to(workspace.root).as_posix()
            for path in workspace.root.rglob("*")
            if path.is_file()
        }
    )

    # The persisted scientific products contain the expected decision.
    validation = json.loads(
        (workspace.root / "validation/results.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (workspace.root / "report/report.json").read_text(encoding="utf-8")
    )
    assert validation["status"] == "PASS"
    assert validation["metrics"]["hypertension_prevalence_absolute_difference"] == 0.0
    assert report["decision"] == "PASS"

    # Manifest exists, matches its external ArtifactReference and is structurally
    # bound to the same experiment/configuration.
    assert execution.manifest is not None
    manifest_service = ExperimentManifest(
        workspace,
        producer_version="2.0.0",
    )
    payload = manifest_service.verify(expected_reference=execution.manifest)

    assert payload["schema_version"] == 2
    assert payload["experiment_id"] == config.id
    assert payload["run_id"] == "acceptance-run-001"
    assert payload["workspace"] == "."
    assert payload["result"]["status"] == "succeeded"
    assert payload["result"]["config"] == payload["config"]
    assert len(payload["result"]["artifacts"]) == 10

    # Reopening the workspace and re-verifying the manifest proves persistence,
    # ownership, hashing and portability after the orchestrator has returned.
    reopened = ExperimentWorkspace.open(config, "acceptance-run-001")
    reopened_manifest = ExperimentManifest(
        reopened,
        producer_version="2.0.0",
    )
    assert (
        reopened_manifest.verify(expected_reference=execution.manifest)
        == payload
    )