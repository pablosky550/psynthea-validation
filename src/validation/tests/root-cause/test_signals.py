from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from validation.interpretation.models import FindingStatus
from validation.knowledge.taxonomy import ValidationDomain
from validation.root_cause.exceptions import RootCauseInputError, RootCauseIntegrityError
from validation.root_cause.models import (
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
)
from validation.root_cause.signals import (
    SignalExtractionContext,
    SignalExtractor,
    SignalRule,
    extract_signals,
)


def _request(*, strict: bool = True, domains: tuple[ValidationDomain, ...] = ()) -> RootCauseRequest:
    return RootCauseRequest(
        id="request-1",
        experiment_id="experiment-1",
        run_id="run-1",
        validation_result_ids=("validation-1",),
        requested_domains=domains,
        strict_integrity=strict,
    )


def _evidence(
    evidence_id: str = "evidence-1",
    *,
    source_type: str = "validation",
    metadata: dict[str, Any] | None = None,
    direction: EvidenceDirection = EvidenceDirection.NEUTRAL,
    related_candidate_id: str | None = None,
) -> EvidenceReference:
    return EvidenceReference(
        id=evidence_id,
        source_type=source_type,
        summary="Observed prevalence difference.",
        locator=f"memory://{evidence_id}",
        direction=direction,
        related_candidate_id=related_candidate_id,
        metadata=metadata or {},
    )


def _explicit_metadata(**overrides: Any) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "domain": ValidationDomain.CONDITIONS.value,
        "classification": DifferenceClassification.PROBABILISTIC.value,
        "summary": "Lower diabetes prevalence in Psynthea.",
        "metric_id": "prevalence.diabetes",
        "synthea_value": 0.14,
        "psynthea_value": 0.09,
        "absolute_difference": -0.05,
        "statistically_significant": True,
        "clinically_relevant": True,
    }
    descriptor.update(overrides)
    return {"signal": descriptor}


def test_explicit_signal_is_typed_traceable_and_deterministic() -> None:
    request = _request()
    evidence = _evidence(metadata=_explicit_metadata())

    first = extract_signals(request, (evidence,))
    second = extract_signals(request, (evidence,))

    assert first == second
    assert len(first.signals) == 1
    signal = first.signals[0]
    assert signal.domain is ValidationDomain.CONDITIONS
    assert signal.classification is DifferenceClassification.PROBABILISTIC
    assert signal.evidence_ids == (evidence.id,)
    assert signal.absolute_difference == pytest.approx(-0.05)
    assert first.consumed_evidence_ids == (evidence.id,)
    assert first.unconsumed_evidence_ids == ()


def test_input_order_does_not_change_canonical_output() -> None:
    request = _request()
    first = _evidence("evidence-a", metadata=_explicit_metadata(metric_id="metric-a"))
    second = _evidence("evidence-b", metadata=_explicit_metadata(metric_id="metric-b"))

    left = extract_signals(request, (first, second))
    right = extract_signals(request, (second, first))

    assert left == right


def test_domain_scope_filters_signal_without_error() -> None:
    request = _request(domains=(ValidationDomain.MEDICATIONS,))
    result = extract_signals(request, (_evidence(metadata=_explicit_metadata()),))

    assert result.signals == ()
    assert result.consumed_evidence_ids == ("evidence-1",)


def test_pass_interpretation_finding_does_not_become_signal() -> None:
    evidence = _evidence(
        source_type="interpretation",
        metadata={
            "binding_kind": "interpretation_finding",
            "binding_id": "finding-1",
            "status": FindingStatus.PASS.value,
            "domain": ValidationDomain.CONDITIONS.value,
        },
    )
    result = extract_signals(_request(), (evidence,))
    assert result.signals == ()


def test_inconclusive_finding_without_explicit_discrepancy_is_not_signal() -> None:
    evidence = _evidence(
        source_type="interpretation",
        metadata={
            "binding_kind": "interpretation_finding",
            "binding_id": "finding-1",
            "status": FindingStatus.INCONCLUSIVE.value,
            "domain": ValidationDomain.VALIDATION_PIPELINE.value,
        },
    )
    result = extract_signals(_request(), (evidence,))
    assert result.signals == ()


def test_inconclusive_finding_with_explicit_pipeline_marker_is_signal() -> None:
    evidence = _evidence(
        source_type="interpretation",
        metadata={
            "binding_kind": "interpretation_finding",
            "binding_id": "finding-1",
            "status": FindingStatus.INCONCLUSIVE.value,
            "domain": ValidationDomain.VALIDATION_PIPELINE.value,
            "difference_kind": "validation_pipeline",
        },
    )
    result = extract_signals(_request(), (evidence,))
    assert result.signals[0].classification is DifferenceClassification.VALIDATION_PIPELINE


def test_validation_evidence_requires_explicit_discrepancy_marker() -> None:
    evidence = _evidence(
        metadata={
            "source_family": "validation",
            "domain": ValidationDomain.CONDITIONS.value,
            "metric_id": "prevalence.diabetes",
        }
    )
    result = extract_signals(_request(), (evidence,))
    assert result.signals == ()


def test_directional_evidence_is_rejected_at_signal_boundary() -> None:
    evidence = _evidence(
        metadata=_explicit_metadata(),
        direction=EvidenceDirection.SUPPORTS,
        related_candidate_id="candidate-1",
    )
    with pytest.raises(RootCauseIntegrityError, match="causally neutral"):
        extract_signals(_request(), (evidence,))


class _MultiEvidenceRule:
    name = "multi_evidence"
    priority = 500

    def supports(self, evidence: EvidenceReference, context: SignalExtractionContext) -> bool:
        del context
        return evidence.id == "evidence-a"

    def extract(
        self, evidence: EvidenceReference, context: SignalExtractionContext
    ) -> tuple[DiscrepancySignal, ...]:
        del context
        return (
            DiscrepancySignal(
                id="signal-multi",
                domain=ValidationDomain.CONDITIONS,
                classification=DifferenceClassification.UNKNOWN,
                summary="Joint discrepancy.",
                source_id=evidence.id,
                evidence_ids=("evidence-a", "evidence-b"),
            ),
        )


def test_multi_evidence_signal_is_order_independent_and_consumes_all_references() -> None:
    request = _request()
    a = _evidence("evidence-a")
    b = _evidence("evidence-b", source_type="external")

    left = extract_signals(request, (a, b), rules=(_MultiEvidenceRule(),))
    right = extract_signals(request, (b, a), rules=(_MultiEvidenceRule(),))

    assert left == right
    assert left.consumed_evidence_ids == ("evidence-a", "evidence-b")
    assert left.unconsumed_evidence_ids == ()


class _BrokenSupportsRule:
    name = "broken_supports"
    priority = 500

    def supports(self, evidence: EvidenceReference, context: SignalExtractionContext) -> bool:
        del evidence, context
        raise RuntimeError("plugin exploded")

    def extract(
        self, evidence: EvidenceReference, context: SignalExtractionContext
    ) -> tuple[DiscrepancySignal, ...]:
        del evidence, context
        return ()


def test_unexpected_supports_failure_is_normalized_in_strict_mode() -> None:
    with pytest.raises(RootCauseInputError, match="evaluating evidence ownership") as error:
        extract_signals(_request(), (_evidence(),), rules=(_BrokenSupportsRule(),))
    assert error.value.context["rule_name"] == "broken_supports"


def test_supports_failure_becomes_diagnostic_in_permissive_mode() -> None:
    result = extract_signals(
        _request(strict=False),
        (_evidence(),),
        rules=(_BrokenSupportsRule(),),
    )
    assert result.signals == ()
    assert result.unconsumed_evidence_ids == ("evidence-1",)
    assert result.diagnostics[0].code == "signals.rule_skipped"


class _NonBooleanSupportsRule:
    name = "non_boolean_supports"
    priority = 500

    def supports(self, evidence: EvidenceReference, context: SignalExtractionContext) -> bool:
        del evidence, context
        return 1  # type: ignore[return-value]

    def extract(
        self, evidence: EvidenceReference, context: SignalExtractionContext
    ) -> tuple[DiscrepancySignal, ...]:
        del evidence, context
        return ()


def test_supports_must_return_actual_boolean() -> None:
    with pytest.raises(RootCauseInputError, match="rejected normalized evidence"):
        extract_signals(_request(), (_evidence(),), rules=(_NonBooleanSupportsRule(),))


class _ClaimingRule:
    def __init__(self, name: str) -> None:
        self.name = name
        self.priority = 100

    def supports(self, evidence: EvidenceReference, context: SignalExtractionContext) -> bool:
        del evidence, context
        return True

    def extract(
        self, evidence: EvidenceReference, context: SignalExtractionContext
    ) -> tuple[DiscrepancySignal, ...]:
        del evidence, context
        return ()


def test_equal_priority_ownership_is_rejected() -> None:
    with pytest.raises(RootCauseIntegrityError, match="equal priority"):
        extract_signals(
            _request(),
            (_evidence(),),
            rules=(_ClaimingRule("rule-a"), _ClaimingRule("rule-b")),
        )


def test_unknown_difference_kind_fails_loudly() -> None:
    evidence = _evidence(
        metadata={
            "source_family": "validation",
            "is_discrepancy": True,
            "domain": ValidationDomain.CONDITIONS.value,
            "difference_kind": "made_up_kind",
        }
    )
    with pytest.raises(RootCauseInputError, match="unsupported explicit difference kind"):
        extract_signals(_request(), (evidence,))


def test_result_and_nested_metadata_are_immutable() -> None:
    result = extract_signals(_request(), (_evidence(metadata=_explicit_metadata()),))
    with pytest.raises(FrozenInstanceError):
        result.request_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.metadata["strict"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        result.signals[0].metadata["new"] = "value"  # type: ignore[index]


def test_context_rejects_duplicate_evidence_ids() -> None:
    duplicate = _evidence()
    with pytest.raises(ValueError, match="duplicate ids"):
        SignalExtractionContext(request=_request(), evidence=(duplicate, duplicate))