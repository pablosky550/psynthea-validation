# Psynthea Root Cause Analysis Report

- **Report ID:** `root-cause-report:809ad3c353131e64318cf094`
- **Request ID:** `root-cause.hypertension-equivalence.run-20260717T114007526034Z-92a6751f1cef`
- **Experiment ID:** `hypertension-equivalence`
- **Run ID:** `run-20260717T114007526034Z-92a6751f1cef`
- **Generated at:** `2026-07-17T11:40:13.330756+00:00`
- **Document fingerprint:** `7a8ee9ff6b3cb5e6a8cb443fae578e838d3f1e13415f9369acdc42d0ebaa2ac7`

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
| Finding ID | root-cause-finding:c67f57b325cf455aac348baf |
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
| Finding ID | root-cause-finding:3585b4097e491cce02f08c44 |
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

### 3. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:0f538ad7e1268fcd598c86f6 |
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

### 4. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:14141ae9c47a29ed10cb3ac8 |
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

### 5. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'observations' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:235da4d7f8bdd7030d94ca0b |
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

### 6. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'conditions_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:2e7ae4bcf7624cfdb18cf812 |
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

### 7. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:437bea2c7ec8ca5a4b3c5604 |
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

### 8. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'medications' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:46033de3b84036633c91c405 |
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

### 9. No viable causal explanation for: Validation discrepancy: Categorical endpoint 'encounter_class.chi_square': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:522d6d2d17deca5df6c9fa58 |
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

### 10. No viable causal explanation for: Validation warning: Continuous endpoint 'conditions_per_patient.mann_whitney_u': warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:53428d7156056f0202fba901 |
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

### 11. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:72bcc9836b1629f71a0dddf7 |
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

### 12. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:95edb96ef3dccd162abf457b |
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

### 13. No viable causal explanation for: Validation warning: Clinical event retention for 'conditions' is warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:9bd1070d7e9adde1569287a4 |
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

### 14. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:a1e288b222e9edac98ace2eb |
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

### 15. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:a2e12a85829eed88e57ffda9 |
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

### 16. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'observations_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:f44d302d3f0dd7a20ca49034 |
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

### 17. No viable causal explanation for: Validation warning: Evidence contains not computed values

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:5f50758afbc1a6a99657ead4 |
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

### 18. No viable causal explanation for: Validation warning: Optional table 'observations' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:6050c4a900647853bde0ceb1 |
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

### 19. No viable causal explanation for: Validation warning: Optional table 'procedures' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:6283f63547735dca2e3c7ef4 |
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

### 20. No viable causal explanation for: Validation warning: Optional table 'medications' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:acc9b134c2d7b7dc722c2861 |
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
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:cohort-loading | cohort_load_result | loaded/cohort_loading_manifest.json | 1da59e93411761b2d685ae0169f05d1dbf7fa4c0243a510b29b9672dec7c656c |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:cohort-normalization | cohort_normalization_result | normalized/cohort_normalization_manifest.json | 1bd3ee40c57ae3630e242c72574b6995be9c978f8474c9435f17f05855b343a5 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:knowledge-result | knowledge_result | knowledge/knowledge_result.json | d81b82f457c66757a82d6b533f4ff19cfd5cfdcd7bb61328cea7fbc7db310257 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:knowledge:hypertension:json | evidence | knowledge/modules/hypertension/interpretation_report.json | 3ee9ba120332fb9913f8fcfa90544347545ce85b59b1a3a03cb8d68059252e51 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:knowledge:hypertension:markdown | report | knowledge/modules/hypertension/interpretation_report.md | a4fad613c446908f71155598821b78b802c1916331baec1007f5a332141a169c |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:psynthea:normalized:conditions | normalized_dataset | normalized/psynthea/conditions.csv | 0b874bcc7f2c17ac1bd2225017a673687281c2e64842dd281e255afc231fb679 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:psynthea:normalized:encounters | normalized_dataset | normalized/psynthea/encounters.csv | 42d2769e1a5e6a0c71aefc242ac2d0a8a0062e0736776358119d7543c9320a32 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:psynthea:normalized:medications | normalized_dataset | normalized/psynthea/medications.csv | 3cd75e58bcfb737e1d45ae51e6349b9153e6a2c2e01bd55e82db55248adf6970 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:psynthea:normalized:observations | normalized_dataset | normalized/psynthea/observations.csv | 2002311e58c3a0140a809583275bb64afdec77337fab92ad370b5d2adb9e633c |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:psynthea:normalized:patients | normalized_dataset | normalized/psynthea/patients.csv | 7a9c4bf6e241b9873285f10bbb2a8ea093187a14c8fd43587277610251374c45 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:psynthea:normalized:procedures | normalized_dataset | normalized/psynthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:synthea:normalized:conditions | normalized_dataset | normalized/synthea/conditions.csv | 7d8e4eb1bfa170bf16fbab90503a7abf844bebb63879c12bf7ac495b8a532867 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:synthea:normalized:encounters | normalized_dataset | normalized/synthea/encounters.csv | 85c6a28875d9fd727e7ae67f1ddaa267de9b29d803cb82df5fcc6cce83c8a19f |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:synthea:normalized:medications | normalized_dataset | normalized/synthea/medications.csv | d23058fb72b0335f5395c70ecb0d0078c40cea6697834cdf40870118ea81254d |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:synthea:normalized:observations | normalized_dataset | normalized/synthea/observations.csv | e4fa553da2f195531093b67bf7a8be3f5a50a88405d42d0df2c28888a2d5ee8e |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:synthea:normalized:patients | normalized_dataset | normalized/synthea/patients.csv | b37c48f44c18c407ac58a722484bd0f5f053bb3f13cbdc4ff3907cf8e2559e68 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:synthea:normalized:procedures | normalized_dataset | normalized/synthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation-result | validation_result | validation/validation_result.json | 71c93d782a002a3f02be477c0af3ef4ecc572f60e8a1ac71a8f1167603e0d6d8 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:categorical_tests | evidence | validation/modules/hypertension/categorical_tests.csv | f462b35cfef7c5ca88d6f7efdfa79c472b326bc075832af26af5ec659408ed5b |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:continuous_tests | evidence | validation/modules/hypertension/continuous_tests.csv | 3888968b89581ac0868972372b983a1bea19881efb7c69bf35f4f78ba14ad9f0 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:distribution_tests | evidence | validation/modules/hypertension/distribution_tests.csv | c04270c9def964e72ad74c7b81e8b65d4f9193b4bda1c64c6547882e71919f49 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:functional_clinical_signal | evidence | validation/modules/hypertension/functional_clinical_signal.csv | cfcfe8dcfdd8070272bc1df6b714ccf96b25402499cc39553d55f13aa7b17401 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:functional_distributional_similarity | evidence | validation/modules/hypertension/functional_distributional_similarity.csv | eb04d2f6925f03e04cbff8b5c326eff055f1a38a129ae6fb4cf8e213a118f775 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:functional_issues | evidence | validation/modules/hypertension/functional_issues.csv | 238f47cc153ecdef05138874ec6fa6494aab38b883ddd8ce3610050c666293ff |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:functional_summary | evidence | validation/modules/hypertension/functional_summary.csv | ab34728d26d98adf650b63b550980c5f5685eb4c572f46c185f6645bb7096315 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:functional_table_status | evidence | validation/modules/hypertension/functional_table_status.csv | 894d0b50175fd337b2336ecec9ac882a25065ac79a9477c903366e5bef8b87f1 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:prevalence_tests | evidence | validation/modules/hypertension/prevalence_tests.csv | c2a6d14838872a6f1b6debe1e8ceedd808a5eba6fc1cb261b802e23441f235c7 |
| hypertension-equivalence:run-20260717T114007526034Z-92a6751f1cef:validation:hypertension:statistical_summary | evidence | validation/modules/hypertension/statistical_summary.csv | 858b1ea318108557968f88c7e59eafa224f8d6f9658bab108327742d5c6cda6c |
| psynthea.output.3134ff4e3946581f | simulator_output | simulators/psynthea/raw/psynthea/patients.csv | 15d12c907aaecae78f3778d1719f2a8b93bb2c73198f339276938412bd485c64 |
| psynthea.output.3e5f7135a4c3e315 | simulator_output | simulators/psynthea/raw/psynthea/observations.csv | 8d7df09dcc5fc0e90c550272085496dac8fef08aacfaf813328cc626c1758452 |
| psynthea.output.6ab6e2f5318e23b2 | simulator_output | simulators/psynthea/raw/psynthea/medications.csv | b12f12386414f769a54c82608df3a8da3001e5cf2bf6149f45e68076e77210c0 |
| psynthea.output.6b9d1865d362e102 | simulator_output | simulators/psynthea/raw/psynthea/conditions.csv | 99c00399b08234275c75af73c526176d6c7b19a6aa758a42c928a2ac99773c5b |
| psynthea.output.a4b3c0aa1d75ef18 | simulator_output | simulators/psynthea/raw/psynthea/encounters.csv | 1fc973d9125b33ef31c84b399adbcc52174d60c32532357ed4edcfd165d709d7 |
| psynthea.stderr | log | simulators/psynthea/logs/stderr.log | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| psynthea.stdout | log | simulators/psynthea/logs/stdout.log | a2140299e4f5334637429295532c1304dbbfe30f3789fb3b1416550e7422355a |
| synthea.output.0e78ece284d452a9 | simulator_output | simulators/synthea/raw/synthea/csv/conditions.csv | 531fbdf8b68d698bd344d9a2c49cdc3d824e9fb43d97c7688d91c8c87086c251 |
| synthea.output.16387b7dcccd33e9 | simulator_output | simulators/synthea/raw/synthea/csv/encounters.csv | 82e87db70815e7c85efc28579fc7ab7655643e1bb26226bbc2b0784b3925ef00 |
| synthea.output.3668d5f59d6209c9 | simulator_output | simulators/synthea/raw/synthea/csv/immunizations.csv | ac7d65041c30ea5671223d7fdc38668fa336c7c43fd7d8fd32d7877c419f6dce |
| synthea.output.43cc910006f50bf1 | simulator_output | simulators/synthea/raw/synthea/csv/observations.csv | 8a1b230112ab6ff6eda1e4b96759fc9bbcb20912d22ce66c4b9ea6667d6cc4e7 |
| synthea.output.459adb0bc21e2b2b | simulator_output | simulators/synthea/raw/synthea/fhir/practitionerInformation1784288408123.json | 82ea80c99ddfc981d820e7ea80846bc172136cc2bd77f963559eced69a665ad0 |
| synthea.output.4f8d07537e705c21 | simulator_output | simulators/synthea/raw/synthea/metadata/2026_07_17T11_40_08Z_100_Massachusetts_ff62ef00_57e4_4d3e_8f56_901bc83c96e3.json | 2c959634ab8cdb09c73a31ac6dc5a779869ab52214c781832ee20897a88a16bb |
| synthea.output.5dfe786b69089d98 | simulator_output | simulators/synthea/raw/synthea/csv/claims_transactions.csv | 4a27ca0595b8e17446a53573474197a9ce525b0aeb6f4b4475b5938a9c8630b5 |
| synthea.output.87ca68789f71a8f3 | simulator_output | simulators/synthea/raw/synthea/csv/payer_transitions.csv | fa8191a366e3ffabf61d364e2254be56e7cadf43751ab62b3f652bf1793f9820 |
| synthea.output.8a61c8aab8685e4e | simulator_output | simulators/synthea/raw/synthea/csv/medications.csv | e499f273f39c18d82360dcebab6d5232744942178e76b0b021d5b47d9b01b59d |
| synthea.output.9978b02439836c2a | simulator_output | simulators/synthea/raw/synthea/csv/careplans.csv | cdc88717afa5e6acd46d985485ec23f612d9e2e15bad070d7d3dafa74b191bbc |
| synthea.output.dc344f5331e02783 | simulator_output | simulators/synthea/raw/synthea/csv/providers.csv | 7bd11dfc186ebe281e1534f74f6730fba3f72241d5b0a56974388635b853702a |
| synthea.output.dddac2726573d04c | simulator_output | simulators/synthea/raw/synthea/csv/organizations.csv | d8a2e17547a50807279147f5c7aaa03e7a572e515efbe9b65461b8db7cdd555b |
| synthea.output.e27c964ac456e35f | simulator_output | simulators/synthea/raw/synthea/csv/patients.csv | 7e431dbdbf6b4353397c7fb341007bdbb5cfb75502519efd240481093f0e03e3 |
| synthea.output.ebcec8fc08e46fda | simulator_output | simulators/synthea/raw/synthea/csv/payers.csv | b90d8715a097b1740c69666b8ca67af33bb7d9c7785a0aab9ab401d6796c1742 |
| synthea.output.eca4593c09a762be | simulator_output | simulators/synthea/raw/synthea/csv/claims.csv | 5d40d89ae0183fa931ce9479b216abfe1fa0c742508911a4deb29188ef711220 |
| synthea.output.f9da6cb36cc83b78 | simulator_output | simulators/synthea/raw/synthea/fhir/hospitalInformation1784288408123.json | 9fa38facf04bdf77bf6f56ac34e8aba1ad6e9ee81694985adbb8a4fcd3bd3a59 |
| synthea.stderr | log | simulators/synthea/logs/stderr.log | 6592844c6fd8042db0dedfa6a937b42582873effa9baf939d4d1ddbb462f2fbc |
| synthea.stdout | log | simulators/synthea/logs/stdout.log | f9630078e17c8bdb5cb32303e9867c97442edba3a30550ed84a72260e6588bee |

## Engine Audit Trail

| Stage | Started | Finished | Duration (s) | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| evidence_collection | 2026-07-17T11:40:13.299533+00:00 | 2026-07-17T11:40:13.301935+00:00 | 0.002402 | 57 | 57 |
| signal_extraction | 2026-07-17T11:40:13.301943+00:00 | 2026-07-17T11:40:13.302927+00:00 | 0.000984 | 57 | 20 |
| candidate_generation | 2026-07-17T11:40:13.302934+00:00 | 2026-07-17T11:40:13.324560+00:00 | 0.021626 | 20 | 20 |
| candidate_ranking | 2026-07-17T11:40:13.324566+00:00 | 2026-07-17T11:40:13.326359+00:00 | 0.001793 | 20 | 20 |
| verification | 2026-07-17T11:40:13.326408+00:00 | 2026-07-17T11:40:13.327027+00:00 | 0.000619 | 20 | 0 |
| attribution | 2026-07-17T11:40:13.327046+00:00 | 2026-07-17T11:40:13.329697+00:00 | 0.002651 | 20 | 20 |
| classification | 2026-07-17T11:40:13.329707+00:00 | 2026-07-17T11:40:13.330030+00:00 | 0.000323 | 20 | 20 |
| reproduction | 2026-07-17T11:40:13.330035+00:00 | 2026-07-17T11:40:13.330037+00:00 | 0.000002 | 1 | 0 |
| report_assembly | 2026-07-17T11:40:13.330511+00:00 | 2026-07-17T11:40:13.330697+00:00 | 0.000186 | 20 | 1 |

## Metadata

```json
{
  "document": {
    "engine": {
      "request_id": "root-cause.hypertension-equivalence.run-20260717T114007526034Z-92a6751f1cef"
    },
    "presentation": {
      "experiment_id": "hypertension-equivalence",
      "orchestrator_run_id": "run-20260717T114007526034Z-92a6751f1cef",
      "stage": "root_cause_analysis"
    }
  },
  "report": {
    "input_metadata": {
      "experiment_id": "hypertension-equivalence",
      "explicit_evidence_source_count": 0,
      "interpretation_finding_source_count": 56,
      "interpretation_report_id": "hypertension-equivalence.run-20260717T114007526034Z-92a6751f1cef.hypertension.interpretation",
      "investigation_source_count": 0,
      "knowledge_entry_source_count": 0,
      "orchestrator_run_id": "run-20260717T114007526034Z-92a6751f1cef",
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
