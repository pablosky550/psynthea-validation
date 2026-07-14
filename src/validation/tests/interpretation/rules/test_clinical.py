from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from validation.comparison.module_validation import ModuleValidationResult
from validation.interpretation.evidence import EvidenceBuilder, EvidenceCatalog, collect_evidence
from validation.models import ValidationCohort
from validation.interpretation.models import EvidenceAvailability, FindingStatus, Severity
from validation.interpretation.rules.base import (
    PipelineStage,
    RuleContext,
    RuleExecutionStatus,
    StageStatus,
)
from validation.interpretation.rules.clinical import (
    ClinicalCodeOverlapRule,
    ClinicalSignalPreservationRule,
    ClinicalThresholds,
    DomainEventRetentionRule,
)


def _context(catalog: EvidenceCatalog) -> RuleContext:
    return RuleContext(
        validation_id="validation-1",
        module_name="hypertension",
        evidence=catalog,
        evaluated_at=datetime(2026, 7, 13, tzinfo=UTC),
        stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
    )


def _clinical_signal_catalog(
    *,
    domain: str = "conditions",
    synthea_count: object = 100,
    psynthea_count: object = 95,
    reference_detected: object = True,
    candidate_detected: object = True,
    expected_terms: object = "hypertension",
    blocking_issue: object = False,
) -> EvidenceCatalog:
    builder = EvidenceBuilder()
    values = {
        "synthea_signal_count": synthea_count,
        "psynthea_signal_count": psynthea_count,
        "shared_code_count": 2,
        "synthea_only_code_count": 0,
        "psynthea_only_code_count": 0,
        "expected_signal_detected_synthea": reference_detected,
        "expected_signal_detected_psynthea": candidate_detected,
        "expected_terms": expected_terms,
        "blocking_issue": blocking_issue,
    }
    for column, value in values.items():
        builder.scalar(
            value,
            metric_id=f"hypertension.functional.clinical_signal.{domain}.{column}",
            name=f"{domain}: {column}",
            source="ModuleValidationResult.clinical_signal",
            metadata={"row_identity": domain, "column": column},
        )
    return builder.build()


def _similarity_catalog(
    *,
    domain: str = "conditions",
    synthea_total: object = 100,
    psynthea_total: object = 95,
    shared: object = 8,
    synthea_only: object = 1,
    psynthea_only: object = 1,
    jaccard: object = 0.80,
    overlap: object = 8 / 9,
    jsd: object = 0.05,
    valid: object = True,
    blocking_issue: object = False,
) -> EvidenceCatalog:
    builder = EvidenceBuilder()
    values = {
        "synthea_total": synthea_total,
        "psynthea_total": psynthea_total,
        "shared_code_count": shared,
        "synthea_only_code_count": synthea_only,
        "psynthea_only_code_count": psynthea_only,
        "jaccard_similarity": jaccard,
        "overlap_coefficient": overlap,
        "jensen_shannon_divergence": jsd,
        "valid_for_distributional_comparison": valid,
        "blocking_issue": blocking_issue,
    }
    for column, value in values.items():
        builder.scalar(
            value,
            metric_id=f"hypertension.functional.distributional_similarity.{domain}.{column}",
            name=f"{domain}: {column}",
            source="ModuleValidationResult.distributional_similarity",
            metadata={"row_identity": domain, "column": column},
        )
    return builder.build()


def test_thresholds_reject_invalid_ordering() -> None:
    with pytest.raises(ValueError, match="failure_event_retention"):
        ClinicalThresholds(
            failure_event_retention=0.9,
            warning_event_retention=0.8,
        )
    with pytest.raises(ValueError, match="maximum_warning_js_divergence"):
        ClinicalThresholds(
            maximum_warning_js_divergence=0.3,
            maximum_failure_js_divergence=0.2,
        )


def test_signal_rule_passes_when_expected_signal_is_preserved() -> None:
    result = ClinicalSignalPreservationRule().run(_context(_clinical_signal_catalog()))
    assert result.status is RuleExecutionStatus.COMPLETED
    assert result.findings[0].status is FindingStatus.PASS
    assert result.findings[0].blocks_research_use is False


def test_signal_rule_fails_when_reference_signal_is_missing_in_psynthea() -> None:
    result = ClinicalSignalPreservationRule().run(
        _context(
            _clinical_signal_catalog(
                psynthea_count=0,
                candidate_detected=False,
                blocking_issue=True,
            )
        )
    )
    finding = result.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.severity is Severity.CRITICAL
    assert finding.blocks_research_use is True
    assert finding.recommendations[0].blocking is True


def test_signal_rule_is_inconclusive_when_reference_does_not_show_expected_signal() -> None:
    result = ClinicalSignalPreservationRule().run(
        _context(
            _clinical_signal_catalog(
                synthea_count=10,
                reference_detected=False,
                candidate_detected=False,
            )
        )
    )
    assert result.findings[0].status is FindingStatus.INCONCLUSIVE
    assert result.findings[0].blocks_research_use is True


def test_signal_rule_does_not_invent_decision_without_expected_terms() -> None:
    result = ClinicalSignalPreservationRule().run(
        _context(_clinical_signal_catalog(expected_terms=None, reference_detected=None, candidate_detected=None))
    )
    assert result.findings[0].status is FindingStatus.NOT_EVALUATED
    assert result.findings[0].severity is Severity.INFO


def test_signal_rule_detects_contradictory_flags_and_counts() -> None:
    result = ClinicalSignalPreservationRule().run(
        _context(_clinical_signal_catalog(synthea_count=0, reference_detected=True))
    )
    assert result.findings[0].status is FindingStatus.INCONCLUSIVE
    assert "contradictory" in result.findings[0].title.lower()


def test_event_retention_pass_warning_and_fail() -> None:
    passing = DomainEventRetentionRule().run(
        _context(_clinical_signal_catalog(synthea_count=100, psynthea_count=90))
    )
    warning = DomainEventRetentionRule().run(
        _context(_clinical_signal_catalog(synthea_count=100, psynthea_count=60))
    )
    failing = DomainEventRetentionRule().run(
        _context(_clinical_signal_catalog(synthea_count=100, psynthea_count=20))
    )
    assert passing.findings[0].status is FindingStatus.PASS
    assert warning.findings[0].status is FindingStatus.WARNING
    assert failing.findings[0].status is FindingStatus.FAIL
    assert failing.findings[0].blocks_research_use is True


def test_event_retention_is_not_applicable_for_absent_reference_signal() -> None:
    result = DomainEventRetentionRule().run(
        _context(_clinical_signal_catalog(synthea_count=0, psynthea_count=0))
    )
    assert result.findings[0].status is FindingStatus.NOT_APPLICABLE
    assert result.findings[0].clinically_relevant is False


def test_code_overlap_pass_warning_and_fail() -> None:
    passing = ClinicalCodeOverlapRule().run(_context(_similarity_catalog()))
    warning = ClinicalCodeOverlapRule().run(
        _context(_similarity_catalog(shared=6, synthea_only=4, psynthea_only=2, jaccard=0.50, overlap=0.75, jsd=0.15))
    )
    failing = ClinicalCodeOverlapRule().run(
        _context(_similarity_catalog(shared=2, synthea_only=8, psynthea_only=3, jaccard=2 / 13, overlap=0.40, jsd=0.30))
    )
    assert passing.findings[0].status is FindingStatus.PASS
    assert warning.findings[0].status is FindingStatus.WARNING
    assert failing.findings[0].status is FindingStatus.FAIL
    assert failing.findings[0].blocks_research_use is True


def test_code_overlap_is_inconclusive_when_functional_layer_blocks_comparison() -> None:
    result = ClinicalCodeOverlapRule().run(
        _context(_similarity_catalog(valid=False, blocking_issue=True))
    )
    assert result.findings[0].status is FindingStatus.INCONCLUSIVE
    assert result.findings[0].blocks_research_use is True


def test_code_overlap_rejects_out_of_range_metrics() -> None:
    result = ClinicalCodeOverlapRule().run(
        _context(_similarity_catalog(jaccard=1.2))
    )
    assert result.findings[0].status is FindingStatus.INCONCLUSIVE


def test_rules_are_not_evaluated_when_required_pipeline_stage_was_not_run() -> None:
    context = RuleContext(
        validation_id="validation-1",
        module_name="hypertension",
        evidence=_clinical_signal_catalog(),
        evaluated_at=datetime(2026, 7, 13, tzinfo=UTC),
        stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.NOT_RUN},
    )
    result = ClinicalSignalPreservationRule().run(context)
    assert result.status is RuleExecutionStatus.NOT_EVALUATED
    assert not result.findings


def test_rules_are_not_evaluated_without_matching_evidence() -> None:
    context = _context(EvidenceCatalog())
    signal = ClinicalSignalPreservationRule().run(context)
    overlap = ClinicalCodeOverlapRule().run(context)
    assert signal.status is RuleExecutionStatus.NOT_EVALUATED
    assert overlap.status is RuleExecutionStatus.NOT_EVALUATED


def test_real_module_validation_result_integrates_through_evidence_registry() -> None:
    table_status = pd.DataFrame(
        [
            {
                "module_name": "hypertension",
                "table": "conditions",
                "synthea_available": True,
                "psynthea_available": True,
                "synthea_rows": 100,
                "psynthea_rows": 95,
                "synthea_empty": False,
                "psynthea_empty": False,
                "row_difference": -5,
                "relative_row_difference": -0.05,
                "required": True,
                "blocking_issue": False,
            }
        ]
    )
    clinical_signal = pd.DataFrame(
        [
            {
                "module_name": "hypertension",
                "domain": "conditions",
                "synthea_signal_count": 100,
                "psynthea_signal_count": 95,
                "shared_code_count": 8,
                "synthea_only_code_count": 1,
                "psynthea_only_code_count": 1,
                "expected_signal_detected_synthea": True,
                "expected_signal_detected_psynthea": True,
                "expected_terms": "hypertension",
                "blocking_issue": False,
            }
        ]
    )
    similarity = pd.DataFrame(
        [
            {
                "module_name": "hypertension",
                "domain": "conditions",
                "synthea_total": 100,
                "psynthea_total": 95,
                "shared_code_count": 8,
                "synthea_only_code_count": 1,
                "psynthea_only_code_count": 1,
                "jaccard_similarity": 0.8,
                "overlap_coefficient": 8 / 9,
                "jensen_shannon_divergence": 0.05,
                "valid_for_distributional_comparison": True,
                "blocking_issue": False,
            }
        ]
    )
    result = ModuleValidationResult(
        module_name="hypertension",
        synthea_cohort=ValidationCohort(source="synthea"),
        psynthea_cohort=ValidationCohort(source="psynthea"),
        table_status=table_status,
        clinical_signal=clinical_signal,
        distributional_similarity=similarity,
        issues=pd.DataFrame(columns=["module_name", "severity", "domain", "issue", "details"]),
        summary=pd.DataFrame(
            [
                {
                    "module_name": "hypertension",
                    "status": "comparable",
                    "status_reason": "ok",
                    "synthea_functional": True,
                    "psynthea_functional": True,
                    "valid_for_comparison": True,
                    "blocking_issue_count": 0,
                    "warning_count": 0,
                    "synthea_condition_count": 100,
                    "psynthea_condition_count": 95,
                    "synthea_observation_count": 0,
                    "psynthea_observation_count": 0,
                    "mean_distributional_similarity": 0.8,
                    "mean_jensen_shannon_divergence": 0.05,
                }
            ]
        ),
    )
    catalog = collect_evidence(result)
    context = _context(catalog)

    signal_evaluation = ClinicalSignalPreservationRule().run(context)
    retention_evaluation = DomainEventRetentionRule().run(context)
    overlap_evaluation = ClinicalCodeOverlapRule().run(context)

    assert signal_evaluation.findings[0].status is FindingStatus.PASS
    assert retention_evaluation.findings[0].status is FindingStatus.PASS
    assert overlap_evaluation.findings[0].status is FindingStatus.PASS


def test_missing_metric_availability_stays_inconclusive_not_zero() -> None:
    builder = EvidenceBuilder()
    for column, value in {
        "synthea_signal_count": 100,
        "psynthea_signal_count": None,
        "shared_code_count": 1,
        "synthea_only_code_count": 0,
        "psynthea_only_code_count": 0,
        "expected_signal_detected_synthea": True,
        "expected_signal_detected_psynthea": True,
        "expected_terms": "hypertension",
        "blocking_issue": False,
    }.items():
        kwargs = {}
        if value is None:
            kwargs["availability"] = EvidenceAvailability.NOT_COMPUTED
        builder.scalar(
            value,
            metric_id=f"hypertension.functional.clinical_signal.conditions.{column}",
            name=column,
            metadata={"row_identity": "conditions", "column": column},
            **kwargs,
        )
    evaluation = DomainEventRetentionRule().run(_context(builder.build()))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_event_retention_detects_material_overproduction() -> None:
    warning = DomainEventRetentionRule().run(
        _context(_clinical_signal_catalog(synthea_count=100, psynthea_count=140))
    )
    failing = DomainEventRetentionRule().run(
        _context(_clinical_signal_catalog(synthea_count=100, psynthea_count=250))
    )
    assert warning.findings[0].status is FindingStatus.WARNING
    assert failing.findings[0].status is FindingStatus.FAIL
    assert failing.findings[0].blocks_research_use is True


def test_code_overlap_rejects_metrics_inconsistent_with_code_counts() -> None:
    result = ClinicalCodeOverlapRule().run(
        _context(_similarity_catalog(shared=8, synthea_only=1, psynthea_only=1, jaccard=0.95))
    )
    finding = result.findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE
    assert "internally inconsistent" in finding.title.lower()
    assert finding.blocks_research_use is True


def test_code_overlap_rejects_unique_code_counts_exceeding_event_totals() -> None:
    result = ClinicalCodeOverlapRule().run(
        _context(
            _similarity_catalog(
                synthea_total=5,
                psynthea_total=5,
                shared=8,
                synthea_only=1,
                psynthea_only=1,
                jaccard=0.8,
                overlap=8 / 9,
            )
        )
    )
    assert result.findings[0].status is FindingStatus.INCONCLUSIVE