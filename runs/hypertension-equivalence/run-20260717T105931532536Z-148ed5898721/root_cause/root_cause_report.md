# Psynthea Root Cause Analysis Report

- **Report ID:** `root-cause-report:7f7027d0c679a4e2b4b5370a`
- **Request ID:** `root-cause.hypertension-equivalence.run-20260717T105931532536Z-148ed5898721`
- **Experiment ID:** `hypertension-equivalence`
- **Run ID:** `run-20260717T105931532536Z-148ed5898721`
- **Generated at:** `2026-07-17T10:59:37.335977+00:00`
- **Document fingerprint:** `aa29737610947b74c79f8a4cb1e5d1754a4e5d98b70098c2507ac6737546fde9`

## Executive Summary

**Overall status:** `INCONCLUSIVE`  
**Causal confidence:** `NONE`

Root-cause analysis completed: 19 inconclusive, 1 plausible.

| Signals | Evidence | Candidates | Verifications | Findings | Reproduction plans |
| --- | --- | --- | --- | --- | --- |
| 20 | 57 | 20 | 0 | 20 | 0 |

## Causal Findings

### 1. Plausible root cause: Investigate root_cause.engine.probabilistic_semantics as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'.

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:c6c6446b8687bf00208c8de1 |
| Status | plausible |
| Confidence | low |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:1f81c70580a520727657b886 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

Protocol applicability matched validation domain 'domain.global'. The protocol does not assert causality; it defines deterministic evidence and verification steps for this category.

**Selected causal candidates**

| Candidate ID | Statement | Category | Status | Rank | Score |
| --- | --- | --- | --- | --- | --- |
| candidate:14d981437a7ef49d21c78bd80e1215e1 | Investigate root_cause.engine.probabilistic_semantics as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.engine.probabilistic_semantics | not_testable | 1 | 1.55 |

**Alternative candidates**

| Candidate ID | Statement | Category | Status | Rank | Score |
| --- | --- | --- | --- | --- | --- |
| candidate:1636ce8c56526352f1f5c7d0364ec74b | Investigate root_cause.validation.statistical_method as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.validation.statistical_method | not_testable | 2 | 1.55 |
| candidate:293386f9601fec110536167ee2478546 | Investigate root_cause.workflow_adaptation as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.workflow_adaptation | not_testable | 3 | 1.55 |
| candidate:4288aefd1c18ef6026fb6441db06d3fa | Investigate root_cause.engine.execution as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.engine.execution | not_testable | 4 | 1.55 |
| candidate:4521fa588925081c2b917bbbe68cc119 | Investigate root_cause.configuration as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.configuration | not_testable | 5 | 1.55 |
| candidate:613de56b95f46fc427efa9592a769550 | Investigate root_cause.compatibility.round_trip as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.compatibility.round_trip | not_testable | 6 | 1.55 |
| candidate:6f476a6da6f6bc7a29c562dad2463638 | Investigate root_cause.validation.ingestion as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.validation.ingestion | not_testable | 7 | 1.55 |
| candidate:7c6bb2d29bf4fceba31b0e04e6ca68e6 | Investigate root_cause.validation.metric_computation as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.validation.metric_computation | not_testable | 8 | 1.55 |
| candidate:8021004416d265529534742576f77d5c | Investigate root_cause.statistical_artifact as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.statistical_artifact | not_testable | 9 | 1.55 |
| candidate:80edc9f40910d72b4e8403a2614f6e9e | Investigate root_cause.validation.interpretation_logic as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.validation.interpretation_logic | not_testable | 10 | 1.55 |
| candidate:959befe028d93504d4a6ad668f750a1b | Investigate root_cause.validation.harmonization as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.validation.harmonization | not_testable | 11 | 1.55 |
| candidate:96519cdf773acfc375df6649cc2c1d68 | Investigate root_cause.engine.temporal_semantics as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.engine.temporal_semantics | not_testable | 12 | 1.55 |
| candidate:aa7b4d4679f81c86f76f83ee1c4e7782 | Investigate root_cause.compatibility.unsupported_gmf as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.compatibility.unsupported_gmf | not_testable | 13 | 1.55 |
| candidate:bcb25e50ce1a30ac5125faa8f3fa2bec | Investigate root_cause.compatibility.parser_import as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.compatibility.parser_import | not_testable | 14 | 1.55 |
| candidate:c05e5699cb24720ba4216acd4032851d | Investigate root_cause.export as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.export | not_testable | 15 | 1.55 |
| candidate:d3d52f7aee8acfbd58362729b3e5924c | Investigate root_cause.clinical_recording as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.clinical_recording | not_testable | 16 | 1.55 |
| candidate:dcabcfa70cc3fc6f32133743845507b0 | Investigate root_cause.data_quality as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.data_quality | not_testable | 17 | 1.55 |
| candidate:e850db39f86be25c385ad0a0619c34c7 | Investigate root_cause.input_data as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.input_data | not_testable | 18 | 1.55 |
| candidate:e8ad29639f467d54b02bbee472a284ec | Investigate root_cause.module_definition as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.module_definition | not_testable | 19 | 1.55 |
| candidate:f3a52b80ac5fa8d8b840a6bb768ab2e9 | Investigate root_cause.terminology_mapping as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'. | root_cause.terminology_mapping | not_testable | 20 | 1.55 |

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- The leading hypothesis lacks sufficient supporting evidence.
- No deterministic verification was available.

### 2. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'conditions.59621000': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:5a924c54e44de43f9861523f |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.conditions |
| Difference classification | unknown |
| Signals | signal:62c16ffc8728889b5f10dd7a |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 3. No viable causal explanation for: Validation warning: Continuous endpoint 'conditions_per_patient.mann_whitney_u': warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:21e45ed2faa7c25fb9683dad |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:fe22eddf4f4bc09bd02f1652 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 4. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:27ae6af91388e2ca64c7b1a6 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:2712a7c0d28fd141e0b62cb4 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 5. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:29bb9e9e9c821b0e24e95a3b |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:6967fce1fb75412a2bba6fa5 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 6. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:2fcd58adcd200061e5a3ba22 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:e8f9d1e82c383edcb75a1d6d |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 7. No viable causal explanation for: Validation warning: Clinical event retention for 'conditions' is warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:42411ff6035f347612c854bf |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:26323a537b07e4fbe4096d6d |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 8. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'conditions_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:47cabfe69957d95761d5ddd4 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:4d9e81767bfeaa684183a4a3 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 9. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:681c29fff6fbef23c2b0c91c |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:96bc2979f69f9c20c60cb976 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 10. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:a233b7663276535f09e36442 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:e0c2df1f70f006bf38e411e8 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 11. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:a32ead3cc4428bb19ebae63c |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:3e1480914b9d36f9333bf0eb |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 12. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'medications' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:afcc742b36c17ce7e0b54245 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:975945a2a08b6204be66583e |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 13. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:c9fc09d9b2eef1e944e208d9 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:8ce3cb390148995d2a131533 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 14. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'observations' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:ca218ef1d2118c17f4326310 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:9160163674ec317d5ba10185 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 15. No viable causal explanation for: Validation discrepancy: Categorical endpoint 'encounter_class.chi_square': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:ca90e85e09dd1525eedf42f6 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:d83f9fde140a2fda4c7c171e |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 16. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:f1982f1ee303c7a199b8328b |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:a104766a0f9812eb2e5ff5a6 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 17. No viable causal explanation for: Validation warning: Evidence contains not computed values

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:3132e9efaa14fa295d2006c3 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.validation_pipeline |
| Difference classification | unknown |
| Signals | signal:509f80553c919185e43990f5 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 18. No viable causal explanation for: Validation warning: Optional table 'procedures' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:8527753b6c67557d4c59f700 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.validation_pipeline |
| Difference classification | unknown |
| Signals | signal:39a9ba6ed7bacc84e30c5a0a |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 19. No viable causal explanation for: Validation warning: Optional table 'medications' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:df29532f9feadb0447d0f737 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.validation_pipeline |
| Difference classification | unknown |
| Signals | signal:582d9af0a4a2ed3686dcbe6f |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

### 20. No viable causal explanation for: Validation warning: Optional table 'observations' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:e66c3c4388dc68829dc2e250 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.validation_pipeline |
| Difference classification | unknown |
| Signals | signal:91ab5ae66d3cfa66095a83c9 |
| Attribution | Unknown — available evidence does not support a concrete source location. |

**Explanation**

All generated candidates were refuted or no candidate could be assessed.

**Selected causal candidates**

_None._

**Alternative candidates**

_None._

**Rejected candidates**

_None._

**Supporting evidence**

_None._

**Contradictory evidence**

_None._

**Deterministic verification results**

_No verification result is attached to this finding._

**Finding limitations**

- No non-refuted candidate remained after deterministic assessment.

## Investigation Coverage

| Finding status | Count |
| --- | --- |
| inconclusive | 19 |
| plausible | 1 |

## Unresolved Questions

- What additional deterministic evidence can resolve signal signal:1f81c70580a520727657b886?
- What additional deterministic evidence can resolve signal signal:26323a537b07e4fbe4096d6d?
- What additional deterministic evidence can resolve signal signal:2712a7c0d28fd141e0b62cb4?
- What additional deterministic evidence can resolve signal signal:39a9ba6ed7bacc84e30c5a0a?
- What additional deterministic evidence can resolve signal signal:3e1480914b9d36f9333bf0eb?
- What additional deterministic evidence can resolve signal signal:4d9e81767bfeaa684183a4a3?
- What additional deterministic evidence can resolve signal signal:509f80553c919185e43990f5?
- What additional deterministic evidence can resolve signal signal:582d9af0a4a2ed3686dcbe6f?
- What additional deterministic evidence can resolve signal signal:62c16ffc8728889b5f10dd7a?
- What additional deterministic evidence can resolve signal signal:6967fce1fb75412a2bba6fa5?
- What additional deterministic evidence can resolve signal signal:8ce3cb390148995d2a131533?
- What additional deterministic evidence can resolve signal signal:9160163674ec317d5ba10185?
- What additional deterministic evidence can resolve signal signal:91ab5ae66d3cfa66095a83c9?
- What additional deterministic evidence can resolve signal signal:96bc2979f69f9c20c60cb976?
- What additional deterministic evidence can resolve signal signal:975945a2a08b6204be66583e?
- What additional deterministic evidence can resolve signal signal:a104766a0f9812eb2e5ff5a6?
- What additional deterministic evidence can resolve signal signal:d83f9fde140a2fda4c7c171e?
- What additional deterministic evidence can resolve signal signal:e0c2df1f70f006bf38e411e8?
- What additional deterministic evidence can resolve signal signal:e8f9d1e82c383edcb75a1d6d?
- What additional deterministic evidence can resolve signal signal:fe22eddf4f4bc09bd02f1652?

## Limitations

- The leading hypothesis lacks sufficient supporting evidence.
- No deterministic verification was available.
- No non-refuted candidate remained after deterministic assessment.
- Candidate generation exceeded RootCauseRequest.max_candidates; complete alternative-candidate components were retained in deterministic source-priority order.
- No explicit verification plan was available for candidate.

## Artifact Integrity

| Artifact ID | Kind | Path | SHA-256 |
| --- | --- | --- | --- |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:cohort-loading | cohort_load_result | loaded/cohort_loading_manifest.json | f30bf85d3d47dbe93afd5fb747a2fbbfec94534511841eb15240e6f4cecb7cb4 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:cohort-normalization | cohort_normalization_result | normalized/cohort_normalization_manifest.json | 82a13dbdc842c837c03b28cf0afb5798202588f11d10a88d509aa28d4a7e5959 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:knowledge-result | knowledge_result | knowledge/knowledge_result.json | cb25b994dd2df1b43bc037bae2bfe101a9dbd943018a2da179070b28dd1baf8a |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:knowledge:hypertension:json | evidence | knowledge/modules/hypertension/interpretation_report.json | 23825ea84c0cf222e6385ee0c9f53eac40e4785db80efea9f64108213c53a32b |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:knowledge:hypertension:markdown | report | knowledge/modules/hypertension/interpretation_report.md | bce10cc6325e4698e7ac765afb7ff49d727bcc58808d4bc0acc4ecb00e66d8b8 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:psynthea:normalized:conditions | normalized_dataset | normalized/psynthea/conditions.csv | 0b874bcc7f2c17ac1bd2225017a673687281c2e64842dd281e255afc231fb679 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:psynthea:normalized:encounters | normalized_dataset | normalized/psynthea/encounters.csv | 42d2769e1a5e6a0c71aefc242ac2d0a8a0062e0736776358119d7543c9320a32 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:psynthea:normalized:medications | normalized_dataset | normalized/psynthea/medications.csv | 3cd75e58bcfb737e1d45ae51e6349b9153e6a2c2e01bd55e82db55248adf6970 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:psynthea:normalized:observations | normalized_dataset | normalized/psynthea/observations.csv | 2002311e58c3a0140a809583275bb64afdec77337fab92ad370b5d2adb9e633c |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:psynthea:normalized:patients | normalized_dataset | normalized/psynthea/patients.csv | 7a9c4bf6e241b9873285f10bbb2a8ea093187a14c8fd43587277610251374c45 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:psynthea:normalized:procedures | normalized_dataset | normalized/psynthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:synthea:normalized:conditions | normalized_dataset | normalized/synthea/conditions.csv | 7d8e4eb1bfa170bf16fbab90503a7abf844bebb63879c12bf7ac495b8a532867 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:synthea:normalized:encounters | normalized_dataset | normalized/synthea/encounters.csv | ddb1a8ac751f48d83bfcb8a1131c69780e1b9414dd67bdb60d24c07fc3590b21 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:synthea:normalized:medications | normalized_dataset | normalized/synthea/medications.csv | d23058fb72b0335f5395c70ecb0d0078c40cea6697834cdf40870118ea81254d |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:synthea:normalized:observations | normalized_dataset | normalized/synthea/observations.csv | e4fa553da2f195531093b67bf7a8be3f5a50a88405d42d0df2c28888a2d5ee8e |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:synthea:normalized:patients | normalized_dataset | normalized/synthea/patients.csv | b37c48f44c18c407ac58a722484bd0f5f053bb3f13cbdc4ff3907cf8e2559e68 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:synthea:normalized:procedures | normalized_dataset | normalized/synthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation-result | validation_result | validation/validation_result.json | df2feba0d2bf536f1a2b9f743cd7a1a7170c20ba3d09218a5594c4cfd4db1543 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:categorical_tests | evidence | validation/modules/hypertension/categorical_tests.csv | f462b35cfef7c5ca88d6f7efdfa79c472b326bc075832af26af5ec659408ed5b |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:continuous_tests | evidence | validation/modules/hypertension/continuous_tests.csv | 3888968b89581ac0868972372b983a1bea19881efb7c69bf35f4f78ba14ad9f0 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:distribution_tests | evidence | validation/modules/hypertension/distribution_tests.csv | c04270c9def964e72ad74c7b81e8b65d4f9193b4bda1c64c6547882e71919f49 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:functional_clinical_signal | evidence | validation/modules/hypertension/functional_clinical_signal.csv | cfcfe8dcfdd8070272bc1df6b714ccf96b25402499cc39553d55f13aa7b17401 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:functional_distributional_similarity | evidence | validation/modules/hypertension/functional_distributional_similarity.csv | eb04d2f6925f03e04cbff8b5c326eff055f1a38a129ae6fb4cf8e213a118f775 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:functional_issues | evidence | validation/modules/hypertension/functional_issues.csv | 238f47cc153ecdef05138874ec6fa6494aab38b883ddd8ce3610050c666293ff |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:functional_summary | evidence | validation/modules/hypertension/functional_summary.csv | ab34728d26d98adf650b63b550980c5f5685eb4c572f46c185f6645bb7096315 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:functional_table_status | evidence | validation/modules/hypertension/functional_table_status.csv | 894d0b50175fd337b2336ecec9ac882a25065ac79a9477c903366e5bef8b87f1 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:prevalence_tests | evidence | validation/modules/hypertension/prevalence_tests.csv | c2a6d14838872a6f1b6debe1e8ceedd808a5eba6fc1cb261b802e23441f235c7 |
| hypertension-equivalence:run-20260717T105931532536Z-148ed5898721:validation:hypertension:statistical_summary | evidence | validation/modules/hypertension/statistical_summary.csv | 858b1ea318108557968f88c7e59eafa224f8d6f9658bab108327742d5c6cda6c |
| psynthea.output.3134ff4e3946581f | simulator_output | simulators/psynthea/raw/psynthea/patients.csv | 15d12c907aaecae78f3778d1719f2a8b93bb2c73198f339276938412bd485c64 |
| psynthea.output.3e5f7135a4c3e315 | simulator_output | simulators/psynthea/raw/psynthea/observations.csv | 8d7df09dcc5fc0e90c550272085496dac8fef08aacfaf813328cc626c1758452 |
| psynthea.output.6ab6e2f5318e23b2 | simulator_output | simulators/psynthea/raw/psynthea/medications.csv | b12f12386414f769a54c82608df3a8da3001e5cf2bf6149f45e68076e77210c0 |
| psynthea.output.6b9d1865d362e102 | simulator_output | simulators/psynthea/raw/psynthea/conditions.csv | 99c00399b08234275c75af73c526176d6c7b19a6aa758a42c928a2ac99773c5b |
| psynthea.output.a4b3c0aa1d75ef18 | simulator_output | simulators/psynthea/raw/psynthea/encounters.csv | 1fc973d9125b33ef31c84b399adbcc52174d60c32532357ed4edcfd165d709d7 |
| psynthea.stderr | log | simulators/psynthea/logs/stderr.log | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| psynthea.stdout | log | simulators/psynthea/logs/stdout.log | 6e259e5302c47e25133246581b866fc13b1f8e1c12c708ecfc163f34dfe95b4d |
| synthea.output.0e78ece284d452a9 | simulator_output | simulators/synthea/raw/synthea/csv/conditions.csv | f719d07239ae6efaf715e1f56c2c1f2f446e2305ec9c9ae0d2975cb79a4999ce |
| synthea.output.16387b7dcccd33e9 | simulator_output | simulators/synthea/raw/synthea/csv/encounters.csv | 008612328589a861ab46b6f6c35e18ff31055566f680b396fc5f6672e73ad7f4 |
| synthea.output.1ba7dcff16432d09 | simulator_output | simulators/synthea/raw/synthea/fhir/hospitalInformation1784285972100.json | 9fa38facf04bdf77bf6f56ac34e8aba1ad6e9ee81694985adbb8a4fcd3bd3a59 |
| synthea.output.3668d5f59d6209c9 | simulator_output | simulators/synthea/raw/synthea/csv/immunizations.csv | bf9a06d9e1a4f1dad36b455eda78bb2f0341b20446719f13a14a53b278491811 |
| synthea.output.43cc910006f50bf1 | simulator_output | simulators/synthea/raw/synthea/csv/observations.csv | 45ce34c59d5a5d012207b561e3e027f241fd9867f7d23d0d0faf19235ebfaa11 |
| synthea.output.476eb5690885cca7 | simulator_output | simulators/synthea/raw/synthea/metadata/2026_07_17T10_59_32Z_100_Massachusetts_1e95a9cb_4816_4df3_9d35_df8009f287e8.json | 3d5ac130d6e21d36a312cd3821add06913a7678da626529a0dcbb300da7aa35f |
| synthea.output.5dfe786b69089d98 | simulator_output | simulators/synthea/raw/synthea/csv/claims_transactions.csv | acc7018acb06670fb24a4f1e50bfc391c20e742cbc36230c4c216141761d49a5 |
| synthea.output.87ca68789f71a8f3 | simulator_output | simulators/synthea/raw/synthea/csv/payer_transitions.csv | ffc033ee2362484c88d020ecb95d6459f6efc7ba57e47c5fe980046eeaf0bc4f |
| synthea.output.8a61c8aab8685e4e | simulator_output | simulators/synthea/raw/synthea/csv/medications.csv | 9a60c7517f3795880d7156ba3109617a33fe5e87c2ef17977c1c93b0ac02cfed |
| synthea.output.9978b02439836c2a | simulator_output | simulators/synthea/raw/synthea/csv/careplans.csv | 6b085182465a975aefeff75793b5a28d5b59e7adece1d0d0d6af9bfaa07ceb86 |
| synthea.output.dc344f5331e02783 | simulator_output | simulators/synthea/raw/synthea/csv/providers.csv | fb400d4019b1b3564d9a91baf66bff8a0dda1aa3c72f8ce92bc2262141934ca9 |
| synthea.output.dddac2726573d04c | simulator_output | simulators/synthea/raw/synthea/csv/organizations.csv | d8a2e17547a50807279147f5c7aaa03e7a572e515efbe9b65461b8db7cdd555b |
| synthea.output.e27c964ac456e35f | simulator_output | simulators/synthea/raw/synthea/csv/patients.csv | 36d7d731537f223219ab60b9f34f025be7753d2423543c4b0c0d24664f47e682 |
| synthea.output.e54184ec586801a3 | simulator_output | simulators/synthea/raw/synthea/fhir/practitionerInformation1784285972100.json | a4155d4fbc2bd3261543c906e3d0dcd0dc7a13a877b4d27b9e81dec0ebbc8ad2 |
| synthea.output.ebcec8fc08e46fda | simulator_output | simulators/synthea/raw/synthea/csv/payers.csv | cf2e102678b8a7eedb68ff91b9050802144060e93ac9c856a6bdfe4f1b019c40 |
| synthea.output.eca4593c09a762be | simulator_output | simulators/synthea/raw/synthea/csv/claims.csv | e42d2f21ba27f788b1c63da381a831f8a921e871bc29606cf1a5fd3f8fe60b12 |
| synthea.stderr | log | simulators/synthea/logs/stderr.log | 6592844c6fd8042db0dedfa6a937b42582873effa9baf939d4d1ddbb462f2fbc |
| synthea.stdout | log | simulators/synthea/logs/stdout.log | 9a8f0a9954153ab68f1da881047beba6fee718748f51b9f3bb2932ab4d1af371 |

## Engine Audit Trail

| Stage | Started | Finished | Duration (s) | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| evidence_collection | 2026-07-17T10:59:37.304573+00:00 | 2026-07-17T10:59:37.306968+00:00 | 0.002395 | 57 | 57 |
| signal_extraction | 2026-07-17T10:59:37.306976+00:00 | 2026-07-17T10:59:37.307976+00:00 | 0.001000 | 57 | 20 |
| candidate_generation | 2026-07-17T10:59:37.307982+00:00 | 2026-07-17T10:59:37.329680+00:00 | 0.021698 | 20 | 20 |
| candidate_ranking | 2026-07-17T10:59:37.329686+00:00 | 2026-07-17T10:59:37.331478+00:00 | 0.001792 | 20 | 20 |
| verification | 2026-07-17T10:59:37.331526+00:00 | 2026-07-17T10:59:37.332143+00:00 | 0.000617 | 20 | 0 |
| attribution | 2026-07-17T10:59:37.332162+00:00 | 2026-07-17T10:59:37.334927+00:00 | 0.002765 | 20 | 20 |
| classification | 2026-07-17T10:59:37.334937+00:00 | 2026-07-17T10:59:37.335261+00:00 | 0.000324 | 20 | 20 |
| reproduction | 2026-07-17T10:59:37.335265+00:00 | 2026-07-17T10:59:37.335268+00:00 | 0.000003 | 1 | 0 |
| report_assembly | 2026-07-17T10:59:37.335734+00:00 | 2026-07-17T10:59:37.335918+00:00 | 0.000184 | 20 | 1 |

## Metadata

```json
{
  "document": {
    "engine": {
      "request_id": "root-cause.hypertension-equivalence.run-20260717T105931532536Z-148ed5898721"
    },
    "presentation": {
      "experiment_id": "hypertension-equivalence",
      "orchestrator_run_id": "run-20260717T105931532536Z-148ed5898721",
      "stage": "root_cause_analysis"
    }
  },
  "report": {
    "input_metadata": {
      "experiment_id": "hypertension-equivalence",
      "explicit_evidence_source_count": 0,
      "interpretation_finding_source_count": 56,
      "interpretation_report_id": "hypertension-equivalence.run-20260717T105931532536Z-148ed5898721.hypertension.interpretation",
      "investigation_source_count": 0,
      "knowledge_entry_source_count": 0,
      "orchestrator_run_id": "run-20260717T105931532536Z-148ed5898721",
      "validation_evidence_source_count": 1
    },
    "schema_version": 2,
    "stage_order": [
      "evidence_collection",
      "signal_extraction",
      "candidate_generation",
      "candidate_ranking",
      "verification",
      "attribution",
      "classification",
      "reproduction",
      "report_assembly"
    ]
  }
}
```

## Scientific Interpretation Boundary

This document reports the conclusions produced by the Root Cause Engine. Rendering did not recalculate statistics, rerank candidates, execute commands, or alter causal status.
