#!/usr/bin/env python3
"""Validate saved EDHPowerLevel labels against live EDHPowerLevel results."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from edhpowerlevel_client import EDHPowerLevelClient, decklist_text  # type: ignore
except ImportError:
    from scripts.edhpowerlevel_client import EDHPowerLevelClient, decklist_text  # type: ignore


COMPARE_FIELDS = (
    "commander_bracket",
    "power_level",
    "tipping_point",
    "efficiency",
    "impact",
    "score",
    "average_playability",
    "not_loaded_cards",
)


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_number}") from exc


def iter_zip_jsonl(zip_path: Path, member: str) -> Iterable[Dict[str, Any]]:
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member) as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.decode("utf-8").strip()
                if not stripped:
                    continue
                try:
                    yield json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL in {zip_path}:{member} line {line_number}") from exc


def load_decks(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.zip:
        return list(iter_zip_jsonl(args.zip, args.zip_member))
    return list(iter_jsonl(args.decks_path))


def comparable_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {field: payload.get(field) for field in COMPARE_FIELDS if field in payload}


def _deck_key(deck: Dict[str, Any]) -> str:
    return str(deck.get("deck_id") or deck.get("snapshot_id") or "")


def load_excluded_decks(report_path: Optional[Path]) -> set[str]:
    if report_path is None or not report_path.exists():
        return set()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    excluded = set()
    for row in report.get("results") or []:
        if row.get("deck_id") is not None:
            excluded.add(str(row.get("deck_id")))
        if row.get("snapshot_id") is not None:
            excluded.add(str(row.get("snapshot_id")))
    return excluded


def select_stratified_sample(
    decks: List[Dict[str, Any]],
    sample_size: int,
    exclude_decks: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    exclude_decks = exclude_decks or set()
    by_y2: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for deck in decks:
        if _deck_key(deck) in exclude_decks:
            continue
        y2 = deck.get("edhpowerlevel")
        if isinstance(y2, dict) and not y2.get("error"):
            by_y2[y2.get("commander_bracket")].append(deck)

    selected: List[Dict[str, Any]] = []
    seen = set()

    # First pass: guarantee coverage of every y2 bracket when available.
    for bracket in sorted(by_y2, key=lambda value: (str(type(value)), value)):
        bucket = sorted(by_y2[bracket], key=lambda deck: str(deck.get("snapshot_id")))
        if not bucket:
            continue
        deck = bucket[0]
        sid = deck.get("snapshot_id")
        selected.append(deck)
        seen.add(sid)
        if len(selected) >= sample_size:
            return selected

    # Second pass: deterministic fill across all labeled decks.
    all_labeled = sorted(
        (deck for bucket in by_y2.values() for deck in bucket),
        key=lambda deck: str(deck.get("snapshot_id")),
    )
    for deck in all_labeled:
        sid = deck.get("snapshot_id")
        if sid in seen:
            continue
        selected.append(deck)
        seen.add(sid)
        if len(selected) >= sample_size:
            break
    return selected


def validate_deck(deck: Dict[str, Any], client: EDHPowerLevelClient) -> Dict[str, Any]:
    expected = comparable_payload(deck.get("edhpowerlevel") or {})
    actual_full = client.analyze(decklist_text(deck.get("mainboard") or []))
    actual = comparable_payload(actual_full)
    matched = expected == actual
    return {
        "snapshot_id": deck.get("snapshot_id"),
        "deck_id": deck.get("deck_id"),
        "archidekt_edh_bracket": deck.get("archidekt_edh_bracket"),
        "expected": expected,
        "actual": actual,
        "matched": matched,
    }


def validate_deck_batch(
    indexed_decks: List[tuple[int, Dict[str, Any]]],
    args: argparse.Namespace,
) -> List[tuple[int, Dict[str, Any]]]:
    rows: List[tuple[int, Dict[str, Any]]] = []
    with EDHPowerLevelClient(
        headless=not args.headed,
        analysis_wait_sec=args.analysis_wait,
        context_recycle_every=args.recycle_every,
    ) as client:
        for index, deck in indexed_decks:
            rows.append((index, validate_deck(deck, client)))
    return rows


def chunk_indexed_sample(
    sample: List[Dict[str, Any]],
    workers: int,
) -> List[List[tuple[int, Dict[str, Any]]]]:
    chunks: List[List[tuple[int, Dict[str, Any]]]] = [[] for _ in range(max(workers, 1))]
    for index, deck in enumerate(sample):
        chunks[index % len(chunks)].append((index, deck))
    return [chunk for chunk in chunks if chunk]


def validate_labels(args: argparse.Namespace) -> Dict[str, Any]:
    decks = load_decks(args)
    excluded = load_excluded_decks(args.exclude_report)
    sample = select_stratified_sample(decks, args.sample_size, excluded)
    indexed_results: List[tuple[int, Dict[str, Any]]] = []

    workers = min(max(args.workers, 1), max(len(sample), 1))
    if workers == 1:
        indexed_results = validate_deck_batch(list(enumerate(sample)), args)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="edhpl-validator") as executor:
            futures = [
                executor.submit(validate_deck_batch, chunk, args)
                for chunk in chunk_indexed_sample(sample, workers)
            ]
            for future in as_completed(futures):
                indexed_results.extend(future.result())

    results = [row for _, row in sorted(indexed_results, key=lambda item: item[0])]
    mismatches = [row for row in results if not row["matched"]]

    summary = {
        "sample_size": len(sample),
        "workers": workers,
        "excluded_decks": len(excluded),
        "compared_fields": list(COMPARE_FIELDS),
        "matched": len(sample) - len(mismatches),
        "mismatched": len(mismatches),
        "results": results,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate saved EDHPowerLevel labels against the live site.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--decks-path", type=Path, help="Path to processed decks.jsonl.")
    source.add_argument("--zip", type=Path, help="Project/archive zip containing processed decks.jsonl.")
    parser.add_argument(
        "--zip-member",
        default="mtg/data/processed/archidekt/decks.jsonl",
        help="decks.jsonl member path inside --zip.",
    )
    parser.add_argument("--sample-size", type=int, default=15, help="Number of decks to validate.")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel browser workers.")
    parser.add_argument(
        "--exclude-report",
        type=Path,
        default=None,
        help="Optional previous validation report whose deck_id/snapshot_id values should be skipped.",
    )
    parser.add_argument("--analysis-wait", type=float, default=8.0, help="Minimum seconds to wait after Analyze before polling for a stable result.")
    parser.add_argument("--recycle-every", type=int, default=50, help="Recycle the browser page every N decks.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium visibly for debugging.")
    parser.add_argument("--report", type=Path, default=None, help="Optional JSON validation report path.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = validate_labels(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary["mismatched"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
