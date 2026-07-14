from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from validation.comparison.spanish_validation import SpanishAdaptationValidation
from validation.interpretation.evidence import EvidenceCatalog, collect_evidence, extract_scalar
from validation.interpretation.models import FindingStatus
from validation.interpretation.rules.base import (
    PipelineStage,
    RuleContext,
    RuleExecutionStatus,
    StageStatus,
)
from validation.interpretation.rules.spanish_adaptation import (
    ClinicalContextLinkageRule,
    HealthcareFlowRepresentationRule,
    PrimaryCareRepresentationRule,
    ReferralPathwayRepresentationRule,
    SpanishAdaptationEvidenceIntegrityRule,
    SpanishAdaptationThresholds,
)


def _indicator(
    domain: str,
    indicator: str,
    *,
    numerator: int,
    denominator: int,
    available: bool = True,
    fraction: float | None = None,
    evidence: str = "test evidence",
) -> dict[str, object]:
    if fraction is None and denominator > 0:
        fraction = numerator / denominator
    return {
        "domain": domain,
        "indicator": indicator,
        "value": numerator,
        "numerator": numerator,
        "denominator": denominator,
        "fraction": fraction,
        "available": available,
        "evidence": evidence,
    }


def _frame(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=(
            "domain",
            "indicator",
            "value",
            "numerator",
            "denominator",
            "fraction",
            "available",
            "evidence",
        ),
    )


def _result(
    *,
    primary_care: pd.DataFrame | None = None,
    referrals: pd.DataFrame | None = None,
    healthcare_flow: pd.DataFrame | None = None,
    clinical_context: pd.DataFrame | None = None,
) -> SpanishAdaptationValidation:
    primary_care = primary_care if primary_care is not None else _frame()
    referrals = referrals if referrals is not None else _frame()
    healthcare_flow = healthcare_flow if healthcare_flow is not None else _frame()
    clinical_context = clinical_context if clinical_context is not None else _frame()
    tables = [table for table in (primary_care, referrals, healthcare_flow, clinical_context) if not table.empty]
    summary = pd.concat(tables, ignore_index=True) if tables else _frame()
    return SpanishAdaptationValidation(
        cohort=object(),  # The evidence adapter never inspects the cohort object.
        primary_care=primary_care,
        referrals=referrals,
        healthcare_flow=healthcare_flow,
        clinical_context=clinical_context,
        summary=summary,
    )


def _context(result: SpanishAdaptationValidation, *, stage: StageStatus = StageStatus.COMPLETED) -> RuleContext:
    return RuleContext(
        validation_id="spanish-test",
        module_name="hypertension",
        evidence=collect_evidence(result),
        evaluated_at=datetime.now(UTC),
        stages={PipelineStage.SPANISH_ADAPTATION: stage},
    )


def _primary(encounters: int, encounter_total: int, patients: int, patient_total: int) -> pd.DataFrame:
    return _frame(
        _indicator(
            "primary_care",
            "primary_care_encounters",
            numerator=encounters,
            denominator=encounter_total,
        ),
        _indicator(
            "primary_care",
            "patients_with_primary_care",
            numerator=patients,
            denominator=patient_total,
        ),
    )


def _flow(patients: int, total: int, emergency: int = 0, inpatient: int = 0) -> pd.DataFrame:
    return _frame(
        _indicator("healthcare_flow", "patients_with_encounters", numerator=patients, denominator=total),
        _indicator("healthcare_flow", "emergency_encounters", numerator=emergency, denominator=max(total, emergency)),
        _indicator("healthcare_flow", "inpatient_encounters", numerator=inpatient, denominator=max(total, inpatient)),
    )


def test_thresholds_reject_invalid_ordering_and_types() -> None:
    with pytest.raises(ValueError):
        SpanishAdaptationThresholds(
            minimum_primary_care_fraction=0.4,
            warning_primary_care_fraction=0.2,
        )
    with pytest.raises(TypeError):
        SpanishAdaptationThresholds(minimum_referral_count=True)
    with pytest.raises(ValueError):
        SpanishAdaptationThresholds(fraction_tolerance=-1.0)


def test_integrity_rule_passes_coherent_summary() -> None:
    context = _context(_result(primary_care=_primary(30, 100, 40, 100)))
    evaluation = SpanishAdaptationEvidenceIntegrityRule().run(context)
    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert evaluation.findings[0].status is FindingStatus.PASS


def test_integrity_rule_blocks_inconsistent_fraction() -> None:
    table = _frame(
        _indicator(
            "primary_care",
            "primary_care_encounters",
            numerator=20,
            denominator=100,
            fraction=0.8,
        )
    )
    evaluation = SpanishAdaptationEvidenceIntegrityRule().run(_context(_result(primary_care=table)))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE
    assert evaluation.findings[0].blocks_research_use is True


def test_integrity_rule_rejects_available_zero_denominator() -> None:
    table = _frame(
        _indicator(
            "primary_care",
            "primary_care_encounters",
            numerator=0,
            denominator=0,
            available=True,
            fraction=None,
        )
    )
    finding = SpanishAdaptationEvidenceIntegrityRule().run(_context(_result(primary_care=table))).findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE


def test_primary_care_passes_when_both_coverage_targets_are_met() -> None:
    evaluation = PrimaryCareRepresentationRule().run(
        _context(_result(primary_care=_primary(25, 100, 30, 100)))
    )
    assert evaluation.findings[0].status is FindingStatus.PASS


def test_primary_care_warns_for_limited_but_nonzero_coverage() -> None:
    evaluation = PrimaryCareRepresentationRule().run(
        _context(_result(primary_care=_primary(10, 100, 10, 100)))
    )
    assert evaluation.findings[0].status is FindingStatus.WARNING
    assert evaluation.findings[0].blocks_research_use is False


def test_primary_care_fails_below_minimum_and_blocks_research_use() -> None:
    evaluation = PrimaryCareRepresentationRule().run(
        _context(_result(primary_care=_primary(1, 100, 1, 100)))
    )
    assert evaluation.findings[0].status is FindingStatus.FAIL
    assert evaluation.findings[0].blocks_research_use is True


def test_primary_care_requires_both_indicators() -> None:
    table = _frame(
        _indicator("primary_care", "primary_care_encounters", numerator=20, denominator=100)
    )
    finding = PrimaryCareRepresentationRule().run(_context(_result(primary_care=table))).findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE


def test_referral_rule_passes_when_any_evaluable_signal_exists() -> None:
    referrals = _frame(
        _indicator("referrals", "referral_like_encounters", numerator=2, denominator=100),
        _indicator("referrals", "referral_like_procedures", numerator=0, denominator=50),
    )
    finding = ReferralPathwayRepresentationRule().run(_context(_result(referrals=referrals))).findings[0]
    assert finding.status is FindingStatus.PASS


def test_referral_zero_is_warning_not_automatic_failure() -> None:
    referrals = _frame(
        _indicator("referrals", "referral_like_encounters", numerator=0, denominator=100),
        _indicator("referrals", "referral_like_procedures", numerator=0, denominator=50),
    )
    finding = ReferralPathwayRepresentationRule().run(_context(_result(referrals=referrals))).findings[0]
    assert finding.status is FindingStatus.WARNING
    assert finding.blocks_research_use is False


def test_referral_rule_is_inconclusive_when_all_sources_unavailable() -> None:
    referrals = _frame(
        _indicator(
            "referrals",
            "referral_like_encounters",
            numerator=0,
            denominator=0,
            available=False,
            fraction=None,
        ),
        _indicator(
            "referrals",
            "referral_like_procedures",
            numerator=0,
            denominator=0,
            available=False,
            fraction=None,
        ),
    )
    finding = ReferralPathwayRepresentationRule().run(_context(_result(referrals=referrals))).findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE


def test_healthcare_flow_passes_with_high_patient_coverage() -> None:
    finding = HealthcareFlowRepresentationRule().run(
        _context(_result(healthcare_flow=_flow(98, 100, emergency=5, inpatient=2)))
    ).findings[0]
    assert finding.status is FindingStatus.PASS


def test_healthcare_flow_warning_and_failure_thresholds() -> None:
    warning = HealthcareFlowRepresentationRule().run(
        _context(_result(healthcare_flow=_flow(90, 100)))
    ).findings[0]
    failure = HealthcareFlowRepresentationRule().run(
        _context(_result(healthcare_flow=_flow(50, 100)))
    ).findings[0]
    assert warning.status is FindingStatus.WARNING
    assert failure.status is FindingStatus.FAIL
    assert failure.blocks_research_use is True


def test_emergency_and_inpatient_zero_do_not_cause_failure() -> None:
    finding = HealthcareFlowRepresentationRule().run(
        _context(_result(healthcare_flow=_flow(100, 100, emergency=0, inpatient=0)))
    ).findings[0]
    assert finding.status is FindingStatus.PASS


def test_clinical_context_emits_pass_warning_and_fail_per_domain() -> None:
    context_table = _frame(
        _indicator("clinical_context", "conditions_linked_to_encounters", numerator=98, denominator=100),
        _indicator("clinical_context", "medications_linked_to_encounters", numerator=90, denominator=100),
        _indicator("clinical_context", "procedures_linked_to_encounters", numerator=50, denominator=100),
    )
    findings = ClinicalContextLinkageRule().run(
        _context(_result(clinical_context=context_table))
    ).findings
    statuses = {finding.title: finding.status for finding in findings}
    assert any(status is FindingStatus.PASS for status in statuses.values())
    assert any(status is FindingStatus.WARNING for status in statuses.values())
    assert any(status is FindingStatus.FAIL for status in statuses.values())


def test_empty_optional_clinical_domain_is_not_applicable() -> None:
    context_table = _frame(
        _indicator(
            "clinical_context",
            "observations_linked_to_encounters",
            numerator=0,
            denominator=0,
            available=False,
            fraction=None,
        )
    )
    finding = ClinicalContextLinkageRule().run(
        _context(_result(clinical_context=context_table))
    ).findings[0]
    assert finding.status is FindingStatus.NOT_APPLICABLE


def test_stage_not_run_prevents_scientific_outputs() -> None:
    context = _context(
        _result(primary_care=_primary(25, 100, 30, 100)),
        stage=StageStatus.NOT_RUN,
    )
    evaluation = PrimaryCareRepresentationRule().run(context)
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.findings == ()


def test_real_adapter_integration_exposes_all_expected_namespaces() -> None:
    result = _result(
        primary_care=_primary(25, 100, 30, 100),
        referrals=_frame(
            _indicator("referrals", "referral_like_encounters", numerator=2, denominator=100)
        ),
        healthcare_flow=_flow(98, 100),
        clinical_context=_frame(
            _indicator("clinical_context", "conditions_linked_to_encounters", numerator=99, denominator=100)
        ),
    )
    catalog = collect_evidence(result)
    metric_ids = {value.metric_id for value in catalog}
    assert any(".spanish.primary_care." in metric_id for metric_id in metric_ids)
    assert any(".spanish.referrals." in metric_id for metric_id in metric_ids)
    assert any(".spanish.healthcare_flow." in metric_id for metric_id in metric_ids)
    assert any(".spanish.clinical_context." in metric_id for metric_id in metric_ids)
    assert any(".spanish.summary." in metric_id for metric_id in metric_ids)


def test_no_rule_claims_improvement_over_synthea_without_paired_evidence() -> None:
    context = _context(_result(primary_care=_primary(25, 100, 30, 100)))
    finding = PrimaryCareRepresentationRule().run(context).findings[0]
    text = " ".join((finding.title, finding.observation, finding.interpretation, finding.impact)).lower()
    assert "improv" not in text
    assert "better" not in text


def test_corrupted_catalog_metric_is_inconclusive_not_zero() -> None:
    # Directly exercise the rule boundary with unavailable evidence rather than
    # allowing missingness to collapse into a numerical zero.
    catalog = EvidenceCatalog(
        (
            extract_scalar(
                None,
                metric_id="test.spanish.primary_care.primary_care.primary_care_encounters.fraction",
                name="fraction",
            ),
        )
    )
    context = RuleContext(
        validation_id="spanish-corrupt",
        module_name="hypertension",
        evidence=catalog,
        stages={PipelineStage.SPANISH_ADAPTATION: StageStatus.COMPLETED},
    )
    evaluation = PrimaryCareRepresentationRule().run(context)
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED


def test_primary_care_is_inconclusive_for_tiny_cohort() -> None:
    finding = PrimaryCareRepresentationRule().run(
        _context(_result(primary_care=_primary(2, 5, 2, 5)))
    ).findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE
    assert finding.blocks_research_use is False


def test_referral_single_proxy_is_warning_not_pass() -> None:
    referrals = _frame(
        _indicator("referrals", "referral_like_encounters", numerator=1, denominator=100),
        _indicator("referrals", "referral_like_procedures", numerator=0, denominator=100),
    )
    finding = ReferralPathwayRepresentationRule().run(
        _context(_result(referrals=referrals))
    ).findings[0]
    assert finding.status is FindingStatus.WARNING


def test_referral_rule_is_inconclusive_for_tiny_evaluable_source() -> None:
    referrals = _frame(
        _indicator("referrals", "referral_like_encounters", numerator=2, denominator=5),
        _indicator("referrals", "referral_like_procedures", numerator=0, denominator=5),
    )
    finding = ReferralPathwayRepresentationRule().run(
        _context(_result(referrals=referrals))
    ).findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE


def test_integrity_detects_summary_domain_mismatch() -> None:
    primary = _primary(25, 100, 30, 100)
    result = _result(primary_care=primary)
    result.summary = result.summary.copy()
    result.summary.loc[
        result.summary["indicator"] == "primary_care_encounters", "numerator"
    ] = 24
    evaluation = SpanishAdaptationEvidenceIntegrityRule().run(_context(result))
    assert any(item.status is FindingStatus.INCONCLUSIVE for item in evaluation.findings)
    assert any(item.blocks_research_use for item in evaluation.findings)


def test_healthcare_flow_does_not_collapse_invalid_context_indicator_to_zero() -> None:
    flow = _flow(98, 100, emergency=5, inpatient=2)
    flow.loc[flow["indicator"] == "emergency_encounters", "fraction"] = 0.9
    findings = HealthcareFlowRepresentationRule().run(
        _context(_result(healthcare_flow=flow))
    ).findings
    assert findings[0].status is FindingStatus.PASS
    assert any(item.status is FindingStatus.INCONCLUSIVE for item in findings[1:])


def test_clinical_context_is_inconclusive_for_tiny_domain() -> None:
    context_table = _frame(
        _indicator(
            "clinical_context",
            "conditions_linked_to_encounters",
            numerator=5,
            denominator=5,
        )
    )
    finding = ClinicalContextLinkageRule().run(
        _context(_result(clinical_context=context_table))
    ).findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE