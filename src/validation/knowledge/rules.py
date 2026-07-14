"""Deterministic candidate rules backed by validated Phase 2A knowledge.

A rule is a machine-readable applicability predicate for causal knowledge that
has already been demonstrated through an evidence-backed investigation.  Rules
do not parse narrative ``detection_pattern`` text, infer new causes, alter
confidence, or convert a match into a causal conclusion.

Only active ``VALIDATED`` knowledge with ``CONFIRMED`` causal certainty may be
exposed through this layer.  Evaluation returns auditable candidates; the later
interpretation layer must still inspect the knowledge entry's evidence,
applicability and limitations before presenting a conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from validation.knowledge.models import (
    CausalCertainty,
    DetectionSignal,
    KnowledgeEntry,
    KnowledgeEntryStatus,
)
from validation.knowledge.taxonomy import CANONICAL_TAXONOMY, TaxonomyCatalog

__all__ = [
    "DuplicateRuleError",
    "InvalidRuleError",
    "KnowledgeRule",
    "RuleCatalog",
    "RuleCondition",
    "RuleMatch",
    "RuleOperator",
    "UnknownRuleError",
]


class InvalidRuleError(ValueError):
    """Raised when a rule violates the validated-knowledge contract."""


class DuplicateRuleError(InvalidRuleError):
    """Raised when a rule identifier is declared more than once."""


class UnknownRuleError(LookupError):
    """Raised when strict rule lookup cannot resolve an identifier."""


class RuleOperator(str, Enum):
    """Deterministic comparisons supported by Phase 2A rules."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    EXISTS = "exists"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"


_IDENTIFIER_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_PATH_SEGMENT_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_STRUCTURED_ROOTS = frozenset(
    {"domain", "finding_id", "metric_id", "observed_value", "source", "metadata"}
)
_ORDERED_OPERATORS = frozenset(
    {
        RuleOperator.GREATER_THAN,
        RuleOperator.GREATER_OR_EQUAL,
        RuleOperator.LESS_THAN,
        RuleOperator.LESS_OR_EQUAL,
    }
)
_MISSING = object()


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_identifier(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _model_tuple(
    values: Sequence[Any], expected_type: type[Any], field_name: str
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(
            f"{field_name} must be a sequence of {expected_type.__name__} values."
        )
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name}[{index}] must be {expected_type.__name__}, "
                f"got {type(value).__name__}."
            )
    return normalized


def _identifier_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of identifiers.")
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_identifier(value, f"{field_name}[{index}]")
        if item not in seen:
            result.append(item)
            seen.add(item)
    return tuple(result)


def _require_numeric(value: Any, field_name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRuleError(f"{field_name} must be a finite number.")
    if not isfinite(float(value)):
        raise InvalidRuleError(f"{field_name} must be finite.")
    return value


def _normalize_membership_value(value: Any, operator: RuleOperator) -> tuple[Any, ...] | frozenset[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(
        value, (Sequence, set, frozenset)
    ):
        raise InvalidRuleError(
            f"{operator.value} requires a non-string sequence or set value."
        )
    if not value:
        raise InvalidRuleError(f"{operator.value} requires at least one candidate value.")
    frozen = _freeze(value)
    return frozen if isinstance(frozen, (tuple, frozenset)) else tuple(frozen)


def _validate_path(path: str) -> str:
    normalized = _require_text(path, "field")
    parts = normalized.split(".")
    if parts[0] not in _STRUCTURED_ROOTS:
        raise InvalidRuleError(
            f"Unsupported rule field {parts[0]!r}; rules may only use structured signal data."
        )
    if len(parts) > 1 and parts[0] != "metadata":
        raise InvalidRuleError("Nested paths are only supported below metadata.")
    if any(not _PATH_SEGMENT_PATTERN.fullmatch(part) for part in parts):
        raise InvalidRuleError(f"Invalid rule field path {normalized!r}.")
    return normalized


def _resolve_path(signal: DetectionSignal, path: str) -> Any:
    parts = path.split(".")
    value: Any = getattr(signal, parts[0])
    for part in parts[1:]:
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _ordered_match(actual: Any, expected: int | float, operator: RuleOperator) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    if not isfinite(float(actual)):
        return False
    if operator is RuleOperator.GREATER_THAN:
        return actual > expected
    if operator is RuleOperator.GREATER_OR_EQUAL:
        return actual >= expected
    if operator is RuleOperator.LESS_THAN:
        return actual < expected
    return actual <= expected


@dataclass(frozen=True, slots=True)
class RuleCondition:
    """One explicit predicate over structured ``DetectionSignal`` data.

    Supported paths are direct structured fields such as ``domain`` or
    ``metric_id`` and nested metadata paths such as ``metadata.table_name``.
    Narrative fields are deliberately excluded because free-text matching is not
    a scientifically stable causal rule.
    """

    id: str
    field: str
    operator: RuleOperator
    value: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "field", _validate_path(self.field))
        if not isinstance(self.operator, RuleOperator):
            raise TypeError("operator must be a RuleOperator member.")

        if self.operator is RuleOperator.EXISTS:
            if not isinstance(self.value, bool):
                raise InvalidRuleError("exists requires a boolean value.")
        elif self.operator in {RuleOperator.IN, RuleOperator.NOT_IN}:
            object.__setattr__(
                self, "value", _normalize_membership_value(self.value, self.operator)
            )
        elif self.operator in _ORDERED_OPERATORS:
            object.__setattr__(
                self, "value", _require_numeric(self.value, self.operator.value)
            )
        else:
            object.__setattr__(self, "value", _freeze(self.value))

    def matches(self, signal: DetectionSignal) -> bool:
        """Evaluate this condition without coercion or free-text normalization."""

        if not isinstance(signal, DetectionSignal):
            raise TypeError("signal must be a DetectionSignal.")
        actual = _resolve_path(signal, self.field)

        if self.operator is RuleOperator.EXISTS:
            return (actual is not _MISSING and actual is not None) is self.value
        if actual is _MISSING:
            return False
        if self.operator is RuleOperator.EQUALS:
            return actual == self.value
        if self.operator is RuleOperator.NOT_EQUALS:
            return actual != self.value
        if self.operator is RuleOperator.IN:
            return actual in self.value
        if self.operator is RuleOperator.NOT_IN:
            return actual not in self.value
        if self.operator is RuleOperator.CONTAINS:
            try:
                return self.value in actual
            except (TypeError, AttributeError):
                return False
        return _ordered_match(actual, self.value, self.operator)


@dataclass(frozen=True, slots=True)
class KnowledgeRule:
    """Auditable conjunction of conditions linked to one knowledge entry."""

    id: str
    knowledge_entry_id: str
    conditions: tuple[RuleCondition, ...]
    domain_ids: tuple[str, ...]
    rationale: str
    priority: int = 100
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self,
            "knowledge_entry_id",
            _require_identifier(self.knowledge_entry_id, "knowledge_entry_id"),
        )
        conditions = _model_tuple(self.conditions, RuleCondition, "conditions")
        if not conditions:
            raise InvalidRuleError("KnowledgeRule requires at least one condition.")
        condition_ids = [condition.id for condition in conditions]
        if len(condition_ids) != len(set(condition_ids)):
            raise InvalidRuleError("conditions contains duplicate identifiers.")
        object.__setattr__(self, "conditions", conditions)

        domains = _identifier_tuple(self.domain_ids, "domain_ids")
        if not domains:
            raise InvalidRuleError("KnowledgeRule requires at least one validation domain.")
        object.__setattr__(self, "domain_ids", domains)
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))

        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer.")
        if self.priority < 0:
            raise ValueError("priority must be non-negative.")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool.")

    def matches(self, signal: DetectionSignal) -> bool:
        """Return whether the rule is enabled and every predicate matches."""

        if not isinstance(signal, DetectionSignal):
            raise TypeError("signal must be a DetectionSignal.")
        return (
            self.enabled
            and signal.domain in self.domain_ids
            and all(condition.matches(signal) for condition in self.conditions)
        )


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """Auditable candidate match; never a causal conclusion by itself."""

    rule_id: str
    signal_id: str
    knowledge_entry: KnowledgeEntry
    matched_condition_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_identifier(self.rule_id, "rule_id"))
        object.__setattr__(self, "signal_id", _require_identifier(self.signal_id, "signal_id"))
        if not isinstance(self.knowledge_entry, KnowledgeEntry):
            raise TypeError("knowledge_entry must be a KnowledgeEntry.")
        condition_ids = _identifier_tuple(
            self.matched_condition_ids, "matched_condition_ids"
        )
        if not condition_ids:
            raise ValueError("matched_condition_ids must not be empty.")
        object.__setattr__(self, "matched_condition_ids", condition_ids)


@dataclass(frozen=True, slots=True)
class RuleCatalog:
    """Validated deterministic catalog over active causal knowledge."""

    rules: tuple[KnowledgeRule, ...]
    knowledge_entries: tuple[KnowledgeEntry, ...]
    taxonomy: TaxonomyCatalog = CANONICAL_TAXONOMY
    _rules_by_id: Mapping[str, KnowledgeRule] = field(
        init=False, repr=False, compare=False
    )
    _entries_by_id: Mapping[str, KnowledgeEntry] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.taxonomy, TaxonomyCatalog):
            raise TypeError("taxonomy must be a TaxonomyCatalog.")
        rules = _model_tuple(self.rules, KnowledgeRule, "rules")
        entries = _model_tuple(
            self.knowledge_entries, KnowledgeEntry, "knowledge_entries"
        )

        rules_by_id = {rule.id: rule for rule in rules}
        entries_by_id = {entry.id: entry for entry in entries}
        if len(rules_by_id) != len(rules):
            raise DuplicateRuleError("rules contains duplicate identifiers.")
        if len(entries_by_id) != len(entries):
            raise InvalidRuleError("knowledge_entries contains duplicate identifiers.")

        superseded_ids = {
            superseded_id for entry in entries for superseded_id in entry.supersedes
        }
        for entry in entries:
            self.taxonomy.require_root_cause(entry.category_id)
            if entry.status is not KnowledgeEntryStatus.VALIDATED:
                raise InvalidRuleError(
                    f"Knowledge entry {entry.id!r} is not validated and cannot drive rules."
                )
            if entry.causal_certainty is not CausalCertainty.CONFIRMED:
                raise InvalidRuleError(
                    f"Knowledge entry {entry.id!r} lacks confirmed causal certainty."
                )
            if entry.id in superseded_ids:
                raise InvalidRuleError(
                    f"Superseded knowledge entry {entry.id!r} cannot drive active rules."
                )

        for rule in rules:
            for domain_id in rule.domain_ids:
                self.taxonomy.require_domain(domain_id)
            entry = entries_by_id.get(rule.knowledge_entry_id)
            if entry is None:
                raise InvalidRuleError(
                    f"Rule {rule.id!r} references unknown knowledge entry "
                    f"{rule.knowledge_entry_id!r}."
                )
            entry_domains = tuple(entry.metadata.get("domain_ids", ()))
            if not entry_domains:
                raise InvalidRuleError(
                    f"Knowledge entry {entry.id!r} requires explicit metadata.domain_ids "
                    "before it can drive rules."
                )
            canonical_entry_domains = self.taxonomy.canonicalize_many(
                entry_domains,
                axis=self.taxonomy.require_domain(entry_domains[0]).axis,
            )
            if not set(rule.domain_ids) <= set(canonical_entry_domains):
                raise InvalidRuleError(
                    f"Rule {rule.id!r} declares domains outside knowledge entry "
                    f"{entry.id!r} applicability."
                )

        ordered_rules = tuple(sorted(rules, key=lambda item: (item.priority, item.id)))
        object.__setattr__(self, "rules", ordered_rules)
        object.__setattr__(
            self, "knowledge_entries", tuple(sorted(entries, key=lambda item: item.id))
        )
        object.__setattr__(self, "_rules_by_id", MappingProxyType(rules_by_id))
        object.__setattr__(self, "_entries_by_id", MappingProxyType(entries_by_id))

    def rule(self, rule_id: str) -> KnowledgeRule:
        """Resolve one rule by stable identifier."""

        key = _require_identifier(rule_id, "rule_id")
        try:
            return self._rules_by_id[key]
        except KeyError as error:
            raise UnknownRuleError(f"Unknown knowledge rule {key!r}.") from error

    def knowledge_entry(self, entry_id: str) -> KnowledgeEntry:
        """Resolve one active knowledge entry by stable identifier."""

        key = _require_identifier(entry_id, "entry_id")
        try:
            return self._entries_by_id[key]
        except KeyError as error:
            raise KeyError(f"Unknown knowledge entry {key!r}.") from error

    def rules_for_entry(self, entry_id: str) -> tuple[KnowledgeRule, ...]:
        """Return rules linked to one active knowledge entry."""

        entry = self.knowledge_entry(entry_id)
        return tuple(rule for rule in self.rules if rule.knowledge_entry_id == entry.id)

    def match(self, signal: DetectionSignal) -> tuple[RuleMatch, ...]:
        """Return all candidate matches in deterministic priority order."""

        if not isinstance(signal, DetectionSignal):
            raise TypeError("signal must be a DetectionSignal.")
        return tuple(
            RuleMatch(
                rule_id=rule.id,
                signal_id=signal.id,
                knowledge_entry=self._entries_by_id[rule.knowledge_entry_id],
                matched_condition_ids=tuple(
                    condition.id for condition in rule.conditions
                ),
            )
            for rule in self.rules
            if rule.matches(signal)
        )

    def match_many(
        self, signals: Iterable[DetectionSignal]
    ) -> Mapping[str, tuple[RuleMatch, ...]]:
        """Evaluate signals independently without collapsing causal candidates."""

        if isinstance(signals, (str, bytes)):
            raise TypeError("signals must be an iterable of DetectionSignal values.")
        results: dict[str, tuple[RuleMatch, ...]] = {}
        for index, signal in enumerate(signals):
            if not isinstance(signal, DetectionSignal):
                raise TypeError(
                    f"signals[{index}] must be DetectionSignal, "
                    f"got {type(signal).__name__}."
                )
            if signal.id in results:
                raise ValueError(f"signals contains duplicate id {signal.id!r}.")
            results[signal.id] = self.match(signal)
        return MappingProxyType(results)