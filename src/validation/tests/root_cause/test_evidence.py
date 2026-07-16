from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from validation.orchestration.models import ArtifactKind, ArtifactReference
from validation.root_cause.evidence import (
    CollectionSeverity,
    EvidenceCollectionContext,
    EvidenceCollector,
    EvidenceRegistry,
    MappingEvidenceAdapter,
    collect_evidence,
)
from validation.root_cause.exceptions import (
    EvidenceCollectionError,
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import RootCauseRequest

NOW = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
SHA = "a" * 64


def request(**overrides: object) -> RootCauseRequest:
    values: dict[str, object] = {
        "id": "rc-request-1",
        "experiment_id": "experiment-1",
        "run_id": "run-1",
        "validation_result_ids": ("validation-1",),
        "created_at": NOW,
    }
    values.update(overrides)
    return RootCauseRequest(**values)


def descriptor(
    *,
    identifier: str = "validation-1",
    summary: str = "Validation discrepancy observed.",
    artifact_id: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "id": identifier,
        "source_type": "validation",
        "summary": summary,
        "locator": f"validation.results[{identifier}]",
        "binding_kind": "validation_result",
        "binding_id": identifier,
        "metadata": {"metric": "condition_prevalence"},
    }
    if artifact_id is not None:
        value["artifact_id"] = artifact_id
        value["sha256"] = SHA
    return value


def artifact() -> ArtifactReference:
    return ArtifactReference(
        id="artifact-1",
        kind=ArtifactKind.VALIDATION_RESULT,
        path=Path("validation/result.json"),
        media_type="application/json",
        created_at=NOW,
        sha256=SHA,
        size_bytes=128,
        producer="validation_engine",
    )


def test_collects_required_binding_and_freezes_nested_metadata() -> None:
    result = collect_evidence(
        request(),
        [descriptor()],
        collected_at=NOW,
        metadata={"nested": {"values": [1, 2]}},
    )

    assert result.request_id == "rc-request-1"
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.direction.value == "neutral"
    assert evidence.metadata["binding_id"] == "validation-1"
    assert isinstance(result.metadata, MappingProxyType)
    assert result.metadata["collection_context"]["nested"]["values"] == (1, 2)
    with pytest.raises(TypeError):
        result.metadata["new"] = "value"  # type: ignore[index]


def test_requires_every_upstream_binding_declared_by_request() -> None:
    with pytest.raises(EvidenceCollectionError) as exc_info:
        collect_evidence(
            request(validation_result_ids=("validation-1", "validation-2")),
            [descriptor(identifier="validation-1")],
            collected_at=NOW,
        )

    payload = exc_info.value.as_dict()
    assert payload["code"] == "root_cause.evidence.collection"
    assert payload["context"]["missing_bindings"] == {
        "validation_result": ["validation-2"]
    }


def test_rejects_descriptor_with_partial_binding() -> None:
    source = descriptor()
    source.pop("binding_id")

    with pytest.raises(RootCauseInputError):
        collect_evidence(request(), [source], collected_at=NOW)


def test_collection_is_deterministic_independently_of_source_order() -> None:
    req = request(validation_result_ids=("validation-1", "validation-2"))
    first = descriptor(identifier="validation-1")
    second = descriptor(identifier="validation-2")

    a = collect_evidence(req, [first, second], collected_at=NOW)
    b = collect_evidence(req, [second, first], collected_at=NOW)

    assert a.evidence == b.evidence
    assert tuple(item.id for item in a.evidence) == tuple(
        sorted(item.id for item in a.evidence)
    )


def test_equal_identifier_with_conflicting_content_is_integrity_error() -> None:
    first = descriptor()
    second = descriptor(summary="Different observation.")

    with pytest.raises(RootCauseIntegrityError):
        collect_evidence(request(), [first, second], collected_at=NOW)


def test_permissive_mode_skips_unsupported_sources_but_still_requires_bindings() -> None:
    result = collect_evidence(
        request(strict_integrity=False),
        [object(), descriptor()],
        strict=False,
        collected_at=NOW,
    )

    assert result.has_warnings
    assert result.diagnostics[0].code == "evidence.unsupported_source"
    assert result.diagnostics[0].severity is CollectionSeverity.WARNING


def test_requested_artifact_must_exist_in_context() -> None:
    with pytest.raises(EvidenceCollectionError):
        collect_evidence(
            request(artifact_ids=("artifact-1",)),
            [descriptor()],
            collected_at=NOW,
        )


def test_artifact_descriptor_is_bound_to_registered_artifact() -> None:
    result = collect_evidence(
        request(artifact_ids=("artifact-1",)),
        [descriptor(artifact_id="artifact-1")],
        artifacts=(artifact(),),
        collected_at=NOW,
    )

    assert result.evidence[0].artifact_id == "artifact-1"
    assert result.evidence[0].sha256 == SHA


def test_non_boolean_integrity_verifier_result_is_rejected() -> None:
    class InvalidVerifier:
        def verify(self, artifact: ArtifactReference) -> bool:
            return "yes"  # type: ignore[return-value]

    with pytest.raises(RootCauseIntegrityError):
        collect_evidence(
            request(artifact_ids=("artifact-1",)),
            [descriptor()],
            artifacts=(artifact(),),
            artifact_verifier=InvalidVerifier(),
            collected_at=NOW,
        )


def test_manifest_identity_must_match_request() -> None:
    manifest = {
        "schema_version": 2,
        "experiment_id": "other-experiment",
        "run_id": "run-1",
        "generated_at": NOW.isoformat(),
        "producer": {"name": "orchestrator", "version": "1"},
        "config_sha256": SHA,
        "config": {},
        "result": {},
    }

    with pytest.raises(RootCauseIntegrityError):
        collect_evidence(request(), [manifest, descriptor()], collected_at=NOW)


def test_registry_rejects_equal_priority_ambiguity() -> None:
    class OtherMappingAdapter(MappingEvidenceAdapter):
        name = "other_mapping"

    registry = EvidenceRegistry((MappingEvidenceAdapter(), OtherMappingAdapter(name="other_mapping")))
    context = EvidenceCollectionContext(request=request(), collected_at=NOW)

    with pytest.raises(RootCauseIntegrityError):
        EvidenceCollector(registry).collect([descriptor()], context=context)


def test_rejects_unrequested_request_bound_object() -> None:
    with pytest.raises(RootCauseIntegrityError) as exc_info:
        collect_evidence(
            request(),
            [descriptor(), descriptor(identifier="validation-foreign")],
            collected_at=NOW,
        )

    assert exc_info.value.as_dict()["context"]["unexpected_bindings"] == {
        "validation_result": ["validation-foreign"]
    }


def test_rejects_unknown_binding_kind() -> None:
    source = descriptor()
    source["binding_kind"] = "validation_reslt"

    with pytest.raises(RootCauseInputError):
        collect_evidence(request(), [source], collected_at=NOW)


def test_artifact_hash_is_canonicalized_from_catalogue() -> None:
    source = descriptor(artifact_id="artifact-1")
    source.pop("sha256")

    result = collect_evidence(
        request(artifact_ids=("artifact-1",)),
        [source],
        artifacts=(artifact(),),
        collected_at=NOW,
    )

    assert result.evidence[0].sha256 == SHA


def test_rejects_descriptor_hash_conflicting_with_catalogued_artifact() -> None:
    source = descriptor(artifact_id="artifact-1")
    source["sha256"] = "b" * 64

    with pytest.raises(RootCauseIntegrityError):
        collect_evidence(
            request(artifact_ids=("artifact-1",)),
            [source],
            artifacts=(artifact(),),
            collected_at=NOW,
        )