from __future__ import annotations

from types import MappingProxyType

import pytest

from validation.interpretation.evidence import EvidenceCatalog
from validation.interpretation.models import (
    EvidenceAvailability,
    EvidenceValue,
    FindingStatus,
    Severity,
)
from validation.interpretation.rules.base import (
    PipelineStage,
    RuleContext,
    RuleExecutionError,
    RuleExecutionStatus,
    StageStatus,
    ValidationDimension,
)
from validation.interpretation.rules.structural import (
    DEFAULT_STRUCTURAL_RULES,
    EvidenceIntegrityRule,
    RequiredTableAvailabilityRule,
    StructuralComparabilityRule,
)


def ev(
    metric_id: str,
    value: object = True,
    *,
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
    column: str | None = None,
    row_identity: str | None = None,
) -> EvidenceValue:
    metadata = {}
    if column is not None:
        metadata["column"] = column
    if row_identity is not None:
        metadata["row_identity"] = row_identity
    return EvidenceValue(
        metric_id=metric_id,
        name=metric_id,
        availability=availability,
        value=value if availability is EvidenceAvailability.AVAILABLE else None,
        metadata=metadata,
    )


def context(
    values: tuple[EvidenceValue, ...],
    *,
    stages: dict[PipelineStage, StageStatus] | None = None,
) -> RuleContext:
    return RuleContext(
        validation_id="run-001",
        module_name="hypertension",
        evidence=EvidenceCatalog(values),
        stages=MappingProxyType(stages or {}),
    )


def table_row(
    table: str,
    *,
    required: bool = True,
    synthea_available: bool = True,
    psynthea_available: bool = True,
    synthea_empty: bool = False,
    psynthea_empty: bool = False,
    blocking_issue: bool = False,
) -> tuple[EvidenceValue, ...]:
    prefix = f"hypertension.functional.table_status.{table}"
    values = {
        "required": required,
        "synthea_available": synthea_available,
        "psynthea_available": psynthea_available,
        "synthea_empty": synthea_empty,
        "psynthea_empty": psynthea_empty,
        "blocking_issue": blocking_issue,
    }
    return tuple(
        ev(
            f"{prefix}.{column}",
            value,
            column=column,
            row_identity=table,
        )
        for column, value in values.items()
    )


def test_evidence_integrity_passes_when_all_values_are_available() -> None:
    evaluation = EvidenceIntegrityRule().run(
        context(
            (ev("metric.available", 0),),
            stages={PipelineStage.INGESTION: StageStatus.COMPLETED},
        )
    )

    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert evaluation.dimension is ValidationDimension.STRUCTURAL
    assert evaluation.findings[0].status is FindingStatus.PASS
    assert evaluation.findings[0].blocks_research_use is False


def test_evidence_integrity_groups_invalid_and_missing_states() -> None:
    evaluation = EvidenceIntegrityRule().run(
        context(
            (
                ev("metric.invalid", availability=EvidenceAvailability.INVALID),
                ev("metric.source", availability=EvidenceAvailability.SOURCE_MISSING),
                ev("metric.empty", availability=EvidenceAvailability.EMPTY),
            ),
            stages={PipelineStage.INGESTION: StageStatus.COMPLETED},
        )
    )

    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert {finding.status for finding in evaluation.findings} == {
        FindingStatus.FAIL,
        FindingStatus.WARNING,
    }
    assert any(finding.severity is Severity.CRITICAL for finding in evaluation.findings)
    assert any(finding.blocks_research_use for finding in evaluation.findings)


def test_evidence_integrity_does_not_treat_zero_as_missing() -> None:
    evaluation = EvidenceIntegrityRule().run(
        context(
            (ev("metric.zero", 0),),
            stages={PipelineStage.INGESTION: StageStatus.COMPLETED},
        )
    )
    assert evaluation.findings[0].status is FindingStatus.PASS


def test_required_tables_pass_for_non_empty_available_pair() -> None:
    evaluation = RequiredTableAvailabilityRule().run(
        context(
            table_row("conditions"),
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    assert evaluation.status is RuleExecutionStatus.COMPLETED
    assert evaluation.findings[0].status is FindingStatus.PASS
    assert evaluation.findings[0].blocks_research_use is False


def test_required_tables_fail_when_psynthea_table_is_missing() -> None:
    evaluation = RequiredTableAvailabilityRule().run(
        context(
            table_row("observations", psynthea_available=False, blocking_issue=True),
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.severity is Severity.CRITICAL
    assert finding.blocks_research_use is True
    assert finding.recommendations[0].blocking is True


def test_optional_table_does_not_create_blocking_failure() -> None:
    evaluation = RequiredTableAvailabilityRule().run(
        context(
            table_row("claims", required=False, psynthea_available=False),
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    assert len(evaluation.findings) == 1
    assert evaluation.findings[0].status is FindingStatus.WARNING
    assert evaluation.findings[0].blocks_research_use is False


def test_comparability_passes_only_on_explicit_boolean_true() -> None:
    metric = ev(
        "hypertension.functional.summary.hypertension.valid_for_comparison",
        True,
        column="valid_for_comparison",
        row_identity="hypertension",
    )
    evaluation = StructuralComparabilityRule().run(
        context(
            (metric,),
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    assert evaluation.findings[0].status is FindingStatus.PASS


def test_comparability_false_blocks_research_use() -> None:
    metric = ev(
        "hypertension.functional.summary.hypertension.valid_for_comparison",
        False,
        column="valid_for_comparison",
        row_identity="hypertension",
    )
    evaluation = StructuralComparabilityRule().run(
        context(
            (metric,),
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.FAIL
    assert finding.severity is Severity.CRITICAL
    assert finding.blocks_research_use is True


def test_comparability_rejects_ambiguous_summary_metrics() -> None:
    metrics = (
        ev(
            "a.functional.summary.a.valid_for_comparison",
            True,
            column="valid_for_comparison",
        ),
        ev(
            "b.functional.summary.b.valid_for_comparison",
            True,
            column="valid_for_comparison",
        ),
    )
    with pytest.raises(RuleExecutionError, match="Exactly one"):
        StructuralComparabilityRule().run(
            context(
                metrics,
                stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
            )
        )


def test_rules_are_not_evaluated_when_required_stage_did_not_run() -> None:
    evaluation = RequiredTableAvailabilityRule().run(context(table_row("conditions")))
    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.findings == ()


def test_default_rule_order_is_deterministic() -> None:
    assert tuple(rule.rule_id for rule in DEFAULT_STRUCTURAL_RULES) == (
        "STRUCT.EVIDENCE_INTEGRITY",
        "STRUCT.REQUIRED_TABLES",
        "STRUCT.COMPARABILITY",
    )


def test_evidence_integrity_empty_catalog_is_not_evaluated() -> None:
    evaluation = EvidenceIntegrityRule().run(
        context((), stages={PipelineStage.INGESTION: StageStatus.COMPLETED})
    )

    assert evaluation.status is RuleExecutionStatus.NOT_EVALUATED
    assert evaluation.findings == ()


def test_required_tables_treats_missing_boolean_as_inconclusive_not_false() -> None:
    values = tuple(
        item for item in table_row("conditions")
        if item.metadata.get("column") != "psynthea_available"
    )
    evaluation = RequiredTableAvailabilityRule().run(
        context(
            values,
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    finding = evaluation.findings[0]
    assert finding.status is FindingStatus.INCONCLUSIVE
    assert finding.blocks_research_use is True


def test_required_tables_rejects_duplicate_row_column_evidence() -> None:
    values = table_row("conditions")
    duplicate = ev(
        "hypertension.functional.table_status.conditions.required_duplicate",
        True,
        column="required",
        row_identity="conditions",
    )
    with pytest.raises(RuleExecutionError, match="Duplicate table-status evidence"):
        RequiredTableAvailabilityRule().run(
            context(
                (*values, duplicate),
                stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
            )
        )


def test_comparability_selects_current_module_from_multi_module_catalog() -> None:
    metrics = (
        ev(
            "diabetes.functional.summary.diabetes.valid_for_comparison",
            False,
            column="valid_for_comparison",
            row_identity="diabetes",
        ),
        ev(
            "hypertension.functional.summary.hypertension.valid_for_comparison",
            True,
            column="valid_for_comparison",
            row_identity="hypertension",
        ),
    )
    evaluation = StructuralComparabilityRule().run(
        context(
            metrics,
            stages={PipelineStage.FUNCTIONAL_VALIDATION: StageStatus.COMPLETED},
        )
    )

    assert evaluation.findings[0].status is FindingStatus.PASS