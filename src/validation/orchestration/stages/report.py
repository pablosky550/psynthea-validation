"""Final scientific-report generation stage.

The stage composes the already persisted validation, interpretation and
root-cause products into one experiment-level report. It deliberately performs
no statistical recalculation, evidence acquisition or causal inference.
"""

from __future__ import annotations

import math

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
import json
import re
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
    "ScientificNarrativeFormatter",
]

_REPORT_SCHEMA_VERSION: Final = "7.0.0"
_REPORT_PRODUCER: Final = "scientific_report_stage"
_REPORT_JSON_PATH: Final = "report/scientific_report.json"
_REPORT_HTML_PATH: Final = "report/scientific_report.html"

_COUNT_MATERIALITY_THRESHOLD: Final = 0.10
_LOW_COUNT_THRESHOLD: Final = 20
_LOW_COUNT_REVIEW_THRESHOLD: Final = 0.25
_LOW_COUNT_MAX_ACCEPTABLE_ABSOLUTE_DIFFERENCE: Final = 1

_REQUIRED_UPSTREAM_ARTIFACTS: Final = {
    ArtifactKind.VALIDATION_RESULT: "validation result",
    ArtifactKind.KNOWLEDGE_RESULT: "knowledge result",
    ArtifactKind.ROOT_CAUSE_RESULT: "root-cause result",
}


class ReportGenerationStageError(RuntimeError):
    """Raised when a truthful final report cannot be composed."""


@dataclass(frozen=True, slots=True)
class ScientificNarrativeFormatter:
    """Translate persisted evidence into publication-oriented scientific prose.

    The formatter never calculates new scientific results. It only selects,
    rounds and narrates values already present in the upstream artifacts.
    """

    decision: str
    module_label: str
    knowledge: Mapping[str, Any]
    root_cause: Mapping[str, Any]
    discrepancies: Sequence[Mapping[str, Any]]

    def abstract(self) -> str:
        """Return a structured IMRaD-style abstract."""
        objective = (
            f"To determine whether Psynthea reproduces Synthea outputs for "
            f"{self.module_label} within the configured functional, statistical "
            "and clinical validation scope."
        )
        methods = (
            "Persisted cohorts were compared using deterministic functional "
            "checks, multiplicity-adjusted statistical evidence, clinical and "
            "epidemiological interpretation, and hypothesis-generating "
            "root-cause analysis."
        )
        results = self.results_summary(max_findings=3)
        conclusion = self.conclusion()
        return (
            f"<p><strong>Objective.</strong> {escape(objective)}</p>"
            f"<p><strong>Métodos.</strong> {escape(methods)}</p>"
            f"<p><strong>Resultados.</strong> {escape(results)}</p>"
            f"<p><strong>Conclusion.</strong> {escape(conclusion)}</p>"
        )

    def results_summary(self, *, max_findings: int = 3) -> str:
        """Summarise the highest-priority findings without exposing engine prose."""
        if not self.discrepancies:
            return (
                "No scientifically material discrepancy was identified in the "
                "persisted evidence."
            )
        statements = [
            self.finding_sentence(item)
            for item in self.discrepancies[:max_findings]
        ]
        return " ".join(statement for statement in statements if statement)

    def conclusion(self) -> str:
        """Return the publication-facing conclusion."""
        modules = _mapping_sequence(self.knowledge.get("modules"))
        ready = bool(modules) and all(
            bool(module.get("research_use_ready")) for module in modules
        )
        if self.decision == "NOT_COMPARABLE":
            return (
                "Equivalence could not be assessed because the persisted "
                "reference evidence was incomplete. No conclusion of agreement "
                "or disagreement between generators is scientifically defensible."
            )
        if self.decision == "INCOMPLETE":
            return (
                "The available evidence is incomplete and does not permit a "
                "defensible equivalence conclusion."
            )
        if self.decision == "PASS" and ready and not self.discrepancies:
            return (
                "No scientifically material discrepancy was detected in this "
                "configured execution. This result supports continued validation "
                "but does not, by itself, demonstrate equivalence or justify "
                "replacement of Synthea by Psynthea."
            )
        return (
            "Scientific equivalence was not demonstrated. Psynthea should not "
            "replace Synthea for downstream research in the evaluated scope "
            "until blocking discrepancies are resolved and independently "
            "reproduced."
        )

    def finding_sentence(self, item: Mapping[str, Any]) -> str:
        """Narrate one finding as a concise result sentence."""
        domain = _humanize(
            str(item.get("domain") or item.get("key") or "endpoint")
        ).lower()
        category = str(item.get("category") or "")
        stats = _extract_display_statistics(
            item.get("related_findings") or ()
        )
        reference = item.get("synthea")
        candidate = item.get("psynthea")

        if category == "missing_candidate_output":
            return (
                f"Psynthea did not reproduce {domain} output observed in "
                f"Synthea ({_fmt(reference)} versus {_fmt(candidate)} records)."
            )
        if category == "candidate_only_output":
            return (
                f"Psynthea introduced {domain} output that was absent from "
                f"Synthea ({_fmt(candidate)} versus {_fmt(reference)} records)."
            )
        if category == "volume_difference":
            direction = "more" if (_relative_difference(reference, candidate) or 0) > 0 else "fewer"
            sentence = (
                f"Psynthea contained materially {direction} {domain} records "
                f"than Synthea ({_fmt(candidate)} versus {_fmt(reference)}; "
                f"{item.get('difference') or 'difference not estimable'})."
            )
            inferential = self._inferential_clause(stats)
            return sentence[:-1] + (f"; {inferential}." if inferential else ".")
        title = str(item.get("title") or "").casefold()
        if "code concordance" in title or "code overlap" in title:
            shared = stats.get("shared")
            jaccard = stats.get("jaccard")
            jsd = stats.get("jsd")
            components = []
            if shared is not None:
                components.append(f"{_fmt(shared)} shared clinical codes")
            if jaccard is not None:
                components.append(f"Jaccard index {float(jaccard):.2f}")
            if jsd is not None:
                components.append(f"JSD {float(jsd):.3f}")
            evidence = ", ".join(components) or "persisted concordance evidence"
            return (
                f"Clinical coding for {domain} was not concordant between "
                f"generators ({evidence})."
            )
        if "prevalence" in title:
            s_prev = stats.get("synthea_prevalence")
            p_prev = stats.get("psynthea_prevalence")
            sentence = (
                f"The prevalence of {domain} differed between Synthea "
                f"({_format_percent(s_prev)}) and Psynthea "
                f"({_format_percent(p_prev)})."
            )
            inferential = self._inferential_clause(stats)
            return sentence[:-1] + (f"; {inferential}." if inferential else ".")
        return _clean_research_text(
            str(
                item.get("evidence")
                or item.get("impact")
                or "Persisted evidence identified a material discrepancy."
            )
        )

    def observed_result(self, item: Mapping[str, Any]) -> str:
        """Return a result-focused narrative with persisted estimates."""
        sentence = self.finding_sentence(item)
        return sentence or "A material discrepancy was identified."

    def scientific_interpretation(self, item: Mapping[str, Any]) -> str:
        """Explain what the result means scientifically."""
        title = str(item.get("title") or "").casefold()
        category = str(item.get("category") or "")
        if category == "missing_candidate_output":
            return (
                "The candidate implementation does not preserve an output domain "
                "present in the reference implementation, precluding equivalence "
                "for analyses that depend on that domain."
            )
        if category == "candidate_only_output":
            return (
                "The candidate implementation introduces events not represented "
                "in the reference implementation, indicating non-equivalent "
                "generation semantics."
            )
        if category == "volume_difference":
            return (
                "The magnitude of the between-generator difference exceeded the "
                "configured materiality threshold and is inconsistent with "
                "equivalent event-generation behaviour."
            )
        if "code concordance" in title or "code overlap" in title:
            return (
                "The generators do not represent sufficiently comparable clinical "
                "concepts or concept-frequency distributions for this domain."
            )
        if "prevalence" in title:
            return (
                "The population-level clinical burden is not reproduced within "
                "the evaluated equivalence criteria."
            )
        return (
            "The persisted evidence does not support scientific equivalence for "
            "this endpoint."
        )

    def scientific_implication(self, item: Mapping[str, Any]) -> str:
        """State the implication for downstream research."""
        domain = _humanize(
            str(item.get("domain") or "this endpoint")
        ).lower()
        title = str(item.get("title") or "").casefold()
        category = str(item.get("category") or "")
        if category == "missing_candidate_output":
            return (
                f"Studies using {domain} would systematically omit clinically "
                "relevant events if Psynthea were substituted for Synthea."
            )
        if "observations" in title:
            return (
                "Phenotyping, monitoring and outcome analyses based on "
                "observations may yield materially different results."
            )
        if "prevalence" in title:
            return (
                "Enfermedad-burden estimates, cohort definitions and epidemiological "
                "comparisons may be biased or non-comparable."
            )
        return (
            "Downstream estimates may differ by generator; replacement is not "
            "scientifically justified until this discrepancy is resolved."
        )

    def overall_interpretation(self) -> str:
        """Return the main Discusión interpretation."""
        if self.decision == "NOT_COMPARABLE":
            return (
                "The reference generator did not provide the minimum persisted "
                "clinical evidence required for a valid comparison. Apparent "
                "zero-versus-non-zero differences are therefore treated as "
                "not assessable rather than as evidence of non-equivalence."
            )
        if self.decision == "INCOMPLETE":
            return (
                "The experiment did not provide a complete evidence chain, so "
                "equivalence and replacement cannot be assessed."
            )
        if not self.discrepancies:
            return (
                "Across the evaluated evidence layers, no material discrepancy "
                "was detected in this configured execution. Absence of a detected "
                "difference is not evidence of equivalence; interpretation remains "
                "restricted to the configured modules, cohort and validation criteria."
            )
        return (
            "Multiple independent evidence layers converge on the same conclusion: "
            "the observed differences are not adequately explained by a single "
            "minor fluctuation and instead indicate non-equivalent generator "
            "behaviour within the evaluated scope."
        )

    def clinical_implications(self) -> str:
        """Return a clinical-impact synthesis."""
        if self.decision == "NOT_COMPARABLE":
            return (
                "No generator-level clinical implication can be inferred from "
                "endpoints whose reference evidence is absent or insufficient."
            )
        if not self.discrepancies:
            return (
                "No material clinical implication was identified within the "
                "evaluated endpoints."
            )
        implications = [
            self.scientific_implication(item)
            for item in self.discrepancies[:3]
        ]
        return " ".join(dict.fromkeys(implications))

    def methodological_implications(self) -> str:
        """Return implications for validation design and interpretation."""
        if self.decision == "NOT_COMPARABLE":
            return (
                "Reference completeness is a prerequisite for scientific comparison. "
                "Empty or missing reference endpoints must be classified as not "
                "assessable and must not be converted into evidence of generator "
                "divergence."
            )
        return (
            "Agreement in cohort size or successful pipeline execution must not be "
            "interpreted as scientific equivalence. Replacement requires concordant "
            "output retention, event volumes, clinical semantics and endpoint-level "
            "evidence after multiplicity adjustment."
        )

    def _inferential_clause(self, stats: Mapping[str, Any]) -> str:
        parts: list[str] = []
        rr = stats.get("risk_ratio")
        lo = stats.get("ci_lower")
        hi = stats.get("ci_upper")
        p = stats.get("adjusted_p")
        if rr is not None:
            estimate = f"RR {float(rr):.2f}"
            if lo is not None and hi is not None:
                estimate += f", 95% CI {float(lo):.2f}–{float(hi):.2f}"
            parts.append(estimate)
        if p is not None:
            parts.append(f"FDR-adjusted p {_p_value_relation(float(p))}")
        if not parts:
            return ""
        return "; ".join(parts) + ", indicating that equivalence criteria were not met"


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

    decision = _decision(context, validation)
    analysis = _build_scientific_analysis(
        decision=decision,
        validation=validation,
        knowledge=knowledge,
        root_cause=root_cause,
    )
    configured_modules = _configured_modules(context, validation, knowledge)
    module_count = len(configured_modules)
    module_selection = (
        "single_module"
        if module_count == 1
        else "explicit_multi_module"
        if module_count > 1
        else "configured_module_set"
    )
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
            "modules": list(configured_modules),
            "module_count": module_count,
            "module_selection": module_selection,
            "reference_date": (
                context.config.cohort.reference_date.isoformat()
                if context.config.cohort.reference_date is not None
                else None
            ),
            "min_age": context.config.cohort.min_age,
            "max_age": context.config.cohort.max_age,
            "años_of_history": getattr(context.config.cohort, "años_of_history", None),
            "observation_start_date": (
                context.config.cohort.observation_start_date.isoformat()
                if getattr(context.config.cohort, "observation_start_date", None) is not None
                else None
            ),
            "observation_end_date": (
                context.config.cohort.observation_end_date.isoformat()
                if getattr(context.config.cohort, "observation_end_date", None) is not None
                else None
            ),
            "wellness_encounters": getattr(context.config.cohort, "wellness_encounters", False),
            "vitals": getattr(context.config.cohort, "vitals", False),
            "mortality": getattr(context.config.cohort, "mortality", False),
            "keystone": getattr(context.config.cohort, "keystone", False),
            "output_format": getattr(context.config.cohort, "output_format", None),
            "parameters": _plain_value(context.config.cohort.parameters),
        },
        "execution_provenance": _execution_provenance(context),
        "executive_summary": _build_executive_summary(
            decision=decision,
            validation=validation,
            knowledge=knowledge,
            root_cause=root_cause,
        ),
        "scientific_analysis": analysis,
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




def _execution_provenance(context: OrchestrationContext) -> dict[str, Any]:
    """Return reproducibility metadata without claiming unpersisted execution details."""
    configured: list[dict[str, Any]] = []
    for simulator in context.config.simulators:
        configured.append({
            "kind": simulator.kind.value,
            "command": list(simulator.command),
            "working_directory": str(simulator.working_directory),
            "arguments": _plain_value(simulator.arguments),
            "environment_keys": sorted(simulator.environment),
            "timeout_seconds": simulator.timeout_seconds,
        })

    observed: list[dict[str, Any]] = []
    for result in context.stage_results:
        metadata = _plain_value(result.metadata)
        for key in ("command", "commands", "executed_command", "simulator_commands"):
            value = _mapping(metadata).get(key)
            if value:
                observed.append({"stage": result.stage.value, "field": key, "value": value})
    return {
        "configured_simulators": configured,
        "persisted_execution_commands": observed,
        "command_status": "exact" if observed else "configured_contract_only",
    }

def _build_scientific_analysis(
    *,
    decision: str,
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    root_cause: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the machine-readable, module-agnostic interpretation layer."""
    validation_section = _build_validation_section(validation)
    knowledge_section = _build_knowledge_section(knowledge)
    root_section = _build_root_cause_section(root_cause)
    discrepancies = _scientific_discrepancies(validation_section, knowledge_section)
    return {
        "decision": decision,
        "conclusion": _scientific_conclusion_v13(
            decision,
            discrepancies,
            knowledge_section,
        ),
        "ranking_method": {
            "components": [
                "severity",
                "blocking_status",
                "relative_magnitude",
                "multiplicity_adjusted_significance",
                "evidence_support",
            ],
            "interpretation": (
                "The deterministic score prioritises investigation and is not "
                "a clinical effect estimate."
            ),
        },
        "discrepancies": [
            {
                key: _plain_value(value)
                for key, value in item.items()
                if key != "related_findings"
            }
            for item in discrepancies
        ],
        "root_cause_status": _mapping(root_section.get("conclusion")).get("status"),
        "interpretation_policy": {
            "technical_pass_is_not_equivalence": True,
            "non_significance_is_not_equivalence": True,
            "replacement_requires_confirmatory_replication": True,
            "positive_equivalence_claim_emitted": False,
        },
    }


def _configured_modules(
    context: OrchestrationContext,
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
) -> tuple[str, ...]:
    """Resolve module names from configuration and persisted upstream evidence."""
    values: list[str] = []

    values.extend(str(item) for item in context.config.cohort.modules if str(item))
    values.extend(
        Path(item).stem
        for item in getattr(context.config.cohort, "module_files", ())
        if str(item)
    )

    configuration = _mapping(validation.get("configuration"))
    values.extend(str(item) for item in _sequence(configuration.get("modules")) if str(item))
    values.extend(
        str(module.get("module_name"))
        for module in _mapping_sequence(validation.get("modules"))
        if module.get("module_name")
    )
    values.extend(
        str(module.get("module_name"))
        for module in _mapping_sequence(knowledge.get("modules"))
        if module.get("module_name")
    )

    return tuple(dict.fromkeys(value for value in values if value))

def _reference_evidence_incomplete(validation: Mapping[str, Any]) -> bool:
    """Return whether persisted reference evidence is insufficient for comparison.

    This guard converts upstream ``reference_empty``/missing-reference states into
    a report-level non-comparability decision. It deliberately does not infer that
    a numeric zero is missing data unless upstream evidence explicitly says so.
    """
    tokens = {
        "reference_empty",
        "reference empty",
        "reference_missing",
        "reference missing",
        "minimum reference clinical signal",
        "insufficient reference",
        "missing reference output",
    }
    text = " ".join(str(value) for value in _flatten_scalars(validation)).casefold()
    return any(token in text for token in tokens)


def _decision(
    context: OrchestrationContext,
    validation_payload: Mapping[str, Any] | None = None,
) -> str:
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
    if validation_payload is not None and _reference_evidence_incomplete(validation_payload):
        return "NOT_COMPARABLE"

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




def _module_scope_label(cohort: Mapping[str, Any]) -> str:
    """Return a concise human-readable module scope for the HTML report."""
    modules = [str(value) for value in _sequence(cohort.get("modules")) if str(value)]
    count = _integer(cohort.get("module_count")) or len(modules)
    if count == 1 and modules:
        return modules[0]
    if count > 1:
        return f"{count} explicitly selected modules"
    return "the configured module set"


def _module_selection_details(cohort: Mapping[str, Any]) -> str:
    """Render the complete module list without dominating the human report."""
    modules = [str(value) for value in _sequence(cohort.get("modules")) if str(value)]
    if len(modules) <= 1:
        return ""
    return (
        f'<details><summary>Show complete module selection ({len(modules)})</summary>'
        + _html_list(modules, "")
        + '</details>'
    )


def _age_range_label(cohort: Mapping[str, Any]) -> str:
    """Format the configured inclusive age range."""
    minimum = cohort.get("min_age")
    maximum = cohort.get("max_age")
    if minimum is None and maximum is None:
        return "No especificado"
    if minimum is None:
        return f"≤ {_fmt(maximum)} años"
    if maximum is None:
        return f"≥ {_fmt(minimum)} años"
    return f"{_fmt(minimum)}–{_fmt(maximum)} años"



def _first_mapping(*values: Any) -> Mapping[str, Any]:
    for value in values:
        mapped = _mapping(value)
        if mapped:
            return mapped
    return {}


def _validation_source(validation: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the canonical validation-stage payload embedded by report.py.

    The report payload exposes a curated validation view and preserves the
    original validation_result.json below ``source``. Cohort-level comparisons
    are currently part of that original payload, so research sections must
    inspect both levels without treating an empty curated view as evidence that
    the metrics were not generated.
    """
    return _first_mapping(validation.get("source"))


def _comparison_payload(validation: Mapping[str, Any]) -> Mapping[str, Any]:
    source = _validation_source(validation)
    return _first_mapping(
        validation.get("comparison"),
        validation.get("java_vs_psynthea"),
        validation.get("cohort_comparison"),
        source.get("comparison"),
        source.get("java_vs_psynthea"),
        source.get("cohort_comparison"),
    )


def _demographic_payload(validation: Mapping[str, Any]) -> Mapping[str, Any]:
    source = _validation_source(validation)
    comparison = _comparison_payload(validation)
    return _first_mapping(
        validation.get("demographics"),
        source.get("demographics"),
        comparison.get("demographics"),
        comparison.get("demographic_comparison"),
    )


def _epidemiology_payload(validation: Mapping[str, Any]) -> Mapping[str, Any]:
    source = _validation_source(validation)
    comparison = _comparison_payload(validation)
    return _first_mapping(
        validation.get("epidemiology"),
        source.get("epidemiology"),
        comparison.get("epidemiology"),
        comparison.get("clinical_epidemiology"),
    )


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if isinstance(value.get("rows"), Sequence) and not isinstance(value.get("rows"), (str, bytes)):
            return _mapping_sequence(value.get("rows"))
        output: list[Mapping[str, Any]] = []
        for key, item in value.items():
            mapped = _mapping(item)
            if mapped:
                output.append({"category": key, **mapped})
        return output
    return _mapping_sequence(value)


def _value_for_engine(row: Mapping[str, Any], engine: str, metric: str | None = None) -> Any:
    aliases = (engine, "java" if engine == "synthea" else "python")
    metric_aliases = {
        "proportion": ("proportion", "fraction", "rate"),
        "count": ("count", "n", "patients"),
    }
    if metric:
        for alias in aliases:
            for candidate_metric in metric_aliases.get(metric, (metric,)):
                for key in (
                    f"{candidate_metric}_{alias}",
                    f"{alias}_{candidate_metric}",
                ):
                    if key in row:
                        return row.get(key)
    for alias in aliases:
        if alias in row:
            value = row.get(alias)
            if metric and isinstance(value, Mapping):
                for candidate_metric in metric_aliases.get(metric, (metric,)):
                    if candidate_metric in value:
                        return value.get(candidate_metric)
            return value
    return None


def _age_statistic_values(
    age_summary: Mapping[str, Any],
    metric_key: str,
) -> tuple[Any, Any]:
    """Read both canonical and legacy age-summary layouts."""
    aliases = {
        "mean_age": ("mean_age", "mean"),
        "median_age": ("median_age", "median", "p50_age"),
        "std_age": ("std_age", "standard_deviation", "sd_age"),
        "p25_age": ("p25_age", "q1", "p25"),
        "p75_age": ("p75_age", "q3", "p75"),
        "min_age": ("min_age", "min"),
        "max_age": ("max_age", "max"),
    }
    for key in aliases.get(metric_key, (metric_key,)):
        value = age_summary.get(key)
        if isinstance(value, Mapping):
            return (
                _value_for_engine(value, "synthea"),
                _value_for_engine(value, "psynthea"),
            )
    return (
        _value_for_engine(age_summary, "synthea", metric_key),
        _value_for_engine(age_summary, "psynthea", metric_key),
    )


def _percent_points(reference: Any, candidate: Any) -> str:
    try:
        return f"{(float(candidate) - float(reference)) * 100:+.1f} pp"
    except (TypeError, ValueError):
        return "N/A"


def _scientific_note(text: str) -> str:
    return f'<div class="callout scientific-note"><strong>Scientific interpretation.</strong> {escape(text)}</div>'


def _cohort_age_limits(cohort: Mapping[str, Any]) -> tuple[int | None, int | None]:
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return _as_int(cohort.get("min_age")), _as_int(cohort.get("max_age"))


def _adapt_age_band_label(
    raw_label: Any,
    *,
    min_age: int | None,
    max_age: int | None,
) -> str:
    label = str(raw_label or "No especificado").strip()
    normalized = label.replace("–", "-").replace("—", "-")
    if normalized.endswith("+"):
        try:
            lower = int(normalized[:-1])
        except ValueError:
            return label
        effective_lower = max(lower, min_age) if min_age is not None else lower
        if max_age is not None:
            return f"{effective_lower}–{max_age}"
        return f"{effective_lower}+"
    if "-" not in normalized:
        return label
    lower_text, upper_text = normalized.split("-", 1)
    try:
        lower, upper = int(lower_text), int(upper_text)
    except ValueError:
        return label
    effective_lower = max(lower, min_age) if min_age is not None else lower
    effective_upper = min(upper, max_age) if max_age is not None else upper
    if effective_lower > effective_upper:
        return ""
    return f"{effective_lower}–{effective_upper}"


def _demographic_interpretation(
    age_summary: Mapping[str, Any],
    sex_rows: Sequence[Mapping[str, Any]],
) -> str:
    s_mean, p_mean = _age_statistic_values(age_summary, "mean_age")
    mean_delta: float | None = None
    try:
        mean_delta = float(p_mean) - float(s_mean)
    except (TypeError, ValueError):
        pass

    maximum_sex_delta: float | None = None
    for row in sex_rows:
        s_fraction = _value_for_engine(row, "synthea", "proportion")
        p_fraction = _value_for_engine(row, "psynthea", "proportion")
        try:
            delta = abs((float(p_fraction) - float(s_fraction)) * 100)
        except (TypeError, ValueError):
            continue
        maximum_sex_delta = delta if maximum_sex_delta is None else max(maximum_sex_delta, delta)

    evidence: list[str] = []
    if mean_delta is not None:
        evidence.append(f"la edad media difirió en {abs(mean_delta):.1f} años")
    if maximum_sex_delta is not None:
        evidence.append(f"la mayor diferencia entre categorías de sexo fue de {maximum_sex_delta:.1f} puntos porcentuales")

    if not evidence:
        return (
            "Age and sex are baseline comparability checks. Clinical differences remain descriptive "
            "until demographic balance and other design factors are assessed prospectively."
        )

    thresholds_exceeded = (
        (mean_delta is not None and abs(mean_delta) >= 5.0)
        or (maximum_sex_delta is not None and maximum_sex_delta >= 10.0)
    )
    if thresholds_exceeded:
        conclusion = (
            "The observed baseline imbalance is potentially material and should be considered when "
            "interpreting downstream clinical-rate differences. Stratified or adjusted analyses are recommended."
        )
    else:
        conclusion = (
            "No large baseline imbalance is apparent from these baseline comparability checks; however, a single run "
            "does not establish demographic equivalence. Confirm balance across seeds and with prespecified tests."
        )
    return f"En esta ejecución, {' and '.join(evidence)}. {conclusion}"


def _render_demographic_comparability(
    validation: Mapping[str, Any],
    cohort: Mapping[str, Any] | None = None,
) -> str:
    demographics = _demographic_payload(validation)
    if not demographics:
        return (
            '<p class="empty">Demographic comparison was not persisted in the validation artifact. '
            'Age and sex comparability cannot be assessed from this report.</p>'
            + _scientific_note(
                "Las diferencias en tasas clínicas no deben interpretarse como efectos del generador hasta disponer de las distribuciones basales de edad y sexo."
            )
        )

    cohort = cohort or {}
    min_age, max_age = _cohort_age_limits(cohort)
    age_summary = _first_mapping(demographics.get("age_summary"), demographics.get("age"))
    age_groups = _rows(demographics.get("age_groups") or demographics.get("age_distribution"))
    sex_rows = _rows(demographics.get("sex_distribution") or demographics.get("sex"))

    sections: list[str] = []
    summary_metrics = (
        ("mean_age", "Media"),
        ("median_age", "Mediana"),
        ("std_age", "Desviación estándar"),
        ("p25_age", "Percentil 25"),
        ("p75_age", "Percentil 75"),
        ("min_age", "Mínimo"),
        ("max_age", "Máximo"),
    )
    if age_summary:
        rows: list[str] = []
        for metric_key, label in summary_metrics:
            s_value, p_value = _age_statistic_values(age_summary, metric_key)
            if s_value is None and p_value is None:
                continue
            delta = "N/A"
            try:
                delta = f"{float(p_value) - float(s_value):+.2f} años"
            except (TypeError, ValueError):
                pass
            rows.append(
                f'<tr><td>{escape(label)}</td><td>{escape(_format_decimal(s_value, 2))}</td>'
                f'<td>{escape(_format_decimal(p_value, 2))}</td><td>{escape(delta)}</td></tr>'
            )
        if rows:
            sections.append(
                '<h3>Resumen de edad</h3><table><thead><tr><th>Estadístico</th><th>Synthea</th>'
                '<th>Psynthea</th><th>Diferencia absoluta</th></tr></thead><tbody>'
                + ''.join(rows) + '</tbody></table>'
            )

    rendered_age_rows: list[str] = []
    for row in age_groups:
        s_n = _value_for_engine(row, "synthea", "count")
        p_n = _value_for_engine(row, "psynthea", "count")
        s_pct = _value_for_engine(row, "synthea", "proportion")
        p_pct = _value_for_engine(row, "psynthea", "proportion")
        try:
            total = int(s_n or 0) + int(p_n or 0)
        except (TypeError, ValueError):
            total = 1
        raw_label = row.get("label") or row.get("group") or row.get("category") or row.get("age_group") or row.get("age_band")
        label = _adapt_age_band_label(raw_label, min_age=min_age, max_age=max_age)
        if not label or total == 0:
            continue
        rendered_age_rows.append(
            f'<tr><td>{escape(label)}</td>'
            f'<td>{escape(_format_integer(s_n))} ({escape(_format_percent(s_pct))})</td>'
            f'<td>{escape(_format_integer(p_n))} ({escape(_format_percent(p_pct))})</td>'
            f'<td>{escape(_percent_points(s_pct, p_pct))}</td></tr>'
        )
    if rendered_age_rows:
        sections.append(
            '<h3>Distribución por grupos de edad</h3><table><thead><tr><th>Grupo de edad</th>'
            '<th>Synthea n (%)</th><th>Psynthea n (%)</th><th>Diferencia</th></tr></thead><tbody>'
            + ''.join(rendered_age_rows) + '</tbody></table>'
        )

    if sex_rows:
        rows = []
        for row in sex_rows:
            label = row.get("label") or row.get("sex") or row.get("category") or "No especificado"
            label = {"Male": "Hombre", "Female": "Mujer", "Unknown": "Desconocido"}.get(str(label), str(label))
            s_n = _value_for_engine(row, "synthea", "count")
            p_n = _value_for_engine(row, "psynthea", "count")
            s_pct = _value_for_engine(row, "synthea", "proportion")
            p_pct = _value_for_engine(row, "psynthea", "proportion")
            rows.append(
                f'<tr><td>{escape(str(label))}</td>'
                f'<td>{escape(_format_integer(s_n))} ({escape(_format_percent(s_pct))})</td>'
                f'<td>{escape(_format_integer(p_n))} ({escape(_format_percent(p_pct))})</td>'
                f'<td>{escape(_percent_points(s_pct, p_pct))}</td></tr>'
            )
        sections.append(
            '<h3>Distribución por sexo</h3><table><thead><tr><th>Categoría de sexo</th>'
            '<th>Synthea n (%)</th><th>Psynthea n (%)</th><th>Diferencia</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table>'
        )

    if not sections:
        sections.append('<p class="empty">El artefacto demográfico no contenía tablas de edad o sexo representables.</p>')
    sections.append(_scientific_note(_demographic_interpretation(age_summary, sex_rows)))
    return ''.join(sections)


def _format_decimal(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(number):
        return "N/A"
    return f"{number:.{digits}f}"


def _format_integer(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "N/A"

def _render_temporal_epidemiology(validation: Mapping[str, Any], cohort: Mapping[str, Any]) -> str:
    epidemiology = _epidemiology_payload(validation)
    start = cohort.get("observation_start_date") or epidemiology.get("observation_start")
    end = cohort.get("observation_end_date") or epidemiology.get("observation_end")
    window = (
        f'<div class="window-banner"><span><strong>Inicio</strong><br>{escape(_fmt(start))}</span>'
        f'<span><strong>Fin</strong><br>{escape(_fmt(end))}</span>'
        '<span><strong>Convención de límites</strong><br>Inclusivos</span></div>'
    )
    if not epidemiology:
        return window + (
            '<p class="empty">Observation-window epidemiology was not persisted in the validation artifact. '
            'Period prevalence and cumulative incidence are therefore not reported.</p>'
        )

    aggregate = _first_mapping(epidemiology.get("aggregate"), epidemiology.get("summary"), epidemiology)
    metrics = ("eligible_patients", "prevalent_patients", "incident_patients")
    rows: list[str] = []
    for metric in metrics:
        s_value = _value_for_engine(aggregate, "synthea", metric)
        p_value = _value_for_engine(aggregate, "psynthea", metric)
        if s_value is None and p_value is None:
            continue
        delta, _ = _relative_difference_display(s_value, p_value)
        rows.append(
            f'<tr><td>{escape(_humanize(metric))}</td><td>{escape(_fmt(s_value))}</td>'
            f'<td>{escape(_fmt(p_value))}</td><td>{escape(delta)}</td></tr>'
        )
    output = [window]
    if rows:
        output.append(
            '<table><thead><tr><th>Métrica poblacional</th><th>Synthea</th><th>Psynthea</th>'
            '<th>Diferencia relativa</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        )

    diseases = _rows(epidemiology.get("diseases") or epidemiology.get("disease_epidemiology"))
    if diseases:
        summary_rows: list[str] = []
        detail_blocks: list[str] = []
        for disease in diseases:
            code = disease.get("code") or disease.get("CODE") or "No especificado"
            label = disease.get("description") or disease.get("label") or code
            s_prev = _value_for_engine(disease, "synthea", "period_prevalence")
            p_prev = _value_for_engine(disease, "psynthea", "period_prevalence")
            s_inc = _value_for_engine(disease, "synthea", "cumulative_incidence")
            p_inc = _value_for_engine(disease, "psynthea", "cumulative_incidence")
            summary_rows.append(
                f'<tr><td><code>{escape(str(code))}</code></td><td>{escape(str(label))}</td>'
                f'<td>{escape(_format_percent(s_prev))}</td><td>{escape(_format_percent(p_prev))}</td>'
                f'<td>{escape(_percent_points(s_prev, p_prev))}</td>'
                f'<td>{escape(_format_percent(s_inc))}</td><td>{escape(_format_percent(p_inc))}</td>'
                f'<td>{escape(_percent_points(s_inc, p_inc))}</td></tr>'
            )
            detail_rows = []
            for metric in ("eligible_patients", "at_risk_patients", "prevalent_patients", "incident_patients", "mean_incident_onset_age", "median_incident_onset_age", "min_incident_onset_age", "max_incident_onset_age"):
                s_value = _value_for_engine(disease, "synthea", metric)
                p_value = _value_for_engine(disease, "psynthea", metric)
                if s_value is None and p_value is None:
                    continue
                detail_rows.append(
                    f'<tr><td>{escape(_humanize(metric))}</td><td>{escape(_fmt(s_value))}</td><td>{escape(_fmt(p_value))}</td></tr>'
                )
            if detail_rows:
                detail_blocks.append(
                    f'<details><summary>{escape(str(label))} ({escape(str(code))}): denominadores y edad de inicio</summary>'
                    '<table><thead><tr><th>Métrica</th><th>Synthea</th><th>Psynthea</th></tr></thead><tbody>'
                    + ''.join(detail_rows) + '</tbody></table></details>'
                )
        output.append(
            '<h3>Epidemiología específica por enfermedad</h3><div class="table-scroll"><table><thead><tr>'
            '<th>Código</th><th>Enfermedad</th><th>Prev. Synthea</th><th>Prev. Psynthea</th><th>Δ prevalencia</th>'
            '<th>Inc. Synthea</th><th>Inc. Psynthea</th><th>Δ incidencia</th></tr></thead><tbody>'
            + ''.join(summary_rows) + '</tbody></table></div>' + ''.join(detail_blocks)
        )
    output.append(_scientific_note(
        "Period prevalence uses the eligible population; cumulative incidence uses the disease-specific population at risk. Diferencias must be interpreted with their denominators and observation window, not as raw event-count discrepancies."
    ))
    return ''.join(output)


def _render_reproducibility(payload: Mapping[str, Any]) -> str:
    provenance = _mapping(payload.get("execution_provenance"))
    observed = _mapping_sequence(provenance.get("persisted_execution_commands"))
    configured = _mapping_sequence(provenance.get("configured_simulators"))
    parts: list[str] = []
    if observed:
        command_text = json.dumps(_plain_value(observed), indent=2, ensure_ascii=False)
        parts.append('<details><summary>Comando(s) exacto(s) de ejecución persistido(s)</summary><pre>' + escape(command_text) + '</pre></details>')
    elif configured:
        command_text = json.dumps(_plain_value(configured), indent=2, ensure_ascii=False)
        parts.append(
            '<details><summary>Contratos configurados de lanzamiento de simuladores</summary><p class="muted">'
            'La ejecución no persistió la línea de comandos completamente resuelta; se muestran contratos de configuración, no comandos que se afirme que fueron ejecutados exactamente.</p><pre>'
            + escape(command_text) + '</pre></details>'
        )
    return ''.join(parts)


def _observation_window_label(cohort: Mapping[str, Any]) -> str:
    start = cohort.get("observation_start_date")
    end = cohort.get("observation_end_date")
    if start is None and end is None:
        return "Not configured"
    if start is None or end is None:
        return "Incomplete configuration"
    return f"{start} – {end}"

def _render_html(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("executive_summary"))
    results = _mapping(payload.get("scientific_results"))
    validation = _mapping(results.get("validation"))
    knowledge = _mapping(results.get("knowledge"))
    root = _mapping(results.get("root_cause"))
    cohort = _mapping(payload.get("cohort"))
    decision = str(payload.get("decision") or "INCOMPLETE").upper()
    discrepancies = _scientific_discrepancies(validation, knowledge)
    module_names = [str(value) for value in _sequence(cohort.get("modules"))]
    module_label = _module_scope_label(cohort)
    module_details = _module_selection_details(cohort)
    verdict = _replacement_verdict(decision, knowledge, discrepancies)
    scientific_verdict = _scientific_verdict_label(decision, discrepancies)
    narrative = ScientificNarrativeFormatter(
        decision=decision,
        module_label=module_label,
        knowledge=knowledge,
        root_cause=root,
        discrepancies=discrepancies,
    )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(str(payload.get('experiment_name') or 'Scientific validation report'))}</title>
<style>
:root{{--ink:#172033;--muted:#657187;--line:#dbe2ea;--paper:#fff;--canvas:#f4f6f8;--navy:#183b63;--blue:#286da8;--green:#18734a;--amber:#9a5c00;--red:#a62b39;--soft-green:#edf8f2;--soft-amber:#fff7e8;--soft-red:#fff1f3;--soft-blue:#eef6fd;--soft:#f7f9fb}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.62 Georgia,"Times New Roman",serif}}main{{max-width:1080px;margin:auto;padding:30px 22px 76px}}header,.paper-section{{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:32px 36px;margin-bottom:22px;box-shadow:0 2px 9px rgba(22,40,65,.035)}}h1,h2,h3,.eyebrow,.label,.badge,nav,.value,.verdict-value,.answer,summary,th{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}h1{{font-size:2.15rem;line-height:1.16;margin:4px 0 8px}}h2{{font-size:1.42rem;color:var(--navy);margin:0 0 19px}}h3{{font-size:1.04rem;margin:21px 0 9px}}p{{margin:9px 0}}.eyebrow,.label{{font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}.eyebrow{{color:var(--blue)}}.muted{{color:var(--muted)}}.verdict-grid{{display:grid;grid-template-columns:minmax(220px,.58fr) 1.95fr;gap:20px;margin-top:23px}}.verdict-box{{padding:24px;border-radius:10px;background:{_decision_background(decision)};border:1px solid {_decision_border(decision)}}}.verdict-value{{font-size:2.2rem;font-weight:900;color:{_decision_color(decision)};margin:3px 0}}.answer{{font-size:1.08rem;font-weight:850;line-height:1.35}}.abstract{{border-left:5px solid {_decision_color(decision)};padding:18px 22px;background:#fafbfd;border-radius:8px}}.abstract p{{margin:7px 0}}.cards,.summary-grid,.figure-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}.card,.finding-panel,.method-box,.discussion-block{{border:1px solid var(--line);border-radius:9px;padding:15px;background:#fbfcfe}}.value{{display:block;font-size:1.08rem;font-weight:850;margin-top:3px;overflow-wrap:anywhere}}nav{{margin-top:22px;padding-top:17px;border-top:1px solid var(--line)}}nav a{{color:var(--blue);text-decoration:none;font-weight:700;margin:4px 18px 4px 0;display:inline-block}}table{{width:100%;border-collapse:collapse;font-size:.91rem}}th,td{{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{background:#f5f8fb;color:var(--navy);font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}}.badge{{display:inline-block;border-radius:999px;padding:3px 9px;font-size:.7rem;font-weight:850;text-transform:uppercase}}.badge-pass,.badge-ready,.badge-succeeded,.badge-performed{{background:var(--soft-green);color:var(--green)}}.badge-review,.badge-warning,.badge-high,.badge-partially-comparable,.badge-plausible,.badge-low-count{{background:var(--soft-amber);color:var(--amber)}}.badge-fail,.badge-failed,.badge-critical,.badge-blocking,.badge-urgent,.badge-not-demonstrated{{background:var(--soft-red);color:var(--red)}}.badge-inconclusive,.badge-incomplete,.badge-unknown,.badge-not-evaluated,.badge-not-informative,.badge-not-assessable,.badge-out-of-scope,.badge-unverified,.badge-not-testable{{background:#eef1f5;color:#566273}}.delta-review{{color:var(--red);font-weight:850}}.delta-acceptable{{color:var(--green);font-weight:850}}.delta-neutral{{color:var(--muted);font-weight:850}}.evidence-profile{{display:grid;gap:10px;margin:13px 0 4px}}.evidence-row{{display:grid;grid-template-columns:minmax(155px,.75fr) 2fr minmax(90px,.45fr);gap:13px;align-items:center}}.evidence-track{{height:9px;background:#e7ebf0;border-radius:99px;overflow:hidden}}.evidence-fill{{height:100%;border-radius:99px;background:#7c8898}}.evidence-fill.pass{{background:var(--green)}}.evidence-fill.partial,.evidence-fill.review{{background:var(--amber)}}.evidence-fill.fail,.evidence-fill.incomplete{{background:var(--red)}}.evidence-label{{font-family:Inter,ui-sans-serif,system-ui,sans-serif;font-size:.85rem;font-weight:750}}.evidence-state{{font-family:Inter,ui-sans-serif,system-ui,sans-serif;font-size:.8rem;color:var(--muted);text-align:right}}.finding{{border:1px solid var(--line);border-left:5px solid var(--red);border-radius:10px;padding:18px;margin:14px 0;background:#fff}}.finding h3{{margin:7px 0 12px}}.finding-grid{{display:grid;grid-template-columns:1fr 1fr;gap:11px}}.finding-wide{{grid-column:1/-1}}.stat-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;margin-top:8px}}.stat-item{{padding:9px 11px;background:var(--soft);border-radius:7px}}.callout{{background:var(--soft-blue);border-left:4px solid var(--blue);padding:15px 18px;border-radius:7px}}details{{border:1px solid var(--line);border-radius:8px;padding:12px 15px;margin:10px 0;background:#fff}}summary{{cursor:pointer;font-weight:780;color:var(--navy)}}.chart{{border:1px solid var(--line);border-radius:9px;padding:12px;background:#fff;overflow-x:auto}}.chart svg{{width:100%;height:auto;min-width:520px}}.table-scroll{{overflow-x:auto}}.window-banner{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0 18px}}.window-banner span{{background:var(--soft-blue);border:1px solid #d7e8f8;border-radius:8px;padding:12px 14px;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}.scientific-note{{margin-top:16px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#101827;color:#e7edf5;padding:15px;border-radius:8px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.matrix-pass td.status{{background:var(--soft-green)}}.matrix-review td.status,.matrix-low-count td.status{{background:var(--soft-amber)}}.matrix-fail td.status{{background:var(--soft-red)}}.recommendation{{display:grid;grid-template-columns:40px 1fr;gap:13px;padding:16px 0;border-bottom:1px solid var(--line)}}.rank{{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:var(--navy);color:#fff;font:850 .9rem Inter,ui-sans-serif,system-ui,sans-serif}}ul{{padding-left:21px}}.empty{{color:var(--muted);font-style:italic}}.footer{{text-align:center;color:var(--muted);font:normal .8rem Inter,ui-sans-serif,system-ui,sans-serif;margin-top:20px}}@media(max-width:760px){{.verdict-grid,.finding-grid,.evidence-row{{grid-template-columns:1fr}}header,.paper-section{{padding:22px}}.finding-wide{{grid-column:auto}}.evidence-state{{text-align:left}}}}@media print{{body{{background:#fff}}main{{max-width:none;padding:0}}header,.paper-section{{box-shadow:none;break-inside:avoid}}nav{{display:none}}details{{break-inside:avoid}}}}
</style>
</head>
<body><main>
<header id="top">
<div class="eyebrow">Validación científica de Psynthea</div>
<h1>{escape(str(payload.get('experiment_name') or payload.get('experiment_id') or 'Experiment'))}</h1>
<p class="muted">Informe de equivalencia orientado a publicación · schema {_REPORT_SCHEMA_VERSION}</p>
<div class="verdict-grid">
<div class="verdict-box"><span class="label">Conclusión científica</span><div class="verdict-value">{escape(scientific_verdict)}</div><div class="answer">{escape(verdict)}</div><p class="muted">Decisión del pipeline: {escape(decision)} · Ámbito evaluado: {escape(module_label)}</p></div>
<div class="abstract"><span class="label">Resumen estructurado</span>{narrative.abstract()}</div>
</div>
<h3>Perfil de evidencia</h3>{_overall_evidence(summary, validation, knowledge, root)}
<h3>Resumen del experimento</h3>
<div class="summary-grid" style="margin-top:15px">
{_metric_card('Tamaño de cohorte', cohort.get('population_size'))}
{_metric_card('Semilla aleatoria', cohort.get('seed'))}
{_metric_card('Fecha de referencia', cohort.get('reference_date'))}
{_metric_card('Ventana observacional', _observation_window_label(cohort))}
{_metric_card('Rango de edad', _age_range_label(cohort))}
{_metric_card('Módulos evaluados', module_label)}
{_metric_card('Motores de simulación', 'Synthea / Psynthea')}
{_metric_card('Variables significativas tras FDR', _mapping(summary.get('validation')).get('significant_after_fdr_count'))}
</div>
{module_details}
<nav><a href="#methods">Métodos</a><a href="#demographics">Demografía</a><a href="#epidemiology">Epidemiología</a><a href="#results">Resultados</a><a href="#discussion">Discusión</a><a href="#actions">Recomendaciones</a><a href="#appendix">Anexo</a></nav>
</header>
<section class="paper-section" id="methods"><h2>1. Métodos</h2>{_methods_and_scope(payload, validation, knowledge)}{_render_reproducibility(payload)}</section>
<section class="paper-section" id="demographics"><h2>2. Comparabilidad demográfica basal</h2>{_render_demographic_comparability(validation, cohort)}</section>
<section class="paper-section" id="epidemiology"><h2>3. Epidemiología en la ventana observacional</h2>{_render_temporal_epidemiology(validation, cohort)}</section>
<section class="paper-section" id="results"><h2>4. Resultados de validación</h2>{_largest_discrepancy_summary(validation, discrepancies)}<h3>Resultados a nivel de cohorte</h3>{_cohort_bar_chart(validation)}{_cohort_comparison_v13(validation)}<h3>Concordancia por dominio</h3>{_domain_concordance_matrix(validation, discrepancies)}<h3>Hallazgos principales</h3>{_render_discrepancies(discrepancies, narrative)}<h3>Síntesis estadística</h3>{_statistical_evidence_v13(validation, discrepancies)}</section>
<section class="paper-section" id="discussion"><h2>5. Discusión</h2>{_discussion_sections(narrative, root, discrepancies)}{_limitations_v13(knowledge, root, discrepancies)}</section>
<section class="paper-section" id="actions"><h2>6. Recomendaciones y preparación para uso en investigación</h2>{_recommendations_v13(knowledge, discrepancies)}{_research_readiness(decision, summary, knowledge, discrepancies)}</section>
<section class="paper-section" id="appendix"><h2>7. Anexo científico</h2>{_validation_scope_summary(knowledge)}{_technical_appendix(payload, validation, knowledge, root)}</section>
<div class="footer">Generado de forma determinista a partir de los artefactos persistidos de Validación, Conocimiento y Análisis de Causa Raíz. La etapa de informe presenta la evidencia y no recalcula los resultados científicos.</div>
</main></body></html>"""
    return _localize_report_html_es(html)


def _localize_report_html_es(html: str) -> str:
    """Localize every researcher-facing HTML text node to Spanish.

    Reproducibility payloads inside ``pre``/``code`` and CSS/JavaScript blocks
    remain verbatim. The transformation is deterministic and does not modify
    scientific values, identifiers, attributes or persisted evidence.
    """

    import re

    exact = {
        "Hypertension equivalence: Synthea vs psynthea": "Equivalencia de hipertensión: Synthea frente a Psynthea",
        "Scientific validation report": "Informe de validación científica",
        "Experiment": "Experimento",
        "REVIEW REQUIRED": "REVISIÓN NECESARIA",
        "PASS": "APROBADO",
        "FAIL": "NO APROBADO",
        "INCOMPLETE": "INCOMPLETO",
        "NOT COMPARABLE": "NO COMPARABLE",
        "Psynthea cannot yet replace Synthea for the evaluated scope": "Psynthea todavía no puede sustituir a Synthea en el ámbito evaluado",
        "Objective.": "Objetivo.",
        "Methods.": "Métodos.",
        "Results.": "Resultados.",
        "Conclusion.": "Conclusión.",
        "Functional evidence": "Evidencia funcional",
        "Statistical evidence": "Evidencia estadística",
        "Clinical and knowledge evidence": "Evidencia clínica y de conocimiento",
        "Causal evidence": "Evidencia causal",
        "Pass": "Aprobado",
        "Fail": "No aprobado",
        "Inconclusive": "No concluyente",
        "Review": "Revisión",
        "Design": "Diseño",
        "Cohort": "Cohorte",
        "Population:": "Población:",
        "Seed:": "Semilla:",
        "Modules:": "Módulos:",
        "Decision principle": "Principio de decisión",
        "Scientific interpretation.": "Interpretación científica.",
        "Largest ranked discrepancy.": "Mayor discrepancia priorizada.",
        "Clinical output": "Resultado clínico",
        "Scientific screening": "Evaluación científica",
        "review": "revisión",
        "performed": "realizada",
        "pass": "aprobado",
        "not informative": "no informativo",
        "not evaluated": "no evaluado",
        "N/A": "No disponible",
        "Domain": "Dominio",
        "Output completeness": "Completitud de resultados",
        "Volume": "Volumen",
        "Clinical concordance": "Concordancia clínica",
        "Overall": "Global",
        "high": "alta",
        "blocking": "bloqueante",
        "Observation": "Observación",
        "Interpretation": "Interpretación",
        "Scientific implication": "Implicación científica",
        "Statistical details": "Detalles estadísticos",
        "Jaccard index": "Índice de Jaccard",
        "Overlap coefficient": "Coeficiente de solapamiento",
        "Jensen–Shannon divergence": "Divergencia de Jensen–Shannon",
        "Risk ratio": "Riesgo relativo",
        "FDR-adjusted p-value": "Valor p ajustado por FDR",
        "95% confidence interval": "Intervalo de confianza del 95 %",
        "Synthea prevalence": "Prevalencia en Synthea",
        "Psynthea prevalence": "Prevalencia en Psynthea",
        "Evidence provenance": "Procedencia de la evidencia",
        "Additional scientific findings (3)": "Hallazgos científicos adicionales (3)",
        "Population prevalence profile": "Perfil de prevalencia poblacional",
        "Modules tested": "Módulos evaluados",
        "Nominally significant": "Significativos nominalmente",
        "Significant after FDR": "Significativos tras FDR",
        "Warnings": "Advertencias",
        "Module": "Módulo",
        "Statistical status": "Estado estadístico",
        "Nominal": "Nominal",
        "After FDR": "Tras FDR",
        "Comparison": "Comparación",
        "comparable": "comparable",
        "Risk-ratio forest plot": "Diagrama de bosque de riesgos relativos",
        "Overall interpretation": "Interpretación global",
        "Global interpretation": "Interpretación global",
        "Clinical implications": "Implicaciones clínicas",
        "Methodological implications": "Implicaciones metodológicas",
        "Causal interpretation": "Interpretación causal",
        "Leading hypothesis": "Hipótesis principal",
        "Evidence supporting this hypothesis": "Evidencia que respalda esta hipótesis",
        "Current confidence": "Confianza actual",
        "Required verification": "Verificación necesaria",
        "Future work": "Trabajo futuro",
        "Limitations": "Limitaciones",
        "Outstanding research questions": "Preguntas de investigación pendientes",
        "Problem.": "Problema.",
        "Likely mechanism.": "Mecanismo probable.",
        "Required action.": "Acción necesaria.",
        "Success criterion.": "Criterio de éxito.",
        "Current status": "Estado actual",
        "Not research ready": "No apto todavía para uso en investigación",
        "Blocking ranked discrepancies": "Discrepancias bloqueantes priorizadas",
        "Knowledge blocking findings": "Hallazgos bloqueantes de conocimiento",
        "Next validation": "Siguiente validación",
        "Required": "Necesaria",
        "Requirements before research use": "Requisitos previos al uso en investigación",
        "Validation coverage": "Cobertura de validación",
        "Actionability": "Capacidad de actuación",
        "Clinical": "Clínica",
        "Epidemiological": "Epidemiológica",
        "Spanish-context": "Contexto español",
        "Statistical": "Estadística",
        "Structural": "Estructural",
        "Reproducibility and provenance": "Reproducibilidad y procedencia",
        "Pipeline stages completed": "Etapas del pipeline completadas",
        "Hashed source artifacts": "Artefactos fuente con hash",
        "Report schema": "Esquema del informe",
        "Generated at": "Generado el",
        "Machine-readable evidence.": "Evidencia legible por máquina.",
        "Pipeline execution": "Ejecución del pipeline",
        "Stage": "Etapa",
        "Status": "Estado",
        "Summary": "Resumen",
        "Error": "Error",
        "6. Recomendaciones and research readiness": "6. Recomendaciones y preparación para uso en investigación",
        "Conditions": "Condiciones",
        "Encounters": "Encuentros",
        "Medications": "Medicaciones",
        "Observations": "Observaciones",
        "Patients": "Pacientes",
        "Procedures": "Procedimientos",
    }

    static_phrases = {
        "Bar length represents evidence status, not a probability or newly calculated confidence score.": "La longitud de la barra representa el estado de la evidencia, no una probabilidad ni una puntuación de confianza calculada de nuevo.",
        "Deterministic comparison of persisted Synthea and Psynthea cohorts using functional, statistical, clinical-knowledge and root-cause evidence.": "Comparación determinista de cohortes persistidas de Synthea y Psynthea mediante evidencia funcional, estadística, clínico-semántica y de análisis de causa raíz.",
        "Equivalence requires complete outputs, acceptable effect magnitude, clinically concordant content and no unresolved blocking evidence.": "La equivalencia exige resultados completos, una magnitud de efecto aceptable, contenido clínicamente concordante y ausencia de evidencia bloqueante no resuelta.",
        "The report consolidates upstream results and does not recalculate tests, acquire external references or infer new causal mechanisms.": "El informe consolida los resultados previos y no recalcula pruebas, no incorpora referencias externas ni infiere nuevos mecanismos causales.",
        "Persisted cohorts were compared using deterministic functional checks, multiplicity-adjusted statistical evidence, clinical and epidemiological interpretation, and hypothesis-generating root-cause analysis.": "Las cohortes persistidas se compararon mediante comprobaciones funcionales deterministas, evidencia estadística ajustada por multiplicidad, interpretación clínica y epidemiológica y análisis de causa raíz orientado a generar hipótesis.",
        "Scientific equivalence was not demonstrated. Psynthea should not replace Synthea for downstream research in the evaluated scope until blocking discrepancies are resolved and independently reproduced.": "No se demostró equivalencia científica. Psynthea no debe sustituir a Synthea en investigaciones posteriores dentro del ámbito evaluado hasta que se resuelvan las discrepancias bloqueantes y se reproduzcan de forma independiente.",
        "Period prevalence uses the eligible population; cumulative incidence uses the disease-specific population at risk. Differences must be interpreted with their denominators and observation window, not as raw event-count discrepancies.": "La prevalencia de periodo utiliza la población elegible; la incidencia acumulada utiliza la población específica en riesgo para cada enfermedad. Las diferencias deben interpretarse junto con sus denominadores y su ventana observacional, no como discrepancias brutas en el número de eventos.",
        "Colour represents the scientific screening status, not the mathematical sign of the difference. Low-count comparisons are shown in amber because relative percentages are unstable at small denominators; they are not promoted to material scientific discrepancies unless the low-count review threshold is met.": "El color representa el estado de la evaluación científica, no el signo matemático de la diferencia. Las comparaciones con recuentos bajos se muestran en ámbar porque los porcentajes relativos son inestables con denominadores pequeños; no se consideran discrepancias científicas materiales salvo que alcancen el umbral predefinido de revisión por bajo recuento.",
        "The magnitude of the between-generator difference exceeded the configured materiality threshold and is inconsistent with equivalent event-generation behaviour.": "La magnitud de la diferencia entre generadores superó el umbral de materialidad configurado y no es compatible con un comportamiento equivalente de generación de eventos.",
        "Downstream estimates may differ by generator; replacement is not scientifically justified until this discrepancy is resolved.": "Las estimaciones posteriores pueden variar según el generador; la sustitución no está científicamente justificada hasta que se resuelva esta discrepancia.",
        "Values are rounded for readability; full precision remains in the source artifacts. JSD ranges from 0 (identical distributions) toward 1 (greater divergence).": "Los valores se redondean para facilitar la lectura; la precisión completa permanece en los artefactos fuente. La JSD varía desde 0 (distribuciones idénticas) hacia 1 (mayor divergencia).",
        "This finding is supported by persisted functional or knowledge-layer evidence; no endpoint-level statistical estimate was extracted.": "Este hallazgo está respaldado por evidencia funcional o de la capa de conocimiento persistida; no se extrajo una estimación estadística específica del desenlace.",
        "The generators do not represent sufficiently comparable clinical concepts or concept-frequency distributions for this domain.": "Los generadores no representan conceptos clínicos ni distribuciones de frecuencia conceptual suficientemente comparables en este dominio.",
        "Phenotyping, monitoring and outcome analyses based on observations may yield materially different results.": "Los análisis de fenotipado, monitorización y resultados basados en observaciones pueden producir resultados materialmente diferentes.",
        "The population-level clinical burden is not reproduced within the evaluated equivalence criteria.": "La carga clínica a nivel poblacional no se reproduce dentro de los criterios de equivalencia evaluados.",
        "Values are rounded for readability; full precision remains in the source artifacts.": "Los valores se redondean para facilitar la lectura; la precisión completa permanece en los artefactos fuente.",
        "Findings are ordered by scientific priority. Internal ranking scores remain available only in the machine-readable report.": "Los hallazgos se ordenan por prioridad científica. Las puntuaciones internas de priorización solo permanecen disponibles en el informe legible por máquina.",
        "Statistical significance alone does not establish equivalence. Functional completeness, effect magnitude, clinical concordance and multiplicity-adjusted evidence are considered together.": "La significación estadística por sí sola no demuestra equivalencia. Se consideran conjuntamente la completitud funcional, la magnitud del efecto, la concordancia clínica y la evidencia ajustada por multiplicidad.",
        "Multiple independent evidence layers converge on the same conclusion: the observed differences are not adequately explained by a single minor fluctuation and instead indicate non-equivalent generator behaviour within the evaluated scope.": "Múltiples capas independientes de evidencia convergen en la misma conclusión: las diferencias observadas no se explican adecuadamente por una única fluctuación menor y apuntan a un comportamiento no equivalente de los generadores dentro del ámbito evaluado.",
        "Agreement in cohort size or successful pipeline execution must not be interpreted as scientific equivalence. Replacement requires concordant output retention, event volumes, clinical semantics and endpoint-level evidence after multiplicity adjustment.": "La concordancia en el tamaño de cohorte o la ejecución satisfactoria del pipeline no deben interpretarse como equivalencia científica. La sustitución exige concordancia en la retención de resultados, los volúmenes de eventos, la semántica clínica y la evidencia por desenlace tras el ajuste por multiplicidad.",
        "The leading hypothesis concerns configuration, but the available evidence does not yet establish a causal mechanism.": "La hipótesis principal se relaciona con la configuración, pero la evidencia disponible todavía no establece un mecanismo causal.",
        "The persisted root-cause artifact links 1 supporting finding(s) to this hypothesis.": "El artefacto persistido de causa raíz vincula un hallazgo de apoyo con esta hipótesis.",
        "None; causal status: inconclusive.": "Ninguna; estado causal: no concluyente.",
        "Deterministic verification has not yet been performed. Patient-level traces and controlled counterfactual reruns are required before causal attribution.": "Todavía no se ha realizado una verificación determinista. Se requieren trazas a nivel de paciente y nuevas ejecuciones contrafactuales controladas antes de atribuir causalidad.",
        "Future validation should prioritise patient-level trace comparison, deterministic verification of the leading causal hypothesis, replication across independent seeds and cohort sizes, and confirmation against the predefined module-specific equivalence tolerances.": "La validación futura debe priorizar la comparación de trazas a nivel de paciente, la verificación determinista de la hipótesis causal principal, la replicación con semillas y tamaños de cohorte independientes y la confirmación frente a las tolerancias de equivalencia predefinidas para cada módulo.",
        "This report reflects one configured execution; generalisation requires replication across independent seeds, cohort sizes and reference dates.": "Este informe refleja una única ejecución configurada; la generalización exige replicación con semillas, tamaños de cohorte y fechas de referencia independientes.",
        "No deterministic causal mechanism was confirmed for the observed discrepancies.": "No se confirmó ningún mecanismo causal determinista para las discrepancias observadas.",
        "The leading hypothesis lacks sufficient supporting evidence.": "La hipótesis principal carece de evidencia de apoyo suficiente.",
        "No deterministic verification was available.": "No se dispuso de verificación determinista.",
        "No non-refuted candidate remained after deterministic assessment.": "No quedó ningún candidato no refutado tras la evaluación determinista.",
        "The causal search retained only the highest-priority hypotheses; additional alternatives may remain unexplored.": "La búsqueda causal conservó únicamente las hipótesis de mayor prioridad; pueden quedar alternativas adicionales sin explorar.",
        "No deterministic verification protocol was available for the leading causal hypothesis.": "No se dispuso de un protocolo de verificación determinista para la hipótesis causal principal.",
        "Resolve or justify all blocking discrepancies.": "Resolver o justificar todas las discrepancias bloqueantes.",
        "Repeat the identical seeded cohort after remediation.": "Repetir la misma cohorte con idéntica semilla después de la corrección.",
        "Replicate the experiment across independent seeds and cohort sizes.": "Replicar el experimento con semillas y tamaños de cohorte independientes.",
        "Confirm that all predefined functional and statistical tolerances are met.": "Confirmar que se cumplen todas las tolerancias funcionales y estadísticas predefinidas.",
        "Complete validation, knowledge, root-cause, integrity-hash and pipeline records are retained in the separately hashed JSON artifacts. They are intentionally not reproduced in the research-facing HTML.": "Los registros completos de validación, conocimiento, causa raíz, hashes de integridad y pipeline se conservan en los artefactos JSON con hash independiente. Deliberadamente no se reproducen en el HTML orientado a investigación.",
    }

    domain_es = {
        "conditions": "condiciones",
        "medications": "medicaciones",
        "encounters": "encuentros",
        "observations": "observaciones",
        "procedures": "procedimientos",
        "epidemiological": "epidemiología",
        "epidemiology": "epidemiología",
        "prevalence": "prevalencia",
    }

    def domain(value: str) -> str:
        return domain_es.get(value.casefold(), value)

    def translate_text(value: str) -> str:
        leading = value[: len(value) - len(value.lstrip())]
        trailing = value[len(value.rstrip()) :]
        core = value.strip()
        if not core:
            return value
        if core in exact:
            return leading + exact[core] + trailing
        for source, target in static_phrases.items():
            core = core.replace(source, target)

        core = re.sub(
            r"To determine whether Psynthea reproduces Synthea outputs for (.*?) within the configured functional, statistical and clinical validation scope\.",
            r"Determinar si Psynthea reproduce los resultados de Synthea para \1 dentro del ámbito configurado de validación funcional, estadística y clínica.",
            core,
        )
        core = re.sub(
            r"In this run, mean age differed by ([0-9.]+) years and the largest sex-category difference was ([0-9.]+) percentage points\. No large baseline imbalance is apparent from these baseline comparability checks; however, a single run does not establish demographic equivalence\. Confirm balance across seeds and with prespecified tests\.",
            r"En esta ejecución, la edad media difirió en \1 años y la mayor diferencia entre categorías de sexo fue de \2 puntos porcentuales. Estas comprobaciones de comparabilidad basal no muestran un desequilibrio importante; sin embargo, una única ejecución no demuestra equivalencia demográfica. Debe confirmarse el equilibrio entre semillas mediante pruebas preespecificadas.",
            core,
        )

        def material(match: re.Match[str]) -> str:
            direction = "mayor" if match.group(1).casefold() == "more" else "menor"
            item = domain(match.group(2))
            return f"Psynthea generó un número materialmente {direction} de registros de {item}"

        core = re.sub(r"Psynthea contained materially (more|fewer) ([A-Za-z]+) records", material, core)
        core = re.sub(r"Psynthea emitted materially (more|fewer) ([A-Za-z]+) records than Synthea\.", lambda m: f"Psynthea generó un número materialmente {'mayor' if m.group(1).casefold() == 'more' else 'menor'} de registros de {domain(m.group(2))} que Synthea.", core)
        core = core.replace(" than Synthea", " que Synthea")
        core = core.replace(" versus ", " frente a ")
        core = core.replace("95% CI", "IC del 95 %")
        core = core.replace("FDR-adjusted p", "valor p ajustado por FDR")
        core = core.replace("indicating that equivalence criteria were not met", "lo que indica que no se cumplieron los criterios de equivalencia")

        core = re.sub(r"Clinical coding for ([A-Za-z]+) was not concordant between generators", lambda m: f"La codificación clínica de {domain(m.group(1))} no fue concordante entre generadores", core)
        core = re.sub(r"Clinical coding for ([A-Za-z]+) was not concordant", lambda m: f"La codificación clínica de {domain(m.group(1))} no fue concordante", core)
        core = re.sub(r"Clinical coding evidence for ([A-Za-z]+) was inconclusive", lambda m: f"La evidencia de codificación clínica para {domain(m.group(1))} no fue concluyente", core)
        core = core.replace("shared clinical codes", "códigos clínicos compartidos")
        core = re.sub(r"The prevalence of ([A-Za-z]+) differed between Synthea \((.*?)\) and Psynthea \((.*?)\)\.", lambda m: f"La prevalencia de {domain(m.group(1))} difirió entre Synthea ({m.group(2)}) y Psynthea ({m.group(3)}).", core)
        core = re.sub(r"Prevalence differed for (.+)", r"La prevalencia difirió para \1", core)
        core = re.sub(r"The prevalence of ([A-Za-z]+) differed between Synthea \((.*?)\) and Psynthea \((.*?)\);", lambda m: f"La prevalencia de {domain(m.group(1))} difirió entre Synthea ({m.group(2)}) y Psynthea ({m.group(3)});", core)

        core = re.sub(r"Which module, lifecycle, denominator or exporter difference explains the material ([A-Za-z]+) divergence\?", lambda m: f"¿Qué diferencia de módulo, ciclo de vida, denominador o exportador explica la divergencia material en {domain(m.group(1))}?", core)
        core = re.sub(r"Which generation, coding or mapping difference explains the ([A-Za-z]+) scientific discrepancy\?", lambda m: f"¿Qué diferencia de generación, codificación o mapeo explica la discrepancia científica en {domain(m.group(1))}?", core)
        core = re.sub(r"Review ([A-Za-z]+) generation semantics", lambda m: f"Revisar la semántica de generación de {domain(m.group(1))}", core)
        core = re.sub(r"Resolve ([A-Za-z]+) scientific discrepancy", lambda m: f"Resolver la discrepancia científica de {domain(m.group(1))}", core)
        core = re.sub(r"Inspect the module transitions, lifecycle rules, denominators and exporter behaviour controlling ([A-Za-z]+), prioritising the evidence linked in this report\.", lambda m: f"Inspeccionar las transiciones del módulo, las reglas del ciclo de vida, los denominadores y el comportamiento del exportador que controlan {domain(m.group(1))}, priorizando la evidencia vinculada en este informe.", core)
        core = re.sub(r"Repeat the identical seeded cohort after the fix, inspect patient-level ([A-Za-z]+) traces, then replicate across independent seeds and confirm that the endpoint meets the approved equivalence tolerance\.", lambda m: f"Repetir la misma cohorte con idéntica semilla después de la corrección, inspeccionar las trazas de {domain(m.group(1))} a nivel de paciente y, posteriormente, replicar con semillas independientes y confirmar que el desenlace cumple la tolerancia de equivalencia aprobada.", core)
        core = core.replace("Not yet confirmed; module transitions, lifecycle semantics, denominators or exporter behaviour require investigation.", "Todavía no confirmado; deben investigarse las transiciones del módulo, la semántica del ciclo de vida, los denominadores o el comportamiento del exportador.")
        core = core.replace("Review the persisted clinical finding, its source evidence and the corresponding generation or mapping logic before repeating validation.", "Revisar el hallazgo clínico persistido, su evidencia fuente y la lógica de generación o mapeo correspondiente antes de repetir la validación.")
        core = core.replace("Clinical equivalence for this domain is blocked until the evidence is corrected.", "La equivalencia clínica de este dominio permanece bloqueada hasta que se corrija la evidencia.")
        core = core.replace("Observation-based phenotyping, monitoring and outcome analyses may produce materially different results.", "Los análisis de fenotipado, monitorización y resultados basados en observaciones pueden producir resultados materialmente diferentes.")
        core = core.replace("Population-level disease-burden estimates may be biased or non-comparable.", "Las estimaciones de carga de enfermedad a nivel poblacional pueden estar sesgadas o no ser comparables.")
        core = core.replace("Not yet confirmed; code mapping, concept selection or event-frequency semantics may differ.", "Todavía no confirmado; pueden diferir el mapeo de códigos, la selección de conceptos o la semántica de frecuencia de eventos.")
        core = core.replace("Not yet confirmed; disease incidence, eligibility logic, denominators or code mapping may differ.", "Todavía no confirmado; pueden diferir la incidencia de enfermedad, la lógica de elegibilidad, los denominadores o el mapeo de códigos.")
        core = core.replace("Period prevalence uses the eligible population; cumulative incidence uses the disease-specific population at risk. Diferencias must be interpreted with their denominators and observation window, not as raw event-count discrepancies.", "La prevalencia de periodo utiliza la población elegible; la incidencia acumulada utiliza la población específica en riesgo para cada enfermedad. Las diferencias deben interpretarse junto con sus denominadores y su ventana observacional, no como discrepancias brutas en el número de eventos.")
        core = core.replace("Psynthea contained materially more Cond...", "Psynthea generó más registros de condiciones...")
        core = core.replace("Psynthea contained materially more Medi...", "Psynthea generó más registros de medicaciones...")
        core = re.sub(r"Decisión del pipeline: REVIEW", "Decisión del pipeline: REVISIÓN", core)
        core = re.sub(r"Decisión del pipeline: PASS", "Decisión del pipeline: APROBADO", core)
        core = re.sub(r"Decisión del pipeline: FAIL", "Decisión del pipeline: NO APROBADO", core)

        return leading + core + trailing

    translated_parts: list[str] = []
    protected_depth = 0
    for part in re.split(r"(<[^>]+>)", html):
        if part.startswith("<"):
            lowered = part.casefold()
            if re.match(r"<(pre|code|style|script)(?:\s|>)", lowered):
                protected_depth += 1
            translated_parts.append(part)
            if re.match(r"</(pre|code|style|script)>", lowered):
                protected_depth = max(0, protected_depth - 1)
            continue
        translated_parts.append(part if protected_depth else translate_text(part))
    return "".join(translated_parts)

def _scientific_conclusion_v13(
    decision: str,
    discrepancies: Sequence[Mapping[str, Any]],
    knowledge: Mapping[str, Any],
) -> str:
    modules = _mapping_sequence(knowledge.get("modules"))
    ready_count = sum(bool(module.get("research_use_ready")) for module in modules)

    if decision == "NOT_COMPARABLE":
        return (
            "The reference evidence was incomplete, so scientific equivalence "
            "could not be assessed. Apparent differences involving an empty "
            "reference endpoint are not interpreted as generator discrepancies."
        )
    if decision == "INCOMPLETE":
        return (
            "The experiment did not produce all required upstream products; "
            "therefore no defensible equivalence conclusion can be issued."
        )
    if decision == "PASS" and not discrepancies and ready_count == len(modules):
        return (
            "No scientifically material discrepancy was detected for the evaluated "
            "modules in this configured execution. Equivalence and replacement are "
            "not established without replicated runs and prospectively defined "
            "equivalence margins for the relevant endpoints."
        )

    leading = [str(item.get("short_label")) for item in discrepancies[:4] if item.get("short_label")]
    detail = ": " + "; ".join(leading) if leading else ""
    module_word = "module" if len(modules) == 1 else "modules"
    return (
        "Scientific equivalence between Psynthea and Synthea was not demonstrated"
        f"{detail}. The evaluated {module_word} should not be used for downstream "
        "research until the blocking discrepancies are resolved and reproduced "
        "across independent runs."
    )


def _research_overview_v13(
    summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    root_cause: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    validation_summary = _mapping(summary.get("validation"))
    root_summary = _mapping(summary.get("root_cause"))
    modules = _mapping_sequence(knowledge.get("modules"))
    ready = sum(bool(module.get("research_use_ready")) for module in modules)
    no_material_discrepancy_detected = (
        not discrepancies and ready == len(modules) and bool(modules)
    )

    return f'''<div class="cards">
{_metric_card("Comparison performed", f"{validation_summary.get('comparable_module_count', 0)} / {validation_summary.get('module_count', 0)}")}
{_metric_card("Material discrepancy", "Not detected" if no_material_discrepancy_detected else "Detected or unresolved")}
{_metric_card("Ranked discrepancies", len(discrepancies))}
{_metric_card("Significant after FDR", validation_summary.get("significant_after_fdr_count"))}
{_metric_card("Research-ready modules", f"{ready} / {len(modules)}")}
{_metric_card("Root-cause status", root_summary.get("status") or "unknown")}
</div>
<div class="callout"><strong>Interpretation:</strong> A completed statistical comparison is not equivalent to demonstrated scientific equivalence. The final decision also considers output completeness, effect magnitude, multiplicity-adjusted evidence, clinical interpretation and unresolved causal uncertainty.</div>'''


def _cohort_counts(validation: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    cohorts = _mapping(validation.get("cohorts"))
    if not cohorts:
        cohorts = _mapping(_mapping(validation.get("source")).get("cohorts"))
    return {str(key): _mapping(value) for key, value in cohorts.items()}


def _cohort_domains(validation: Mapping[str, Any]) -> tuple[str, ...]:
    cohorts = _cohort_counts(validation)
    reference = _mapping(cohorts.get("synthea"))
    candidate = _mapping(cohorts.get("psynthea"))
    excluded = {"source", "engine", "generator", "name"}
    return tuple(
        sorted(
            key
            for key in set(reference) | set(candidate)
            if key not in excluded and _is_number(reference.get(key), candidate.get(key))
        )
    )



def _cohort_comparison_v13(validation: Mapping[str, Any]) -> str:
    cohorts = _cohort_counts(validation)
    synthea = _mapping(cohorts.get("synthea"))
    psynthea = _mapping(cohorts.get("psynthea"))
    rows: list[str] = []
    reference_incomplete = _reference_evidence_incomplete(validation)

    for domain in _cohort_domains(validation):
        reference = synthea.get(domain)
        candidate = psynthea.get(domain)
        category = _count_discrepancy_category(reference, candidate)
        if reference_incomplete and category == "candidate_only_output":
            delta = "N/A"
            status = "not assessable"
        else:
            delta, _ = _relative_difference_display(reference, candidate)
            status = _count_difference_status(reference, candidate)
        delta_class = _delta_class_for_status(status)
        rows.append(
            f'<tr><td>{escape(_humanize(domain))}</td>'
            f'<td>{escape(_fmt(reference))}</td><td>{escape(_fmt(candidate))}</td>'
            f'<td class="{delta_class}">{escape(delta)}</td><td>{_badge(status)}</td></tr>'
        )

    if not rows:
        return '<p class="empty">No cohort-level numeric outputs were available.</p>'
    return (
        '<table><thead><tr><th>Clinical output</th><th>Synthea</th><th>Psynthea</th>'
        '<th>Diferencia relativa</th><th>Scientific screening</th></tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table><p class="muted">Colour represents the scientific screening status, not the mathematical sign of the difference. Low-count comparisons are shown in amber because relative percentages are unstable at small denominators; they are not promoted to material scientific discrepancies unless the low-count review threshold is met.</p>'
    )


def _relative_difference_display(reference: Any, candidate: Any) -> tuple[str, str]:
    try:
        baseline = float(reference)
        observed = float(candidate)
    except (TypeError, ValueError):
        return "N/A", ""
    if baseline == 0:
        return ("N/A", "delta-neutral") if observed == 0 else ("Not estimable", "delta-review")
    percentage = ((observed - baseline) / baseline) * 100.0
    css = "delta-neutral" if abs(percentage) < 1e-12 else ("delta-review" if percentage != 0 else "delta-neutral")
    return f"{percentage:+.1f} %", css


def _scientific_discrepancies(
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
) -> list[dict[str, Any]]:
    cohorts = _cohort_counts(validation)
    reference = _mapping(cohorts.get("synthea"))
    candidate = _mapping(cohorts.get("psynthea"))
    findings = _all_knowledge_findings(knowledge)
    discrepancies: list[dict[str, Any]] = []
    reference_incomplete = _reference_evidence_incomplete(validation)

    for domain in _cohort_domains(validation):
        synthea_value = reference.get(domain)
        psynthea_value = candidate.get(domain)
        if not _material_count_difference(synthea_value, psynthea_value):
            continue

        related = _related_findings(findings, domain)
        category = _count_discrepancy_category(synthea_value, psynthea_value)
        if reference_incomplete and category == "candidate_only_output":
            continue
        relative = _relative_difference(synthea_value, psynthea_value)
        severity = _count_severity(category, relative, related)
        score = _scientific_impact_score(
            severity=severity,
            blocking=_has_blocking_evidence(related),
            relative_difference=relative,
            adjusted_significance=_has_adjusted_significance(related),
            evidence_count=len(related),
        )
        discrepancy = {
            "key": domain,
            "domain": domain,
            "category": category,
            "title": _count_title(domain, category),
            "short_label": _count_short_label(domain, category, relative),
            "severity": severity,
            "blocking": category in {"missing_candidate_output", "candidate_only_output"} or _has_blocking_evidence(related),
            "impact": _count_impact(domain, category, synthea_value, psynthea_value, relative),
            "synthea": synthea_value,
            "psynthea": psynthea_value,
            "difference": _relative_difference_display(synthea_value, psynthea_value)[0],
            "tests": _evidence_basis(related, category),
            "evidence": _count_evidence(domain, synthea_value, psynthea_value, relative, related),
            "finding_count": len(related),
            "score": score,
            "related_findings": related,
        }
        discrepancies.append(discrepancy)

    if not reference_incomplete:
        discrepancies.extend(_finding_only_discrepancies(findings, existing=discrepancies))
    discrepancies.sort(key=lambda item: (-float(item.get("score", 0.0)), _severity_rank(item.get("severity")), str(item.get("title"))))
    return discrepancies[:8]


def _all_knowledge_findings(knowledge: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values: list[Mapping[str, Any]] = []
    for module in _mapping_sequence(knowledge.get("modules")):
        report = _mapping(module.get("interpretation_report"))
        values.extend(_mapping_sequence(report.get("findings")))
        values.extend(_mapping_sequence(_mapping(module.get("summary")).get("priority_findings")))
    unique: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        identity = str(item.get("finding_id") or item.get("id") or item.get("rule_id") or json.dumps(_plain_value(item), sort_keys=True))
        if identity not in seen:
            seen.add(identity)
            unique.append(item)
    return unique


def _finding_text(finding: Mapping[str, Any]) -> str:
    return " ".join(str(value) for value in _flatten_scalars(finding)).casefold()


def _related_findings(findings: Sequence[Mapping[str, Any]], domain: str) -> list[Mapping[str, Any]]:
    tokens = {domain.casefold(), domain.rstrip("s").casefold(), f"{domain}_per_patient".casefold()}
    return [finding for finding in findings if any(token and token in _finding_text(finding) for token in tokens)]


def _finding_only_discrepancies(
    findings: Sequence[Mapping[str, Any]],
    *,
    existing: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    existing_text = " ".join(str(item.get("domain") or item.get("key") or "") for item in existing).casefold()
    output: list[dict[str, Any]] = []
    for finding in findings:
        severity = str(finding.get("severity") or "").casefold()
        status = str(finding.get("status") or "").casefold()
        text = _finding_text(finding)
        if severity not in {"critical", "high"} and status not in {"fail", "failed", "blocking"}:
            continue
        if any(token in existing_text for token in _extract_domain_tokens(finding)):
            continue
        title = str(finding.get("title") or finding.get("observation") or finding.get("rule_id") or "Knowledge-layer discrepancy")
        if len(title) > 140:
            title = title[:137].rstrip() + "..."
        score = _scientific_impact_score(
            severity=severity or "high",
            blocking=_finding_is_blocking(finding),
            relative_difference=None,
            adjusted_significance=_has_adjusted_significance((finding,)),
            evidence_count=1,
        )
        output.append({
            "key": str(finding.get("finding_id") or finding.get("id") or title),
            "domain": _first_domain_token(finding),
            "category": "knowledge_finding",
            "title": title,
            "short_label": title.lower(),
            "severity": severity if severity in {"critical", "high", "medium", "low"} else "high",
            "blocking": _finding_is_blocking(finding),
            "impact": str(finding.get("impact") or finding.get("interpretation") or "The Knowledge Engine classified this finding as scientifically material."),
            "synthea": None,
            "psynthea": None,
            "difference": "N/A",
            "tests": _evidence_basis((finding,), "knowledge_finding"),
            "evidence": str(finding.get("observation") or finding.get("interpretation") or "Persisted Knowledge Engine evidence."),
            "finding_count": 1,
            "score": score,
            "related_findings": [finding],
        })
    return output




def _render_discrepancies(
    discrepancies: Sequence[Mapping[str, Any]],
    narrative: ScientificNarrativeFormatter | None = None,
) -> str:
    if not discrepancies:
        return '<p class="empty">No scientifically material discrepancy was identified.</p>'
    if narrative is None:
        narrative = ScientificNarrativeFormatter(
            decision="REVIEW",
            module_label="the evaluated scope",
            knowledge={},
            root_cause={},
            discrepancies=discrepancies,
        )
    visible = discrepancies[:5]
    hidden = discrepancies[5:]
    rendered = "".join(
        _finding_card(item, narrative=narrative) for item in visible
    )
    if hidden:
        rendered += (
            f'<details><summary>Additional scientific findings ({len(hidden)})</summary>'
            + "".join(
                _finding_card(item, narrative=narrative, compact=True)
                for item in hidden
            )
            + '</details>'
        )
    return (
        rendered
        + '<p class="muted">Findings are ordered by scientific priority. '
        'Internal ranking scores remain available only in the machine-readable report.</p>'
    )


def _statistical_evidence_v13(validation: Mapping[str, Any], discrepancies: Sequence[Mapping[str, Any]]) -> str:
    aggregate = _mapping(validation.get("aggregate"))
    modules = _mapping_sequence(validation.get("modules"))
    rows = []
    for module in modules:
        stats = _mapping(module.get("statistical_summary"))
        rows.append(
            f'<tr><td>{escape(_fmt(module.get("module_name")))}</td>'
            f'<td>{_badge(stats.get("validation_status"))}</td>'
            f'<td>{escape(_fmt(stats.get("significant_test_count")))}</td>'
            f'<td>{escape(_fmt(stats.get("significant_after_fdr_count")))}</td>'
            f'<td>{_badge("performed" if stats.get("valid_for_statistical_comparison") else ("not assessable" if str(stats.get("validation_status") or "").casefold() in {"reference_empty", "reference_missing"} else "incomplete"))}</td></tr>'
        )
    table = (
        '<table><thead><tr><th>Module</th><th>Estadísticoal status</th><th>Nominal</th><th>After FDR</th><th>Comparison</th></tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
        if rows
        else '<p class="empty">No module-level statistical summary was available.</p>'
    )
    if len(modules) > 1 and rows:
        table = (
            f'<details><summary>Module-level statistical summary ({len(modules)} modules)</summary>'
            + table
            + '</details>'
        )
    forest = _forest_plot(discrepancies)
    return (
        '<div class="cards">'
        + _metric_card("Modules tested", aggregate.get("module_count"))
        + _metric_card("Nominally significant", aggregate.get("significant_test_count"))
        + _metric_card("Significant after FDR", aggregate.get("significant_after_fdr_count"))
        + _metric_card("Warnings", aggregate.get("warning_count"))
        + '</div>'
        + table
        + forest
        + '<div class="callout"><strong>Interpretation.</strong> Estadísticoal significance alone does not establish equivalence. Functional completeness, effect magnitude, clinical concordance and multiplicity-adjusted evidence are considered together.</div>'
    )


def _validation_scope(knowledge: Mapping[str, Any]) -> str:
    identifiers = _collect_validation_identifiers(knowledge)
    grouped: dict[str, list[str]] = {}
    for identifier in identifiers:
        grouped.setdefault(identifier.split(".", 1)[0], []).append(identifier)
    labels = {
        "ACTION": "Actionability checks", "CLINICAL": "Clinical checks",
        "EPI": "Epidemiological checks", "SPANISH": "Spanish-context checks",
        "STAT": "Estadísticoal checks", "STRUCT": "Structural checks",
    }
    summary = ''.join(
        f'<div class="card"><span class="label">{escape(labels.get(prefix, prefix))}</span><span class="value">{len(values)} evaluated</span></div>'
        for prefix, values in sorted(grouped.items())
    )
    details = ''.join(
        f'<details><summary>{escape(labels.get(prefix, prefix))}: rule identifiers</summary>{_html_list(sorted(values), "")}</details>'
        for prefix, values in sorted(grouped.items())
    )
    return ('<h3>Validation-rule coverage</h3><div class="cards">' + summary + '</div>' + details) if grouped else '<p class="empty">No structured validation-rule identifiers were persisted.</p>'

def _collect_validation_identifiers(value: Any) -> set[str]:
    allowed_prefixes = {"ACTION", "CLINICAL", "EPI", "SPANISH", "STAT", "STRUCT"}
    pattern = re.compile(
        r"^(ACTION|CLINICAL|EPI|SPANISH|STAT|STRUCT)\."
        r"[A-Z0-9_]+(?:\.[A-Z0-9_]+)*$"
    )
    identifiers: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if isinstance(child, str) and str(key).casefold() in {
                    "rule_id", "action_id", "rule", "validation_rule_id"
                }:
                    candidate = child.strip()
                    if candidate.split(".", 1)[0] in allowed_prefixes and pattern.fullmatch(candidate):
                        identifiers.add(candidate)
                visit(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                visit(child)

    visit(value)
    return identifiers




def _root_cause_assessment_v13(
    root: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    del discrepancies
    conclusion = _mapping(root.get("conclusion"))
    counts = _mapping(root.get("counts"))
    candidates = _mapping_sequence(root.get("candidates"))
    findings = _mapping_sequence(root.get("findings"))
    support: dict[str, int] = {}
    selected_ids: list[str] = []
    for finding in findings:
        for candidate_id in _sequence(
            finding.get("selected_candidate_ids")
        ):
            key = str(candidate_id)
            support[key] = support.get(key, 0) + 1
            selected_ids.append(key)
    by_id = {
        str(candidate.get("id") or candidate.get("candidate_id")): candidate
        for candidate in candidates
    }
    selected = [
        by_id[candidate_id]
        for candidate_id in dict.fromkeys(selected_ids)
        if candidate_id in by_id
    ]
    if not selected:
        selected = sorted(
            candidates,
            key=lambda candidate: -_candidate_score(candidate),
        )[:1]

    verification_count = _integer(counts.get("verifications"))
    if selected:
        leading = selected[0]
        label = _causal_hypothesis_sentence(leading)
        supporting = support.get(
            str(leading.get("id") or leading.get("candidate_id")),
            0,
        )
        evidence = (
            f"The persisted root-cause artifact links {supporting} supporting "
            "finding(s) to this hypothesis."
            if supporting
            else (
                "The persisted evidence is currently insufficient to support "
                "this hypothesis."
            )
        )
    else:
        label = "No defensible leading causal hypothesis was retained."
        evidence = (
            "The root-cause artifact did not retain a research-facing "
            "hypothesis supported by the available evidence."
        )

    status = str(conclusion.get("status") or "unknown").replace("_", " ")
    confidence = str(
        conclusion.get("confidence") or "not established"
    ).replace("_", " ")
    verification = (
        f"{verification_count} deterministic verification(s) were reported."
        if verification_count
        else "Deterministic verification has not yet been performed."
    )
    return (
        '<h3>Causal interpretation</h3>'
        '<div class="discussion-block">'
        '<span class="label">Leading hypothesis</span>'
        f'<p>{escape(label)}</p>'
        '<span class="label">Evidence supporting this hypothesis</span>'
        f'<p>{escape(evidence)}</p>'
        '<span class="label">Current confidence</span>'
        f'<p>{escape(confidence.capitalize())}; causal status: '
        f'{escape(status)}.</p>'
        '<span class="label">Required verification</span>'
        f'<p>{escape(verification)} Patient-level traces and controlled '
        'counterfactual reruns are required before causal attribution.</p>'
        '</div>'
    )


def _recommendations_v13(knowledge: Mapping[str, Any], discrepancies: Sequence[Mapping[str, Any]]) -> str:
    items=[]; seen=set()
    for discrepancy in discrepancies:
        title, action = _recommendation_for_discrepancy(discrepancy)
        domain = _humanize(str(discrepancy.get("domain") or discrepancy.get("key") or "endpoint"))
        key = re.sub(r"[^a-z0-9]+", " ", domain.casefold()).strip()
        if key in seen: continue
        seen.add(key)
        mechanism = _likely_mechanism(discrepancy)
        criterion = _verification_for_discrepancy(discrepancy)
        items.append((title, mechanism, action, criterion, discrepancy))
        if len(items) == 6: break
    rendered=''.join(
        f'<div class="recommendation"><div class="rank">{i}</div><div>{_badge("urgent" if str(d.get("severity"))=="critical" else "high")} '
        f'{_badge("blocking" if d.get("blocking") else "review")}<h3>{escape(title)}</h3>'
        f'<p><strong>Problem.</strong> {escape(_research_implication(d))}</p>'
        f'<p><strong>Likely mechanism.</strong> {escape(mechanism)}</p>'
        f'<p><strong>Required action.</strong> {escape(action)}</p>'
        f'<p><strong>Success criterion.</strong> {escape(criterion)}</p></div></div>'
        for i,(title,mechanism,action,criterion,d) in enumerate(items,1)
    )
    return rendered or '<p class="empty">No prioritised remediation was required.</p>'


def _limitations_v13(knowledge: Mapping[str, Any], root: Mapping[str, Any], discrepancies: Sequence[Mapping[str, Any]]) -> str:
    limitations=["This report reflects one configured execution; generalisation requires replication across independent seeds, cohort sizes and reference dates."]
    missing=[_humanize(str(x.get("domain"))) for x in discrepancies if x.get("category")=="missing_candidate_output"]
    if missing: limitations.append("Psynthea produced no output for " + ", ".join(missing) + "; distributional equivalence cannot be assessed for these domains.")
    if str(_mapping(root.get("conclusion")).get("status") or "").casefold() != "confirmed": limitations.append("No deterministic causal mechanism was confirmed for the observed discrepancies.")
    for raw in _sequence(root.get("limitations")):
        translated=_research_facing_limitation(str(raw))
        if translated and translated not in limitations: limitations.append(translated)
    questions=[]
    for item in discrepancies[:6]:
        q=_question_for_discrepancy(item)
        if q not in questions: questions.append(q)
    return '<h3>Limitations</h3>'+_html_list(limitations,"No material limitation was identified.")+'<h3>Outstanding research questions</h3>'+_html_list(questions,"No outstanding scientific question was identified.")

def _count_difference_status(reference: Any, candidate: Any) -> str:
    """Classify a cohort-level count comparison for scientific screening.

    Low counts are handled separately because a one-record difference can
    produce a large and unstable relative percentage. A ``low count`` result
    is therefore displayed as amber and is not treated as a material
    discrepancy by itself.

    Zero-versus-non-zero comparisons remain ``review`` because they represent
    output presence/absence rather than ordinary sampling variation.
    """
    baseline = _to_float(reference)
    observed = _to_float(candidate)
    if baseline is None or observed is None:
        return "not evaluated"
    if baseline < 0 or observed < 0:
        return "not evaluated"
    if baseline == observed:
        return "not informative" if baseline == 0 else "pass"
    if baseline == 0 or observed == 0:
        return "review"

    absolute_difference = abs(observed - baseline)
    relative_difference = absolute_difference / baseline

    if min(baseline, observed) < _LOW_COUNT_THRESHOLD:
        if (
            absolute_difference
            <= _LOW_COUNT_MAX_ACCEPTABLE_ABSOLUTE_DIFFERENCE
        ):
            return "low count"
        return (
            "review"
            if relative_difference >= _LOW_COUNT_REVIEW_THRESHOLD
            else "low count"
        )

    return (
        "review"
        if relative_difference >= _COUNT_MATERIALITY_THRESHOLD
        else "performed"
    )


def _material_count_difference(reference: Any, candidate: Any) -> bool:
    """Return whether a count comparison warrants material-discrepancy review."""
    return _count_difference_status(reference, candidate) == "review"


def _relative_difference(reference: Any, candidate: Any) -> float | None:
    try:
        baseline = float(reference)
        observed = float(candidate)
    except (TypeError, ValueError):
        return None
    if baseline == 0:
        return None
    return (observed - baseline) / baseline


def _count_discrepancy_category(reference: Any, candidate: Any) -> str:
    if not _numeric_zero(reference) and _numeric_zero(candidate):
        return "missing_candidate_output"
    if _numeric_zero(reference) and not _numeric_zero(candidate):
        return "candidate_only_output"
    return "volume_difference"


def _count_severity(category: str, relative: float | None, findings: Sequence[Mapping[str, Any]]) -> str:
    if category in {"missing_candidate_output", "candidate_only_output"}:
        return "critical"
    if _has_blocking_evidence(findings) or (relative is not None and abs(relative) >= 0.50):
        return "high"
    return "medium"


def _scientific_impact_score(*, severity: str, blocking: bool, relative_difference: float | None, adjusted_significance: bool, evidence_count: int) -> float:
    score = {"critical": 50.0, "high": 35.0, "medium": 20.0, "low": 10.0}.get(severity, 5.0)
    if blocking:
        score += 20.0
    if relative_difference is not None:
        score += min(abs(relative_difference) * 20.0, 20.0)
    if adjusted_significance:
        score += 15.0
    score += min(evidence_count, 5) * 2.0
    return round(score, 2)


def _count_title(domain: str, category: str) -> str:
    label = _humanize(domain)
    if category == "missing_candidate_output":
        return f"{label} output absent in Psynthea"
    if category == "candidate_only_output":
        return f"{label} output present only in Psynthea"
    return f"{label} volume differs materially"


def _count_short_label(domain: str, category: str, relative: float | None) -> str:
    if category == "missing_candidate_output":
        return f"{_humanize(domain).lower()} absent"
    if category == "candidate_only_output":
        return f"candidate-only {_humanize(domain).lower()}"
    direction = "higher" if (relative or 0.0) > 0 else "lower"
    return f"{_humanize(domain).lower()} {direction} in Psynthea"


def _count_impact(domain: str, category: str, reference: Any, candidate: Any, relative: float | None) -> str:
    label = _humanize(domain).lower()
    if category == "missing_candidate_output":
        return f"Psynthea emitted no {label} records although Synthea emitted {_fmt(reference)}."
    if category == "candidate_only_output":
        return f"Psynthea emitted {_fmt(candidate)} {label} records while Synthea emitted none."
    direction = "more" if (relative or 0.0) > 0 else "fewer"
    return f"Psynthea emitted materially {direction} {label} records than Synthea."


def _count_evidence(domain: str, reference: Any, candidate: Any, relative: float | None, findings: Sequence[Mapping[str, Any]]) -> str:
    delta = _relative_difference_display(reference, candidate)[0]
    base = f"Synthea generated {_fmt(reference)} {_humanize(domain).lower()} records and Psynthea generated {_fmt(candidate)} ({delta})."
    statistical = _statistical_summary_from_findings(findings)
    return base + (" " + statistical if statistical != "No endpoint-specific statistical record was extracted." else "")


def _statistical_summary_from_findings(findings: Sequence[Mapping[str, Any]]) -> str:
    test_names: list[str] = []
    p_values: list[float] = []
    adjusted_values: list[float] = []
    effect_labels: list[str] = []
    for finding in findings:
        for key, value in _walk_items(finding):
            normalized = key.casefold()
            if normalized in {"test_name", "test"} and value:
                test_names.append(str(value))
            elif normalized in {"p_value", "p-value"}:
                number = _to_float(value)
                if number is not None:
                    p_values.append(number)
            elif normalized in {"adjusted_p_value", "adjusted_p", "fdr_p_value"}:
                number = _to_float(value)
                if number is not None:
                    adjusted_values.append(number)
            elif normalized in {"effect_size", "statistic", "risk_ratio", "odds_ratio", "jensen_shannon_divergence"}:
                number = _to_float(value)
                if number is not None:
                    effect_labels.append(f"{_humanize(normalized)}={number:.3g}")
    parts: list[str] = []
    if test_names:
        parts.append("Tests: " + ", ".join(dict.fromkeys(test_names)) + ".")
    if adjusted_values:
        parts.append(f"Mínimo FDR-adjusted p-value: {_format_p_value(min(adjusted_values))}.")
    elif p_values:
        parts.append(f"Mínimo nominal p-value: {_format_p_value(min(p_values))}.")
    if effect_labels:
        parts.append("Reported estimates: " + ", ".join(dict.fromkeys(effect_labels[:4])) + ".")
    return " ".join(parts) if parts else "No endpoint-specific statistical record was extracted."


def _evidence_basis(findings: Sequence[Mapping[str, Any]], category: str) -> list[str]:
    values = ["Cohort-level output comparison"]
    text = " ".join(_finding_text(item) for item in findings)
    if category in {"missing_candidate_output", "candidate_only_output"}:
        values.append("Functional output-retention assessment")
    if any(token in text for token in ("fdr", "adjusted_p", "adjusted p")):
        values.append("Multiplicity-adjusted inference")
    if any(token in text for token in ("confidence", "ci_lower", "ci_upper", "95 %")):
        values.append("Confidence interval")
    if any(token in text for token in ("kolmogorov", "mann_whitney", "welch", "chi_square", "jensen_shannon")):
        values.append("Named statistical comparison")
    return list(dict.fromkeys(values))


def _has_blocking_evidence(findings: Sequence[Mapping[str, Any]]) -> bool:
    return any(_finding_is_blocking(finding) for finding in findings)


def _finding_is_blocking(finding: Mapping[str, Any]) -> bool:
    if bool(finding.get("blocking")) or bool(finding.get("blocking_issue")):
        return True
    return any(token in _finding_text(finding) for token in ("blocking", "critical", "research_use_ready=false"))


def _has_adjusted_significance(findings: Sequence[Mapping[str, Any]]) -> bool:
    text = " ".join(_finding_text(finding) for finding in findings)
    return any(token in text for token in ("significant_after_fdr", "fdr-adjusted", "adjusted_p", "adjusted p"))



def _recommendation_for_discrepancy(item: Mapping[str, Any]) -> tuple[str, str]:
    domain = _humanize(str(item.get("domain") or item.get("key") or "endpoint"))
    category = str(item.get("category") or "")
    title_text = str(item.get("title") or "")
    quoted = re.search(r"['\"]([a-zA-Z][a-zA-Z0-9_-]{2,})['\"]", title_text)
    if quoted and domain.casefold() in {"clinical endpoint", "clinical", "knowledge"}:
        domain = _humanize(quoted.group(1))
    if category == "missing_candidate_output":
        return (f"Restore {domain} output generation", f"Trace the state transitions, record constructors, export mapping and retention filters responsible for {domain.lower()} emission in Psynthea, then compare emitted records with the same Synthea execution.")
    if category == "candidate_only_output":
        return (f"Audit candidate-only {domain} output", f"Determine why Psynthea emits {domain.lower()} records absent from the reference run and verify whether the difference reflects transition semantics, defaults or exporter behaviour.")
    if category == "knowledge_finding":
        return (f"Resolve {domain} scientific discrepancy", f"Review the persisted clinical finding, its source evidence and the corresponding generation or mapping logic before repeating validation.")
    return (f"Review {domain} generation semantics", f"Inspect the module transitions, lifecycle rules, denominators and exporter behaviour controlling {domain.lower()}, prioritising the evidence linked in this report.")


def _verification_for_discrepancy(item: Mapping[str, Any]) -> str:
    domain = _humanize(str(item.get("domain") or item.get("key") or "endpoint")).lower()
    return f"Repeat the identical seeded cohort after the fix, inspect patient-level {domain} traces, then replicate across independent seeds and confirm that the endpoint meets the approved equivalence tolerance."



def _question_for_discrepancy(item: Mapping[str, Any]) -> str:
    domain = _humanize(str(item.get("domain") or item.get("key") or "endpoint"))
    title_text = str(item.get("title") or "")
    quoted = re.search(r"['\"]([a-zA-Z][a-zA-Z0-9_-]{2,})['\"]", title_text)
    if quoted and domain.casefold() in {"clinical endpoint", "clinical", "knowledge"}:
        domain = _humanize(quoted.group(1))
    category = str(item.get("category") or "")
    if category == "missing_candidate_output":
        return f"Which Psynthea transition, record-construction or export step prevents {domain.lower()} records from being emitted?"
    if category == "candidate_only_output":
        return f"Which Psynthea default or transition creates {domain.lower()} records that do not appear in the reference run?"
    if category == "knowledge_finding":
        return f"Which generation, coding or mapping difference explains the {domain.lower()} scientific discrepancy?"
    return f"Which module, lifecycle, denominator or exporter difference explains the material {domain.lower()} divergence?"


def _candidate_score(candidate: Mapping[str, Any]) -> float:
    for key in ("score", "ranking_score", "confidence_score", "probability"):
        value = _to_float(candidate.get(key))
        if value is not None:
            return value
    return 0.0



def _extract_domain_tokens(finding: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("domain", "metric", "endpoint", "endpoint_id"):
        value = finding.get(key)
        if value:
            tokens.add(str(value).casefold())
    text = _finding_text(finding)
    for quoted in re.findall(r"['\"]([a-zA-Z][a-zA-Z0-9_-]{2,})['\"]", text):
        tokens.add(quoted.casefold())
    return tokens



def _first_domain_token(finding: Mapping[str, Any]) -> str:
    tokens = _extract_domain_tokens(finding)
    excluded = {"clinical", "knowledge", "endpoint", "module", "population"}
    usable = sorted(token for token in tokens if token not in excluded)
    return usable[0] if usable else "clinical endpoint"


def _flatten_scalars(value: Any) -> list[Any]:
    output: list[Any] = []
    if isinstance(value, Mapping):
        for child in value.values():
            output.extend(_flatten_scalars(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            output.extend(_flatten_scalars(child))
    elif value is not None:
        output.append(value)
    return output


def _walk_items(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    output: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            output.append((str(key), child))
            output.extend(_walk_items(child, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            output.extend(_walk_items(child, prefix))
    return output


def _is_number(*values: Any) -> bool:
    return any(_to_float(value) is not None for value in values)


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _humanize(value: str) -> str:
    translations = {
        "eligible_patients": "Pacientes elegibles",
        "prevalent_patients": "Pacientes prevalentes",
        "incident_patients": "Pacientes incidentes",
        "at_risk_patients": "Pacientes en riesgo",
        "period_prevalence": "Prevalencia de periodo",
        "cumulative_incidence": "Incidencia acumulada",
        "mean_incident_onset_age": "Edad media de inicio incidente",
        "median_incident_onset_age": "Edad mediana de inicio incidente",
        "min_incident_onset_age": "Edad mínima de inicio incidente",
        "max_incident_onset_age": "Edad máxima de inicio incidente",
    }
    return translations.get(value, value.replace("_", " ").replace("-", " ").strip().title())


def _format_p_value(value: float) -> str:
    return f"{value:.3f}" if value >= 0.001 else f"{value:.2e}"




def _delta_class_for_status(status: str) -> str:
    normalized = status.casefold().replace("_", " ")
    if normalized in {"pass", "performed", "ready", "supported"}:
        return "delta-acceptable"
    if normalized == "low count":
        return "delta-neutral"
    if normalized in {"review", "fail", "failed", "blocking", "not demonstrated"}:
        return "delta-review"
    return "delta-neutral"


def _overall_evidence(
    summary: Mapping[str, Any],
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    root: Mapping[str, Any],
) -> str:
    del summary
    functional = _functional_evidence_status(validation)
    statistical_statuses = [
        str(
            _mapping(module.get("statistical_summary")).get(
                "validation_status"
            )
            or "unknown"
        )
        for module in _mapping_sequence(validation.get("modules"))
    ]
    knowledge_statuses = [
        str(module.get("overall_status") or "unknown")
        for module in _mapping_sequence(knowledge.get("modules"))
    ]
    root_status = str(
        _mapping(root.get("conclusion")).get("status") or "unknown"
    )
    items = (
        ("Functional evidence", functional),
        (
            "Estadísticoal evidence",
            _aggregate_evidence_status(statistical_statuses),
        ),
        (
            "Clinical and knowledge evidence",
            _aggregate_evidence_status(knowledge_statuses),
        ),
        ("Causal evidence", root_status),
    )
    return (
        '<div class="evidence-profile">'
        + "".join(_evidence_profile_row(label, status) for label, status in items)
        + '</div><p class="muted">Bar length represents evidence status, not a '
        'probability or newly calculated confidence score.</p>'
    )


def _functional_evidence_status(validation: Mapping[str, Any]) -> str:
    if _reference_evidence_incomplete(validation):
        return "reference incomplete"
    summaries = [
        _mapping(module.get("functional_summary"))
        for module in _mapping_sequence(validation.get("modules"))
    ]
    if not summaries:
        return "unknown"
    if any(not bool(item.get("valid_for_comparison")) for item in summaries):
        return "fail"
    if any(_integer(item.get("blocking_issue_count")) > 0 for item in summaries):
        return "fail"
    if all(
        bool(item.get("synthea_functional"))
        and bool(item.get("psynthea_functional"))
        for item in summaries
    ):
        return "pass with warning" if any(_integer(item.get("warning_count")) > 0 for item in summaries) else "pass"
    return _aggregate_evidence_status(
        [str(item.get("status") or "unknown") for item in summaries]
    )

def _aggregate_evidence_status(statuses: Sequence[str]) -> str:
    normalized = [status.casefold().replace("_", " ") for status in statuses if status]
    if not normalized:
        return "unknown"
    if any(status in {"fail", "failed", "rejected"} for status in normalized):
        return "fail"
    if any("incomplete" in status for status in normalized):
        return "incomplete"
    if any(status in {"partially comparable", "partial", "warning", "review"} for status in normalized):
        return "partial"
    if any("inconclusive" in status for status in normalized):
        return "inconclusive"
    if all(status in {"pass", "passed", "ready", "succeeded", "comparable"} for status in normalized):
        return "pass"
    return normalized[0]


def _evidence_card(label: str, status: str, note: str) -> str:
    normalized = status.casefold().replace("_", " ")
    css = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "unknown"
    css = {
        "partially-comparable": "partial",
        "pass-with-warning": "partial",
    }.get(css, css)
    widths = {"pass": 100, "partial": 70, "review": 55, "fail": 35, "incomplete": 20, "inconclusive": 20, "unknown": 10}
    width = widths.get(css, 45)
    display = _humanize(normalized)
    return (
        f'<div class="evidence-card evidence-{escape(css)}">'
        f'<span class="label">{escape(label)}</span>'
        f'<div class="evidence-status">{escape(display)}</div>'
        f'<span class="evidence-note">{escape(note)}</span>'
        f'<div class="meter" aria-hidden="true"><span style="width:{width}%"></span></div></div>'
    )


def _final_assessment_summary(
    decision: str,
    summary: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    root: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    validation_summary = _mapping(summary.get("validation"))
    root_conclusion = _mapping(root.get("conclusion"))
    blocking = sum(bool(item.get("blocking")) for item in discrepancies)
    no_material_discrepancy_detected = decision == "PASS" and not discrepancies
    values = (
        (
            "Material discrepancy detected",
            "No" if no_material_discrepancy_detected else "Yes or unresolved",
        ),
        ("Equivalence demonstrated", "No"),
        ("Blocking discrepancies", blocking),
        (
            "FDR-significant tests",
            validation_summary.get("significant_after_fdr_count", 0),
        ),
        ("Root cause", root_conclusion.get("status") or "unknown"),
        ("Next validation", "Required"),
    )
    return '<div class="final-assessment">' + "".join(
        f'<div class="mini"><span class="label">{escape(label)}</span><strong>{escape(_fmt(value))}</strong></div>'
        for label, value in values
    ) + '</div>'


def _research_readiness_label(decision: str, knowledge: Mapping[str, Any]) -> str:
    modules = _mapping_sequence(knowledge.get("modules"))
    ready = bool(modules) and all(bool(module.get("research_use_ready")) for module in modules)
    if decision == "PASS" and ready:
        return "Eligible for confirmatory validation within evaluated scope"
    if decision in {"INCOMPLETE", "NOT_COMPARABLE"}:
        return "Research readiness cannot be assessed"
    return "Not research ready"


def _research_readiness(
    decision: str,
    summary: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    knowledge_summary = _mapping(summary.get("knowledge"))
    blocking = [item for item in discrepancies if item.get("blocking")]

    if decision == "NOT_COMPARABLE":
        requirements = [
            "Restore and verify the minimum reference clinical output required for comparison.",
            "Repeat the identical seeded cohort after restoring reference completeness.",
            "Confirm that affected endpoints are statistically and clinically assessable before interpreting generator differences.",
        ]
    elif decision == "PASS" and not discrepancies:
        requirements = [
            "Predefine endpoint-specific equivalence margins before confirmatory analysis.",
            "Replicate the experiment across independent seeds, cohort sizes and reference dates.",
            "Demonstrate that confidence intervals remain within the approved equivalence margins.",
            "Obtain independent review before authorising replacement in downstream research.",
        ]
    else:
        requirements = [
            "Resolve or justify all blocking discrepancies.",
            "Repeat the identical seeded cohort after remediation.",
            "Replicate the experiment across independent seeds and cohort sizes.",
            "Confirm that all predefined functional and statistical tolerances are met.",
        ]

    return (
        '<div class="readiness">'
        f'<div class="cards">{_metric_card("Current status", _research_readiness_label(decision, knowledge))}'
        f'{_metric_card("Blocking ranked discrepancies", len(blocking))}'
        f'{_metric_card("Knowledge blocking findings", knowledge_summary.get("blocking_finding_count"))}'
        f'{_metric_card("Next validation", "Required")}</div>'
        '<h3>Requirements before research use</h3>'
        + _html_list(
            requirements,
            "Confirmatory validation remains required before replacement.",
        )
        + '</div>'
    )


def _research_facing_statistical_summary(item: Mapping[str, Any]) -> str:
    summary = _statistical_summary_from_findings(item.get("related_findings") or ())
    if summary and not summary.startswith("No endpoint-specific"):
        return summary
    category = str(item.get("category") or "")
    if category in {"missing_candidate_output", "candidate_only_output", "volume_difference"}:
        return "No direct statistical endpoint was extracted; evidence derives from functional cohort comparison and Knowledge Engine interpretation."
    return "No direct statistical endpoint is available; this discrepancy is supported by persisted functional or knowledge-layer evidence."


def _research_facing_candidate_label(candidate: Mapping[str, Any]) -> str:
    category = str(candidate.get("category") or "").strip()
    if category:
        return _humanize(category.split(".")[-1])
    title = str(candidate.get("title") or "").strip()
    if title and not _contains_internal_identifier(title):
        return title
    statement = str(candidate.get("statement") or "").strip()
    quoted = re.search(r"root_cause(?:\.engine)?\.([a-zA-Z0-9_]+)", statement)
    if quoted:
        return _humanize(quoted.group(1))
    return "Unverified causal hypothesis"


def _contains_internal_identifier(value: str) -> bool:
    text = value.casefold()
    return any(token in text for token in (
        "signal:", "candidate:", "protocol.", "protocol:", "root_cause.",
        "root-cause.", "request_id", "artifact_id",
    ))


def _scientific_verdict_label(
    decision: str,
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    """Separate pipeline status from the strength of the scientific conclusion."""
    if decision == "PASS" and not discrepancies:
        return "NO MATERIAL DISCREPANCY DETECTED"
    if decision == "PASS":
        return "REVIEW REQUIRED"
    if decision == "REVIEW":
        return "REVIEW REQUIRED"
    if decision == "NOT_COMPARABLE":
        return "NOT COMPARABLE"
    return "INCOMPLETE"


def _replacement_verdict(decision: str, knowledge: Mapping[str, Any], discrepancies: Sequence[Mapping[str, Any]]) -> str:
    ready = bool(_mapping_sequence(knowledge.get("modules"))) and all(bool(x.get("research_use_ready")) for x in _mapping_sequence(knowledge.get("modules")))
    if decision == "PASS" and ready and not discrepancies:
        return (
            "No blocking discrepancy was detected; equivalence and replacement "
            "remain to be demonstrated in confirmatory validation"
        )
    if decision in {"INCOMPLETE", "NOT_COMPARABLE"}: return "Replacement cannot be assessed"
    return "Psynthea cannot yet replace Synthea for the evaluated scope"


def _methods_and_scope(payload: Mapping[str, Any], validation: Mapping[str, Any], knowledge: Mapping[str, Any]) -> str:
    del validation, knowledge
    cohort = _mapping(payload.get("cohort"))
    module_scope = _module_scope_label(cohort)
    return (
        '<div class="figure-grid">'
        '<div class="method-box"><span class="label">Design</span><p>Deterministic comparison of persisted Synthea and Psynthea cohorts using functional, statistical, clinical-knowledge and root-cause evidence.</p></div>'
        f'<div class="method-box"><span class="label">Cohort</span><p>Population: <strong>{escape(_fmt(cohort.get("population_size")))}</strong><br>Seed: <strong>{escape(_fmt(cohort.get("seed")))}</strong><br>Fecha de referencia: <strong>{escape(_fmt(cohort.get("reference_date")))}</strong><br>Rango de edad: <strong>{escape(_age_range_label(cohort))}</strong><br>Modules: <strong>{escape(module_scope)}</strong></p></div>'
        '<div class="method-box"><span class="label">Decision principle</span><p>Equivalence requires complete outputs, acceptable effect magnitude, clinically concordant content and no unresolved blocking evidence.</p></div>'
        '</div>'
        + _module_selection_details(cohort)
        + '<p class="muted">The report consolidates upstream results and does not recalculate tests, acquire external references or infer new causal mechanisms.</p>'
    )


def _cohort_bar_chart(validation: Mapping[str, Any]) -> str:
    cohorts = _cohort_counts(validation)
    synthea = _mapping(cohorts.get("synthea"))
    psynthea = _mapping(cohorts.get("psynthea"))
    domains = _cohort_domains(validation)
    maxima = [
        max(float(synthea.get(domain) or 0), float(psynthea.get(domain) or 0))
        for domain in domains
    ]
    if not domains or max(maxima, default=0) <= 0:
        return (
            '<p class="empty">No se dispuso de resultados numéricos de cohorte '
            'para la visualización.</p>'
        )

    width = 900
    row_height = 52
    legend_height = 42
    height = legend_height + 28 + row_height * len(domains)
    maximum = max(maxima)
    synthea_color = "#456f9a"
    psynthea_color = "#8aa9c5"

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Comparación de resultados de cohorte entre Synthea y Psynthea">',
        f'<rect x="230" y="12" width="14" height="14" rx="3" fill="{synthea_color}"/>',
        '<text x="251" y="24" font-size="12">Synthea</text>',
        f'<rect x="330" y="12" width="14" height="14" rx="3" fill="{psynthea_color}"/>',
        '<text x="351" y="24" font-size="12">Psynthea</text>',
    ]

    for index, domain in enumerate(domains):
        y = legend_height + index * row_height
        synthea_value = float(synthea.get(domain) or 0)
        psynthea_value = float(psynthea.get(domain) or 0)
        scale = 520 / maximum
        parts.extend(
            [
                f'<text x="8" y="{y + 18}" font-size="13">'
                f'{escape(_humanize(domain))}</text>',
                f'<rect x="230" y="{y}" width="{synthea_value * scale:.1f}" '
                f'height="15" rx="3" fill="{synthea_color}"/>',
                f'<rect x="230" y="{y + 19}" width="{psynthea_value * scale:.1f}" '
                f'height="15" rx="3" fill="{psynthea_color}"/>',
                f'<text x="{235 + synthea_value * scale:.1f}" y="{y + 12}" '
                f'font-size="11">{escape(_fmt(synthea.get(domain)))}</text>',
                f'<text x="{235 + psynthea_value * scale:.1f}" y="{y + 31}" '
                f'font-size="11">{escape(_fmt(psynthea.get(domain)))}</text>',
            ]
        )

    parts.append("</svg>")
    return '<div class="chart">' + "".join(parts) + "</div>"


def _domain_concordance_matrix(
    validation: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    domains = _cohort_domains(validation)
    cohorts = _cohort_counts(validation)
    reference = _mapping(cohorts.get("synthea"))
    candidate = _mapping(cohorts.get("psynthea"))
    rows: list[str] = []
    reference_incomplete = _reference_evidence_incomplete(validation)

    for domain in domains:
        domain_findings = [
            item
            for item in discrepancies
            if str(item.get("domain")) == domain
        ]
        count_finding = next(
            (
                item
                for item in domain_findings
                if item.get("category")
                in {
                    "missing_candidate_output",
                    "candidate_only_output",
                    "volume_difference",
                }
            ),
            None,
        )
        has_clinical_finding = any(
            item.get("category") == "knowledge_finding"
            for item in domain_findings
        )

        category = str(
            count_finding.get("category") if count_finding else ""
        )
        if reference_incomplete and category == "candidate_only_output":
            output = "not assessable"
            volume = "not assessable"
        elif category in {
            "missing_candidate_output",
            "candidate_only_output",
        }:
            output = "fail"
            volume = "not assessable"
        else:
            output = "pass"
            volume = _count_difference_status(
                reference.get(domain),
                candidate.get(domain),
            )

        clinical = "review" if has_clinical_finding else "not evaluated"
        overall = (
            "not assessable"
            if output == "not assessable"
            else (
                "fail"
                if output == "fail"
                else (
                    "review"
                    if volume == "review" or clinical == "review"
                    else (
                        "low count"
                        if volume == "low count"
                        else "pass"
                    )
                )
            )
        )
        matrix_class = "review" if overall in {"low count", "not assessable"} else overall
        rows.append(
            f'<tr class="matrix-{escape(matrix_class)}">'
            f'<td>{escape(_humanize(domain))}</td>'
            f'<td class="status">{_badge(output)}</td>'
            f'<td class="status">{_badge(volume)}</td>'
            f'<td class="status">{_badge(clinical)}</td>'
            f'<td class="status">{_badge(overall)}</td></tr>'
        )

    if not rows:
        return '<p class="empty">No domain matrix could be constructed.</p>'
    return (
        '<table><thead><tr><th>Domain</th><th>Output completeness</th>'
        '<th>Volume</th><th>Clinical concordance</th><th>Overall</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table>'
    )


def _finding_card(
    item: Mapping[str, Any],
    *,
    narrative: ScientificNarrativeFormatter,
    compact: bool = False,
) -> str:
    stats = _extract_display_statistics(item.get("related_findings") or ())
    details = _statistical_details_html(stats, item)
    implication = narrative.scientific_implication(item)
    return (
        '<article class="finding">'
        f'<div>{_badge(item.get("severity"))} '
        f'{_badge("blocking" if item.get("blocking") else "review")}</div>'
        f'<h3>{escape(_publication_finding_title(item))}</h3>'
        '<div class="finding-grid">'
        f'<div class="finding-panel"><span class="label">Observation</span>'
        f'<p>{escape(narrative.observed_result(item))}</p></div>'
        f'<div class="finding-panel"><span class="label">Interpretation</span>'
        f'<p>{escape(narrative.scientific_interpretation(item))}</p></div>'
        + (
            ''
            if compact
            else (
                '<div class="finding-panel finding-wide">'
                '<span class="label">Scientific implication</span>'
                f'<p>{escape(implication)}</p></div>'
            )
        )
        + '</div>'
        + details
        + '</article>'
    )


def _observed_result(item: Mapping[str, Any]) -> str:
    if item.get('synthea') is not None or item.get('psynthea') is not None:
        return f"Synthea: {_fmt(item.get('synthea'))}; Psynthea: {_fmt(item.get('psynthea'))}; relative difference: {item.get('difference') or 'N/A'}."
    stats=_extract_display_statistics(item.get('related_findings') or ())
    if stats.get('shared') is not None:
        return f"{_fmt(stats.get('shared'))} clinical codes were shared; code-set overlap was {_qualify_overlap(stats.get('jaccard'))} and frequency distributions were {_qualify_divergence(stats.get('jsd'))}."
    if stats.get('synthea_prevalence') is not None or stats.get('psynthea_prevalence') is not None:
        return f"Synthea prevalence: {_format_percent(stats.get('synthea_prevalence'))}; Psynthea prevalence: {_format_percent(stats.get('psynthea_prevalence'))}; absolute difference: {_format_percentage_points(stats.get('absolute_difference'))}."
    return _clean_research_text(str(item.get('evidence') or 'Persisted scientific evidence identified a material discrepancy.'))


def _scientific_meaning(item: Mapping[str, Any]) -> str:
    title=str(item.get('title') or '').casefold(); category=str(item.get('category') or '')
    if 'code concordance' in title or 'code overlap' in title: return 'The generators do not represent a sufficiently comparable set of clinical concepts or concept frequencies for this domain.'
    if 'prevalence endpoint' in title: return 'The endpoint prevalence differs materially between generators and equivalence is not supported for this clinical concept.'
    if 'prevalence profile' in title: return 'The population disease-burden profile is not consistently reproduced across the evaluated endpoints.'
    if category=='missing_candidate_output': return 'The candidate generator does not reproduce a clinical output present in the reference generator.'
    if category=='candidate_only_output': return 'The candidate generator introduces an output absent from the reference generator.'
    if category=='volume_difference': return 'The clinical event volume differs beyond the configured materiality threshold.'
    return _clean_research_text(str(item.get('impact') or 'The persisted evidence does not support scientific equivalence.'))


def _research_implication(item: Mapping[str, Any]) -> str:
    domain=_humanize(str(item.get('domain') or 'this endpoint')).lower(); category=str(item.get('category') or '')
    if category=='missing_candidate_output': return f"Studies relying on {domain} would omit clinically relevant events and should not use Psynthea as a substitute until output is restored."
    if 'observations' in str(item.get('title') or '').casefold(): return 'Observation-based phenotyping, monitoring and outcome analyses may produce materially different results.'
    if 'prevalence' in str(item.get('title') or '').casefold(): return 'Population-level disease-burden estimates may be biased or non-comparable.'
    return str(item.get('impact') or 'Downstream analyses may not be scientifically comparable until this finding is resolved.')


def _extract_display_statistics(findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    aliases={'jaccard':'jaccard','jaccard_index':'jaccard','overlap':'overlap','overlap_coefficient':'overlap','jensen_shannon_divergence':'jsd','jsd':'jsd','shared':'shared','shared_count':'shared','synthea_prevalence':'synthea_prevalence','psynthea_prevalence':'psynthea_prevalence','absolute_difference':'absolute_difference','relative_difference':'relative_difference','risk_ratio':'risk_ratio','odds_ratio':'odds_ratio','adjusted_p':'adjusted_p','adjusted_p_value':'adjusted_p','fdr_p_value':'adjusted_p','p_value':'p_value','ci_lower':'ci_lower','ci_upper':'ci_upper'}
    out={}
    for finding in findings:
        for key,value in _walk_items(finding):
            nk=key.casefold(); target=aliases.get(nk)
            if target and target not in out and (_to_float(value) is not None or target=='shared'): out[target]=_to_float(value) if target!='shared' else value
        text=' '.join(str(x) for x in _flatten_scalars(finding))
        for pattern,target in [(r'Jaccard\s*=\s*([0-9.eE+-]+)','jaccard'),(r'overlap\s*=\s*([0-9.eE+-]+)','overlap'),(r'JSD\s*=\s*([0-9.eE+-]+)','jsd'),(r'shared\s*=\s*(\d+)','shared'),(r'Synthea prevalence\s*=\s*([0-9.eE+-]+)','synthea_prevalence'),(r'psynthea prevalence\s*=\s*([0-9.eE+-]+)','psynthea_prevalence'),(r'absolute_difference\s*=\s*([0-9.eE+-]+)','absolute_difference'),(r'risk_ratio\s*=\s*([0-9.eE+-]+)','risk_ratio'),(r'adjusted_p\s*=\s*([0-9.eE+-]+)','adjusted_p')]:
            m=re.search(pattern,text,re.I)
            if m and target not in out: out[target]=float(m.group(1))
        ci=re.search(r'95%\s*CI\s*=\s*\[\s*([0-9.eE+-]+)\s*,\s*([0-9.eE+-]+)\s*\]',text,re.I)
        if ci: out.setdefault('ci_lower',float(ci.group(1))); out.setdefault('ci_upper',float(ci.group(2)))
    return out


def _statistical_details_html(stats: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    labels=[('jaccard','Jaccard index',lambda x:f'{x:.2f}'),('overlap','Overlap coefficient',lambda x:f'{x:.2f}'),('jsd','Jensen–Shannon divergence',lambda x:f'{x:.3f}'),('risk_ratio','Risk ratio',lambda x:f'{x:.2f}'),('odds_ratio','Odds ratio',lambda x:f'{x:.2f}'),('adjusted_p','FDR-adjusted p-value',_format_p_value),('p_value','Nominal p-value',_format_p_value)]
    cells=[]
    for key,label,fn in labels:
        if stats.get(key) is not None: cells.append(f'<div class="stat-item"><span class="label">{escape(label)}</span><strong>{escape(fn(float(stats[key])))}</strong></div>')
    if stats.get('ci_lower') is not None and stats.get('ci_upper') is not None: cells.append(f'<div class="stat-item"><span class="label">95% confidence interval</span><strong>{float(stats["ci_lower"]):.2f}–{float(stats["ci_upper"]):.2f}</strong></div>')
    if stats.get('synthea_prevalence') is not None: cells.append(f'<div class="stat-item"><span class="label">Synthea prevalence</span><strong>{escape(_format_percent(stats["synthea_prevalence"]))}</strong></div>')
    if stats.get('psynthea_prevalence') is not None: cells.append(f'<div class="stat-item"><span class="label">Psynthea prevalence</span><strong>{escape(_format_percent(stats["psynthea_prevalence"]))}</strong></div>')
    if not cells: return '<details><summary>Evidence provenance</summary><p class="muted">This finding is supported by persisted functional or knowledge-layer evidence; no endpoint-level statistical estimate was extracted.</p></details>'
    note=' JSD ranges from 0 (identical distributions) toward 1 (greater divergence).' if stats.get('jsd') is not None else ''
    return '<details><summary>Estadísticoal details</summary><div class="stat-list">'+''.join(cells)+'</div><p class="muted">Values are rounded for readability; full precision remains in the source artifacts.'+note+'</p></details>'


def _forest_plot(
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    points: list[tuple[str, float, float, float]] = []
    seen: set[tuple[str, float, float, float]] = set()

    for item in discrepancies:
        stats = _extract_display_statistics(
            item.get("related_findings") or ()
        )
        rr = stats.get("risk_ratio")
        lower = stats.get("ci_lower")
        upper = stats.get("ci_upper")
        if (
            rr is None
            or lower is None
            or upper is None
            or float(lower) <= 0
            or float(upper) <= 0
        ):
            continue

        domain = str(item.get("domain") or item.get("key") or "")
        identity = (
            domain.casefold(),
            round(float(rr), 8),
            round(float(lower), 8),
            round(float(upper), 8),
        )
        if identity in seen:
            continue
        seen.add(identity)
        points.append(
            (
                _publication_finding_title(item),
                float(rr),
                float(lower),
                float(upper),
            )
        )

    if not points:
        return (
            '<p class="muted">No valid risk-ratio confidence intervals '
            'were available for a forest plot.</p>'
        )

    import math

    points = points[:8]
    max_log = max(
        abs(math.log(value))
        for _, estimate, lower, upper in points
        for value in (lower, upper, estimate)
    )
    max_log = max(max_log, 0.4)
    width = 900
    height = 55 + 42 * len(points)
    left = 330
    span = 500

    def x_position(value: float) -> float:
        return left + (math.log(value) + max_log) / (2 * max_log) * span

    output = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Risk-ratio forest plot">',
        f'<line x1="{x_position(1):.1f}" y1="25" '
        f'x2="{x_position(1):.1f}" y2="{height - 20}" '
        'stroke="#777" stroke-dasharray="4 4"/>',
    ]
    for index, (label, estimate, lower, upper) in enumerate(points):
        y = 45 + index * 42
        short_label = label if len(label) < 42 else label[:39] + "..."
        output.extend(
            [
                f'<text x="5" y="{y + 4}" font-size="12">'
                f'{escape(short_label)}</text>',
                f'<line x1="{x_position(lower):.1f}" y1="{y}" '
                f'x2="{x_position(upper):.1f}" y2="{y}" '
                'stroke="#315f88" stroke-width="3"/>',
                f'<circle cx="{x_position(estimate):.1f}" cy="{y}" '
                'r="5" fill="#183b63"/>',
                f'<text x="840" y="{y + 4}" font-size="11">'
                f'{estimate:.2f} [{lower:.2f}–{upper:.2f}]</text>',
            ]
        )
    output.append("</svg>")
    return (
        '<h3>Risk-ratio forest plot</h3><div class="chart">'
        + "".join(output)
        + '</div>'
    )


def _discussion_summary(decision: str, discrepancies: Sequence[Mapping[str, Any]], knowledge: Mapping[str, Any]) -> str:
    leading=', '.join(str(x.get('short_label')) for x in discrepancies[:3] if x.get('short_label')) or 'no material discrepancy'
    return f'<div class="callout"><strong>Interpretation.</strong> The overall decision is <strong>{escape(decision)}</strong>. The principal evidence concerns {escape(leading)}. These findings should be interpreted as module-specific and constrained to the configured cohort, seed and reference date.</div>'


def _likely_mechanism(item: Mapping[str, Any]) -> str:
    category=str(item.get('category') or ''); domain=_humanize(str(item.get('domain') or 'endpoint')).lower()
    if category=='missing_candidate_output': return f'Not yet confirmed; candidate mechanisms include missing state transitions, record construction or export retention for {domain}.'
    if category=='candidate_only_output': return f'Not yet confirmed; defaults or transition semantics may create candidate-only {domain} records.'
    if 'code concordance' in str(item.get('title') or '').casefold(): return 'Not yet confirmed; code mapping, concept selection or event-frequency semantics may differ.'
    if 'prevalence' in str(item.get('title') or '').casefold(): return 'Not yet confirmed; disease incidence, eligibility logic, denominators or code mapping may differ.'
    return 'Not yet confirmed; module transitions, lifecycle semantics, denominators or exporter behaviour require investigation.'


def _causal_evidence_label(candidate: Mapping[str, Any], support: int) -> str:
    status=str(candidate.get('status') or candidate.get('confidence') or 'unverified').replace('_',' ')
    return f'{support} supporting finding(s); current status: {status}.'


def _research_facing_limitation(text: str) -> str:
    low=text.casefold()
    if not text.strip(): return ''
    if 'max_candidates' in low or 'candidate generation exceeded' in low: return 'The causal search retained only the highest-priority hypotheses; additional alternatives may remain unexplored.'
    if 'verification plan' in low and 'candidate' in low: return 'No deterministic verification protocol was available for the leading causal hypothesis.'
    if _contains_internal_identifier(text): return ''
    return _clean_research_text(text)


def _clean_research_text(text: str) -> str:
    text=re.sub(r'\b(?:signal|candidate|protocol|request_id|artifact_id)\s*[:=]\s*\S+','',text,flags=re.I)
    return re.sub(r'\s+',' ',text).strip()


def _format_percent(value: Any) -> str:
    number=_to_float(value)
    return 'N/A' if number is None else f'{number*100:.1f}%'


def _format_percentage_points(value: Any) -> str:
    number=_to_float(value)
    return 'N/A' if number is None else f'{number*100:+.1f} puntos porcentuales'


def _qualify_overlap(value: Any) -> str:
    x=_to_float(value)
    if x is None: return 'not estimable'
    return 'low' if x<.4 else ('moderate' if x<.7 else 'high')


def _qualify_divergence(value: Any) -> str:
    x=_to_float(value)
    if x is None: return 'not estimable'
    return 'strongly divergent' if x>=.5 else ('moderately divergent' if x>=.2 else 'similar')



def _p_value_relation(value: float) -> str:
    """Format a p-value as a publication-style relation."""
    if value < 0.0001:
        return "< 0.0001"
    return f"= {value:.3f}"


def _publication_finding_title(item: Mapping[str, Any]) -> str:
    """Convert engine-oriented finding titles into result statements."""
    domain = _humanize(
        str(item.get("domain") or item.get("key") or "endpoint")
    )
    category = str(item.get("category") or "")
    reference = item.get("synthea")
    candidate = item.get("psynthea")
    if category == "missing_candidate_output":
        return f"Psynthea did not reproduce {domain} output"
    if category == "candidate_only_output":
        return f"Psynthea introduced candidate-only {domain} output"
    if category == "volume_difference":
        direction = (
            "more"
            if (_relative_difference(reference, candidate) or 0) > 0
            else "fewer"
        )
        return f"Psynthea contained materially {direction} {domain} records"
    title = str(item.get("title") or "Scientific finding")
    title = re.sub(
        r"^Clinical code concordance for ['\"]([^'\"]+)['\"] is fail$",
        r"Clinical coding for \1 was not concordant",
        title,
        flags=re.I,
    )
    title = re.sub(
        r"^Clinical code overlap for ['\"]([^'\"]+)['\"] is inconclusive$",
        r"Clinical coding evidence for \1 was inconclusive",
        title,
        flags=re.I,
    )
    title = re.sub(
        r"^Prevalence endpoint ['\"]([^'\"]+)['\"]:\s*fail$",
        r"Prevalence differed for \1",
        title,
        flags=re.I,
    )
    return title


def _evidence_profile_row(label: str, status: str) -> str:
    normalized = status.casefold().replace("_", " ")
    css = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "unknown"
    css = {
        "partially-comparable": "partial",
        "pass-with-warning": "partial",
        "inconclusive": "incomplete",
        "not-testable": "incomplete",
        "reference-incomplete": "incomplete",
        "reference-empty": "incomplete",
    }.get(css, css)
    widths = {
        "pass": 100,
        "partial": 68,
        "review": 52,
        "fail": 32,
        "incomplete": 18,
        "unknown": 10,
    }
    width = widths.get(css, 42)
    display = _humanize(normalized)
    return (
        '<div class="evidence-row">'
        f'<div class="evidence-label">{escape(label)}</div>'
        '<div class="evidence-track" aria-hidden="true">'
        f'<div class="evidence-fill {escape(css)}" '
        f'style="width:{width}%"></div></div>'
        f'<div class="evidence-state">{escape(display)}</div>'
        '</div>'
    )


def _largest_discrepancy_summary(
    validation: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    if not discrepancies:
        return (
            '<div class="callout"><strong>Key result.</strong> No material '
            'discrepancy was identified in the ranked evidence.</div>'
        )
    item = discrepancies[0]
    label = _publication_finding_title(item)
    difference = str(item.get("difference") or "not estimable")
    return (
        '<div class="callout"><strong>Largest ranked discrepancy.</strong> '
        f'{escape(label)}'
        + (
            f' ({escape(difference)}).'
            if difference not in {"N/A", "not estimable"}
            else "."
        )
        + '</div>'
    )


def _discussion_sections(
    narrative: ScientificNarrativeFormatter,
    root: Mapping[str, Any],
    discrepancies: Sequence[Mapping[str, Any]],
) -> str:
    return (
        '<h3>Overall interpretation</h3>'
        f'<div class="discussion-block"><p>{escape(narrative.overall_interpretation())}</p></div>'
        '<h3>Clinical implications</h3>'
        f'<div class="discussion-block"><p>{escape(narrative.clinical_implications())}</p></div>'
        '<h3>Methodological implications</h3>'
        f'<div class="discussion-block"><p>{escape(narrative.methodological_implications())}</p></div>'
        + _root_cause_assessment_v13(root, discrepancies)
        + '<h3>Future work</h3>'
        '<div class="discussion-block"><p>Future validation should prioritise '
        'patient-level trace comparison, deterministic verification of the '
        'leading causal hypothesis, replication across independent seeds and '
        'cohort sizes, and confirmation against the predefined module-specific '
        'equivalence tolerances.</p></div>'
    )


def _validation_scope_summary(knowledge: Mapping[str, Any]) -> str:
    identifiers = _collect_validation_identifiers(knowledge)
    grouped: dict[str, int] = {}
    for identifier in identifiers:
        prefix = identifier.split(".", 1)[0]
        grouped[prefix] = grouped.get(prefix, 0) + 1
    labels = {
        "ACTION": "Actionability",
        "CLINICAL": "Clinical",
        "EPI": "Epidemiological",
        "SPANISH": "Spanish-context",
        "STAT": "Estadísticoal",
        "STRUCT": "Structural",
    }
    if not grouped:
        return (
            '<p class="empty">No structured validation-rule coverage was '
            'persisted.</p>'
        )
    cards = "".join(
        _metric_card(labels.get(prefix, prefix), f"{count} checks")
        for prefix, count in sorted(grouped.items())
    )
    return (
        '<h3>Validation coverage</h3><div class="cards">'
        + cards
        + '</div>'
    )


def _causal_hypothesis_sentence(candidate: Mapping[str, Any]) -> str:
    label = _research_facing_candidate_label(candidate)
    normalized = label.casefold()
    if "probabilistic semantics" in normalized:
        return (
            "The observed discrepancies are most consistent with differences "
            "in probabilistic state-transition behaviour between the generators."
        )
    if "transition" in normalized:
        return (
            "The observed discrepancies may arise from non-equivalent state "
            "transition behaviour between the generators."
        )
    if "export" in normalized or "retention" in normalized:
        return (
            "The observed discrepancies may arise from differences in record "
            "construction, retention or export behaviour."
        )
    return (
        f"The leading hypothesis concerns {label.lower()}, but the available "
        "evidence does not yet establish a causal mechanism."
    )



def _technical_appendix(
    payload: Mapping[str, Any],
    validation: Mapping[str, Any],
    knowledge: Mapping[str, Any],
    root: Mapping[str, Any],
) -> str:
    del validation, knowledge, root
    artifacts = _mapping(payload.get("source_artifacts"))
    stages = _mapping_sequence(payload.get("stage_summary"))
    succeeded = sum(
        str(stage.get("status") or "").casefold() == "succeeded"
        for stage in stages
    )
    return (
        '<h3>Reproducibility and provenance</h3>'
        '<div class="cards">'
        + _metric_card("Pipeline stages completed", f"{succeeded} / {len(stages)}")
        + _metric_card("Hashed source artifacts", len(artifacts))
        + _metric_card("Report schema", payload.get("schema_version"))
        + _metric_card("Generated at", payload.get("generated_at"))
        + '</div>'
        '<div class="callout"><strong>Machine-readable evidence.</strong> '
        'Complete validation, knowledge, root-cause, integrity-hash and '
        'pipeline records are retained in the separately hashed JSON artifacts. '
        'They are intentionally not reproduced in the research-facing HTML.</div>'
    )


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
    return {"PASS":"var(--green)","REVIEW":"var(--amber)","NOT_COMPARABLE":"var(--amber)","INCOMPLETE":"var(--red)"}.get(decision,"var(--muted)")


def _decision_background(decision: str) -> str:
    return {"PASS":"var(--soft-green)","REVIEW":"var(--soft-amber)","NOT_COMPARABLE":"var(--soft-amber)","INCOMPLETE":"var(--soft-red)"}.get(decision,"#f2f4f7")


def _decision_border(decision: str) -> str:
    return {"PASS":"#b9dec9","REVIEW":"#efd09b","NOT_COMPARABLE":"#efd09b","INCOMPLETE":"#edbbc0"}.get(decision,"var(--line)")


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