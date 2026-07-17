"""Root-cause analysis stage for the Experiment Orchestrator.

This module is the application boundary between the Phase 2B orchestration
pipeline and the Phase 3 Root Cause Engine.

The handler:

* loads already-produced upstream scientific outputs;
* builds a canonical ``RootCauseRequest``;
* executes the injected ``RootCauseEngine``;
* persists deterministic JSON and Markdown representations;
* returns immutable artefact references to the Orchestrator.

It does not duplicate evidence normalization, causal inference, report rendering
or manifest serialization.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from validation.orchestration.adapters.root_cause import (
    RootCauseRequestAdapter,
    RootCauseRequestSource,
)
from validation.orchestration.models import (
    ArtifactKind,
    ExperimentStage,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
    StageOutput,
)
from validation.root_cause.engine import (
    EngineInputs,
    RootCauseEngine,
    RootCauseEngineResult,
)
from validation.root_cause.models import RootCauseStatus
from validation.root_cause.report import (
    ReportConfiguration,
    build_root_cause_document,
    render_json_report,
    render_markdown_report,
)


_ROOT_CAUSE_PRODUCER = "root_cause_engine"
_ROOT_CAUSE_RESULT_PATH = "root_cause/root_cause_result.json"
_ROOT_CAUSE_REPORT_PATH = "root_cause/root_cause_report.md"


@dataclass(frozen=True, slots=True)
class RootCauseStagePayload:
    """Complete typed input required by the root-cause stage."""

    request_source: RootCauseRequestSource
    engine_inputs: EngineInputs

    def __post_init__(self) -> None:
        if not isinstance(self.request_source, RootCauseRequestSource):
            raise TypeError(
                "request_source must be a RootCauseRequestSource."
            )
        if not isinstance(self.engine_inputs, EngineInputs):
            raise TypeError("engine_inputs must be EngineInputs.")


@runtime_checkable
class RootCauseStageInputProvider(Protocol):
    """Load upstream domain objects required by the Root Cause Engine."""

    def load(
        self,
        context: OrchestrationContext,
    ) -> RootCauseStagePayload:
        """Load and validate all upstream causal-analysis inputs."""


@dataclass(frozen=True, slots=True)
class RootCauseStageHandler:
    """Execute and persist one complete root-cause investigation."""

    input_provider: RootCauseStageInputProvider
    engine: RootCauseEngine = field(default_factory=RootCauseEngine)
    request_adapter: RootCauseRequestAdapter = field(
        default_factory=RootCauseRequestAdapter
    )
    report_configuration: ReportConfiguration = field(
        default_factory=ReportConfiguration
    )
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    stage: ExperimentStage = field(
        default=ExperimentStage.ROOT_CAUSE_ANALYSIS,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.input_provider, RootCauseStageInputProvider):
            raise TypeError(
                "input_provider must implement RootCauseStageInputProvider."
            )
        if not isinstance(self.engine, RootCauseEngine):
            raise TypeError("engine must be a RootCauseEngine.")
        if not isinstance(self.request_adapter, RootCauseRequestAdapter):
            raise TypeError(
                "request_adapter must be a RootCauseRequestAdapter."
            )
        if not isinstance(
            self.report_configuration,
            ReportConfiguration,
        ):
            raise TypeError(
                "report_configuration must be a ReportConfiguration."
            )
        if not callable(self.clock):
            raise TypeError("clock must be callable.")

    def execute(
        self,
        context: OrchestrationContext,
    ) -> StageOutput:
        """Execute Phase 3 and persist its canonical outputs."""

        if not isinstance(context, OrchestrationContext):
            raise TypeError(
                "context must be an OrchestrationContext."
            )

        payload = self.input_provider.load(context)

        created_at = _aware_datetime(
            self.clock(),
            "clock result",
        )

        request = self.request_adapter.build(
            payload.request_source,
            created_at=created_at,
        )

        engine_result = self.engine.run(
            request,
            payload.engine_inputs,
        )

        document_generated_at = max(
            _aware_datetime(self.clock(), "clock result"),
            engine_result.report.generated_at,
        )

        document = build_root_cause_document(
            engine_result,
            configuration=self.report_configuration,
            generated_at=document_generated_at,
            metadata={
                "orchestrator_run_id": context.run_id,
                "experiment_id": context.config.id,
                "stage": self.stage.value,
            },
        )

        json_path = context.workspace.write_text(
            _ROOT_CAUSE_RESULT_PATH,
            render_json_report(document),
        )
        markdown_path = context.workspace.write_text(
            _ROOT_CAUSE_REPORT_PATH,
            render_markdown_report(document),
        )

        json_artifact = context.workspace.artifact_reference(
            artifact_id=_artifact_id(
                context,
                suffix="result",
            ),
            kind=ArtifactKind.ROOT_CAUSE_RESULT,
            path=json_path,
            media_type="application/json",
            producer=_ROOT_CAUSE_PRODUCER,
            created_at=created_at,
            metadata={
                "schema_version": engine_result.schema_version,
                "request_id": request.id,
                "report_id": engine_result.report.id,
                "root_cause_status": engine_result.report.status.value,
                "causal_confidence": (
                    engine_result.report.confidence.value
                ),
                "document_fingerprint": (
                    document.document_fingerprint
                ),
            },
        )

        markdown_artifact = context.workspace.artifact_reference(
            artifact_id=_artifact_id(
                context,
                suffix="report",
            ),
            kind=ArtifactKind.REPORT,
            path=markdown_path,
            media_type="text/markdown; charset=utf-8",
            producer=_ROOT_CAUSE_PRODUCER,
            created_at=created_at,
            metadata={
                "report_type": "root_cause",
                "request_id": request.id,
                "report_id": engine_result.report.id,
                "root_cause_status": engine_result.report.status.value,
                "document_fingerprint": (
                    document.document_fingerprint
                ),
            },
        )

        return StageOutput(
            artifacts=(
                json_artifact,
                markdown_artifact,
            ),
            summary=_stage_summary(engine_result),
            metadata={
                "request_id": request.id,
                "report_id": engine_result.report.id,
                "root_cause_status": (
                    engine_result.report.status.value
                ),
                "causal_confidence": (
                    engine_result.report.confidence.value
                ),
                "finding_count": len(
                    engine_result.report.findings
                ),
                "signal_count": len(
                    engine_result.report.signals
                ),
                "candidate_count": len(
                    engine_result.report.candidates
                ),
                "verification_count": len(
                    engine_result.report.verifications
                ),
                "reproduction_plan_count": len(
                    engine_result.report.reproduction_plans
                ),
                "engine_schema_version": (
                    engine_result.schema_version
                ),
                "document_fingerprint": (
                    document.document_fingerprint
                ),
            },
        )


def _artifact_id(
    context: OrchestrationContext,
    *,
    suffix: str,
) -> str:
    return (
        f"{context.config.id}."
        f"{context.run_id}."
        f"root-cause."
        f"{suffix}"
    )


def _stage_summary(
    result: RootCauseEngineResult,
) -> str:
    report = result.report

    if report.status is RootCauseStatus.NOT_APPLICABLE:
        return (
            "Root-cause analysis completed successfully; "
            "no causal investigation was applicable."
        )

    return (
        "Root-cause analysis completed with "
        f"{len(report.findings)} finding(s), "
        f"{len(report.candidates)} candidate(s) and "
        f"status {report.status.value!r}."
    )


def _aware_datetime(
    value: datetime,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} must be timezone-aware."
        )
    return value.astimezone(UTC)