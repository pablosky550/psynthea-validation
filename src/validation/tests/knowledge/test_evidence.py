from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from validation.knowledge.evidence import (
    DuplicateEvidenceError,
    EvidenceCollection,
    EvidenceCollector,
    EvidenceProtocolMismatchError,
    EvidenceRequirementMismatchError,
    MissingRequiredEvidenceError,
    attach_evidence,
    audit_protocol_evidence,
    canonical_json_bytes,
)
from validation.knowledge.models import (
    DetectionSignal,
    EvidenceItem,
    EvidenceSourceKind,
    InvestigationCase,
    InvestigationStatus,
)
from validation.knowledge.protocols import MISSING_OR_EMPTY_OUTPUT_PROTOCOL

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
PROTOCOL = MISSING_OR_EMPTY_OUTPUT_PROTOCOL
STEP = PROTOCOL.steps[0]
REQ = STEP.evidence_requirements[0]


def _collector(*, step=STEP) -> EvidenceCollector:
    return EvidenceCollector(protocol=PROTOCOL, step=step, clock=lambda: NOW)


def _case() -> InvestigationCase:
    return InvestigationCase(
        id="case.1",
        title="Missing observations",
        status=InvestigationStatus.OPEN,
        signals=(
            DetectionSignal(
                id="signal.1",
                domain="domain.observations",
                summary="Observation output is empty.",
                metric_id="observations.row_count",
            ),
        ),
        opened_at=NOW,
        updated_at=NOW,
    )


def test_canonical_json_bytes_are_order_independent_and_stable() -> None:
    left = canonical_json_bytes({"b": 2, "a": {3, 1}})
    right = canonical_json_bytes({"a": {1, 3}, "b": 2})
    assert left == right == b'{"a":[1,3],"b":2}'


def test_canonical_json_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json_bytes({"value": float("nan")})


def test_from_structure_has_reproducible_digest_and_protocol_provenance() -> None:
    item = _collector().from_structure(
        id="evidence.manifest",
        source_kind=REQ.source_kind,
        summary="Pinned run manifest",
        locator="memory://manifest",
        value={"seed": 42, "population": 100},
        requirement_ids=(REQ.id,),
    )
    payload = canonical_json_bytes({"seed": 42, "population": 100})
    assert item.sha256 == sha256(payload).hexdigest()
    assert item.collected_at == NOW
    assert item.metadata["protocol_id"] == PROTOCOL.id
    assert item.metadata["protocol_version"] == PROTOCOL.version
    assert item.metadata["protocol_step_id"] == STEP.id
    assert item.metadata["protocol_requirement_ids"] == (REQ.id,)


def test_observation_does_not_claim_byte_integrity() -> None:
    item = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.review",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="Clinical review",
        locator="meeting://review-1",
    )
    assert item.sha256 is None


def test_from_file_hashes_exact_bytes(tmp_path: Path) -> None:
    path = tmp_path / "artifact.csv"
    path.write_bytes(b"a,b\n1,2\n")
    item = EvidenceCollector(clock=lambda: NOW).from_file(
        id="evidence.file",
        source_kind=EvidenceSourceKind.RAW_DATA,
        summary="Raw artifact",
        path=path,
    )
    assert item.sha256 == sha256(path.read_bytes()).hexdigest()
    assert item.metadata["file_size_bytes"] == path.stat().st_size
    assert item.locator == str(path.resolve())


def test_reserved_metadata_cannot_be_forged() -> None:
    with pytest.raises(ValueError, match="reserved key"):
        _collector().from_text(
            id="evidence.conflict",
            source_kind=REQ.source_kind,
            summary="Conflict",
            locator="memory://conflict",
            text="x",
            requirement_ids=(REQ.id,),
            metadata={"protocol_id": "protocol.other"},
        )


def test_requirement_claim_requires_protocol_context() -> None:
    with pytest.raises(EvidenceRequirementMismatchError, match="require"):
        EvidenceCollector(clock=lambda: NOW).observation(
            id="evidence.no-protocol",
            source_kind=REQ.source_kind,
            summary="No protocol",
            locator="memory://x",
            requirement_ids=(REQ.id,),
        )


def test_collector_rejects_requirement_from_another_step() -> None:
    other_requirement = PROTOCOL.steps[1].evidence_requirements[0]
    with pytest.raises(EvidenceRequirementMismatchError, match="another step"):
        _collector().observation(
            id="evidence.wrong-step",
            source_kind=other_requirement.source_kind,
            summary="Wrong step",
            locator="memory://wrong-step",
            requirement_ids=(other_requirement.id,),
        )


def test_collection_is_deterministic_and_exact_duplicate_is_idempotent() -> None:
    first = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.b",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="B",
        locator="memory://b",
    )
    second = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.a",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="A",
        locator="memory://a",
    )
    collection = EvidenceCollection((first, second, first))
    assert [item.id for item in collection] == ["evidence.a", "evidence.b"]


def test_collection_rejects_same_id_for_distinct_observations() -> None:
    first = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.same",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="First",
        locator="memory://first",
    )
    second = replace(first, summary="Second")
    with pytest.raises(DuplicateEvidenceError, match="different observations"):
        EvidenceCollection((first, second))


def test_audit_requires_explicit_requirement_claim() -> None:
    item = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.unclaimed",
        source_kind=REQ.source_kind,
        summary="Correct source kind but unclaimed",
        locator="memory://unclaimed",
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    assert item in audit.unclaimed_evidence
    assert not audit.requirement(REQ.id).satisfied


def test_audit_accepts_matching_protocol_step_requirement_and_source_kind() -> None:
    item = _collector().observation(
        id="evidence.accepted",
        source_kind=REQ.source_kind,
        summary="Accepted",
        locator="memory://accepted",
        requirement_ids=(REQ.id,),
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    coverage = audit.requirement(REQ.id)
    assert coverage.satisfied
    assert coverage.evidence == (item,)
    assert not coverage.rejected_evidence_ids


def test_audit_rejects_wrong_source_kind() -> None:
    item = _collector().observation(
        id="evidence.wrong-kind",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="Wrong kind",
        locator="memory://wrong-kind",
        requirement_ids=(REQ.id,),
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    assert not audit.requirement(REQ.id).satisfied
    assert item.id in audit.invalid_claims


def test_audit_rejects_evidence_from_another_protocol_even_with_same_requirement_id() -> None:
    item = EvidenceItem(
        id="evidence.foreign",
        source_kind=REQ.source_kind,
        summary="Foreign protocol evidence",
        locator="memory://foreign",
        collected_at=NOW,
        metadata={
            "protocol_id": "protocol.other",
            "protocol_version": PROTOCOL.version,
            "protocol_step_id": STEP.id,
            "protocol_requirement_ids": (REQ.id,),
        },
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    assert not audit.requirement(REQ.id).satisfied
    assert "protocol_id='protocol.other'" in audit.invalid_claims[item.id]


def test_audit_rejects_wrong_protocol_version() -> None:
    item = EvidenceItem(
        id="evidence.old-version",
        source_kind=REQ.source_kind,
        summary="Old protocol evidence",
        locator="memory://old",
        collected_at=NOW,
        metadata={
            "protocol_id": PROTOCOL.id,
            "protocol_version": "0.9.0",
            "protocol_step_id": STEP.id,
            "protocol_requirement_ids": (REQ.id,),
        },
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    assert not audit.requirement(REQ.id).satisfied
    assert "protocol_version='0.9.0'" in audit.invalid_claims[item.id]


def test_audit_rejects_unknown_requirement_claim() -> None:
    item = EvidenceItem(
        id="evidence.unknown",
        source_kind=REQ.source_kind,
        summary="Unknown requirement",
        locator="memory://unknown",
        collected_at=NOW,
        metadata={"protocol_requirement_ids": ("requirement.unknown",)},
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    assert "unknown requirement 'requirement.unknown'" in audit.invalid_claims[item.id]


def test_require_complete_reports_missing_and_invalid_evidence() -> None:
    item = EvidenceItem(
        id="evidence.invalid",
        source_kind=REQ.source_kind,
        summary="Invalid",
        locator="memory://invalid",
        collected_at=NOW,
        metadata={"protocol_requirement_ids": ("requirement.unknown",)},
    )
    audit = audit_protocol_evidence(PROTOCOL, (item,))
    with pytest.raises(MissingRequiredEvidenceError, match="missing required evidence"):
        audit.require_complete()


def test_attach_evidence_returns_new_case_without_interpreting_it() -> None:
    case = _case()
    item = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.attach",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="Attached",
        locator="memory://attach",
    )
    updated = attach_evidence(
        case,
        item,
        updated_at=NOW + timedelta(minutes=5),
        note="Evidence collected.",
    )
    assert case.evidence == ()
    assert updated.evidence == (item,)
    assert updated.hypotheses == case.hypotheses
    assert updated.verifications == case.verifications
    assert updated.status is InvestigationStatus.OPEN
    assert updated.notes == ("Evidence collected.",)


def test_attach_evidence_is_idempotent_for_exact_duplicate() -> None:
    item = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.idempotent",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="Idempotent",
        locator="memory://idempotent",
    )
    once = attach_evidence(_case(), item, updated_at=NOW)
    twice = attach_evidence(once, item, updated_at=NOW)
    assert twice.evidence == (item,)


def test_attach_evidence_rejects_time_regression() -> None:
    item = EvidenceCollector(clock=lambda: NOW).observation(
        id="evidence.time",
        source_kind=EvidenceSourceKind.EXPERT_REVIEW,
        summary="Time",
        locator="memory://time",
    )
    with pytest.raises(ValueError, match="must not precede"):
        attach_evidence(_case(), item, updated_at=NOW - timedelta(seconds=1))