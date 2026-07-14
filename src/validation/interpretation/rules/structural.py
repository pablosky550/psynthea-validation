"""Deterministic structural validation rules for scientific interpretation.

Structural rules execute before statistical or clinical interpretation.  Their
purpose is to decide whether the normalized evidence is technically complete
and whether Synthea and psynthea outputs are structurally comparable.

The rules in this module never infer clinical equivalence.  They only evaluate:

* integrity of normalized evidence;
* availability and non-emptiness of required output tables;
* explicit comparability signals produced by the functional validation stage.

A structural failure may block downstream research use because statistical
conclusions over missing, invalid or non-comparable sources would be unsafe.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from validation.interpretation.models import (
    Confidence,
    EvidenceAvailability,
    EvidenceReference,
    EvidenceRole,
    EvidenceStrength,
    FindingStatus,
    InterpretationFinding,
    Recommendation,
    RecommendationPriority,
    Severity,
)
from validation.interpretation.rules.base import (
    ApplicabilityDecision,
    Inference,
    PipelineStage,
    RuleContext,
    RuleOutcome,
    StructuralRule,
)

__all__ = [
    "DEFAULT_STRUCTURAL_RULES",
    "EvidenceIntegrityRule",
    "RequiredTableAvailabilityRule",
    "StructuralComparabilityRule",
]


_UNAVAILABLE_STATES: Final = frozenset(
    {
        EvidenceAvailability.SOURCE_MISSING,
        EvidenceAvailability.FIELD_MISSING,
        EvidenceAvailability.EMPTY,
        EvidenceAvailability.INVALID,
        EvidenceAvailability.NOT_COMPUTED,
    }
)


def _column(value: object) -> str | None:
    metadata = getattr(value, "metadata", {})
    column = metadata.get("column") if isinstance(metadata, Mapping) else None
    return column if isinstance(column, str) else None


def _row_identity(value: object) -> str | None:
    metadata = getattr(value, "metadata", {})
    identity = metadata.get("row_identity") if isinstance(metadata, Mapping) else None
    return identity if isinstance(identity, str) else None


def _references(values: Iterable[object], role: EvidenceRole) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(metric_id=value.metric_id, role=role)
        for value in sorted(values, key=lambda item: item.metric_id)
    )


def _severity_for_availability(states: set[EvidenceAvailability]) -> Severity:
    if EvidenceAvailability.INVALID in states:
        return Severity.CRITICAL
    if EvidenceAvailability.SOURCE_MISSING in states:
        return Severity.HIGH
    if EvidenceAvailability.FIELD_MISSING in states:
        return Severity.HIGH
    if EvidenceAvailability.EMPTY in states:
        return Severity.MODERATE
    return Severity.LOW


def _confidence_for_count(count: int) -> Confidence:
    return Confidence.VERY_HIGH if count > 0 else Confidence.HIGH


class EvidenceIntegrityRule(StructuralRule):
    """Detect unavailable, malformed or non-computed normalized evidence.

    The rule scans the full catalog because structural corruption may occur in
    metrics not known in advance.  It groups evidence by availability state and
    emits one auditable finding per state, avoiding one finding per cell.
    """

    rule_id = "STRUCT.EVIDENCE_INTEGRITY"
    domain = "structural"
    description = "Assess integrity and availability of normalized validation evidence."
    required_stages = (PipelineStage.INGESTION,)
    tags = ("structural", "evidence-quality", "research-safety")

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        if len(context.evidence) == 0:
            return ApplicabilityDecision.not_evaluated(
                "Ingestion completed but produced an empty evidence catalog."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        grouped: dict[EvidenceAvailability, list[object]] = defaultdict(list)
        for value in context.evidence:
            if value.availability in _UNAVAILABLE_STATES:
                grouped[value.availability].append(value)

        if not grouped:
            available = tuple(context.evidence)
            refs = _references(available[:1], EvidenceRole.PRIMARY)
            finding = InterpretationFinding(
                finding_id="STRUCT.EVIDENCE_INTEGRITY.PASS",
                rule_id=self.rule_id,
                domain=self.domain,
                title="Normalized evidence is structurally valid",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
                confidence=Confidence.VERY_HIGH,
                evidence_strength=EvidenceStrength.VERY_STRONG,
                observation=(
                    f"All {len(available)} normalized evidence values are available or explicitly "
                    "non-applicable."
                ),
                interpretation="No missing, empty, invalid or uncomputed evidence was detected.",
                impact="Structural evidence quality does not block downstream validation.",
                evidence=refs,
                limitations=(
                    "This rule validates evidence availability, not statistical or clinical equivalence.",
                ),
                tags=self.tags,
                confidence_score=0.99,
                blocks_research_use=False,
            )
            inference = Inference(
                inference_id="STRUCT.EVIDENCE_INTEGRITY.ALL_VALID",
                statement="The normalized evidence catalog contains no structural availability defects.",
                evidence=refs,
                rationale="Every catalog item has an accepted structural availability state.",
                confidence=0.99,
            )
            return RuleOutcome(findings=(finding,), inferences=(inference,))

        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []
        for availability in sorted(grouped, key=lambda item: item.value):
            values = grouped[availability]
            refs = _references(values, EvidenceRole.PRIMARY)
            states = {availability}
            severity = _severity_for_availability(states)
            blocks = availability in {
                EvidenceAvailability.INVALID,
                EvidenceAvailability.SOURCE_MISSING,
                EvidenceAvailability.FIELD_MISSING,
            }
            status = FindingStatus.FAIL if blocks else FindingStatus.WARNING
            label = availability.value.replace("_", " ")
            finding = InterpretationFinding(
                finding_id=f"STRUCT.EVIDENCE_INTEGRITY.{availability.value.upper()}",
                rule_id=self.rule_id,
                domain=self.domain,
                title=f"Evidence contains {label} values",
                status=status,
                severity=severity,
                confidence=_confidence_for_count(len(values)),
                evidence_strength=EvidenceStrength.VERY_STRONG,
                observation=f"Detected {len(values)} evidence value(s) with availability '{availability.value}'.",
                interpretation=(
                    "The affected metrics cannot be treated as observed zeroes or valid calculated values."
                ),
                impact=(
                    "Downstream rules using these metrics must not issue equivalence conclusions."
                    if blocks
                    else "Downstream interpretation is limited for the affected metrics."
                ),
                evidence=refs,
                recommendations=(
                    Recommendation(
                        recommendation_id=f"STRUCT.REPAIR.{availability.value.upper()}",
                        action="Inspect the originating pipeline source and regenerate the affected evidence.",
                        priority=(
                            RecommendationPriority.URGENT
                            if blocks
                            else RecommendationPriority.HIGH
                        ),
                        rationale=(
                            f"Evidence marked '{availability.value}' is not a valid observed measurement."
                        ),
                        expected_outcome="All affected metrics are regenerated with explicit valid availability.",
                        verification=(
                            "Re-run evidence normalization and confirm that the affected metric identifiers no "
                            "longer have the flagged availability state."
                        ),
                        blocking=blocks,
                    ),
                ),
                limitations=(
                    "The rule identifies structural symptoms but does not determine the implementation root cause.",
                ),
                tags=(*self.tags, availability.value),
                confidence_score=0.99,
                blocks_research_use=blocks,
            )
            inference = Inference(
                inference_id=f"STRUCT.EVIDENCE_INTEGRITY.INFERENCE.{availability.value.upper()}",
                statement=f"Metrics marked '{availability.value}' are structurally unusable as observed evidence.",
                evidence=refs,
                rationale="Availability semantics explicitly distinguish these values from valid observations.",
                confidence=0.99,
            )
            findings.append(finding)
            inferences.append(inference)

        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


class RequiredTableAvailabilityRule(StructuralRule):
    """Validate required Synthea/psynthea output table pairs.

    The rule consumes the canonical ``functional.table_status`` evidence and
    evaluates each required table independently.  Optional tables never produce
    blocking failures.
    """

    rule_id = "STRUCT.REQUIRED_TABLES"
    domain = "structural"
    description = "Assess availability and non-emptiness of required output tables."
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("structural", "tables", "comparability")

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows: dict[str, dict[str, object]] = defaultdict(dict)
        for value in context.evidence:
            if ".functional.table_status." not in value.metric_id:
                continue
            identity = _row_identity(value)
            column = _column(value)
            if not identity or not column:
                continue
            if column in rows[identity]:
                raise ValueError(
                    f"Duplicate table-status evidence for row {identity!r}, column {column!r}."
                )
            rows[identity][column] = value

        if not rows:
            raise ValueError("No functional.table_status evidence is available for structural table validation.")

        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []
        for table_name in sorted(rows):
            metrics = rows[table_name]
            relevant = tuple(metrics[key] for key in sorted(metrics))
            refs = _references(relevant, EvidenceRole.PRIMARY)

            required_state = _read_boolean_metric(metrics, "required")
            if required_state.value is None:
                findings.append(
                    _inconclusive_table_finding(
                        rule=self,
                        table_name=table_name,
                        refs=refs,
                        reason=required_state.reason,
                        blocking=True,
                    )
                )
                continue
            required = required_state.value

            states = {
                name: _read_boolean_metric(metrics, name)
                for name in (
                    "synthea_available",
                    "psynthea_available",
                    "synthea_empty",
                    "psynthea_empty",
                    "blocking_issue",
                )
            }
            malformed = tuple(state.reason for state in states.values() if state.value is None)
            if malformed:
                findings.append(
                    _inconclusive_table_finding(
                        rule=self,
                        table_name=table_name,
                        refs=refs,
                        reason="; ".join(malformed),
                        blocking=required,
                    )
                )
                continue

            synthea_available = bool(states["synthea_available"].value)
            psynthea_available = bool(states["psynthea_available"].value)
            synthea_empty = bool(states["synthea_empty"].value)
            psynthea_empty = bool(states["psynthea_empty"].value)
            explicit_block = bool(states["blocking_issue"].value)

            unavailable = not synthea_available or not psynthea_available
            empty = synthea_empty or psynthea_empty
            failed = unavailable or empty or explicit_block

            if not required:
                if failed:
                    findings.append(
                        InterpretationFinding(
                            finding_id=f"STRUCT.REQUIRED_TABLES.{table_name}.OPTIONAL_WARNING",
                            rule_id=self.rule_id,
                            domain=self.domain,
                            title=f"Optional table '{table_name}' is unavailable or empty",
                            status=FindingStatus.WARNING,
                            severity=Severity.LOW,
                            confidence=Confidence.VERY_HIGH,
                            evidence_strength=EvidenceStrength.VERY_STRONG,
                            observation=(
                                f"Optional table status: Synthea available={synthea_available}, "
                                f"psynthea available={psynthea_available}, Synthea empty={synthea_empty}, "
                                f"psynthea empty={psynthea_empty}, blocking_issue={explicit_block}."
                            ),
                            interpretation="The optional table cannot support supplementary analysis.",
                            impact="Core structural comparability is not blocked because the table is optional.",
                            evidence=refs,
                            limitations=(
                                "Optionality is taken from the pipeline configuration and is not inferred clinically.",
                            ),
                            tags=(*self.tags, table_name, "optional"),
                            confidence_score=0.99,
                            blocks_research_use=False,
                        )
                    )
                continue

            if failed:
                severity = Severity.CRITICAL if unavailable else Severity.HIGH
                observation_parts = []
                if unavailable:
                    observation_parts.append(
                        f"availability: Synthea={synthea_available}, psynthea={psynthea_available}"
                    )
                if empty:
                    observation_parts.append(
                        f"empty: Synthea={synthea_empty}, psynthea={psynthea_empty}"
                    )
                if explicit_block:
                    observation_parts.append("pipeline blocking_issue=True")
                finding = InterpretationFinding(
                    finding_id=f"STRUCT.REQUIRED_TABLES.{table_name}.FAIL",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Required table '{table_name}' is not comparable",
                    status=FindingStatus.FAIL,
                    severity=severity,
                    confidence=Confidence.VERY_HIGH,
                    evidence_strength=EvidenceStrength.VERY_STRONG,
                    observation="; ".join(observation_parts),
                    interpretation=(
                        "The required table pair is absent, empty or explicitly blocked and therefore cannot "
                        "support a valid cross-engine comparison."
                    ),
                    impact=(
                        "Validation conclusions for this clinical domain are blocked until both outputs are present "
                        "and contain analyzable records."
                    ),
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"STRUCT.REQUIRED_TABLES.{table_name}.REGENERATE",
                            action=f"Regenerate and verify the '{table_name}' outputs for both engines.",
                            priority=RecommendationPriority.URGENT,
                            rationale="Both required cohorts must expose comparable non-empty tables.",
                            expected_outcome="Both table sources are available, non-empty and not blocked.",
                            verification=(
                                f"Confirm the '{table_name}' table_status row reports both available=True, "
                                "both empty=False and blocking_issue=False."
                            ),
                            blocking=True,
                        ),
                    ),
                    limitations=(
                        "This finding does not establish whether the defect originated in simulation or export.",
                    ),
                    tags=(*self.tags, table_name),
                    confidence_score=0.99,
                    blocks_research_use=True,
                )
            else:
                finding = InterpretationFinding(
                    finding_id=f"STRUCT.REQUIRED_TABLES.{table_name}.PASS",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Required table '{table_name}' is structurally available",
                    status=FindingStatus.PASS,
                    severity=Severity.INFO,
                    confidence=Confidence.VERY_HIGH,
                    evidence_strength=EvidenceStrength.VERY_STRONG,
                    observation="Both engines provide a non-empty required table without a blocking issue.",
                    interpretation="The table pair is structurally eligible for downstream comparison.",
                    impact="Structural availability does not block analysis of this table.",
                    evidence=refs,
                    limitations=(
                        "Availability does not demonstrate distributional or clinical equivalence.",
                    ),
                    tags=(*self.tags, table_name),
                    confidence_score=0.99,
                    blocks_research_use=False,
                )

            inference = Inference(
                inference_id=f"STRUCT.REQUIRED_TABLES.{table_name}.COMPARABILITY",
                statement=(
                    f"Required table '{table_name}' is structurally comparable."
                    if not failed
                    else f"Required table '{table_name}' is not structurally comparable."
                ),
                evidence=refs,
                rationale=(
                    "The decision follows directly from paired availability, emptiness and blocking indicators."
                ),
                confidence=0.99,
            )
            findings.append(finding)
            inferences.append(inference)

        if not findings:
            all_values = tuple(
                value for value in context.evidence if ".functional.table_status." in value.metric_id
            )
            refs = _references(all_values, EvidenceRole.CONTEXT)
            findings.append(
                InterpretationFinding(
                    finding_id="STRUCT.REQUIRED_TABLES.NO_REQUIRED_TABLES",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title="No required tables were declared",
                    status=FindingStatus.WARNING,
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    evidence_strength=EvidenceStrength.STRONG,
                    observation="The structural table-status evidence contains no rows marked required=True.",
                    interpretation="The pipeline cannot enforce mandatory table coverage from this configuration.",
                    impact="Research safety depends on whether required-table configuration was intentionally omitted.",
                    evidence=refs,
                    limitations=("The rule cannot infer which domains should have been mandatory.",),
                    tags=(*self.tags, "configuration"),
                    confidence_score=0.9,
                    blocks_research_use=False,
                )
            )

        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


class StructuralComparabilityRule(StructuralRule):
    """Interpret the explicit module-level ``valid_for_comparison`` signal."""

    rule_id = "STRUCT.COMPARABILITY"
    domain = "structural"
    description = "Assess explicit module-level structural comparability."
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("structural", "module", "comparability")

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        all_candidates = tuple(
            value
            for value in context.evidence
            if ".functional.summary." in value.metric_id
            and _column(value) == "valid_for_comparison"
        )
        module_candidates = tuple(
            value for value in all_candidates if _row_identity(value) == context.module_name
        )
        candidates = module_candidates or all_candidates
        if len(candidates) != 1:
            raise ValueError(
                "Exactly one functional summary valid_for_comparison metric is required; "
                f"found {len(candidates)}."
            )
        metric = candidates[0]
        refs = _references((metric,), EvidenceRole.PRIMARY)

        if not metric.is_available or not isinstance(metric.value, bool):
            status = FindingStatus.INCONCLUSIVE
            severity = Severity.HIGH
            blocks = True
            observation = (
                "The module-level valid_for_comparison signal is unavailable or is not boolean."
            )
            interpretation = "Structural comparability cannot be established from the pipeline output."
            impact = "Statistical and clinical equivalence conclusions must not be issued."
        elif metric.value:
            status = FindingStatus.PASS
            severity = Severity.INFO
            blocks = False
            observation = "The functional validation stage reports valid_for_comparison=True."
            interpretation = "The module passed the pipeline's structural comparability gate."
            impact = "Downstream statistical validation may proceed, subject to its own assumptions."
        else:
            status = FindingStatus.FAIL
            severity = Severity.CRITICAL
            blocks = True
            observation = "The functional validation stage reports valid_for_comparison=False."
            interpretation = "The compared outputs do not satisfy the structural prerequisites for equivalence testing."
            impact = "Any downstream equivalence conclusion would be methodologically unsafe."

        recommendations: tuple[Recommendation, ...] = ()
        if blocks:
            recommendations = (
                Recommendation(
                    recommendation_id="STRUCT.COMPARABILITY.RESOLVE",
                    action="Resolve all blocking functional-validation issues before statistical interpretation.",
                    priority=RecommendationPriority.URGENT,
                    rationale="Structural comparability is a prerequisite for valid cross-engine inference.",
                    expected_outcome="The functional summary reports valid_for_comparison=True.",
                    verification=(
                        "Re-run functional validation and confirm the unique summary metric "
                        "valid_for_comparison is boolean True."
                    ),
                    blocking=True,
                ),
            )

        finding = InterpretationFinding(
            finding_id=f"STRUCT.COMPARABILITY.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Module-level structural comparability",
            status=status,
            severity=severity,
            confidence=Confidence.VERY_HIGH,
            evidence_strength=EvidenceStrength.VERY_STRONG,
            observation=observation,
            interpretation=interpretation,
            impact=impact,
            evidence=refs,
            recommendations=recommendations,
            limitations=(
                "This gate does not itself prove statistical, epidemiological or clinical equivalence.",
            ),
            tags=self.tags,
            confidence_score=0.99,
            blocks_research_use=blocks,
        )
        inference = Inference(
            inference_id="STRUCT.COMPARABILITY.DECISION",
            statement=interpretation,
            evidence=refs,
            rationale="The pipeline exposes an explicit canonical comparability decision.",
            confidence=0.99,
        )
        return RuleOutcome(findings=(finding,), inferences=(inference,))


@dataclass(frozen=True, slots=True)
class _BooleanMetricState:
    value: bool | None
    reason: str


def _read_boolean_metric(metrics: Mapping[str, object], column: str) -> _BooleanMetricState:
    value = metrics.get(column)
    if value is None:
        return _BooleanMetricState(None, f"Required table-status field {column!r} is absent.")
    if not value.is_available:
        return _BooleanMetricState(
            None,
            f"Table-status field {column!r} has availability {value.availability.value!r}.",
        )
    if not isinstance(value.value, bool):
        return _BooleanMetricState(None, f"Table-status field {column!r} is not boolean.")
    return _BooleanMetricState(value.value, "Boolean table-status field is valid.")


def _inconclusive_table_finding(
    *,
    rule: RequiredTableAvailabilityRule,
    table_name: str,
    refs: tuple[EvidenceReference, ...],
    reason: str,
    blocking: bool,
) -> InterpretationFinding:
    return InterpretationFinding(
        finding_id=f"STRUCT.REQUIRED_TABLES.{table_name}.INCONCLUSIVE",
        rule_id=rule.rule_id,
        domain=rule.domain,
        title=f"Table status for '{table_name}' is inconclusive",
        status=FindingStatus.INCONCLUSIVE,
        severity=Severity.HIGH if blocking else Severity.MODERATE,
        confidence=Confidence.VERY_HIGH,
        evidence_strength=EvidenceStrength.STRONG,
        observation=reason,
        interpretation="The table-status record is incomplete or malformed and cannot support a binary structural decision.",
        impact=(
            "Downstream validation for this required table is blocked."
            if blocking
            else "Supplementary analysis of this optional table is unavailable."
        ),
        evidence=refs,
        recommendations=(
            Recommendation(
                recommendation_id=f"STRUCT.REQUIRED_TABLES.{table_name}.REPAIR_STATUS",
                action=f"Regenerate the canonical table-status evidence for '{table_name}'.",
                priority=(RecommendationPriority.URGENT if blocking else RecommendationPriority.HIGH),
                rationale="A missing or malformed status field must not be interpreted as boolean False.",
                expected_outcome="All table-status fields are available and strictly boolean.",
                verification="Re-run normalization and confirm one unique boolean value for every required status column.",
                blocking=blocking,
            ),
        ),
        limitations=("No conclusion is made about the underlying table while its status evidence is malformed.",),
        tags=(*rule.tags, table_name, "inconclusive"),
        confidence_score=0.99,
        blocks_research_use=blocking,
    )


DEFAULT_STRUCTURAL_RULES: Final = (
    EvidenceIntegrityRule(),
    RequiredTableAvailabilityRule(),
    StructuralComparabilityRule(),
)