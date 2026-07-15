"""Deterministic, evidence-backed source attribution for root-cause analysis.

This module localizes a *selected causal candidate* within the simulator or
validation stack.  It does not select a candidate, determine final causal
status, or infer unsupported source locations.

Scientific invariants
---------------------
* Ranking is not attribution.
* Candidate metadata is never sufficient on its own; every concrete location
  must be backed by registered evidence.
* Conflicting locations are resolved conservatively to their deepest common,
  evidence-supported level, or to ``UNKNOWN`` when no common location exists.
* A successful verifier can strengthen confidence, but cannot invent a source
  location absent from its evidence.
* Insufficient precision is represented by a partial/unknown attribution, not
  by a technical exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from validation.root_cause.exceptions import AttributionError, RootCauseIntegrityError
from validation.root_cause.models import (
    AttributionLevel,
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    CausalConfidence,
    EvidenceDirection,
    EvidenceReference,
    SourceAttribution,
    VerificationOutcome,
    VerificationResult,
)

__all__ = [
    "AttributionContext",
    "AttributionDiagnostic",
    "AttributionDiagnosticCode",
    "AttributionEngine",
    "AttributionHint",
    "AttributionResult",
    "AttributionRule",
    "EvidenceMetadataRule",
    "attribute_source",
]


class AttributionDiagnosticCode(str, Enum):
    """Stable, machine-readable non-fatal attribution diagnostics."""

    NO_LOCATION_EVIDENCE = "no_location_evidence"
    CONFLICTING_HINTS = "conflicting_hints"
    RULE_NOT_APPLICABLE = "rule_not_applicable"
    RULE_FAILED = "rule_failed"
    CONTRADICTORY_EVIDENCE_IGNORED = "contradictory_evidence_ignored"
    UNVERIFIED_LOCATION = "unverified_location"


@dataclass(frozen=True, slots=True)
class AttributionDiagnostic:
    """Auditable non-fatal observation emitted during attribution."""

    code: AttributionDiagnosticCode
    message: str
    rule_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, AttributionDiagnosticCode):
            raise TypeError("code must be an AttributionDiagnosticCode.")
        message = _text(self.message, "message")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "rule_id", _optional_identifier(self.rule_id, "rule_id"))
        object.__setattr__(
            self, "evidence_ids", _identifier_tuple(self.evidence_ids, "evidence_ids")
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class AttributionHint:
    """One rule-emitted, evidence-backed source-location claim.

    Fields may be cumulative.  For example, a state-level hint may include both
    ``module`` and ``state``.  ``level`` identifies the most precise field the
    rule claims is supported.
    """

    level: AttributionLevel
    evidence_ids: tuple[str, ...]
    rationale: str
    rule_id: str
    component: str | None = None
    module: str | None = None
    state: str | None = None
    transition: str | None = None
    logic: str | None = None
    exporter: str | None = None
    metric: str | None = None
    configuration_key: str | None = None
    environment_key: str | None = None
    weight: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.level, AttributionLevel):
            raise TypeError("level must be an AttributionLevel.")
        if self.level is AttributionLevel.UNKNOWN:
            raise ValueError("AttributionHint cannot use UNKNOWN; emit no hint instead.")
        object.__setattr__(
            self, "evidence_ids", _identifier_tuple(self.evidence_ids, "evidence_ids", allow_empty=False)
        )
        object.__setattr__(self, "rationale", _text(self.rationale, "rationale"))
        object.__setattr__(self, "rule_id", _identifier(self.rule_id, "rule_id"))
        for name in _LOCATION_FIELDS:
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise TypeError("weight must be numeric.")
        weight = float(self.weight)
        if not 0.0 < weight <= 1.0:
            raise ValueError("weight must be in the interval (0, 1].")
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))
        required = _LEVEL_FIELD[self.level]
        if getattr(self, required) is None:
            raise ValueError(f"{self.level.value} hint requires {required}.")
        _validate_location_shape(self)


@dataclass(frozen=True, slots=True)
class AttributionContext:
    """Immutable input graph used by source-attribution rules."""

    candidate: CausalCandidate
    assessment: CandidateAssessment
    evidence: tuple[EvidenceReference, ...]
    verifications: tuple[VerificationResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CausalCandidate):
            raise TypeError("candidate must be a CausalCandidate.")
        if not isinstance(self.assessment, CandidateAssessment):
            raise TypeError("assessment must be a CandidateAssessment.")
        if self.assessment.candidate_id != self.candidate.id:
            raise RootCauseIntegrityError(
                "CandidateAssessment belongs to a different candidate.",
                context={
                    "candidate_id": self.candidate.id,
                    "assessment_candidate_id": self.assessment.candidate_id,
                },
            )
        evidence = _typed_tuple(self.evidence, EvidenceReference, "evidence")
        verifications = _typed_tuple(
            self.verifications, VerificationResult, "verifications"
        )
        _unique_ids(evidence, "evidence")
        _unique_ids(verifications, "verifications")
        for verification in verifications:
            if verification.candidate_id != self.candidate.id:
                raise RootCauseIntegrityError(
                    "VerificationResult belongs to a different candidate.",
                    context={
                        "candidate_id": self.candidate.id,
                        "verification_id": verification.id,
                        "verification_candidate_id": verification.candidate_id,
                    },
                )
        evidence_ids = {item.id for item in evidence}
        referenced = set(self.assessment.supporting_evidence_ids)
        referenced.update(self.assessment.contradictory_evidence_ids)
        for verification in verifications:
            referenced.update(verification.evidence_ids)
        missing = sorted(referenced - evidence_ids)
        if missing:
            raise RootCauseIntegrityError(
                "Attribution context is missing referenced evidence.",
                context={"missing_evidence_ids": missing},
            )
        object.__setattr__(self, "evidence", tuple(sorted(evidence, key=lambda item: item.id)))
        object.__setattr__(
            self,
            "verifications",
            tuple(sorted(verifications, key=lambda item: item.id)),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@runtime_checkable
class AttributionRule(Protocol):
    """Injectable rule that extracts source-location hints from evidence."""

    @property
    def rule_id(self) -> str:
        """Return a stable identifier used in diagnostics and provenance."""

    @property
    def priority(self) -> int:
        """Return deterministic execution priority; lower values run first."""

    def infer(self, context: AttributionContext) -> Sequence[AttributionHint]:
        """Return zero or more evidence-backed hints without side effects."""


@dataclass(frozen=True, slots=True)
class EvidenceMetadataRule:
    """Extract canonical provenance keys from evidence metadata.

    The rule intentionally recognizes a small, explicit vocabulary.  Unknown
    metadata keys are ignored rather than guessed.
    """

    rule_id: str = "attribution.evidence_metadata"
    priority: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _identifier(self.rule_id, "rule_id"))
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer.")

    def infer(self, context: AttributionContext) -> Sequence[AttributionHint]:
        supporting_ids = _effective_supporting_evidence_ids(context)
        hints: list[AttributionHint] = []
        for item in context.evidence:
            if item.id not in supporting_ids:
                continue
            location = _location_from_metadata(item.metadata)
            if not location:
                continue
            level = _most_precise_level(location)
            hints.append(
                AttributionHint(
                    level=level,
                    evidence_ids=(item.id,),
                    rationale=f"Evidence {item.id} records canonical source provenance.",
                    rule_id=self.rule_id,
                    weight=1.0 if item.direction is EvidenceDirection.SUPPORTS else 0.75,
                    **location,
                )
            )
        return tuple(hints)


@dataclass(frozen=True, slots=True)
class AttributionResult:
    """Attribution plus complete audit trail of accepted hints and diagnostics."""

    attribution: SourceAttribution
    hints: tuple[AttributionHint, ...] = ()
    diagnostics: tuple[AttributionDiagnostic, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.attribution, SourceAttribution):
            raise TypeError("attribution must be a SourceAttribution.")
        hints = _typed_tuple(self.hints, AttributionHint, "hints")
        diagnostics = _typed_tuple(
            self.diagnostics, AttributionDiagnostic, "diagnostics"
        )
        object.__setattr__(self, "hints", tuple(hints))
        object.__setattr__(self, "diagnostics", tuple(diagnostics))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


class AttributionEngine:
    """Conservative deterministic coordinator for source attribution."""

    def __init__(
        self,
        rules: Iterable[AttributionRule] | None = None,
        *,
        strict: bool = True,
    ) -> None:
        if not isinstance(strict, bool):
            raise TypeError("strict must be a bool.")
        supplied = tuple(rules) if rules is not None else (EvidenceMetadataRule(),)
        normalized: list[AttributionRule] = []
        seen: set[str] = set()
        for rule in supplied:
            if not isinstance(rule, AttributionRule):
                raise TypeError("Every attribution rule must implement AttributionRule.")
            rule_id = _identifier(rule.rule_id, "rule.rule_id")
            if rule_id in seen:
                raise ValueError(f"Duplicate attribution rule_id: {rule_id}.")
            if isinstance(rule.priority, bool) or not isinstance(rule.priority, int):
                raise TypeError(f"Rule {rule_id} priority must be an integer.")
            seen.add(rule_id)
            normalized.append(rule)
        self._rules = tuple(sorted(normalized, key=lambda r: (r.priority, r.rule_id)))
        self._strict = strict

    @property
    def rules(self) -> tuple[AttributionRule, ...]:
        return self._rules

    def attribute(self, context: AttributionContext) -> AttributionResult:
        if not isinstance(context, AttributionContext):
            raise TypeError("context must be an AttributionContext.")

        evidence_by_id = {item.id: item for item in context.evidence}
        diagnostics: list[AttributionDiagnostic] = []
        hints: list[AttributionHint] = []

        for rule in self._rules:
            try:
                emitted = rule.infer(context)
                if isinstance(emitted, (str, bytes)) or not isinstance(emitted, Sequence):
                    raise RootCauseIntegrityError(
                        "Attribution rule must return a sequence of AttributionHint objects.",
                        context={"rule_id": rule.rule_id},
                    )
                for hint in emitted:
                    if not isinstance(hint, AttributionHint):
                        raise RootCauseIntegrityError(
                            "Attribution rule emitted an invalid hint type.",
                            context={
                                "rule_id": rule.rule_id,
                                "type": type(hint).__name__,
                            },
                        )
                    if hint.rule_id != rule.rule_id:
                        raise RootCauseIntegrityError(
                            "Attribution hint rule_id does not match the emitting rule.",
                            context={
                                "emitting_rule_id": rule.rule_id,
                                "hint_rule_id": hint.rule_id,
                            },
                        )
                    missing = sorted(set(hint.evidence_ids) - evidence_by_id.keys())
                    if missing:
                        raise RootCauseIntegrityError(
                            "Attribution hint references unknown evidence.",
                            context={"rule_id": rule.rule_id, "missing_evidence_ids": missing},
                        )
                    invalid = [
                        evidence_id
                        for evidence_id in hint.evidence_ids
                        if evidence_by_id[evidence_id].direction
                        is EvidenceDirection.CONTRADICTS
                    ]
                    if invalid:
                        diagnostics.append(
                            AttributionDiagnostic(
                                code=AttributionDiagnosticCode.CONTRADICTORY_EVIDENCE_IGNORED,
                                message="A location hint backed by contradictory evidence was ignored.",
                                rule_id=rule.rule_id,
                                evidence_ids=tuple(sorted(invalid)),
                            )
                        )
                        continue
                    hints.append(hint)
            except (AttributionError, RootCauseIntegrityError):
                raise
            except Exception as exc:  # pragma: no cover - defensive collaborator boundary
                if self._strict:
                    raise AttributionError(
                        "Attribution rule execution failed.",
                        context={"rule_id": rule.rule_id, "error_type": type(exc).__name__},
                    ) from exc
                diagnostics.append(
                    AttributionDiagnostic(
                        code=AttributionDiagnosticCode.RULE_FAILED,
                        message=f"Rule {rule.rule_id} failed and was skipped.",
                        rule_id=rule.rule_id,
                        metadata={"error_type": type(exc).__name__, "error": str(exc)},
                    )
                )

        hints = _deduplicate_hints(hints)
        if not hints:
            diagnostics.append(
                AttributionDiagnostic(
                    code=AttributionDiagnosticCode.NO_LOCATION_EVIDENCE,
                    message="No evidence-backed source location could be established.",
                )
            )
            return AttributionResult(
                attribution=SourceAttribution(level=AttributionLevel.UNKNOWN),
                hints=(),
                diagnostics=tuple(diagnostics),
                metadata={"candidate_id": context.candidate.id},
            )

        resolved, conflict = _resolve_hints(hints)
        if conflict:
            diagnostics.append(
                AttributionDiagnostic(
                    code=AttributionDiagnosticCode.CONFLICTING_HINTS,
                    message="Conflicting source hints were reduced conservatively.",
                    evidence_ids=tuple(sorted({eid for hint in hints for eid in hint.evidence_ids})),
                    metadata={"resolved_level": resolved["level"].value},
                )
            )

        evidence_ids = tuple(sorted({eid for hint in hints for eid in hint.evidence_ids}))
        confidence = (
            CausalConfidence.NONE
            if resolved["level"] is AttributionLevel.UNKNOWN
            else _confidence(context, hints, conflict)
        )
        rationale = _rationale(resolved, hints, conflict)
        attribution = SourceAttribution(
            confidence=confidence,
            evidence_ids=evidence_ids,
            rationale=rationale,
            **resolved,
        )
        return AttributionResult(
            attribution=attribution,
            hints=tuple(hints),
            diagnostics=tuple(diagnostics),
            metadata={
                "candidate_id": context.candidate.id,
                "rule_ids": tuple(sorted({hint.rule_id for hint in hints})),
            },
        )


def attribute_source(
    *,
    candidate: CausalCandidate,
    assessment: CandidateAssessment,
    evidence: Sequence[EvidenceReference],
    verifications: Sequence[VerificationResult] = (),
    rules: Iterable[AttributionRule] | None = None,
    strict: bool = True,
    metadata: Mapping[str, Any] | None = None,
) -> AttributionResult:
    """Functional API for deterministic source attribution."""

    context = AttributionContext(
        candidate=candidate,
        assessment=assessment,
        evidence=tuple(evidence),
        verifications=tuple(verifications),
        metadata={} if metadata is None else metadata,
    )
    return AttributionEngine(rules=rules, strict=strict).attribute(context)


_LOCATION_FIELDS = (
    "component",
    "module",
    "state",
    "transition",
    "logic",
    "exporter",
    "metric",
    "configuration_key",
    "environment_key",
)

_LEVEL_FIELD = {
    AttributionLevel.COMPONENT: "component",
    AttributionLevel.MODULE: "module",
    AttributionLevel.STATE: "state",
    AttributionLevel.TRANSITION: "transition",
    AttributionLevel.LOGIC: "logic",
    AttributionLevel.EXPORTER: "exporter",
    AttributionLevel.METRIC: "metric",
    AttributionLevel.CONFIGURATION: "configuration_key",
    AttributionLevel.ENVIRONMENT: "environment_key",
}

_LEVEL_SPECIFICITY = {
    AttributionLevel.COMPONENT: 1,
    AttributionLevel.MODULE: 2,
    AttributionLevel.STATE: 3,
    AttributionLevel.TRANSITION: 4,
    AttributionLevel.LOGIC: 4,
    AttributionLevel.EXPORTER: 2,
    AttributionLevel.METRIC: 2,
    AttributionLevel.CONFIGURATION: 2,
    AttributionLevel.ENVIRONMENT: 2,
}

_METADATA_ALIASES = {
    "component": ("component", "source_component"),
    "module": ("module", "source_module", "module_name", "module_path"),
    "state": ("state", "source_state", "state_name"),
    "transition": ("transition", "source_transition", "transition_type"),
    "logic": ("logic", "source_logic", "logic_type"),
    "exporter": ("exporter", "exporter_name", "export_format"),
    "metric": ("metric", "metric_name", "metric_id"),
    "configuration_key": ("configuration_key", "config_key"),
    "environment_key": ("environment_key", "env_key"),
}


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty.")
    return value


def _optional_text(value: str | None, field_name: str) -> str | None:
    return None if value is None else _text(value, field_name)


def _identifier(value: str, field_name: str) -> str:
    value = _text(value, field_name)
    if not all(ch.isalnum() or ch in "._:-" for ch in value):
        raise ValueError(f"{field_name} contains unsupported characters.")
    return value


def _optional_identifier(value: str | None, field_name: str) -> str | None:
    return None if value is None else _identifier(value, field_name)


def _identifier_tuple(
    values: Iterable[str], field_name: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of identifiers.")
    normalized = tuple(sorted({_identifier(value, field_name) for value in values}))
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})


def _typed_tuple(values: Iterable[Any], expected: type[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable.")
    result = tuple(values)
    for value in result:
        if not isinstance(value, expected):
            raise TypeError(f"{field_name} must contain only {expected.__name__} objects.")
    return result


def _unique_ids(values: Sequence[Any], field_name: str) -> None:
    ids = [value.id for value in values]
    if len(ids) != len(set(ids)):
        raise RootCauseIntegrityError(
            f"{field_name} contains duplicate IDs.", context={"ids": ids}
        )


def _validate_location_shape(hint: AttributionHint) -> None:
    if hint.level is AttributionLevel.MODULE and hint.state is not None:
        raise ValueError("A module-level hint cannot claim a state.")
    if hint.level is AttributionLevel.COMPONENT and any(
        getattr(hint, name) is not None for name in _LOCATION_FIELDS if name != "component"
    ):
        raise ValueError("A component-level hint cannot contain a more precise location.")
    branch_fields = {
        AttributionLevel.EXPORTER: "exporter",
        AttributionLevel.METRIC: "metric",
        AttributionLevel.CONFIGURATION: "configuration_key",
        AttributionLevel.ENVIRONMENT: "environment_key",
    }
    if hint.level in branch_fields:
        allowed = {"component", branch_fields[hint.level]}
        unexpected = [
            name for name in _LOCATION_FIELDS if name not in allowed and getattr(hint, name) is not None
        ]
        if unexpected:
            raise ValueError(
                f"{hint.level.value} hint contains incompatible fields: {unexpected}."
            )


def _effective_supporting_evidence_ids(context: AttributionContext) -> set[str]:
    supporting = set(context.assessment.supporting_evidence_ids)
    for verification in context.verifications:
        if verification.outcome is VerificationOutcome.PASSED:
            supporting.update(verification.evidence_ids)
    # Neutral provenance may localize a source without supporting causal direction.
    supporting.update(
        item.id
        for item in context.evidence
        if item.related_candidate_id in (None, context.candidate.id)
        and item.direction is EvidenceDirection.NEUTRAL
    )
    return supporting


def _location_from_metadata(metadata: Mapping[str, Any]) -> dict[str, str]:
    location: dict[str, str] = {}
    for canonical, aliases in _METADATA_ALIASES.items():
        found: set[str] = set()
        for alias in aliases:
            value = metadata.get(alias)
            if value is not None:
                found.add(_text(value, f"metadata[{alias!r}]") if isinstance(value, str) else str(value))
        if len(found) > 1:
            raise RootCauseIntegrityError(
                "Evidence metadata contains conflicting aliases for one location field.",
                context={"field": canonical, "values": sorted(found)},
            )
        if found:
            location[canonical] = next(iter(found))
    return location


def _most_precise_level(location: Mapping[str, str]) -> AttributionLevel:
    precedence = (
        ("transition", AttributionLevel.TRANSITION),
        ("logic", AttributionLevel.LOGIC),
        ("state", AttributionLevel.STATE),
        ("module", AttributionLevel.MODULE),
        ("exporter", AttributionLevel.EXPORTER),
        ("metric", AttributionLevel.METRIC),
        ("configuration_key", AttributionLevel.CONFIGURATION),
        ("environment_key", AttributionLevel.ENVIRONMENT),
        ("component", AttributionLevel.COMPONENT),
    )
    for field_name, level in precedence:
        if field_name in location:
            return level
    raise RootCauseIntegrityError("Location metadata did not contain a recognized field.")


def _deduplicate_hints(hints: Sequence[AttributionHint]) -> list[AttributionHint]:
    by_key: dict[tuple[Any, ...], AttributionHint] = {}
    for hint in hints:
        key = (
            hint.level,
            *(getattr(hint, name) for name in _LOCATION_FIELDS),
            hint.evidence_ids,
            hint.rule_id,
        )
        existing = by_key.get(key)
        if existing is None or hint.weight > existing.weight:
            by_key[key] = hint
    return sorted(
        by_key.values(),
        key=lambda hint: (
            -_LEVEL_SPECIFICITY[hint.level],
            tuple(getattr(hint, name) or "" for name in _LOCATION_FIELDS),
            hint.rule_id,
            hint.evidence_ids,
        ),
    )


def _resolve_hints(hints: Sequence[AttributionHint]) -> tuple[dict[str, Any], bool]:
    # Attribution branches are not globally ordered.  A GMF state and an
    # exporter, for example, are competing locations rather than different
    # levels of the same path.  Resolve cross-branch evidence only to a common
    # component; otherwise remain UNKNOWN.
    branches = {_branch_for_level(hint.level) for hint in hints}
    non_component_branches = branches - {"component"}
    if len(non_component_branches) > 1:
        components = {hint.component for hint in hints if hint.component is not None}
        if len(components) == 1:
            return {
                "level": AttributionLevel.COMPONENT,
                "component": next(iter(components)),
            }, True
        return {"level": AttributionLevel.UNKNOWN}, True

    # Prefer the deepest location within one branch.  Lower-level hints remain
    # corroborating context but cannot override a more precise consistent hint.
    max_specificity = max(_LEVEL_SPECIFICITY[hint.level] for hint in hints)
    deepest = [hint for hint in hints if _LEVEL_SPECIFICITY[hint.level] == max_specificity]
    fields: dict[str, str] = {}
    conflict = False
    for name in _LOCATION_FIELDS:
        values = {getattr(hint, name) for hint in deepest if getattr(hint, name) is not None}
        if len(values) == 1:
            fields[name] = next(iter(values))
        elif len(values) > 1:
            conflict = True

    if not conflict:
        level = max((hint.level for hint in deepest), key=lambda level: _LEVEL_SPECIFICITY[level])
        required = _LEVEL_FIELD[level]
        if required in fields:
            return {"level": level, **fields}, False

    # Conservative common ancestor for the GMF branch.
    for name, level in (
        ("state", AttributionLevel.STATE),
        ("module", AttributionLevel.MODULE),
        ("component", AttributionLevel.COMPONENT),
    ):
        values = {getattr(hint, name) for hint in hints if getattr(hint, name) is not None}
        if len(values) == 1:
            value = next(iter(values))
            allowed = {"component"}
            if level in (AttributionLevel.MODULE, AttributionLevel.STATE):
                allowed.add("module")
            if level is AttributionLevel.STATE:
                allowed.add("state")
            resolved = {
                field: next(iter({getattr(h, field) for h in hints if getattr(h, field) is not None}), None)
                for field in allowed
            }
            resolved = {key: val for key, val in resolved.items() if val is not None}
            resolved[name] = value
            return {"level": level, **resolved}, True

    return {"level": AttributionLevel.UNKNOWN}, True



def _branch_for_level(level: AttributionLevel) -> str:
    if level in {
        AttributionLevel.MODULE,
        AttributionLevel.STATE,
        AttributionLevel.TRANSITION,
        AttributionLevel.LOGIC,
    }:
        return "gmf"
    if level is AttributionLevel.COMPONENT:
        return "component"
    return level.value

def _confidence(
    context: AttributionContext, hints: Sequence[AttributionHint], conflict: bool
) -> CausalConfidence:
    if conflict:
        return CausalConfidence.LOW
    distinct_evidence = {eid for hint in hints for eid in hint.evidence_ids}
    passed = any(v.outcome is VerificationOutcome.PASSED for v in context.verifications)
    supported = context.candidate.status is CandidateStatus.SUPPORTED
    if passed and supported and len(distinct_evidence) >= 2:
        return CausalConfidence.VERY_HIGH
    if passed or (supported and len(distinct_evidence) >= 2):
        return CausalConfidence.HIGH
    if len(distinct_evidence) >= 2:
        return CausalConfidence.MODERATE
    return CausalConfidence.LOW


def _rationale(
    resolved: Mapping[str, Any], hints: Sequence[AttributionHint], conflict: bool
) -> str:
    level = resolved["level"]
    if level is AttributionLevel.UNKNOWN:
        return "Conflicting evidence did not support a common source location."
    field_name = _LEVEL_FIELD[level]
    value = resolved[field_name]
    prefix = "Conflicting hints were reduced to" if conflict else "Evidence localized the source to"
    return (
        f"{prefix} {level.value} '{value}' using {len(hints)} "
        f"evidence-backed attribution hint(s)."
    )