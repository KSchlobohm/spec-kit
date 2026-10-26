from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO

import pytest

_stream: TextIO | None = None


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--phase-timings-output",
        action="store",
        default=None,
        help="Write per-test setup/call/teardown timing rows to this CSV file.",
    )


def pytest_configure(config: pytest.Config) -> None:
    global _stream

    if hasattr(config, "workerinput"):
        return

    output = config.getoption("--phase-timings-output")
    if output is None:
        return

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    _stream = path.open("w", newline="", encoding="utf-8")
    csv.writer(_stream).writerow(
        ("nodeid", "module", "phase", "duration_seconds", "outcome")
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _stream is None:
        return

    csv.writer(_stream).writerow(
        (
            report.nodeid,
            report.location[0],
            report.when,
            f"{report.duration:.9f}",
            report.outcome,
        )
    )
    _stream.flush()


def pytest_unconfigure(config: pytest.Config) -> None:
    global _stream

    if _stream is not None:
        _stream.close()
    _stream = None
