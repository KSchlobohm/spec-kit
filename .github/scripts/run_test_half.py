"""Run one fixed, file-preserving half of the two-worker CI experiment."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def selected_files(root: Path, half: int) -> list[str]:
    if type(half) is not int or half not in (1, 2):
        raise ValueError("half must be 1 or 2")
    manifest = json.loads(
        (root / ".github" / "test-halves.json").read_text(encoding="utf-8")
    )
    if not isinstance(manifest, dict) or set(manifest) != {"1", "2"}:
        raise ValueError("test-halves.json must contain exactly halves 1 and 2")
    for files in manifest.values():
        if not isinstance(files, list) or not files or not all(
            isinstance(path, str) for path in files
        ):
            raise ValueError("each half must be a nonempty list of file paths")
    all_files = manifest["1"] + manifest["2"]
    if len(all_files) != len(set(all_files)):
        raise ValueError("test halves contain duplicate or overlapping files")
    discovered = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("test_*.py")
        if path.is_file()
    }
    if set(all_files) != discovered:
        missing = sorted(discovered - set(all_files))
        unknown = sorted(set(all_files) - discovered)
        raise ValueError(f"test half inventory mismatch: missing={missing}, unknown={unknown}")
    return sorted(manifest[str(half)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--half", type=int, choices=(1, 2), required=True)
    args = parser.parse_args(argv)
    try:
        files = selected_files(REPO_ROOT, args.half)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Test half {args.half}/2: {len(files)} files; exactly two pytest workers", flush=True)
    for path in files:
        print(path, flush=True)
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "-n", "2", "-ra",
            "--junitxml=test-results.xml", *files,
        ],
        cwd=REPO_ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
