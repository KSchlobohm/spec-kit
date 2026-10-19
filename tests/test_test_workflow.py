"""Guard the fixed suite halves and two-worker CI experiment."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib
import xml.etree.ElementTree as ET

from packaging.requirements import Requirement
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent


def _workflow():
    return yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )


def test_pytest_keeps_all_six_os_python_combinations():
    workflow = _workflow()
    job = workflow["jobs"]["pytest"]

    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"] == {
        "matrix": {
            "os": ["ubuntu-latest", "windows-latest", "macos-latest"],
            "python-version": ["3.13", "3.14"],
        }
    }
    assert "if" not in job
    assert "continue-on-error" not in job


def test_pytest_runs_full_suite_with_exactly_two_workers_and_no_failure_fallback():
    """The full suite is now accounted for across the two fixed halves."""
    job = _workflow()["jobs"]["pytest"]
    steps = {step["name"]: step for step in job["steps"]}

    assert steps["Install dependencies"]["run"] == "uv sync --extra test"
    assert steps["Run tests"] == {
        "name": "Run tests",
        "run": "uv run python .github/scripts/run_test_half.py --half 1",
    }
    assert steps["Upload test results"] == {
        "name": "Upload test results",
        "if": "${{ always() }}",
        "uses": "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "with": {
            "name": "test-half-1-${{ matrix.os }}-python-${{ matrix.python-version }}",
            "path": "test-results.xml",
            "if-no-files-found": "error",
        },
    }
    assert "env" not in job
    assert "env" not in _workflow()
    with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    options = config["tool"]["pytest"]["ini_options"]
    assert options["testpaths"] == ["tests"]
    assert options["addopts"] == ["-v", "--strict-markers", "--tb=short"]


def test_xdist_is_a_test_only_dependency_in_the_audited_snapshot():
    with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    test_requirements = {
        Requirement(value).name
        for value in project["optional-dependencies"]["test"]
    }
    runtime_requirements = {Requirement(value).name for value in project["dependencies"]}

    assert {"pytest", "pytest-cov", "pytest-xdist"} <= test_requirements
    assert "pytest-xdist" not in runtime_requirements
    snapshot = (REPO_ROOT / ".github" / "security-audit-requirements.txt").read_text(
        encoding="utf-8"
    )
    assert "\npytest-xdist==" in snapshot
    assert "\nexecnet==" in snapshot


def test_ruff_job_is_preserved():
    job = _workflow()["jobs"]["ruff"]
    steps = {step["name"]: step for step in job["steps"]}

    assert job["runs-on"] == "ubuntu-latest"
    assert steps["Set up Python"]["with"]["python-version"] == "3.14"
    assert steps["Run ruff check"]["run"] == "uvx ruff@0.15.0 check src tests"
    assert "if" not in job
    assert "continue-on-error" not in job
    assert "continue-on-error" not in steps["Run ruff check"]


@pytest.fixture
def selector():
    spec = importlib.util.spec_from_file_location(
        "run_test_half", REPO_ROOT / ".github" / "scripts" / "run_test_half.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def partition_root(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("test_a.py", "test_b.py"):
        (tmp_path / "tests" / name).write_text("def test_ok(): pass\n")
    (tmp_path / ".github" / "test-halves.json").write_text(
        json.dumps({"1": ["tests/test_a.py"], "2": ["tests/test_b.py"]}),
        encoding="utf-8",
    )
    return tmp_path


def test_halves_cover_every_file_exactly_once(selector):
    first = selector.selected_files(REPO_ROOT, 1)
    second = selector.selected_files(REPO_ROOT, 2)
    assert first and second
    assert not set(first) & set(second)
    assert set(first + second) == {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "tests").rglob("test_*.py")
    }


@pytest.mark.parametrize("half,expected", [(1, "tests/test_a.py"), (2, "tests/test_b.py")])
def test_selects_only_requested_half(selector, partition_root, half, expected):
    assert selector.selected_files(partition_root, half) == [expected]


@pytest.mark.parametrize("half", [0, 3, -1, "1", True])
def test_rejects_invalid_half(selector, partition_root, half):
    with pytest.raises(ValueError, match="half must"):
        selector.selected_files(partition_root, half)


@pytest.mark.parametrize(
    "manifest,reason",
    [
        ([], "exactly halves"),
        ({"1": ["tests/test_a.py"]}, "exactly halves"),
        ({"1": [], "2": ["tests/test_b.py"]}, "nonempty"),
        ({"1": "tests/test_a.py", "2": ["tests/test_b.py"]}, "nonempty"),
        ({"1": [1], "2": ["tests/test_b.py"]}, "nonempty"),
        ({"1": ["tests/test_a.py"] * 2, "2": ["tests/test_b.py"]}, "duplicate"),
        ({"1": ["tests/test_a.py"], "2": ["tests/test_a.py"]}, "overlapping"),
        ({"1": ["../test_a.py"], "2": ["tests/test_b.py"]}, "inventory mismatch"),
        ({"1": ["tests/test_missing.py"], "2": ["tests/test_b.py"]}, "inventory mismatch"),
    ],
)
def test_rejects_invalid_selection(selector, partition_root, manifest, reason):
    (partition_root / ".github" / "test-halves.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=reason):
        selector.selected_files(partition_root, 1)


def test_rejects_unassigned_new_file(selector, partition_root):
    (partition_root / "tests" / "test_new.py").touch()
    with pytest.raises(ValueError, match="missing=.*test_new"):
        selector.selected_files(partition_root, 1)


@pytest.mark.parametrize("half", [1, 2])
@pytest.mark.parametrize("exit_code", [0, 1, 5])
def test_runner_keeps_two_workers_and_propagates_failure(
    selector, partition_root, monkeypatch, capsys, half, exit_code
):
    monkeypatch.setattr(selector, "REPO_ROOT", partition_root)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, exit_code)

    monkeypatch.setattr(selector.subprocess, "run", run)
    assert selector.main(["--half", str(half)]) == exit_code
    files = selector.selected_files(partition_root, half)
    assert calls == [(
        [
            selector.sys.executable, "-m", "pytest", "-n", "2", "-ra",
            "--junitxml=test-results.xml", *files,
        ],
        {"cwd": partition_root, "check": False},
    )]
    assert files[0] in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [[], ["--half", "0"], ["--half", "3"], ["--half", "x"]])
def test_cli_rejects_invalid_half_before_launch(selector, monkeypatch, arguments):
    monkeypatch.setattr(
        selector.subprocess, "run", lambda *args, **kwargs: pytest.fail("launched pytest")
    )
    with pytest.raises(SystemExit) as exc:
        selector.main(arguments)
    assert exc.value.code == 2


@pytest.mark.parametrize("contents", ["{", '{"1": [], "2": []}', None])
def test_cli_reports_invalid_or_missing_manifest(
    selector, partition_root, monkeypatch, capsys, contents
):
    monkeypatch.setattr(selector, "REPO_ROOT", partition_root)
    if contents is None:
        monkeypatch.setattr(selector, "REPO_ROOT", partition_root / "missing")
    else:
        (partition_root / ".github" / "test-halves.json").write_text(
            contents, encoding="utf-8"
        )
    monkeypatch.setattr(
        selector.subprocess, "run", lambda *args, **kwargs: pytest.fail("launched pytest")
    )
    with pytest.raises(SystemExit) as exc:
        selector.main(["--half", "1"])
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("half,exit_code,outcome", [(1, 0, "1 passed"), (2, 1, "1 failed")])
def test_real_runner_selects_half_and_writes_results(
    selector, partition_root, half, exit_code, outcome
):
    script = partition_root / ".github" / "scripts" / "run_test_half.py"
    script.parent.mkdir()
    script.write_text(
        (REPO_ROOT / ".github" / "scripts" / "run_test_half.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (partition_root / "tests" / "test_b.py").write_text(
        "def test_failure(): assert False\n", encoding="utf-8"
    )
    result = subprocess.run(
        [selector.sys.executable, str(script), "--half", str(half)],
        cwd=partition_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert outcome in result.stdout
    assert "2 workers" in result.stdout
    cases = ET.parse(partition_root / "test-results.xml").findall(".//testcase")
    assert len(cases) == 1
    assert cases[0].attrib["name"] == ("test_ok" if half == 1 else "test_failure")
