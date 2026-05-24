#!/usr/bin/env python3
"""Archive and sync Phase-E experiment artifacts through rclone."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from download_archidekt_raw import download_drive_file, extract_drive_file_id  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.download_archidekt_raw import download_drive_file, extract_drive_file_id  # type: ignore


DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_REMOTE = os.environ.get("MTG_EXPERIMENTS_DRIVE_REMOTE", "mtg-experiments:")
DEFAULT_PUBLIC_MANIFEST_URL = os.environ.get("MTG_EXPERIMENTS_MANIFEST_URL", "1MU0AilsDnG11M9pySkDUebLKkJ4a_5kR")
MANIFEST_FILENAME = "experiments_manifest.json"
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {1, 2}
MODEL_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
USER_AGENT = "mtg-experiments-sync/0.1"

# Bundles carry shared artifacts that aren't tied to a single (rep, algo) model:
# - spot_check: experiments/spot_check/
# - voting: experiments/voting/
# - shared: experiments/seeds.json + experiments/folds.json (top-level files).
KNOWN_BUNDLES: Dict[str, Dict[str, Any]] = {
    "spot_check": {
        "kind": "directory",
        "relative_path": "spot_check",
    },
    "voting": {
        "kind": "directory",
        "relative_path": "voting",
    },
    "shared": {
        "kind": "files",
        "relative_paths": ("seeds.json", "folds.json"),
    },
}


def validate_model_id(model_id: str) -> str:
    if not MODEL_ID_RE.fullmatch(model_id):
        raise ValueError(f"Invalid model id: {model_id}")
    return model_id


def valid_remote_zip_model_id(name: str) -> Optional[str]:
    """Return the model/bundle id for a valid remote zip filename, else None."""
    if not name.endswith(".zip"):
        return None
    model_id = Path(name).stem
    if not MODEL_ID_RE.fullmatch(model_id):
        return None
    return model_id


def is_valid_zip(path: Path) -> bool:
    try:
        return path.exists() and zipfile.is_zipfile(path)
    except OSError:
        return False


def write_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def safe_archive_members(archive: zipfile.ZipFile) -> Iterable[zipfile.ZipInfo]:
    for member in archive.infolist():
        path = Path(member.filename)
        if member.is_dir():
            continue
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe path inside archive: {member.filename}")
        yield member


def create_model_archive(
    model_id: str,
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    model_id = validate_model_id(model_id)
    model_dir = experiment_dir / model_id
    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"Missing experiment model directory: {model_dir}")

    archive_dir = archive_dir or (experiment_dir / "archives")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{model_id}.zip"
    tmp_path = archive_path.with_suffix(".zip.tmp")
    files: List[str] = []

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted(model_dir.rglob("*")):
            if not path.is_file():
                continue
            arcname = path.relative_to(experiment_dir)
            archive.write(path, arcname.as_posix())
            files.append(arcname.as_posix())
    tmp_path.replace(archive_path)

    return {
        "status": "ok",
        "model_id": model_id,
        "archive_path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "files": files,
    }


def bundle_source_paths(bundle_id: str, *, experiment_dir: Path) -> List[Path]:
    """Resolve the on-disk paths a bundle should archive."""
    spec = KNOWN_BUNDLES.get(bundle_id)
    if spec is None:
        raise ValueError(f"Unknown bundle id: {bundle_id}. Known: {sorted(KNOWN_BUNDLES)}")
    if spec["kind"] == "directory":
        return [experiment_dir / spec["relative_path"]]
    if spec["kind"] == "files":
        return [experiment_dir / rel for rel in spec["relative_paths"]]
    raise ValueError(f"Unsupported bundle kind for {bundle_id}: {spec['kind']}")


def bundle_has_content(bundle_id: str, *, experiment_dir: Path) -> bool:
    """True when at least one source path for the bundle exists locally."""
    for source in bundle_source_paths(bundle_id, experiment_dir=experiment_dir):
        if source.is_dir() and any(source.rglob("*")):
            return True
        if source.is_file():
            return True
    return False


def create_bundle_archive(
    bundle_id: str,
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Zip the configured paths for a bundle into ``<archive_dir>/<bundle_id>.zip``."""
    validate_model_id(bundle_id)
    sources = bundle_source_paths(bundle_id, experiment_dir=experiment_dir)
    if not any(source.exists() for source in sources):
        raise FileNotFoundError(
            f"No bundle sources exist for {bundle_id}: {[str(s) for s in sources]}"
        )

    archive_dir = archive_dir or (experiment_dir / "archives")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{bundle_id}.zip"
    tmp_path = archive_path.with_suffix(".zip.tmp")
    files: List[str] = []

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for source in sources:
            if source.is_dir():
                for path in sorted(source.rglob("*")):
                    if not path.is_file():
                        continue
                    arcname = path.relative_to(experiment_dir)
                    archive.write(path, arcname.as_posix())
                    files.append(arcname.as_posix())
            elif source.is_file():
                arcname = source.relative_to(experiment_dir)
                archive.write(source, arcname.as_posix())
                files.append(arcname.as_posix())
    tmp_path.replace(archive_path)

    return {
        "status": "ok",
        "bundle_id": bundle_id,
        "archive_path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "files": files,
    }


def upload_bundle(
    bundle_id: str,
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
    remote: str = DEFAULT_REMOTE,
    rclone_bin: str = "rclone",
) -> Dict[str, Any]:
    """Archive and upload a known bundle (spot_check / voting / shared)."""
    remote = require_remote(remote)
    archive = create_bundle_archive(bundle_id, experiment_dir=experiment_dir, archive_dir=archive_dir)
    command = [
        rclone_bin,
        "copyto",
        archive["archive_path"],
        remote_file_path(remote, f"{bundle_id}.zip"),
    ]
    rclone = run_rclone(command)
    status = "ok" if rclone["returncode"] == 0 else "failed"
    return {
        "status": status,
        "bundle_id": bundle_id,
        "archive": archive,
        "remote": remote,
        "rclone": rclone,
    }


def extract_model_archive(
    archive_path: Path,
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    overwrite: bool = False,
) -> Dict[str, Any]:
    if not archive_path.exists():
        raise FileNotFoundError(f"Missing experiment archive: {archive_path}")

    experiment_dir.mkdir(parents=True, exist_ok=True)
    root = experiment_dir.resolve()
    extracted: List[str] = []
    skipped: List[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in safe_archive_members(archive):
            target = experiment_dir / member.filename
            target_parent = target.parent
            target_parent.mkdir(parents=True, exist_ok=True)
            resolved_target = target.resolve()
            if not resolved_target.is_relative_to(root):
                raise ValueError(f"Unsafe archive target: {member.filename}")
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
        "status": "ok",
        "archive_path": str(archive_path),
        "experiment_dir": str(experiment_dir),
        "extracted": extracted,
        "skipped_existing": skipped,
    }


def remote_archive_path(remote: str, model_id: str) -> str:
    return remote_file_path(remote, f"{validate_model_id(model_id)}.zip")


def remote_file_path(remote: str, filename: str) -> str:
    remote = remote.rstrip("/")
    filename = filename.lstrip("/")
    if remote.endswith(":"):
        return f"{remote}{filename}"
    return f"{remote}/{filename}"


def run_rclone(command: Sequence[str]) -> Dict[str, Any]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "ok" if completed.returncode == 0 else "failed",
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_remote(remote: str) -> str:
    if not remote:
        raise ValueError(
            "Missing experiments Drive remote. Pass --experiments-drive-remote "
            "or set MTG_EXPERIMENTS_DRIVE_REMOTE."
        )
    return remote


def require_manifest_url(manifest_url: str) -> str:
    if not manifest_url:
        raise ValueError(
            "Missing public experiments manifest. Pass --experiments-manifest-url "
            "or set MTG_EXPERIMENTS_MANIFEST_URL."
        )
    return manifest_url


def download_public_drive_file(file_id: str, out_path: Path, *, chunk_size: int = 1024 * 1024) -> Dict[str, Any]:
    """Download a public Google Drive file without requiring rclone."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/uc?{urlencode({'export': 'download', 'id': file_id})}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    tmp_path = out_path.with_suffix(out_path.suffix + ".download")
    downloaded = 0
    try:
        with urlopen(request, timeout=60) as response, tmp_path.open("wb") as handle:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
    except (HTTPError, URLError, TimeoutError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download public Drive file {file_id}: {exc}") from exc
    tmp_path.replace(out_path)
    return {
        "status": "ok",
        "file_id": file_id,
        "path": str(out_path),
        "downloaded_bytes": downloaded,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def read_public_manifest(manifest_url: str, *, archive_dir: Path) -> Dict[str, Any]:
    manifest_url = require_manifest_url(manifest_url)
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = archive_dir / MANIFEST_FILENAME

    source_path = Path(manifest_url)
    if source_path.exists():
        manifest_path.write_bytes(source_path.read_bytes())
        download = {
            "status": "ok",
            "source": str(source_path),
            "path": str(manifest_path),
            "mode": "local_file",
        }
    else:
        file_id = extract_drive_file_id(manifest_url)
        download = download_public_drive_file(file_id, manifest_path)
        download["mode"] = "public_drive"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid public experiments manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Public experiments manifest must be a JSON object.")
    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        raise ValueError(
            f"Unsupported public experiments manifest schema_version: {schema_version!r}. "
            f"Supported: {sorted(SUPPORTED_MANIFEST_SCHEMA_VERSIONS)}"
        )
    models = manifest.get("models")
    if not isinstance(models, list):
        raise ValueError("Public experiments manifest must contain a models list.")
    bundles = manifest.get("bundles") or []
    if not isinstance(bundles, list):
        raise ValueError("Public experiments manifest 'bundles' must be a list when present.")
    return {
        "status": "ok",
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "download": download,
    }


def manifest_model_records(manifest: Mapping[str, Any], models: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    selected = {validate_model_id(model) for model in models} if models else None
    records: List[Dict[str, Any]] = []
    for raw_record in manifest.get("models", []):
        if not isinstance(raw_record, dict):
            raise ValueError("Each manifest model entry must be an object.")
        model_id = validate_model_id(str(raw_record.get("model_id", "")))
        if selected is not None and model_id not in selected:
            continue
        filename = str(raw_record.get("filename") or f"{model_id}.zip")
        if filename != f"{model_id}.zip":
            raise ValueError(f"Manifest filename for {model_id} must be {model_id}.zip")
        drive_file_id = str(raw_record.get("drive_file_id") or "")
        if not drive_file_id:
            raise ValueError(f"Manifest entry for {model_id} is missing drive_file_id.")
        records.append({
            "model_id": model_id,
            "filename": filename,
            "drive_file_id": drive_file_id,
            "size_bytes": raw_record.get("size_bytes"),
            "sha256": raw_record.get("sha256"),
        })
    if selected is not None:
        found = {record["model_id"] for record in records}
        missing = sorted(selected - found)
        if missing:
            raise ValueError(f"Public experiments manifest is missing model(s): {', '.join(missing)}")
    return records


def manifest_bundle_records(manifest: Mapping[str, Any], bundles: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Read bundle entries from a manifest (schema v2). v1 manifests yield []."""
    raw_entries = manifest.get("bundles") or []
    selected = {validate_model_id(bundle) for bundle in bundles} if bundles else None
    records: List[Dict[str, Any]] = []
    for raw_record in raw_entries:
        if not isinstance(raw_record, dict):
            raise ValueError("Each manifest bundle entry must be an object.")
        bundle_id = validate_model_id(str(raw_record.get("bundle_id") or raw_record.get("model_id") or ""))
        if selected is not None and bundle_id not in selected:
            continue
        filename = str(raw_record.get("filename") or f"{bundle_id}.zip")
        if filename != f"{bundle_id}.zip":
            raise ValueError(f"Manifest filename for bundle {bundle_id} must be {bundle_id}.zip")
        drive_file_id = str(raw_record.get("drive_file_id") or "")
        if not drive_file_id:
            raise ValueError(f"Manifest bundle entry for {bundle_id} is missing drive_file_id.")
        records.append({
            "bundle_id": bundle_id,
            "filename": filename,
            "drive_file_id": drive_file_id,
            "size_bytes": raw_record.get("size_bytes"),
            "sha256": raw_record.get("sha256"),
        })
    if selected is not None:
        found = {record["bundle_id"] for record in records}
        missing = sorted(selected - found)
        if missing:
            raise ValueError(f"Public experiments manifest is missing bundle(s): {', '.join(missing)}")
    return records


def upload_model(
    model_id: str,
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
    remote: str = DEFAULT_REMOTE,
    rclone_bin: str = "rclone",
) -> Dict[str, Any]:
    remote = require_remote(remote)
    archive = create_model_archive(model_id, experiment_dir=experiment_dir, archive_dir=archive_dir)
    command = [
        rclone_bin,
        "copyto",
        archive["archive_path"],
        remote_archive_path(remote, model_id),
    ]
    rclone = run_rclone(command)
    status = "ok" if rclone["returncode"] == 0 else "failed"
    return {
        "status": status,
        "model_id": validate_model_id(model_id),
        "archive": archive,
        "remote": remote,
        "rclone": rclone,
    }


def list_remote_archives(*, remote: str = DEFAULT_REMOTE, rclone_bin: str = "rclone") -> Dict[str, Any]:
    remote = require_remote(remote)
    command = [rclone_bin, "lsf", remote, "--files-only", "--include", "*.zip"]
    rclone = run_rclone(command)
    files: List[str] = []
    skipped_files: List[str] = []
    if rclone["returncode"] == 0:
        for line in rclone["stdout"].splitlines():
            name = line.strip()
            if not name.endswith(".zip"):
                continue
            model_id = valid_remote_zip_model_id(name)
            if model_id is None:
                skipped_files.append(name)
                continue
            files.append(f"{model_id}.zip")
    return {
        "status": "ok" if rclone["returncode"] == 0 else "failed",
        "remote": remote,
        "files": sorted(files),
        "skipped_files": sorted(skipped_files),
        "rclone": rclone,
    }


def download_archives(
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
    remote: str = DEFAULT_REMOTE,
    models: Optional[Sequence[str]] = None,
    overwrite: bool = False,
    rclone_bin: str = "rclone",
) -> Dict[str, Any]:
    remote = require_remote(remote)
    archive_dir = archive_dir or (experiment_dir / "archives")
    archive_dir.mkdir(parents=True, exist_ok=True)

    if models:
        archive_names = [f"{validate_model_id(model)}.zip" for model in models]
        listing: Optional[Dict[str, Any]] = None
    else:
        listing = list_remote_archives(remote=remote, rclone_bin=rclone_bin)
        if listing["status"] != "ok":
            return {
                "status": "failed",
                "remote": remote,
                "listing": listing,
                "downloads": [],
                "extracts": [],
            }
        archive_names = listing["files"]

    downloads: List[Dict[str, Any]] = []
    extracts: List[Dict[str, Any]] = []
    for archive_name in archive_names:
        model_id = validate_model_id(Path(archive_name).stem)
        archive_path = archive_dir / f"{model_id}.zip"
        command = [
            rclone_bin,
            "copyto",
            remote_archive_path(remote, model_id),
            str(archive_path),
        ]
        rclone = run_rclone(command)
        downloads.append({
            "model_id": model_id,
            "archive_path": str(archive_path),
            "rclone": rclone,
            "status": "ok" if rclone["returncode"] == 0 else "failed",
        })
        if rclone["returncode"] == 0:
            extracts.append(extract_model_archive(archive_path, experiment_dir=experiment_dir, overwrite=overwrite))

    failed = [download for download in downloads if download["status"] != "ok"]
    return {
        "status": "failed" if failed else "ok",
        "remote": remote,
        "archive_dir": str(archive_dir),
        "listing": listing,
        "downloads": downloads,
        "extracts": extracts,
    }


def _ensure_local_archive(
    *,
    label: str,
    archive_path: Path,
    drive_file_id: str,
    force_download: bool,
) -> Dict[str, Any]:
    """Reuse a cached zip if it's already a valid archive, otherwise download it."""
    if not force_download and is_valid_zip(archive_path):
        return {
            "label": label,
            "status": "ok",
            "mode": "cached",
            "archive_path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "drive_file_id": drive_file_id,
        }
    record = download_drive_file(drive_file_id, archive_path)
    record.update({"label": label, "status": "ok", "mode": "downloaded", "drive_file_id": drive_file_id})
    return record


def download_public_archives(
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
    manifest_url: str = DEFAULT_PUBLIC_MANIFEST_URL,
    models: Optional[Sequence[str]] = None,
    bundles: Optional[Sequence[str]] = None,
    overwrite: bool = False,
    force_download: bool = False,
) -> Dict[str, Any]:
    archive_dir = archive_dir or (experiment_dir / "archives")
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_record = read_public_manifest(manifest_url, archive_dir=archive_dir)
    model_records = manifest_model_records(manifest_record["manifest"], models=models)
    # If --bundles is not passed, default to grabbing every bundle the manifest advertises.
    requested_bundles: Optional[Sequence[str]] = bundles
    if requested_bundles is None and "bundles" in manifest_record["manifest"]:
        requested_bundles = None  # take all entries from manifest
    bundle_records = manifest_bundle_records(manifest_record["manifest"], bundles=requested_bundles)

    downloads: List[Dict[str, Any]] = []
    extracts: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    def process_record(record: Mapping[str, Any], *, kind: str, identifier: str) -> None:
        archive_path = archive_dir / record["filename"]
        try:
            download = _ensure_local_archive(
                label=f"{kind}:{identifier}",
                archive_path=archive_path,
                drive_file_id=record["drive_file_id"],
                force_download=force_download,
            )
            download["kind"] = kind
            download[f"{kind}_id"] = identifier
            downloads.append(download)
        except RuntimeError as exc:
            failure = {
                "kind": kind,
                f"{kind}_id": identifier,
                "drive_file_id": record["drive_file_id"],
                "archive_path": str(archive_path),
                "status": "failed",
                "error": str(exc),
            }
            failures.append(failure)
            downloads.append(failure)
            return

        try:
            extract = extract_model_archive(archive_path, experiment_dir=experiment_dir, overwrite=overwrite)
            extract["kind"] = kind
            extract[f"{kind}_id"] = identifier
            extracts.append(extract)
        except (ValueError, OSError) as exc:
            failures.append({
                "kind": kind,
                f"{kind}_id": identifier,
                "archive_path": str(archive_path),
                "status": "extract_failed",
                "error": str(exc),
            })

    for record in model_records:
        process_record(record, kind="model", identifier=record["model_id"])
    for record in bundle_records:
        process_record(record, kind="bundle", identifier=record["bundle_id"])

    return {
        "status": "ok" if not failures else "partial",
        "manifest": {
            "manifest_path": manifest_record["manifest_path"],
            "download": manifest_record["download"],
            "model_count": len(manifest_record["manifest"].get("models", [])),
            "bundle_count": len(manifest_record["manifest"].get("bundles", []) or []),
            "schema_version": manifest_record["manifest"].get("schema_version"),
        },
        "selected_models": [record["model_id"] for record in model_records],
        "selected_bundles": [record["bundle_id"] for record in bundle_records],
        "archive_dir": str(archive_dir),
        "downloads": downloads,
        "extracts": extracts,
        "failures": failures,
    }


def list_remote_zip_metadata(*, remote: str = DEFAULT_REMOTE, rclone_bin: str = "rclone") -> Dict[str, Any]:
    remote = require_remote(remote)
    command = [rclone_bin, "lsjson", remote, "--files-only", "--include", "*.zip"]
    rclone = run_rclone(command)
    files: List[Dict[str, Any]] = []
    skipped_files: List[str] = []
    if rclone["returncode"] == 0:
        try:
            payload = json.loads(rclone["stdout"])
        except json.JSONDecodeError as exc:
            return {
                "status": "failed",
                "remote": remote,
                "files": [],
                "skipped_files": [],
                "rclone": rclone,
                "error": f"Invalid rclone lsjson output: {exc}",
            }
        for raw_file in payload:
            if not isinstance(raw_file, dict):
                continue
            name = str(raw_file.get("Name") or raw_file.get("Path") or "")
            if not name.endswith(".zip"):
                continue
            model_id = valid_remote_zip_model_id(name)
            if model_id is None:
                skipped_files.append(name)
                continue
            drive_file_id = str(raw_file.get("ID") or "")
            if not drive_file_id:
                return {
                    "status": "failed",
                    "remote": remote,
                    "files": [],
                    "skipped_files": sorted(skipped_files),
                    "rclone": rclone,
                    "error": f"rclone metadata for {name} did not include an ID.",
                }
            files.append({
                "model_id": model_id,
                "filename": f"{model_id}.zip",
                "drive_file_id": drive_file_id,
                "size_bytes": raw_file.get("Size"),
            })
    return {
        "status": "ok" if rclone["returncode"] == 0 else "failed",
        "remote": remote,
        "files": sorted(files, key=lambda item: item["model_id"]),
        "skipped_files": sorted(skipped_files),
        "rclone": rclone,
    }


def publish_local_bundles(
    *,
    experiment_dir: Path,
    archive_dir: Path,
    remote: str,
    rclone_bin: str,
    bundles: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Zip and upload every bundle whose source paths exist locally."""
    requested = list(bundles) if bundles else list(KNOWN_BUNDLES)
    records: List[Dict[str, Any]] = []
    for bundle_id in requested:
        if bundle_id not in KNOWN_BUNDLES:
            records.append({
                "status": "skipped",
                "bundle_id": bundle_id,
                "reason": "unknown_bundle",
            })
            continue
        if not bundle_has_content(bundle_id, experiment_dir=experiment_dir):
            records.append({
                "status": "skipped",
                "bundle_id": bundle_id,
                "reason": "no_local_content",
            })
            continue
        try:
            record = upload_bundle(
                bundle_id,
                experiment_dir=experiment_dir,
                archive_dir=archive_dir,
                remote=remote,
                rclone_bin=rclone_bin,
            )
        except (FileNotFoundError, ValueError) as exc:
            record = {
                "status": "failed",
                "bundle_id": bundle_id,
                "error": str(exc),
            }
        records.append(record)
    return records


def publish_manifest(
    *,
    experiment_dir: Path = DEFAULT_EXPERIMENT_DIR,
    archive_dir: Optional[Path] = None,
    remote: str = DEFAULT_REMOTE,
    rclone_bin: str = "rclone",
    bundles: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    archive_dir = archive_dir or (experiment_dir / "archives")
    archive_dir.mkdir(parents=True, exist_ok=True)

    bundle_uploads = publish_local_bundles(
        experiment_dir=experiment_dir,
        archive_dir=archive_dir,
        remote=remote,
        rclone_bin=rclone_bin,
        bundles=bundles,
    )

    metadata = list_remote_zip_metadata(remote=remote, rclone_bin=rclone_bin)
    if metadata["status"] != "ok":
        return {
            "status": "failed",
            "remote": remote,
            "metadata": metadata,
            "bundle_uploads": bundle_uploads,
            "manifest": None,
            "upload": None,
        }

    bundle_ids = set(KNOWN_BUNDLES)
    model_entries: List[Dict[str, Any]] = []
    bundle_entries: List[Dict[str, Any]] = []
    for entry in metadata["files"]:
        target = bundle_entries if entry["model_id"] in bundle_ids else model_entries
        target.append({
            "bundle_id" if entry["model_id"] in bundle_ids else "model_id": entry["model_id"],
            "filename": entry["filename"],
            "drive_file_id": entry["drive_file_id"],
            "size_bytes": entry.get("size_bytes"),
        })

    manifest: Dict[str, Any] = {
        "schema_version": 2 if bundle_entries else 1,
        "generated_at": utc_now(),
        "models": model_entries,
    }
    if bundle_entries:
        manifest["bundles"] = bundle_entries
    manifest_path = archive_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    upload_command = [
        rclone_bin,
        "copyto",
        str(manifest_path),
        remote_file_path(remote, MANIFEST_FILENAME),
    ]
    upload = run_rclone(upload_command)
    status = "ok" if upload["returncode"] == 0 else "failed"
    manifest_remote_metadata: Optional[Dict[str, Any]] = None
    if status == "ok":
        remote_manifest = run_rclone([rclone_bin, "lsjson", remote_file_path(remote, MANIFEST_FILENAME)])
        if remote_manifest["returncode"] == 0:
            try:
                manifest_remote_metadata = json.loads(remote_manifest["stdout"])
            except json.JSONDecodeError:
                manifest_remote_metadata = None

    return {
        "status": status,
        "remote": remote,
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "bundle_uploads": bundle_uploads,
        "upload": upload,
        "remote_manifest": manifest_remote_metadata,
    }


def check_write_access(
    *,
    remote: str = DEFAULT_REMOTE,
    rclone_bin: str = "rclone",
) -> Dict[str, Any]:
    remote = require_remote(remote)
    token = f"__mtg_write_check_{int(time.time() * 1000)}.txt"
    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / token
        local_path.write_text("mtg write check\n", encoding="utf-8")
        remote_path = remote_file_path(remote, token)
        upload = run_rclone([rclone_bin, "copyto", str(local_path), remote_path])
        delete = None
        if upload["returncode"] == 0:
            delete = run_rclone([rclone_bin, "deletefile", remote_path])
        status = "ok" if upload["returncode"] == 0 and delete is not None and delete["returncode"] == 0 else "failed"
        return {
            "status": status,
            "remote": remote,
            "remote_path": remote_path,
            "upload": upload,
            "delete": delete,
        }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Phase-E experiment archives through rclone.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    common.add_argument("--archive-dir", type=Path, default=None)
    common.add_argument("--experiments-drive-remote", default=DEFAULT_REMOTE)
    common.add_argument("--experiments-manifest-url", default=DEFAULT_PUBLIC_MANIFEST_URL)
    common.add_argument("--rclone-bin", default="rclone")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload-model", parents=[common], help="Archive and upload one model directory.")
    upload.add_argument("model_id")

    upload_bundle_parser = subparsers.add_parser(
        "upload-bundle",
        parents=[common],
        help=f"Archive and upload a shared bundle: {', '.join(sorted(KNOWN_BUNDLES))}.",
    )
    upload_bundle_parser.add_argument("bundle_id", choices=sorted(KNOWN_BUNDLES))

    download = subparsers.add_parser("download", parents=[common], help="Download and extract model archives.")
    download.add_argument("--models", nargs="+", default=None)
    download.add_argument("--overwrite", action="store_true")

    download_public = subparsers.add_parser(
        "download-public",
        parents=[common],
        help="Download and extract model archives from a public manifest.",
    )
    download_public.add_argument("--models", nargs="+", default=None)
    download_public.add_argument(
        "--bundles",
        nargs="+",
        default=None,
        help=f"Restrict bundles to fetch (omit to take everything in the manifest). Known: {', '.join(sorted(KNOWN_BUNDLES))}.",
    )
    download_public.add_argument("--overwrite", action="store_true")
    download_public.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download archives even when a valid local zip is already present.",
    )

    publish = subparsers.add_parser("publish-manifest", parents=[common], help="Publish a public manifest from remote zips.")
    publish.add_argument(
        "--bundles",
        nargs="+",
        default=None,
        help=f"Restrict which bundles to upload before listing (default: all known). Known: {', '.join(sorted(KNOWN_BUNDLES))}.",
    )

    subparsers.add_parser("check-write", parents=[common], help="Check whether the configured remote is writable.")
    subparsers.add_parser("list", parents=[common], help="List remote model archives.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    if args.command == "upload-model":
        return upload_model(
            args.model_id,
            experiment_dir=args.experiment_dir,
            archive_dir=args.archive_dir,
            remote=args.experiments_drive_remote,
            rclone_bin=args.rclone_bin,
        )
    if args.command == "upload-bundle":
        return upload_bundle(
            args.bundle_id,
            experiment_dir=args.experiment_dir,
            archive_dir=args.archive_dir,
            remote=args.experiments_drive_remote,
            rclone_bin=args.rclone_bin,
        )
    if args.command == "download":
        return download_archives(
            experiment_dir=args.experiment_dir,
            archive_dir=args.archive_dir,
            remote=args.experiments_drive_remote,
            models=args.models,
            overwrite=args.overwrite,
            rclone_bin=args.rclone_bin,
        )
    if args.command == "download-public":
        return download_public_archives(
            experiment_dir=args.experiment_dir,
            archive_dir=args.archive_dir,
            manifest_url=args.experiments_manifest_url,
            models=args.models,
            bundles=args.bundles,
            overwrite=args.overwrite,
            force_download=args.force_download,
        )
    if args.command == "publish-manifest":
        return publish_manifest(
            experiment_dir=args.experiment_dir,
            archive_dir=args.archive_dir,
            remote=args.experiments_drive_remote,
            rclone_bin=args.rclone_bin,
            bundles=args.bundles,
        )
    if args.command == "check-write":
        return check_write_access(remote=args.experiments_drive_remote, rclone_bin=args.rclone_bin)
    if args.command == "list":
        return list_remote_archives(remote=args.experiments_drive_remote, rclone_bin=args.rclone_bin)
    raise ValueError(f"Unknown command: {args.command}")


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    payload = run(args)
    write_json(payload)
    status = payload.get("status")
    if status == "ok":
        return 0
    if status == "partial":
        # download-public with some per-record failures should not abort the whole
        # init pipeline — successes were still extracted. Failures are surfaced
        # in payload["failures"] for visibility.
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
