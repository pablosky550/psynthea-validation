"""Tests for deterministic scientific interpretation report rendering."""

from __future__ import annotations

from datetime import UTC, datetime
from json import loads

import pytest

from validation.interpretation.engine import EngineExecution
from validation.interpretation.models import (
    Confidence,
    EvidenceAvailability,
    EvidenceReference,
    EvidenceRole,
    EvidenceStrength,
    EvidenceValue,
    FindingStatus,
    InterpretationFinding,
    InterpretationReport,
    Recommendation,
    RecommendationPriority,
    Severity,
)
from validation.interpretation.report import (
    ReportConfiguration,
    ReportConsistencyError,
    build_interpretation_document,
    render_json_report,
    render_markdown_report,
    write_report_bundle,
)
from validation.interpretation.rules.base import (
    ApplicabilityDecision,
    RuleEvaluation,
    RuleExecutionStatus,
    ValidationDimension,
)
from validation.interpretation.summary import build_interpretation_summary

NOW = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)


def _evidence(metric_id: str = "metric.one", value: object = 1) -> EvidenceValue:
    return EvidenceValue(
        metric_id=metric_id,
        name=metric_id,
        availability=EvidenceAvailability.AVAILABLE,
        value=value,
        source="test",
    )


def _finding(
    finding_id: str,
    *,
    rule_id: str,
    status: FindingStatus,
    severity: Severity,
    blocks: bool = False,
    recommendation: bool = False,
) -> InterpretationFinding:
    recommendations = ()
    if recommendation:
        recommendations = (
            Recommendation(
                recommendation_id=f"{finding_id}.REC",
                action="Review | repair the affected output.",
                priority=RecommendationPriority.URGENT,
                rationale="The finding requires correction.",
                expected_outcome="The defect is resolved.",
                verification="Re-run validation and verify the metric.",
                blocking=blocks,
            ),
        )
    return InterpretationFinding(
        finding_id=finding_id,
        rule_id=rule_id,
        domain="clinical_domain",
        title=f"Title {finding_id}",
        status=status,
        severity=severity,
        confidence=Confidence.HIGH,
        evidence_strength=(
            EvidenceStrength.INSUFFICIENT
            if status is FindingStatus.INCONCLUSIVE
            else EvidenceStrength.STRONG
        ),
        observation="Observed value | with a table delimiter.",
        interpretation="Deterministic interpretation.",
        impact="Research impact.",
        evidence=(
            EvidenceReference(
                metric_id="metric.one",
                role=EvidenceRole.PRIMARY,
                rationale="Primary evidence.",
            ),
        ),
        recommendations=recommendations,
        limitations=("Scope limitation.",),
        blocks_research_use=blocks,
        created_at=NOW,
    )


def _evaluation(
    rule_id: str,
    dimension: ValidationDimension,
    *,
    status: RuleExecutionStatus = RuleExecutionStatus.COMPLETED,
    findings: tuple[InterpretationFinding, ...] = (),
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule_id,
        dimension=dimension,
        status=status,
        findings=findings,
        inferences=(),
        derived_evidence=(),
        requirements=(),
        dependencies=(),
        stages=(),
        applicability=(
            ApplicabilityDecision.not_evaluated("Required evidence is unavailable.")
            if status is RuleExecutionStatus.NOT_EVALUATED
            else ApplicabilityDecision.applicable()
        ),
        started_at=NOW,
        completed_at=NOW,
    )


def _execution() -> EngineExecution:
    structural = _evaluation(
        "STRUCT.ONE",
        ValidationDimension.STRUCTURAL,
        findings=(
            _finding(
                "F.PASS",
                rule_id="STRUCT.ONE",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
            ),
        ),
    )
    clinical = _evaluation(
        "CLIN.ONE",
        ValidationDimension.CLINICAL,
        findings=(
            _finding(
                "F.FAIL",
                rule_id="CLIN.ONE",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                blocks=True,
                recommendation=True,
            ),
        ),
    )
    incomplete = _evaluation(
        "STAT.MISSING",
        ValidationDimension.STATISTICAL,
        status=RuleExecutionStatus.NOT_EVALUATED,
    )
    evaluations = (structural, incomplete, clinical)
    findings = tuple(item for evaluation in evaluations for item in evaluation.findings)
    report = InterpretationReport(
        report_id="report.one",
        pipeline_run_id="run.one",
        module_name="hypertension",
        findings=findings,
        evidence=(_evidence(),),
        generated_at=NOW,
        metadata={"engine": {"registry_fingerprint": "abc123"}},
    )
    return EngineExecution(
        report=report,
        evaluations=evaluations,
        execution_order=tuple(item.rule_id for item in evaluations),
        started_at=NOW,
        completed_at=NOW,
    )


def test_configuration_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        ReportConfiguration(title=" ")
    with pytest.raises(TypeError):
        ReportConfiguration(maximum_priority_findings=True)
    with pytest.raises(ValueError):
        ReportConfiguration(maximum_evidence_items_per_finding=-1)


def test_build_document_uses_conservative_summary() -> None:
    document = build_interpretation_document(_execution())

    assert document.summary.overall_status is FindingStatus.FAIL
    assert not document.summary.research_use_ready
    assert document.research_use_statement.startswith("Not ready")
    assert [item.rule_id for item in document.incomplete_evaluations] == ["STAT.MISSING"]


def test_document_rejects_summary_from_another_run() -> None:
    execution = _execution()
    summary = build_interpretation_summary(execution)
    object.__setattr__(summary, "pipeline_run_id", "other.run")

    with pytest.raises(ReportConsistencyError):
        build_interpretation_document(execution, summary=summary)


def test_markdown_contains_required_scientific_sections() -> None:
    markdown = render_markdown_report(build_interpretation_document(_execution()))

    for section in (
        "## Executive Summary",
        "## Validation by Dimension",
        "## Priority Findings",
        "## Detailed Findings",
        "## Recommendations",
        "## Incomplete or Blocked Rules",
        "## Limitations",
        "## Audit Trail",
    ):
        assert section in markdown
    assert "NOT READY" in markdown
    assert "STAT.MISSING" in markdown


def test_markdown_escapes_table_delimiters() -> None:
    markdown = render_markdown_report(build_interpretation_document(_execution()))

    assert "Observed value | with" in markdown
    assert "Review | repair" not in markdown
    assert "Review \\| repair" in markdown


def test_json_is_valid_and_preserves_traceability() -> None:
    payload = loads(render_json_report(build_interpretation_document(_execution())))

    assert payload["schema"] == "psynthea.interpretation.report"
    assert payload["summary"]["report_id"] == "report.one"
    assert payload["findings"][1]["finding_id"] == "F.FAIL"
    assert payload["recommendations"][0]["finding_id"] == "F.FAIL"
    assert payload["audit"]["execution_order"] == [
        "STRUCT.ONE",
        "STAT.MISSING",
        "CLIN.ONE",
    ]


def test_rendering_is_deterministic() -> None:
    document = build_interpretation_document(_execution(), generated_at=NOW)

    assert render_markdown_report(document) == render_markdown_report(document)
    assert render_json_report(document) == render_json_report(document)


def test_report_policy_can_exclude_pass_findings() -> None:
    document = build_interpretation_document(
        _execution(),
        configuration=ReportConfiguration(include_pass_findings=False),
    )

    assert [item.finding_id for item in document.findings] == ["F.FAIL"]
    assert "F.PASS" not in render_markdown_report(document)


def test_priority_only_policy_does_not_change_summary() -> None:
    execution = _execution()
    document = build_interpretation_document(
        execution,
        configuration=ReportConfiguration(include_all_findings=False),
    )

    assert document.summary.finding_count == 2
    assert [item.finding_id for item in document.findings] == ["F.FAIL"]


def test_evidence_detail_limit_is_enforced() -> None:
    document = build_interpretation_document(
        _execution(),
        configuration=ReportConfiguration(maximum_evidence_items_per_finding=0),
    )
    markdown = render_markdown_report(document)

    assert "… 1 more" in markdown


def test_recommendations_are_sorted_by_priority_and_traceable() -> None:
    document = build_interpretation_document(_execution())

    finding_id, recommendation = document.recommendations[0]
    assert finding_id == "F.FAIL"
    assert recommendation.priority is RecommendationPriority.URGENT


def test_write_report_bundle_creates_synchronized_utf8_files(tmp_path) -> None:
    document = build_interpretation_document(_execution())

    markdown_path, json_path = write_report_bundle(document, tmp_path, stem="hypertension")

    assert markdown_path.name == "hypertension.md"
    assert json_path.name == "hypertension.json"
    assert markdown_path.read_text(encoding="utf-8") == render_markdown_report(document)
    assert loads(json_path.read_text(encoding="utf-8"))["summary"]["report_id"] == "report.one"


def test_write_bundle_rejects_unsafe_stem(tmp_path) -> None:
    with pytest.raises(ValueError):
        write_report_bundle(
            build_interpretation_document(_execution()),
            tmp_path,
            stem="../escape",
        )


def test_json_indent_validation() -> None:
    document = build_interpretation_document(_execution())
    with pytest.raises(TypeError):
        render_json_report(document, indent=True)
    with pytest.raises(ValueError):
        render_json_report(document, indent=-1)


def test_metadata_is_detached_from_external_mutation() -> None:
    metadata = {"nested": {"values": [1, 2]}}
    document = build_interpretation_document(_execution(), metadata=metadata)
    metadata["nested"]["values"].append(3)

    payload = document.to_dict()
    assert payload["metadata"]["nested"]["values"] == [1, 2]


def test_document_fingerprint_is_stable_and_auditable() -> None:
    document = build_interpretation_document(_execution(), generated_at=NOW)
    first = document.to_dict()
    second = document.to_dict()

    assert first["schema_version"] == "1.1.0"
    assert first["document_fingerprint"] == second["document_fingerprint"]
    assert len(first["document_fingerprint"]) == 64
    assert first["document_fingerprint"] in render_markdown_report(document)


def test_reserved_metadata_keys_cannot_be_overridden() -> None:
    for key in ("source_report_id", "pipeline_run_id", "document_fingerprint"):
        with pytest.raises(ValueError, match="reserved"):
            build_interpretation_document(_execution(), metadata={key: "spoofed"})


def test_metadata_sets_are_serialized_deterministically() -> None:
    document = build_interpretation_document(
        _execution(),
        generated_at=NOW,
        metadata={"unordered": {"beta", "alpha", "gamma"}},
    )
    payload = loads(render_json_report(document))

    assert payload["metadata"]["unordered"] == ["alpha", "beta", "gamma"]


def test_non_finite_metadata_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_interpretation_document(_execution(), metadata={"invalid": float("nan")})


def test_generated_at_cannot_precede_execution_completion() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        build_interpretation_document(
            _execution(),
            generated_at=datetime(2026, 7, 13, 9, 59, tzinfo=UTC),
        )


def test_title_is_normalized_to_one_markdown_line() -> None:
    document = build_interpretation_document(
        _execution(),
        configuration=ReportConfiguration(title="  Validation\n  Report  "),
    )

    assert document.configuration.title == "Validation Report"
    assert render_markdown_report(document).startswith("# Validation Report\n")


def test_priority_only_policy_hides_recommendations_for_hidden_findings() -> None:
    execution = _execution()
    document = build_interpretation_document(
        execution,
        configuration=ReportConfiguration(
            include_all_findings=False,
            include_pass_findings=False,
        ),
    )

    included = {item.finding_id for item in document.findings}
    assert included == {"F.FAIL"}
    assert all(finding_id in included for finding_id, _ in document.recommendations)


def test_stem_rejects_overlong_or_whitespace_names(tmp_path) -> None:
    document = build_interpretation_document(_execution())
    with pytest.raises(ValueError):
        write_report_bundle(document, tmp_path, stem="a" * 129)
    with pytest.raises(ValueError):
        write_report_bundle(document, tmp_path, stem="bad name")


def test_bundle_rolls_back_markdown_when_json_replace_fails(tmp_path, monkeypatch) -> None:
    import validation.interpretation.report as report_module

    document = build_interpretation_document(_execution())
    markdown_path = tmp_path / "hypertension.md"
    json_path = tmp_path / "hypertension.json"
    markdown_path.write_text("old markdown", encoding="utf-8")
    json_path.write_text("old json", encoding="utf-8")

    real_replace = report_module.replace
    calls = 0

    def failing_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(report_module, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated"):
        report_module.write_report_bundle(document, tmp_path, stem="hypertension")

    assert markdown_path.read_text(encoding="utf-8") == "old markdown"
    assert json_path.read_text(encoding="utf-8") == "old json"
    assert not list(tmp_path.glob("*.tmp"))