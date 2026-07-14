from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from validation.interpretation.evidence import EvidenceCatalog, collect_evidence, extract_scalar
from validation.interpretation.models import FindingStatus, Severity
from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.interpretation.rules.base import (
    PipelineStage,
    RuleContext,
    RuleExecutionStatus,
    StageStatus,
)
from validation.interpretation.rules.statistical import (
    DistributionEquivalenceRule,
    GlobalStatisticalReadinessRule,
    PrevalenceEquivalenceRule,
    StatisticalThresholds,
    TestFamilyEquivalenceRule as FamilyEquivalenceRule,
)


def _value(namespace: str, identity: str, column: str, value):
    return extract_scalar(
        value,
        metric_id=f"hypertension.{namespace}.{identity}.{column}",
        name=f"{identity}: {column}",
        metadata={"row_identity": identity, "column": column},
    )


def _context(*values):
    return RuleContext(
        validation_id="run-001",
        module_name="hypertension",
        evidence=EvidenceCatalog(tuple(values)),
        evaluated_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        stages={PipelineStage.STATISTICAL_VALIDATION: StageStatus.COMPLETED},
    )


def test_thresholds_reject_invalid_policy() -> None:
    with pytest.raises(ValueError):
        StatisticalThresholds(alpha=1.0)
    with pytest.raises(ValueError):
        StatisticalThresholds(small_effect=0.6, moderate_effect=0.5)
    with pytest.raises(ValueError):
        StatisticalThresholds(risk_ratio_lower_tolerance=1.1)


def test_global_readiness_passes_only_when_valid_and_not_skipped() -> None:
    metrics = (
        _value("statistics.summary", "hypertension", "valid_for_statistical_comparison", True),
        _value("statistics.summary", "hypertension", "skipped", False),
        _value("statistics.summary", "hypertension", "validation_status", "pass"),
        _value("statistics.summary", "hypertension", "skip_reason", None),
    )

    evaluation = GlobalStatisticalReadinessRule().run(_context(*metrics))

    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert evaluation.findings[0].status is FindingStatus.PASS
    assert evaluation.findings[0].blocks_research_use is False
    assert evaluation.inferences[0].inference_id.endswith("READY")


def test_global_readiness_blocks_skipped_comparison() -> None:
    metrics = (
        _value("statistics.summary", "hypertension", "valid_for_statistical_comparison", False),
        _value("statistics.summary", "hypertension", "skipped", True),
        _value("statistics.summary", "hypertension", "validation_status", "skipped"),
        _value("statistics.summary", "hypertension", "skip_reason", "Insufficient cohort size"),
    )

    evaluation = GlobalStatisticalReadinessRule().run(_context(*metrics))

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE
    assert finding.severity is Severity.HIGH
    assert finding.blocks_research_use
    assert finding.recommendations[0].blocking


def _continuous(*, p_value: float, effect: float, significant: bool, n: int = 500):
    identity = "age.ks"
    namespace = "statistics.continuous"
    return (
        _value(namespace, identity, "test_name", "Kolmogorov-Smirnov"),
        _value(namespace, identity, "p_value", p_value),
        _value(namespace, identity, "effect_size", effect),
        _value(namespace, identity, "significant", significant),
        _value(namespace, identity, "n_synthea", n),
        _value(namespace, identity, "n_psynthea", n),
    )


def test_significant_negligible_effect_is_warning_not_fail() -> None:
    evaluation = FamilyEquivalenceRule().run(
        _context(*_continuous(p_value=0.001, effect=0.05, significant=True))
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.WARNING
    assert finding.severity is Severity.LOW
    assert not finding.blocks_research_use
    assert "below the configured practical-relevance threshold" in finding.interpretation


def test_significant_material_effect_fails() -> None:
    evaluation = FamilyEquivalenceRule().run(
        _context(*_continuous(p_value=0.001, effect=0.65, significant=True))
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.blocks_research_use
    assert finding.recommendations[0].blocking


def test_non_significant_negligible_effect_passes() -> None:
    evaluation = FamilyEquivalenceRule().run(
        _context(*_continuous(p_value=0.40, effect=0.03, significant=False))
    )

    assert evaluation.findings[0].status is FindingStatus.PASS


def test_small_sample_is_inconclusive_even_with_favorable_statistics() -> None:
    evaluation = FamilyEquivalenceRule().run(
        _context(*_continuous(p_value=0.80, effect=0.01, significant=False, n=12))
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE
    assert finding.evidence_strength.value == "insufficient"
    assert finding.blocks_research_use


def _prevalence(
    *,
    s_prev: float,
    p_prev: float,
    absolute: float,
    relative: float,
    rr: float,
    adjusted_p: float,
    fdr: bool,
):
    namespace = "statistics.prevalence"
    identity = "conditions.59621000"
    values = {
        "synthea_prevalence": s_prev,
        "psynthea_prevalence": p_prev,
        "absolute_difference": absolute,
        "relative_difference": relative,
        "risk_ratio": rr,
        "risk_ratio_ci_lower": rr - 0.05,
        "risk_ratio_ci_upper": rr + 0.05,
        "adjusted_p_value": adjusted_p,
        "significant_after_fdr": fdr,
        "synthea_total": 1000,
        "psynthea_total": 1000,
    }
    return tuple(_value(namespace, identity, column, value) for column, value in values.items())


def test_prevalence_fdr_significant_and_material_fails() -> None:
    evaluation = PrevalenceEquivalenceRule().run(
        _context(
            *_prevalence(
                s_prev=0.20,
                p_prev=0.30,
                absolute=0.10,
                relative=0.50,
                rr=1.50,
                adjusted_p=0.001,
                fdr=True,
            )
        )
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.clinically_relevant is True
    assert finding.blocks_research_use


def test_prevalence_small_fdr_significant_difference_is_warning() -> None:
    evaluation = PrevalenceEquivalenceRule().run(
        _context(
            *_prevalence(
                s_prev=0.200,
                p_prev=0.205,
                absolute=0.005,
                relative=0.025,
                rr=1.025,
                adjusted_p=0.01,
                fdr=True,
            )
        )
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.WARNING
    assert finding.severity is Severity.LOW
    assert not finding.blocks_research_use


def _distribution(*, p_value: float, jsd: float, effect: float, significant: bool):
    namespace = "statistics.distribution"
    identity = "encounters.ks"
    values = {
        "test_name": "Kolmogorov-Smirnov",
        "p_value": p_value,
        "jensen_shannon_divergence": jsd,
        "effect_size": effect,
        "significant": significant,
        "n_synthea": 500,
        "n_psynthea": 500,
    }
    return tuple(_value(namespace, identity, column, value) for column, value in values.items())


def test_distribution_significant_but_small_is_warning() -> None:
    evaluation = DistributionEquivalenceRule().run(
        _context(*_distribution(p_value=0.001, jsd=0.02, effect=0.03, significant=True))
    )
    assert evaluation.findings[0].status is FindingStatus.WARNING
    assert not evaluation.findings[0].blocks_research_use


def test_distribution_material_and_significant_fails() -> None:
    evaluation = DistributionEquivalenceRule().run(
        _context(*_distribution(p_value=0.001, jsd=0.25, effect=0.40, significant=True))
    )
    assert evaluation.findings[0].status is FindingStatus.FAIL
    assert evaluation.findings[0].blocks_research_use


def test_distribution_non_significant_and_within_tolerance_passes() -> None:
    evaluation = DistributionEquivalenceRule().run(
        _context(*_distribution(p_value=0.50, jsd=0.03, effect=0.05, significant=False))
    )
    assert evaluation.findings[0].status is FindingStatus.PASS


def test_missing_sample_size_is_inconclusive() -> None:
    values = list(_continuous(p_value=0.40, effect=0.03, significant=False))
    values = tuple(value for value in values if value.metadata.get("column") != "n_psynthea")
    evaluation = FamilyEquivalenceRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE
    assert evaluation.findings[0].blocks_research_use


def test_inconsistent_significance_flag_is_inconclusive() -> None:
    evaluation = FamilyEquivalenceRule().run(
        _context(*_continuous(p_value=0.001, effect=0.50, significant=False))
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE
    assert "disagrees" in evaluation.findings[0].observation


def test_prevalence_rr_ci_outside_equivalence_margin_prevents_pass() -> None:
    values = list(
        _prevalence(
            s_prev=0.20,
            p_prev=0.205,
            absolute=0.005,
            relative=0.025,
            rr=1.025,
            adjusted_p=0.20,
            fdr=False,
        )
    )
    replacements = {
        "risk_ratio_ci_lower": 0.70,
        "risk_ratio_ci_upper": 1.40,
    }
    values = tuple(
        _value("statistics.prevalence", "conditions.59621000", column, replacements[column])
        if (column := value.metadata.get("column")) in replacements
        else value
        for value in values
    )
    evaluation = PrevalenceEquivalenceRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.WARNING
    assert evaluation.findings[0].clinically_relevant is True


def test_invalid_prevalence_confidence_interval_is_inconclusive() -> None:
    values = list(
        _prevalence(
            s_prev=0.20,
            p_prev=0.21,
            absolute=0.01,
            relative=0.05,
            rr=1.05,
            adjusted_p=0.20,
            fdr=False,
        )
    )
    replacements = {"risk_ratio_ci_lower": 1.20, "risk_ratio_ci_upper": 0.90}
    values = tuple(
        _value("statistics.prevalence", "conditions.59621000", column, replacements[column])
        if (column := value.metadata.get("column")) in replacements
        else value
        for value in values
    )
    evaluation = PrevalenceEquivalenceRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_distribution_inconsistent_significance_is_inconclusive() -> None:
    evaluation = DistributionEquivalenceRule().run(
        _context(*_distribution(p_value=0.001, jsd=0.20, effect=0.30, significant=False))
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_real_pipeline_result_normalizes_and_executes_end_to_end() -> None:
    continuous = pd.DataFrame([
        {
            "module_name": "hypertension",
            "metric": "age",
            "test_name": "Kolmogorov-Smirnov",
            "statistic": 0.03,
            "p_value": 0.40,
            "effect_size": 0.03,
            "significant": False,
            "n_synthea": 500,
            "n_psynthea": 500,
            "notes": "",
        }
    ])
    categorical = pd.DataFrame(columns=[
        "module_name", "scope", "domain", "test_name", "statistic", "p_value",
        "effect_size", "significant", "n_synthea", "n_psynthea", "notes"
    ])
    prevalence = pd.DataFrame([
        {
            "module_name": "hypertension", "scope": "module", "domain": "conditions",
            "code": "59621000", "synthea_events": 200, "synthea_total": 1000,
            "psynthea_events": 205, "psynthea_total": 1000,
            "synthea_prevalence": 0.20, "psynthea_prevalence": 0.205,
            "absolute_difference": 0.005, "relative_difference": 0.025,
            "risk_ratio": 1.025, "risk_ratio_ci_lower": 0.95,
            "risk_ratio_ci_upper": 1.10, "odds_ratio": 1.03,
            "odds_ratio_ci_lower": 0.94, "odds_ratio_ci_upper": 1.12,
            "test_name": "Fisher exact", "statistic": 0.0, "p_value": 0.50,
            "adjusted_p_value": 0.50, "significant": False,
            "significant_after_fdr": False, "notes": "",
        }
    ])
    distribution = pd.DataFrame([
        {
            "module_name": "hypertension", "scope": "module",
            "domain": "encounters_per_patient", "test_name": "Kolmogorov-Smirnov",
            "statistic": 0.04, "p_value": 0.50, "effect_size": 0.05,
            "jensen_shannon_divergence": 0.03, "significant": False,
            "n_synthea": 500, "n_psynthea": 500, "notes": "",
        }
    ])
    summary = pd.DataFrame([
        {
            "module_name": "hypertension", "validation_status": "pass",
            "valid_for_statistical_comparison": True, "skipped": False,
            "skip_reason": None, "continuous_test_count": 1,
            "categorical_test_count": 0, "prevalence_test_count": 1,
            "distribution_test_count": 1, "significant_test_count": 0,
            "significant_after_fdr_count": 0,
            "mean_jensen_shannon_divergence": 0.03,
        }
    ])
    result = ModuleStatisticalComparisonResult(
        module_name="hypertension",
        validation=None,  # adapter does not inspect the nested functional result
        continuous_tests=continuous,
        categorical_tests=categorical,
        prevalence_tests=prevalence,
        distribution_tests=distribution,
        summary=summary,
    )
    catalog = collect_evidence(result)
    context = RuleContext(
        validation_id="run-integration",
        module_name="hypertension",
        evidence=catalog,
        evaluated_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        stages={PipelineStage.STATISTICAL_VALIDATION: StageStatus.COMPLETED},
    )

    assert GlobalStatisticalReadinessRule().run(context).findings[0].status is FindingStatus.PASS
    assert FamilyEquivalenceRule().run(context).findings[0].status is FindingStatus.PASS
    assert PrevalenceEquivalenceRule().run(context).findings[0].status is FindingStatus.PASS
    assert DistributionEquivalenceRule().run(context).findings[0].status is FindingStatus.PASS