#!/usr/bin/env python3
"""Phase C.1 — freeze the modelable Archidekt snapshot set.

The modeling target is y1 (Archidekt bracket), but the project intentionally
keeps only snapshots where both y1 and y2 are in {2, 3, 4}. The excluded decks
are written separately for qualitative analysis and auditability.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - exercised by console script and direct import tests
    from preprocessing import iter_jsonl, split_modeling_records, write_jsonl  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.preprocessing import iter_jsonl, split_modeling_records, write_jsonl  # type: ignore


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_snapshot_ids(path: Path, snapshot_ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for index, snapshot_id in enumerate(snapshot_ids):
            comma = "," if index < len(snapshot_ids) - 1 else ""
            handle.write(json.dumps(snapshot_id, ensure_ascii=False))
            handle.write(comma)
            handle.write("\n")
        handle.write("]\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter Phase-C modelable decks and write excluded deck audit records.",
    )
    parser.add_argument(
        "--features-path",
        type=Path,
        default=DEFAULT_PROCESSED_DIR / "deck_features.jsonl",
        help="Input deck_features.jsonl produced by build-archidekt-features.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Directory for modeling_snapshot_ids.json, modeling_excluded.jsonl, and manifest.",
    )
    parser.add_argument(
        "--snapshot-ids-name",
        default="modeling_snapshot_ids.json",
        help="Output filename for included snapshot ids.",
    )
    parser.add_argument(
        "--excluded-name",
        default="modeling_excluded.jsonl",
        help="Output filename for excluded deck audit rows.",
    )
    parser.add_argument(
        "--manifest-name",
        default="modeling_dataset_manifest.json",
        help="Output filename for the Phase-C filter manifest.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    features_path: Path = args.features_path
    if not features_path.exists():
        raise FileNotFoundError(f"Expected {features_path} — run build-archidekt-features first.")

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_ids_path = out_dir / args.snapshot_ids_name
    excluded_path = out_dir / args.excluded_name
    manifest_path = out_dir / args.manifest_name

    records = list(iter_jsonl(features_path))
    included, excluded, reasons = split_modeling_records(records)
    snapshot_ids = [record["snapshot_id"] for record in included if isinstance(record.get("snapshot_id"), str)]

    write_snapshot_ids(snapshot_ids_path, snapshot_ids)
    write_jsonl(excluded_path, excluded)

    reason_dict = dict(sorted(reasons.items()))
    summary: Dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "source": str(features_path),
        "total_decks": len(records),
        "included": len(included),
        "excluded": len(excluded),
        "exclusion_reasons": reason_dict,
        "outputs": {
            "snapshot_ids": str(snapshot_ids_path),
            "excluded": str(excluded_path),
        },
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

