from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from validation.knowledge.taxonomy import RootCauseCategory
from validation.root_cause.attribution import (
    AttributionContext,
    AttributionEngine,
    AttributionHint,
    EvidenceMetadataRule,
)
from validation.root_cause.exceptions import RootCauseIntegrityError
from validation.root_cause.models import (
    AttributionLevel,
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    CausalConfidence,
    EvidenceDirection,
    EvidenceReference,
    VerificationOutcome,
    VerificationResult,
)


def candidate(status: CandidateStatus = CandidateStatus.PRIORITIZED) -> CausalCandidate:
    return CausalCandidate(
        id="candidate.1",
        category=RootCauseCategory.TEMPORAL_SEMANTICS,
        statement="Delay semantics differ.",
        mechanism="Different temporal transition behavior.",
        signal_ids=("signal.1",),
        status=status,
        source_rule_id="rule.1",
    )


def assessment(*supporting: str) -> CandidateAssessment:
    return CandidateAssessment(
        candidate_id="candidate.1",
        rank=1,
        total_score=1.0,
        evidence_support=1.0,
        supporting_evidence_ids=tuple(supporting),
        rationale="Ranked from evidence.",
    )


def evidence(eid: str, **metadata: str) -> EvidenceReference:
    return EvidenceReference(
        id=eid,
        source_type="clinical.provenance",
        summary="Observed provenance.",
        locator="record.conditions[0]",
        direction=EvidenceDirection.SUPPORTS,
        related_candidate_id="candidate.1",
        metadata=metadata,
    )


def test_state_attribution_from_canonical_provenance() -> None:
    ev = evidence("evidence.1", component="engine", source_module="diabetes.json", source_state="Diagnose Diabetes")
    result = AttributionEngine().attribute(
        AttributionContext(candidate(), assessment(ev.id), (ev,))
    )
    assert result.attribution.level is AttributionLevel.STATE
    assert result.attribution.module == "diabetes.json"
    assert result.attribution.state == "Diagnose Diabetes"
    assert result.attribution.confidence is CausalConfidence.LOW


def test_passed_verification_and_supported_candidate_raise_confidence() -> None:
    ev1 = evidence("evidence.1", component="engine", module="diabetes.json", state="Diagnose Diabetes")
    ev2 = evidence("evidence.2", component="engine", module="diabetes.json", state="Diagnose Diabetes")
    verification = VerificationResult(
        id="verification.1",
        candidate_id="candidate.1",
        verifier_id="verifier.temporal",
        outcome=VerificationOutcome.PASSED,
        procedure="Replay state transition.",
        expected_result="Difference reproduced.",
        observed_result="Difference reproduced.",
        evidence_ids=(ev2.id,),
    )
    result = AttributionEngine().attribute(
        AttributionContext(
            candidate(CandidateStatus.SUPPORTED),
            assessment(ev1.id),
            (ev1, ev2),
            (verification,),
        )
    )
    assert result.attribution.confidence is CausalConfidence.VERY_HIGH


def test_conflicting_states_reduce_to_common_module() -> None:
    ev1 = evidence("evidence.1", component="engine", module="diabetes.json", state="State A")
    ev2 = evidence("evidence.2", component="engine", module="diabetes.json", state="State B")
    result = AttributionEngine().attribute(
        AttributionContext(candidate(), assessment(ev1.id, ev2.id), (ev1, ev2))
    )
    assert result.attribution.level is AttributionLevel.MODULE
    assert result.attribution.module == "diabetes.json"
    assert result.attribution.confidence is CausalConfidence.LOW
    assert result.diagnostics


def test_unrelated_conflicting_branches_return_unknown() -> None:
    ev1 = evidence("evidence.1", module="diabetes.json", state="State A")
    ev2 = evidence("evidence.2", exporter="fhir")
    result = AttributionEngine().attribute(
        AttributionContext(candidate(), assessment(ev1.id, ev2.id), (ev1, ev2))
    )
    assert result.attribution.level is AttributionLevel.UNKNOWN
    assert result.attribution.confidence is CausalConfidence.NONE


def test_contradictory_evidence_cannot_back_location_hint() -> None:
    ev = EvidenceReference(
        id="evidence.1",
        source_type="clinical.provenance",
        summary="Contradictory source.",
        locator="x",
        direction=EvidenceDirection.CONTRADICTS,
        related_candidate_id="candidate.1",
        metadata={"module": "diabetes.json"},
    )
    custom = type(
        "Rule",
        (),
        {
            "rule_id": "rule.custom",
            "priority": 1,
            "infer": lambda self, ctx: (
                AttributionHint(
                    level=AttributionLevel.MODULE,
                    module="diabetes.json",
                    evidence_ids=(ev.id,),
                    rationale="Bad hint.",
                    rule_id="rule.custom",
                ),
            ),
        },
    )()
    result = AttributionEngine((custom,)).attribute(
        AttributionContext(candidate(), assessment(), (ev,))
    )
    assert result.attribution.level is AttributionLevel.UNKNOWN


def test_missing_referenced_evidence_is_integrity_error() -> None:
    with pytest.raises(RootCauseIntegrityError):
        AttributionContext(candidate(), assessment("missing"), ())


def test_rule_hint_with_unknown_evidence_is_integrity_error() -> None:
    custom = type(
        "Rule",
        (),
        {
            "rule_id": "rule.custom",
            "priority": 1,
            "infer": lambda self, ctx: (
                AttributionHint(
                    level=AttributionLevel.MODULE,
                    module="diabetes.json",
                    evidence_ids=("missing",),
                    rationale="Invalid.",
                    rule_id="rule.custom",
                ),
            ),
        },
    )()
    with pytest.raises(RootCauseIntegrityError):
        AttributionEngine((custom,)).attribute(
            AttributionContext(candidate(), assessment(), ())
        )


def test_metadata_is_deeply_immutable() -> None:
    context = AttributionContext(candidate(), assessment(), (), metadata={"nested": {"a": [1]}})
    with pytest.raises(TypeError):
        context.metadata["x"] = 1
    with pytest.raises(TypeError):
        context.metadata["nested"]["a"] = (2,)
    with pytest.raises(FrozenInstanceError):
        context.candidate = candidate()


def test_conflicting_metadata_aliases_are_integrity_error() -> None:
    ev = evidence("evidence.1", module="a.json", source_module="b.json")
    with pytest.raises(RootCauseIntegrityError):
        AttributionEngine((EvidenceMetadataRule(),)).attribute(
            AttributionContext(candidate(), assessment(ev.id), (ev,))
        )