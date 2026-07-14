"""Deterministic clinical interpretation rules for module-level equivalence.

Clinical rules execute after structural and statistical readiness checks.  They
interpret the explicit clinical signals and coded-domain overlap emitted by the
functional validation stage; they never infer diagnoses directly from raw CSV
rows and never treat code-set identity as proof of complete clinical equivalence.

Decision principles
-------------------

* The Synthea reference must expose the expected signal before its absence in
  psynthea can be classified as a replication failure.
* Expected-signal preservation is evaluated independently for conditions,
  medications, procedures and observations.
* Code-set overlap and event-count retention are complementary: either can reveal
  a clinically meaningful loss hidden by the other.
* Missing, malformed or internally contradictory evidence remains inconclusive.
* PASS establishes preservation of the configured clinical signal only; it does
  not establish temporal, causal or guideline-level equivalence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Final

from validation.interpretation.models import (
    Confidence,
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
    ClinicalRule,
    Inference,
    PipelineStage,
    RuleContext,
    RuleOutcome,
)

__all__ = [
    "ClinicalCodeOverlapRule",
    "ClinicalSignalPreservationRule",
    "ClinicalThresholds",
    "DEFAULT_CLINICAL_RULES",
    "DomainEventRetentionRule",
]


@dataclass(frozen=True, slots=True)
class ClinicalThresholds:
    """Auditable policy thresholds for clinical-equivalence interpretation."""

    minimum_reference_events: int = 1
    warning_event_retention: float = 0.80
    failure_event_retention: float = 0.50
    warning_event_overproduction: float = 1.25
    failure_event_overproduction: float = 2.00
    warning_jaccard_similarity: float = 0.70
    failure_jaccard_similarity: float = 0.40
    warning_overlap_coefficient: float = 0.80
    failure_overlap_coefficient: float = 0.50
    maximum_warning_js_divergence: float = 0.10
    maximum_failure_js_divergence: float = 0.25

    def __post_init__(self) -> None:
        if isinstance(self.minimum_reference_events, bool) or not isinstance(
            self.minimum_reference_events, int
        ):
            raise TypeError("minimum_reference_events must be an integer.")
        if self.minimum_reference_events < 1:
            raise ValueError("minimum_reference_events must be at least 1.")

        probability_fields = (
            "warning_event_retention",
            "failure_event_retention",
            "warning_jaccard_similarity",
            "failure_jaccard_similarity",
            "warning_overlap_coefficient",
            "failure_overlap_coefficient",
            "maximum_warning_js_divergence",
            "maximum_failure_js_divergence",
        )
        for name in probability_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric.")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1.")

        for name in ("warning_event_overproduction", "failure_event_overproduction"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric.")
            if not isfinite(float(value)) or float(value) < 1.0:
                raise ValueError(f"{name} must be finite and at least 1.0.")

        if self.failure_event_retention > self.warning_event_retention:
            raise ValueError(
                "failure_event_retention must not exceed warning_event_retention."
            )
        if self.warning_event_overproduction < 1.0:
            raise ValueError("warning_event_overproduction must be at least 1.0.")
        if self.failure_event_overproduction < self.warning_event_overproduction:
            raise ValueError(
                "failure_event_overproduction must not be below "
                "warning_event_overproduction."
            )
        if self.failure_jaccard_similarity > self.warning_jaccard_similarity:
            raise ValueError(
                "failure_jaccard_similarity must not exceed warning_jaccard_similarity."
            )
        if self.failure_overlap_coefficient > self.warning_overlap_coefficient:
            raise ValueError(
                "failure_overlap_coefficient must not exceed warning_overlap_coefficient."
            )
        if self.maximum_warning_js_divergence > self.maximum_failure_js_divergence:
            raise ValueError(
                "maximum_warning_js_divergence must not exceed "
                "maximum_failure_js_divergence."
            )


DEFAULT_THRESHOLDS: Final = ClinicalThresholds()


def _column(value: object) -> str | None:
    metadata = getattr(value, "metadata", {})
    column = metadata.get("column") if isinstance(metadata, Mapping) else None
    return column if isinstance(column, str) else None


def _row_identity(value: object) -> str | None:
    metadata = getattr(value, "metadata", {})
    identity = metadata.get("row_identity") if isinstance(metadata, Mapping) else None
    return identity if isinstance(identity, str) else None


def _rows(context: RuleContext, namespace: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = defaultdict(dict)
    needle = f".{namespace}."
    for value in context.evidence:
        if needle not in value.metric_id:
            continue
        identity = _row_identity(value)
        column = _column(value)
        if identity is None or column is None:
            continue
        if column in grouped[identity]:
            raise ValueError(
                f"Duplicate clinical evidence for {namespace!r}, row "
                f"{identity!r}, column {column!r}."
            )
        grouped[identity][column] = value
    return grouped


def _refs(
    values: Iterable[object], role: EvidenceRole = EvidenceRole.PRIMARY
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(metric_id=value.metric_id, role=role)
        for value in sorted(values, key=lambda item: item.metric_id)
    )


def _available_value(metrics: Mapping[str, object], column: str) -> object | None:
    metric = metrics.get(column)
    if metric is None or not getattr(metric, "is_available", False):
        return None
    return metric.value


def _number(metrics: Mapping[str, object], column: str) -> float | None:
    value = _available_value(metrics, column)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _integer(metrics: Mapping[str, object], column: str) -> int | None:
    value = _number(metrics, column)
    if value is None or not value.is_integer():
        return None
    return int(value)


def _boolean(metrics: Mapping[str, object], column: str) -> bool | None:
    value = _available_value(metrics, column)
    return value if isinstance(value, bool) else None


def _text(metrics: Mapping[str, object], column: str) -> str | None:
    value = _available_value(metrics, column)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _domain_from_identity(identity: str) -> str:
    return identity.split(".", 1)[0]


def _strength(reference_events: int | None) -> EvidenceStrength:
    if reference_events is None:
        return EvidenceStrength.INSUFFICIENT
    if reference_events < 10:
        return EvidenceStrength.WEAK
    if reference_events < 100:
        return EvidenceStrength.MODERATE
    if reference_events < 1000:
        return EvidenceStrength.STRONG
    return EvidenceStrength.VERY_STRONG


def _confidence(reference_events: int | None, complete: bool = True) -> Confidence:
    if not complete:
        return Confidence.LOW
    if reference_events is None or reference_events < 10:
        return Confidence.MODERATE
    if reference_events < 100:
        return Confidence.HIGH
    return Confidence.VERY_HIGH


def _inconclusive_finding(
    *,
    rule: ClinicalRule,
    identity: str,
    title: str,
    metrics: Mapping[str, object],
    reason: str,
    tags: tuple[str, ...],
    blocking: bool = False,
) -> InterpretationFinding:
    return InterpretationFinding(
        finding_id=f"{rule.rule_id}.{identity}.INCONCLUSIVE",
        rule_id=rule.rule_id,
        domain=rule.domain,
        title=title,
        status=FindingStatus.INCONCLUSIVE,
        severity=Severity.HIGH if blocking else Severity.MODERATE,
        confidence=Confidence.LOW,
        evidence_strength=EvidenceStrength.INSUFFICIENT,
        observation=reason,
        interpretation="The available evidence is insufficient for a defensible clinical conclusion.",
        impact=(
            "Clinical equivalence for this domain is blocked until the evidence is corrected."
            if blocking
            else "No pass or fail conclusion is issued for this clinical domain."
        ),
        evidence=_refs(metrics.values()),
        recommendations=(
            Recommendation(
                recommendation_id=f"{rule.rule_id}.{identity}.REPAIR",
                action="Regenerate and validate the affected clinical-comparison evidence.",
                priority=(
                    RecommendationPriority.URGENT
                    if blocking
                    else RecommendationPriority.HIGH
                ),
                rationale=reason,
                expected_outcome="All required clinical metrics are available, typed and mutually consistent.",
                verification=(
                    "Re-run evidence collection and confirm that the row can be interpreted "
                    "without missing or contradictory fields."
                ),
                blocking=blocking,
            ),
        ),
        limitations=(
            "The rule does not infer missing values from neighboring metrics.",
        ),
        tags=tags,
        confidence_score=0.35,
        clinically_relevant=True,
        blocks_research_use=blocking,
    )


class ClinicalSignalPreservationRule(ClinicalRule):
    """Assess preservation of explicitly configured clinical module signals."""

    rule_id = "CLINICAL.SIGNAL_PRESERVATION"
    domain = "clinical"
    description = "Assess whether psynthea reproduces expected module-level clinical signals."
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("clinical", "expected-signal", "module-fidelity")

    def __init__(self, thresholds: ClinicalThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, ClinicalThresholds):
            raise TypeError("thresholds must be a ClinicalThresholds instance.")
        self.thresholds = thresholds

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        rows = _rows(context, "functional.clinical_signal")
        if not rows:
            return ApplicabilityDecision.not_evaluated(
                "No functional clinical-signal evidence was produced."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "functional.clinical_signal")
        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []

        for identity in sorted(rows):
            metrics = rows[identity]
            domain = _domain_from_identity(identity)
            synthea_count = _integer(metrics, "synthea_signal_count")
            psynthea_count = _integer(metrics, "psynthea_signal_count")
            reference_detected = _boolean(metrics, "expected_signal_detected_synthea")
            candidate_detected = _boolean(metrics, "expected_signal_detected_psynthea")
            expected_terms = _text(metrics, "expected_terms")
            blocking_issue = _boolean(metrics, "blocking_issue")
            refs = _refs(metrics.values())

            if synthea_count is None or psynthea_count is None or blocking_issue is None:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical signal preservation for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason="Signal counts or the blocking indicator are missing or malformed.",
                        tags=(*self.tags, domain),
                        blocking=True,
                    )
                )
                continue
            if synthea_count < 0 or psynthea_count < 0:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical signal preservation for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason="Clinical signal counts cannot be negative.",
                        tags=(*self.tags, domain),
                        blocking=True,
                    )
                )
                continue

            # No expected terms were configured for this domain.  Counts remain
            # useful context, but an expected-signal decision would be invented.
            if expected_terms is None:
                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.NOT_EVALUATED",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"No expected clinical terms configured for '{domain}'",
                    status=FindingStatus.NOT_EVALUATED,
                    severity=Severity.INFO,
                    confidence=Confidence.HIGH,
                    evidence_strength=EvidenceStrength.MODERATE,
                    observation=(
                        f"Synthea produced {synthea_count} signal(s) and psynthea produced "
                        f"{psynthea_count}, but no expected_terms value was configured."
                    ),
                    interpretation="Expected-signal preservation is not evaluated for this domain.",
                    impact="This rule contributes no pass or fail decision for the domain.",
                    evidence=refs,
                    limitations=(
                        "Event counts alone cannot identify whether the intended module signal is present.",
                    ),
                    tags=(*self.tags, domain, "configuration"),
                    confidence_score=0.9,
                    clinically_relevant=None,
                    blocks_research_use=False,
                )
                findings.append(finding)
                continue

            if reference_detected is None or candidate_detected is None:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical signal preservation for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason=(
                            "Expected clinical terms were configured, but one or both detection "
                            "flags are unavailable or non-boolean."
                        ),
                        tags=(*self.tags, domain),
                        blocking=True,
                    )
                )
                continue

            if reference_detected and synthea_count == 0:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Reference signal evidence for '{domain}' is contradictory",
                        metrics=metrics,
                        reason=(
                            "Synthea is marked as containing the expected signal while its signal "
                            "count is zero."
                        ),
                        tags=(*self.tags, domain, "contradiction"),
                        blocking=True,
                    )
                )
                continue
            if candidate_detected and psynthea_count == 0:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"psynthea signal evidence for '{domain}' is contradictory",
                        metrics=metrics,
                        reason=(
                            "psynthea is marked as containing the expected signal while its signal "
                            "count is zero."
                        ),
                        tags=(*self.tags, domain, "contradiction"),
                        blocking=True,
                    )
                )
                continue

            if not reference_detected:
                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.REFERENCE_INCONCLUSIVE",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Reference run does not establish the expected '{domain}' signal",
                    status=FindingStatus.INCONCLUSIVE,
                    severity=Severity.MODERATE,
                    confidence=_confidence(synthea_count),
                    evidence_strength=_strength(synthea_count),
                    observation=(
                        f"Expected terms '{expected_terms}' were not detected in the Synthea "
                        f"reference output ({synthea_count} domain signal(s))."
                    ),
                    interpretation=(
                        "The reference run cannot serve as positive evidence for replication of "
                        "this configured clinical signal."
                    ),
                    impact="The candidate cannot be failed for not reproducing a signal absent from the reference.",
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.REVIEW_REFERENCE",
                            action="Review expected terms, reference seed and module execution for this domain.",
                            priority=RecommendationPriority.HIGH,
                            rationale="A configured expected signal must first be demonstrated in Synthea.",
                            expected_outcome="The reference run detects the intended signal or the configuration is corrected.",
                            verification=(
                                "Confirm expected_signal_detected_synthea=True with a positive "
                                "synthea_signal_count."
                            ),
                            blocking=True,
                        ),
                    ),
                    limitations=(
                        "This result may reflect terminology mismatch rather than absent clinical behavior.",
                    ),
                    tags=(*self.tags, domain, "reference"),
                    confidence_score=0.8,
                    clinically_relevant=True,
                    blocks_research_use=True,
                )
                findings.append(finding)
                continue

            if not candidate_detected or blocking_issue:
                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.FAIL",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"psynthea does not preserve the expected '{domain}' signal",
                    status=FindingStatus.FAIL,
                    severity=Severity.CRITICAL if psynthea_count == 0 else Severity.HIGH,
                    confidence=_confidence(synthea_count),
                    evidence_strength=_strength(synthea_count),
                    observation=(
                        f"Synthea detected expected terms '{expected_terms}' with {synthea_count} "
                        f"signal(s); psynthea detected={candidate_detected}, count={psynthea_count}, "
                        f"blocking_issue={blocking_issue}."
                    ),
                    interpretation=(
                        "The candidate output does not reproduce an explicitly demonstrated "
                        "clinical signal from the reference module."
                    ),
                    impact=(
                        "Functional clinical equivalence for this domain is not established and "
                        "downstream use may omit clinically intended events."
                    ),
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.RESTORE_SIGNAL",
                            action=(
                                f"Trace the '{domain}' module path and restore generation or export "
                                "of the configured expected signal."
                            ),
                            priority=RecommendationPriority.URGENT,
                            rationale="The reference demonstrates a signal that the candidate fails to preserve.",
                            expected_outcome="Both engines detect the configured expected clinical terms.",
                            verification=(
                                "Re-run validation and confirm expected_signal_detected_psynthea=True, "
                                "a positive psynthea_signal_count and blocking_issue=False."
                            ),
                            blocking=True,
                        ),
                    ),
                    limitations=(
                        "The rule localizes the affected domain but not the exact engine, module or exporter defect.",
                    ),
                    tags=(*self.tags, domain),
                    confidence_score=0.97,
                    clinically_relevant=True,
                    blocks_research_use=True,
                )
                statement = f"The expected '{domain}' signal is not preserved by psynthea."
            else:
                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.PASS",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Expected '{domain}' signal is preserved",
                    status=FindingStatus.PASS,
                    severity=Severity.INFO,
                    confidence=_confidence(synthea_count),
                    evidence_strength=_strength(synthea_count),
                    observation=(
                        f"Both engines detected expected terms '{expected_terms}'; Synthea count="
                        f"{synthea_count}, psynthea count={psynthea_count}."
                    ),
                    interpretation="psynthea preserves the configured module-level clinical signal.",
                    impact="No expected-signal defect is identified for this domain.",
                    evidence=refs,
                    limitations=(
                        "Presence of the signal does not establish equivalent frequency, timing or patient-level dependencies.",
                    ),
                    tags=(*self.tags, domain),
                    confidence_score=0.97,
                    clinically_relevant=True,
                    blocks_research_use=False,
                )
                statement = f"The expected '{domain}' signal is preserved by psynthea."

            findings.append(finding)
            inferences.append(
                Inference(
                    inference_id=f"{self.rule_id}.{identity}.INFERENCE",
                    statement=statement,
                    evidence=refs,
                    rationale=(
                        "The conclusion follows from paired expected-term detection flags and "
                        "domain signal counts."
                    ),
                    confidence=0.97,
                )
            )

        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


class DomainEventRetentionRule(ClinicalRule):
    """Assess whether psynthea retains a clinically plausible event volume."""

    rule_id = "CLINICAL.EVENT_RETENTION"
    domain = "clinical"
    description = "Assess domain-level retention of module-generated clinical event counts."
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("clinical", "event-volume", "module-fidelity")

    def __init__(self, thresholds: ClinicalThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, ClinicalThresholds):
            raise TypeError("thresholds must be a ClinicalThresholds instance.")
        self.thresholds = thresholds

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        if not _rows(context, "functional.clinical_signal"):
            return ApplicabilityDecision.not_evaluated(
                "No functional clinical-signal evidence was produced."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "functional.clinical_signal")
        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []

        for identity in sorted(rows):
            metrics = rows[identity]
            domain = _domain_from_identity(identity)
            reference = _integer(metrics, "synthea_signal_count")
            candidate = _integer(metrics, "psynthea_signal_count")
            refs = _refs(metrics.values())

            if reference is None or candidate is None or reference < 0 or candidate < 0:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Event retention for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason="Paired non-negative integer signal counts are required.",
                        tags=(*self.tags, domain),
                    )
                )
                continue

            if reference < self.thresholds.minimum_reference_events:
                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.NOT_APPLICABLE",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Event retention is not applicable to sparse '{domain}' reference output",
                    status=FindingStatus.NOT_APPLICABLE,
                    severity=Severity.INFO,
                    confidence=Confidence.HIGH,
                    evidence_strength=EvidenceStrength.INSUFFICIENT,
                    observation=(
                        f"The Synthea reference contains {reference} signal(s), below the "
                        f"minimum of {self.thresholds.minimum_reference_events}."
                    ),
                    interpretation="A retention ratio is not defined for an effectively absent reference signal.",
                    impact="No event-volume decision is issued for this domain.",
                    evidence=refs,
                    limitations=(
                        "A different reference seed or larger cohort may produce analyzable events.",
                    ),
                    tags=(*self.tags, domain, "sparse-reference"),
                    confidence_score=0.95,
                    clinically_relevant=False,
                    blocks_research_use=False,
                )
                findings.append(finding)
                continue

            retention = candidate / reference
            if (
                retention < self.thresholds.failure_event_retention
                or retention > self.thresholds.failure_event_overproduction
            ):
                status = FindingStatus.FAIL
                severity = Severity.HIGH
                blocking = True
                interpretation = (
                    "psynthea clinical event volume falls outside the configured failure "
                    "interval relative to Synthea."
                )
            elif (
                retention < self.thresholds.warning_event_retention
                or retention > self.thresholds.warning_event_overproduction
            ):
                status = FindingStatus.WARNING
                severity = Severity.MODERATE
                blocking = False
                interpretation = (
                    "psynthea shows a potentially meaningful reduction or excess in "
                    "clinical event volume."
                )
            else:
                status = FindingStatus.PASS
                severity = Severity.INFO
                blocking = False
                interpretation = (
                    "psynthea event volume lies inside the configured two-sided "
                    "clinical-retention interval."
                )

            finding = InterpretationFinding(
                finding_id=f"{self.rule_id}.{identity}.{status.value.upper()}",
                rule_id=self.rule_id,
                domain=self.domain,
                title=f"Clinical event retention for '{domain}' is {status.value}",
                status=status,
                severity=severity,
                confidence=_confidence(reference),
                evidence_strength=_strength(reference),
                observation=(
                    f"Synthea count={reference}, psynthea count={candidate}, "
                    f"retention={retention:.3f}."
                ),
                interpretation=interpretation,
                impact=(
                    "Clinically intended output may be materially under- or over-generated."
                    if status is FindingStatus.FAIL
                    else (
                        "The reduction should be reviewed before claiming event-volume equivalence."
                        if status is FindingStatus.WARNING
                        else "No material event-volume loss is identified by this policy threshold."
                    )
                ),
                evidence=refs,
                recommendations=(
                    (
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.INVESTIGATE",
                            action=f"Investigate abnormal generation volume for '{domain}' events in psynthea.",
                            priority=(
                                RecommendationPriority.URGENT
                                if status is FindingStatus.FAIL
                                else RecommendationPriority.HIGH
                            ),
                            rationale=(
                                f"Observed ratio {retention:.3f} falls outside the configured "
                                "two-sided event-volume tolerance."
                            ),
                            expected_outcome="The event-retention ratio meets the configured tolerance or a justified model difference is documented.",
                            verification="Re-run the same seeded cohorts and recompute paired domain signal counts.",
                            blocking=blocking,
                        ),
                    )
                    if status is not FindingStatus.PASS
                    else ()
                ),
                limitations=(
                    "This count ratio is descriptive and does not adjust for patient mix, repeated events or timing.",
                ),
                tags=(*self.tags, domain),
                confidence_score=0.95,
                clinically_relevant=status is not FindingStatus.PASS,
                blocks_research_use=blocking,
            )
            findings.append(finding)
            inferences.append(
                Inference(
                    inference_id=f"{self.rule_id}.{identity}.INFERENCE",
                    statement=f"The '{domain}' event-retention ratio is {retention:.3f}.",
                    evidence=refs,
                    rationale="The ratio is computed from paired module-level signal counts.",
                    confidence=0.95,
                )
            )

        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


class ClinicalCodeOverlapRule(ClinicalRule):
    """Interpret code-set and frequency-distribution concordance by domain."""

    rule_id = "CLINICAL.CODE_OVERLAP"
    domain = "clinical"
    description = "Assess clinical code-set overlap and distributional concordance by domain."
    required_stages = (PipelineStage.FUNCTIONAL_VALIDATION,)
    tags = ("clinical", "codes", "distributional-fidelity")

    def __init__(self, thresholds: ClinicalThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, ClinicalThresholds):
            raise TypeError("thresholds must be a ClinicalThresholds instance.")
        self.thresholds = thresholds

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        if not _rows(context, "functional.distributional_similarity"):
            return ApplicabilityDecision.not_evaluated(
                "No functional distributional-similarity evidence was produced."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "functional.distributional_similarity")
        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []

        for identity in sorted(rows):
            metrics = rows[identity]
            domain = _domain_from_identity(identity)
            synthea_total = _integer(metrics, "synthea_total")
            psynthea_total = _integer(metrics, "psynthea_total")
            shared = _integer(metrics, "shared_code_count")
            synthea_only = _integer(metrics, "synthea_only_code_count")
            psynthea_only = _integer(metrics, "psynthea_only_code_count")
            jaccard = _number(metrics, "jaccard_similarity")
            overlap = _number(metrics, "overlap_coefficient")
            jsd = _number(metrics, "jensen_shannon_divergence")
            valid = _boolean(metrics, "valid_for_distributional_comparison")
            blocking_issue = _boolean(metrics, "blocking_issue")
            refs = _refs(metrics.values())

            required_values = (
                synthea_total,
                psynthea_total,
                shared,
                synthea_only,
                psynthea_only,
                jaccard,
                overlap,
                jsd,
            )
            if any(value is None for value in required_values) or valid is None or blocking_issue is None:
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical code overlap for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason="The distributional-similarity row is incomplete or malformed.",
                        tags=(*self.tags, domain),
                        blocking=True,
                    )
                )
                continue

            assert synthea_total is not None
            assert psynthea_total is not None
            assert shared is not None
            assert synthea_only is not None
            assert psynthea_only is not None
            assert jaccard is not None
            assert overlap is not None
            assert jsd is not None

            if any(value < 0 for value in (synthea_total, psynthea_total, shared, synthea_only, psynthea_only)):
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical code overlap for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason="Counts used for code overlap cannot be negative.",
                        tags=(*self.tags, domain),
                        blocking=True,
                    )
                )
                continue
            if not all(0.0 <= value <= 1.0 for value in (jaccard, overlap, jsd)):
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical code overlap for '{domain}' is inconclusive",
                        metrics=metrics,
                        reason="Jaccard, overlap and Jensen-Shannon metrics must lie in [0, 1].",
                        tags=(*self.tags, domain),
                        blocking=True,
                    )
                )
                continue

            synthea_unique = shared + synthea_only
            psynthea_unique = shared + psynthea_only
            union = shared + synthea_only + psynthea_only
            expected_jaccard = shared / union if union else 1.0
            minimum_unique = min(synthea_unique, psynthea_unique)
            expected_overlap = shared / minimum_unique if minimum_unique else 1.0
            consistency_tolerance = 1e-9
            if (
                synthea_total < synthea_unique
                or psynthea_total < psynthea_unique
                or abs(jaccard - expected_jaccard) > consistency_tolerance
                or abs(overlap - expected_overlap) > consistency_tolerance
            ):
                findings.append(
                    _inconclusive_finding(
                        rule=self,
                        identity=identity,
                        title=f"Clinical code overlap for '{domain}' is internally inconsistent",
                        metrics=metrics,
                        reason=(
                            "Code counts, event totals and reported Jaccard/overlap values "
                            "do not describe the same underlying code sets."
                        ),
                        tags=(*self.tags, domain, "contradiction"),
                        blocking=True,
                    )
                )
                continue

            if not valid or blocking_issue:
                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.INCONCLUSIVE",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Clinical code overlap for '{domain}' cannot be compared",
                    status=FindingStatus.INCONCLUSIVE,
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    evidence_strength=EvidenceStrength.STRONG,
                    observation=(
                        f"valid_for_distributional_comparison={valid}, "
                        f"blocking_issue={blocking_issue}."
                    ),
                    interpretation="The functional layer does not authorize a distributional code comparison.",
                    impact="No clinical code-overlap conclusion is issued for this domain.",
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.RESOLVE_BLOCK",
                            action="Resolve the domain-level functional comparison block.",
                            priority=RecommendationPriority.URGENT,
                            rationale="Clinical distribution metrics are unsafe when the source comparison is blocked.",
                            expected_outcome="The domain is explicitly valid for distributional comparison.",
                            verification=(
                                "Confirm valid_for_distributional_comparison=True and blocking_issue=False."
                            ),
                            blocking=True,
                        ),
                    ),
                    limitations=(
                        "The blocking signal does not identify whether the defect arose during simulation or export.",
                    ),
                    tags=(*self.tags, domain),
                    confidence_score=0.95,
                    clinically_relevant=True,
                    blocks_research_use=True,
                )
                findings.append(finding)
                continue

            failure = (
                jaccard < self.thresholds.failure_jaccard_similarity
                or overlap < self.thresholds.failure_overlap_coefficient
                or jsd > self.thresholds.maximum_failure_js_divergence
            )
            warning = (
                jaccard < self.thresholds.warning_jaccard_similarity
                or overlap < self.thresholds.warning_overlap_coefficient
                or jsd > self.thresholds.maximum_warning_js_divergence
            )

            if failure:
                status = FindingStatus.FAIL
                severity = Severity.HIGH
                blocking = True
                interpretation = "The candidate shows materially poor clinical code-set or frequency concordance."
            elif warning:
                status = FindingStatus.WARNING
                severity = Severity.MODERATE
                blocking = False
                interpretation = "The domain shows partial clinical code concordance that warrants review."
            else:
                status = FindingStatus.PASS
                severity = Severity.INFO
                blocking = False
                interpretation = "The domain meets the configured code-set and distributional concordance criteria."

            finding = InterpretationFinding(
                finding_id=f"{self.rule_id}.{identity}.{status.value.upper()}",
                rule_id=self.rule_id,
                domain=self.domain,
                title=f"Clinical code concordance for '{domain}' is {status.value}",
                status=status,
                severity=severity,
                confidence=Confidence.VERY_HIGH,
                evidence_strength=EvidenceStrength.VERY_STRONG,
                observation=(
                    f"Jaccard={jaccard:.3f}, overlap={overlap:.3f}, JSD={jsd:.3f}, "
                    f"shared={shared}, Synthea-only={synthea_only}, psynthea-only={psynthea_only}."
                ),
                interpretation=interpretation,
                impact=(
                    "Clinically represented concepts or their relative frequencies may be materially different."
                    if status is FindingStatus.FAIL
                    else (
                        "Differences should be reviewed before declaring domain-level clinical fidelity."
                        if status is FindingStatus.WARNING
                        else "No material code-level discrepancy is identified by the configured policy."
                    )
                ),
                evidence=refs,
                recommendations=(
                    (
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.REVIEW_CODES",
                            action=f"Review Synthea-only and psynthea-only '{domain}' codes and their frequencies.",
                            priority=(
                                RecommendationPriority.URGENT
                                if status is FindingStatus.FAIL
                                else RecommendationPriority.HIGH
                            ),
                            rationale="The observed overlap or divergence falls outside configured tolerances.",
                            expected_outcome="Code-set overlap and Jensen-Shannon divergence meet the approved thresholds or justified mappings are documented.",
                            verification="Recompute code-level similarity after correcting mappings or generation behavior.",
                            blocking=blocking,
                        ),
                    )
                    if status is not FindingStatus.PASS
                    else ()
                ),
                limitations=(
                    "Code overlap does not prove semantic equivalence when coding systems, granularity or mappings differ.",
                    "Aggregate code distributions do not test patient-level temporal ordering or comorbidity relationships.",
                ),
                tags=(*self.tags, domain),
                confidence_score=0.98,
                clinically_relevant=status is not FindingStatus.PASS,
                blocks_research_use=blocking,
            )
            findings.append(finding)
            inferences.append(
                Inference(
                    inference_id=f"{self.rule_id}.{identity}.INFERENCE",
                    statement=(
                        f"The '{domain}' domain has Jaccard={jaccard:.3f}, "
                        f"overlap={overlap:.3f} and JSD={jsd:.3f}."
                    ),
                    evidence=refs,
                    rationale="These metrics jointly describe code-set and frequency-distribution concordance.",
                    confidence=0.98,
                )
            )

        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


DEFAULT_CLINICAL_RULES: Final = (
    ClinicalSignalPreservationRule(),
    DomainEventRetentionRule(),
    ClinicalCodeOverlapRule(),
)