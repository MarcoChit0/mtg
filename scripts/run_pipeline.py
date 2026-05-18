#!/usr/bin/env python3
"""Project-level reproducibility runner.

This is the growing "main script" for the project. It runs every implemented
stage in order, records a manifest, and keeps placeholders for phases that are
planned but not implemented yet.
"""

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
from typing import Any, Dict, Iterable, List, Optional, Sequence


DEFAULT_RAW_DIR = Path("data/raw/archidekt")
DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents")
DEFAULT_MANIFEST_PATH = Path("experiments/pipeline_run_manifest.json")
DEFAULT_PROCESSED_DRIVE_URL = os.environ.get(
    "ARCHIDEKT_PROCESSED_DRIVE_URL",
    "https://drive.google.com/file/d/1gXCxPeFjxgkNmizWCTU62m-s311B05R0/view?usp=sharing",
)

FUTURE_STAGES = (
    "phase_f_best_models",
    "phase_g_model_vs_calculator",
    "phase_h_interpretability",
    "phase_i_article",
    "phase_j_ood",
    "phase_k_stacking",
)


@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    command: Optional[List[str]]
    implemented: bool = True
    reason: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def existing_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def python_script(path: str, *args: str) -> List[str]:
    return [sys.executable, path, *args]


def _append_option(command: List[str], flag: str, value: Optional[Any]) -> None:
    if value not in (None, ""):
        command.extend([flag, str(value)])


def _append_bool(command: List[str], flag: str, enabled: bool) -> None:
    if enabled:
        command.append(flag)


def build_restore_processed_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/download_archidekt_processed.py",
        "--out-dir",
        str(args.processed_dir),
        "--report-path",
        str(args.processed_dir / "processed_restore_report.json"),
    )
    _append_option(command, "--drive-url", args.processed_drive_url)
    _append_option(command, "--file-id", args.processed_file_id)
    _append_option(command, "--archive", args.processed_archive)
    _append_bool(command, "--force-download", args.force_download)
    _append_bool(command, "--overwrite", args.overwrite)
    return Stage(
        "restore_processed",
        "Restore frozen processed data from a processed.zip archive or Google Drive link.",
        command,
    )


def build_restore_raw_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/download_archidekt_raw.py",
        "--out-dir",
        str(args.raw_dir),
        "--processed-dir",
        str(args.processed_dir),
        "--skip-process",
    )
    _append_option(command, "--drive-url", args.raw_drive_url)
    _append_option(command, "--file-id", args.raw_file_id)
    _append_option(command, "--archive", args.raw_archive)
    _append_bool(command, "--force-download", args.force_download)
    _append_bool(command, "--overwrite", args.overwrite)
    return Stage(
        "restore_raw",
        "Restore frozen Archidekt raw payloads from Archive.zip or Google Drive.",
        command,
    )


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
    _append_bool(command, "--overwrite", args.process_overwrite or args.overwrite)
    if not args.run_live_y2:
        command.append("--skip-y2")
    return Stage(
        "process_raw",
        "Process restored raw payloads into decks/cards JSONL; live y2 is opt-in.",
        command,
    )


def build_features_stage(args: argparse.Namespace) -> Stage:
    command = python_script(
        "scripts/build_features.py",
        "--processed-dir",
        str(args.processed_dir),
        "--raw-dir",
        str(args.raw_dir),
        "--out-dir",
        str(args.processed_dir),
        "--overwrite",
    )
    return Stage(
        "build_features",
        "Build deck_features.jsonl and bag_of_cards.jsonl.",
        command,
    )


def build_stage_plan(args: argparse.Namespace) -> List[Stage]:
    stages: List[Stage] = []
    if args.data_source == "processed-drive":
        stages.append(build_restore_processed_stage(args))
    elif args.data_source == "raw-drive":
        stages.append(build_restore_raw_stage(args))
        stages.append(build_process_raw_stage(args))

    if args.data_source != "processed-drive" or args.rebuild_features:
        stages.append(build_features_stage(args))
    elif args.data_source == "processed-drive":
        stages.append(Stage(
            "build_features",
            "Skipped by default for processed snapshots to preserve frozen feature values; use --rebuild-features to rerun.",
            None,
            implemented=True,
            reason="skipped_preserve_processed_snapshot",
        ))

    if not args.skip_reports:
        stages.append(Stage(
            "phase_b_eda_divergence",
            "Generate EDA and direct y1-vs-y2 divergence reports.",
            python_script(
                "scripts/phase_b_eda_divergence.py",
                "--data-dir",
                str(args.processed_dir),
                "--docs-dir",
                str(args.docs_dir),
            ),
        ))

    stages.append(Stage(
        "phase_c_preprocessing",
        "Freeze modelable snapshot ids and excluded deck audit rows.",
        python_script(
            "scripts/phase_c_filter_dataset.py",
            "--features-path",
            str(args.processed_dir / "deck_features.jsonl"),
            "--out-dir",
            str(args.processed_dir),
        ),
    ))

    if args.run_tests:
        stages.append(Stage(
            "tests",
            "Run the local unittest suite.",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ))

    if args.run_spot_check:
        stages.append(Stage(
            "phase_d_spot_check",
            "Run Phase-D spot-checking across candidate algorithms.",
            python_script(
                "scripts/phase_d_spot_check.py",
                "--processed-dir",
                str(args.processed_dir),
                "--docs-dir",
                str(args.docs_dir),
            ),
        ))
    else:
        stages.append(Stage(
            "phase_d_spot_check",
            "Implemented but not run by default because it trains multiple models; use --run-spot-check.",
            None,
            implemented=True,
            reason="skipped_use_--run-spot-check",
        ))

    if args.run_nested_cv:
        stages.append(Stage(
            "phase_e_nested_cv",
            "Run Phase-E nested cross-validation for the selected 10 models.",
            python_script(
                "scripts/phase_e_nested_cv.py",
                "--processed-dir",
                str(args.processed_dir),
                "--docs-dir",
                str(args.docs_dir),
                "--experiment-dir",
                str(args.experiment_dir),
            ),
        ))
    else:
        stages.append(Stage(
            "phase_e_nested_cv",
            "Implemented but not run by default because full nested CV is expensive; use --run-nested-cv.",
            None,
            implemented=True,
            reason="skipped_use_--run-nested-cv",
        ))

    for name in FUTURE_STAGES:
        stages.append(Stage(
            name,
            "Planned in documents/action_plan.md; not implemented yet.",
            None,
            implemented=False,
            reason="not_implemented_yet",
        ))
    return stages


def has_local_processed_inputs(args: argparse.Namespace) -> bool:
    return all(existing_file(path) for path in (
        args.processed_dir / "decks.jsonl",
        args.processed_dir / "cards.jsonl",
    ))


def resolve_auto_data_source(args: argparse.Namespace) -> argparse.Namespace:
    if args.data_source != "auto":
        return args
    resolved = copy(args)
    resolved.data_source = "local" if has_local_processed_inputs(args) else "processed-drive"
    return resolved


def selected_stages(stages: Sequence[Stage], names: Sequence[str]) -> List[Stage]:
    if not names:
        return list(stages)
    wanted = set(names)
    known = {stage.name for stage in stages}
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(f"Unknown stage(s): {', '.join(unknown)}")
    return [stage for stage in stages if stage.name in wanted]


def check_inputs(args: argparse.Namespace, stages: Sequence[Stage]) -> None:
    stage_names = {stage.name for stage in stages if stage.command is not None}
    if args.data_source == "local":
        required = [
            args.processed_dir / "decks.jsonl",
            args.processed_dir / "cards.jsonl",
        ]
        if "build_features" not in stage_names:
            required.extend([
                args.processed_dir / "deck_features.jsonl",
                args.processed_dir / "bag_of_cards.jsonl",
            ])
        missing = [str(path) for path in required if not existing_file(path)]
        if missing:
            raise FileNotFoundError(
                "Missing local input file(s). Restore data first with "
                "`uv run run-mtg-pipeline --data-source processed-drive ...` "
                "or `--data-source raw-drive ...`. Missing: "
                + ", ".join(missing)
            )
    if args.data_source == "processed-drive":
        archive = args.processed_archive or Path("processed.zip")
        has_source = bool(args.processed_drive_url or args.processed_file_id or existing_file(archive))
        if not has_source:
            raise ValueError(
                "Processed restore needs --processed-drive-url, --processed-file-id, "
                "or an existing processed.zip archive."
            )
    if args.data_source == "raw-drive":
        archive = args.raw_archive or (args.raw_dir / "Archive.zip")
        has_source = bool(args.raw_drive_url or args.raw_file_id or existing_file(archive))
        if not has_source:
            raise ValueError(
                "Raw restore needs --raw-drive-url, --raw-file-id, or an existing Archive.zip."
            )


def print_plan(stages: Sequence[Stage]) -> None:
    print("Pipeline plan:")
    for stage in stages:
        if stage.command is None:
            status = "pending" if not stage.implemented else "skipped"
            print(f"  - {stage.name}: {status} ({stage.reason or stage.description})")
        else:
            print(f"  - {stage.name}: {' '.join(stage.command)}")


def run_stage(stage: Stage, *, dry_run: bool = False) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "name": stage.name,
        "description": stage.description,
        "implemented": stage.implemented,
        "reason": stage.reason,
        "command": stage.command,
        "status": None,
        "started_at": None,
        "finished_at": None,
        "elapsed_seconds": None,
        "returncode": None,
    }
    if stage.command is None:
        record["status"] = "pending" if not stage.implemented else "skipped"
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
        raise subprocess.CalledProcessError(completed.returncode, stage.command)
    return record


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the implemented MTG project pipeline and record a reproducibility manifest.",
    )
    parser.add_argument(
        "--data-source",
        choices=["auto", "local", "processed-drive", "raw-drive"],
        default="auto",
        help="Where to start. auto uses local processed data when present; otherwise it restores the frozen processed snapshot.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--raw-drive-url", default="")
    parser.add_argument("--raw-file-id", default="")
    parser.add_argument("--raw-archive", type=Path, default=None)
    parser.add_argument("--processed-drive-url", default=DEFAULT_PROCESSED_DRIVE_URL)
    parser.add_argument("--processed-file-id", default="")
    parser.add_argument("--processed-archive", type=Path, default=None)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--process-overwrite", action="store_true")
    parser.add_argument("--run-live-y2", action="store_true", help="Opt in to live EDHPowerLevel queries for raw processing.")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-views", type=int, default=1000)
    parser.add_argument(
        "--rebuild-features",
        action="store_true",
        help="Rebuild deck_features/bag_of_cards even after restoring processed data.",
    )
    parser.add_argument("--skip-reports", action="store_true", help="Skip Phase-B EDA/divergence report generation.")
    parser.add_argument("--run-tests", action="store_true", help="Run unittest at the end.")
    parser.add_argument("--run-spot-check", action="store_true", help="Run Phase-D spot-checking after Phase C.")
    parser.add_argument("--run-nested-cv", action="store_true", help="Run Phase-E nested CV after Phase D/C.")
    parser.add_argument("--only", nargs="+", default=[], help="Run only the named stage(s) from the generated plan.")
    parser.add_argument("--list-stages", action="store_true", help="Print the generated plan and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print and record the plan without executing commands.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--experiment-dir", type=Path, default=Path("experiments"))
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    args = resolve_auto_data_source(args)
    all_stages = build_stage_plan(args)
    stages = selected_stages(all_stages, args.only)
    if args.list_stages:
        print_plan(stages)
        return {"status": "listed", "stages": [stage.name for stage in stages]}

    check_inputs(args, stages)
    print_plan(stages)

    manifest: Dict[str, Any] = {
        "started_at": utc_now_iso(),
        "finished_at": None,
        "status": "running",
        "parameters": {
            "data_source": args.data_source,
            "raw_dir": str(args.raw_dir),
            "processed_dir": str(args.processed_dir),
            "docs_dir": str(args.docs_dir),
            "rebuild_features": args.rebuild_features,
            "run_live_y2": args.run_live_y2,
            "run_tests": args.run_tests,
            "run_spot_check": args.run_spot_check,
            "run_nested_cv": args.run_nested_cv,
            "only": args.only,
            "dry_run": args.dry_run,
        },
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
    run(args)
    if not args.list_stages:
        print(f"\nManifest written to {args.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
