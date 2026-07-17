# Psynthea Scientific Validation Report

Generated at: `2026-07-17T09:26:22.168722+00:00`

## Executive Summary

| Field | Value |
| --- | --- |
| Module | hypertension |
| Pipeline run | run-20260717T092616615350Z-3e39dc09836f |
| Overall status | FAIL |
| Maximum severity | HIGH |
| Research-use gate | NOT READY |
| Rules evaluated | 18 |
| Findings | 56 |
| Evidence values | 526 |
| Blocking findings | 32 |
| Incomplete rules | 6 |

**Research-use conclusion:** Not ready for unrestricted research use; blocking or incomplete validation conditions remain.

## Validation by Dimension

| Dimension | Status | Max severity | Rules | Findings | Incomplete | Blocking | Research-ready |
| --- | --- | --- | --- | --- | --- | --- | --- |
| structural | WARNING | low | 3 | 8 | 0 | 0 | yes |
| statistical | FAIL | high | 4 | 34 | 0 | 26 | no |
| clinical | FAIL | high | 3 | 12 | 0 | 5 | no |
| epidemiological | INCONCLUSIVE | high | 3 | 2 | 1 | 1 | no |
| spanish_adaptation | INCONCLUSIVE | info | 5 | 0 | 5 | 0 | no |

## Priority Findings

### Clinical event retention for 'medications' is fail

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.EVENT_RETENTION.medications.FAIL |
| Rule | CLINICAL.EVENT_RETENTION |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | yes |

**Observation.** Synthea count=48, psynthea count=0, retention=0.000.

**Interpretation.** psynthea clinical event volume falls outside the configured failure interval relative to Synthea.

**Impact.** Clinically intended output may be materially under- or over-generated.

**Limitations**
- This count ratio is descriptive and does not adjust for patient mix, repeated events or timing.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.medications.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.synthea_only_code_count | primary | available | 3 | — |
| hypertension.functional.clinical_signal.medications.synthea_signal_count | primary | available | 48 | — |
### Clinical event retention for 'observations' is fail

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.EVENT_RETENTION.observations.FAIL |
| Rule | CLINICAL.EVENT_RETENTION |
| Status | FAIL |
| Severity | high |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | yes |

**Observation.** Synthea count=3224, psynthea count=0, retention=0.000.

**Interpretation.** psynthea clinical event volume falls outside the configured failure interval relative to Synthea.

**Impact.** Clinically intended output may be materially under- or over-generated.

**Limitations**
- This count ratio is descriptive and does not adjust for patient mix, repeated events or timing.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.observations.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.synthea_only_code_count | primary | available | 5 | — |
| hypertension.functional.clinical_signal.observations.synthea_signal_count | primary | available | 3224 | — |
### Prevalence endpoint 'conditions.59621000': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.conditions.59621000.FAIL |
| Rule | STAT.PREVALENCE |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** Synthea prevalence=0.29; psynthea prevalence=0.46; absolute_difference=0.17; relative_difference=0.5862068965517243; risk_ratio=1.5862068965517244; 95% CI=[1.0923422673509318, 2.3033552704776303]; adjusted_p=0.0130277822628989; significant_after_fdr=True.

**Interpretation.** The prevalence difference survives FDR correction and exceeds materiality tolerance.

**Impact.** Prevalence equivalence is not supported for this clinical code.

**Limitations**
- FDR controls the expected false-discovery proportion across tested prevalence endpoints.
- Statistical prevalence similarity does not establish clinical pathway equivalence.
- Risk-ratio equivalence requires the full confidence interval to lie within [0.8, 1.25].

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.conditions.59621000.absolute_difference | primary | available | 0.17 | — |
| hypertension.statistics.prevalence.conditions.59621000.adjusted_p_value | primary | available | 0.0130277822628989 | — |
| hypertension.statistics.prevalence.conditions.59621000.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio | primary | available | 2.0855683269476373 | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio_ci_lower | primary | available | 1.162884266037268 | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio_ci_upper | primary | available | 3.740350930354552 | — |
| hypertension.statistics.prevalence.conditions.59621000.p_value | primary | available | 0.0130277822628989 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_events | primary | available | 46 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_prevalence | primary | available | 0.46 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.conditions.59621000.relative_difference | primary | available | 0.5862068965517243 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio | primary | available | 1.5862068965517244 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio_ci_lower | primary | available | 1.0923422673509318 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio_ci_upper | primary | available | 2.3033552704776303 | — |
| hypertension.statistics.prevalence.conditions.59621000.significant | primary | available | True | — |
| hypertension.statistics.prevalence.conditions.59621000.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.conditions.59621000.statistic | primary | available | 2.483008927356754 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_events | primary | available | 29 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_prevalence | primary | available | 0.29 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |
### Continuous endpoint 'encounters_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.encounters_per_patient.kolmogorov_smirnov.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=2.20876e-59, effect_size=1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.effect_size | primary | available | 1.0 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.p_value | primary | available | 2.208760693199506e-59 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.significant | primary | available | True | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.statistic | primary | available | 1.0 | — |
### Continuous endpoint 'encounters_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.encounters_per_patient.mann_whitney_u.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=1.76245e-35, effect_size=-1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.effect_size | primary | available | -1.0 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.p_value | primary | available | 1.7624465916349795e-35 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.significant | primary | available | True | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.statistic | primary | available | 10000.0 | — |
### Continuous endpoint 'encounters_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.encounters_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=2.87307e-47, effect_size=-3.68967 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.effect_size | primary | available | -3.689666185268692 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.p_value | primary | available | 2.873071134163329e-47 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.statistic | primary | available | -26.08987979918192 | — |
### Continuous endpoint 'medications_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.medications_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=9.87863e-08, effect_size=-0.813346 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.effect_size | primary | available | -0.8133457582761467 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.p_value | primary | available | 9.878631814650468e-08 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.statistic | primary | available | -5.751223011263779 | — |
### Continuous endpoint 'observations_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.observations_per_patient.kolmogorov_smirnov.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=2.20876e-59, effect_size=1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.effect_size | primary | available | 1.0 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.p_value | primary | available | 2.208760693199506e-59 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.significant | primary | available | True | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.statistic | primary | available | 1.0 | — |
### Continuous endpoint 'observations_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.observations_per_patient.mann_whitney_u.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=5.5448e-40, effect_size=-1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.effect_size | primary | available | -1.0 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.p_value | primary | available | 5.544798383772403e-40 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.significant | primary | available | True | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.statistic | primary | available | 10000.0 | — |
### Continuous endpoint 'observations_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.observations_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=6.62025e-117, effect_size=-20.406 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.effect_size | primary | available | -20.406037611301443 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.p_value | primary | available | 6.620254057615393e-117 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.statistic | primary | available | -144.2924757209899 | — |

## Detailed Findings

### Clinical

#### No expected clinical terms configured for 'conditions'

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.SIGNAL_PRESERVATION.conditions.NOT_EVALUATED |
| Rule | CLINICAL.SIGNAL_PRESERVATION |
| Status | NOT EVALUATED |
| Severity | info |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | no |

**Observation.** Synthea produced 29 signal(s) and psynthea produced 46, but no expected_terms value was configured.

**Interpretation.** Expected-signal preservation is not evaluated for this domain.

**Impact.** This rule contributes no pass or fail decision for the domain.

**Limitations**
- Event counts alone cannot identify whether the intended module signal is present.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.conditions.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.conditions.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.conditions.psynthea_signal_count | primary | available | 46 | — |
| hypertension.functional.clinical_signal.conditions.shared_code_count | primary | available | 1 | — |
| hypertension.functional.clinical_signal.conditions.synthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.conditions.synthea_signal_count | primary | available | 29 | — |

#### No expected clinical terms configured for 'medications'

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.SIGNAL_PRESERVATION.medications.NOT_EVALUATED |
| Rule | CLINICAL.SIGNAL_PRESERVATION |
| Status | NOT EVALUATED |
| Severity | info |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | no |

**Observation.** Synthea produced 48 signal(s) and psynthea produced 0, but no expected_terms value was configured.

**Interpretation.** Expected-signal preservation is not evaluated for this domain.

**Impact.** This rule contributes no pass or fail decision for the domain.

**Limitations**
- Event counts alone cannot identify whether the intended module signal is present.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.medications.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.synthea_only_code_count | primary | available | 3 | — |
| hypertension.functional.clinical_signal.medications.synthea_signal_count | primary | available | 48 | — |

#### No expected clinical terms configured for 'observations'

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.SIGNAL_PRESERVATION.observations.NOT_EVALUATED |
| Rule | CLINICAL.SIGNAL_PRESERVATION |
| Status | NOT EVALUATED |
| Severity | info |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | no |

**Observation.** Synthea produced 3224 signal(s) and psynthea produced 0, but no expected_terms value was configured.

**Interpretation.** Expected-signal preservation is not evaluated for this domain.

**Impact.** This rule contributes no pass or fail decision for the domain.

**Limitations**
- Event counts alone cannot identify whether the intended module signal is present.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.observations.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.synthea_only_code_count | primary | available | 5 | — |
| hypertension.functional.clinical_signal.observations.synthea_signal_count | primary | available | 3224 | — |

#### No expected clinical terms configured for 'procedures'

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.SIGNAL_PRESERVATION.procedures.NOT_EVALUATED |
| Rule | CLINICAL.SIGNAL_PRESERVATION |
| Status | NOT EVALUATED |
| Severity | info |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | no |

**Observation.** Synthea produced 0 signal(s) and psynthea produced 0, but no expected_terms value was configured.

**Interpretation.** Expected-signal preservation is not evaluated for this domain.

**Impact.** This rule contributes no pass or fail decision for the domain.

**Limitations**
- Event counts alone cannot identify whether the intended module signal is present.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.procedures.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.procedures.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.synthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.synthea_signal_count | primary | available | 0 | — |

#### Clinical event retention for 'conditions' is warning

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.EVENT_RETENTION.conditions.WARNING |
| Rule | CLINICAL.EVENT_RETENTION |
| Status | WARNING |
| Severity | moderate |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | no |

**Observation.** Synthea count=29, psynthea count=46, retention=1.586.

**Interpretation.** psynthea shows a potentially meaningful reduction or excess in clinical event volume.

**Impact.** The reduction should be reviewed before claiming event-volume equivalence.

**Limitations**
- This count ratio is descriptive and does not adjust for patient mix, repeated events or timing.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.conditions.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.conditions.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.conditions.psynthea_signal_count | primary | available | 46 | — |
| hypertension.functional.clinical_signal.conditions.shared_code_count | primary | available | 1 | — |
| hypertension.functional.clinical_signal.conditions.synthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.conditions.synthea_signal_count | primary | available | 29 | — |

#### Clinical event retention for 'medications' is fail

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.EVENT_RETENTION.medications.FAIL |
| Rule | CLINICAL.EVENT_RETENTION |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | moderate |
| Blocks research use | yes |

**Observation.** Synthea count=48, psynthea count=0, retention=0.000.

**Interpretation.** psynthea clinical event volume falls outside the configured failure interval relative to Synthea.

**Impact.** Clinically intended output may be materially under- or over-generated.

**Limitations**
- This count ratio is descriptive and does not adjust for patient mix, repeated events or timing.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.medications.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.medications.synthea_only_code_count | primary | available | 3 | — |
| hypertension.functional.clinical_signal.medications.synthea_signal_count | primary | available | 48 | — |

#### Clinical event retention for 'observations' is fail

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.EVENT_RETENTION.observations.FAIL |
| Rule | CLINICAL.EVENT_RETENTION |
| Status | FAIL |
| Severity | high |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | yes |

**Observation.** Synthea count=3224, psynthea count=0, retention=0.000.

**Interpretation.** psynthea clinical event volume falls outside the configured failure interval relative to Synthea.

**Impact.** Clinically intended output may be materially under- or over-generated.

**Limitations**
- This count ratio is descriptive and does not adjust for patient mix, repeated events or timing.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.observations.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.observations.synthea_only_code_count | primary | available | 5 | — |
| hypertension.functional.clinical_signal.observations.synthea_signal_count | primary | available | 3224 | — |

#### Event retention is not applicable to sparse 'procedures' reference output

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.EVENT_RETENTION.procedures.NOT_APPLICABLE |
| Rule | CLINICAL.EVENT_RETENTION |
| Status | NOT APPLICABLE |
| Severity | info |
| Confidence | high |
| Evidence strength | insufficient |
| Blocks research use | no |

**Observation.** The Synthea reference contains 0 signal(s), below the minimum of 1.

**Interpretation.** A retention ratio is not defined for an effectively absent reference signal.

**Impact.** No event-volume decision is issued for this domain.

**Limitations**
- A different reference seed or larger cohort may produce analyzable events.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.procedures.blocking_issue | primary | available | False | — |
| hypertension.functional.clinical_signal.procedures.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.psynthea_signal_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.shared_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.synthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.clinical_signal.procedures.synthea_signal_count | primary | available | 0 | — |

#### Clinical code concordance for 'conditions' is pass

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.CODE_OVERLAP.conditions.PASS |
| Rule | CLINICAL.CODE_OVERLAP |
| Status | PASS |
| Severity | info |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Jaccard=1.000, overlap=1.000, JSD=0.000, shared=1, Synthea-only=0, psynthea-only=0.

**Interpretation.** The domain meets the configured code-set and distributional concordance criteria.

**Impact.** No material code-level discrepancy is identified by the configured policy.

**Limitations**
- Code overlap does not prove semantic equivalence when coding systems, granularity or mappings differ.
- Aggregate code distributions do not test patient-level temporal ordering or comorbidity relationships.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.distributional_similarity.conditions.blocking_issue | primary | available | False | — |
| hypertension.functional.distributional_similarity.conditions.jaccard_similarity | primary | available | 1.0 | — |
| hypertension.functional.distributional_similarity.conditions.jensen_shannon_divergence | primary | available | 0.0 | — |
| hypertension.functional.distributional_similarity.conditions.overlap_coefficient | primary | available | 1.0 | — |
| hypertension.functional.distributional_similarity.conditions.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.conditions.psynthea_total | primary | available | 46 | — |
| hypertension.functional.distributional_similarity.conditions.shared_code_count | primary | available | 1 | — |
| hypertension.functional.distributional_similarity.conditions.synthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.conditions.synthea_total | primary | available | 29 | — |
| hypertension.functional.distributional_similarity.conditions.valid_for_distributional_comparison | primary | available | True | — |

#### Clinical code overlap for 'medications' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.CODE_OVERLAP.medications.INCONCLUSIVE |
| Rule | CLINICAL.CODE_OVERLAP |
| Status | INCONCLUSIVE |
| Severity | high |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** The distributional-similarity row is incomplete or malformed.

**Interpretation.** The available evidence is insufficient for a defensible clinical conclusion.

**Impact.** Clinical equivalence for this domain is blocked until the evidence is corrected.

**Limitations**
- The rule does not infer missing values from neighboring metrics.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.distributional_similarity.medications.blocking_issue | primary | available | False | — |
| hypertension.functional.distributional_similarity.medications.jaccard_similarity | primary | available | 0.0 | — |
| hypertension.functional.distributional_similarity.medications.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.medications.overlap_coefficient | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.medications.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.medications.psynthea_total | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.medications.shared_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.medications.synthea_only_code_count | primary | available | 3 | — |
| hypertension.functional.distributional_similarity.medications.synthea_total | primary | available | 48 | — |
| hypertension.functional.distributional_similarity.medications.valid_for_distributional_comparison | primary | available | False | — |

#### Clinical code overlap for 'observations' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.CODE_OVERLAP.observations.INCONCLUSIVE |
| Rule | CLINICAL.CODE_OVERLAP |
| Status | INCONCLUSIVE |
| Severity | high |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** The distributional-similarity row is incomplete or malformed.

**Interpretation.** The available evidence is insufficient for a defensible clinical conclusion.

**Impact.** Clinical equivalence for this domain is blocked until the evidence is corrected.

**Limitations**
- The rule does not infer missing values from neighboring metrics.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.distributional_similarity.observations.blocking_issue | primary | available | False | — |
| hypertension.functional.distributional_similarity.observations.jaccard_similarity | primary | available | 0.0 | — |
| hypertension.functional.distributional_similarity.observations.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.observations.overlap_coefficient | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.observations.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.observations.psynthea_total | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.observations.shared_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.observations.synthea_only_code_count | primary | available | 5 | — |
| hypertension.functional.distributional_similarity.observations.synthea_total | primary | available | 3224 | — |
| hypertension.functional.distributional_similarity.observations.valid_for_distributional_comparison | primary | available | False | — |

#### Clinical code overlap for 'procedures' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | CLINICAL.CODE_OVERLAP.procedures.INCONCLUSIVE |
| Rule | CLINICAL.CODE_OVERLAP |
| Status | INCONCLUSIVE |
| Severity | high |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** The distributional-similarity row is incomplete or malformed.

**Interpretation.** The available evidence is insufficient for a defensible clinical conclusion.

**Impact.** Clinical equivalence for this domain is blocked until the evidence is corrected.

**Limitations**
- The rule does not infer missing values from neighboring metrics.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.distributional_similarity.procedures.blocking_issue | primary | available | False | — |
| hypertension.functional.distributional_similarity.procedures.jaccard_similarity | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.procedures.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.procedures.overlap_coefficient | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.procedures.psynthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.procedures.psynthea_total | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.procedures.shared_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.procedures.synthea_only_code_count | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.procedures.synthea_total | primary | available | 0 | — |
| hypertension.functional.distributional_similarity.procedures.valid_for_distributional_comparison | primary | available | False | — |

### Distribution

#### Distribution endpoint 'conditions.chi_square' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | STAT.DISTRIBUTION.conditions.chi_square.INCONCLUSIVE |
| Rule | STAT.DISTRIBUTION |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** A finite p-value, JSD and significance decision are required.

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.distribution.conditions.chi_square.effect_size | primary | not_computed | — | — |
| hypertension.statistics.distribution.conditions.chi_square.jensen_shannon_divergence | primary | available | 0.0 | — |
| hypertension.statistics.distribution.conditions.chi_square.n_psynthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.conditions.chi_square.n_synthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.conditions.chi_square.notes | primary | available | No comparable coded distribution available. | — |
| hypertension.statistics.distribution.conditions.chi_square.p_value | primary | not_computed | — | — |
| hypertension.statistics.distribution.conditions.chi_square.significant | primary | not_computed | — | — |
| hypertension.statistics.distribution.conditions.chi_square.statistic | primary | not_computed | — | — |

#### Distribution endpoint 'medications.chi_square' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | STAT.DISTRIBUTION.medications.chi_square.INCONCLUSIVE |
| Rule | STAT.DISTRIBUTION |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** A finite p-value, JSD and significance decision are required.

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.distribution.medications.chi_square.effect_size | primary | not_computed | — | — |
| hypertension.statistics.distribution.medications.chi_square.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.statistics.distribution.medications.chi_square.n_psynthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.medications.chi_square.n_synthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.medications.chi_square.notes | primary | available | No comparable coded distribution available. | — |
| hypertension.statistics.distribution.medications.chi_square.p_value | primary | not_computed | — | — |
| hypertension.statistics.distribution.medications.chi_square.significant | primary | not_computed | — | — |
| hypertension.statistics.distribution.medications.chi_square.statistic | primary | not_computed | — | — |

#### Distribution endpoint 'observations.chi_square' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | STAT.DISTRIBUTION.observations.chi_square.INCONCLUSIVE |
| Rule | STAT.DISTRIBUTION |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** A finite p-value, JSD and significance decision are required.

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.distribution.observations.chi_square.effect_size | primary | not_computed | — | — |
| hypertension.statistics.distribution.observations.chi_square.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.statistics.distribution.observations.chi_square.n_psynthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.observations.chi_square.n_synthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.observations.chi_square.notes | primary | available | No comparable coded distribution available. | — |
| hypertension.statistics.distribution.observations.chi_square.p_value | primary | not_computed | — | — |
| hypertension.statistics.distribution.observations.chi_square.significant | primary | not_computed | — | — |
| hypertension.statistics.distribution.observations.chi_square.statistic | primary | not_computed | — | — |

#### Distribution endpoint 'procedures.chi_square' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | STAT.DISTRIBUTION.procedures.chi_square.INCONCLUSIVE |
| Rule | STAT.DISTRIBUTION |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** A finite p-value, JSD and significance decision are required.

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.distribution.procedures.chi_square.effect_size | primary | not_computed | — | — |
| hypertension.statistics.distribution.procedures.chi_square.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.statistics.distribution.procedures.chi_square.n_psynthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.procedures.chi_square.n_synthea | primary | not_computed | — | — |
| hypertension.statistics.distribution.procedures.chi_square.notes | primary | available | No comparable coded distribution available. | — |
| hypertension.statistics.distribution.procedures.chi_square.p_value | primary | not_computed | — | — |
| hypertension.statistics.distribution.procedures.chi_square.significant | primary | not_computed | — | — |
| hypertension.statistics.distribution.procedures.chi_square.statistic | primary | not_computed | — | — |

### Epidemiological

#### Demographic population profile

| Field | Value |
| --- | --- |
| Finding ID | EPI.DEMOGRAPHIC_PROFILE.PASS |
| Rule | EPI.DEMOGRAPHIC_PROFILE |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** All 4 demographic comparison(s) remain within configured population-equivalence tolerances.

**Interpretation.** The available evidence supports H1 for the measured demographic dimensions.

**Impact.** Population-level comparisons may proceed for the measured demographics.

**Limitations**
- The rule evaluates only demographic dimensions emitted by the statistical pipeline.
- Passing H1 does not establish clinical or causal equivalence.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.categorical.gender.chi_square.effect_size | primary | available | 0.0605967872435082 | — |
| hypertension.statistics.categorical.gender.chi_square.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.categorical.gender.chi_square.n_synthea | primary | available | 100 | — |
| hypertension.statistics.categorical.gender.chi_square.notes | primary | not_computed | — | — |
| hypertension.statistics.categorical.gender.chi_square.p_value | primary | available | 0.391462579007701 | — |
| hypertension.statistics.categorical.gender.chi_square.significant | primary | available | False | — |
| hypertension.statistics.categorical.gender.chi_square.statistic | primary | available | 0.7343941248470013 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.effect_size | primary | available | 0.08 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.p_value | primary | available | 0.9084105017744524 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.significant | primary | available | False | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.statistic | primary | available | 0.08 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.effect_size | primary | available | -0.0185999999999999 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.age.mann_whitney_u.p_value | primary | available | 0.8211908103897939 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.significant | primary | available | False | — |
| … 8 more | — | — | — | — |

#### Population prevalence profile

| Field | Value |
| --- | --- |
| Finding ID | EPI.PREVALENCE_PROFILE.INCONCLUSIVE |
| Rule | EPI.PREVALENCE_PROFILE |
| Status | INCONCLUSIVE |
| Severity | high |
| Confidence | low |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** Evaluated 9 prevalence comparison(s): 1 material, 0 statistically significant but within tolerance, and 8 incomplete or inconsistent.

**Interpretation.** H2 cannot be evaluated safely because prevalence evidence is incomplete or contradictory.

**Impact.** Population-level disease-burden conclusions require the stated limitations or remediation.

**Limitations**
- Equivalence is limited to conditions represented in the prevalence table.
- Prevalence agreement does not demonstrate preserved temporal or causal relationships.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.conditions.59621000.absolute_difference | primary | available | 0.17 | — |
| hypertension.statistics.prevalence.conditions.59621000.adjusted_p_value | primary | available | 0.0130277822628989 | — |
| hypertension.statistics.prevalence.conditions.59621000.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio | primary | available | 2.0855683269476373 | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio_ci_lower | primary | available | 1.162884266037268 | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio_ci_upper | primary | available | 3.740350930354552 | — |
| hypertension.statistics.prevalence.conditions.59621000.p_value | primary | available | 0.0130277822628989 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_events | primary | available | 46 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_prevalence | primary | available | 0.46 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.conditions.59621000.relative_difference | primary | available | 0.5862068965517243 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio | primary | available | 1.5862068965517244 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio_ci_lower | primary | available | 1.0923422673509318 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio_ci_upper | primary | available | 2.3033552704776303 | — |
| hypertension.statistics.prevalence.conditions.59621000.significant | primary | available | True | — |
| hypertension.statistics.prevalence.conditions.59621000.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.conditions.59621000.statistic | primary | available | 2.483008927356754 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_events | primary | available | 29 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_prevalence | primary | available | 0.29 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_total | primary | available | 100 | — |
| … 169 more | — | — | — | — |

### Prevalence

#### Prevalence endpoint 'conditions.59621000': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.conditions.59621000.FAIL |
| Rule | STAT.PREVALENCE |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** Synthea prevalence=0.29; psynthea prevalence=0.46; absolute_difference=0.17; relative_difference=0.5862068965517243; risk_ratio=1.5862068965517244; 95% CI=[1.0923422673509318, 2.3033552704776303]; adjusted_p=0.0130277822628989; significant_after_fdr=True.

**Interpretation.** The prevalence difference survives FDR correction and exceeds materiality tolerance.

**Impact.** Prevalence equivalence is not supported for this clinical code.

**Limitations**
- FDR controls the expected false-discovery proportion across tested prevalence endpoints.
- Statistical prevalence similarity does not establish clinical pathway equivalence.
- Risk-ratio equivalence requires the full confidence interval to lie within [0.8, 1.25].

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.conditions.59621000.absolute_difference | primary | available | 0.17 | — |
| hypertension.statistics.prevalence.conditions.59621000.adjusted_p_value | primary | available | 0.0130277822628989 | — |
| hypertension.statistics.prevalence.conditions.59621000.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio | primary | available | 2.0855683269476373 | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio_ci_lower | primary | available | 1.162884266037268 | — |
| hypertension.statistics.prevalence.conditions.59621000.odds_ratio_ci_upper | primary | available | 3.740350930354552 | — |
| hypertension.statistics.prevalence.conditions.59621000.p_value | primary | available | 0.0130277822628989 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_events | primary | available | 46 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_prevalence | primary | available | 0.46 | — |
| hypertension.statistics.prevalence.conditions.59621000.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.conditions.59621000.relative_difference | primary | available | 0.5862068965517243 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio | primary | available | 1.5862068965517244 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio_ci_lower | primary | available | 1.0923422673509318 | — |
| hypertension.statistics.prevalence.conditions.59621000.risk_ratio_ci_upper | primary | available | 2.3033552704776303 | — |
| hypertension.statistics.prevalence.conditions.59621000.significant | primary | available | True | — |
| hypertension.statistics.prevalence.conditions.59621000.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.conditions.59621000.statistic | primary | available | 2.483008927356754 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_events | primary | available | 29 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_prevalence | primary | available | 0.29 | — |
| hypertension.statistics.prevalence.conditions.59621000.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'medications.308136' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.medications.308136.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0024006366894774, 0.6664898553842817].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.medications.308136.absolute_difference | primary | available | -0.12 | — |
| hypertension.statistics.prevalence.medications.308136.adjusted_p_value | primary | available | 0.0005294773038177 | — |
| hypertension.statistics.prevalence.medications.308136.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.medications.308136.odds_ratio | primary | available | 0.0352238805970149 | — |
| hypertension.statistics.prevalence.medications.308136.odds_ratio_ci_lower | primary | available | 0.0020557107512159 | — |
| hypertension.statistics.prevalence.medications.308136.odds_ratio_ci_upper | primary | available | 0.6035488035361415 | — |
| hypertension.statistics.prevalence.medications.308136.p_value | primary | available | 0.0003529848692118 | — |
| hypertension.statistics.prevalence.medications.308136.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.medications.308136.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.medications.308136.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.medications.308136.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.medications.308136.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.medications.308136.risk_ratio_ci_lower | primary | available | 0.0024006366894774 | — |
| hypertension.statistics.prevalence.medications.308136.risk_ratio_ci_upper | primary | available | 0.6664898553842817 | — |
| hypertension.statistics.prevalence.medications.308136.significant | primary | available | True | — |
| hypertension.statistics.prevalence.medications.308136.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.medications.308136.statistic | primary | available | -3.5729480050524822 | — |
| hypertension.statistics.prevalence.medications.308136.synthea_events | primary | available | 12 | — |
| hypertension.statistics.prevalence.medications.308136.synthea_prevalence | primary | available | 0.12 | — |
| hypertension.statistics.prevalence.medications.308136.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'medications.310798' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.medications.310798.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.001842964011791, 0.4982591302224974].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.medications.310798.absolute_difference | primary | available | -0.16 | — |
| hypertension.statistics.prevalence.medications.310798.adjusted_p_value | primary | available | 5.4758621785209725e-05 | — |
| hypertension.statistics.prevalence.medications.310798.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.medications.310798.odds_ratio | primary | available | 0.025478667269712 | — |
| hypertension.statistics.prevalence.medications.310798.odds_ratio_ci_lower | primary | available | 0.0015060906379847 | — |
| hypertension.statistics.prevalence.medications.310798.odds_ratio_ci_upper | primary | available | 0.4310248463594016 | — |
| hypertension.statistics.prevalence.medications.310798.p_value | primary | available | 3.0421456547338734e-05 | — |
| hypertension.statistics.prevalence.medications.310798.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.medications.310798.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.medications.310798.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.medications.310798.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.medications.310798.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.medications.310798.risk_ratio_ci_lower | primary | available | 0.001842964011791 | — |
| hypertension.statistics.prevalence.medications.310798.risk_ratio_ci_upper | primary | available | 0.4982591302224974 | — |
| hypertension.statistics.prevalence.medications.310798.significant | primary | available | True | — |
| hypertension.statistics.prevalence.medications.310798.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.medications.310798.statistic | primary | available | -4.170288281141495 | — |
| hypertension.statistics.prevalence.medications.310798.synthea_events | primary | available | 16 | — |
| hypertension.statistics.prevalence.medications.310798.synthea_prevalence | primary | available | 0.16 | — |
| hypertension.statistics.prevalence.medications.310798.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'medications.314076' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.medications.314076.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0014954614883, 0.3977929236390255].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.medications.314076.absolute_difference | primary | available | -0.2 | — |
| hypertension.statistics.prevalence.medications.314076.adjusted_p_value | primary | available | 5.464051814195638e-06 | — |
| hypertension.statistics.prevalence.medications.314076.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.medications.314076.odds_ratio | primary | available | 0.0195364640213566 | — |
| hypertension.statistics.prevalence.medications.314076.odds_ratio_ci_lower | primary | available | 0.0011636949516898 | — |
| hypertension.statistics.prevalence.medications.314076.odds_ratio_ci_upper | primary | available | 0.3279840871557583 | — |
| hypertension.statistics.prevalence.medications.314076.p_value | primary | available | 2.428467472975839e-06 | — |
| hypertension.statistics.prevalence.medications.314076.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.medications.314076.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.medications.314076.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.medications.314076.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.medications.314076.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.medications.314076.risk_ratio_ci_lower | primary | available | 0.0014954614883 | — |
| hypertension.statistics.prevalence.medications.314076.risk_ratio_ci_upper | primary | available | 0.3977929236390255 | — |
| hypertension.statistics.prevalence.medications.314076.significant | primary | available | True | — |
| hypertension.statistics.prevalence.medications.314076.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.medications.314076.statistic | primary | available | -4.714045207910317 | — |
| hypertension.statistics.prevalence.medications.314076.synthea_events | primary | available | 20 | — |
| hypertension.statistics.prevalence.medications.314076.synthea_prevalence | primary | available | 0.2 | — |
| hypertension.statistics.prevalence.medications.314076.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'observations.8462-4' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.observations.8462-4.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0025970336808063, 0.7278916643295309].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.observations.8462-4.absolute_difference | primary | available | -0.11 | — |
| hypertension.statistics.prevalence.observations.8462-4.adjusted_p_value | primary | available | 0.0007260891654759 | — |
| hypertension.statistics.prevalence.observations.8462-4.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.observations.8462-4.odds_ratio | primary | available | 0.0387194462470257 | — |
| hypertension.statistics.prevalence.observations.8462-4.odds_ratio_ci_lower | primary | available | 0.0022493144290031 | — |
| hypertension.statistics.prevalence.observations.8462-4.odds_ratio_ci_upper | primary | available | 0.6665122040499926 | — |
| hypertension.statistics.prevalence.observations.8462-4.p_value | primary | available | 0.0006454125915341 | — |
| hypertension.statistics.prevalence.observations.8462-4.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.observations.8462-4.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.8462-4.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.8462-4.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.8462-4.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.8462-4.risk_ratio_ci_lower | primary | available | 0.0025970336808063 | — |
| hypertension.statistics.prevalence.observations.8462-4.risk_ratio_ci_upper | primary | available | 0.7278916643295309 | — |
| hypertension.statistics.prevalence.observations.8462-4.significant | primary | available | True | — |
| hypertension.statistics.prevalence.observations.8462-4.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.observations.8462-4.statistic | primary | available | -3.4117754381277265 | — |
| hypertension.statistics.prevalence.observations.8462-4.synthea_events | primary | available | 11 | — |
| hypertension.statistics.prevalence.observations.8462-4.synthea_prevalence | primary | available | 0.11 | — |
| hypertension.statistics.prevalence.observations.8462-4.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'observations.8480-6' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.observations.8480-6.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0025970336808063, 0.7278916643295309].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.observations.8480-6.absolute_difference | primary | available | -0.11 | — |
| hypertension.statistics.prevalence.observations.8480-6.adjusted_p_value | primary | available | 0.0007260891654759 | — |
| hypertension.statistics.prevalence.observations.8480-6.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.observations.8480-6.odds_ratio | primary | available | 0.0387194462470257 | — |
| hypertension.statistics.prevalence.observations.8480-6.odds_ratio_ci_lower | primary | available | 0.0022493144290031 | — |
| hypertension.statistics.prevalence.observations.8480-6.odds_ratio_ci_upper | primary | available | 0.6665122040499926 | — |
| hypertension.statistics.prevalence.observations.8480-6.p_value | primary | available | 0.0006454125915341 | — |
| hypertension.statistics.prevalence.observations.8480-6.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.observations.8480-6.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.8480-6.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.8480-6.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.8480-6.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.8480-6.risk_ratio_ci_lower | primary | available | 0.0025970336808063 | — |
| hypertension.statistics.prevalence.observations.8480-6.risk_ratio_ci_upper | primary | available | 0.7278916643295309 | — |
| hypertension.statistics.prevalence.observations.8480-6.significant | primary | available | True | — |
| hypertension.statistics.prevalence.observations.8480-6.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.observations.8480-6.statistic | primary | available | -3.4117754381277265 | — |
| hypertension.statistics.prevalence.observations.8480-6.synthea_events | primary | available | 11 | — |
| hypertension.statistics.prevalence.observations.8480-6.synthea_prevalence | primary | available | 0.11 | — |
| hypertension.statistics.prevalence.observations.8480-6.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'observations.DALY' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.observations.DALY.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0003133440043439, 0.0789926158934438].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.observations.DALY.absolute_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.DALY.adjusted_p_value | primary | available | 6.265462751287367e-45 | — |
| hypertension.statistics.prevalence.observations.DALY.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.observations.DALY.odds_ratio | primary | available | 2.475186257765897e-05 | — |
| hypertension.statistics.prevalence.observations.DALY.odds_ratio_ci_lower | primary | available | 4.863794522764045e-07 | — |
| hypertension.statistics.prevalence.observations.DALY.odds_ratio_ci_upper | primary | available | 0.0012596229100466 | — |
| hypertension.statistics.prevalence.observations.DALY.p_value | primary | available | 2.0884875837624556e-45 | — |
| hypertension.statistics.prevalence.observations.DALY.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.observations.DALY.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.DALY.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.DALY.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.DALY.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.DALY.risk_ratio_ci_lower | primary | available | 0.0003133440043439 | — |
| hypertension.statistics.prevalence.observations.DALY.risk_ratio_ci_upper | primary | available | 0.0789926158934438 | — |
| hypertension.statistics.prevalence.observations.DALY.significant | primary | available | True | — |
| hypertension.statistics.prevalence.observations.DALY.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.observations.DALY.statistic | primary | available | -14.142135623730953 | — |
| hypertension.statistics.prevalence.observations.DALY.synthea_events | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.DALY.synthea_prevalence | primary | available | 1.0 | — |
| hypertension.statistics.prevalence.observations.DALY.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'observations.QALY' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.observations.QALY.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0003133440043439, 0.0789926158934438].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.observations.QALY.absolute_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.QALY.adjusted_p_value | primary | available | 6.265462751287367e-45 | — |
| hypertension.statistics.prevalence.observations.QALY.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.observations.QALY.odds_ratio | primary | available | 2.475186257765897e-05 | — |
| hypertension.statistics.prevalence.observations.QALY.odds_ratio_ci_lower | primary | available | 4.863794522764045e-07 | — |
| hypertension.statistics.prevalence.observations.QALY.odds_ratio_ci_upper | primary | available | 0.0012596229100466 | — |
| hypertension.statistics.prevalence.observations.QALY.p_value | primary | available | 2.0884875837624556e-45 | — |
| hypertension.statistics.prevalence.observations.QALY.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.observations.QALY.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.QALY.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.QALY.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.QALY.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.QALY.risk_ratio_ci_lower | primary | available | 0.0003133440043439 | — |
| hypertension.statistics.prevalence.observations.QALY.risk_ratio_ci_upper | primary | available | 0.0789926158934438 | — |
| hypertension.statistics.prevalence.observations.QALY.significant | primary | available | True | — |
| hypertension.statistics.prevalence.observations.QALY.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.observations.QALY.statistic | primary | available | -14.142135623730953 | — |
| hypertension.statistics.prevalence.observations.QALY.synthea_events | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.QALY.synthea_prevalence | primary | available | 1.0 | — |
| hypertension.statistics.prevalence.observations.QALY.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

#### Prevalence endpoint 'observations.QOLS' has an invalid risk-ratio interval

| Field | Value |
| --- | --- |
| Finding ID | STAT.PREVALENCE.observations.QOLS.INCONCLUSIVE |
| Rule | STAT.PREVALENCE |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** Observed risk_ratio=0.0, CI=[0.0003133440043439, 0.0789926158934438].

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.prevalence.observations.QOLS.absolute_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.QOLS.adjusted_p_value | primary | available | 6.265462751287367e-45 | — |
| hypertension.statistics.prevalence.observations.QOLS.notes | primary | not_computed | — | — |
| hypertension.statistics.prevalence.observations.QOLS.odds_ratio | primary | available | 2.475186257765897e-05 | — |
| hypertension.statistics.prevalence.observations.QOLS.odds_ratio_ci_lower | primary | available | 4.863794522764045e-07 | — |
| hypertension.statistics.prevalence.observations.QOLS.odds_ratio_ci_upper | primary | available | 0.0012596229100466 | — |
| hypertension.statistics.prevalence.observations.QOLS.p_value | primary | available | 2.0884875837624556e-45 | — |
| hypertension.statistics.prevalence.observations.QOLS.psynthea_events | primary | available | 0 | — |
| hypertension.statistics.prevalence.observations.QOLS.psynthea_prevalence | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.QOLS.psynthea_total | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.QOLS.relative_difference | primary | available | -1.0 | — |
| hypertension.statistics.prevalence.observations.QOLS.risk_ratio | primary | available | 0.0 | — |
| hypertension.statistics.prevalence.observations.QOLS.risk_ratio_ci_lower | primary | available | 0.0003133440043439 | — |
| hypertension.statistics.prevalence.observations.QOLS.risk_ratio_ci_upper | primary | available | 0.0789926158934438 | — |
| hypertension.statistics.prevalence.observations.QOLS.significant | primary | available | True | — |
| hypertension.statistics.prevalence.observations.QOLS.significant_after_fdr | primary | available | True | — |
| hypertension.statistics.prevalence.observations.QOLS.statistic | primary | available | -14.142135623730953 | — |
| hypertension.statistics.prevalence.observations.QOLS.synthea_events | primary | available | 100 | — |
| hypertension.statistics.prevalence.observations.QOLS.synthea_prevalence | primary | available | 1.0 | — |
| hypertension.statistics.prevalence.observations.QOLS.synthea_total | primary | available | 100 | — |
| … 1 more | — | — | — | — |

### Statistical

#### Statistical comparison is ready

| Field | Value |
| --- | --- |
| Finding ID | STAT.READINESS.hypertension.PASS |
| Rule | STAT.READINESS |
| Status | PASS |
| Severity | info |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** The pipeline reports valid_for_statistical_comparison=True and skipped=False.

**Interpretation.** Endpoint-level statistical rules may be evaluated.

**Impact.** Statistical readiness does not block downstream interpretation.

**Limitations**
- Readiness does not imply equivalence; endpoint-level results remain decisive.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.summary.hypertension.categorical_test_count | primary | available | 2 | — |
| hypertension.statistics.summary.hypertension.continuous_test_count | primary | available | 18 | — |
| hypertension.statistics.summary.hypertension.distribution_test_count | primary | available | 4 | — |
| hypertension.statistics.summary.hypertension.mean_jensen_shannon_divergence | primary | available | 0.0 | — |
| hypertension.statistics.summary.hypertension.prevalence_test_count | primary | available | 9 | — |
| hypertension.statistics.summary.hypertension.significant_after_fdr_count | primary | available | 9 | — |
| hypertension.statistics.summary.hypertension.significant_test_count | primary | available | 21 | — |
| hypertension.statistics.summary.hypertension.skip_reason | primary | not_computed | — | — |
| hypertension.statistics.summary.hypertension.skipped | primary | available | False | — |
| hypertension.statistics.summary.hypertension.valid_for_statistical_comparison | primary | available | True | — |
| hypertension.statistics.summary.hypertension.validation_status | primary | available | partially_comparable | — |

#### Continuous endpoint 'age.kolmogorov_smirnov': pass

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.age.kolmogorov_smirnov.PASS |
| Rule | STAT.TEST_FAMILIES |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=0.908411, effect_size=0.08 (negligible), n_synthea=100, n_psynthea=100.

**Interpretation.** No statistically significant or practically relevant difference was detected.

**Impact.** This endpoint supports statistical similarity under the configured thresholds.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.effect_size | primary | available | 0.08 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.p_value | primary | available | 0.9084105017744524 | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.significant | primary | available | False | — |
| hypertension.statistics.continuous.age.kolmogorov_smirnov.statistic | primary | available | 0.08 | — |

#### Continuous endpoint 'age.mann_whitney_u': pass

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.age.mann_whitney_u.PASS |
| Rule | STAT.TEST_FAMILIES |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=0.821191, effect_size=-0.0186 (negligible), n_synthea=100, n_psynthea=100.

**Interpretation.** No statistically significant or practically relevant difference was detected.

**Impact.** This endpoint supports statistical similarity under the configured thresholds.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.age.mann_whitney_u.effect_size | primary | available | -0.0185999999999999 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.age.mann_whitney_u.p_value | primary | available | 0.8211908103897939 | — |
| hypertension.statistics.continuous.age.mann_whitney_u.significant | primary | available | False | — |
| hypertension.statistics.continuous.age.mann_whitney_u.statistic | primary | available | 5093.0 | — |

#### Continuous endpoint 'age.welch_t_test': pass

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.age.welch_t_test.PASS |
| Rule | STAT.TEST_FAMILIES |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=0.80067, effect_size=-0.0357541 (negligible), n_synthea=100, n_psynthea=100.

**Interpretation.** No statistically significant or practically relevant difference was detected.

**Impact.** This endpoint supports statistical similarity under the configured thresholds.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.age.welch_t_test.effect_size | primary | available | -0.0357540984510791 | — |
| hypertension.statistics.continuous.age.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.age.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.age.welch_t_test.p_value | primary | available | 0.8006700198836396 | — |
| hypertension.statistics.continuous.age.welch_t_test.significant | primary | available | False | — |
| hypertension.statistics.continuous.age.welch_t_test.statistic | primary | available | -0.252819654699695 | — |

#### Continuous endpoint 'conditions_per_patient.kolmogorov_smirnov': pass

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.conditions_per_patient.kolmogorov_smirnov.PASS |
| Rule | STAT.TEST_FAMILIES |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=0.111195, effect_size=0.17 (very small), n_synthea=100, n_psynthea=100.

**Interpretation.** No statistically significant or practically relevant difference was detected.

**Impact.** This endpoint supports statistical similarity under the configured thresholds.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.effect_size | primary | available | 0.1699999999999999 | — |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.p_value | primary | available | 0.1111952605382919 | — |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.significant | primary | available | False | — |
| hypertension.statistics.continuous.conditions_per_patient.kolmogorov_smirnov.statistic | primary | available | 0.1699999999999999 | — |

#### Continuous endpoint 'conditions_per_patient.mann_whitney_u': warning

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.conditions_per_patient.mann_whitney_u.WARNING |
| Rule | STAT.TEST_FAMILIES |
| Status | WARNING |
| Severity | low |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=0.0133111, effect_size=0.17 (very small), n_synthea=100, n_psynthea=100.

**Interpretation.** A statistically detectable difference exists, but its effect magnitude is below the configured practical-relevance threshold.

**Impact.** The difference should be reported but does not alone demonstrate material non-equivalence.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.effect_size | primary | available | 0.17 | — |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.p_value | primary | available | 0.0133110623401141 | — |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.significant | primary | available | True | — |
| hypertension.statistics.continuous.conditions_per_patient.mann_whitney_u.statistic | primary | available | 4150.0 | — |

#### Continuous endpoint 'conditions_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.conditions_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | moderate |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=0.0128971, effect_size=0.354903 (small), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.effect_size | primary | available | 0.3549033903260028 | — |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.p_value | primary | available | 0.0128971180075548 | — |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.conditions_per_patient.welch_t_test.statistic | primary | available | 2.5095459396561273 | — |

#### Continuous endpoint 'encounters_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.encounters_per_patient.kolmogorov_smirnov.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=2.20876e-59, effect_size=1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.effect_size | primary | available | 1.0 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.p_value | primary | available | 2.208760693199506e-59 | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.significant | primary | available | True | — |
| hypertension.statistics.continuous.encounters_per_patient.kolmogorov_smirnov.statistic | primary | available | 1.0 | — |

#### Continuous endpoint 'encounters_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.encounters_per_patient.mann_whitney_u.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=1.76245e-35, effect_size=-1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.effect_size | primary | available | -1.0 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.p_value | primary | available | 1.7624465916349795e-35 | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.significant | primary | available | True | — |
| hypertension.statistics.continuous.encounters_per_patient.mann_whitney_u.statistic | primary | available | 10000.0 | — |

#### Continuous endpoint 'encounters_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.encounters_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=2.87307e-47, effect_size=-3.68967 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.effect_size | primary | available | -3.689666185268692 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.p_value | primary | available | 2.873071134163329e-47 | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.encounters_per_patient.welch_t_test.statistic | primary | available | -26.08987979918192 | — |

#### Continuous endpoint 'medications_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.medications_per_patient.kolmogorov_smirnov.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | moderate |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=0.000411741, effect_size=0.29 (small), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.effect_size | primary | available | 0.29 | — |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.p_value | primary | available | 0.0004117410017938 | — |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.significant | primary | available | True | — |
| hypertension.statistics.continuous.medications_per_patient.kolmogorov_smirnov.statistic | primary | available | 0.29 | — |

#### Continuous endpoint 'medications_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.medications_per_patient.mann_whitney_u.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | moderate |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=7.12477e-09, effect_size=-0.29 (small), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.effect_size | primary | available | -0.29 | — |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.p_value | primary | available | 7.124770044265602e-09 | — |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.significant | primary | available | True | — |
| hypertension.statistics.continuous.medications_per_patient.mann_whitney_u.statistic | primary | available | 6450.0 | — |

#### Continuous endpoint 'medications_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.medications_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=9.87863e-08, effect_size=-0.813346 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.effect_size | primary | available | -0.8133457582761467 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.p_value | primary | available | 9.878631814650468e-08 | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.medications_per_patient.welch_t_test.statistic | primary | available | -5.751223011263779 | — |

#### Continuous endpoint 'observations_per_patient.kolmogorov_smirnov': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.observations_per_patient.kolmogorov_smirnov.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=2.20876e-59, effect_size=1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.effect_size | primary | available | 1.0 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.p_value | primary | available | 2.208760693199506e-59 | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.significant | primary | available | True | — |
| hypertension.statistics.continuous.observations_per_patient.kolmogorov_smirnov.statistic | primary | available | 1.0 | — |

#### Continuous endpoint 'observations_per_patient.mann_whitney_u': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.observations_per_patient.mann_whitney_u.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=5.5448e-40, effect_size=-1 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.effect_size | primary | available | -1.0 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.p_value | primary | available | 5.544798383772403e-40 | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.significant | primary | available | True | — |
| hypertension.statistics.continuous.observations_per_patient.mann_whitney_u.statistic | primary | available | 10000.0 | — |

#### Continuous endpoint 'observations_per_patient.welch_t_test': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.observations_per_patient.welch_t_test.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | high |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | yes |

**Observation.** statistical test: p=6.62025e-117, effect_size=-20.406 (large), n_synthea=100, n_psynthea=100.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.effect_size | primary | available | -20.406037611301443 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.p_value | primary | available | 6.620254057615393e-117 | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.significant | primary | available | True | — |
| hypertension.statistics.continuous.observations_per_patient.welch_t_test.statistic | primary | available | -144.2924757209899 | — |

#### Continuous endpoint 'procedures_per_patient.kolmogorov_smirnov': pass

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.procedures_per_patient.kolmogorov_smirnov.PASS |
| Rule | STAT.TEST_FAMILIES |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=1, effect_size=0 (negligible), n_synthea=100, n_psynthea=100.

**Interpretation.** No statistically significant or practically relevant difference was detected.

**Impact.** This endpoint supports statistical similarity under the configured thresholds.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.effect_size | primary | available | 0.0 | — |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.p_value | primary | available | 1.0 | — |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.significant | primary | available | False | — |
| hypertension.statistics.continuous.procedures_per_patient.kolmogorov_smirnov.statistic | primary | available | 0.0 | — |

#### Continuous endpoint 'procedures_per_patient.mann_whitney_u' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.procedures_per_patient.mann_whitney_u.INCONCLUSIVE |
| Rule | STAT.TEST_FAMILIES |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** A finite p-value, effect size and significance flag are required.

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.effect_size | primary | available | 0.0 | — |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.p_value | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.significant | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.mann_whitney_u.statistic | primary | available | 5000.0 | — |

#### Continuous endpoint 'procedures_per_patient.welch_t_test' is inconclusive

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.continuous.procedures_per_patient.welch_t_test.INCONCLUSIVE |
| Rule | STAT.TEST_FAMILIES |
| Status | INCONCLUSIVE |
| Severity | moderate |
| Confidence | low |
| Evidence strength | insufficient |
| Blocks research use | yes |

**Observation.** A finite p-value, effect size and significance flag are required.

**Interpretation.** The available statistical evidence is insufficient for a defensible equivalence decision.

**Impact.** This endpoint must not be reported as statistically equivalent or different.

**Limitations**
- No missing value has been interpreted as zero.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.effect_size | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.n_synthea | primary | available | 100 | — |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.notes | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.p_value | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.significant | primary | not_computed | — | — |
| hypertension.statistics.continuous.procedures_per_patient.welch_t_test.statistic | primary | not_computed | — | — |

#### Categorical endpoint 'encounter_class.chi_square': fail

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.categorical.encounter_class.chi_square.FAIL |
| Rule | STAT.TEST_FAMILIES |
| Status | FAIL |
| Severity | moderate |
| Confidence | moderate |
| Evidence strength | moderate |
| Blocks research use | yes |

**Observation.** statistical test: p=3.07608e-118, effect_size=0.744462 (moderate), n_synthea=941, n_psynthea=46.

**Interpretation.** The engines differ statistically and the estimated effect is not negligible.

**Impact.** Functional/statistical equivalence is not supported for this endpoint.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.categorical.encounter_class.chi_square.effect_size | primary | available | 0.7444623761769559 | — |
| hypertension.statistics.categorical.encounter_class.chi_square.n_psynthea | primary | available | 46 | — |
| hypertension.statistics.categorical.encounter_class.chi_square.n_synthea | primary | available | 941 | — |
| hypertension.statistics.categorical.encounter_class.chi_square.notes | primary | not_computed | — | — |
| hypertension.statistics.categorical.encounter_class.chi_square.p_value | primary | available | 3.076084430638223e-118 | — |
| hypertension.statistics.categorical.encounter_class.chi_square.significant | primary | available | True | — |
| hypertension.statistics.categorical.encounter_class.chi_square.statistic | primary | available | 547.0193145589798 | — |

#### Categorical endpoint 'gender.chi_square': pass

| Field | Value |
| --- | --- |
| Finding ID | STAT.TEST_FAMILIES.categorical.gender.chi_square.PASS |
| Rule | STAT.TEST_FAMILIES |
| Status | PASS |
| Severity | info |
| Confidence | high |
| Evidence strength | strong |
| Blocks research use | no |

**Observation.** statistical test: p=0.391463, effect_size=0.0605968 (negligible), n_synthea=100, n_psynthea=100.

**Interpretation.** No statistically significant or practically relevant difference was detected.

**Impact.** This endpoint supports statistical similarity under the configured thresholds.

**Limitations**
- Statistical similarity is not equivalent to clinical interchangeability.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.statistics.categorical.gender.chi_square.effect_size | primary | available | 0.0605967872435082 | — |
| hypertension.statistics.categorical.gender.chi_square.n_psynthea | primary | available | 100 | — |
| hypertension.statistics.categorical.gender.chi_square.n_synthea | primary | available | 100 | — |
| hypertension.statistics.categorical.gender.chi_square.notes | primary | not_computed | — | — |
| hypertension.statistics.categorical.gender.chi_square.p_value | primary | available | 0.391462579007701 | — |
| hypertension.statistics.categorical.gender.chi_square.significant | primary | available | False | — |
| hypertension.statistics.categorical.gender.chi_square.statistic | primary | available | 0.7343941248470013 | — |

### Structural

#### Evidence contains not computed values

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.EVIDENCE_INTEGRITY.NOT_COMPUTED |
| Rule | STRUCT.EVIDENCE_INTEGRITY |
| Status | WARNING |
| Severity | low |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Detected 83 evidence value(s) with availability 'not_computed'.

**Interpretation.** The affected metrics cannot be treated as observed zeroes or valid calculated values.

**Impact.** Downstream interpretation is limited for the affected metrics.

**Limitations**
- The rule identifies structural symptoms but does not determine the implementation root cause.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.clinical_signal.conditions.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.conditions.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.medications.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.observations.expected_terms | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_signal_detected_psynthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_signal_detected_synthea | primary | not_computed | — | — |
| hypertension.functional.clinical_signal.procedures.expected_terms | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.medications.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.medications.overlap_coefficient | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.observations.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.observations.overlap_coefficient | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.procedures.jaccard_similarity | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.procedures.jensen_shannon_divergence | primary | not_computed | — | — |
| hypertension.functional.distributional_similarity.procedures.overlap_coefficient | primary | not_computed | — | — |
| hypertension.functional.table_status.procedures.relative_row_difference | primary | not_computed | — | — |
| … 63 more | — | — | — | — |

#### Required table 'conditions' is structurally available

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.REQUIRED_TABLES.conditions.PASS |
| Rule | STRUCT.REQUIRED_TABLES |
| Status | PASS |
| Severity | info |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Both engines provide a non-empty required table without a blocking issue.

**Interpretation.** The table pair is structurally eligible for downstream comparison.

**Impact.** Structural availability does not block analysis of this table.

**Limitations**
- Availability does not demonstrate distributional or clinical equivalence.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.table_status.conditions.blocking_issue | primary | available | False | — |
| hypertension.functional.table_status.conditions.psynthea_available | primary | available | True | — |
| hypertension.functional.table_status.conditions.psynthea_empty | primary | available | False | — |
| hypertension.functional.table_status.conditions.psynthea_rows | primary | available | 46 | — |
| hypertension.functional.table_status.conditions.relative_row_difference | primary | available | 0.5862068965517241 | — |
| hypertension.functional.table_status.conditions.required | primary | available | True | — |
| hypertension.functional.table_status.conditions.row_difference | primary | available | 17 | — |
| hypertension.functional.table_status.conditions.synthea_available | primary | available | True | — |
| hypertension.functional.table_status.conditions.synthea_empty | primary | available | False | — |
| hypertension.functional.table_status.conditions.synthea_rows | primary | available | 29 | — |

#### Required table 'encounters' is structurally available

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.REQUIRED_TABLES.encounters.PASS |
| Rule | STRUCT.REQUIRED_TABLES |
| Status | PASS |
| Severity | info |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Both engines provide a non-empty required table without a blocking issue.

**Interpretation.** The table pair is structurally eligible for downstream comparison.

**Impact.** Structural availability does not block analysis of this table.

**Limitations**
- Availability does not demonstrate distributional or clinical equivalence.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.table_status.encounters.blocking_issue | primary | available | False | — |
| hypertension.functional.table_status.encounters.psynthea_available | primary | available | True | — |
| hypertension.functional.table_status.encounters.psynthea_empty | primary | available | False | — |
| hypertension.functional.table_status.encounters.psynthea_rows | primary | available | 46 | — |
| hypertension.functional.table_status.encounters.relative_row_difference | primary | available | -0.951115834218916 | — |
| hypertension.functional.table_status.encounters.required | primary | available | True | — |
| hypertension.functional.table_status.encounters.row_difference | primary | available | -895 | — |
| hypertension.functional.table_status.encounters.synthea_available | primary | available | True | — |
| hypertension.functional.table_status.encounters.synthea_empty | primary | available | False | — |
| hypertension.functional.table_status.encounters.synthea_rows | primary | available | 941 | — |

#### Optional table 'medications' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.REQUIRED_TABLES.medications.OPTIONAL_WARNING |
| Rule | STRUCT.REQUIRED_TABLES |
| Status | WARNING |
| Severity | low |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Optional table status: Synthea available=True, psynthea available=True, Synthea empty=False, psynthea empty=True, blocking_issue=False.

**Interpretation.** The optional table cannot support supplementary analysis.

**Impact.** Core structural comparability is not blocked because the table is optional.

**Limitations**
- Optionality is taken from the pipeline configuration and is not inferred clinically.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.table_status.medications.blocking_issue | primary | available | False | — |
| hypertension.functional.table_status.medications.psynthea_available | primary | available | True | — |
| hypertension.functional.table_status.medications.psynthea_empty | primary | available | True | — |
| hypertension.functional.table_status.medications.psynthea_rows | primary | available | 0 | — |
| hypertension.functional.table_status.medications.relative_row_difference | primary | available | -1.0 | — |
| hypertension.functional.table_status.medications.required | primary | available | False | — |
| hypertension.functional.table_status.medications.row_difference | primary | available | -48 | — |
| hypertension.functional.table_status.medications.synthea_available | primary | available | True | — |
| hypertension.functional.table_status.medications.synthea_empty | primary | available | False | — |
| hypertension.functional.table_status.medications.synthea_rows | primary | available | 48 | — |

#### Optional table 'observations' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.REQUIRED_TABLES.observations.OPTIONAL_WARNING |
| Rule | STRUCT.REQUIRED_TABLES |
| Status | WARNING |
| Severity | low |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Optional table status: Synthea available=True, psynthea available=True, Synthea empty=False, psynthea empty=True, blocking_issue=False.

**Interpretation.** The optional table cannot support supplementary analysis.

**Impact.** Core structural comparability is not blocked because the table is optional.

**Limitations**
- Optionality is taken from the pipeline configuration and is not inferred clinically.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.table_status.observations.blocking_issue | primary | available | False | — |
| hypertension.functional.table_status.observations.psynthea_available | primary | available | True | — |
| hypertension.functional.table_status.observations.psynthea_empty | primary | available | True | — |
| hypertension.functional.table_status.observations.psynthea_rows | primary | available | 0 | — |
| hypertension.functional.table_status.observations.relative_row_difference | primary | available | -1.0 | — |
| hypertension.functional.table_status.observations.required | primary | available | False | — |
| hypertension.functional.table_status.observations.row_difference | primary | available | -3224 | — |
| hypertension.functional.table_status.observations.synthea_available | primary | available | True | — |
| hypertension.functional.table_status.observations.synthea_empty | primary | available | False | — |
| hypertension.functional.table_status.observations.synthea_rows | primary | available | 3224 | — |

#### Required table 'patients' is structurally available

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.REQUIRED_TABLES.patients.PASS |
| Rule | STRUCT.REQUIRED_TABLES |
| Status | PASS |
| Severity | info |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Both engines provide a non-empty required table without a blocking issue.

**Interpretation.** The table pair is structurally eligible for downstream comparison.

**Impact.** Structural availability does not block analysis of this table.

**Limitations**
- Availability does not demonstrate distributional or clinical equivalence.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.table_status.patients.blocking_issue | primary | available | False | — |
| hypertension.functional.table_status.patients.psynthea_available | primary | available | True | — |
| hypertension.functional.table_status.patients.psynthea_empty | primary | available | False | — |
| hypertension.functional.table_status.patients.psynthea_rows | primary | available | 100 | — |
| hypertension.functional.table_status.patients.relative_row_difference | primary | available | 0.0 | — |
| hypertension.functional.table_status.patients.required | primary | available | True | — |
| hypertension.functional.table_status.patients.row_difference | primary | available | 0 | — |
| hypertension.functional.table_status.patients.synthea_available | primary | available | True | — |
| hypertension.functional.table_status.patients.synthea_empty | primary | available | False | — |
| hypertension.functional.table_status.patients.synthea_rows | primary | available | 100 | — |

#### Optional table 'procedures' is unavailable or empty

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.REQUIRED_TABLES.procedures.OPTIONAL_WARNING |
| Rule | STRUCT.REQUIRED_TABLES |
| Status | WARNING |
| Severity | low |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** Optional table status: Synthea available=True, psynthea available=True, Synthea empty=True, psynthea empty=True, blocking_issue=False.

**Interpretation.** The optional table cannot support supplementary analysis.

**Impact.** Core structural comparability is not blocked because the table is optional.

**Limitations**
- Optionality is taken from the pipeline configuration and is not inferred clinically.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.table_status.procedures.blocking_issue | primary | available | False | — |
| hypertension.functional.table_status.procedures.psynthea_available | primary | available | True | — |
| hypertension.functional.table_status.procedures.psynthea_empty | primary | available | True | — |
| hypertension.functional.table_status.procedures.psynthea_rows | primary | available | 0 | — |
| hypertension.functional.table_status.procedures.relative_row_difference | primary | not_computed | — | — |
| hypertension.functional.table_status.procedures.required | primary | available | False | — |
| hypertension.functional.table_status.procedures.row_difference | primary | available | 0 | — |
| hypertension.functional.table_status.procedures.synthea_available | primary | available | True | — |
| hypertension.functional.table_status.procedures.synthea_empty | primary | available | True | — |
| hypertension.functional.table_status.procedures.synthea_rows | primary | available | 0 | — |

#### Module-level structural comparability

| Field | Value |
| --- | --- |
| Finding ID | STRUCT.COMPARABILITY.PASS |
| Rule | STRUCT.COMPARABILITY |
| Status | PASS |
| Severity | info |
| Confidence | very_high |
| Evidence strength | very_strong |
| Blocks research use | no |

**Observation.** The functional validation stage reports valid_for_comparison=True.

**Interpretation.** The module passed the pipeline's structural comparability gate.

**Impact.** Downstream statistical validation may proceed, subject to its own assumptions.

**Limitations**
- This gate does not itself prove statistical, epidemiological or clinical equivalence.

**Evidence**
| Metric | Role | Availability | Value | Rationale |
| --- | --- | --- | --- | --- |
| hypertension.functional.summary.hypertension.valid_for_comparison | primary | available | True | — |


## Recommendations

| Priority | Recommendation | Finding | Action | Blocking | Verification |
| --- | --- | --- | --- | --- | --- |
| urgent | CLINICAL.CODE_OVERLAP.medications.REPAIR | CLINICAL.CODE_OVERLAP.medications.INCONCLUSIVE | Regenerate and validate the affected clinical-comparison evidence. | yes | Re-run evidence collection and confirm that the row can be interpreted without missing or contradictory fields. |
| urgent | CLINICAL.CODE_OVERLAP.observations.REPAIR | CLINICAL.CODE_OVERLAP.observations.INCONCLUSIVE | Regenerate and validate the affected clinical-comparison evidence. | yes | Re-run evidence collection and confirm that the row can be interpreted without missing or contradictory fields. |
| urgent | CLINICAL.CODE_OVERLAP.procedures.REPAIR | CLINICAL.CODE_OVERLAP.procedures.INCONCLUSIVE | Regenerate and validate the affected clinical-comparison evidence. | yes | Re-run evidence collection and confirm that the row can be interpreted without missing or contradictory fields. |
| urgent | CLINICAL.EVENT_RETENTION.medications.INVESTIGATE | CLINICAL.EVENT_RETENTION.medications.FAIL | Investigate abnormal generation volume for 'medications' events in psynthea. | yes | Re-run the same seeded cohorts and recompute paired domain signal counts. |
| urgent | CLINICAL.EVENT_RETENTION.observations.INVESTIGATE | CLINICAL.EVENT_RETENTION.observations.FAIL | Investigate abnormal generation volume for 'observations' events in psynthea. | yes | Re-run the same seeded cohorts and recompute paired domain signal counts. |
| urgent | EPI.PREVALENCE_PROFILE.RECALIBRATE | EPI.PREVALENCE_PROFILE.INCONCLUSIVE | Recalibrate the affected disease modules and rerun prevalence validation. | yes | Regenerate both cohorts, apply FDR correction and confirm no principal prevalence remains materially discordant. |
| high | CLINICAL.EVENT_RETENTION.conditions.INVESTIGATE | CLINICAL.EVENT_RETENTION.conditions.WARNING | Investigate abnormal generation volume for 'conditions' events in psynthea. | no | Re-run the same seeded cohorts and recompute paired domain signal counts. |
| high | STAT.DISTRIBUTION.conditions.chi_square.RECOMPUTE | STAT.DISTRIBUTION.conditions.chi_square.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.DISTRIBUTION.medications.chi_square.RECOMPUTE | STAT.DISTRIBUTION.medications.chi_square.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.DISTRIBUTION.observations.chi_square.RECOMPUTE | STAT.DISTRIBUTION.observations.chi_square.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.DISTRIBUTION.procedures.chi_square.RECOMPUTE | STAT.DISTRIBUTION.procedures.chi_square.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.conditions.59621000.REVIEW | STAT.PREVALENCE.conditions.59621000.FAIL | Review disease-module incidence logic, cohort denominators and code mapping for this endpoint. | yes | Repeat across seeds and confirm absolute, relative and ratio criteria using FDR-adjusted inference. |
| high | STAT.PREVALENCE.medications.308136.RECOMPUTE | STAT.PREVALENCE.medications.308136.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.medications.310798.RECOMPUTE | STAT.PREVALENCE.medications.310798.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.medications.314076.RECOMPUTE | STAT.PREVALENCE.medications.314076.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.observations.8462-4.RECOMPUTE | STAT.PREVALENCE.observations.8462-4.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.observations.8480-6.RECOMPUTE | STAT.PREVALENCE.observations.8480-6.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.observations.DALY.RECOMPUTE | STAT.PREVALENCE.observations.DALY.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.observations.QALY.RECOMPUTE | STAT.PREVALENCE.observations.QALY.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.PREVALENCE.observations.QOLS.RECOMPUTE | STAT.PREVALENCE.observations.QOLS.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.TEST_FAMILIES.categorical.encounter_class.chi_square.INVESTIGATE | STAT.TEST_FAMILIES.categorical.encounter_class.chi_square.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.conditions_per_patient.welch_t_test.INVESTIGATE | STAT.TEST_FAMILIES.continuous.conditions_per_patient.welch_t_test.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.encounters_per_patient.kolmogorov_smirnov.INVESTIGATE | STAT.TEST_FAMILIES.continuous.encounters_per_patient.kolmogorov_smirnov.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.encounters_per_patient.mann_whitney_u.INVESTIGATE | STAT.TEST_FAMILIES.continuous.encounters_per_patient.mann_whitney_u.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.encounters_per_patient.welch_t_test.INVESTIGATE | STAT.TEST_FAMILIES.continuous.encounters_per_patient.welch_t_test.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.medications_per_patient.kolmogorov_smirnov.INVESTIGATE | STAT.TEST_FAMILIES.continuous.medications_per_patient.kolmogorov_smirnov.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.medications_per_patient.mann_whitney_u.INVESTIGATE | STAT.TEST_FAMILIES.continuous.medications_per_patient.mann_whitney_u.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.medications_per_patient.welch_t_test.INVESTIGATE | STAT.TEST_FAMILIES.continuous.medications_per_patient.welch_t_test.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.observations_per_patient.kolmogorov_smirnov.INVESTIGATE | STAT.TEST_FAMILIES.continuous.observations_per_patient.kolmogorov_smirnov.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.observations_per_patient.mann_whitney_u.INVESTIGATE | STAT.TEST_FAMILIES.continuous.observations_per_patient.mann_whitney_u.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.observations_per_patient.welch_t_test.INVESTIGATE | STAT.TEST_FAMILIES.continuous.observations_per_patient.welch_t_test.FAIL | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | yes | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |
| high | STAT.TEST_FAMILIES.continuous.procedures_per_patient.mann_whitney_u.RECOMPUTE | STAT.TEST_FAMILIES.continuous.procedures_per_patient.mann_whitney_u.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STAT.TEST_FAMILIES.continuous.procedures_per_patient.welch_t_test.RECOMPUTE | STAT.TEST_FAMILIES.continuous.procedures_per_patient.welch_t_test.INCONCLUSIVE | Recompute the statistical endpoint with complete finite inputs and adequate sample size. | yes | Re-run normalization and confirm that all metrics required by this rule are available. |
| high | STRUCT.REPAIR.NOT_COMPUTED | STRUCT.EVIDENCE_INTEGRITY.NOT_COMPUTED | Inspect the originating pipeline source and regenerate the affected evidence. | no | Re-run evidence normalization and confirm that the affected metric identifiers no longer have the flagged availability state. |
| medium | STAT.TEST_FAMILIES.continuous.conditions_per_patient.mann_whitney_u.INVESTIGATE | STAT.TEST_FAMILIES.continuous.conditions_per_patient.mann_whitney_u.WARNING | Inspect the endpoint definition, cohort construction and random-seed sensitivity. | no | Repeat the comparison across independent seeds and report effect estimates with uncertainty. |

## Incomplete or Blocked Rules

| Rule | Dimension | Execution status | Applicability | Reason |
| --- | --- | --- | --- | --- |
| EPI.RELATIONSHIP_PRESERVATION | epidemiological | not_evaluated | not_evaluated | No explicit age-, sex-, stratified-association or comorbidity comparison evidence was produced; H3 must not be inferred from marginal distributions. |
| SPANISH.EVIDENCE_INTEGRITY | spanish_adaptation | not_evaluated | not_evaluated | Required pipeline stages are not complete. |
| SPANISH.PRIMARY_CARE | spanish_adaptation | not_evaluated | not_evaluated | Required pipeline stages are not complete. |
| SPANISH.REFERRALS | spanish_adaptation | not_evaluated | not_evaluated | Required pipeline stages are not complete. |
| SPANISH.HEALTHCARE_FLOW | spanish_adaptation | not_evaluated | not_evaluated | Required pipeline stages are not complete. |
| SPANISH.CLINICAL_CONTEXT | spanish_adaptation | not_evaluated | not_evaluated | Required pipeline stages are not complete. |

## Limitations

- 6 rule(s) did not complete with an evaluated or explicitly non-applicable result.
- 32 finding(s) explicitly block downstream research use.
- At least one validation dimension remains inconclusive.

## Audit Trail

| Field | Value |
| --- | --- |
| Report ID | hypertension-equivalence.run-20260717T092616615350Z-3e39dc09836f.hypertension.interpretation |
| Pipeline run | run-20260717T092616615350Z-3e39dc09836f |
| Report schema | 1.1.0 |
| Generated at | 2026-07-17T09:26:22.168722+00:00 |
| Execution started | 2026-07-17T09:26:22.162604+00:00 |
| Execution completed | 2026-07-17T09:26:22.168722+00:00 |
| Execution duration (s) | 0.006118 |
| Rule order | STRUCT.EVIDENCE_INTEGRITY → STRUCT.REQUIRED_TABLES → STRUCT.COMPARABILITY → STAT.READINESS → STAT.TEST_FAMILIES → STAT.PREVALENCE → STAT.DISTRIBUTION → CLINICAL.SIGNAL_PRESERVATION → CLINICAL.EVENT_RETENTION → CLINICAL.CODE_OVERLAP → EPI.DEMOGRAPHIC_PROFILE → EPI.PREVALENCE_PROFILE → EPI.RELATIONSHIP_PRESERVATION → SPANISH.EVIDENCE_INTEGRITY → SPANISH.PRIMARY_CARE → SPANISH.REFERRALS → SPANISH.HEALTHCARE_FLOW → SPANISH.CLINICAL_CONTEXT |
| Document fingerprint | d2984d5ab632393dbb3f81936107125d9349154b39c293844c8715c3af747f07 |

### Rule Evaluations

| Rule | Dimension | Status | Duration (s) | Findings | Derived evidence |
| --- | --- | --- | --- | --- | --- |
| STRUCT.EVIDENCE_INTEGRITY | structural | completed | 0.000213 | 1 | 0 |
| STRUCT.REQUIRED_TABLES | structural | completed | 0.000300 | 6 | 0 |
| STRUCT.COMPARABILITY | structural | completed | 0.000079 | 1 | 0 |
| STAT.READINESS | statistical | completed | 0.000095 | 1 | 0 |
| STAT.TEST_FAMILIES | statistical | completed | 0.000921 | 20 | 0 |
| STAT.PREVALENCE | statistical | completed | 0.000973 | 9 | 0 |
| STAT.DISTRIBUTION | statistical | completed | 0.000222 | 4 | 0 |
| CLINICAL.SIGNAL_PRESERVATION | clinical | completed | 0.000245 | 4 | 0 |
| CLINICAL.EVENT_RETENTION | clinical | completed | 0.000244 | 4 | 0 |
| CLINICAL.CODE_OVERLAP | clinical | completed | 0.000302 | 4 | 0 |
| EPI.DEMOGRAPHIC_PROFILE | epidemiological | completed | 0.000763 | 1 | 0 |
| EPI.PREVALENCE_PROFILE | epidemiological | completed | 0.000644 | 1 | 0 |
| EPI.RELATIONSHIP_PRESERVATION | epidemiological | not_evaluated | 0.000544 | 0 | 0 |
| SPANISH.EVIDENCE_INTEGRITY | spanish_adaptation | not_evaluated | 0.000004 | 0 | 0 |
| SPANISH.PRIMARY_CARE | spanish_adaptation | not_evaluated | 0.000004 | 0 | 0 |
| SPANISH.REFERRALS | spanish_adaptation | not_evaluated | 0.000006 | 0 | 0 |
| SPANISH.HEALTHCARE_FLOW | spanish_adaptation | not_evaluated | 0.000003 | 0 | 0 |
| SPANISH.CLINICAL_CONTEXT | spanish_adaptation | not_evaluated | 0.000002 | 0 | 0 |

### Report Metadata

```json
{
  "pipeline_run_id": "run-20260717T092616615350Z-3e39dc09836f",
  "recommendation_plan_fingerprint": "11fa003d10c2d6c043ea58faf132d5a1f62fc51986360110e4e76f7af2fb191a",
  "source_report_id": "hypertension-equivalence.run-20260717T092616615350Z-3e39dc09836f.hypertension.interpretation",
  "workflow_version": "1.1.0"
}
```
