#!/usr/bin/env python3
# ----- ------ ----- ----- ------ ----- ----- ------ -----
# OpenSUSI jun1okamura <jun1okamura@gmail.com>
# LICENSE: Apache License Version 2.0
# ----- ------ ----- ----- ------ ----- ----- ------ -----

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_artifact_id(data: dict, name: str) -> Optional[int]:
    # GitHub's list-artifacts API still includes expired artifacts; trying to
    # download one returns a bare 404 from the zip endpoint. Treat an expired
    # match as "not found" so callers (including --allow-missing) behave the
    # same as if the artifact never existed, instead of failing with a
    # confusing curl 404 downstream.
    for artifact in data.get("artifacts", []):
        if artifact.get("name") == name and not artifact.get("expired"):
            return artifact.get("id")

    return None


def find_artifact_status(data: dict, name: str) -> str:
    """Return 'missing', 'expired', or 'ok' for diagnostics."""
    for artifact in data.get("artifacts", []):
        if artifact.get("name") == name:
            return "expired" if artifact.get("expired") else "ok"

    return "missing"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve artifact ID from GitHub API response")
    parser.add_argument("--json-file", required=True, type=Path)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Exit 0 with empty stdout instead of failing when the artifact is not found.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        data = load_json(args.json_file)
        artifact_id = find_artifact_id(data, args.artifact_name)

        if artifact_id is None:
            if args.allow_missing:
                sys.exit(0)

            status = find_artifact_status(data, args.artifact_name)
            if status == "expired":
                raise RuntimeError(
                    f"Artifact expired, cannot download: {args.artifact_name} "
                    "(re-run the source workflow to regenerate it)"
                )
            raise RuntimeError(f"Artifact not found: {args.artifact_name}")

        print(artifact_id)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()