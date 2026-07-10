"""
Tests for the publication-oriented plotting layer.

The suite uses already-computed comparison tables and the non-interactive Agg
backend. It therefore validates plotting behaviour without executing simulators,
loading cohort files or recomputing statistical results.
"""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import pandas as pd
import pytest

from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.plots import (
    ModuleFigures,
    NoPlottableDataError,
    PlotConfig,
    ValidationFigures,
    build_module_figures,
    build_validation_figures,
    plot_categorical_effect_sizes,
    plot_continuous_effect_sizes,
    plot_divergence_heatmap,
    plot_fdr_adjusted_prevalence_p_values,
    plot_jensen_shannon_divergence,
    plot_module_validation_summary,
    plot_nominal_p_values,
    plot_prevalence_comparison,
    plot_prevalence_differences,
    plot_prevalence_equivalence,
    plot_prevalence_risk_ratio_forest,
    plot_validation_status_overview,
    save_module_figures,
    save_validation_figures,
)


@pytest.fixture(autouse=True)
def _close_all_figures() -> None:
    """Prevent matplotlib state leaking between tests."""

    yield
    plt.close("all")


@pytest.fixture
def prevalence_tests() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module_name": "demo module",
                "scope": "prevalence",
                "domain": "conditions",
                "code": "A",
                "synthea_prevalence": 0.10,
                "psynthea_prevalence": 0.12,
                "absolute_difference": 0.02,
                "relative_difference": 0.20,
                "risk_ratio": 1.20,
                "risk_ratio_ci_lower": 1.02,
                "risk_ratio_ci_upper": 1.41,
                "odds_ratio": 1.23,
                "odds_ratio_ci_lower": 1.01,
                "odds_ratio_ci_upper": 1.49,
                "p_value": 0.01,
                "adjusted_p_value": 0.03,
                "significant": True,
                "significant_after_fdr": True,
                "test_name": "two_proportion_z",
                "statistic": 2.4,
                "notes": "",
            },
            {
                "module_name": "demo module",
                "scope": "prevalence",
                "domain": "medications",
                "code": "B",
                "synthea_prevalence": 0.35,
                "psynthea_prevalence": 0.34,
                "absolute_difference": -0.01,
                "relative_difference": -0.0286,
                "risk_ratio": 0.97,
                "risk_ratio_ci_lower": 0.88,
                "risk_ratio_ci_upper": 1.07,
                "odds_ratio": 0.96,
                "odds_ratio_ci_lower": 0.84,
                "odds_ratio_ci_upper": 1.10,
                "p_value": 0.40,
                "adjusted_p_value": 0.50,
                "significant": False,
                "significant_after_fdr": False,
                "test_name": "two_proportion_z",
                "statistic": -0.8,
                "notes": "",
            },
            {
                "module_name": "demo module",
                "scope": "prevalence",
                "domain": "procedures",
                "code": "C",
                "synthea_prevalence": 0.02,
                "psynthea_prevalence": 0.05,
                "absolute_difference": 0.03,
                "relative_difference": 1.50,
                "risk_ratio": 2.50,
                "risk_ratio_ci_lower": 1.20,
                "risk_ratio_ci_upper": 5.21,
                "odds_ratio": 2.58,
                "odds_ratio_ci_lower": 1.18,
                "odds_ratio_ci_upper": 5.64,
                "p_value": 0.004,
                "adjusted_p_value": 0.018,
                "significant": True,
                "significant_after_fdr": True,
                "test_name": "fisher_exact",
                "statistic": 2.58,
                "notes": "",
            },
        ]
    )


@pytest.fixture
def continuous_tests() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module_name": "demo module",
                "scope": "continuous",
                "metric": "age",
                "test_name": "welch_t",
                "statistic": 1.5,
                "p_value": 0.13,
                "effect_size": 0.15,
                "significant": False,
                "notes": "",
            },
            {
                "module_name": "demo module",
                "scope": "continuous",
                "metric": "encounters_per_patient",
                "test_name": "mann_whitney_u",
                "statistic": 25.0,
                "p_value": 0.01,
                "effect_size": -0.42,
                "significant": True,
                "notes": "",
            },
        ]
    )


@pytest.fixture
def categorical_tests() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module_name": "demo module",
                "scope": "categorical",
                "domain": "gender",
                "test_name": "chi_square",
                "statistic": 3.0,
                "p_value": 0.08,
                "effect_size": 0.08,
                "significant": False,
                "notes": "",
            },
            {
                "module_name": "demo module",
                "scope": "categorical",
                "domain": "encounter_class",
                "test_name": "chi_square",
                "statistic": 8.5,
                "p_value": 0.004,
                "effect_size": 0.22,
                "significant": True,
                "notes": "",
            },
        ]
    )


@pytest.fixture
def distribution_tests() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "module_name": "demo module",
                "scope": "code_distribution",
                "domain": "conditions",
                "test_name": "chi_square",
                "statistic": 4.0,
                "p_value": 0.04,
                "effect_size": 0.12,
                "jensen_shannon_divergence": 0.025,
                "significant": True,
                "notes": "",
            },
            {
                "module_name": "demo module",
                "scope": "code_distribution",
                "domain": "medications",
                "test_name": "chi_square",
                "statistic": 1.2,
                "p_value": 0.27,
                "effect_size": 0.05,
                "jensen_shannon_divergence": 0.008,
                "significant": False,
                "notes": "",
            },
        ]
    )


@pytest.fixture
def comparison(
    prevalence_tests: pd.DataFrame,
    continuous_tests: pd.DataFrame,
    categorical_tests: pd.DataFrame,
    distribution_tests: pd.DataFrame,
) -> ModuleStatisticalComparisonResult:
    summary = pd.DataFrame(
        [
            {
                "module_name": "demo module",
                "validation_status": "comparable",
                "valid_for_statistical_comparison": True,
                "skipped": False,
                "skip_reason": None,
                "continuous_test_count": len(continuous_tests),
                "categorical_test_count": len(categorical_tests),
                "prevalence_test_count": len(prevalence_tests),
                "distribution_test_count": len(distribution_tests),
                "significant_test_count": 4,
                "significant_after_fdr_count": 2,
                "mean_jensen_shannon_divergence": 0.0165,
            }
        ]
    )
    validation = SimpleNamespace(summary=pd.DataFrame([{"status": "comparable"}]))
    return ModuleStatisticalComparisonResult(
        module_name="demo module",
        validation=validation,
        continuous_tests=continuous_tests,
        categorical_tests=categorical_tests,
        prevalence_tests=prevalence_tests,
        distribution_tests=distribution_tests,
        summary=summary,
    )


def _empty_comparison() -> ModuleStatisticalComparisonResult:
    validation = SimpleNamespace(summary=pd.DataFrame([{"status": "not_comparable"}]))
    return ModuleStatisticalComparisonResult(
        module_name="empty",
        validation=validation,
        continuous_tests=pd.DataFrame(
            columns=["scope", "metric", "test_name", "statistic", "p_value", "effect_size", "significant", "notes"]
        ),
        categorical_tests=pd.DataFrame(
            columns=["scope", "domain", "test_name", "statistic", "p_value", "effect_size", "significant", "notes"]
        ),
        prevalence_tests=pd.DataFrame(
            columns=[
                "scope", "domain", "code", "synthea_prevalence",
                "psynthea_prevalence", "absolute_difference", "risk_ratio",
                "risk_ratio_ci_lower", "risk_ratio_ci_upper", "p_value",
                "adjusted_p_value", "significant_after_fdr", "test_name",
                "statistic", "notes",
            ]
        ),
        distribution_tests=pd.DataFrame(
            columns=[
                "scope", "domain", "test_name", "statistic", "p_value",
                "effect_size", "jensen_shannon_divergence", "significant", "notes",
            ]
        ),
        summary=pd.DataFrame(),
    )


# =============================================================================
# Configuration
# =============================================================================


def test_plot_config_defaults_are_valid() -> None:
    config = PlotConfig()

    assert config.alpha == pytest.approx(0.05)
    assert config.prevalence_rank_by == "absolute_difference"
    assert config.annotate_values


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.0, 1.1])
def test_plot_config_rejects_invalid_alpha(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha"):
        PlotConfig(alpha=alpha)


@pytest.mark.parametrize(
    "field_name",
    ["top_n_prevalence", "top_n_effect_sizes", "top_n_p_values"],
)
def test_plot_config_rejects_non_positive_top_n(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        PlotConfig(**{field_name: 0})


@pytest.mark.parametrize(
    "field_name",
    [
        "prevalence_equivalence_margin",
        "continuous_effect_margin",
        "categorical_effect_margin",
    ],
)
def test_plot_config_rejects_negative_margins(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        PlotConfig(**{field_name: -0.01})


# =============================================================================
# Module-level figures
# =============================================================================


def test_plot_prevalence_comparison_returns_dumbbell_figure(
    prevalence_tests: pd.DataFrame,
) -> None:
    figure = plot_prevalence_comparison(prevalence_tests, module_name="demo")

    assert isinstance(figure, Figure)
    assert "Prevalence comparison" in figure.axes[0].get_title()
    assert len(figure.axes[0].collections) == 2


@pytest.mark.parametrize(
    "rank_by",
    ["prevalence", "absolute_difference", "clinical_priority"],
)
def test_plot_prevalence_comparison_supports_all_rankings(
    prevalence_tests: pd.DataFrame,
    rank_by: str,
) -> None:
    figure = plot_prevalence_comparison(
        prevalence_tests,
        rank_by=rank_by,
        clinical_priority=("conditions:A", "procedures:C"),
        top_n=2,
    )

    assert isinstance(figure, Figure)
    assert len(figure.axes[0].get_yticklabels()) == 2


def test_plot_prevalence_differences_adds_zero_reference(
    prevalence_tests: pd.DataFrame,
) -> None:
    figure = plot_prevalence_differences(prevalence_tests)

    assert isinstance(figure, Figure)
    assert any(line.get_xdata()[0] == 0.0 for line in figure.axes[0].lines)


def test_plot_prevalence_equivalence_requires_non_negative_margin(
    prevalence_tests: pd.DataFrame,
) -> None:
    with pytest.raises(ValueError, match="equivalence_margin"):
        plot_prevalence_equivalence(prevalence_tests, equivalence_margin=-0.01)


def test_plot_prevalence_equivalence_returns_screening_figure(
    prevalence_tests: pd.DataFrame,
) -> None:
    figure = plot_prevalence_equivalence(
        prevalence_tests,
        equivalence_margin=0.02,
        module_name="demo",
    )

    assert isinstance(figure, Figure)
    assert "equivalence screening" in figure.axes[0].get_title().lower()


def test_plot_prevalence_risk_ratio_forest_uses_log_scale(
    prevalence_tests: pd.DataFrame,
) -> None:
    figure = plot_prevalence_risk_ratio_forest(prevalence_tests)

    assert isinstance(figure, Figure)
    assert figure.axes[0].get_xscale() == "log"


def test_plot_prevalence_risk_ratio_forest_rejects_invalid_intervals(
    prevalence_tests: pd.DataFrame,
) -> None:
    frame = prevalence_tests.copy()
    frame[["risk_ratio", "risk_ratio_ci_lower", "risk_ratio_ci_upper"]] = 0.0

    with pytest.raises(NoPlottableDataError, match="risk-ratio"):
        plot_prevalence_risk_ratio_forest(frame)


def test_plot_continuous_effect_sizes_returns_figure(
    continuous_tests: pd.DataFrame,
) -> None:
    figure = plot_continuous_effect_sizes(continuous_tests, practical_margin=0.20)

    assert isinstance(figure, Figure)
    assert "Continuous effect sizes" in figure.axes[0].get_title()


def test_plot_categorical_effect_sizes_returns_figure(
    categorical_tests: pd.DataFrame,
) -> None:
    figure = plot_categorical_effect_sizes(categorical_tests, practical_margin=0.10)

    assert isinstance(figure, Figure)
    assert "Categorical effect sizes" in figure.axes[0].get_title()


def test_effect_size_plot_rejects_all_missing_effects(
    continuous_tests: pd.DataFrame,
) -> None:
    frame = continuous_tests.copy()
    frame["effect_size"] = pd.NA

    with pytest.raises(NoPlottableDataError):
        plot_continuous_effect_sizes(frame)


def test_plot_nominal_p_values_excludes_prevalence_tests(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    figure = plot_nominal_p_values(comparison)

    labels = [tick.get_text() for tick in figure.axes[0].get_yticklabels()]
    assert isinstance(figure, Figure)
    assert labels
    assert all("conditions:A" not in label for label in labels)


def test_plot_fdr_adjusted_prevalence_p_values_returns_figure(
    prevalence_tests: pd.DataFrame,
) -> None:
    figure = plot_fdr_adjusted_prevalence_p_values(prevalence_tests)

    assert isinstance(figure, Figure)
    assert "FDR-adjusted" in figure.axes[0].get_title()


def test_plot_jensen_shannon_divergence_returns_sorted_figure(
    distribution_tests: pd.DataFrame,
) -> None:
    figure = plot_jensen_shannon_divergence(distribution_tests)

    labels = [tick.get_text() for tick in figure.axes[0].get_yticklabels()]
    assert isinstance(figure, Figure)
    assert labels == ["medications", "conditions"]


def test_plot_module_validation_summary_returns_figure(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    figure = plot_module_validation_summary(comparison)

    assert isinstance(figure, Figure)
    assert len(figure.axes[0].patches) == 4


def test_plot_module_validation_summary_rejects_empty_summary() -> None:
    with pytest.raises(NoPlottableDataError, match="summary"):
        plot_module_validation_summary(_empty_comparison())


# =============================================================================
# Complete-run figures
# =============================================================================


def test_plot_validation_status_overview_returns_figure(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    figure = plot_validation_status_overview([comparison])

    assert isinstance(figure, Figure)
    assert "across modules" in figure.axes[0].get_title()


def test_plot_validation_status_overview_rejects_empty_sequence() -> None:
    with pytest.raises(NoPlottableDataError, match="status"):
        plot_validation_status_overview([])


def test_plot_divergence_heatmap_returns_figure(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    figure = plot_divergence_heatmap([comparison])

    assert isinstance(figure, Figure)
    assert len(figure.axes) == 2  # main axis plus colour bar


def test_plot_divergence_heatmap_skips_comparisons_without_distribution_data(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    empty = _empty_comparison()
    figure = plot_divergence_heatmap([empty, comparison])

    assert isinstance(figure, Figure)


def test_plot_divergence_heatmap_rejects_no_usable_data() -> None:
    with pytest.raises(NoPlottableDataError, match="divergence"):
        plot_divergence_heatmap([_empty_comparison()])


# =============================================================================
# Builders
# =============================================================================


def test_build_module_figures_builds_all_applicable_figures(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    result = build_module_figures(
        comparison,
        config=PlotConfig(prevalence_equivalence_margin=0.02),
    )

    assert result.module_name == "demo module"
    assert set(result.figures) == {
        "prevalence_comparison",
        "prevalence_differences",
        "prevalence_equivalence",
        "prevalence_risk_ratio_forest",
        "continuous_effect_sizes",
        "categorical_effect_sizes",
        "jensen_shannon_divergence",
        "nominal_p_values",
        "fdr_adjusted_prevalence_p_values",
        "module_validation_summary",
    }
    assert all(isinstance(figure, Figure) for figure in result.figures.values())


def test_build_module_figures_omits_equivalence_by_default(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    result = build_module_figures(comparison)

    assert "prevalence_equivalence" not in result.figures


def test_build_module_figures_omits_unavailable_figures() -> None:
    result = build_module_figures(_empty_comparison())

    assert result.figures == {}


def test_build_validation_figures_builds_global_figures(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    result = build_validation_figures([comparison])

    assert set(result.figures) == {
        "validation_status_overview",
        "divergence_heatmap",
    }


def test_build_validation_figures_omits_unavailable_global_figures() -> None:
    result = build_validation_figures([])

    assert result.figures == {}


# =============================================================================
# Persistence
# =============================================================================


def test_save_module_figures_writes_deterministic_filenames(tmp_path) -> None:
    figure = plt.figure()
    result = save_module_figures(
        ModuleFigures(module_name="Demo Module / 2026", figures={"summary": figure}),
        tmp_path,
        file_format="png",
        dpi=72,
    )

    path = result["summary"]
    assert path.name == "demo_module_2026__summary.png"
    assert path.is_file()
    assert path.stat().st_size > 0


def test_save_validation_figures_writes_global_prefix(tmp_path) -> None:
    figure = plt.figure()
    result = save_validation_figures(
        ValidationFigures(figures={"overview": figure}),
        tmp_path,
        file_format="svg",
    )

    path = result["overview"]
    assert path.name == "validation__overview.svg"
    assert path.is_file()


def test_save_module_figures_creates_output_directory(tmp_path) -> None:
    output_dir = tmp_path / "nested" / "figures"
    result = save_module_figures(
        ModuleFigures(module_name="demo", figures={"one": plt.figure()}),
        output_dir,
    )

    assert output_dir.is_dir()
    assert result["one"].is_file()


def test_save_module_figures_can_close_saved_figures(tmp_path) -> None:
    figure = plt.figure()
    number = figure.number

    save_module_figures(
        ModuleFigures(module_name="demo", figures={"one": figure}),
        tmp_path,
        close=True,
    )

    assert not plt.fignum_exists(number)


@pytest.mark.parametrize("file_format", ["PNG", "svg"])
def test_save_module_figures_normalises_file_format(
    tmp_path,
    file_format: str,
) -> None:
    result = save_module_figures(
        ModuleFigures(module_name="demo", figures={"one": plt.figure()}),
        tmp_path / file_format.replace(".", "dot"),
        file_format=file_format,
    )

    expected_suffix = ".svg" if file_format.lower().endswith("svg") else ".png"
    assert result["one"].suffix == expected_suffix


def test_save_module_figures_rejects_invalid_dpi(tmp_path) -> None:
    with pytest.raises(ValueError, match="dpi"):
        save_module_figures(
            ModuleFigures(module_name="demo", figures={"one": plt.figure()}),
            tmp_path,
            dpi=0,
        )


# =============================================================================
# Data validation
# =============================================================================


def test_prevalence_plot_rejects_missing_required_columns() -> None:
    with pytest.raises(ValueError, match="Missing required prevalence columns"):
        plot_prevalence_comparison(pd.DataFrame({"code": ["A"]}))


def test_prevalence_plot_rejects_empty_frame() -> None:
    with pytest.raises(ValueError, match="Missing required prevalence columns"):
        plot_prevalence_comparison(pd.DataFrame())


def test_p_value_plot_rejects_invalid_alpha(
    comparison: ModuleStatisticalComparisonResult,
) -> None:
    with pytest.raises(ValueError, match="alpha"):
        plot_nominal_p_values(comparison, alpha=1.0)


def test_prevalence_plot_rejects_non_positive_top_n(
    prevalence_tests: pd.DataFrame,
) -> None:
    with pytest.raises(ValueError, match="top_n"):
        plot_prevalence_comparison(prevalence_tests, top_n=0)
