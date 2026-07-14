"""Deterministic rendering of scientific interpretation results.

This module is a presentation boundary.  It converts one fully evaluated
:class:`~validation.interpretation.engine.EngineExecution` and its conservative
:class:`~validation.interpretation.summary.InterpretationSummary` into a
human-readable Markdown report and a machine-readable JSON document.

Scientific safety rules
-----------------------

* Rendering never recalculates statistics or changes scientific status.
* The summary and execution must refer to the same report and pipeline run.
* Incomplete rules and blocking findings are always visible.
* Recommendations remain linked to their originating findings.
* Evidence references remain stable and auditable.
* Output order and JSON serialization are deterministic.
* File writes are atomic and use UTF-8.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from hashlib import sha256
from json import dumps
from os import fsync, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final

from validation.interpretation.engine import EngineExecution
from validation.interpretation.models import (
    EvidenceReference,
    FindingStatus,
    InterpretationFinding,
    Recommendation,
    RecommendationPriority,
)
from validation.interpretation.rules.base import RuleEvaluation, RuleExecutionStatus
from validation.interpretation.summary import (
    InterpretationSummary,
    SummaryConfiguration,
    build_interpretation_summary,
)

__all__ = [
    "InterpretationDocument",
    "ReportConfiguration",
    "ReportConsistencyError",
    "build_interpretation_document",
    "render_json_report",
    "render_markdown_report",
    "write_json_report",
    "write_markdown_report",
    "write_report_bundle",
]


class ReportConsistencyError(ValueError):
    """Raised when execution and summary cannot describe the same report."""


_STATUS_LABELS: Final = {
    FindingStatus.PASS: "PASS",
    FindingStatus.WARNING: "WARNING",
    FindingStatus.FAIL: "FAIL",
    FindingStatus.INCONCLUSIVE: "INCONCLUSIVE",
    FindingStatus.NOT_APPLICABLE: "NOT APPLICABLE",
    FindingStatus.NOT_EVALUATED: "NOT EVALUATED",
}

_PRIORITY_ORDER: Final = {
    RecommendationPriority.URGENT: 0,
    RecommendationPriority.HIGH: 1,
    RecommendationPriority.MEDIUM: 2,
    RecommendationPriority.LOW: 3,
}

_SAFE_STEM_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESERVED_METADATA_KEYS: Final = frozenset({"source_report_id", "pipeline_run_id", "document_fingerprint"})

_INCOMPLETE_RULE_STATUSES: Final = frozenset(
    {
        RuleExecutionStatus.INSUFFICIENT_EVIDENCE,
        RuleExecutionStatus.BLOCKED_DEPENDENCY,
        RuleExecutionStatus.NOT_EVALUATED,
    }
)


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
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
    """Return deterministic JSON-compatible data for report payloads."""

    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError("Report metadata datetimes must be timezone-aware.")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        serialized = [_serialize(item) for item in value]
        return sorted(serialized, key=lambda item: dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _serialize(value.to_dict())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported report metadata type: {type(value).__name__}.")


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


def _clean_paragraph(value: str) -> str:
    return " ".join(value.strip().split())


def _bullet(value: str, *, indent: int = 0) -> str:
    return f"{'  ' * indent}- {_clean_paragraph(value)}"


def _recommendation_key(item: tuple[InterpretationFinding, Recommendation]) -> tuple[int, str, str]:
    finding, recommendation = item
    return (
        _PRIORITY_ORDER[recommendation.priority],
        finding.finding_id,
        recommendation.recommendation_id,
    )


@dataclass(frozen=True, slots=True)
class ReportConfiguration:
    """Presentation policy for Markdown and JSON report rendering."""

    title: str = "Psynthea Scientific Validation Report"
    include_all_findings: bool = True
    include_pass_findings: bool = True
    include_evidence_details: bool = True
    include_rule_audit: bool = True
    include_metadata: bool = True
    maximum_priority_findings: int = 10
    maximum_evidence_items_per_finding: int = 20

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _clean_paragraph(_non_empty_text(self.title, "title")))
        for field_name in (
            "include_all_findings",
            "include_pass_findings",
            "include_evidence_details",
            "include_rule_audit",
            "include_metadata",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool.")
        for field_name in (
            "maximum_priority_findings",
            "maximum_evidence_items_per_finding",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")


@dataclass(frozen=True, slots=True)
class InterpretationDocument:
    """Immutable report-ready representation of one engine execution."""

    execution: EngineExecution
    summary: InterpretationSummary
    configuration: ReportConfiguration
    generated_at: datetime
    findings: tuple[InterpretationFinding, ...]
    recommendations: tuple[tuple[str, Recommendation], ...]
    incomplete_evaluations: tuple[RuleEvaluation, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.execution, EngineExecution):
            raise TypeError("execution must be an EngineExecution.")
        if not isinstance(self.summary, InterpretationSummary):
            raise TypeError("summary must be an InterpretationSummary.")
        if not isinstance(self.configuration, ReportConfiguration):
            raise TypeError("configuration must be a ReportConfiguration.")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime.")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware.")
        normalized_generated_at = self.generated_at.astimezone(UTC)
        if normalized_generated_at < self.execution.completed_at:
            raise ValueError("generated_at cannot precede execution.completed_at.")
        object.__setattr__(self, "generated_at", normalized_generated_at)

        findings = tuple(self.findings)
        if not all(isinstance(item, InterpretationFinding) for item in findings):
            raise TypeError("findings must contain InterpretationFinding values only.")
        finding_ids = [item.finding_id for item in findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("findings must not contain duplicate identifiers.")
        object.__setattr__(self, "findings", findings)

        recommendations = tuple(self.recommendations)
        for item in recommendations:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], Recommendation)
            ):
                raise TypeError(
                    "recommendations must contain (finding_id, Recommendation) tuples."
                )
        recommendation_keys = [(item[0], item[1].recommendation_id) for item in recommendations]
        if len(recommendation_keys) != len(set(recommendation_keys)):
            raise ValueError("recommendations must not contain duplicate finding/recommendation pairs.")
        object.__setattr__(self, "recommendations", recommendations)

        incomplete = tuple(self.incomplete_evaluations)
        if not all(isinstance(item, RuleEvaluation) for item in incomplete):
            raise TypeError("incomplete_evaluations must contain RuleEvaluation values only.")
        object.__setattr__(self, "incomplete_evaluations", incomplete)
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))

        _validate_document_consistency(self)

    @property
    def research_use_statement(self) -> str:
        if self.summary.research_use_ready:
            return "Ready for research use under the evaluated scope and documented limitations."
        return (
            "Not ready for unrestricted research use; blocking or incomplete validation "
            "conditions remain."
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical machine-readable report payload."""

        payload = {
            "schema": "psynthea.interpretation.report",
            "schema_version": "1.1.0",
            "generated_at": self.generated_at.isoformat(),
            "title": self.configuration.title,
            "research_use_statement": self.research_use_statement,
            "summary": self.summary.to_dict(),
            "findings": [item.to_dict() for item in self.findings],
            "recommendations": [
                {"finding_id": finding_id, **recommendation.to_dict()}
                for finding_id, recommendation in self.recommendations
            ],
            "incomplete_rules": [item.to_dict() for item in self.incomplete_evaluations],
            "audit": {
                "report": self.execution.report.to_dict(),
                "execution_order": list(self.execution.execution_order),
                "execution_status_counts": dict(self.execution.execution_status_counts),
                "started_at": self.execution.started_at.isoformat(),
                "completed_at": self.execution.completed_at.isoformat(),
                "duration_seconds": self.execution.duration_seconds,
            },
            "metadata": _serialize(self.metadata),
        }
        payload["document_fingerprint"] = _fingerprint(payload)
        return payload



def _validate_document_consistency(document: InterpretationDocument) -> None:
    execution = document.execution
    summary = document.summary
    report = execution.report

    if summary.report_id != report.report_id:
        raise ReportConsistencyError("summary.report_id does not match execution.report.report_id.")
    if summary.pipeline_run_id != report.pipeline_run_id:
        raise ReportConsistencyError(
            "summary.pipeline_run_id does not match execution.report.pipeline_run_id."
        )
    if summary.module_name != report.module_name:
        raise ReportConsistencyError("summary.module_name does not match report.module_name.")
    if summary.rule_count != len(execution.evaluations):
        raise ReportConsistencyError("summary.rule_count does not match engine evaluations.")
    if summary.finding_count != len(report.findings):
        raise ReportConsistencyError("summary.finding_count does not match report findings.")
    if summary.evidence_count != len(report.evidence):
        raise ReportConsistencyError("summary.evidence_count does not match report evidence.")

    report_ids = {item.finding_id for item in report.findings}
    document_ids = {item.finding_id for item in document.findings}
    if not document_ids.issubset(report_ids):
        raise ReportConsistencyError("document findings contain identifiers absent from the report.")

    expected_incomplete = tuple(
        item for item in execution.evaluations if item.status in _INCOMPLETE_RULE_STATUSES
    )
    if document.incomplete_evaluations != expected_incomplete:
        raise ReportConsistencyError(
            "incomplete_evaluations must exactly match incomplete engine evaluations."
        )

    known_finding_ids = {item.finding_id for item in document.findings}
    for finding_id, _ in document.recommendations:
        if finding_id not in report_ids:
            raise ReportConsistencyError(
                f"Recommendation references unknown finding {finding_id!r}."
            )
        if finding_id not in known_finding_ids:
            raise ReportConsistencyError(
                "Every rendered recommendation must reference an included finding."
            )


def build_interpretation_document(
    execution: EngineExecution,
    *,
    summary: InterpretationSummary | None = None,
    configuration: ReportConfiguration | None = None,
    summary_configuration: SummaryConfiguration | None = None,
    generated_at: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> InterpretationDocument:
    """Build one immutable report document without changing scientific decisions."""

    if not isinstance(execution, EngineExecution):
        raise TypeError("execution must be an EngineExecution.")
    config = configuration or ReportConfiguration()
    if not isinstance(config, ReportConfiguration):
        raise TypeError("configuration must be a ReportConfiguration.")

    if summary is None:
        summary_policy = summary_configuration or SummaryConfiguration(
            maximum_priority_findings=config.maximum_priority_findings
        )
        summary = build_interpretation_summary(
            execution,
            configuration=summary_policy,
        )
    elif not isinstance(summary, InterpretationSummary):
        raise TypeError("summary must be an InterpretationSummary or None.")

    findings = tuple(
        item
        for item in execution.report.findings
        if config.include_pass_findings or item.status is not FindingStatus.PASS
    )
    if not config.include_all_findings:
        priority_ids = {item.finding_id for item in summary.priority_findings}
        findings = tuple(item for item in findings if item.finding_id in priority_ids)

    included_finding_ids = {item.finding_id for item in findings}
    recommendation_pairs = sorted(
        (
            (finding, recommendation)
            for finding in execution.report.findings
            if finding.finding_id in included_finding_ids
            for recommendation in finding.recommendations
        ),
        key=_recommendation_key,
    )
    recommendations = tuple(
        (finding.finding_id, recommendation)
        for finding, recommendation in recommendation_pairs
    )

    incomplete = tuple(
        item
        for item in execution.evaluations
        if item.status in _INCOMPLETE_RULE_STATUSES
    )
    report_metadata = dict(metadata or {})
    reserved = _RESERVED_METADATA_KEYS.intersection(report_metadata)
    if reserved:
        raise ValueError(
            "metadata contains reserved report keys: " + ", ".join(sorted(reserved))
        )
    report_metadata["source_report_id"] = execution.report.report_id
    report_metadata["pipeline_run_id"] = execution.report.pipeline_run_id
    _canonical_json_bytes(report_metadata)

    return InterpretationDocument(
        execution=execution,
        summary=summary,
        configuration=config,
        generated_at=generated_at or execution.completed_at,
        findings=findings,
        recommendations=recommendations,
        incomplete_evaluations=incomplete,
        metadata=report_metadata,
    )


def _render_executive_summary(document: InterpretationDocument) -> list[str]:
    summary = document.summary
    return [
        "## Executive Summary",
        "",
        _table(
            ("Field", "Value"),
            (
                ("Module", summary.module_name or "Not specified"),
                ("Pipeline run", summary.pipeline_run_id),
                ("Overall status", _STATUS_LABELS[summary.overall_status]),
                ("Maximum severity", summary.maximum_severity.value.upper()),
                ("Research-use gate", "READY" if summary.research_use_ready else "NOT READY"),
                ("Rules evaluated", summary.rule_count),
                ("Findings", summary.finding_count),
                ("Evidence values", summary.evidence_count),
                ("Blocking findings", summary.blocking_finding_count),
                ("Incomplete rules", summary.incomplete_rule_count),
            ),
        ),
        "",
        f"**Research-use conclusion:** {document.research_use_statement}",
    ]


def _render_dimensions(document: InterpretationDocument) -> list[str]:
    rows = [
        (
            item.dimension.value,
            _STATUS_LABELS[item.status],
            item.maximum_severity.value,
            item.rule_count,
            item.finding_count,
            item.incomplete_rule_count,
            item.blocking_finding_count,
            "yes" if item.research_use_ready else "no",
        )
        for item in document.summary.dimensions
    ]
    return [
        "## Validation by Dimension",
        "",
        _table(
            (
                "Dimension",
                "Status",
                "Max severity",
                "Rules",
                "Findings",
                "Incomplete",
                "Blocking",
                "Research-ready",
            ),
            rows,
        ),
    ]


def _render_priority_findings(document: InterpretationDocument) -> list[str]:
    included = {item.finding_id for item in document.findings}
    findings = tuple(
        item for item in document.summary.priority_findings if item.finding_id in included
    )
    sections = ["## Priority Findings", ""]
    if not findings:
        sections.append("_No priority findings were selected by the summary policy._")
        return sections
    for finding in findings:
        sections.extend(_render_finding(finding, document, level=3))
    return sections


def _evidence_lookup(document: InterpretationDocument) -> Mapping[str, Any]:
    return {item.metric_id: item for item in document.execution.report.evidence}


def _render_evidence_references(
    references: Sequence[EvidenceReference],
    document: InterpretationDocument,
) -> list[str]:
    if not references:
        return ["_No evidence references._"]
    lookup = _evidence_lookup(document)
    rows: list[tuple[Any, ...]] = []
    limit = document.configuration.maximum_evidence_items_per_finding
    for reference in references[:limit]:
        value = lookup.get(reference.metric_id)
        rows.append(
            (
                reference.metric_id,
                reference.role.value,
                getattr(value, "availability", None).value if value is not None else "missing",
                getattr(value, "value", None),
                reference.rationale,
            )
        )
    if len(references) > limit:
        rows.append((f"… {len(references) - limit} more", "", "", "", ""))
    return [
        _table(
            ("Metric", "Role", "Availability", "Value", "Rationale"),
            rows,
        )
    ]


def _render_finding(
    finding: InterpretationFinding,
    document: InterpretationDocument,
    *,
    level: int,
) -> list[str]:
    prefix = "#" * level
    sections = [
        f"{prefix} {finding.title}",
        "",
        _table(
            ("Field", "Value"),
            (
                ("Finding ID", finding.finding_id),
                ("Rule", finding.rule_id),
                ("Status", _STATUS_LABELS[finding.status]),
                ("Severity", finding.severity.value),
                ("Confidence", finding.confidence.value),
                ("Evidence strength", finding.evidence_strength.value),
                ("Blocks research use", "yes" if finding.blocks_research_use else "no"),
            ),
        ),
        "",
        f"**Observation.** {_clean_paragraph(finding.observation)}",
        "",
        f"**Interpretation.** {_clean_paragraph(finding.interpretation)}",
        "",
        f"**Impact.** {_clean_paragraph(finding.impact)}",
    ]
    if finding.limitations:
        sections.extend(["", "**Limitations**", *(_bullet(item) for item in finding.limitations)])
    if finding.hypotheses:
        sections.extend(["", "**Root-cause hypotheses (not demonstrated causes)**"])
        for hypothesis in finding.hypotheses:
            sections.append(
                _bullet(
                    f"{hypothesis.statement} [plausibility={hypothesis.plausibility.value}]"
                )
            )
            sections.append(_bullet(hypothesis.rationale, indent=1))
    if document.configuration.include_evidence_details:
        sections.extend(["", "**Evidence**"])
        sections.extend(_render_evidence_references(finding.evidence, document))
    return sections


def _render_all_findings(document: InterpretationDocument) -> list[str]:
    sections = ["## Detailed Findings", ""]
    if not document.findings:
        sections.append("_No findings are included under the selected report policy._")
        return sections
    grouped: dict[str, list[InterpretationFinding]] = defaultdict(list)
    for finding in document.findings:
        grouped[finding.domain].append(finding)
    for domain in sorted(grouped):
        sections.extend([f"### {domain.replace('_', ' ').title()}", ""])
        for finding in grouped[domain]:
            sections.extend(_render_finding(finding, document, level=4))
            sections.append("")
    return sections


def _render_recommendations(document: InterpretationDocument) -> list[str]:
    sections = ["## Recommendations", ""]
    if not document.recommendations:
        sections.append("_No recommendations were produced._")
        return sections
    rows = [
        (
            recommendation.priority.value,
            recommendation.recommendation_id,
            finding_id,
            recommendation.action,
            "yes" if recommendation.blocking else "no",
            recommendation.verification,
        )
        for finding_id, recommendation in document.recommendations
    ]
    sections.append(
        _table(
            ("Priority", "Recommendation", "Finding", "Action", "Blocking", "Verification"),
            rows,
        )
    )
    return sections


def _render_incomplete_rules(document: InterpretationDocument) -> list[str]:
    sections = ["## Incomplete or Blocked Rules", ""]
    if not document.incomplete_evaluations:
        sections.append("_All rules completed or were explicitly non-applicable._")
        return sections
    rows = [
        (
            item.rule_id,
            item.dimension.value,
            item.status.value,
            item.applicability.status.value,
            item.applicability.reason,
        )
        for item in document.incomplete_evaluations
    ]
    sections.append(
        _table(("Rule", "Dimension", "Execution status", "Applicability", "Reason"), rows)
    )
    return sections


def _render_limitations(document: InterpretationDocument) -> list[str]:
    sections = ["## Limitations", ""]
    if not document.summary.limitations:
        sections.append("_No global limitations were recorded._")
        return sections
    sections.extend(_bullet(item) for item in document.summary.limitations)
    return sections


def _render_audit(document: InterpretationDocument) -> list[str]:
    execution = document.execution
    sections = [
        "## Audit Trail",
        "",
        _table(
            ("Field", "Value"),
            (
                ("Report ID", execution.report.report_id),
                ("Pipeline run", execution.report.pipeline_run_id),
                ("Report schema", execution.report.schema_version),
                ("Generated at", execution.report.generated_at.isoformat()),
                ("Execution started", execution.started_at.isoformat()),
                ("Execution completed", execution.completed_at.isoformat()),
                ("Execution duration (s)", f"{execution.duration_seconds:.6f}"),
                ("Rule order", " → ".join(execution.execution_order)),
                ("Document fingerprint", document.to_dict()["document_fingerprint"]),
            ),
        ),
    ]
    if document.configuration.include_rule_audit:
        rows = [
            (
                item.rule_id,
                item.dimension.value,
                item.status.value,
                f"{item.duration_seconds:.6f}",
                len(item.findings),
                len(item.derived_evidence),
            )
            for item in execution.evaluations
        ]
        sections.extend(
            [
                "",
                "### Rule Evaluations",
                "",
                _table(
                    ("Rule", "Dimension", "Status", "Duration (s)", "Findings", "Derived evidence"),
                    rows,
                ),
            ]
        )
    if document.configuration.include_metadata and document.metadata:
        sections.extend(["", "### Report Metadata", "", "```json"])
        sections.append(dumps(_serialize(document.metadata), sort_keys=True, indent=2))
        sections.append("```")
    return sections


def render_markdown_report(document: InterpretationDocument) -> str:
    """Render a deterministic, human-readable Markdown report."""

    if not isinstance(document, InterpretationDocument):
        raise TypeError("document must be an InterpretationDocument.")
    sections: list[str] = [
        f"# {document.configuration.title}",
        "",
        f"Generated at: `{document.generated_at.isoformat()}`",
        "",
    ]
    for renderer in (
        _render_executive_summary,
        _render_dimensions,
        _render_priority_findings,
        _render_all_findings,
        _render_recommendations,
        _render_incomplete_rules,
        _render_limitations,
        _render_audit,
    ):
        sections.extend(renderer(document))
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def render_json_report(document: InterpretationDocument, *, indent: int | None = 2) -> str:
    """Render the canonical JSON representation with stable key ordering."""

    if not isinstance(document, InterpretationDocument):
        raise TypeError("document must be an InterpretationDocument.")
    if indent is not None and (isinstance(indent, bool) or not isinstance(indent, int)):
        raise TypeError("indent must be an integer or None.")
    if isinstance(indent, int) and indent < 0:
        raise ValueError("indent must be non-negative.")
    return dumps(
        document.to_dict(),
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        separators=None if indent is not None else (",", ":"),
        allow_nan=False,
    ) + "\n"


def _write_temporary(path: Path, content: str) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            fsync(handle.fileno())
        return temporary
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _atomic_write(path: Path, content: str) -> Path:
    path = path.expanduser()
    temporary = _write_temporary(path, content)
    try:
        replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def write_markdown_report(document: InterpretationDocument, output_path: str | Path) -> Path:
    """Atomically write the Markdown report using UTF-8."""

    return _atomic_write(Path(output_path), render_markdown_report(document))


def write_json_report(
    document: InterpretationDocument,
    output_path: str | Path,
    *,
    indent: int | None = 2,
) -> Path:
    """Atomically write the canonical JSON report using UTF-8."""

    return _atomic_write(Path(output_path), render_json_report(document, indent=indent))


def write_report_bundle(
    document: InterpretationDocument,
    output_directory: str | Path,
    *,
    stem: str | None = None,
) -> tuple[Path, Path]:
    """Write synchronized Markdown and JSON artifacts with rollback on failure."""

    if not isinstance(document, InterpretationDocument):
        raise TypeError("document must be an InterpretationDocument.")
    directory = Path(output_directory).expanduser()
    safe_stem = _clean_paragraph(_non_empty_text(stem or document.summary.report_id, "stem"))
    if not _SAFE_STEM_PATTERN.fullmatch(safe_stem):
        raise ValueError(
            "stem must be a safe filename component of at most 128 characters."
        )

    markdown_path = directory / f"{safe_stem}.md"
    json_path = directory / f"{safe_stem}.json"
    markdown_temp = _write_temporary(markdown_path, render_markdown_report(document))
    json_temp: Path | None = None
    markdown_backup: Path | None = None
    json_backup: Path | None = None
    markdown_replaced = False
    json_replaced = False
    try:
        json_temp = _write_temporary(json_path, render_json_report(document))
        if markdown_path.exists():
            markdown_backup = _write_temporary(
                markdown_path, markdown_path.read_text(encoding="utf-8")
            )
        if json_path.exists():
            json_backup = _write_temporary(json_path, json_path.read_text(encoding="utf-8"))

        replace(markdown_temp, markdown_path)
        markdown_replaced = True
        replace(json_temp, json_path)
        json_replaced = True
    except Exception:
        markdown_temp.unlink(missing_ok=True)
        if json_temp is not None:
            json_temp.unlink(missing_ok=True)
        if markdown_replaced:
            if markdown_backup is not None:
                replace(markdown_backup, markdown_path)
                markdown_backup = None
            else:
                markdown_path.unlink(missing_ok=True)
        if json_replaced:
            if json_backup is not None:
                replace(json_backup, json_path)
                json_backup = None
            else:
                json_path.unlink(missing_ok=True)
        raise
    finally:
        if markdown_backup is not None:
            markdown_backup.unlink(missing_ok=True)
        if json_backup is not None:
            json_backup.unlink(missing_ok=True)
    return markdown_path, json_path