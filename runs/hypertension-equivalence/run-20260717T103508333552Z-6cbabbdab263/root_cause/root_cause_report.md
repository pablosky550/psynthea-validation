# Psynthea Root Cause Analysis Report

- **Report ID:** `root-cause-report:a0157aa170b51d731b786be5`
- **Request ID:** `root-cause.hypertension-equivalence.run-20260717T103508333552Z-6cbabbdab263`
- **Experiment ID:** `hypertension-equivalence`
- **Run ID:** `run-20260717T103508333552Z-6cbabbdab263`
- **Generated at:** `2026-07-17T10:35:14.211017+00:00`
- **Document fingerprint:** `2646922b6f384019115ee8cf21e6d31fd26bcc19d6132439a4a237b798197ff4`

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
| Finding ID | root-cause-finding:f3bfe685f4449c0b013e0a2c |
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
| Finding ID | root-cause-finding:e34c3771f6202b9aaaf6b7a3 |
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

### 3. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:261aa21e52a624ace620ab9f |
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

### 4. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:2f710b85d5c01cb0b7844a9a |
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

### 5. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'conditions_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:382707f90677be78fe9426da |
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

### 6. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:4d385533f0422ed563d25449 |
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

### 7. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:4f68356ab480f770f1e9af18 |
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

### 8. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:9126473af8b61bbf5cf7b458 |
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

### 9. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'medications' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:91a8751e7c863eaf8632f44c |
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

### 10. No viable causal explanation for: Validation warning: Clinical event retention for 'conditions' is warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:a37b4c072b1785c4bc5ea624 |
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

### 11. No viable causal explanation for: Validation warning: Continuous endpoint 'conditions_per_patient.mann_whitney_u': warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:ad076629b23c1c522b884bc2 |
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

### 12. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:aee8a873911ac4c3abdb6ef7 |
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

### 13. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:b3c997c852d938ee4443007f |
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

### 14. No viable causal explanation for: Validation discrepancy: Categorical endpoint 'encounter_class.chi_square': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:b7849cde712bcddf4c207027 |
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

### 15. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:f6ba61cc92993ff9b36f7345 |
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

### 16. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'observations' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:f7ba8b6a42dcc26d15f2b0fb |
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

### 17. No viable causal explanation for: Validation warning: Optional table 'medications' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:0611f4051e31224c62b524d2 |
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

### 18. No viable causal explanation for: Validation warning: Optional table 'procedures' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:155bcc2e8408bfbfda3b2b02 |
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

### 19. No viable causal explanation for: Validation warning: Optional table 'observations' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:31d522d39c8adfc412703b50 |
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

### 20. No viable causal explanation for: Validation warning: Evidence contains not computed values

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:3a2f615d2b7334e5c89cb4c3 |
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
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:cohort-loading | cohort_load_result | loaded/cohort_loading_manifest.json | 13eb49f84a6b0837e59ba80744a52d7f307d29d1e696093cda2870bc64f93f63 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:cohort-normalization | cohort_normalization_result | normalized/cohort_normalization_manifest.json | c03a7cff969512e772897d598466acd09e115c0ec6e45b6ebffb0e392870fc6d |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:knowledge-result | knowledge_result | knowledge/knowledge_result.json | 59f80d5a508fd3748e682915c651a4f7828338ee2f4e0a2b580c96831f353667 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:knowledge:hypertension:json | evidence | knowledge/modules/hypertension/interpretation_report.json | 997e1c6629c8347fa9df9389f45b12ed0ddfef0c7cb1bfe26d0d8e6fafa694e5 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:knowledge:hypertension:markdown | report | knowledge/modules/hypertension/interpretation_report.md | 0b718ca91b5757473e12a289b569724f6bd3c5ed6d4ba531a64c22dd338e8096 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:psynthea:normalized:conditions | normalized_dataset | normalized/psynthea/conditions.csv | 0b874bcc7f2c17ac1bd2225017a673687281c2e64842dd281e255afc231fb679 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:psynthea:normalized:encounters | normalized_dataset | normalized/psynthea/encounters.csv | 42d2769e1a5e6a0c71aefc242ac2d0a8a0062e0736776358119d7543c9320a32 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:psynthea:normalized:medications | normalized_dataset | normalized/psynthea/medications.csv | 3cd75e58bcfb737e1d45ae51e6349b9153e6a2c2e01bd55e82db55248adf6970 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:psynthea:normalized:observations | normalized_dataset | normalized/psynthea/observations.csv | 2002311e58c3a0140a809583275bb64afdec77337fab92ad370b5d2adb9e633c |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:psynthea:normalized:patients | normalized_dataset | normalized/psynthea/patients.csv | 7a9c4bf6e241b9873285f10bbb2a8ea093187a14c8fd43587277610251374c45 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:psynthea:normalized:procedures | normalized_dataset | normalized/psynthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:synthea:normalized:conditions | normalized_dataset | normalized/synthea/conditions.csv | 7d8e4eb1bfa170bf16fbab90503a7abf844bebb63879c12bf7ac495b8a532867 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:synthea:normalized:encounters | normalized_dataset | normalized/synthea/encounters.csv | 7445bfaf8798703fef77a0d3291b29592c7c8e4b19b696c086f191dd775ffa33 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:synthea:normalized:medications | normalized_dataset | normalized/synthea/medications.csv | d23058fb72b0335f5395c70ecb0d0078c40cea6697834cdf40870118ea81254d |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:synthea:normalized:observations | normalized_dataset | normalized/synthea/observations.csv | e4fa553da2f195531093b67bf7a8be3f5a50a88405d42d0df2c28888a2d5ee8e |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:synthea:normalized:patients | normalized_dataset | normalized/synthea/patients.csv | b37c48f44c18c407ac58a722484bd0f5f053bb3f13cbdc4ff3907cf8e2559e68 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:synthea:normalized:procedures | normalized_dataset | normalized/synthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation-result | validation_result | validation/validation_result.json | 7f49b0c060619fb8a1c209ee39a5fc6040a632070c838a9f162061154dd061ae |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:categorical_tests | evidence | validation/modules/hypertension/categorical_tests.csv | f462b35cfef7c5ca88d6f7efdfa79c472b326bc075832af26af5ec659408ed5b |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:continuous_tests | evidence | validation/modules/hypertension/continuous_tests.csv | 3888968b89581ac0868972372b983a1bea19881efb7c69bf35f4f78ba14ad9f0 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:distribution_tests | evidence | validation/modules/hypertension/distribution_tests.csv | c04270c9def964e72ad74c7b81e8b65d4f9193b4bda1c64c6547882e71919f49 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:functional_clinical_signal | evidence | validation/modules/hypertension/functional_clinical_signal.csv | cfcfe8dcfdd8070272bc1df6b714ccf96b25402499cc39553d55f13aa7b17401 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:functional_distributional_similarity | evidence | validation/modules/hypertension/functional_distributional_similarity.csv | eb04d2f6925f03e04cbff8b5c326eff055f1a38a129ae6fb4cf8e213a118f775 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:functional_issues | evidence | validation/modules/hypertension/functional_issues.csv | 238f47cc153ecdef05138874ec6fa6494aab38b883ddd8ce3610050c666293ff |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:functional_summary | evidence | validation/modules/hypertension/functional_summary.csv | ab34728d26d98adf650b63b550980c5f5685eb4c572f46c185f6645bb7096315 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:functional_table_status | evidence | validation/modules/hypertension/functional_table_status.csv | 894d0b50175fd337b2336ecec9ac882a25065ac79a9477c903366e5bef8b87f1 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:prevalence_tests | evidence | validation/modules/hypertension/prevalence_tests.csv | c2a6d14838872a6f1b6debe1e8ceedd808a5eba6fc1cb261b802e23441f235c7 |
| hypertension-equivalence:run-20260717T103508333552Z-6cbabbdab263:validation:hypertension:statistical_summary | evidence | validation/modules/hypertension/statistical_summary.csv | 858b1ea318108557968f88c7e59eafa224f8d6f9658bab108327742d5c6cda6c |
| psynthea.output.3134ff4e3946581f | simulator_output | simulators/psynthea/raw/psynthea/patients.csv | 15d12c907aaecae78f3778d1719f2a8b93bb2c73198f339276938412bd485c64 |
| psynthea.output.3e5f7135a4c3e315 | simulator_output | simulators/psynthea/raw/psynthea/observations.csv | 8d7df09dcc5fc0e90c550272085496dac8fef08aacfaf813328cc626c1758452 |
| psynthea.output.6ab6e2f5318e23b2 | simulator_output | simulators/psynthea/raw/psynthea/medications.csv | b12f12386414f769a54c82608df3a8da3001e5cf2bf6149f45e68076e77210c0 |
| psynthea.output.6b9d1865d362e102 | simulator_output | simulators/psynthea/raw/psynthea/conditions.csv | 99c00399b08234275c75af73c526176d6c7b19a6aa758a42c928a2ac99773c5b |
| psynthea.output.a4b3c0aa1d75ef18 | simulator_output | simulators/psynthea/raw/psynthea/encounters.csv | 1fc973d9125b33ef31c84b399adbcc52174d60c32532357ed4edcfd165d709d7 |
| psynthea.stderr | log | simulators/psynthea/logs/stderr.log | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| psynthea.stdout | log | simulators/psynthea/logs/stdout.log | 6c6e5248c8ccd30071090756847708f39a5ddc7664a5bc30981a5c9678e92a85 |
| synthea.output.0e78ece284d452a9 | simulator_output | simulators/synthea/raw/synthea/csv/conditions.csv | 51054c9767d0c7ad6a858c68af48d7f1df288787f574309ef292a42ebf833ebf |
| synthea.output.16387b7dcccd33e9 | simulator_output | simulators/synthea/raw/synthea/csv/encounters.csv | ab33a73cebc3f5a9c709a26d8d76a330b7f907f4e136e66e498868ad0143e7ba |
| synthea.output.1e01a60a3ad57aff | simulator_output | simulators/synthea/raw/synthea/fhir/hospitalInformation1784284508913.json | 9fa38facf04bdf77bf6f56ac34e8aba1ad6e9ee81694985adbb8a4fcd3bd3a59 |
| synthea.output.3668d5f59d6209c9 | simulator_output | simulators/synthea/raw/synthea/csv/immunizations.csv | 3daeae7975e959cfadb6ddfa6ad3e43226c273981bde94d9de784c97c1144add |
| synthea.output.43cc910006f50bf1 | simulator_output | simulators/synthea/raw/synthea/csv/observations.csv | 09beb117641282eb9783144cf5012d12786031ec24fdbf2afa10f41ae052da9a |
| synthea.output.5dfe786b69089d98 | simulator_output | simulators/synthea/raw/synthea/csv/claims_transactions.csv | b9a8315b3d62200264045facfa4e89581db9baebc7738d805149ced7155582ac |
| synthea.output.7da44dbe5cc6ced3 | simulator_output | simulators/synthea/raw/synthea/fhir/practitionerInformation1784284508913.json | 82e802141b018dd2bde15f638926416e153a11fcd1b053fe744dc3843b64d933 |
| synthea.output.87ca68789f71a8f3 | simulator_output | simulators/synthea/raw/synthea/csv/payer_transitions.csv | 307f68a01c819f67cf7957b8982bf09b06a1515d80d72053c2e00f250298eb2e |
| synthea.output.8a61c8aab8685e4e | simulator_output | simulators/synthea/raw/synthea/csv/medications.csv | 01d53f393d4de71cea3dfbb9c96bbf6cb0722d13f9a534de2695cc39c090dd28 |
| synthea.output.9978b02439836c2a | simulator_output | simulators/synthea/raw/synthea/csv/careplans.csv | bc72e255609725f40696286c256c76380aa71b2bd380ebbe0234e607d4563607 |
| synthea.output.dc344f5331e02783 | simulator_output | simulators/synthea/raw/synthea/csv/providers.csv | 70bdf62f76333b653253f6db2669af594647b5b3a1275f99c3f1be7dc11b5b72 |
| synthea.output.dddac2726573d04c | simulator_output | simulators/synthea/raw/synthea/csv/organizations.csv | d8a2e17547a50807279147f5c7aaa03e7a572e515efbe9b65461b8db7cdd555b |
| synthea.output.e27c964ac456e35f | simulator_output | simulators/synthea/raw/synthea/csv/patients.csv | 27d5267debd283a36488b965f02b30fda5b889ed410762f92026d2f3bd1dcfc8 |
| synthea.output.e9dddf76988e3f51 | simulator_output | simulators/synthea/raw/synthea/metadata/2026_07_17T10_35_08Z_100_Massachusetts_23a4a2c2_95ca_44d6_b2c1_3f8df091e6d3.json | 40d8461298272e1a52f15e6bc3e96595b6bf8a405d665ed874b8192bc22de590 |
| synthea.output.ebcec8fc08e46fda | simulator_output | simulators/synthea/raw/synthea/csv/payers.csv | bb950e17dd3b403f676d50775a7e740b7f1c5d5f8224f715da443fd12c1a9c8b |
| synthea.output.eca4593c09a762be | simulator_output | simulators/synthea/raw/synthea/csv/claims.csv | 72ef7cc516b586a1bbb9b12f37a6b8e29608bbd9ec2cf9781063275468f83cad |
| synthea.stderr | log | simulators/synthea/logs/stderr.log | 6592844c6fd8042db0dedfa6a937b42582873effa9baf939d4d1ddbb462f2fbc |
| synthea.stdout | log | simulators/synthea/logs/stdout.log | b276352057fc9352af043873d482ec1dcf656e8bec94e5a46f554e122c6a141f |

## Engine Audit Trail

| Stage | Started | Finished | Duration (s) | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| evidence_collection | 2026-07-17T10:35:14.179796+00:00 | 2026-07-17T10:35:14.182177+00:00 | 0.002381 | 57 | 57 |
| signal_extraction | 2026-07-17T10:35:14.182184+00:00 | 2026-07-17T10:35:14.183169+00:00 | 0.000985 | 57 | 20 |
| candidate_generation | 2026-07-17T10:35:14.183175+00:00 | 2026-07-17T10:35:14.204759+00:00 | 0.021584 | 20 | 20 |
| candidate_ranking | 2026-07-17T10:35:14.204765+00:00 | 2026-07-17T10:35:14.206551+00:00 | 0.001786 | 20 | 20 |
| verification | 2026-07-17T10:35:14.206602+00:00 | 2026-07-17T10:35:14.207216+00:00 | 0.000614 | 20 | 0 |
| attribution | 2026-07-17T10:35:14.207235+00:00 | 2026-07-17T10:35:14.209964+00:00 | 0.002729 | 20 | 20 |
| classification | 2026-07-17T10:35:14.209975+00:00 | 2026-07-17T10:35:14.210300+00:00 | 0.000325 | 20 | 20 |
| reproduction | 2026-07-17T10:35:14.210305+00:00 | 2026-07-17T10:35:14.210307+00:00 | 0.000002 | 1 | 0 |
| report_assembly | 2026-07-17T10:35:14.210771+00:00 | 2026-07-17T10:35:14.210958+00:00 | 0.000187 | 20 | 1 |

## Metadata

```json
{
  "document": {
    "engine": {
      "request_id": "root-cause.hypertension-equivalence.run-20260717T103508333552Z-6cbabbdab263"
    },
    "presentation": {
      "experiment_id": "hypertension-equivalence",
      "orchestrator_run_id": "run-20260717T103508333552Z-6cbabbdab263",
      "stage": "root_cause_analysis"
    }
  },
  "report": {
    "input_metadata": {
      "experiment_id": "hypertension-equivalence",
      "explicit_evidence_source_count": 0,
      "interpretation_finding_source_count": 56,
      "interpretation_report_id": "hypertension-equivalence.run-20260717T103508333552Z-6cbabbdab263.hypertension.interpretation",
      "investigation_source_count": 0,
      "knowledge_entry_source_count": 0,
      "orchestrator_run_id": "run-20260717T103508333552Z-6cbabbdab263",
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
