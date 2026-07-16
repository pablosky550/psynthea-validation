"""Deterministic and auditable verification of causal candidates.

This module executes explicit, reproducible checks against prioritised causal
candidates.  It is the only Phase 3 stage allowed to turn a testable hypothesis
into verification evidence, but it still does not select a final root cause.
Final causal classification belongs to the attribution/engine stages.

Scientific boundary
-------------------
``PASSED`` and ``FAILED`` are scientific outcomes produced by a verifier that
completed its procedure. ``ERROR`` is a technical execution failure and must
never be interpreted as evidence for or against a candidate. ``INCONCLUSIVE``
means the check completed but its observations could not discriminate the
hypothesis. ``SKIPPED`` and ``NOT_RUN`` are explicit non-results.

Design guarantees
-----------------
* Verifiers are injected and addressed by stable identifiers.
* Verification plans are explicit; this module never invents shell commands.
* Input candidates, evidence and artefacts are validated before execution.
* Candidate order and verifier registration order cannot change the output.
* Every execution records exact inputs, expected/observed results, timing,
  generated evidence, output artefacts and diagnostic metadata.
* Technical failures are isolated at the verifier boundary and represented as
  ``ERROR`` results, unless strict execution requests exception propagation.
* Candidate status transitions are conservative and derived only from completed
  verification outcomes.
* No subprocess, filesystem or network access exists in this module.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from json import dumps
from math import isfinite
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from validation.knowledge.models import VerificationCheck
from validation.orchestration.models import ArtifactReference
from validation.root_cause.exceptions import (
    RootCauseInputError,
    RootCauseIntegrityError,
    VerificationExecutionError,
)
from validation.root_cause.models import (
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
    VerificationOutcome,
    VerificationResult,
)

__all__ = [
    "CandidateVerificationSummary",
    "ExecutionFailurePolicy",
    "ExplicitVerificationPlanSource",
    "KnowledgeCheckPlanSource",
    "Verifier",
    "VerifierContext",
    "VerifierObservation",
    "VerificationDiagnostic",
    "VerificationEngine",
    "VerificationExecution",
    "VerificationPlanSource",
    "VerificationSeverity",
    "VerificationSpecification",
    "VerificationStageContext",
    "execute_verifications",
]


_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN: Final = compile_pattern(r"^[0-9a-f]{64}$")


class ExecutionFailurePolicy(str, Enum):
    """How unexpected verifier failures cross the execution boundary."""

    RECORD_ERROR = "record_error"
    RAISE = "raise"


class VerificationSeverity(str, Enum):
    """Severity of one non-fatal verification diagnostic."""

    INFO = "info"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class VerificationDiagnostic:
    """One deterministic, machine-readable execution diagnostic."""

    code: str
    message: str
    severity: VerificationSeverity = VerificationSeverity.WARNING
    candidate_id: str | None = None
    specification_id: str | None = None
    verifier_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if not isinstance(self.severity, VerificationSeverity):
            raise TypeError("severity must be a VerificationSeverity member.")
        for field_name in ("candidate_id", "specification_id", "verifier_id"):
            object.__setattr__(
                self,
                field_name,
                _optional_identifier(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class VerificationSpecification:
    """Immutable execution plan for one deterministic candidate check.

    ``command`` is descriptive provenance only.  It is passed to the injected
    verifier and recorded in the result; this module never executes it.
    """

    id: str
    candidate_id: str
    verifier_id: str
    procedure: str
    expected_result: str
    input_artifact_ids: tuple[str, ...] = ()
    prerequisite_evidence_ids: tuple[str, ...] = ()
    command: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self, "candidate_id", _require_identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "verifier_id", _require_identifier(self.verifier_id, "verifier_id")
        )
        object.__setattr__(self, "procedure", _require_text(self.procedure, "procedure"))
        object.__setattr__(
            self,
            "expected_result",
            _require_text(self.expected_result, "expected_result"),
        )
        for field_name in (
            "input_artifact_ids",
            "prerequisite_evidence_ids",
            "depends_on",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_identifier_tuple(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "command", _normalize_text_tuple(self.command, "command"))
        if not isinstance(self.required, bool):
            raise TypeError("required must be a bool.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))
        if self.id in self.depends_on:
            raise ValueError("A verification specification cannot depend on itself.")


@dataclass(frozen=True, slots=True)
class VerifierObservation:
    """Raw, immutable observation returned by an injected verifier.

    Verifiers may return only completed scientific outcomes.  Technical errors
    must be raised as exceptions and are translated by :class:`VerificationEngine`.
    """

    outcome: VerificationOutcome
    observed_result: str
    evidence: tuple[EvidenceReference, ...] = ()
    output_artifacts: tuple[ArtifactReference, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, VerificationOutcome):
            raise TypeError("outcome must be a VerificationOutcome member.")
        if self.outcome not in {
            VerificationOutcome.PASSED,
            VerificationOutcome.FAILED,
            VerificationOutcome.INCONCLUSIVE,
        }:
            raise ValueError(
                "VerifierObservation accepts only PASSED, FAILED or INCONCLUSIVE; "
                "technical errors must be raised and non-execution is controlled by the engine."
            )
        object.__setattr__(
            self, "observed_result", _require_text(self.observed_result, "observed_result")
        )
        evidence = _normalize_models(self.evidence, EvidenceReference, "evidence")
        artifacts = _normalize_models(
            self.output_artifacts, ArtifactReference, "output_artifacts"
        )
        _require_unique_ids(evidence, "evidence")
        _require_unique_ids(artifacts, "output_artifacts")
        object.__setattr__(self, "evidence", tuple(sorted(evidence, key=lambda item: item.id)))
        object.__setattr__(
            self,
            "output_artifacts",
            tuple(sorted(artifacts, key=lambda item: item.id)),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))
        if self.outcome in {VerificationOutcome.PASSED, VerificationOutcome.FAILED} and not self.evidence:
            raise ValueError(
                f"A {self.outcome.value} verifier observation requires generated evidence."
            )


@dataclass(frozen=True, slots=True)
class VerifierContext:
    """Read-only inputs supplied to one verifier execution."""

    request: RootCauseRequest
    candidate: CausalCandidate
    assessment: CandidateAssessment
    specification: VerificationSpecification
    evidence: tuple[EvidenceReference, ...]
    artifacts: tuple[ArtifactReference, ...]
    prior_results: tuple[VerificationResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        if not isinstance(self.candidate, CausalCandidate):
            raise TypeError("candidate must be a CausalCandidate.")
        if not isinstance(self.assessment, CandidateAssessment):
            raise TypeError("assessment must be a CandidateAssessment.")
        if not isinstance(self.specification, VerificationSpecification):
            raise TypeError("specification must be a VerificationSpecification.")
        if self.assessment.candidate_id != self.candidate.id:
            raise ValueError("assessment does not belong to candidate.")
        if self.specification.candidate_id != self.candidate.id:
            raise ValueError("specification does not belong to candidate.")

        evidence = _normalize_models(self.evidence, EvidenceReference, "evidence")
        artifacts = _normalize_models(self.artifacts, ArtifactReference, "artifacts")
        prior = _normalize_models(self.prior_results, VerificationResult, "prior_results")
        _require_unique_ids(evidence, "evidence")
        _require_unique_ids(artifacts, "artifacts")
        _require_unique_ids(prior, "prior_results")
        object.__setattr__(self, "evidence", tuple(sorted(evidence, key=lambda item: item.id)))
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.id)))
        object.__setattr__(self, "prior_results", tuple(sorted(prior, key=lambda item: item.id)))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@runtime_checkable
class Verifier(Protocol):
    """Injected deterministic backend for one stable verifier identifier."""

    @property
    def id(self) -> str:
        """Stable verifier identifier."""

    def verify(self, context: VerifierContext) -> VerifierObservation:
        """Execute one check and return a completed scientific observation."""


@runtime_checkable
class VerificationPlanSource(Protocol):
    """Injected source of explicit verification specifications."""

    @property
    def id(self) -> str:
        """Stable plan-source identifier."""

    def specifications(
        self,
        *,
        request: RootCauseRequest,
        candidates: tuple[CausalCandidate, ...],
        assessments: tuple[CandidateAssessment, ...],
    ) -> Sequence[VerificationSpecification]:
        """Return deterministic plans for the supplied candidate set."""


@dataclass(frozen=True, slots=True)
class ExplicitVerificationPlanSource:
    """Plan source backed by already constructed specifications."""

    plans: tuple[VerificationSpecification, ...]
    source_id: str = "verification.plan.explicit"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _require_identifier(self.source_id, "source_id"))
        plans = _normalize_models(self.plans, VerificationSpecification, "plans")
        _require_unique_ids(plans, "plans")
        object.__setattr__(self, "plans", tuple(sorted(plans, key=lambda item: item.id)))
        _validate_dependency_graph(self.plans)

    @property
    def id(self) -> str:
        return self.source_id

    def specifications(
        self,
        *,
        request: RootCauseRequest,
        candidates: tuple[CausalCandidate, ...],
        assessments: tuple[CandidateAssessment, ...],
    ) -> Sequence[VerificationSpecification]:
        del request, assessments
        candidate_ids = {candidate.id for candidate in candidates}
        return tuple(plan for plan in self.plans if plan.candidate_id in candidate_ids)


@dataclass(frozen=True, slots=True)
class KnowledgeCheckPlanSource:
    """Adapter from Phase 2A ``VerificationCheck`` objects to Phase 3 plans.

    Bindings are deliberately explicit.  The adapter never assumes that a
    knowledge hypothesis identifier equals a generated candidate identifier.
    ``verifier_by_check_id`` must map each selected knowledge check to a concrete
    injected verifier.
    """

    checks: tuple[VerificationCheck, ...]
    candidate_check_ids: Mapping[str, Sequence[str]]
    verifier_by_check_id: Mapping[str, str]
    input_artifact_ids_by_check_id: Mapping[str, Sequence[str]] = field(default_factory=dict)
    prerequisite_evidence_ids_by_check_id: Mapping[str, Sequence[str]] = field(
        default_factory=dict
    )
    source_id: str = "verification.plan.knowledge"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _require_identifier(self.source_id, "source_id"))
        checks = _normalize_models(self.checks, VerificationCheck, "checks")
        _require_unique_ids(checks, "checks")
        object.__setattr__(self, "checks", tuple(sorted(checks, key=lambda item: item.id)))
        check_ids = {check.id for check in checks}

        bindings = _freeze_sequence_mapping(
            self.candidate_check_ids, "candidate_check_ids", identifiers=True
        )
        verifier_map = _freeze_text_mapping(
            self.verifier_by_check_id, "verifier_by_check_id", identifiers=True
        )
        artifact_map = _freeze_sequence_mapping(
            self.input_artifact_ids_by_check_id,
            "input_artifact_ids_by_check_id",
            identifiers=True,
        )
        evidence_map = _freeze_sequence_mapping(
            self.prerequisite_evidence_ids_by_check_id,
            "prerequisite_evidence_ids_by_check_id",
            identifiers=True,
        )

        referenced = {check_id for values in bindings.values() for check_id in values}
        unknown = sorted(referenced - check_ids)
        if unknown:
            raise ValueError(
                "candidate_check_ids references unknown checks: " + ", ".join(unknown) + "."
            )
        missing_verifiers = sorted(referenced - set(verifier_map))
        if missing_verifiers:
            raise ValueError(
                "Selected knowledge checks require verifier mappings: "
                + ", ".join(missing_verifiers)
                + "."
            )
        for mapping_name, mapping_value in (
            ("verifier_by_check_id", verifier_map),
            ("input_artifact_ids_by_check_id", artifact_map),
            ("prerequisite_evidence_ids_by_check_id", evidence_map),
        ):
            extras = sorted(set(mapping_value) - check_ids)
            if extras:
                raise ValueError(
                    f"{mapping_name} references unknown checks: {', '.join(extras)}."
                )

        object.__setattr__(self, "candidate_check_ids", bindings)
        object.__setattr__(self, "verifier_by_check_id", verifier_map)
        object.__setattr__(self, "input_artifact_ids_by_check_id", artifact_map)
        object.__setattr__(self, "prerequisite_evidence_ids_by_check_id", evidence_map)

    @property
    def id(self) -> str:
        return self.source_id

    def specifications(
        self,
        *,
        request: RootCauseRequest,
        candidates: tuple[CausalCandidate, ...],
        assessments: tuple[CandidateAssessment, ...],
    ) -> Sequence[VerificationSpecification]:
        del request, assessments
        check_by_id = {check.id: check for check in self.checks}
        plans: list[VerificationSpecification] = []
        for candidate in sorted(candidates, key=lambda item: item.id):
            for check_id in self.candidate_check_ids.get(candidate.id, ()):
                check = check_by_id[check_id]
                plans.append(
                    VerificationSpecification(
                        id=_stable_identifier(
                            "verification.spec",
                            {"candidate_id": candidate.id, "check_id": check.id},
                        ),
                        candidate_id=candidate.id,
                        verifier_id=self.verifier_by_check_id[check.id],
                        procedure=check.procedure,
                        expected_result=check.expected_result,
                        input_artifact_ids=self.input_artifact_ids_by_check_id.get(
                            check.id, ()
                        ),
                        prerequisite_evidence_ids=(
                            *check.evidence_ids,
                            *self.prerequisite_evidence_ids_by_check_id.get(check.id, ()),
                        ),
                        metadata={
                            "knowledge_verification_check_id": check.id,
                            "knowledge_hypothesis_id": check.hypothesis_id,
                            "description": check.description,
                            "source_plan_id": self.id,
                        },
                    )
                )
        return tuple(plans)


@dataclass(frozen=True, slots=True)
class VerificationStageContext:
    """Complete immutable input to the verification stage."""

    request: RootCauseRequest
    candidates: tuple[CausalCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    evidence: tuple[EvidenceReference, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    strict: bool | None = None
    failure_policy: ExecutionFailurePolicy = ExecutionFailurePolicy.RECORD_ERROR
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        candidates = _normalize_models(self.candidates, CausalCandidate, "candidates")
        assessments = _normalize_models(
            self.assessments, CandidateAssessment, "assessments"
        )
        evidence = _normalize_models(self.evidence, EvidenceReference, "evidence")
        artifacts = _normalize_models(self.artifacts, ArtifactReference, "artifacts")
        _require_unique_ids(candidates, "candidates")
        _require_unique_candidate_assessments(assessments)
        _require_unique_ids(evidence, "evidence")
        _require_unique_ids(artifacts, "artifacts")

        candidate_by_id = {candidate.id: candidate for candidate in candidates}
        assessment_ids = {assessment.candidate_id for assessment in assessments}
        if assessment_ids != set(candidate_by_id):
            raise ValueError(
                "assessments must cover candidates exactly; "
                f"missing={sorted(set(candidate_by_id) - assessment_ids)}, "
                f"unknown={sorted(assessment_ids - set(candidate_by_id))}."
            )
        invalid_statuses = {
            candidate.id: candidate.status.value
            for candidate in candidates
            if candidate.status not in {
                CandidateStatus.PRIORITIZED,
                CandidateStatus.UNDER_VERIFICATION,
            }
        }
        if invalid_statuses:
            raise ValueError(
                "Verification accepts only PRIORITIZED or UNDER_VERIFICATION candidates: "
                + repr(dict(sorted(invalid_statuses.items())))
                + "."
            )

        evidence_ids = {item.id for item in evidence}
        artifact_ids = {item.id for item in artifacts}
        requested_artifacts = set(self.request.artifact_ids)
        missing_requested = sorted(requested_artifacts - artifact_ids)
        if missing_requested:
            raise ValueError(
                "Verification context is missing request artefacts: "
                + ", ".join(missing_requested)
                + "."
            )
        for candidate in candidates:
            missing = sorted(set(candidate.prerequisite_evidence_ids) - evidence_ids)
            if missing:
                raise ValueError(
                    f"Candidate {candidate.id!r} references unavailable prerequisite evidence: "
                    + ", ".join(missing)
                    + "."
                )

        if self.strict is not None and not isinstance(self.strict, bool):
            raise TypeError("strict must be bool or None.")
        if not isinstance(self.failure_policy, ExecutionFailurePolicy):
            raise TypeError("failure_policy must be an ExecutionFailurePolicy member.")

        object.__setattr__(
            self, "candidates", tuple(sorted(candidates, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "assessments",
            tuple(sorted(assessments, key=lambda item: (item.rank, item.candidate_id))),
        )
        object.__setattr__(self, "evidence", tuple(sorted(evidence, key=lambda item: item.id)))
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.id)))
        object.__setattr__(
            self,
            "strict",
            self.request.strict_integrity if self.strict is None else self.strict,
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def candidate_catalog(self) -> Mapping[str, CausalCandidate]:
        return MappingProxyType({item.id: item for item in self.candidates})

    @property
    def assessment_catalog(self) -> Mapping[str, CandidateAssessment]:
        return MappingProxyType({item.candidate_id: item for item in self.assessments})

    @property
    def evidence_catalog(self) -> Mapping[str, EvidenceReference]:
        return MappingProxyType({item.id: item for item in self.evidence})

    @property
    def artifact_catalog(self) -> Mapping[str, ArtifactReference]:
        return MappingProxyType({item.id: item for item in self.artifacts})


@dataclass(frozen=True, slots=True)
class CandidateVerificationSummary:
    """Aggregated verification state for one candidate."""

    candidate_id: str
    status: CandidateStatus
    result_ids: tuple[str, ...]
    passed: int = 0
    failed: int = 0
    inconclusive: int = 0
    error: int = 0
    skipped: int = 0
    not_run: int = 0
    required_result_ids: tuple[str, ...] = ()
    rationale: str = "Verification summary unavailable."

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _require_identifier(self.candidate_id, "candidate_id")
        )
        if not isinstance(self.status, CandidateStatus):
            raise TypeError("status must be a CandidateStatus member.")
        object.__setattr__(
            self, "result_ids", _normalize_identifier_tuple(self.result_ids, "result_ids")
        )
        object.__setattr__(
            self,
            "required_result_ids",
            _normalize_identifier_tuple(self.required_result_ids, "required_result_ids"),
        )
        if not set(self.required_result_ids) <= set(self.result_ids):
            raise ValueError("required_result_ids must be a subset of result_ids.")
        for field_name in (
            "passed",
            "failed",
            "inconclusive",
            "error",
            "skipped",
            "not_run",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_int(getattr(self, field_name), field_name),
            )
        if sum(
            (
                self.passed,
                self.failed,
                self.inconclusive,
                self.error,
                self.skipped,
                self.not_run,
            )
        ) != len(self.result_ids):
            raise ValueError("Outcome counts must equal len(result_ids).")
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))


@dataclass(frozen=True, slots=True)
class VerificationExecution:
    """Complete deterministic output of the verification stage."""

    request_id: str
    candidates: tuple[CausalCandidate, ...]
    specifications: tuple[VerificationSpecification, ...]
    results: tuple[VerificationResult, ...]
    evidence: tuple[EvidenceReference, ...]
    output_artifacts: tuple[ArtifactReference, ...]
    summaries: tuple[CandidateVerificationSummary, ...]
    diagnostics: tuple[VerificationDiagnostic, ...] = ()
    plan_source_ids: tuple[str, ...] = ()
    verifier_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _require_identifier(self.request_id, "request_id")
        )
        candidates = _normalize_models(self.candidates, CausalCandidate, "candidates")
        specs = _normalize_models(
            self.specifications, VerificationSpecification, "specifications"
        )
        results = _normalize_models(self.results, VerificationResult, "results")
        evidence = _normalize_models(self.evidence, EvidenceReference, "evidence")
        artifacts = _normalize_models(
            self.output_artifacts, ArtifactReference, "output_artifacts"
        )
        summaries = _normalize_models(
            self.summaries, CandidateVerificationSummary, "summaries"
        )
        diagnostics = _normalize_models(
            self.diagnostics, VerificationDiagnostic, "diagnostics"
        )
        for name, values in (
            ("candidates", candidates),
            ("specifications", specs),
            ("results", results),
            ("evidence", evidence),
            ("output_artifacts", artifacts),
        ):
            _require_unique_ids(values, name)
        _require_unique_summary_candidates(summaries)

        candidate_ids = {candidate.id for candidate in candidates}
        spec_by_id = {spec.id: spec for spec in specs}
        if {summary.candidate_id for summary in summaries} != candidate_ids:
            raise ValueError("summaries must cover candidates exactly.")
        unknown_specs = sorted({spec.candidate_id for spec in specs} - candidate_ids)
        if unknown_specs:
            raise ValueError(
                "specifications reference unknown candidates: " + ", ".join(unknown_specs) + "."
            )
        expected_result_ids = {
            _result_id(self.request_id, spec.id, spec.candidate_id, spec.verifier_id) for spec in specs
        }
        actual_result_ids = {result.id for result in results}
        if actual_result_ids != expected_result_ids:
            raise ValueError(
                "results must cover specifications exactly; "
                f"missing={sorted(expected_result_ids - actual_result_ids)}, "
                f"unknown={sorted(actual_result_ids - expected_result_ids)}."
            )
        for result in results:
            matching = [
                spec
                for spec in specs
                if _result_id(self.request_id, spec.id, spec.candidate_id, spec.verifier_id) == result.id
            ]
            if len(matching) != 1:
                raise ValueError(f"Result {result.id!r} has no unique specification.")
            spec = matching[0]
            if result.candidate_id != spec.candidate_id or result.verifier_id != spec.verifier_id:
                raise ValueError(f"Result {result.id!r} does not match its specification.")

        evidence_ids = {item.id for item in evidence}
        artifact_ids = {item.id for item in artifacts}
        for result in results:
            missing_evidence = sorted(set(result.evidence_ids) - evidence_ids)
            missing_artifacts = sorted(
                {item.id for item in result.output_artifacts} - artifact_ids
            )
            if missing_evidence or missing_artifacts:
                raise ValueError(
                    f"Result {result.id!r} references unregistered outputs; "
                    f"evidence={missing_evidence}, artifacts={missing_artifacts}."
                )

        summary_by_candidate = {summary.candidate_id: summary for summary in summaries}
        for candidate in candidates:
            if candidate.status != summary_by_candidate[candidate.id].status:
                raise ValueError(
                    f"Candidate {candidate.id!r} status disagrees with its summary."
                )

        object.__setattr__(
            self, "candidates", tuple(sorted(candidates, key=lambda item: item.id))
        )
        object.__setattr__(self, "specifications", tuple(sorted(specs, key=lambda item: item.id)))
        object.__setattr__(self, "results", tuple(sorted(results, key=lambda item: item.id)))
        object.__setattr__(self, "evidence", tuple(sorted(evidence, key=lambda item: item.id)))
        object.__setattr__(
            self, "output_artifacts", tuple(sorted(artifacts, key=lambda item: item.id))
        )
        object.__setattr__(
            self, "summaries", tuple(sorted(summaries, key=lambda item: item.candidate_id))
        )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.code,
                        item.candidate_id or "",
                        item.specification_id or "",
                        item.verifier_id or "",
                        item.message,
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "plan_source_ids",
            _normalize_identifier_tuple(self.plan_source_ids, "plan_source_ids"),
        )
        object.__setattr__(
            self, "verifier_ids", _normalize_identifier_tuple(self.verifier_ids, "verifier_ids")
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


class VerificationEngine:
    """Coordinate deterministic planning and injected verifier execution."""

    def __init__(
        self,
        *,
        plan_sources: Sequence[VerificationPlanSource],
        verifiers: Sequence[Verifier],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._plan_sources = _normalize_protocols(
            plan_sources, VerificationPlanSource, "plan_sources"
        )
        self._verifiers = _normalize_protocols(verifiers, Verifier, "verifiers")
        _require_unique_protocol_ids(self._plan_sources, "plan_sources")
        _require_unique_protocol_ids(self._verifiers, "verifiers")
        self._plan_sources = tuple(sorted(self._plan_sources, key=lambda item: item.id))
        self._verifier_by_id = MappingProxyType(
            {verifier.id: verifier for verifier in sorted(self._verifiers, key=lambda item: item.id)}
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        if not callable(self._clock):
            raise TypeError("clock must be callable.")

    def execute(self, context: VerificationStageContext) -> VerificationExecution:
        """Plan and execute all candidate checks in dependency order."""

        if not isinstance(context, VerificationStageContext):
            raise TypeError("context must be a VerificationStageContext.")

        diagnostics: list[VerificationDiagnostic] = []
        specifications = self._collect_specifications(context, diagnostics)
        if not context.request.execute_verifications:
            results = tuple(
                self._not_run_result(context.request.id, spec) for spec in specifications
            )
            candidates, summaries = _summarize_candidates(
                context.request.id, context.candidates, specifications, results
            )
            return VerificationExecution(
                request_id=context.request.id,
                candidates=candidates,
                specifications=specifications,
                results=results,
                evidence=(),
                output_artifacts=(),
                summaries=summaries,
                diagnostics=tuple(diagnostics),
                plan_source_ids=tuple(source.id for source in self._plan_sources),
                verifier_ids=tuple(self._verifier_by_id),
                metadata={
                    "executed": False,
                    "reason": "request.execute_verifications is false",
                    **dict(context.metadata),
                },
            )

        result_by_spec: dict[str, VerificationResult] = {}
        generated_evidence: dict[str, EvidenceReference] = {}
        generated_artifacts: dict[str, ArtifactReference] = {}
        evidence_catalog = dict(context.evidence_catalog)
        artifact_catalog = dict(context.artifact_catalog)

        for layer in _execution_layers(specifications):
            for spec in layer:
                result, produced_evidence = self._execute_specification(
                    context=context,
                    specification=spec,
                    result_by_spec=result_by_spec,
                    evidence_catalog={**evidence_catalog, **generated_evidence},
                    artifact_catalog={**artifact_catalog, **generated_artifacts},
                    diagnostics=diagnostics,
                )
                result_by_spec[spec.id] = result
                for item in result.output_artifacts:
                    _register_unique_output(
                        generated_artifacts,
                        item,
                        "output artifact",
                    )
                for item in produced_evidence:
                    _register_unique_output(generated_evidence, item, "evidence")
                if set(result.evidence_ids) != {item.id for item in produced_evidence}:
                    raise RootCauseIntegrityError(
                        "Verifier result evidence does not match registered evidence objects.",
                        context={
                            "specification_id": spec.id,
                            "result_evidence_ids": result.evidence_ids,
                            "produced_evidence_ids": tuple(
                                item.id for item in produced_evidence
                            ),
                        },
                    )

        results = tuple(result_by_spec[spec.id] for spec in specifications)
        candidates, summaries = _summarize_candidates(
            context.request.id, context.candidates, specifications, results
        )
        return VerificationExecution(
            request_id=context.request.id,
            candidates=candidates,
            specifications=specifications,
            results=results,
            evidence=tuple(generated_evidence.values()),
            output_artifacts=tuple(generated_artifacts.values()),
            summaries=summaries,
            diagnostics=tuple(diagnostics),
            plan_source_ids=tuple(source.id for source in self._plan_sources),
            verifier_ids=tuple(self._verifier_by_id),
            metadata={"executed": True, **dict(context.metadata)},
        )

    def _collect_specifications(
        self,
        context: VerificationStageContext,
        diagnostics: list[VerificationDiagnostic],
    ) -> tuple[VerificationSpecification, ...]:
        plans: dict[str, VerificationSpecification] = {}
        for source in self._plan_sources:
            try:
                produced = source.specifications(
                    request=context.request,
                    candidates=context.candidates,
                    assessments=context.assessments,
                )
                normalized = _normalize_models(
                    produced, VerificationSpecification, f"{source.id}.specifications"
                )
            except (RootCauseInputError, RootCauseIntegrityError):
                raise
            except Exception as exc:
                raise RootCauseIntegrityError(
                    "Verification plan source violated its contract.",
                    context={
                        "plan_source_id": source.id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                ) from exc
            for plan in normalized:
                existing = plans.get(plan.id)
                if existing is not None and existing != plan:
                    raise RootCauseIntegrityError(
                        "Different verification specifications share the same id.",
                        context={"specification_id": plan.id, "plan_source_id": source.id},
                    )
                plans[plan.id] = plan

        ordered = tuple(sorted(plans.values(), key=lambda item: item.id))
        _validate_plans_against_context(ordered, context, self._verifier_by_id)
        _validate_dependency_graph(ordered)
        planned_candidates = {plan.candidate_id for plan in ordered}
        for candidate in context.candidates:
            if candidate.id not in planned_candidates:
                diagnostics.append(
                    VerificationDiagnostic(
                        code="verification.candidate.unplanned",
                        message="No explicit verification plan was available for candidate.",
                        severity=VerificationSeverity.WARNING,
                        candidate_id=candidate.id,
                    )
                )
        return ordered

    def _execute_specification(
        self,
        *,
        context: VerificationStageContext,
        specification: VerificationSpecification,
        result_by_spec: Mapping[str, VerificationResult],
        evidence_catalog: Mapping[str, EvidenceReference],
        artifact_catalog: Mapping[str, ArtifactReference],
        diagnostics: list[VerificationDiagnostic],
    ) -> tuple[VerificationResult, tuple[EvidenceReference, ...]]:
        dependency_results = tuple(
            result_by_spec[dependency_id] for dependency_id in specification.depends_on
        )
        blocking = tuple(
            result
            for result in dependency_results
            if result.outcome
            not in {VerificationOutcome.PASSED, VerificationOutcome.FAILED}
        )
        if blocking:
            diagnostics.append(
                VerificationDiagnostic(
                    code="verification.dependency.blocked",
                    message="Verification was skipped because a dependency did not complete decisively.",
                    severity=VerificationSeverity.INFO,
                    candidate_id=specification.candidate_id,
                    specification_id=specification.id,
                    verifier_id=specification.verifier_id,
                    metadata={"blocking_result_ids": tuple(item.id for item in blocking)},
                )
            )
            return (
                self._skipped_result(
                    context.request.id,
                    specification,
                    "Skipped because prerequisite verification did not complete decisively.",
                ),
                (),
            )

        verifier = self._verifier_by_id[specification.verifier_id]
        candidate = context.candidate_catalog[specification.candidate_id]
        assessment = context.assessment_catalog[specification.candidate_id]
        selected_evidence = tuple(
            evidence_catalog[evidence_id]
            for evidence_id in specification.prerequisite_evidence_ids
        )
        selected_artifacts = tuple(
            artifact_catalog[artifact_id]
            for artifact_id in specification.input_artifact_ids
        )
        verifier_context = VerifierContext(
            request=context.request,
            candidate=replace(candidate, status=CandidateStatus.UNDER_VERIFICATION),
            assessment=assessment,
            specification=specification,
            evidence=selected_evidence,
            artifacts=selected_artifacts,
            prior_results=dependency_results,
            metadata=context.metadata,
        )

        started_at = _normalize_clock_value(self._clock(), "clock(started_at)")
        try:
            observation = verifier.verify(verifier_context)
        except Exception as exc:
            finished_at = _normalize_clock_value(self._clock(), "clock(finished_at)")
            if context.failure_policy is ExecutionFailurePolicy.RAISE:
                raise VerificationExecutionError(
                    "Injected verifier failed during deterministic execution.",
                    context={
                        "candidate_id": specification.candidate_id,
                        "specification_id": specification.id,
                        "verifier_id": specification.verifier_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                ) from exc
            diagnostics.append(
                VerificationDiagnostic(
                    code="verification.verifier.error",
                    message="Verifier raised an unexpected technical error.",
                    candidate_id=specification.candidate_id,
                    specification_id=specification.id,
                    verifier_id=specification.verifier_id,
                    metadata={"error_type": type(exc).__name__, "error": str(exc)},
                )
            )
            return (
                VerificationResult(
                    id=_result_id(
                    context.request.id,
                    specification.id,
                    specification.candidate_id,
                    specification.verifier_id,
                ),
                candidate_id=specification.candidate_id,
                verifier_id=specification.verifier_id,
                outcome=VerificationOutcome.ERROR,
                procedure=specification.procedure,
                expected_result=specification.expected_result,
                input_artifact_ids=specification.input_artifact_ids,
                command=specification.command,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=_duration(started_at, finished_at),
                error_message=f"{type(exc).__name__}: {exc}",
                    metadata={
                        "specification_id": specification.id,
                        "required": specification.required,
                        **dict(specification.metadata),
                    },
                ),
                (),
            )

        if not isinstance(observation, VerifierObservation):
            raise RootCauseIntegrityError(
                "Verifier.verify() violated its return contract.",
                context={
                    "candidate_id": specification.candidate_id,
                    "specification_id": specification.id,
                    "verifier_id": specification.verifier_id,
                    "actual_type": type(observation).__name__,
                },
            )
        _validate_observation(
            observation,
            specification=specification,
            existing_evidence=evidence_catalog,
            existing_artifacts=artifact_catalog,
        )

        finished_at = _normalize_clock_value(self._clock(), "clock(finished_at)")
        return (
            VerificationResult(
            id=_result_id(
                context.request.id,
                specification.id,
                specification.candidate_id,
                specification.verifier_id,
            ),
            candidate_id=specification.candidate_id,
            verifier_id=specification.verifier_id,
            outcome=observation.outcome,
            procedure=specification.procedure,
            expected_result=specification.expected_result,
            observed_result=observation.observed_result,
            input_artifact_ids=specification.input_artifact_ids,
            output_artifacts=observation.output_artifacts,
            evidence_ids=tuple(item.id for item in observation.evidence),
            command=specification.command,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=_duration(started_at, finished_at),
                metadata={
                    "specification_id": specification.id,
                    "required": specification.required,
                    **dict(specification.metadata),
                    **dict(observation.metadata),
                },
            ),
            observation.evidence,
        )

    @staticmethod
    def _not_run_result(
        request_id: str, specification: VerificationSpecification
    ) -> VerificationResult:
        return VerificationResult(
            id=_result_id(
                request_id,
                specification.id,
                specification.candidate_id,
                specification.verifier_id,
            ),
            candidate_id=specification.candidate_id,
            verifier_id=specification.verifier_id,
            outcome=VerificationOutcome.NOT_RUN,
            procedure=specification.procedure,
            expected_result=specification.expected_result,
            input_artifact_ids=specification.input_artifact_ids,
            command=specification.command,
            metadata={
                "specification_id": specification.id,
                "required": specification.required,
                **dict(specification.metadata),
            },
        )

    @staticmethod
    def _skipped_result(
        request_id: str,
        specification: VerificationSpecification,
        observed_result: str,
    ) -> VerificationResult:
        # VerificationResult requires observed_result for SKIPPED and permits no
        # error_message.  No timing is recorded because no verifier ran.
        return VerificationResult(
            id=_result_id(
                context.request.id,
                specification.id,
                specification.candidate_id,
                specification.verifier_id,
            ),
            candidate_id=specification.candidate_id,
            verifier_id=specification.verifier_id,
            outcome=VerificationOutcome.SKIPPED,
            procedure=specification.procedure,
            expected_result=specification.expected_result,
            observed_result=observed_result,
            input_artifact_ids=specification.input_artifact_ids,
            command=specification.command,
            metadata={
                "specification_id": specification.id,
                "required": specification.required,
                **dict(specification.metadata),
            },
        )


def execute_verifications(
    context: VerificationStageContext,
    *,
    plan_sources: Sequence[VerificationPlanSource],
    verifiers: Sequence[Verifier],
    clock: Callable[[], datetime] | None = None,
) -> VerificationExecution:
    """Functional facade for one deterministic verification execution."""

    return VerificationEngine(
        plan_sources=plan_sources,
        verifiers=verifiers,
        clock=clock,
    ).execute(context)


# -----------------------------------------------------------------------------
# Validation and aggregation helpers
# -----------------------------------------------------------------------------


def _validate_plans_against_context(
    plans: Sequence[VerificationSpecification],
    context: VerificationStageContext,
    verifiers: Mapping[str, Verifier],
) -> None:
    candidate_ids = set(context.candidate_catalog)
    evidence_ids = set(context.evidence_catalog)
    artifact_ids = set(context.artifact_catalog)
    unknown_candidates = sorted({plan.candidate_id for plan in plans} - candidate_ids)
    unknown_verifiers = sorted({plan.verifier_id for plan in plans} - set(verifiers))
    if unknown_candidates:
        raise RootCauseInputError(
            "Verification plans reference unknown candidates.",
            context={"candidate_ids": unknown_candidates},
        )
    if unknown_verifiers:
        raise RootCauseInputError(
            "Verification plans reference unregistered verifiers.",
            context={"verifier_ids": unknown_verifiers},
        )
    for plan in plans:
        missing_evidence = sorted(set(plan.prerequisite_evidence_ids) - evidence_ids)
        missing_artifacts = sorted(set(plan.input_artifact_ids) - artifact_ids)
        if missing_evidence or missing_artifacts:
            raise RootCauseInputError(
                "Verification plan inputs are unavailable.",
                context={
                    "specification_id": plan.id,
                    "missing_evidence_ids": missing_evidence,
                    "missing_artifact_ids": missing_artifacts,
                },
            )


def _validate_observation(
    observation: VerifierObservation,
    *,
    specification: VerificationSpecification,
    existing_evidence: Mapping[str, EvidenceReference],
    existing_artifacts: Mapping[str, ArtifactReference],
) -> None:
    expected_direction = {
        VerificationOutcome.PASSED: EvidenceDirection.SUPPORTS,
        VerificationOutcome.FAILED: EvidenceDirection.CONTRADICTS,
        VerificationOutcome.INCONCLUSIVE: EvidenceDirection.NEUTRAL,
    }[observation.outcome]

    for evidence in observation.evidence:
        if evidence.id in existing_evidence:
            raise RootCauseIntegrityError(
                "Verifier output evidence ids must be new within the investigation.",
                context={"specification_id": specification.id, "evidence_id": evidence.id},
            )
        if evidence.related_candidate_id != specification.candidate_id:
            raise RootCauseIntegrityError(
                "Verifier evidence must be explicitly bound to the verified candidate.",
                context={
                    "specification_id": specification.id,
                    "evidence_id": evidence.id,
                    "expected_candidate_id": specification.candidate_id,
                    "actual_candidate_id": evidence.related_candidate_id,
                },
            )
        if evidence.direction is not expected_direction:
            raise RootCauseIntegrityError(
                "Verifier evidence direction conflicts with the verification outcome.",
                context={
                    "specification_id": specification.id,
                    "evidence_id": evidence.id,
                    "outcome": observation.outcome.value,
                    "expected_direction": expected_direction.value,
                    "actual_direction": evidence.direction.value,
                },
            )

    for artifact in observation.output_artifacts:
        if artifact.id in existing_artifacts:
            raise RootCauseIntegrityError(
                "Verifier output artefact ids must be new within the investigation.",
                context={"specification_id": specification.id, "artifact_id": artifact.id},
            )


def _summarize_candidates(
    request_id: str,
    candidates: Sequence[CausalCandidate],
    specifications: Sequence[VerificationSpecification],
    results: Sequence[VerificationResult],
) -> tuple[tuple[CausalCandidate, ...], tuple[CandidateVerificationSummary, ...]]:
    specs_by_candidate: dict[str, list[VerificationSpecification]] = defaultdict(list)
    results_by_candidate: dict[str, list[VerificationResult]] = defaultdict(list)
    spec_by_result_id = {
        _result_id(request_id, spec.id, spec.candidate_id, spec.verifier_id): spec
        for spec in specifications
    }
    for spec in specifications:
        specs_by_candidate[spec.candidate_id].append(spec)
    for result in results:
        results_by_candidate[result.candidate_id].append(result)

    updated: list[CausalCandidate] = []
    summaries: list[CandidateVerificationSummary] = []
    for candidate in sorted(candidates, key=lambda item: item.id):
        candidate_results = tuple(
            sorted(results_by_candidate.get(candidate.id, ()), key=lambda item: item.id)
        )
        required_results = tuple(
            result
            for result in candidate_results
            if spec_by_result_id[result.id].required
        )
        counts = {outcome: 0 for outcome in VerificationOutcome}
        for result in candidate_results:
            counts[result.outcome] += 1

        status, rationale = _derive_candidate_status(
            required_results=required_results,
            all_results=candidate_results,
        )
        updated_candidate = replace(candidate, status=status)
        updated.append(updated_candidate)
        summaries.append(
            CandidateVerificationSummary(
                candidate_id=candidate.id,
                status=status,
                result_ids=tuple(result.id for result in candidate_results),
                required_result_ids=tuple(result.id for result in required_results),
                passed=counts[VerificationOutcome.PASSED],
                failed=counts[VerificationOutcome.FAILED],
                inconclusive=counts[VerificationOutcome.INCONCLUSIVE],
                error=counts[VerificationOutcome.ERROR],
                skipped=counts[VerificationOutcome.SKIPPED],
                not_run=counts[VerificationOutcome.NOT_RUN],
                rationale=rationale,
            )
        )
    return tuple(updated), tuple(summaries)


def _derive_candidate_status(
    *,
    required_results: Sequence[VerificationResult],
    all_results: Sequence[VerificationResult],
) -> tuple[CandidateStatus, str]:
    if not all_results:
        return CandidateStatus.NOT_TESTABLE, "No explicit verification plan was available."
    all_outcomes = {result.outcome for result in all_results}
    if VerificationOutcome.FAILED in all_outcomes:
        return (
            CandidateStatus.REFUTED,
            "At least one deterministic verification falsified the candidate.",
        )
    if not required_results:
        return (
            CandidateStatus.INSUFFICIENT_EVIDENCE,
            "Only optional checks were available; they cannot support the candidate.",
        )
    required_outcomes = {result.outcome for result in required_results}
    if required_outcomes == {VerificationOutcome.PASSED}:
        return (
            CandidateStatus.SUPPORTED,
            "All required deterministic verifications passed.",
        )
    if VerificationOutcome.NOT_RUN in required_outcomes:
        return (
            CandidateStatus.PRIORITIZED,
            "Required verifications were planned but not executed.",
        )
    return (
        CandidateStatus.INSUFFICIENT_EVIDENCE,
        "Required verifications did not produce a complete decisive result.",
    )


def _validate_dependency_graph(plans: Sequence[VerificationSpecification]) -> None:
    plan_ids = {plan.id for plan in plans}
    for plan in plans:
        unknown = sorted(set(plan.depends_on) - plan_ids)
        if unknown:
            raise ValueError(
                f"Verification plan {plan.id!r} depends on unknown plans: {', '.join(unknown)}."
            )
        cross_candidate = sorted(
            dependency_id
            for dependency_id in plan.depends_on
            if next(item for item in plans if item.id == dependency_id).candidate_id
            != plan.candidate_id
        )
        if cross_candidate:
            raise ValueError(
                f"Verification plan {plan.id!r} has cross-candidate dependencies: "
                + ", ".join(cross_candidate)
                + "."
            )

    dependencies = {plan.id: set(plan.depends_on) for plan in plans}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(plan_id: str) -> None:
        if plan_id in visited:
            return
        if plan_id in visiting:
            raise ValueError(f"Verification plans contain a dependency cycle at {plan_id!r}.")
        visiting.add(plan_id)
        for dependency_id in sorted(dependencies[plan_id]):
            visit(dependency_id)
        visiting.remove(plan_id)
        visited.add(plan_id)

    for plan_id in sorted(dependencies):
        visit(plan_id)


def _execution_layers(
    plans: Sequence[VerificationSpecification],
) -> tuple[tuple[VerificationSpecification, ...], ...]:
    remaining = {plan.id: plan for plan in plans}
    completed: set[str] = set()
    layers: list[tuple[VerificationSpecification, ...]] = []
    while remaining:
        layer = tuple(
            sorted(
                (
                    plan
                    for plan in remaining.values()
                    if set(plan.depends_on) <= completed
                ),
                key=lambda item: item.id,
            )
        )
        if not layer:
            raise RootCauseIntegrityError(
                "Verification dependency graph cannot be scheduled.",
                context={"remaining_specification_ids": sorted(remaining)},
            )
        layers.append(layer)
        for plan in layer:
            remaining.pop(plan.id)
            completed.add(plan.id)
    return tuple(layers)


# -----------------------------------------------------------------------------
# Generic normalization helpers
# -----------------------------------------------------------------------------


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


def _optional_identifier(value: str | None, field_name: str) -> str | None:
    return None if value is None else _require_identifier(value, field_name)


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


def _normalize_models(values: Sequence[Any], expected_type: type[Any], field_name: str) -> tuple[Any, ...]:
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


def _normalize_protocols(values: Sequence[Any], protocol: type[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, protocol):
            raise TypeError(
                f"{field_name}[{index}] does not satisfy {protocol.__name__}."
            )
        _require_identifier(value.id, f"{field_name}[{index}].id")
    return normalized


def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    identifiers = [value.id for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{field_name} must contain unique ids.")


def _require_unique_candidate_assessments(values: Sequence[CandidateAssessment]) -> None:
    identifiers = [value.candidate_id for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("assessments must contain unique candidate_id values.")


def _require_unique_summary_candidates(values: Sequence[CandidateVerificationSummary]) -> None:
    identifiers = [value.candidate_id for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("summaries must contain unique candidate_id values.")


def _require_unique_protocol_ids(values: Sequence[Any], field_name: str) -> None:
    identifiers = [_require_identifier(value.id, f"{field_name}.id") for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{field_name} must contain unique ids.")


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        frozen[_require_text(key, f"{field_name} key")] = _deep_freeze(item)
    return MappingProxyType(frozen)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                _require_text(key, "mapping key"): _deep_freeze(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    return value


def _freeze_sequence_mapping(
    value: Mapping[str, Sequence[str]], field_name: str, *, identifiers: bool
) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, tuple[str, ...]] = {}
    for key, items in value.items():
        normalized_key = _require_identifier(key, f"{field_name} key")
        normalized[normalized_key] = (
            _normalize_identifier_tuple(items, f"{field_name}[{key!r}]")
            if identifiers
            else _normalize_text_tuple(items, f"{field_name}[{key!r}]")
        )
    return MappingProxyType(dict(sorted(normalized.items())))


def _freeze_text_mapping(
    value: Mapping[str, str], field_name: str, *, identifiers: bool
) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = _require_identifier(key, f"{field_name} key")
        normalized[normalized_key] = (
            _require_identifier(item, f"{field_name}[{key!r}]")
            if identifiers
            else _require_text(item, f"{field_name}[{key!r}]")
        )
    return MappingProxyType(dict(sorted(normalized.items())))


def _normalize_clock_value(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must return datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _duration(started_at: datetime, finished_at: datetime) -> float:
    duration = (finished_at - started_at).total_seconds()
    if not isfinite(duration) or duration < 0:
        raise RootCauseIntegrityError(
            "Verification clock produced an invalid execution window.",
            context={
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_seconds": duration,
            },
        )
    return duration


def _stable_identifier(prefix: str, payload: Mapping[str, Any]) -> str:
    canonical = dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{_require_identifier(prefix, 'prefix')}:{digest}"


def _result_id(
    request_id: str, specification_id: str, candidate_id: str, verifier_id: str
) -> str:
    return _stable_identifier(
        "verification.result",
        {
            "request_id": request_id,
            "specification_id": specification_id,
            "candidate_id": candidate_id,
            "verifier_id": verifier_id,
        },
    )


def _register_unique_output(
    registry: dict[str, Any], item: Any, label: str
) -> None:
    existing = registry.get(item.id)
    if existing is not None and existing != item:
        raise RootCauseIntegrityError(
            f"Different {label}s share the same id.",
            context={f"{label.replace(' ', '_')}_id": item.id},
        )
    registry[item.id] = item