from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import sys

import pytest

from validation.orchestration.models import (
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)
from validation.orchestration.runners import (
    CommandPlan,
    PsyntheaRunner,
    RunnerConfigurationError,
    RunnerIntegrityError,
    SyntheaRunner,
    runner_for,
)
from validation.orchestration.workspace import ExperimentWorkspace


def _simulator_config(
    kind: SimulatorKind,
    workdir: Path,
    *,
    script: Path | None = None,
    arguments: dict | None = None,
    expected: tuple[str, ...] = (),
    timeout: float = 5.0,
) -> SimulatorConfig:
    command = (sys.executable, str(script)) if script else (sys.executable,)
    return SimulatorConfig(
        kind=kind,
        command=command,
        working_directory=workdir,
        output_subdirectory="cohort",
        timeout_seconds=timeout,
        arguments=arguments or {},
        expected_output_files=expected,
    )


def _experiment(
    tmp_path: Path,
    *,
    synthea: SimulatorConfig | None = None,
    psynthea: SimulatorConfig | None = None,
    modules_dir: Path | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        id="exp.runners",
        name="Runner contract",
        cohort=CohortConfig(
            population=25,
            seed=42,
            modules=("hypertension", "diabetes"),
            modules_dir = modules_dir,
            reference_date=date(2026, 1, 1),
            min_age=18,
            max_age=90,
        ),
        simulators=(
            synthea or _simulator_config(SimulatorKind.SYNTHEA, tmp_path),
            psynthea or _simulator_config(SimulatorKind.PSYNTHEA, tmp_path),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.HTML,),
    )

def test_psynthea_default_plan_includes_modules_directory(
    tmp_path: Path,
) -> None:
    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    config = _experiment(
        tmp_path,
        modules_dir=modules_dir,
    )
    runner = PsyntheaRunner(
        config.simulator(SimulatorKind.PSYNTHEA)
    )

    plan = runner.build_plan(
        experiment=config,
        workspace=_workspace(config),
    )

    modules_dir_index = plan.command.index("-d")

    assert plan.command[modules_dir_index + 1] == str(
        modules_dir.resolve()
    )
    assert plan.command.count("-d") == 1
    assert plan.command.count("-m") == 2

def test_synthea_plan_does_not_receive_psynthea_modules_directory(
    tmp_path: Path,
) -> None:
    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    config = _experiment(
        tmp_path,
        modules_dir=modules_dir,
    )
    runner = SyntheaRunner(
        config.simulator(SimulatorKind.SYNTHEA)
    )

    plan = runner.build_plan(
        experiment=config,
        workspace=_workspace(config),
    )

    assert "-d" not in plan.command
    assert "--modules-dir" not in plan.command
    assert plan.command[-2:] == (
        "-m",
        "hypertension,diabetes",
    )

def test_psynthea_custom_template_receives_modules_directory(
    tmp_path: Path,
) -> None:
    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        arguments={
            "command_arguments": (
                "generate",
                "--population={population}",
                "--output={output_dir}",
            ),
        },
    )
    config = _experiment(
        tmp_path,
        psynthea=psynthea,
        modules_dir=modules_dir,
    )

    plan = PsyntheaRunner(psynthea).build_plan(
        experiment=config,
        workspace=_workspace(config),
    )

    assert plan.command[-2:] == (
        "-d",
        str(modules_dir.resolve()),
    )
    assert plan.command.count("-d") == 1

def test_psynthea_custom_template_does_not_duplicate_short_modules_dir_option(
    tmp_path: Path,
) -> None:
    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        arguments={
            "command_arguments": (
                "generate",
                "-d",
                "{modules_dir}",
                "--output={output_dir}",
            ),
        },
    )
    config = _experiment(
        tmp_path,
        psynthea=psynthea,
        modules_dir=modules_dir,
    )

    plan = PsyntheaRunner(psynthea).build_plan(
        experiment=config,
        workspace=_workspace(config),
    )

    assert plan.command.count("-d") == 1

    modules_dir_index = plan.command.index("-d")
    assert plan.command[modules_dir_index + 1] == str(
        modules_dir.resolve()
    )

def test_psynthea_custom_template_does_not_duplicate_long_modules_dir_option(
    tmp_path: Path,
) -> None:
    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        arguments={
            "command_arguments": (
                "generate",
                "--modules-dir={modules_dir}",
                "--output={output_dir}",
            ),
        },
    )
    config = _experiment(
        tmp_path,
        psynthea=psynthea,
        modules_dir=modules_dir,
    )

    plan = PsyntheaRunner(psynthea).build_plan(
        experiment=config,
        workspace=_workspace(config),
    )

    modules_dir_arguments = tuple(
        argument
        for argument in plan.command
        if argument == "-d"
        or argument == "--modules-dir"
        or argument.startswith("--modules-dir=")
    )

    assert modules_dir_arguments == (
        f"--modules-dir={modules_dir.resolve()}",
    )

def _workspace(config: ExperimentConfig) -> ExperimentWorkspace:
    return ExperimentWorkspace.create(config=config, run_id="run-001")


def _script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / f"script_{len(list(tmp_path.glob('script_*.py')))}.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_runner_for_returns_registered_adapter(tmp_path: Path) -> None:
    assert isinstance(
        runner_for(_simulator_config(SimulatorKind.SYNTHEA, tmp_path)),
        SyntheaRunner,
    )
    assert isinstance(
        runner_for(_simulator_config(SimulatorKind.PSYNTHEA, tmp_path)),
        PsyntheaRunner,
    )


def test_runner_rejects_wrong_simulator_configuration(tmp_path: Path) -> None:
    config = _simulator_config(SimulatorKind.PSYNTHEA, tmp_path)
    with pytest.raises(RunnerConfigurationError):
        SyntheaRunner(config)


def test_build_plan_is_deterministic_and_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    config = _experiment(tmp_path)
    workspace = _workspace(config)
    runner = SyntheaRunner(config.simulator(SimulatorKind.SYNTHEA))

    plan = runner.build_plan(experiment=config, workspace=workspace)

    assert plan.command[-6:] == ("-p", "25", "-s", "42", "-m", "hypertension,diabetes")
    assert plan.output_directory.name == "cohort"
    assert not plan.output_directory.exists()


def test_custom_template_renders_all_supported_cohort_fields(tmp_path: Path) -> None:
    custom = {
        "command_arguments": (
            "--population={population}",
            "--seed={seed}",
            "--modules={modules}",
            "--date={reference_date}",
            "--compact-date={reference_date_compact}",
            "--ages={min_age}-{max_age}",
            "--age-range={age_range}",
            "--out={output_dir}",
        ),
        "module_separator": ";",
    }
    synthea = _simulator_config(SimulatorKind.SYNTHEA, tmp_path, arguments=custom)
    config = _experiment(tmp_path, synthea=synthea)
    plan = SyntheaRunner(synthea).build_plan(
        experiment=config,
        workspace=_workspace(config),
    )

    assert "--modules=hypertension;diabetes" in plan.command
    assert "--date=2026-01-01" in plan.command
    assert "--compact-date=20260101" in plan.command
    assert "--ages=18-90" in plan.command
    assert "--age-range=18-90" in plan.command
    assert any(item.startswith("--out=") for item in plan.command)


@pytest.mark.parametrize(
    "template",
    [
        ("{unknown}",),
        ("{population",),
        ("{population!r}",),
        ("{missing.field}",),
    ],
)
def test_invalid_command_templates_fail_closed(tmp_path: Path, template: tuple[str, ...]) -> None:
    synthea = _simulator_config(
        SimulatorKind.SYNTHEA,
        tmp_path,
        arguments={"command_arguments": template},
    )
    config = _experiment(tmp_path, synthea=synthea)
    with pytest.raises(RunnerConfigurationError):
        SyntheaRunner(synthea).build_plan(
            experiment=config,
            workspace=_workspace(config),
        )


def test_build_plan_rejects_workspace_or_runner_configuration_drift(tmp_path: Path) -> None:
    config = _experiment(tmp_path)
    workspace = _workspace(config)
    changed = replace(config, cohort=replace(config.cohort, population=30))
    runner = SyntheaRunner(config.simulator(SimulatorKind.SYNTHEA))

    with pytest.raises(RunnerIntegrityError):
        runner.build_plan(experiment=changed, workspace=workspace)


def test_successful_run_persists_logs_and_hashed_outputs(tmp_path: Path) -> None:
    script = _script(
        tmp_path,
        """
from pathlib import Path
import sys
out = Path(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--out=')))
out.mkdir(parents=True, exist_ok=True)
(out / 'patients.csv').write_text('id\\n1\\n', encoding='utf-8')
print('stdout line')
print('stderr line', file=sys.stderr)
""",
    )
    arguments = {
        "command_arguments": ("--out={output_dir}",),
        "discover_outputs": True,
    }
    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        script=script,
        arguments=arguments,
    )
    config = _experiment(tmp_path, psynthea=psynthea)
    workspace = _workspace(config)

    result = PsyntheaRunner(psynthea).run(
        experiment=config,
        workspace=workspace,
        run_id="run-001",
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.return_code == 0
    assert len(result.artifacts) == 3
    assert all(item.sha256 and item.size_bytes is not None for item in result.artifacts)
    assert result.metadata["discovered_output_count"] == 1


def test_output_artifact_id_is_stable_for_its_relative_path(tmp_path: Path) -> None:
    script = _script(
        tmp_path,
        """
from pathlib import Path
import sys
out = Path(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--out=')))
out.mkdir(parents=True, exist_ok=True)
(out / 'patients.csv').write_text('id\\n1\\n', encoding='utf-8')
""",
    )
    args = {"command_arguments": ("--out={output_dir}",), "discover_outputs": True}
    psynthea = _simulator_config(SimulatorKind.PSYNTHEA, tmp_path, script=script, arguments=args)
    config1 = _experiment(tmp_path / "one", psynthea=replace(psynthea, working_directory=tmp_path))
    config1.output_root.mkdir(parents=True, exist_ok=True)
    result1 = PsyntheaRunner(config1.simulator(SimulatorKind.PSYNTHEA)).run(
        experiment=config1, workspace=_workspace(config1), run_id="run-001"
    )

    config2 = replace(config1, output_root=tmp_path / "two")
    result2 = PsyntheaRunner(config2.simulator(SimulatorKind.PSYNTHEA)).run(
        experiment=config2, workspace=_workspace(config2), run_id="run-001"
    )

    id1 = next(a.id for a in result1.artifacts if a.kind.value == "simulator_output")
    id2 = next(a.id for a in result2.artifacts if a.kind.value == "simulator_output")
    assert id1 == id2


def test_non_zero_exit_is_returned_as_failed_domain_result(tmp_path: Path) -> None:
    script = _script(tmp_path, "import sys; print('bad', file=sys.stderr); raise SystemExit(7)")
    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        script=script,
        arguments={"command_arguments": (), "discover_outputs": False},
    )
    # Empty templates are deliberately invalid, so provide a harmless argument.
    psynthea = replace(psynthea, arguments={"command_arguments": ("--noop",), "discover_outputs": False})
    config = _experiment(tmp_path, psynthea=psynthea)

    result = PsyntheaRunner(psynthea).run(
        experiment=config,
        workspace=_workspace(config),
        run_id="run-001",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.return_code == 7
    assert "return code 7" in result.error_message


def test_missing_executable_is_returned_as_failed_result_with_logs(tmp_path: Path) -> None:
    psynthea = SimulatorConfig(
        kind=SimulatorKind.PSYNTHEA,
        command=(str(tmp_path / "does-not-exist"),),
        working_directory=tmp_path,
        output_subdirectory="cohort",
        arguments={"command_arguments": ("--noop",), "discover_outputs": False},
    )
    config = _experiment(tmp_path, psynthea=psynthea)

    result = PsyntheaRunner(psynthea).run(
        experiment=config,
        workspace=_workspace(config),
        run_id="run-001",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.return_code is None
    assert "not found" in result.error_message
    assert len(result.artifacts) == 2


def test_timeout_terminates_process_and_returns_failed_result(tmp_path: Path) -> None:
    script = _script(tmp_path, "import time; time.sleep(30)")
    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        script=script,
        timeout=0.05,
        arguments={"command_arguments": ("--noop",), "discover_outputs": False},
    )
    config = _experiment(tmp_path, psynthea=psynthea)

    result = PsyntheaRunner(psynthea).run(
        experiment=config,
        workspace=_workspace(config),
        run_id="run-001",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.metadata["timed_out"] is True
    assert "exceeded timeout" in result.error_message


def test_missing_expected_output_fails_even_when_process_succeeds(tmp_path: Path) -> None:
    script = _script(tmp_path, "print('done')")
    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        script=script,
        expected=("patients.csv",),
        arguments={"command_arguments": ("--noop",), "discover_outputs": False},
    )
    config = _experiment(tmp_path, psynthea=psynthea)

    result = PsyntheaRunner(psynthea).run(
        experiment=config,
        workspace=_workspace(config),
        run_id="run-001",
    )

    assert result.status is ExecutionStatus.FAILED
    assert "patients.csv" in result.error_message


def test_symlink_output_is_rejected_as_integrity_violation(tmp_path: Path) -> None:
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks unsupported")
    script = _script(
        tmp_path,
        """
from pathlib import Path
import sys
out = Path(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--out=')))
out.mkdir(parents=True, exist_ok=True)
target = out.parent / 'outside.txt'
target.write_text('outside', encoding='utf-8')
(out / 'escape.csv').symlink_to(target)
""",
    )
    psynthea = _simulator_config(
        SimulatorKind.PSYNTHEA,
        tmp_path,
        script=script,
        arguments={"command_arguments": ("--out={output_dir}",), "discover_outputs": True},
    )
    config = _experiment(tmp_path, psynthea=psynthea)

    with pytest.raises(RunnerIntegrityError):
        PsyntheaRunner(psynthea).run(
            experiment=config,
            workspace=_workspace(config),
            run_id="run-001",
        )


def test_existing_output_directory_is_never_reused(tmp_path: Path) -> None:
    config = _experiment(tmp_path)
    workspace = _workspace(config)
    runner = SyntheaRunner(config.simulator(SimulatorKind.SYNTHEA))
    plan = runner.build_plan(experiment=config, workspace=workspace)
    plan.output_directory.mkdir(parents=True)

    with pytest.raises(RunnerIntegrityError):
        runner.run(experiment=config, workspace=workspace, run_id="run-001")


def test_command_plan_rejects_expected_file_outside_output_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="below output_directory"):
        CommandPlan(
            simulator=SimulatorKind.SYNTHEA,
            command=("synthea",),
            working_directory=tmp_path.resolve(),
            output_directory=(tmp_path / "out").resolve(),
            environment={},
            timeout_seconds=1.0,
            expected_output_files=((tmp_path / "elsewhere.csv").resolve(),),
            discover_outputs=False,
        )