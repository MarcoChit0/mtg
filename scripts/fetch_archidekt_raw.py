#!/usr/bin/env python3
"""Fetch raw Archidekt Commander deck payloads.

This script intentionally stores the full raw API responses before any project
specific filtering. Processing happens in scripts/process_archidekt_raw.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_archidekt_raw import extract_mainboard, validate_deck


BASE_URL = "https://archidekt.com"
DEFAULT_USER_AGENT = "mtg-archidekt-research/0.1"


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


def read_existing_detail_deck_ids(path: Path) -> Set[int]:
    deck_ids: Set[int] = set()
    for record in iter_jsonl(path) or []:
        deck_id = record.get("deck_id")
        if isinstance(deck_id, int):
            deck_ids.add(deck_id)
    return deck_ids


def fetch_json(url: str, user_agent: str = DEFAULT_USER_AGENT, timeout: float = 30.0) -> Tuple[Optional[int], Any]:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            body = response.read().decode("utf-8")
            return status, json.loads(body)
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            payload: Any = json.loads(body) if body else {"error": str(exc)}
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"error": str(exc)}
        return int(exc.code), payload
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, {"error": str(exc), "error_type": type(exc).__name__}


def build_search_url(bracket: int, page: int) -> str:
    query = urlencode(
        {
            "deckFormat": 3,
            "edhBracket": bracket,
            "orderBy": "-viewCount",
            "page": page,
        }
    )
    return f"{BASE_URL}/api/decks/v3/?{query}"


def build_detail_url(deck_id: int) -> str:
    return f"{BASE_URL}/api/decks/{deck_id}/"


def get_search_results(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    return []


def page_is_below_min_views(results: List[Dict[str, Any]], min_views: int) -> bool:
    return bool(results) and all(int(result.get("viewCount") or 0) < min_views for result in results)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch raw Archidekt Commander deck payloads.")
    parser.add_argument("--min-views", type=int, default=1000, help="Minimum Archidekt view count.")
    parser.add_argument("--brackets", type=int, nargs="+", default=[2, 3, 4], help="EDH brackets to fetch.")
    parser.add_argument("--out-dir", type=Path, default=Path("data/raw/archidekt"), help="Raw output directory.")
    parser.add_argument("--sleep-sec", type=non_negative_float, default=0.25, help="Seconds between API calls.")
    parser.add_argument("--max-decks", type=positive_int, default=None, help="Maximum valid deck details to save this run.")
    parser.add_argument("--resume", action="store_true", help="Skip deck ids already present in raw_deck_details.jsonl.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch search pages but do not write detail payloads.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="HTTP User-Agent header.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir: Path = args.out_dir
    search_pages_path = out_dir / "raw_deck_search_pages.jsonl"
    deck_details_path = out_dir / "raw_deck_details.jsonl"
    manifest_path = out_dir / "fetch_manifest.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    existing_deck_ids = read_existing_detail_deck_ids(deck_details_path) if args.resume else set()

    summary: Dict[str, Any] = {
        "record_type": "archidekt_fetch_manifest",
        "run_id": run_id,
        "started_at": utc_now_iso(),
        "finished_at": None,
        "parameters": {
            "min_views": args.min_views,
            "brackets": list(args.brackets),
            "out_dir": str(out_dir),
            "sleep_sec": args.sleep_sec,
            "max_decks": args.max_decks,
            "resume": bool(args.resume),
            "dry_run": bool(args.dry_run),
        },
        "search_pages_fetched": 0,
        "detail_payloads_saved": 0,
        "detail_payloads_attempted": 0,
        "detail_payloads_rejected": 0,
        "skipped_existing": 0,
        "skipped_below_min_views": 0,
        "rejection_reasons": {},
        "errors": [],
        "stopped_reason": None,
        "max_decks_reached": False,
    }

    stop_all = False
    for bracket in args.brackets:
        if stop_all:
            break

        page = 1
        while True:
            if args.max_decks is not None and summary["detail_payloads_saved"] >= args.max_decks:
                summary["stopped_reason"] = "max_decks"
                summary["max_decks_reached"] = True
                stop_all = True
                break

            search_url = build_search_url(bracket=bracket, page=page)
            fetched_at = utc_now_iso()
            status, payload = fetch_json(search_url, user_agent=args.user_agent)
            summary["search_pages_fetched"] += 1

            search_record = {
                "record_type": "archidekt_deck_search_page",
                "run_id": run_id,
                "fetched_at": fetched_at,
                "bracket": bracket,
                "page": page,
                "search_url": search_url,
                "status": status,
                "response": payload,
            }
            if not args.dry_run:
                append_jsonl(search_pages_path, search_record)

            if status != 200:
                summary["errors"].append(
                    {"stage": "search", "bracket": bracket, "page": page, "status": status, "payload": payload}
                )
                break

            results = get_search_results(payload)
            if not results:
                summary["stopped_reason"] = summary["stopped_reason"] or "empty_page"
                break

            if page_is_below_min_views(results, args.min_views):
                summary["stopped_reason"] = summary["stopped_reason"] or "below_min_views"
                break

            for candidate in results:
                if args.max_decks is not None and summary["detail_payloads_saved"] >= args.max_decks:
                    summary["stopped_reason"] = "max_decks"
                    summary["max_decks_reached"] = True
                    stop_all = True
                    break

                view_count = int(candidate.get("viewCount") or 0)
                if view_count < args.min_views:
                    summary["skipped_below_min_views"] += 1
                    continue

                deck_id = candidate.get("id")
                if not isinstance(deck_id, int):
                    summary["errors"].append({"stage": "candidate", "reason": "missing_deck_id", "candidate": candidate})
                    continue

                if deck_id in existing_deck_ids:
                    summary["skipped_existing"] += 1
                    continue

                detail_url = build_detail_url(deck_id)
                summary["detail_payloads_attempted"] += 1
                detail_fetched_at = utc_now_iso()

                if args.dry_run:
                    print(detail_url)
                    continue

                detail_status, detail_payload = fetch_json(detail_url, user_agent=args.user_agent)
                detail_record = {
                    "record_type": "archidekt_deck_detail",
                    "run_id": run_id,
                    "fetched_at": detail_fetched_at,
                    "deck_id": deck_id,
                    "detail_url": detail_url,
                    "status": detail_status,
                    "response": detail_payload,
                }

                if detail_status == 200 and isinstance(detail_payload, dict):
                    mainboard, trace = extract_mainboard(detail_payload)
                    rejection_reasons = validate_deck(
                        detail_payload,
                        mainboard,
                        trace,
                        min_views=args.min_views,
                        brackets=set(args.brackets),
                    )
                    if rejection_reasons:
                        summary["detail_payloads_rejected"] += 1
                        for reason in rejection_reasons:
                            summary["rejection_reasons"][reason] = summary["rejection_reasons"].get(reason, 0) + 1
                    else:
                        append_jsonl(deck_details_path, detail_record)
                        existing_deck_ids.add(deck_id)
                        summary["detail_payloads_saved"] += 1
                else:
                    summary["errors"].append(
                        {"stage": "detail", "deck_id": deck_id, "status": detail_status, "payload": detail_payload}
                    )

                if args.sleep_sec:
                    time.sleep(args.sleep_sec)

            if stop_all:
                break

            page += 1
            if args.sleep_sec:
                time.sleep(args.sleep_sec)

    summary["finished_at"] = utc_now_iso()
    summary["stopped_reason"] = summary["stopped_reason"] or "completed"
    if not args.dry_run:
        append_jsonl(manifest_path, summary)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
