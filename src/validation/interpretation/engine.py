"""Deterministic orchestration of scientific interpretation rules.

The engine is the only component allowed to coordinate rule execution.  It:

* validates the rule graph before any scientific work starts;
* executes rules in a stable dependency-respecting order;
* propagates prior evaluations and derived evidence explicitly;
* never converts rule implementation failures into scientific findings;
* emits one immutable :class:`InterpretationReport` containing every finding
  and every evidence value available at the end of the run.

The engine does not interpret evidence itself and does not aggregate findings
into a new clinical claim.  Report-level summaries belong to a separate layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final

from validation.interpretation.evidence import EvidenceCatalog
from validation.interpretation.models import InterpretationReport
from validation.interpretation.rules.base import (
    InterpretationRule,
    PipelineStage,
    RuleContext,
    RuleEvaluation,
    RuleExecutionStatus,
    StageStatus,
)
from validation.interpretation.rules.clinical import DEFAULT_CLINICAL_RULES
from validation.interpretation.rules.epidemiological import (
    DEFAULT_EPIDEMIOLOGICAL_RULES,
)
from validation.interpretation.rules.spanish_adaptation import (
    DEFAULT_SPANISH_ADAPTATION_RULES,
)
from validation.interpretation.rules.statistical import DEFAULT_STATISTICAL_RULES
from validation.interpretation.rules.structural import DEFAULT_STRUCTURAL_RULES

__all__ = [
    "DEFAULT_INTERPRETATION_RULES",
    "ENGINE_VERSION",
    "EngineConfigurationError",
    "EngineExecution",
    "InterpretationEngine",
    "InterpretationEngineConfig",
]

ENGINE_VERSION: Final = "1.2.0"
_RESERVED_METADATA_KEYS: Final = frozenset({"engine", "rule_evaluations", "evidence_lineage"})
_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class EngineConfigurationError(ValueError):
    """Raised when the rule registry or run configuration is invalid."""


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
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _normalize_stages(
    stages: Mapping[PipelineStage, StageStatus],
) -> Mapping[PipelineStage, StageStatus]:
    if not isinstance(stages, Mapping):
        raise TypeError("stages must be a mapping from PipelineStage to StageStatus.")
    normalized: dict[PipelineStage, StageStatus] = {}
    for stage, status in stages.items():
        if not isinstance(stage, PipelineStage):
            raise TypeError("stages keys must be PipelineStage members.")
        if not isinstance(status, StageStatus):
            raise TypeError("stages values must be StageStatus members.")
        normalized[stage] = status
    return MappingProxyType(normalized)


def _deep_freeze(value: Any) -> Any:
    """Recursively detach mutable containers used in execution metadata."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _freeze_metadata(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("metadata must be a mapping.")
    normalized = {str(key): item for key, item in value.items()}
    collisions = sorted(_RESERVED_METADATA_KEYS.intersection(normalized))
    if collisions:
        raise EngineConfigurationError(
            f"metadata uses engine-reserved keys: {collisions}."
        )
    return _deep_freeze(normalized)


@dataclass(frozen=True, slots=True)
class InterpretationEngineConfig:
    """Immutable identifiers and execution context for one interpretation run."""

    validation_id: str
    pipeline_run_id: str
    module_name: str
    report_id: str | None = None
    stages: Mapping[PipelineStage, StageStatus] = field(default_factory=dict)
    research_use: bool = True
    schema_version: str = "1.1.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "validation_id", _identifier(self.validation_id, "validation_id")
        )
        object.__setattr__(
            self, "pipeline_run_id", _identifier(self.pipeline_run_id, "pipeline_run_id")
        )
        object.__setattr__(self, "module_name", _identifier(self.module_name, "module_name"))
        report_id = self.report_id or f"{self.validation_id}.interpretation"
        object.__setattr__(self, "report_id", _identifier(report_id, "report_id"))
        object.__setattr__(
            self, "schema_version", _identifier(self.schema_version, "schema_version")
        )
        if not isinstance(self.research_use, bool):
            raise TypeError("research_use must be a bool.")
        object.__setattr__(self, "stages", _normalize_stages(self.stages))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class EngineExecution:
    """Complete auditable result of one engine execution."""

    report: InterpretationReport
    evaluations: tuple[RuleEvaluation, ...]
    execution_order: tuple[str, ...]
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.report, InterpretationReport):
            raise TypeError("report must be an InterpretationReport.")
        evaluations = tuple(self.evaluations)
        if not all(isinstance(item, RuleEvaluation) for item in evaluations):
            raise TypeError("evaluations must contain RuleEvaluation values only.")
        order = tuple(_identifier(item, "execution_order item") for item in self.execution_order)
        if tuple(item.rule_id for item in evaluations) != order:
            raise ValueError("execution_order must match the RuleEvaluation sequence exactly.")
        for field_name, value in (
            ("started_at", self.started_at),
            ("completed_at", self.completed_at),
        ):
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime.")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware.")
        started = self.started_at.astimezone(UTC)
        completed = self.completed_at.astimezone(UTC)
        if completed < started:
            raise ValueError("completed_at cannot precede started_at.")
        if len(order) != len(set(order)):
            raise ValueError("execution_order must not contain duplicate rule identifiers.")
        report_findings = tuple(
            finding for evaluation in evaluations for finding in evaluation.findings
        )
        if self.report.findings != report_findings:
            raise ValueError("report findings must exactly match the ordered rule evaluations.")
        if self.report.generated_at != completed:
            raise ValueError("report.generated_at must equal execution completed_at.")
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(self, "execution_order", order)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def execution_status_counts(self) -> Mapping[str, int]:
        """Return immutable counts grouped by rule execution status."""

        counts = {status.value: 0 for status in RuleExecutionStatus}
        for evaluation in self.evaluations:
            counts[evaluation.status.value] += 1
        return MappingProxyType(counts)

    @property
    def incomplete_evaluations(self) -> tuple[RuleEvaluation, ...]:
        """Return rules that did not complete or become explicitly non-applicable."""

        accepted = {
            RuleExecutionStatus.COMPLETED,
            RuleExecutionStatus.NOT_APPLICABLE,
        }
        return tuple(item for item in self.evaluations if item.status not in accepted)

    @property
    def research_use_ready(self) -> bool:
        """Conservative execution-level gate for downstream research use.

        A report with no blocking findings is not sufficient when rules were
        skipped, blocked or lacked evidence. At least one scientific finding
        must also have been produced.
        """

        return (
            bool(self.report.findings)
            and not self.incomplete_evaluations
            and self.report.research_use_allowed
        )

    def evaluation(self, rule_id: str) -> RuleEvaluation | None:
        """Return one rule evaluation by stable identifier."""

        rule_id = _identifier(rule_id, "rule_id")
        return next((item for item in self.evaluations if item.rule_id == rule_id), None)


DEFAULT_INTERPRETATION_RULES: Final = (
    *DEFAULT_STRUCTURAL_RULES,
    *DEFAULT_STATISTICAL_RULES,
    *DEFAULT_CLINICAL_RULES,
    *DEFAULT_EPIDEMIOLOGICAL_RULES,
    *DEFAULT_SPANISH_ADAPTATION_RULES,
)


class InterpretationEngine:
    """Execute an immutable registry of interpretation rules safely."""

    __slots__ = ("_rules", "_execution_order")

    def __init__(
        self,
        rules: Sequence[InterpretationRule] = DEFAULT_INTERPRETATION_RULES,
    ) -> None:
        if isinstance(rules, (str, bytes)) or not isinstance(rules, Sequence):
            raise TypeError("rules must be a sequence of InterpretationRule objects.")
        normalized = tuple(rules)
        if not normalized:
            raise EngineConfigurationError("At least one interpretation rule is required.")
        for index, rule in enumerate(normalized):
            if not isinstance(rule, InterpretationRule):
                raise TypeError(
                    f"rules[{index}] must be InterpretationRule, got {type(rule).__name__}."
                )
        self._validate_registry(normalized)
        order = self._topological_order(normalized)
        by_id = {rule.rule_id: rule for rule in normalized}
        self._rules = tuple(by_id[rule_id] for rule_id in order)
        self._execution_order = order

    @property
    def rules(self) -> tuple[InterpretationRule, ...]:
        return self._rules

    @property
    def execution_order(self) -> tuple[str, ...]:
        return self._execution_order

    @property
    def registry_manifest(self) -> tuple[Mapping[str, Any], ...]:
        """Return a stable machine-readable description of the rule registry."""

        return tuple(
            MappingProxyType(
                {
                    "rule_id": rule.rule_id,
                    "class": f"{type(rule).__module__}.{type(rule).__qualname__}",
                    "dimension": rule.dimension.value,
                    "dependencies": tuple(
                        {
                            "rule_id": dependency.rule_id,
                            "required": dependency.required,
                            "policy": dependency.policy.value,
                        }
                        for dependency in rule.dependencies
                    ),
                    "required_stages": tuple(stage.value for stage in rule.required_stages),
                }
            )
            for rule in self._rules
        )

    @property
    def registry_fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint of the active rule graph."""

        serializable = [
            {
                "rule_id": item["rule_id"],
                "class": item["class"],
                "dimension": item["dimension"],
                "dependencies": list(item["dependencies"]),
                "required_stages": list(item["required_stages"]),
            }
            for item in self.registry_manifest
        ]
        payload = dumps(serializable, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_registry(rules: tuple[InterpretationRule, ...]) -> None:
        rule_ids = [rule.rule_id for rule in rules]
        duplicates = sorted({item for item in rule_ids if rule_ids.count(item) > 1})
        if duplicates:
            raise EngineConfigurationError(
                f"Duplicate rule identifiers are not allowed: {duplicates}."
            )
        known = set(rule_ids)
        missing: dict[str, list[str]] = {}
        for rule in rules:
            unknown = sorted(
                dependency.rule_id
                for dependency in rule.dependencies
                if dependency.required and dependency.rule_id not in known
            )
            if unknown:
                missing[rule.rule_id] = unknown
        if missing:
            details = "; ".join(
                f"{rule_id} -> {dependencies}" for rule_id, dependencies in missing.items()
            )
            raise EngineConfigurationError(f"Required rule dependencies are absent: {details}.")

    @staticmethod
    def _topological_order(rules: tuple[InterpretationRule, ...]) -> tuple[str, ...]:
        """Return a stable topological order, preserving registry order when possible."""

        index = {rule.rule_id: position for position, rule in enumerate(rules)}
        known = set(index)
        incoming: dict[str, set[str]] = {
            rule.rule_id: {
                dependency.rule_id
                for dependency in rule.dependencies
                if dependency.rule_id in known
            }
            for rule in rules
        }
        outgoing: dict[str, set[str]] = {rule.rule_id: set() for rule in rules}
        for target, sources in incoming.items():
            for source in sources:
                outgoing[source].add(target)

        ready = sorted(
            (rule_id for rule_id, sources in incoming.items() if not sources),
            key=index.__getitem__,
        )
        ordered: list[str] = []
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for target in sorted(outgoing[current], key=index.__getitem__):
                incoming[target].discard(current)
                if not incoming[target] and target not in ordered and target not in ready:
                    ready.append(target)
                    ready.sort(key=index.__getitem__)

        if len(ordered) != len(rules):
            cyclic = sorted(rule_id for rule_id, sources in incoming.items() if sources)
            raise EngineConfigurationError(
                f"Rule dependency graph contains a cycle involving: {cyclic}."
            )
        return tuple(ordered)

    def run(
        self,
        evidence: EvidenceCatalog,
        *,
        config: InterpretationEngineConfig,
    ) -> InterpretationReport:
        """Execute all rules and return the final machine-readable report."""

        return self.execute(evidence, config=config).report

    def execute(
        self,
        evidence: EvidenceCatalog,
        *,
        config: InterpretationEngineConfig,
    ) -> EngineExecution:
        """Execute all rules and retain the complete rule-level audit trail."""

        if not isinstance(evidence, EvidenceCatalog):
            raise TypeError("evidence must be an EvidenceCatalog.")
        if not isinstance(config, InterpretationEngineConfig):
            raise TypeError("config must be an InterpretationEngineConfig.")

        started_at = datetime.now(UTC)
        current_catalog = evidence
        evaluations: dict[str, RuleEvaluation] = {}
        evidence_lineage: list[dict[str, Any]] = []

        for rule in self._rules:
            context = RuleContext(
                validation_id=config.validation_id,
                module_name=config.module_name,
                evidence=current_catalog,
                evaluated_at=started_at,
                research_use=config.research_use,
                stages=config.stages,
                prior_evaluations=evaluations,
                metadata=config.metadata,
            )
            evaluation = rule.run(context)
            evaluations[rule.rule_id] = evaluation

            if evaluation.derived_evidence:
                derived_catalog = EvidenceCatalog(
                    tuple(item.value for item in evaluation.derived_evidence)
                )
                current_catalog = current_catalog.merge(derived_catalog)
                evidence_lineage.extend(
                    {
                        "metric_id": item.value.metric_id,
                        "produced_by_rule": rule.rule_id,
                        "formula": item.formula,
                        "source_metric_ids": list(item.source_metric_ids),
                    }
                    for item in evaluation.derived_evidence
                )

        evaluation_sequence = tuple(evaluations[rule_id] for rule_id in self._execution_order)
        findings = tuple(
            finding
            for evaluation in evaluation_sequence
            for finding in evaluation.findings
        )
        completed_at = datetime.now(UTC)
        execution_status_counts = {status.value: 0 for status in RuleExecutionStatus}
        for evaluation in evaluation_sequence:
            execution_status_counts[evaluation.status.value] += 1
        incomplete_statuses = {
            RuleExecutionStatus.INSUFFICIENT_EVIDENCE,
            RuleExecutionStatus.BLOCKED_DEPENDENCY,
            RuleExecutionStatus.NOT_EVALUATED,
        }
        research_use_ready = (
            bool(findings)
            and not any(item.status in incomplete_statuses for item in evaluation_sequence)
            and not any(finding.blocks_research_use for finding in findings)
        )
        report_metadata = {
            **dict(config.metadata),
            "engine": {
                "version": ENGINE_VERSION,
                "rule_count": len(self._rules),
                "execution_order": list(self._execution_order),
                "registry_fingerprint": self.registry_fingerprint,
                "registry_manifest": list(self.registry_manifest),
                "execution_status_counts": execution_status_counts,
                "research_use_requested": config.research_use,
                "research_use_ready": research_use_ready,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": (completed_at - started_at).total_seconds(),
            },
            "rule_evaluations": [item.to_dict() for item in evaluation_sequence],
            "evidence_lineage": evidence_lineage,
        }
        report = InterpretationReport(
            report_id=config.report_id,
            pipeline_run_id=config.pipeline_run_id,
            module_name=config.module_name,
            findings=findings,
            evidence=current_catalog.values,
            generated_at=completed_at,
            schema_version=config.schema_version,
            engine_version=ENGINE_VERSION,
            metadata=report_metadata,
        )
        return EngineExecution(
            report=report,
            evaluations=evaluation_sequence,
            execution_order=self._execution_order,
            started_at=started_at,
            completed_at=completed_at,
        )