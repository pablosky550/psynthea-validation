"""Deterministic interpretation rules for Spanish SNS adaptation evidence.

These rules interpret the descriptive indicators emitted by
``validate_spanish_adaptation``.  They evaluate whether psynthea exposes explicit
signals of primary care, referral pathways, healthcare utilisation and clinical
context linkage that are expected in an adaptation to the Spanish National Health
System (SNS).

Scientific boundaries
---------------------

* The rules never claim that the Spanish adaptation is *better* than Synthea
  without a paired reference or an external benchmark.
* Pattern-derived indicators are treated as descriptive proxies, not validated
  healthcare classifications.
* A legitimate observed zero is distinct from unavailable evidence.
* Fractions are checked against numerators and denominators before interpretation.
* Thresholds are explicit policy parameters and never hidden in rule bodies.
* PASS means that the configured representation criterion is met; it does not
  establish clinical realism, causal coherence or compliance with SNS guidelines.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isclose, isfinite
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
    Inference,
    InterpretationRule,
    PipelineStage,
    RuleContext,
    RuleOutcome,
    ValidationDimension,
)

__all__ = [
    "ClinicalContextLinkageRule",
    "DEFAULT_SPANISH_ADAPTATION_RULES",
    "HealthcareFlowRepresentationRule",
    "PrimaryCareRepresentationRule",
    "ReferralPathwayRepresentationRule",
    "SpanishAdaptationEvidenceIntegrityRule",
    "SpanishAdaptationRule",
    "SpanishAdaptationThresholds",
]


@dataclass(frozen=True, slots=True)
class SpanishAdaptationThresholds:
    """Auditable policy thresholds for descriptive SNS representation."""

    minimum_primary_care_fraction: float = 0.05
    warning_primary_care_fraction: float = 0.15
    minimum_primary_care_patient_fraction: float = 0.05
    warning_primary_care_patient_fraction: float = 0.20
    minimum_referral_count: int = 2
    minimum_evaluable_denominator: int = 20
    minimum_referral_evaluable_records: int = 20
    minimum_patient_encounter_fraction: float = 0.80
    warning_patient_encounter_fraction: float = 0.95
    minimum_context_linkage_fraction: float = 0.80
    warning_context_linkage_fraction: float = 0.95
    fraction_tolerance: float = 1e-9

    def __post_init__(self) -> None:
        probability_fields = (
            "minimum_primary_care_fraction",
            "warning_primary_care_fraction",
            "minimum_primary_care_patient_fraction",
            "warning_primary_care_patient_fraction",
            "minimum_patient_encounter_fraction",
            "warning_patient_encounter_fraction",
            "minimum_context_linkage_fraction",
            "warning_context_linkage_fraction",
        )
        for name in probability_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric.")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1.")

        if isinstance(self.minimum_referral_count, bool) or not isinstance(
            self.minimum_referral_count, int
        ):
            raise TypeError("minimum_referral_count must be an integer.")
        if self.minimum_referral_count < 1:
            raise ValueError("minimum_referral_count must be at least one.")

        for name in ("minimum_evaluable_denominator", "minimum_referral_evaluable_records"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")
            if value < 1:
                raise ValueError(f"{name} must be at least one.")

        if isinstance(self.fraction_tolerance, bool) or not isinstance(
            self.fraction_tolerance, (int, float)
        ):
            raise TypeError("fraction_tolerance must be numeric.")
        if not isfinite(float(self.fraction_tolerance)) or self.fraction_tolerance < 0:
            raise ValueError("fraction_tolerance must be finite and non-negative.")

        ordered_pairs = (
            ("minimum_primary_care_fraction", "warning_primary_care_fraction"),
            (
                "minimum_primary_care_patient_fraction",
                "warning_primary_care_patient_fraction",
            ),
            ("minimum_patient_encounter_fraction", "warning_patient_encounter_fraction"),
            ("minimum_context_linkage_fraction", "warning_context_linkage_fraction"),
        )
        for minimum_name, warning_name in ordered_pairs:
            if getattr(self, minimum_name) > getattr(self, warning_name):
                raise ValueError(f"{minimum_name} must not exceed {warning_name}.")


DEFAULT_THRESHOLDS: Final = SpanishAdaptationThresholds()


class SpanishAdaptationRule(InterpretationRule):
    """Base class for rules interpreting Spanish-adaptation indicators."""

    dimension = ValidationDimension.SPANISH_ADAPTATION


def _column(value: object) -> str | None:
    metadata = getattr(value, "metadata", {})
    column = metadata.get("column") if isinstance(metadata, Mapping) else None
    return column if isinstance(column, str) else None


def _row_identity(value: object) -> str | None:
    metadata = getattr(value, "metadata", {})
    identity = metadata.get("row_identity") if isinstance(metadata, Mapping) else None
    return identity if isinstance(identity, str) else None


def _indicator_from_identity(identity: str) -> str:
    return identity.split(".", 1)[1] if "." in identity else identity


def _rows(context: RuleContext, table: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = defaultdict(dict)
    needle = f".spanish.{table}."
    for value in context.evidence:
        if needle not in value.metric_id:
            continue
        identity = _row_identity(value)
        column = _column(value)
        if identity is None or column is None:
            continue
        if column in grouped[identity]:
            raise ValueError(
                f"Duplicate Spanish-adaptation evidence for table {table!r}, "
                f"row {identity!r}, column {column!r}."
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


def _boolean(metrics: Mapping[str, object], column: str) -> bool | None:
    value = _available_value(metrics, column)
    return value if isinstance(value, bool) else None


def _number(metrics: Mapping[str, object], column: str) -> float | None:
    value = _available_value(metrics, column)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if isfinite(result) else None


def _integer(metrics: Mapping[str, object], column: str) -> int | None:
    value = _number(metrics, column)
    if value is None or not value.is_integer():
        return None
    return int(value)


def _fraction(metrics: Mapping[str, object]) -> float | None:
    value = _number(metrics, "fraction")
    if value is None or not 0.0 <= value <= 1.0:
        return None
    return value


def _strength(denominator: int | None) -> EvidenceStrength:
    if denominator is None or denominator <= 0:
        return EvidenceStrength.INSUFFICIENT
    if denominator < 20:
        return EvidenceStrength.WEAK
    if denominator < 100:
        return EvidenceStrength.MODERATE
    if denominator < 1000:
        return EvidenceStrength.STRONG
    return EvidenceStrength.VERY_STRONG


def _confidence(denominator: int | None, *, proxy: bool = True) -> Confidence:
    if denominator is None or denominator <= 0:
        return Confidence.LOW
    if denominator < 20:
        return Confidence.MODERATE
    if proxy:
        return Confidence.HIGH
    return Confidence.VERY_HIGH


def _confidence_score(denominator: int | None, *, proxy: bool = True) -> float:
    """Return a conservative numeric confidence score aligned with sample size."""

    if denominator is None or denominator <= 0:
        return 0.25
    if denominator < 20:
        return 0.50
    if denominator < 100:
        return 0.72 if proxy else 0.80
    if denominator < 1000:
        return 0.86 if proxy else 0.92
    return 0.92 if proxy else 0.97


def _inconclusive(
    *,
    rule: SpanishAdaptationRule,
    identity: str,
    title: str,
    metrics: Mapping[str, object],
    reason: str,
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
        interpretation=(
            "The Spanish-adaptation indicator cannot support a defensible conclusion."
        ),
        impact=(
            "Evaluation of this SNS representation domain is blocked until the indicator is corrected."
            if blocking
            else "No positive or negative conclusion is issued for this indicator."
        ),
        evidence=_refs(metrics.values()),
        recommendations=(
            Recommendation(
                recommendation_id=f"{rule.rule_id}.{identity}.REPAIR",
                action="Regenerate and validate the affected Spanish-adaptation indicator.",
                priority=(
                    RecommendationPriority.URGENT
                    if blocking
                    else RecommendationPriority.HIGH
                ),
                rationale="Unavailable or internally inconsistent indicators must not be interpreted.",
                expected_outcome="The indicator contains coherent availability, count and fraction fields.",
                verification=(
                    "Re-run evidence collection and verify that numerator, denominator, fraction "
                    "and availability are mutually consistent."
                ),
                blocking=blocking,
            ),
        ),
        limitations=(
            "This finding identifies an evidence-quality defect, not its implementation root cause.",
        ),
        tags=(*rule.tags, "inconclusive"),
        confidence_score=0.4,
        clinically_relevant=True,
        blocks_research_use=blocking,
    )


def _validate_indicator(
    metrics: Mapping[str, object], thresholds: SpanishAdaptationThresholds
) -> str | None:
    available = _boolean(metrics, "available")
    numerator = _integer(metrics, "numerator")
    denominator = _integer(metrics, "denominator")
    fraction = _number(metrics, "fraction")
    value = _number(metrics, "value")

    if available is None:
        return "The indicator availability flag is missing or non-boolean."
    if numerator is None or denominator is None:
        return "Numerator and denominator must be available non-negative integers."
    if numerator < 0 or denominator < 0:
        return "Numerator and denominator must be non-negative."
    if numerator > denominator:
        return "Numerator cannot exceed denominator."
    if value is not None and not isclose(
        value, float(numerator), rel_tol=0.0, abs_tol=thresholds.fraction_tolerance
    ):
        return "Indicator value is inconsistent with its numerator."

    if denominator == 0:
        if fraction is not None:
            return "Fraction must be unavailable when denominator is zero."
        if available:
            return "An indicator with denominator zero cannot be marked available."
        return None

    if not available:
        return "A positive denominator is inconsistent with available=False."
    if fraction is None or not 0.0 <= fraction <= 1.0:
        return "A positive denominator requires a finite fraction in [0, 1]."
    expected = numerator / denominator
    if not isclose(
        fraction,
        expected,
        rel_tol=0.0,
        abs_tol=thresholds.fraction_tolerance,
    ):
        return (
            f"Fraction {fraction:.12g} is inconsistent with numerator/denominator "
            f"({expected:.12g})."
        )
    return None


def _minimum_denominator_reason(
    metrics: Mapping[str, object],
    thresholds: SpanishAdaptationThresholds,
) -> str | None:
    denominator = _integer(metrics, "denominator")
    if denominator is None:
        return "The indicator denominator is unavailable or invalid."
    if denominator < thresholds.minimum_evaluable_denominator:
        return (
            f"The indicator denominator ({denominator}) is below the configured minimum "
            f"for a conclusive representation decision ({thresholds.minimum_evaluable_denominator})."
        )
    return None


class SpanishAdaptationEvidenceIntegrityRule(SpanishAdaptationRule):
    """Validate internal coherence of all Spanish-adaptation indicators."""

    rule_id = "SPANISH.EVIDENCE_INTEGRITY"
    domain = "spanish_adaptation"
    description = "Validate availability, count and fraction coherence of SNS indicators."
    required_stages = (PipelineStage.SPANISH_ADAPTATION,)
    tags = ("spanish-adaptation", "evidence-quality", "research-safety")

    def __init__(self, thresholds: SpanishAdaptationThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, SpanishAdaptationThresholds):
            raise TypeError("thresholds must be a SpanishAdaptationThresholds instance.")
        self.thresholds = thresholds

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        if not _rows(context, "summary"):
            return ApplicabilityDecision.not_evaluated(
                "No Spanish-adaptation summary evidence was produced."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "summary")
        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []
        invalid: list[tuple[str, Mapping[str, object], str]] = []

        for identity in sorted(rows):
            reason = _validate_indicator(rows[identity], self.thresholds)
            if reason is not None:
                invalid.append((identity, rows[identity], reason))

        # The summary is a denormalized mirror of the four domain tables.  A
        # mismatch indicates corruption or stale evidence and must block
        # interpretation even when each row is arithmetically valid in isolation.
        domain_tables = ("primary_care", "referrals", "healthcare_flow", "clinical_context")
        domain_rows: dict[str, Mapping[str, object]] = {}
        for table_name in domain_tables:
            for identity, metrics in _rows(context, table_name).items():
                if identity in domain_rows:
                    invalid.append((identity, metrics, "The same indicator appears in multiple domain tables."))
                else:
                    domain_rows[identity] = metrics

        summary_ids = set(rows)
        domain_ids = set(domain_rows)
        for identity in sorted(summary_ids ^ domain_ids):
            metrics = rows.get(identity) or domain_rows.get(identity) or {}
            invalid.append((identity, metrics, "The summary and domain tables contain different indicator sets."))

        for identity in sorted(summary_ids & domain_ids):
            summary_metrics = rows[identity]
            source_metrics = domain_rows[identity]
            for column in ("value", "numerator", "denominator", "fraction", "available", "evidence"):
                left = _available_value(summary_metrics, column)
                right = _available_value(source_metrics, column)
                if isinstance(left, float) and isinstance(right, float):
                    equal = isclose(left, right, rel_tol=0.0, abs_tol=self.thresholds.fraction_tolerance)
                else:
                    equal = left == right
                if not equal:
                    invalid.append((identity, summary_metrics, f"Summary column {column!r} does not match its domain-table value."))
                    break

        if not invalid:
            all_metrics = tuple(
                metric for row in rows.values() for metric in row.values()
            )
            refs = _refs(all_metrics[:1])
            finding = InterpretationFinding(
                finding_id=f"{self.rule_id}.PASS",
                rule_id=self.rule_id,
                domain=self.domain,
                title="Spanish-adaptation indicators are internally coherent",
                status=FindingStatus.PASS,
                severity=Severity.INFO,
                confidence=Confidence.VERY_HIGH,
                evidence_strength=EvidenceStrength.VERY_STRONG,
                observation=f"All {len(rows)} summary indicators satisfy count and fraction invariants.",
                interpretation="The descriptive SNS indicators are structurally safe to interpret.",
                impact="Downstream Spanish-adaptation rules may evaluate their respective domains.",
                evidence=refs,
                limitations=(
                    "Internal coherence does not establish validity of the underlying text-pattern classifiers.",
                ),
                tags=self.tags,
                confidence_score=0.99,
                clinically_relevant=False,
                blocks_research_use=False,
            )
            inference = Inference(
                inference_id=f"{self.rule_id}.ALL_COHERENT",
                statement="All Spanish-adaptation indicators satisfy their arithmetic invariants.",
                evidence=refs,
                rationale="Every summary row has coherent availability, numerator, denominator and fraction values.",
                confidence=0.99,
            )
            return RuleOutcome(findings=(finding,), inferences=(inference,))

        grouped_invalid: dict[str, tuple[Mapping[str, object], list[str]]] = {}
        for identity, metrics, reason in invalid:
            if identity not in grouped_invalid:
                grouped_invalid[identity] = (metrics, [reason])
            elif reason not in grouped_invalid[identity][1]:
                grouped_invalid[identity][1].append(reason)

        for identity in sorted(grouped_invalid):
            metrics, reasons = grouped_invalid[identity]
            findings.append(
                _inconclusive(
                    rule=self,
                    identity=identity,
                    title=f"Spanish indicator '{_indicator_from_identity(identity)}' is inconsistent",
                    metrics=metrics,
                    reason="; ".join(reasons),
                    blocking=True,
                )
            )
        return RuleOutcome(findings=tuple(findings))


class PrimaryCareRepresentationRule(SpanishAdaptationRule):
    """Assess explicit primary-care representation in the generated cohort."""

    rule_id = "SPANISH.PRIMARY_CARE"
    domain = "spanish_adaptation"
    description = "Assess primary-care encounter and patient coverage proxies."
    required_stages = (PipelineStage.SPANISH_ADAPTATION,)
    tags = ("spanish-adaptation", "primary-care", "sns")

    def __init__(self, thresholds: SpanishAdaptationThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, SpanishAdaptationThresholds):
            raise TypeError("thresholds must be a SpanishAdaptationThresholds instance.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "primary_care"):
            return ApplicabilityDecision.not_evaluated("No primary-care indicators were produced.")
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "primary_care")
        by_indicator = {_indicator_from_identity(key): (key, value) for key, value in rows.items()}
        required = ("primary_care_encounters", "patients_with_primary_care")
        missing = [name for name in required if name not in by_indicator]
        if missing:
            metric_values = tuple(metric for row in rows.values() for metric in row.values())
            return RuleOutcome(
                findings=(
                    _inconclusive(
                        rule=self,
                        identity="PRIMARY_CARE",
                        title="Primary-care representation is inconclusive",
                        metrics={str(index): value for index, value in enumerate(metric_values)},
                        reason=f"Missing required primary-care indicators: {missing}.",
                        blocking=True,
                    ),
                )
            )

        encounter_identity, encounter_metrics = by_indicator["primary_care_encounters"]
        patient_identity, patient_metrics = by_indicator["patients_with_primary_care"]
        for identity, metrics in (
            (encounter_identity, encounter_metrics),
            (patient_identity, patient_metrics),
        ):
            reason = _validate_indicator(metrics, self.thresholds)
            if reason is not None:
                return RuleOutcome(
                    findings=(
                        _inconclusive(
                            rule=self,
                            identity=identity,
                            title="Primary-care representation is inconclusive",
                            metrics=metrics,
                            reason=reason,
                            blocking=True,
                        ),
                    )
                )

        for identity, metrics in ((encounter_identity, encounter_metrics), (patient_identity, patient_metrics)):
            sample_reason = _minimum_denominator_reason(metrics, self.thresholds)
            if sample_reason is not None:
                return RuleOutcome(
                    findings=(
                        _inconclusive(
                            rule=self,
                            identity=identity,
                            title="Primary-care representation is sample-size limited",
                            metrics=metrics,
                            reason=sample_reason,
                            blocking=False,
                        ),
                    )
                )

        encounter_fraction = _fraction(encounter_metrics)
        patient_fraction = _fraction(patient_metrics)
        encounter_denominator = _integer(encounter_metrics, "denominator")
        patient_denominator = _integer(patient_metrics, "denominator")
        assert encounter_fraction is not None and patient_fraction is not None
        refs = _refs((*encounter_metrics.values(), *patient_metrics.values()))

        if (
            encounter_fraction < self.thresholds.minimum_primary_care_fraction
            or patient_fraction < self.thresholds.minimum_primary_care_patient_fraction
        ):
            status = FindingStatus.FAIL
            severity = Severity.HIGH
            blocks = True
            interpretation = "Primary-care representation is below the configured minimum criterion."
            action = "Review encounter classification and the module pathway that should generate primary-care activity."
        elif (
            encounter_fraction < self.thresholds.warning_primary_care_fraction
            or patient_fraction < self.thresholds.warning_primary_care_patient_fraction
        ):
            status = FindingStatus.WARNING
            severity = Severity.MODERATE
            blocks = False
            interpretation = "Primary care is represented, but coverage is limited relative to the configured target."
            action = "Review whether primary-care encounter frequency and patient coverage match the intended SNS scenario."
        else:
            status = FindingStatus.PASS
            severity = Severity.INFO
            blocks = False
            interpretation = "The cohort contains explicit primary-care activity meeting the configured criterion."
            action = None

        recommendations: tuple[Recommendation, ...] = ()
        if action is not None:
            recommendations = (
                Recommendation(
                    recommendation_id=f"{self.rule_id}.REVIEW",
                    action=action,
                    priority=(
                        RecommendationPriority.URGENT
                        if blocks
                        else RecommendationPriority.HIGH
                    ),
                    rationale="Primary care is a defining feature of the intended Spanish care pathway.",
                    expected_outcome="Primary-care encounter and patient fractions meet the configured target.",
                    verification=(
                        "Re-run Spanish adaptation validation and verify both primary-care fractions "
                        "against the declared thresholds."
                    ),
                    blocking=blocks,
                ),
            )

        finding = InterpretationFinding(
            finding_id=f"{self.rule_id}.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Primary-care representation in psynthea",
            status=status,
            severity=severity,
            confidence=min(
                (_confidence(encounter_denominator), _confidence(patient_denominator)),
                key=lambda item: list(Confidence).index(item),
            ),
            evidence_strength=min(
                (_strength(encounter_denominator), _strength(patient_denominator)),
                key=lambda item: list(EvidenceStrength).index(item),
            ),
            observation=(
                f"Primary-care encounters={encounter_fraction:.3%}; patients with primary care="
                f"{patient_fraction:.3%}."
            ),
            interpretation=interpretation,
            impact=(
                "The intended SNS adaptation lacks adequate primary-care representation."
                if blocks
                else "The result informs whether the intended primary-care pathway is visibly represented."
            ),
            evidence=refs,
            recommendations=recommendations,
            limitations=(
                "The indicators are text-pattern proxies and do not prove organisational or guideline-level fidelity.",
                "No claim of improvement over Synthea is made without paired reference evidence.",
            ),
            tags=self.tags,
            confidence_score=min(
                _confidence_score(encounter_denominator),
                _confidence_score(patient_denominator),
            ),
            clinically_relevant=True,
            blocks_research_use=blocks,
        )
        inference = Inference(
            inference_id=f"{self.rule_id}.REPRESENTATION",
            statement=interpretation,
            evidence=refs,
            rationale="The decision combines encounter-level and patient-level primary-care coverage.",
            confidence=min(
                _confidence_score(encounter_denominator),
                _confidence_score(patient_denominator),
            ),
        )
        return RuleOutcome(findings=(finding,), inferences=(inference,))


class ReferralPathwayRepresentationRule(SpanishAdaptationRule):
    """Assess whether referral or specialist-transition signals are represented."""

    rule_id = "SPANISH.REFERRALS"
    domain = "spanish_adaptation"
    description = "Assess descriptive referral and specialist-transition signals."
    required_stages = (PipelineStage.SPANISH_ADAPTATION,)
    tags = ("spanish-adaptation", "referrals", "care-pathway")

    def __init__(self, thresholds: SpanishAdaptationThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, SpanishAdaptationThresholds):
            raise TypeError("thresholds must be a SpanishAdaptationThresholds instance.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "referrals"):
            return ApplicabilityDecision.not_evaluated("No referral indicators were produced.")
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "referrals")
        available_rows: list[tuple[str, Mapping[str, object]]] = []
        invalid_findings: list[InterpretationFinding] = []
        for identity in sorted(rows):
            metrics = rows[identity]
            available = _boolean(metrics, "available")
            if available is False and _integer(metrics, "denominator") == 0:
                continue
            reason = _validate_indicator(metrics, self.thresholds)
            if reason is not None:
                invalid_findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title="Referral representation is inconclusive",
                        metrics=metrics,
                        reason=reason,
                        blocking=False,
                    )
                )
            else:
                available_rows.append((identity, metrics))

        if invalid_findings:
            return RuleOutcome(findings=tuple(invalid_findings))
        if not available_rows:
            return RuleOutcome(
                findings=(
                    _inconclusive(
                        rule=self,
                        identity="REFERRALS",
                        title="Referral representation was not evaluable",
                        metrics={
                            str(index): metric
                            for index, metric in enumerate(
                                metric for row in rows.values() for metric in row.values()
                            )
                        },
                        reason="Neither encounters nor procedures provided an evaluable referral indicator.",
                        blocking=False,
                    ),
                )
            )

        total = sum(_integer(metrics, "numerator") or 0 for _, metrics in available_rows)
        evaluable_records = sum(_integer(metrics, "denominator") or 0 for _, metrics in available_rows)
        refs = _refs(metric for _, row in available_rows for metric in row.values())

        if evaluable_records < self.thresholds.minimum_referral_evaluable_records:
            return RuleOutcome(
                findings=(
                    _inconclusive(
                        rule=self,
                        identity="REFERRALS_SAMPLE",
                        title="Referral representation is sample-size limited",
                        metrics={
                            str(index): metric
                            for index, metric in enumerate(
                                metric for _, row in available_rows for metric in row.values()
                            )
                        },
                        reason=(
                            f"Only {evaluable_records} encounter/procedure records were evaluable; "
                            f"at least {self.thresholds.minimum_referral_evaluable_records} are required."
                        ),
                        blocking=False,
                    ),
                )
            )

        if total >= self.thresholds.minimum_referral_count:
            status = FindingStatus.PASS
            severity = Severity.INFO
            interpretation = "Multiple explicit referral or specialist-transition proxies are represented."
            recommendations: tuple[Recommendation, ...] = ()
        else:
            status = FindingStatus.WARNING
            severity = Severity.MODERATE
            interpretation = (
                "Referral-pathway evidence is absent or too sparse for a positive representation conclusion."
            )
            recommendations = (
                Recommendation(
                    recommendation_id=f"{self.rule_id}.REVIEW",
                    action="Review whether referral pathways are expected for this module, seed and cohort size.",
                    priority=RecommendationPriority.MEDIUM,
                    rationale="A zero referral count may be valid for some modules but may indicate missing SNS pathway logic.",
                    expected_outcome="Referral behavior is either demonstrated or explicitly documented as non-applicable.",
                    verification="Validate the relevant module path and re-run the referral indicators on an adequately sized cohort.",
                    blocking=False,
                ),
            )

        finding = InterpretationFinding(
            finding_id=f"{self.rule_id}.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Referral-pathway representation in psynthea",
            status=status,
            severity=severity,
            confidence=_confidence(evaluable_records),
            evidence_strength=_strength(evaluable_records),
            observation=(f"Detected {total} referral-like record(s) among {evaluable_records} "
                         "evaluable encounter/procedure records."),
            interpretation=interpretation,
            impact="The result describes visibility of referral pathways but does not validate their clinical appropriateness.",
            evidence=refs,
            recommendations=recommendations,
            limitations=(
                "Referral detection is based on text-pattern proxies.",
                "Absence of referrals is not automatically a failure because applicability depends on module and cohort context.",
            ),
            tags=self.tags,
            confidence_score=_confidence_score(evaluable_records),
            clinically_relevant=True,
            blocks_research_use=False,
        )
        return RuleOutcome(findings=(finding,))


class HealthcareFlowRepresentationRule(SpanishAdaptationRule):
    """Assess patient coverage and describe emergency/inpatient utilisation."""

    rule_id = "SPANISH.HEALTHCARE_FLOW"
    domain = "spanish_adaptation"
    description = "Assess encounter coverage and contextual healthcare-flow signals."
    required_stages = (PipelineStage.SPANISH_ADAPTATION,)
    tags = ("spanish-adaptation", "healthcare-flow", "utilisation")

    def __init__(self, thresholds: SpanishAdaptationThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, SpanishAdaptationThresholds):
            raise TypeError("thresholds must be a SpanishAdaptationThresholds instance.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "healthcare_flow"):
            return ApplicabilityDecision.not_evaluated("No healthcare-flow indicators were produced.")
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "healthcare_flow")
        by_indicator = {_indicator_from_identity(key): (key, row) for key, row in rows.items()}
        if "patients_with_encounters" not in by_indicator:
            values = tuple(metric for row in rows.values() for metric in row.values())
            return RuleOutcome(
                findings=(
                    _inconclusive(
                        rule=self,
                        identity="HEALTHCARE_FLOW",
                        title="Healthcare-flow representation is inconclusive",
                        metrics={str(i): value for i, value in enumerate(values)},
                        reason="The patients_with_encounters indicator is missing.",
                        blocking=True,
                    ),
                )
            )

        identity, coverage_metrics = by_indicator["patients_with_encounters"]
        reason = _validate_indicator(coverage_metrics, self.thresholds)
        if reason is not None:
            return RuleOutcome(
                findings=(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title="Healthcare-flow representation is inconclusive",
                        metrics=coverage_metrics,
                        reason=reason,
                        blocking=True,
                    ),
                )
            )

        sample_reason = _minimum_denominator_reason(coverage_metrics, self.thresholds)
        if sample_reason is not None:
            return RuleOutcome(
                findings=(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title="Healthcare-flow representation is sample-size limited",
                        metrics=coverage_metrics,
                        reason=sample_reason,
                        blocking=False,
                    ),
                )
            )

        contextual_counts: dict[str, int] = {}
        contextual_findings: list[InterpretationFinding] = []
        for name in ("emergency_encounters", "inpatient_encounters"):
            item = by_indicator.get(name)
            if item is None:
                continue
            contextual_identity, contextual_metrics = item
            contextual_reason = _validate_indicator(contextual_metrics, self.thresholds)
            if contextual_reason is not None:
                contextual_findings.append(
                    _inconclusive(
                        rule=self,
                        identity=contextual_identity,
                        title=f"Contextual healthcare-flow indicator '{name}' is inconclusive",
                        metrics=contextual_metrics,
                        reason=contextual_reason,
                        blocking=False,
                    )
                )
            else:
                contextual_counts[name] = _integer(contextual_metrics, "numerator") or 0

        coverage = _fraction(coverage_metrics)
        denominator = _integer(coverage_metrics, "denominator")
        assert coverage is not None
        refs = _refs(metric for _, row in by_indicator.values() for metric in row.values())

        if coverage < self.thresholds.minimum_patient_encounter_fraction:
            status = FindingStatus.FAIL
            severity = Severity.HIGH
            blocks = True
            interpretation = "Too few patients have any recorded encounter to support the intended care-flow representation."
        elif coverage < self.thresholds.warning_patient_encounter_fraction:
            status = FindingStatus.WARNING
            severity = Severity.MODERATE
            blocks = False
            interpretation = "Encounter coverage is present but below the configured target."
        else:
            status = FindingStatus.PASS
            severity = Severity.INFO
            blocks = False
            interpretation = "Patient-level encounter coverage meets the configured care-flow criterion."

        recommendations: tuple[Recommendation, ...] = ()
        if status is not FindingStatus.PASS:
            recommendations = (
                Recommendation(
                    recommendation_id=f"{self.rule_id}.IMPROVE_COVERAGE",
                    action="Review wellness, primary-care and other encounter-generating pathways.",
                    priority=(
                        RecommendationPriority.URGENT
                        if blocks
                        else RecommendationPriority.HIGH
                    ),
                    rationale="Longitudinal clinical events require adequate encounter coverage.",
                    expected_outcome="The patient encounter fraction reaches the configured target.",
                    verification="Re-run the cohort and verify patients_with_encounters fraction.",
                    blocking=blocks,
                ),
            )

        finding = InterpretationFinding(
            finding_id=f"{self.rule_id}.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Healthcare-flow representation in psynthea",
            status=status,
            severity=severity,
            confidence=_confidence(denominator),
            evidence_strength=_strength(denominator),
            observation=(
                f"Patients with encounters={coverage:.3%}; "
                f"emergency encounters={contextual_counts.get('emergency_encounters', 0)}; "
                f"inpatient encounters={contextual_counts.get('inpatient_encounters', 0)}."
            ),
            interpretation=interpretation,
            impact="Insufficient encounter coverage can undermine longitudinal and clinical-context analyses." if blocks else "Encounter coverage supports interpretation of the simulated care pathway.",
            evidence=refs,
            recommendations=recommendations,
            limitations=(
                "Emergency and inpatient counts are contextual and are not required to be non-zero for every module.",
                "This rule assesses coverage, not appropriateness or temporal ordering of encounters.",
            ),
            tags=self.tags,
            confidence_score=_confidence_score(denominator),
            clinically_relevant=True,
            blocks_research_use=blocks,
        )
        return RuleOutcome(findings=(finding, *contextual_findings))


class ClinicalContextLinkageRule(SpanishAdaptationRule):
    """Assess whether clinical records remain linked to encounter context."""

    rule_id = "SPANISH.CLINICAL_CONTEXT"
    domain = "spanish_adaptation"
    description = "Assess encounter linkage for conditions, medications, procedures and observations."
    required_stages = (PipelineStage.SPANISH_ADAPTATION,)
    tags = ("spanish-adaptation", "clinical-context", "encounter-linkage")

    def __init__(self, thresholds: SpanishAdaptationThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, SpanishAdaptationThresholds):
            raise TypeError("thresholds must be a SpanishAdaptationThresholds instance.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "clinical_context"):
            return ApplicabilityDecision.not_evaluated("No clinical-context indicators were produced.")
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "clinical_context")
        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []

        for identity in sorted(rows):
            metrics = rows[identity]
            indicator = _indicator_from_identity(identity)
            available = _boolean(metrics, "available")
            denominator = _integer(metrics, "denominator")
            if available is False and denominator == 0:
                # No records in this optional domain: linkage is not applicable, not a failure.
                refs = _refs(metrics.values())
                findings.append(
                    InterpretationFinding(
                        finding_id=f"{self.rule_id}.{identity}.NOT_APPLICABLE",
                        rule_id=self.rule_id,
                        domain=self.domain,
                        title=f"Encounter linkage for '{indicator}' is not applicable",
                        status=FindingStatus.NOT_APPLICABLE,
                        severity=Severity.INFO,
                        confidence=Confidence.HIGH,
                        evidence_strength=EvidenceStrength.INSUFFICIENT,
                        observation="The source clinical table is empty or lacks evaluable records.",
                        interpretation="No encounter-linkage conclusion is required for an absent clinical domain.",
                        impact="This indicator does not affect other populated clinical domains.",
                        evidence=refs,
                        limitations=("Absence may still require review if this domain was expected from the module.",),
                        tags=(*self.tags, indicator),
                        confidence_score=0.85,
                        clinically_relevant=False,
                        blocks_research_use=False,
                    )
                )
                continue

            reason = _validate_indicator(metrics, self.thresholds)
            if reason is not None:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Encounter linkage for '{indicator}' is inconclusive",
                        metrics=metrics,
                        reason=reason,
                        blocking=True,
                    )
                )
                continue

            sample_reason = _minimum_denominator_reason(metrics, self.thresholds)
            if sample_reason is not None:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Encounter linkage for '{indicator}' is sample-size limited",
                        metrics=metrics,
                        reason=sample_reason,
                        blocking=False,
                    )
                )
                continue

            fraction = _fraction(metrics)
            assert fraction is not None
            refs = _refs(metrics.values())
            if fraction < self.thresholds.minimum_context_linkage_fraction:
                status = FindingStatus.FAIL
                severity = Severity.HIGH
                blocks = True
            elif fraction < self.thresholds.warning_context_linkage_fraction:
                status = FindingStatus.WARNING
                severity = Severity.MODERATE
                blocks = False
            else:
                status = FindingStatus.PASS
                severity = Severity.INFO
                blocks = False

            recommendations: tuple[Recommendation, ...] = ()
            if status is not FindingStatus.PASS:
                recommendations = (
                    Recommendation(
                        recommendation_id=f"{self.rule_id}.{identity}.LINK",
                        action=f"Restore encounter references for records represented by '{indicator}'.",
                        priority=(
                            RecommendationPriority.URGENT
                            if blocks
                            else RecommendationPriority.HIGH
                        ),
                        rationale="Clinical events without encounter context weaken longitudinal care-pathway interpretation.",
                        expected_outcome="The encounter-linkage fraction meets the configured target.",
                        verification=f"Re-run validation and verify {indicator} fraction.",
                        blocking=blocks,
                    ),
                )

            finding = InterpretationFinding(
                finding_id=f"{self.rule_id}.{identity}.{status.value.upper()}",
                rule_id=self.rule_id,
                domain=self.domain,
                title=f"Encounter linkage for '{indicator}'",
                status=status,
                severity=severity,
                confidence=_confidence(denominator, proxy=False),
                evidence_strength=_strength(denominator),
                observation=f"Encounter-linked records={fraction:.3%} ({_integer(metrics, 'numerator')}/{denominator}).",
                interpretation=(
                    "Clinical records retain adequate encounter context."
                    if status is FindingStatus.PASS
                    else "Clinical records have incomplete encounter context."
                ),
                impact=(
                    "Longitudinal and care-pathway analyses may be unreliable for this clinical domain."
                    if blocks
                    else "Some care-context analyses may require caution."
                    if status is FindingStatus.WARNING
                    else "Encounter context supports longitudinal interpretation."
                ),
                evidence=refs,
                recommendations=recommendations,
                limitations=(
                    "Presence of an encounter reference does not prove that the encounter type or timing is clinically correct.",
                ),
                tags=(*self.tags, indicator),
                confidence_score=_confidence_score(denominator, proxy=False),
                clinically_relevant=True,
                blocks_research_use=blocks,
            )
            findings.append(finding)
            inferences.append(
                Inference(
                    inference_id=f"{self.rule_id}.{identity}.INFERENCE",
                    statement=f"{indicator} encounter-linkage fraction is {fraction:.3%}.",
                    evidence=refs,
                    rationale="The indicator directly reports linked records over all domain records.",
                    confidence=_confidence_score(denominator, proxy=False),
                )
            )

        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


DEFAULT_SPANISH_ADAPTATION_RULES: Final = (
    SpanishAdaptationEvidenceIntegrityRule(),
    PrimaryCareRepresentationRule(),
    ReferralPathwayRepresentationRule(),
    HealthcareFlowRepresentationRule(),
    ClinicalContextLinkageRule(),
)