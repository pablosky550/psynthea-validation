from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from validation.knowledge.models import (
    ActionPriority,
    CausalCertainty,
    DetectionSignal,
    EvidenceItem,
    EvidenceSourceKind,
    KnowledgeEntry,
    KnowledgeEntryStatus,
    RecommendedAction,
    VerificationCheck,
    VerificationStatus,
)
from validation.knowledge.rules import (
    DuplicateRuleError,
    InvalidRuleError,
    KnowledgeRule,
    RuleCatalog,
    RuleCondition,
    RuleOperator,
    UnknownRuleError,
)
from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)


def evidence() -> EvidenceItem:
    return EvidenceItem(
        id="ev.1",
        source_kind=EvidenceSourceKind.REPRODUCTION,
        summary="Reproduced export omission",
        locator="run://controlled",
        collected_at=NOW,
    )


def verification() -> VerificationCheck:
    return VerificationCheck(
        id="check.1",
        hypothesis_id="hyp.1",
        description="Reconcile record and export",
        procedure="Compare internal entries with exported rows.",
        expected_result="Every internal observation has one exported row.",
        status=VerificationStatus.PASSED,
        actual_result="Internal observations were absent from export.",
        evidence_ids=("ev.1",),
        executed_at=NOW,
    )


def action() -> RecommendedAction:
    return RecommendedAction(
        id="action.1",
        title="Review exporter",
        description="Implement observation export reconciliation.",
        priority=ActionPriority.HIGH,
        target_component="export.observations",
        verification_after_action="Re-run record-to-export reconciliation.",
    )


def entry(
    *,
    id: str = "knowledge.export.observations",
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.VALIDATED,
    certainty: CausalCertainty = CausalCertainty.CONFIRMED,
    domains: tuple[str, ...] | None = (ValidationDomain.OBSERVATIONS.value,),
    supersedes: tuple[str, ...] = (),
) -> KnowledgeEntry:
    metadata = {} if domains is None else {"domain_ids": domains}
    return KnowledgeEntry(
        id=id,
        title="Observation export omission",
        status=status,
        category_id=RootCauseCategory.EXPORT.value,
        detection_pattern="Observation events exist internally but are absent from output.",
        root_cause="Observation exporter omits supported internal entries.",
        causal_certainty=certainty,
        source_investigation_id="investigation.1",
        source_hypothesis_id="hyp.1",
        evidence=(evidence(),) if status is KnowledgeEntryStatus.VALIDATED else (),
        verifications=(verification(),) if status is KnowledgeEntryStatus.VALIDATED else (),
        recommended_actions=(action(),) if status is KnowledgeEntryStatus.VALIDATED else (),
        applicability=("Internal observation exists before export.",),
        created_at=NOW,
        updated_at=NOW,
        supersedes=supersedes,
        metadata=metadata,
    )


def condition(
    id: str = "condition.table",
    field: str = "metadata.table_name",
    operator: RuleOperator = RuleOperator.EQUALS,
    value: object = "observations",
) -> RuleCondition:
    return RuleCondition(id=id, field=field, operator=operator, value=value)


def rule(
    *,
    id: str = "rule.export.observations",
    entry_id: str = "knowledge.export.observations",
    conditions: tuple[RuleCondition, ...] | None = None,
    domains: tuple[str, ...] = (ValidationDomain.OBSERVATIONS.value,),
    priority: int = 100,
    enabled: bool = True,
) -> KnowledgeRule:
    return KnowledgeRule(
        id=id,
        knowledge_entry_id=entry_id,
        conditions=conditions or (condition(),),
        domain_ids=domains,
        rationale="Exact structured signature validated during the investigation.",
        priority=priority,
        enabled=enabled,
    )


def signal(
    *,
    id: str = "signal.1",
    domain: str = ValidationDomain.OBSERVATIONS.value,
    observed_value: object = 0,
    metadata: dict[str, object] | None = None,
) -> DetectionSignal:
    return DetectionSignal(
        id=id,
        domain=domain,
        summary="Observations missing",
        metric_id="metric.observation_rows",
        observed_value=observed_value,
        metadata=metadata or {"table_name": "observations", "row_count": 0},
    )


def test_rejects_narrative_and_instance_fields() -> None:
    for field in ("summary", "id"):
        with pytest.raises(InvalidRuleError):
            condition(field=field)


def test_rejects_invalid_nested_path() -> None:
    with pytest.raises(InvalidRuleError):
        condition(field="metric_id.value")
    with pytest.raises(InvalidRuleError):
        condition(field="metadata._private")


def test_membership_requires_non_empty_collection() -> None:
    with pytest.raises(InvalidRuleError):
        condition(operator=RuleOperator.IN, value="observations")
    with pytest.raises(InvalidRuleError):
        condition(operator=RuleOperator.IN, value=())


def test_ordered_operator_requires_finite_number() -> None:
    with pytest.raises(InvalidRuleError):
        condition(operator=RuleOperator.GREATER_THAN, value=True)
    with pytest.raises(InvalidRuleError):
        condition(operator=RuleOperator.GREATER_THAN, value=float("nan"))


def test_exists_requires_boolean() -> None:
    with pytest.raises(InvalidRuleError):
        condition(operator=RuleOperator.EXISTS, value=1)


def test_condition_values_are_deeply_immutable() -> None:
    source = ["observations", "conditions"]
    item = condition(operator=RuleOperator.IN, value=source)
    source.append("procedures")
    assert item.value == ("observations", "conditions")


def test_all_operators_have_deterministic_semantics() -> None:
    current = signal()
    assert condition(operator=RuleOperator.EQUALS, value="observations").matches(current)
    assert condition(operator=RuleOperator.NOT_EQUALS, value="conditions").matches(current)
    assert condition(operator=RuleOperator.IN, value=("observations", "conditions")).matches(current)
    assert condition(operator=RuleOperator.NOT_IN, value=("conditions",)).matches(current)
    assert condition(field="metadata", operator=RuleOperator.CONTAINS, value="row_count").matches(current)
    assert condition(field="metadata.row_count", operator=RuleOperator.EXISTS, value=True).matches(current)
    assert condition(field="metadata.unknown", operator=RuleOperator.EXISTS, value=False).matches(current)
    assert condition(field="metadata.row_count", operator=RuleOperator.GREATER_OR_EQUAL, value=0).matches(current)
    assert condition(field="metadata.row_count", operator=RuleOperator.LESS_OR_EQUAL, value=0).matches(current)


def test_missing_path_does_not_satisfy_not_equals_or_not_in() -> None:
    current = signal(metadata={"table_name": "observations"})
    assert not condition(field="metadata.absent", operator=RuleOperator.NOT_EQUALS, value=1).matches(current)
    assert not condition(field="metadata.absent", operator=RuleOperator.NOT_IN, value=(1, 2)).matches(current)


def test_non_numeric_actual_does_not_match_ordered_condition() -> None:
    current = signal(metadata={"table_name": "observations", "row_count": "zero"})
    assert not condition(field="metadata.row_count", operator=RuleOperator.LESS_THAN, value=1).matches(current)


def test_rule_requires_unique_conditions_and_domains() -> None:
    duplicate = condition()
    with pytest.raises(InvalidRuleError):
        rule(conditions=(duplicate, duplicate))
    assert rule(domains=(ValidationDomain.OBSERVATIONS.value,) * 2).domain_ids == (
        ValidationDomain.OBSERVATIONS.value,
    )


def test_disabled_or_wrong_domain_rule_does_not_match() -> None:
    assert not rule(enabled=False).matches(signal())
    assert not rule(domains=(ValidationDomain.CONDITIONS.value,)).matches(signal())


def test_rule_uses_conjunction_of_conditions() -> None:
    current_rule = rule(
        conditions=(
            condition(),
            condition(
                id="condition.zero",
                field="metadata.row_count",
                operator=RuleOperator.EQUALS,
                value=0,
            ),
        )
    )
    assert current_rule.matches(signal())
    assert not current_rule.matches(signal(metadata={"table_name": "observations", "row_count": 3}))


def test_catalog_rejects_duplicate_rules() -> None:
    current = rule()
    with pytest.raises(DuplicateRuleError):
        RuleCatalog(rules=(current, current), knowledge_entries=(entry(),))


def test_catalog_requires_known_active_validated_entry() -> None:
    with pytest.raises(InvalidRuleError):
        RuleCatalog(rules=(rule(entry_id="unknown"),), knowledge_entries=(entry(),))

    draft = entry(status=KnowledgeEntryStatus.DRAFT, certainty=CausalCertainty.PROBABLE)
    with pytest.raises(InvalidRuleError):
        RuleCatalog(rules=(rule(),), knowledge_entries=(draft,))


def test_catalog_requires_explicit_entry_domains() -> None:
    with pytest.raises(InvalidRuleError):
        RuleCatalog(rules=(rule(),), knowledge_entries=(entry(domains=None),))


def test_catalog_rejects_rule_domain_outside_entry_applicability() -> None:
    with pytest.raises(InvalidRuleError):
        RuleCatalog(
            rules=(rule(domains=(ValidationDomain.CONDITIONS.value,)),),
            knowledge_entries=(entry(),),
        )


def test_catalog_rejects_superseded_entry_when_both_are_present() -> None:
    old = entry(id="knowledge.old")
    new = entry(id="knowledge.export.observations", supersedes=(old.id,))
    with pytest.raises(InvalidRuleError):
        RuleCatalog(rules=(rule(),), knowledge_entries=(old, new))


def test_catalog_orders_matches_by_priority_then_id() -> None:
    second = rule(id="rule.second", priority=20)
    first = rule(id="rule.first", priority=10)
    catalog = RuleCatalog(rules=(second, first), knowledge_entries=(entry(),))
    assert [item.rule_id for item in catalog.match(signal())] == [
        "rule.first",
        "rule.second",
    ]


def test_match_is_candidate_with_exact_condition_ids() -> None:
    current_rule = rule(
        conditions=(
            condition(),
            condition(
                id="condition.zero",
                field="metadata.row_count",
                operator=RuleOperator.EQUALS,
                value=0,
            ),
        )
    )
    match = RuleCatalog(
        rules=(current_rule,), knowledge_entries=(entry(),)
    ).match(signal())[0]
    assert match.signal_id == "signal.1"
    assert match.knowledge_entry.id == "knowledge.export.observations"
    assert match.matched_condition_ids == ("condition.table", "condition.zero")


def test_lookup_and_rules_for_entry_are_strict() -> None:
    catalog = RuleCatalog(rules=(rule(),), knowledge_entries=(entry(),))
    assert catalog.rule("rule.export.observations").id == "rule.export.observations"
    assert catalog.knowledge_entry("knowledge.export.observations").id == "knowledge.export.observations"
    assert catalog.rules_for_entry("knowledge.export.observations") == (rule(),)
    with pytest.raises(UnknownRuleError):
        catalog.rule("unknown")
    with pytest.raises(KeyError):
        catalog.knowledge_entry("unknown")


def test_match_many_is_immutable_and_rejects_duplicate_signal_ids() -> None:
    catalog = RuleCatalog(rules=(rule(),), knowledge_entries=(entry(),))
    result = catalog.match_many((signal(id="signal.1"), signal(id="signal.2")))
    assert tuple(result) == ("signal.1", "signal.2")
    with pytest.raises(TypeError):
        result["signal.3"] = ()
    with pytest.raises(ValueError):
        catalog.match_many((signal(), signal()))