# Psynthea Root Cause Analysis Report

- **Report ID:** `root-cause-report:40dea60edde425e972c16a05`
- **Request ID:** `root-cause.hypertension-equivalence.run-20260721T094517871463Z-4cb9823c3b2c`
- **Experiment ID:** `hypertension-equivalence`
- **Run ID:** `run-20260721T094517871463Z-4cb9823c3b2c`
- **Generated at:** `2026-07-21T09:45:28.504455+00:00`
- **Document fingerprint:** `eb3dbc920d14ffa3ea45955ef2a555535752334406de1a7e8fc33c875edb9523`

## Executive Summary

**Overall status:** `INCONCLUSIVE`  
**Causal confidence:** `NONE`

Root-cause analysis completed: 24 inconclusive, 1 plausible.

| Signals | Evidence | Candidates | Verifications | Findings | Reproduction plans |
| --- | --- | --- | --- | --- | --- |
| 25 | 59 | 20 | 0 | 25 | 0 |

## Causal Findings

### 1. Plausible root cause: Investigate root_cause.engine.probabilistic_semantics as a possible explanation for signal 'signal:1f81c70580a520727657b886' using protocol 'protocol.generic_root_cause:v1.0.0'.

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:23feec418c25c6f644fc5b92 |
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

### 2. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'observations.8302-2': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:17dd27faceee8defd4ad2b9f |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.conditions |
| Difference classification | unknown |
| Signals | signal:38aecea457e42fee0922525a |
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

### 3. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'observations.29463-7': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:4cf3090b5f5cbb867020691f |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.conditions |
| Difference classification | unknown |
| Signals | signal:a5d4fbb7839e3317887a0ab9 |
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

### 4. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'conditions.59621000': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:78234c27769a609706342531 |
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

### 5. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'observations.39156-5': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:865bb576b002c9ccac50eeb9 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.conditions |
| Difference classification | unknown |
| Signals | signal:b84981cdea904fcffbfe2946 |
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

### 6. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'observations.8480-6': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:8fe9b01f0825d5e88e633d2c |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.conditions |
| Difference classification | unknown |
| Signals | signal:aecd2529022a509279bf269a |
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

### 7. No viable causal explanation for: Validation discrepancy: Prevalence endpoint 'observations.8462-4': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:f64c6058a11532e592ae800e |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.conditions |
| Difference classification | unknown |
| Signals | signal:ab41cffd510754febde76c7d |
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

### 8. No viable causal explanation for: Validation discrepancy: Clinical code concordance for 'observations' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:15822959c00606bc74a5b678 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:8c4e88238704a904cbf2c45e |
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

### 9. No viable causal explanation for: Validation discrepancy: Distribution endpoint 'observations.chi_square': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:27f45cbab3ebda3f58081a81 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:e71baffd39ab93c4a6ce726a |
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

### 10. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:31d28e586adf8b140aad0d92 |
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

### 11. No viable causal explanation for: Validation warning: Continuous endpoint 'conditions_per_patient.mann_whitney_u': warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:4c8cd02b6609d8e7769cbe76 |
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

### 12. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:7fef976e02bf0de6890facf4 |
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

### 13. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:8c10456b36bf66339b120efe |
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

### 14. No viable causal explanation for: Validation warning: Clinical event retention for 'conditions' is warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:94250353b9fb126f6005d1b2 |
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

### 15. No viable causal explanation for: Validation warning: Continuous endpoint 'observations_per_patient.welch_t_test': warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:943644e2ab42916126835b53 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:c07327767e9bcab2c80723a9 |
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
| Finding ID | root-cause-finding:95b8af33c45e537db3e3610d |
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

### 17. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'encounters_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:b01f86c4bcbcdedfb45e98dd |
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

### 18. No viable causal explanation for: Validation discrepancy: Categorical endpoint 'encounter_class.chi_square': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:b3f643461b5834f7b0b9efeb |
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

### 19. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'conditions_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:ba5d267722e91f2c992471f8 |
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

### 20. No viable causal explanation for: Validation discrepancy: Clinical event retention for 'medications' is fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:c2c0377a10ce15998df21629 |
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

### 21. No viable causal explanation for: Validation warning: Continuous endpoint 'observations_per_patient.mann_whitney_u': warning

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:d9af51c28a5fe231777e0e25 |
| Status | inconclusive |
| Confidence | none |
| Domain | domain.global |
| Difference classification | unknown |
| Signals | signal:6b35369ada2f07211ec0bf48 |
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

### 22. No viable causal explanation for: Validation discrepancy: Continuous endpoint 'medications_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:efe2f8aae3838c8fc569aa8f |
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

### 23. No viable causal explanation for: Validation warning: Evidence contains not computed values

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:1e5f13408722320420361a2c |
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

### 24. No viable causal explanation for: Validation warning: Optional table 'procedures' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:4a0a729bcf18bdd50cd8be12 |
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

### 25. No viable causal explanation for: Validation warning: Optional table 'medications' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | root-cause-finding:a1dde2340b884e99d60c2740 |
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
| inconclusive | 24 |
| plausible | 1 |

## Unresolved Questions

- What additional deterministic evidence can resolve signal signal:1f81c70580a520727657b886?
- What additional deterministic evidence can resolve signal signal:26323a537b07e4fbe4096d6d?
- What additional deterministic evidence can resolve signal signal:2712a7c0d28fd141e0b62cb4?
- What additional deterministic evidence can resolve signal signal:38aecea457e42fee0922525a?
- What additional deterministic evidence can resolve signal signal:39a9ba6ed7bacc84e30c5a0a?
- What additional deterministic evidence can resolve signal signal:3e1480914b9d36f9333bf0eb?
- What additional deterministic evidence can resolve signal signal:4d9e81767bfeaa684183a4a3?
- What additional deterministic evidence can resolve signal signal:509f80553c919185e43990f5?
- What additional deterministic evidence can resolve signal signal:582d9af0a4a2ed3686dcbe6f?
- What additional deterministic evidence can resolve signal signal:62c16ffc8728889b5f10dd7a?
- What additional deterministic evidence can resolve signal signal:6967fce1fb75412a2bba6fa5?
- What additional deterministic evidence can resolve signal signal:6b35369ada2f07211ec0bf48?
- What additional deterministic evidence can resolve signal signal:8c4e88238704a904cbf2c45e?
- What additional deterministic evidence can resolve signal signal:8ce3cb390148995d2a131533?
- What additional deterministic evidence can resolve signal signal:96bc2979f69f9c20c60cb976?
- What additional deterministic evidence can resolve signal signal:975945a2a08b6204be66583e?
- What additional deterministic evidence can resolve signal signal:a5d4fbb7839e3317887a0ab9?
- What additional deterministic evidence can resolve signal signal:ab41cffd510754febde76c7d?
- What additional deterministic evidence can resolve signal signal:aecd2529022a509279bf269a?
- What additional deterministic evidence can resolve signal signal:b84981cdea904fcffbfe2946?
- What additional deterministic evidence can resolve signal signal:c07327767e9bcab2c80723a9?
- What additional deterministic evidence can resolve signal signal:d83f9fde140a2fda4c7c171e?
- What additional deterministic evidence can resolve signal signal:e71baffd39ab93c4a6ce726a?
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
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:cohort-loading | cohort_load_result | loaded/cohort_loading_manifest.json | a67c80f5b46e48eee746b7e718991735afd71950a841ceed964e550300334372 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:cohort-normalization | cohort_normalization_result | normalized/cohort_normalization_manifest.json | 051892d11663a81bea6c54d9caf1dc8155927ffed0ea75401aea99863d0892d4 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:knowledge-result | knowledge_result | knowledge/knowledge_result.json | 745e7276bba27dc819eb3b977ce50db84b191fa001f5af4f9ccec3bba264338e |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:knowledge:hypertension:json | evidence | knowledge/modules/hypertension/interpretation_report.json | 9f71d5c0fa4f378c278563e212c4627a6f5a98edd8a66fcc93706164c57acae5 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:knowledge:hypertension:markdown | report | knowledge/modules/hypertension/interpretation_report.md | 3f09593a5d7de53817f5645ea1c8a9098460e14857517bc3ca9ff70c4e08d09c |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:psynthea:normalized:conditions | normalized_dataset | normalized/psynthea/conditions.csv | 8e953f2895e531e9970cea6db01c5707a0c0363163a19c4d9531ed381eb18c78 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:psynthea:normalized:encounters | normalized_dataset | normalized/psynthea/encounters.csv | e0b30aaf341eafa229d007aa8c60badc00caf2cfc92499e11ff4d056cede494d |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:psynthea:normalized:medications | normalized_dataset | normalized/psynthea/medications.csv | 3cd75e58bcfb737e1d45ae51e6349b9153e6a2c2e01bd55e82db55248adf6970 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:psynthea:normalized:observations | normalized_dataset | normalized/psynthea/observations.csv | ebe4b9ba001865fa4ffa1d4270b28c541f3a00edce898a7fa73d4b6c52f04435 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:psynthea:normalized:patients | normalized_dataset | normalized/psynthea/patients.csv | a29dff18f59d449aa81fd94b4bdd60c06800089736728101dbd2e3f7ec86d467 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:psynthea:normalized:procedures | normalized_dataset | normalized/psynthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:synthea:normalized:conditions | normalized_dataset | normalized/synthea/conditions.csv | 7d8e4eb1bfa170bf16fbab90503a7abf844bebb63879c12bf7ac495b8a532867 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:synthea:normalized:encounters | normalized_dataset | normalized/synthea/encounters.csv | 280f211a9336b35ba2165e9cdcb04d33d904e86cac94f18d0b8155c3a9ddbe6c |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:synthea:normalized:medications | normalized_dataset | normalized/synthea/medications.csv | f20f9e196e541fbf942965a0bd1953d8591a04c4ae583408e1087facd10c6777 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:synthea:normalized:observations | normalized_dataset | normalized/synthea/observations.csv | 711823129392c3932cef4b6bf7e699e457cfd54f3fda3a0ab8ff2ddf6269007f |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:synthea:normalized:patients | normalized_dataset | normalized/synthea/patients.csv | b37c48f44c18c407ac58a722484bd0f5f053bb3f13cbdc4ff3907cf8e2559e68 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:synthea:normalized:procedures | normalized_dataset | normalized/synthea/procedures.csv | 01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation-result | validation_result | validation/validation_result.json | 468fe64589e43dfc70b7c2ccbdf2d2b7b2e5b95efd6b7b9adff144d3d9d4baab |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:categorical_tests | evidence | validation/modules/hypertension/categorical_tests.csv | c9c78f2cca208f3c445bfc9a013a5bbf67527b51dcfb07720412d33f1ac9dd14 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:continuous_tests | evidence | validation/modules/hypertension/continuous_tests.csv | 188f47bae5984b10a7b55bf6bbf479db122509a76c1b02b10cb9207304963ef1 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:distribution_tests | evidence | validation/modules/hypertension/distribution_tests.csv | d6f3862ecdabd872c507c4481682e9ab13e248741ba705a1fa5b1f3db7b51484 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:functional_clinical_signal | evidence | validation/modules/hypertension/functional_clinical_signal.csv | c96ea7e5382504b219107e68258a53c4ea200bc8260d4bab4c930b27969e2716 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:functional_distributional_similarity | evidence | validation/modules/hypertension/functional_distributional_similarity.csv | 9bba46fd590e1f640bd119c4ef1c4884e1c38b2c9da4bf40b0d5f6cd1476e300 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:functional_issues | evidence | validation/modules/hypertension/functional_issues.csv | 483ab1a3a5629dc780ebae51d87cc6eaa328e85097a7872beb3271cb2e77cee7 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:functional_summary | evidence | validation/modules/hypertension/functional_summary.csv | 03b2f69876373181dd637e4bea2ddf9293c7225c51680ae87ba48bacbfbf0bd1 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:functional_table_status | evidence | validation/modules/hypertension/functional_table_status.csv | 1ee532d9179eb693d88c9584ad7188857f389a461863faf3261fa3752ad4f20b |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:prevalence_tests | evidence | validation/modules/hypertension/prevalence_tests.csv | 9fb3e7f8879c209c77bbcc2f35801a9e2ca95d52f42f69444c2612f755755634 |
| hypertension-equivalence:run-20260721T094517871463Z-4cb9823c3b2c:validation:hypertension:statistical_summary | evidence | validation/modules/hypertension/statistical_summary.csv | f3afff6092ba3e2746b832ebf93ef6a83b032e29ba0550cacb6fd319f97327bd |
| psynthea.output.20e8b2d7430643ce | simulator_output | simulators/psynthea/raw/psynthea/imaging_studies.csv | f39ae66b3b3b7a9229226292a1da519ef46020f3fdae1f09fbef6f1294668c67 |
| psynthea.output.3134ff4e3946581f | simulator_output | simulators/psynthea/raw/psynthea/patients.csv | 33ea663a789ddfb35d7675625c5a2f59229474df3e444ef89641b91cb62bd497 |
| psynthea.output.3e5f7135a4c3e315 | simulator_output | simulators/psynthea/raw/psynthea/observations.csv | 02770762062819d2d8aae241bb6a849bf0e1e2720cb1c2f0e232be66cf2307be |
| psynthea.output.6ab6e2f5318e23b2 | simulator_output | simulators/psynthea/raw/psynthea/medications.csv | b12f12386414f769a54c82608df3a8da3001e5cf2bf6149f45e68076e77210c0 |
| psynthea.output.6b9d1865d362e102 | simulator_output | simulators/psynthea/raw/psynthea/conditions.csv | 269186847715328ab3eff0ad85fed7125aad5b4e9e10de7d15dca2c65ffda4f1 |
| psynthea.output.a4b3c0aa1d75ef18 | simulator_output | simulators/psynthea/raw/psynthea/encounters.csv | 6678960d9329e5e763d72eedcf9c2a30aacbe0ad56ce1fcaca992b3bb7a93593 |
| psynthea.output.b8de9c5c4ec422c5 | simulator_output | simulators/psynthea/raw/psynthea/supplies.csv | 1c38d10c9b6ed3767cb19dbd179e9324a5486b8ef48b1937ebdd93db067a4c4f |
| psynthea.output.c5942525a6f4f29d | simulator_output | simulators/psynthea/raw/psynthea/devices.csv | b12f12386414f769a54c82608df3a8da3001e5cf2bf6149f45e68076e77210c0 |
| psynthea.stderr | log | simulators/psynthea/logs/stderr.log | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| psynthea.stdout | log | simulators/psynthea/logs/stdout.log | 11eeeca75b246beed0c3982c4961e0a9c5722c2133684d08ff62b12e53876baf |
| synthea.output.0e78ece284d452a9 | simulator_output | simulators/synthea/raw/synthea/csv/conditions.csv | 77752ccb2bb041b3367983111d1640eead9f317f6b1ccd1126b822cb6465aaba |
| synthea.output.16387b7dcccd33e9 | simulator_output | simulators/synthea/raw/synthea/csv/encounters.csv | d413abee18ac60dbc7f45649a93d83bef7c3728a4557363dc005f24bf496243b |
| synthea.output.25d2d6efa8730e7a | simulator_output | simulators/synthea/raw/synthea/fhir/practitionerInformation1784627118683.json | f7d0bcfff5bfd1f3bf4e336191d8ece34fc87637a348ae763bcbd4ef8a0f0365 |
| synthea.output.3668d5f59d6209c9 | simulator_output | simulators/synthea/raw/synthea/csv/immunizations.csv | 60d7d2c42cc3ea66673d7ca2ba46b683b26a1d2def600cc5cc587f1a45086d1e |
| synthea.output.43cc910006f50bf1 | simulator_output | simulators/synthea/raw/synthea/csv/observations.csv | 99ef5fe5ce52467cf77edbd5d52eb1a34d22ff54995bc554695076d54f488dcf |
| synthea.output.5dfe786b69089d98 | simulator_output | simulators/synthea/raw/synthea/csv/claims_transactions.csv | 4ad0d0880fd621d061d9efb2b46a25a93e521cb5cbdc9670ce1bf45c6d9d168d |
| synthea.output.87ca68789f71a8f3 | simulator_output | simulators/synthea/raw/synthea/csv/payer_transitions.csv | 1e8878454479b756f5e9f5a372f8143e03da3909fef1ec42c1e49e9323a6dd74 |
| synthea.output.8a61c8aab8685e4e | simulator_output | simulators/synthea/raw/synthea/csv/medications.csv | 4f935ec9d7d30cf77cb3de23a616b1072c8085520cc6833bde2d864b402eee7a |
| synthea.output.9978b02439836c2a | simulator_output | simulators/synthea/raw/synthea/csv/careplans.csv | ca20b59c7a0891c306351edfb12f68d33806ca98bf82abebedd5590a9e9f5e4d |
| synthea.output.c829599d782e65ff | simulator_output | simulators/synthea/raw/synthea/fhir/hospitalInformation1784627118683.json | 9fa38facf04bdf77bf6f56ac34e8aba1ad6e9ee81694985adbb8a4fcd3bd3a59 |
| synthea.output.dc344f5331e02783 | simulator_output | simulators/synthea/raw/synthea/csv/providers.csv | d44e63cd037b4a3f98b5820afb6f3e65bf0e0d05f163b2836508397d4b4cf2e5 |
| synthea.output.dddac2726573d04c | simulator_output | simulators/synthea/raw/synthea/csv/organizations.csv | d8a2e17547a50807279147f5c7aaa03e7a572e515efbe9b65461b8db7cdd555b |
| synthea.output.e27c964ac456e35f | simulator_output | simulators/synthea/raw/synthea/csv/patients.csv | 07e4d5f46d39cc4349607356a2256247b97ed22947fc5b5af87b2fc016a601de |
| synthea.output.ebcec8fc08e46fda | simulator_output | simulators/synthea/raw/synthea/csv/payers.csv | e4f9df3ac7326e562a4a6eefc24bac0669c9de2ac9764c24540b9f681854c509 |
| synthea.output.eca4593c09a762be | simulator_output | simulators/synthea/raw/synthea/csv/claims.csv | 6ffea737d16f2c7cb08c6ee44308f6c4efafa1eee03e824defbc77e4fb744fe2 |
| synthea.output.f3be9a11791ea58a | simulator_output | simulators/synthea/raw/synthea/metadata/2026_07_21T09_45_18Z_100_Massachusetts_8b7b572b_e3c7_4239_b605_d7688a36857e.json | 44473b6b0138f8e48fee4239a29f4face7852d325ea7f35b1c8595af1c2207c4 |
| synthea.stderr | log | simulators/synthea/logs/stderr.log | 6592844c6fd8042db0dedfa6a937b42582873effa9baf939d4d1ddbb462f2fbc |
| synthea.stdout | log | simulators/synthea/logs/stdout.log | e01c9a92b0822713a9c4973d58081a3b1e02cca8a2e2eab80b75f7645660ce63 |

## Engine Audit Trail

| Stage | Started | Finished | Duration (s) | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| evidence_collection | 2026-07-21T09:45:28.460753+00:00 | 2026-07-21T09:45:28.463324+00:00 | 0.002571 | 59 | 59 |
| signal_extraction | 2026-07-21T09:45:28.463332+00:00 | 2026-07-21T09:45:28.464487+00:00 | 0.001155 | 59 | 25 |
| candidate_generation | 2026-07-21T09:45:28.464493+00:00 | 2026-07-21T09:45:28.497858+00:00 | 0.033365 | 25 | 20 |
| candidate_ranking | 2026-07-21T09:45:28.497864+00:00 | 2026-07-21T09:45:28.499659+00:00 | 0.001795 | 20 | 20 |
| verification | 2026-07-21T09:45:28.499709+00:00 | 2026-07-21T09:45:28.500328+00:00 | 0.000619 | 20 | 0 |
| attribution | 2026-07-21T09:45:28.500347+00:00 | 2026-07-21T09:45:28.503160+00:00 | 0.002813 | 20 | 20 |
| classification | 2026-07-21T09:45:28.503170+00:00 | 2026-07-21T09:45:28.503556+00:00 | 0.000386 | 25 | 25 |
| reproduction | 2026-07-21T09:45:28.503560+00:00 | 2026-07-21T09:45:28.503563+00:00 | 0.000003 | 1 | 0 |
| report_assembly | 2026-07-21T09:45:28.504139+00:00 | 2026-07-21T09:45:28.504395+00:00 | 0.000256 | 25 | 1 |

## Metadata

```json
{
  "document": {
    "engine": {
      "request_id": "root-cause.hypertension-equivalence.run-20260721T094517871463Z-4cb9823c3b2c"
    },
    "presentation": {
      "experiment_id": "hypertension-equivalence",
      "orchestrator_run_id": "run-20260721T094517871463Z-4cb9823c3b2c",
      "stage": "root_cause_analysis"
    }
  },
  "report": {
    "input_metadata": {
      "experiment_id": "hypertension-equivalence",
      "explicit_evidence_source_count": 0,
      "interpretation_finding_source_count": 58,
      "interpretation_report_id": "hypertension-equivalence.run-20260721T094517871463Z-4cb9823c3b2c.hypertension.interpretation",
      "investigation_source_count": 0,
      "knowledge_entry_source_count": 0,
      "orchestrator_run_id": "run-20260721T094517871463Z-4cb9823c3b2c",
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
