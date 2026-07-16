from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.root_cause.candidates import (
    CandidateGenerationContext,
    CandidateGenerator,
    ClassificationCandidateRule,
    generate_candidates,
)
from validation.root_cause.exceptions import RootCauseInputError, RootCauseIntegrityError
from validation.root_cause.models import (
    CandidateStatus,
    CausalCandidate,
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceReference,
    RootCauseRequest,
)


def _request(*, max_candidates: int = 20, strict: bool = True) -> RootCauseRequest:
    return RootCauseRequest(
        id="request-1",
        experiment_id="experiment-1",
        run_id="run-1",
        validation_result_ids=("validation-1",),
        requested_domains=(ValidationDomain.CONDITIONS,),
        max_candidates=max_candidates,
        strict_integrity=strict,
    )


def _evidence(identifier: str = "evidence-1") -> EvidenceReference:
    return EvidenceReference(
        id=identifier,
        source_type="validation",
        summary="Observed prevalence discrepancy.",
        locator=f"memory://{identifier}",
    )


def _signal(
    identifier: str = "signal-1",
    *,
    classification: DifferenceClassification = DifferenceClassification.PROBABILISTIC,
    evidence_ids: tuple[str, ...] = ("evidence-1",),
) -> DiscrepancySignal:
    return DiscrepancySignal(
        id=identifier,
        domain=ValidationDomain.CONDITIONS,
        classification=classification,
        summary="Psynthea prevalence differs from Synthea.",
        source_id="validation-1",
        metric_id="prevalence.diabetes",
        evidence_ids=evidence_ids,
    )


def _candidate(
    identifier: str,
    *,
    alternatives: tuple[str, ...] = (),
    source_rule_id: str = "custom-rule",
) -> CausalCandidate:
    return CausalCandidate(
        id=identifier,
        category=RootCauseCategory.PROBABILISTIC_SEMANTICS,
        statement=f"Candidate {identifier}.",
        mechanism="A deterministic mechanism that can be verified.",
        signal_ids=("signal-1",),
        status=CandidateStatus.GENERATED,
        source_rule_id=source_rule_id,
        expected_observations=("A corresponding execution divergence is observed.",),
        falsification_criteria=("Controlled execution remains equivalent.",),
        prerequisite_evidence_ids=("evidence-1",),
        alternative_candidate_ids=alternatives,
    )


def test_classification_rule_generates_neutral_testable_candidates() -> None:
    result = generate_candidates(
        _request(),
        (_signal(),),
        evidence=(_evidence(),),
        protocol_catalog=None,
        rules=(ClassificationCandidateRule(),),
    )

    assert result.candidates
    assert all(candidate.status is CandidateStatus.GENERATED for candidate in result.candidates)
    assert all(candidate.expected_observations for candidate in result.candidates)
    assert all(candidate.falsification_criteria for candidate in result.candidates)
    assert result.unhandled_signal_ids == ()


def test_input_order_does_not_change_output() -> None:
    request = _request()
    first = _signal("signal-a")
    second = _signal("signal-b")
    evidence = (_evidence(),)

    left = generate_candidates(
        request,
        (first, second),
        evidence=evidence,
        protocol_catalog=None,
        rules=(ClassificationCandidateRule(),),
    )
    right = generate_candidates(
        request,
        (second, first),
        evidence=evidence,
        protocol_catalog=None,
        rules=(ClassificationCandidateRule(),),
    )

    assert left == right


def test_signal_evidence_must_be_present_even_when_catalog_is_empty() -> None:
    with pytest.raises(RootCauseIntegrityError, match="outside the candidate-generation context"):
        CandidateGenerationContext(
            request=_request(),
            signals=(_signal(),),
            evidence=(),
        )


def test_context_rejects_signal_outside_requested_domain() -> None:
    signal = DiscrepancySignal(
        id="signal-1",
        domain=ValidationDomain.MEDICATIONS,
        classification=DifferenceClassification.SEMANTIC,
        summary="Medication discrepancy.",
        source_id="validation-1",
        evidence_ids=("evidence-1",),
    )
    with pytest.raises(RootCauseInputError, match="outside requested validation domains"):
        CandidateGenerationContext(
            request=_request(),
            signals=(signal,),
            evidence=(_evidence(),),
        )


class _DuplicateRule:
    name = "duplicate-rule"
    priority = 100

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        del signal, context
        candidate = _candidate("candidate-1", source_rule_id=self.name)
        return candidate, candidate


def test_source_counts_count_unique_candidates_not_duplicate_emissions() -> None:
    result = generate_candidates(
        _request(),
        (_signal(),),
        evidence=(_evidence(),),
        protocol_catalog=None,
        rules=(_DuplicateRule(),),
    )
    assert len(result.candidates) == 1
    assert result.source_counts == {"duplicate-rule": 1}


class _AlternativeGraphRule:
    name = "alternative-graph"
    priority = 100

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        del signal, context
        return (
            _candidate("candidate-a", alternatives=("candidate-b",), source_rule_id=self.name),
            _candidate("candidate-b", alternatives=("candidate-a",), source_rule_id=self.name),
            _candidate("candidate-c", source_rule_id=self.name),
        )


def test_candidate_limit_never_orphans_alternative_relationships() -> None:
    result = generate_candidates(
        _request(max_candidates=1),
        (_signal(),),
        evidence=(_evidence(),),
        protocol_catalog=None,
        rules=(_AlternativeGraphRule(),),
    )

    assert tuple(candidate.id for candidate in result.candidates) == ("candidate-c",)
    assert result.diagnostics[0].code == "candidates.limit_applied"
    assert set(result.diagnostics[0].metadata["omitted_candidate_ids"]) == {
        "candidate-a",
        "candidate-b",
    }


class _BrokenRule:
    name = "broken-rule"
    priority = 100

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        del signal, context
        raise RuntimeError("plugin failed")


def test_permissive_mode_records_plugin_failure_without_claiming_causality() -> None:
    result = generate_candidates(
        _request(strict=False),
        (_signal(),),
        evidence=(_evidence(),),
        protocol_catalog=None,
        rules=(_BrokenRule(),),
    )

    assert result.candidates == ()
    assert result.unhandled_signal_ids == ("signal-1",)
    assert result.diagnostics[0].code == "candidates.source_skipped"


def test_strict_mode_normalizes_plugin_failure() -> None:
    from validation.root_cause.exceptions import CandidateGenerationError

    with pytest.raises(CandidateGenerationError, match="unexpected exception"):
        generate_candidates(
            _request(strict=True),
            (_signal(),),
            evidence=(_evidence(),),
            protocol_catalog=None,
            rules=(_BrokenRule(),),
        )


def test_generation_output_is_deeply_immutable() -> None:
    result = generate_candidates(
        _request(),
        (_signal(),),
        evidence=(_evidence(),),
        protocol_catalog=None,
        rules=(ClassificationCandidateRule(),),
        metadata={"nested": {"values": [1, 2]}},
    )

    with pytest.raises(FrozenInstanceError):
        result.request_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.metadata["new"] = True  # type: ignore[index]
    assert result.metadata["context_metadata"]["nested"]["values"] == (1, 2)


class _WrongSignalRule:
    name = "wrong-signal"
    priority = 100

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        del signal, context
        return (
            CausalCandidate(
                id="candidate-wrong",
                category=RootCauseCategory.UNKNOWN,
                statement="Wrong signal candidate.",
                mechanism="Broken extension contract.",
                signal_ids=("different-signal",),
                source_rule_id=self.name,
            ),
        )


def test_rule_cannot_emit_candidate_for_another_signal() -> None:
    from validation.root_cause.exceptions import CandidateGenerationError

    with pytest.raises(CandidateGenerationError) as exc_info:
        generate_candidates(
            _request(),
            (_signal(),),
            evidence=(_evidence(),),
            protocol_catalog=None,
            rules=(_WrongSignalRule(),),
        )
    assert "currently being processed" in exc_info.value.context["error"]