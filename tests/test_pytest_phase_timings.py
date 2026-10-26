from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_TIMINGS_PLUGIN = REPO_ROOT / ".github" / "scripts"


def test_diagnostic_workflow_limits_pytest_to_capped_windows_python314() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["pytest"]
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"]["matrix"] == {
        "os": ["windows-latest"],
        "python-version": ["3.14"],
    }
    steps = {step["name"]: step for step in job["steps"]}
    assert steps["Check out upstream baseline"]["with"] == {
        "repository": "github/spec-kit",
        "ref": "0bd4773e2e268d89bc6c1bf754aa989da9ae2dab",
        "path": "source",
    }
    test_step = steps["Run full pytest suite"]
    assert test_step["working-directory"] == "source"
    assert (
        "uv run pytest -p pytest_phase_timings "
        '--phase-timings-output="$phaseTimingsFile" -n auto --maxschedchunk=25 '
        '--durations=0 --durations-min=0 -ra --junitxml="$junitFile" 2>&1 |'
    ) in test_step["run"]
    assert steps["Upload diagnostic results"]["if"] == "always()"
    assert steps["Upload diagnostic results"]["with"]["path"] == "diagnostic-output/"


def test_phase_timings_plugin_records_all_phases_and_outcomes(tmp_path: Path) -> None:
    sample_tests = tmp_path / "test_sample.py"
    sample_tests.write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def resource():\n"
        "    yield\n"
        "def test_pass(resource):\n"
        "    assert True\n"
        "@pytest.mark.skip(reason='diagnostic smoke test')\n"
        "def test_skip():\n"
        "    assert True\n"
        "def test_fail():\n"
        "    assert False\n",
        encoding="utf-8",
    )
    timings_file = tmp_path / "phase-timings.csv"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        (str(PHASE_TIMINGS_PLUGIN), env.get("PYTHONPATH", ""))
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_phase_timings",
            f"--phase-timings-output={timings_file}",
            "-n",
            "2",
            "--maxschedchunk=25",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    with timings_file.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    passing_test_phases = {
        row["phase"] for row in rows if row["nodeid"] == "test_sample.py::test_pass"
    }
    assert result.returncode == 1, result.stdout + result.stderr
    assert passing_test_phases == {"setup", "call", "teardown"}
    assert any(row["outcome"] == "skipped" for row in rows)
    assert any(row["outcome"] == "failed" for row in rows)
    assert all(float(row["duration_seconds"]) >= 0 for row in rows)
