#!/usr/bin/env python3
"""Repair decks whose y2 was scraped as the pre-Analyze default page state.

The EDHPowerLevel page renders demo defaults (bracket=4, power_level=5.55,
score=447, impact=516.00, efficiency=4.82, average_playability=51.8) before
the in-browser scoring runs. Under load, the old scraper polling could lock
onto those defaults and return them as the deck's y2 label. The client was
fixed (see ``edhpowerlevel_client.py``); this script repairs the saved data:

1. Scans ``decks.jsonl`` for snapshots whose ``edhpowerlevel`` matches the
   default fingerprint.
2. Backs up ``decks.jsonl`` and ``edhpowerlevel_results.jsonl``.
3. Rewrites both, clearing the affected snapshots:
   - sets ``edhpowerlevel = None`` in ``decks.jsonl``
   - drops their entries from ``edhpowerlevel_results.jsonl``
4. Optionally invokes ``refresh-edhpowerlevel-labels`` to re-label them with
   the fixed client.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DECKS_PATH = DEFAULT_PROCESSED_DIR / "decks.jsonl"
DEFAULT_RESULTS_PATH = DEFAULT_PROCESSED_DIR / "edhpowerlevel_results.jsonl"

# Default page state fingerprint, observed empirically by loading
# https://edhpowerlevel.com/ in a fresh Chromium context and reading the
# pre-Analyze rendered values. Five fields used so collision with a real
# computed deck is effectively impossible.
DEFAULT_FINGERPRINT: Dict[str, Any] = {
    "commander_bracket": 4,
    "power_level": "5.55",
    "score": "447",
    "impact": "516.00",
    "efficiency": "4.82",
    "average_playability": "51.8",
}


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_number}") from exc


def is_default_state(epl: Any) -> bool:
    if not isinstance(epl, dict):
        return False
    for field, expected in DEFAULT_FINGERPRINT.items():
        if str(epl.get(field)) != str(expected):
            return False
    return True


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def find_affected(decks_path: Path) -> List[Dict[str, Any]]:
    affected: List[Dict[str, Any]] = []
    for record in iter_jsonl(decks_path):
        if is_default_state(record.get("edhpowerlevel")):
            affected.append(
                {
                    "snapshot_id": record.get("snapshot_id"),
                    "deck_id": record.get("deck_id"),
                    "edhpowerlevel": record.get("edhpowerlevel"),
                }
            )
    return affected


def rewrite_decks_jsonl(decks_path: Path, affected_snapshot_ids: Set[str]) -> int:
    """Rewrite decks.jsonl, setting edhpowerlevel=None for affected snapshots."""
    tmp_path = decks_path.with_suffix(decks_path.suffix + ".tmp")
    cleared = 0
    with decks_path.open("r", encoding="utf-8") as src, tmp_path.open("w", encoding="utf-8") as dst:
        for line in src:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            sid = record.get("snapshot_id")
            if sid in affected_snapshot_ids:
                record["edhpowerlevel"] = None
                cleared += 1
            dst.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            dst.write("\n")
    tmp_path.replace(decks_path)
    return cleared


def filter_results_log(results_path: Path, affected_snapshot_ids: Set[str]) -> int:
    """Rewrite results log, removing affected snapshot_ids so refresh re-queries them."""
    if not results_path.exists():
        return 0
    tmp_path = results_path.with_suffix(results_path.suffix + ".tmp")
    dropped = 0
    with results_path.open("r", encoding="utf-8") as src, tmp_path.open("w", encoding="utf-8") as dst:
        for line in src:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if record.get("snapshot_id") in affected_snapshot_ids:
                dropped += 1
                continue
            dst.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            dst.write("\n")
    tmp_path.replace(results_path)
    return dropped


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decks-path", type=Path, default=DEFAULT_DECKS_PATH)
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_PROCESSED_DIR / "fix_default_state_y2_report.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only identify affected decks; do not write anything.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backing up decks.jsonl and results.jsonl (faster but riskier).",
    )
    parser.add_argument(
        "--run-refresh",
        action="store_true",
        help="After clearing labels, invoke `uv run refresh-edhpowerlevel-labels` to re-label.",
    )
    parser.add_argument(
        "--refresh-workers",
        type=int,
        default=16,
        help="Workers passed to refresh-edhpowerlevel-labels when --run-refresh is set.",
    )
    args = parser.parse_args(argv)

    print(f"Scanning {args.decks_path} for default-state y2 labels...", file=sys.stderr)
    affected = find_affected(args.decks_path)
    print(f"  found {len(affected)} affected decks.", file=sys.stderr)

    if not affected:
        print("Nothing to do.", file=sys.stderr)
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(
                {"affected": [], "fingerprint": DEFAULT_FINGERPRINT, "ran_at": utc_stamp()},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return 0

    affected_ids: Set[str] = {row["snapshot_id"] for row in affected if row.get("snapshot_id")}
    print("Sample of affected decks:", file=sys.stderr)
    for row in affected[:5]:
        print(f"  deck_id={row['deck_id']} snapshot_id={row['snapshot_id']}", file=sys.stderr)

    if args.dry_run:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(
                {
                    "fingerprint": DEFAULT_FINGERPRINT,
                    "affected_count": len(affected),
                    "affected": affected,
                    "dry_run": True,
                    "ran_at": utc_stamp(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(f"Dry-run complete. Report at {args.report_path}.", file=sys.stderr)
        return 0

    stamp = utc_stamp()
    if not args.no_backup:
        decks_backup = args.decks_path.with_suffix(f".bak-fix-default-{stamp}")
        results_backup = args.results_path.with_suffix(f".bak-fix-default-{stamp}")
        print(f"Backing up:\n  {args.decks_path} -> {decks_backup}", file=sys.stderr)
        shutil.copy2(args.decks_path, decks_backup)
        if args.results_path.exists():
            print(f"  {args.results_path} -> {results_backup}", file=sys.stderr)
            shutil.copy2(args.results_path, results_backup)

    cleared = rewrite_decks_jsonl(args.decks_path, affected_ids)
    print(f"Cleared edhpowerlevel for {cleared} snapshots in {args.decks_path}.", file=sys.stderr)

    dropped = filter_results_log(args.results_path, affected_ids)
    print(f"Dropped {dropped} entries from {args.results_path}.", file=sys.stderr)

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(
        json.dumps(
            {
                "fingerprint": DEFAULT_FINGERPRINT,
                "affected_count": len(affected),
                "affected": affected,
                "cleared_in_decks": cleared,
                "dropped_from_results": dropped,
                "ran_at": utc_stamp(),
                "ran_refresh": bool(args.run_refresh),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Report at {args.report_path}.", file=sys.stderr)

    if args.run_refresh:
        print("\nInvoking refresh-edhpowerlevel-labels...", file=sys.stderr)
        cmd = [
            "uv", "run", "refresh-edhpowerlevel-labels",
            "--workers", str(args.refresh_workers),
            "--decks-path", str(args.decks_path),
            "--results-path", str(args.results_path),
        ]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"refresh-edhpowerlevel-labels exited with code {result.returncode}", file=sys.stderr)
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
