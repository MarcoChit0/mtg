#!/usr/bin/env python3
"""Restore Archidekt raw JSONL files from a Google Drive archive.

The default source is the project raw-data archive shared through Google Drive.
It downloads (or reuses) the archive and extracts the expected raw files into
``data/raw/archidekt``.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


DEFAULT_DRIVE_URL = "https://drive.google.com/file/d/11Ahbt7xHAaQqvEwVdJE2zXzXYNna0IeG/view?usp=drive_link"
DEFAULT_OUT_DIR = Path("data/raw/archidekt")
EXPECTED_RAW_FILES = {
    "fetch_manifest.jsonl",
    "raw_deck_details.jsonl",
    "raw_deck_search_pages.jsonl",
}
USER_AGENT = "mtg-archidekt-raw-restore/0.1"


def extract_drive_file_id(value: str) -> str:
    """Extract a Google Drive file id from a URL or return the id itself."""
    value = value.strip()
    if not value:
        raise ValueError("empty Google Drive URL/file id")
    if re.fullmatch(r"[-_A-Za-z0-9]{20,}", value):
        return value

    parsed = urlparse(value)
    match = re.search(r"/file/d/([^/]+)", parsed.path)
    if match:
        return match.group(1)

    query = parse_qs(parsed.query)
    ids = query.get("id")
    if ids and ids[0]:
        return ids[0]

    raise ValueError(f"Could not extract Google Drive file id from {value!r}")


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num_bytes} B"


def _confirm_token_from_response(headers: Any, body: bytes) -> Optional[str]:
    for key, value in headers.items():
        if key.lower().startswith("set-cookie"):
            match = re.search(r"download_warning[^=]*=([^;]+)", value)
            if match:
                return match.group(1)

    text = body.decode("utf-8", errors="ignore")
    patterns = [
        r'name="confirm"\s+value="([^"]+)"',
        r'confirm=([0-9A-Za-z_-]+)&',
        r'"downloadUrl":"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        token = html.unescape(match.group(1))
        if pattern.startswith('"downloadUrl"'):
            query = parse_qs(urlparse(token.replace("\\u003d", "=").replace("\\u0026", "&")).query)
            values = query.get("confirm")
            if values:
                return values[0]
            continue
        return token
    return None


def _drive_warning_download_url(body: bytes, file_id: str) -> Optional[str]:
    """Return the "Download anyway" URL from Google Drive's warning page."""
    text = body.decode("utf-8", errors="ignore")
    form_match = re.search(r'<form[^>]+id="download-form"[^>]*>', text)
    if not form_match:
        return None

    form_tag = form_match.group(0)
    action_match = re.search(r'action="([^"]+)"', form_tag)
    action = html.unescape(action_match.group(1)) if action_match else "https://drive.google.com/uc"

    # Limit input parsing to the form body so unrelated page inputs cannot
    # leak into the follow-up request.
    tail = text[form_match.end():]
    end_match = re.search(r"</form>", tail, flags=re.IGNORECASE)
    form_body = tail[: end_match.start()] if end_match else tail

    fields: Dict[str, str] = {}
    for input_match in re.finditer(r"<input\b[^>]*>", form_body, flags=re.IGNORECASE):
        tag = input_match.group(0)
        name_match = re.search(r'name="([^"]+)"', tag)
        if not name_match:
            continue
        value_match = re.search(r'value="([^"]*)"', tag)
        fields[html.unescape(name_match.group(1))] = html.unescape(value_match.group(1)) if value_match else ""

    fields.setdefault("id", file_id)
    fields.setdefault("export", "download")
    if "confirm" not in fields:
        return None

    return f"{urljoin('https://drive.google.com/', action)}?{urlencode(fields)}"


def _filename_from_headers(headers: Any) -> Optional[str]:
    disposition = headers.get("Content-Disposition") or headers.get("content-disposition")
    if not disposition:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
    if not match:
        return None
    return html.unescape(match.group(1))


def download_drive_file(file_id: str, archive_path: Path, *, chunk_size: int = 1024 * 1024) -> Dict[str, Any]:
    """Download a public Google Drive file, including large-file confirmations."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    def open_url(url: str):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        return opener.open(request, timeout=60)

    try:
        url = f"https://drive.google.com/uc?{urlencode({'export': 'download', 'id': file_id})}"
        response = None
        headers = None
        for _ in range(3):
            response = open_url(url)
            headers = response.headers
            content_type = headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                break

            body = response.read()
            warning_url = _drive_warning_download_url(body, file_id)
            token = _confirm_token_from_response(headers, body)
            if warning_url:
                url = warning_url
            elif token:
                url = f"https://drive.google.com/uc?{urlencode({'export': 'download', 'id': file_id, 'confirm': token})}"
            else:
                snippet = body[:500].decode("utf-8", errors="ignore").replace("\n", " ")
                raise RuntimeError(
                    "Google Drive returned an HTML page instead of a file. "
                    "Check that the file is shared with anyone who has the link. "
                    f"Snippet: {snippet}"
                )
            response.close()
        else:
            raise RuntimeError("Google Drive kept returning HTML instead of the file after confirmation attempts.")

        assert response is not None
        assert headers is not None

        total_header = headers.get("Content-Length")
        total = int(total_header) if total_header and total_header.isdigit() else None
        downloaded = 0
        started = time.monotonic()
        tmp_path = archive_path.with_suffix(archive_path.suffix + ".download")
        with tmp_path.open("wb") as handle:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if sys.stderr.isatty():
                    if total:
                        pct = downloaded / total * 100
                        sys.stderr.write(f"\rDownloading {human_size(downloaded)} / {human_size(total)} ({pct:5.1f}%)")
                    else:
                        sys.stderr.write(f"\rDownloading {human_size(downloaded)}")
                    sys.stderr.flush()
        if sys.stderr.isatty():
            sys.stderr.write("\n")
            sys.stderr.flush()
        response.close()
        if downloaded < 4096 and not zipfile.is_zipfile(tmp_path):
            snippet = tmp_path.read_bytes()[:500].decode("utf-8", errors="ignore").replace("\n", " ")
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded file does not look like a zip archive. Snippet: {snippet}")
        tmp_path.replace(archive_path)
        return {
            "archive_path": str(archive_path),
            "downloaded_bytes": downloaded,
            "content_length": total,
            "filename": _filename_from_headers(headers),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Could not download Google Drive file {file_id}: {exc}") from exc


def _safe_members(archive: zipfile.ZipFile) -> Iterable[zipfile.ZipInfo]:
    for member in archive.infolist():
        path = Path(member.filename)
        if member.is_dir():
            continue
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe path inside archive: {member.filename}")
        if path.name in EXPECTED_RAW_FILES:
            yield member


def extract_raw_archive(archive_path: Path, out_dir: Path, *, overwrite: bool = False) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: List[str] = []
    skipped: List[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        members = list(_safe_members(archive))
        seen = {Path(member.filename).name for member in members}
        missing = sorted(EXPECTED_RAW_FILES - seen)
        if missing:
            raise ValueError(f"Archive is missing expected file(s): {', '.join(missing)}")

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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore raw Archidekt JSONL files from Google Drive.")
    parser.add_argument("--drive-url", default=DEFAULT_DRIVE_URL, help="Google Drive file URL or file id.")
    parser.add_argument("--file-id", default=None, help="Google Drive file id. Overrides --drive-url.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Destination raw directory.")
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed/archidekt"),
        help="Destination processed directory.",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="Local archive path. Defaults to <out-dir>/Archive.zip.",
    )
    parser.add_argument("--force-download", action="store_true", help="Download even when the local archive exists.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing raw JSONL files.")
    parser.add_argument("--download-only", action="store_true", help="Download the archive without extracting it.")
    parser.add_argument(
        "--skip-process",
        action="store_true",
        help="Restore raw files only; do not run process-archidekt-raw afterward.",
    )
    parser.add_argument(
        "--process-overwrite",
        action="store_true",
        help="Pass --overwrite to process-archidekt-raw.",
    )
    parser.add_argument(
        "--process-y2",
        action="store_true",
        help="Also run EDHPowerLevel enrichment. By default processing uses --skip-y2.",
    )
    parser.add_argument("--workers", type=int, default=1, help="Workers to pass to EDHPowerLevel processing.")
    parser.add_argument("--min-views", type=int, default=1000, help="Minimum Archidekt view count for processing.")
    parser.add_argument("--brackets", type=int, nargs="+", default=[2, 3, 4], help="Accepted EDH brackets for processing.")
    return parser.parse_args(argv)


def process_restored_raw(args: argparse.Namespace) -> Dict[str, Any]:
    """Run the project processor against the restored raw directory."""
    try:
        from process_archidekt_raw import parse_args as parse_process_args, run as run_process  # type: ignore
    except ImportError:
        from scripts.process_archidekt_raw import parse_args as parse_process_args, run as run_process  # type: ignore

    argv = [
        "--raw-dir",
        str(args.out_dir),
        "--out-dir",
        str(args.processed_dir),
        "--min-views",
        str(args.min_views),
        "--brackets",
        *[str(bracket) for bracket in args.brackets],
        "--workers",
        str(args.workers),
    ]
    if args.process_overwrite:
        argv.append("--overwrite")
    if not args.process_y2:
        argv.append("--skip-y2")

    process_args = parse_process_args(argv)
    return run_process(process_args)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    archive_path = args.archive or (args.out_dir / "Archive.zip")
    file_id = args.file_id or extract_drive_file_id(args.drive_url)

    summary: Dict[str, Any] = {
        "file_id": file_id,
        "archive_path": str(archive_path),
        "out_dir": str(args.out_dir),
        "processed_dir": str(args.processed_dir),
        "download": None,
        "extract": None,
        "process": None,
    }

    archive_is_usable = archive_path.exists() and zipfile.is_zipfile(archive_path)
    if args.force_download or not archive_is_usable:
        summary["download"] = download_drive_file(file_id, archive_path)
    else:
        summary["download"] = {
            "status": "skipped_existing_archive",
            "archive_path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
        }

    if not args.download_only:
        summary["extract"] = extract_raw_archive(archive_path, args.out_dir, overwrite=args.overwrite)
        if not args.skip_process:
            summary["process"] = process_restored_raw(args)

    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
