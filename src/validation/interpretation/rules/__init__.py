"""Public rule API for deterministic scientific interpretation.

The package exports rule contracts, concrete rule families and their immutable
registries.  Consumers should import from this module rather than depending on
private helpers inside individual rule implementations.
"""

from __future__ import annotations

from validation.interpretation.rules.base import (
    Applicability,
    ApplicabilityDecision,
    ClinicalRule,
    DerivedEvidence,
    EpidemiologicalRule,
    EvidenceRequirement,
    Inference,
    InterpretationRule,
    PipelineStage,
    RuleContext,
    RuleDependency,
    RuleDependencyAssessment,
    RuleEvaluation,
    RuleExecutionError,
    RuleExecutionStatus,
    RuleInvariantError,
    RuleOutcome,
    StageAssessment,
    StageStatus,
    StatisticalRule,
    StructuralRule,
    ValidationDimension,
)
from validation.interpretation.rules.clinical import (
    ClinicalCodeOverlapRule,
    ClinicalSignalPreservationRule,
    ClinicalThresholds,
    DEFAULT_CLINICAL_RULES,
    DomainEventRetentionRule,
)
from validation.interpretation.rules.epidemiological import (
    DEFAULT_EPIDEMIOLOGICAL_RULES,
    DemographicProfileEquivalenceRule,
    EpidemiologicalRelationshipPreservationRule,
    EpidemiologicalThresholds,
    PopulationPrevalenceProfileRule,
)
from validation.interpretation.rules.spanish_adaptation import (
    ClinicalContextLinkageRule,
    DEFAULT_SPANISH_ADAPTATION_RULES,
    HealthcareFlowRepresentationRule,
    PrimaryCareRepresentationRule,
    ReferralPathwayRepresentationRule,
    SpanishAdaptationEvidenceIntegrityRule,
    SpanishAdaptationRule,
    SpanishAdaptationThresholds,
)
from validation.interpretation.rules.statistical import (
    DEFAULT_STATISTICAL_RULES,
    DistributionEquivalenceRule,
    GlobalStatisticalReadinessRule,
    PrevalenceEquivalenceRule,
    StatisticalThresholds,
    TestFamilyEquivalenceRule,
)
from validation.interpretation.rules.structural import (
    DEFAULT_STRUCTURAL_RULES,
    EvidenceIntegrityRule,
    RequiredTableAvailabilityRule,
    StructuralComparabilityRule,
)

__all__ = [
    "Applicability",
    "ApplicabilityDecision",
    "ClinicalCodeOverlapRule",
    "ClinicalContextLinkageRule",
    "ClinicalRule",
    "ClinicalSignalPreservationRule",
    "ClinicalThresholds",
    "DEFAULT_CLINICAL_RULES",
    "DEFAULT_EPIDEMIOLOGICAL_RULES",
    "DEFAULT_SPANISH_ADAPTATION_RULES",
    "DEFAULT_STATISTICAL_RULES",
    "DEFAULT_STRUCTURAL_RULES",
    "DemographicProfileEquivalenceRule",
    "DerivedEvidence",
    "DistributionEquivalenceRule",
    "DomainEventRetentionRule",
    "EpidemiologicalRelationshipPreservationRule",
    "EpidemiologicalRule",
    "EpidemiologicalThresholds",
    "EvidenceIntegrityRule",
    "EvidenceRequirement",
    "GlobalStatisticalReadinessRule",
    "HealthcareFlowRepresentationRule",
    "Inference",
    "InterpretationRule",
    "PipelineStage",
    "PopulationPrevalenceProfileRule",
    "PrevalenceEquivalenceRule",
    "PrimaryCareRepresentationRule",
    "ReferralPathwayRepresentationRule",
    "RequiredTableAvailabilityRule",
    "RuleContext",
    "RuleDependency",
    "RuleDependencyAssessment",
    "RuleEvaluation",
    "RuleExecutionError",
    "RuleExecutionStatus",
    "RuleInvariantError",
    "RuleOutcome",
    "SpanishAdaptationEvidenceIntegrityRule",
    "SpanishAdaptationRule",
    "SpanishAdaptationThresholds",
    "StageAssessment",
    "StageStatus",
    "StatisticalRule",
    "StatisticalThresholds",
    "StructuralComparabilityRule",
    "StructuralRule",
    "TestFamilyEquivalenceRule",
    "ValidationDimension",
]