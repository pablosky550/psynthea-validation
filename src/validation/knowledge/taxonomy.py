"""Canonical taxonomy for evidence-backed root-cause investigations.

Phase 2A must distinguish *where* a discrepancy is observed from *why* it
occurred.  An empty ``observations.csv`` belongs to the observations domain,
but its root cause may be export, module semantics, unsupported GMF behaviour,
configuration, or data quality.  Conflating these dimensions would encode an
untested causal claim into the classification itself.

This module therefore defines two orthogonal, immutable taxonomic axes:

``ROOT_CAUSE``
    The component or mechanism that produced a validated discrepancy.

``VALIDATION_DOMAIN``
    The clinical or technical area in which the discrepancy is observed.

The taxonomy contains no detection heuristics and performs no causal inference.
It only supplies stable identifiers, definitions, hierarchy validation and
strict lookup facilities for hypotheses, investigation protocols and published
knowledge entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence, TypeVar

__all__ = [
    "CANONICAL_TAXONOMY",
    "RootCauseCategory",
    "TaxonomyAxis",
    "TaxonomyCatalog",
    "TaxonomyTerm",
    "UnknownTaxonomyTermError",
    "ValidationDomain",
]


class TaxonomyAxis(str, Enum):
    """Independent dimensions used to classify Phase 2A knowledge."""

    ROOT_CAUSE = "root_cause"
    VALIDATION_DOMAIN = "validation_domain"


class RootCauseCategory(str, Enum):
    """Stable identifiers for selectable root-cause categories.

    The values, rather than enum member names, are persisted in
    :class:`~validation.knowledge.models.CausalHypothesis` and
    :class:`~validation.knowledge.models.KnowledgeEntry`.
    """

    INPUT_DATA = "root_cause.input_data"
    CONFIGURATION = "root_cause.configuration"
    MODULE_DEFINITION = "root_cause.module_definition"
    PARSER_IMPORT = "root_cause.compatibility.parser_import"
    UNSUPPORTED_GMF = "root_cause.compatibility.unsupported_gmf"
    ROUND_TRIP = "root_cause.compatibility.round_trip"
    ENGINE_EXECUTION = "root_cause.engine.execution"
    TEMPORAL_SEMANTICS = "root_cause.engine.temporal_semantics"
    PROBABILISTIC_SEMANTICS = "root_cause.engine.probabilistic_semantics"
    CLINICAL_RECORDING = "root_cause.clinical_recording"
    EXPORT = "root_cause.export"
    TERMINOLOGY_MAPPING = "root_cause.terminology_mapping"
    WORKFLOW_ADAPTATION = "root_cause.workflow_adaptation"
    STATISTICAL_ARTIFACT = "root_cause.statistical_artifact"
    DATA_QUALITY = "root_cause.data_quality"
    VALIDATION_INGESTION = "root_cause.validation.ingestion"
    VALIDATION_HARMONIZATION = "root_cause.validation.harmonization"
    VALIDATION_METRIC = "root_cause.validation.metric_computation"
    VALIDATION_STATISTICS = "root_cause.validation.statistical_method"
    VALIDATION_INTERPRETATION = "root_cause.validation.interpretation_logic"
    EXECUTION_ENVIRONMENT = "root_cause.execution_environment"
    UNKNOWN = "root_cause.unknown"


class ValidationDomain(str, Enum):
    """Stable identifiers for affected validation domains."""

    DEMOGRAPHICS = "domain.demographics"
    CONDITIONS = "domain.conditions"
    ENCOUNTERS = "domain.encounters"
    MEDICATIONS = "domain.medications"
    OBSERVATIONS = "domain.observations"
    PROCEDURES = "domain.procedures"
    IMMUNIZATIONS = "domain.immunizations"
    ALLERGIES = "domain.allergies"
    TEMPORALITY = "domain.temporality"
    COMORBIDITY = "domain.comorbidity"
    COSTS = "domain.costs"
    REFERRALS = "domain.referrals"
    PRIMARY_CARE = "domain.primary_care"
    INTEROPERABILITY = "domain.interoperability"
    PROVENANCE = "domain.provenance"
    MORTALITY = "domain.mortality"
    VALIDATION_PIPELINE = "domain.validation_pipeline"
    GLOBAL = "domain.global"


class UnknownTaxonomyTermError(LookupError):
    """Raised when strict taxonomy lookup cannot resolve an identifier or alias."""


_IDENTIFIER_PATTERN = compile_pattern(r"^[a-z0-9][a-z0-9._:-]*$")
_EnumT = TypeVar("_EnumT", bound=Enum)


def _require_enum(value: _EnumT, enum_type: type[_EnumT], field_name: str) -> _EnumT:
    if not isinstance(value, enum_type):
        raise TypeError(
            f"{field_name} must be a {enum_type.__name__} member, "
            f"got {type(value).__name__}."
        )
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_identifier(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name).lower()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only lowercase letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _normalize_text_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_text(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _normalize_identifier_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of identifiers.")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_identifier(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class TaxonomyTerm:
    """One immutable node in a taxonomy axis.

    ``selectable=False`` is used for organizational parent nodes.  Such terms
    may structure investigation protocols but must not be persisted as the
    final category of a causal hypothesis or knowledge entry.
    """

    id: str
    axis: TaxonomyAxis
    label: str
    definition: str
    investigation_question: str
    parent_id: str | None = None
    selectable: bool = True
    aliases: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    deprecated: bool = False
    replacement_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "axis", _require_enum(self.axis, TaxonomyAxis, "axis"))
        object.__setattr__(self, "label", _require_text(self.label, "label"))
        object.__setattr__(self, "definition", _require_text(self.definition, "definition"))
        object.__setattr__(
            self,
            "investigation_question",
            _require_text(self.investigation_question, "investigation_question"),
        )
        object.__setattr__(
            self,
            "parent_id",
            None if self.parent_id is None else _require_identifier(self.parent_id, "parent_id"),
        )
        if not isinstance(self.selectable, bool):
            raise TypeError("selectable must be a bool.")
        object.__setattr__(self, "aliases", _normalize_identifier_tuple(self.aliases, "aliases"))
        object.__setattr__(self, "examples", _normalize_text_tuple(self.examples, "examples"))
        if not isinstance(self.deprecated, bool):
            raise TypeError("deprecated must be a bool.")
        object.__setattr__(
            self,
            "replacement_id",
            None
            if self.replacement_id is None
            else _require_identifier(self.replacement_id, "replacement_id"),
        )

        if self.id == self.parent_id:
            raise ValueError("A taxonomy term cannot be its own parent.")
        if self.id in self.aliases:
            raise ValueError("A taxonomy term cannot declare its own id as an alias.")
        if self.deprecated and self.replacement_id is None:
            raise ValueError("A deprecated taxonomy term requires replacement_id.")
        if not self.deprecated and self.replacement_id is not None:
            raise ValueError("replacement_id is only valid for deprecated taxonomy terms.")
        if self.replacement_id == self.id:
            raise ValueError("A taxonomy term cannot replace itself.")
        if self.deprecated and self.selectable:
            raise ValueError("Deprecated taxonomy terms cannot remain selectable.")


@dataclass(frozen=True, slots=True)
class TaxonomyCatalog:
    """Validated immutable taxonomy with strict, alias-aware lookup."""

    terms: tuple[TaxonomyTerm, ...]
    version: str
    _by_id: Mapping[str, TaxonomyTerm] = field(init=False, repr=False, compare=False)
    _alias_to_id: Mapping[str, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.terms, (str, bytes)) or not isinstance(self.terms, Sequence):
            raise TypeError("terms must be a sequence of TaxonomyTerm values.")
        normalized_terms = tuple(self.terms)
        for index, term in enumerate(normalized_terms):
            if not isinstance(term, TaxonomyTerm):
                raise TypeError(
                    f"terms[{index}] must be TaxonomyTerm, got {type(term).__name__}."
                )
        if not normalized_terms:
            raise ValueError("TaxonomyCatalog requires at least one term.")
        object.__setattr__(self, "terms", normalized_terms)
        object.__setattr__(self, "version", _require_identifier(self.version, "version"))

        by_id: dict[str, TaxonomyTerm] = {}
        for term in normalized_terms:
            if term.id in by_id:
                raise ValueError(f"Duplicate taxonomy term id {term.id!r}.")
            by_id[term.id] = term

        alias_to_id: dict[str, str] = {}
        for term in normalized_terms:
            for alias in term.aliases:
                if alias in by_id:
                    raise ValueError(
                        f"Alias {alias!r} collides with canonical taxonomy term id."
                    )
                existing = alias_to_id.get(alias)
                if existing is not None and existing != term.id:
                    raise ValueError(
                        f"Alias {alias!r} is assigned to both {existing!r} and {term.id!r}."
                    )
                alias_to_id[alias] = term.id

        for term in normalized_terms:
            if term.parent_id is not None:
                parent = by_id.get(term.parent_id)
                if parent is None:
                    raise ValueError(
                        f"Taxonomy term {term.id!r} references unknown parent {term.parent_id!r}."
                    )
                if parent.axis is not term.axis:
                    raise ValueError(
                        f"Taxonomy term {term.id!r} and parent {parent.id!r} must share an axis."
                    )
            if term.replacement_id is not None:
                replacement = by_id.get(term.replacement_id)
                if replacement is None:
                    raise ValueError(
                        f"Taxonomy term {term.id!r} references unknown replacement "
                        f"{term.replacement_id!r}."
                    )
                if replacement.axis is not term.axis:
                    raise ValueError(
                        f"Taxonomy term {term.id!r} and replacement {replacement.id!r} "
                        "must share an axis."
                    )
                if replacement.deprecated:
                    raise ValueError("A replacement taxonomy term must not be deprecated.")

        self._validate_acyclic_parents(by_id)
        self._validate_acyclic_replacements(by_id)

        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_alias_to_id", MappingProxyType(alias_to_id))

    @staticmethod
    def _validate_acyclic_parents(by_id: Mapping[str, TaxonomyTerm]) -> None:
        for start_id in by_id:
            visited: set[str] = set()
            current_id: str | None = start_id
            while current_id is not None:
                if current_id in visited:
                    raise ValueError(f"Taxonomy parent cycle detected at {current_id!r}.")
                visited.add(current_id)
                current_id = by_id[current_id].parent_id

    @staticmethod
    def _validate_acyclic_replacements(by_id: Mapping[str, TaxonomyTerm]) -> None:
        for start_id in by_id:
            visited: set[str] = set()
            current_id: str | None = start_id
            while current_id is not None:
                if current_id in visited:
                    raise ValueError(f"Taxonomy replacement cycle detected at {current_id!r}.")
                visited.add(current_id)
                current_id = by_id[current_id].replacement_id

    def resolve(self, identifier_or_alias: str) -> TaxonomyTerm:
        """Resolve a canonical id or alias, failing loudly on unknown values."""

        normalized = _require_identifier(identifier_or_alias, "identifier_or_alias")
        canonical_id = self._alias_to_id.get(normalized, normalized)
        try:
            return self._by_id[canonical_id]
        except KeyError as exc:
            raise UnknownTaxonomyTermError(
                f"Unknown taxonomy term or alias: {normalized!r}."
            ) from exc

    def contains(self, identifier_or_alias: str) -> bool:
        """Return whether a value resolves without weakening strict lookup elsewhere."""

        try:
            self.resolve(identifier_or_alias)
        except UnknownTaxonomyTermError:
            return False
        return True

    def require_selectable(
        self,
        identifier_or_alias: str,
        *,
        axis: TaxonomyAxis | None = None,
    ) -> TaxonomyTerm:
        """Resolve a term and require it to be active, selectable and on ``axis``."""

        if axis is not None:
            _require_enum(axis, TaxonomyAxis, "axis")
        term = self.resolve(identifier_or_alias)
        if axis is not None and term.axis is not axis:
            raise ValueError(
                f"Taxonomy term {term.id!r} belongs to {term.axis.value}, not {axis.value}."
            )
        if term.deprecated:
            raise ValueError(
                f"Taxonomy term {term.id!r} is deprecated; use {term.replacement_id!r}."
            )
        if not term.selectable:
            raise ValueError(f"Taxonomy term {term.id!r} is organizational and not selectable.")
        return term

    def require_root_cause(self, identifier_or_alias: str) -> TaxonomyTerm:
        """Require a selectable root-cause category."""

        return self.require_selectable(identifier_or_alias, axis=TaxonomyAxis.ROOT_CAUSE)

    def require_domain(self, identifier_or_alias: str) -> TaxonomyTerm:
        """Require a selectable validation domain."""

        return self.require_selectable(identifier_or_alias, axis=TaxonomyAxis.VALIDATION_DOMAIN)

    def terms_for_axis(
        self,
        axis: TaxonomyAxis,
        *,
        selectable_only: bool = False,
    ) -> tuple[TaxonomyTerm, ...]:
        """Return deterministic terms for one axis in declaration order."""

        _require_enum(axis, TaxonomyAxis, "axis")
        return tuple(
            term
            for term in self.terms
            if term.axis is axis and (term.selectable or not selectable_only)
        )

    def children_of(self, identifier_or_alias: str) -> tuple[TaxonomyTerm, ...]:
        """Return direct children of a term in declaration order."""

        parent = self.resolve(identifier_or_alias)
        return tuple(term for term in self.terms if term.parent_id == parent.id)

    def ancestors_of(self, identifier_or_alias: str) -> tuple[TaxonomyTerm, ...]:
        """Return parent-to-root ancestry, nearest parent first."""

        term = self.resolve(identifier_or_alias)
        ancestors: list[TaxonomyTerm] = []
        parent_id = term.parent_id
        while parent_id is not None:
            parent = self._by_id[parent_id]
            ancestors.append(parent)
            parent_id = parent.parent_id
        return tuple(ancestors)

    def descendants_of(self, identifier_or_alias: str) -> tuple[TaxonomyTerm, ...]:
        """Return all descendants in deterministic declaration order."""

        root = self.resolve(identifier_or_alias)
        descendant_ids: set[str] = set()
        frontier = [root.id]
        while frontier:
            parent_id = frontier.pop()
            child_ids = [term.id for term in self.terms if term.parent_id == parent_id]
            descendant_ids.update(child_ids)
            frontier.extend(child_ids)
        return tuple(term for term in self.terms if term.id in descendant_ids)

    def canonicalize_many(
        self,
        values: Iterable[str],
        *,
        axis: TaxonomyAxis,
    ) -> tuple[str, ...]:
        """Resolve, validate and de-duplicate identifiers while preserving order."""

        _require_enum(axis, TaxonomyAxis, "axis")
        if isinstance(values, (str, bytes)):
            raise TypeError("values must be an iterable of taxonomy identifiers, not a string.")
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            term = self.require_selectable(value, axis=axis)
            if term.id not in seen:
                normalized.append(term.id)
                seen.add(term.id)
        if not normalized:
            raise ValueError("At least one taxonomy term is required.")
        return tuple(normalized)


# -----------------------------------------------------------------------------
# Canonical Phase 2A taxonomy
# -----------------------------------------------------------------------------


def _term(
    id: str,
    axis: TaxonomyAxis,
    label: str,
    definition: str,
    question: str,
    *,
    parent_id: str | None = None,
    selectable: bool = True,
    aliases: tuple[str, ...] = (),
    examples: tuple[str, ...] = (),
) -> TaxonomyTerm:
    return TaxonomyTerm(
        id=id,
        axis=axis,
        label=label,
        definition=definition,
        investigation_question=question,
        parent_id=parent_id,
        selectable=selectable,
        aliases=aliases,
        examples=examples,
    )


_CANONICAL_TERMS = (
    # Root-cause hierarchy -----------------------------------------------------
    _term(
        "root_cause",
        TaxonomyAxis.ROOT_CAUSE,
        "Root cause",
        "Organizational root for causal categories.",
        "Which mechanism produced the observed discrepancy?",
        selectable=False,
    ),
    _term(
        RootCauseCategory.INPUT_DATA.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Input data",
        "The source cohort or input artifact is absent, malformed, incomplete, or not comparable before simulation analysis begins.",
        "Were both engines given complete and comparable source inputs?",
        parent_id="root_cause",
        aliases=("input", "source_data"),
        examples=("A required CSV is missing before validation.",),
    ),
    _term(
        RootCauseCategory.CONFIGURATION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Configuration",
        "Different seeds, horizons, population constraints, enabled modules, or exporter settings make runs non-equivalent.",
        "Were both executions configured under equivalent experimental conditions?",
        parent_id="root_cause",
        aliases=("config",),
        examples=("Synthea exports observations while the psynthea exporter is disabled.",),
    ),
    _term(
        RootCauseCategory.MODULE_DEFINITION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Module definition",
        "The clinical protocol, state graph, codes, conditions, transitions, or probabilities differ in the module definition itself.",
        "Do both engines execute semantically equivalent module definitions?",
        parent_id="root_cause",
        aliases=("module", "protocol_definition"),
        examples=("Different hypertension onset probability in otherwise supported modules.",),
    ),
    _term(
        "root_cause.compatibility",
        TaxonomyAxis.ROOT_CAUSE,
        "GMF compatibility",
        "Organizational category for import, support and round-trip fidelity of the Synthea Generic Module Framework.",
        "Was GMF semantics preserved when crossing the compatibility boundary?",
        parent_id="root_cause",
        selectable=False,
    ),
    _term(
        RootCauseCategory.PARSER_IMPORT.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Parser or import translation",
        "The JSON-to-IR translation misreads, drops, rewrites, or resolves a supported module construct incorrectly.",
        "Does the imported IR faithfully represent the source GMF construct?",
        parent_id="root_cause.compatibility",
        aliases=("parser", "import"),
        examples=("A transition target is resolved to the wrong state during import.",),
    ),
    _term(
        RootCauseCategory.UNSUPPORTED_GMF.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Unsupported GMF construct",
        "The module relies on a state, transition, logic type, field, or semantic that psynthea does not implement faithfully.",
        "Does the failing path contain a GMF construct outside the supported compatibility subset?",
        parent_id="root_cause.compatibility",
        aliases=("unsupported", "gmf_unsupported"),
        examples=("A required GMF state is rejected or intentionally unsupported.",),
    ),
    _term(
        RootCauseCategory.ROUND_TRIP.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Round-trip transformation",
        "Importing and re-exporting the supported IR changes representable module semantics or structure.",
        "Does load followed by dump preserve the supported IR identity?",
        parent_id="root_cause.compatibility",
        aliases=("roundtrip",),
        examples=("A complex transition loses a branch during export.",),
    ),
    _term(
        "root_cause.engine",
        TaxonomyAxis.ROOT_CAUSE,
        "Simulation engine",
        "Organizational category for runtime execution semantics.",
        "Did both engines execute the same protocol semantics?",
        parent_id="root_cause",
        selectable=False,
    ),
    _term(
        RootCauseCategory.ENGINE_EXECUTION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Engine execution",
        "State processing, transition following, context management, or lifecycle execution differs at runtime.",
        "Does the same IR produce the same state trajectory under controlled inputs?",
        parent_id="root_cause.engine",
        aliases=("engine", "runtime"),
        examples=("A state is processed twice in one engine and once in the other.",),
    ),
    _term(
        RootCauseCategory.TEMPORAL_SEMANTICS.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Temporal semantics",
        "Differences in time stepping, delay resolution, onset or stop dates, age calculation, or event ordering alter outcomes.",
        "Are time advancement and event boundaries semantically equivalent?",
        parent_id="root_cause.engine",
        aliases=("temporal", "time"),
        examples=("A Delay resumes one simulation step later than in Synthea.",),
    ),
    _term(
        RootCauseCategory.PROBABILISTIC_SEMANTICS.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Probabilistic semantics",
        "Random-number consumption, weighted sampling, probability normalization, or branch ordering changes stochastic outcomes.",
        "Do both engines apply probabilities and consume randomness equivalently?",
        parent_id="root_cause.engine",
        aliases=("probability", "rng"),
        examples=("Distributed transitions normalize weights differently.",),
    ),
    _term(
        RootCauseCategory.CLINICAL_RECORDING.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Clinical recording",
        "The engine executes the event but fails to create, associate, close, or retain the corresponding internal clinical record entry.",
        "Was the event produced by the state and represented correctly in HealthRecord?",
        parent_id="root_cause",
        aliases=("record", "health_record"),
        examples=("Observation executes but no ObservationEntry is stored.",),
    ),
    _term(
        RootCauseCategory.EXPORT.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Export",
        "A valid internal event is missing, transformed incorrectly, or written to the wrong output artifact by an exporter.",
        "Does the internal record contain the event that is absent or malformed in output?",
        parent_id="root_cause",
        aliases=("exporter", "serialization"),
        examples=("ObservationEntry exists but observations.csv has no corresponding row.",),
    ),
    _term(
        RootCauseCategory.TERMINOLOGY_MAPPING.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Terminology mapping",
        "Equivalent clinical concepts use inconsistent codes, systems, units, or mappings across engines or exporters.",
        "Do apparently different codes or units represent the same clinical concept?",
        parent_id="root_cause",
        aliases=("mapping", "terminology"),
        examples=("The same diagnosis is emitted under different SNOMED CT codes.",),
    ),
    _term(
        RootCauseCategory.WORKFLOW_ADAPTATION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Workflow adaptation",
        "An intentional healthcare-system adaptation changes encounters, referrals, providers, or care pathways without necessarily changing clinical coherence.",
        "Is the difference an intended Spanish care-pathway adaptation rather than a fidelity defect?",
        parent_id="root_cause",
        aliases=("spanish_adaptation", "workflow"),
        examples=("A primary-care encounter is added before specialist referral.",),
    ),
    _term(
        RootCauseCategory.STATISTICAL_ARTIFACT.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Statistical artifact",
        "The apparent discrepancy is explained by sampling variability, multiplicity, sparse data, unstable estimation, or an unsuitable statistical comparison.",
        "Does the discrepancy persist under effect-size, confidence-interval and replication analysis?",
        parent_id="root_cause",
        aliases=("statistics", "sampling_noise"),
        examples=("A tiny effect is significant only because the cohort is extremely large.",),
    ),
    _term(
        RootCauseCategory.DATA_QUALITY.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Generated data quality",
        "Output rows exist but contain invalid values, broken references, duplicate events, impossible dates, or schema violations.",
        "Are the generated artifacts internally valid before comparing clinical behaviour?",
        parent_id="root_cause",
        aliases=("quality",),
        examples=("A medication row references a non-existent encounter.",),
    ),
    _term(
        "root_cause.validation",
        TaxonomyAxis.ROOT_CAUSE,
        "Validation framework",
        "Organizational category for discrepancies introduced by the comparison pipeline rather than by either simulator.",
        "Did the validation framework create or distort the apparent difference?",
        parent_id="root_cause",
        selectable=False,
    ),
    _term(
        RootCauseCategory.VALIDATION_INGESTION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Validation ingestion",
        "The validation loader reads the wrong artifact, schema, delimiter, encoding, table, or subset, creating a discrepancy not present in the source outputs.",
        "Does direct inspection of the source artifact disagree with the rows loaded by the validation pipeline?",
        parent_id="root_cause.validation",
        aliases=("loader", "validation_loader"),
        examples=("The loader reads an obsolete observations.csv from a previous run.",),
    ),
    _term(
        RootCauseCategory.VALIDATION_HARMONIZATION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Validation harmonization",
        "Normalization, cohort alignment, code canonicalization, unit conversion, deduplication, or join logic makes otherwise comparable outputs appear different.",
        "Does the discrepancy appear only after normalization or cohort harmonization?",
        parent_id="root_cause.validation",
        aliases=("normalization", "harmonization"),
        examples=("Equivalent UCUM units are not converted before comparison.",),
    ),
    _term(
        RootCauseCategory.VALIDATION_METRIC.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Metric computation",
        "The validation framework defines or computes a metric incorrectly, including denominator selection, event counting, censoring, or aggregation.",
        "Can the reported metric be independently reproduced from the normalized cohort?",
        parent_id="root_cause.validation",
        aliases=("metric", "metric_bug"),
        examples=("Prevalence is divided by encounters instead of unique patients.",),
    ),
    _term(
        RootCauseCategory.VALIDATION_STATISTICS.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Statistical method",
        "The selected test, assumptions, implementation, multiplicity correction, confidence interval, or effect-size calculation is inappropriate or incorrect.",
        "Would a validated independent implementation produce the same statistical conclusion?",
        parent_id="root_cause.validation",
        aliases=("statistical_method", "test_selection"),
        examples=("Chi-square is used despite sparse expected counts requiring Fisher's exact test.",),
    ),
    _term(
        RootCauseCategory.VALIDATION_INTERPRETATION.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Interpretation logic",
        "The evidence, confidence, severity, recommendation, or narrative layer overstates, understates, or misclassifies a valid statistical result.",
        "Is the underlying result correct but its scientific interpretation unsupported or inconsistent?",
        parent_id="root_cause.validation",
        aliases=("interpretation", "narrative_logic"),
        examples=("A small non-clinical effect is labelled as a confirmed major behavioural defect.",),
    ),
    _term(
        RootCauseCategory.EXECUTION_ENVIRONMENT.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Execution environment",
        "Version drift, locale, timezone, dependency, filesystem, concurrency, or platform behaviour changes the result.",
        "Can the discrepancy be reproduced in a controlled, version-pinned environment?",
        parent_id="root_cause",
        aliases=("environment", "platform"),
        examples=("Different timezone settings shift event dates across midnight.",),
    ),
    _term(
        RootCauseCategory.UNKNOWN.value,
        TaxonomyAxis.ROOT_CAUSE,
        "Unknown root cause",
        "Evidence is insufficient to assign a demonstrated causal category.",
        "Which additional evidence is required before a causal category can be selected?",
        parent_id="root_cause",
        aliases=("unresolved",),
        examples=("The discrepancy is reproducible but no layer has yet been isolated.",),
    ),
    # Validation-domain hierarchy --------------------------------------------
    _term(
        "domain",
        TaxonomyAxis.VALIDATION_DOMAIN,
        "Validation domain",
        "Organizational root for affected clinical and technical domains.",
        "Where is the discrepancy observed?",
        selectable=False,
    ),
    *(
        _term(
            domain.value,
            TaxonomyAxis.VALIDATION_DOMAIN,
            label,
            definition,
            question,
            parent_id="domain",
            aliases=aliases,
            examples=examples,
        )
        for domain, label, definition, question, aliases, examples in (
            (
                ValidationDomain.DEMOGRAPHICS,
                "Demographics",
                "Patient age, sex, birth date, geography, race, ethnicity, or other population attributes.",
                "Which demographic distribution or field is affected?",
                ("patients", "demography"),
                ("Age distribution differs between cohorts.",),
            ),
            (
                ValidationDomain.CONDITIONS,
                "Conditions",
                "Diagnoses, onset and resolution, prevalence, incidence, and active-condition state.",
                "Which diagnosis or condition lifecycle is affected?",
                ("diagnoses",),
                ("Hypertension prevalence differs by 15 percentage points.",),
            ),
            (
                ValidationDomain.ENCOUNTERS,
                "Encounters",
                "Clinical contacts, encounter classes, providers, durations, and care settings.",
                "Which encounter type, sequence, or association is affected?",
                ("visits",),
                ("Primary-care encounters are absent.",),
            ),
            (
                ValidationDomain.MEDICATIONS,
                "Medications",
                "Medication orders, exposure periods, codes, dosages, and encounter associations.",
                "Which medication event or treatment pathway is affected?",
                ("drugs",),
                ("Antihypertensive orders are missing from CSV output.",),
            ),
            (
                ValidationDomain.OBSERVATIONS,
                "Observations",
                "Vital signs, laboratory values, scores, units, missingness, and measured values.",
                "Which observation code, value, unit, or export path is affected?",
                ("labs", "vitals"),
                ("QALY observations are absent in psynthea output.",),
            ),
            (
                ValidationDomain.PROCEDURES,
                "Procedures",
                "Clinical procedures, interventions, dates, codes, and encounter associations.",
                "Which procedure event or association is affected?",
                (),
                ("A diagnostic procedure is present only in Synthea.",),
            ),
            (
                ValidationDomain.IMMUNIZATIONS,
                "Immunizations",
                "Vaccination events, products, schedules, and administration encounters.",
                "Which immunization event or schedule is affected?",
                ("vaccinations",),
                ("A vaccine dose is emitted under a different code.",),
            ),
            (
                ValidationDomain.ALLERGIES,
                "Allergies",
                "Allergy onset, resolution, substances, reactions, and severity.",
                "Which allergy representation or lifecycle is affected?",
                (),
                ("Allergy entries are not retained after import.",),
            ),
            (
                ValidationDomain.TEMPORALITY,
                "Temporality",
                "Ordering, intervals, durations, age at event, and longitudinal trajectory coherence.",
                "Which temporal constraint or event sequence is violated?",
                ("longitudinal",),
                ("Medication precedes diagnosis.",),
            ),
            (
                ValidationDomain.COMORBIDITY,
                "Comorbidity",
                "Joint disease occurrence, clinical associations, and cross-module dependencies.",
                "Which relationship between conditions or risk factors is affected?",
                ("relationships",),
                ("The hypertension-diabetes association is not preserved.",),
            ),
            (
                ValidationDomain.COSTS,
                "Costs",
                "Claims, payer, billing, cost, and economic output where applicable.",
                "Which economic concept is affected and is it in scope for psynthea?",
                ("billing", "claims"),
                ("US billing metadata is intentionally absent.",),
            ),
            (
                ValidationDomain.REFERRALS,
                "Referrals",
                "Referral events, origin, destination, timing, and specialty pathway.",
                "Which referral path or transition is affected?",
                (),
                ("Specialist referral is missing after primary-care assessment.",),
            ),
            (
                ValidationDomain.PRIMARY_CARE,
                "Primary care",
                "Spanish primary-care contacts, longitudinal management, and gatekeeping workflows.",
                "Which primary-care adaptation or workflow is affected?",
                ("atencion_primaria",),
                ("Follow-up occurs in specialist care instead of primary care.",),
            ),
            (
                ValidationDomain.INTEROPERABILITY,
                "Interoperability",
                "CSV, FHIR, OMOP, schemas, identifiers, references, and cross-format fidelity.",
                "Which representation, schema, or cross-format relationship is affected?",
                ("fhir", "omop", "csv"),
                ("FHIR references do not resolve after export.",),
            ),
            (
                ValidationDomain.PROVENANCE,
                "Provenance and ground truth",
                "Source module, source state, latent truth, missingness provenance, and traceability metadata attached to generated events.",
                "Which provenance or ground-truth relationship is affected?",
                ("ground_truth", "traceability"),
                ("An exported observation loses its source_state provenance.",),
            ),
            (
                ValidationDomain.MORTALITY,
                "Mortality",
                "Death events, survival time, cause of death, age at death, and mortality-related longitudinal coherence.",
                "Which mortality event, timing, or survival distribution is affected?",
                ("death", "survival"),
                ("The engines produce materially different ages at death.",),
            ),
            (
                ValidationDomain.VALIDATION_PIPELINE,
                "Validation pipeline",
                "Loaders, normalization, cohort construction, metric computation, statistics, interpretation, reporting, and validation artifacts.",
                "Which stage of the validation pipeline is affected?",
                ("validation", "comparison_pipeline"),
                ("The source outputs agree but the normalized tables differ.",),
            ),
            (
                ValidationDomain.GLOBAL,
                "Global",
                "Cross-cutting discrepancy affecting multiple domains or the complete experiment.",
                "Is the issue systemic rather than confined to one clinical domain?",
                ("cross_cutting",),
                ("Different population sizes invalidate all downstream comparisons.",),
            ),
        )
    ),
)


CANONICAL_TAXONOMY = TaxonomyCatalog(
    terms=_CANONICAL_TERMS,
    version="phase2a.2",
)