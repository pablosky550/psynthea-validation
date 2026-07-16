"""Deterministic extraction of typed discrepancy signals for Phase 3.

This module converts the neutral, provenance-preserving observations produced by
:mod:`validation.root_cause.evidence` into immutable
:class:`~validation.root_cause.models.DiscrepancySignal` objects.

Scientific boundary
-------------------
A discrepancy signal states *what differs* and *where it was observed*. It does
not state *why* the difference occurred. Signal extraction therefore must not:

* generate causal hypotheses;
* select a root-cause category;
* rank explanations;
* interpret correlation as causation;
* mark a cause as confirmed, probable or plausible;
* execute verification procedures.

Difference classification is allowed only when it describes the observed nature
of the discrepancy (for example temporal, terminology or export-only). When the
normalized evidence does not make that nature explicit, the extractor preserves
``DifferenceClassification.UNKNOWN`` rather than guessing.

Design guarantees
-----------------

* Rules are deterministic, ordered and independently injectable.
* One evidence item is handled by at most one rule unless a rule deliberately
  emits multiple orthogonal signals.
* Signal identifiers are content-addressed unless an upstream stable identifier
  is explicitly provided.
* Every signal retains one or more evidence references.
* Duplicate identifiers are accepted only for equivalent normalized signals.
* Requested validation domains are enforced at the extraction boundary.
* Strict and permissive modes are explicit and auditable.
* Input ordering cannot affect canonical signal ordering.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from json import dumps
from math import isfinite
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from validation.interpretation.models import FindingStatus
from validation.knowledge.taxonomy import ValidationDomain
from validation.root_cause.evidence import EvidenceCollection, SourceFamily
from validation.root_cause.exceptions import (
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import (
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
)

__all__ = [
    "ExplicitSignalRule",
    "InterpretationFindingSignalRule",
    "SignalDiagnostic",
    "SignalExtraction",
    "SignalExtractionContext",
    "SignalExtractionSeverity",
    "SignalExtractor",
    "SignalRule",
    "ValidationEvidenceSignalRule",
    "extract_signals",
]


# =============================================================================
# Public extraction contracts
# =============================================================================


class SignalExtractionSeverity(str, Enum):
    """Severity of a non-fatal extraction diagnostic."""

    INFO = "info"
    WARNING = "warning"


_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SIGNAL_PREFIX: Final = "signal"
_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class SignalDiagnostic:
    """Auditable event produced when permissive extraction skips evidence."""

    code: str
    message: str
    severity: SignalExtractionSeverity = SignalExtractionSeverity.WARNING
    evidence_id: str | None = None
    rule_name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if not isinstance(self.severity, SignalExtractionSeverity):
            raise TypeError("severity must be a SignalExtractionSeverity member.")
        object.__setattr__(
            self,
            "evidence_id",
            _optional_identifier(self.evidence_id, "evidence_id"),
        )
        object.__setattr__(
            self,
            "rule_name",
            _optional_identifier(self.rule_name, "rule_name"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class SignalExtractionContext:
    """Immutable context shared by all signal rules for one investigation."""

    request: RootCauseRequest
    evidence: tuple[EvidenceReference, ...]
    strict: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        normalized = _normalize_models(self.evidence, EvidenceReference, "evidence")
        _require_unique_ids(normalized, "evidence")
        object.__setattr__(self, "evidence", tuple(sorted(normalized, key=lambda item: item.id)))
        if self.strict is None:
            object.__setattr__(self, "strict", self.request.strict_integrity)
        elif not isinstance(self.strict, bool):
            raise TypeError("strict must be a boolean or None.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @classmethod
    def from_collection(
        cls,
        request: RootCauseRequest,
        collection: EvidenceCollection,
        *,
        strict: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "SignalExtractionContext":
        """Build a context while verifying collection/request identity."""

        if not isinstance(collection, EvidenceCollection):
            raise TypeError("collection must be an EvidenceCollection.")
        if collection.request_id != request.id:
            raise RootCauseIntegrityError(
                "Evidence collection belongs to a different root-cause request.",
                context={
                    "request_id": request.id,
                    "collection_request_id": collection.request_id,
                },
            )
        return cls(
            request=request,
            evidence=collection.evidence,
            strict=strict,
            metadata=metadata or {},
        )

    @property
    def evidence_catalog(self) -> Mapping[str, EvidenceReference]:
        """Return an immutable evidence catalogue indexed by stable id."""

        return MappingProxyType({item.id: item for item in self.evidence})

    def domain_allowed(self, domain: ValidationDomain) -> bool:
        """Return whether a signal domain is within the request scope."""

        return not self.request.requested_domains or domain in self.request.requested_domains


@dataclass(frozen=True, slots=True)
class SignalExtraction:
    """Canonical result of deterministic signal extraction."""

    request_id: str
    signals: tuple[DiscrepancySignal, ...]
    diagnostics: tuple[SignalDiagnostic, ...] = ()
    consumed_evidence_ids: tuple[str, ...] = ()
    unconsumed_evidence_ids: tuple[str, ...] = ()
    schema_version: int = _SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_identifier(self.request_id, "request_id"))

        signals = _normalize_models(self.signals, DiscrepancySignal, "signals")
        _require_unique_ids(signals, "signals")
        object.__setattr__(self, "signals", tuple(sorted(signals, key=lambda item: item.id)))

        diagnostics = _normalize_models(self.diagnostics, SignalDiagnostic, "diagnostics")
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.severity.value,
                        item.code,
                        item.evidence_id or "",
                        item.rule_name or "",
                        item.message,
                    ),
                )
            ),
        )

        consumed = _normalize_identifiers(self.consumed_evidence_ids, "consumed_evidence_ids")
        unconsumed = _normalize_identifiers(
            self.unconsumed_evidence_ids,
            "unconsumed_evidence_ids",
        )
        overlap = set(consumed).intersection(unconsumed)
        if overlap:
            raise ValueError(
                "consumed_evidence_ids and unconsumed_evidence_ids must be disjoint; "
                f"overlap={sorted(overlap)!r}."
            )
        object.__setattr__(self, "consumed_evidence_ids", tuple(sorted(consumed)))
        object.__setattr__(self, "unconsumed_evidence_ids", tuple(sorted(unconsumed)))

        referenced = {evidence_id for signal in signals for evidence_id in signal.evidence_ids}
        missing = referenced.difference(consumed)
        if missing:
            raise ValueError(
                "Every evidence reference used by a signal must be marked consumed; "
                f"missing={sorted(missing)!r}."
            )

        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer.")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be greater than zero.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@runtime_checkable
class SignalRule(Protocol):
    """Injectable deterministic contract for one signal-extraction rule."""

    name: str
    priority: int

    def supports(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> bool:
        """Return whether this rule owns the supplied evidence item."""

    def extract(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> tuple[DiscrepancySignal, ...]:
        """Return zero or more non-causal discrepancy signals."""


# =============================================================================
# Built-in deterministic rules
# =============================================================================


@dataclass(frozen=True, slots=True)
class ExplicitSignalRule:
    """Extract a signal from an explicit, normalized ``metadata['signal']`` descriptor.

    This is the most authoritative rule because all scientific fields are supplied
    upstream rather than inferred here. The descriptor supports the fields of
    :class:`DiscrepancySignal` except ``evidence_ids``, which is always bound to
    the current evidence item, and ``source_id``, which defaults to that evidence
    identifier.
    """

    name: str = "explicit_signal"
    priority: int = 300

    def supports(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> bool:
        del context
        return isinstance(evidence.metadata.get("signal"), Mapping)

    def extract(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> tuple[DiscrepancySignal, ...]:
        descriptor = evidence.metadata.get("signal")
        if not isinstance(descriptor, Mapping):
            raise RootCauseInputError(
                "Explicit signal metadata must be a mapping.",
                context={"evidence_id": evidence.id},
            )

        domain = _coerce_domain(descriptor.get("domain"), "metadata.signal.domain")
        if not context.domain_allowed(domain):
            return ()

        classification = _coerce_classification(
            descriptor.get("classification", DifferenceClassification.UNKNOWN),
            "metadata.signal.classification",
        )
        source_id = _optional_identifier(descriptor.get("source_id"), "metadata.signal.source_id")
        source_id = source_id or evidence.id

        supplied_id = _optional_identifier(descriptor.get("id"), "metadata.signal.id")
        metric_id = _optional_identifier(descriptor.get("metric_id"), "metadata.signal.metric_id")
        cohort_id = _optional_identifier(descriptor.get("cohort_id"), "metadata.signal.cohort_id")
        affected = _normalize_identifiers(
            descriptor.get("affected_entity_ids", ()),
            "metadata.signal.affected_entity_ids",
        )

        payload = {
            "domain": domain.value,
            "classification": classification.value,
            "source_id": source_id,
            "metric_id": metric_id,
            "cohort_id": cohort_id,
            "synthea_value": descriptor.get("synthea_value"),
            "psynthea_value": descriptor.get("psynthea_value"),
            "absolute_difference": descriptor.get("absolute_difference"),
            "relative_difference": descriptor.get("relative_difference"),
            "effect_size": descriptor.get("effect_size"),
            "statistically_significant": descriptor.get("statistically_significant"),
            "clinically_relevant": descriptor.get("clinically_relevant"),
            "affected_entity_ids": affected,
            "evidence_ids": (evidence.id,),
        }
        signal_id = supplied_id or _signal_id(payload)
        summary = descriptor.get("summary", evidence.summary)

        return (
            DiscrepancySignal(
                id=signal_id,
                domain=domain,
                classification=classification,
                summary=_require_text(summary, "metadata.signal.summary"),
                source_id=source_id,
                metric_id=metric_id,
                cohort_id=cohort_id,
                synthea_value=descriptor.get("synthea_value"),
                psynthea_value=descriptor.get("psynthea_value"),
                absolute_difference=_optional_finite_number(
                    descriptor.get("absolute_difference"),
                    "metadata.signal.absolute_difference",
                ),
                relative_difference=_optional_finite_number(
                    descriptor.get("relative_difference"),
                    "metadata.signal.relative_difference",
                ),
                effect_size=_optional_finite_number(
                    descriptor.get("effect_size"),
                    "metadata.signal.effect_size",
                ),
                statistically_significant=_optional_bool(
                    descriptor.get("statistically_significant"),
                    "metadata.signal.statistically_significant",
                ),
                clinically_relevant=_optional_bool(
                    descriptor.get("clinically_relevant"),
                    "metadata.signal.clinically_relevant",
                ),
                affected_entity_ids=affected,
                evidence_ids=(evidence.id,),
                metadata=_signal_metadata(
                    rule_name=self.name,
                    evidence=evidence,
                    upstream=descriptor.get("metadata"),
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class InterpretationFindingSignalRule:
    """Transform one warning/failing interpretation finding into a typed signal.

    PASS, NOT_APPLICABLE and NOT_EVALUATED findings are context, not discrepancy
    signals. INCONCLUSIVE findings are retained only when they explicitly report
    unavailable or invalid evidence, in which case they become a validation-
    pipeline signal only when upstream explicitly marks the inconclusive state
    as a discrepancy. Epistemic uncertainty alone is not transformed into one.
    """

    name: str = "interpretation_finding"
    priority: int = 200

    def supports(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> bool:
        del context
        return (
            evidence.metadata.get("binding_kind") == "interpretation_finding"
            and evidence.metadata.get("binding_id") is not None
        )

    def extract(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> tuple[DiscrepancySignal, ...]:
        status = _coerce_finding_status(evidence.metadata.get("status"), evidence.id)
        if status in {
            FindingStatus.PASS,
            FindingStatus.NOT_APPLICABLE,
            FindingStatus.NOT_EVALUATED,
        }:
            return ()

        domain = _coerce_domain(evidence.metadata.get("domain"), "evidence.metadata.domain")
        if not context.domain_allowed(domain):
            return ()

        classification = _classification_from_explicit_metadata(evidence.metadata)
        if status is FindingStatus.INCONCLUSIVE and not _inconclusive_is_discrepancy(
            evidence.metadata
        ):
            return ()

        source_id = _require_identifier(
            evidence.metadata["binding_id"],
            "evidence.metadata.binding_id",
        )
        metric_id = _first_identifier(
            evidence.metadata.get("metric_id"),
            evidence.metadata.get("rule_id"),
        )
        cohort_id = _optional_identifier(
            evidence.metadata.get("cohort_id"),
            "evidence.metadata.cohort_id",
        )

        affected = _extract_affected_entities(evidence.metadata)
        statistically_significant = _optional_bool(
            evidence.metadata.get("statistically_significant"),
            "evidence.metadata.statistically_significant",
        )
        clinically_relevant = _optional_bool(
            evidence.metadata.get("clinically_relevant"),
            "evidence.metadata.clinically_relevant",
        )
        summary = _finding_summary(evidence, status)

        payload = {
            "domain": domain.value,
            "classification": classification.value,
            "source_id": source_id,
            "metric_id": metric_id,
            "cohort_id": cohort_id,
            "status": status.value,
            "evidence_id": evidence.id,
            "affected_entity_ids": affected,
        }
        return (
            DiscrepancySignal(
                id=_signal_id(payload),
                domain=domain,
                classification=classification,
                summary=summary,
                source_id=source_id,
                metric_id=metric_id,
                cohort_id=cohort_id,
                synthea_value=evidence.metadata.get("synthea_value"),
                psynthea_value=evidence.metadata.get("psynthea_value"),
                absolute_difference=_optional_finite_number(
                    evidence.metadata.get("absolute_difference"),
                    "evidence.metadata.absolute_difference",
                ),
                relative_difference=_optional_finite_number(
                    evidence.metadata.get("relative_difference"),
                    "evidence.metadata.relative_difference",
                ),
                effect_size=_optional_finite_number(
                    evidence.metadata.get("effect_size"),
                    "evidence.metadata.effect_size",
                ),
                statistically_significant=statistically_significant,
                clinically_relevant=clinically_relevant,
                affected_entity_ids=affected,
                evidence_ids=(evidence.id,),
                metadata=_signal_metadata(
                    rule_name=self.name,
                    evidence=evidence,
                    upstream={
                        "finding_status": status.value,
                        "severity": evidence.metadata.get("severity"),
                        "confidence": evidence.metadata.get("confidence"),
                        "evidence_strength": evidence.metadata.get("evidence_strength"),
                        "blocks_research_use": evidence.metadata.get("blocks_research_use"),
                        "limitations": evidence.metadata.get("limitations"),
                        "tags": evidence.metadata.get("tags"),
                    },
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class ValidationEvidenceSignalRule:
    """Extract a signal from normalized Phase 1 validation evidence.

    The rule requires explicit ``domain`` and discrepancy semantics in metadata.
    It deliberately refuses to infer a domain from free-form metric names. A
    validation observation is considered discrepant when one of these explicit
    markers is present:

    * ``is_discrepancy is True``;
    * ``status`` is ``warning`` or ``fail``;
    * ``equivalent is False``.
    """

    name: str = "validation_evidence"
    priority: int = 100

    def supports(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> bool:
        del context
        family = evidence.metadata.get("source_family")
        return family == SourceFamily.VALIDATION.value or evidence.source_type == SourceFamily.VALIDATION.value

    def extract(
        self,
        evidence: EvidenceReference,
        context: SignalExtractionContext,
    ) -> tuple[DiscrepancySignal, ...]:
        if not _is_explicit_discrepancy(evidence.metadata):
            return ()

        domain = _coerce_domain(evidence.metadata.get("domain"), "evidence.metadata.domain")
        if not context.domain_allowed(domain):
            return ()

        classification = _classification_from_explicit_metadata(evidence.metadata)
        source_id = _first_identifier(
            evidence.metadata.get("validation_result_id"),
            evidence.metadata.get("binding_id"),
            evidence.id,
        )
        metric_id = _first_identifier(
            evidence.metadata.get("metric_id"),
            evidence.metadata.get("metric"),
        )
        cohort_id = _optional_identifier(
            evidence.metadata.get("cohort_id"),
            "evidence.metadata.cohort_id",
        )
        affected = _extract_affected_entities(evidence.metadata)

        payload = {
            "domain": domain.value,
            "classification": classification.value,
            "source_id": source_id,
            "metric_id": metric_id,
            "cohort_id": cohort_id,
            "evidence_id": evidence.id,
            "affected_entity_ids": affected,
        }
        return (
            DiscrepancySignal(
                id=_signal_id(payload),
                domain=domain,
                classification=classification,
                summary=evidence.summary,
                source_id=source_id,
                metric_id=metric_id,
                cohort_id=cohort_id,
                synthea_value=evidence.metadata.get("synthea_value"),
                psynthea_value=evidence.metadata.get("psynthea_value"),
                absolute_difference=_optional_finite_number(
                    evidence.metadata.get("absolute_difference"),
                    "evidence.metadata.absolute_difference",
                ),
                relative_difference=_optional_finite_number(
                    evidence.metadata.get("relative_difference"),
                    "evidence.metadata.relative_difference",
                ),
                effect_size=_optional_finite_number(
                    evidence.metadata.get("effect_size"),
                    "evidence.metadata.effect_size",
                ),
                statistically_significant=_optional_bool(
                    evidence.metadata.get("statistically_significant"),
                    "evidence.metadata.statistically_significant",
                ),
                clinically_relevant=_optional_bool(
                    evidence.metadata.get("clinically_relevant"),
                    "evidence.metadata.clinically_relevant",
                ),
                affected_entity_ids=affected,
                evidence_ids=(evidence.id,),
                metadata=_signal_metadata(
                    rule_name=self.name,
                    evidence=evidence,
                    upstream={
                        "status": evidence.metadata.get("status"),
                        "equivalent": evidence.metadata.get("equivalent"),
                        "is_discrepancy": evidence.metadata.get("is_discrepancy"),
                        "test_name": evidence.metadata.get("test_name"),
                        "p_value": evidence.metadata.get("p_value"),
                        "confidence_interval": evidence.metadata.get("confidence_interval"),
                    },
                ),
            ),
        )


# =============================================================================
# Extraction engine
# =============================================================================


@dataclass(slots=True)
class _SignalRegistry:
    """Mutable internal registry enforcing deterministic identifier integrity."""

    _signals: dict[str, DiscrepancySignal] = field(default_factory=dict)

    def add(self, signal: DiscrepancySignal) -> None:
        if not isinstance(signal, DiscrepancySignal):
            raise TypeError("signal must be a DiscrepancySignal.")
        existing = self._signals.get(signal.id)
        if existing is None:
            self._signals[signal.id] = signal
            return
        if existing != signal:
            raise RootCauseIntegrityError(
                "Two non-equivalent discrepancy signals share the same identifier.",
                context={"signal_id": signal.id},
            )

    def values(self) -> tuple[DiscrepancySignal, ...]:
        return tuple(sorted(self._signals.values(), key=lambda item: item.id))


class SignalExtractor:
    """Deterministic coordinator for rule-based discrepancy signal extraction."""

    def __init__(self, rules: Sequence[SignalRule] | None = None) -> None:
        selected = tuple(rules) if rules is not None else (
            ExplicitSignalRule(),
            InterpretationFindingSignalRule(),
            ValidationEvidenceSignalRule(),
        )
        if not selected:
            raise ValueError("At least one signal rule is required.")
        for index, rule in enumerate(selected):
            if not isinstance(rule, SignalRule):
                raise TypeError(f"rules[{index}] does not implement SignalRule.")
            _require_identifier(rule.name, f"rules[{index}].name")
            if isinstance(rule.priority, bool) or not isinstance(rule.priority, int):
                raise TypeError(f"rules[{index}].priority must be an integer.")

        names = [rule.name for rule in selected]
        if len(names) != len(set(names)):
            raise ValueError("Signal rule names must be unique.")
        self._rules = tuple(sorted(selected, key=lambda item: (-item.priority, item.name)))

    @property
    def rules(self) -> tuple[SignalRule, ...]:
        """Rules in deterministic execution order."""

        return self._rules

    def extract(self, context: SignalExtractionContext) -> SignalExtraction:
        """Extract canonical discrepancy signals from normalized evidence."""

        if not isinstance(context, SignalExtractionContext):
            raise TypeError("context must be a SignalExtractionContext.")

        registry = _SignalRegistry()
        diagnostics: list[SignalDiagnostic] = []
        consumed: set[str] = set()

        for evidence in context.evidence:
            matching: tuple[SignalRule, ...] = ()
            try:
                matching = _matching_rules(evidence, context, self._rules)
                if not matching:
                    continue

                rule = matching[0]
                if len(matching) > 1 and matching[0].priority == matching[1].priority:
                    raise RootCauseIntegrityError(
                        "Multiple signal rules with equal priority claim the same evidence item.",
                        context={
                            "evidence_id": evidence.id,
                            "rule_names": tuple(item.name for item in matching),
                            "priority": matching[0].priority,
                        },
                    )

                extracted = rule.extract(evidence, context)
                if isinstance(extracted, (str, bytes)) or not isinstance(extracted, Sequence):
                    raise TypeError(
                        f"Signal rule {rule.name!r} must return a sequence of signals."
                    )
                normalized = _normalize_models(
                    extracted,
                    DiscrepancySignal,
                    f"rule[{rule.name}].signals",
                )
                for signal in normalized:
                    _validate_emitted_signal(signal, evidence, context, rule.name)
                    registry.add(signal)
                    consumed.update(signal.evidence_ids)
                consumed.add(evidence.id)
            except (RootCauseInputError, RootCauseIntegrityError, TypeError, ValueError) as exc:
                rule_name = _diagnostic_rule_name(matching, exc)
                if context.strict:
                    if isinstance(exc, (RootCauseInputError, RootCauseIntegrityError)):
                        raise
                    raise RootCauseInputError(
                        "Signal extraction rule rejected normalized evidence.",
                        context={
                            "evidence_id": evidence.id,
                            "rule_name": rule_name,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    ) from exc
                diagnostics.append(
                    SignalDiagnostic(
                        code=_diagnostic_code(exc),
                        message="Signal evidence could not be transformed safely.",
                        evidence_id=evidence.id,
                        rule_name=rule_name,
                        metadata={
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "error_context": getattr(exc, "context", {}),
                        },
                    )
                )

        signals = registry.values()
        unconsumed = set(context.evidence_catalog).difference(consumed)
        _validate_signal_graph(signals, context)
        return SignalExtraction(
            request_id=context.request.id,
            signals=signals,
            diagnostics=tuple(diagnostics),
            consumed_evidence_ids=tuple(consumed),
            unconsumed_evidence_ids=tuple(unconsumed),
            metadata={
                "rule_names": tuple(rule.name for rule in self._rules),
                "strict": context.strict,
                "requested_domains": tuple(
                    domain.value for domain in context.request.requested_domains
                ),
            },
        )


def extract_signals(
    request: RootCauseRequest,
    evidence: EvidenceCollection | Sequence[EvidenceReference],
    *,
    rules: Sequence[SignalRule] | None = None,
    strict: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> SignalExtraction:
    """Functional convenience API for deterministic signal extraction."""

    if not isinstance(request, RootCauseRequest):
        raise TypeError("request must be a RootCauseRequest.")
    if isinstance(evidence, EvidenceCollection):
        context = SignalExtractionContext.from_collection(
            request,
            evidence,
            strict=strict,
            metadata=metadata,
        )
    else:
        context = SignalExtractionContext(
            request=request,
            evidence=tuple(evidence),
            strict=strict,
            metadata=metadata or {},
        )
    return SignalExtractor(rules).extract(context)


# =============================================================================
# Integrity and normalization helpers
# =============================================================================


def _matching_rules(
    evidence: EvidenceReference,
    context: SignalExtractionContext,
    rules: Sequence[SignalRule],
) -> tuple[SignalRule, ...]:
    """Evaluate rule ownership while normalizing extension failures."""

    matching: list[SignalRule] = []
    for rule in rules:
        try:
            supported = rule.supports(evidence, context)
        except (RootCauseInputError, RootCauseIntegrityError, TypeError, ValueError):
            raise
        except Exception as exc:  # pragma: no cover - defensive plugin boundary
            raise RootCauseInputError(
                "Signal rule failed while evaluating evidence ownership.",
                context={
                    "evidence_id": evidence.id,
                    "rule_name": rule.name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc
        if not isinstance(supported, bool):
            raise TypeError(
                f"Signal rule {rule.name!r}.supports() must return a boolean."
            )
        if supported:
            matching.append(rule)
    return tuple(matching)


def _diagnostic_rule_name(
    matching: Sequence[SignalRule],
    error: Exception,
) -> str | None:
    if matching:
        return matching[0].name
    context = getattr(error, "context", {})
    candidate = context.get("rule_name") if isinstance(context, Mapping) else None
    return candidate if isinstance(candidate, str) else None


def _diagnostic_code(error: Exception) -> str:
    context = getattr(error, "context", {})
    if (
        isinstance(error, RootCauseIntegrityError)
        and isinstance(context, Mapping)
        and "rule_names" in context
        and "priority" in context
    ):
        return "signals.ambiguous_rule"
    return "signals.rule_skipped"


def _validate_emitted_signal(
    signal: DiscrepancySignal,
    evidence: EvidenceReference,
    context: SignalExtractionContext,
    rule_name: str,
) -> None:
    if evidence.direction is not EvidenceDirection.NEUTRAL:
        raise RootCauseIntegrityError(
            "Signal extraction requires causally neutral evidence.",
            context={
                "rule_name": rule_name,
                "evidence_id": evidence.id,
                "direction": evidence.direction.value,
            },
        )
    if evidence.id not in signal.evidence_ids:
        raise RootCauseIntegrityError(
            "A signal rule emitted a signal not linked to its source evidence.",
            context={
                "rule_name": rule_name,
                "signal_id": signal.id,
                "evidence_id": evidence.id,
            },
        )
    unknown = set(signal.evidence_ids).difference(context.evidence_catalog)
    if unknown:
        raise RootCauseIntegrityError(
            "A signal references evidence absent from the extraction context.",
            context={
                "rule_name": rule_name,
                "signal_id": signal.id,
                "unknown_evidence_ids": sorted(unknown),
            },
        )
    if not context.domain_allowed(signal.domain):
        raise RootCauseIntegrityError(
            "A signal rule emitted a domain outside the request scope.",
            context={
                "rule_name": rule_name,
                "signal_id": signal.id,
                "domain": signal.domain.value,
            },
        )


def _validate_signal_graph(
    signals: Sequence[DiscrepancySignal],
    context: SignalExtractionContext,
) -> None:
    evidence_ids = set(context.evidence_catalog)
    for signal in signals:
        missing = set(signal.evidence_ids).difference(evidence_ids)
        if missing:
            raise RootCauseIntegrityError(
                "Signal graph contains dangling evidence references.",
                context={"signal_id": signal.id, "missing_evidence_ids": sorted(missing)},
            )


def _inconclusive_is_discrepancy(metadata: Mapping[str, Any]) -> bool:
    """Require explicit discrepancy semantics for inconclusive findings.

    ``INCONCLUSIVE`` describes epistemic insufficiency, not necessarily a
    difference between simulators.  It becomes a signal only when upstream has
    explicitly classified the observed issue or marked it as a discrepancy.
    """

    if metadata.get("difference_classification") is not None:
        return True
    if metadata.get("classification") is not None:
        return True
    if metadata.get("difference_kind") is not None:
        return True
    marker = metadata.get("is_discrepancy")
    return marker is not None and _require_bool(
        marker, "evidence.metadata.is_discrepancy"
    )


def _classification_from_explicit_metadata(
    metadata: Mapping[str, Any],
) -> DifferenceClassification:
    explicit = metadata.get("difference_classification", metadata.get("classification"))
    if explicit is not None:
        return _coerce_classification(explicit, "evidence.metadata.classification")

    # These mappings use explicit upstream semantic markers, not free-text
    # keyword matching. They classify the observed discrepancy, never its cause.
    marker = metadata.get("difference_kind")
    if marker is None:
        return DifferenceClassification.UNKNOWN
    normalized = _require_text(marker, "evidence.metadata.difference_kind").lower()
    aliases = {
        "input": DifferenceClassification.INPUT,
        "configuration": DifferenceClassification.CONFIGURATION,
        "structural": DifferenceClassification.STRUCTURAL,
        "semantic": DifferenceClassification.SEMANTIC,
        "temporal": DifferenceClassification.TEMPORAL,
        "probabilistic": DifferenceClassification.PROBABILISTIC,
        "clinical_recording": DifferenceClassification.CLINICAL_RECORDING,
        "terminology": DifferenceClassification.TERMINOLOGY,
        "export": DifferenceClassification.EXPORT_ONLY,
        "export_only": DifferenceClassification.EXPORT_ONLY,
        "validation_pipeline": DifferenceClassification.VALIDATION_PIPELINE,
        "execution_environment": DifferenceClassification.EXECUTION_ENVIRONMENT,
        "statistical_artifact": DifferenceClassification.STATISTICAL_ARTIFACT,
        "expected_adaptation": DifferenceClassification.EXPECTED_ADAPTATION,
        "implementation_limitation": DifferenceClassification.IMPLEMENTATION_LIMITATION,
        "multifactorial": DifferenceClassification.MULTIFACTORIAL,
        "unknown": DifferenceClassification.UNKNOWN,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise RootCauseInputError(
            "Evidence contains an unsupported explicit difference kind.",
            context={"difference_kind": normalized},
        ) from exc


def _is_explicit_discrepancy(metadata: Mapping[str, Any]) -> bool:
    marker = metadata.get("is_discrepancy")
    if marker is not None:
        return _require_bool(marker, "evidence.metadata.is_discrepancy")

    equivalent = metadata.get("equivalent")
    if equivalent is not None:
        return not _require_bool(equivalent, "evidence.metadata.equivalent")

    status = metadata.get("status")
    if status is None:
        return False
    if isinstance(status, Enum):
        status = status.value
    normalized = _require_text(status, "evidence.metadata.status").lower()
    return normalized in {"warning", "fail", "failed"}


def _coerce_finding_status(value: Any, evidence_id: str) -> FindingStatus:
    if isinstance(value, FindingStatus):
        return value
    if isinstance(value, str):
        try:
            return FindingStatus(value)
        except ValueError as exc:
            raise RootCauseInputError(
                "Interpretation finding evidence contains an unsupported status.",
                context={"evidence_id": evidence_id, "status": value},
            ) from exc
    raise RootCauseInputError(
        "Interpretation finding evidence is missing its status.",
        context={"evidence_id": evidence_id},
    )


def _coerce_domain(value: Any, field_name: str) -> ValidationDomain:
    if isinstance(value, ValidationDomain):
        return value
    if isinstance(value, str):
        try:
            return ValidationDomain(value)
        except ValueError as exc:
            raise RootCauseInputError(
                "Evidence contains an unsupported validation domain.",
                context={"field": field_name, "value": value},
            ) from exc
    raise RootCauseInputError(
        "Evidence must declare a canonical validation domain.",
        context={"field": field_name, "value_type": type(value).__name__},
    )


def _coerce_classification(value: Any, field_name: str) -> DifferenceClassification:
    if isinstance(value, DifferenceClassification):
        return value
    if isinstance(value, str):
        try:
            return DifferenceClassification(value)
        except ValueError as exc:
            raise RootCauseInputError(
                "Evidence contains an unsupported difference classification.",
                context={"field": field_name, "value": value},
            ) from exc
    raise RootCauseInputError(
        "Difference classification must be a canonical enum member or value.",
        context={"field": field_name, "value_type": type(value).__name__},
    )


def _extract_affected_entities(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw = metadata.get("affected_entity_ids")
    if raw is None:
        candidates = (
            metadata.get("module_id"),
            metadata.get("module_name"),
            metadata.get("state_id"),
            metadata.get("state_name"),
            metadata.get("transition_id"),
            metadata.get("code"),
        )
        raw = tuple(item for item in candidates if item is not None)
    return _normalize_identifiers(raw, "evidence.metadata.affected_entity_ids")


def _finding_summary(evidence: EvidenceReference, status: FindingStatus) -> str:
    prefix = {
        FindingStatus.FAIL: "Validation discrepancy",
        FindingStatus.WARNING: "Validation warning",
        FindingStatus.INCONCLUSIVE: "Inconclusive validation evidence",
    }[status]
    return f"{prefix}: {evidence.summary}"


def _signal_metadata(
    *,
    rule_name: str,
    evidence: EvidenceReference,
    upstream: Any = None,
) -> Mapping[str, Any]:
    metadata: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "extraction_rule": rule_name,
        "source_type": evidence.source_type,
        "source_locator": evidence.locator,
        "source_artifact_id": evidence.artifact_id,
        "source_sha256": evidence.sha256,
        "source_observed_at": evidence.observed_at,
    }
    if upstream is not None:
        metadata["upstream"] = upstream
    return metadata


def _signal_id(payload: Mapping[str, Any]) -> str:
    digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{_SIGNAL_PREFIX}:{digest[:24]}"


def _canonical_json(value: Any) -> str:
    return dumps(
        _to_canonical(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _to_canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("Canonical signal content must not contain NaN or infinity.")
        return value
    if isinstance(value, Enum):
        return _to_canonical(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _to_canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        normalized = [_to_canonical(item) for item in value]
        return sorted(normalized, key=lambda item: dumps(item, sort_keys=True, default=str))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_canonical(item) for item in value]
    return str(value)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return _deep_freeze(dict(value))


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_identifier(value: Any, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _optional_identifier(value: Any, field_name: str) -> str | None:
    return None if value is None else _require_identifier(value, field_name)


def _first_identifier(*values: Any) -> str | None:
    for index, value in enumerate(values):
        if value is not None:
            return _require_identifier(value, f"identifier_candidate[{index}]")
    return None


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean.")
    return value


def _optional_bool(value: Any, field_name: str) -> bool | None:
    return None if value is None else _require_bool(value, field_name)


def _optional_finite_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric or None.")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def _normalize_identifiers(values: Any, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    if isinstance(values, (bytes, bytearray)) or not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of identifiers.")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_identifier(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _normalize_models(
    values: Sequence[Any],
    expected_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {expected_type.__name__} values.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name}[{index}] must be {expected_type.__name__}, "
                f"got {type(value).__name__}."
            )
    return normalized


def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value.id in seen:
            duplicates.add(value.id)
        seen.add(value.id)
    if duplicates:
        raise ValueError(f"{field_name} contains duplicate ids: {sorted(duplicates)!r}.")