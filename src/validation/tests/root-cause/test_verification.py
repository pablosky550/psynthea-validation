from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from validation.knowledge.taxonomy import RootCauseCategory
from validation.root_cause.exceptions import RootCauseIntegrityError
from validation.root_cause.models import (
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
    VerificationOutcome,
)
from validation.root_cause.verification import (
    ExecutionFailurePolicy,
    ExplicitVerificationPlanSource,
    VerificationEngine,
    VerificationSpecification,
    VerificationStageContext,
    VerifierObservation,
)


def request(identifier: str = "request.one", *, execute: bool = True) -> RootCauseRequest:
    return RootCauseRequest(
        id=identifier,
        experiment_id="experiment.one",
        run_id="run.one",
        validation_result_ids=("validation.one",),
        execute_verifications=execute,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )


def candidate(identifier: str = "candidate.one") -> CausalCandidate:
    return CausalCandidate(
        id=identifier,
        category=RootCauseCategory.UNKNOWN,
        statement="A deterministic mechanism explains the discrepancy.",
        mechanism="The candidate changes the observed validation output.",
        signal_ids=("signal.one",),
        status=CandidateStatus.PRIORITIZED,
        source_rule_id="rule.one",
    )


def assessment(identifier: str = "candidate.one") -> CandidateAssessment:
    return CandidateAssessment(
        candidate_id=identifier,
        rank=1,
        total_score=0.0,
    )


def plan(*, required: bool = True) -> VerificationSpecification:
    return VerificationSpecification(
        id="spec.one",
        candidate_id="candidate.one",
        verifier_id="verifier.one",
        procedure="Execute a deterministic comparison.",
        expected_result="The candidate-specific difference is reproduced.",
        required=required,
    )


def evidence(
    direction: EvidenceDirection,
    *,
    identifier: str = "evidence.generated",
) -> EvidenceReference:
    return EvidenceReference(
        id=identifier,
        source_type="verification.output",
        summary="Deterministic verification observation.",
        locator="verification://spec.one",
        direction=direction,
        related_candidate_id="candidate.one",
    )


class FixedClock:
    def __init__(self) -> None:
        self._values = iter(
            (
                datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
                datetime(2026, 7, 15, 10, 0, 1, tzinfo=UTC),
            )
        )

    def __call__(self) -> datetime:
        return next(self._values)


@dataclass(frozen=True)
class StaticVerifier:
    observation: object
    id: str = "verifier.one"

    def verify(self, context):
        del context
        return self.observation


@dataclass(frozen=True)
class RaisingVerifier:
    id: str = "verifier.one"

    def verify(self, context):
        del context
        raise RuntimeError("backend unavailable")


def context(req: RootCauseRequest | None = None) -> VerificationStageContext:
    return VerificationStageContext(
        request=req or request(),
        candidates=(candidate(),),
        assessments=(assessment(),),
    )


def engine(verifier, *, specification: VerificationSpecification | None = None) -> VerificationEngine:
    return VerificationEngine(
        plan_sources=(ExplicitVerificationPlanSource((specification or plan(),)),),
        verifiers=(verifier,),
        clock=FixedClock(),
    )


def test_decisive_observation_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires generated evidence"):
        VerifierObservation(
            outcome=VerificationOutcome.PASSED,
            observed_result="Matched.",
        )


def test_passed_verification_supports_candidate() -> None:
    execution = engine(
        StaticVerifier(
            VerifierObservation(
                outcome=VerificationOutcome.PASSED,
                observed_result="Matched.",
                evidence=(evidence(EvidenceDirection.SUPPORTS),),
            )
        )
    ).execute(context())

    assert execution.candidates[0].status is CandidateStatus.SUPPORTED
    assert execution.results[0].outcome is VerificationOutcome.PASSED
    assert execution.results[0].duration_seconds == 1.0


def test_inconclusive_verification_accepts_only_neutral_evidence() -> None:
    execution = engine(
        StaticVerifier(
            VerifierObservation(
                outcome=VerificationOutcome.INCONCLUSIVE,
                observed_result="The check did not discriminate the hypotheses.",
                evidence=(evidence(EvidenceDirection.NEUTRAL),),
            )
        )
    ).execute(context())

    assert execution.candidates[0].status is CandidateStatus.INSUFFICIENT_EVIDENCE


def test_inconclusive_directional_evidence_is_integrity_error() -> None:
    verifier = StaticVerifier(
        VerifierObservation(
            outcome=VerificationOutcome.INCONCLUSIVE,
            observed_result="Ambiguous.",
            evidence=(evidence(EvidenceDirection.SUPPORTS),),
        )
    )
    with pytest.raises(RootCauseIntegrityError, match="direction conflicts"):
        engine(verifier).execute(context())


def test_optional_failed_check_refutes_candidate() -> None:
    execution = engine(
        StaticVerifier(
            VerifierObservation(
                outcome=VerificationOutcome.FAILED,
                observed_result="The expected mechanism was absent.",
                evidence=(evidence(EvidenceDirection.CONTRADICTS),),
            )
        ),
        specification=plan(required=False),
    ).execute(context())

    assert execution.candidates[0].status is CandidateStatus.REFUTED


def test_verifier_contract_violation_is_not_downgraded_to_error_result() -> None:
    with pytest.raises(RootCauseIntegrityError, match="return contract"):
        engine(StaticVerifier(object())).execute(context())


def test_technical_failure_is_recorded_as_error_by_default() -> None:
    execution = engine(RaisingVerifier()).execute(context())

    assert execution.results[0].outcome is VerificationOutcome.ERROR
    assert execution.candidates[0].status is CandidateStatus.INSUFFICIENT_EVIDENCE
    assert execution.results[0].error_message == "RuntimeError: backend unavailable"


def test_result_identifier_is_scoped_to_request() -> None:
    verifier = StaticVerifier(
        VerifierObservation(
            outcome=VerificationOutcome.PASSED,
            observed_result="Matched.",
            evidence=(evidence(EvidenceDirection.SUPPORTS),),
        )
    )
    first = engine(verifier).execute(context(request("request.one")))
    second = engine(verifier).execute(context(request("request.two")))

    assert first.results[0].id != second.results[0].id


def test_verifier_cannot_reuse_existing_evidence_identifier() -> None:
    existing = evidence(EvidenceDirection.NEUTRAL)
    ctx = VerificationStageContext(
        request=request(),
        candidates=(candidate(),),
        assessments=(assessment(),),
        evidence=(existing,),
    )
    verifier = StaticVerifier(
        VerifierObservation(
            outcome=VerificationOutcome.PASSED,
            observed_result="Matched.",
            evidence=(evidence(EvidenceDirection.SUPPORTS),),
        )
    )
    with pytest.raises(RootCauseIntegrityError, match="must be new"):
        engine(verifier).execute(ctx)


def test_disabled_execution_produces_not_run_without_calling_verifier() -> None:
    execution = engine(RaisingVerifier()).execute(context(request(execute=False)))

    assert execution.results[0].outcome is VerificationOutcome.NOT_RUN
    assert execution.candidates[0].status is CandidateStatus.PRIORITIZED