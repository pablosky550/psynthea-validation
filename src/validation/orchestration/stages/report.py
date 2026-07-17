"""Final scientific-report generation stage.

The stage composes the already persisted validation, interpretation and
root-cause products into one experiment-level report.  It deliberately performs
no statistical recalculation, evidence acquisition or causal inference.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
import json
from pathlib import Path
from typing import Any, Final

from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExecutionStatus,
    ExperimentStage,
    ReportFormat,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
    StageOutput,
)

__all__ = [
    "ReportGenerationStageError",
    "ReportGenerationStageHandler",
]

_REPORT_SCHEMA_VERSION: Final = "1.0"
_REPORT_PRODUCER: Final = "scientific_report_stage"
_REPORT_JSON_PATH: Final = "report/scientific_report.json"
_REPORT_HTML_PATH: Final = "report/scientific_report.html"

_REQUIRED_UPSTREAM_ARTIFACTS: Final = {
    ArtifactKind.VALIDATION_RESULT: "validation result",
    ArtifactKind.KNOWLEDGE_RESULT: "knowledge result",
    ArtifactKind.ROOT_CAUSE_RESULT: "root-cause result",
}


class ReportGenerationStageError(RuntimeError):
    """Raised when a truthful final report cannot be composed."""


@dataclass(frozen=True, slots=True)
class ReportGenerationStageHandler:
    """Compose the final experiment-level scientific report."""

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    stage: ExperimentStage = field(
        default=ExperimentStage.REPORT_GENERATION,
        init=False,
    )

    def __post_init__(self) -> None:
        if not callable(self.clock):
            raise TypeError("clock must be callable.")

    def execute(self, context: OrchestrationContext) -> StageOutput:
        if not isinstance(context, OrchestrationContext):
            raise TypeError("context must be an OrchestrationContext.")

        generated_at = _aware_datetime(self.clock(), "clock result")
        source_artifacts = _required_source_artifacts(context.artifacts)
        source_payloads = {
            kind: _read_verified_json(context, artifact)
            for kind, artifact in source_artifacts.items()
        }

        payload = _build_report_payload(
            context,
            generated_at=generated_at,
            source_artifacts=source_artifacts,
            source_payloads=source_payloads,
        )

        unsupported = tuple(
            item for item in context.config.report_formats
            if item not in {ReportFormat.JSON, ReportFormat.HTML}
        )
        if unsupported:
            names = ", ".join(item.value for item in unsupported)
            raise ReportGenerationStageError(
                "Unsupported final report format(s): " + names + "."
            )

        artifacts: list[ArtifactReference] = []
        generated_formats: list[str] = []

        if ReportFormat.JSON in context.config.report_formats:
            path = context.workspace.write_json(_REPORT_JSON_PATH, payload)
            artifacts.append(
                context.workspace.artifact_reference(
                    artifact_id=_artifact_id(context, "json"),
                    kind=ArtifactKind.REPORT,
                    path=path,
                    media_type="application/json",
                    producer=_REPORT_PRODUCER,
                    created_at=generated_at,
                    metadata=_artifact_metadata(payload, "json"),
                )
            )
            generated_formats.append(ReportFormat.JSON.value)

        if ReportFormat.HTML in context.config.report_formats:
            path = context.workspace.write_text(
                _REPORT_HTML_PATH,
                _render_html(payload),
            )
            artifacts.append(
                context.workspace.artifact_reference(
                    artifact_id=_artifact_id(context, "html"),
                    kind=ArtifactKind.REPORT,
                    path=path,
                    media_type="text/html; charset=utf-8",
                    producer=_REPORT_PRODUCER,
                    created_at=generated_at,
                    metadata=_artifact_metadata(payload, "html"),
                )
            )
            generated_formats.append(ReportFormat.HTML.value)

        if not artifacts:
            raise ReportGenerationStageError(
                "No supported final report format was requested."
            )

        return StageOutput(
            artifacts=tuple(artifacts),
            summary=(
                "Generated final scientific report in "
                + ", ".join(generated_formats)
                + f" format(s); decision={payload['decision']}."
            ),
            metadata={
                "schema_version": _REPORT_SCHEMA_VERSION,
                "decision": payload["decision"],
                "formats": tuple(generated_formats),
                "source_artifact_count": len(source_artifacts),
                "report_artifact_count": len(artifacts),
            },
        )


def _required_source_artifacts(
    artifacts: Sequence[ArtifactReference],
) -> Mapping[ArtifactKind, ArtifactReference]:
    if isinstance(artifacts, (str, bytes)):
        raise TypeError("artifacts must be a sequence.")

    resolved: dict[ArtifactKind, ArtifactReference] = {}
    for kind, description in _REQUIRED_UPSTREAM_ARTIFACTS.items():
        candidates = tuple(
            artifact for artifact in artifacts
            if artifact.kind is kind
        )
        if len(candidates) != 1:
            raise ReportGenerationStageError(
                "Final report generation requires exactly one "
                f"{description} artifact; found {len(candidates)}."
            )
        resolved[kind] = candidates[0]
    return resolved


def _read_verified_json(
    context: OrchestrationContext,
    artifact: ArtifactReference,
) -> Mapping[str, Any]:
    if artifact.media_type.split(";", 1)[0].strip() != "application/json":
        raise ReportGenerationStageError(
            f"Source artifact {artifact.id!r} is not JSON."
        )

    path = context.workspace.resolve(artifact.path)
    if not path.is_file() or path.is_symlink():
        raise ReportGenerationStageError(
            f"Source artifact {artifact.id!r} is missing or unsafe."
        )

    content = path.read_bytes()
    from hashlib import sha256

    if artifact.size_bytes is not None and len(content) != artifact.size_bytes:
        raise ReportGenerationStageError(
            f"Source artifact {artifact.id!r} size changed."
        )
    if artifact.sha256 is not None and sha256(content).hexdigest() != artifact.sha256:
        raise ReportGenerationStageError(
            f"Source artifact {artifact.id!r} hash changed."
        )

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReportGenerationStageError(
            f"Cannot read source artifact {artifact.id!r}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReportGenerationStageError(
            f"Source artifact {artifact.id!r} root must be an object."
        )
    return payload


def _build_report_payload(
    context: OrchestrationContext,
    *,
    generated_at: datetime,
    source_artifacts: Mapping[ArtifactKind, ArtifactReference],
    source_payloads: Mapping[ArtifactKind, Mapping[str, Any]],
) -> dict[str, Any]:
    validation = source_payloads[ArtifactKind.VALIDATION_RESULT]
    knowledge = source_payloads[ArtifactKind.KNOWLEDGE_RESULT]
    root_cause = source_payloads[ArtifactKind.ROOT_CAUSE_RESULT]

    decision = _decision(context)
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "experiment_id": context.config.id,
        "experiment_name": context.config.name,
        "run_id": context.run_id,
        "generated_at": generated_at.isoformat(),
        "decision": decision,
        "description": context.config.description,
        "tags": list(context.config.tags),
        "cohort": {
            "population_size": context.config.cohort.population_size,
            "seed": context.config.cohort.seed,
            "modules": list(context.config.cohort.modules),
            "reference_date": (
                context.config.cohort.reference_date.isoformat()
                if context.config.cohort.reference_date is not None
                else None
            ),
        },
        "stage_summary": [
            {
                "stage": result.stage.value,
                "status": result.status.value,
                "summary": result.summary,
                "error_message": result.error_message,
                "metadata": _plain_value(result.metadata),
            }
            for result in context.stage_results
        ],
        "scientific_results": {
            "validation": _scientific_summary(validation),
            "knowledge": _scientific_summary(knowledge),
            "root_cause": _scientific_summary(root_cause),
        },
        "source_artifacts": {
            kind.value: _artifact_payload(artifact)
            for kind, artifact in source_artifacts.items()
        },
        "artifact_count_before_report": len(context.artifacts),
    }


def _decision(context: OrchestrationContext) -> str:
    relevant = tuple(
        result for result in context.stage_results
        if result.stage in {
            ExperimentStage.VALIDATION,
            ExperimentStage.KNOWLEDGE_ENRICHMENT,
            ExperimentStage.ROOT_CAUSE_ANALYSIS,
        }
    )
    if any(result.status is not ExecutionStatus.SUCCEEDED for result in relevant):
        return "INCOMPLETE"

    validation = context.stage_result(ExperimentStage.VALIDATION)
    knowledge = context.stage_result(ExperimentStage.KNOWLEDGE_ENRICHMENT)
    root_cause = context.stage_result(ExperimentStage.ROOT_CAUSE_ANALYSIS)

    blocking = int((knowledge.metadata if knowledge else {}).get("blocking_finding_count", 0))
    root_status = str((root_cause.metadata if root_cause else {}).get("root_cause_status", ""))
    validation_status = str((validation.metadata if validation else {}).get("overall_status", "")).lower()

    if blocking > 0 or root_status.lower() in {"confirmed", "probable"}:
        return "REVIEW"
    if validation_status in {"failed", "fail", "rejected"}:
        return "REVIEW"
    return "PASS"


def _scientific_summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    preferred = (
        "schema_version", "aggregate", "summary", "decision",
        "status", "root_cause_status", "report_id", "request_id",
    )
    result = {key: _plain_value(payload[key]) for key in preferred if key in payload}
    if not result:
        result = {"keys": sorted(str(key) for key in payload)}
    return result


def _artifact_payload(artifact: ArtifactReference) -> dict[str, Any]:
    return {
        "artifact_id": artifact.id,
        "path": artifact.path.as_posix(),
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "producer": artifact.producer,
    }


def _artifact_metadata(payload: Mapping[str, Any], report_format: str) -> Mapping[str, Any]:
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "report_type": "final_scientific_report",
        "format": report_format,
        "decision": payload["decision"],
        "source_artifact_count": len(payload["source_artifacts"]),
    }


def _artifact_id(context: OrchestrationContext, suffix: str) -> str:
    return f"{context.config.id}.{context.run_id}.scientific-report.{suffix}"


def _render_html(payload: Mapping[str, Any]) -> str:
    stage_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(item['stage']))}</td>"
        f"<td>{escape(str(item['status']))}</td>"
        f"<td>{escape(str(item.get('summary') or ''))}</td>"
        "</tr>"
        for item in payload["stage_summary"]
    )
    artifacts = "\n".join(
        f"<li><strong>{escape(kind)}</strong>: "
        f"<code>{escape(str(item['path']))}</code> "
        f"(<code>{escape(str(item['sha256']))}</code>)</li>"
        for kind, item in payload["source_artifacts"].items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(str(payload['experiment_name']))}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;line-height:1.5}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:8px;text-align:left}}code{{overflow-wrap:anywhere}}.decision{{font-size:1.4rem;font-weight:700}}
</style>
</head>
<body>
<h1>{escape(str(payload['experiment_name']))}</h1>
<p><strong>Experiment:</strong> {escape(str(payload['experiment_id']))}</p>
<p><strong>Run:</strong> {escape(str(payload['run_id']))}</p>
<p class="decision">Decision: {escape(str(payload['decision']))}</p>
<h2>Pipeline stages</h2>
<table><thead><tr><th>Stage</th><th>Status</th><th>Summary</th></tr></thead><tbody>{stage_rows}</tbody></table>
<h2>Scientific source artifacts</h2><ul>{artifacts}</ul>
<h2>Machine-readable summary</h2>
<pre>{escape(json.dumps(payload['scientific_results'], ensure_ascii=False, indent=2, sort_keys=True))}</pre>
</body>
</html>
"""


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain_value(item) for item in value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)