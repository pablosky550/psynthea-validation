"""Deterministic statistical interpretation rules for Synthea equivalence.

This module interprets canonical evidence produced by the statistical-comparison
stage.  It never recomputes tests from raw cohorts and never treats a p-value as
proof of practical or clinical relevance.

Decision principles
-------------------

* Statistical significance and effect magnitude are evaluated independently.
* FDR-adjusted prevalence results take precedence over unadjusted p-values.
* A confidence interval crossing the null prevents a conclusive ratio finding.
* Small samples, invalid values and skipped comparisons remain inconclusive.
* PASS means that the configured statistical equivalence criteria were met; it
  does not by itself establish clinical equivalence.
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
    Inference,
    PipelineStage,
    RuleContext,
    RuleOutcome,
    StatisticalRule,
)

__all__ = [
    "DEFAULT_STATISTICAL_RULES",
    "DistributionEquivalenceRule",
    "GlobalStatisticalReadinessRule",
    "PrevalenceEquivalenceRule",
    "StatisticalThresholds",
    "TestFamilyEquivalenceRule",
]


@dataclass(frozen=True, slots=True)
class StatisticalThresholds:
    """Explicit interpretation thresholds used by deterministic rules.

    These values are policy, not universal scientific constants.  Keeping them
    in one immutable object makes each decision reproducible and reviewable.
    """

    alpha: float = 0.05
    minimum_sample_size: int = 30
    negligible_effect: float = 0.10
    small_effect: float = 0.20
    moderate_effect: float = 0.50
    large_effect: float = 0.80
    prevalence_absolute_tolerance: float = 0.02
    prevalence_relative_tolerance: float = 0.20
    risk_ratio_lower_tolerance: float = 0.80
    risk_ratio_upper_tolerance: float = 1.25
    jensen_shannon_tolerance: float = 0.10

    def __post_init__(self) -> None:
        probability_fields = (
            "alpha",
            "negligible_effect",
            "small_effect",
            "moderate_effect",
            "large_effect",
            "prevalence_absolute_tolerance",
            "prevalence_relative_tolerance",
            "jensen_shannon_tolerance",
        )
        for name in probability_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric.")
            if not isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must lie strictly between 0 and 1.")
        if isinstance(self.minimum_sample_size, bool) or not isinstance(
            self.minimum_sample_size, int
        ):
            raise TypeError("minimum_sample_size must be an integer.")
        if self.minimum_sample_size < 2:
            raise ValueError("minimum_sample_size must be at least 2.")
        if not (
            self.negligible_effect
            <= self.small_effect
            <= self.moderate_effect
            <= self.large_effect
        ):
            raise ValueError("Effect thresholds must be monotonically increasing.")
        if not 0.0 < self.risk_ratio_lower_tolerance <= 1.0:
            raise ValueError("risk_ratio_lower_tolerance must be in (0, 1].")
        if self.risk_ratio_upper_tolerance < 1.0:
            raise ValueError("risk_ratio_upper_tolerance must be at least 1.")
        if self.risk_ratio_lower_tolerance >= self.risk_ratio_upper_tolerance:
            raise ValueError("Risk-ratio equivalence bounds must define a non-empty interval.")
        for name in (
            "prevalence_absolute_tolerance",
            "prevalence_relative_tolerance",
            "jensen_shannon_tolerance",
        ):
            if float(getattr(self, name)) > 1.0:
                raise ValueError(f"{name} must not exceed 1.0.")


DEFAULT_THRESHOLDS: Final = StatisticalThresholds()


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
                f"Duplicate statistical evidence for {namespace!r}, row "
                f"{identity!r}, column {column!r}."
            )
        grouped[identity][column] = value
    return grouped


def _refs(values: Iterable[object], role: EvidenceRole = EvidenceRole.PRIMARY) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(metric_id=value.metric_id, role=role)
        for value in sorted(values, key=lambda item: item.metric_id)
    )


def _available_value(metrics: Mapping[str, object], column: str) -> object | None:
    value = metrics.get(column)
    if value is None or not getattr(value, "is_available", False):
        return None
    return value.value


def _number(metrics: Mapping[str, object], column: str) -> float | None:
    value = _available_value(metrics, column)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _integer(metrics: Mapping[str, object], column: str) -> int | None:
    number = _number(metrics, column)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _boolean(metrics: Mapping[str, object], column: str) -> bool | None:
    value = _available_value(metrics, column)
    return value if isinstance(value, bool) else None


def _text(metrics: Mapping[str, object], column: str) -> str | None:
    value = _available_value(metrics, column)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()



def _significance_is_consistent(
    *, p_value: float, significant: bool, alpha: float
) -> bool:
    """Return whether the pipeline flag agrees with its declared alpha rule."""

    return significant is (p_value < alpha)


def _sample_sizes_are_adequate(
    n1: int | None, n2: int | None, minimum: int
) -> tuple[bool, str | None]:
    if n1 is None or n2 is None:
        return False, "Both group sample sizes are required for statistical interpretation."
    if n1 < minimum or n2 < minimum:
        return (
            False,
            f"Minimum group size is {min(n1, n2)}, below the configured minimum of {minimum}.",
        )
    return True, None


def _effect_label(effect: float, thresholds: StatisticalThresholds) -> tuple[str, Severity]:
    magnitude = abs(effect)
    if magnitude < thresholds.negligible_effect:
        return "negligible", Severity.INFO
    if magnitude < thresholds.small_effect:
        return "very small", Severity.LOW
    if magnitude < thresholds.moderate_effect:
        return "small", Severity.LOW
    if magnitude < thresholds.large_effect:
        return "moderate", Severity.MODERATE
    return "large", Severity.HIGH


def _strength(n1: int | None, n2: int | None) -> EvidenceStrength:
    if n1 is None or n2 is None:
        return EvidenceStrength.MODERATE
    minimum = min(n1, n2)
    if minimum < 30:
        return EvidenceStrength.WEAK
    if minimum < 100:
        return EvidenceStrength.MODERATE
    if minimum < 1000:
        return EvidenceStrength.STRONG
    return EvidenceStrength.VERY_STRONG


def _confidence(n1: int | None, n2: int | None, complete: bool = True) -> Confidence:
    if not complete:
        return Confidence.LOW
    if n1 is None or n2 is None:
        return Confidence.MODERATE
    minimum = min(n1, n2)
    if minimum < 30:
        return Confidence.LOW
    if minimum < 100:
        return Confidence.MODERATE
    if minimum < 1000:
        return Confidence.HIGH
    return Confidence.VERY_HIGH


def _inconclusive(
    *,
    rule: StatisticalRule,
    identity: str,
    title: str,
    refs: tuple[EvidenceReference, ...],
    reason: str,
    tags: tuple[str, ...],
) -> InterpretationFinding:
    return InterpretationFinding(
        finding_id=f"{rule.rule_id}.{identity}.INCONCLUSIVE",
        rule_id=rule.rule_id,
        domain=rule.domain,
        title=title,
        status=FindingStatus.INCONCLUSIVE,
        severity=Severity.MODERATE,
        confidence=Confidence.LOW,
        evidence_strength=EvidenceStrength.INSUFFICIENT,
        observation=reason,
        interpretation="The available statistical evidence is insufficient for a defensible equivalence decision.",
        impact="This endpoint must not be reported as statistically equivalent or different.",
        evidence=refs,
        recommendations=(
            Recommendation(
                recommendation_id=f"{rule.rule_id}.{identity}.RECOMPUTE",
                action="Recompute the statistical endpoint with complete finite inputs and adequate sample size.",
                priority=RecommendationPriority.HIGH,
                rationale=reason,
                expected_outcome="The endpoint contains valid test statistics, effect information and sample sizes.",
                verification="Re-run normalization and confirm that all metrics required by this rule are available.",
                blocking=True,
            ),
        ),
        limitations=("No missing value has been interpreted as zero.",),
        tags=(*tags, "inconclusive"),
        confidence_score=0.25,
        blocks_research_use=True,
    )


class GlobalStatisticalReadinessRule(StatisticalRule):
    """Interpret whether the pipeline considers this module statistically comparable."""

    rule_id = "STAT.READINESS"
    domain = "statistical"
    description = "Assess global readiness for statistical comparison."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("statistics", "readiness", "research-safety")

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "statistics.summary")
        if not rows:
            raise ValueError("No statistics.summary evidence is available.")
        if len(rows) != 1:
            raise ValueError("Exactly one statistics.summary row is required per module.")

        identity, metrics = next(iter(rows.items()))
        refs = _refs(metrics.values())
        valid = _boolean(metrics, "valid_for_statistical_comparison")
        skipped = _boolean(metrics, "skipped")
        reason = _text(metrics, "skip_reason")
        status_text = _text(metrics, "validation_status")

        if valid is None or skipped is None:
            finding = _inconclusive(
                rule=self,
                identity=identity,
                title="Statistical comparison readiness is indeterminate",
                refs=refs,
                reason="The statistical summary does not expose valid boolean readiness and skipped flags.",
                tags=self.tags,
            )
            return RuleOutcome(findings=(finding,))

        if skipped or not valid:
            finding = InterpretationFinding(
                finding_id=f"{self.rule_id}.{identity}.BLOCKED",
                rule_id=self.rule_id,
                domain=self.domain,
                title="Statistical comparison is not ready",
                status=FindingStatus.INCONCLUSIVE,
                severity=Severity.HIGH,
                confidence=Confidence.VERY_HIGH,
                evidence_strength=EvidenceStrength.VERY_STRONG,
                observation=(
                    f"valid_for_statistical_comparison={valid}; skipped={skipped}; "
                    f"validation_status={status_text!r}; skip_reason={reason!r}."
                ),
                interpretation="The pipeline explicitly prevented or invalidated statistical comparison.",
                impact="No downstream statistical equivalence claim is admissible for this module.",
                evidence=refs,
                recommendations=(
                    Recommendation(
                        recommendation_id=f"{self.rule_id}.{identity}.UNBLOCK",
                        action="Resolve the pipeline condition that blocked statistical comparison and rerun the module.",
                        priority=RecommendationPriority.URGENT,
                        rationale=reason or "The statistical summary marked the comparison as invalid or skipped.",
                        expected_outcome="The summary reports valid_for_statistical_comparison=True and skipped=False.",
                        verification="Inspect the regenerated statistics.summary evidence before executing endpoint rules.",
                        blocking=True,
                    ),
                ),
                tags=(*self.tags, "blocked"),
                confidence_score=0.99,
                blocks_research_use=True,
            )
            return RuleOutcome(findings=(finding,))

        finding = InterpretationFinding(
            finding_id=f"{self.rule_id}.{identity}.PASS",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Statistical comparison is ready",
            status=FindingStatus.PASS,
            severity=Severity.INFO,
            confidence=Confidence.VERY_HIGH,
            evidence_strength=EvidenceStrength.VERY_STRONG,
            observation="The pipeline reports valid_for_statistical_comparison=True and skipped=False.",
            interpretation="Endpoint-level statistical rules may be evaluated.",
            impact="Statistical readiness does not block downstream interpretation.",
            evidence=refs,
            limitations=("Readiness does not imply equivalence; endpoint-level results remain decisive.",),
            tags=self.tags,
            confidence_score=0.99,
            blocks_research_use=False,
        )
        inference = Inference(
            inference_id=f"{self.rule_id}.{identity}.READY",
            statement="The module is eligible for endpoint-level statistical interpretation.",
            evidence=refs,
            rationale="The canonical summary explicitly marks the comparison as valid and not skipped.",
            confidence=0.99,
        )
        return RuleOutcome(findings=(finding,), inferences=(inference,))


class TestFamilyEquivalenceRule(StatisticalRule):
    """Interpret continuous and categorical test families using p-value and effect size."""

    rule_id = "STAT.TEST_FAMILIES"
    domain = "statistical"
    description = "Interpret continuous and categorical statistical endpoints."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("statistics", "effect-size", "significance")

    def __init__(self, thresholds: StatisticalThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, StatisticalThresholds):
            raise TypeError("thresholds must be StatisticalThresholds.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "statistics.continuous") and not _rows(context, "statistics.categorical"):
            return ApplicabilityDecision.not_applicable(
                "No continuous or categorical statistical tests were produced for this module."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        findings: list[InterpretationFinding] = []
        inferences: list[Inference] = []
        for family in ("continuous", "categorical"):
            for identity, metrics in sorted(_rows(context, f"statistics.{family}").items()):
                refs = _refs(metrics.values())
                p_value = _number(metrics, "p_value")
                effect = _number(metrics, "effect_size")
                significant = _boolean(metrics, "significant")
                n1 = _integer(metrics, "n_synthea")
                n2 = _integer(metrics, "n_psynthea")
                test_name = _text(metrics, "test_name") or "statistical test"

                if p_value is None or effect is None or significant is None:
                    findings.append(
                        _inconclusive(
                            rule=self,
                            identity=f"{family}.{identity}",
                            title=f"{family.title()} endpoint '{identity}' is inconclusive",
                            refs=refs,
                            reason="A finite p-value, effect size and significance flag are required.",
                            tags=(*self.tags, family),
                        )
                    )
                    continue
                if not 0.0 <= p_value <= 1.0:
                    findings.append(
                        _inconclusive(
                            rule=self,
                            identity=f"{family}.{identity}",
                            title=f"{family.title()} endpoint '{identity}' has an invalid p-value",
                            refs=refs,
                            reason=f"Observed p_value={p_value}, outside [0, 1].",
                            tags=(*self.tags, family),
                        )
                    )
                    continue
                adequate, sample_reason = _sample_sizes_are_adequate(
                    n1, n2, self.thresholds.minimum_sample_size
                )
                if not adequate:
                    findings.append(
                        _inconclusive(
                            rule=self,
                            identity=f"{family}.{identity}",
                            title=f"{family.title()} endpoint '{identity}' is underpowered",
                            refs=refs,
                            reason=sample_reason or "Sample-size adequacy could not be established.",
                            tags=(*self.tags, family, "sample-size"),
                        )
                    )
                    continue
                if not _significance_is_consistent(
                    p_value=p_value, significant=significant, alpha=self.thresholds.alpha
                ):
                    findings.append(
                        _inconclusive(
                            rule=self,
                            identity=f"{family}.{identity}",
                            title=f"{family.title()} endpoint '{identity}' has inconsistent inference",
                            refs=refs,
                            reason=(
                                f"The significance flag ({significant}) disagrees with p={p_value:.6g} "
                                f"at alpha={self.thresholds.alpha}."
                            ),
                            tags=(*self.tags, family, "inconsistent-significance"),
                        )
                    )
                    continue

                label, effect_severity = _effect_label(effect, self.thresholds)
                practically_relevant = abs(effect) >= self.thresholds.small_effect
                statistically_significant = significant

                if statistically_significant and practically_relevant:
                    status = FindingStatus.FAIL
                    severity = max(effect_severity, Severity.MODERATE, key=lambda item: list(Severity).index(item))
                    interpretation = "The engines differ statistically and the estimated effect is not negligible."
                    impact = "Functional/statistical equivalence is not supported for this endpoint."
                    blocks = True
                elif statistically_significant:
                    status = FindingStatus.WARNING
                    severity = Severity.LOW
                    interpretation = (
                        "A statistically detectable difference exists, but its effect magnitude is below the "
                        "configured practical-relevance threshold."
                    )
                    impact = "The difference should be reported but does not alone demonstrate material non-equivalence."
                    blocks = False
                elif practically_relevant:
                    status = FindingStatus.WARNING
                    severity = effect_severity
                    interpretation = (
                        "The effect estimate is practically relevant although the null-hypothesis test is not significant."
                    )
                    impact = "Potential low-power or high-variance non-equivalence requires further investigation."
                    blocks = False
                else:
                    status = FindingStatus.PASS
                    severity = Severity.INFO
                    interpretation = "No statistically significant or practically relevant difference was detected."
                    impact = "This endpoint supports statistical similarity under the configured thresholds."
                    blocks = False

                finding = InterpretationFinding(
                    finding_id=f"{self.rule_id}.{family}.{identity}.{status.value.upper()}",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"{family.title()} endpoint '{identity}': {status.value}",
                    status=status,
                    severity=severity,
                    confidence=_confidence(n1, n2),
                    evidence_strength=_strength(n1, n2),
                    observation=(
                        f"{test_name}: p={p_value:.6g}, effect_size={effect:.6g} ({label}), "
                        f"n_synthea={n1}, n_psynthea={n2}."
                    ),
                    interpretation=interpretation,
                    impact=impact,
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{family}.{identity}.INVESTIGATE",
                            action="Inspect the endpoint definition, cohort construction and random-seed sensitivity.",
                            priority=RecommendationPriority.HIGH if blocks else RecommendationPriority.MEDIUM,
                            rationale="The endpoint exhibits statistical or practical evidence of divergence.",
                            expected_outcome="The source of divergence is explained or the endpoint falls within tolerance.",
                            verification="Repeat the comparison across independent seeds and report effect estimates with uncertainty.",
                            blocking=blocks,
                        ),
                    ) if status in {FindingStatus.FAIL, FindingStatus.WARNING} else (),
                    limitations=("Statistical similarity is not equivalent to clinical interchangeability.",),
                    tags=(*self.tags, family, label),
                    confidence_score=0.95 if min(n1 or 0, n2 or 0) >= 100 else 0.75,
                    blocks_research_use=blocks,
                )
                findings.append(finding)
                inferences.append(
                    Inference(
                        inference_id=f"{self.rule_id}.{family}.{identity}.CLASSIFICATION",
                        statement=f"The endpoint has a {label} effect and status {status.value}.",
                        evidence=refs,
                        rationale="Classification combines p-value and effect-size criteria without conflating them.",
                        confidence=finding.confidence_score,
                    )
                )

        if not findings:
            raise ValueError("No interpretable continuous or categorical test rows were found.")
        return RuleOutcome(findings=tuple(findings), inferences=tuple(inferences))


class PrevalenceEquivalenceRule(StatisticalRule):
    """Interpret code-level prevalence differences with multiplicity correction."""

    rule_id = "STAT.PREVALENCE"
    domain = "prevalence"
    description = "Interpret prevalence differences, ratios, confidence intervals and FDR results."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("statistics", "prevalence", "fdr", "confidence-interval")

    def __init__(self, thresholds: StatisticalThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, StatisticalThresholds):
            raise TypeError("thresholds must be StatisticalThresholds.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "statistics.prevalence"):
            return ApplicabilityDecision.not_applicable("No prevalence endpoints were produced.")
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        findings: list[InterpretationFinding] = []
        for identity, metrics in sorted(_rows(context, "statistics.prevalence").items()):
            refs = _refs(metrics.values())
            synthea_prev = _number(metrics, "synthea_prevalence")
            psynthea_prev = _number(metrics, "psynthea_prevalence")
            absolute = _number(metrics, "absolute_difference")
            relative = _number(metrics, "relative_difference")
            rr = _number(metrics, "risk_ratio")
            rr_low = _number(metrics, "risk_ratio_ci_lower")
            rr_high = _number(metrics, "risk_ratio_ci_upper")
            adjusted_p = _number(metrics, "adjusted_p_value")
            fdr_significant = _boolean(metrics, "significant_after_fdr")
            n1 = _integer(metrics, "synthea_total")
            n2 = _integer(metrics, "psynthea_total")

            required_numbers = (synthea_prev, psynthea_prev, absolute)
            if any(value is None for value in required_numbers) or fdr_significant is None:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Prevalence endpoint '{identity}' is inconclusive",
                        refs=refs,
                        reason="Prevalences, absolute difference and the FDR significance decision are required.",
                        tags=self.tags,
                    )
                )
                continue
            if not 0.0 <= synthea_prev <= 1.0 or not 0.0 <= psynthea_prev <= 1.0:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Prevalence endpoint '{identity}' contains invalid prevalence values",
                        refs=refs,
                        reason=f"Observed prevalences are {synthea_prev} and {psynthea_prev}; expected [0, 1].",
                        tags=self.tags,
                    )
                )
                continue

            adequate, sample_reason = _sample_sizes_are_adequate(
                n1, n2, self.thresholds.minimum_sample_size
            )
            if not adequate:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Prevalence endpoint '{identity}' is underpowered",
                        refs=refs,
                        reason=sample_reason or "Sample-size adequacy could not be established.",
                        tags=(*self.tags, "sample-size"),
                    )
                )
                continue
            if adjusted_p is not None and not 0.0 <= adjusted_p <= 1.0:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Prevalence endpoint '{identity}' has an invalid adjusted p-value",
                        refs=refs,
                        reason=f"Observed adjusted_p_value={adjusted_p}, outside [0, 1].",
                        tags=(*self.tags, "invalid-adjusted-p"),
                    )
                )
                continue
            if adjusted_p is not None and not _significance_is_consistent(
                p_value=adjusted_p,
                significant=fdr_significant,
                alpha=self.thresholds.alpha,
            ):
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Prevalence endpoint '{identity}' has inconsistent FDR inference",
                        refs=refs,
                        reason=(
                            f"significant_after_fdr={fdr_significant} disagrees with "
                            f"adjusted_p_value={adjusted_p:.6g} at alpha={self.thresholds.alpha}."
                        ),
                        tags=(*self.tags, "inconsistent-fdr"),
                    )
                )
                continue

            abs_ok = abs(absolute) <= self.thresholds.prevalence_absolute_tolerance
            relative_ok = relative is None or abs(relative) <= self.thresholds.prevalence_relative_tolerance
            ratio_ci_available = rr is not None and rr_low is not None and rr_high is not None
            if ratio_ci_available and (rr_low > rr_high or rr <= 0.0 or rr_low <= 0.0):
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Prevalence endpoint '{identity}' has an invalid risk-ratio interval",
                        refs=refs,
                        reason=f"Observed risk_ratio={rr}, CI=[{rr_low}, {rr_high}].",
                        tags=(*self.tags, "invalid-confidence-interval"),
                    )
                )
                continue
            ratio_ci_crosses_null = bool(ratio_ci_available and rr_low <= 1.0 <= rr_high)
            ratio_equivalent = bool(
                ratio_ci_available
                and self.thresholds.risk_ratio_lower_tolerance <= rr_low
                and rr_high <= self.thresholds.risk_ratio_upper_tolerance
            )
            ratio_material = bool(ratio_ci_available and not ratio_equivalent)
            material = not abs_ok or not relative_ok or ratio_material

            if fdr_significant and material:
                status = FindingStatus.FAIL
                severity = Severity.HIGH
                interpretation = "The prevalence difference survives FDR correction and exceeds materiality tolerance."
                impact = "Prevalence equivalence is not supported for this clinical code."
                blocks = True
            elif fdr_significant:
                status = FindingStatus.WARNING
                severity = Severity.LOW
                interpretation = "The difference survives FDR correction but remains within configured materiality tolerance."
                impact = "A detectable but small prevalence divergence should be disclosed."
                blocks = False
            elif material:
                status = FindingStatus.WARNING
                severity = Severity.MODERATE
                interpretation = (
                    "The point estimate exceeds materiality tolerance, but multiplicity-adjusted significance is absent."
                )
                impact = "The endpoint is not a clean equivalence pass and may require more power or seed replication."
                blocks = False
            else:
                status = FindingStatus.PASS
                severity = Severity.INFO
                interpretation = "The prevalence difference is not FDR-significant and remains within tolerance."
                impact = "This code-level prevalence supports statistical similarity."
                blocks = False

            limitations = [
                "FDR controls the expected false-discovery proportion across tested prevalence endpoints.",
                "Statistical prevalence similarity does not establish clinical pathway equivalence.",
            ]
            if ratio_ci_available:
                limitations.append(
                    "Risk-ratio equivalence requires the full confidence interval to lie within "
                    f"[{self.thresholds.risk_ratio_lower_tolerance}, "
                    f"{self.thresholds.risk_ratio_upper_tolerance}]."
                )
                if ratio_ci_crosses_null:
                    limitations.append("The risk-ratio confidence interval includes the null value 1.0.")
            else:
                limitations.append(
                    "A complete risk-ratio confidence interval was unavailable; the decision relies on "
                    "absolute and relative prevalence margins."
                )

            findings.append(
                InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.{status.value.upper()}",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Prevalence endpoint '{identity}': {status.value}",
                    status=status,
                    severity=severity,
                    confidence=_confidence(n1, n2, complete=adjusted_p is not None),
                    evidence_strength=_strength(n1, n2),
                    observation=(
                        f"Synthea prevalence={synthea_prev:.6g}; psynthea prevalence={psynthea_prev:.6g}; "
                        f"absolute_difference={absolute:.6g}; relative_difference={relative}; risk_ratio={rr}; "
                        f"95% CI=[{rr_low}, {rr_high}]; adjusted_p={adjusted_p}; "
                        f"significant_after_fdr={fdr_significant}."
                    ),
                    interpretation=interpretation,
                    impact=impact,
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.REVIEW",
                            action="Review disease-module incidence logic, cohort denominators and code mapping for this endpoint.",
                            priority=RecommendationPriority.HIGH if blocks else RecommendationPriority.MEDIUM,
                            rationale="The prevalence point estimate or multiplicity-adjusted test indicates divergence.",
                            expected_outcome="Prevalence differences are explained or reduced below configured tolerances.",
                            verification="Repeat across seeds and confirm absolute, relative and ratio criteria using FDR-adjusted inference.",
                            blocking=blocks,
                        ),
                    ) if status in {FindingStatus.FAIL, FindingStatus.WARNING} else (),
                    limitations=tuple(limitations),
                    tags=(*self.tags, "material" if material else "within-tolerance"),
                    confidence_score=0.95 if adjusted_p is not None else 0.70,
                    clinically_relevant=material,
                    blocks_research_use=blocks,
                )
            )

        return RuleOutcome(findings=tuple(findings))


class DistributionEquivalenceRule(StatisticalRule):
    """Interpret full-distribution comparisons using hypothesis tests and JSD."""

    rule_id = "STAT.DISTRIBUTION"
    domain = "distribution"
    description = "Interpret distributional similarity using significance, effect size and JSD."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("statistics", "distribution", "ks", "jensen-shannon")

    def __init__(self, thresholds: StatisticalThresholds = DEFAULT_THRESHOLDS) -> None:
        if not isinstance(thresholds, StatisticalThresholds):
            raise TypeError("thresholds must be StatisticalThresholds.")
        self.thresholds = thresholds

    def applicability(self, context: RuleContext, evidence: Mapping[str, object]) -> ApplicabilityDecision:
        if not _rows(context, "statistics.distribution"):
            return ApplicabilityDecision.not_applicable("No distribution endpoints were produced.")
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        findings: list[InterpretationFinding] = []
        for identity, metrics in sorted(_rows(context, "statistics.distribution").items()):
            refs = _refs(metrics.values())
            p_value = _number(metrics, "p_value")
            effect = _number(metrics, "effect_size")
            jsd = _number(metrics, "jensen_shannon_divergence")
            significant = _boolean(metrics, "significant")
            n1 = _integer(metrics, "n_synthea")
            n2 = _integer(metrics, "n_psynthea")
            test_name = _text(metrics, "test_name") or "distribution test"

            if p_value is None or jsd is None or significant is None:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Distribution endpoint '{identity}' is inconclusive",
                        refs=refs,
                        reason="A finite p-value, JSD and significance decision are required.",
                        tags=self.tags,
                    )
                )
                continue
            if not 0.0 <= p_value <= 1.0 or not 0.0 <= jsd <= 1.0:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Distribution endpoint '{identity}' contains invalid statistics",
                        refs=refs,
                        reason=f"Observed p_value={p_value} and JSD={jsd}; both must lie in [0, 1].",
                        tags=self.tags,
                    )
                )
                continue

            adequate, sample_reason = _sample_sizes_are_adequate(
                n1, n2, self.thresholds.minimum_sample_size
            )
            if not adequate:
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Distribution endpoint '{identity}' is underpowered",
                        refs=refs,
                        reason=sample_reason or "Sample-size adequacy could not be established.",
                        tags=(*self.tags, "sample-size"),
                    )
                )
                continue
            if not _significance_is_consistent(
                p_value=p_value, significant=significant, alpha=self.thresholds.alpha
            ):
                findings.append(
                    _inconclusive(
                        rule=self,
                        identity=identity,
                        title=f"Distribution endpoint '{identity}' has inconsistent inference",
                        refs=refs,
                        reason=(
                            f"The significance flag ({significant}) disagrees with p={p_value:.6g} "
                            f"at alpha={self.thresholds.alpha}."
                        ),
                        tags=(*self.tags, "inconsistent-significance"),
                    )
                )
                continue

            significant_result = significant
            jsd_material = jsd > self.thresholds.jensen_shannon_tolerance
            effect_material = effect is not None and abs(effect) >= self.thresholds.small_effect
            material = jsd_material or effect_material

            if significant_result and material:
                status, severity, blocks = FindingStatus.FAIL, Severity.HIGH, True
                interpretation = "The distributions differ statistically and exceed a magnitude threshold."
                impact = "Distributional equivalence is not supported for this endpoint."
            elif significant_result:
                status, severity, blocks = FindingStatus.WARNING, Severity.LOW, False
                interpretation = "The test detects a difference, but JSD/effect magnitude remains small."
                impact = "A small distributional divergence should be reported without overstating materiality."
            elif material:
                status, severity, blocks = FindingStatus.WARNING, Severity.MODERATE, False
                interpretation = "Distribution magnitude exceeds tolerance despite a non-significant test."
                impact = "Potential low power or localized divergence requires visual and replicated assessment."
            else:
                status, severity, blocks = FindingStatus.PASS, Severity.INFO, False
                interpretation = "Neither the hypothesis test nor the magnitude criteria indicate material divergence."
                impact = "This endpoint supports distributional similarity under the configured policy."

            findings.append(
                InterpretationFinding(
                    finding_id=f"{self.rule_id}.{identity}.{status.value.upper()}",
                    rule_id=self.rule_id,
                    domain=self.domain,
                    title=f"Distribution endpoint '{identity}': {status.value}",
                    status=status,
                    severity=severity,
                    confidence=_confidence(n1, n2),
                    evidence_strength=_strength(n1, n2),
                    observation=(
                        f"{test_name}: p={p_value:.6g}, JSD={jsd:.6g}, effect_size={effect}, "
                        f"n_synthea={n1}, n_psynthea={n2}."
                    ),
                    interpretation=interpretation,
                    impact=impact,
                    evidence=refs,
                    recommendations=(
                        Recommendation(
                            recommendation_id=f"{self.rule_id}.{identity}.INSPECT",
                            action="Inspect ECDF/histogram plots and repeat the distribution comparison across seeds.",
                            priority=RecommendationPriority.HIGH if blocks else RecommendationPriority.MEDIUM,
                            rationale="Distribution-level statistics indicate detectable or material divergence.",
                            expected_outcome="The divergence is localized and explained or reduced below tolerance.",
                            verification="Confirm both hypothesis-test and JSD/effect criteria after regeneration.",
                            blocking=blocks,
                        ),
                    ) if status in {FindingStatus.FAIL, FindingStatus.WARNING} else (),
                    limitations=(
                        "A non-significant KS-type test is not proof that distributions are identical.",
                        "JSD complements but does not replace clinical interpretation of the variable.",
                    ),
                    tags=(*self.tags, "material" if material else "within-tolerance"),
                    confidence_score=0.95 if min(n1 or 0, n2 or 0) >= 100 else 0.75,
                    blocks_research_use=blocks,
                )
            )

        return RuleOutcome(findings=tuple(findings))


DEFAULT_STATISTICAL_RULES: Final = (
    GlobalStatisticalReadinessRule(),
    TestFamilyEquivalenceRule(),
    PrevalenceEquivalenceRule(),
    DistributionEquivalenceRule(),
)