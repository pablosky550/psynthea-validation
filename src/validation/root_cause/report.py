"""Deterministic scientific rendering for Phase 3 root-cause analyses.

This module is a presentation boundary.  It transforms an already validated
:class:`~validation.root_cause.models.RootCauseReport` (or the richer
:class:`~validation.root_cause.engine.RootCauseEngineResult`) into stable JSON
and Markdown documents without recalculating scores, changing causal status,
or inferring information that is absent from the engine output.

Scientific safety rules
-----------------------
* Rendering never promotes or demotes a causal conclusion.
* Selected, alternative, and rejected candidates remain distinguishable.
* Supporting and contradictory evidence are always rendered separately.
* Technical verifier errors remain technical errors, never causal findings.
* Unknown attribution remains explicitly unknown.
* Limitations and unresolved questions are never hidden.
* Machine-readable output is canonical, deterministic, and fingerprinted.
* File writes are atomic, UTF-8 encoded, and optionally integrity-checked.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from hashlib import sha256
from json import dumps
from math import isfinite
from os import fsync, replace
from pathlib import Path, PurePath
from re import compile as compile_pattern
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import Any, Final

from validation.root_cause.engine import EngineStage, RootCauseEngineResult, StageRecord
from validation.root_cause.models import (
    AttributionLevel,
    CandidateAssessment,
    CausalCandidate,
    EvidenceReference,
    ReproductionPlan,
    RootCauseFinding,
    RootCauseReport,
    RootCauseStatus,
    VerificationOutcome,
    VerificationResult,
)

__all__ = [
    "ReportBundle",
    "ReportConfiguration",
    "ReportConsistencyError",
    "RootCauseDocument",
    "build_root_cause_document",
    "render_json_report",
    "render_markdown_report",
    "write_json_report",
    "write_markdown_report",
    "write_report_bundle",
]

_SCHEMA_NAME: Final = "psynthea.root_cause.report"
_SCHEMA_VERSION: Final = "2.0.0"
_SAFE_STEM_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_STATUS_ORDER: Final = {
    RootCauseStatus.CONFIRMED: 0,
    RootCauseStatus.PROBABLE: 1,
    RootCauseStatus.MULTIFACTORIAL: 2,
    RootCauseStatus.EXPECTED_DIFFERENCE: 3,
    RootCauseStatus.IMPLEMENTATION_LIMITATION: 4,
    RootCauseStatus.PLAUSIBLE: 5,
    RootCauseStatus.INCONCLUSIVE: 6,
    RootCauseStatus.NOT_APPLICABLE: 7,
}

_OUTCOME_LABELS: Final = {
    VerificationOutcome.PASSED: "PASSED",
    VerificationOutcome.FAILED: "FAILED",
    VerificationOutcome.INCONCLUSIVE: "INCONCLUSIVE",
    VerificationOutcome.ERROR: "ERROR",
    VerificationOutcome.SKIPPED: "SKIPPED",
    VerificationOutcome.NOT_RUN: "NOT RUN",
}


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Report metadata mapping keys must be strings.")
            frozen[key] = _freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _serialize(value: Any) -> Any:
    """Convert supported values into deterministic JSON-compatible data."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise TypeError("Report values cannot contain NaN or infinity.")
        return value
    if isinstance(value, datetime):
        return _aware_datetime(value, "datetime").isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Enum):
        return _serialize(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _serialize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        serialized = [_serialize(item) for item in value]
        return sorted(
            serialized,
            key=lambda item: dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _serialize(getattr(value, item.name))
            for item in fields(value)
        }
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _serialize(to_dict())
    raise TypeError(f"Unsupported report value type: {type(value).__name__}.")


def _canonical_json_bytes(value: Any) -> bytes:
    return dumps(
        _serialize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _escape_cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|") or "—"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "_No data available._"
    normalized_headers = [_escape_cell(item) for item in headers]
    lines = [
        "| " + " | ".join(normalized_headers) + " |",
        "| " + " | ".join("---" for _ in normalized_headers) + " |",
    ]
    for row in rows:
        if len(row) != len(headers):
            raise ValueError("Every Markdown table row must match the header length.")
        lines.append("| " + " | ".join(_escape_cell(item) for item in row) + " |")
    return "\n".join(lines)


def _bullet(value: str, *, indent: int = 0) -> str:
    return f"{'  ' * indent}- {' '.join(value.strip().split())}"


def _display_command(command: Sequence[str]) -> str:
    def quote(token: str) -> str:
        if token and all(character.isalnum() or character in "-._/:=@+" for character in token):
            return token
        return "'" + token.replace("'", "'\\''") + "'"

    return " ".join(quote(token) for token in command)


def _safe_stem(value: str) -> str:
    stem = value.strip()
    if not _SAFE_STEM_PATTERN.fullmatch(stem):
        raise ValueError(
            "file_stem must contain only letters, numbers, '.', '_' or '-', "
            "begin with an alphanumeric character, and be at most 128 characters."
        )
    return stem


class ReportConsistencyError(ValueError):
    """Raised when report-ready data is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class ReportConfiguration:
    """Presentation policy for root-cause JSON and Markdown documents."""

    title: str = "Psynthea Root Cause Analysis Report"
    include_candidate_details: bool = True
    include_evidence_details: bool = True
    include_verification_details: bool = True
    include_reproduction_details: bool = True
    include_artifacts: bool = True
    include_engine_trace: bool = True
    include_metadata: bool = True
    maximum_evidence_items_per_finding: int = 50
    maximum_candidates_per_finding: int = 25

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _non_empty_text(self.title, "title"))
        for name in (
            "include_candidate_details",
            "include_evidence_details",
            "include_verification_details",
            "include_reproduction_details",
            "include_artifacts",
            "include_engine_trace",
            "include_metadata",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool.")
        for name in (
            "maximum_evidence_items_per_finding",
            "maximum_candidates_per_finding",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class RootCauseDocument:
    """Immutable, report-ready view of one root-cause investigation."""

    report: RootCauseReport
    configuration: ReportConfiguration
    generated_at: datetime
    engine_schema_version: int | None = None
    stages: tuple[StageRecord, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.report, RootCauseReport):
            raise TypeError("report must be a RootCauseReport.")
        if not isinstance(self.configuration, ReportConfiguration):
            raise TypeError("configuration must be a ReportConfiguration.")
        generated = _aware_datetime(self.generated_at, "generated_at")
        if generated < self.report.generated_at:
            raise ValueError("generated_at cannot precede report.generated_at.")
        object.__setattr__(self, "generated_at", generated)
        if self.engine_schema_version is not None:
            if isinstance(self.engine_schema_version, bool) or not isinstance(
                self.engine_schema_version, int
            ):
                raise TypeError("engine_schema_version must be an integer or None.")
            if self.engine_schema_version <= 0:
                raise ValueError("engine_schema_version must be positive.")
        stages = tuple(self.stages)
        if not all(isinstance(item, StageRecord) for item in stages):
            raise TypeError("stages must contain StageRecord values only.")
        if stages:
            expected = tuple(EngineStage)
            actual = tuple(item.stage for item in stages)
            if actual != expected:
                raise ReportConsistencyError(
                    "stages must contain every engine stage exactly once in canonical order."
                )
        object.__setattr__(self, "stages", stages)
        object.__setattr__(self, "metadata", _freeze(self.metadata))
        _validate_document(self)

    @property
    def document_fingerprint(self) -> str:
        return _fingerprint(self._payload_without_fingerprint())

    @property
    def selected_candidate_count(self) -> int:
        return len(
            {
                candidate_id
                for finding in self.report.findings
                for candidate_id in finding.selected_candidate_ids
            }
        )

    def _payload_without_fingerprint(self) -> dict[str, Any]:
        report = self.report
        payload: dict[str, Any] = {
            "schema": _SCHEMA_NAME,
            "schema_version": _SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "title": self.configuration.title,
            "identity": {
                "report_id": report.id,
                "request_id": report.request_id,
                "experiment_id": report.experiment_id,
                "run_id": report.run_id,
            },
            "conclusion": {
                "status": report.status,
                "confidence": report.confidence,
                "executive_summary": report.executive_summary,
            },
            "counts": {
                "signals": len(report.signals),
                "evidence": len(report.evidence),
                "candidates": len(report.candidates),
                "selected_candidates": self.selected_candidate_count,
                "verifications": len(report.verifications),
                "findings": len(report.findings),
                "reproduction_plans": len(report.reproduction_plans),
                "artifacts": len(report.artifacts),
            },
            "signals": report.signals,
            "findings": report.findings,
            "unresolved_questions": report.unresolved_questions,
            "limitations": report.limitations,
        }
        if self.configuration.include_candidate_details:
            payload["candidates"] = report.candidates
            payload["assessments"] = report.assessments
        if self.configuration.include_evidence_details:
            payload["evidence"] = report.evidence
        if self.configuration.include_verification_details:
            payload["verifications"] = report.verifications
        if self.configuration.include_reproduction_details:
            payload["reproduction_plans"] = report.reproduction_plans
        if self.configuration.include_artifacts:
            payload["artifacts"] = report.artifacts
        if self.configuration.include_engine_trace and self.stages:
            payload["engine"] = {
                "schema_version": self.engine_schema_version,
                "stages": self.stages,
                "total_duration_seconds": sum(item.duration_seconds for item in self.stages),
            }
        if self.configuration.include_metadata:
            payload["metadata"] = {
                "report": report.metadata,
                "document": self.metadata,
            }
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = _serialize(self._payload_without_fingerprint())
        payload["document_fingerprint"] = _fingerprint(payload)
        return payload


@dataclass(frozen=True, slots=True)
class ReportBundle:
    """References and hashes for one atomically written JSON/Markdown bundle."""

    markdown_path: Path
    json_path: Path
    manifest_path: Path
    markdown_sha256: str
    json_sha256: str
    manifest_sha256: str
    document_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("markdown_path", "json_path", "manifest_path"):
            value = getattr(self, name)
            if not isinstance(value, Path):
                value = Path(value)
            object.__setattr__(self, name, value)
        for name in (
            "markdown_sha256",
            "json_sha256",
            "manifest_sha256",
            "document_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"{name} must be a SHA-256 hexadecimal digest.")
            try:
                int(value, 16)
            except ValueError as exc:
                raise ValueError(f"{name} must be hexadecimal.") from exc


def _validate_document(document: RootCauseDocument) -> None:
    report = document.report
    finding_signal_ids = {signal_id for item in report.findings for signal_id in item.signal_ids}
    report_signal_ids = {item.id for item in report.signals}
    if finding_signal_ids != report_signal_ids:
        missing = sorted(report_signal_ids - finding_signal_ids)
        unexpected = sorted(finding_signal_ids - report_signal_ids)
        raise ReportConsistencyError(
            "Every report signal must be represented by a finding; "
            f"missing={missing}, unexpected={unexpected}."
        )

    assessment_ids = {item.candidate_id for item in report.assessments}
    candidate_ids = {item.id for item in report.candidates}
    if assessment_ids != candidate_ids:
        raise ReportConsistencyError(
            "Every candidate must have exactly one assessment in a final report."
        )

    plan_ids = {item.id for item in report.reproduction_plans}
    referenced_plan_ids = {
        item.reproduction_plan_id
        for item in report.findings
        if item.reproduction_plan_id is not None
    }
    if referenced_plan_ids != plan_ids:
        raise ReportConsistencyError(
            "Every reproduction plan must be referenced by exactly the report findings that use it."
        )


def build_root_cause_document(
    source: RootCauseReport | RootCauseEngineResult,
    *,
    configuration: ReportConfiguration | None = None,
    generated_at: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RootCauseDocument:
    """Build a deterministic report-ready document without changing conclusions."""

    config = configuration or ReportConfiguration()
    if not isinstance(config, ReportConfiguration):
        raise TypeError("configuration must be a ReportConfiguration or None.")

    if isinstance(source, RootCauseEngineResult):
        report = source.report
        stages = source.stages
        engine_schema_version = source.schema_version
        source_metadata: Mapping[str, Any] = source.metadata
    elif isinstance(source, RootCauseReport):
        report = source
        stages = ()
        engine_schema_version = None
        source_metadata = {}
    else:
        raise TypeError("source must be a RootCauseReport or RootCauseEngineResult.")

    timestamp = generated_at or report.generated_at
    merged_metadata = {
        "engine": source_metadata,
        "presentation": dict(metadata or {}),
    }
    return RootCauseDocument(
        report=report,
        configuration=config,
        generated_at=timestamp,
        engine_schema_version=engine_schema_version,
        stages=stages,
        metadata=merged_metadata,
    )


def _assessment_by_candidate(document: RootCauseDocument) -> dict[str, CandidateAssessment]:
    return {item.candidate_id: item for item in document.report.assessments}


def _candidate_by_id(document: RootCauseDocument) -> dict[str, CausalCandidate]:
    return {item.id: item for item in document.report.candidates}


def _evidence_by_id(document: RootCauseDocument) -> dict[str, EvidenceReference]:
    return {item.id: item for item in document.report.evidence}


def _verification_by_id(document: RootCauseDocument) -> dict[str, VerificationResult]:
    return {item.id: item for item in document.report.verifications}


def _plan_by_id(document: RootCauseDocument) -> dict[str, ReproductionPlan]:
    return {item.id: item for item in document.report.reproduction_plans}


def _render_identifier_list(identifiers: Sequence[str]) -> str:
    return ", ".join(f"`{item}`" for item in identifiers) if identifiers else "_None._"


def _artifact_display_value(artifact: Any, field_name: str) -> Any:
    value = getattr(artifact, field_name, None)
    return value.value if isinstance(value, Enum) else value


def _render_attribution(finding: RootCauseFinding) -> str:
    attribution = finding.attribution
    if attribution.level is AttributionLevel.UNKNOWN:
        return "Unknown — available evidence does not support a concrete source location."
    parts = [f"level={attribution.level.value}"]
    for name in (
        "component",
        "module",
        "state",
        "transition",
        "logic",
        "exporter",
        "metric",
        "configuration_key",
        "environment_key",
    ):
        value = getattr(attribution, name)
        if value is not None:
            parts.append(f"{name}={value}")
    parts.append(f"confidence={attribution.confidence.value}")
    return "; ".join(parts)


def render_markdown_report(document: RootCauseDocument) -> str:
    """Render one stable, human-readable scientific Markdown report."""

    if not isinstance(document, RootCauseDocument):
        raise TypeError("document must be a RootCauseDocument.")

    report = document.report
    candidates = _candidate_by_id(document)
    assessments = _assessment_by_candidate(document)
    evidence = _evidence_by_id(document)
    verifications = _verification_by_id(document)
    plans = _plan_by_id(document)

    lines: list[str] = [
        f"# {document.configuration.title}",
        "",
        f"- **Report ID:** `{report.id}`",
        f"- **Request ID:** `{report.request_id}`",
        f"- **Experiment ID:** `{report.experiment_id}`",
        f"- **Run ID:** `{report.run_id}`",
        f"- **Generated at:** `{document.generated_at.isoformat()}`",
        f"- **Document fingerprint:** `{document.document_fingerprint}`",
        "",
        "## Executive Summary",
        "",
        f"**Overall status:** `{report.status.value.upper()}`  ",
        f"**Causal confidence:** `{report.confidence.value.upper()}`",
        "",
        report.executive_summary,
        "",
        _table(
            ("Signals", "Evidence", "Candidates", "Verifications", "Findings", "Reproduction plans"),
            ((
                len(report.signals),
                len(report.evidence),
                len(report.candidates),
                len(report.verifications),
                len(report.findings),
                len(report.reproduction_plans),
            ),),
        ),
        "",
        "## Causal Findings",
        "",
    ]

    ordered_findings = sorted(
        report.findings,
        key=lambda item: (_STATUS_ORDER[item.status], item.domain.value, item.id),
    )
    for index, finding in enumerate(ordered_findings, start=1):
        lines.extend(
            [
                f"### {index}. {finding.summary}",
                "",
                _table(
                    ("Field", "Value"),
                    (
                        ("Finding ID", finding.id),
                        ("Status", finding.status.value),
                        ("Confidence", finding.confidence.value),
                        ("Domain", finding.domain.value),
                        ("Difference classification", finding.classification.value),
                        ("Signals", ", ".join(finding.signal_ids)),
                        ("Attribution", _render_attribution(finding)),
                    ),
                ),
                "",
                "**Explanation**",
                "",
                finding.explanation,
                "",
            ]
        )

        candidate_groups = (
            ("Selected causal candidates", finding.selected_candidate_ids),
            ("Alternative candidates", finding.alternative_candidate_ids),
            ("Rejected candidates", finding.rejected_candidate_ids),
        )
        for title, identifiers in candidate_groups:
            lines.extend([f"**{title}**", ""])
            if not identifiers:
                lines.extend(["_None._", ""])
                continue
            if not document.configuration.include_candidate_details:
                lines.extend([_render_identifier_list(identifiers), ""])
                continue
            limited = identifiers[: document.configuration.maximum_candidates_per_finding]
            rows = []
            for candidate_id in limited:
                candidate = candidates[candidate_id]
                assessment = assessments[candidate_id]
                rows.append(
                    (
                        candidate.id,
                        candidate.statement,
                        candidate.category.value,
                        candidate.status.value,
                        assessment.rank,
                        f"{assessment.total_score:.6g}",
                    )
                )
            lines.extend(
                [
                    _table(
                        ("Candidate ID", "Statement", "Category", "Status", "Rank", "Score"),
                        rows,
                    ),
                    "",
                ]
            )
            if len(identifiers) > len(limited):
                lines.extend(
                    [
                        f"_{len(identifiers) - len(limited)} additional candidates omitted by presentation policy._",
                        "",
                    ]
                )

        for title, identifiers in (
            ("Supporting evidence", finding.supporting_evidence_ids),
            ("Contradictory evidence", finding.contradictory_evidence_ids),
        ):
            lines.extend([f"**{title}**", ""])
            if not identifiers:
                lines.extend(["_None._", ""])
                continue
            if not document.configuration.include_evidence_details:
                lines.extend([_render_identifier_list(identifiers), ""])
                continue
            limited = identifiers[: document.configuration.maximum_evidence_items_per_finding]
            rows = [
                (
                    item.id,
                    item.direction.value,
                    item.source_type,
                    item.summary,
                    item.artifact_id,
                )
                for item in (evidence[evidence_id] for evidence_id in limited)
            ]
            lines.extend(
                [
                    _table(
                        ("Evidence ID", "Direction", "Source", "Summary", "Artifact"),
                        rows,
                    ),
                    "",
                ]
            )
            if len(identifiers) > len(limited):
                lines.extend(
                    [
                        f"_{len(identifiers) - len(limited)} additional evidence items omitted by presentation policy._",
                        "",
                    ]
                )

        lines.extend(["**Deterministic verification results**", ""])
        if not finding.verification_result_ids:
            lines.extend(["_No verification result is attached to this finding._", ""])
        elif not document.configuration.include_verification_details:
            lines.extend([_render_identifier_list(finding.verification_result_ids), ""])
        else:
            rows = []
            for verification_id in finding.verification_result_ids:
                item = verifications[verification_id]
                rows.append(
                    (
                        item.id,
                        item.verifier_id,
                        _OUTCOME_LABELS[item.outcome],
                        item.expected_result,
                        item.observed_result or item.error_message,
                    )
                )
            lines.extend(
                [
                    _table(
                        ("Verification ID", "Verifier", "Outcome", "Expected", "Observed / error"),
                        rows,
                    ),
                    "",
                ]
            )

        if finding.reproduction_plan_id is not None:
            plan = plans[finding.reproduction_plan_id]
            lines.extend(["**Reproduction procedure**", ""])
            if not document.configuration.include_reproduction_details:
                lines.extend([f"Plan: `{plan.id}`", ""])
            else:
                lines.extend(
                    [
                        f"Plan: `{plan.id}` — {plan.title}",
                        "",
                        f"Objective: {plan.objective}",
                        "",
                        f"Working directory: `{plan.working_directory}`",
                        "",
                    ]
                )
                for command in plan.commands:
                    lines.extend(["```text", _display_command(command), "```", ""])
                lines.extend([f"Expected result: {plan.expected_result}", ""])

        if finding.limitations:
            lines.extend(["**Finding limitations**", ""])
            lines.extend(_bullet(item) for item in finding.limitations)
            lines.append("")

    lines.extend(["## Investigation Coverage", ""])
    status_counts = Counter(item.status.value for item in report.findings)
    lines.extend(
        [
            _table(
                ("Finding status", "Count"),
                tuple(sorted(status_counts.items())),
            ),
            "",
            "## Unresolved Questions",
            "",
        ]
    )
    if report.unresolved_questions:
        lines.extend(_bullet(item) for item in report.unresolved_questions)
    else:
        lines.append("_No unresolved questions were recorded._")

    lines.extend(["", "## Limitations", ""])
    if report.limitations:
        lines.extend(_bullet(item) for item in report.limitations)
    else:
        lines.append("_No report-level limitations were recorded._")

    if document.configuration.include_artifacts:
        lines.extend(["", "## Artifact Integrity", ""])
        if not report.artifacts:
            lines.append("_No artifacts were registered._")
        else:
            rows = []
            for artifact in sorted(report.artifacts, key=lambda item: item.id):
                rows.append(
                    (
                        artifact.id,
                        _artifact_display_value(artifact, "kind"),
                        _artifact_display_value(artifact, "path"),
                        _artifact_display_value(artifact, "sha256"),
                    )
                )
            lines.append(_table(("Artifact ID", "Kind", "Path", "SHA-256"), rows))

    if document.configuration.include_engine_trace and document.stages:
        lines.extend(["", "## Engine Audit Trail", ""])
        rows = [
            (
                item.stage.value,
                item.started_at.isoformat(),
                item.finished_at.isoformat(),
                f"{item.duration_seconds:.6f}",
                item.input_count,
                item.output_count,
            )
            for item in document.stages
        ]
        lines.append(
            _table(
                ("Stage", "Started", "Finished", "Duration (s)", "Inputs", "Outputs"),
                rows,
            )
        )

    if document.configuration.include_metadata:
        lines.extend(["", "## Metadata", ""])
        metadata_payload = {
            "report": report.metadata,
            "document": document.metadata,
        }
        lines.extend(["```json", dumps(_serialize(metadata_payload), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False), "```"] )

    lines.extend(
        [
            "",
            "## Scientific Interpretation Boundary",
            "",
            "This document reports the conclusions produced by the Root Cause Engine. "
            "Rendering did not recalculate statistics, rerank candidates, execute commands, "
            "or alter causal status.",
            "",
        ]
    )
    return "\n".join(lines)


def render_json_report(document: RootCauseDocument, *, indent: int | None = 2) -> str:
    """Render canonical JSON with stable ordering and no non-finite values."""

    if not isinstance(document, RootCauseDocument):
        raise TypeError("document must be a RootCauseDocument.")
    if indent is not None:
        indent = _non_negative_int(indent, "indent")
    return dumps(
        document.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        allow_nan=False,
    ) + "\n"


def _atomic_write(path: Path, content: str) -> Path:
    if not isinstance(path, Path):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(encoded)
            handle.flush()
            fsync(handle.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def write_markdown_report(document: RootCauseDocument, path: Path | str) -> Path:
    """Atomically write a UTF-8 Markdown report."""

    return _atomic_write(Path(path), render_markdown_report(document))


def write_json_report(
    document: RootCauseDocument,
    path: Path | str,
    *,
    indent: int | None = 2,
) -> Path:
    """Atomically write a UTF-8 JSON report."""

    return _atomic_write(Path(path), render_json_report(document, indent=indent))


def write_report_bundle(
    document: RootCauseDocument,
    directory: Path | str,
    *,
    file_stem: str = "root_cause_report",
) -> ReportBundle:
    """Write Markdown, JSON, and a content-hash manifest atomically per file."""

    if not isinstance(document, RootCauseDocument):
        raise TypeError("document must be a RootCauseDocument.")
    output_directory = Path(directory)
    stem = _safe_stem(file_stem)
    markdown = render_markdown_report(document)
    json_text = render_json_report(document)
    markdown_bytes = markdown.encode("utf-8")
    json_bytes = json_text.encode("utf-8")
    markdown_sha = sha256(markdown_bytes).hexdigest()
    json_sha = sha256(json_bytes).hexdigest()

    markdown_path = output_directory / f"{stem}.md"
    json_path = output_directory / f"{stem}.json"
    manifest_path = output_directory / f"{stem}.manifest.json"
    manifest_payload = {
        "schema": "psynthea.root_cause.report_bundle",
        "schema_version": "1.0.0",
        "document_fingerprint": document.document_fingerprint,
        "files": {
            markdown_path.name: {
                "media_type": "text/markdown; charset=utf-8",
                "sha256": markdown_sha,
                "size_bytes": len(markdown_bytes),
            },
            json_path.name: {
                "media_type": "application/json; charset=utf-8",
                "sha256": json_sha,
                "size_bytes": len(json_bytes),
            },
        },
    }
    manifest_text = dumps(
        manifest_payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    manifest_sha = sha256(manifest_text.encode("utf-8")).hexdigest()

    _atomic_write(markdown_path, markdown)
    _atomic_write(json_path, json_text)
    _atomic_write(manifest_path, manifest_text)

    return ReportBundle(
        markdown_path=markdown_path,
        json_path=json_path,
        manifest_path=manifest_path,
        markdown_sha256=markdown_sha,
        json_sha256=json_sha,
        manifest_sha256=manifest_sha,
        document_fingerprint=document.document_fingerprint,
    )