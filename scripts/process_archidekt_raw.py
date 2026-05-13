#!/usr/bin/env python3
"""Process saved Archidekt raw payloads and enrich them with EDHPowerLevel.

The script has two phases:

* **Phase A — ingest**: read ``raw_deck_details.jsonl``, validate decks, and
  write ``cards.jsonl`` + ``decks.jsonl`` (deduped by ``deck_id``, by card-list
  fingerprint, and against already-processed snapshots). Each deck record
  carries an ``edhpowerlevel`` field, initialised to ``None``.

* **Phase B — enrich y2**: walk ``decks.jsonl`` looking for records with
  ``edhpowerlevel is None``, submit each to https://edhpowerlevel.com/ via a
  Playwright-driven Chromium, parse the scoring fields out of the page, and
  rewrite ``decks.jsonl`` with ``edhpowerlevel`` populated. Resume-safe: a
  sidecar JSONL log captures every attempt so an interrupted run can pick up
  where it left off.

The script writes ``cards.jsonl``, ``decks.jsonl``,
``processing_manifest.jsonl``, ``rejected_decks.jsonl``, and (while Phase B is
running) ``edhpowerlevel_results.jsonl``. There is no ``deck_cards.jsonl``;
the per-deck-card information lives inline on each deck record under
``mainboard`` and can be flattened on demand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
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
    "processing_manifest.jsonl",
    "rejected_decks.jsonl",
    "edhpowerlevel_results.jsonl",
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
        "owner_id": _deck_owner_id(deck),
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
        # External label slot — populated by Phase B.
        "edhpowerlevel": None,
    }


def _deck_owner_id(deck: Dict[str, Any]) -> Any:
    owner = deck.get("owner")
    if isinstance(owner, dict):
        return owner.get("id") or owner.get("username")
    return owner


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
    parser = argparse.ArgumentParser(description="Process raw Archidekt deck payloads and enrich with EDHPowerLevel.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Directory containing raw_deck_details.jsonl.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Processed output directory.")
    parser.add_argument("--min-views", type=int, default=1000, help="Minimum Archidekt view count.")
    parser.add_argument("--brackets", type=int, nargs="+", default=[2, 3, 4], help="Accepted EDH brackets.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing processed JSONL outputs.")

    # ----- Phase B knobs ----------------------------------------------------
    parser.add_argument(
        "--skip-y2",
        action="store_true",
        help="Skip the EDHPowerLevel enrichment phase.",
    )
    parser.add_argument(
        "--y2-only",
        action="store_true",
        help="Skip Phase A and only run EDHPowerLevel enrichment on existing decks.jsonl.",
    )
    parser.add_argument(
        "--y2-max-decks",
        type=int,
        default=None,
        help="Cap how many decks to query EDHPowerLevel for this run (resume-friendly).",
    )
    parser.add_argument(
        "--y2-sleep",
        type=float,
        default=0.5,
        help="Seconds to wait between EDHPowerLevel analyses (be courteous).",
    )
    parser.add_argument(
        "--y2-headed",
        action="store_true",
        help="Run Chromium with a visible window — useful when debugging selectors.",
    )
    parser.add_argument(
        "--y2-analysis-wait",
        type=float,
        default=6.0,
        help="Seconds to wait after clicking Analyze before scraping the result.",
    )
    parser.add_argument(
        "--y2-recycle-every",
        type=int,
        default=50,
        help="Recreate the browser page every N analyses to bound memory.",
    )
    parser.add_argument(
        "--y2-flush-every",
        type=int,
        default=25,
        help="Rewrite decks.jsonl with the latest y2 progress every N analyses.",
    )
    parser.add_argument(
        "--y2-retry-failed",
        action="store_true",
        help="Re-query decks whose previous attempt returned an error.",
    )
    return parser.parse_args(argv)


# ============================================================================
# Phase A — ingest
# ============================================================================
def _phase_a(args: argparse.Namespace, summary: Dict[str, Any]) -> None:
    raw_details_path = args.raw_dir / "raw_deck_details.jsonl"
    out_dir: Path = args.out_dir

    cards_path = out_dir / "cards.jsonl"
    decks_path = out_dir / "decks.jsonl"
    rejected_path = out_dir / "rejected_decks.jsonl"

    (
        seen_card_ids,
        accepted_snapshot_ids,
        rejected_snapshot_ids,
        accepted_deck_ids,
        seen_fingerprints,
        fingerprint_to_deck_id,
    ) = existing_ids(out_dir)
    brackets = set(args.brackets)

    total_raw, candidate_records = latest_raw_records(raw_details_path)
    summary["raw_records_read"] = total_raw
    summary["duplicate_deck_id_skipped"] = total_raw - len(candidate_records)

    for raw_record in candidate_records:
        deck_id = raw_record.get("deck_id")

        # Already accepted in a previous run — skip entirely. This is the
        # "same user, same deck_id" dedup the spec calls for: regardless of
        # whether 1 or 20 cards changed since last fetch, deck_id is the
        # canonical identity for a deck within a user.
        if isinstance(deck_id, int) and deck_id in accepted_deck_ids:
            summary["skipped_existing_snapshots"] += 1
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

        if sid in rejected_snapshot_ids:
            summary["skipped_existing_snapshots"] += 1
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

        # Card-list fingerprint dedup: rejects decks with an identical
        # mainboard from a *different* deck_id (the "different users, same
        # cards" case in the spec).
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


# ============================================================================
# Phase B — EDHPowerLevel y2 enrichment
# ============================================================================
def _decks_missing_y2(decks_path: Path, retry_failed: bool) -> List[str]:
    missing: List[str] = []
    for record in iter_jsonl(decks_path) or []:
        sid = record.get("snapshot_id")
        if not isinstance(sid, str):
            continue
        y2 = record.get("edhpowerlevel")
        if y2 is None:
            missing.append(sid)
            continue
        if retry_failed and isinstance(y2, dict) and y2.get("error"):
            missing.append(sid)
    return missing


def _load_y2_progress(path: Path) -> Dict[str, Dict[str, Any]]:
    """Return latest result per snapshot from the append-only progress log."""
    latest: Dict[str, Dict[str, Any]] = {}
    for record in iter_jsonl(path) or []:
        sid = record.get("snapshot_id")
        if isinstance(sid, str):
            latest[sid] = record
    return latest


def _rewrite_decks_with_y2(
    decks_path: Path, y2_by_sid: Dict[str, Dict[str, Any]], summary: Dict[str, Any]
) -> int:
    """Atomically rewrite decks.jsonl with `edhpowerlevel` populated.

    Returns the number of records that gained a non-error y2. We rewrite
    rather than update-in-place so partial progress is always readable.
    """
    if not y2_by_sid:
        return 0
    tmp_path = decks_path.with_suffix(decks_path.suffix + ".tmp")
    populated = 0
    with tmp_path.open("w", encoding="utf-8") as out:
        for record in iter_jsonl(decks_path) or []:
            sid = record.get("snapshot_id")
            entry = y2_by_sid.get(sid)
            if entry is not None:
                payload = {k: v for k, v in entry.items() if k != "snapshot_id"}
                record["edhpowerlevel"] = payload
                if not payload.get("error"):
                    populated += 1
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            out.write("\n")
    os.replace(tmp_path, decks_path)
    summary["y2_decks_in_decks_jsonl"] = populated
    return populated


def _phase_b(args: argparse.Namespace, summary: Dict[str, Any]) -> None:
    # Imported lazily so Phase A doesn't pull Playwright in when --skip-y2 is
    # set or when the user only wants to ingest. We probe ``sys.modules``
    # first so unit tests can inject a fake client without depending on
    # import path layout; then try the unprefixed name (works when running
    # the script directly), then the package-qualified name (works under
    # ``uv run`` where ``scripts`` is the installed package).
    import sys

    module = sys.modules.get("edhpowerlevel_client")
    if module is None:
        try:
            from edhpowerlevel_client import EDHPowerLevelClient, decklist_text  # type: ignore
        except ImportError:
            from scripts.edhpowerlevel_client import EDHPowerLevelClient, decklist_text  # type: ignore
    else:
        EDHPowerLevelClient = module.EDHPowerLevelClient  # type: ignore
        decklist_text = module.decklist_text  # type: ignore

    out_dir: Path = args.out_dir
    decks_path = out_dir / "decks.jsonl"
    progress_path = out_dir / "edhpowerlevel_results.jsonl"

    if not decks_path.exists():
        summary["y2_phase"] = {"status": "skipped", "reason": "no_decks_jsonl"}
        return

    progress = _load_y2_progress(progress_path)
    # If progress exists from a prior run, apply it before deciding what's missing.
    if progress:
        _rewrite_decks_with_y2(decks_path, progress, summary)

    missing = _decks_missing_y2(decks_path, retry_failed=args.y2_retry_failed)
    if not missing:
        summary["y2_phase"] = {
            "status": "complete",
            "missing": 0,
            "processed_this_run": 0,
        }
        return

    cap = args.y2_max_decks if args.y2_max_decks else len(missing)
    targets = set(missing[:cap])

    summary["y2_phase"] = {
        "status": "running",
        "missing_initial": len(missing),
        "targets_this_run": len(targets),
    }
    summary["y2_attempted"] = 0
    summary["y2_succeeded"] = 0
    summary["y2_failed"] = 0
    bracket_counts: Counter = Counter()

    pending_writes: Dict[str, Dict[str, Any]] = dict(progress)

    def flush() -> None:
        if pending_writes:
            _rewrite_decks_with_y2(decks_path, pending_writes, summary)

    started = time.monotonic()
    with EDHPowerLevelClient(
        headless=not args.y2_headed,
        analysis_wait_sec=args.y2_analysis_wait,
        context_recycle_every=args.y2_recycle_every,
    ) as client:
        # We re-read decks.jsonl line by line to keep memory low even on
        # tens of thousands of decks. Skip those not in the target set.
        for record in iter_jsonl(decks_path) or []:
            sid = record.get("snapshot_id")
            if sid not in targets:
                continue
            mainboard = record.get("mainboard") or []
            decklist = decklist_text(mainboard)
            result = client.analyze(decklist)
            result_with_id = dict(result)
            result_with_id["snapshot_id"] = sid
            result_with_id["deck_id"] = record.get("deck_id")
            result_with_id["queried_at"] = utc_now_iso()
            append_jsonl(progress_path, result_with_id)
            pending_writes[sid] = result_with_id

            summary["y2_attempted"] += 1
            if result.get("error"):
                summary["y2_failed"] += 1
            else:
                summary["y2_succeeded"] += 1
                if "commander_bracket" in result:
                    bracket_counts[result["commander_bracket"]] += 1

            if summary["y2_attempted"] % args.y2_flush_every == 0:
                flush()

            if args.y2_sleep:
                time.sleep(args.y2_sleep)

    flush()
    elapsed = time.monotonic() - started
    summary["y2_phase"]["status"] = "done"
    summary["y2_phase"]["elapsed_seconds"] = round(elapsed, 2)
    summary["y2_phase"]["bracket_distribution"] = dict(bracket_counts)


# ============================================================================
# Entrypoint
# ============================================================================
def run(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "processing_manifest.jsonl"

    if args.overwrite:
        for filename in OUTPUT_FILES:
            path = out_dir / filename
            if path.exists():
                path.unlink()

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
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
            "skip_y2": bool(args.skip_y2),
            "y2_only": bool(args.y2_only),
            "y2_max_decks": args.y2_max_decks,
        },
        "raw_records_read": 0,
        "duplicate_deck_id_skipped": 0,
        "accepted_decks": 0,
        "rejected_decks": 0,
        "skipped_existing_snapshots": 0,
        "cards_written": 0,
        "rejection_reasons": Counter(),
        "errors": [],
    }

    if not args.y2_only:
        _phase_a(args, summary)

    if not args.skip_y2:
        try:
            _phase_b(args, summary)
        except ImportError as exc:
            summary["errors"].append({"phase": "y2", "error": f"import_error: {exc}"})
            summary.setdefault("y2_phase", {})["status"] = "skipped"
            summary["y2_phase"]["reason"] = "playwright_not_available"
        except Exception as exc:
            summary["errors"].append({"phase": "y2", "error": str(exc), "error_type": type(exc).__name__})
            summary.setdefault("y2_phase", {})["status"] = "error"

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
