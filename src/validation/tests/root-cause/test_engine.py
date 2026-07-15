from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.root_cause.attribution import AttributionResult
from validation.root_cause.engine import (
    ConservativeFindingPolicy,
    EngineStage,
    FindingDecision,
    StageRecord,
    _aggregate_report_conclusion,
    _canonical,
    _finding_attribution,
    _validate_finding_decision,
)
from validation.root_cause.exceptions import RootCauseIntegrityError
from validation.root_cause.models import (
    AttributionLevel,
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    CausalConfidence,
    DifferenceClassification,
    DiscrepancySignal,
    RootCauseFinding,
    RootCauseStatus,
    SourceAttribution,
)


def _signal() -> DiscrepancySignal:
    return DiscrepancySignal(
        id="signal:1",
        domain=ValidationDomain.CONDITIONS,
        classification=DifferenceClassification.SEMANTIC,
        summary="Condition prevalence differs.",
        source_id="validation:1",
    )


def _candidate(candidate_id: str = "candidate:1") -> CausalCandidate:
    return CausalCandidate(
        id=candidate_id,
        category=RootCauseCategory.MODULE_DEFINITION,
        statement="The module definition differs.",
        mechanism="A state emits a different clinical event.",
        signal_ids=("signal:1",),
        source_rule_id="rule:1",
    )


def _assessment(candidate_id: str = "candidate:1", score: float = 0.0) -> CandidateAssessment:
    return CandidateAssessment(
        candidate_id=candidate_id,
        rank=1,
        total_score=score,
        rationale="Deterministic ranking.",
    )


def _finding(status: RootCauseStatus, confidence: CausalConfidence) -> RootCauseFinding:
    classification = DifferenceClassification.SEMANTIC
    selected: tuple[str, ...] = ()
    support: tuple[str, ...] = ()
    if status is RootCauseStatus.PLAUSIBLE:
        selected = ("candidate:1",)
    return RootCauseFinding(
        id=f"finding:{status.value}",
        status=status,
        confidence=confidence,
        classification=classification,
        domain=ValidationDomain.CONDITIONS,
        summary="Finding summary.",
        explanation="Finding explanation.",
        signal_ids=("signal:1",),
        selected_candidate_ids=selected,
        supporting_evidence_ids=support,
    )


def test_stage_record_rejects_reverse_time() -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="cannot precede"):
        StageRecord(
            stage=EngineStage.EVIDENCE_COLLECTION,
            started_at=now,
            finished_at=now - timedelta(seconds=1),
            input_count=1,
            output_count=1,
        )


def test_conservative_policy_returns_inconclusive_without_candidates() -> None:
    decision = ConservativeFindingPolicy().decide(
        signal=_signal(),
        candidates=(),
        assessments=(),
        evidence=(),
        verifications=(),
        attributions={},
    )
    assert decision.status is RootCauseStatus.INCONCLUSIVE
    assert decision.confidence is CausalConfidence.NONE
    assert not decision.selected_candidate_ids


def test_aggregate_mixed_independent_statuses_is_not_multifactorial() -> None:
    result = _aggregate_report_conclusion(
        (
            _finding(RootCauseStatus.PLAUSIBLE, CausalConfidence.LOW),
            _finding(RootCauseStatus.INCONCLUSIVE, CausalConfidence.NONE),
        )
    )
    assert result == (RootCauseStatus.INCONCLUSIVE, CausalConfidence.NONE)


def test_aggregate_equal_status_uses_lowest_confidence() -> None:
    result = _aggregate_report_conclusion(
        (
            _finding(RootCauseStatus.PLAUSIBLE, CausalConfidence.MODERATE),
            _finding(RootCauseStatus.PLAUSIBLE, CausalConfidence.LOW),
        )
    )
    assert result == (RootCauseStatus.PLAUSIBLE, CausalConfidence.LOW)


def test_aggregate_empty_collection_is_integrity_error() -> None:
    with pytest.raises(RootCauseIntegrityError, match="empty finding"):
        _aggregate_report_conclusion(())


def test_finding_policy_cannot_reference_candidate_from_another_signal() -> None:
    decision = FindingDecision(
        status=RootCauseStatus.PLAUSIBLE,
        confidence=CausalConfidence.LOW,
        classification=DifferenceClassification.SEMANTIC,
        selected_candidate_ids=("candidate:other",),
    )
    with pytest.raises(RootCauseIntegrityError, match="outside the current signal"):
        _validate_finding_decision(
            decision,
            signal=_signal(),
            candidate_ids={"candidate:1"},
            evidence_ids=set(),
            verification_by_id={},
        )


def test_finding_policy_cannot_reference_unknown_evidence() -> None:
    decision = FindingDecision(
        status=RootCauseStatus.PROBABLE,
        confidence=CausalConfidence.MODERATE,
        classification=DifferenceClassification.SEMANTIC,
        selected_candidate_ids=("candidate:1",),
        supporting_evidence_ids=("evidence:missing",),
    )
    with pytest.raises(RootCauseIntegrityError, match="unknown evidence"):
        _validate_finding_decision(
            decision,
            signal=_signal(),
            candidate_ids={"candidate:1"},
            evidence_ids=set(),
            verification_by_id={},
        )


def test_multicandidate_attribution_is_unknown_when_locations_differ() -> None:
    first = AttributionResult(
        attribution=SourceAttribution(
            level=AttributionLevel.MODULE,
            module="diabetes.json",
            confidence=CausalConfidence.HIGH,
            evidence_ids=("evidence:1",),
            rationale="Module provenance.",
        )
    )
    second = AttributionResult(
        attribution=SourceAttribution(
            level=AttributionLevel.MODULE,
            module="hypertension.json",
            confidence=CausalConfidence.HIGH,
            evidence_ids=("evidence:2",),
            rationale="Module provenance.",
        )
    )
    attribution = _finding_attribution(
        ("candidate:1", "candidate:2"),
        {"candidate:1": first, "candidate:2": second},
    )
    assert attribution.level is AttributionLevel.UNKNOWN
    assert attribution.confidence is CausalConfidence.NONE


def test_multicandidate_attribution_preserves_identical_location() -> None:
    shared = SourceAttribution(
        level=AttributionLevel.MODULE,
        module="diabetes.json",
        confidence=CausalConfidence.HIGH,
        evidence_ids=("evidence:1",),
        rationale="Shared module provenance.",
    )
    attribution = _finding_attribution(
        ("candidate:1", "candidate:2"),
        {
            "candidate:1": AttributionResult(attribution=shared),
            "candidate:2": AttributionResult(attribution=shared),
        },
    )
    assert attribution == shared


def test_canonical_serialization_sorts_sets_deterministically() -> None:
    assert _canonical({"b", "a", "c"}) == ["a", "b", "c"]