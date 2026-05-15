#!/usr/bin/env python3
"""Refresh EDHPowerLevel labels in processed Archidekt decks with progress."""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from edhpowerlevel_client import EDHPowerLevelClient, decklist_text  # type: ignore
except ImportError:
    from scripts.edhpowerlevel_client import EDHPowerLevelClient, decklist_text  # type: ignore


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DECKS_PATH = DEFAULT_PROCESSED_DIR / "decks.jsonl"
DEFAULT_RESULTS_PATH = DEFAULT_PROCESSED_DIR / "edhpowerlevel_results.jsonl"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def load_latest_results(path: Path) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for record in iter_jsonl(path) or []:
        sid = record.get("snapshot_id")
        if isinstance(sid, str):
            latest[sid] = record
    return latest


def should_query(record: Dict[str, Any], args: argparse.Namespace) -> bool:
    if args.refresh_existing:
        return True
    y2 = record.get("edhpowerlevel")
    if y2 is None:
        return True
    return bool(args.retry_failed and isinstance(y2, dict) and y2.get("error"))


def load_targets(
    decks_path: Path,
    args: argparse.Namespace,
    existing_progress: Dict[str, Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], int]:
    targets: List[Dict[str, Any]] = []
    already_done = 0
    for record in iter_jsonl(decks_path) or []:
        sid = record.get("snapshot_id")
        if not isinstance(sid, str) or not should_query(record, args):
            continue

        previous = existing_progress.get(sid)
        if args.resume and previous and not previous.get("error"):
            already_done += 1
            continue

        targets.append(
            {
                "snapshot_id": sid,
                "deck_id": record.get("deck_id"),
                "mainboard": record.get("mainboard") or [],
            }
        )
    if args.max_decks is not None:
        targets = targets[: args.max_decks]
    return targets, already_done


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}h{minutes:02d}m"
    return f"{minutes:d}m{secs:02d}s"


class ProgressPrinter:
    def __init__(self, total: int, already_done: int, interval_sec: float) -> None:
        self.total = total
        self.already_done = already_done
        self.done = already_done
        self.ok = already_done
        self.failed = 0
        self.interval_sec = max(interval_sec, 0.2)
        self.started = time.monotonic()
        self.last_print = 0.0
        self.lock = threading.Lock()
        self.is_tty = sys.stderr.isatty()

    def update(self, *, ok: bool, force: bool = False) -> None:
        with self.lock:
            self.done += 1
            if ok:
                self.ok += 1
            else:
                self.failed += 1
            self.print_locked(force=force)

    def print_locked(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_print < self.interval_sec:
            return
        self.last_print = now
        elapsed = max(now - self.started, 0.001)
        queried_this_run = max(self.done - self.already_done, 0)
        rate = queried_this_run / elapsed
        remaining = max(self.total - self.done, 0)
        eta = remaining / rate if rate > 0 else None
        pct = (self.done / self.total * 100.0) if self.total else 100.0
        line = (
            f"EDH labels {self.done}/{self.total} ({pct:5.1f}%) "
            f"ok={self.ok} err={self.failed} "
            f"rate={rate * 60:5.1f}/min eta={format_duration(eta)}"
        )
        end = "\r" if self.is_tty and not force else "\n"
        prefix = "\r" if self.is_tty else ""
        print(prefix + line, end=end, file=sys.stderr, flush=True)

    def finish(self) -> None:
        with self.lock:
            self.print_locked(force=True)


def rewrite_decks_with_results(decks_path: Path, results_by_sid: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    tmp_path = decks_path.with_suffix(decks_path.suffix + ".tmp")
    total = 0
    updated = 0
    labeled = 0
    with tmp_path.open("w", encoding="utf-8") as out:
        for record in iter_jsonl(decks_path) or []:
            total += 1
            sid = record.get("snapshot_id")
            result = results_by_sid.get(sid)
            if result is not None:
                payload = {key: value for key, value in result.items() if key != "snapshot_id"}
                record["edhpowerlevel"] = payload
                updated += 1
            y2 = record.get("edhpowerlevel")
            if isinstance(y2, dict) and not y2.get("error"):
                labeled += 1
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            out.write("\n")
    os.replace(tmp_path, decks_path)
    return {"total_decks": total, "updated_decks": updated, "labeled_decks": labeled}


def backup_existing_progress(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    path.replace(backup)
    return backup


def run(args: argparse.Namespace) -> Dict[str, Any]:
    args.workers = max(int(args.workers or 1), 1)
    args.flush_every = max(int(args.flush_every or 1), 1)
    if args.reset_progress:
        backup = backup_existing_progress(args.results_path)
        if backup:
            print(f"Backed up previous progress to {backup}", file=sys.stderr)

    existing_progress = load_latest_results(args.results_path) if args.resume else {}
    targets, already_done = load_targets(args.decks_path, args, existing_progress)
    total = already_done + len(targets)
    work_queue: collections.deque[Dict[str, Any]] = collections.deque(targets)
    work_lock = threading.Lock()
    state_lock = threading.Lock()
    stop_event = threading.Event()

    results_by_sid: Dict[str, Dict[str, Any]] = dict(existing_progress)
    summary: Dict[str, Any] = {
        "started_at": utc_now_iso(),
        "finished_at": None,
        "decks_path": str(args.decks_path),
        "results_path": str(args.results_path),
        "workers": args.workers,
        "refresh_existing": bool(args.refresh_existing),
        "resume": bool(args.resume),
        "already_done": already_done,
        "targets_this_run": len(targets),
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "bracket_distribution": {},
        "errors": [],
    }
    bracket_counts: Counter = Counter()
    progress = ProgressPrinter(total=total, already_done=already_done, interval_sec=args.progress_interval)

    print(
        f"Refreshing EDHPowerLevel labels: total={total}, this_run={len(targets)}, "
        f"already_done={already_done}, workers={args.workers}",
        file=sys.stderr,
    )
    print(f"Progress log: {args.results_path}", file=sys.stderr)

    def flush_locked() -> None:
        stats = rewrite_decks_with_results(args.decks_path, results_by_sid)
        summary.update({f"last_flush_{key}": value for key, value in stats.items()})

    def worker_loop(worker_index: int) -> None:
        try:
            with EDHPowerLevelClient(
                headless=not args.headed,
                analysis_wait_sec=args.analysis_wait,
                context_recycle_every=args.recycle_every,
            ) as client:
                while not stop_event.is_set():
                    with work_lock:
                        if not work_queue:
                            return
                        item = work_queue.popleft()

                    decklist = decklist_text(item["mainboard"])
                    result = client.analyze(decklist)
                    result_with_id = dict(result)
                    result_with_id["snapshot_id"] = item["snapshot_id"]
                    result_with_id["deck_id"] = item["deck_id"]
                    result_with_id["queried_at"] = utc_now_iso()
                    result_with_id["worker"] = worker_index

                    ok = not bool(result.get("error"))
                    with state_lock:
                        append_jsonl(args.results_path, result_with_id)
                        results_by_sid[item["snapshot_id"]] = result_with_id
                        summary["attempted"] += 1
                        if ok:
                            summary["succeeded"] += 1
                            if "commander_bracket" in result:
                                bracket_counts[result["commander_bracket"]] += 1
                        else:
                            summary["failed"] += 1

                        progress.update(ok=ok)
                        if summary["attempted"] % args.flush_every == 0:
                            flush_locked()

                    if args.sleep:
                        time.sleep(args.sleep)
        except Exception as exc:
            stop_event.set()
            with state_lock:
                summary["errors"].append(
                    {
                        "worker": worker_index,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )

    started = time.monotonic()
    interrupted = False
    threads = [
        threading.Thread(target=worker_loop, args=(index,), name=f"edh-refresh-{index}")
        for index in range(max(args.workers, 1))
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        interrupted = True
        stop_event.set()
        print("\nInterrupted. Waiting for active deck analyses to finish...", file=sys.stderr)
        for thread in threads:
            thread.join()
    finally:
        with state_lock:
            flush_locked()
        progress.finish()

    summary["finished_at"] = utc_now_iso()
    summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
    summary["bracket_distribution"] = dict(bracket_counts)
    if summary["errors"]:
        summary["status"] = "error"
    elif interrupted:
        summary["status"] = "interrupted"
    else:
        summary["status"] = "done"

    if args.summary_path:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return summary


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh EDHPowerLevel labels with visible progress.")
    parser.add_argument("--decks-path", type=Path, default=DEFAULT_DECKS_PATH, help="Processed decks.jsonl path.")
    parser.add_argument(
        "--results-path",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help="Append-only EDHPowerLevel results JSONL path.",
    )
    parser.add_argument("--workers", type=int, default=8, help="Parallel Chromium workers.")
    parser.add_argument("--max-decks", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep after each query per worker.")
    parser.add_argument("--analysis-wait", type=float, default=8.0, help="Minimum seconds to wait after Analyze before polling for a stable result.")
    parser.add_argument("--recycle-every", type=int, default=50, help="Recycle each browser page every N decks.")
    parser.add_argument("--flush-every", type=int, default=500, help="Rewrite decks.jsonl every N new results.")
    parser.add_argument("--progress-interval", type=float, default=2.0, help="Seconds between progress updates.")
    parser.add_argument("--headed", action="store_true", help="Show Chromium windows for debugging.")
    parser.add_argument("--refresh-existing", action="store_true", help="Re-query decks even if labels exist.")
    parser.add_argument("--retry-failed", action="store_true", help="Include decks whose current label is an error.")
    parser.add_argument("--reset-progress", action="store_true", help="Move the current results log aside before starting.")
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Do not skip successful snapshot_ids already present in --results-path.",
    )
    parser.set_defaults(resume=True)
    parser.add_argument("--summary-path", type=Path, default=None, help="Optional JSON summary output.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if summary["status"] == "interrupted":
        return 130
    return 1 if summary["status"] == "error" or summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
