from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.orchestration.models import ArtifactKind, ArtifactReference
from validation.root_cause.models import (
    AttributionLevel,
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    CausalConfidence,
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceDirection,
    EvidenceReference,
    ReproductionPlan,
    RootCauseFinding,
    RootCauseReport,
    RootCauseRequest,
    RootCauseStatus,
    SourceAttribution,
    VerificationOutcome,
    VerificationResult,
)

NOW = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=2)
DIGEST = "a" * 64


def _artifact(identifier: str = "artifact.validation", **overrides: object) -> ArtifactReference:
    values: dict[str, object] = {
        "id": identifier,
        "kind": ArtifactKind.EVIDENCE,
        "path": Path(f"root_cause/{identifier}.json"),
        "media_type": "application/json",
        "created_at": NOW,
        "sha256": DIGEST,
        "size_bytes": 128,
        "producer": "root_cause_engine",
    }
    values.update(overrides)
    return ArtifactReference(**values)  # type: ignore[arg-type]


def _signal(**overrides: object) -> DiscrepancySignal:
    values: dict[str, object] = {
        "id": "signal.prevalence",
        "domain": ValidationDomain.CONDITIONS,
        "classification": DifferenceClassification.PROBABILISTIC,
        "summary": "Psynthea prevalence is lower than Synthea prevalence.",
        "source_id": "validation.prevalence",
        "metric_id": "metric.prevalence",
        "synthea_value": {"value": 0.31},
        "psynthea_value": {"value": 0.24},
        "absolute_difference": -0.07,
        "relative_difference": -0.225806,
        "statistically_significant": True,
        "clinically_relevant": True,
        "metadata": {"nested": {"values": [1, 2]}},
    }
    values.update(overrides)
    return DiscrepancySignal(**values)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> CausalCandidate:
    values: dict[str, object] = {
        "id": "candidate.transition",
        "category": RootCauseCategory.PROBABILISTIC_SEMANTICS,
        "statement": "Distributed transition semantics differ between engines.",
        "mechanism": "Different normalization of transition weights changes branch selection.",
        "signal_ids": ("signal.prevalence",),
        "status": CandidateStatus.SUPPORTED,
        "source_rule_id": "rule.distributed-transition",
        "expected_observations": ("Different branch frequencies are observed.",),
        "falsification_criteria": ("Branch frequencies are identical under fixed seeds.",),
    }
    values.update(overrides)
    return CausalCandidate(**values)  # type: ignore[arg-type]


def _evidence(**overrides: object) -> EvidenceReference:
    values: dict[str, object] = {
        "id": "evidence.branch-frequency",
        "source_type": "provenance_trace",
        "summary": "Fixed-seed traces select different transition branches.",
        "locator": "traces/patient-001.json",
        "direction": EvidenceDirection.SUPPORTS,
        "related_candidate_id": "candidate.transition",
        "artifact_id": "artifact.validation",
        "sha256": DIGEST,
        "observed_at": NOW,
    }
    values.update(overrides)
    return EvidenceReference(**values)  # type: ignore[arg-type]


def _assessment(**overrides: object) -> CandidateAssessment:
    values: dict[str, object] = {
        "candidate_id": "candidate.transition",
        "rank": 1,
        "total_score": 3.5,
        "evidence_support": 1.0,
        "knowledge_match": 0.5,
        "provenance_match": 1.0,
        "reproducibility": 1.0,
        "mechanism_specificity": 0.5,
        "contradictory_evidence": 0.0,
        "missing_evidence": 0.25,
        "alternative_explanations": 0.25,
        "supporting_evidence_ids": ("evidence.branch-frequency",),
        "rationale": "The candidate matches deterministic provenance evidence.",
    }
    values.update(overrides)
    return CandidateAssessment(**values)  # type: ignore[arg-type]


def _verification(**overrides: object) -> VerificationResult:
    output = _artifact("artifact.verification")
    values: dict[str, object] = {
        "id": "verification.fixed-seed",
        "candidate_id": "candidate.transition",
        "verifier_id": "verifier.transition-frequency",
        "outcome": VerificationOutcome.PASSED,
        "procedure": "Replay both engines with identical seeds and compare branch traces.",
        "expected_result": "Branch selection differs at the attributed transition.",
        "observed_result": "The same deterministic divergence was reproduced.",
        "input_artifact_ids": ("artifact.validation",),
        "output_artifacts": (output,),
        "evidence_ids": ("evidence.branch-frequency",),
        "command": ("python", "-m", "validation.verify_transition"),
        "started_at": NOW,
        "finished_at": LATER,
        "duration_seconds": 2.0,
    }
    values.update(overrides)
    return VerificationResult(**values)  # type: ignore[arg-type]


def _attribution(**overrides: object) -> SourceAttribution:
    values: dict[str, object] = {
        "level": AttributionLevel.TRANSITION,
        "component": "psynthea.ir.transitions.DistributedTransition",
        "module": "diabetes.json",
        "state": "Evaluate Diabetes Risk",
        "transition": "distributed_transition",
        "confidence": CausalConfidence.VERY_HIGH,
        "evidence_ids": ("evidence.branch-frequency",),
        "rationale": "The divergence begins at this transition under fixed seeds.",
    }
    values.update(overrides)
    return SourceAttribution(**values)  # type: ignore[arg-type]


def _plan(**overrides: object) -> ReproductionPlan:
    values: dict[str, object] = {
        "id": "reproduction.transition",
        "experiment_id": "experiment.hypertension",
        "run_id": "run.001",
        "title": "Reproduce distributed-transition divergence",
        "objective": "Reproduce the selected branch mismatch under fixed seeds.",
        "commands": (("python", "-m", "validation.verify_transition"),),
        "working_directory": Path("workspace"),
        "seeds": (42,),
        "module_paths": ("modules/diabetes.json",),
        "patient_ids": ("patient.001",),
        "required_artifact_ids": ("artifact.validation",),
        "required_hashes": {"artifact.validation": DIGEST},
        "configuration": {"population": 1, "seed": 42},
        "software_versions": {"psynthea": "0.1.0", "synthea": "3.3.0"},
        "verification_steps": ("Compare transition traces.",),
    }
    values.update(overrides)
    return ReproductionPlan(**values)  # type: ignore[arg-type]


def _finding(**overrides: object) -> RootCauseFinding:
    values: dict[str, object] = {
        "id": "finding.transition",
        "status": RootCauseStatus.CONFIRMED,
        "confidence": CausalConfidence.VERY_HIGH,
        "classification": DifferenceClassification.PROBABILISTIC,
        "domain": ValidationDomain.CONDITIONS,
        "summary": "Distributed-transition semantics cause the prevalence difference.",
        "explanation": "Fixed-seed replay reproduces the first divergence at one transition.",
        "signal_ids": ("signal.prevalence",),
        "selected_candidate_ids": ("candidate.transition",),
        "supporting_evidence_ids": ("evidence.branch-frequency",),
        "verification_result_ids": ("verification.fixed-seed",),
        "attribution": _attribution(),
        "reproduction_plan_id": "reproduction.transition",
    }
    values.update(overrides)
    return RootCauseFinding(**values)  # type: ignore[arg-type]


def _report(**overrides: object) -> RootCauseReport:
    artifacts = (_artifact("artifact.validation"), _artifact("artifact.verification"))
    values: dict[str, object] = {
        "id": "report.root-cause",
        "request_id": "request.root-cause",
        "experiment_id": "experiment.hypertension",
        "run_id": "run.001",
        "status": RootCauseStatus.CONFIRMED,
        "confidence": CausalConfidence.VERY_HIGH,
        "generated_at": NOW,
        "signals": (_signal(),),
        "evidence": (_evidence(),),
        "candidates": (_candidate(),),
        "assessments": (_assessment(),),
        "verifications": (_verification(),),
        "findings": (_finding(),),
        "reproduction_plans": (_plan(),),
        "artifacts": artifacts,
        "executive_summary": "A deterministic transition-semantics difference was confirmed.",
    }
    values.update(overrides)
    return RootCauseReport(**values)  # type: ignore[arg-type]


def test_request_normalizes_deduplicates_and_deep_freezes_metadata() -> None:
    metadata = {"nested": {"values": [1, 2]}}
    request = RootCauseRequest(
        id="request.root-cause",
        experiment_id="experiment.hypertension",
        run_id="run.001",
        validation_result_ids=("validation.prevalence", "validation.prevalence"),
        requested_domains=(ValidationDomain.CONDITIONS, ValidationDomain.CONDITIONS),
        created_at=NOW,
        metadata=metadata,
    )
    metadata["nested"]["values"].append(3)

    assert request.validation_result_ids == ("validation.prevalence",)
    assert request.requested_domains == (ValidationDomain.CONDITIONS,)
    assert request.metadata["nested"]["values"] == (1, 2)
    with pytest.raises(TypeError):
        request.metadata["new"] = True


def test_models_are_immutable() -> None:
    signal = _signal()
    with pytest.raises(FrozenInstanceError):
        signal.summary = "changed"  # type: ignore[misc]


def test_mapping_keys_must_be_strings() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        _signal(metadata={1: "invalid"})


def test_directional_evidence_requires_candidate_context() -> None:
    with pytest.raises(ValueError, match="Directional evidence requires"):
        _evidence(related_candidate_id=None)


def test_candidate_requires_traceable_generation_source() -> None:
    with pytest.raises(ValueError, match="requires source_rule_id"):
        _candidate(source_rule_id=None)


def test_candidate_assessment_enforces_documented_score_formula() -> None:
    with pytest.raises(ValueError, match="documented explainable ranking formula"):
        _assessment(total_score=99.0)


def test_verification_lifecycle_invariants_are_strict() -> None:
    with pytest.raises(ValueError, match="requires error_message"):
        _verification(outcome=VerificationOutcome.ERROR, error_message=None)
    with pytest.raises(ValueError, match="not-run verification"):
        _verification(outcome=VerificationOutcome.NOT_RUN, observed_result="unexpected")
    with pytest.raises(ValueError, match="finished_at cannot precede"):
        _verification(started_at=LATER, finished_at=NOW)


def test_unknown_attribution_cannot_claim_location_or_confidence() -> None:
    with pytest.raises(ValueError, match="Unknown attribution cannot contain"):
        SourceAttribution(level=AttributionLevel.UNKNOWN, module="diabetes.json")
    with pytest.raises(ValueError, match="requires confidence NONE"):
        SourceAttribution(
            level=AttributionLevel.UNKNOWN,
            confidence=CausalConfidence.LOW,
        )


def test_confirmed_finding_requires_selection_evidence_verification_and_attribution() -> None:
    with pytest.raises(ValueError, match="exactly one selected candidate"):
        _finding(selected_candidate_ids=())
    with pytest.raises(ValueError, match="supporting evidence"):
        _finding(supporting_evidence_ids=())
    with pytest.raises(ValueError, match="positive verification"):
        _finding(verification_result_ids=())


def test_confirmed_report_validates_complete_reference_graph() -> None:
    report = _report()

    assert report.status is RootCauseStatus.CONFIRMED
    assert report.findings[0].selected_candidate_ids == ("candidate.transition",)
    assert report.verifications[0].output_artifacts[0].id == "artifact.verification"


def test_report_rejects_non_contiguous_ranks() -> None:
    with pytest.raises(ValueError, match="contiguous one-based"):
        _report(assessments=(_assessment(rank=2),))


def test_report_requires_verification_output_artifacts_to_be_registered() -> None:
    with pytest.raises(ValueError, match="output_artifacts references unknown ids"):
        _report(artifacts=(_artifact("artifact.validation"),))


def test_confirmed_report_requires_supported_selected_candidate() -> None:
    with pytest.raises(ValueError, match="only SUPPORTED candidates"):
        _report(candidates=(_candidate(status=CandidateStatus.PRIORITIZED),))


def test_confirmed_verification_must_target_selected_candidate() -> None:
    alternative = _candidate(
        id="candidate.alternative",
        status=CandidateStatus.SUPPORTED,
        source_rule_id="rule.alternative",
    )
    verification = _verification(candidate_id="candidate.alternative")
    with pytest.raises(ValueError, match="for its selected candidate"):
        _report(candidates=(_candidate(), alternative), verifications=(verification,))


def test_reproduction_plan_must_match_report_execution_identity() -> None:
    with pytest.raises(ValueError, match="must match report experiment_id and run_id"):
        _report(reproduction_plans=(_plan(run_id="run.other"),))