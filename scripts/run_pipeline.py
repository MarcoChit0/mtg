#!/usr/bin/env python3
"""Project-level CLI for the MTG reproducibility workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from copy import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_RAW_DIR = Path("data/raw/archidekt")
DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_MANIFEST_PATH = Path("experiments/pipeline_run_manifest.json")
DEFAULT_PROCESSED_DRIVE_URL = os.environ.get(
    "ARCHIDEKT_PROCESSED_DRIVE_URL",
    "https://drive.google.com/file/d/1gXCxPeFjxgkNmizWCTU62m-s311B05R0/view?usp=sharing",
)
DEFAULT_EXPERIMENTS_DRIVE_REMOTE = os.environ.get("MTG_EXPERIMENTS_DRIVE_REMOTE", "mtg-experiments:")
DEFAULT_EXPERIMENTS_MANIFEST_URL = os.environ.get("MTG_EXPERIMENTS_MANIFEST_URL", "1MU0AilsDnG11M9pySkDUebLKkJ4a_5kR")

SELECTED_ALGORITHMS = (
    "decision_tree",
    "gradient_boosting",
    "knn",
    "linear_svc",
    "logistic_regression",
    "naive_bayes",
    "random_forest",
)
FEATURE_CHOICES = ("df", "bc")
# Phase D pool — kept symmetric for BC and DF after the 2026-05-19 redesign.
# SVC RBF/Poly were dropped because they don't run in BC.
SPOT_CHECK_ALGORITHMS = (
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "naive_bayes",
    "logistic_regression",
    "linear_svc",
    "knn",
)


@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    command: Optional[List[str]]
    implemented: bool = True
    reason: str = ""
    failure_hint: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def existing_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def python_script(path: str, *args: str) -> List[str]:
    return [sys.executable, path, *args]


def append_option(command: List[str], flag: str, value: Optional[Any]) -> None:
    if value not in (None, ""):
        command.extend([flag, str(value)])


def append_bool(command: List[str], flag: str, enabled: bool) -> None:
    if enabled:
        command.append(flag)


def append_many(command: List[str], flag: str, values: Optional[Sequence[Any]]) -> None:
    if values:
        command.append(flag)
        command.extend(str(value) for value in values)


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def build_restore_processed_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/download_archidekt_processed.py",
        "--out-dir",
        str(args.processed_dir),
        "--report-path",
        str(args.processed_dir / "processed_restore_report.json"),
    )
    append_option(command, "--drive-url", args.processed_drive_url)
    append_option(command, "--file-id", args.processed_file_id)
    append_option(command, "--archive", args.processed_archive)
    append_bool(command, "--force-download", args.force_download)
    append_bool(command, "--overwrite", args.overwrite)
    return Stage("restore_processed", "Restore the frozen processed data snapshot.", command)


def build_restore_raw_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/download_archidekt_raw.py",
        "--out-dir",
        str(args.raw_dir),
        "--processed-dir",
        str(args.processed_dir),
        "--skip-process",
    )
    append_option(command, "--drive-url", args.raw_drive_url)
    append_option(command, "--file-id", args.raw_file_id)
    append_option(command, "--archive", args.raw_archive)
    append_bool(command, "--force-download", args.force_download)
    append_bool(command, "--overwrite", args.overwrite)
    return Stage("restore_raw", "Restore frozen raw Archidekt payloads.", command)


def build_process_raw_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/process_archidekt_raw.py",
        "--raw-dir",
        str(args.raw_dir),
        "--out-dir",
        str(args.processed_dir),
        "--min-views",
        str(args.min_views),
        "--brackets",
        "2",
        "3",
        "4",
        "--workers",
        str(args.workers),
    )
    append_bool(command, "--overwrite", args.process_overwrite or args.overwrite)
    if not args.run_live_y2:
        command.append("--skip-y2")
    return Stage("process_raw", "Process raw payloads into processed JSONL files.", command)


def build_features_stage(args: argparse.Namespace) -> Stage:
    return Stage(
        "build_features",
        "Build deck feature and bag-of-cards files.",
        python_script(
            "scripts/build_features.py",
            "--processed-dir",
            str(args.processed_dir),
            "--raw-dir",
            str(args.raw_dir),
            "--out-dir",
            str(args.processed_dir),
            "--overwrite",
        ),
    )


def build_phase_b_stage(args: argparse.Namespace) -> Stage:
    return Stage(
        "phase_b_eda_divergence",
        "Generate EDA and y1-vs-y2 divergence reports.",
        python_script(
            "scripts/phase_b_eda_divergence.py",
            "--data-dir",
            str(args.processed_dir),
            "--docs-dir",
            str(args.docs_dir),
        ),
    )


def build_phase_c_stage(args: argparse.Namespace) -> Stage:
    return Stage(
        "phase_c_preprocessing",
        "Freeze modelable snapshot ids and refresh preprocessing_report.md.",
        python_script(
            "scripts/phase_c_filter_dataset.py",
            "--features-path",
            str(args.processed_dir / "deck_features.jsonl"),
            "--out-dir",
            str(args.processed_dir),
            "--docs-dir",
            str(args.docs_dir),
        ),
    )


def build_restore_public_experiments_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/sync_experiments_drive.py",
        "download-public",
        "--experiment-dir",
        str(args.experiment_dir),
        "--experiments-manifest-url",
        args.experiments_manifest_url,
    )
    append_many(command, "--models", args.experiment_models)
    append_bool(command, "--overwrite", args.overwrite_experiments)
    return Stage(
        "restore_public_experiments",
        "Restore Phase-E experiment archives from the public manifest.",
        command,
    )


def build_spot_check_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/phase_d_spot_check.py",
        "--processed-dir",
        str(args.processed_dir),
        "--docs-dir",
        str(args.docs_dir),
        "--experiment-dir",
        str(args.experiment_dir / "spot_check"),
    )
    append_many(command, "--seeds", args.seeds)
    append_option(command, "--test-size", args.test_size)
    append_many(command, "--bc-min-df-values", args.bc_min_df_values)
    append_many(command, "--algorithms", args.algorithms)
    append_many(command, "--representations", args.representations)
    append_option(command, "--n-jobs", args.n_jobs)
    append_option(command, "--max-rows", args.max_rows)
    append_bool(command, "--quiet-progress", args.quiet_progress)
    return Stage("phase_d_spot_check", "Run Phase-D spot-checking (N=5 repetitions per combination).", command)


def build_upload_spot_check_bundle_stage(args: argparse.Namespace) -> Stage:
    return Stage(
        "upload_spot_check_bundle",
        "Upload the spot_check bundle to the shared Drive remote.",
        python_script(
            "scripts/sync_experiments_drive.py",
            "upload-bundle",
            "spot_check",
            "--experiment-dir",
            str(args.experiment_dir),
            "--experiments-drive-remote",
            args.experiments_drive_remote,
            "--rclone-bin",
            args.rclone_bin,
        ),
        failure_hint=(
            f"Sem permissão de escrita em {args.experiments_drive_remote} para subir "
            "spot_check. Peça acesso de colaborador ou rode com --run-local."
        ),
    )


def build_check_drive_write_stage(args: argparse.Namespace) -> Stage:
    return Stage(
        "check_drive_write",
        "Check write permission on the experiments Drive remote.",
        python_script(
            "scripts/sync_experiments_drive.py",
            "check-write",
            "--experiments-drive-remote",
            args.experiments_drive_remote,
            "--rclone-bin",
            args.rclone_bin,
        ),
        failure_hint=(
            f"Sem permissão de escrita em {args.experiments_drive_remote}. "
            "Peça acesso de colaborador ou rode com --run-local."
        ),
    )


def build_train_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/phase_e_nested_cv.py",
        "--processed-dir",
        str(args.processed_dir),
        "--docs-dir",
        str(args.docs_dir),
        "--experiment-dir",
        str(args.experiment_dir),
        "--experiments-drive-remote",
        args.experiments_drive_remote,
        "--rclone-bin",
        args.rclone_bin,
    )
    append_option(command, "--model", args.model)
    append_option(command, "--feature", args.feature)
    append_option(command, "--bc-min-df", args.bc_min_df)
    append_option(command, "--outer-splits", args.outer_splits)
    append_option(command, "--inner-splits", args.inner_splits)
    append_many(command, "--repeats", args.repeats)
    append_option(command, "--random-state", args.random_state)
    append_option(command, "--grid-n-jobs", args.grid_n_jobs)
    append_option(command, "--grid-verbose", args.grid_verbose)
    append_option(command, "--estimator-n-jobs", args.estimator_n_jobs)
    append_option(command, "--max-rows", args.max_rows)
    append_option(command, "--max-grid-values", args.max_grid_values)
    append_bool(command, "--use-tfidf", args.use_tfidf)
    append_bool(command, "--run-local", args.run_local)
    append_bool(command, "--no-wait-drive-upload", args.no_wait_drive_upload)
    append_bool(command, "--no-merge-existing-models", args.no_merge_existing_models)
    append_bool(command, "--force-rerun", args.force_rerun)
    append_bool(command, "--from-spot-check", args.from_spot_check)
    append_option(command, "--spot-check-summary", args.spot_check_summary)
    append_bool(command, "--skip-voting", args.skip_voting)
    append_bool(command, "--quiet-progress", args.quiet_progress)
    return Stage("phase_e_nested_cv", "Train Phase-E nested CV models.", command)


def build_publish_manifest_stage(args: argparse.Namespace) -> Stage:
    return Stage(
        "publish_experiments_manifest",
        "Publish the public experiments manifest after Drive uploads.",
        python_script(
            "scripts/sync_experiments_drive.py",
            "publish-manifest",
            "--experiment-dir",
            str(args.experiment_dir),
            "--experiments-drive-remote",
            args.experiments_drive_remote,
            "--rclone-bin",
            args.rclone_bin,
        ),
    )


def build_test_stage() -> Stage:
    return Stage(
        "tests",
        "Run the local unittest suite.",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    )


def build_init_stage_plan(args: argparse.Namespace) -> List[Stage]:
    stages: List[Stage] = []
    if args.data_source == "processed-drive":
        stages.append(build_restore_processed_stage(args))
    elif args.data_source == "raw-drive":
        stages.extend([build_restore_raw_stage(args), build_process_raw_stage(args), build_features_stage(args)])
    elif args.rebuild_features:
        stages.append(build_features_stage(args))

    if not args.skip_reports:
        stages.append(build_phase_b_stage(args))
    stages.append(build_phase_c_stage(args))

    if args.skip_experiment_restore:
        stages.append(Stage(
            "restore_public_experiments",
            "Public experiment restore skipped by request.",
            None,
            reason="skipped_by_--skip-experiment-restore",
        ))
    else:
        stages.append(build_restore_public_experiments_stage(args))

    if args.run_tests:
        stages.append(build_test_stage())
    return stages


def build_spot_check_stage_plan(args: argparse.Namespace) -> List[Stage]:
    stages: List[Stage] = [build_spot_check_stage(args)]
    if not args.run_local:
        # Publish the spot-check selection so collaborators running `train`
        # later read the same A_DF / A_BC sets via --from-spot-check.
        stages.append(build_check_drive_write_stage(args))
        stages.append(build_upload_spot_check_bundle_stage(args))
    return stages


def build_train_stage_plan(args: argparse.Namespace) -> List[Stage]:
    stages: List[Stage] = []
    if not args.run_local:
        stages.append(build_check_drive_write_stage(args))
    stages.append(build_train_stage(args))
    if not args.run_local:
        stages.append(build_publish_manifest_stage(args))
    return stages


def build_stage_plan(args: argparse.Namespace) -> List[Stage]:
    if args.command == "init":
        return build_init_stage_plan(args)
    if args.command == "spot-checking":
        return build_spot_check_stage_plan(args)
    if args.command == "train":
        return build_train_stage_plan(args)
    raise ValueError(f"Unknown command: {args.command}")


def has_local_processed_inputs(args: argparse.Namespace) -> bool:
    return all(existing_file(path) for path in (
        args.processed_dir / "decks.jsonl",
        args.processed_dir / "cards.jsonl",
    ))


def has_initialized_modeling_inputs(args: argparse.Namespace) -> bool:
    return all(existing_file(path) for path in (
        args.processed_dir / "deck_features.jsonl",
        args.processed_dir / "bag_of_cards.jsonl",
        args.processed_dir / "modeling_snapshot_ids.json",
    ))


def resolve_auto_data_source(args: argparse.Namespace) -> argparse.Namespace:
    if getattr(args, "data_source", None) != "auto":
        return args
    resolved = copy(args)
    resolved.data_source = "local" if has_local_processed_inputs(args) else "processed-drive"
    return resolved


def check_inputs(args: argparse.Namespace, stages: Sequence[Stage]) -> None:
    stage_names = {stage.name for stage in stages if stage.command is not None}
    if args.command == "init":
        if args.data_source == "local" and not has_local_processed_inputs(args):
            raise FileNotFoundError(
                "Missing local processed data. Run `uv run run-mtg-pipeline init --data-source processed-drive` "
                "or provide data/processed/archidekt."
            )
        if args.data_source == "processed-drive" and "restore_processed" in stage_names:
            archive = args.processed_archive or Path("processed.zip")
            has_source = bool(args.processed_drive_url or args.processed_file_id or existing_file(archive))
            if not has_source:
                raise ValueError("Processed restore needs --processed-drive-url, --processed-file-id, or processed.zip.")
        if args.data_source == "raw-drive" and "restore_raw" in stage_names:
            archive = args.raw_archive or (args.raw_dir / "Archive.zip")
            has_source = bool(args.raw_drive_url or args.raw_file_id or existing_file(archive))
            if not has_source:
                raise ValueError("Raw restore needs --raw-drive-url, --raw-file-id, or Archive.zip.")
    elif args.command in {"spot-checking", "train"} and not has_initialized_modeling_inputs(args):
        raise FileNotFoundError(
            "Init has not been completed for modeling. Run `uv run run-mtg-pipeline init` first."
        )


def print_plan(stages: Sequence[Stage]) -> None:
    print("Pipeline plan:")
    for stage in stages:
        if stage.command is None:
            print(f"  - {stage.name}: skipped ({stage.reason or stage.description})")
        else:
            print(f"  - {stage.name}: {' '.join(stage.command)}")


def run_stage(stage: Stage, *, dry_run: bool = False) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "name": stage.name,
        "description": stage.description,
        "implemented": stage.implemented,
        "reason": stage.reason,
        "failure_hint": stage.failure_hint,
        "command": stage.command,
        "status": None,
        "started_at": None,
        "finished_at": None,
        "elapsed_seconds": None,
        "returncode": None,
    }
    if stage.command is None:
        record["status"] = "skipped"
        return record
    if dry_run:
        record["status"] = "dry_run"
        return record

    record["started_at"] = utc_now_iso()
    started = time.monotonic()
    print(f"\n==> {stage.name}")
    print(" ".join(stage.command))
    completed = subprocess.run(stage.command, check=False)
    record["finished_at"] = utc_now_iso()
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    record["returncode"] = completed.returncode
    record["status"] = "ok" if completed.returncode == 0 else "failed"
    if completed.returncode != 0:
        if stage.failure_hint:
            raise RuntimeError(stage.failure_hint)
        raise subprocess.CalledProcessError(completed.returncode, stage.command)
    return record


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--list-stages", action="store_true", help="Print the generated plan and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print and record the plan without executing commands.")


def add_init_args(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)
    parser.add_argument(
        "--data-source",
        choices=["auto", "local", "processed-drive", "raw-drive"],
        default="processed-drive",
        help="Where init starts. Default restores the frozen processed snapshot.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--raw-drive-url", default="")
    parser.add_argument("--raw-file-id", default="")
    parser.add_argument("--raw-archive", type=Path, default=None)
    parser.add_argument("--processed-drive-url", default=DEFAULT_PROCESSED_DRIVE_URL)
    parser.add_argument("--processed-file-id", default="")
    parser.add_argument("--processed-archive", type=Path, default=None)
    parser.add_argument("--experiments-manifest-url", default=DEFAULT_EXPERIMENTS_MANIFEST_URL)
    parser.add_argument("--experiment-models", nargs="+", default=[])
    parser.add_argument("--skip-experiment-restore", action="store_true")
    parser.add_argument("--overwrite-experiments", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--process-overwrite", action="store_true")
    parser.add_argument("--run-live-y2", action="store_true", help="Opt in to live EDHPowerLevel queries.")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-views", type=int, default=1000)
    parser.add_argument("--rebuild-features", action="store_true")
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument("--run-tests", action="store_true")


def add_spot_check_args(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[1, 2, 3, 4, 5],
        help="Seeds for the N=5 spot-check repetitions (default 1..5).",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--bc-min-df-values", "--min-df-values", dest="bc_min_df_values", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--algorithms", nargs="+", choices=SPOT_CHECK_ALGORITHMS, default=list(SPOT_CHECK_ALGORITHMS))
    parser.add_argument("--representations", nargs="+", choices=["DF", "BC"], default=["DF", "BC"])
    parser.add_argument("--n-jobs", type=int, default=-1)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument(
        "--run-local",
        action="store_true",
        help="Do not publish the spot_check bundle to the shared Drive remote.",
    )
    parser.add_argument(
        "--experiments-drive-remote",
        default=DEFAULT_EXPERIMENTS_DRIVE_REMOTE,
        help="rclone remote root for collaborator uploads (used only when publishing the spot_check bundle).",
    )
    parser.add_argument("--rclone-bin", default="rclone")


def add_train_args(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)
    parser.add_argument("--model", choices=SELECTED_ALGORITHMS, default=None)
    parser.add_argument("--feature", choices=FEATURE_CHOICES, default=None)
    parser.add_argument("--experiments-drive-remote", default=DEFAULT_EXPERIMENTS_DRIVE_REMOTE)
    parser.add_argument("--rclone-bin", default="rclone")
    parser.add_argument("--run-local", action="store_true")
    parser.add_argument("--no-wait-drive-upload", action="store_true")
    parser.add_argument("--bc-min-df", type=int, default=10)
    parser.add_argument("--use-tfidf", action="store_true")
    parser.add_argument("--outer-splits", type=int, default=5)
    parser.add_argument("--inner-splits", type=int, default=3)
    parser.add_argument("--repeats", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--grid-n-jobs", type=int, default=1)
    parser.add_argument("--grid-verbose", type=int, default=0)
    parser.add_argument("--estimator-n-jobs", type=int, default=-1)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-grid-values", type=int, default=None)
    parser.add_argument("--no-merge-existing-models", action="store_true")
    parser.add_argument("--force-rerun", action="store_true")
    parser.add_argument(
        "--from-spot-check",
        dest="from_spot_check",
        action="store_true",
        default=True,
        help="Read top-5 per representation from spot-check summary and train each union algorithm in both reps (default).",
    )
    parser.add_argument(
        "--no-from-spot-check",
        dest="from_spot_check",
        action="store_false",
        help="Ignore spot-check selection and train --algorithms × --representations directly.",
    )
    parser.add_argument(
        "--spot-check-summary",
        type=Path,
        default=Path("experiments/spot_check/summary.json"),
    )
    parser.add_argument(
        "--skip-voting",
        action="store_true",
        help="Skip the post-training voting ensembles (E.5).",
    )
    parser.add_argument("--quiet-progress", action="store_true")


def normalize_argv(argv: Optional[List[str]]) -> List[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    commands = {"init", "spot-checking", "train"}
    if not values:
        return ["init"]
    if values[0] not in commands:
        return ["init", *values]
    return values


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project interface for the MTG ML pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize processed data, reports, preprocessing, and public experiments.")
    add_init_args(init)

    spot = subparsers.add_parser("spot-checking", help="Run Phase-D spot-checking after init.")
    add_spot_check_args(spot)

    train = subparsers.add_parser("train", help="Run Phase-E nested CV training after init.")
    add_train_args(train)
    return parser.parse_args(normalize_argv(argv))


def run(args: argparse.Namespace) -> Dict[str, Any]:
    if args.command == "init":
        args = resolve_auto_data_source(args)
    stages = build_stage_plan(args)
    if args.list_stages:
        print_plan(stages)
        return {"status": "listed", "command": args.command, "stages": [stage.name for stage in stages]}

    check_inputs(args, stages)
    print_plan(stages)

    manifest: Dict[str, Any] = {
        "started_at": utc_now_iso(),
        "finished_at": None,
        "status": "running",
        "command": args.command,
        "parameters": jsonable(vars(args)),
        "stages": [],
    }
    try:
        for stage in stages:
            record = run_stage(stage, dry_run=args.dry_run)
            manifest["stages"].append(record)
            write_manifest(args.manifest_path, manifest)
        manifest["status"] = "ok"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        raise
    finally:
        manifest["finished_at"] = utc_now_iso()
        write_manifest(args.manifest_path, manifest)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        run(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return int(exc.returncode or 1)
    if not args.list_stages:
        print(f"\nManifest written to {args.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
