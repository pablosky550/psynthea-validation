"""Scientific rule contracts for deterministic, auditable interpretation.

Rules consume canonical :class:`EvidenceCatalog` objects and never inspect raw
pipeline outputs.  The closed execution template enforces, in order:

1. pipeline-stage readiness;
2. rule-dependency readiness;
3. evidence requirements;
4. applicability;
5. deterministic interpretation;
6. validation of derived evidence, inferences and findings.

A concrete rule implements only ``interpret`` and, when needed,
``applicability``.  It cannot silently turn missing inputs, skipped pipeline
stages, failed dependencies or implementation errors into scientific findings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final

from validation.interpretation.evidence import EvidenceCatalog
from validation.interpretation.models import (
    EvidenceAvailability,
    EvidenceReference,
    EvidenceRole,
    EvidenceValue,
    InterpretationFinding,
)

__all__ = [
    "Applicability",
    "ApplicabilityDecision",
    "ClinicalRule",
    "DerivedEvidence",
    "EpidemiologicalRule",
    "EvidenceRequirement",
    "Inference",
    "InterpretationRule",
    "PipelineStage",
    "RuleContext",
    "RuleDependency",
    "RuleDependencyAssessment",
    "RuleEvaluation",
    "RuleExecutionError",
    "RuleExecutionStatus",
    "RuleInvariantError",
    "RuleOutcome",
    "StageAssessment",
    "StageStatus",
    "StatisticalRule",
    "StructuralRule",
    "ValidationDimension",
]

_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class RuleExecutionError(RuntimeError):
    """Raised when a rule implementation cannot complete safely."""


class RuleInvariantError(RuleExecutionError):
    """Raised when a concrete rule violates the rule contract."""


class RuleExecutionStatus(str, Enum):
    COMPLETED = "completed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUATED = "not_evaluated"


class Applicability(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUATED = "not_evaluated"


class ValidationDimension(str, Enum):
    STRUCTURAL = "structural"
    FUNCTIONAL = "functional"
    STATISTICAL = "statistical"
    CLINICAL = "clinical"
    EPIDEMIOLOGICAL = "epidemiological"
    SPANISH_ADAPTATION = "spanish_adaptation"
    EXPORT = "export"
    PERFORMANCE = "performance"


class PipelineStage(str, Enum):
    INGESTION = "ingestion"
    FUNCTIONAL_VALIDATION = "functional_validation"
    STATISTICAL_VALIDATION = "statistical_validation"
    CLINICAL_VALIDATION = "clinical_validation"
    SPANISH_ADAPTATION = "spanish_adaptation"
    REPORTING = "reporting"


class StageStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_RUN = "not_run"


class DependencyPolicy(str, Enum):
    REQUIRE_COMPLETED = "require_completed"
    REQUIRE_FINDINGS = "require_findings"


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


def _normalize_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


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


@dataclass(frozen=True, slots=True)
class StageAssessment:
    stage: PipelineStage
    status: StageStatus
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage, PipelineStage):
            raise TypeError("stage must be a PipelineStage member.")
        if not isinstance(self.status, StageStatus):
            raise TypeError("status must be a StageStatus member.")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class RuleDependency:
    rule_id: str
    required: bool = True
    policy: DependencyPolicy = DependencyPolicy.REQUIRE_COMPLETED
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_identifier(self.rule_id, "rule_id"))
        if not isinstance(self.required, bool):
            raise TypeError("required must be a bool.")
        if not isinstance(self.policy, DependencyPolicy):
            raise TypeError("policy must be a DependencyPolicy member.")
        if self.rationale is not None:
            object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))


@dataclass(frozen=True, slots=True)
class RuleDependencyAssessment:
    dependency: RuleDependency
    evaluation: RuleEvaluation | None
    satisfied: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.dependency, RuleDependency):
            raise TypeError("dependency must be a RuleDependency.")
        if self.evaluation is not None and not isinstance(self.evaluation, RuleEvaluation):
            raise TypeError("evaluation must be a RuleEvaluation or None.")
        if not isinstance(self.satisfied, bool):
            raise TypeError("satisfied must be a bool.")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class RuleContext:
    validation_id: str
    module_name: str
    evidence: EvidenceCatalog
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    research_use: bool = True
    stages: Mapping[PipelineStage, StageStatus] = field(default_factory=dict)
    prior_evaluations: Mapping[str, RuleEvaluation] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation_id", _require_identifier(self.validation_id, "validation_id"))
        object.__setattr__(self, "module_name", _require_identifier(self.module_name, "module_name"))
        if not isinstance(self.evidence, EvidenceCatalog):
            raise TypeError("evidence must be an EvidenceCatalog.")
        object.__setattr__(self, "evaluated_at", _normalize_utc(self.evaluated_at, "evaluated_at"))
        if not isinstance(self.research_use, bool):
            raise TypeError("research_use must be a bool.")

        stages: dict[PipelineStage, StageStatus] = {}
        for stage, status in self.stages.items():
            if not isinstance(stage, PipelineStage) or not isinstance(status, StageStatus):
                raise TypeError("stages must map PipelineStage to StageStatus.")
            stages[stage] = status
        prior: dict[str, RuleEvaluation] = {}
        for rule_id, evaluation in self.prior_evaluations.items():
            key = _require_identifier(rule_id, "prior_evaluations key")
            if not isinstance(evaluation, RuleEvaluation):
                raise TypeError("prior_evaluations values must be RuleEvaluation objects.")
            if evaluation.rule_id != key:
                raise ValueError("prior_evaluations key must match evaluation.rule_id.")
            prior[key] = evaluation
        object.__setattr__(self, "stages", MappingProxyType(stages))
        object.__setattr__(self, "prior_evaluations", MappingProxyType(prior))
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    metric_id: str
    accepted_availability: frozenset[EvidenceAvailability] = field(
        default_factory=lambda: frozenset({EvidenceAvailability.AVAILABLE})
    )
    required: bool = True
    role: EvidenceRole = EvidenceRole.PRIMARY
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _require_identifier(self.metric_id, "metric_id"))
        if not isinstance(self.required, bool):
            raise TypeError("required must be a bool.")
        if not isinstance(self.role, EvidenceRole):
            raise TypeError("role must be an EvidenceRole member.")
        accepted = frozenset(self.accepted_availability)
        if not accepted or not all(isinstance(item, EvidenceAvailability) for item in accepted):
            raise TypeError("accepted_availability must contain EvidenceAvailability members.")
        object.__setattr__(self, "accepted_availability", accepted)
        if self.rationale is not None:
            object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))


@dataclass(frozen=True, slots=True)
class RequirementAssessment:
    requirement: EvidenceRequirement
    evidence: EvidenceValue | None
    satisfied: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, EvidenceRequirement):
            raise TypeError("requirement must be an EvidenceRequirement.")
        if self.evidence is not None and not isinstance(self.evidence, EvidenceValue):
            raise TypeError("evidence must be an EvidenceValue or None.")
        expected = self.evidence is not None and self.evidence.availability in self.requirement.accepted_availability
        if self.satisfied is not expected:
            raise ValueError("satisfied is inconsistent with evidence availability.")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class ApplicabilityDecision:
    status: Applicability
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, Applicability):
            raise TypeError("status must be an Applicability member.")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))

    @classmethod
    def applicable(cls, reason: str = "Rule applicability criteria are satisfied.") -> ApplicabilityDecision:
        return cls(Applicability.APPLICABLE, reason)

    @classmethod
    def not_applicable(cls, reason: str) -> ApplicabilityDecision:
        return cls(Applicability.NOT_APPLICABLE, reason)

    @classmethod
    def not_evaluated(cls, reason: str) -> ApplicabilityDecision:
        return cls(Applicability.NOT_EVALUATED, reason)


@dataclass(frozen=True, slots=True)
class Inference:
    inference_id: str
    statement: str
    evidence: tuple[EvidenceReference, ...]
    rationale: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "inference_id", _require_identifier(self.inference_id, "inference_id"))
        object.__setattr__(self, "statement", _require_text(self.statement, "statement"))
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))
        references = tuple(self.evidence)
        if not references or not all(isinstance(item, EvidenceReference) for item in references):
            raise TypeError("evidence must contain at least one EvidenceReference.")
        object.__setattr__(self, "evidence", references)
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise TypeError("confidence must be numeric or None.")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise ValueError("confidence must be between 0 and 1.")
            object.__setattr__(self, "confidence", float(self.confidence))


@dataclass(frozen=True, slots=True)
class DerivedEvidence:
    value: EvidenceValue
    formula: str
    source_metric_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.value, EvidenceValue):
            raise TypeError("value must be an EvidenceValue.")
        object.__setattr__(self, "formula", _require_text(self.formula, "formula"))
        sources = tuple(_require_identifier(item, "source_metric_ids item") for item in self.source_metric_ids)
        if not sources:
            raise ValueError("source_metric_ids must not be empty.")
        if len(sources) != len(set(sources)):
            raise ValueError("source_metric_ids must be unique.")
        object.__setattr__(self, "source_metric_ids", sources)


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    findings: tuple[InterpretationFinding, ...]
    inferences: tuple[Inference, ...] = ()
    derived_evidence: tuple[DerivedEvidence, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        findings = tuple(self.findings)
        inferences = tuple(self.inferences)
        derived = tuple(self.derived_evidence)
        if not findings or not all(isinstance(item, InterpretationFinding) for item in findings):
            raise TypeError("findings must contain at least one InterpretationFinding.")
        if not all(isinstance(item, Inference) for item in inferences):
            raise TypeError("inferences must contain Inference values only.")
        if not all(isinstance(item, DerivedEvidence) for item in derived):
            raise TypeError("derived_evidence must contain DerivedEvidence values only.")
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "inferences", inferences)
        object.__setattr__(self, "derived_evidence", derived)
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes, "notes"))


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule_id: str
    dimension: ValidationDimension
    status: RuleExecutionStatus
    findings: tuple[InterpretationFinding, ...]
    inferences: tuple[Inference, ...]
    derived_evidence: tuple[DerivedEvidence, ...]
    requirements: tuple[RequirementAssessment, ...]
    dependencies: tuple[RuleDependencyAssessment, ...]
    stages: tuple[StageAssessment, ...]
    applicability: ApplicabilityDecision
    started_at: datetime
    completed_at: datetime
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_identifier(self.rule_id, "rule_id"))
        if not isinstance(self.dimension, ValidationDimension):
            raise TypeError("dimension must be a ValidationDimension member.")
        if not isinstance(self.status, RuleExecutionStatus):
            raise TypeError("status must be a RuleExecutionStatus member.")
        for field_name, values, expected_type in (
            ("findings", self.findings, InterpretationFinding),
            ("inferences", self.inferences, Inference),
            ("derived_evidence", self.derived_evidence, DerivedEvidence),
            ("requirements", self.requirements, RequirementAssessment),
            ("dependencies", self.dependencies, RuleDependencyAssessment),
            ("stages", self.stages, StageAssessment),
        ):
            values = tuple(values)
            if not all(isinstance(item, expected_type) for item in values):
                raise TypeError(f"{field_name} must contain {expected_type.__name__} values only.")
            object.__setattr__(self, field_name, values)
        if not isinstance(self.applicability, ApplicabilityDecision):
            raise TypeError("applicability must be an ApplicabilityDecision.")
        started = _normalize_utc(self.started_at, "started_at")
        completed = _normalize_utc(self.completed_at, "completed_at")
        if completed < started:
            raise ValueError("completed_at cannot precede started_at.")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes, "notes"))

        if self.status is not RuleExecutionStatus.COMPLETED and (
            self.findings or self.inferences or self.derived_evidence
        ):
            raise ValueError("Only COMPLETED evaluations may contain scientific outputs.")

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "dimension": self.dimension.value,
            "status": self.status.value,
            "findings": [item.to_dict() for item in self.findings],
            "inferences": [
                {
                    "inference_id": item.inference_id,
                    "statement": item.statement,
                    "rationale": item.rationale,
                    "confidence": item.confidence,
                    "evidence": [
                        {
                            "metric_id": ref.metric_id,
                            "role": ref.role.value,
                            "rationale": ref.rationale,
                        }
                        for ref in item.evidence
                    ],
                }
                for item in self.inferences
            ],
            "derived_evidence": [
                {
                    "metric": item.value.to_dict(),
                    "formula": item.formula,
                    "source_metric_ids": list(item.source_metric_ids),
                }
                for item in self.derived_evidence
            ],
            "requirements": [
                {
                    "metric_id": item.requirement.metric_id,
                    "required": item.requirement.required,
                    "satisfied": item.satisfied,
                    "observed_availability": item.evidence.availability.value if item.evidence else None,
                    "reason": item.reason,
                }
                for item in self.requirements
            ],
            "dependencies": [
                {
                    "rule_id": item.dependency.rule_id,
                    "required": item.dependency.required,
                    "policy": item.dependency.policy.value,
                    "satisfied": item.satisfied,
                    "reason": item.reason,
                }
                for item in self.dependencies
            ],
            "stages": [
                {"stage": item.stage.value, "status": item.status.value, "reason": item.reason}
                for item in self.stages
            ],
            "applicability": {
                "status": self.applicability.status.value,
                "reason": self.applicability.reason,
            },
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "notes": list(self.notes),
        }


class InterpretationRule(ABC):
    rule_id: str
    domain: str
    description: str
    dimension: ValidationDimension
    requirements: tuple[EvidenceRequirement, ...] = ()
    dependencies: tuple[RuleDependency, ...] = ()
    required_stages: tuple[PipelineStage, ...] = ()
    tags: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls.interpret, "__isabstractmethod__", False):
            return
        cls.rule_id = _require_identifier(getattr(cls, "rule_id", ""), "rule_id")
        cls.domain = _require_identifier(getattr(cls, "domain", ""), "domain")
        cls.description = _require_text(getattr(cls, "description", ""), "description")
        if not isinstance(getattr(cls, "dimension", None), ValidationDimension):
            raise TypeError("dimension must be a ValidationDimension member.")
        cls.requirements = tuple(getattr(cls, "requirements", ()))
        cls.dependencies = tuple(getattr(cls, "dependencies", ()))
        cls.required_stages = tuple(getattr(cls, "required_stages", ()))
        cls.tags = _normalize_text_tuple(getattr(cls, "tags", ()), "tags")
        if not all(isinstance(item, EvidenceRequirement) for item in cls.requirements):
            raise TypeError("requirements must contain EvidenceRequirement values only.")
        if not all(isinstance(item, RuleDependency) for item in cls.dependencies):
            raise TypeError("dependencies must contain RuleDependency values only.")
        if not all(isinstance(item, PipelineStage) for item in cls.required_stages):
            raise TypeError("required_stages must contain PipelineStage values only.")
        for values, label, key in (
            (cls.requirements, "metric requirement", lambda item: item.metric_id),
            (cls.dependencies, "rule dependency", lambda item: item.rule_id),
            (cls.required_stages, "pipeline stage", lambda item: item),
        ):
            keys = [key(item) for item in values]
            if len(keys) != len(set(keys)):
                raise ValueError(f"A rule cannot declare the same {label} twice.")
        if any(item.rule_id == cls.rule_id for item in cls.dependencies):
            raise ValueError("A rule cannot depend on itself.")

    def assess_stages(self, context: RuleContext) -> tuple[StageAssessment, ...]:
        assessments: list[StageAssessment] = []
        for stage in self.required_stages:
            status = context.stages.get(stage, StageStatus.NOT_RUN)
            reason = (
                "Required pipeline stage completed."
                if status is StageStatus.COMPLETED
                else f"Required pipeline stage is {status.value}."
            )
            assessments.append(StageAssessment(stage, status, reason))
        return tuple(assessments)

    def assess_dependencies(self, context: RuleContext) -> tuple[RuleDependencyAssessment, ...]:
        assessments: list[RuleDependencyAssessment] = []
        for dependency in self.dependencies:
            evaluation = context.prior_evaluations.get(dependency.rule_id)
            if evaluation is None:
                assessments.append(RuleDependencyAssessment(dependency, None, False, "Dependency evaluation is absent."))
                continue
            satisfied = evaluation.status is RuleExecutionStatus.COMPLETED
            if satisfied and dependency.policy is DependencyPolicy.REQUIRE_FINDINGS:
                satisfied = bool(evaluation.findings)
            assessments.append(
                RuleDependencyAssessment(
                    dependency,
                    evaluation,
                    satisfied,
                    "Dependency policy is satisfied." if satisfied else "Dependency policy is not satisfied.",
                )
            )
        return tuple(assessments)

    def assess_requirements(self, catalog: EvidenceCatalog) -> tuple[RequirementAssessment, ...]:
        assessments: list[RequirementAssessment] = []
        for requirement in self.requirements:
            evidence = catalog.get(requirement.metric_id)
            satisfied = evidence is not None and evidence.availability in requirement.accepted_availability
            if evidence is None:
                reason = f"Evidence metric {requirement.metric_id!r} is absent."
            elif satisfied:
                reason = f"Availability {evidence.availability.value!r} is accepted."
            else:
                reason = f"Availability {evidence.availability.value!r} is not accepted."
            assessments.append(RequirementAssessment(requirement, evidence, satisfied, reason))
        return tuple(assessments)

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, EvidenceValue]
    ) -> ApplicabilityDecision:
        return ApplicabilityDecision.applicable()

    @abstractmethod
    def interpret(
        self, context: RuleContext, evidence: Mapping[str, EvidenceValue]
    ) -> RuleOutcome:
        """Return a fully structured outcome after all preconditions are met."""

    def _empty_evaluation(
        self,
        *,
        status: RuleExecutionStatus,
        applicability: ApplicabilityDecision,
        started_at: datetime,
        requirements: tuple[RequirementAssessment, ...],
        dependencies: tuple[RuleDependencyAssessment, ...],
        stages: tuple[StageAssessment, ...],
        notes: tuple[str, ...],
    ) -> RuleEvaluation:
        return RuleEvaluation(
            rule_id=self.rule_id,
            dimension=self.dimension,
            status=status,
            findings=(),
            inferences=(),
            derived_evidence=(),
            requirements=requirements,
            dependencies=dependencies,
            stages=stages,
            applicability=applicability,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            notes=notes,
        )

    def run(self, context: RuleContext) -> RuleEvaluation:
        if not isinstance(context, RuleContext):
            raise TypeError("context must be a RuleContext.")
        started_at = datetime.now(UTC)
        stages = self.assess_stages(context)
        incomplete_stages = tuple(item for item in stages if item.status is not StageStatus.COMPLETED)
        if incomplete_stages:
            return self._empty_evaluation(
                status=RuleExecutionStatus.NOT_EVALUATED,
                applicability=ApplicabilityDecision.not_evaluated("Required pipeline stages are not complete."),
                started_at=started_at,
                requirements=(),
                dependencies=(),
                stages=stages,
                notes=tuple(item.reason for item in incomplete_stages),
            )

        dependencies = self.assess_dependencies(context)
        blocked = tuple(item for item in dependencies if item.dependency.required and not item.satisfied)
        if blocked:
            return self._empty_evaluation(
                status=RuleExecutionStatus.BLOCKED_DEPENDENCY,
                applicability=ApplicabilityDecision.not_evaluated("Required rule dependencies are not satisfied."),
                started_at=started_at,
                requirements=(),
                dependencies=dependencies,
                stages=stages,
                notes=tuple(item.reason for item in blocked),
            )

        requirements = self.assess_requirements(context.evidence)
        missing = tuple(item for item in requirements if item.requirement.required and not item.satisfied)
        if missing:
            return self._empty_evaluation(
                status=RuleExecutionStatus.INSUFFICIENT_EVIDENCE,
                applicability=ApplicabilityDecision.not_evaluated("Mandatory evidence requirements are not satisfied."),
                started_at=started_at,
                requirements=requirements,
                dependencies=dependencies,
                stages=stages,
                notes=tuple(item.reason for item in missing),
            )

        resolved = MappingProxyType({
            item.requirement.metric_id: item.evidence
            for item in requirements
            if item.evidence is not None
        })
        try:
            applicability = self.applicability(context, resolved)
        except Exception as exc:  # noqa: BLE001
            raise RuleExecutionError(
                f"Rule {self.rule_id!r} failed during applicability evaluation: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(applicability, ApplicabilityDecision):
            raise RuleInvariantError("applicability() must return ApplicabilityDecision.")
        if applicability.status is not Applicability.APPLICABLE:
            return self._empty_evaluation(
                status=(RuleExecutionStatus.NOT_APPLICABLE if applicability.status is Applicability.NOT_APPLICABLE else RuleExecutionStatus.NOT_EVALUATED),
                applicability=applicability,
                started_at=started_at,
                requirements=requirements,
                dependencies=dependencies,
                stages=stages,
                notes=(),
            )

        try:
            outcome = self.interpret(context, resolved)
        except RuleExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RuleExecutionError(
                f"Rule {self.rule_id!r} failed during interpretation: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(outcome, RuleOutcome):
            raise RuleInvariantError("interpret() must return RuleOutcome.")

        known_metrics = {value.metric_id for value in context.evidence}
        derived_ids = [item.value.metric_id for item in outcome.derived_evidence]
        if len(derived_ids) != len(set(derived_ids)):
            raise RuleInvariantError("Derived evidence metric identifiers must be unique.")
        if known_metrics.intersection(derived_ids):
            raise RuleInvariantError("Derived evidence must not overwrite existing evidence metrics.")
        for derived in outcome.derived_evidence:
            unknown_sources = set(derived.source_metric_ids) - known_metrics
            if unknown_sources:
                raise RuleInvariantError(f"Derived evidence references unknown source metrics: {sorted(unknown_sources)}.")
        all_metrics = known_metrics | set(derived_ids)

        finding_ids: set[str] = set()
        for finding in outcome.findings:
            if finding.rule_id != self.rule_id or finding.domain != self.domain:
                raise RuleInvariantError("Every finding must reference the executing rule and domain.")
            if finding.finding_id in finding_ids:
                raise RuleInvariantError("Finding identifiers must be unique within one rule outcome.")
            finding_ids.add(finding.finding_id)
            unknown = {ref.metric_id for ref in finding.evidence} - all_metrics
            if unknown:
                raise RuleInvariantError(f"Finding references unknown evidence metrics: {sorted(unknown)}.")

        inference_ids: set[str] = set()
        for inference in outcome.inferences:
            if inference.inference_id in inference_ids:
                raise RuleInvariantError("Inference identifiers must be unique within one rule outcome.")
            inference_ids.add(inference.inference_id)
            unknown = {ref.metric_id for ref in inference.evidence} - all_metrics
            if unknown:
                raise RuleInvariantError(f"Inference references unknown evidence metrics: {sorted(unknown)}.")

        return RuleEvaluation(
            rule_id=self.rule_id,
            dimension=self.dimension,
            status=RuleExecutionStatus.COMPLETED,
            findings=outcome.findings,
            inferences=outcome.inferences,
            derived_evidence=outcome.derived_evidence,
            requirements=requirements,
            dependencies=dependencies,
            stages=stages,
            applicability=applicability,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            notes=outcome.notes,
        )


class StructuralRule(InterpretationRule, ABC):
    dimension = ValidationDimension.STRUCTURAL


class StatisticalRule(InterpretationRule, ABC):
    dimension = ValidationDimension.STATISTICAL


class ClinicalRule(InterpretationRule, ABC):
    dimension = ValidationDimension.CLINICAL


class EpidemiologicalRule(InterpretationRule, ABC):
    dimension = ValidationDimension.EPIDEMIOLOGICAL