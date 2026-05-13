#!/usr/bin/env python3
"""Fetch raw Archidekt Commander deck payloads.

This script intentionally stores the full raw API responses before any project
specific filtering. Processing happens in scripts/process_archidekt_raw.py.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=1,
        help="Number of parallel workers fetching Archidekt deck detail payloads.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip deck ids already present in raw_deck_details.jsonl.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch search pages but do not write detail payloads.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="HTTP User-Agent header.")
    parser.add_argument("--no-progress", action="store_true", help="Disable the stderr progress bar.")
    return parser.parse_args(argv)


def format_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


class ProgressReporter:
    def __init__(self, max_decks: Optional[int], enabled: bool) -> None:
        self.max_decks = max_decks
        self.enabled = enabled and sys.stderr.isatty()
        self.start = time.monotonic()
        self.last_width = 0

    def render(self, summary: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        saved = int(summary["detail_payloads_saved"])
        attempted = int(summary["detail_payloads_attempted"])
        rejected = int(summary["detail_payloads_rejected"])
        pages = int(summary["search_pages_fetched"])
        elapsed = max(time.monotonic() - self.start, 1e-9)
        rate = saved / elapsed
        if self.max_decks:
            total = self.max_decks
            ratio = min(saved / total, 1.0)
            bar_width = 24
            filled = int(bar_width * ratio)
            bar = "#" * filled + "-" * (bar_width - filled)
            eta = (total - saved) / rate if rate > 0 else 0.0
            line = (
                f"[{bar}] {saved}/{total} ({ratio*100:5.1f}%) | "
                f"attempt={attempted} reject={rejected} pages={pages} | "
                f"{rate:.2f} decks/s eta={format_duration(eta)}"
            )
        else:
            line = (
                f"saved={saved} attempt={attempted} reject={rejected} pages={pages} | "
                f"{rate:.2f} decks/s elapsed={format_duration(elapsed)}"
            )
        padded = line.ljust(self.last_width)
        sys.stderr.write("\r" + padded)
        sys.stderr.flush()
        self.last_width = max(self.last_width, len(line))

    def finish(self, summary: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.render(summary)
        sys.stderr.write("\n")
        sys.stderr.flush()


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
            "workers": args.workers,
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

    workers = max(int(args.workers or 1), 1)
    progress = ProgressReporter(max_decks=args.max_decks, enabled=not args.no_progress)
    progress.render(summary)

    def fetch_detail_record(deck_id: int) -> Dict[str, Any]:
        detail_url = build_detail_url(deck_id)
        detail_fetched_at = utc_now_iso()
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

        result: Dict[str, Any] = {
            "deck_id": deck_id,
            "detail_record": detail_record,
            "status": detail_status,
            "payload": detail_payload,
            "rejection_reasons": [],
            "error": None,
        }
        if detail_status == 200 and isinstance(detail_payload, dict):
            mainboard, trace = extract_mainboard(detail_payload)
            result["rejection_reasons"] = validate_deck(
                detail_payload,
                mainboard,
                trace,
                min_views=args.min_views,
                brackets=set(args.brackets),
            )
        else:
            result["error"] = {
                "stage": "detail",
                "deck_id": deck_id,
                "status": detail_status,
                "payload": detail_payload,
            }

        if args.sleep_sec:
            time.sleep(args.sleep_sec)
        return result

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
            progress.render(summary)

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

            detail_deck_ids: List[int] = []
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

                if args.dry_run:
                    summary["detail_payloads_attempted"] += 1
                    print(detail_url)
                    continue

                detail_deck_ids.append(deck_id)

            if args.dry_run:
                progress.render(summary)
                if stop_all:
                    break
                page += 1
                if args.sleep_sec:
                    time.sleep(args.sleep_sec)
                continue

            next_index = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}

                def submit_available() -> None:
                    nonlocal next_index
                    while next_index < len(detail_deck_ids) and len(futures) < workers:
                        if (
                            args.max_decks is not None
                            and summary["detail_payloads_saved"] + len(futures) >= args.max_decks
                        ):
                            break
                        deck_id_to_fetch = detail_deck_ids[next_index]
                        next_index += 1
                        summary["detail_payloads_attempted"] += 1
                        futures[executor.submit(fetch_detail_record, deck_id_to_fetch)] = deck_id_to_fetch

                submit_available()
                while futures:
                    future = next(as_completed(futures))
                    deck_id = futures.pop(future)
                    try:
                        detail_result = future.result()
                    except Exception as exc:
                        summary["errors"].append(
                            {"stage": "detail", "deck_id": deck_id, "error": str(exc), "error_type": type(exc).__name__}
                        )
                        progress.render(summary)
                        submit_available()
                        continue

                    if detail_result["error"]:
                        summary["errors"].append(detail_result["error"])
                    elif detail_result["rejection_reasons"]:
                        summary["detail_payloads_rejected"] += 1
                        for reason in detail_result["rejection_reasons"]:
                            summary["rejection_reasons"][reason] = summary["rejection_reasons"].get(reason, 0) + 1
                    else:
                        append_jsonl(deck_details_path, detail_result["detail_record"])
                        existing_deck_ids.add(deck_id)
                        summary["detail_payloads_saved"] += 1

                    if args.max_decks is not None and summary["detail_payloads_saved"] >= args.max_decks:
                        summary["stopped_reason"] = "max_decks"
                        summary["max_decks_reached"] = True
                        stop_all = True

                    progress.render(summary)
                    submit_available()

            if stop_all:
                break

            page += 1
            if args.sleep_sec:
                time.sleep(args.sleep_sec)

    summary["finished_at"] = utc_now_iso()
    summary["stopped_reason"] = summary["stopped_reason"] or "completed"
    progress.finish(summary)
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
