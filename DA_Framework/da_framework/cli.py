"""Command line interface for the MAIZSIM IES framework."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .errors import DAFrameworkError
from .workflow import run_juvenile_enum, run_single_ies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run MAIZSIM iterative ensemble smoother experiments."
    )
    parser.add_argument(
        "--config",
        default="maizsim_ies_example.toml",
        help="Path to a TOML configuration file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read config/observations and generate prior ensemble without "
            "running MAIZSIM."
        ),
    )
    parser.add_argument(
        "--juvenile-enum",
        action="store_true",
        help="Run the outer JuvenileLeaves enumeration.",
    )

    args = parser.parse_args(argv)
    try:
        config = load_config(Path(args.config))
        if args.juvenile_enum:
            results = run_juvenile_enum(config, dry_run=args.dry_run)
            for result in results:
                print(
                    "JuvenileLeaves "
                    f"{result.juvenile_leaves}: run_dir={result.run_dir}"
                )
            return 0

        result = run_single_ies(config, dry_run=args.dry_run)
        print(f"run_dir={result.run_dir}")
        print(f"rmse_summary={result.rmse_file}")
        if args.dry_run:
            print("dry_run=true; MAIZSIM executable was not run")
        return 0
    except DAFrameworkError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
