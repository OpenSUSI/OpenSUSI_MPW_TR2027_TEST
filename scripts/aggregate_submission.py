#!/usr/bin/env python3
# ----- ------ ----- ----- ------ ----- ----- ------ -----
# OpenSUSI jun1okamura <jun1okamura@gmail.com>
# LICENSE: Apache License Version 2.0
# ----- ------ ----- ----- ------ ----- ----- ------ -----

from pathlib import Path
import argparse
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aggregate_config import load_config
from aggregate_scan import collect_users
from aggregate_grid import build_positions
from aggregate_gds import aggregate
from aggregate_manifest import write_manifest


DEFAULT_INFO_YAML = Path("info.yaml")
DEFAULT_USERS_DIR = Path("users")
DEFAULT_OUTPUT_GDS = Path("project/ALL_GDSII_MDP.gds")
DEFAULT_OUTPUT_MANIFEST = Path("project/manifest.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate user MDP GDS files into a single top GDS."
    )

    parser.add_argument(
        "--info-yaml",
        type=Path,
        default=DEFAULT_INFO_YAML,
        help=f"Path to info.yaml (default: {DEFAULT_INFO_YAML})",
    )
    parser.add_argument(
        "--users-dir",
        type=Path,
        default=DEFAULT_USERS_DIR,
        help=f"Path to users directory (default: {DEFAULT_USERS_DIR})",
    )
    parser.add_argument(
        "--output-gds",
        type=Path,
        default=DEFAULT_OUTPUT_GDS,
        help=f"Output aggregated GDS path (default: {DEFAULT_OUTPUT_GDS})",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=DEFAULT_OUTPUT_MANIFEST,
        help=f"Output manifest path (default: {DEFAULT_OUTPUT_MANIFEST})",
    )

    return parser.parse_args()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def validate_submission_sequences(users, max_tiles: int) -> None:
    seen: dict[int, str] = {}

    for user in users:
        seq = int(user.submission_sequence)

        if seq <= 0:
            raise RuntimeError(
                f"Invalid submissionSequence: {seq}, order={user.manifest.get('orderId')}, "
                f"path={user.manifest_path}"
            )

        if seq in seen:
            raise RuntimeError(
                f"Duplicate submissionSequence: {seq}, "
                f"orders={seen[seq]} and {user.manifest.get('orderId')}"
            )

        if seq > max_tiles:
            raise RuntimeError(
                f"submissionSequence exceeds grid capacity: seq={seq}, max_tiles={max_tiles}, "
                f"order={user.manifest.get('orderId')}"
            )

        seen[seq] = str(user.manifest.get("orderId"))


def sort_users_by_submission_sequence(users):
    return sorted(users, key=lambda user: user.submission_sequence)


def remap_for_dry_run(users, max_user_tiles: int):
    """
    dryRun: True -- the reticle doesn't need to fill up, so once raw
    submissionSequence values would exceed the grid's user-tile capacity,
    wrap back around to the first user tile (submissionSequence=1) instead
    of erroring. If wrapping makes two submissions land on the same
    effective tile, the one with the larger (more recent) raw sequence wins
    -- the earlier one is silently superseded, as if it had been
    overwritten by a later dry-run test.
    """
    if max_user_tiles <= 0:
        raise RuntimeError(
            f"No tile slots available for users: grid capacity={max_user_tiles}"
        )

    best_raw_by_slot: dict[int, int] = {}
    best_user_by_slot: dict[int, object] = {}

    for user in users:
        raw_seq = int(user.submission_sequence)

        if raw_seq <= 0:
            raise RuntimeError(
                f"Invalid submissionSequence: {raw_seq}, order={user.manifest.get('orderId')}, "
                f"path={user.manifest_path}"
            )

        effective_seq = ((raw_seq - 1) % max_user_tiles) + 1

        if effective_seq not in best_raw_by_slot or raw_seq > best_raw_by_slot[effective_seq]:
            if effective_seq in best_user_by_slot:
                superseded = best_user_by_slot[effective_seq]
                print(
                    f"dryRun: tile slot {effective_seq} reassigned from "
                    f"{superseded.manifest.get('orderId')} (seq={best_raw_by_slot[effective_seq]}) "
                    f"to {user.manifest.get('orderId')} (seq={raw_seq})"
                )
            best_raw_by_slot[effective_seq] = raw_seq
            best_user_by_slot[effective_seq] = user

    remapped = []
    for effective_seq, user in best_user_by_slot.items():
        user.submission_sequence = effective_seq
        remapped.append(user)

    return remapped


def main() -> None:
    args = parse_args()

    ensure_parent_dir(args.output_gds)
    ensure_parent_dir(args.output_manifest)

    config = load_config(args.info_yaml)
    users = collect_users(args.users_dir)

    max_tiles = config.grid_x * config.grid_y

    if config.dry_run:
        max_user_tiles = max_tiles - (1 if config.teg_gds else 0)
        users = remap_for_dry_run(users, max_user_tiles)
    else:
        validate_submission_sequences(users, max_tiles)

    ordered_users = sort_users_by_submission_sequence(users)

    positions = build_positions(
        config.grid_x,
        config.grid_y,
        config.pitch_x,
        config.pitch_y,
    )

    placements = aggregate(
        config=config,
        users=ordered_users,
        positions=positions,
        out_gds=args.output_gds,
    )

    write_manifest(
        path=args.output_manifest,
        config=config,
        placements=placements,
        output_gds=args.output_gds,
    )

    print("DONE")
    print(f"info.yaml   : {args.info_yaml}")
    print(f"users dir   : {args.users_dir}")
    print(f"output GDS  : {args.output_gds}")
    print(f"manifest    : {args.output_manifest}")
    print(f"dry_run     : {config.dry_run}")
    print(f"user count  : {len(ordered_users)}")
    print(f"placements  : {len(placements)}")


if __name__ == "__main__":
    main()