"""Tests for immutable validation-run configuration models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from validation.config import (
    CONFIG_SCHEMA_VERSION,
    CohortInputConfig,
    ConfigurationError,
    ModuleConfig,
    OutputConfig,
    PresentationConfig,
    StatisticalConfig,
    ValidationRunConfig,
)


def _config(tmp_path: Path, *, overwrite: bool = False) -> ValidationRunConfig:
    return ValidationRunConfig(
        inputs=CohortInputConfig(tmp_path / "synthea", tmp_path / "psynthea"),
        output=OutputConfig(tmp_path / "output", overwrite=overwrite),
        modules=(
            ModuleConfig(
                "Hypertension",
                expected_condition_terms=("hypertension",),
                expected_observation_terms=("blood pressure",),
            ),
        ),
        reference_date=date(2025, 1, 1),
    )


def _write_cohorts(tmp_path: Path) -> None:
    for name in ("synthea", "psynthea"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "patients.csv").write_text("Id\nP1\n", encoding="utf-8")


def test_module_config_normalises_and_deduplicates_terms() -> None:
    config = ModuleConfig(
        "  Hypertension  ",
        expected_condition_terms=(" hypertension ", "Hypertension", "HTN"),
    )
    assert config.name == "Hypertension"
    assert config.expected_condition_terms == ("hypertension", "HTN")
    assert config.has_expected_signals


def test_module_config_rejects_string_term_collection() -> None:
    with pytest.raises(ConfigurationError):
        ModuleConfig("Hypertension", expected_condition_terms="hypertension")


def test_module_config_rejects_blank_name() -> None:
    with pytest.raises(ConfigurationError):
        ModuleConfig("  ")


def test_statistical_config_defaults_are_consistent() -> None:
    config = StatisticalConfig()
    assert config.alpha == 0.05
    assert config.confidence_level == 0.95
    assert config.top_n_codes == 25


@pytest.mark.parametrize("alpha", [0, 1, -0.1, 1.1, True, "0.05"])
def test_statistical_config_rejects_invalid_alpha(alpha) -> None:
    with pytest.raises(ConfigurationError):
        StatisticalConfig(alpha=alpha)


def test_statistical_config_derives_confidence_from_custom_alpha() -> None:
    config = StatisticalConfig(alpha=0.01)
    assert config.alpha == 0.01
    assert config.confidence_level == 0.99


def test_statistical_config_allows_independent_confidence_level() -> None:
    config = StatisticalConfig(alpha=0.05, confidence_level=0.99)
    assert config.alpha == 0.05
    assert config.confidence_level == 0.99


def test_statistical_config_normalises_numeric_values_to_float() -> None:
    config = StatisticalConfig(alpha=0.05, confidence_level=0.9)
    assert isinstance(config.alpha, float)
    assert isinstance(config.confidence_level, float)


def test_presentation_config_normalises_figure_format() -> None:
    config = PresentationConfig(figure_format=".SVG")
    assert config.figure_format == "svg"


def test_presentation_config_normalises_numeric_margins() -> None:
    config = PresentationConfig(
        prevalence_equivalence_margin=0,
        continuous_effect_margin=1,
    )
    assert config.prevalence_equivalence_margin == 0.0
    assert config.continuous_effect_margin == 1.0


def test_presentation_config_requires_priority_when_selected() -> None:
    with pytest.raises(ConfigurationError, match="clinical_priority"):
        PresentationConfig(prevalence_rank_by="clinical_priority")


@pytest.mark.parametrize("value", ["condition", ":123", "condition:", " : "])
def test_presentation_config_rejects_invalid_clinical_priority(value: str) -> None:
    with pytest.raises(ConfigurationError, match="domain:code"):
        PresentationConfig(clinical_priority=(value,))


def test_presentation_config_accepts_domain_code_priority() -> None:
    config = PresentationConfig(
        prevalence_rank_by="clinical_priority",
        clinical_priority=("conditions:59621000", "medications:860975"),
    )
    assert config.clinical_priority == (
        "conditions:59621000",
        "medications:860975",
    )


def test_presentation_config_builds_plot_config_with_supplied_alpha() -> None:
    config = PresentationConfig(top_n_prevalence_plots=7)
    plot_config = config.to_plot_config(alpha=0.01)
    assert plot_config.alpha == 0.01
    assert plot_config.top_n_prevalence == 7


def test_output_config_exposes_derived_paths(tmp_path: Path) -> None:
    config = OutputConfig(tmp_path / "run")
    assert config.report_path == tmp_path / "run" / "validation_report.md"
    assert config.figures_dir == tmp_path / "run" / "figures"
    assert config.tables_dir == tmp_path / "run" / "tables"


@pytest.mark.parametrize("filename", ["report.txt", "../report.md", "/tmp/report.md"])
def test_output_config_rejects_unsafe_report_filename(
    tmp_path: Path,
    filename: str,
) -> None:
    with pytest.raises(ConfigurationError):
        OutputConfig(tmp_path, report_filename=filename)


def test_output_config_rejects_identical_subdirectories(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        OutputConfig(tmp_path, figures_subdir="artifacts", tables_subdir="artifacts")


def test_output_validation_ignores_empty_directories(tmp_path: Path) -> None:
    output = OutputConfig(tmp_path / "run")
    output.figures_dir.mkdir(parents=True)
    output.tables_dir.mkdir()
    output.validate_output_state()


@pytest.mark.parametrize("subdirectory", ["figures", "tables"])
def test_output_validation_rejects_non_empty_artifact_directory(
    tmp_path: Path,
    subdirectory: str,
) -> None:
    output = OutputConfig(tmp_path / "run")
    target = output.root_dir / subdirectory
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match=subdirectory):
        output.validate_output_state()


def test_cohort_input_config_rejects_same_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        CohortInputConfig(tmp_path, tmp_path)


def test_filesystem_validation_accepts_complete_inputs(tmp_path: Path) -> None:
    _write_cohorts(tmp_path)
    _config(tmp_path).validate_filesystem()


def test_filesystem_validation_rejects_missing_required_file(tmp_path: Path) -> None:
    (tmp_path / "synthea").mkdir()
    (tmp_path / "psynthea").mkdir()
    (tmp_path / "synthea" / "patients.csv").write_text("Id\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="psynthea"):
        _config(tmp_path).validate_filesystem()


def test_run_config_rejects_empty_modules(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="At least one"):
        ValidationRunConfig(
            inputs=CohortInputConfig(tmp_path / "a", tmp_path / "b"),
            output=OutputConfig(tmp_path / "out"),
            modules=(),
        )


def test_run_config_rejects_duplicate_module_names(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="duplicates"):
        ValidationRunConfig(
            inputs=CohortInputConfig(tmp_path / "a", tmp_path / "b"),
            output=OutputConfig(tmp_path / "out"),
            modules=(ModuleConfig("Asthma"), ModuleConfig("asthma")),
        )


def test_run_config_supports_case_insensitive_module_lookup(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.module("hypertension").name == "Hypertension"


def test_run_config_module_lookup_rejects_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        _config(tmp_path).module("asthma")


def test_run_config_is_immutable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with pytest.raises(FrozenInstanceError):
        config.run_name = "changed"


def test_schema_version_is_serialised(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.to_dict()["schema_version"] == CONFIG_SCHEMA_VERSION


def test_run_config_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    base = _config(tmp_path)
    with pytest.raises(ConfigurationError, match="schema_version"):
        ValidationRunConfig(
            inputs=base.inputs,
            output=base.output,
            modules=base.modules,
            schema_version=999,
        )


def test_serialisation_round_trip_is_lossless(tmp_path: Path) -> None:
    config = _config(tmp_path)
    restored = ValidationRunConfig.from_mapping(config.to_dict())
    assert restored == config
    assert restored.fingerprint == config.fingerprint
    assert restored.scientific_fingerprint == config.scientific_fingerprint


def test_configuration_fingerprint_changes_with_output_path(tmp_path: Path) -> None:
    first = _config(tmp_path)
    second = ValidationRunConfig(
        inputs=first.inputs,
        output=OutputConfig(tmp_path / "different-output"),
        modules=first.modules,
        statistics=first.statistics,
        presentation=first.presentation,
        reference_date=first.reference_date,
    )
    assert first.configuration_fingerprint != second.configuration_fingerprint


def test_scientific_fingerprint_ignores_output_and_presentation(tmp_path: Path) -> None:
    first = _config(tmp_path)
    second = ValidationRunConfig(
        inputs=CohortInputConfig(tmp_path / "other-synthea", tmp_path / "other-psynthea"),
        output=OutputConfig(tmp_path / "different-output"),
        modules=first.modules,
        statistics=first.statistics,
        presentation=PresentationConfig(dpi=600, figure_format="svg"),
        reference_date=first.reference_date,
    )
    assert first.configuration_fingerprint != second.configuration_fingerprint
    assert first.scientific_fingerprint == second.scientific_fingerprint


def test_scientific_fingerprint_changes_with_statistics(tmp_path: Path) -> None:
    first = _config(tmp_path)
    second = ValidationRunConfig(
        inputs=first.inputs,
        output=first.output,
        modules=first.modules,
        statistics=StatisticalConfig(top_n_codes=10),
        presentation=first.presentation,
        reference_date=first.reference_date,
    )
    assert first.scientific_fingerprint != second.scientific_fingerprint


def test_fingerprint_remains_alias_for_complete_configuration(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.fingerprint == config.configuration_fingerprint


def test_from_mapping_parses_iso_reference_date(tmp_path: Path) -> None:
    values = _config(tmp_path).to_dict()
    values["reference_date"] = "2024-12-31"
    assert ValidationRunConfig.from_mapping(values).reference_date == date(2024, 12, 31)


def test_from_mapping_wraps_unknown_statistics_field(tmp_path: Path) -> None:
    values = _config(tmp_path).to_dict()
    values["statistics"]["alhpa"] = 0.05
    with pytest.raises(ConfigurationError, match="Invalid statistics"):
        ValidationRunConfig.from_mapping(values)


def test_from_mapping_identifies_invalid_module_index(tmp_path: Path) -> None:
    values = _config(tmp_path).to_dict()
    values["modules"].append({"name": " "})
    with pytest.raises(ConfigurationError, match=r"modules\[1\]"):
        ValidationRunConfig.from_mapping(values)


def test_from_mapping_rejects_non_mapping_root() -> None:
    with pytest.raises(ConfigurationError, match="root"):
        ValidationRunConfig.from_mapping([])


def test_run_plot_config_uses_statistical_alpha(tmp_path: Path) -> None:
    base = _config(tmp_path)
    config = ValidationRunConfig(
        inputs=base.inputs,
        output=base.output,
        modules=base.modules,
        statistics=StatisticalConfig(alpha=0.01),
        presentation=base.presentation,
        reference_date=base.reference_date,
    )
    assert config.to_plot_config().alpha == 0.01


def test_existing_report_requires_explicit_overwrite(tmp_path: Path) -> None:
    _write_cohorts(tmp_path)
    config = _config(tmp_path)
    config.output.root_dir.mkdir()
    config.output.report_path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        config.validate_filesystem()


def test_existing_outputs_are_allowed_when_overwrite_enabled(tmp_path: Path) -> None:
    _write_cohorts(tmp_path)
    config = _config(tmp_path, overwrite=True)
    config.output.figures_dir.mkdir(parents=True)
    (config.output.figures_dir / "old.png").write_text("existing", encoding="utf-8")
    config.validate_filesystem()
