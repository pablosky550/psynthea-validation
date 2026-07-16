from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from json import loads
from pathlib import Path

from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.root_cause.models import (
    CandidateAssessment,
    CausalCandidate,
    CausalConfidence,
    DifferenceClassification,
    DiscrepancySignal,
    RootCauseFinding,
    RootCauseReport,
    RootCauseStatus,
)
from validation.root_cause.report import (
    ReportConfiguration,
    build_root_cause_document,
    render_json_report,
    render_markdown_report,
    write_report_bundle,
)

NOW = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)


def _report() -> RootCauseReport:
    signal = DiscrepancySignal(
        id="signal:1",
        domain=ValidationDomain.CONDITIONS,
        classification=DifferenceClassification.SEMANTIC,
        summary="Condition prevalence differs.",
        source_id="validation:1",
    )
    candidate = CausalCandidate(
        id="candidate:1",
        category=RootCauseCategory.MODULE_DEFINITION,
        statement="The module definition differs.",
        mechanism="A state emits a different event.",
        signal_ids=(signal.id,),
        source_rule_id="rule:1",
    )
    assessment = CandidateAssessment(
        candidate_id=candidate.id,
        rank=1,
        total_score=0.0,
        rationale="Deterministic ranking.",
    )
    finding = RootCauseFinding(
        id="finding:1",
        status=RootCauseStatus.PLAUSIBLE,
        confidence=CausalConfidence.LOW,
        classification=DifferenceClassification.SEMANTIC,
        domain=ValidationDomain.CONDITIONS,
        summary="Module definition is a plausible explanation.",
        explanation="The candidate is prioritized but not verified.",
        signal_ids=(signal.id,),
        selected_candidate_ids=(candidate.id,),
        limitations=("Deterministic verification is pending.",),
    )
    return RootCauseReport(
        id="report:1",
        request_id="request:1",
        experiment_id="experiment:1",
        run_id="run:1",
        status=RootCauseStatus.PLAUSIBLE,
        confidence=CausalConfidence.LOW,
        generated_at=NOW,
        signals=(signal,),
        evidence=(),
        candidates=(candidate,),
        assessments=(assessment,),
        verifications=(),
        findings=(finding,),
        executive_summary="One plausible explanation remains unverified.",
        metadata={"z": 2, "a": 1},
    )


def test_json_is_deterministic_and_fingerprint_matches_payload() -> None:
    document = build_root_cause_document(_report(), generated_at=NOW)
    first = render_json_report(document)
    second = render_json_report(document)
    assert first == second
    payload = loads(first)
    fingerprint = payload.pop("document_fingerprint")
    import json
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert fingerprint == sha256(canonical).hexdigest()


def test_json_configuration_omits_disabled_sections() -> None:
    configuration = ReportConfiguration(
        include_candidate_details=False,
        include_evidence_details=False,
        include_verification_details=False,
        include_reproduction_details=False,
        include_artifacts=False,
        include_engine_trace=False,
        include_metadata=False,
    )
    payload = loads(render_json_report(build_root_cause_document(_report(), configuration=configuration)))
    for key in ("candidates", "assessments", "evidence", "verifications", "reproduction_plans", "artifacts", "metadata"):
        assert key not in payload


def test_markdown_respects_candidate_detail_policy() -> None:
    detailed = render_markdown_report(build_root_cause_document(_report()))
    compact = render_markdown_report(
        build_root_cause_document(
            _report(),
            configuration=ReportConfiguration(include_candidate_details=False),
        )
    )
    assert "| Candidate ID | Statement |" in detailed
    assert "| Candidate ID | Statement |" not in compact
    assert "`candidate:1`" in compact


def test_markdown_metadata_policy_is_respected() -> None:
    with_metadata = render_markdown_report(build_root_cause_document(_report()))
    without_metadata = render_markdown_report(
        build_root_cause_document(
            _report(), configuration=ReportConfiguration(include_metadata=False)
        )
    )
    assert "## Metadata" in with_metadata
    assert '"a": 1' in with_metadata
    assert "## Metadata" not in without_metadata


def test_report_bundle_hashes_match_written_files(tmp_path: Path) -> None:
    document = build_root_cause_document(_report())
    bundle = write_report_bundle(document, tmp_path, file_stem="root-cause")
    assert bundle.markdown_sha256 == sha256(bundle.markdown_path.read_bytes()).hexdigest()
    assert bundle.json_sha256 == sha256(bundle.json_path.read_bytes()).hexdigest()
    assert bundle.manifest_sha256 == sha256(bundle.manifest_path.read_bytes()).hexdigest()
    manifest = loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["document_fingerprint"] == document.document_fingerprint


def test_document_metadata_is_deeply_immutable() -> None:
    metadata = {"nested": {"items": [1, 2]}}
    document = build_root_cause_document(_report(), metadata=metadata)
    metadata["nested"]["items"].append(3)
    assert document.metadata["presentation"]["nested"]["items"] == (1, 2)