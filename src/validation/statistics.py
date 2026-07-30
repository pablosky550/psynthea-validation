"""
Statistical validation utilities.

This module contains reusable statistical tests and effect-size estimators used
by Phase 2 of the validation framework.

The module answers how strong the evidence is that two cohorts differ. It does
not load data, compute descriptive cohort metrics, compare domain profiles,
create plots or generate reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, isfinite, log, sqrt
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import jensenshannon

from validation.constants import (
    DEFAULT_CONFIDENCE_LEVEL,
    DEFAULT_SIGNIFICANCE_LEVEL,
)


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class ConfidenceInterval:
    """
    Lower and upper bounds for an estimated quantity.
    """

    lower: float | None
    upper: float | None
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL


@dataclass(slots=True)
class StatisticalTestResult:
    """
    Canonical result returned by every inferential statistical test.
    """

    test_name: str
    statistic: float | None
    p_value: float | None
    effect_size: float | None = None
    effect_size_name: str | None = None
    confidence_interval: ConfidenceInterval | None = None
    n_synthea: int | None = None
    n_psynthea: int | None = None
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL
    significant: bool | None = None
    interpretation: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class MultipleTestingCorrectionResult:
    """
    Result of applying a multiple-testing correction to p-values.
    """

    method: str
    alpha: float
    results: pd.DataFrame

    @property
    def adjusted_p_values(self) -> pd.Series:
        """Return Benjamini-Hochberg adjusted p-values."""

        return self.results["adjusted_p_value"]

    @property
    def rejected(self) -> pd.Series:
        """Return whether each null hypothesis is rejected after correction."""

        return self.results["significant"]


@dataclass(slots=True)
class BinaryAssociationResult:
    """
    Epidemiological association measures for a 2x2 event table.
    """

    synthea_events: int
    synthea_total: int
    psynthea_events: int
    psynthea_total: int

    risk_ratio: float | None
    risk_ratio_ci: ConfidenceInterval | None
    odds_ratio: float | None
    odds_ratio_ci: ConfidenceInterval | None
    absolute_risk_difference: float | None
    relative_risk_difference: float | None


# =============================================================================
# Cleaning helpers
# =============================================================================

def _clean_numeric_values(
    values: Iterable[Any],
) -> np.ndarray:
    """
    Return a finite numeric numpy array.
    """

    series = pd.to_numeric(
        pd.Series(values),
        errors="coerce",
    )

    array = series.dropna().to_numpy(dtype=float)

    return array[np.isfinite(array)]


def _clean_counts(
    counts: Iterable[Any],
) -> np.ndarray:
    """
    Return a non-negative finite numeric array for count vectors.
    """

    array = _clean_numeric_values(counts)

    return np.where(
        array < 0,
        0.0,
        array,
    )


def _safe_divide(
    numerator: float,
    denominator: float,
) -> float | None:
    """
    Divide two values while protecting against zero denominators.
    """

    if denominator == 0:
        return None

    result = numerator / denominator

    if not isfinite(result):
        return None

    return result


def _is_valid_probability(
    value: float,
) -> bool:
    """
    Return True when a value is a valid probability.
    """

    return 0.0 <= value <= 1.0


def _z_value(
    confidence_level: float,
) -> float:
    """
    Return the standard-normal critical value for a confidence level.
    """

    alpha = 1.0 - confidence_level

    return float(stats.norm.ppf(1.0 - alpha / 2.0))


def _p_value_significant(
    p_value: float | None,
    alpha: float,
) -> bool | None:
    """
    Return whether a p-value is significant at a given alpha.
    """

    if p_value is None or pd.isna(p_value):
        return None

    return bool(p_value < alpha)


def _empty_result(
    test_name: str,
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
    interpretation: str | None = None,
) -> StatisticalTestResult:
    """
    Return a stable empty statistical result.
    """

    return StatisticalTestResult(
        test_name=test_name,
        statistic=None,
        p_value=None,
        alpha=alpha,
        significant=None,
        interpretation=interpretation or "insufficient_data",
    )


# =============================================================================
# Confidence intervals
# =============================================================================

def confidence_interval_mean(
    values: Iterable[Any],
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> ConfidenceInterval:
    """
    Return a t-based confidence interval for a sample mean.
    """

    sample = _clean_numeric_values(values)
    n = len(sample)

    if n == 0:
        return ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=confidence_level,
        )

    mean = float(np.mean(sample))

    if n == 1:
        return ConfidenceInterval(
            lower=mean,
            upper=mean,
            confidence_level=confidence_level,
        )

    standard_error = float(stats.sem(sample))
    critical_value = float(stats.t.ppf(
        (1.0 + confidence_level) / 2.0,
        df=n - 1,
    ))
    margin = critical_value * standard_error

    return ConfidenceInterval(
        lower=mean - margin,
        upper=mean + margin,
        confidence_level=confidence_level,
    )


def confidence_interval_proportion(
    events: int,
    total: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> ConfidenceInterval:
    """
    Return a Wilson confidence interval for a single proportion.
    """

    if total <= 0 or events < 0 or events > total:
        return ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=confidence_level,
        )

    z = _z_value(confidence_level)
    p_hat = events / total
    denominator = 1.0 + (z ** 2) / total
    centre = p_hat + (z ** 2) / (2.0 * total)
    margin = z * sqrt(
        (p_hat * (1.0 - p_hat) / total)
        + ((z ** 2) / (4.0 * total ** 2))
    )

    return ConfidenceInterval(
        lower=max(0.0, (centre - margin) / denominator),
        upper=min(1.0, (centre + margin) / denominator),
        confidence_level=confidence_level,
    )


def confidence_interval_difference_proportions(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> ConfidenceInterval:
    """
    Return a Wald confidence interval for two-proportion difference.
    """

    if synthea_total <= 0 or psynthea_total <= 0:
        return ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=confidence_level,
        )

    p_synthea = synthea_events / synthea_total
    p_psynthea = psynthea_events / psynthea_total
    difference = p_psynthea - p_synthea
    standard_error = sqrt(
        (p_synthea * (1.0 - p_synthea) / synthea_total)
        + (p_psynthea * (1.0 - p_psynthea) / psynthea_total)
    )
    margin = _z_value(confidence_level) * standard_error

    return ConfidenceInterval(
        lower=difference - margin,
        upper=difference + margin,
        confidence_level=confidence_level,
    )


# =============================================================================
# Continuous effect sizes
# =============================================================================

def cohen_d(
    synthea_values: Iterable[Any],
    psynthea_values: Iterable[Any],
) -> float | None:
    """
    Return Cohen's d for the difference between two means.
    """

    synthea = _clean_numeric_values(synthea_values)
    psynthea = _clean_numeric_values(psynthea_values)

    n_synthea = len(synthea)
    n_psynthea = len(psynthea)

    if n_synthea < 2 or n_psynthea < 2:
        return None

    pooled_variance = (
        ((n_synthea - 1) * np.var(synthea, ddof=1))
        + ((n_psynthea - 1) * np.var(psynthea, ddof=1))
    ) / (n_synthea + n_psynthea - 2)

    if pooled_variance <= 0:
        return None

    return float((np.mean(psynthea) - np.mean(synthea)) / sqrt(pooled_variance))


def standardized_mean_difference(
    synthea_values: Iterable[Any],
    psynthea_values: Iterable[Any],
) -> float | None:
    """
    Return the standardized mean difference between two cohorts.
    """

    return cohen_d(
        synthea_values,
        psynthea_values,
    )


# =============================================================================
# Continuous statistical tests
# =============================================================================

def kolmogorov_smirnov_test(
    synthea_values: Iterable[Any],
    psynthea_values: Iterable[Any],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> StatisticalTestResult:
    """
    Compare two complete continuous distributions with the KS test.
    """

    synthea = _clean_numeric_values(synthea_values)
    psynthea = _clean_numeric_values(psynthea_values)

    if len(synthea) == 0 or len(psynthea) == 0:
        return _empty_result(
            "kolmogorov_smirnov",
            alpha,
        )

    result = stats.ks_2samp(
        synthea,
        psynthea,
        alternative="two-sided",
        method="auto",
    )
    p_value = float(result.pvalue)

    return StatisticalTestResult(
        test_name="kolmogorov_smirnov",
        statistic=float(result.statistic),
        p_value=p_value,
        effect_size=float(result.statistic),
        effect_size_name="D",
        n_synthea=len(synthea),
        n_psynthea=len(psynthea),
        alpha=alpha,
        significant=_p_value_significant(p_value, alpha),
    )


def mann_whitney_u_test(
    synthea_values: Iterable[Any],
    psynthea_values: Iterable[Any],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> StatisticalTestResult:
    """
    Compare two continuous samples without assuming normality.
    """

    synthea = _clean_numeric_values(synthea_values)
    psynthea = _clean_numeric_values(psynthea_values)

    if len(synthea) == 0 or len(psynthea) == 0:
        return _empty_result(
            "mann_whitney_u",
            alpha,
        )

    result = stats.mannwhitneyu(
        synthea,
        psynthea,
        alternative="two-sided",
        method="auto",
    )
    p_value = float(result.pvalue)

    rank_biserial = 1.0 - (2.0 * float(result.statistic)) / (len(synthea) * len(psynthea))

    return StatisticalTestResult(
        test_name="mann_whitney_u",
        statistic=float(result.statistic),
        p_value=p_value,
        effect_size=float(rank_biserial),
        effect_size_name="rank_biserial_correlation",
        n_synthea=len(synthea),
        n_psynthea=len(psynthea),
        alpha=alpha,
        significant=_p_value_significant(p_value, alpha),
    )


def welch_t_test(
    synthea_values: Iterable[Any],
    psynthea_values: Iterable[Any],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> StatisticalTestResult:
    """
    Compare two means allowing unequal variances.
    """

    synthea = _clean_numeric_values(synthea_values)
    psynthea = _clean_numeric_values(psynthea_values)

    if len(synthea) < 2 or len(psynthea) < 2:
        return _empty_result(
            "welch_t_test",
            alpha,
        )

    result = stats.ttest_ind(
        psynthea,
        synthea,
        equal_var=False,
        nan_policy="omit",
    )
    p_value = float(result.pvalue)

    mean_difference = float(np.mean(psynthea) - np.mean(synthea))
    standard_error = sqrt(
        np.var(psynthea, ddof=1) / len(psynthea)
        + np.var(synthea, ddof=1) / len(synthea)
    )

    numerator = standard_error ** 4
    denominator = (
        ((np.var(psynthea, ddof=1) / len(psynthea)) ** 2) / (len(psynthea) - 1)
        + ((np.var(synthea, ddof=1) / len(synthea)) ** 2) / (len(synthea) - 1)
    )

    if denominator == 0:
        confidence_interval = ConfidenceInterval(
            lower=mean_difference,
            upper=mean_difference,
            confidence_level=confidence_level,
        )
    else:
        degrees_freedom = numerator / denominator
        critical_value = float(stats.t.ppf(
            (1.0 + confidence_level) / 2.0,
            df=degrees_freedom,
        ))
        margin = critical_value * standard_error
        confidence_interval = ConfidenceInterval(
            lower=mean_difference - margin,
            upper=mean_difference + margin,
            confidence_level=confidence_level,
        )

    return StatisticalTestResult(
        test_name="welch_t_test",
        statistic=float(result.statistic),
        p_value=p_value,
        effect_size=cohen_d(
            synthea,
            psynthea,
        ),
        effect_size_name="cohen_d",
        confidence_interval=confidence_interval,
        n_synthea=len(synthea),
        n_psynthea=len(psynthea),
        alpha=alpha,
        significant=_p_value_significant(p_value, alpha),
    )


def continuous_distribution_tests(
    synthea_values: Iterable[Any],
    psynthea_values: Iterable[Any],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> pd.DataFrame:
    """
    Return the standard continuous-variable test battery.
    """

    results = [
        kolmogorov_smirnov_test(
            synthea_values,
            psynthea_values,
            alpha,
        ),
        mann_whitney_u_test(
            synthea_values,
            psynthea_values,
            alpha,
        ),
        welch_t_test(
            synthea_values,
            psynthea_values,
            alpha,
        ),
    ]

    return statistical_results_to_dataframe(results)


# =============================================================================
# Categorical effect sizes and distribution tests
# =============================================================================

def cramers_v(
    contingency_table: pd.DataFrame | np.ndarray | list[list[int]],
) -> float | None:
    """
    Return Cramer's V for a contingency table.
    """

    table = np.asarray(
        contingency_table,
        dtype=float,
    )

    if table.ndim != 2 or table.size == 0:
        return None

    n = float(table.sum())
    rows, columns = table.shape

    if n == 0 or min(rows, columns) <= 1:
        return None

    chi2 = float(stats.chi2_contingency(table, correction=False).statistic)

    return float(sqrt(chi2 / (n * (min(rows, columns) - 1))))


def chi_square_test(
    contingency_table: pd.DataFrame | np.ndarray | list[list[int]],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> StatisticalTestResult:
    """
    Compare categorical distributions with Pearson's chi-square test.
    """

    table = np.asarray(
        contingency_table,
        dtype=float,
    )

    if table.ndim != 2 or table.size == 0 or table.sum() == 0:
        return _empty_result(
            "chi_square",
            alpha,
        )

    if table.shape[0] < 2 or table.shape[1] < 2:
        return _empty_result(
            "chi_square",
            alpha,
            "requires_at_least_2x2_table",
        )

    result = stats.chi2_contingency(
        table,
        correction=False,
    )
    p_value = float(result.pvalue)

    return StatisticalTestResult(
        test_name="chi_square",
        statistic=float(result.statistic),
        p_value=p_value,
        effect_size=cramers_v(table),
        effect_size_name="cramers_v",
        n_synthea=int(table[0].sum()) if table.shape[0] >= 1 else None,
        n_psynthea=int(table[1].sum()) if table.shape[0] >= 2 else None,
        alpha=alpha,
        significant=_p_value_significant(p_value, alpha),
    )


def fisher_exact_test(
    table_2x2: pd.DataFrame | np.ndarray | list[list[int]],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> StatisticalTestResult:
    """
    Compare a 2x2 categorical table with Fisher's exact test.
    """

    table = np.asarray(
        table_2x2,
        dtype=float,
    )

    if table.shape != (2, 2) or table.sum() == 0:
        return _empty_result(
            "fisher_exact",
            alpha,
            "requires_2x2_table",
        )

    statistic, p_value = stats.fisher_exact(
        table,
        alternative="two-sided",
    )

    return StatisticalTestResult(
        test_name="fisher_exact",
        statistic=float(statistic),
        p_value=float(p_value),
        effect_size=float(statistic) if isfinite(float(statistic)) else None,
        effect_size_name="odds_ratio",
        n_synthea=int(table[0].sum()),
        n_psynthea=int(table[1].sum()),
        alpha=alpha,
        significant=_p_value_significant(float(p_value), alpha),
    )


def jensen_shannon_divergence(
    synthea_counts: Iterable[Any],
    psynthea_counts: Iterable[Any],
) -> float | None:
    """
    Compare two full count distributions with Jensen-Shannon divergence.
    """

    synthea = _clean_counts(synthea_counts)
    psynthea = _clean_counts(psynthea_counts)

    if len(synthea) != len(psynthea) or len(synthea) == 0:
        return None

    if synthea.sum() == 0 or psynthea.sum() == 0:
        return None

    synthea_probabilities = synthea / synthea.sum()
    psynthea_probabilities = psynthea / psynthea.sum()

    distance = float(jensenshannon(
        synthea_probabilities,
        psynthea_probabilities,
        base=2.0,
    ))

    return distance ** 2


def categorical_distribution_tests(
    synthea_counts: Iterable[Any],
    psynthea_counts: Iterable[Any],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> pd.DataFrame:
    """
    Return the standard categorical-distribution test battery.
    """

    synthea = _clean_counts(synthea_counts)
    psynthea = _clean_counts(psynthea_counts)

    if len(synthea) != len(psynthea) or len(synthea) == 0:
        return statistical_results_to_dataframe([
            _empty_result(
                "chi_square",
                alpha,
                "count_vectors_must_have_same_length",
            )
        ])

    table = np.vstack([
        synthea,
        psynthea,
    ])

    chi_square = chi_square_test(
        table,
        alpha,
    )

    jsd = jensen_shannon_divergence(
        synthea,
        psynthea,
    )

    jsd_result = StatisticalTestResult(
        test_name="jensen_shannon_divergence",
        statistic=jsd,
        p_value=None,
        effect_size=jsd,
        effect_size_name="JSD",
        n_synthea=int(synthea.sum()),
        n_psynthea=int(psynthea.sum()),
        alpha=alpha,
        significant=None,
        interpretation="distance_metric_no_p_value",
    )

    return statistical_results_to_dataframe([
        chi_square,
        jsd_result,
    ])


# =============================================================================
# Binary proportions and epidemiological measures
# =============================================================================

def _validate_binary_counts(
    events: int,
    total: int,
) -> bool:
    """
    Return True when binary event counts are coherent.
    """

    return total >= 0 and 0 <= events <= total


def risk_ratio(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
) -> float | None:
    """
    Return the risk ratio for psynthea relative to Synthea Java.
    """

    if not (
        _validate_binary_counts(synthea_events, synthea_total)
        and _validate_binary_counts(psynthea_events, psynthea_total)
    ):
        return None

    synthea_risk = _safe_divide(
        synthea_events,
        synthea_total,
    )
    psynthea_risk = _safe_divide(
        psynthea_events,
        psynthea_total,
    )

    if synthea_risk in (None, 0.0) or psynthea_risk is None:
        return None

    return _safe_divide(
        psynthea_risk,
        synthea_risk,
    )


def odds_ratio(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    continuity_correction: float = 0.5,
) -> float | None:
    """
    Return the odds ratio for psynthea relative to Synthea Java.
    """

    if not (
        _validate_binary_counts(synthea_events, synthea_total)
        and _validate_binary_counts(psynthea_events, psynthea_total)
    ):
        return None

    a = float(psynthea_events)
    b = float(psynthea_total - psynthea_events)
    c = float(synthea_events)
    d = float(synthea_total - synthea_events)

    if min(a, b, c, d) == 0:
        a += continuity_correction
        b += continuity_correction
        c += continuity_correction
        d += continuity_correction

    return _safe_divide(
        a * d,
        b * c,
    )


def confidence_interval_risk_ratio(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    continuity_correction: float = 0.5,
) -> ConfidenceInterval:
    """
    Return a log-scale confidence interval for the risk ratio.
    """

    if not (
        _validate_binary_counts(synthea_events, synthea_total)
        and _validate_binary_counts(psynthea_events, psynthea_total)
    ):
        return ConfidenceInterval(None, None, confidence_level)

    if synthea_total == 0 or psynthea_total == 0:
        return ConfidenceInterval(None, None, confidence_level)

    a = float(psynthea_events)
    n1 = float(psynthea_total)
    c = float(synthea_events)
    n0 = float(synthea_total)

    if a == 0 or c == 0:
        a += continuity_correction
        c += continuity_correction
        n1 += continuity_correction
        n0 += continuity_correction

    rr = _safe_divide(
        a / n1,
        c / n0,
    )

    if rr is None or rr <= 0:
        return ConfidenceInterval(None, None, confidence_level)

    variance = (
        (1.0 / a)
        - (1.0 / n1)
        + (1.0 / c)
        - (1.0 / n0)
    )

    # With coherent binary counts the log-risk-ratio variance is
    # mathematically non-negative. Clamp only floating-point underflow so a
    # value such as -1e-16 cannot abort the complete validation pipeline.
    standard_error = sqrt(max(0.0, variance))
    margin = _z_value(confidence_level) * standard_error

    return ConfidenceInterval(
        lower=exp(log(rr) - margin),
        upper=exp(log(rr) + margin),
        confidence_level=confidence_level,
    )


def confidence_interval_odds_ratio(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    continuity_correction: float = 0.5,
) -> ConfidenceInterval:
    """
    Return a log-scale confidence interval for the odds ratio.
    """

    a = float(psynthea_events)
    b = float(psynthea_total - psynthea_events)
    c = float(synthea_events)
    d = float(synthea_total - synthea_events)

    if min(a, b, c, d) < 0:
        return ConfidenceInterval(None, None, confidence_level)

    if min(a, b, c, d) == 0:
        a += continuity_correction
        b += continuity_correction
        c += continuity_correction
        d += continuity_correction

    odds = _safe_divide(
        a * d,
        b * c,
    )

    if odds is None or odds <= 0:
        return ConfidenceInterval(None, None, confidence_level)

    standard_error = sqrt(
        (1.0 / a)
        + (1.0 / b)
        + (1.0 / c)
        + (1.0 / d)
    )
    margin = _z_value(confidence_level) * standard_error

    return ConfidenceInterval(
        lower=exp(log(odds) - margin),
        upper=exp(log(odds) + margin),
        confidence_level=confidence_level,
    )


def binary_association_measures(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> BinaryAssociationResult:
    """
    Return risk ratio, odds ratio and risk differences for a binary event.
    """

    if not (
        _validate_binary_counts(synthea_events, synthea_total)
        and _validate_binary_counts(psynthea_events, psynthea_total)
    ):
        return BinaryAssociationResult(
            synthea_events=synthea_events,
            synthea_total=synthea_total,
            psynthea_events=psynthea_events,
            psynthea_total=psynthea_total,
            risk_ratio=None,
            risk_ratio_ci=None,
            odds_ratio=None,
            odds_ratio_ci=None,
            absolute_risk_difference=None,
            relative_risk_difference=None,
        )

    p_synthea = _safe_divide(
        synthea_events,
        synthea_total,
    )
    p_psynthea = _safe_divide(
        psynthea_events,
        psynthea_total,
    )

    absolute_difference = None
    relative_difference = None

    if p_synthea is not None and p_psynthea is not None:
        absolute_difference = p_psynthea - p_synthea
        relative_difference = _safe_divide(
            absolute_difference,
            p_synthea,
        )

    return BinaryAssociationResult(
        synthea_events=synthea_events,
        synthea_total=synthea_total,
        psynthea_events=psynthea_events,
        psynthea_total=psynthea_total,
        risk_ratio=risk_ratio(
            synthea_events,
            synthea_total,
            psynthea_events,
            psynthea_total,
        ),
        risk_ratio_ci=confidence_interval_risk_ratio(
            synthea_events,
            synthea_total,
            psynthea_events,
            psynthea_total,
            confidence_level,
        ),
        odds_ratio=odds_ratio(
            synthea_events,
            synthea_total,
            psynthea_events,
            psynthea_total,
        ),
        odds_ratio_ci=confidence_interval_odds_ratio(
            synthea_events,
            synthea_total,
            psynthea_events,
            psynthea_total,
            confidence_level,
        ),
        absolute_risk_difference=absolute_difference,
        relative_risk_difference=relative_difference,
    )


def proportion_z_test(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> StatisticalTestResult:
    """
    Compare two independent proportions with a pooled z-test.
    """

    if not (
        _validate_binary_counts(synthea_events, synthea_total)
        and _validate_binary_counts(psynthea_events, psynthea_total)
    ):
        return _empty_result(
            "proportion_z_test",
            alpha,
            "invalid_binary_counts",
        )

    if synthea_total == 0 or psynthea_total == 0:
        return _empty_result(
            "proportion_z_test",
            alpha,
        )

    pooled = (synthea_events + psynthea_events) / (synthea_total + psynthea_total)
    standard_error = sqrt(
        pooled
        * (1.0 - pooled)
        * ((1.0 / synthea_total) + (1.0 / psynthea_total))
    )

    if standard_error == 0:
        return _empty_result(
            "proportion_z_test",
            alpha,
            "zero_standard_error",
        )

    p_synthea = synthea_events / synthea_total
    p_psynthea = psynthea_events / psynthea_total
    statistic = (p_psynthea - p_synthea) / standard_error
    p_value = float(2.0 * stats.norm.sf(abs(statistic)))

    return StatisticalTestResult(
        test_name="proportion_z_test",
        statistic=float(statistic),
        p_value=p_value,
        effect_size=p_psynthea - p_synthea,
        effect_size_name="risk_difference",
        confidence_interval=confidence_interval_difference_proportions(
            synthea_events,
            synthea_total,
            psynthea_events,
            psynthea_total,
            confidence_level,
        ),
        n_synthea=synthea_total,
        n_psynthea=psynthea_total,
        alpha=alpha,
        significant=_p_value_significant(p_value, alpha),
    )


def binary_event_tests(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> pd.DataFrame:
    """
    Return the standard binary-event statistical test battery.
    """

    table = np.array([
        [
            synthea_events,
            synthea_total - synthea_events,
        ],
        [
            psynthea_events,
            psynthea_total - psynthea_events,
        ],
    ])

    results = [
        proportion_z_test(
            synthea_events,
            synthea_total,
            psynthea_events,
            psynthea_total,
            alpha,
        ),
        chi_square_test(
            table,
            alpha,
        ),
        fisher_exact_test(
            table,
            alpha,
        ),
    ]

    return statistical_results_to_dataframe(results)


# =============================================================================
# Multiple-testing correction
# =============================================================================

def benjamini_hochberg(
    p_values: Iterable[Any],
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> MultipleTestingCorrectionResult:
    """
    Apply Benjamini-Hochberg false-discovery-rate correction.
    """

    series = pd.to_numeric(
        pd.Series(list(p_values)),
        errors="coerce",
    )

    result = pd.DataFrame({
        "p_value": series,
    })
    result["rank"] = pd.NA
    result["adjusted_p_value"] = pd.NA
    result["significant"] = False

    valid = result["p_value"].dropna()
    valid = valid[
        (valid >= 0.0)
        & (valid <= 1.0)
    ]

    m = len(valid)

    if m == 0:
        return MultipleTestingCorrectionResult(
            method="benjamini_hochberg",
            alpha=alpha,
            results=result,
        )

    ordered = valid.sort_values()
    ranks = pd.Series(
        np.arange(1, m + 1),
        index=ordered.index,
        dtype=float,
    )

    adjusted = ordered * m / ranks
    adjusted = adjusted.sort_index()
    ordered_adjusted = adjusted.loc[ordered.index]
    monotonic = ordered_adjusted.iloc[::-1].cummin().iloc[::-1].clip(upper=1.0)

    result.loc[ordered.index, "rank"] = ranks.loc[ordered.index]
    result.loc[monotonic.index, "adjusted_p_value"] = monotonic
    result.loc[monotonic.index, "significant"] = monotonic < alpha

    return MultipleTestingCorrectionResult(
        method="benjamini_hochberg",
        alpha=alpha,
        results=result,
    )


# =============================================================================
# DataFrame serialization
# =============================================================================

def _confidence_interval_to_dict(
    confidence_interval: ConfidenceInterval | None,
) -> dict[str, float | None]:
    """
    Serialize a confidence interval into flat DataFrame columns.
    """

    if confidence_interval is None:
        return {
            "ci_lower": None,
            "ci_upper": None,
            "confidence_level": None,
        }

    return {
        "ci_lower": confidence_interval.lower,
        "ci_upper": confidence_interval.upper,
        "confidence_level": confidence_interval.confidence_level,
    }


def statistical_results_to_dataframe(
    results: Iterable[StatisticalTestResult],
) -> pd.DataFrame:
    """
    Convert statistical results into a stable tabular schema.
    """

    rows: list[dict[str, Any]] = []

    for result in results:
        row = asdict(result)
        row.pop(
            "confidence_interval",
            None,
        )
        row.update(_confidence_interval_to_dict(result.confidence_interval))
        rows.append(row)

    return pd.DataFrame(
        rows,
        columns=[
            "test_name",
            "statistic",
            "p_value",
            "effect_size",
            "effect_size_name",
            "ci_lower",
            "ci_upper",
            "confidence_level",
            "n_synthea",
            "n_psynthea",
            "alpha",
            "significant",
            "interpretation",
        ],
    )


def binary_association(
    synthea_events: int,
    synthea_total: int,
    psynthea_events: int,
    psynthea_total: int,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> BinaryAssociationResult:
    """
    Return binary epidemiological association measures.

    This is the public alias used by the comparison layer. It delegates to
    ``binary_association_measures`` to keep the implementation centralized.
    """

    return binary_association_measures(
        synthea_events=synthea_events,
        synthea_total=synthea_total,
        psynthea_events=psynthea_events,
        psynthea_total=psynthea_total,
        confidence_level=confidence_level,
    )


def binary_association_to_dataframe(
    result: BinaryAssociationResult,
) -> pd.DataFrame:
    """
    Convert binary epidemiological measures into a stable one-row table.
    """

    return pd.DataFrame([
        {
            "synthea_events": result.synthea_events,
            "synthea_total": result.synthea_total,
            "psynthea_events": result.psynthea_events,
            "psynthea_total": result.psynthea_total,
            "risk_ratio": result.risk_ratio,
            "risk_ratio_ci_lower": (
                None if result.risk_ratio_ci is None else result.risk_ratio_ci.lower
            ),
            "risk_ratio_ci_upper": (
                None if result.risk_ratio_ci is None else result.risk_ratio_ci.upper
            ),
            "odds_ratio": result.odds_ratio,
            "odds_ratio_ci_lower": (
                None if result.odds_ratio_ci is None else result.odds_ratio_ci.lower
            ),
            "odds_ratio_ci_upper": (
                None if result.odds_ratio_ci is None else result.odds_ratio_ci.upper
            ),
            "absolute_risk_difference": result.absolute_risk_difference,
            "relative_risk_difference": result.relative_risk_difference,
        }
    ])


__all__ = [
    "BinaryAssociationResult",
    "ConfidenceInterval",
    "MultipleTestingCorrectionResult",
    "StatisticalTestResult",
    "benjamini_hochberg",
    "binary_association",
    "binary_association_measures",
    "binary_association_to_dataframe",
    "binary_event_tests",
    "categorical_distribution_tests",
    "chi_square_test",
    "cohen_d",
    "confidence_interval_difference_proportions",
    "confidence_interval_mean",
    "confidence_interval_odds_ratio",
    "confidence_interval_proportion",
    "confidence_interval_risk_ratio",
    "continuous_distribution_tests",
    "cramers_v",
    "fisher_exact_test",
    "jensen_shannon_divergence",
    "kolmogorov_smirnov_test",
    "mann_whitney_u_test",
    "odds_ratio",
    "proportion_z_test",
    "risk_ratio",
    "standardized_mean_difference",
    "statistical_results_to_dataframe",
    "welch_t_test",
]
