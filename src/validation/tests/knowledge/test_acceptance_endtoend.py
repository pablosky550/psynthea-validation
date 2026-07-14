"""End-to-end acceptance test for the Phase 2A knowledge framework."""

from __future__ import annotations

from datetime import UTC, datetime

from validation.knowledge import (
    ActionPriority,
    CausalCertainty,
    CausalHypothesis,
    DetectionSignal,
    EvidenceCollector,
    EvidenceDirection,
    EvidenceSourceKind,
    HypothesisEvidenceAssessment,
    HypothesisStatus,
    InvestigationCase,
    InvestigationStatus,
    KnowledgeRegistry,
    KnowledgeRule,
    RecommendedAction,
    RuleCatalog,
    RuleCondition,
    RuleOperator,
    ValidationDomain,
    VerificationCheck,
    VerificationStatus,
    attach_evidence,
    audit_protocol_evidence,
    CANONICAL_PROTOCOLS,
)

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)


def test_phase2a_evidence_to_candidate_knowledge_acceptance() -> None:
    """Prove that every Phase 2A layer collaborates without causal guessing."""

    protocol = CANONICAL_PROTOCOLS.resolve("protocol.missing_or_empty_output")
    signal = DetectionSignal(
        id="signal.observations.empty",
        domain=ValidationDomain.OBSERVATIONS.value,
        summary="The psynthea observation cohort contains no exported rows.",
        finding_id="finding.observations.empty",
        metric_id="metric.observation_rows",
        observed_value=0,
        metadata={"table_name": "observations", "row_count": 0},
    )
    investigation = InvestigationCase(
        id="investigation.observations.export",
        title="Missing observation export",
        status=InvestigationStatus.IN_PROGRESS,
        signals=(signal,),
        opened_at=NOW,
        updated_at=NOW,
    )

    evidence_items = []
    minute = 0
    for step in protocol.steps:
        collector = EvidenceCollector(
            protocol=protocol,
            step=step,
            clock=lambda minute=minute: NOW.replace(minute=minute),
        )
        for requirement in step.required_evidence:
            evidence_items.append(
                collector.from_structure(
                    id=f"evidence.{requirement.id}",
                    source_kind=requirement.source_kind,
                    summary=requirement.description,
                    locator=f"acceptance://{step.id}/{requirement.id}",
                    value={
                        "protocol": protocol.qualified_id,
                        "step": step.id,
                        "requirement": requirement.id,
                        "result": "collected",
                    },
                    requirement_ids=(requirement.id,),
                )
            )
        minute += 1

    investigation = attach_evidence(
        investigation,
        evidence_items,
        updated_at=NOW.replace(minute=10),
        note="All mandatory protocol evidence collected.",
    )
    audit = audit_protocol_evidence(protocol, investigation.evidence)
    assert audit.require_complete() is audit
    assert not audit.missing_required

    decisive_evidence = next(
        item
        for item in investigation.evidence
        if item.id == "evidence.record_export_reconciliation"
    )
    hypothesis = CausalHypothesis(
        id="hypothesis.observation_export",
        category_id="root_cause.export",
        statement="The CSV exporter omits valid internal observation entries.",
        rationale=(
            "The controlled record-to-export reconciliation isolates the loss "
            "between HealthRecord and the CSV artifact."
        ),
        status=HypothesisStatus.SUPPORTED,
        certainty=CausalCertainty.CONFIRMED,
        evidence_assessments=(
            HypothesisEvidenceAssessment(
                evidence_id=decisive_evidence.id,
                direction=EvidenceDirection.SUPPORTS,
                rationale="The internal entry is present and its exported row is absent.",
            ),
        ),
    )
    verification = VerificationCheck(
        id="verification.record_to_export",
        hypothesis_id=hypothesis.id,
        description="Reconcile internal observation entries with exported rows.",
        procedure="Match stable observation identities before and after export.",
        expected_result="Every internal observation has one exported row.",
        status=VerificationStatus.PASSED,
        actual_result="One internal observation had no exported row.",
        evidence_ids=(decisive_evidence.id,),
        executed_at=NOW.replace(minute=11),
    )
    resolved = InvestigationCase(
        id=investigation.id,
        title=investigation.title,
        status=InvestigationStatus.RESOLVED,
        signals=investigation.signals,
        hypotheses=(hypothesis,),
        evidence=investigation.evidence,
        verifications=(verification,),
        selected_hypothesis_id=hypothesis.id,
        opened_at=investigation.opened_at,
        updated_at=NOW.replace(minute=12),
        notes=investigation.notes,
    )

    registry = KnowledgeRegistry(investigations=(resolved,))
    entry = registry.publish_from_investigation(
        resolved.id,
        entry_id="knowledge.observation_export_omission",
        title="Observation export omission",
        detection_pattern=(
            "Structured observation output is empty while controlled internal "
            "record entries are present."
        ),
        root_cause="The CSV exporter omits supported ObservationEntry records.",
        recommended_actions=(
            RecommendedAction(
                id="action.repair_observation_export",
                title="Repair observation export",
                description="Serialize supported ObservationEntry records to observations.csv.",
                priority=ActionPriority.HIGH,
                target_component="psynthea.export.csv.observations",
                verification_after_action="Repeat record-to-export reconciliation.",
            ),
        ),
        applicability=("The affected CSV exporter version is enabled.",),
        domain_ids=(ValidationDomain.OBSERVATIONS.value,),
        published_at=NOW.replace(minute=13),
    )
    assert registry.knowledge_entries(active_only=True) == (entry,)

    rules = RuleCatalog(
        rules=(
            KnowledgeRule(
                id="rule.observations.zero_rows",
                knowledge_entry_id=entry.id,
                conditions=(
                    RuleCondition(
                        id="condition.observations_table",
                        field="metadata.table_name",
                        operator=RuleOperator.EQUALS,
                        value="observations",
                    ),
                    RuleCondition(
                        id="condition.zero_rows",
                        field="metadata.row_count",
                        operator=RuleOperator.EQUALS,
                        value=0,
                    ),
                ),
                domain_ids=(ValidationDomain.OBSERVATIONS.value,),
                rationale="Exact structured signature demonstrated by the validated case.",
            ),
        ),
        knowledge_entries=registry.knowledge_entries(active_only=True),
        taxonomy=registry.taxonomy,
    )
    matches = rules.match(signal)

    assert len(matches) == 1
    assert matches[0].knowledge_entry is entry
    assert matches[0].signal_id == signal.id
    assert matches[0].matched_condition_ids == (
        "condition.observations_table",
        "condition.zero_rows",
    )
    assert entry.source_investigation_id == resolved.id
    assert entry.source_hypothesis_id == hypothesis.id
    assert matches[0].knowledge_entry.root_cause == entry.root_cause