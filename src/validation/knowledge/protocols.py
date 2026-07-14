"""Reproducible investigation protocols for Phase 2A causal validation.

The validation engine detects differences; this module defines how an investigator
must examine those differences before a causal conclusion may enter the knowledge
base.  Protocols are immutable, versioned investigation plans.  They prescribe
which evidence to collect, in which order, what result would support progression,
and which causal layers each step is capable of assessing.

This module deliberately does **not** infer root causes, execute shell commands,
inspect repositories, or mutate :mod:`validation.knowledge.models`.  A completed
protocol produces evidence and verification records; scientific judgement remains
explicit and auditable through ``CausalHypothesis`` and
``HypothesisEvidenceAssessment``.

Design guarantees
-----------------
* Protocol selection is explicit and domain-based; no silent heuristic assigns a
  cause from a validation failure.
* Every referenced taxonomy term is validated against the canonical Phase 2A
  taxonomy at construction time.
* Investigation steps form an acyclic dependency graph with stable identifiers.
* Evidence requirements distinguish mandatory evidence from corroboration and
  optional context.
* A protocol can instantiate reproducible ``VerificationCheck`` objects without
  coupling the protocol layer to an execution backend.
* Canonical protocol identifiers and versions are persistence-safe and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Mapping, Sequence, TypeVar

from validation.knowledge.models import EvidenceSourceKind, VerificationCheck
from validation.knowledge.taxonomy import (
    CANONICAL_TAXONOMY,
    RootCauseCategory,
    ValidationDomain,
)

__all__ = [
    "CANONICAL_PROTOCOLS",
    "EvidenceRequirement",
    "EvidenceRequirementLevel",
    "InvestigationProtocol",
    "ProtocolCatalog",
    "ProtocolStep",
    "ProtocolStepKind",
    "UnknownProtocolError",
]


# =============================================================================
# Enumerations and errors
# =============================================================================


class ProtocolStepKind(str, Enum):
    """Purpose of one investigation step."""

    REPRODUCE = "reproduce"
    INSPECT_INPUT = "inspect_input"
    INSPECT_MODULE = "inspect_module"
    INSPECT_RUNTIME = "inspect_runtime"
    INSPECT_RECORD = "inspect_record"
    INSPECT_EXPORT = "inspect_export"
    INSPECT_VALIDATION = "inspect_validation"
    COMPARE_TERMINOLOGY = "compare_terminology"
    COMPARE_TEMPORALITY = "compare_temporality"
    COMPARE_STATISTICS = "compare_statistics"
    CONTROL_EXPERIMENT = "control_experiment"
    SYNTHESIZE = "synthesize"


class EvidenceRequirementLevel(str, Enum):
    """Strength with which an evidence source is required by a step."""

    REQUIRED = "required"
    CORROBORATING = "corroborating"
    OPTIONAL = "optional"


class UnknownProtocolError(LookupError):
    """Raised when strict protocol lookup cannot resolve an identifier or alias."""


# =============================================================================
# Validation helpers
# =============================================================================


_IDENTIFIER_PATTERN = compile_pattern(r"^[a-z0-9][a-z0-9._:-]*$")
_VERSION_PATTERN = compile_pattern(r"^[a-z0-9][a-z0-9._+-]*$")
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


def _require_version(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name).lower()
    if not _VERSION_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only lowercase letters, numbers, '.', '_', '+', or '-'."
        )
    return normalized


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


def _normalize_enum_tuple(
    values: Sequence[_EnumT],
    enum_type: type[_EnumT],
    field_name: str,
) -> tuple[_EnumT, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {enum_type.__name__} values.")

    normalized: list[_EnumT] = []
    seen: set[_EnumT] = set()
    for index, value in enumerate(values):
        item = _require_enum(value, enum_type, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _normalize_model_tuple(
    values: Sequence[object],
    expected_type: type[object],
    field_name: str,
) -> tuple[object, ...]:
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


def _assert_acyclic_steps(steps: Sequence["ProtocolStep"]) -> None:
    dependencies = {step.id: set(step.depends_on) for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            raise ValueError(f"Protocol steps contain a dependency cycle at {step_id!r}.")
        visiting.add(step_id)
        for dependency_id in dependencies[step_id]:
            visit(dependency_id)
        visiting.remove(step_id)
        visited.add(step_id)

    for current_id in dependencies:
        visit(current_id)


# =============================================================================
# Protocol models
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    """Evidence that must or may be collected during one protocol step.

    ``acceptance_criteria`` describes what makes the evidence usable, not what
    causal conclusion it should produce.  This distinction prevents a protocol
    from encoding its expected cause into the collection plan.
    """

    id: str
    source_kind: EvidenceSourceKind
    description: str
    acceptance_criteria: str
    level: EvidenceRequirementLevel = EvidenceRequirementLevel.REQUIRED
    suggested_locators: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self,
            "source_kind",
            _require_enum(self.source_kind, EvidenceSourceKind, "source_kind"),
        )
        object.__setattr__(self, "description", _require_text(self.description, "description"))
        object.__setattr__(
            self,
            "acceptance_criteria",
            _require_text(self.acceptance_criteria, "acceptance_criteria"),
        )
        object.__setattr__(
            self,
            "level",
            _require_enum(self.level, EvidenceRequirementLevel, "level"),
        )
        object.__setattr__(
            self,
            "suggested_locators",
            _normalize_text_tuple(self.suggested_locators, "suggested_locators"),
        )


@dataclass(frozen=True, slots=True)
class ProtocolStep:
    """One ordered, independently verifiable investigation action."""

    id: str
    title: str
    kind: ProtocolStepKind
    procedure: str
    expected_result: str
    interpretation_boundary: str
    evidence_requirements: tuple[EvidenceRequirement, ...]
    investigates_category_ids: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    stop_if: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "kind", _require_enum(self.kind, ProtocolStepKind, "kind"))
        object.__setattr__(self, "procedure", _require_text(self.procedure, "procedure"))
        object.__setattr__(
            self,
            "expected_result",
            _require_text(self.expected_result, "expected_result"),
        )
        object.__setattr__(
            self,
            "interpretation_boundary",
            _require_text(self.interpretation_boundary, "interpretation_boundary"),
        )
        requirements = _normalize_model_tuple(
            self.evidence_requirements,
            EvidenceRequirement,
            "evidence_requirements",
        )
        requirement_ids = [item.id for item in requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("evidence_requirements contains duplicate ids.")
        if not requirements:
            raise ValueError("ProtocolStep requires at least one evidence requirement.")
        object.__setattr__(self, "evidence_requirements", requirements)
        if not any(
            requirement.level is EvidenceRequirementLevel.REQUIRED
            for requirement in requirements
        ):
            raise ValueError(
                "ProtocolStep requires at least one REQUIRED evidence requirement."
            )
        object.__setattr__(
            self,
            "investigates_category_ids",
            _normalize_identifier_tuple(
                self.investigates_category_ids,
                "investigates_category_ids",
            ),
        )
        if not self.investigates_category_ids:
            raise ValueError("ProtocolStep requires at least one investigated root-cause category.")
        for category_id in self.investigates_category_ids:
            CANONICAL_TAXONOMY.require_root_cause(category_id)
        object.__setattr__(
            self,
            "depends_on",
            _normalize_identifier_tuple(self.depends_on, "depends_on"),
        )
        if self.id in self.depends_on:
            raise ValueError("A protocol step cannot depend on itself.")
        object.__setattr__(
            self,
            "stop_if",
            None if self.stop_if is None else _require_text(self.stop_if, "stop_if"),
        )

    @property
    def required_evidence(self) -> tuple[EvidenceRequirement, ...]:
        """Evidence requirements that must be satisfied before completion."""

        return tuple(
            requirement
            for requirement in self.evidence_requirements
            if requirement.level is EvidenceRequirementLevel.REQUIRED
        )

    def to_verification_check(self, hypothesis_id: str, *, id_prefix: str = "check") -> VerificationCheck:
        """Create an unexecuted verification check for one causal hypothesis.

        Execution status and collected evidence remain unset by design.  The
        investigation workflow must create a new immutable ``VerificationCheck``
        after performing the procedure.
        """

        normalized_hypothesis_id = _require_identifier(hypothesis_id, "hypothesis_id")
        normalized_prefix = _require_identifier(id_prefix, "id_prefix")
        return VerificationCheck(
            id=f"{normalized_prefix}.{self.id}",
            hypothesis_id=normalized_hypothesis_id,
            description=self.title,
            procedure=self.procedure,
            expected_result=self.expected_result,
        )


@dataclass(frozen=True, slots=True)
class InvestigationProtocol:
    """Versioned investigation plan for one class of validation discrepancy."""

    id: str
    version: str
    title: str
    objective: str
    applicability: str
    domain_ids: tuple[str, ...]
    candidate_category_ids: tuple[str, ...]
    steps: tuple[ProtocolStep, ...]
    aliases: tuple[str, ...] = ()
    exit_criteria: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "version", _require_version(self.version, "version"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "objective", _require_text(self.objective, "objective"))
        object.__setattr__(
            self,
            "applicability",
            _require_text(self.applicability, "applicability"),
        )
        object.__setattr__(
            self,
            "domain_ids",
            _normalize_identifier_tuple(self.domain_ids, "domain_ids"),
        )
        if not self.domain_ids:
            raise ValueError("InvestigationProtocol requires at least one validation domain.")
        for domain_id in self.domain_ids:
            CANONICAL_TAXONOMY.require_domain(domain_id)

        object.__setattr__(
            self,
            "candidate_category_ids",
            _normalize_identifier_tuple(
                self.candidate_category_ids,
                "candidate_category_ids",
            ),
        )
        if not self.candidate_category_ids:
            raise ValueError("InvestigationProtocol requires candidate root-cause categories.")
        for category_id in self.candidate_category_ids:
            CANONICAL_TAXONOMY.require_root_cause(category_id)

        normalized_steps = _normalize_model_tuple(self.steps, ProtocolStep, "steps")
        if not normalized_steps:
            raise ValueError("InvestigationProtocol requires at least one step.")
        step_ids = [step.id for step in normalized_steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("steps contains duplicate ids.")
        available_ids = set(step_ids)
        for step in normalized_steps:
            unknown_dependencies = sorted(set(step.depends_on) - available_ids)
            if unknown_dependencies:
                raise ValueError(
                    f"Step {step.id!r} references unknown dependencies: "
                    + ", ".join(unknown_dependencies)
                    + "."
                )
            out_of_scope = sorted(
                set(step.investigates_category_ids) - set(self.candidate_category_ids)
            )
            if out_of_scope:
                raise ValueError(
                    f"Step {step.id!r} investigates categories outside the protocol scope: "
                    + ", ".join(out_of_scope)
                    + "."
                )
        _assert_acyclic_steps(normalized_steps)

        evidence_ids = [
            requirement.id
            for step in normalized_steps
            for requirement in step.evidence_requirements
        ]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(
                "Evidence requirement ids must be unique across the entire protocol."
            )

        investigated_categories = {
            category_id
            for step in normalized_steps
            for category_id in step.investigates_category_ids
        }
        uncovered_categories = sorted(
            set(self.candidate_category_ids) - investigated_categories
        )
        if uncovered_categories:
            raise ValueError(
                "Protocol candidate categories are not investigated by any step: "
                + ", ".join(uncovered_categories)
                + "."
            )

        object.__setattr__(self, "steps", normalized_steps)

        object.__setattr__(self, "aliases", _normalize_identifier_tuple(self.aliases, "aliases"))
        if self.id in self.aliases:
            raise ValueError("A protocol cannot declare its own id as an alias.")
        object.__setattr__(
            self,
            "exit_criteria",
            _normalize_text_tuple(self.exit_criteria, "exit_criteria"),
        )
        if not self.exit_criteria:
            raise ValueError("InvestigationProtocol requires explicit exit criteria.")
        object.__setattr__(
            self,
            "limitations",
            _normalize_text_tuple(self.limitations, "limitations"),
        )

    @property
    def qualified_id(self) -> str:
        """Identifier-safe, persistence-safe protocol identity including version.

        The separator and version token conform to the same identifier grammar used
        by the knowledge models, so the value can safely participate in persisted
        check identifiers.
        """

        version_token = self.version.replace("+", "_")
        return f"{self.id}:v{version_token}"

    def step(self, step_id: str) -> ProtocolStep:
        """Return one step by stable identifier, failing loudly when unknown."""

        normalized = _require_identifier(step_id, "step_id")
        for step in self.steps:
            if step.id == normalized:
                return step
        raise KeyError(f"Unknown step {normalized!r} in protocol {self.qualified_id!r}.")

    def evidence_requirement(self, requirement_id: str) -> EvidenceRequirement:
        """Return one protocol-wide evidence requirement by stable identifier."""

        normalized = _require_identifier(requirement_id, "requirement_id")
        for step in self.steps:
            for requirement in step.evidence_requirements:
                if requirement.id == normalized:
                    return requirement
        raise KeyError(
            f"Unknown evidence requirement {normalized!r} in protocol "
            f"{self.qualified_id!r}."
        )

    def instantiate_checks(
        self,
        hypothesis_id: str,
        *,
        id_prefix: str | None = None,
    ) -> tuple[VerificationCheck, ...]:
        """Instantiate one immutable verification check per protocol step."""

        prefix = (
            self.qualified_id
            if id_prefix is None
            else _require_identifier(id_prefix, "id_prefix")
        )
        return tuple(
            step.to_verification_check(hypothesis_id, id_prefix=prefix)
            for step in self.steps
        )

    def execution_layers(self) -> tuple[tuple[ProtocolStep, ...], ...]:
        """Return deterministic dependency layers for workflow orchestration.

        Steps in the same layer have no unresolved dependencies between them and
        may be executed independently.  The original declaration order is
        retained inside each layer.
        """

        remaining = {step.id: step for step in self.steps}
        completed: set[str] = set()
        layers: list[tuple[ProtocolStep, ...]] = []
        while remaining:
            layer = tuple(
                step
                for step in self.steps
                if step.id in remaining and set(step.depends_on) <= completed
            )
            if not layer:  # Defensive: construction already rejects cycles.
                raise RuntimeError("Protocol dependency graph cannot be resolved.")
            layers.append(layer)
            completed.update(step.id for step in layer)
            for step in layer:
                remaining.pop(step.id)
        return tuple(layers)


@dataclass(frozen=True, slots=True)
class ProtocolCatalog:
    """Immutable, alias-aware catalog of validated investigation protocols."""

    protocols: tuple[InvestigationProtocol, ...]
    version: str
    taxonomy_version: str
    _by_id: Mapping[str, InvestigationProtocol] = field(init=False, repr=False, compare=False)
    _by_qualified_id: Mapping[str, InvestigationProtocol] = field(
        init=False, repr=False, compare=False
    )
    _alias_to_id: Mapping[str, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        normalized_protocols = _normalize_model_tuple(
            self.protocols,
            InvestigationProtocol,
            "protocols",
        )
        if not normalized_protocols:
            raise ValueError("ProtocolCatalog requires at least one protocol.")
        object.__setattr__(self, "protocols", normalized_protocols)
        object.__setattr__(self, "version", _require_version(self.version, "version"))
        object.__setattr__(
            self,
            "taxonomy_version",
            _require_version(self.taxonomy_version, "taxonomy_version"),
        )
        if self.taxonomy_version != CANONICAL_TAXONOMY.version:
            raise ValueError(
                "ProtocolCatalog taxonomy_version does not match CANONICAL_TAXONOMY.version."
            )

        by_id: dict[str, InvestigationProtocol] = {}
        for protocol in normalized_protocols:
            if protocol.id in by_id:
                raise ValueError(f"Duplicate protocol id {protocol.id!r}.")
            by_id[protocol.id] = protocol

        by_qualified_id: dict[str, InvestigationProtocol] = {}
        for protocol in normalized_protocols:
            if protocol.qualified_id in by_qualified_id:
                raise ValueError(
                    f"Duplicate qualified protocol id {protocol.qualified_id!r}."
                )
            by_qualified_id[protocol.qualified_id] = protocol

        alias_to_id: dict[str, str] = {}
        for protocol in normalized_protocols:
            for alias in protocol.aliases:
                if alias in by_id:
                    raise ValueError(f"Protocol alias {alias!r} collides with a protocol id.")
                previous = alias_to_id.get(alias)
                if previous is not None and previous != protocol.id:
                    raise ValueError(
                        f"Protocol alias {alias!r} is assigned to both {previous!r} "
                        f"and {protocol.id!r}."
                    )
                alias_to_id[alias] = protocol.id

        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(
            self, "_by_qualified_id", MappingProxyType(by_qualified_id)
        )
        object.__setattr__(self, "_alias_to_id", MappingProxyType(alias_to_id))

    def resolve(self, protocol_id_or_alias: str) -> InvestigationProtocol:
        """Resolve a canonical protocol id or alias, failing loudly if unknown."""

        key = _require_identifier(protocol_id_or_alias, "protocol_id_or_alias")
        qualified_match = self._by_qualified_id.get(key)
        if qualified_match is not None:
            return qualified_match

        canonical_id = self._alias_to_id.get(key, key)
        try:
            return self._by_id[canonical_id]
        except KeyError as error:
            raise UnknownProtocolError(f"Unknown investigation protocol {key!r}.") from error

    def for_domain(self, domain_id: str) -> tuple[InvestigationProtocol, ...]:
        """Return protocols explicitly applicable to a canonical domain.

        This method narrows candidate protocols; it never selects one
        automatically or infers a root cause.
        """

        canonical_domain = CANONICAL_TAXONOMY.require_domain(domain_id).id
        return tuple(
            protocol
            for protocol in self.protocols
            if canonical_domain in protocol.domain_ids
            or ValidationDomain.GLOBAL.value in protocol.domain_ids
        )

    def investigating(self, category_id: str) -> tuple[InvestigationProtocol, ...]:
        """Return protocols capable of examining a root-cause category."""

        canonical_category = CANONICAL_TAXONOMY.require_root_cause(category_id).id
        return tuple(
            protocol
            for protocol in self.protocols
            if canonical_category in protocol.candidate_category_ids
        )


# =============================================================================
# Canonical protocol construction helpers
# =============================================================================


def _evidence(
    id: str,
    source_kind: EvidenceSourceKind,
    description: str,
    acceptance_criteria: str,
    *,
    level: EvidenceRequirementLevel = EvidenceRequirementLevel.REQUIRED,
    suggested_locators: tuple[str, ...] = (),
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=id,
        source_kind=source_kind,
        description=description,
        acceptance_criteria=acceptance_criteria,
        level=level,
        suggested_locators=suggested_locators,
    )


def _step(
    id: str,
    title: str,
    kind: ProtocolStepKind,
    procedure: str,
    expected_result: str,
    interpretation_boundary: str,
    evidence_requirements: tuple[EvidenceRequirement, ...],
    investigates: tuple[RootCauseCategory, ...],
    *,
    depends_on: tuple[str, ...] = (),
    stop_if: str | None = None,
) -> ProtocolStep:
    return ProtocolStep(
        id=id,
        title=title,
        kind=kind,
        procedure=procedure,
        expected_result=expected_result,
        interpretation_boundary=interpretation_boundary,
        evidence_requirements=evidence_requirements,
        investigates_category_ids=tuple(category.value for category in investigates),
        depends_on=depends_on,
        stop_if=stop_if,
    )


def _protocol(
    id: str,
    title: str,
    objective: str,
    applicability: str,
    domains: tuple[ValidationDomain, ...],
    candidates: tuple[RootCauseCategory, ...],
    steps: tuple[ProtocolStep, ...],
    *,
    aliases: tuple[str, ...] = (),
    exit_criteria: tuple[str, ...],
    limitations: tuple[str, ...] = (),
) -> InvestigationProtocol:
    return InvestigationProtocol(
        id=id,
        version="1.0.0",
        title=title,
        objective=objective,
        applicability=applicability,
        domain_ids=tuple(domain.value for domain in domains),
        candidate_category_ids=tuple(category.value for category in candidates),
        steps=steps,
        aliases=aliases,
        exit_criteria=exit_criteria,
        limitations=limitations,
    )


# =============================================================================
# Canonical Phase 2A investigation protocols
# =============================================================================


_MISSING_OUTPUT_CANDIDATES = (
    RootCauseCategory.INPUT_DATA,
    RootCauseCategory.CONFIGURATION,
    RootCauseCategory.MODULE_DEFINITION,
    RootCauseCategory.PARSER_IMPORT,
    RootCauseCategory.UNSUPPORTED_GMF,
    RootCauseCategory.ENGINE_EXECUTION,
    RootCauseCategory.CLINICAL_RECORDING,
    RootCauseCategory.EXPORT,
    RootCauseCategory.VALIDATION_INGESTION,
    RootCauseCategory.VALIDATION_HARMONIZATION,
    RootCauseCategory.DATA_QUALITY,
    RootCauseCategory.EXECUTION_ENVIRONMENT,
    RootCauseCategory.UNKNOWN,
)

MISSING_OR_EMPTY_OUTPUT_PROTOCOL = _protocol(
    "protocol.missing_or_empty_output",
    "Missing or empty clinical output",
    "Localize why an expected clinical event type or code is absent from one cohort without assuming that absence originated in the simulator or exporter.",
    "Use when a table has zero rows, an expected code has zero prevalence, or an event class is absent from one engine's exported cohort.",
    (
        ValidationDomain.CONDITIONS,
        ValidationDomain.ENCOUNTERS,
        ValidationDomain.MEDICATIONS,
        ValidationDomain.OBSERVATIONS,
        ValidationDomain.PROCEDURES,
        ValidationDomain.IMMUNIZATIONS,
        ValidationDomain.ALLERGIES,
        ValidationDomain.PROVENANCE,
        ValidationDomain.INTEROPERABILITY,
    ),
    _MISSING_OUTPUT_CANDIDATES,
    (
        _step(
            "reproduce_absence",
            "Reproduce and delimit the absence",
            ProtocolStepKind.REPRODUCE,
            "Re-run both engines with pinned versions, configuration, module, seed, population and output directory. Confirm the absence directly in fresh artifacts and in the validation loader output.",
            "The absence is either reproduced under controlled conditions or identified as non-reproducible/environment-specific.",
            "Reproduction establishes that a discrepancy exists; it does not identify the responsible layer.",
            (
                _evidence(
                    "fresh_run_manifest",
                    EvidenceSourceKind.REPRODUCTION,
                    "Pinned execution manifest and fresh-run result for both engines.",
                    "Includes engine versions, module hash, configuration, seed, population, timestamps, commands and output paths.",
                ),
                _evidence(
                    "raw_artifact_counts",
                    EvidenceSourceKind.RAW_DATA,
                    "Direct row and patient counts from the source artifacts.",
                    "Counts are computed from the fresh artifacts before validation normalization.",
                ),
                _evidence(
                    "loader_counts",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Rows and patients observed after validation ingestion.",
                    "References the same artifacts and cohort identifiers as the raw counts.",
                ),
            ),
            (
                RootCauseCategory.INPUT_DATA,
                RootCauseCategory.CONFIGURATION,
                RootCauseCategory.VALIDATION_INGESTION,
                RootCauseCategory.EXECUTION_ENVIRONMENT,
                RootCauseCategory.UNKNOWN,
            ),
            stop_if="Stop causal attribution and mark the case non-reproducible if the discrepancy cannot be reproduced after environment and artifact identity are verified.",
        ),
        _step(
            "verify_protocol_generation",
            "Verify that the clinical protocol can generate the event",
            ProtocolStepKind.INSPECT_MODULE,
            "Trace the expected event from the module definition through guards, transitions, probabilities and imported IR. Confirm whether the relevant state is reachable for the controlled cohort.",
            "The module either contains a reachable supported event-producing state or evidence shows that the event is absent, unreachable, altered during import or intentionally conditional.",
            "A reachable state demonstrates capability, not that it executed for the affected patients.",
            (
                _evidence(
                    "module_definition",
                    EvidenceSourceKind.MODULE_DEFINITION,
                    "Exact module states, transitions, conditions and codes relevant to the event.",
                    "Uses the same module hash recorded by the reproduction step.",
                ),
                _evidence(
                    "imported_ir",
                    EvidenceSourceKind.SOURCE_CODE,
                    "Imported IR representation and parser support for the relevant state and transition types.",
                    "Shows one-to-one translation or an explicit unsupported/error path; silent assumptions are not accepted.",
                ),
            ),
            (
                RootCauseCategory.MODULE_DEFINITION,
                RootCauseCategory.PARSER_IMPORT,
                RootCauseCategory.UNSUPPORTED_GMF,
                RootCauseCategory.CONFIGURATION,
            ),
            depends_on=("reproduce_absence",),
        ),
        _step(
            "trace_runtime_to_record",
            "Trace execution from state to internal record",
            ProtocolStepKind.INSPECT_RUNTIME,
            "Instrument or inspect a controlled execution to determine whether the event-producing state is entered, completed and recorded in the patient's internal HealthRecord with the expected provenance and encounter association.",
            "The event is localized as not executed, executed but not recorded, or correctly present in the internal record.",
            "Runtime traces from a single patient must not be generalized to population prevalence without cohort-level corroboration.",
            (
                _evidence(
                    "state_trace",
                    EvidenceSourceKind.EXECUTION_LOG,
                    "Per-patient state and transition trace for a controlled case expected to produce the event.",
                    "Contains module, state, timestamp, transition and patient identifier or deterministic surrogate.",
                ),
                _evidence(
                    "internal_record_snapshot",
                    EvidenceSourceKind.REPRODUCTION,
                    "Internal HealthRecord snapshot after the relevant state executes.",
                    "Demonstrates presence or absence of the exact event, code, dates, encounter and provenance fields.",
                ),
            ),
            (
                RootCauseCategory.ENGINE_EXECUTION,
                RootCauseCategory.CLINICAL_RECORDING,
                RootCauseCategory.UNSUPPORTED_GMF,
                RootCauseCategory.MODULE_DEFINITION,
            ),
            depends_on=("verify_protocol_generation",),
        ),
        _step(
            "trace_record_to_export",
            "Trace internal record to exported artifact",
            ProtocolStepKind.INSPECT_EXPORT,
            "For an event confirmed in the internal record, trace exporter selection, row construction, filtering, schema mapping and destination path. Compare the internal event count with raw exported rows.",
            "The exporter either preserves the internal events, transforms them incorrectly, filters them, or omits them.",
            "Export is only a supported cause when the corresponding internal event has been demonstrated to exist.",
            (
                _evidence(
                    "exporter_path",
                    EvidenceSourceKind.SOURCE_CODE,
                    "Exporter code path handling the confirmed internal entry type.",
                    "Identifies all filters, mappings and write destinations affecting the event.",
                ),
                _evidence(
                    "record_export_reconciliation",
                    EvidenceSourceKind.EXPORT_ARTIFACT,
                    "Deterministic reconciliation between internal entries and exported rows.",
                    "Uses stable event keys or a documented matching strategy and reports unmatched entries in both directions.",
                ),
            ),
            (
                RootCauseCategory.EXPORT,
                RootCauseCategory.DATA_QUALITY,
                RootCauseCategory.CONFIGURATION,
            ),
            depends_on=("trace_runtime_to_record",),
        ),
        _step(
            "audit_validation_visibility",
            "Audit validation ingestion and harmonization",
            ProtocolStepKind.INSPECT_VALIDATION,
            "Trace the confirmed raw exported rows through loader selection, schema parsing, normalization, filtering, code canonicalization and cohort construction.",
            "The validation pipeline either preserves the raw events or introduces the apparent absence.",
            "A validation-layer cause requires direct disagreement between raw artifacts and normalized pipeline data.",
            (
                _evidence(
                    "loader_trace",
                    EvidenceSourceKind.SOURCE_CODE,
                    "Loader and normalization path for the affected artifact and event type.",
                    "Shows selected file, parsed columns, filters, canonicalization and resulting row identity.",
                ),
                _evidence(
                    "raw_normalized_reconciliation",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Row-level reconciliation before and after validation normalization.",
                    "Reports every dropped, changed or unmatched event with an explicit reason.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_INGESTION,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.DATA_QUALITY,
            ),
            depends_on=("trace_record_to_export",),
        ),
        _step(
            "synthesize_causal_chain",
            "Synthesize the causal chain",
            ProtocolStepKind.SYNTHESIZE,
            "Construct competing hypotheses for every plausible layer, assess each evidence item separately against each hypothesis, execute discriminating checks, and retain uncertainty when the evidence does not isolate one cause.",
            "A supported, refuted or inconclusive hypothesis set with an explicit evidence chain and no unsupported causal leap.",
            "The protocol may end with root_cause.unknown; completion does not require forcing a specific cause.",
            (
                _evidence(
                    "causal_evidence_matrix",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "Matrix linking each hypothesis to supporting, refuting, contextual and limiting evidence.",
                    "Every causal statement references collected evidence and records unresolved alternatives.",
                ),
            ),
            _MISSING_OUTPUT_CANDIDATES,
            depends_on=(
                "reproduce_absence",
                "verify_protocol_generation",
                "trace_runtime_to_record",
                "trace_record_to_export",
                "audit_validation_visibility",
            ),
        ),
    ),
    aliases=("protocol.empty_csv", "protocol.missing_code", "protocol.zero_prevalence"),
    exit_criteria=(
        "Fresh artifacts reproduce or explicitly fail to reproduce the absence under a pinned environment.",
        "The event has been traced across module/IR, runtime, HealthRecord, exporter and validation ingestion boundaries as applicable.",
        "All retained causal hypotheses have explicit evidence assessments and verification outcomes.",
        "Any confirmed cause is supported by at least one discriminating verification, not merely by absence at the final output.",
    ),
    limitations=(
        "A single controlled patient can localize a software layer but cannot establish population-level frequency.",
        "An event legitimately absent because of protocol eligibility must not be labelled an implementation defect.",
    ),
)


_PREVALENCE_CANDIDATES = (
    RootCauseCategory.INPUT_DATA,
    RootCauseCategory.CONFIGURATION,
    RootCauseCategory.MODULE_DEFINITION,
    RootCauseCategory.PARSER_IMPORT,
    RootCauseCategory.UNSUPPORTED_GMF,
    RootCauseCategory.ENGINE_EXECUTION,
    RootCauseCategory.TEMPORAL_SEMANTICS,
    RootCauseCategory.PROBABILISTIC_SEMANTICS,
    RootCauseCategory.CLINICAL_RECORDING,
    RootCauseCategory.EXPORT,
    RootCauseCategory.TERMINOLOGY_MAPPING,
    RootCauseCategory.WORKFLOW_ADAPTATION,
    RootCauseCategory.STATISTICAL_ARTIFACT,
    RootCauseCategory.VALIDATION_INGESTION,
    RootCauseCategory.VALIDATION_HARMONIZATION,
    RootCauseCategory.VALIDATION_METRIC,
    RootCauseCategory.VALIDATION_STATISTICS,
    RootCauseCategory.DATA_QUALITY,
    RootCauseCategory.EXECUTION_ENVIRONMENT,
    RootCauseCategory.UNKNOWN,
)

PREVALENCE_DIFFERENCE_PROTOCOL = _protocol(
    "protocol.prevalence_difference",
    "Prevalence or event-frequency difference",
    "Determine whether an observed frequency difference reflects cohort construction, terminology, metric definition, stochastic variation, export visibility or genuine behavioural divergence.",
    "Use when the same clinical concept appears in both cohorts but prevalence, incidence, patient count or event frequency differs materially or statistically.",
    (
        ValidationDomain.CONDITIONS,
        ValidationDomain.ENCOUNTERS,
        ValidationDomain.MEDICATIONS,
        ValidationDomain.OBSERVATIONS,
        ValidationDomain.PROCEDURES,
        ValidationDomain.IMMUNIZATIONS,
        ValidationDomain.ALLERGIES,
        ValidationDomain.COMORBIDITY,
        ValidationDomain.MORTALITY,
    ),
    _PREVALENCE_CANDIDATES,
    (
        _step(
            "verify_comparable_estimand",
            "Verify cohort and estimand equivalence",
            ProtocolStepKind.INSPECT_VALIDATION,
            "Confirm that both metrics use the same eligible population, observation window, patient identity rules, censoring, event deduplication, concept set and denominator. Independently recompute the metric from normalized data.",
            "Both reported values represent the same estimand, or a validation/cohort-definition mismatch is demonstrated.",
            "No engine-level conclusion is valid until cohort and metric equivalence are established.",
            (
                _evidence(
                    "cohort_specification",
                    EvidenceSourceKind.CONFIGURATION,
                    "Formal cohort, time-window, concept-set and denominator specification.",
                    "The same specification is applied to both engines and is version-controlled.",
                ),
                _evidence(
                    "independent_metric_recalculation",
                    EvidenceSourceKind.REPRODUCTION,
                    "Independent patient-level recalculation of both estimates.",
                    "Reproduces reported numerator, denominator and estimate with traceable patient/event membership.",
                ),
            ),
            (
                RootCauseCategory.INPUT_DATA,
                RootCauseCategory.VALIDATION_INGESTION,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.VALIDATION_METRIC,
                RootCauseCategory.DATA_QUALITY,
            ),
        ),
        _step(
            "verify_concept_equivalence",
            "Verify terminology and event equivalence",
            ProtocolStepKind.COMPARE_TERMINOLOGY,
            "Compare code systems, codes, descriptions, units, active-status rules and event types. Recalculate frequency using a reviewed equivalence concept set and inspect unmatched concepts.",
            "The difference either persists after terminology harmonization or is explained by concept mapping and representation.",
            "Matching descriptions alone are insufficient evidence that codes are clinically equivalent.",
            (
                _evidence(
                    "concept_crosswalk",
                    EvidenceSourceKind.EXTERNAL_REFERENCE,
                    "Reviewed mapping between concepts emitted by both engines.",
                    "Records code system, code, display, version, equivalence type and reviewer/source.",
                ),
                _evidence(
                    "unmatched_concepts",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Frequency table of unmatched concepts before and after harmonization.",
                    "Includes patient counts and event counts for each unmatched concept.",
                ),
            ),
            (
                RootCauseCategory.TERMINOLOGY_MAPPING,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.EXPORT,
            ),
            depends_on=("verify_comparable_estimand",),
        ),
        _step(
            "assess_statistical_stability",
            "Assess sampling and statistical stability",
            ProtocolStepKind.COMPARE_STATISTICS,
            "Evaluate absolute and relative differences, confidence intervals, effect size, multiplicity-adjusted inference, sparse-data assumptions and sensitivity to population size and seed replication.",
            "The discrepancy is characterized as stable, unstable, clinically negligible, statistically uncertain or robust across replications.",
            "Statistical significance alone neither establishes clinical relevance nor identifies a software cause.",
            (
                _evidence(
                    "effect_and_interval_analysis",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Effect estimates with confidence intervals, multiplicity handling and assumption diagnostics.",
                    "Reports the estimand, method, assumptions, effect size and predeclared relevance threshold.",
                ),
                _evidence(
                    "seed_replication",
                    EvidenceSourceKind.REPRODUCTION,
                    "Repeated controlled simulations across deterministic seeds.",
                    "Uses a predeclared replication plan and reports between-seed variability.",
                    level=EvidenceRequirementLevel.CORROBORATING,
                ),
            ),
            (
                RootCauseCategory.STATISTICAL_ARTIFACT,
                RootCauseCategory.VALIDATION_STATISTICS,
                RootCauseCategory.EXECUTION_ENVIRONMENT,
            ),
            depends_on=("verify_comparable_estimand", "verify_concept_equivalence"),
        ),
        _step(
            "compare_protocol_semantics",
            "Compare clinical and execution semantics",
            ProtocolStepKind.INSPECT_RUNTIME,
            "Trace eligibility, guards, onset conditions, transition probabilities, RNG consumption, delays, event recording and export for matched controlled scenarios and population strata.",
            "A specific semantic divergence is isolated, an intentional workflow adaptation is demonstrated, or engine behaviour remains equivalent within the inspected pathways.",
            "Observed aggregate differences do not prove which state or transition caused them; matched traces and controlled perturbations are required.",
            (
                _evidence(
                    "module_ir_comparison",
                    EvidenceSourceKind.MODULE_DEFINITION,
                    "Side-by-side module and imported-IR representation of eligibility and event-producing pathways.",
                    "Includes transition ordering, conditions, distributions, delays and codes.",
                ),
                _evidence(
                    "matched_execution_traces",
                    EvidenceSourceKind.EXECUTION_LOG,
                    "Matched state trajectories for controlled patients or deterministic scenarios.",
                    "Shows the first point of semantic divergence and the preceding equivalent state.",
                ),
                _evidence(
                    "controlled_parameter_perturbation",
                    EvidenceSourceKind.REPRODUCTION,
                    "Experiment changing one suspected parameter or semantic at a time.",
                    "Produces the predicted directional change if the hypothesis is causal.",
                    level=EvidenceRequirementLevel.CORROBORATING,
                ),
            ),
            (
                RootCauseCategory.CONFIGURATION,
                RootCauseCategory.MODULE_DEFINITION,
                RootCauseCategory.PARSER_IMPORT,
                RootCauseCategory.UNSUPPORTED_GMF,
                RootCauseCategory.ENGINE_EXECUTION,
                RootCauseCategory.TEMPORAL_SEMANTICS,
                RootCauseCategory.PROBABILISTIC_SEMANTICS,
                RootCauseCategory.CLINICAL_RECORDING,
                RootCauseCategory.EXPORT,
                RootCauseCategory.WORKFLOW_ADAPTATION,
            ),
            depends_on=("assess_statistical_stability",),
        ),
        _step(
            "synthesize_prevalence_cause",
            "Synthesize prevalence evidence",
            ProtocolStepKind.SYNTHESIZE,
            "Evaluate competing validation, statistical, terminology, export and behavioural hypotheses against the complete evidence set. Record residual uncertainty and distinguish intentional adaptation from fidelity defects.",
            "A defensible causal assessment with explicit alternatives, limitations and recommended next verification.",
            "A robust aggregate difference may remain causally unresolved; root_cause.unknown is preferable to an unsupported behavioural claim.",
            (
                _evidence(
                    "prevalence_causal_matrix",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "Hypothesis-by-evidence assessment for the observed frequency difference.",
                    "Includes all candidate layers considered, refuting evidence and unresolved confounding.",
                ),
            ),
            _PREVALENCE_CANDIDATES,
            depends_on=(
                "verify_comparable_estimand",
                "verify_concept_equivalence",
                "assess_statistical_stability",
                "compare_protocol_semantics",
            ),
        ),
    ),
    aliases=("protocol.frequency_difference", "protocol.incidence_difference"),
    exit_criteria=(
        "Cohort membership, concept set, time window and denominator are demonstrated equivalent or their mismatch is documented as the cause.",
        "The effect is quantified with confidence intervals, relevance thresholds and replication sensitivity where feasible.",
        "Any claimed behavioural cause identifies a specific semantic divergence and at least one discriminating verification.",
        "Intentional Spanish workflow adaptations are reported separately from implementation defects.",
    ),
    limitations=(
        "Different random-number consumption can prevent patient-level identity even when population behaviour is equivalent.",
        "Synthea is an implementation reference, not epidemiological ground truth.",
    ),
)


TEMPORAL_SEQUENCE_PROTOCOL = _protocol(
    "protocol.temporal_sequence_difference",
    "Temporal sequence or age-at-event difference",
    "Determine why event ordering, delays, durations, age at onset, stop dates or longitudinal trajectories differ between engines.",
    "Use for impossible orderings, shifted event dates, different age-at-diagnosis distributions, condition duration differences or treatment-before-diagnosis findings.",
    (
        ValidationDomain.TEMPORALITY,
        ValidationDomain.CONDITIONS,
        ValidationDomain.ENCOUNTERS,
        ValidationDomain.MEDICATIONS,
        ValidationDomain.PROCEDURES,
        ValidationDomain.MORTALITY,
    ),
    (
        RootCauseCategory.INPUT_DATA,
        RootCauseCategory.CONFIGURATION,
        RootCauseCategory.MODULE_DEFINITION,
        RootCauseCategory.PARSER_IMPORT,
        RootCauseCategory.ENGINE_EXECUTION,
        RootCauseCategory.TEMPORAL_SEMANTICS,
        RootCauseCategory.CLINICAL_RECORDING,
        RootCauseCategory.EXPORT,
        RootCauseCategory.WORKFLOW_ADAPTATION,
        RootCauseCategory.VALIDATION_HARMONIZATION,
        RootCauseCategory.VALIDATION_METRIC,
        RootCauseCategory.DATA_QUALITY,
        RootCauseCategory.EXECUTION_ENVIRONMENT,
        RootCauseCategory.UNKNOWN,
    ),
    (
        _step(
            "establish_time_contract",
            "Establish the temporal contract",
            ProtocolStepKind.INSPECT_INPUT,
            "Document date precision, timezone, simulation end date, birthdate semantics, age calculation, inclusive/exclusive boundaries, step size, censoring and open-event closure rules for both engines and validation.",
            "A single explicit temporal contract is established or incompatible assumptions are identified.",
            "Date equality cannot be assessed before precision, timezone and boundary semantics are aligned.",
            (
                _evidence(
                    "temporal_configuration",
                    EvidenceSourceKind.CONFIGURATION,
                    "Pinned time-related configuration and implementation semantics.",
                    "Covers all temporal assumptions used by simulation, export and validation.",
                ),
            ),
            (
                RootCauseCategory.CONFIGURATION,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.EXECUTION_ENVIRONMENT,
            ),
        ),
        _step(
            "reconstruct_patient_timeline",
            "Reconstruct affected patient timelines",
            ProtocolStepKind.COMPARE_TEMPORALITY,
            "Build ordered timelines from raw artifacts and normalized data for matched deterministic cases. Include module/state provenance, encounters, conditions, observations, medication and procedure boundaries.",
            "The first temporal divergence and the layer where it appears are identified for each controlled case.",
            "A few timelines localize semantics but do not establish distributional impact.",
            (
                _evidence(
                    "raw_timelines",
                    EvidenceSourceKind.RAW_DATA,
                    "Chronological raw-event timelines for controlled patients.",
                    "Preserves original timestamps, precision, identifiers and references.",
                ),
                _evidence(
                    "normalized_timelines",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Corresponding timelines after validation normalization.",
                    "Every normalized event traces back to its raw source event.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.DATA_QUALITY,
                RootCauseCategory.EXPORT,
                RootCauseCategory.CLINICAL_RECORDING,
            ),
            depends_on=("establish_time_contract",),
        ),
        _step(
            "trace_delay_and_boundaries",
            "Trace delay and boundary execution",
            ProtocolStepKind.INSPECT_RUNTIME,
            "Inspect Delay state persistence, simulation stepping, transition resumption, event start/stop creation, death handling and final closure using a minimal deterministic module or fixture.",
            "Temporal semantics are shown equivalent or a specific boundary, delay or closure divergence is isolated.",
            "The minimal fixture must preserve the suspected semantic; oversimplification can remove the defect.",
            (
                _evidence(
                    "minimal_temporal_reproduction",
                    EvidenceSourceKind.REPRODUCTION,
                    "Minimal deterministic module and execution trace reproducing the temporal behaviour.",
                    "Pins birthdate, start date, step size, delays and expected event boundaries.",
                ),
                _evidence(
                    "temporal_code_path",
                    EvidenceSourceKind.SOURCE_CODE,
                    "Relevant engine, state, record and exporter time-handling code paths.",
                    "Identifies unit conversion, comparison operators and closure semantics.",
                ),
            ),
            (
                RootCauseCategory.MODULE_DEFINITION,
                RootCauseCategory.PARSER_IMPORT,
                RootCauseCategory.ENGINE_EXECUTION,
                RootCauseCategory.TEMPORAL_SEMANTICS,
                RootCauseCategory.CLINICAL_RECORDING,
                RootCauseCategory.EXPORT,
            ),
            depends_on=("reconstruct_patient_timeline",),
        ),
        _step(
            "validate_temporal_metric",
            "Validate longitudinal metric computation",
            ProtocolStepKind.INSPECT_VALIDATION,
            "Independently recompute age at event, durations, ordering violations and censoring from reviewed timelines. Compare with framework metrics and statistical summaries.",
            "The validation metric is reproduced or a metric/normalization defect is isolated.",
            "A correct patient timeline can still yield a wrong aggregate metric through censoring or denominator errors.",
            (
                _evidence(
                    "manual_temporal_recalculation",
                    EvidenceSourceKind.REPRODUCTION,
                    "Independent calculation for selected timelines and the aggregate cohort.",
                    "Documents formulas, censoring and inclusion rules and reproduces patient-level values.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.VALIDATION_METRIC,
                RootCauseCategory.DATA_QUALITY,
            ),
            depends_on=("reconstruct_patient_timeline",),
        ),
        _step(
            "synthesize_temporal_cause",
            "Synthesize temporal evidence",
            ProtocolStepKind.SYNTHESIZE,
            "Assess configuration, module, engine, recording, export and validation hypotheses against the temporal contract, controlled trace and independent metric calculation.",
            "A supported temporal cause, intentional workflow difference or explicitly unresolved case.",
            "Temporal association alone does not establish which earlier event caused a later clinical outcome.",
            (
                _evidence(
                    "temporal_causal_matrix",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "Evidence assessment for each temporal causal hypothesis.",
                    "Separates timestamp representation, engine semantics and clinical causation.",
                ),
            ),
            (
                RootCauseCategory.INPUT_DATA,
                RootCauseCategory.CONFIGURATION,
                RootCauseCategory.MODULE_DEFINITION,
                RootCauseCategory.PARSER_IMPORT,
                RootCauseCategory.ENGINE_EXECUTION,
                RootCauseCategory.TEMPORAL_SEMANTICS,
                RootCauseCategory.CLINICAL_RECORDING,
                RootCauseCategory.EXPORT,
                RootCauseCategory.WORKFLOW_ADAPTATION,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.VALIDATION_METRIC,
                RootCauseCategory.DATA_QUALITY,
                RootCauseCategory.EXECUTION_ENVIRONMENT,
                RootCauseCategory.UNKNOWN,
            ),
            depends_on=(
                "establish_time_contract",
                "reconstruct_patient_timeline",
                "trace_delay_and_boundaries",
                "validate_temporal_metric",
            ),
        ),
    ),
    aliases=("protocol.age_at_event", "protocol.event_ordering"),
    exit_criteria=(
        "Temporal assumptions are explicit and consistent across simulation, export and validation.",
        "At least one affected timeline is reconstructed end-to-end with the first divergence localized.",
        "Aggregate temporal metrics are independently reproduced.",
        "Any confirmed temporal cause is demonstrated by a controlled trace or minimal reproduction.",
    ),
)


TERMINOLOGY_MISMATCH_PROTOCOL = _protocol(
    "protocol.terminology_mismatch",
    "Clinical terminology or unit mismatch",
    "Determine whether apparently missing or different clinical events are representationally equivalent, incorrectly mapped, or genuinely different.",
    "Use when descriptions match but codes differ, code systems are inconsistent, units differ, or one concept fragments into several codes.",
    (
        ValidationDomain.CONDITIONS,
        ValidationDomain.MEDICATIONS,
        ValidationDomain.OBSERVATIONS,
        ValidationDomain.PROCEDURES,
        ValidationDomain.IMMUNIZATIONS,
        ValidationDomain.ALLERGIES,
        ValidationDomain.INTEROPERABILITY,
    ),
    (
        RootCauseCategory.MODULE_DEFINITION,
        RootCauseCategory.PARSER_IMPORT,
        RootCauseCategory.EXPORT,
        RootCauseCategory.TERMINOLOGY_MAPPING,
        RootCauseCategory.VALIDATION_HARMONIZATION,
        RootCauseCategory.DATA_QUALITY,
        RootCauseCategory.UNKNOWN,
    ),
    (
        _step(
            "inventory_concepts",
            "Inventory source and output concepts",
            ProtocolStepKind.COMPARE_TERMINOLOGY,
            "Extract code system, code, display, version, unit and frequency from module definitions, internal records and exported artifacts for both engines.",
            "A traceable concept inventory identifies the first layer where representation diverges.",
            "Display-text similarity is contextual evidence only and cannot establish semantic equivalence.",
            (
                _evidence(
                    "concept_inventory",
                    EvidenceSourceKind.RAW_DATA,
                    "Layer-by-layer concept inventory for both engines.",
                    "Includes module, IR, record and export representations with counts.",
                ),
            ),
            (
                RootCauseCategory.MODULE_DEFINITION,
                RootCauseCategory.PARSER_IMPORT,
                RootCauseCategory.EXPORT,
                RootCauseCategory.TERMINOLOGY_MAPPING,
                RootCauseCategory.DATA_QUALITY,
            ),
        ),
        _step(
            "establish_clinical_equivalence",
            "Establish clinical equivalence",
            ProtocolStepKind.COMPARE_TERMINOLOGY,
            "Review authoritative terminology sources and documented mappings to classify concepts as equivalent, broader, narrower, related or non-equivalent. Validate unit conversions separately.",
            "Every proposed mapping has a documented equivalence type and authoritative support or remains explicitly unmapped.",
            "An expert or ontology mapping can establish representation equivalence but not equal simulation behaviour.",
            (
                _evidence(
                    "authoritative_mapping",
                    EvidenceSourceKind.EXTERNAL_REFERENCE,
                    "Versioned terminology references and reviewed crosswalk.",
                    "Records source, version, mapping relation, reviewer and unresolved ambiguity.",
                ),
            ),
            (
                RootCauseCategory.TERMINOLOGY_MAPPING,
                RootCauseCategory.VALIDATION_HARMONIZATION,
            ),
            depends_on=("inventory_concepts",),
        ),
        _step(
            "recompute_after_mapping",
            "Recompute metrics after reviewed mapping",
            ProtocolStepKind.CONTROL_EXPERIMENT,
            "Apply only the reviewed mapping in an isolated analysis and recompute affected frequencies and distributions without altering source artifacts.",
            "The original discrepancy is reduced, removed or persists after semantic harmonization.",
            "Removing a discrepancy after mapping supports a representational cause; it does not prove which component introduced the mapping difference.",
            (
                _evidence(
                    "mapping_sensitivity_result",
                    EvidenceSourceKind.REPRODUCTION,
                    "Before/after metrics under the reviewed crosswalk.",
                    "Preserves original results and records exact mapping version and affected rows.",
                ),
            ),
            (
                RootCauseCategory.TERMINOLOGY_MAPPING,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.EXPORT,
            ),
            depends_on=("establish_clinical_equivalence",),
        ),
        _step(
            "synthesize_terminology_cause",
            "Synthesize terminology evidence",
            ProtocolStepKind.SYNTHESIZE,
            "Identify whether the divergence originates in module content, import, internal representation, export or validation harmonization and assess each alternative against the inventory and mapping sensitivity result.",
            "A layer-specific supported hypothesis or an explicitly unresolved terminology discrepancy.",
            "Equivalent codes do not imply equivalent timing, frequency or workflow.",
            (
                _evidence(
                    "terminology_causal_matrix",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "Hypothesis assessment across terminology layers.",
                    "References authoritative mappings and records non-equivalence explicitly.",
                ),
            ),
            (
                RootCauseCategory.MODULE_DEFINITION,
                RootCauseCategory.PARSER_IMPORT,
                RootCauseCategory.EXPORT,
                RootCauseCategory.TERMINOLOGY_MAPPING,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.DATA_QUALITY,
                RootCauseCategory.UNKNOWN,
            ),
            depends_on=("inventory_concepts", "establish_clinical_equivalence", "recompute_after_mapping"),
        ),
    ),
    aliases=("protocol.code_mismatch", "protocol.unit_mismatch"),
    exit_criteria=(
        "Every compared concept has an explicit code system, code, version and unit where applicable.",
        "Proposed equivalences are supported by authoritative, versioned references or remain unmapped.",
        "Metric sensitivity to the reviewed mapping is quantified.",
        "The origin layer of any confirmed mapping defect is identified.",
    ),
)


VALIDATION_RESULT_PROTOCOL = _protocol(
    "protocol.validation_result_audit",
    "Validation result and interpretation audit",
    "Verify that a reported finding is faithfully derived from source artifacts, normalized cohorts, metric definitions, statistical methods and interpretation rules before investigating simulator behaviour.",
    "Use when a result is surprising, internally inconsistent, disputed, highly consequential, or potentially caused by the validation framework itself.",
    (ValidationDomain.VALIDATION_PIPELINE, ValidationDomain.GLOBAL),
    (
        RootCauseCategory.VALIDATION_INGESTION,
        RootCauseCategory.VALIDATION_HARMONIZATION,
        RootCauseCategory.VALIDATION_METRIC,
        RootCauseCategory.VALIDATION_STATISTICS,
        RootCauseCategory.VALIDATION_INTERPRETATION,
        RootCauseCategory.DATA_QUALITY,
        RootCauseCategory.UNKNOWN,
    ),
    (
        _step(
            "trace_artifact_lineage",
            "Trace artifact and cohort lineage",
            ProtocolStepKind.INSPECT_VALIDATION,
            "Verify source paths, hashes, run identifiers, schemas, loader selection, normalization and cohort membership for every input contributing to the finding.",
            "The finding is tied to the intended immutable artifacts and a reproducible normalized cohort.",
            "Correct lineage is necessary but does not validate the metric or conclusion.",
            (
                _evidence(
                    "artifact_lineage",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Artifact-to-cohort lineage with hashes and row counts.",
                    "Every normalized row can be traced to an immutable source artifact and run.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_INGESTION,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.DATA_QUALITY,
            ),
        ),
        _step(
            "recompute_metric_independently",
            "Recompute the metric independently",
            ProtocolStepKind.INSPECT_VALIDATION,
            "Implement or calculate the metric through an independent minimal path using the declared estimand, inclusion rules, numerator, denominator, censoring and missing-data policy.",
            "The independent result agrees within numerical tolerance or isolates a metric/normalization defect.",
            "Agreement between two implementations can still preserve a shared specification error; the estimand must also be clinically reviewed.",
            (
                _evidence(
                    "independent_metric",
                    EvidenceSourceKind.REPRODUCTION,
                    "Independent metric calculation and patient-level membership trace.",
                    "Documents formula, tolerance and all inclusion/exclusion decisions.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.VALIDATION_METRIC,
            ),
            depends_on=("trace_artifact_lineage",),
        ),
        _step(
            "verify_statistical_method",
            "Verify statistical method and assumptions",
            ProtocolStepKind.COMPARE_STATISTICS,
            "Review test selection, assumptions, sparse-data handling, confidence interval, effect size, multiplicity correction, numerical implementation and decision thresholds. Reproduce with an independent trusted implementation where feasible.",
            "The statistical result is reproduced with valid assumptions or a statistical-method defect is demonstrated.",
            "A correct p-value does not validate the scientific importance or causal interpretation of the effect.",
            (
                _evidence(
                    "statistical_reproduction",
                    EvidenceSourceKind.REPRODUCTION,
                    "Independent statistical calculation with diagnostics.",
                    "Reports inputs, library/version, assumptions, outputs and tolerance.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_STATISTICS,
                RootCauseCategory.DATA_QUALITY,
            ),
            depends_on=("recompute_metric_independently",),
        ),
        _step(
            "audit_interpretation_chain",
            "Audit evidence-to-narrative interpretation",
            ProtocolStepKind.INSPECT_VALIDATION,
            "Trace finding status, confidence, severity, recommendations and narrative back to statistical evidence and explicit interpretation rules. Check that uncertainty and alternatives are preserved.",
            "Every interpretive statement is supported by evidence and rules, or an overstatement/misclassification is isolated.",
            "Interpretation logic may recommend investigation but must not state an unverified root cause as fact.",
            (
                _evidence(
                    "interpretation_trace",
                    EvidenceSourceKind.PIPELINE_RESULT,
                    "Finding-to-evidence-to-rule-to-narrative trace.",
                    "Every causal or severity statement names its evidence and decision rule.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_INTERPRETATION,
                RootCauseCategory.UNKNOWN,
            ),
            depends_on=("verify_statistical_method",),
        ),
        _step(
            "synthesize_validation_audit",
            "Synthesize validation audit",
            ProtocolStepKind.SYNTHESIZE,
            "Determine whether the finding is valid, corrected, downgraded, withdrawn or still uncertain. Preserve original and corrected outputs with provenance.",
            "An auditable disposition of the validation finding and any required corrective action.",
            "Passing this audit validates the measurement chain, not the correctness of either simulator.",
            (
                _evidence(
                    "validation_audit_record",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "Final audit record and disposition.",
                    "References all reproduced calculations and preserves original result identifiers.",
                ),
            ),
            (
                RootCauseCategory.VALIDATION_INGESTION,
                RootCauseCategory.VALIDATION_HARMONIZATION,
                RootCauseCategory.VALIDATION_METRIC,
                RootCauseCategory.VALIDATION_STATISTICS,
                RootCauseCategory.VALIDATION_INTERPRETATION,
                RootCauseCategory.DATA_QUALITY,
                RootCauseCategory.UNKNOWN,
            ),
            depends_on=(
                "trace_artifact_lineage",
                "recompute_metric_independently",
                "verify_statistical_method",
                "audit_interpretation_chain",
            ),
        ),
    ),
    aliases=("protocol.pipeline_audit", "protocol.finding_audit"),
    exit_criteria=(
        "Artifact lineage and normalized cohort membership are reproducible.",
        "The metric and statistical result are independently reproduced or corrected.",
        "Interpretive claims do not exceed the evidence and preserve uncertainty.",
        "Original and corrected findings remain linked through stable identifiers and provenance.",
    ),
)


GENERIC_ROOT_CAUSE_PROTOCOL = _protocol(
    "protocol.generic_root_cause",
    "Generic evidence-backed root-cause investigation",
    "Provide a safe fallback workflow for discrepancies not yet covered by a specialized canonical protocol.",
    "Use only when no specialized protocol adequately covers the observed discrepancy; document why specialized protocols were insufficient.",
    (ValidationDomain.GLOBAL,),
    tuple(RootCauseCategory),
    (
        _step(
            "reproduce_and_scope",
            "Reproduce and scope the discrepancy",
            ProtocolStepKind.REPRODUCE,
            "Reproduce the finding under a pinned environment, identify affected domains and quantify its scope without assigning a cause.",
            "A stable detection signal and bounded affected population, event set or artifact.",
            "Reproducibility and scope are descriptive evidence, not causal evidence.",
            (
                _evidence(
                    "controlled_reproduction",
                    EvidenceSourceKind.REPRODUCTION,
                    "Pinned reproduction and quantified scope.",
                    "Includes immutable inputs, configuration, versions and result identifiers.",
                ),
            ),
            tuple(RootCauseCategory),
        ),
        _step(
            "map_system_boundaries",
            "Map the full data and execution path",
            ProtocolStepKind.INSPECT_RUNTIME,
            "Map every boundary from input and module definition through parser/IR, engine, record, export, validation and interpretation. Identify where the two paths first diverge.",
            "A boundary map with evidence availability and first observed divergence.",
            "The first observed divergence is not necessarily the originating cause; upstream latent differences must remain candidates.",
            (
                _evidence(
                    "boundary_map",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "End-to-end system boundary and evidence map.",
                    "Names artifacts, code paths, transformations and unresolved blind spots.",
                ),
            ),
            tuple(RootCauseCategory),
            depends_on=("reproduce_and_scope",),
        ),
        _step(
            "design_discriminating_checks",
            "Design and execute discriminating checks",
            ProtocolStepKind.CONTROL_EXPERIMENT,
            "Form competing testable hypotheses and design checks whose outcomes distinguish between them. Prefer one-variable perturbations, minimal reproductions and independent recalculations.",
            "Each retained hypothesis has at least one completed discriminating check or an explicit evidence limitation.",
            "Checks that produce the same expected outcome under competing hypotheses are not discriminating evidence.",
            (
                _evidence(
                    "discriminating_experiments",
                    EvidenceSourceKind.REPRODUCTION,
                    "Results of tests designed to separate competing hypotheses.",
                    "Predeclares expected outcomes under each hypothesis and records actual results.",
                ),
            ),
            tuple(RootCauseCategory),
            depends_on=("map_system_boundaries",),
        ),
        _step(
            "synthesize_generic_cause",
            "Synthesize evidence without forced attribution",
            ProtocolStepKind.SYNTHESIZE,
            "Assess each evidence item against every retained hypothesis, record refutations and limitations, and publish a cause only when the verification standard in knowledge.models is met.",
            "A supported cause, refuted alternatives, or an explicit unknown/inconclusive outcome.",
            "The protocol is successful even when it concludes that evidence is insufficient.",
            (
                _evidence(
                    "generic_causal_matrix",
                    EvidenceSourceKind.EXPERT_REVIEW,
                    "Complete hypothesis-evidence-verification matrix.",
                    "Contains no causal statement without an evidence reference and rationale.",
                ),
            ),
            tuple(RootCauseCategory),
            depends_on=(
                "reproduce_and_scope",
                "map_system_boundaries",
                "design_discriminating_checks",
            ),
        ),
    ),
    aliases=("protocol.generic", "protocol.unknown"),
    exit_criteria=(
        "The discrepancy is reproduced or explicitly classified as non-reproducible.",
        "Competing hypotheses span all plausible system layers identified by the boundary map.",
        "At least one discriminating check is completed for any supported causal conclusion.",
        "Insufficient evidence results in an unknown or inconclusive conclusion rather than forced attribution.",
    ),
    limitations=(
        "The generic protocol is intentionally broad and should not replace a more specific reviewed protocol.",
    ),
)


CANONICAL_PROTOCOLS = ProtocolCatalog(
    protocols=(
        MISSING_OR_EMPTY_OUTPUT_PROTOCOL,
        PREVALENCE_DIFFERENCE_PROTOCOL,
        TEMPORAL_SEQUENCE_PROTOCOL,
        TERMINOLOGY_MISMATCH_PROTOCOL,
        VALIDATION_RESULT_PROTOCOL,
        GENERIC_ROOT_CAUSE_PROTOCOL,
    ),
    version="phase2a.2",
    taxonomy_version=CANONICAL_TAXONOMY.version,
)