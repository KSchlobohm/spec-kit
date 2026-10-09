"""CLI adapter for ``specify version``."""

from __future__ import annotations

import json

import typer

from . import _operation_version
from ._console import console
from ._operation_version import (
    VersionResult,
    _feature_capabilities,
    _openssl_version,
    collect_version_result,
)

platform = _operation_version.platform

_INTERNAL_ERROR_MESSAGE = "Unable to collect version information."


def _json_result(cli_version: str) -> dict[str, object]:
    """Collect the complete machine-readable version result."""
    result = collect_version_result(
        cli_version_getter=lambda: cli_version,
        openssl_version_getter=_openssl_version,
        feature_capabilities_getter=_feature_capabilities,
    )
    return _result_payload(result)


def _result_payload(result: VersionResult) -> dict[str, object]:
    """Map a complete operation result to the established CLI JSON shape."""
    if result.runtime is None or result.system is None:
        raise ValueError("Complete version information is required.")

    return {
        "cli_version": result.cli_version,
        "runtime": {
            "python": result.runtime.python,
            "openssl": result.runtime.openssl,
        },
        "system": {
            "platform": result.system.platform,
            "architecture": result.system.architecture,
            "os_version": result.system.os_version,
        },
        "features": result.features,
    }


def _serialize_json(payload: dict[str, object]) -> str:
    """Serialize one JSON envelope without terminal formatting."""
    return json.dumps(payload, indent=2)


def version(
    features: bool = typer.Option(
        False,
        "--features",
        help="Show local CLI feature capabilities.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit complete version information as JSON.",
    ),
) -> None:
    """Display the CLI version; use --json for complete system information."""
    from . import get_speckit_version

    if json_output:
        try:
            result = collect_version_result(
                cli_version_getter=get_speckit_version,
                openssl_version_getter=_openssl_version,
                feature_capabilities_getter=_feature_capabilities,
            )
            payload = _result_payload(result)
            rendered = _serialize_json(payload)
        except Exception:  # noqa: BLE001
            # JSON mode must normalize every unexpected command failure.
            failure = {
                "error": {
                    "code": "internal_error",
                    "message": _INTERNAL_ERROR_MESSAGE,
                    "details": {},
                }
            }
            typer.echo(_serialize_json(failure), err=True)
            raise typer.Exit(1)

        typer.echo(rendered)
        return

    if features:
        result = collect_version_result(
            include_environment=False,
            cli_version_getter=get_speckit_version,
            feature_capabilities_getter=_feature_capabilities,
        )
        console.print(f"Spec Kit CLI: {result.cli_version}")
        console.print()
        console.print("Features:")
        for key, enabled in result.features.items():
            label = key.replace("_", " ")
            console.print(f"- {label}: {'yes' if enabled else 'no'}")
        return

    result = collect_version_result(
        include_environment=False,
        cli_version_getter=get_speckit_version,
        feature_capabilities_getter=_feature_capabilities,
    )
    console.print(f"Spec Kit CLI: {result.cli_version}")


def register(app: typer.Typer) -> None:
    """Register ``specify version`` on the root application."""
    app.command()(version)
