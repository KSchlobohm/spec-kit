"""Fork-only reference fixture for unsupported versus missing CLI diagnostics."""

from pathlib import Path

import pytest

from specify_cli.integrations import get_integration
from specify_cli.workflows.base import StepContext, StepStatus
from specify_cli.workflows.steps.command import CommandStep
from specify_cli.workflows.steps.prompt import PromptStep


@pytest.mark.parametrize(
    ("step_class", "step_config"),
    [
        (CommandStep, {"command": "speckit.specify"}),
        (PromptStep, {"prompt": "hello"}),
    ],
    ids=["command", "prompt"],
)
@pytest.mark.parametrize("integration", ["bob", "claude"], ids=["unsupported", "missing"])
def test_dispatch_diagnostic(step_class, step_config, integration, monkeypatch):
    impl = get_integration(integration)
    assert impl is not None
    if integration == "bob":
        assert impl.build_exec_args("hello") is None
    else:
        assert impl.build_exec_args("hello")

    def which(executable):
        return str(Path.cwd() / "fixture-bob") if executable == "bob" else None

    def unexpected_process(*args, **kwargs):
        pytest.fail("The diagnostic fixture must never execute an integration CLI")

    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr("subprocess.run", unexpected_process)
    result = step_class().execute(
        {"id": "diagnostic", "integration": integration, **step_config},
        StepContext(project_root=str(Path.cwd())),
    )

    assert result.status == StepStatus.FAILED
    assert result.output["dispatched"] is False
    assert result.output["exit_code"] == 1
    assert result.error
    if integration == "bob":
        assert "does not support" in result.error
        assert "dispatch" in result.error
        assert "CLI not found or not installed" not in result.error
    else:
        assert "CLI not found or not installed" in result.error
