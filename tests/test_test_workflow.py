"""Guard two-worker CI execution without narrowing the test suite."""

from pathlib import Path
import tomllib

from packaging.requirements import Requirement
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
    job = _workflow()["jobs"]["pytest"]
    steps = {step["name"]: step for step in job["steps"]}

    assert steps["Install dependencies"]["run"] == "uv sync --extra test"
    assert steps["Run tests"] == {
        "name": "Run tests",
        "run": "uv run pytest -n 2",
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
