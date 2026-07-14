"""Deterministic consolidation of scientific validation recommendations.

The interpretation rules attach concrete recommendations to individual findings.
This module turns those distributed recommendations into one immutable action
plan without changing the scientific findings that produced them.

Scientific safety rules
-----------------------

* Original :class:`Recommendation` objects remain unchanged and traceable.
* Consolidation is allowed only for semantically identical actions.
* Priority and blocking status may only escalate, never be weakened.
* Conflicting owners are preserved explicitly instead of selecting one silently.
* A recommendation from a hidden or filtered report is never invented here;
  the complete :class:`EngineExecution` is the source of truth.
* Incomplete rule evaluations are represented as explicit review actions because
  missing analysis cannot be treated as absence of required work.
* Ordering and fingerprints are deterministic.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from re import sub
from types import MappingProxyType
from typing import Any, Final

from validation.interpretation.engine import EngineExecution
from validation.interpretation.models import (
    FindingStatus,
    InterpretationFinding,
    Recommendation,
    RecommendationPriority,
    Severity,
)
from validation.interpretation.rules.base import RuleEvaluation, RuleExecutionStatus

__all__ = [
    "ActionPlanConfiguration",
    "ActionPlanItem",
    "RecommendationPlan",
    "build_recommendation_plan",
]

_PRIORITY_RANK: Final = {
    RecommendationPriority.LOW: 0,
    RecommendationPriority.MEDIUM: 1,
    RecommendationPriority.HIGH: 2,
    RecommendationPriority.URGENT: 3,
}
_STATUS_RANK: Final = {
    FindingStatus.NOT_APPLICABLE: 0,
    FindingStatus.NOT_EVALUATED: 1,
    FindingStatus.PASS: 2,
    FindingStatus.WARNING: 3,
    FindingStatus.INCONCLUSIVE: 4,
    FindingStatus.FAIL: 5,
}
_SEVERITY_RANK: Final = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MODERATE: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}
_INCOMPLETE_STATUSES: Final = frozenset(
    {
        RuleExecutionStatus.INSUFFICIENT_EVIDENCE,
        RuleExecutionStatus.BLOCKED_DEPENDENCY,
        RuleExecutionStatus.NOT_EVALUATED,
    }
)
_SPACE_PATTERN: Final = r"\s+"


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _canonical_text(value: str) -> str:
    """Return a conservative key for exact semantic-action consolidation.

    Only case, surrounding whitespace and repeated whitespace are normalized.
    Punctuation and wording remain significant to avoid merging distinct actions.
    """

    return sub(_SPACE_PATTERN, " ", value.strip()).casefold()


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


def _canonical_json(value: Any) -> bytes:
    def normalize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): normalize(item[key]) for key in sorted(item, key=str)}
        if isinstance(item, (set, frozenset)):
            normalized = [normalize(value) for value in item]
            return sorted(normalized, key=lambda value: dumps(value, sort_keys=True))
        if isinstance(item, (tuple, list)):
            return [normalize(value) for value in item]
        return item

    return dumps(
        normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class ActionPlanConfiguration:
    """Presentation policy for building a recommendation action plan."""

    include_low_priority: bool = True
    include_non_blocking: bool = True
    include_incomplete_rule_actions: bool = True
    maximum_items: int | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "include_low_priority",
            "include_non_blocking",
            "include_incomplete_rule_actions",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool.")
        if self.maximum_items is not None:
            if isinstance(self.maximum_items, bool) or not isinstance(self.maximum_items, int):
                raise TypeError("maximum_items must be an integer or None.")
            if self.maximum_items < 1:
                raise ValueError("maximum_items must be at least 1 when provided.")


@dataclass(frozen=True, slots=True)
class ActionPlanItem:
    """One consolidated, traceable and executable validation action."""

    action_id: str
    action: str
    priority: RecommendationPriority
    blocking: bool
    rationales: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    verification_steps: tuple[str, ...]
    owners: tuple[str, ...]
    source_finding_ids: tuple[str, ...]
    source_rule_ids: tuple[str, ...]
    source_recommendation_ids: tuple[str, ...]
    related_hypothesis_ids: tuple[str, ...] = ()
    incomplete_rule_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _text(self.action_id, "action_id"))
        object.__setattr__(self, "action", _text(self.action, "action"))
        if not isinstance(self.priority, RecommendationPriority):
            raise TypeError("priority must be a RecommendationPriority member.")
        if not isinstance(self.blocking, bool):
            raise TypeError("blocking must be a bool.")

        for field_name in (
            "rationales",
            "expected_outcomes",
            "verification_steps",
            "owners",
            "source_finding_ids",
            "source_rule_ids",
            "source_recommendation_ids",
            "related_hypothesis_ids",
            "incomplete_rule_ids",
        ):
            values = tuple(_text(item, f"{field_name} item") for item in getattr(self, field_name))
            values = tuple(dict.fromkeys(values))
            object.__setattr__(self, field_name, values)

        if not self.rationales:
            raise ValueError("rationales must not be empty.")
        if not self.expected_outcomes:
            raise ValueError("expected_outcomes must not be empty.")
        if not self.verification_steps:
            raise ValueError("verification_steps must not be empty.")
        if not self.source_recommendation_ids and not self.incomplete_rule_ids:
            raise ValueError(
                "An action item must reference recommendations or incomplete rules."
            )
        if bool(self.source_recommendation_ids) != bool(self.source_finding_ids):
            raise ValueError(
                "Recommendation-derived actions must reference both findings and recommendations."
            )
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))

    @property
    def has_owner_conflict(self) -> bool:
        return len(self.owners) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action,
            "priority": self.priority.value,
            "blocking": self.blocking,
            "rationales": list(self.rationales),
            "expected_outcomes": list(self.expected_outcomes),
            "verification_steps": list(self.verification_steps),
            "owners": list(self.owners),
            "owner_conflict": self.has_owner_conflict,
            "source_finding_ids": list(self.source_finding_ids),
            "source_rule_ids": list(self.source_rule_ids),
            "source_recommendation_ids": list(self.source_recommendation_ids),
            "related_hypothesis_ids": list(self.related_hypothesis_ids),
            "incomplete_rule_ids": list(self.incomplete_rule_ids),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RecommendationPlan:
    """Immutable action plan derived from one complete engine execution."""

    report_id: str
    pipeline_run_id: str
    module_name: str | None
    items: tuple[ActionPlanItem, ...]
    source_recommendation_count: int
    candidate_item_count: int
    omitted_item_count: int
    incomplete_rule_count: int
    configuration: ActionPlanConfiguration
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", _text(self.report_id, "report_id"))
        object.__setattr__(self, "pipeline_run_id", _text(self.pipeline_run_id, "pipeline_run_id"))
        if self.module_name is not None:
            object.__setattr__(self, "module_name", _text(self.module_name, "module_name"))
        items = tuple(self.items)
        if not all(isinstance(item, ActionPlanItem) for item in items):
            raise TypeError("items must contain ActionPlanItem values only.")
        ids = [item.action_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("items must not contain duplicate action identifiers.")
        object.__setattr__(self, "items", items)
        for field_name in (
            "source_recommendation_count",
            "candidate_item_count",
            "omitted_item_count",
            "incomplete_rule_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        if self.candidate_item_count < len(self.items):
            raise ValueError("candidate_item_count cannot be smaller than the retained item count.")
        if self.omitted_item_count != self.candidate_item_count - len(self.items):
            raise ValueError(
                "omitted_item_count must equal candidate_item_count minus retained items."
            )
        if not isinstance(self.configuration, ActionPlanConfiguration):
            raise TypeError("configuration must be an ActionPlanConfiguration.")
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))

    @property
    def blocking_items(self) -> tuple[ActionPlanItem, ...]:
        return tuple(item for item in self.items if item.blocking)

    @property
    def owner_conflicts(self) -> tuple[ActionPlanItem, ...]:
        return tuple(item for item in self.items if item.has_owner_conflict)

    @property
    def priority_counts(self) -> Mapping[str, int]:
        counts = {priority.value: 0 for priority in RecommendationPriority}
        for item in self.items:
            counts[item.priority.value] += 1
        return MappingProxyType(counts)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict(include_fingerprint=False))

    def to_dict(self, *, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "schema": "psynthea.interpretation.recommendation_plan",
            "schema_version": "1.1.0",
            "report_id": self.report_id,
            "pipeline_run_id": self.pipeline_run_id,
            "module_name": self.module_name,
            "source_recommendation_count": self.source_recommendation_count,
            "candidate_item_count": self.candidate_item_count,
            "omitted_item_count": self.omitted_item_count,
            "has_omitted_actions": self.omitted_item_count > 0,
            "incomplete_rule_count": self.incomplete_rule_count,
            "item_count": len(self.items),
            "blocking_item_count": len(self.blocking_items),
            "owner_conflict_count": len(self.owner_conflicts),
            "priority_counts": dict(self.priority_counts),
            "items": [item.to_dict() for item in self.items],
            "configuration": {
                "include_low_priority": self.configuration.include_low_priority,
                "include_non_blocking": self.configuration.include_non_blocking,
                "include_incomplete_rule_actions": self.configuration.include_incomplete_rule_actions,
                "maximum_items": self.configuration.maximum_items,
            },
            "metadata": dict(self.metadata),
        }
        if include_fingerprint:
            payload["fingerprint"] = _fingerprint(payload)
        return payload


@dataclass(slots=True)
class _Accumulator:
    action: str
    priority: RecommendationPriority
    blocking: bool
    rationales: list[str] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    verification_steps: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    source_finding_ids: list[str] = field(default_factory=list)
    source_rule_ids: list[str] = field(default_factory=list)
    source_recommendation_ids: list[str] = field(default_factory=list)
    related_hypothesis_ids: list[str] = field(default_factory=list)
    source_statuses: list[FindingStatus] = field(default_factory=list)
    source_severities: list[Severity] = field(default_factory=list)
    source_blocks_research_use: bool = False


def _append_unique(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _recommendation_sort_key(item: ActionPlanItem) -> tuple[Any, ...]:
    return (
        0 if item.blocking else 1,
        -_PRIORITY_RANK[item.priority],
        item.action.casefold(),
        item.action_id,
    )


def _action_id(action: str, source_type: str = "recommendation") -> str:
    digest = sha256(f"{source_type}:{_canonical_text(action)}".encode("utf-8")).hexdigest()[:16]
    return f"ACTION.{digest.upper()}"


def _build_incomplete_action(evaluation: RuleEvaluation) -> ActionPlanItem:
    status = evaluation.status.value.replace("_", " ")
    action = f"Complete or resolve validation rule {evaluation.rule_id}."
    reasons = [f"Rule execution ended with status '{evaluation.status.value}'."]
    reasons.extend(item.reason for item in evaluation.stages if item.status.value != "completed")
    reasons.extend(item.reason for item in evaluation.dependencies if not item.satisfied)
    reasons.extend(item.reason for item in evaluation.requirements if not item.satisfied)
    reasons = list(dict.fromkeys(reasons))
    return ActionPlanItem(
        action_id=_action_id(action, "incomplete-rule"),
        action=action,
        priority=(
            RecommendationPriority.URGENT
            if evaluation.status is RuleExecutionStatus.BLOCKED_DEPENDENCY
            else RecommendationPriority.HIGH
        ),
        blocking=True,
        rationales=tuple(reasons),
        expected_outcomes=(
            f"Rule {evaluation.rule_id} reaches COMPLETED or NOT_APPLICABLE with an auditable evaluation.",
        ),
        verification_steps=(
            f"Re-run the interpretation engine and confirm rule {evaluation.rule_id} no longer has status {evaluation.status.value}.",
        ),
        owners=(),
        source_finding_ids=(),
        source_rule_ids=(evaluation.rule_id,),
        source_recommendation_ids=(),
        incomplete_rule_ids=(evaluation.rule_id,),
        metadata={"source_execution_status": status},
    )


def build_recommendation_plan(
    execution: EngineExecution,
    *,
    configuration: ActionPlanConfiguration | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RecommendationPlan:
    """Build a deterministic action plan from all findings in an engine execution."""

    if not isinstance(execution, EngineExecution):
        raise TypeError("execution must be an EngineExecution.")
    config = configuration or ActionPlanConfiguration()
    if not isinstance(config, ActionPlanConfiguration):
        raise TypeError("configuration must be an ActionPlanConfiguration or None.")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None.")

    accumulators: dict[str, _Accumulator] = {}
    source_count = 0
    seen_recommendation_ids: dict[str, str] = {}
    for finding in execution.report.findings:
        if not isinstance(finding, InterpretationFinding):
            raise TypeError("execution report contains a non-InterpretationFinding value.")
        for recommendation in finding.recommendations:
            previous_finding = seen_recommendation_ids.get(recommendation.recommendation_id)
            if previous_finding is not None:
                raise ValueError(
                    "Recommendation identifier "
                    f"{recommendation.recommendation_id!r} is reused by findings "
                    f"{previous_finding!r} and {finding.finding_id!r}; global provenance "
                    "would be ambiguous."
                )
            seen_recommendation_ids[recommendation.recommendation_id] = finding.finding_id
            source_count += 1
            key = _canonical_text(recommendation.action)
            accumulator = accumulators.get(key)
            if accumulator is None:
                accumulator = _Accumulator(
                    action=_text(recommendation.action, "recommendation.action"),
                    priority=recommendation.priority,
                    blocking=(recommendation.blocking or finding.blocks_research_use),
                )
                accumulators[key] = accumulator
            else:
                if _PRIORITY_RANK[recommendation.priority] > _PRIORITY_RANK[accumulator.priority]:
                    accumulator.priority = recommendation.priority
                accumulator.blocking = (
                    accumulator.blocking
                    or recommendation.blocking
                    or finding.blocks_research_use
                )

            _append_unique(accumulator.rationales, (recommendation.rationale,))
            _append_unique(accumulator.expected_outcomes, (recommendation.expected_outcome,))
            _append_unique(accumulator.verification_steps, (recommendation.verification,))
            if recommendation.owner is not None:
                _append_unique(accumulator.owners, (recommendation.owner,))
            _append_unique(accumulator.source_finding_ids, (finding.finding_id,))
            _append_unique(accumulator.source_rule_ids, (finding.rule_id,))
            _append_unique(
                accumulator.source_recommendation_ids,
                (recommendation.recommendation_id,),
            )
            _append_unique(
                accumulator.related_hypothesis_ids,
                tuple(
                    f"{finding.finding_id}:{hypothesis_id}"
                    for hypothesis_id in recommendation.related_hypothesis_ids
                ),
            )
            accumulator.source_statuses.append(finding.status)
            accumulator.source_severities.append(finding.severity)
            accumulator.source_blocks_research_use = (
                accumulator.source_blocks_research_use or finding.blocks_research_use
            )

    items: list[ActionPlanItem] = []
    for accumulator in accumulators.values():
        effective_priority = accumulator.priority
        if accumulator.blocking and _PRIORITY_RANK[effective_priority] < _PRIORITY_RANK[RecommendationPriority.HIGH]:
            effective_priority = RecommendationPriority.HIGH
        item = ActionPlanItem(
            action_id=_action_id(accumulator.action),
            action=accumulator.action,
            priority=effective_priority,
            blocking=accumulator.blocking,
            rationales=tuple(accumulator.rationales),
            expected_outcomes=tuple(accumulator.expected_outcomes),
            verification_steps=tuple(accumulator.verification_steps),
            owners=tuple(accumulator.owners),
            source_finding_ids=tuple(accumulator.source_finding_ids),
            source_rule_ids=tuple(accumulator.source_rule_ids),
            source_recommendation_ids=tuple(accumulator.source_recommendation_ids),
            related_hypothesis_ids=tuple(accumulator.related_hypothesis_ids),
            metadata={
                "highest_source_status": max(
                    accumulator.source_statuses, key=_STATUS_RANK.__getitem__
                ).value,
                "highest_source_severity": max(
                    accumulator.source_severities, key=_SEVERITY_RANK.__getitem__
                ).value,
                "source_occurrence_count": len(accumulator.source_recommendation_ids),
                "source_blocks_research_use": accumulator.source_blocks_research_use,
            },
        )
        if not config.include_low_priority and item.priority is RecommendationPriority.LOW:
            continue
        if not config.include_non_blocking and not item.blocking:
            continue
        items.append(item)

    incomplete = tuple(
        evaluation
        for evaluation in execution.evaluations
        if evaluation.status in _INCOMPLETE_STATUSES
    )
    if config.include_incomplete_rule_actions:
        items.extend(_build_incomplete_action(evaluation) for evaluation in incomplete)

    items.sort(key=_recommendation_sort_key)
    candidate_item_count = len(items)
    if config.maximum_items is not None:
        items = items[: config.maximum_items]
    omitted_item_count = candidate_item_count - len(items)

    plan_metadata = dict(metadata or {})
    reserved = {"source_report_id", "execution_fingerprint"}.intersection(plan_metadata)
    if reserved:
        raise ValueError(
            "metadata contains recommendation-plan reserved keys: "
            + ", ".join(sorted(reserved))
        )
    plan_metadata["source_report_id"] = execution.report.report_id
    engine_metadata = execution.report.metadata.get("engine", {})
    if isinstance(engine_metadata, Mapping) and "registry_fingerprint" in engine_metadata:
        plan_metadata["execution_fingerprint"] = engine_metadata["registry_fingerprint"]
    _canonical_json(plan_metadata)

    return RecommendationPlan(
        report_id=execution.report.report_id,
        pipeline_run_id=execution.report.pipeline_run_id,
        module_name=execution.report.module_name,
        items=tuple(items),
        source_recommendation_count=source_count,
        candidate_item_count=candidate_item_count,
        omitted_item_count=omitted_item_count,
        incomplete_rule_count=len(incomplete),
        configuration=config,
        metadata=plan_metadata,
    )