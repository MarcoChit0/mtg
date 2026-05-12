#!/usr/bin/env python3
"""Process saved Archidekt raw payloads into JSONL modeling tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


DEFAULT_RAW_DIR = Path("data/raw/archidekt")
DEFAULT_OUT_DIR = Path("data/processed/archidekt")
OUTPUT_FILES = (
    "cards.jsonl",
    "decks.jsonl",
    "deck_cards.jsonl",
    "processing_manifest.jsonl",
    "rejected_decks.jsonl",
)
BOARD_EXCLUDED_CATEGORIES = {"maybeboard", "sideboard", "tokensextras", "tokensandextras"}
BASIC_LAND_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
COLOR_NAME_TO_SYMBOL = {
    "White": "W",
    "Blue": "U",
    "Black": "B",
    "Red": "R",
    "Green": "G",
    "W": "W",
    "U": "U",
    "B": "B",
    "R": "R",
    "G": "G",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_number}") from exc


def normalize_category(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def color_symbols(values: Sequence[Any]) -> Set[str]:
    symbols: Set[str] = set()
    for value in values or []:
        symbol = COLOR_NAME_TO_SYMBOL.get(str(value))
        if symbol:
            symbols.add(symbol)
    return symbols


def commander_category_names(deck: Dict[str, Any]) -> Set[str]:
    names = {"commander"}
    for category in deck.get("categories") or []:
        if not isinstance(category, dict):
            continue
        if category.get("isPremier") is True:
            names.add(normalize_category(category.get("name")))
    return names


def is_commander_category(categories: Sequence[Any], commander_categories: Set[str]) -> bool:
    return any(normalize_category(category) in commander_categories for category in categories or [])


def is_basic_land(oracle: Dict[str, Any]) -> bool:
    name = oracle.get("name")
    super_types = set(oracle.get("superTypes") or [])
    types = set(oracle.get("types") or [])
    return name in BASIC_LAND_NAMES or ("Basic" in super_types and "Land" in types)


def allows_multiple_copies(oracle: Dict[str, Any]) -> bool:
    text = str(oracle.get("text") or "").casefold()
    return bool(
        re.search(r"a deck can have any number of cards named", text)
        or re.search(r"a deck can have up to [a-z0-9 -]+ cards named", text)
    )


def strip_deck_metadata(deck: Dict[str, Any]) -> Dict[str, Any]:
    omitted = {"cards", "featured", "customFeatured", "cardPackage"}
    return {key: value for key, value in deck.items() if key not in omitted}


def raw_detail_from_record(record: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if record.get("status") not in (None, 200):
        return None, "fetch_status_not_200"
    payload = record.get("response", record.get("payload", record))
    if isinstance(payload, dict) and isinstance(payload.get("cards"), list):
        return payload, ""
    return None, "missing_deck_payload"


def excluded_category_names(deck: Dict[str, Any]) -> Set[str]:
    excluded = set(BOARD_EXCLUDED_CATEGORIES)
    for category in deck.get("categories") or []:
        if not isinstance(category, dict):
            continue
        name = category.get("name")
        if category.get("includedInDeck") is False:
            excluded.add(normalize_category(name))
    return excluded


def row_exclusion_reasons(row: Dict[str, Any], excluded_categories: Set[str]) -> List[str]:
    reasons: List[str] = []
    if row.get("deletedAt") is not None:
        reasons.append("deleted")
    if row.get("companion") is True:
        reasons.append("companion")
    categories = row.get("categories") or []
    if any(normalize_category(category) in excluded_categories for category in categories):
        reasons.append("excluded_category")
    return reasons


def extract_mainboard(deck: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    excluded_categories = excluded_category_names(deck)
    commander_categories = commander_category_names(deck)
    trace: Dict[str, Any] = {
        "total_card_rows": len(deck.get("cards") or []),
        "excluded_rows": Counter(),
        "excluded_quantity": Counter(),
        "included_rows": 0,
        "included_quantity": 0,
        "commander_rows": 0,
        "commander_quantity": 0,
        "excluded_categories": sorted(excluded_categories),
        "commander_categories": sorted(commander_categories),
    }

    mainboard: List[Dict[str, Any]] = []
    for row in deck.get("cards") or []:
        if not isinstance(row, dict):
            continue

        quantity = int(row.get("quantity") or 0)
        reasons = row_exclusion_reasons(row, excluded_categories)
        if reasons:
            for reason in reasons:
                trace["excluded_rows"][reason] += 1
                trace["excluded_quantity"][reason] += quantity
            continue

        oracle = ((row.get("card") or {}).get("oracleCard") or {})
        categories = row.get("categories") or []
        is_commander = is_commander_category(categories, commander_categories)
        item = {
            "deck_row_id": row.get("id"),
            "oracle": oracle,
            "oracle_uid": oracle.get("uid"),
            "oracle_name": oracle.get("name"),
            "quantity": quantity,
            "categories": categories,
            "is_commander": is_commander,
            "custom_cmc": row.get("customCmc"),
            "modifier": row.get("modifier"),
            "notes": row.get("notes"),
        }
        mainboard.append(item)
        trace["included_rows"] += 1
        trace["included_quantity"] += quantity
        if is_commander:
            trace["commander_rows"] += 1
            trace["commander_quantity"] += quantity

    trace["excluded_rows"] = dict(trace["excluded_rows"])
    trace["excluded_quantity"] = dict(trace["excluded_quantity"])
    return mainboard, trace


def validate_deck(
    deck: Dict[str, Any],
    mainboard: List[Dict[str, Any]],
    trace: Dict[str, Any],
    min_views: int,
    brackets: Set[int],
) -> List[str]:
    reasons: List[str] = []

    if deck.get("private") is not False:
        reasons.append("private")
    if deck.get("unlisted") is not False:
        reasons.append("unlisted")
    if deck.get("deckFormat") != 3:
        reasons.append("not_commander_format")
    if deck.get("edhBracket") not in brackets:
        reasons.append("missing_or_invalid_bracket")
    if int(deck.get("viewCount") or 0) < min_views:
        reasons.append("low_view_count")
    if int(trace.get("included_quantity") or 0) != 100:
        reasons.append("mainboard_count_not_100")
    if int(trace.get("commander_quantity") or 0) < 1:
        reasons.append("missing_commander")

    missing_oracle = [
        {"deck_row_id": row.get("deck_row_id"), "oracle_name": row.get("oracle_name")}
        for row in mainboard
        if not row.get("oracle_uid")
    ]
    if missing_oracle:
        reasons.append("missing_oracle_uid")
        trace["missing_oracle"] = missing_oracle

    non_positive_quantity = [
        {"oracle_uid": row.get("oracle_uid"), "oracle_name": row.get("oracle_name"), "quantity": row.get("quantity")}
        for row in mainboard
        if int(row.get("quantity") or 0) <= 0
    ]
    if non_positive_quantity:
        reasons.append("non_positive_quantity")
        trace["non_positive_quantity"] = non_positive_quantity

    illegal_cards = []
    for row in mainboard:
        oracle = row.get("oracle") or {}
        legality = ((oracle.get("legalities") or {}).get("commander"))
        if legality != "legal":
            illegal_cards.append(
                {
                    "oracle_uid": row.get("oracle_uid"),
                    "oracle_name": row.get("oracle_name"),
                    "legality": legality,
                }
            )
    if illegal_cards:
        reasons.append("illegal_commander_card")
        trace["illegal_cards"] = illegal_cards

    quantities_by_oracle: Dict[str, int] = defaultdict(int)
    first_row_by_oracle: Dict[str, Dict[str, Any]] = {}
    for row in mainboard:
        oracle_uid = row.get("oracle_uid")
        if not oracle_uid:
            continue
        quantities_by_oracle[oracle_uid] += int(row.get("quantity") or 0)
        first_row_by_oracle.setdefault(oracle_uid, row)

    duplicate_violations = []
    for oracle_uid, quantity in quantities_by_oracle.items():
        if quantity <= 1:
            continue
        row = first_row_by_oracle[oracle_uid]
        oracle = row.get("oracle") or {}
        if is_basic_land(oracle) or allows_multiple_copies(oracle):
            continue
        duplicate_violations.append(
            {"oracle_uid": oracle_uid, "oracle_name": row.get("oracle_name"), "quantity": quantity}
        )
    if duplicate_violations:
        reasons.append("duplicate_nonbasic")
        trace["duplicate_violations"] = duplicate_violations

    commander_rows = [row for row in mainboard if row.get("is_commander")]
    commander_colors: Set[str] = set()
    for row in commander_rows:
        commander_colors.update(color_symbols((row.get("oracle") or {}).get("colorIdentity") or []))
    trace["commander_color_identity"] = sorted(commander_colors)

    color_identity_violations = []
    for row in mainboard:
        card_colors = color_symbols((row.get("oracle") or {}).get("colorIdentity") or [])
        if not card_colors.issubset(commander_colors):
            color_identity_violations.append(
                {
                    "oracle_uid": row.get("oracle_uid"),
                    "oracle_name": row.get("oracle_name"),
                    "color_identity": sorted(card_colors),
                }
            )
    if color_identity_violations:
        reasons.append("color_identity_violation")
        trace["color_identity_violations"] = color_identity_violations

    return reasons


def snapshot_id(deck_id: Any, fetched_at: str) -> str:
    return f"archidekt:{deck_id}:{fetched_at}"


def deck_snapshot_record(
    raw_record: Dict[str, Any],
    deck: Dict[str, Any],
    mainboard: List[Dict[str, Any]],
    trace: Dict[str, Any],
) -> Dict[str, Any]:
    fetched_at = raw_record.get("fetched_at") or utc_now_iso()
    deck_id = raw_record.get("deck_id", deck.get("id"))
    commanders = [row.get("oracle_uid") for row in mainboard if row.get("is_commander")]
    return {
        "record_type": "processed_archidekt_deck",
        "snapshot_id": snapshot_id(deck_id, fetched_at),
        "deck_id": deck_id,
        "source_url": raw_record.get("detail_url") or f"https://archidekt.com/decks/{deck_id}",
        "fetched_at": fetched_at,
        "archidekt_updated_at": deck.get("updatedAt"),
        "archidekt_edh_bracket": deck.get("edhBracket"),
        "view_count": deck.get("viewCount"),
        "commander_oracle_uids": commanders,
        "mainboard_count": trace.get("included_quantity"),
        "validation_trace": trace,
        "raw_deck_metadata": strip_deck_metadata(deck),
        "mainboard": [
            {
                "deck_row_id": row.get("deck_row_id"),
                "oracle_uid": row.get("oracle_uid"),
                "oracle_name": row.get("oracle_name"),
                "quantity": row.get("quantity"),
                "categories": row.get("categories"),
                "is_commander": row.get("is_commander"),
                "custom_cmc": row.get("custom_cmc"),
                "modifier": row.get("modifier"),
                "notes": row.get("notes"),
            }
            for row in mainboard
        ],
    }


def deck_card_records(raw_record: Dict[str, Any], deck: Dict[str, Any], mainboard: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fetched_at = raw_record.get("fetched_at") or utc_now_iso()
    deck_id = raw_record.get("deck_id", deck.get("id"))
    sid = snapshot_id(deck_id, fetched_at)
    records: List[Dict[str, Any]] = []
    for row in mainboard:
        records.append(
            {
                "record_type": "processed_archidekt_deck_card",
                "snapshot_id": sid,
                "deck_id": deck_id,
                "fetched_at": fetched_at,
                "oracle_uid": row.get("oracle_uid"),
                "oracle_name": row.get("oracle_name"),
                "quantity": row.get("quantity"),
                "categories": row.get("categories"),
                "is_commander": row.get("is_commander"),
                "deck_row_id": row.get("deck_row_id"),
                "custom_cmc": row.get("custom_cmc"),
                "modifier": row.get("modifier"),
                "notes": row.get("notes"),
            }
        )
    return records


def card_record(raw_record: Dict[str, Any], deck: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    oracle = row.get("oracle") or {}
    return {
        "record_type": "processed_archidekt_card",
        "oracle_uid": row.get("oracle_uid"),
        "oracle_id": oracle.get("id"),
        "oracle_name": oracle.get("name"),
        "first_seen_deck_id": raw_record.get("deck_id", deck.get("id")),
        "first_seen_fetched_at": raw_record.get("fetched_at"),
        "raw_oracle_card": oracle,
    }


def rejected_record(
    raw_record: Dict[str, Any],
    deck: Optional[Dict[str, Any]],
    reasons: List[str],
    trace: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fetched_at = raw_record.get("fetched_at") or utc_now_iso()
    deck_id = raw_record.get("deck_id") or (deck or {}).get("id")
    record = {
        "record_type": "rejected_archidekt_deck",
        "snapshot_id": snapshot_id(deck_id, fetched_at),
        "deck_id": deck_id,
        "fetched_at": fetched_at,
        "detail_url": raw_record.get("detail_url"),
        "rejection_reasons": reasons,
        "trace": trace or {},
        "raw_summary": {
            "name": (deck or {}).get("name"),
            "private": (deck or {}).get("private"),
            "unlisted": (deck or {}).get("unlisted"),
            "deckFormat": (deck or {}).get("deckFormat"),
            "edhBracket": (deck or {}).get("edhBracket"),
            "viewCount": (deck or {}).get("viewCount"),
        },
    }
    if extra:
        record.update(extra)
    return record


def deck_fingerprint(mainboard: List[Dict[str, Any]]) -> str:
    """SHA-256 of sorted oracle_uid:quantity pairs — uniquely identifies a card list."""
    parts = sorted(
        f"{row['oracle_uid']}:{row['quantity']}"
        for row in mainboard
        if row.get("oracle_uid")
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def latest_raw_records(path: Path) -> Tuple[int, List[Dict[str, Any]]]:
    """Return (total_records_read, deduplicated_records).

    For each deck_id, keeps only the record whose deck has the most recent
    updatedAt (falling back to fetched_at). Records missing a deck_id are
    passed through unchanged so downstream can reject them properly.
    """
    total = 0
    best: Dict[int, Tuple[str, Dict[str, Any]]] = {}
    orphans: List[Dict[str, Any]] = []
    for record in iter_jsonl(path) or []:
        total += 1
        deck_id = record.get("deck_id")
        if not isinstance(deck_id, int):
            orphans.append(record)
            continue
        deck = record.get("response") or {}
        sort_key = deck.get("updatedAt") or record.get("fetched_at") or ""
        existing = best.get(deck_id)
        if existing is None or sort_key > existing[0]:
            best[deck_id] = (sort_key, record)
    return total, orphans + [rec for _, rec in best.values()]


def existing_ids(
    out_dir: Path,
) -> Tuple[Set[str], Set[str], Set[str], Set[int], Set[str], Dict[str, int]]:
    card_ids: Set[str] = set()
    accepted_snapshot_ids: Set[str] = set()
    rejected_snapshot_ids: Set[str] = set()
    accepted_deck_ids: Set[int] = set()
    seen_fingerprints: Set[str] = set()
    fingerprint_to_deck_id: Dict[str, int] = {}

    for record in iter_jsonl(out_dir / "cards.jsonl") or []:
        oracle_uid = record.get("oracle_uid")
        if isinstance(oracle_uid, str):
            card_ids.add(oracle_uid)

    for record in iter_jsonl(out_dir / "decks.jsonl") or []:
        sid = record.get("snapshot_id")
        if isinstance(sid, str):
            accepted_snapshot_ids.add(sid)
        deck_id = record.get("deck_id")
        if isinstance(deck_id, int):
            accepted_deck_ids.add(deck_id)
        fp = deck_fingerprint(record.get("mainboard") or [])
        seen_fingerprints.add(fp)
        if isinstance(deck_id, int):
            fingerprint_to_deck_id[fp] = deck_id

    for record in iter_jsonl(out_dir / "rejected_decks.jsonl") or []:
        sid = record.get("snapshot_id")
        if isinstance(sid, str):
            rejected_snapshot_ids.add(sid)

    return card_ids, accepted_snapshot_ids, rejected_snapshot_ids, accepted_deck_ids, seen_fingerprints, fingerprint_to_deck_id


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process raw Archidekt deck payloads.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Directory containing raw_deck_details.jsonl.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Processed output directory.")
    parser.add_argument("--min-views", type=int, default=1000, help="Minimum Archidekt view count.")
    parser.add_argument("--brackets", type=int, nargs="+", default=[2, 3, 4], help="Accepted EDH brackets.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing processed JSONL outputs.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    raw_details_path = args.raw_dir / "raw_deck_details.jsonl"
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.overwrite:
        for filename in OUTPUT_FILES:
            path = out_dir / filename
            if path.exists():
                path.unlink()

    cards_path = out_dir / "cards.jsonl"
    decks_path = out_dir / "decks.jsonl"
    deck_cards_path = out_dir / "deck_cards.jsonl"
    manifest_path = out_dir / "processing_manifest.jsonl"
    rejected_path = out_dir / "rejected_decks.jsonl"

    (
        seen_card_ids,
        accepted_snapshot_ids,
        rejected_snapshot_ids,
        accepted_deck_ids,
        seen_fingerprints,
        fingerprint_to_deck_id,
    ) = existing_ids(out_dir)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    brackets = set(args.brackets)

    # Pre-pass: one record per deck_id (latest updatedAt wins).
    total_raw, candidate_records = latest_raw_records(raw_details_path)

    summary: Dict[str, Any] = {
        "record_type": "archidekt_processing_manifest",
        "run_id": run_id,
        "started_at": utc_now_iso(),
        "finished_at": None,
        "parameters": {
            "raw_dir": str(args.raw_dir),
            "out_dir": str(out_dir),
            "min_views": args.min_views,
            "brackets": list(args.brackets),
            "overwrite": bool(args.overwrite),
        },
        "raw_records_read": total_raw,
        "duplicate_deck_id_skipped": total_raw - len(candidate_records),
        "accepted_decks": 0,
        "rejected_decks": 0,
        "skipped_existing": 0,
        "cards_written": 0,
        "deck_card_rows_written": 0,
        "rejection_reasons": Counter(),
        "errors": [],
    }

    for raw_record in candidate_records:
        deck_id = raw_record.get("deck_id")

        # Already accepted in a previous run — skip entirely.
        if isinstance(deck_id, int) and deck_id in accepted_deck_ids:
            summary["skipped_existing"] += 1
            continue

        deck, payload_error = raw_detail_from_record(raw_record)
        if deck is None:
            reasons = [payload_error]
            rejected = rejected_record(raw_record, None, reasons)
            sid = rejected["snapshot_id"]
            if sid not in rejected_snapshot_ids:
                append_jsonl(rejected_path, rejected)
                rejected_snapshot_ids.add(sid)
                summary["rejected_decks"] += 1
                summary["rejection_reasons"].update(reasons)
            continue

        fetched_at = raw_record.get("fetched_at") or utc_now_iso()
        sid = snapshot_id(deck_id, fetched_at)

        # Already rejected in a previous run — skip.
        if sid in rejected_snapshot_ids:
            summary["skipped_existing"] += 1
            continue

        mainboard, trace = extract_mainboard(deck)
        reasons = validate_deck(deck, mainboard, trace, min_views=args.min_views, brackets=brackets)

        if reasons:
            rejected = rejected_record(raw_record, deck, reasons, trace)
            append_jsonl(rejected_path, rejected)
            rejected_snapshot_ids.add(sid)
            summary["rejected_decks"] += 1
            summary["rejection_reasons"].update(reasons)
            continue

        # Deduplicate by card list fingerprint (catches copied decks).
        fp = deck_fingerprint(mainboard)
        if fp in seen_fingerprints:
            reasons = ["duplicate_card_list"]
            rejected = rejected_record(
                raw_record, deck, reasons, trace,
                extra={"duplicate_of_deck_id": fingerprint_to_deck_id.get(fp)},
            )
            append_jsonl(rejected_path, rejected)
            rejected_snapshot_ids.add(sid)
            summary["rejected_decks"] += 1
            summary["rejection_reasons"].update(reasons)
            continue

        seen_fingerprints.add(fp)
        fingerprint_to_deck_id[fp] = deck_id

        for row in mainboard:
            oracle_uid = row.get("oracle_uid")
            if isinstance(oracle_uid, str) and oracle_uid not in seen_card_ids:
                append_jsonl(cards_path, card_record(raw_record, deck, row))
                seen_card_ids.add(oracle_uid)
                summary["cards_written"] += 1

        deck_snapshot = deck_snapshot_record(raw_record, deck, mainboard, trace)
        append_jsonl(decks_path, deck_snapshot)
        accepted_snapshot_ids.add(sid)
        accepted_deck_ids.add(deck_id)
        summary["accepted_decks"] += 1

        for row_record in deck_card_records(raw_record, deck, mainboard):
            append_jsonl(deck_cards_path, row_record)
            summary["deck_card_rows_written"] += 1

    summary["finished_at"] = utc_now_iso()
    summary["rejection_reasons"] = dict(summary["rejection_reasons"])
    append_jsonl(manifest_path, summary)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
