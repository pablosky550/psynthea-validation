"""Adapt orchestration outputs into a canonical RootCauseRequest.

This module defines the boundary between the Experiment Orchestrator and the
Phase 3 Root Cause Engine. It validates that all upstream scientific stages
completed successfully and converts their immutable outputs into the identifier-
based request contract consumed by the causal engine.

The adapter does not:

* execute root-cause analysis;
* read or deserialize persisted artefacts;
* collect evidence;
* infer causal conclusions;
* mutate upstream results.

Artefact loading remains the responsibility of the orchestration stage handler,
while evidence normalization remains inside ``validation.root_cause.evidence``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from validation.interpretation.models import InterpretationReport
from validation.knowledge.models import InvestigationCase, KnowledgeEntry
from validation.knowledge.taxonomy import ValidationDomain
from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExecutionStatus,
    ExperimentResult,
    ExperimentStage,
    SimulatorKind,
)
from validation.root_cause.exceptions import (
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import RootCauseRequest


_REQUIRED_UPSTREAM_STAGES = (
    ExperimentStage.COHORT_LOADING,
    ExperimentStage.COHORT_NORMALIZATION,
    ExperimentStage.VALIDATION,
    ExperimentStage.KNOWLEDGE_ENRICHMENT,
)

_REQUIRED_SIMULATORS = frozenset(
    {
        SimulatorKind.SYNTHEA,
        SimulatorKind.PSYNTHEA,
    }
)

_REQUIRED_ARTIFACT_KINDS = frozenset(
    {
        ArtifactKind.VALIDATION_RESULT,
        ArtifactKind.KNOWLEDGE_RESULT,
    }
)


@dataclass(frozen=True, slots=True)
class RootCauseRequestSource:
    """Complete upstream input required to construct one causal request.

    ``experiment_result`` may represent an in-progress orchestration snapshot.
    It is therefore not required to have overall ``SUCCEEDED`` status, because
    root-cause analysis runs before report generation and manifest finalization.
    """

    experiment_result: ExperimentResult
    interpretation_report: InterpretationReport
    investigation_cases: tuple[InvestigationCase, ...] = ()
    knowledge_entries: tuple[KnowledgeEntry, ...] = ()
    requested_domains: tuple[ValidationDomain, ...] = ()
    max_candidates: int = 20
    execute_verifications: bool = True
    strict_integrity: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.experiment_result, ExperimentResult):
            raise TypeError("experiment_result must be an ExperimentResult.")
        if not isinstance(self.interpretation_report, InterpretationReport):
            raise TypeError(
                "interpretation_report must be an InterpretationReport."
            )

        object.__setattr__(
            self,
            "investigation_cases",
            _normalize_model_tuple(
                self.investigation_cases,
                InvestigationCase,
                "investigation_cases",
            ),
        )
        object.__setattr__(
            self,
            "knowledge_entries",
            _normalize_model_tuple(
                self.knowledge_entries,
                KnowledgeEntry,
                "knowledge_entries",
            ),
        )
        object.__setattr__(
            self,
            "requested_domains",
            _normalize_domains(self.requested_domains),
        )

        if isinstance(self.max_candidates, bool) or not isinstance(
            self.max_candidates,
            int,
        ):
            raise TypeError("max_candidates must be an integer.")
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be greater than zero.")

        if not isinstance(self.execute_verifications, bool):
            raise TypeError("execute_verifications must be a bool.")
        if not isinstance(self.strict_integrity, bool):
            raise TypeError("strict_integrity must be a bool.")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping.")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@dataclass(frozen=True, slots=True)
class RootCauseRequestAdapter:
    """Build a validated RootCauseRequest from upstream experiment outputs."""

    request_id_prefix: str = "root-cause"
    required_media_types: tuple[str, ...] = (
        "application/json",
        "application/fhir+json",
    )

    def build(
        self,
        source: RootCauseRequestSource,
        *,
        created_at: datetime | None = None,
    ) -> RootCauseRequest:
        """Validate upstream contracts and build the canonical request."""

        if not isinstance(source, RootCauseRequestSource):
            raise TypeError("source must be a RootCauseRequestSource.")

        experiment = source.experiment_result
        timestamp = _normalize_timestamp(created_at)

        self._validate_experiment_identity(source)
        self._validate_simulator_runs(experiment)
        self._validate_upstream_stages(experiment)

        validation_artifacts = self._artifacts_of_kind(
            experiment,
            ArtifactKind.VALIDATION_RESULT,
        )
        knowledge_artifacts = self._artifacts_of_kind(
            experiment,
            ArtifactKind.KNOWLEDGE_RESULT,
        )

        self._validate_required_artifacts(
            validation_artifacts=validation_artifacts,
            knowledge_artifacts=knowledge_artifacts,
        )

        artifact_ids = tuple(
            artifact.id
            for artifact in sorted(
                (*validation_artifacts, *knowledge_artifacts),
                key=lambda item: item.id,
            )
        )

        validation_result_ids = tuple(
            artifact.id
            for artifact in sorted(
                validation_artifacts,
                key=lambda item: item.id,
            )
        )

        finding_ids = tuple(
            sorted(
                finding.finding_id
                for finding in source.interpretation_report.findings
            )
        )

        investigation_case_ids = tuple(
            sorted(case.id for case in source.investigation_cases)
        )

        knowledge_entry_ids = tuple(
            sorted(entry.id for entry in source.knowledge_entries)
        )

        metadata = {
            "adapter": type(self).__name__,
            "interpretation_report_id": source.interpretation_report.report_id,
            "interpretation_pipeline_run_id": (
                source.interpretation_report.pipeline_run_id
            ),
            "validation_artifact_ids": tuple(
                artifact.id for artifact in validation_artifacts
            ),
            "knowledge_artifact_ids": tuple(
                artifact.id for artifact in knowledge_artifacts
            ),
            "source_stage_ids": tuple(
                stage.id
                for stage in experiment.stage_results
                if stage.stage in _REQUIRED_UPSTREAM_STAGES
            ),
            **dict(source.metadata),
        }

        return RootCauseRequest(
            id=self._request_id(experiment),
            experiment_id=experiment.experiment_id,
            run_id=experiment.run_id,
            validation_result_ids=validation_result_ids,
            interpretation_finding_ids=finding_ids,
            investigation_case_ids=investigation_case_ids,
            knowledge_entry_ids=knowledge_entry_ids,
            artifact_ids=artifact_ids,
            requested_domains=source.requested_domains,
            max_candidates=source.max_candidates,
            execute_verifications=source.execute_verifications,
            strict_integrity=source.strict_integrity,
            created_at=timestamp,
            metadata=metadata,
        )

    def _validate_experiment_identity(
        self,
        source: RootCauseRequestSource,
    ) -> None:
        experiment = source.experiment_result
        report = source.interpretation_report

        if report.pipeline_run_id != experiment.run_id:
            raise RootCauseIntegrityError(
                "InterpretationReport pipeline_run_id does not match "
                "ExperimentResult.run_id.",
                context={
                    "experiment_id": experiment.experiment_id,
                    "experiment_run_id": experiment.run_id,
                    "interpretation_report_id": report.report_id,
                    "interpretation_pipeline_run_id": report.pipeline_run_id,
                },
            )

    def _validate_simulator_runs(
        self,
        experiment: ExperimentResult,
    ) -> None:
        simulator_runs = {
            item.simulator: item
            for item in experiment.simulator_runs
        }

        missing = _REQUIRED_SIMULATORS - simulator_runs.keys()
        if missing:
            raise RootCauseInputError(
                "Root-cause analysis requires successful runs from both "
                "Synthea and Psynthea.",
                context={
                    "experiment_id": experiment.experiment_id,
                    "run_id": experiment.run_id,
                    "missing_simulators": tuple(
                        sorted(item.value for item in missing)
                    ),
                },
            )

        unsuccessful = {
            simulator.value: simulator_runs[simulator].status.value
            for simulator in _REQUIRED_SIMULATORS
            if simulator_runs[simulator].status
            is not ExecutionStatus.SUCCEEDED
        }
        if unsuccessful:
            raise RootCauseInputError(
                "Root-cause analysis cannot start while an upstream simulator "
                "run is unsuccessful.",
                context={
                    "experiment_id": experiment.experiment_id,
                    "run_id": experiment.run_id,
                    "simulator_statuses": unsuccessful,
                },
            )

    def _validate_upstream_stages(
        self,
        experiment: ExperimentResult,
    ) -> None:
        stage_results = {
            item.stage: item
            for item in experiment.stage_results
        }

        missing = tuple(
            stage
            for stage in _REQUIRED_UPSTREAM_STAGES
            if stage not in stage_results
        )
        if missing:
            raise RootCauseInputError(
                "Root-cause analysis is missing required upstream stages.",
                context={
                    "experiment_id": experiment.experiment_id,
                    "run_id": experiment.run_id,
                    "missing_stages": tuple(
                        stage.value for stage in missing
                    ),
                },
            )

        unsuccessful = {
            stage.value: stage_results[stage].status.value
            for stage in _REQUIRED_UPSTREAM_STAGES
            if stage_results[stage].status
            is not ExecutionStatus.SUCCEEDED
        }
        if unsuccessful:
            raise RootCauseInputError(
                "Root-cause analysis requires all upstream scientific stages "
                "to complete successfully.",
                context={
                    "experiment_id": experiment.experiment_id,
                    "run_id": experiment.run_id,
                    "stage_statuses": unsuccessful,
                },
            )

    def _artifacts_of_kind(
        self,
        experiment: ExperimentResult,
        kind: ArtifactKind,
    ) -> tuple[ArtifactReference, ...]:
        artifacts = tuple(
            artifact
            for artifact in _all_artifacts(experiment)
            if artifact.kind is kind
        )

        for artifact in artifacts:
            self._validate_artifact_compatibility(artifact)

        return tuple(sorted(artifacts, key=lambda item: item.id))

    def _validate_required_artifacts(
        self,
        *,
        validation_artifacts: tuple[ArtifactReference, ...],
        knowledge_artifacts: tuple[ArtifactReference, ...],
    ) -> None:
        missing: list[str] = []

        if not validation_artifacts:
            missing.append(ArtifactKind.VALIDATION_RESULT.value)
        if not knowledge_artifacts:
            missing.append(ArtifactKind.KNOWLEDGE_RESULT.value)

        if missing:
            raise RootCauseInputError(
                "Root-cause analysis requires persisted validation and "
                "knowledge artefacts.",
                context={
                    "missing_artifact_kinds": tuple(missing),
                },
            )

    def _validate_artifact_compatibility(
        self,
        artifact: ArtifactReference,
    ) -> None:
        if artifact.media_type not in self.required_media_types:
            raise RootCauseInputError(
                "Root-cause input artefact uses an unsupported media type.",
                context={
                    "artifact_id": artifact.id,
                    "artifact_kind": artifact.kind.value,
                    "media_type": artifact.media_type,
                    "supported_media_types": self.required_media_types,
                },
            )

        if artifact.sha256 is None:
            raise RootCauseIntegrityError(
                "Root-cause input artefact must contain a SHA-256 digest.",
                context={
                    "artifact_id": artifact.id,
                    "artifact_kind": artifact.kind.value,
                    "path": artifact.path,
                },
            )

        if artifact.size_bytes is None or artifact.size_bytes <= 0:
            raise RootCauseIntegrityError(
                "Root-cause input artefact must contain a positive size.",
                context={
                    "artifact_id": artifact.id,
                    "artifact_kind": artifact.kind.value,
                    "size_bytes": artifact.size_bytes,
                },
            )

    def _request_id(
        self,
        experiment: ExperimentResult,
    ) -> str:
        return (
            f"{self.request_id_prefix}."
            f"{experiment.experiment_id}."
            f"{experiment.run_id}"
        )


def _all_artifacts(
    experiment: ExperimentResult,
) -> tuple[ArtifactReference, ...]:
    """Return every unique artefact visible from the experiment snapshot."""

    collected: dict[str, ArtifactReference] = {}

    def register(artifact: ArtifactReference) -> None:
        existing = collected.get(artifact.id)
        if existing is not None and existing != artifact:
            raise RootCauseIntegrityError(
                "Conflicting artefact references share the same identifier.",
                context={
                    "artifact_id": artifact.id,
                    "first_kind": existing.kind.value,
                    "second_kind": artifact.kind.value,
                    "first_path": existing.path,
                    "second_path": artifact.path,
                },
            )
        collected[artifact.id] = artifact

    for artifact in experiment.artifacts:
        register(artifact)

    for simulator_run in experiment.simulator_runs:
        for artifact in simulator_run.artifacts:
            register(artifact)

    for stage_result in experiment.stage_results:
        for artifact in stage_result.artifacts:
            register(artifact)

    return tuple(sorted(collected.values(), key=lambda item: item.id))


def _normalize_model_tuple(
    values: Sequence[Any],
    expected_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(
            f"{field_name} must be a sequence of "
            f"{expected_type.__name__} values."
        )

    normalized = tuple(values)
    seen: set[str] = set()

    for index, value in enumerate(normalized):
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name}[{index}] must be "
                f"{expected_type.__name__}, "
                f"got {type(value).__name__}."
            )

        item_id = value.id
        if item_id in seen:
            raise ValueError(
                f"{field_name} contains duplicate id {item_id!r}."
            )
        seen.add(item_id)

    return normalized


def _normalize_domains(
    values: Sequence[ValidationDomain],
) -> tuple[ValidationDomain, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(
            "requested_domains must be a sequence of ValidationDomain members."
        )

    normalized: list[ValidationDomain] = []

    for index, value in enumerate(values):
        if not isinstance(value, ValidationDomain):
            raise TypeError(
                f"requested_domains[{index}] must be a ValidationDomain, "
                f"got {type(value).__name__}."
            )
        if value not in normalized:
            normalized.append(value)

    return tuple(normalized)


def _normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if not isinstance(value, datetime):
        raise TypeError("created_at must be a datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware.")
    return value.astimezone(UTC)