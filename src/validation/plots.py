"""
Publication-oriented plotting layer for validation results.

This module converts already-computed statistical comparison outputs into
reproducible matplotlib figures suitable for scientific review and reporting.

It intentionally does not compute metrics, run statistical tests, load cohort
files, write narrative reports or execute simulators. Statistical estimates,
p-values, confidence intervals and multiplicity corrections must be produced by
the comparison layer before reaching this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.constants import (
    DEFAULT_DPI,
    DEFAULT_FIGURE_FORMAT,
    DEFAULT_SIGNIFICANCE_LEVEL,
)

__all__ = [
    "NoPlottableDataError",
    "PlotConfig",
    "ModuleFigures",
    "ValidationFigures",
    "plot_prevalence_comparison",
    "plot_prevalence_differences",
    "plot_prevalence_equivalence",
    "plot_prevalence_risk_ratio_forest",
    "plot_continuous_effect_sizes",
    "plot_categorical_effect_sizes",
    "plot_nominal_p_values",
    "plot_fdr_adjusted_prevalence_p_values",
    "plot_jensen_shannon_divergence",
    "plot_module_validation_summary",
    "plot_validation_status_overview",
    "plot_divergence_heatmap",
    "build_module_figures",
    "build_validation_figures",
    "save_module_figures",
    "save_validation_figures",
]


# =============================================================================
# Configuration
# =============================================================================

_DEFAULT_FIGSIZE = (10.0, 6.0)
_WIDE_FIGSIZE = (12.0, 7.0)
_TALL_FIGSIZE = (12.0, 8.0)

_SOURCE_LABELS: Mapping[str, str] = {
    "synthea_prevalence": "Synthea",
    "psynthea_prevalence": "psynthea",
}

_SCOPE_LABELS: Mapping[str, str] = {
    "continuous": "Continuous",
    "categorical": "Categorical",
    "prevalence": "Prevalence",
    "code_distribution": "Code distribution",
}

_DECISION_ORDER = ("pass", "warning", "fail", "skipped")
_DECISION_LABELS = {
    "pass": "Pass",
    "warning": "Warning",
    "fail": "Fail",
    "skipped": "Skipped",
}

# Okabe-Ito colour-blind-safe palette. Markers, hatching and annotations are
# also used so interpretation never depends on colour alone.
_COLOUR_SYNTHEA = "#0072B2"
_COLOUR_PSYNTHEA = "#D55E00"
_COLOUR_NEUTRAL = "#7A7A7A"
_COLOUR_POSITIVE = "#009E73"
_COLOUR_NEGATIVE = "#CC79A7"
_COLOUR_SIGNIFICANT = "#D55E00"
_COLOUR_NON_SIGNIFICANT = "#999999"
_COLOUR_EQUIVALENCE = "#E6F4EA"
_COLOUR_GRID = "#D9D9D9"


class NoPlottableDataError(ValueError):
    """Raised when a requested figure has no valid rows to display."""


@dataclass(frozen=True, slots=True)
class PlotConfig:
    """Shared scientific and presentation configuration for generated figures."""

    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL
    top_n_prevalence: int = 15
    top_n_effect_sizes: int = 20
    top_n_p_values: int = 25
    prevalence_rank_by: Literal[
        "prevalence", "absolute_difference", "clinical_priority"
    ] = "absolute_difference"
    prevalence_equivalence_margin: float | None = None
    continuous_effect_margin: float | None = 0.20
    categorical_effect_margin: float | None = 0.10
    clinical_priority: tuple[str, ...] = ()
    annotate_values: bool = True

    def __post_init__(self) -> None:
        _require_probability(self.alpha, "alpha")
        _require_positive(self.top_n_prevalence, "top_n_prevalence")
        _require_positive(self.top_n_effect_sizes, "top_n_effect_sizes")
        _require_positive(self.top_n_p_values, "top_n_p_values")
        _require_optional_non_negative(
            self.prevalence_equivalence_margin,
            "prevalence_equivalence_margin",
        )
        _require_optional_non_negative(
            self.continuous_effect_margin,
            "continuous_effect_margin",
        )
        _require_optional_non_negative(
            self.categorical_effect_margin,
            "categorical_effect_margin",
        )


@dataclass(slots=True)
class ModuleFigures:
    """Named figures generated for one module comparison."""

    module_name: str
    figures: dict[str, Figure] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationFigures:
    """Named figures generated across a complete validation run."""

    figures: dict[str, Figure] = field(default_factory=dict)


# =============================================================================
# Module-level plots
# =============================================================================


def plot_prevalence_comparison(
    prevalence_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    top_n: int = 15,
    rank_by: Literal[
        "prevalence", "absolute_difference", "clinical_priority"
    ] = "absolute_difference",
    clinical_priority: Sequence[str] = (),
    annotate_values: bool = True,
) -> Figure:
    """Plot paired prevalence estimates as a dumbbell chart.

    The dumbbell design displays the absolute prevalence level and the distance
    between simulators more efficiently than grouped bars. Selection can be
    driven by prevalence, absolute difference or an externally defined clinical
    priority list.
    """

    _require_positive(top_n, "top_n")
    frame = _select_prevalence_rows(
        _prepare_prevalence_frame(prevalence_tests),
        top_n=top_n,
        rank_by=rank_by,
        clinical_priority=clinical_priority,
    ).sort_values("_ranking", ascending=True)

    with _plot_context():
        figure, axis = plt.subplots(figsize=_WIDE_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(frame), dtype=float)
        synthea = frame["synthea_prevalence"].to_numpy(dtype=float) * 100
        psynthea = frame["psynthea_prevalence"].to_numpy(dtype=float) * 100

        for position, left, right in zip(positions, synthea, psynthea, strict=True):
            axis.plot(
                [left, right],
                [position, position],
                color=_COLOUR_NEUTRAL,
                linewidth=1.5,
                zorder=1,
            )

        axis.scatter(
            synthea,
            positions,
            color=_COLOUR_SYNTHEA,
            marker="o",
            label=_SOURCE_LABELS["synthea_prevalence"],
            zorder=2,
        )
        axis.scatter(
            psynthea,
            positions,
            facecolors="none",
            edgecolors=_COLOUR_PSYNTHEA,
            marker="s",
            linewidths=1.8,
            label=_SOURCE_LABELS["psynthea_prevalence"],
            zorder=3,
        )

        axis.set_yticks(positions, frame["label"])
        axis.set_xlabel("Patient prevalence (%)")
        axis.set_ylabel("Clinical code")
        axis.set_title(_title("Prevalence comparison", module_name))
        axis.legend(frameon=False)
        _style_axis(axis, grid_axis="x")

        if annotate_values:
            for position, left, right in zip(positions, synthea, psynthea, strict=True):
                axis.annotate(
                    f"{left:.1f}",
                    (left, position),
                    xytext=(-5, 6),
                    textcoords="offset points",
                    ha="right",
                    fontsize="x-small",
                )
                axis.annotate(
                    f"{right:.1f}",
                    (right, position),
                    xytext=(5, 6),
                    textcoords="offset points",
                    ha="left",
                    fontsize="x-small",
                )

    return figure


def plot_prevalence_differences(
    prevalence_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    top_n: int = 15,
    annotate_values: bool = True,
) -> Figure:
    """Plot the largest signed prevalence differences in percentage points."""

    _require_positive(top_n, "top_n")
    frame = _prepare_prevalence_frame(prevalence_tests)
    frame = (
        frame.assign(_ranking=frame["absolute_difference"].abs())
        .sort_values("_ranking", ascending=False)
        .head(top_n)
        .sort_values("absolute_difference", ascending=True)
    )

    values = frame["absolute_difference"].to_numpy(dtype=float) * 100
    significant = frame["significant_after_fdr"].to_numpy(dtype=bool)
    colours = [
        _COLOUR_SIGNIFICANT
        if is_significant
        else (_COLOUR_POSITIVE if value >= 0 else _COLOUR_NEGATIVE)
        for value, is_significant in zip(values, significant, strict=True)
    ]

    with _plot_context():
        figure, axis = plt.subplots(figsize=_WIDE_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(frame), dtype=float)
        bars = axis.barh(positions, values, color=colours)

        for bar, is_significant in zip(bars, significant, strict=True):
            if is_significant:
                bar.set_hatch("///")

        axis.axvline(0.0, color="black", linewidth=1.0)
        axis.set_yticks(positions, frame["label"])
        axis.set_xlabel("psynthea − Synthea (percentage points)")
        axis.set_ylabel("Clinical code")
        axis.set_title(_title("Largest prevalence differences", module_name))
        _style_axis(axis, grid_axis="x")

        if annotate_values:
            for position, value, is_significant in zip(
                positions,
                values,
                significant,
                strict=True,
            ):
                suffix = " *" if is_significant else ""
                _annotate_horizontal_value(axis, position, value, f"{value:+.2f}{suffix}")

        axis.text(
            0.99,
            0.01,
            "* FDR-significant; positive values indicate higher prevalence in psynthea",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize="x-small",
        )

    return figure


def plot_prevalence_equivalence(
    prevalence_tests: pd.DataFrame,
    *,
    equivalence_margin: float,
    module_name: str | None = None,
    top_n: int = 20,
    annotate_values: bool = True,
) -> Figure:
    """Plot prevalence differences against a pre-specified equivalence margin.

    ``equivalence_margin`` is expressed as a proportion (for example, ``0.02``
    for ±2 percentage points). This chart classifies point estimates only; it
    does not claim formal equivalence because the current comparison result does
    not expose confidence intervals for prevalence differences.
    """

    _require_positive(top_n, "top_n")
    _require_non_negative(equivalence_margin, "equivalence_margin")
    frame = _prepare_prevalence_frame(prevalence_tests)
    frame = (
        frame.assign(_ranking=frame["absolute_difference"].abs())
        .sort_values("_ranking", ascending=False)
        .head(top_n)
        .sort_values("absolute_difference", ascending=True)
    )

    values = frame["absolute_difference"].to_numpy(dtype=float) * 100
    margin = equivalence_margin * 100
    within = np.abs(values) <= margin

    with _plot_context():
        figure, axis = plt.subplots(figsize=_WIDE_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(frame), dtype=float)
        axis.axvspan(
            -margin,
            margin,
            color=_COLOUR_EQUIVALENCE,
            label=f"Point-estimate margin ±{margin:g} pp",
            zorder=0,
        )
        axis.axvline(0.0, color="black", linewidth=1.0, zorder=1)
        axis.scatter(
            values[within],
            positions[within],
            color=_COLOUR_POSITIVE,
            marker="o",
            label="Within margin",
            zorder=3,
        )
        axis.scatter(
            values[~within],
            positions[~within],
            facecolors="none",
            edgecolors=_COLOUR_SIGNIFICANT,
            marker="s",
            linewidths=1.8,
            label="Outside margin",
            zorder=3,
        )
        axis.set_yticks(positions, frame["label"])
        axis.set_xlabel("psynthea − Synthea (percentage points)")
        axis.set_ylabel("Clinical code")
        axis.set_title(_title("Prevalence equivalence screening", module_name))
        axis.legend(frameon=False)
        _style_axis(axis, grid_axis="x")

        if annotate_values:
            for position, value in zip(positions, values, strict=True):
                _annotate_horizontal_value(axis, position, value, f"{value:+.2f}")

        axis.text(
            0.99,
            0.01,
            "Point-estimate screening only; formal equivalence requires confidence intervals",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize="x-small",
        )

    return figure


def plot_prevalence_risk_ratio_forest(
    prevalence_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    top_n: int = 20,
    annotate_values: bool = True,
) -> Figure:
    """Plot prevalence risk ratios and their available confidence intervals."""

    _require_positive(top_n, "top_n")
    frame = _validated_numeric_frame(
        prevalence_tests,
        required_columns={
            "domain",
            "code",
            "risk_ratio",
            "risk_ratio_ci_lower",
            "risk_ratio_ci_upper",
            "significant_after_fdr",
        },
        numeric_columns=[
            "risk_ratio",
            "risk_ratio_ci_lower",
            "risk_ratio_ci_upper",
        ],
        context="prevalence risk-ratio",
    )
    frame = frame[
        (frame["risk_ratio"] > 0)
        & (frame["risk_ratio_ci_lower"] > 0)
        & (frame["risk_ratio_ci_upper"] > 0)
    ].copy()
    if frame.empty:
        raise NoPlottableDataError("No usable prevalence risk-ratio data available.")

    frame["label"] = frame["domain"].astype(str) + ":" + frame["code"].astype(str)
    frame["_ranking"] = np.abs(np.log(frame["risk_ratio"]))
    frame = (
        frame.sort_values("_ranking", ascending=False)
        .head(top_n)
        .sort_values("risk_ratio", ascending=True)
    )

    estimates = frame["risk_ratio"].to_numpy(dtype=float)
    lower = frame["risk_ratio_ci_lower"].to_numpy(dtype=float)
    upper = frame["risk_ratio_ci_upper"].to_numpy(dtype=float)
    errors = np.vstack([estimates - lower, upper - estimates])
    significant = frame["significant_after_fdr"].fillna(False).to_numpy(dtype=bool)

    with _plot_context():
        figure, axis = plt.subplots(figsize=_TALL_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(frame), dtype=float)

        for position, estimate, error, is_significant in zip(
            positions,
            estimates,
            errors.T,
            significant,
            strict=True,
        ):
            marker = "s" if is_significant else "o"
            colour = _COLOUR_SIGNIFICANT if is_significant else _COLOUR_NEUTRAL
            axis.errorbar(
                estimate,
                position,
                xerr=np.asarray(error).reshape(2, 1),
                fmt=marker,
                color=colour,
                ecolor=colour,
                capsize=3,
                markerfacecolor="none" if not is_significant else colour,
                zorder=3,
            )

        axis.axvline(1.0, color="black", linewidth=1.0)
        axis.set_xscale("log")
        axis.set_yticks(positions, frame["label"])
        axis.set_xlabel("Risk ratio, psynthea / Synthea (95% CI)")
        axis.set_ylabel("Clinical code")
        axis.set_title(_title("Prevalence risk-ratio forest plot", module_name))
        _style_axis(axis, grid_axis="x")

        if annotate_values:
            for position, estimate, low, high in zip(
                positions,
                estimates,
                lower,
                upper,
                strict=True,
            ):
                axis.annotate(
                    f"{estimate:.2f} [{low:.2f}, {high:.2f}]",
                    (high, position),
                    xytext=(5, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize="x-small",
                )

        axis.text(
            0.99,
            0.01,
            "Square markers indicate FDR-significant prevalence comparisons",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize="x-small",
        )

    return figure


def plot_continuous_effect_sizes(
    continuous_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    top_n: int = 20,
    practical_margin: float | None = 0.20,
    annotate_values: bool = True,
) -> Figure:
    """Plot continuous-test effect sizes without mixing incompatible scales."""

    return _plot_effect_size_family(
        continuous_tests,
        label_column="metric",
        family_name="Continuous",
        module_name=module_name,
        top_n=top_n,
        practical_margin=practical_margin,
        annotate_values=annotate_values,
    )


def plot_categorical_effect_sizes(
    categorical_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    top_n: int = 20,
    practical_margin: float | None = 0.10,
    annotate_values: bool = True,
) -> Figure:
    """Plot categorical-test effect sizes on their own interpretable scale."""

    return _plot_effect_size_family(
        categorical_tests,
        label_column="domain",
        family_name="Categorical",
        module_name=module_name,
        top_n=top_n,
        practical_margin=practical_margin,
        annotate_values=annotate_values,
    )


def plot_nominal_p_values(
    comparison: ModuleStatisticalComparisonResult,
    *,
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
    top_n: int = 25,
) -> Figure:
    """Plot nominal p-values for non-prevalence statistical tests."""

    _require_probability(alpha, "alpha")
    _require_positive(top_n, "top_n")
    frame = _nominal_p_value_frame(comparison)
    return _plot_p_value_frame(
        frame,
        title=_title("Nominal statistical significance", comparison.module_name),
        alpha=alpha,
        top_n=top_n,
        footnote="Nominal p-values; no multiplicity adjustment is applied in this figure",
    )


def plot_fdr_adjusted_prevalence_p_values(
    prevalence_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
    top_n: int = 25,
) -> Figure:
    """Plot Benjamini-Hochberg-adjusted prevalence p-values only."""

    _require_probability(alpha, "alpha")
    _require_positive(top_n, "top_n")
    frame = _prevalence_adjusted_p_value_frame(prevalence_tests)
    return _plot_p_value_frame(
        frame,
        title=_title("FDR-adjusted prevalence significance", module_name),
        alpha=alpha,
        top_n=top_n,
        footnote="Benjamini-Hochberg-adjusted prevalence p-values",
    )


def plot_jensen_shannon_divergence(
    distribution_tests: pd.DataFrame,
    *,
    module_name: str | None = None,
    annotate_values: bool = True,
) -> Figure:
    """Plot Jensen-Shannon divergence for coded clinical domains."""

    frame = _validated_numeric_frame(
        distribution_tests,
        required_columns={"domain", "jensen_shannon_divergence"},
        numeric_columns=["jensen_shannon_divergence"],
        context="distribution divergence",
    ).sort_values("jensen_shannon_divergence", ascending=True)

    with _plot_context():
        figure, axis = plt.subplots(figsize=_DEFAULT_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(frame), dtype=float)
        values = frame["jensen_shannon_divergence"].to_numpy(dtype=float)
        axis.barh(positions, values, color=_COLOUR_SYNTHEA)
        axis.set_yticks(positions, frame["domain"].astype(str))
        axis.set_xlabel("Jensen–Shannon divergence")
        axis.set_ylabel("Clinical domain")
        axis.set_title(_title("Coded-distribution divergence", module_name))
        axis.set_xlim(left=0.0)
        _style_axis(axis, grid_axis="x")

        if annotate_values:
            for position, value in zip(positions, values, strict=True):
                _annotate_horizontal_value(axis, position, value, f"{value:.4f}")

        axis.text(
            0.99,
            0.01,
            "0 indicates identical coded distributions; no clinical threshold is imposed",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize="x-small",
        )

    return figure


def plot_module_validation_summary(
    comparison: ModuleStatisticalComparisonResult,
) -> Figure:
    """Plot test counts and significant-result counts for one module."""

    summary = _first_row(comparison.summary)
    if not summary:
        raise NoPlottableDataError("No usable module summary data available.")

    categories = ["Continuous", "Categorical", "Prevalence", "Distribution"]
    totals = np.asarray(
        [
            _safe_int(summary.get("continuous_test_count")),
            _safe_int(summary.get("categorical_test_count")),
            _safe_int(summary.get("prevalence_test_count")),
            _safe_int(summary.get("distribution_test_count")),
        ],
        dtype=float,
    )
    if not np.any(totals > 0):
        raise NoPlottableDataError("No usable module test-count data available.")

    # Only prevalence exposes a dedicated post-FDR count in the current schema.
    adjusted = np.asarray(
        [0, 0, _safe_int(summary.get("significant_after_fdr_count")), 0],
        dtype=float,
    )

    with _plot_context():
        figure, axis = plt.subplots(figsize=_DEFAULT_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(categories), dtype=float)
        bars = axis.bar(positions, totals, color=_COLOUR_SYNTHEA, label="Tests run")
        axis.scatter(
            positions,
            adjusted,
            color=_COLOUR_SIGNIFICANT,
            marker="s",
            label="FDR-significant prevalence tests",
            zorder=3,
        )
        axis.set_xticks(positions, categories)
        axis.set_ylabel("Count")
        axis.set_title(_title("Module statistical summary", comparison.module_name))
        axis.legend(frameon=False)
        _style_axis(axis, grid_axis="y")

        for bar, value in zip(bars, totals, strict=True):
            axis.annotate(
                f"{int(value)}",
                (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                fontsize="small",
            )

    return figure


# =============================================================================
# Validation-run plots
# =============================================================================


def plot_validation_status_overview(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
) -> Figure:
    """Plot the final validation-status distribution across modules."""

    rows = [_comparison_status_row(comparison) for comparison in comparisons]
    if not rows:
        raise NoPlottableDataError("No usable validation status data available.")

    counts = pd.Series([row["decision"] for row in rows]).value_counts()
    categories = [category for category in _DECISION_ORDER if category in counts.index]
    values = [int(counts[category]) for category in categories]
    colours = {
        "pass": _COLOUR_POSITIVE,
        "warning": "#E69F00",
        "fail": _COLOUR_SIGNIFICANT,
        "skipped": _COLOUR_NEUTRAL,
    }

    with _plot_context():
        figure, axis = plt.subplots(figsize=_DEFAULT_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(categories), dtype=float)
        bars = axis.bar(
            positions,
            values,
            color=[colours[category] for category in categories],
        )
        axis.set_xticks(positions, [_DECISION_LABELS[category] for category in categories])
        axis.set_ylabel("Modules")
        axis.set_title("Validation status across modules")
        axis.set_ylim(bottom=0)
        _style_axis(axis, grid_axis="y")

        for bar, value in zip(bars, values, strict=True):
            axis.annotate(
                str(value),
                (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
            )

    return figure


def plot_divergence_heatmap(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    *,
    annotate_values: bool = True,
) -> Figure:
    """Plot module-by-domain Jensen-Shannon divergence as a heatmap."""

    records: list[dict[str, object]] = []
    for comparison in comparisons:
        frame = comparison.distribution_tests
        required = {"domain", "jensen_shannon_divergence"}
        if frame.empty or not required.issubset(frame.columns):
            continue
        subset = frame[["domain", "jensen_shannon_divergence"]].copy()
        subset["jensen_shannon_divergence"] = pd.to_numeric(
            subset["jensen_shannon_divergence"],
            errors="coerce",
        )
        subset = subset.dropna(subset=["jensen_shannon_divergence"])
        for row in subset.itertuples(index=False):
            records.append(
                {
                    "module_name": comparison.module_name,
                    "domain": str(row.domain),
                    "value": float(row.jensen_shannon_divergence),
                }
            )

    if not records:
        raise NoPlottableDataError("No usable divergence heatmap data available.")

    matrix = (
        pd.DataFrame(records)
        .pivot_table(
            index="module_name",
            columns="domain",
            values="value",
            aggfunc="mean",
        )
        .sort_index()
    )

    with _plot_context():
        width = max(8.0, 1.6 * len(matrix.columns) + 4.0)
        height = max(5.0, 0.55 * len(matrix.index) + 2.5)
        figure, axis = plt.subplots(figsize=(width, height), constrained_layout=True)
        masked = np.ma.masked_invalid(matrix.to_numpy(dtype=float))
        image = axis.imshow(masked, aspect="auto", interpolation="nearest", cmap="viridis")
        axis.set_xticks(np.arange(len(matrix.columns)), matrix.columns, rotation=35, ha="right")
        axis.set_yticks(np.arange(len(matrix.index)), matrix.index)
        axis.set_xlabel("Clinical domain")
        axis.set_ylabel("Module")
        axis.set_title("Jensen–Shannon divergence by module and domain")
        colourbar = figure.colorbar(image, ax=axis)
        colourbar.set_label("Jensen–Shannon divergence")

        if annotate_values:
            values = matrix.to_numpy(dtype=float)
            finite_values = values[np.isfinite(values)]
            midpoint = float(np.nanmedian(finite_values)) if finite_values.size else 0.0
            for row_index in range(values.shape[0]):
                for column_index in range(values.shape[1]):
                    value = values[row_index, column_index]
                    if np.isfinite(value):
                        text_colour = "white" if value > midpoint else "black"
                        axis.text(
                            column_index,
                            row_index,
                            f"{value:.3f}",
                            ha="center",
                            va="center",
                            color=text_colour,
                            fontsize="x-small",
                        )

    return figure


# =============================================================================
# Figure builders and persistence
# =============================================================================


def build_module_figures(
    comparison: ModuleStatisticalComparisonResult,
    *,
    config: PlotConfig | None = None,
) -> ModuleFigures:
    """Build every scientifically applicable figure for one module."""

    config = config or PlotConfig()
    builders: Sequence[tuple[str, Callable[[], Figure]]] = [
        (
            "prevalence_comparison",
            lambda: plot_prevalence_comparison(
                comparison.prevalence_tests,
                module_name=comparison.module_name,
                top_n=config.top_n_prevalence,
                rank_by=config.prevalence_rank_by,
                clinical_priority=config.clinical_priority,
                annotate_values=config.annotate_values,
            ),
        ),
        (
            "prevalence_differences",
            lambda: plot_prevalence_differences(
                comparison.prevalence_tests,
                module_name=comparison.module_name,
                top_n=config.top_n_prevalence,
                annotate_values=config.annotate_values,
            ),
        ),
        (
            "prevalence_risk_ratio_forest",
            lambda: plot_prevalence_risk_ratio_forest(
                comparison.prevalence_tests,
                module_name=comparison.module_name,
                top_n=config.top_n_prevalence,
                annotate_values=config.annotate_values,
            ),
        ),
        (
            "continuous_effect_sizes",
            lambda: plot_continuous_effect_sizes(
                comparison.continuous_tests,
                module_name=comparison.module_name,
                top_n=config.top_n_effect_sizes,
                practical_margin=config.continuous_effect_margin,
                annotate_values=config.annotate_values,
            ),
        ),
        (
            "categorical_effect_sizes",
            lambda: plot_categorical_effect_sizes(
                comparison.categorical_tests,
                module_name=comparison.module_name,
                top_n=config.top_n_effect_sizes,
                practical_margin=config.categorical_effect_margin,
                annotate_values=config.annotate_values,
            ),
        ),
        (
            "jensen_shannon_divergence",
            lambda: plot_jensen_shannon_divergence(
                comparison.distribution_tests,
                module_name=comparison.module_name,
                annotate_values=config.annotate_values,
            ),
        ),
        (
            "nominal_p_values",
            lambda: plot_nominal_p_values(
                comparison,
                alpha=config.alpha,
                top_n=config.top_n_p_values,
            ),
        ),
        (
            "fdr_adjusted_prevalence_p_values",
            lambda: plot_fdr_adjusted_prevalence_p_values(
                comparison.prevalence_tests,
                module_name=comparison.module_name,
                alpha=config.alpha,
                top_n=config.top_n_p_values,
            ),
        ),
        (
            "module_validation_summary",
            lambda: plot_module_validation_summary(comparison),
        ),
    ]

    if config.prevalence_equivalence_margin is not None:
        builders = [
            *builders[:2],
            (
                "prevalence_equivalence",
                lambda: plot_prevalence_equivalence(
                    comparison.prevalence_tests,
                    equivalence_margin=config.prevalence_equivalence_margin,
                    module_name=comparison.module_name,
                    top_n=config.top_n_prevalence,
                    annotate_values=config.annotate_values,
                ),
            ),
            *builders[2:],
        ]

    figures: dict[str, Figure] = {}
    for name, builder in builders:
        try:
            figures[name] = builder()
        except NoPlottableDataError:
            continue

    return ModuleFigures(module_name=comparison.module_name, figures=figures)


def build_validation_figures(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    *,
    annotate_values: bool = True,
) -> ValidationFigures:
    """Build complete-run figures across all module comparisons."""

    builders: Sequence[tuple[str, Callable[[], Figure]]] = [
        (
            "validation_status_overview",
            lambda: plot_validation_status_overview(comparisons),
        ),
        (
            "divergence_heatmap",
            lambda: plot_divergence_heatmap(
                comparisons,
                annotate_values=annotate_values,
            ),
        ),
    ]

    figures: dict[str, Figure] = {}
    for name, builder in builders:
        try:
            figures[name] = builder()
        except NoPlottableDataError:
            continue

    return ValidationFigures(figures=figures)


def save_module_figures(
    module_figures: ModuleFigures,
    output_dir: str | Path,
    *,
    file_format: str = DEFAULT_FIGURE_FORMAT,
    dpi: int = DEFAULT_DPI,
    close: bool = False,
) -> dict[str, Path]:
    """Save all figures for one module and return their generated paths."""

    module_slug = _slugify(module_figures.module_name)
    return _save_figures(
        module_figures.figures,
        output_dir,
        filename_prefix=f"{module_slug}__",
        file_format=file_format,
        dpi=dpi,
        close=close,
    )


def save_validation_figures(
    validation_figures: ValidationFigures,
    output_dir: str | Path,
    *,
    file_format: str = DEFAULT_FIGURE_FORMAT,
    dpi: int = DEFAULT_DPI,
    close: bool = False,
) -> dict[str, Path]:
    """Save complete-run validation figures and return their generated paths."""

    return _save_figures(
        validation_figures.figures,
        output_dir,
        filename_prefix="validation__",
        file_format=file_format,
        dpi=dpi,
        close=close,
    )


# =============================================================================
# Plot-ready frame construction
# =============================================================================


def _prepare_prevalence_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "domain",
        "code",
        "synthea_prevalence",
        "psynthea_prevalence",
        "absolute_difference",
        "significant_after_fdr",
    }
    prepared = _validated_numeric_frame(
        frame,
        required_columns=required,
        numeric_columns=[
            "synthea_prevalence",
            "psynthea_prevalence",
            "absolute_difference",
        ],
        context="prevalence",
    )
    prepared["label"] = prepared["domain"].astype(str) + ":" + prepared["code"].astype(str)
    prepared["significant_after_fdr"] = (
        prepared["significant_after_fdr"].fillna(False).astype(bool)
    )
    return prepared


def _select_prevalence_rows(
    frame: pd.DataFrame,
    *,
    top_n: int,
    rank_by: str,
    clinical_priority: Sequence[str],
) -> pd.DataFrame:
    if rank_by == "prevalence":
        ranked = frame.assign(
            _ranking=frame[["synthea_prevalence", "psynthea_prevalence"]].max(axis=1)
        )
    elif rank_by == "absolute_difference":
        ranked = frame.assign(_ranking=frame["absolute_difference"].abs())
    elif rank_by == "clinical_priority":
        if not clinical_priority:
            raise ValueError(
                "clinical_priority must contain domain:code labels when "
                "rank_by='clinical_priority'."
            )
        priority = {label: len(clinical_priority) - index for index, label in enumerate(clinical_priority)}
        ranked = frame[frame["label"].isin(priority)].copy()
        ranked["_ranking"] = ranked["label"].map(priority).astype(float)
        if ranked.empty:
            raise NoPlottableDataError("No usable clinically prioritised prevalence data available.")
    else:
        raise ValueError(
            "rank_by must be 'prevalence', 'absolute_difference' or 'clinical_priority'."
        )

    selected = ranked.sort_values("_ranking", ascending=False).head(top_n)
    if selected.empty:
        raise NoPlottableDataError("No usable prevalence data available.")
    return selected


def _nominal_p_value_frame(
    comparison: ModuleStatisticalComparisonResult,
) -> pd.DataFrame:
    frames = [
        _standard_p_value_frame(comparison.continuous_tests, label_column="metric"),
        _standard_p_value_frame(comparison.categorical_tests, label_column="domain"),
        _standard_p_value_frame(comparison.distribution_tests, label_column="domain"),
    ]
    available = [frame for frame in frames if not frame.empty]
    if not available:
        raise NoPlottableDataError("No usable nominal p-value data available.")

    combined = pd.concat(available, ignore_index=True)
    combined["label"] = combined.apply(_test_label, axis=1)
    return _valid_probability_rows(combined, "p_value", "nominal p-value")


def _prevalence_adjusted_p_value_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "scope",
        "domain",
        "code",
        "test_name",
        "adjusted_p_value",
        "significant_after_fdr",
    }
    missing = required.difference(frame.columns)
    if frame.empty or missing:
        raise NoPlottableDataError("No usable FDR-adjusted prevalence p-value data available.")

    result = frame[list(required)].copy()
    result["p_value"] = pd.to_numeric(result["adjusted_p_value"], errors="coerce")
    result["significant"] = result["significant_after_fdr"].fillna(False).astype(bool)
    result["domain_or_metric"] = result["domain"].astype(str) + ":" + result["code"].astype(str)
    result["label"] = result.apply(_test_label, axis=1)
    return _valid_probability_rows(result, "p_value", "FDR-adjusted prevalence p-value")


def _standard_p_value_frame(frame: pd.DataFrame, *, label_column: str) -> pd.DataFrame:
    required = {"scope", label_column, "test_name", "p_value", "significant"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(
            columns=["scope", "domain_or_metric", "test_name", "p_value", "significant"]
        )
    result = frame[list(required)].copy()
    return result.rename(columns={label_column: "domain_or_metric"})


# =============================================================================
# Internal plotting helpers
# =============================================================================


def _plot_effect_size_family(
    frame: pd.DataFrame,
    *,
    label_column: str,
    family_name: str,
    module_name: str | None,
    top_n: int,
    practical_margin: float | None,
    annotate_values: bool,
) -> Figure:
    _require_positive(top_n, "top_n")
    _require_optional_non_negative(practical_margin, "practical_margin")
    prepared = _validated_numeric_frame(
        frame,
        required_columns={label_column, "test_name", "effect_size", "significant"},
        numeric_columns=["effect_size"],
        context=f"{family_name.lower()} effect-size",
    )
    prepared["label"] = (
        prepared[label_column].astype(str) + " | " + prepared["test_name"].astype(str)
    )
    prepared["significant"] = prepared["significant"].fillna(False).astype(bool)
    prepared = (
        prepared.assign(_ranking=prepared["effect_size"].abs())
        .sort_values("_ranking", ascending=False)
        .head(top_n)
        .sort_values("effect_size", ascending=True)
    )

    values = prepared["effect_size"].to_numpy(dtype=float)
    significant = prepared["significant"].to_numpy(dtype=bool)

    with _plot_context():
        figure, axis = plt.subplots(figsize=_WIDE_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(prepared), dtype=float)
        colours = [
            _COLOUR_SIGNIFICANT if value else _COLOUR_SYNTHEA
            for value in significant
        ]
        bars = axis.barh(positions, values, color=colours)
        for bar, is_significant in zip(bars, significant, strict=True):
            if is_significant:
                bar.set_hatch("///")

        axis.axvline(0.0, color="black", linewidth=1.0)
        if practical_margin is not None:
            axis.axvspan(
                -practical_margin,
                practical_margin,
                color=_COLOUR_EQUIVALENCE,
                label=f"Reference band ±{practical_margin:g}",
                zorder=0,
            )
            axis.legend(frameon=False)

        axis.set_yticks(positions, prepared["label"])
        axis.set_xlabel("Effect size")
        axis.set_ylabel("Statistical test")
        axis.set_title(_title(f"{family_name} effect sizes", module_name))
        _style_axis(axis, grid_axis="x")

        if annotate_values:
            for position, value in zip(positions, values, strict=True):
                _annotate_horizontal_value(axis, position, value, f"{value:+.3f}")

        axis.text(
            0.99,
            0.01,
            "Reference bands are descriptive and must match the approved validation protocol",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize="x-small",
        )

    return figure


def _plot_p_value_frame(
    frame: pd.DataFrame,
    *,
    title: str,
    alpha: float,
    top_n: int,
    footnote: str,
) -> Figure:
    frame = (
        frame.sort_values("p_value", ascending=True)
        .head(top_n)
        .sort_values("p_value", ascending=False)
    )
    transformed = -np.log10(
        np.clip(frame["p_value"].to_numpy(dtype=float), np.finfo(float).tiny, 1.0)
    )
    threshold = -np.log10(alpha)
    significant = frame["significant"].fillna(False).to_numpy(dtype=bool)

    with _plot_context():
        figure, axis = plt.subplots(figsize=_WIDE_FIGSIZE, constrained_layout=True)
        positions = np.arange(len(frame), dtype=float)
        colours = [
            _COLOUR_SIGNIFICANT if value else _COLOUR_NON_SIGNIFICANT
            for value in significant
        ]
        bars = axis.barh(positions, transformed, color=colours)
        for bar, is_significant in zip(bars, significant, strict=True):
            if is_significant:
                bar.set_hatch("///")

        axis.axvline(
            threshold,
            color="black",
            linestyle="--",
            linewidth=1.0,
            label=f"alpha = {alpha:g}",
        )
        axis.set_yticks(positions, frame["label"])
        axis.set_xlabel("−log10(p-value)")
        axis.set_ylabel("Statistical test")
        axis.set_title(title)
        axis.legend(frameon=False)
        _style_axis(axis, grid_axis="x")
        axis.text(
            0.99,
            0.01,
            footnote,
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize="x-small",
        )

    return figure


def _comparison_status_row(
    comparison: ModuleStatisticalComparisonResult,
) -> dict[str, object]:
    summary = _first_row(comparison.summary)
    skipped = bool(summary.get("skipped", False))
    valid = bool(summary.get("valid_for_statistical_comparison", False))
    significant = _safe_int(summary.get("significant_test_count"))
    significant_fdr = _safe_int(summary.get("significant_after_fdr_count"))

    if skipped:
        decision = "skipped"
    elif not valid or significant_fdr > 0:
        decision = "fail"
    elif significant > 0:
        decision = "warning"
    else:
        decision = "pass"

    return {"module_name": comparison.module_name, "decision": decision}


def _save_figures(
    figures: Mapping[str, Figure],
    output_dir: str | Path,
    *,
    filename_prefix: str,
    file_format: str,
    dpi: int,
    close: bool,
) -> dict[str, Path]:
    _require_positive(dpi, "dpi")
    normalized_format = _normalise_file_format(file_format)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for name, figure in figures.items():
        path = destination / f"{filename_prefix}{_slugify(name)}.{normalized_format}"
        figure.savefig(
            path,
            dpi=dpi,
            format=normalized_format,
            bbox_inches="tight",
            metadata={"Creator": "psynthea-validation"},
        )
        paths[name] = path
        if close:
            plt.close(figure)
    return paths


# =============================================================================
# Generic helpers
# =============================================================================


def _validated_numeric_frame(
    frame: pd.DataFrame,
    *,
    required_columns: set[str],
    numeric_columns: Sequence[str],
    context: str,
) -> pd.DataFrame:
    missing = required_columns.difference(frame.columns)
    if missing:
        columns = ", ".join(sorted(missing))
        raise ValueError(f"Missing required {context} columns: {columns}.")

    prepared = frame.copy()
    for column in numeric_columns:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared = prepared.dropna(subset=list(numeric_columns))
    if prepared.empty:
        raise NoPlottableDataError(f"No usable {context} data available.")
    return prepared


def _valid_probability_rows(
    frame: pd.DataFrame,
    column: str,
    context: str,
) -> pd.DataFrame:
    result = frame.copy()
    result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result[result[column].between(0.0, 1.0, inclusive="both")]
    if result.empty:
        raise NoPlottableDataError(f"No usable {context} data available.")
    return result


def _test_label(row: pd.Series) -> str:
    scope = _SCOPE_LABELS.get(str(row["scope"]), str(row["scope"]))
    return f"{scope} | {row['domain_or_metric']} | {row['test_name']}"


def _title(base: str, module_name: str | None) -> str:
    return base if not module_name else f"{base} — {module_name}"


def _style_axis(axis: Axes, *, grid_axis: Literal["x", "y"]) -> None:
    axis.grid(axis=grid_axis, color=_COLOUR_GRID, linewidth=0.8, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def _plot_context():
    return plt.rc_context(
        {
            "font.size": 10,
            "axes.titlesize": 14,
            "axes.titleweight": "semibold",
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _annotate_horizontal_value(
    axis: Axes,
    position: float,
    value: float,
    text: str,
) -> None:
    axis.annotate(
        text,
        xy=(value, position),
        xytext=(5 if value >= 0 else -5, 0),
        textcoords="offset points",
        va="center",
        ha="left" if value >= 0 else "right",
        fontsize="x-small",
    )


def _normalise_file_format(file_format: str) -> str:
    normalized = file_format.strip().lower().lstrip(".")
    if not normalized:
        raise ValueError("file_format must not be empty.")
    figure = Figure()
    try:
        supported = set(figure.canvas.get_supported_filetypes())
    finally:
        plt.close(figure)
    if normalized not in supported:
        available = ", ".join(sorted(supported))
        raise ValueError(
            f"Unsupported figure format '{file_format}'. Supported: {available}."
        )
    return normalized


def _slugify(value: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "_"
        for character in value
    )
    slug = "_".join(part for part in slug.split("_") if part)
    return slug or "figure"


def _first_row(frame: pd.DataFrame) -> dict[str, object]:
    return {} if frame.empty else frame.iloc[0].to_dict()


def _safe_int(value: object) -> int:
    if value is None or pd.isna(value):
        return 0
    return int(value)


def _require_positive(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")


def _require_probability(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 < float(value) < 1.0
    ):
        raise ValueError(f"{name} must be strictly between 0 and 1.")


def _require_non_negative(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be non-negative.")


def _require_optional_non_negative(value: float | None, name: str) -> None:
    if value is not None:
        _require_non_negative(value, name)
