"""Final scientific-report generation stage.

The stage composes the already persisted validation, interpretation and
root-cause products into one experiment-level report. It deliberately performs
no statistical recalculation, evidence acquisition or causal inference.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
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

_REPORT_SCHEMA_VERSION: Final = "1.3.3"
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
            item
            for item in context.config.report_formats
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
                "Generated consolidated scientific report in "
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
            artifact for artifact in artifacts if artifact.kind is kind
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
        "report_type": "consolidated_scientific_validation_report",
        "experiment_id": context.config.id,
        "experiment_name": context.config.name,
        "run_id": context.run_id,
        "generated_at": generated_at.isoformat(),
        "decision": decision,
        "description": context.config.description,
        "tags": list(context.config.tags),
        "cohort": {
            "population_size": context.config.cohort.population,
            "seed": context.config.cohort.seed,
            "modules": list(context.config.cohort.modules),
            "reference_date": (
                context.config.cohort.reference_date.isoformat()
                if context.config.cohort.reference_date is not None
                else None
            ),
        },
        "executive_summary": _build_executive_summary(
            decision=decision,
            validation=validation,
            knowledge=knowledge,
            root_cause=root_cause,
        ),
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
            "validation": _build_validation_section(validation),
            "knowledge": _build_knowledge_section(knowledge),
            "root_cause": _build_root_cause_section(root_cause),
        },
        "source_artifacts": {
            kind.value: _artifact_payload(artifact)
            for kind, artifact in source_artifacts.items()
        },
        "artifact_count_before_report": len(context.artifacts),
    }


def _decision(context: OrchestrationContext) -> str:
    relevant = tuple(
        result
        for result in context.stage_results
        if result.stage
        in {
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

    blocking = int(
        (knowledge.metadata if knowledge else {}).get("blocking_finding_count", 0)
    )
    root_status = str(
        (root_cause.metadata if root_cause else {}).get("root_cause_status", "")
    )
    validation_status = str(
        (validation.metadata if validation else {}).get("overall_status", "")
    ).lower()

    if blocking > 0 or root_status.lower() in {"confirmed", "probable"}:
        return "REVIEW"
    if validation_status in {"failed", "fail", "rejected"}:
        return "REVIEW"
    return "PASS"


def _build_executive_summary(
    *,
    decision: str,
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    root_cause: Mapping[str, Any],
) -> dict[str, Any]:
    validation_aggregate = _mapping(validation.get("aggregate"))
    knowledge_aggregate = _mapping(knowledge.get("aggregate"))
    root_conclusion = _mapping(root_cause.get("conclusion"))
    root_counts = _mapping(root_cause.get("counts"))

    return {
        "decision": decision,
        "validation": {
            "module_count": _integer(validation_aggregate.get("module_count")),
            "comparable_module_count": _integer(
                validation_aggregate.get("comparable_module_count")
            ),
            "significant_test_count": _integer(
                validation_aggregate.get("significant_test_count")
            ),
            "significant_after_fdr_count": _integer(
                validation_aggregate.get("significant_after_fdr_count")
            ),
            "blocking_issue_count": _integer(
                validation_aggregate.get("blocking_issue_count")
            ),
            "warning_count": _integer(validation_aggregate.get("warning_count")),
        },
        "knowledge": {
            "finding_count": _integer(knowledge_aggregate.get("finding_count")),
            "blocking_finding_count": _integer(
                knowledge_aggregate.get("blocking_finding_count")
            ),
            "recommendation_count": _integer(
                knowledge_aggregate.get("recommendation_count")
            ),
            "incomplete_rule_count": _integer(
                knowledge_aggregate.get("incomplete_rule_count")
            ),
            "research_ready_count": _integer(
                knowledge_aggregate.get("research_ready_count")
            ),
        },
        "root_cause": {
            "status": root_conclusion.get("status"),
            "confidence": root_conclusion.get("confidence"),
            "executive_summary": root_conclusion.get("executive_summary"),
            "signal_count": _integer(root_counts.get("signals")),
            "candidate_count": _integer(root_counts.get("candidates")),
            "finding_count": _integer(root_counts.get("findings")),
            "verification_count": _integer(root_counts.get("verifications")),
            "reproduction_plan_count": _integer(
                root_counts.get("reproduction_plans")
            ),
        },
    }


def _build_validation_section(payload: Mapping[str, Any]) -> dict[str, Any]:
    modules = _mapping_sequence(payload.get("modules"))
    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "aggregate": _plain_value(_mapping(payload.get("aggregate"))),
        "configuration": _plain_value(_mapping(payload.get("configuration"))),
        "cohorts": _plain_value(_mapping(payload.get("cohorts"))),
        "modules": [
            {
                "module_name": module.get("module_name"),
                "functional_summary": _plain_value(
                    _mapping(module.get("functional_summary"))
                ),
                "statistical_summary": _plain_value(
                    _mapping(module.get("statistical_summary"))
                ),
                "tables": _plain_value(_mapping(module.get("tables"))),
            }
            for module in modules
        ],
        "source": _plain_value(payload),
    }


def _build_knowledge_section(payload: Mapping[str, Any]) -> dict[str, Any]:
    modules = _mapping_sequence(payload.get("modules"))
    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "aggregate": _plain_value(_mapping(payload.get("aggregate"))),
        "configuration": _plain_value(_mapping(payload.get("configuration"))),
        "modules": [
            {
                "module_name": module.get("module_name"),
                "overall_status": module.get("overall_status"),
                "research_use_ready": module.get("research_use_ready"),
                "finding_count": module.get("finding_count"),
                "blocking_finding_count": module.get("blocking_finding_count"),
                "recommendation_count": module.get("recommendation_count"),
                "incomplete_rule_count": module.get("incomplete_rule_count"),
                "summary": _plain_value(_mapping(module.get("summary"))),
                "interpretation_report": _plain_value(
                    _mapping(module.get("interpretation_report"))
                ),
                "recommendation_plan": _plain_value(
                    _mapping(module.get("recommendation_plan"))
                ),
                "stage_statuses": _plain_value(
                    _mapping(module.get("stage_statuses"))
                ),
                "artifacts": _plain_value(_mapping(module.get("artifacts"))),
            }
            for module in modules
        ],
        "source": _plain_value(payload),
    }


def _build_root_cause_section(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "title": payload.get("title"),
        "identity": _plain_value(_mapping(payload.get("identity"))),
        "conclusion": _plain_value(_mapping(payload.get("conclusion"))),
        "counts": _plain_value(_mapping(payload.get("counts"))),
        "findings": _plain_value(_sequence(payload.get("findings"))),
        "signals": _plain_value(_sequence(payload.get("signals"))),
        "candidates": _plain_value(_sequence(payload.get("candidates"))),
        "assessments": _plain_value(_sequence(payload.get("assessments"))),
        "limitations": _plain_value(_sequence(payload.get("limitations"))),
        "unresolved_questions": _plain_value(
            _sequence(payload.get("unresolved_questions"))
        ),
        "verifications": _plain_value(_sequence(payload.get("verifications"))),
        "reproduction_plans": _plain_value(
            _sequence(payload.get("reproduction_plans"))
        ),
        "engine": _plain_value(_mapping(payload.get("engine"))),
        "source": _plain_value(payload),
    }


def _artifact_payload(artifact: ArtifactReference) -> dict[str, Any]:
    return {
        "artifact_id": artifact.id,
        "path": artifact.path.as_posix(),
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "producer": artifact.producer,
    }


def _artifact_metadata(
    payload: Mapping[str, Any], report_format: str
) -> Mapping[str, Any]:
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
    summary = _mapping(payload.get("executive_summary"))
    scientific_results = _mapping(payload.get("scientific_results"))
    validation = _mapping(scientific_results.get("validation"))
    knowledge = _mapping(scientific_results.get("knowledge"))
    root_cause = _mapping(scientific_results.get("root_cause"))
    decision = str(payload.get("decision") or "INCOMPLETE").upper()
    discrepancies = _scientific_discrepancies(validation, knowledge)
    conclusion = _scientific_conclusion_v13(decision, discrepancies, knowledge)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(str(payload.get('experiment_name') or 'Scientific validation report'))}</title>
<style>
:root{{--ink:#152238;--muted:#64748b;--line:#dbe3ec;--paper:#fff;--canvas:#f3f6f9;--navy:#15385f;--blue:#2368a2;--green:#18724a;--amber:#9a5a00;--red:#a32634;--soft-red:#fff1f3;--soft-amber:#fff7e8;--soft-green:#edf8f2;--soft-blue:#edf5fc;--soft-gray:#f7f9fb}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--canvas);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}}main{{max-width:1180px;margin:auto;padding:28px 22px 72px}}header,.section{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:28px;margin-bottom:20px;box-shadow:0 2px 8px rgba(20,40,70,.035)}}h1{{font-size:2rem;margin:0 0 6px}}h2{{font-size:1.35rem;color:var(--navy);margin:0 0 18px}}h3{{font-size:1.05rem;margin:18px 0 9px}}p{{margin:8px 0}}a{{color:var(--blue)}}.eyebrow{{font-size:.78rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:var(--blue)}}.muted{{color:var(--muted)}}.decision-row{{display:grid;grid-template-columns:minmax(220px,.72fr) 2fr;gap:20px;align-items:stretch;margin-top:22px}}.decision-box{{border-radius:12px;padding:24px;background:{_decision_background(decision)};border:1px solid {_decision_border(decision)}}}.decision-label{{font-size:.77rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}}.decision-value{{font-size:2.2rem;font-weight:900;margin-top:4px;color:{_decision_color(decision)}}}.conclusion{{border-left:5px solid {_decision_color(decision)};padding:18px 20px;background:#fafbfd;border-radius:8px;font-size:1.03rem}}.meta,.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}}.meta{{margin-top:20px}}.card{{border:1px solid var(--line);border-radius:10px;padding:15px;background:#fbfcfe}}.label{{display:block;color:var(--muted);font-size:.73rem;font-weight:750;text-transform:uppercase;letter-spacing:.045em}}.value{{display:block;font-size:1.17rem;font-weight:800;margin-top:3px;overflow-wrap:anywhere}}nav{{margin-top:22px;padding-top:18px;border-top:1px solid var(--line)}}nav a{{display:inline-block;margin:4px 14px 4px 0;text-decoration:none;font-weight:650;font-size:.9rem}}table{{width:100%;border-collapse:collapse;font-size:.91rem}}th,td{{padding:11px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{background:#f5f8fb;color:var(--navy);font-size:.78rem;text-transform:uppercase;letter-spacing:.035em}}tr:last-child td{{border-bottom:0}}.badge{{display:inline-block;border-radius:999px;padding:3px 9px;font-size:.72rem;font-weight:850;text-transform:uppercase;letter-spacing:.035em}}.badge-pass,.badge-ready,.badge-succeeded,.badge-performed{{background:var(--soft-green);color:var(--green)}}.badge-review,.badge-warning,.badge-plausible,.badge-high{{background:var(--soft-amber);color:var(--amber)}}.badge-fail,.badge-failed,.badge-blocking,.badge-critical,.badge-urgent,.badge-not-demonstrated{{background:var(--soft-red);color:var(--red)}}.badge-inconclusive,.badge-incomplete,.badge-unknown,.badge-not-evaluated,.badge-not-informative,.badge-out-of-scope{{background:#eef1f5;color:#566273}}.discrepancy{{border:1px solid var(--line);border-left:5px solid var(--red);border-radius:10px;padding:18px;margin:14px 0;background:#fff}}.discrepancy h3{{margin:4px 0 8px}}.discrepancy-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-top:14px}}.mini{{background:var(--soft-gray);padding:11px 13px;border-radius:8px}}.strength{{font-weight:800}}.bar{{height:7px;background:#e7edf3;border-radius:99px;overflow:hidden;margin-top:7px}}.bar span{{display:block;height:100%;background:var(--navy)}}.delta-negative{{color:var(--red);font-weight:800}}.delta-positive{{color:var(--red);font-weight:800}}.delta-neutral{{color:var(--green);font-weight:800}}.recommendation{{display:grid;grid-template-columns:42px 1fr;gap:14px;border-bottom:1px solid var(--line);padding:15px 0}}.recommendation:last-child{{border:0}}.rank{{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:var(--navy);color:#fff;font-weight:850}}.callout{{background:var(--soft-blue);border-left:4px solid var(--blue);padding:14px 17px;border-radius:7px}}.scope-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.scope-box{{border:1px solid var(--line);border-radius:9px;padding:15px;background:#fbfcfe}}details{{border:1px solid var(--line);border-radius:9px;padding:12px 15px;margin:10px 0;background:#fff}}summary{{cursor:pointer;font-weight:750;color:var(--navy)}}pre{{white-space:pre-wrap;word-break:break-word;background:#111b2a;color:#e9eef6;padding:16px;border-radius:8px;max-height:560px;overflow:auto;font-size:.79rem}}ul{{padding-left:21px}}.empty{{color:var(--muted);font-style:italic}}.footer{{text-align:center;color:var(--muted);font-size:.82rem;margin-top:20px}}@media(max-width:760px){{.decision-row,.scope-grid{{grid-template-columns:1fr}}header,.section{{padding:20px}}}}@media print{{body{{background:#fff}}main{{max-width:none;padding:0}}header,.section{{box-shadow:none;break-inside:avoid}}nav{{display:none}}details{{break-inside:avoid}}}}
</style>
</head>
<body><main>
<header id="top">
<div class="eyebrow">Psynthea scientific validation</div>
<h1>{escape(str(payload.get('experiment_name') or payload.get('experiment_id') or 'Experiment'))}</h1>
<p class="muted">Research-facing scientific validation report · schema {_REPORT_SCHEMA_VERSION}</p>
<div class="decision-row">
<div class="decision-box"><span class="decision-label">Overall scientific decision</span><div class="decision-value">{escape(decision)}</div><div class="muted"><strong>{escape("Not research ready" if decision == "REVIEW" else "")}</strong></div></div>
<div class="conclusion"><strong>Scientific conclusion.</strong><br>{escape(conclusion)}</div>
</div>
<div class="meta">
{_metric_card('Experiment', payload.get('experiment_id'))}
{_metric_card('Run', payload.get('run_id'))}
{_metric_card('Population', _mapping(payload.get('cohort')).get('population_size'))}
{_metric_card('Seed', _mapping(payload.get('cohort')).get('seed'))}
{_metric_card('Modules', ', '.join(str(x) for x in _sequence(_mapping(payload.get('cohort')).get('modules'))))}
{_metric_card('Generated', payload.get('generated_at'))}
</div>
<nav><a href="#overview">Assessment</a><a href="#comparison">Cohorts</a><a href="#findings">Major discrepancies</a><a href="#statistics">Statistics</a><a href="#scope">Scope</a><a href="#root-cause">Root cause</a><a href="#recommendations">Recommendations</a><a href="#limitations">Limitations</a><a href="#appendix">Appendix</a></nav>
</header>
<section class="section" id="overview"><h2>1. Scientific assessment</h2>{_research_overview_v13(summary, validation, knowledge, root_cause, discrepancies)}</section>
<section class="section" id="comparison"><h2>2. Cohort comparison</h2>{_cohort_comparison_v13(validation)}</section>
<section class="section" id="findings"><h2>3. Major scientific discrepancies</h2>{_render_discrepancies(discrepancies)}</section>
<section class="section" id="statistics"><h2>4. Statistical evidence</h2>{_statistical_evidence_v13(validation, discrepancies)}</section>
<section class="section" id="scope"><h2>5. Validation scope</h2>{_validation_scope(knowledge)}</section>
<section class="section" id="root-cause"><h2>6. Root-cause assessment</h2>{_root_cause_assessment_v13(root_cause, discrepancies)}</section>
<section class="section" id="recommendations"><h2>7. Prioritised recommendations</h2>{_recommendations_v13(knowledge, discrepancies)}</section>
<section class="section" id="limitations"><h2>8. Limitations and outstanding questions</h2>{_limitations_v13(knowledge, root_cause, discrepancies)}</section>
<section class="section" id="appendix"><h2>9. Technical appendix</h2>{_technical_appendix(payload, validation, knowledge, root_cause)}</section>
<div class="footer">Generated deterministically from persisted Validation, Knowledge and Root Cause artifacts. The reporting stage consolidates and formats evidence; it does not recalculate scientific results.</div>
</main></body></html>"""


def _scientific_conclusion_v13(decision: str, discrepancies: Sequence[Mapping[str, Any]], knowledge: Mapping[str, Any]) -> str:
    ready = any(bool(m.get("research_use_ready")) for m in _mapping_sequence(knowledge.get("modules")))
    if decision == "PASS" and ready and not discrepancies:
        return "The available evidence supports equivalence for the evaluated modules within the stated scope and limitations."
    if decision == "INCOMPLETE":
        return "The experiment did not produce all required upstream results; no defensible equivalence conclusion can be issued."
    labels = [str(x.get("short_label")) for x in discrepancies[:4] if x.get("short_label")]
    suffix = ": " + ", ".join(labels) + "." if labels else "."
    return "Scientific equivalence between Psynthea and Synthea was not demonstrated" + suffix + " The evaluated module is not suitable for downstream research until these discrepancies are resolved and the experiment is repeated."


def _research_overview_v13(summary: Mapping[str, Any], validation: Mapping[str, Any], knowledge: Mapping[str, Any], root_cause: Mapping[str, Any], discrepancies: Sequence[Mapping[str, Any]]) -> str:
    val = _mapping(summary.get("validation")); know = _mapping(summary.get("knowledge")); root = _mapping(summary.get("root_cause"))
    modules = _mapping_sequence(knowledge.get("modules")); ready = sum(1 for m in modules if bool(m.get("research_use_ready")))
    major = len(discrepancies)
    return f"""<div class="cards">
{_metric_card('Comparison performed', f"{val.get('comparable_module_count', 0)} / {val.get('module_count', 0)}")}
{_metric_card('Overall equivalence', 'Not demonstrated' if major else 'Supported')}
{_metric_card('Major discrepancies', major)}
{_metric_card('Significant after FDR', val.get('significant_after_fdr_count'))}
{_metric_card('Research-ready modules', f"{ready} / {len(modules)}")}
{_metric_card('Root-cause status', root.get('status') or 'unknown')}
</div>
<div class="callout"><strong>Interpretation:</strong> “Comparison performed” means that the available cohorts supported statistical analysis. It does not mean that equivalence was demonstrated. Research readiness additionally requires clinically coherent outputs and no blocking scientific findings.</div>"""


def _cohort_counts(validation: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    cohorts = _mapping(validation.get("cohorts"))
    if cohorts:
        return {str(k): _mapping(v) for k, v in cohorts.items()}
    source = _mapping(validation.get("source"))
    return {str(k): _mapping(v) for k, v in _mapping(source.get("cohorts")).items()}


def _cohort_comparison_v13(validation: Mapping[str, Any]) -> str:
    cohorts = _cohort_counts(validation)
    synthea = _mapping(cohorts.get("synthea"))
    psynthea = _mapping(cohorts.get("psynthea"))
    domains = ("patients", "conditions", "encounters", "medications", "observations", "procedures")
    rows = []
    for domain in domains:
        a = synthea.get(domain); b = psynthea.get(domain)
        if a is None and b is None:
            continue
        delta, delta_class = _relative_difference_display(a, b)
        if domain == "patients" and a == b:
            status = "performed"
        elif domain == "procedures" and _numeric_zero(a) and _numeric_zero(b):
            status = "not informative"
        else:
            status = "pass" if a == b else "review"
        rows.append(f"<tr><td>{escape(domain.title())}</td><td>{escape(_fmt(a))}</td><td>{escape(_fmt(b))}</td><td class=\"{delta_class}\">{escape(delta)}</td><td>{_badge(status)}</td></tr>")
    if not rows:
        return '<p class="empty">No cohort counts were available.</p>'
    return '<table><thead><tr><th>Clinical output</th><th>Synthea</th><th>Psynthea</th><th>Relative difference</th><th>Screening</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table><p class="muted">Relative differences describe output volume and are not used as a standalone equivalence criterion. “N/A” is reported when both reference and candidate counts are zero. When both cohorts contain zero events, the endpoint is marked “not informative” because no comparative conclusion can be drawn.</p>'


def _relative_difference_display(reference: Any, candidate: Any) -> tuple[str, str]:
    try:
        a = float(reference); b = float(candidate)
    except (TypeError, ValueError):
        return "N/A", ""
    if a == 0:
        return ("N/A", "delta-neutral") if b == 0 else ("Not estimable", "delta-positive")
    pct = ((b - a) / a) * 100.0
    text = f"{pct:+.1f} %"
    return text, "delta-neutral" if abs(pct) < 1e-12 else ("delta-positive" if pct > 0 else "delta-negative")


def _scientific_discrepancies(validation: Mapping[str, Any], knowledge: Mapping[str, Any]) -> list[dict[str, Any]]:
    cohorts = _cohort_counts(validation)
    synthea = _mapping(cohorts.get("synthea"))
    psynthea = _mapping(cohorts.get("psynthea"))
    findings = _all_knowledge_findings(knowledge)
    result: list[dict[str, Any]] = []
    definitions = (
        ("observations", "Observation generation absent", "observations", "critical", "No clinical observations were produced by Psynthea."),
        ("medications", "Medication generation absent", "medications", "critical", "No medication records were produced by Psynthea."),
        ("encounters", "Encounter generation differs materially", "encounters", "high", "Psynthea generated substantially fewer encounters than Synthea."),
        ("conditions", "Hypertension prevalence differs", "conditions", "high", "The principal hypertension prevalence differs materially between engines."),
    )
    for key, title, domain, severity, impact in definitions:
        reference = synthea.get(domain)
        candidate = psynthea.get(domain)
        if not _material_count_difference(reference, candidate):
            continue
        related = _endpoint_findings(findings, key)
        tests = _supporting_tests_for_endpoint(key, related)
        evidence = _scientific_evidence_summary(key, reference, candidate, related)
        dimensions = _distinct_evidence_dimensions(key, tests, related)
        result.append({
            "key": key,
            "title": title,
            "short_label": title.lower(),
            "severity": severity,
            "impact": impact,
            "synthea": reference,
            "psynthea": candidate,
            "difference": _relative_difference_display(reference, candidate)[0],
            "tests": tests,
            "evidence": evidence,
            "strength": _evidence_strength_v131(dimensions),
            "finding_count": len(related),
            "evidence_dimensions": dimensions,
        })
    return result


def _material_count_difference(reference: Any, candidate: Any) -> bool:
    try:
        a = float(reference); b = float(candidate)
    except (TypeError, ValueError):
        return False
    if a == b:
        return False
    if a == 0:
        return b != 0
    return abs((b - a) / a) >= 0.10


def _all_knowledge_findings(knowledge: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for module in _mapping_sequence(knowledge.get("modules")):
        report = _mapping(module.get("interpretation_report"))
        out.extend(_mapping_sequence(report.get("findings")))
        out.extend(_mapping_sequence(_mapping(module.get("summary")).get("priority_findings")))
    unique: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in out:
        identity = str(item.get("finding_id") or item.get("id") or (item.get("title"), item.get("observation")))
        if identity not in seen:
            seen.add(identity)
            unique.append(item)
    return unique


def _finding_text(finding: Mapping[str, Any]) -> str:
    return " ".join(str(finding.get(k) or "") for k in ("title", "finding_id", "observation", "interpretation", "impact", "rule_id", "evidence_ids")).lower()


def _endpoint_findings(findings: Sequence[Mapping[str, Any]], endpoint: str) -> list[Mapping[str, Any]]:
    structured_tokens = {
        "observations": {"observations", "observation", "observations_per_patient"},
        "medications": {"medications", "medication", "medications_per_patient"},
        "encounters": {"encounters", "encounter", "encounters_per_patient"},
        "conditions": {"conditions", "condition", "59621000", "conditions.59621000"},
    }[endpoint]
    text_aliases = {
        "observations": ("observations_per_patient", "observation generation", "observation table"),
        "medications": ("medications_per_patient", "medication generation", "medication table"),
        "encounters": ("encounters_per_patient", "encounter generation", "encounter volume"),
        "conditions": ("conditions.59621000", "hypertension prevalence", "prevalence endpoint"),
    }[endpoint]

    matched: list[Mapping[str, Any]] = []
    for finding in findings:
        structured = " ".join(
            str(finding.get(key) or "")
            for key in (
                "endpoint",
                "endpoint_id",
                "metric",
                "metric_id",
                "domain",
                "code",
                "rule_id",
                "evidence_ids",
            )
        ).casefold()
        structured_parts = {
            token.strip(" ,;:[](){}\"'").casefold()
            for token in structured.replace("/", " ").split()
            if token.strip()
        }
        if any(token.casefold() in structured_parts for token in structured_tokens):
            matched.append(finding)
            continue

        text = _finding_text(finding)
        if any(alias in text for alias in text_aliases):
            matched.append(finding)

    return matched


def _supporting_tests_for_endpoint(
    endpoint: str,
    findings: Sequence[Mapping[str, Any]],
) -> list[str]:
    text = " ".join(_finding_text(item) for item in findings)
    evidence: list[str] = []

    if endpoint in {"observations", "medications"}:
        evidence.append("Functional output-retention assessment")
        if any(token in text for token in ("kolmogorov", "mann", "welch")):
            evidence.append("Complementary distribution, location and mean comparisons")
    elif endpoint == "encounters":
        evidence.append("Cohort-level encounter-volume comparison")
        if any(token in text for token in ("kolmogorov", "mann", "welch")):
            evidence.append("Complementary distribution, location and mean comparisons")
    else:
        evidence.append("Prevalence comparison")
        if "risk_ratio" in text:
            evidence.append("Risk-ratio effect estimate")
        if any(token in text for token in ("adjusted_p", "fdr")):
            evidence.append("Multiplicity-adjusted inference")
        if any(token in text for token in ("confidence", "95% ci", "95 % ci")):
            evidence.append("95 % confidence interval")

    return list(dict.fromkeys(evidence))


def _scientific_evidence_summary(endpoint: str, reference: Any, candidate: Any, findings: Sequence[Mapping[str, Any]]) -> str:
    if endpoint in {"observations", "medications"}:
        label = "observation" if endpoint == "observations" else "medication"
        return f"Synthea generated {_fmt(reference)} {label} records, whereas Psynthea generated none. Both output tables were present, but the Psynthea {label} table was empty."
    if endpoint == "encounters":
        delta, _ = _relative_difference_display(reference, candidate)
        evidence = _encounter_statistical_evidence(findings)
        return (f"Synthea generated {_fmt(reference)} encounters and Psynthea {_fmt(candidate)} ({delta}). " + evidence).strip()
    prevalence = _prevalence_evidence(findings)
    if prevalence:
        return prevalence
    delta, _ = _relative_difference_display(reference, candidate)
    return f"Synthea prevalence: {_percent_from_count(reference)}; Psynthea prevalence: {_percent_from_count(candidate)}; relative difference: {delta}."


def _best_matching_observation(findings: Sequence[Mapping[str, Any]], tokens: Sequence[str]) -> str:
    observations = [str(finding.get("observation")) for finding in findings if finding.get("observation") and any(token in _finding_text(finding) for token in tokens)]
    observations.sort(key=len, reverse=True)
    return observations[0] if observations else ""


def _encounter_statistical_evidence(findings: Sequence[Mapping[str, Any]]) -> str:
    import re

    text = " ".join(
        str(finding.get("observation") or "")
        for finding in findings
        if any(
            token in _finding_text(finding)
            for token in ("welch", "encounters_per_patient")
        )
    )
    if not text:
        return ""

    p_match = re.search(
        r"(?:adjusted_)?p(?:_value)?\s*[=:]\s*([0-9.eE+-]+)",
        text,
        flags=re.IGNORECASE,
    )
    effect_match = re.search(
        r"effect(?:_size)?\s*[=:]\s*([0-9.eE+-]+)",
        text,
        flags=re.IGNORECASE,
    )
    n_s_match = re.search(r"n_synthea\s*[=:]\s*(\d+)", text, flags=re.IGNORECASE)
    n_p_match = re.search(r"n_psynthea\s*[=:]\s*(\d+)", text, flags=re.IGNORECASE)

    statements: list[str] = []
    if effect_match:
        effect = float(effect_match.group(1))
        magnitude = abs(effect)
        label = (
            "large"
            if magnitude >= 0.8
            else "moderate"
            if magnitude >= 0.5
            else "small"
            if magnitude >= 0.2
            else "negligible"
        )
        statements.append(
            "Standardized effect-size estimate reported by the Validation "
            f"Engine: {effect:.2f} ({label}); the persisted evidence does not "
            "identify the specific effect-size metric."
        )
    if p_match:
        statements.append(f"p-value: {_format_p_value(float(p_match.group(1)))}.")
    if n_s_match and n_p_match:
        statements.append(
            f"Cohort size: {_fmt(int(n_s_match.group(1)))} Synthea and "
            f"{_fmt(int(n_p_match.group(1)))} Psynthea patients."
        )

    return " ".join(statements) if statements else _best_matching_observation(
        findings,
        ("welch", "encounters_per_patient"),
    )


def _prevalence_evidence(findings: Sequence[Mapping[str, Any]]) -> str:
    import re
    text = " ".join(str(f.get("observation") or "") for f in findings)
    patterns = {
        "sp": r"Synthea prevalence=([0-9.eE+-]+)", "pp": r"psynthea prevalence=([0-9.eE+-]+)",
        "ad": r"absolute_difference=([0-9.eE+-]+)", "rd": r"relative_difference=([0-9.eE+-]+)",
        "rr": r"risk_ratio=([0-9.eE+-]+)", "lo": r"95% CI=\[([0-9.eE+-]+)",
        "hi": r"95% CI=\[[0-9.eE+-]+, ([0-9.eE+-]+)\]", "p": r"adjusted_p=([0-9.eE+-]+)",
    }
    values: dict[str, float] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try: values[key] = float(match.group(1))
            except ValueError: pass
    if not {"sp", "pp", "rr", "lo", "hi", "p"}.issubset(values):
        return ""
    absolute = values.get("ad", values["pp"] - values["sp"])
    relative = values.get("rd", (values["pp"] - values["sp"]) / values["sp"] if values["sp"] else 0.0)
    return (f"Synthea prevalence: {values['sp'] * 100:.1f} %; Psynthea prevalence: {values['pp'] * 100:.1f} %; "
            f"absolute difference: {absolute * 100:+.1f} percentage points; relative difference: {relative * 100:+.1f} %; "
            f"risk ratio: {values['rr']:.2f}; 95 % CI: {values['lo']:.2f}–{values['hi']:.2f}; FDR-adjusted p-value: {_format_p_value(values['p'])}.")


def _percent_from_count(value: Any) -> str:
    try: return f"{float(value):.1f} %"
    except (TypeError, ValueError): return _fmt(value)


def _format_p_value(value: float) -> str:
    return f"{value:.3f}" if value >= 0.001 else f"{value:.2e}"


def _distinct_evidence_dimensions(endpoint: str, tests: Sequence[str], findings: Sequence[Mapping[str, Any]]) -> int:
    dimensions = 1
    if tests: dimensions += 1
    text = " ".join(_finding_text(item) for item in findings)
    if any(token in text for token in ("retention", "table empty", "table_empty", "clinical event volume")): dimensions += 1
    if endpoint == "conditions" and any(token in text for token in ("risk_ratio", "confidence", "95% ci")): dimensions += 1
    return min(dimensions, 4)


def _evidence_strength_v131(dimensions: int) -> str:
    return "Strong" if dimensions >= 3 else ("Moderate" if dimensions == 2 else "Preliminary")


def _render_discrepancies(
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    if not discrepancies:
        return '<p class="empty">No major clinically material discrepancy was identified.</p>'

    blocks: list[str] = []
    for item in discrepancies:
        evidence_basis = _html_list(
            item.get("tests") or (),
            "No supporting evidence category was extracted.",
        )
        blocks.append(
            f'<article class="discrepancy"><div>{_badge(item.get("severity"))} '
            f'{_badge("blocking")}</div><h3>{escape(str(item.get("title")))}</h3>'
            f'<p>{escape(str(item.get("impact")))}</p><div class="discrepancy-grid">'
            f'<div class="mini"><span class="label">Cohort evidence</span>'
            f'Synthea: <strong>{escape(_fmt(item.get("synthea")))}</strong><br>'
            f'Psynthea: <strong>{escape(_fmt(item.get("psynthea")))}</strong><br>'
            f'Difference: <strong>{escape(str(item.get("difference")))}</strong></div>'
            f'<div class="mini"><span class="label">Scientific evidence</span>'
            f'{escape(str(item.get("evidence")))}</div>'
            f'<div class="mini"><span class="label">Evidence basis</span>{evidence_basis}</div>'
            f'<div class="mini"><span class="label">Interpretation status</span>'
            f'{_badge("supported discrepancy")}<br><span class="muted">'
            f'{escape(str(item.get("finding_count")))} supporting engine finding(s); '
            'counts may share underlying evidence.</span></div></div></article>'
        )

    return (
        "".join(blocks)
        + '<div class="callout"><strong>Evidence-count caution:</strong> '
        'Supporting engine findings can share underlying evidence and must not '
        'be interpreted as independent replications.</div>'
        '<p class="muted"><strong>Severity definitions:</strong> Critical indicates '
        'complete absence of output in a clinically relevant domain where Synthea '
        'produced events. High indicates generated output with a material and '
        'statistically supported discordance.</p>'
    )


def _endpoint_statistical_summary(item: Mapping[str, Any]) -> str:
    key = str(item.get("key") or "")
    evidence = str(item.get("evidence") or "")

    if key in {"observations", "medications"}:
        return "Not estimable: Psynthea generated no events for this endpoint."
    if key == "encounters":
        marker = "Standardized effect-size estimate"
        start = evidence.find(marker)
        if start >= 0:
            return evidence[start:]
        return "No endpoint-specific effect estimate was available."
    if key == "conditions":
        marker = "risk ratio:"
        start = evidence.lower().find(marker)
        if start >= 0:
            summary = evidence[start:]
            return summary[0].upper() + summary[1:]
        return "No prevalence effect estimate was available."
    return "No endpoint-specific estimate was available."


def _statistical_evidence_v13(
    validation: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    aggregate = _mapping(validation.get("aggregate"))
    rows = []
    for module in _mapping_sequence(validation.get("modules")):
        summary = _mapping(module.get("statistical_summary"))
        rows.append((
            module.get("module_name"),
            summary.get("validation_status"),
            summary.get("significant_test_count"),
            summary.get("significant_after_fdr_count"),
            summary.get("valid_for_statistical_comparison"),
        ))

    body = "".join(
        f'<tr><td>{escape(_fmt(module))}</td><td>{_badge(status)}</td>'
        f'<td>{escape(_fmt(significant))}</td><td>{escape(_fmt(fdr))}</td>'
        f'<td>{_badge("performed" if valid else "incomplete")}</td>'
        f'<td>{_badge("not demonstrated" if discrepancies else "pass")}</td></tr>'
        for module, status, significant, fdr, valid in rows
    )

    endpoint_rows = "".join(
        f'<tr><td>{escape(str(item.get("title") or item.get("key") or "Endpoint"))}</td>'
        f'<td>{escape(_fmt(item.get("synthea")))}</td>'
        f'<td>{escape(_fmt(item.get("psynthea")))}</td>'
        f'<td>{escape(str(item.get("difference") or "—"))}</td>'
        f'<td>{escape(_endpoint_statistical_summary(item))}</td></tr>'
        for item in discrepancies
    )
    endpoint_table = (
        '<h3>Key endpoint estimates</h3>'
        '<table><thead><tr><th>Endpoint</th><th>Synthea</th><th>Psynthea</th>'
        '<th>Relative difference</th><th>Statistical estimate</th></tr></thead>'
        f'<tbody>{endpoint_rows}</tbody></table>'
        '<p class="muted">A 95 % confidence interval is shown only when present '
        'in persisted upstream evidence. No interval or effect-size identity is '
        'inferred by the reporting stage.</p>'
        if endpoint_rows
        else '<p class="empty">No key discrepant endpoint estimates were available.</p>'
    )

    return (
        f'<div class="cards">'
        f'{_metric_card("Modules tested", aggregate.get("module_count"))}'
        f'{_metric_card("Nominally significant tests", aggregate.get("significant_test_count"))}'
        f'{_metric_card("Significant after FDR", aggregate.get("significant_after_fdr_count"))}'
        f'{_metric_card("Warnings", aggregate.get("warning_count"))}'
        f'</div><h3>Module-level interpretation</h3>'
        f'<table><thead><tr><th>Module</th><th>Validation status</th>'
        f'<th>Nominally significant</th><th>After FDR</th><th>Comparison</th>'
        f'<th>Equivalence</th></tr></thead><tbody>{body}</tbody></table>'
        f'{endpoint_table}'
        '<p class="muted">Multiple tests supporting the same clinical discrepancy '
        'are consolidated in Section 3. P-values, effect estimates and confidence '
        'intervals are reproduced from the Validation and Knowledge engines; the '
        'report performs no statistical recalculation.</p>'
    )


def _validation_scope(knowledge: Mapping[str, Any]) -> str:
    identifiers = _collect_validation_identifiers(knowledge)
    spanish = sorted(x for x in identifiers if "SPANISH." in x.upper())
    other = _consolidate_validation_identifiers(
        x for x in identifiers if x not in spanish and x.upper().startswith("EPI.")
    )
    if spanish:
        spanish_html = _html_list(spanish, "")
        spanish_note = "Spanish-healthcare rules were present but were not evaluated with an explicit Spanish clinical reference."
    else:
        spanish_html = '<p class="empty">No Spanish-healthcare rule identifiers were present in the persisted Knowledge Engine output.</p>'
        spanish_note = "Spanish healthcare adaptation remains outside this experiment's scope."
    return f'<div class="scope-grid"><div class="scope-box"><span class="label">Evaluated in this experiment</span><h3>Synthea–Psynthea equivalence</h3><ul><li>Functional output generation</li><li>Clinical event volumes</li><li>Prevalence and distributional endpoints</li><li>Multiplicity-adjusted statistical evidence</li></ul></div><div class="scope-box"><span class="label">Not evaluated in this experiment</span><h3>Spanish healthcare adaptation</h3>{spanish_html}<p>{escape(spanish_note)}</p><p class="muted">These dimensions require an independent experiment with an explicit Spanish clinical reference. They must not be interpreted as failed Synthea–Psynthea equivalence results.</p></div></div><details><summary>Other incomplete or non-applicable validation dimensions</summary>{_html_list(other, "No additional out-of-scope dimensions were identified.")}</details>'


def _consolidate_validation_identifiers(identifiers: Sequence[str] | Any) -> list[str]:
    consolidated: dict[str, str] = {}
    suffixes = {"PASS", "FAIL", "WARNING", "INFERENCE", "INCOMPLETE", "INCONCLUSIVE", "RECALIBRATE", "NOT_APPLICABLE", "NOT_EVALUATED"}
    for raw in identifiers:
        value = str(raw).strip()
        parts = value.split(".")
        while parts and parts[-1].upper() in suffixes:
            parts.pop()
        key = ".".join(parts) or value
        consolidated.setdefault(key.casefold(), key)
    return sorted(consolidated.values(), key=str.casefold)


def _collect_validation_identifiers(value: Any) -> set[str]:
    identifiers: set[str] = set()
    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if isinstance(child, str) and str(key).lower() in {"rule_id", "id", "action_id", "rule", "code"}:
                    if "SPANISH." in child.upper() or child.upper().startswith("EPI."):
                        identifiers.add(child)
                visit(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item: visit(child)
        elif isinstance(item, str):
            for token in item.replace("'", " ").replace('"', " ").replace(",", " ").split():
                cleaned = token.strip(".;:()[]{}")
                if "SPANISH." in cleaned.upper() or cleaned.upper().startswith("EPI."):
                    identifiers.add(cleaned)
    visit(value)
    return identifiers

def _root_cause_assessment_v13(
    root: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    conclusion = _mapping(root.get("conclusion"))
    counts = _mapping(root.get("counts"))
    findings = _mapping_sequence(root.get("findings"))
    candidates = {
        str(item.get("id")): item
        for item in _mapping_sequence(root.get("candidates"))
    }

    plausible = [
        finding
        for finding in findings
        if str(finding.get("status")).lower() in {"plausible", "probable", "confirmed"}
    ]
    selected: list[Mapping[str, Any]] = []
    for finding in plausible:
        for candidate_id in _sequence(finding.get("selected_candidate_ids")):
            candidate = candidates.get(str(candidate_id))
            if candidate:
                selected.append(candidate)

    statement = "No clinically specific cause has been confirmed."
    if selected:
        raw = str(selected[0].get("statement") or selected[0].get("category") or "")
        if "probabilistic" in raw.lower() or "probabilistic" in str(selected[0]).lower():
            statement = (
                "Differences in probabilistic transition semantics may contribute "
                "to at least one observed discrepancy."
            )
        elif raw:
            statement = raw

    status = str(conclusion.get("status") or "inconclusive")
    verification_count = _integer(counts.get("verifications"))
    verification_status = "Performed" if verification_count > 0 else "Not performed"
    confirmed_count = sum(
        1 for finding in findings if str(finding.get("status")).lower() == "confirmed"
    )

    return (
        f'<div class="cards">'
        f'{_metric_card("Root-cause status", status)}'
        f'{_metric_card("Deterministic verification", verification_status)}'
        f'{_metric_card("Confirmed causes", confirmed_count)}'
        f'</div><h3>Leading investigation hypothesis</h3><p>{escape(statement)}</p>'
        '<div class="discrepancy-grid">'
        '<div class="mini"><span class="label">Evidence status</span>Indirect only. '
        'No deterministic verification has established causality.</div>'
        f'<div class="mini"><span class="label">Affected discrepancies</span>'
        f'{escape(", ".join(str(item.get("title")) for item in discrepancies) or "Not linked")}</div>'
        '<div class="mini"><span class="label">Scientific interpretation</span>'
        'The current root-cause result is hypothesis-generating, not confirmatory.'        '</div></div><div class="callout"><strong>Causal caution:</strong> A plausible '
        'candidate prioritises investigation. It must not be reported as the '
        'confirmed explanation while verification remains incomplete.</div>'
    )


def _recommendations_v13(knowledge: Mapping[str, Any], discrepancies: Sequence[Mapping[str, Any]]) -> str:
    primary = {
        "observations": ("Restore Observation generation", "Ensure clinically intended observation states emit valid records, then repeat the same seeded comparison."),
        "medications": ("Restore Medication generation", "Ensure medication-order states emit medication records and validate event retention against Synthea."),
        "encounters": ("Review encounter workflow", "Inspect encounter creation, closure and transition logic responsible for the approximately 95% volume deficit."),
        "conditions": ("Review hypertension probabilities", "Audit incidence, prevalence and transition probabilities, then repeat prevalence validation across independent seeds."),
    }
    rendered = []
    for idx, item in enumerate(discrepancies, 1):
        title, action = primary.get(str(item.get("key")), (str(item.get("title")), "Investigate and repeat validation."))
        rendered.append(f'''<div class="recommendation"><div class="rank">{idx}</div><div><div>{_badge('urgent' if item.get('severity')=='critical' else 'high')} {_badge('blocking')}</div><h3>{escape(title)}</h3><p>{escape(action)}</p><p><strong>Verification:</strong> Re-run identical cohorts first, then repeat across independent seeds and confirm that the relevant endpoint falls within the approved tolerance.</p></div></div>''')
    additional = []
    for module in _mapping_sequence(knowledge.get("modules")):
        for rec in _mapping_sequence(_mapping(module.get("recommendation_plan")).get("items")):
            action = str(rec.get("action") or rec.get("action_id") or "")
            if action and not any(token in action.lower() for token in ("spanish", "primary_care", "referral")):
                additional.append(action)
    additional = list(dict.fromkeys(additional))
    details = '<details><summary>Additional engine recommendations</summary>' + _html_list(additional, "No additional recommendations were generated.") + '</details>'
    return ''.join(rendered) + details


def _limitations_v13(
    knowledge: Mapping[str, Any],
    root: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    limitations = [
        "The current experiment uses one cohort size and one random seed; reproducibility across independent seeds has not yet been demonstrated.",
        "Missing Observation and Medication outputs prevent complete clinical equivalence assessment for the hypertension module.",
        "The Root Cause Engine result is inconclusive and no deterministic verification has confirmed a causal mechanism.",
        "Spanish healthcare adaptation was outside the evaluated scope and requires a separate reference-driven experiment.",
    ]
    questions_map = {
        "observations": "Why are Observation states producing no records?",
        "medications": "Why are MedicationOrder or treatment states not emitting medication records?",
        "encounters": "Which workflow or transition logic reduces encounter generation relative to Synthea?",
        "conditions": "Which probability, transition or denominator difference produces excess hypertension prevalence?",
    }
    questions = [
        questions_map[str(item.get("key"))]
        for item in discrepancies
        if str(item.get("key")) in questions_map
    ]
    return (
        f'<h3>Primary limitations</h3>'
        f'{_html_list(limitations, "No primary limitations were identified.")}'
        f'<h3>Outstanding scientific questions</h3>'
        f'{_html_list(questions, "No outstanding scientific question was identified.")}'
        '<p class="muted">Internal root-cause signal identifiers and unresolved '
        'engine-level records are intentionally excluded from the research-facing '
        'HTML report. They remain available in the hashed machine-readable Root '
        'Cause artifact for engineering investigation.</p>'
    )


def _technical_appendix(payload: Mapping[str, Any], validation: Mapping[str, Any], knowledge: Mapping[str, Any], root: Mapping[str, Any]) -> str:
    validation_summary = {"schema_version": validation.get("schema_version"), "generated_at": validation.get("generated_at"), "aggregate": validation.get("aggregate"), "configuration": validation.get("configuration"), "cohorts": validation.get("cohorts"), "modules": validation.get("modules")}
    knowledge_summary = {"schema_version": knowledge.get("schema_version"), "generated_at": knowledge.get("generated_at"), "aggregate": knowledge.get("aggregate"), "configuration": knowledge.get("configuration"), "modules": [{"module_name": module.get("module_name"), "overall_status": module.get("overall_status"), "research_use_ready": module.get("research_use_ready"), "finding_count": module.get("finding_count"), "blocking_finding_count": module.get("blocking_finding_count"), "recommendation_count": module.get("recommendation_count"), "incomplete_rule_count": module.get("incomplete_rule_count"), "artifacts": module.get("artifacts")} for module in _mapping_sequence(knowledge.get("modules"))]}
    root_summary = {"schema_version": root.get("schema_version"), "generated_at": root.get("generated_at"), "identity": root.get("identity"), "conclusion": root.get("conclusion"), "counts": root.get("counts"), "limitations": root.get("limitations"), "engine": root.get("engine")}
    return (_render_stage_table(_mapping_sequence(payload.get("stage_summary"))) + _json_details("Source artifact manifest", payload.get("source_artifacts")) + _json_details("Validation Engine summary", validation_summary) + _json_details("Knowledge Engine summary", knowledge_summary) + _json_details("Root Cause Engine summary", root_summary) + '<div class="callout"><strong>Full machine-readable outputs:</strong> Complete Validation, Knowledge and Root Cause payloads remain available as separately hashed source artifacts listed in the manifest above. They are intentionally not duplicated inside this HTML report.</div>')

def _render_stage_table(stages: Sequence[Mapping[str, Any]]) -> str:
    if not stages:return '<p class="empty">No stage execution summary was available.</p>'
    body=''.join(f'<tr><td>{escape(_fmt(x.get("stage")))}</td><td>{_badge(x.get("status"))}</td><td>{escape(_fmt(x.get("summary")))}</td><td>{escape(_fmt(x.get("error_message") or "—"))}</td></tr>' for x in stages)
    return f'<h3>Pipeline execution</h3><table><thead><tr><th>Stage</th><th>Status</th><th>Summary</th><th>Error</th></tr></thead><tbody>{body}</tbody></table>'


def _metric_card(label: str, value: Any) -> str:
    return f'<div class="card"><span class="label">{escape(label)}</span><span class="value">{escape(_fmt(value))}</span></div>'


def _json_details(title: str, value: Any) -> str:
    return f'<details><summary>{escape(title)}</summary><pre>{escape(json.dumps(_plain_value(value),ensure_ascii=False,indent=2,sort_keys=True))}</pre></details>'


def _html_list(values: Sequence[Any], empty: str) -> str:
    return '<ul>'+''.join(f'<li>{escape(str(x))}</li>' for x in values)+'</ul>' if values else f'<p class="empty">{escape(empty)}</p>'


def _badge(value: Any) -> str:
    text=str(value or 'unknown'); css=''.join(ch if ch.isalnum() else '-' for ch in text.lower()).strip('-')
    return f'<span class="badge badge-{escape(css)}">{escape(text)}</span>'


def _decision_color(decision: str) -> str:
    return {"PASS":"var(--green)","REVIEW":"var(--amber)","INCOMPLETE":"var(--red)"}.get(decision,"var(--muted)")


def _decision_background(decision: str) -> str:
    return {"PASS":"var(--soft-green)","REVIEW":"var(--soft-amber)","INCOMPLETE":"var(--soft-red)"}.get(decision,"#f2f4f7")


def _decision_border(decision: str) -> str:
    return {"PASS":"#b9dec9","REVIEW":"#efd09b","INCOMPLETE":"#edbbc0"}.get(decision,"var(--line)")


def _comparison_status(a: Any,b: Any) -> str:
    if a is None or b is None:return 'incomplete'
    try:return 'pass' if float(a)==float(b) else 'review'
    except (TypeError,ValueError):return 'pass' if a==b else 'review'


def _dedupe_rows(rows: Sequence[tuple[Any,...]]) -> list[tuple[Any,...]]:
    seen=set(); out=[]
    for row in rows:
        key=tuple(str(x) for x in row[:4])
        if key not in seen:seen.add(key);out.append(row)
    return out


def _table_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value,Mapping):
        for key in ("rows","records","data","items"):
            if key in value:return _mapping_sequence(value.get(key))
        if value and all(isinstance(v,Mapping) for v in value.values()):return tuple(_mapping(v) for v in value.values())
    return _mapping_sequence(value)


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) is not None:return mapping.get(key)
    return None


def _severity_rank(value: Any) -> int:
    return {"critical":0,"high":1,"medium":2,"moderate":2,"low":3}.get(str(value).lower(),4)


def _priority_rank(value: Any) -> int:
    return {"urgent":0,"high":1,"medium":2,"normal":2,"low":3}.get(str(value).lower(),4)


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return f"{int(value):,}"
        return f"{value:.4g}"
    return str(value)


def _numeric_zero(value: Any) -> bool:
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _integer(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _aware_datetime(value, "datetime value").isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return str(value)


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)