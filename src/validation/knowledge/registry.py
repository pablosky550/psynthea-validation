"""Validated registry for Phase 2A causal knowledge.

The registry is the application boundary between auditable investigations and
reusable root-cause knowledge. It stores immutable domain objects, validates
cross-object provenance, and exposes deterministic snapshots. It never infers a
cause, executes protocols, persists files, or renders reports.

Publication rule
----------------
A knowledge entry may be ``VALIDATED`` only when it is derived from the selected
hypothesis of a resolved investigation, that hypothesis is confirmed, and at
least one passed verification supports it with evidence from the same case.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from validation.knowledge.models import (
    CausalCertainty,
    CausalHypothesis,
    InvestigationCase,
    InvestigationStatus,
    KnowledgeEntry,
    KnowledgeEntryStatus,
    RecommendedAction,
    VerificationStatus,
)
from validation.knowledge.taxonomy import (
    CANONICAL_TAXONOMY,
    TaxonomyAxis,
    TaxonomyCatalog,
)

__all__ = [
    "DuplicateInvestigationError",
    "DuplicateKnowledgeEntryError",
    "InvalidKnowledgePublicationError",
    "KnowledgeRegistry",
    "KnowledgeRegistryError",
    "RegistrySnapshot",
    "SupersessionError",
    "UnknownInvestigationError",
    "UnknownKnowledgeEntryError",
]


class KnowledgeRegistryError(RuntimeError):
    """Base class for registry failures."""


class DuplicateInvestigationError(KnowledgeRegistryError):
    """Raised when an investigation id is already registered."""


class UnknownInvestigationError(KnowledgeRegistryError):
    """Raised when an investigation cannot be resolved."""


class DuplicateKnowledgeEntryError(KnowledgeRegistryError):
    """Raised when a knowledge-entry id is already registered."""


class UnknownKnowledgeEntryError(KnowledgeRegistryError):
    """Raised when a knowledge entry cannot be resolved."""


class InvalidKnowledgePublicationError(KnowledgeRegistryError):
    """Raised when evidence or lifecycle requirements prevent publication."""


class SupersessionError(KnowledgeRegistryError):
    """Raised when a supersession relation is invalid."""


def _require_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_text(value: str, field_name: str) -> str:
    return _require_identifier(value, field_name)


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _models(values: Sequence[Any], model: type[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {model.__name__} values.")
    result = tuple(values)
    for index, value in enumerate(result):
        if not isinstance(value, model):
            raise TypeError(
                f"{field_name}[{index}] must be {model.__name__}, "
                f"got {type(value).__name__}."
            )
    return result


def _texts(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_text(value, f"{field_name}[{index}]")
        if item not in seen:
            result.append(item)
            seen.add(item)
    return tuple(result)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _assert_unique_ids(values: Sequence[Any], field_name: str) -> None:
    ids = [value.id for value in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{field_name} contains duplicate ids.")


def _validate_supersession_graph(entries: Mapping[str, KnowledgeEntry]) -> None:
    for entry in entries.values():
        for target_id in entry.supersedes:
            target = entries.get(target_id)
            if target is None:
                raise SupersessionError(
                    f"Knowledge entry {entry.id!r} supersedes unknown entry {target_id!r}."
                )
            if entry.created_at < target.created_at:
                raise SupersessionError(
                    f"Knowledge entry {entry.id!r} cannot supersede newer entry {target_id!r}."
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(entry_id: str) -> None:
        if entry_id in visited:
            return
        if entry_id in visiting:
            raise SupersessionError(f"Supersession cycle detected at {entry_id!r}.")
        visiting.add(entry_id)
        for target_id in entries[entry_id].supersedes:
            visit(target_id)
        visiting.remove(entry_id)
        visited.add(entry_id)

    for entry_id in entries:
        visit(entry_id)


def _superseded_ids(entries: Iterable[KnowledgeEntry]) -> frozenset[str]:
    return frozenset(target for entry in entries for target in entry.supersedes)


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """Immutable point-in-time registry state suitable for persistence."""

    investigations: tuple[InvestigationCase, ...]
    knowledge_entries: tuple[KnowledgeEntry, ...]
    taxonomy_version: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, Any] = field(default_factory=dict)
    _investigations_by_id: Mapping[str, InvestigationCase] = field(
        init=False, repr=False, compare=False
    )
    _entries_by_id: Mapping[str, KnowledgeEntry] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        investigations = _models(self.investigations, InvestigationCase, "investigations")
        entries = _models(self.knowledge_entries, KnowledgeEntry, "knowledge_entries")
        _assert_unique_ids(investigations, "investigations")
        _assert_unique_ids(entries, "knowledge_entries")

        investigations_by_id = {item.id: item for item in investigations}
        entries_by_id = {item.id: item for item in entries}
        for entry in entries:
            if entry.source_investigation_id not in investigations_by_id:
                raise ValueError(
                    f"Entry {entry.id!r} references unknown investigation "
                    f"{entry.source_investigation_id!r}."
                )
        _validate_supersession_graph(entries_by_id)

        object.__setattr__(self, "investigations", tuple(sorted(investigations, key=lambda x: x.id)))
        object.__setattr__(self, "knowledge_entries", tuple(sorted(entries, key=lambda x: x.id)))
        object.__setattr__(self, "taxonomy_version", _require_identifier(self.taxonomy_version, "taxonomy_version"))
        object.__setattr__(self, "created_at", _aware_utc(self.created_at, "created_at"))
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))
        object.__setattr__(self, "_investigations_by_id", MappingProxyType(investigations_by_id))
        object.__setattr__(self, "_entries_by_id", MappingProxyType(entries_by_id))

    @property
    def active_entries(self) -> tuple[KnowledgeEntry, ...]:
        """Validated entries not replaced by another registered entry."""

        superseded = _superseded_ids(self.knowledge_entries)
        return tuple(
            entry
            for entry in self.knowledge_entries
            if entry.status is KnowledgeEntryStatus.VALIDATED and entry.id not in superseded
        )

    def investigation(self, investigation_id: str) -> InvestigationCase:
        key = _require_identifier(investigation_id, "investigation_id")
        try:
            return self._investigations_by_id[key]
        except KeyError as error:
            raise UnknownInvestigationError(f"Unknown investigation {key!r}.") from error

    def knowledge_entry(self, entry_id: str) -> KnowledgeEntry:
        key = _require_identifier(entry_id, "entry_id")
        try:
            return self._entries_by_id[key]
        except KeyError as error:
            raise UnknownKnowledgeEntryError(f"Unknown knowledge entry {key!r}.") from error


class KnowledgeRegistry:
    """Controlled mutable registry over immutable Phase 2A domain objects."""

    def __init__(
        self,
        *,
        taxonomy: TaxonomyCatalog = CANONICAL_TAXONOMY,
        investigations: Iterable[InvestigationCase] = (),
        knowledge_entries: Iterable[KnowledgeEntry] = (),
    ) -> None:
        if not isinstance(taxonomy, TaxonomyCatalog):
            raise TypeError("taxonomy must be a TaxonomyCatalog.")
        self._taxonomy = taxonomy
        self._investigations: dict[str, InvestigationCase] = {}
        self._entries: dict[str, KnowledgeEntry] = {}
        for investigation in investigations:
            self.register_investigation(investigation)
        for entry in knowledge_entries:
            self.register_knowledge_entry(entry)

    @property
    def taxonomy(self) -> TaxonomyCatalog:
        return self._taxonomy

    def register_investigation(self, investigation: InvestigationCase) -> InvestigationCase:
        if not isinstance(investigation, InvestigationCase):
            raise TypeError("investigation must be an InvestigationCase.")
        if investigation.id in self._investigations:
            raise DuplicateInvestigationError(
                f"Investigation {investigation.id!r} already exists."
            )
        self._validate_investigation(investigation)
        self._investigations[investigation.id] = investigation
        return investigation

    def replace_investigation(self, investigation: InvestigationCase) -> InvestigationCase:
        if not isinstance(investigation, InvestigationCase):
            raise TypeError("investigation must be an InvestigationCase.")
        current = self._investigations.get(investigation.id)
        if current is None:
            raise UnknownInvestigationError(f"Unknown investigation {investigation.id!r}.")
        if investigation.opened_at != current.opened_at:
            raise ValueError("Replacing an investigation must preserve opened_at.")
        if investigation.updated_at < current.updated_at:
            raise ValueError("Replacing an investigation cannot move updated_at backwards.")
        self._validate_investigation(investigation)
        for entry in self.entries_for_investigation(investigation.id):
            self._validate_entry(entry, investigation)
        self._investigations[investigation.id] = investigation
        return investigation

    def investigation(self, investigation_id: str) -> InvestigationCase:
        key = _require_identifier(investigation_id, "investigation_id")
        try:
            return self._investigations[key]
        except KeyError as error:
            raise UnknownInvestigationError(f"Unknown investigation {key!r}.") from error

    def investigations(
        self, *, status: InvestigationStatus | None = None
    ) -> tuple[InvestigationCase, ...]:
        if status is not None and not isinstance(status, InvestigationStatus):
            raise TypeError("status must be an InvestigationStatus or None.")
        return tuple(
            item
            for item in sorted(self._investigations.values(), key=lambda x: x.id)
            if status is None or item.status is status
        )

    def register_knowledge_entry(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        if not isinstance(entry, KnowledgeEntry):
            raise TypeError("entry must be a KnowledgeEntry.")
        if entry.id in self._entries:
            raise DuplicateKnowledgeEntryError(
                f"Knowledge entry {entry.id!r} already exists."
            )
        investigation = self.investigation(entry.source_investigation_id)
        self._validate_entry(entry, investigation)
        candidate = dict(self._entries)
        candidate[entry.id] = entry
        _validate_supersession_graph(candidate)
        self._entries[entry.id] = entry
        return entry

    def replace_knowledge_entry(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        if not isinstance(entry, KnowledgeEntry):
            raise TypeError("entry must be a KnowledgeEntry.")
        current = self._entries.get(entry.id)
        if current is None:
            raise UnknownKnowledgeEntryError(f"Unknown knowledge entry {entry.id!r}.")
        if entry.created_at != current.created_at:
            raise ValueError("Replacing a knowledge entry must preserve created_at.")
        if entry.updated_at < current.updated_at:
            raise ValueError("Replacing a knowledge entry cannot move updated_at backwards.")
        if entry.source_investigation_id != current.source_investigation_id:
            raise ValueError("source_investigation_id is immutable.")
        if entry.source_hypothesis_id != current.source_hypothesis_id:
            raise ValueError("source_hypothesis_id is immutable.")
        investigation = self.investigation(entry.source_investigation_id)
        self._validate_entry(entry, investigation)
        candidate = dict(self._entries)
        candidate[entry.id] = entry
        _validate_supersession_graph(candidate)
        self._entries[entry.id] = entry
        return entry

    def publish_from_investigation(
        self,
        investigation_id: str,
        *,
        entry_id: str,
        title: str,
        detection_pattern: str,
        root_cause: str,
        recommended_actions: Sequence[RecommendedAction],
        applicability: Sequence[str],
        domain_ids: Sequence[str],
        limitations: Sequence[str] = (),
        supersedes: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        published_at: datetime | None = None,
    ) -> KnowledgeEntry:
        """Publish demonstrated knowledge; never infer or select a cause."""

        investigation = self.investigation(investigation_id)
        hypothesis = investigation.selected_hypothesis
        self._require_publishable_investigation(investigation, hypothesis)
        assert hypothesis is not None

        passed = tuple(
            check
            for check in investigation.verifications
            if check.hypothesis_id == hypothesis.id
            and check.status is VerificationStatus.PASSED
        )
        evidence_ids = set(hypothesis.supporting_evidence_ids)
        for check in passed:
            evidence_ids.update(check.evidence_ids)
        evidence = tuple(item for item in investigation.evidence if item.id in evidence_ids)
        if not evidence:
            raise InvalidKnowledgePublicationError(
                "Publication requires supporting evidence from the investigation."
            )

        actions = _models(recommended_actions, RecommendedAction, "recommended_actions")
        if not actions:
            raise InvalidKnowledgePublicationError(
                "Publication requires at least one recommended action."
            )
        applicability_values = _texts(applicability, "applicability")
        if not applicability_values:
            raise InvalidKnowledgePublicationError(
                "Publication requires at least one applicability condition."
            )
        domains = self._taxonomy.canonicalize_many(
            domain_ids, axis=TaxonomyAxis.VALIDATION_DOMAIN
        )
        superseded_ids = _texts(supersedes, "supersedes")
        for target_id in superseded_ids:
            if target_id not in self._entries:
                raise SupersessionError(
                    f"Knowledge entry {entry_id!r} supersedes unknown entry {target_id!r}."
                )

        timestamp = datetime.now(UTC) if published_at is None else _aware_utc(
            published_at, "published_at"
        )
        entry_metadata = dict(metadata or {})
        entry_metadata.update(
            {
                "domain_ids": domains,
                "taxonomy_version": self._taxonomy.version,
            }
        )
        entry = KnowledgeEntry(
            id=_require_identifier(entry_id, "entry_id"),
            title=_require_text(title, "title"),
            status=KnowledgeEntryStatus.VALIDATED,
            category_id=self._taxonomy.require_root_cause(hypothesis.category_id).id,
            detection_pattern=_require_text(detection_pattern, "detection_pattern"),
            root_cause=_require_text(root_cause, "root_cause"),
            causal_certainty=CausalCertainty.CONFIRMED,
            source_investigation_id=investigation.id,
            source_hypothesis_id=hypothesis.id,
            evidence=evidence,
            verifications=passed,
            recommended_actions=actions,
            applicability=applicability_values,
            limitations=_texts(limitations, "limitations"),
            created_at=timestamp,
            updated_at=timestamp,
            supersedes=superseded_ids,
            metadata=entry_metadata,
        )
        return self.register_knowledge_entry(entry)

    def deprecate_entry(
        self, entry_id: str, *, reason: str, changed_at: datetime | None = None
    ) -> KnowledgeEntry:
        current = self.knowledge_entry(entry_id)
        timestamp = datetime.now(UTC) if changed_at is None else _aware_utc(
            changed_at, "changed_at"
        )
        if timestamp < current.updated_at:
            raise ValueError("changed_at cannot precede updated_at.")
        metadata = dict(current.metadata)
        metadata["deprecation_reason"] = _require_text(reason, "reason")
        metadata["deprecated_at"] = timestamp.isoformat()
        return self.replace_knowledge_entry(
            replace(
                current,
                status=KnowledgeEntryStatus.DEPRECATED,
                causal_certainty=CausalCertainty.PROBABLE,
                updated_at=timestamp,
                metadata=metadata,
            )
        )

    def knowledge_entry(self, entry_id: str) -> KnowledgeEntry:
        key = _require_identifier(entry_id, "entry_id")
        try:
            return self._entries[key]
        except KeyError as error:
            raise UnknownKnowledgeEntryError(f"Unknown knowledge entry {key!r}.") from error

    def knowledge_entries(
        self,
        *,
        status: KnowledgeEntryStatus | None = None,
        active_only: bool = False,
    ) -> tuple[KnowledgeEntry, ...]:
        if status is not None and not isinstance(status, KnowledgeEntryStatus):
            raise TypeError("status must be a KnowledgeEntryStatus or None.")
        if active_only and status is not None:
            raise ValueError("active_only cannot be combined with status.")
        entries = tuple(sorted(self._entries.values(), key=lambda x: x.id))
        if active_only:
            superseded = _superseded_ids(entries)
            return tuple(
                entry
                for entry in entries
                if entry.status is KnowledgeEntryStatus.VALIDATED
                and entry.id not in superseded
            )
        return tuple(entry for entry in entries if status is None or entry.status is status)

    def entries_for_investigation(
        self, investigation_id: str
    ) -> tuple[KnowledgeEntry, ...]:
        investigation = self.investigation(investigation_id)
        return tuple(
            entry
            for entry in self.knowledge_entries()
            if entry.source_investigation_id == investigation.id
        )

    def entries_for_category(
        self, category_id: str, *, active_only: bool = True
    ) -> tuple[KnowledgeEntry, ...]:
        category = self._taxonomy.require_root_cause(category_id).id
        return tuple(
            entry
            for entry in self.knowledge_entries(active_only=active_only)
            if entry.category_id == category
        )

    def entries_for_domain(
        self, domain_id: str, *, active_only: bool = True
    ) -> tuple[KnowledgeEntry, ...]:
        domain = self._taxonomy.require_domain(domain_id).id
        return tuple(
            entry
            for entry in self.knowledge_entries(active_only=active_only)
            if domain in tuple(entry.metadata.get("domain_ids", ()))
        )

    def snapshot(
        self,
        *,
        created_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RegistrySnapshot:
        return RegistrySnapshot(
            investigations=self.investigations(),
            knowledge_entries=self.knowledge_entries(),
            taxonomy_version=self._taxonomy.version,
            created_at=datetime.now(UTC)
            if created_at is None
            else _aware_utc(created_at, "created_at"),
            metadata=metadata or {},
        )

    def _validate_investigation(self, investigation: InvestigationCase) -> None:
        for signal in investigation.signals:
            self._taxonomy.require_domain(signal.domain)
        for hypothesis in investigation.hypotheses:
            self._taxonomy.require_root_cause(hypothesis.category_id)

    def _validate_entry(
        self, entry: KnowledgeEntry, investigation: InvestigationCase
    ) -> None:
        hypothesis = next(
            (
                item
                for item in investigation.hypotheses
                if item.id == entry.source_hypothesis_id
            ),
            None,
        )
        if hypothesis is None:
            raise InvalidKnowledgePublicationError(
                f"Entry {entry.id!r} references an unknown source hypothesis."
            )
        category = self._taxonomy.require_root_cause(entry.category_id).id
        if category != hypothesis.category_id:
            raise InvalidKnowledgePublicationError(
                "Entry category must match the source hypothesis category."
            )

        source_evidence = {item.id: item for item in investigation.evidence}
        for item in entry.evidence:
            if source_evidence.get(item.id) != item:
                raise InvalidKnowledgePublicationError(
                    f"Entry evidence {item.id!r} is absent from or differs from the case."
                )
        source_checks = {item.id: item for item in investigation.verifications}
        for check in entry.verifications:
            if source_checks.get(check.id) != check:
                raise InvalidKnowledgePublicationError(
                    f"Entry verification {check.id!r} is absent from or differs from the case."
                )

        for target_id in entry.supersedes:
            if target_id not in self._entries:
                raise SupersessionError(
                    f"Entry {entry.id!r} supersedes unknown entry {target_id!r}."
                )
        if entry.status is KnowledgeEntryStatus.VALIDATED:
            self._require_publishable_investigation(investigation, hypothesis)
            if investigation.selected_hypothesis_id != hypothesis.id:
                raise InvalidKnowledgePublicationError(
                    "Validated entry must reference the selected hypothesis."
                )
            supporting = set(hypothesis.supporting_evidence_ids)
            published = {item.id for item in entry.evidence}
            if not supporting <= published:
                raise InvalidKnowledgePublicationError(
                    "Validated entry omits supporting evidence from its hypothesis."
                )

    @staticmethod
    def _require_publishable_investigation(
        investigation: InvestigationCase,
        hypothesis: CausalHypothesis | None,
    ) -> None:
        if investigation.status is not InvestigationStatus.RESOLVED:
            raise InvalidKnowledgePublicationError(
                "Validated knowledge requires a resolved investigation."
            )
        if hypothesis is None:
            raise InvalidKnowledgePublicationError(
                "Resolved investigation has no selected hypothesis."
            )
        if hypothesis.certainty is not CausalCertainty.CONFIRMED:
            raise InvalidKnowledgePublicationError(
                "Selected hypothesis must have confirmed causal certainty."
            )
        if not any(
            check.hypothesis_id == hypothesis.id
            and check.status is VerificationStatus.PASSED
            for check in investigation.verifications
        ):
            raise InvalidKnowledgePublicationError(
                "Selected hypothesis requires at least one passed verification."
            )