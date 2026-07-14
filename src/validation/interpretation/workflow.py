"""End-to-end workflow for scientific interpretation of validation outputs.

This module is the public application-service layer of the interpretation
subsystem. It connects the already isolated scientific components without
moving scientific decisions into orchestration code:

1. normalize supported pipeline outputs into canonical evidence;
2. merge evidence catalogs without allowing metric collisions;
3. derive truthful pipeline-stage readiness from successful normalization;
4. execute the deterministic interpretation engine;
5. build the executive summary, recommendation plan and report document;
6. optionally persist a synchronized report bundle.

The workflow never recalculates validation statistics, invents findings or marks
an unavailable stage as completed. All scientific decisions remain in rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final

from validation.interpretation.engine import (
    EngineExecution,
    InterpretationEngine,
    InterpretationEngineConfig,
)
from validation.interpretation.evidence import (
    DEFAULT_EVIDENCE_REGISTRY,
    EvidenceCatalog,
    EvidenceRegistry,
    collect_evidence,
)
from validation.interpretation.recommendations import (
    ActionPlanConfiguration,
    RecommendationPlan,
    build_recommendation_plan,
)
from validation.interpretation.report import (
    InterpretationDocument,
    ReportConfiguration,
    build_interpretation_document,
    write_report_bundle,
)
from validation.interpretation.rules.base import PipelineStage, StageStatus
from validation.interpretation.summary import (
    InterpretationSummary,
    SummaryConfiguration,
    build_interpretation_summary,
)

__all__ = [
    "InterpretationInput",
    "InterpretationWorkflow",
    "InterpretationWorkflowConfig",
    "InterpretationWorkflowError",
    "InterpretationWorkflowResult",
    "WorkflowArtifacts",
]

WORKFLOW_VERSION: Final = "1.1.0"
_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_RESERVED_METADATA_KEYS: Final = frozenset(
    {
        "workflow",
        "input_manifest",
        "evidence_metric_count",
        "workflow_fingerprint",
        "evidence_catalog_fingerprint",
    }
)


class InterpretationWorkflowError(RuntimeError):
    """Raised when orchestration cannot proceed without ambiguity."""


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _serialize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_serialize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _serialize(value.to_dict())
    return value


def _fingerprint(value: Any) -> str:
    payload = dumps(
        _serialize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _catalog_fingerprint(catalog: EvidenceCatalog) -> str:
    """Return a content fingerprint over canonical evidence, not only metric IDs."""

    if not isinstance(catalog, EvidenceCatalog):
        raise TypeError("catalog must be an EvidenceCatalog.")
    payload = tuple(
        value.to_dict()
        for value in sorted(catalog, key=lambda item: item.metric_id)
    )
    return _fingerprint(payload)


def _file_digest(path: Path) -> tuple[str, int]:
    """Return SHA-256 and byte size for one persisted artifact."""

    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path.")
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _workflow_fingerprint_payload(
    *,
    input_manifest: Sequence[Mapping[str, Any]],
    stage_statuses: Mapping[PipelineStage, StageStatus],
    evidence_catalog_fingerprint: str,
    execution: EngineExecution,
    summary: InterpretationSummary,
    recommendation_plan: RecommendationPlan,
    document: InterpretationDocument,
) -> Mapping[str, Any]:
    """Build the canonical, timestamp-free workflow integrity payload."""

    return {
        "workflow_version": WORKFLOW_VERSION,
        "input_manifest": tuple(dict(item) for item in input_manifest),
        "stage_statuses": {
            stage.value: status.value
            for stage, status in sorted(stage_statuses.items(), key=lambda item: item[0].value)
        },
        "evidence_catalog_fingerprint": evidence_catalog_fingerprint,
        "engine_report_id": execution.report.report_id,
        "engine_pipeline_run_id": execution.report.pipeline_run_id,
        "engine_registry_fingerprint": execution.report.metadata["engine"][
            "registry_fingerprint"
        ],
        "engine_execution_order": execution.execution_order,
        "summary_status": summary.overall_status.value,
        "summary_research_use_ready": summary.research_use_ready,
        "recommendation_plan_fingerprint": recommendation_plan.fingerprint,
        "document_fingerprint": document.to_dict()["document_fingerprint"],
    }


@dataclass(frozen=True, slots=True)
class InterpretationInput:
    """One pipeline output and the stage whose successful result it represents."""

    stage: PipelineStage
    source: Any
    label: str | None = None
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.stage, PipelineStage):
            raise TypeError("stage must be a PipelineStage member.")
        if self.stage in {PipelineStage.INGESTION, PipelineStage.REPORTING}:
            raise ValueError(
                "InterpretationInput stage must represent a validation output, not ingestion or reporting."
            )
        if self.source is None:
            raise ValueError("source must not be None.")
        if self.label is not None:
            object.__setattr__(self, "label", _identifier(self.label, "label"))
        if not isinstance(self.required, bool):
            raise TypeError("required must be a bool.")

    @property
    def source_type(self) -> str:
        return f"{type(self.source).__module__}.{type(self.source).__qualname__}"


@dataclass(frozen=True, slots=True)
class InterpretationWorkflowConfig:
    """Immutable policy for one end-to-end interpretation workflow run."""

    validation_id: str
    pipeline_run_id: str
    module_name: str
    report_id: str | None = None
    research_use: bool = True
    strict_evidence: bool = True
    stage_overrides: Mapping[PipelineStage, StageStatus] = field(default_factory=dict)
    engine_schema_version: str = "1.1.0"
    summary: SummaryConfiguration = field(default_factory=SummaryConfiguration)
    recommendations: ActionPlanConfiguration = field(default_factory=ActionPlanConfiguration)
    report: ReportConfiguration = field(default_factory=ReportConfiguration)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation_id", _identifier(self.validation_id, "validation_id"))
        object.__setattr__(
            self, "pipeline_run_id", _identifier(self.pipeline_run_id, "pipeline_run_id")
        )
        object.__setattr__(self, "module_name", _identifier(self.module_name, "module_name"))
        if self.report_id is not None:
            object.__setattr__(self, "report_id", _identifier(self.report_id, "report_id"))
        if not isinstance(self.research_use, bool):
            raise TypeError("research_use must be a bool.")
        if not isinstance(self.strict_evidence, bool):
            raise TypeError("strict_evidence must be a bool.")
        object.__setattr__(
            self,
            "engine_schema_version",
            _identifier(self.engine_schema_version, "engine_schema_version"),
        )
        if not isinstance(self.summary, SummaryConfiguration):
            raise TypeError("summary must be a SummaryConfiguration.")
        if not isinstance(self.recommendations, ActionPlanConfiguration):
            raise TypeError("recommendations must be an ActionPlanConfiguration.")
        if not isinstance(self.report, ReportConfiguration):
            raise TypeError("report must be a ReportConfiguration.")
        if not isinstance(self.stage_overrides, Mapping):
            raise TypeError("stage_overrides must be a mapping.")
        normalized_overrides: dict[PipelineStage, StageStatus] = {}
        for stage, status in self.stage_overrides.items():
            if not isinstance(stage, PipelineStage):
                raise TypeError("stage_overrides keys must be PipelineStage members.")
            if not isinstance(status, StageStatus):
                raise TypeError("stage_overrides values must be StageStatus members.")
            if status is StageStatus.COMPLETED:
                raise ValueError(
                    "Stage completion is controlled exclusively by successful evidence normalization."
                )
            normalized_overrides[stage] = status
        object.__setattr__(
            self, "stage_overrides", MappingProxyType(normalized_overrides)
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping.")
        metadata = {str(key): item for key, item in self.metadata.items()}
        collisions = sorted(_RESERVED_METADATA_KEYS.intersection(metadata))
        if collisions:
            raise ValueError(f"metadata uses workflow-reserved keys: {collisions}.")
        object.__setattr__(self, "metadata", _freeze(metadata))


@dataclass(frozen=True, slots=True)
class WorkflowArtifacts:
    """Persisted report paths with cryptographic integrity metadata."""

    markdown_report: Path
    json_report: Path
    markdown_sha256: str
    json_sha256: str
    markdown_size_bytes: int
    json_size_bytes: int

    def __post_init__(self) -> None:
        for field_name in ("markdown_report", "json_report"):
            value = getattr(self, field_name)
            if not isinstance(value, Path):
                raise TypeError(f"{field_name} must be a pathlib.Path.")
            path = value.expanduser()
            if not path.is_file():
                raise ValueError(f"{field_name} must reference an existing file.")
            object.__setattr__(self, field_name, path)
        if self.markdown_report == self.json_report:
            raise ValueError("Markdown and JSON artifacts must use different files.")
        for field_name in ("markdown_sha256", "json_sha256"):
            digest = _identifier(getattr(self, field_name), field_name)
            if len(digest) != 64:
                raise ValueError(f"{field_name} must be a SHA-256 hexadecimal digest.")
            object.__setattr__(self, field_name, digest)
        for field_name in ("markdown_size_bytes", "json_size_bytes"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        observed_markdown = _file_digest(self.markdown_report)
        observed_json = _file_digest(self.json_report)
        if observed_markdown != (self.markdown_sha256, self.markdown_size_bytes):
            raise ValueError("Markdown artifact integrity metadata does not match file content.")
        if observed_json != (self.json_sha256, self.json_size_bytes):
            raise ValueError("JSON artifact integrity metadata does not match file content.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "markdown_report": str(self.markdown_report),
            "json_report": str(self.json_report),
            "markdown_sha256": self.markdown_sha256,
            "json_sha256": self.json_sha256,
            "markdown_size_bytes": self.markdown_size_bytes,
            "json_size_bytes": self.json_size_bytes,
        }


@dataclass(frozen=True, slots=True)
class InterpretationWorkflowResult:
    """Complete immutable result of one end-to-end interpretation workflow."""

    evidence: EvidenceCatalog
    execution: EngineExecution
    summary: InterpretationSummary
    recommendation_plan: RecommendationPlan
    document: InterpretationDocument
    input_manifest: tuple[Mapping[str, Any], ...]
    stage_statuses: Mapping[PipelineStage, StageStatus]
    started_at: datetime
    completed_at: datetime
    evidence_catalog_fingerprint: str
    workflow_fingerprint: str
    artifacts: WorkflowArtifacts | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, EvidenceCatalog):
            raise TypeError("evidence must be an EvidenceCatalog.")
        if not isinstance(self.execution, EngineExecution):
            raise TypeError("execution must be an EngineExecution.")
        if not isinstance(self.summary, InterpretationSummary):
            raise TypeError("summary must be an InterpretationSummary.")
        if not isinstance(self.recommendation_plan, RecommendationPlan):
            raise TypeError("recommendation_plan must be a RecommendationPlan.")
        if not isinstance(self.document, InterpretationDocument):
            raise TypeError("document must be an InterpretationDocument.")
        manifest = tuple(_freeze(dict(item)) for item in self.input_manifest)
        if not manifest:
            raise ValueError("input_manifest must not be empty.")
        labels = [item["label"] for item in manifest]
        if len(labels) != len(set(labels)):
            raise ValueError("input_manifest labels must be unique.")
        if not isinstance(self.stage_statuses, Mapping):
            raise TypeError("stage_statuses must be a mapping.")
        stages: dict[PipelineStage, StageStatus] = {}
        for stage, status in self.stage_statuses.items():
            if not isinstance(stage, PipelineStage) or not isinstance(status, StageStatus):
                raise TypeError("stage_statuses must map PipelineStage to StageStatus.")
            stages[stage] = status
        if stages.get(PipelineStage.INGESTION) is not StageStatus.COMPLETED:
            raise ValueError("A successful workflow result must have completed ingestion.")
        for field_name in ("started_at", "completed_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime.")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware.")
        started = self.started_at.astimezone(UTC)
        completed = self.completed_at.astimezone(UTC)
        if completed < started:
            raise ValueError("completed_at cannot precede started_at.")
        if self.execution.started_at < started or self.execution.completed_at > completed:
            raise ValueError("Engine execution must be contained within workflow timestamps.")
        if self.summary.report_id != self.execution.report.report_id:
            raise ValueError("summary and execution must reference the same report.")
        if self.document.summary.report_id != self.summary.report_id:
            raise ValueError("document and summary must reference the same report.")
        if self.recommendation_plan.report_id != self.execution.report.report_id:
            raise ValueError("recommendation plan and execution must reference the same report.")
        if set(stages) != set(PipelineStage):
            raise ValueError("stage_statuses must contain every PipelineStage exactly once.")
        successful_manifest = tuple(
            item for item in manifest if item.get("normalization_status") == "completed"
        )
        if sum(int(item.get("evidence_count", 0)) for item in successful_manifest) != len(self.evidence):
            raise ValueError("Successful manifest evidence counts must equal the merged catalog size.")
        successful_stages = {PipelineStage(item["stage"]) for item in successful_manifest}
        completed_validation_stages = {
            stage
            for stage, status in stages.items()
            if status is StageStatus.COMPLETED
            and stage not in {PipelineStage.INGESTION, PipelineStage.REPORTING}
        }
        if successful_stages != completed_validation_stages:
            raise ValueError(
                "Completed validation stages must exactly match successfully normalized inputs."
            )
        evidence_fingerprint = _identifier(
            self.evidence_catalog_fingerprint, "evidence_catalog_fingerprint"
        )
        if len(evidence_fingerprint) != 64:
            raise ValueError("evidence_catalog_fingerprint must be a SHA-256 hexadecimal digest.")
        if evidence_fingerprint != _catalog_fingerprint(self.evidence):
            raise ValueError("evidence_catalog_fingerprint does not match canonical evidence content.")
        fingerprint = _identifier(self.workflow_fingerprint, "workflow_fingerprint")
        if len(fingerprint) != 64:
            raise ValueError("workflow_fingerprint must be a SHA-256 hexadecimal digest.")
        expected_fingerprint = _fingerprint(
            _workflow_fingerprint_payload(
                input_manifest=manifest,
                stage_statuses=stages,
                evidence_catalog_fingerprint=evidence_fingerprint,
                execution=self.execution,
                summary=self.summary,
                recommendation_plan=self.recommendation_plan,
                document=self.document,
            )
        )
        if fingerprint != expected_fingerprint:
            raise ValueError("workflow_fingerprint does not match workflow result content.")
        if self.artifacts is not None and not isinstance(self.artifacts, WorkflowArtifacts):
            raise TypeError("artifacts must be WorkflowArtifacts or None.")
        object.__setattr__(self, "input_manifest", manifest)
        object.__setattr__(self, "stage_statuses", MappingProxyType(stages))
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)
        object.__setattr__(self, "evidence_catalog_fingerprint", evidence_fingerprint)
        object.__setattr__(self, "workflow_fingerprint", fingerprint)

    @property
    def research_use_ready(self) -> bool:
        return (
            self.execution.research_use_ready
            and self.summary.research_use_ready
            and not self.recommendation_plan.blocking_items
        )

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.1.0",
            "workflow_version": WORKFLOW_VERSION,
            "workflow_fingerprint": self.workflow_fingerprint,
            "evidence_catalog_fingerprint": self.evidence_catalog_fingerprint,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "research_use_ready": self.research_use_ready,
            "stage_statuses": {
                stage.value: status.value
                for stage, status in sorted(
                    self.stage_statuses.items(), key=lambda item: item[0].value
                )
            },
            "input_manifest": [_serialize(item) for item in self.input_manifest],
            "evidence": self.evidence.to_dict(),
            "execution": {
                "report_id": self.execution.report.report_id,
                "pipeline_run_id": self.execution.report.pipeline_run_id,
                "execution_order": list(self.execution.execution_order),
                "execution_status_counts": dict(self.execution.execution_status_counts),
                "research_use_ready": self.execution.research_use_ready,
            },
            "summary": self.summary.to_dict(),
            "recommendation_plan": self.recommendation_plan.to_dict(),
            "document": self.document.to_dict(),
            "artifacts": self.artifacts.to_dict() if self.artifacts else None,
        }


class InterpretationWorkflow:
    """Application service that runs the complete interpretation lifecycle."""

    __slots__ = ("_engine", "_registry")

    def __init__(
        self,
        *,
        engine: InterpretationEngine | None = None,
        registry: EvidenceRegistry = DEFAULT_EVIDENCE_REGISTRY,
    ) -> None:
        self._engine = engine or InterpretationEngine()
        if not isinstance(self._engine, InterpretationEngine):
            raise TypeError("engine must be an InterpretationEngine or None.")
        if not isinstance(registry, EvidenceRegistry):
            raise TypeError("registry must be an EvidenceRegistry.")
        self._registry = registry

    @property
    def engine(self) -> InterpretationEngine:
        return self._engine

    @property
    def registry(self) -> EvidenceRegistry:
        return self._registry

    @staticmethod
    def _normalize_inputs(
        inputs: Sequence[InterpretationInput],
    ) -> tuple[InterpretationInput, ...]:
        if isinstance(inputs, (str, bytes)) or not isinstance(inputs, Sequence):
            raise TypeError("inputs must be a sequence of InterpretationInput values.")
        normalized = tuple(inputs)
        if not normalized:
            raise InterpretationWorkflowError("At least one interpretation input is required.")
        if not all(isinstance(item, InterpretationInput) for item in normalized):
            raise TypeError("inputs must contain InterpretationInput values only.")
        labels = tuple(
            item.label or f"{item.stage.value}.{position + 1}"
            for position, item in enumerate(normalized)
        )
        if len(labels) != len(set(labels)):
            raise InterpretationWorkflowError("Input labels must be unique.")
        stages = [item.stage for item in normalized]
        duplicates = sorted(
            {stage.value for stage in stages if stages.count(stage) > 1}
        )
        if duplicates:
            raise InterpretationWorkflowError(
                "Only one canonical output per validation stage is accepted; "
                f"duplicates: {duplicates}."
            )
        return normalized

    @staticmethod
    def _build_stage_statuses(
        inputs: tuple[InterpretationInput, ...],
        overrides: Mapping[PipelineStage, StageStatus],
    ) -> Mapping[PipelineStage, StageStatus]:
        stages = {stage: StageStatus.NOT_RUN for stage in PipelineStage}
        stages[PipelineStage.INGESTION] = StageStatus.COMPLETED
        for item in inputs:
            stages[item.stage] = StageStatus.COMPLETED
        for stage, status in overrides.items():
            if stage in {item.stage for item in inputs} and status is not StageStatus.COMPLETED:
                raise InterpretationWorkflowError(
                    f"Stage {stage.value!r} has a successfully normalized input but override "
                    f"declares {status.value!r}."
                )
            stages[stage] = status
        return MappingProxyType(stages)

    def run(
        self,
        inputs: Sequence[InterpretationInput],
        *,
        config: InterpretationWorkflowConfig,
    ) -> InterpretationWorkflowResult:
        """Run the workflow without writing files."""

        return self._run(inputs, config=config, output_directory=None, stem=None)

    def run_and_write(
        self,
        inputs: Sequence[InterpretationInput],
        *,
        config: InterpretationWorkflowConfig,
        output_directory: str | Path,
        stem: str | None = None,
    ) -> InterpretationWorkflowResult:
        """Run the workflow and atomically persist Markdown and JSON reports."""

        return self._run(
            inputs,
            config=config,
            output_directory=Path(output_directory),
            stem=stem,
        )

    def _run(
        self,
        inputs: Sequence[InterpretationInput],
        *,
        config: InterpretationWorkflowConfig,
        output_directory: Path | None,
        stem: str | None,
    ) -> InterpretationWorkflowResult:
        if not isinstance(config, InterpretationWorkflowConfig):
            raise TypeError("config must be an InterpretationWorkflowConfig.")
        normalized_inputs = self._normalize_inputs(inputs)
        started_at = datetime.now(UTC)

        catalogs: list[EvidenceCatalog] = []
        successful_inputs: list[InterpretationInput] = []
        manifest: list[dict[str, Any]] = []
        for position, item in enumerate(normalized_inputs):
            label = item.label or f"{item.stage.value}.{position + 1}"
            try:
                catalog = collect_evidence(
                    item.source,
                    strict=config.strict_evidence,
                    registry=self._registry,
                )
            except Exception as exc:
                manifest.append(
                    {
                        "label": label,
                        "stage": item.stage.value,
                        "required": item.required,
                        "source_type": item.source_type,
                        "normalization_status": "failed",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "evidence_count": 0,
                        "available_count": 0,
                        "unavailable_count": 0,
                        "metric_ids_fingerprint": None,
                        "evidence_fingerprint": None,
                    }
                )
                if item.required:
                    raise InterpretationWorkflowError(
                        f"Required input {label!r} for stage {item.stage.value!r} "
                        f"could not be normalized: {type(exc).__name__}: {exc}"
                    ) from exc
                continue
            catalogs.append(catalog)
            successful_inputs.append(item)
            manifest.append(
                {
                    "label": label,
                    "stage": item.stage.value,
                    "required": item.required,
                    "source_type": item.source_type,
                    "normalization_status": "completed",
                    "error_type": None,
                    "error_message": None,
                    "evidence_count": len(catalog),
                    "available_count": len(catalog.available),
                    "unavailable_count": len(catalog.unavailable),
                    "metric_ids_fingerprint": _fingerprint(
                        tuple(value.metric_id for value in catalog)
                    ),
                    "evidence_fingerprint": _catalog_fingerprint(catalog),
                }
            )

        if not catalogs:
            raise InterpretationWorkflowError(
                "No input produced evidence; interpretation cannot proceed."
            )
        evidence = catalogs[0]
        try:
            evidence = evidence.merge(*catalogs[1:])
        except Exception as exc:
            raise InterpretationWorkflowError(
                f"Evidence catalogs cannot be merged safely: {type(exc).__name__}: {exc}"
            ) from exc

        stages = self._build_stage_statuses(tuple(successful_inputs), config.stage_overrides)
        workflow_metadata = dict(config.metadata)
        workflow_metadata.update(
            {
                "workflow": {
                    "version": WORKFLOW_VERSION,
                    "input_count": len(manifest),
                    "strict_evidence": config.strict_evidence,
                },
                "input_manifest": manifest,
                "evidence_metric_count": len(evidence),
            }
        )
        engine_config = InterpretationEngineConfig(
            validation_id=config.validation_id,
            pipeline_run_id=config.pipeline_run_id,
            module_name=config.module_name,
            report_id=config.report_id,
            stages=stages,
            research_use=config.research_use,
            schema_version=config.engine_schema_version,
            metadata=workflow_metadata,
        )
        execution = self._engine.execute(evidence, config=engine_config)
        summary = build_interpretation_summary(
            execution,
            configuration=config.summary,
        )
        recommendation_plan = build_recommendation_plan(
            execution,
            configuration=config.recommendations,
            metadata={"workflow_version": WORKFLOW_VERSION},
        )
        document = build_interpretation_document(
            execution,
            summary=summary,
            configuration=config.report,
            metadata={
                "workflow_version": WORKFLOW_VERSION,
                "recommendation_plan_fingerprint": recommendation_plan.fingerprint,
            },
        )

        artifacts: WorkflowArtifacts | None = None
        if output_directory is not None:
            markdown_path, json_path = write_report_bundle(
                document,
                output_directory,
                stem=stem,
            )
            markdown_digest, markdown_size = _file_digest(markdown_path)
            json_digest, json_size = _file_digest(json_path)
            artifacts = WorkflowArtifacts(
                markdown_report=markdown_path,
                json_report=json_path,
                markdown_sha256=markdown_digest,
                json_sha256=json_digest,
                markdown_size_bytes=markdown_size,
                json_size_bytes=json_size,
            )

        completed_at = datetime.now(UTC)
        evidence_catalog_fingerprint = _catalog_fingerprint(evidence)
        fingerprint_payload = _workflow_fingerprint_payload(
            input_manifest=manifest,
            stage_statuses=stages,
            evidence_catalog_fingerprint=evidence_catalog_fingerprint,
            execution=execution,
            summary=summary,
            recommendation_plan=recommendation_plan,
            document=document,
        )
        return InterpretationWorkflowResult(
            evidence=evidence,
            execution=execution,
            summary=summary,
            recommendation_plan=recommendation_plan,
            document=document,
            input_manifest=tuple(manifest),
            stage_statuses=stages,
            started_at=started_at,
            completed_at=completed_at,
            evidence_catalog_fingerprint=evidence_catalog_fingerprint,
            workflow_fingerprint=_fingerprint(fingerprint_payload),
            artifacts=artifacts,
        )