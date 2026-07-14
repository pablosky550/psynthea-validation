from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from validation.knowledge.models import (
    ActionPriority,
    CausalCertainty,
    CausalHypothesis,
    DetectionSignal,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSourceKind,
    HypothesisEvidenceAssessment,
    HypothesisStatus,
    InvestigationCase,
    InvestigationStatus,
    KnowledgeEntryStatus,
    RecommendedAction,
    VerificationCheck,
    VerificationStatus,
)
from validation.knowledge.registry import (
    DuplicateInvestigationError,
    InvalidKnowledgePublicationError,
    KnowledgeRegistry,
    SupersessionError,
    UnknownKnowledgeEntryError,
)
from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)


def _evidence(evidence_id: str = "ev.export") -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        source_kind=EvidenceSourceKind.SOURCE_CODE,
        summary="Exporter omits observation rows.",
        locator="src/validation/exporter.py:42",
        collected_at=NOW,
        sha256="a" * 64,
    )


def _resolved_case(case_id: str = "case.obs") -> InvestigationCase:
    evidence = _evidence()
    hypothesis = CausalHypothesis(
        id="hyp.export",
        category_id=RootCauseCategory.EXPORT.value,
        statement="The exporter omits valid observation entries.",
        rationale="The internal record contains the event but the CSV does not.",
        status=HypothesisStatus.SUPPORTED,
        certainty=CausalCertainty.CONFIRMED,
        evidence_assessments=(
            HypothesisEvidenceAssessment(
                evidence_id=evidence.id,
                direction=EvidenceDirection.SUPPORTS,
                rationale="Record-to-export reconciliation isolates the exporter boundary.",
            ),
        ),
    )
    verification = VerificationCheck(
        id="check.export",
        hypothesis_id=hypothesis.id,
        description="Reconcile record and CSV.",
        procedure="Export a controlled patient and compare stable event identifiers.",
        expected_result="Every internal observation appears in the CSV.",
        status=VerificationStatus.PASSED,
        actual_result="The observation is present internally and absent from the CSV.",
        evidence_ids=(evidence.id,),
        executed_at=NOW,
    )
    return InvestigationCase(
        id=case_id,
        title="Missing observations",
        status=InvestigationStatus.RESOLVED,
        signals=(
            DetectionSignal(
                id="signal.obs",
                domain=ValidationDomain.OBSERVATIONS.value,
                summary="psynthea observations are empty.",
                finding_id="finding.obs.empty",
            ),
        ),
        hypotheses=(hypothesis,),
        evidence=(evidence,),
        verifications=(verification,),
        selected_hypothesis_id=hypothesis.id,
        opened_at=NOW,
        updated_at=NOW,
    )


def _action() -> RecommendedAction:
    return RecommendedAction(
        id="action.export",
        title="Implement observation export",
        description="Serialize ObservationEntry values into observations.csv.",
        priority=ActionPriority.HIGH,
        target_component="psynthea.export.csv",
        verification_after_action="Repeat record-to-export reconciliation.",
    )


def _publish(
    registry: KnowledgeRegistry,
    *,
    entry_id: str = "knowledge.obs.export",
    supersedes: tuple[str, ...] = (),
    published_at: datetime = NOW,
):
    return registry.publish_from_investigation(
        "case.obs",
        entry_id=entry_id,
        title="Observation export omission",
        detection_pattern="Internal observations exist but exported rows are absent.",
        root_cause="The CSV exporter does not serialize ObservationEntry records.",
        recommended_actions=(_action(),),
        applicability=("psynthea CSV exports using the affected exporter version",),
        domain_ids=(ValidationDomain.OBSERVATIONS.value,),
        supersedes=supersedes,
        published_at=published_at,
    )


def test_registers_and_resolves_investigation() -> None:
    case = _resolved_case()
    registry = KnowledgeRegistry(investigations=(case,))
    assert registry.investigation(case.id) is case
    assert registry.investigations(status=InvestigationStatus.RESOLVED) == (case,)


def test_duplicate_investigation_fails_loudly() -> None:
    case = _resolved_case()
    registry = KnowledgeRegistry(investigations=(case,))
    with pytest.raises(DuplicateInvestigationError):
        registry.register_investigation(case)


def test_publish_from_resolved_case_preserves_provenance() -> None:
    registry = KnowledgeRegistry(investigations=(_resolved_case(),))
    entry = _publish(registry)
    assert entry.status is KnowledgeEntryStatus.VALIDATED
    assert entry.causal_certainty is CausalCertainty.CONFIRMED
    assert entry.category_id == RootCauseCategory.EXPORT.value
    assert entry.source_hypothesis_id == "hyp.export"
    assert [item.id for item in entry.evidence] == ["ev.export"]
    assert [item.id for item in entry.verifications] == ["check.export"]
    assert entry.metadata["domain_ids"] == (ValidationDomain.OBSERVATIONS.value,)


def test_publication_rejects_unresolved_case() -> None:
    resolved = _resolved_case()
    open_case = InvestigationCase(
        id=resolved.id,
        title=resolved.title,
        status=InvestigationStatus.IN_PROGRESS,
        signals=resolved.signals,
        hypotheses=resolved.hypotheses,
        evidence=resolved.evidence,
        verifications=resolved.verifications,
        opened_at=resolved.opened_at,
        updated_at=resolved.updated_at,
    )
    registry = KnowledgeRegistry(investigations=(open_case,))
    with pytest.raises(InvalidKnowledgePublicationError, match="resolved"):
        _publish(registry)


def test_publication_requires_recommended_action() -> None:
    registry = KnowledgeRegistry(investigations=(_resolved_case(),))
    with pytest.raises(InvalidKnowledgePublicationError, match="recommended action"):
        registry.publish_from_investigation(
            "case.obs",
            entry_id="knowledge.invalid",
            title="Invalid",
            detection_pattern="Pattern",
            root_cause="Cause",
            recommended_actions=(),
            applicability=("Applicable",),
            domain_ids=(ValidationDomain.OBSERVATIONS.value,),
            published_at=NOW,
        )


def test_unknown_superseded_entry_is_rejected() -> None:
    registry = KnowledgeRegistry(investigations=(_resolved_case(),))
    with pytest.raises(SupersessionError, match="unknown entry"):
        _publish(registry, supersedes=("knowledge.missing",))


def test_supersession_removes_old_entry_from_active_view() -> None:
    registry = KnowledgeRegistry(investigations=(_resolved_case(),))
    old = _publish(registry)
    new = _publish(
        registry,
        entry_id="knowledge.obs.export.v2",
        supersedes=(old.id,),
        published_at=NOW + timedelta(days=1),
    )
    assert registry.knowledge_entries(active_only=True) == (new,)
    assert registry.knowledge_entries() == (old, new)


def test_deprecation_preserves_audit_trail_and_removes_entry_from_active_view() -> None:
    registry = KnowledgeRegistry(investigations=(_resolved_case(),))
    entry = _publish(registry)
    deprecated = registry.deprecate_entry(
        entry.id,
        reason="Exporter implementation changed.",
        changed_at=NOW + timedelta(days=1),
    )
    assert deprecated.status is KnowledgeEntryStatus.DEPRECATED
    assert deprecated.metadata["deprecation_reason"] == "Exporter implementation changed."
    assert registry.knowledge_entries(active_only=True) == ()


def test_replacing_investigation_cannot_invalidate_published_entry() -> None:
    case = _resolved_case()
    registry = KnowledgeRegistry(investigations=(case,))
    _publish(registry)
    incompatible = replace(
        case,
        hypotheses=(),
        verifications=(),
        selected_hypothesis_id=None,
        status=InvestigationStatus.IN_PROGRESS,
        updated_at=NOW + timedelta(hours=1),
    )
    with pytest.raises(InvalidKnowledgePublicationError, match="source hypothesis"):
        registry.replace_investigation(incompatible)


def test_snapshot_is_deterministic_and_queryable() -> None:
    registry = KnowledgeRegistry(investigations=(_resolved_case(),))
    entry = _publish(registry)
    snapshot = registry.snapshot(created_at=NOW, metadata={"run": ["phase2a"]})
    assert snapshot.investigation("case.obs").id == "case.obs"
    assert snapshot.knowledge_entry(entry.id) == entry
    assert snapshot.active_entries == (entry,)
    assert snapshot.metadata["run"] == ("phase2a",)
    with pytest.raises(TypeError):
        snapshot.metadata["run"] = ()


def test_unknown_entry_lookup_uses_domain_specific_error() -> None:
    registry = KnowledgeRegistry()
    with pytest.raises(UnknownKnowledgeEntryError):
        registry.knowledge_entry("knowledge.unknown")