from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.root_cause.exceptions import RootCauseInputError, RootCauseIntegrityError
from validation.root_cause.models import (
    CandidateStatus,
    CausalCandidate,
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
)
from validation.root_cause.ranking import (
    AlternativeExplanationCriterion,
    CandidateRanker,
    CriterionAssessment,
    EvidenceCriterion,
    KnowledgeMatchCriterion,
    MechanismSpecificityCriterion,
    MissingEvidenceCriterion,
    ProvenanceCriterion,
    RankingContext,
    ReproducibilityCriterion,
    rank_candidates,
)


def _request(*, strict: bool = True, domains=(ValidationDomain.CONDITIONS,)) -> RootCauseRequest:
    return RootCauseRequest(
        id="request-1",
        experiment_id="experiment-1",
        run_id="run-1",
        validation_result_ids=("validation-1",),
        requested_domains=domains,
        strict_integrity=strict,
    )


def _signal(identifier: str = "signal-1", *, evidence_ids=("evidence-neutral",), domain=ValidationDomain.CONDITIONS) -> DiscrepancySignal:
    return DiscrepancySignal(
        id=identifier,
        domain=domain,
        classification=DifferenceClassification.PROBABILISTIC,
        summary="Observed prevalence discrepancy.",
        source_id="validation-1",
        metric_id="prevalence.diabetes",
        evidence_ids=evidence_ids,
        affected_entity_ids=("diabetes.json",),
        metadata={"source_module": "diabetes.json", "source_state": "Diagnose Diabetes"},
    )


def _evidence(identifier: str, *, direction=EvidenceDirection.NEUTRAL, candidate_id=None) -> EvidenceReference:
    return EvidenceReference(
        id=identifier,
        source_type="validation",
        summary=f"Evidence {identifier}.",
        locator=f"memory://{identifier}",
        direction=direction,
        related_candidate_id=candidate_id,
    )


def _candidate(identifier: str, *, alternatives=(), metadata=None, prerequisite=("evidence-neutral",)) -> CausalCandidate:
    return CausalCandidate(
        id=identifier,
        category=RootCauseCategory.PROBABILISTIC_SEMANTICS,
        statement=f"Candidate {identifier}.",
        mechanism="Distributed transition sampling differs between engines.",
        signal_ids=("signal-1",),
        source_rule_id="rule.probabilistic-semantics",
        expected_observations=("Controlled branch frequencies diverge.",),
        falsification_criteria=("Branch frequencies remain equivalent.",),
        prerequisite_evidence_ids=prerequisite,
        alternative_candidate_ids=alternatives,
        metadata=metadata or {"source_module": "diabetes.json", "source_state": "Diagnose Diabetes"},
    )


def test_ranking_is_deterministic_and_independent_of_input_order() -> None:
    request = _request()
    signal = _signal()
    evidence = (_evidence("evidence-neutral"),)
    a = _candidate("candidate-a")
    b = _candidate("candidate-b")

    left = rank_candidates(request, (a, b), signals=(signal,), evidence=evidence)
    right = rank_candidates(request, (b, a), signals=(signal,), evidence=evidence)

    assert left == right
    assert tuple(item.id for item in left.candidates) == ("candidate-a", "candidate-b")
    assert tuple(item.rank for item in left.assessments) == (1, 2)


def test_directional_evidence_changes_only_explicit_candidate_components() -> None:
    result = rank_candidates(
        _request(),
        (_candidate("candidate-a"), _candidate("candidate-b")),
        signals=(_signal(),),
        evidence=(
            _evidence("evidence-neutral"),
            _evidence("evidence-support", direction=EvidenceDirection.SUPPORTS, candidate_id="candidate-a"),
            _evidence("evidence-contradict", direction=EvidenceDirection.CONTRADICTS, candidate_id="candidate-b"),
        ),
    )

    assessments = {item.candidate_id: item for item in result.assessments}
    assert assessments["candidate-a"].evidence_support > 0
    assert assessments["candidate-a"].supporting_evidence_ids == ("evidence-support",)
    assert assessments["candidate-b"].contradictory_evidence > 0
    assert assessments["candidate-b"].contradictory_evidence_ids == ("evidence-contradict",)
    assert assessments["candidate-a"].rank < assessments["candidate-b"].rank


def test_total_score_matches_documented_formula_and_components() -> None:
    result = rank_candidates(
        _request(),
        (_candidate("candidate-a"),),
        signals=(_signal(),),
        evidence=(_evidence("evidence-neutral"),),
    )
    assessment = result.assessments[0]
    expected = (
        assessment.evidence_support
        + assessment.knowledge_match
        + assessment.provenance_match
        + assessment.reproducibility
        + assessment.mechanism_specificity
        - assessment.contradictory_evidence
        - assessment.missing_evidence
        - assessment.alternative_explanations
    )
    assert assessment.total_score == pytest.approx(expected)
    assert set(assessment.score_components) == {
        "evidence_support", "knowledge_match", "provenance_match", "reproducibility",
        "mechanism_specificity", "contradictory_evidence", "missing_evidence",
        "alternative_explanations",
    }


def test_missing_prerequisite_is_penalized_not_raised() -> None:
    result = rank_candidates(
        _request(),
        (_candidate("candidate-a", prerequisite=("missing-evidence",)),),
        signals=(_signal(),),
        evidence=(_evidence("evidence-neutral"),),
    )
    assessment = result.assessments[0]
    assert assessment.missing_evidence > 0
    assert "Missing prerequisite evidence 'missing-evidence'." in assessment.missing_evidence_descriptions


def test_context_rejects_signal_evidence_not_in_catalog() -> None:
    with pytest.raises(RootCauseIntegrityError, match="references unavailable evidence"):
        RankingContext(
            request=_request(),
            candidates=(_candidate("candidate-a"),),
            signals=(_signal(evidence_ids=("not-present",)),),
            evidence=(_evidence("evidence-neutral"),),
        )


def test_context_rejects_signal_outside_requested_domain() -> None:
    with pytest.raises(RootCauseInputError, match="outside the request's validation domains"):
        RankingContext(
            request=_request(),
            candidates=(_candidate("candidate-a"),),
            signals=(_signal(domain=ValidationDomain.MEDICATIONS),),
            evidence=(_evidence("evidence-neutral"),),
        )


def test_context_rejects_non_generated_candidate() -> None:
    candidate = _candidate("candidate-a")
    candidate = CausalCandidate(
        id=candidate.id,
        category=candidate.category,
        statement=candidate.statement,
        mechanism=candidate.mechanism,
        signal_ids=candidate.signal_ids,
        status=CandidateStatus.PRIORITIZED,
        source_rule_id=candidate.source_rule_id,
        expected_observations=candidate.expected_observations,
        falsification_criteria=candidate.falsification_criteria,
        prerequisite_evidence_ids=candidate.prerequisite_evidence_ids,
        metadata=candidate.metadata,
    )
    with pytest.raises(RootCauseInputError, match="only newly generated"):
        RankingContext(
            request=_request(), candidates=(candidate,), signals=(_signal(),),
            evidence=(_evidence("evidence-neutral"),),
        )


class _BrokenEvidenceCriterion:
    id = "ranking.evidence"
    component = "evidence_support"
    def assess(self, candidate, context):
        raise RuntimeError("plugin failed")


def _criteria_with_broken_evidence():
    return (
        _BrokenEvidenceCriterion(), KnowledgeMatchCriterion(), ProvenanceCriterion(),
        ReproducibilityCriterion(), MechanismSpecificityCriterion(),
        EvidenceCriterion(id="ranking.contradictory_evidence", component="contradictory_evidence"),
        MissingEvidenceCriterion(), AlternativeExplanationCriterion(),
    )


def test_strict_mode_normalizes_criterion_failure_as_integrity_error() -> None:
    context = RankingContext(
        request=_request(strict=True), candidates=(_candidate("candidate-a"),),
        signals=(_signal(),), evidence=(_evidence("evidence-neutral"),),
    )
    with pytest.raises(RootCauseIntegrityError, match="violated its execution contract"):
        CandidateRanker(_criteria_with_broken_evidence()).rank(context)


def test_permissive_mode_records_criterion_failure_and_contributes_zero() -> None:
    context = RankingContext(
        request=_request(strict=False), candidates=(_candidate("candidate-a"),),
        signals=(_signal(),), evidence=(_evidence("evidence-neutral"),),
    )
    result = CandidateRanker(_criteria_with_broken_evidence()).rank(context)
    assert result.assessments[0].evidence_support == 0.0
    assert result.diagnostics[0].code == "ranking.criterion_failed"


def test_empty_candidate_set_is_valid() -> None:
    result = rank_candidates(
        _request(), (), signals=(_signal(),), evidence=(_evidence("evidence-neutral"),)
    )
    assert result.candidates == ()
    assert result.assessments == ()


def test_output_is_deeply_immutable() -> None:
    result = rank_candidates(
        _request(), (_candidate("candidate-a"),), signals=(_signal(),),
        evidence=(_evidence("evidence-neutral"),), metadata={"nested": {"values": [1, 2]}},
    )
    with pytest.raises(FrozenInstanceError):
        result.request_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.metadata["context"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        result.metadata["context"]["nested"]["values"] = ()  # type: ignore[index]