"""Deterministic epidemiological interpretation for Synthea equivalence.

This module translates statistical comparison evidence into population-level
conclusions aligned with the scientific validation hypotheses:

* H1 — demographic distributions are equivalent;
* H2 — principal prevalences do not differ materially;
* H3 — age-, sex- and comorbidity-related patterns are preserved.

The rules never recompute statistics from raw cohorts and never infer an
unmeasured relationship.  Missing relationship evidence is therefore reported as
``NOT_EVALUATED`` rather than silently treated as equivalence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from re import split
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
    EpidemiologicalRule,
    Inference,
    PipelineStage,
    RuleContext,
    RuleOutcome,
)

__all__ = [
    "DEFAULT_EPIDEMIOLOGICAL_RULES",
    "DemographicProfileEquivalenceRule",
    "EpidemiologicalRelationshipPreservationRule",
    "EpidemiologicalThresholds",
    "PopulationPrevalenceProfileRule",
]


@dataclass(frozen=True, slots=True)
class EpidemiologicalThresholds:
    """Auditable policy thresholds for population-level interpretation."""

    alpha: float = 0.05
    minimum_sample_size: int = 30
    demographic_effect_tolerance: float = 0.20
    demographic_js_tolerance: float = 0.10
    prevalence_absolute_tolerance: float = 0.02
    prevalence_relative_tolerance: float = 0.20
    prevalence_failure_fraction: float = 0.20
    prevalence_warning_fraction: float = 0.05
    relationship_effect_tolerance: float = 0.20

    def __post_init__(self) -> None:
        numeric = (
            "alpha",
            "demographic_effect_tolerance",
            "demographic_js_tolerance",
            "prevalence_absolute_tolerance",
            "prevalence_relative_tolerance",
            "prevalence_failure_fraction",
            "prevalence_warning_fraction",
            "relationship_effect_tolerance",
        )
        for name in numeric:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric.")
            if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1.")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must lie strictly between 0 and 1.")
        if isinstance(self.minimum_sample_size, bool) or not isinstance(
            self.minimum_sample_size, int
        ):
            raise TypeError("minimum_sample_size must be an integer.")
        if self.minimum_sample_size < 2:
            raise ValueError("minimum_sample_size must be at least 2.")
        if self.prevalence_warning_fraction > self.prevalence_failure_fraction:
            raise ValueError(
                "prevalence_warning_fraction must not exceed prevalence_failure_fraction."
            )
        if self.prevalence_failure_fraction == 0.0:
            raise ValueError("prevalence_failure_fraction must be greater than zero.")


DEFAULT_THRESHOLDS: Final = EpidemiologicalThresholds()

_DEMOGRAPHIC_TOKENS: Final = (
    "age",
    "edad",
    "sex",
    "sexo",
    "gender",
    "race",
    "ethnicity",
    "demographic",
)
_RELATIONSHIP_TOKENS: Final = (
    "comorbid",
    "association",
    "relationship",
    "stratified",
    "interaction",
    "by_age",
    "age_band",
    "by_sex",
    "by_gender",
    "sex_specific",
    "gender_specific",
)


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
                f"Duplicate epidemiological evidence for {namespace!r}, row "
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


def _available(metrics: Mapping[str, object], column: str) -> object | None:
    metric = metrics.get(column)
    if metric is None or not getattr(metric, "is_available", False):
        return None
    return metric.value


def _number(metrics: Mapping[str, object], column: str) -> float | None:
    value = _available(metrics, column)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _integer(metrics: Mapping[str, object], column: str) -> int | None:
    value = _number(metrics, column)
    return int(value) if value is not None and value.is_integer() and value >= 0 else None


def _probability(metrics: Mapping[str, object], column: str) -> float | None:
    value = _number(metrics, column)
    return value if value is not None and 0.0 <= value <= 1.0 else None


def _non_negative_number(metrics: Mapping[str, object], column: str) -> float | None:
    value = _number(metrics, column)
    return value if value is not None and value >= 0.0 else None


def _boolean(metrics: Mapping[str, object], column: str) -> bool | None:
    value = _available(metrics, column)
    return value if isinstance(value, bool) else None


def _coalesce(first: int | float | None, second: int | float | None) -> int | float | None:
    return first if first is not None else second


def _matches(identity: str, tokens: tuple[str, ...]) -> bool:
    normalized = identity.casefold()
    parts = tuple(part for part in split(r"[^a-z0-9]+", normalized) if part)
    compact = "_".join(parts)
    return any(
        (
            any(
                part == token or (token == "comorbid" and part.startswith(token))
                for part in parts
            )
            if "_" not in token
            else f"_{token}_" in f"_{compact}_"
        )
        for token in tokens
    )


def _require_thresholds(value: EpidemiologicalThresholds) -> EpidemiologicalThresholds:
    if not isinstance(value, EpidemiologicalThresholds):
        raise TypeError("thresholds must be an EpidemiologicalThresholds instance.")
    return value


def _all_metrics(rows: Mapping[str, Mapping[str, object]]) -> tuple[object, ...]:
    return tuple(metric for columns in rows.values() for metric in columns.values())


def _evidence_strength(minimum_n: int | None, row_count: int) -> EvidenceStrength:
    if row_count == 0 or minimum_n is None:
        return EvidenceStrength.INSUFFICIENT
    if minimum_n < 30:
        return EvidenceStrength.WEAK
    if minimum_n < 100:
        return EvidenceStrength.MODERATE
    if minimum_n < 1000:
        return EvidenceStrength.STRONG
    return EvidenceStrength.VERY_STRONG


def _confidence(minimum_n: int | None, complete: bool) -> Confidence:
    if not complete:
        return Confidence.LOW
    if minimum_n is None or minimum_n < 30:
        return Confidence.LOW
    if minimum_n < 100:
        return Confidence.MODERATE
    if minimum_n < 1000:
        return Confidence.HIGH
    return Confidence.VERY_HIGH


class DemographicProfileEquivalenceRule(EpidemiologicalRule):
    """Interpret H1 from age, sex and other demographic comparison rows."""

    rule_id = "EPI.DEMOGRAPHIC_PROFILE"
    domain = "epidemiological"
    description = "Assess preservation of demographic population distributions."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("epidemiological", "H1", "demography", "population")

    def __init__(self, thresholds: EpidemiologicalThresholds = DEFAULT_THRESHOLDS) -> None:
        self.thresholds = _require_thresholds(thresholds)

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        candidates = self._candidate_rows(context)
        if not candidates:
            return ApplicabilityDecision.not_evaluated(
                "No age, sex or other demographic statistical rows were produced."
            )
        return ApplicabilityDecision.applicable()

    def _candidate_rows(self, context: RuleContext) -> dict[str, dict[str, object]]:
        candidates: dict[str, dict[str, object]] = {}
        for namespace in (
            "statistics.continuous",
            "statistics.categorical",
            "statistics.distribution",
        ):
            for identity, metrics in _rows(context, namespace).items():
                if _matches(identity, _DEMOGRAPHIC_TOKENS):
                    candidates[f"{namespace}:{identity}"] = metrics
        return candidates

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = self._candidate_rows(context)
        defects: list[str] = []
        material: list[str] = []
        significant_small: list[str] = []
        minimum_sizes: list[int] = []

        for identity, metrics in rows.items():
            p_value = _probability(metrics, "p_value")
            significant = _boolean(metrics, "significant")
            effect = _number(metrics, "effect_size")
            jsd = _probability(metrics, "jensen_shannon_divergence")
            n1 = _integer(metrics, "n_synthea")
            n2 = _integer(metrics, "n_psynthea")

            if n1 is not None and n2 is not None:
                minimum_sizes.append(min(n1, n2))
            if p_value is None or significant is None or (effect is None and jsd is None):
                defects.append(f"{identity}: incomplete comparison evidence")
                continue
            if significant is not (p_value < self.thresholds.alpha):
                defects.append(f"{identity}: significance flag disagrees with p-value")
                continue
            if n1 is None or n2 is None or min(n1, n2) < self.thresholds.minimum_sample_size:
                defects.append(f"{identity}: insufficient or missing sample size")
                continue

            effect_material = effect is not None and abs(effect) > self.thresholds.demographic_effect_tolerance
            js_material = jsd is not None and jsd > self.thresholds.demographic_js_tolerance
            if effect_material or js_material:
                material.append(identity)
            elif significant:
                significant_small.append(identity)

        minimum_n = min(minimum_sizes) if minimum_sizes else None
        complete = not defects
        refs = _refs(_all_metrics(rows))

        if defects:
            status = FindingStatus.INCONCLUSIVE
            severity = Severity.HIGH
            blocks = True
            observation = f"{len(defects)} of {len(rows)} demographic comparison(s) are incomplete or inconsistent."
            interpretation = "H1 cannot be evaluated safely from the available demographic evidence."
        elif material:
            status = FindingStatus.FAIL
            severity = Severity.HIGH
            blocks = True
            observation = f"{len(material)} of {len(rows)} demographic comparison(s) exceed population-equivalence tolerances."
            interpretation = "The demographic profile differs materially between Synthea and psynthea."
        elif significant_small:
            status = FindingStatus.WARNING
            severity = Severity.LOW
            blocks = False
            observation = f"{len(significant_small)} demographic comparison(s) are statistically significant but remain within practical tolerances."
            interpretation = "H1 is provisionally supported, with small detectable demographic differences."
        else:
            status = FindingStatus.PASS
            severity = Severity.INFO
            blocks = False
            observation = f"All {len(rows)} demographic comparison(s) remain within configured population-equivalence tolerances."
            interpretation = "The available evidence supports H1 for the measured demographic dimensions."

        recommendations: tuple[Recommendation, ...] = ()
        if blocks:
            recommendations = (
                Recommendation(
                    recommendation_id="EPI.DEMOGRAPHIC_PROFILE.REMEDIATE",
                    action="Review cohort construction, age generation and demographic sampling before population-level use.",
                    priority=RecommendationPriority.URGENT,
                    rationale="Material or unevaluable demographic differences can confound every downstream comparison.",
                    expected_outcome="Demographic comparisons are complete and remain within approved equivalence tolerances.",
                    verification="Regenerate both cohorts and rerun age and categorical demographic comparisons with adequate sample sizes.",
                    blocking=True,
                ),
            )

        finding = InterpretationFinding(
            finding_id=f"EPI.DEMOGRAPHIC_PROFILE.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Demographic population profile",
            status=status,
            severity=severity,
            confidence=_confidence(minimum_n, complete),
            evidence_strength=_evidence_strength(minimum_n, len(rows)),
            observation=observation,
            interpretation=interpretation,
            impact=(
                "Population-level comparisons may proceed for the measured demographics."
                if not blocks
                else "Population-level conclusions are blocked because demographic comparability is not established."
            ),
            evidence=refs,
            recommendations=recommendations,
            limitations=(
                "The rule evaluates only demographic dimensions emitted by the statistical pipeline.",
                "Passing H1 does not establish clinical or causal equivalence.",
            ),
            tags=self.tags,
            confidence_score=(
                0.95
                if complete and minimum_n is not None and minimum_n >= 100
                else 0.70
            ),
            clinically_relevant=True,
            blocks_research_use=blocks,
        )
        inference = Inference(
            inference_id=f"EPI.DEMOGRAPHIC_PROFILE.{status.value.upper()}.INFERENCE",
            statement=interpretation,
            evidence=refs,
            rationale="The decision combines significance, effect magnitude, distribution divergence and sample adequacy.",
            confidence=finding.confidence_score,
        )
        return RuleOutcome(findings=(finding,), inferences=(inference,))


class PopulationPrevalenceProfileRule(EpidemiologicalRule):
    """Interpret H2 across the full set of principal prevalence comparisons."""

    rule_id = "EPI.PREVALENCE_PROFILE"
    domain = "epidemiological"
    description = "Assess population-level preservation of the principal prevalence profile."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("epidemiological", "H2", "prevalence", "population")

    def __init__(self, thresholds: EpidemiologicalThresholds = DEFAULT_THRESHOLDS) -> None:
        self.thresholds = _require_thresholds(thresholds)

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        if not _rows(context, "statistics.prevalence"):
            return ApplicabilityDecision.not_evaluated(
                "No prevalence comparisons were produced by the statistical stage."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = _rows(context, "statistics.prevalence")
        defects: list[str] = []
        material: list[str] = []
        significant_small: list[str] = []
        minimum_sizes: list[int] = []

        for identity, metrics in rows.items():
            absolute = _non_negative_number(metrics, "absolute_difference")
            relative = _non_negative_number(metrics, "relative_difference")
            adjusted_p = _probability(metrics, "adjusted_p_value")
            fdr = _boolean(metrics, "significant_after_fdr")
            n1 = _integer(metrics, "synthea_total")
            n2 = _integer(metrics, "psynthea_total")

            if n1 is not None and n2 is not None:
                minimum_sizes.append(min(n1, n2))
            if None in (absolute, relative, adjusted_p, fdr, n1, n2):
                defects.append(f"{identity}: incomplete prevalence evidence")
                continue
            assert absolute is not None and relative is not None
            assert adjusted_p is not None and fdr is not None
            assert n1 is not None and n2 is not None
            if fdr is not (adjusted_p < self.thresholds.alpha):
                defects.append(f"{identity}: FDR flag disagrees with adjusted p-value")
                continue
            if min(n1, n2) < self.thresholds.minimum_sample_size:
                defects.append(f"{identity}: insufficient cohort size")
                continue

            outside = (
                abs(absolute) > self.thresholds.prevalence_absolute_tolerance
                and abs(relative) > self.thresholds.prevalence_relative_tolerance
            )
            if outside:
                material.append(identity)
            elif fdr:
                significant_small.append(identity)

        row_count = len(rows)
        material_fraction = len(material) / row_count
        warning_fraction = (len(material) + len(significant_small)) / row_count
        minimum_n = min(minimum_sizes) if minimum_sizes else None
        complete = not defects
        refs = _refs(_all_metrics(rows))

        if defects:
            status = FindingStatus.INCONCLUSIVE
            severity = Severity.HIGH
            blocks = True
            interpretation = "H2 cannot be evaluated safely because prevalence evidence is incomplete or contradictory."
        elif material_fraction >= self.thresholds.prevalence_failure_fraction:
            status = FindingStatus.FAIL
            severity = Severity.HIGH
            blocks = True
            interpretation = "A material fraction of principal prevalences differs beyond the configured epidemiological tolerances."
        elif material or warning_fraction >= self.thresholds.prevalence_warning_fraction:
            status = FindingStatus.WARNING
            severity = Severity.MODERATE if material else Severity.LOW
            blocks = bool(material)
            interpretation = (
                "H2 is not fully supported because at least one principal prevalence differs materially."
                if material
                else "H2 is provisionally supported, although small FDR-detectable prevalence differences remain."
            )
        else:
            status = FindingStatus.PASS
            severity = Severity.INFO
            blocks = False
            interpretation = "The measured prevalence profile supports H2 within configured epidemiological tolerances."

        observation = (
            f"Evaluated {row_count} prevalence comparison(s): {len(material)} material, "
            f"{len(significant_small)} statistically significant but within tolerance, "
            f"and {len(defects)} incomplete or inconsistent."
        )
        recommendations: tuple[Recommendation, ...] = ()
        if blocks:
            recommendations = (
                Recommendation(
                    recommendation_id="EPI.PREVALENCE_PROFILE.RECALIBRATE",
                    action="Recalibrate the affected disease modules and rerun prevalence validation.",
                    priority=RecommendationPriority.URGENT,
                    rationale="Material prevalence drift changes the population represented by psynthea.",
                    expected_outcome="Principal prevalence differences remain within the approved absolute and relative tolerances.",
                    verification="Regenerate both cohorts, apply FDR correction and confirm no principal prevalence remains materially discordant.",
                    blocking=True,
                ),
            )

        finding = InterpretationFinding(
            finding_id=f"EPI.PREVALENCE_PROFILE.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Population prevalence profile",
            status=status,
            severity=severity,
            confidence=_confidence(minimum_n, complete),
            evidence_strength=_evidence_strength(minimum_n, row_count),
            observation=observation,
            interpretation=interpretation,
            impact=(
                "The measured disease burden is epidemiologically comparable."
                if status is FindingStatus.PASS
                else "Population-level disease-burden conclusions require the stated limitations or remediation."
            ),
            evidence=refs,
            recommendations=recommendations,
            limitations=(
                "Equivalence is limited to conditions represented in the prevalence table.",
                "Prevalence agreement does not demonstrate preserved temporal or causal relationships.",
            ),
            tags=self.tags,
            confidence_score=(
                0.95
                if complete and minimum_n is not None and minimum_n >= 100
                else 0.70
            ),
            clinically_relevant=True,
            blocks_research_use=blocks,
        )
        inference = Inference(
            inference_id=f"EPI.PREVALENCE_PROFILE.{status.value.upper()}.INFERENCE",
            statement=interpretation,
            evidence=refs,
            rationale="The decision aggregates absolute and relative prevalence differences after FDR correction.",
            confidence=finding.confidence_score,
        )
        return RuleOutcome(findings=(finding,), inferences=(inference,))


class EpidemiologicalRelationshipPreservationRule(EpidemiologicalRule):
    """Interpret H3 only when explicit stratified or relationship evidence exists."""

    rule_id = "EPI.RELATIONSHIP_PRESERVATION"
    domain = "epidemiological"
    description = "Assess preservation of age, sex and comorbidity relationships."
    required_stages = (PipelineStage.STATISTICAL_VALIDATION,)
    tags = ("epidemiological", "H3", "relationships", "comorbidity")

    def __init__(self, thresholds: EpidemiologicalThresholds = DEFAULT_THRESHOLDS) -> None:
        self.thresholds = _require_thresholds(thresholds)

    def _candidate_rows(self, context: RuleContext) -> dict[str, dict[str, object]]:
        candidates: dict[str, dict[str, object]] = {}
        for namespace in (
            "statistics.continuous",
            "statistics.categorical",
            "statistics.distribution",
            "statistics.prevalence",
        ):
            for identity, metrics in _rows(context, namespace).items():
                if _matches(identity, _RELATIONSHIP_TOKENS):
                    candidates[f"{namespace}:{identity}"] = metrics
        return candidates

    def applicability(
        self, context: RuleContext, evidence: Mapping[str, object]
    ) -> ApplicabilityDecision:
        if not self._candidate_rows(context):
            return ApplicabilityDecision.not_evaluated(
                "No explicit age-, sex-, stratified-association or comorbidity comparison evidence was produced; H3 must not be inferred from marginal distributions."
            )
        return ApplicabilityDecision.applicable()

    def interpret(self, context: RuleContext, evidence: Mapping[str, object]) -> RuleOutcome:
        rows = self._candidate_rows(context)
        defects: list[str] = []
        material: list[str] = []
        significant_small: list[str] = []
        minimum_sizes: list[int] = []

        for identity, metrics in rows.items():
            p_value = _number(metrics, "adjusted_p_value")
            significant = _boolean(metrics, "significant_after_fdr")
            if p_value is None or significant is None:
                p_value = _probability(metrics, "p_value")
                significant = _boolean(metrics, "significant")
            effect = _number(metrics, "effect_size")
            if effect is None:
                effect = _number(metrics, "relative_difference")
            n1 = _coalesce(
                _integer(metrics, "n_synthea"),
                _integer(metrics, "synthea_total"),
            )
            n2 = _coalesce(
                _integer(metrics, "n_psynthea"),
                _integer(metrics, "psynthea_total"),
            )
            assert n1 is None or isinstance(n1, int)
            assert n2 is None or isinstance(n2, int)

            if n1 is not None and n2 is not None:
                minimum_sizes.append(min(n1, n2))
            if p_value is None or significant is None or effect is None or n1 is None or n2 is None:
                defects.append(f"{identity}: incomplete relationship evidence")
                continue
            if significant is not (p_value < self.thresholds.alpha):
                defects.append(f"{identity}: significance flag disagrees with p-value")
                continue
            if min(n1, n2) < self.thresholds.minimum_sample_size:
                defects.append(f"{identity}: insufficient sample size")
                continue
            if abs(effect) > self.thresholds.relationship_effect_tolerance:
                material.append(identity)
            elif significant:
                significant_small.append(identity)

        minimum_n = min(minimum_sizes) if minimum_sizes else None
        complete = not defects
        refs = _refs(_all_metrics(rows))
        if defects:
            status, severity, blocks = FindingStatus.INCONCLUSIVE, Severity.HIGH, True
            interpretation = "H3 cannot be evaluated safely from the available relationship evidence."
        elif material:
            status, severity, blocks = FindingStatus.FAIL, Severity.HIGH, True
            interpretation = "At least one measured age, sex or comorbidity relationship differs materially between engines."
        elif significant_small:
            status, severity, blocks = FindingStatus.WARNING, Severity.LOW, False
            interpretation = "H3 is provisionally supported, with statistically detectable but small relationship differences."
        else:
            status, severity, blocks = FindingStatus.PASS, Severity.INFO, False
            interpretation = "The explicit stratified and relationship evidence supports H3 within configured tolerances."

        finding = InterpretationFinding(
            finding_id=f"EPI.RELATIONSHIP_PRESERVATION.{status.value.upper()}",
            rule_id=self.rule_id,
            domain=self.domain,
            title="Epidemiological relationship preservation",
            status=status,
            severity=severity,
            confidence=_confidence(minimum_n, complete),
            evidence_strength=_evidence_strength(minimum_n, len(rows)),
            observation=(
                f"Evaluated {len(rows)} explicit relationship comparison(s): "
                f"{len(material)} material, {len(significant_small)} small significant, "
                f"and {len(defects)} incomplete."
            ),
            interpretation=interpretation,
            impact=(
                "Measured age, sex and comorbidity patterns remain suitable for epidemiological use."
                if not blocks
                else "Research using subgroup or comorbidity relationships is blocked pending remediation."
            ),
            evidence=refs,
            recommendations=(
                (
                    Recommendation(
                        recommendation_id="EPI.RELATIONSHIP_PRESERVATION.REMEDIATE",
                        action="Inspect stratification logic, shared patient attributes and comorbidity transitions for the affected relationship rows.",
                        priority=RecommendationPriority.URGENT,
                        rationale="Marginal equivalence cannot compensate for distorted subgroup or comorbidity relationships.",
                        expected_outcome="All explicit relationship comparisons are complete and within the approved effect tolerance.",
                        verification="Regenerate stratified cohorts and rerun the relationship comparisons with adequate group sizes.",
                        blocking=True,
                    ),
                )
                if blocks
                else ()
            ),
            limitations=(
                "Only explicit relationship rows are interpreted; marginal age, sex or prevalence agreement is not used as a surrogate for H3.",
            ),
            tags=self.tags,
            confidence_score=(
                0.95
                if complete and minimum_n is not None and minimum_n >= 100
                else 0.70
            ),
            clinically_relevant=True,
            blocks_research_use=blocks,
        )
        inference = Inference(
            inference_id=f"EPI.RELATIONSHIP_PRESERVATION.{status.value.upper()}.INFERENCE",
            statement=interpretation,
            evidence=refs,
            rationale="The decision uses only explicit stratified, association or comorbidity evidence.",
            confidence=finding.confidence_score,
        )
        return RuleOutcome(findings=(finding,), inferences=(inference,))


DEFAULT_EPIDEMIOLOGICAL_RULES: Final = (
    DemographicProfileEquivalenceRule(),
    PopulationPrevalenceProfileRule(),
    EpidemiologicalRelationshipPreservationRule(),
)