"""Tests for the Phase 2A root-cause knowledge domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from validation.knowledge.models import (
    ActionPriority,
    CausalCertainty,
    CausalHypothesis,
    DetectionSignal,
    EvidenceDirection,
    EvidenceItem,
    HypothesisEvidenceAssessment,
    EvidenceSourceKind,
    HypothesisStatus,
    InvestigationCase,
    InvestigationStatus,
    KnowledgeEntry,
    KnowledgeEntryStatus,
    RecommendedAction,
    VerificationCheck,
    VerificationStatus,
)


NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)


def _signal(**overrides) -> DetectionSignal:
    values = {
        "id": "signal.obs.zero",
        "domain": "observations",
        "summary": "Psynthea generated zero observation rows.",
        "finding_id": "OBS.COVERAGE.ZERO",
        "metric_id": "psynthea.observations.rows",
        "observed_value": 0,
        "metadata": {"cohort": {"source": "psynthea"}},
    }
    values.update(overrides)
    return DetectionSignal(**values)


def _evidence(
    evidence_id: str = "evidence.exporter.missing",
    *,
    source_kind: EvidenceSourceKind = EvidenceSourceKind.SOURCE_CODE,
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        source_kind=source_kind,
        summary="The CSV exporter does not serialize ObservationEntry values.",
        locator="src/psynthea/export/csv.py:120-180",
        collected_at=NOW,
        details="No observation writer is registered in the export dispatch table.",
    )


def _assessment(
    evidence_id: str = "evidence.exporter.missing",
    direction: EvidenceDirection = EvidenceDirection.SUPPORTS,
) -> HypothesisEvidenceAssessment:
    return HypothesisEvidenceAssessment(
        evidence_id=evidence_id,
        direction=direction,
        rationale="The inspected exporter path directly determines whether the event is serialized.",
    )


def _hypothesis(
    *,
    status: HypothesisStatus = HypothesisStatus.SUPPORTED,
    certainty: CausalCertainty = CausalCertainty.CONFIRMED,
    evidence_assessments: tuple[HypothesisEvidenceAssessment, ...] = (_assessment(),),
) -> CausalHypothesis:
    return CausalHypothesis(
        id="hypothesis.missing_observation_export",
        category_id="export.missing_entity",
        statement="Observations are generated internally but omitted by the CSV exporter.",
        rationale="The record contains observations while the exported table contains no rows.",
        status=status,
        certainty=certainty,
        evidence_assessments=evidence_assessments,
    )


def _verification(
    *,
    status: VerificationStatus = VerificationStatus.PASSED,
    evidence_ids: tuple[str, ...] = ("evidence.exporter.missing",),
) -> VerificationCheck:
    return VerificationCheck(
        id="verification.trace_observation",
        hypothesis_id="hypothesis.missing_observation_export",
        description="Trace one Observation from module execution to CSV output.",
        procedure="Generate one deterministic patient and inspect record plus CSV tables.",
        expected_result="Observation exists in HealthRecord but is absent from observations.csv.",
        status=status,
        actual_result=(
            "The observation exists in memory and is absent from the exported CSV."
            if status is not VerificationStatus.NOT_RUN
            else None
        ),
        evidence_ids=evidence_ids,
        executed_at=NOW if status is not VerificationStatus.NOT_RUN else None,
    )


def _action() -> RecommendedAction:
    return RecommendedAction(
        id="action.implement_observation_export",
        title="Implement observation CSV export",
        description="Serialize every supported ObservationEntry with provenance fields.",
        priority=ActionPriority.HIGH,
        target_component="psynthea.export.csv",
        verification_after_action="Repeat the deterministic run and confirm row-level parity.",
    )


def _resolved_case() -> InvestigationCase:
    return InvestigationCase(
        id="INV-OBS-001",
        title="Zero observations in psynthea CSV output",
        status=InvestigationStatus.RESOLVED,
        signals=(_signal(),),
        hypotheses=(_hypothesis(),),
        evidence=(_evidence(),),
        verifications=(_verification(),),
        selected_hypothesis_id="hypothesis.missing_observation_export",
        opened_at=NOW,
        updated_at=NOW + timedelta(hours=1),
        owner="IRYCIS validation team",
    )


def test_detection_signal_normalizes_and_deep_freezes_values() -> None:
    metadata = {"cohort": {"tables": ["observations"]}}
    observed = {"counts": [0]}

    signal = _signal(metadata=metadata, observed_value=observed)
    metadata["cohort"]["tables"].append("patients")
    observed["counts"].append(1)

    assert signal.observed_value["counts"] == (0,)
    assert signal.metadata["cohort"]["tables"] == ("observations",)
    with pytest.raises(TypeError):
        signal.metadata["new"] = "value"


def test_detection_signal_requires_a_metric_or_finding_reference() -> None:
    with pytest.raises(ValueError, match="requires finding_id, metric_id, or both"):
        _signal(finding_id=None, metric_id=None)


def test_identifier_boundaries_reject_raw_or_unsafe_values() -> None:
    with pytest.raises(ValueError, match="only letters"):
        _signal(id="signal with spaces")
    with pytest.raises(TypeError, match="domain must be a string"):
        _signal(domain=123)


def test_evidence_normalizes_datetime_to_utc_and_sha256_to_lowercase() -> None:
    local_time = datetime(2026, 7, 14, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    digest = "A" * 64

    evidence = EvidenceItem(
        id="evidence.log",
        source_kind=EvidenceSourceKind.EXECUTION_LOG,
        summary="The export command completed successfully.",
        locator="runs/001/export.log",
        collected_at=local_time,
        sha256=digest,
    )

    assert evidence.collected_at == NOW
    assert evidence.sha256 == digest.lower()


def test_evidence_rejects_naive_datetime_invalid_digest_and_raw_enums() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceItem(
            id="evidence.naive",
            source_kind=EvidenceSourceKind.RAW_DATA,
                summary="Raw table inspected.",
            locator="observations.csv",
            collected_at=datetime(2026, 7, 14, 10, 0),
        )
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        EvidenceItem(
            id="evidence.digest",
            source_kind=EvidenceSourceKind.RAW_DATA,
                summary="Raw table inspected.",
            locator="observations.csv",
            collected_at=NOW,
            sha256="not-a-digest",
        )
    with pytest.raises(TypeError, match="EvidenceSourceKind"):
        EvidenceItem(
            id="evidence.enum",
            source_kind="raw_data",
                summary="Raw table inspected.",
            locator="observations.csv",
            collected_at=NOW,
        )


def test_supported_hypothesis_requires_supporting_evidence() -> None:
    with pytest.raises(ValueError, match="requires supporting evidence"):
        _hypothesis(
            status=HypothesisStatus.SUPPORTED,
            certainty=CausalCertainty.PLAUSIBLE,
            evidence_assessments=(),
        )


def test_confirmed_certainty_requires_supported_status() -> None:
    with pytest.raises(ValueError, match="requires a supported hypothesis"):
        _hypothesis(
            status=HypothesisStatus.UNDER_INVESTIGATION,
            certainty=CausalCertainty.CONFIRMED,
        )


def test_same_evidence_cannot_support_and_refute_hypothesis() -> None:
    with pytest.raises(ValueError, match="at most once"):
        _hypothesis(evidence_assessments=(
            _assessment("evidence.exporter.missing", EvidenceDirection.SUPPORTS),
            _assessment("evidence.exporter.missing", EvidenceDirection.REFUTES),
        ))


def test_refuted_hypothesis_requires_refuting_evidence_and_low_certainty() -> None:
    with pytest.raises(ValueError, match="requires refuting evidence"):
        _hypothesis(
            status=HypothesisStatus.REFUTED,
            certainty=CausalCertainty.HYPOTHETICAL,
            evidence_assessments=(),
        )
    with pytest.raises(ValueError, match="cannot retain positive causal certainty"):
        _hypothesis(
            status=HypothesisStatus.REFUTED,
            certainty=CausalCertainty.PLAUSIBLE,
            evidence_assessments=(
                _assessment("evidence.refutation", EvidenceDirection.REFUTES),
            ),
        )


def test_completed_verification_requires_result_time_and_evidence() -> None:
    base = {
        "id": "verification.invalid",
        "hypothesis_id": "hypothesis.test",
        "description": "Inspect the exporter.",
        "procedure": "Read the export dispatch table.",
        "expected_result": "No observation writer is present.",
        "status": VerificationStatus.PASSED,
    }
    with pytest.raises(ValueError, match="requires actual_result"):
        VerificationCheck(**base)
    with pytest.raises(ValueError, match="requires executed_at"):
        VerificationCheck(**base, actual_result="Confirmed." )
    with pytest.raises(ValueError, match="requires evidence_ids"):
        VerificationCheck(**base, actual_result="Confirmed.", executed_at=NOW)


def test_not_run_verification_cannot_contain_results() -> None:
    with pytest.raises(ValueError, match="cannot contain execution results"):
        VerificationCheck(
            id="verification.not_run",
            hypothesis_id="hypothesis.test",
            description="Inspect exporter.",
            procedure="Read source code.",
            expected_result="Writer is absent.",
            status=VerificationStatus.NOT_RUN,
            actual_result="Already inspected.",
        )


def test_resolved_case_exposes_selected_hypothesis() -> None:
    case = _resolved_case()

    assert case.selected_hypothesis is not None
    assert case.selected_hypothesis.id == "hypothesis.missing_observation_export"
    assert case.updated_at > case.opened_at


def test_open_case_cannot_select_a_root_cause() -> None:
    with pytest.raises(ValueError, match="only valid for resolved"):
        InvestigationCase(
            id="INV-OPEN-001",
            title="Open investigation",
            status=InvestigationStatus.OPEN,
            signals=(_signal(),),
            hypotheses=(_hypothesis(),),
            evidence=(_evidence(),),
            selected_hypothesis_id="hypothesis.missing_observation_export",
            opened_at=NOW,
            updated_at=NOW,
        )


def test_resolved_case_requires_supported_verified_selected_hypothesis() -> None:
    proposed = _hypothesis(
        status=HypothesisStatus.PROPOSED,
        certainty=CausalCertainty.HYPOTHETICAL,
        evidence_assessments=(),
    )
    with pytest.raises(ValueError, match="must select a supported hypothesis"):
        InvestigationCase(
            id="INV-INVALID-001",
            title="Invalid resolution",
            status=InvestigationStatus.RESOLVED,
            signals=(_signal(),),
            hypotheses=(proposed,),
            evidence=(_evidence(),),
            selected_hypothesis_id=proposed.id,
            opened_at=NOW,
            updated_at=NOW,
        )

    with pytest.raises(ValueError, match="passed verification"):
        InvestigationCase(
            id="INV-INVALID-002",
            title="Unverified resolution",
            status=InvestigationStatus.RESOLVED,
            signals=(_signal(),),
            hypotheses=(_hypothesis(),),
            evidence=(_evidence(),),
            selected_hypothesis_id="hypothesis.missing_observation_export",
            opened_at=NOW,
            updated_at=NOW,
        )


def test_case_rejects_unknown_and_duplicate_references() -> None:
    unknown = _hypothesis(evidence_assessments=(_assessment("evidence.unknown"),))
    with pytest.raises(ValueError, match="references unknown ids"):
        InvestigationCase(
            id="INV-UNKNOWN-001",
            title="Unknown evidence reference",
            status=InvestigationStatus.IN_PROGRESS,
            signals=(_signal(),),
            hypotheses=(unknown,),
            evidence=(_evidence(),),
            opened_at=NOW,
            updated_at=NOW,
        )

    with pytest.raises(ValueError, match="duplicate id"):
        InvestigationCase(
            id="INV-DUP-001",
            title="Duplicate evidence",
            status=InvestigationStatus.IN_PROGRESS,
            signals=(_signal(),),
            evidence=(_evidence(), _evidence()),
            opened_at=NOW,
            updated_at=NOW,
        )


def test_case_rejects_invalid_temporal_order() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        InvestigationCase(
            id="INV-TIME-001",
            title="Invalid timestamps",
            status=InvestigationStatus.OPEN,
            signals=(_signal(),),
            opened_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )


def test_validated_knowledge_entry_requires_confirmed_verified_evidence() -> None:
    entry = KnowledgeEntry(
        id="KB-OBS-001",
        title="Observation rows missing because CSV export is absent",
        status=KnowledgeEntryStatus.VALIDATED,
        category_id="export.missing_entity",
        detection_pattern="The source cohort has observations and psynthea exports zero rows.",
        root_cause="The psynthea CSV exporter does not serialize ObservationEntry records.",
        causal_certainty=CausalCertainty.CONFIRMED,
        source_investigation_id="INV-OBS-001",
        source_hypothesis_id="hypothesis.missing_observation_export",
        evidence=(_evidence(),),
        verifications=(_verification(),),
        recommended_actions=(_action(),),
        applicability=("CSV exports produced by the affected exporter version",),
        limitations=("Does not apply when the module itself generates no observations.",),
        created_at=NOW,
        updated_at=NOW,
    )

    assert entry.status is KnowledgeEntryStatus.VALIDATED
    assert entry.evidence[0].source_kind is EvidenceSourceKind.SOURCE_CODE


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"causal_certainty": CausalCertainty.PROBABLE}, "confirmed causal certainty"),
        ({"evidence": ()}, "requires evidence"),
        ({"verifications": ()}, "passed verification"),
        ({"recommended_actions": ()}, "recommended action"),
    ],
)
def test_invalid_validated_knowledge_entries_are_rejected(overrides, message) -> None:
    values = {
        "id": "KB-OBS-001",
        "title": "Observation export defect",
        "status": KnowledgeEntryStatus.VALIDATED,
        "category_id": "export.missing_entity",
        "detection_pattern": "Psynthea observation rows are zero while internal events exist.",
        "root_cause": "ObservationEntry is not serialized by the CSV exporter.",
        "causal_certainty": CausalCertainty.CONFIRMED,
        "source_investigation_id": "INV-OBS-001",
        "source_hypothesis_id": "hypothesis.missing_observation_export",
        "evidence": (_evidence(),),
        "verifications": (_verification(),),
        "recommended_actions": (_action(),),
        "applicability": ("Affected exporter version",),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        KnowledgeEntry(**values)


def test_draft_entry_cannot_claim_confirmed_causality() -> None:
    with pytest.raises(ValueError, match="reserved for validated"):
        KnowledgeEntry(
            id="KB-DRAFT-001",
            title="Unconfirmed observation export explanation",
            status=KnowledgeEntryStatus.DRAFT,
            category_id="export.missing_entity",
            detection_pattern="Observation table is empty.",
            root_cause="The exporter may omit observations.",
            causal_certainty=CausalCertainty.CONFIRMED,
            source_investigation_id="INV-OBS-001",
            source_hypothesis_id="hypothesis.missing_observation_export",
            evidence=(_evidence(),),
            verifications=(_verification(),),
            recommended_actions=(_action(),),
            applicability=("Pending verification",),
            created_at=NOW,
            updated_at=NOW,
        )


def test_models_are_frozen_and_collections_are_detached() -> None:
    notes = ["Initial audit completed."]
    case = InvestigationCase(
        id="INV-FROZEN-001",
        title="Frozen model test",
        status=InvestigationStatus.OPEN,
        signals=(_signal(),),
        opened_at=NOW,
        updated_at=NOW,
        notes=notes,
    )
    notes.append("External mutation")

    assert case.notes == ("Initial audit completed.",)
    with pytest.raises(FrozenInstanceError):
        case.title = "Changed"


def test_duplicate_text_values_are_normalized_without_reordering() -> None:
    hypothesis = CausalHypothesis(
        id="hypothesis.normalization",
        category_id="data.mapping",
        statement="Codes may be mapped differently.",
        rationale="Descriptions match while codes differ.",
        limitations=("Needs terminology review", "Needs terminology review", "Version-specific"),
    )

    assert hypothesis.limitations == ("Needs terminology review", "Version-specific")


def test_evidence_direction_is_hypothesis_specific() -> None:
    evidence = _evidence("evidence.shared")
    supports = CausalHypothesis(
        id="hypothesis.supports",
        category_id="export",
        statement="The exporter omits observations.",
        rationale="The export path lacks an observation writer.",
        status=HypothesisStatus.SUPPORTED,
        certainty=CausalCertainty.PROBABLE,
        evidence_assessments=(
            HypothesisEvidenceAssessment(
                evidence_id=evidence.id,
                direction=EvidenceDirection.SUPPORTS,
                rationale="Absence of a writer supports an export omission.",
            ),
        ),
    )
    refutes = CausalHypothesis(
        id="hypothesis.refutes",
        category_id="engine",
        statement="The engine never generates observations.",
        rationale="No event would be available to export.",
        status=HypothesisStatus.REFUTED,
        certainty=CausalCertainty.HYPOTHETICAL,
        evidence_assessments=(
            HypothesisEvidenceAssessment(
                evidence_id=evidence.id,
                direction=EvidenceDirection.REFUTES,
                rationale="The inspected path proves generation and isolates export.",
            ),
        ),
    )

    assert supports.supporting_evidence_ids == (evidence.id,)
    assert refutes.refuting_evidence_ids == (evidence.id,)


def test_knowledge_entry_verifications_must_reference_published_hypothesis() -> None:
    mismatched = VerificationCheck(
        id="verification.other",
        hypothesis_id="hypothesis.other",
        description="Check another hypothesis.",
        procedure="Execute a deterministic trace.",
        expected_result="The alternative hypothesis is supported.",
        status=VerificationStatus.PASSED,
        actual_result="The check completed.",
        evidence_ids=("evidence.exporter.missing",),
        executed_at=NOW,
    )
    with pytest.raises(ValueError, match="source_hypothesis_id"):
        KnowledgeEntry(
            id="KB-MISMATCH-001",
            title="Mismatched verification provenance",
            status=KnowledgeEntryStatus.VALIDATED,
            category_id="export.missing_entity",
            detection_pattern="Observations exist internally but not in CSV.",
            root_cause="The observation writer is missing.",
            causal_certainty=CausalCertainty.CONFIRMED,
            source_investigation_id="INV-OBS-001",
            source_hypothesis_id="hypothesis.missing_observation_export",
            evidence=(_evidence(),),
            verifications=(mismatched,),
            recommended_actions=(_action(),),
            applicability=("Affected exporter version",),
            created_at=NOW,
            updated_at=NOW,
        )
