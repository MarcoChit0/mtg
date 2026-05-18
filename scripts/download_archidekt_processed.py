#!/usr/bin/env python3
"""Restore processed Archidekt data from a Google Drive archive."""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set

try:
    from download_archidekt_raw import download_drive_file, extract_drive_file_id  # type: ignore
except ImportError:
    from scripts.download_archidekt_raw import download_drive_file, extract_drive_file_id  # type: ignore


DEFAULT_DRIVE_URL = os.environ.get(
    "ARCHIDEKT_PROCESSED_DRIVE_URL",
    "https://drive.google.com/file/d/1gXCxPeFjxgkNmizWCTU62m-s311B05R0/view?usp=sharing",
)
DEFAULT_ARCHIVE = Path("processed.zip")
DEFAULT_OUT_DIR = Path("data/processed/archidekt")
REQUIRED_PROCESSED_FILES: Set[str] = {
    "cards.jsonl",
    "decks.jsonl",
    "edhpowerlevel_results.jsonl",
    "processing_manifest.jsonl",
    "rejected_decks.jsonl",
}
OPTIONAL_PROCESSED_FILES: Set[str] = {
    "README.md",
    "bag_of_cards.jsonl",
    "deck_features.jsonl",
    "feature_manifest.jsonl",
}
ALLOWED_PROCESSED_FILES = REQUIRED_PROCESSED_FILES | OPTIONAL_PROCESSED_FILES
COLOR_ORDER = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
COLOR_ALIASES = {
    "WHITE": "W",
    "BLUE": "U",
    "BLACK": "B",
    "RED": "R",
    "GREEN": "G",
}


def _safe_members(archive: zipfile.ZipFile) -> Iterable[zipfile.ZipInfo]:
    for member in archive.infolist():
        path = Path(member.filename)
        if member.is_dir():
            continue
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe path inside archive: {member.filename}")
        if path.name in ALLOWED_PROCESSED_FILES:
            yield member


def extract_processed_archive(archive_path: Path, out_dir: Path, *, overwrite: bool = False) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: List[str] = []
    skipped: List[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        members = list(_safe_members(archive))
        seen = {Path(member.filename).name for member in members}
        missing = sorted(REQUIRED_PROCESSED_FILES - seen)
        if missing:
            raise ValueError(f"Archive is missing expected processed file(s): {', '.join(missing)}")

        for member in members:
            target = out_dir / Path(member.filename).name
            if target.exists() and not overwrite:
                skipped.append(str(target))
                continue
            tmp_path = target.with_suffix(target.suffix + ".tmp")
            with archive.open(member) as source, tmp_path.open("wb") as dest:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    dest.write(chunk)
            tmp_path.replace(target)
            extracted.append(str(target))

    return {
        "archive_path": str(archive_path),
        "out_dir": str(out_dir),
        "extracted": extracted,
        "skipped_existing": skipped,
    }


def _jsonl_records(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} line {line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object in {path} line {line_number}")
            yield payload


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _counter_sort_key(item: Any) -> Any:
    if isinstance(item, int):
        return (0, item)
    if isinstance(item, str) and item.isdigit():
        return (0, int(item))
    return (1, str(item))


def _counter_dict(counter: Counter[Any]) -> Dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter, key=_counter_sort_key)}


def _top_items(counter: Counter[str], limit: int = 10) -> List[Dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _mean(total: float, count: int) -> Optional[float]:
    return round(total / count, 3) if count else None


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _color_identity_key(colors: Any) -> str:
    if not isinstance(colors, list):
        return "unknown"
    normalized: List[str] = []
    for color in colors:
        if not isinstance(color, str) or not color:
            continue
        symbol = COLOR_ALIASES.get(color.upper(), color[0].upper())
        if symbol in COLOR_ORDER:
            normalized.append(symbol)
    if not normalized:
        return "C"
    unique = sorted(set(normalized), key=lambda symbol: COLOR_ORDER[symbol])
    return "".join(unique)


def _file_report(path: Path) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "exists": path.exists(),
        "path": str(path),
    }
    if path.exists():
        report["size_bytes"] = path.stat().st_size
        if path.suffix == ".jsonl":
            report["lines"] = _line_count(path)
    return report


def _snapshot_id_report(path: Path, deck_snapshot_ids: Set[str]) -> Dict[str, Any]:
    snapshot_ids: Set[str] = set()
    for record in _jsonl_records(path):
        snapshot_id = record.get("snapshot_id")
        if isinstance(snapshot_id, str):
            snapshot_ids.add(snapshot_id)

    missing = deck_snapshot_ids - snapshot_ids
    extra = snapshot_ids - deck_snapshot_ids
    return {
        "path": str(path),
        "snapshot_ids": len(snapshot_ids),
        "matches_decks": not missing and not extra,
        "missing_from_file": len(missing),
        "extra_in_file": len(extra),
    }


def build_processed_report(out_dir: Path) -> Dict[str, Any]:
    decks_path = out_dir / "decks.jsonl"
    cards_path = out_dir / "cards.jsonl"
    if not decks_path.exists():
        raise FileNotFoundError(f"Missing required processed file: {decks_path}")
    if not cards_path.exists():
        raise FileNotFoundError(f"Missing required processed file: {cards_path}")

    files = {filename: _file_report(out_dir / filename) for filename in sorted(ALLOWED_PROCESSED_FILES)}
    missing_required_files = sorted(
        filename for filename in REQUIRED_PROCESSED_FILES if not (out_dir / filename).exists()
    )

    deck_snapshot_ids: Set[str] = set()
    unique_deck_ids: Set[Any] = set()
    referenced_oracle_uids: Set[str] = set()
    archidekt_brackets: Counter[Any] = Counter()
    edhpowerlevel_brackets: Counter[Any] = Counter()
    color_identities: Counter[str] = Counter()
    commander_rows: Counter[int] = Counter()
    top_commanders: Counter[str] = Counter()

    total_decks = 0
    labeled_edhpowerlevel = 0
    missing_edhpowerlevel = 0
    invalid_mainboard_count = 0
    mainboard_total = 0
    mainboard_min: Optional[int] = None
    mainboard_max: Optional[int] = None
    view_count_total = 0
    view_count_seen = 0
    view_count_min: Optional[int] = None
    view_count_max: Optional[int] = None
    power_level_total = 0.0
    power_level_seen = 0
    updated_at_min: Optional[str] = None
    updated_at_max: Optional[str] = None

    for deck in _jsonl_records(decks_path):
        total_decks += 1
        deck_id = deck.get("deck_id")
        if deck_id is not None:
            unique_deck_ids.add(deck_id)
        snapshot_id = deck.get("snapshot_id")
        if isinstance(snapshot_id, str):
            deck_snapshot_ids.add(snapshot_id)

        mainboard = deck.get("mainboard")
        if not isinstance(mainboard, list):
            mainboard = []
        mainboard_count = deck.get("mainboard_count")
        if not isinstance(mainboard_count, int):
            mainboard_count = sum(card.get("quantity", 0) for card in mainboard if isinstance(card, dict))
        mainboard_total += mainboard_count
        mainboard_min = mainboard_count if mainboard_min is None else min(mainboard_min, mainboard_count)
        mainboard_max = mainboard_count if mainboard_max is None else max(mainboard_max, mainboard_count)
        if mainboard_count != 100:
            invalid_mainboard_count += 1

        commanders: List[str] = []
        for card in mainboard:
            if not isinstance(card, dict):
                continue
            oracle_uid = card.get("oracle_uid")
            if isinstance(oracle_uid, str):
                referenced_oracle_uids.add(oracle_uid)
            if card.get("is_commander"):
                commanders.append(str(card.get("oracle_name") or oracle_uid or "unknown"))
        commander_rows[len(commanders)] += 1
        top_commanders.update(commanders)

        archidekt_bracket = deck.get("archidekt_edh_bracket")
        if archidekt_bracket is not None:
            archidekt_brackets[archidekt_bracket] += 1

        edhpowerlevel = deck.get("edhpowerlevel")
        if isinstance(edhpowerlevel, dict) and edhpowerlevel:
            labeled_edhpowerlevel += 1
            bracket = edhpowerlevel.get("commander_bracket")
            if bracket is not None:
                edhpowerlevel_brackets[bracket] += 1
            power_level = _parse_float(edhpowerlevel.get("power_level"))
            if power_level is not None:
                power_level_total += power_level
                power_level_seen += 1
        else:
            missing_edhpowerlevel += 1

        trace = deck.get("validation_trace")
        colors = trace.get("commander_color_identity") if isinstance(trace, dict) else None
        color_identities[_color_identity_key(colors)] += 1

        view_count = deck.get("view_count")
        if isinstance(view_count, int):
            view_count_total += view_count
            view_count_seen += 1
            view_count_min = view_count if view_count_min is None else min(view_count_min, view_count)
            view_count_max = view_count if view_count_max is None else max(view_count_max, view_count)

        updated_at = deck.get("archidekt_updated_at")
        if isinstance(updated_at, str):
            updated_at_min = updated_at if updated_at_min is None else min(updated_at_min, updated_at)
            updated_at_max = updated_at if updated_at_max is None else max(updated_at_max, updated_at)

    card_uids = {
        record["oracle_uid"]
        for record in _jsonl_records(cards_path)
        if isinstance(record.get("oracle_uid"), str)
    }
    missing_card_uids = referenced_oracle_uids - card_uids

    snapshot_checks: Dict[str, Any] = {}
    for filename in ("deck_features.jsonl", "bag_of_cards.jsonl"):
        path = out_dir / filename
        if path.exists():
            snapshot_checks[filename] = _snapshot_id_report(path, deck_snapshot_ids)

    checks = {
        "required_files_present": not missing_required_files,
        "missing_required_files": missing_required_files,
        "snapshot_alignment": snapshot_checks,
        "card_reference_coverage": {
            "referenced_oracle_uids": len(referenced_oracle_uids),
            "cards_file_oracle_uids": len(card_uids),
            "missing_oracle_uids": len(missing_card_uids),
            "covers_all_references": not missing_card_uids,
        },
        "mainboard_count_all_100": invalid_mainboard_count == 0,
    }

    status_ok = (
        checks["required_files_present"]
        and checks["card_reference_coverage"]["covers_all_references"]
        and checks["mainboard_count_all_100"]
        and all(check["matches_decks"] for check in snapshot_checks.values())
    )

    return {
        "status": "ok" if status_ok else "needs_attention",
        "out_dir": str(out_dir),
        "files": files,
        "decks": {
            "total_snapshots": total_decks,
            "unique_deck_ids": len(unique_deck_ids),
            "duplicate_deck_ids": total_decks - len(unique_deck_ids),
            "mainboard_count": {
                "min": mainboard_min,
                "max": mainboard_max,
                "mean": _mean(float(mainboard_total), total_decks),
                "not_100": invalid_mainboard_count,
            },
            "commander_rows": _counter_dict(commander_rows),
            "archidekt_edh_brackets": _counter_dict(archidekt_brackets),
            "edhpowerlevel": {
                "labeled": labeled_edhpowerlevel,
                "missing": missing_edhpowerlevel,
                "commander_brackets": _counter_dict(edhpowerlevel_brackets),
                "power_level_mean": _mean(power_level_total, power_level_seen),
            },
            "color_identities": _counter_dict(color_identities),
            "view_count": {
                "min": view_count_min,
                "max": view_count_max,
                "mean": _mean(float(view_count_total), view_count_seen),
            },
            "archidekt_updated_at": {
                "min": updated_at_min,
                "max": updated_at_max,
            },
            "top_commanders": _top_items(top_commanders),
        },
        "checks": checks,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore processed Archidekt JSONL files from Google Drive.")
    parser.add_argument("--drive-url", default=DEFAULT_DRIVE_URL, help="Google Drive file URL or file id.")
    parser.add_argument("--file-id", default=None, help="Google Drive file id. Overrides --drive-url.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Destination processed directory.")
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="Local archive path. Defaults to ./processed.zip.",
    )
    parser.add_argument("--force-download", action="store_true", help="Download even when the local archive exists.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing processed JSONL files.")
    parser.add_argument("--download-only", action="store_true", help="Download the archive without extracting it.")
    parser.add_argument("--skip-report", action="store_true", help="Do not build the extracted deck report.")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Optional JSON path for the extracted deck report.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    archive_path = args.archive or DEFAULT_ARCHIVE
    source = args.file_id or args.drive_url
    archive_is_usable = archive_path.exists() and zipfile.is_zipfile(archive_path)
    if not source and (args.force_download or not archive_is_usable):
        raise ValueError("Provide --drive-url or --file-id for the processed data archive.")
    file_id = args.file_id or (extract_drive_file_id(args.drive_url) if args.drive_url else None)

    summary: Dict[str, Any] = {
        "file_id": file_id,
        "archive_path": str(archive_path),
        "out_dir": str(args.out_dir),
        "download": None,
        "extract": None,
        "report": None,
    }

    if args.force_download or not archive_is_usable:
        assert file_id is not None
        summary["download"] = download_drive_file(file_id, archive_path)
    else:
        summary["download"] = {
            "status": "skipped_existing_archive",
            "archive_path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
        }

    if not args.download_only:
        summary["extract"] = extract_processed_archive(archive_path, args.out_dir, overwrite=args.overwrite)
        if not args.skip_report:
            report = build_processed_report(args.out_dir)
            summary["report"] = report
            if args.report_path:
                args.report_path.parent.mkdir(parents=True, exist_ok=True)
                args.report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
