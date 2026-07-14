from __future__ import annotations

from datetime import UTC, datetime

import pytest

from validation.interpretation.evidence import EvidenceCatalog, extract_scalar
from validation.interpretation.models import FindingStatus, Severity
from validation.interpretation.rules.base import (
    Applicability,
    PipelineStage,
    RuleContext,
    RuleExecutionStatus,
    StageStatus,
)
from validation.interpretation.rules.epidemiological import (
    DEFAULT_EPIDEMIOLOGICAL_RULES,
    DemographicProfileEquivalenceRule,
    EpidemiologicalRelationshipPreservationRule,
    EpidemiologicalThresholds,
    PopulationPrevalenceProfileRule,
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
        validation_id="validation-1",
        module_name="hypertension",
        evidence=EvidenceCatalog(tuple(values)),
        evaluated_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        stages={PipelineStage.STATISTICAL_VALIDATION: StageStatus.COMPLETED},
    )


def _comparison(
    namespace: str,
    identity: str,
    *,
    p_value: float,
    effect: float,
    significant: bool,
    n: int = 500,
    jsd: float | None = None,
):
    values = [
        _value(namespace, identity, "p_value", p_value),
        _value(namespace, identity, "effect_size", effect),
        _value(namespace, identity, "significant", significant),
        _value(namespace, identity, "n_synthea", n),
        _value(namespace, identity, "n_psynthea", n),
    ]
    if jsd is not None:
        values.append(_value(namespace, identity, "jensen_shannon_divergence", jsd))
    return tuple(values)


def _prevalence(
    identity: str,
    *,
    absolute: float,
    relative: float,
    adjusted_p: float,
    fdr: bool,
    n: int = 1000,
):
    values = {
        "synthea_total": n,
        "psynthea_total": n,
        "absolute_difference": absolute,
        "relative_difference": relative,
        "adjusted_p_value": adjusted_p,
        "significant_after_fdr": fdr,
    }
    return tuple(
        _value("statistics.prevalence", identity, column, value)
        for column, value in values.items()
    )


def test_thresholds_are_strictly_validated() -> None:
    with pytest.raises(ValueError):
        EpidemiologicalThresholds(alpha=0.0)
    with pytest.raises(ValueError):
        EpidemiologicalThresholds(minimum_sample_size=1)
    with pytest.raises(ValueError):
        EpidemiologicalThresholds(
            prevalence_warning_fraction=0.30,
            prevalence_failure_fraction=0.20,
        )
    with pytest.raises(TypeError):
        EpidemiologicalThresholds(minimum_sample_size=True)
    with pytest.raises(ValueError):
        EpidemiologicalThresholds(prevalence_failure_fraction=0.0)


def test_default_registry_is_stable_and_complete() -> None:
    assert tuple(rule.rule_id for rule in DEFAULT_EPIDEMIOLOGICAL_RULES) == (
        "EPI.DEMOGRAPHIC_PROFILE",
        "EPI.PREVALENCE_PROFILE",
        "EPI.RELATIONSHIP_PRESERVATION",
    )


def test_demographic_profile_passes_when_age_and_sex_are_equivalent() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "age.ks",
                p_value=0.40,
                effect=0.05,
                significant=False,
            ),
            *_comparison(
                "statistics.categorical",
                "sex.chi_square",
                p_value=0.30,
                effect=0.04,
                significant=False,
            ),
        )
    )

    finding = evaluation.findings[0]
    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert finding.status is FindingStatus.PASS
    assert finding.blocks_research_use is False
    assert "supports H1" in finding.interpretation
    assert len(finding.evidence) == 10


def test_demographic_material_effect_fails_h1() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "age.ks",
                p_value=0.001,
                effect=0.45,
                significant=True,
            )
        )
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.severity is Severity.HIGH
    assert finding.blocks_research_use
    assert finding.recommendations[0].blocking


def test_demographic_significant_but_small_is_warning() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.categorical",
                "gender.chi_square",
                p_value=0.001,
                effect=0.05,
                significant=True,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.WARNING
    assert not evaluation.findings[0].blocks_research_use


def test_demographic_missing_sample_size_is_inconclusive() -> None:
    values = _comparison(
        "statistics.continuous",
        "age.ks",
        p_value=0.50,
        effect=0.01,
        significant=False,
    )
    values = tuple(v for v in values if v.metadata["column"] != "n_psynthea")
    evaluation = DemographicProfileEquivalenceRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE
    assert evaluation.findings[0].blocks_research_use


def test_demographic_rule_is_not_evaluated_without_demographic_rows() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "encounter_count.ks",
                p_value=0.50,
                effect=0.01,
                significant=False,
            )
        )
    )
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.applicability.status is Applicability.NOT_EVALUATED
    assert evaluation.findings == ()


def test_prevalence_profile_passes_h2_when_all_rows_are_within_tolerance() -> None:
    evaluation = PopulationPrevalenceProfileRule().run(
        _context(
            *_prevalence(
                "conditions.59621000",
                absolute=0.005,
                relative=0.025,
                adjusted_p=0.20,
                fdr=False,
            ),
            *_prevalence(
                "conditions.44054006",
                absolute=0.010,
                relative=0.10,
                adjusted_p=0.30,
                fdr=False,
            ),
        )
    )
    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.PASS
    assert "supports H2" in finding.interpretation
    assert finding.clinically_relevant is True


def test_prevalence_profile_fails_when_material_fraction_reaches_policy() -> None:
    rows = []
    for index in range(5):
        rows.extend(
            _prevalence(
                f"conditions.code-{index}",
                absolute=0.08 if index == 0 else 0.005,
                relative=0.50 if index == 0 else 0.02,
                adjusted_p=0.001 if index == 0 else 0.40,
                fdr=index == 0,
            )
        )
    evaluation = PopulationPrevalenceProfileRule().run(_context(*rows))
    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.blocks_research_use
    assert finding.recommendations[0].recommendation_id.endswith("RECALIBRATE")


def test_single_material_prevalence_below_failure_fraction_is_blocking_warning() -> None:
    rows = []
    for index in range(10):
        rows.extend(
            _prevalence(
                f"conditions.code-{index}",
                absolute=0.05 if index == 0 else 0.005,
                relative=0.30 if index == 0 else 0.02,
                adjusted_p=0.001 if index == 0 else 0.40,
                fdr=index == 0,
            )
        )
    evaluation = PopulationPrevalenceProfileRule().run(_context(*rows))
    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.WARNING
    assert finding.severity is Severity.MODERATE
    assert finding.blocks_research_use


def test_prevalence_fdr_inconsistency_is_inconclusive() -> None:
    evaluation = PopulationPrevalenceProfileRule().run(
        _context(
            *_prevalence(
                "conditions.59621000",
                absolute=0.005,
                relative=0.02,
                adjusted_p=0.001,
                fdr=False,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_relationship_rule_refuses_to_infer_h3_from_marginal_evidence() -> None:
    evaluation = EpidemiologicalRelationshipPreservationRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "age.ks",
                p_value=0.40,
                effect=0.05,
                significant=False,
            ),
            *_prevalence(
                "conditions.59621000",
                absolute=0.005,
                relative=0.02,
                adjusted_p=0.40,
                fdr=False,
            ),
        )
    )
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert "must not be inferred" in evaluation.applicability.reason


def test_relationship_preservation_passes_explicit_stratified_evidence() -> None:
    evaluation = EpidemiologicalRelationshipPreservationRule().run(
        _context(
            *_comparison(
                "statistics.categorical",
                "hypertension.by_sex.chi_square",
                p_value=0.40,
                effect=0.05,
                significant=False,
            ),
            *_comparison(
                "statistics.continuous",
                "hypertension.age_band.ks",
                p_value=0.50,
                effect=0.04,
                significant=False,
            ),
        )
    )
    assert evaluation.findings[0].status is FindingStatus.PASS
    assert "supports H3" in evaluation.findings[0].interpretation


def test_relationship_material_effect_fails_h3() -> None:
    evaluation = EpidemiologicalRelationshipPreservationRule().run(
        _context(
            *_comparison(
                "statistics.categorical",
                "diabetes.comorbidity_hypertension.chi_square",
                p_value=0.001,
                effect=0.35,
                significant=True,
            )
        )
    )
    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.blocks_research_use
    assert finding.recommendations[0].blocking


def test_stage_failure_prevents_scientific_output() -> None:
    context = RuleContext(
        validation_id="validation-1",
        module_name="hypertension",
        evidence=EvidenceCatalog(
            _comparison(
                "statistics.continuous",
                "age.ks",
                p_value=0.40,
                effect=0.05,
                significant=False,
            )
        ),
        stages={PipelineStage.STATISTICAL_VALIDATION: StageStatus.FAILED},
    )
    evaluation = DemographicProfileEquivalenceRule().run(context)
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.findings == ()


@pytest.mark.parametrize(
    "rule_type",
    (
        DemographicProfileEquivalenceRule,
        PopulationPrevalenceProfileRule,
        EpidemiologicalRelationshipPreservationRule,
    ),
)
def test_rules_reject_non_threshold_configuration(rule_type) -> None:
    with pytest.raises(TypeError, match="EpidemiologicalThresholds"):
        rule_type(thresholds=object())


def test_demographic_candidate_matching_uses_token_boundaries() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "traceability.ks",
                p_value=0.40,
                effect=0.05,
                significant=False,
            )
        )
    )
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED


def test_demographic_rejects_out_of_range_p_value() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "age.ks",
                p_value=1.2,
                effect=0.05,
                significant=False,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_demographic_rejects_invalid_js_divergence() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.distribution",
                "age.distribution",
                p_value=0.40,
                effect=0.05,
                significant=False,
                jsd=1.1,
            )
        )
    )
    # effect_size is still valid, so the invalid optional JSD is ignored safely.
    assert evaluation.findings[0].status is FindingStatus.PASS


def test_demographic_js_divergence_can_drive_material_failure() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.distribution",
                "age.distribution",
                p_value=0.40,
                effect=0.01,
                significant=False,
                jsd=0.30,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.FAIL


def test_demographic_zero_sample_size_is_not_replaced_or_accepted() -> None:
    evaluation = DemographicProfileEquivalenceRule().run(
        _context(
            *_comparison(
                "statistics.continuous",
                "age.ks",
                p_value=0.40,
                effect=0.05,
                significant=False,
                n=0,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_prevalence_rule_is_not_evaluated_without_rows() -> None:
    evaluation = PopulationPrevalenceProfileRule().run(_context())
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.findings == ()


def test_prevalence_rejects_negative_differences() -> None:
    evaluation = PopulationPrevalenceProfileRule().run(
        _context(
            *_prevalence(
                "conditions.59621000",
                absolute=-0.01,
                relative=-0.10,
                adjusted_p=0.20,
                fdr=False,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_prevalence_rejects_out_of_range_adjusted_p_value() -> None:
    evaluation = PopulationPrevalenceProfileRule().run(
        _context(
            *_prevalence(
                "conditions.59621000",
                absolute=0.01,
                relative=0.10,
                adjusted_p=1.1,
                fdr=False,
            )
        )
    )
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_prevalence_significant_small_difference_is_nonblocking_warning() -> None:
    evaluation = PopulationPrevalenceProfileRule().run(
        _context(
            *_prevalence(
                "conditions.59621000",
                absolute=0.005,
                relative=0.05,
                adjusted_p=0.001,
                fdr=True,
            )
        )
    )
    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.WARNING
    assert finding.severity is Severity.LOW
    assert finding.blocks_research_use is False


def test_relationship_falls_back_to_prevalence_columns_without_truthiness_bug() -> None:
    values = [
        _value("statistics.prevalence", "hypertension.by_sex", "adjusted_p_value", 0.40),
        _value("statistics.prevalence", "hypertension.by_sex", "significant_after_fdr", False),
        _value("statistics.prevalence", "hypertension.by_sex", "relative_difference", 0.05),
        _value("statistics.prevalence", "hypertension.by_sex", "synthea_total", 1000),
        _value("statistics.prevalence", "hypertension.by_sex", "psynthea_total", 1000),
    ]
    evaluation = EpidemiologicalRelationshipPreservationRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.PASS


def test_relationship_zero_primary_sample_is_not_hidden_by_fallback_total() -> None:
    values = [
        _value("statistics.prevalence", "hypertension.by_sex", "adjusted_p_value", 0.40),
        _value("statistics.prevalence", "hypertension.by_sex", "significant_after_fdr", False),
        _value("statistics.prevalence", "hypertension.by_sex", "relative_difference", 0.05),
        _value("statistics.prevalence", "hypertension.by_sex", "n_synthea", 0),
        _value("statistics.prevalence", "hypertension.by_sex", "n_psynthea", 0),
        _value("statistics.prevalence", "hypertension.by_sex", "synthea_total", 1000),
        _value("statistics.prevalence", "hypertension.by_sex", "psynthea_total", 1000),
    ]
    evaluation = EpidemiologicalRelationshipPreservationRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE


def test_relationship_significant_small_effect_is_warning() -> None:
    evaluation = EpidemiologicalRelationshipPreservationRule().run(
        _context(
            *_comparison(
                "statistics.categorical",
                "hypertension.by_sex.chi_square",
                p_value=0.001,
                effect=0.05,
                significant=True,
            )
        )
    )
    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.WARNING
    assert finding.blocks_research_use is False


def test_relationship_incomplete_evidence_is_inconclusive() -> None:
    values = _comparison(
        "statistics.categorical",
        "hypertension.by_sex.chi_square",
        p_value=0.40,
        effect=0.05,
        significant=False,
    )
    values = tuple(value for value in values if value.metadata["column"] != "effect_size")
    evaluation = EpidemiologicalRelationshipPreservationRule().run(_context(*values))
    assert evaluation.findings[0].status is FindingStatus.INCONCLUSIVE