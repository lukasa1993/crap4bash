from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .core import analyze, format_report, run_test_command


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Calculate CRAP scores for Bash functions.")
    value.add_argument("filters", nargs="*")
    value.add_argument("--root", type=Path, default=Path("."))
    value.add_argument("--coverage", type=Path, default=Path("target/coverage"))
    value.add_argument("--test-command", default="kcov target/coverage bats tests")
    value.add_argument("--no-test", action="store_true")
    value.add_argument("--json", action="store_true", dest="json_output")
    value.add_argument("--fail-over", type=float)
    value.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    coverage = args.coverage if args.coverage.is_absolute() else root / args.coverage
    try:
        if not args.no_test:
            if coverage.name == "coverage" and coverage.parent.name == "target":
                shutil.rmtree(coverage, ignore_errors=True)
            coverage.mkdir(parents=True, exist_ok=True)
            run_test_command(args.test_command, root)
        metrics = analyze(root, coverage if coverage.exists() else None, args.filters)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"crap4bash: {error}", file=sys.stderr)
        return 1
    print(json.dumps([metric.to_dict() for metric in metrics], indent=2, sort_keys=True) if args.json_output else format_report(metrics), end="\n" if args.json_output else "")
    return 2 if args.fail_over is not None and any(metric.crap is not None and metric.crap > args.fail_over for metric in metrics) else 0
