import importlib.util
import json
import threading
import time
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetcher = load_module("fetch_archidekt_raw", "scripts/fetch_archidekt_raw.py")
processor = load_module("process_archidekt_raw", "scripts/process_archidekt_raw.py")
raw_restore = load_module("download_archidekt_raw", "scripts/download_archidekt_raw.py")
processed_restore = load_module("download_archidekt_processed", "scripts/download_archidekt_processed.py")
label_validator = load_module("validate_edhpowerlevel_labels", "scripts/validate_edhpowerlevel_labels.py")
label_refresher = load_module("refresh_edhpowerlevel_labels", "scripts/refresh_edhpowerlevel_labels.py")


def read_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def oracle(uid, name=None, colors=None, types=None, super_types=None, legality="legal", text=""):
    return {
        "id": abs(hash(uid)) % 1000000,
        "uid": uid,
        "name": name or uid,
        "colorIdentity": colors or [],
        "types": types or ["Artifact"],
        "superTypes": super_types or [],
        "legalities": {"commander": legality},
        "text": text,
    }


def card_row(uid, quantity=1, categories=None, oracle_data=None, companion=False, deleted_at=None):
    oracle_card = oracle_data or oracle(uid)
    return {
        "id": abs(hash((uid, tuple(categories or [])))) % 1000000,
        "quantity": quantity,
        "categories": categories or ["Artifact"],
        "companion": companion,
        "deletedAt": deleted_at,
        "customCmc": None,
        "modifier": "Normal",
        "notes": None,
        "card": {
            "uid": f"print-{uid}",
            "collectorNumber": "1",
            "edition": {"editioncode": "tst"},
            "scryfallImageHash": "image",
            "oracleCard": oracle_card,
        },
    }


def base_categories(extra=None):
    categories = [
        {"name": "Commander", "includedInDeck": True, "isPremier": True},
        {"name": "Artifact", "includedInDeck": True, "isPremier": False},
        {"name": "Creature", "includedInDeck": True, "isPremier": False},
        {"name": "Land", "includedInDeck": True, "isPremier": False},
        {"name": "Tokens", "includedInDeck": True, "isPremier": False},
        {"name": "Maybeboard", "includedInDeck": False, "isPremier": False},
        {"name": "Sideboard", "includedInDeck": True, "isPremier": False},
        {"name": "Tokens & Extras", "includedInDeck": True, "isPremier": False},
    ]
    if extra:
        categories.extend(extra)
    return categories


def deck(deck_id, cards, **overrides):
    payload = {
        "id": deck_id,
        "name": f"Deck {deck_id}",
        "private": False,
        "unlisted": False,
        "deckFormat": 3,
        "edhBracket": 3,
        "viewCount": 5000,
        "updatedAt": "2026-05-05T00:00:00Z",
        "featured": "image-url",
        "customFeatured": "custom-image-url",
        "categories": base_categories(overrides.pop("extra_categories", None)),
        "cards": cards,
    }
    payload.update(overrides)
    return payload


def normal_cards(count=100, commander_colors=None):
    cards = [
        card_row(
            "commander-1",
            categories=["Commander", "Creature"],
            oracle_data=oracle("commander-1", "Commander One", colors=commander_colors or [], types=["Creature"]),
        )
    ]
    for index in range(1, count):
        cards.append(card_row(f"card-{index}", categories=["Artifact"]))
    return cards


def write_raw_details(raw_dir, decks):
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "raw_deck_details.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for index, payload in enumerate(decks, start=1):
            record = {
                "record_type": "archidekt_deck_detail",
                "run_id": "test-run",
                "fetched_at": f"2026-05-05T00:00:{index:02d}+00:00",
                "deck_id": payload["id"],
                "detail_url": f"https://archidekt.com/api/decks/{payload['id']}/",
                "status": 200,
                "response": payload,
            }
            handle.write(json.dumps(record))
            handle.write("\n")


class FetchArchidektRawTests(unittest.TestCase):
    def test_fetcher_saves_search_pages_and_max_decks_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            detail_calls = []

            def fake_fetch_json(url, user_agent=fetcher.DEFAULT_USER_AGENT, timeout=30.0):
                if "/api/decks/v3/" in url:
                    return 200, {
                        "results": [
                            {"id": 101, "viewCount": 5000},
                            {"id": 102, "viewCount": 4000},
                            {"id": 103, "viewCount": 3000},
                        ]
                    }
                detail_calls.append(url)
                deck_id = int(url.rstrip("/").split("/")[-1])
                return 200, deck(deck_id, normal_cards(), edhBracket=2)

            args = fetcher.parse_args(
                ["--out-dir", str(out_dir), "--brackets", "2", "--sleep-sec", "0", "--max-decks", "2"]
            )
            with patch.object(fetcher, "fetch_json", side_effect=fake_fetch_json):
                summary = fetcher.run(args)

            details = read_jsonl(out_dir / "raw_deck_details.jsonl")
            manifests = read_jsonl(out_dir / "fetch_manifest.jsonl")
            search_pages = read_jsonl(out_dir / "raw_deck_search_pages.jsonl")

            self.assertEqual([record["deck_id"] for record in details], [101, 102])
            self.assertEqual(len(detail_calls), 2)
            self.assertEqual(len(search_pages), 1)
            self.assertTrue(summary["max_decks_reached"])
            self.assertEqual(manifests[-1]["stopped_reason"], "max_decks")

    def test_fetcher_resume_skips_existing_deck_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            fetcher.append_jsonl(
                out_dir / "raw_deck_details.jsonl",
                {"record_type": "archidekt_deck_detail", "deck_id": 201, "status": 200, "response": {"id": 201}},
            )
            detail_calls = []

            def fake_fetch_json(url, user_agent=fetcher.DEFAULT_USER_AGENT, timeout=30.0):
                if "/api/decks/v3/" in url:
                    page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
                    if page > 1:
                        return 200, {"results": []}
                    return 200, {"results": [{"id": 201, "viewCount": 5000}, {"id": 202, "viewCount": 4000}]}
                detail_calls.append(url)
                return 200, deck(202, normal_cards(), edhBracket=2)

            args = fetcher.parse_args(["--out-dir", str(out_dir), "--brackets", "2", "--sleep-sec", "0", "--resume"])
            with patch.object(fetcher, "fetch_json", side_effect=fake_fetch_json):
                summary = fetcher.run(args)

            details = read_jsonl(out_dir / "raw_deck_details.jsonl")
            self.assertEqual([record["deck_id"] for record in details], [201, 202])
            self.assertEqual(len(detail_calls), 1)
            self.assertEqual(summary["skipped_existing"], 1)

    def test_fetcher_does_not_save_invalid_deck_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            def fake_fetch_json(url, user_agent=fetcher.DEFAULT_USER_AGENT, timeout=30.0):
                if "/api/decks/v3/" in url:
                    page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
                    if page > 1:
                        return 200, {"results": []}
                    return 200, {"results": [{"id": 301, "viewCount": 5000}, {"id": 302, "viewCount": 4000}]}
                deck_id = int(url.rstrip("/").split("/")[-1])
                if deck_id == 301:
                    return 200, deck(301, normal_cards(99), edhBracket=2)
                return 200, deck(302, normal_cards(), edhBracket=2)

            args = fetcher.parse_args(["--out-dir", str(out_dir), "--brackets", "2", "--sleep-sec", "0"])
            with patch.object(fetcher, "fetch_json", side_effect=fake_fetch_json):
                summary = fetcher.run(args)

            details = read_jsonl(out_dir / "raw_deck_details.jsonl")
            self.assertEqual([record["deck_id"] for record in details], [302])
            self.assertEqual(summary["detail_payloads_saved"], 1)
            self.assertEqual(summary["detail_payloads_rejected"], 1)
            self.assertEqual(summary["rejection_reasons"]["mainboard_count_not_100"], 1)

    def test_fetcher_fetches_details_with_parallel_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            lock = threading.Lock()
            stats = {"active": 0, "max_active": 0}

            def fake_fetch_json(url, user_agent=fetcher.DEFAULT_USER_AGENT, timeout=30.0):
                if "/api/decks/v3/" in url:
                    page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
                    if page > 1:
                        return 200, {"results": []}
                    return 200, {"results": [{"id": deck_id, "viewCount": 5000} for deck_id in range(401, 407)]}

                with lock:
                    stats["active"] += 1
                    stats["max_active"] = max(stats["max_active"], stats["active"])
                time.sleep(0.02)
                with lock:
                    stats["active"] -= 1

                deck_id = int(url.rstrip("/").split("/")[-1])
                return 200, deck(deck_id, normal_cards(), edhBracket=2)

            args = fetcher.parse_args(
                ["--out-dir", str(out_dir), "--brackets", "2", "--sleep-sec", "0", "--workers", "3"]
            )
            with patch.object(fetcher, "fetch_json", side_effect=fake_fetch_json):
                summary = fetcher.run(args)

            details = read_jsonl(out_dir / "raw_deck_details.jsonl")
            self.assertEqual({record["deck_id"] for record in details}, set(range(401, 407)))
            self.assertGreaterEqual(stats["max_active"], 2)
            self.assertEqual(summary["parameters"]["workers"], 3)
            self.assertEqual(summary["detail_payloads_attempted"], 6)
            self.assertEqual(summary["detail_payloads_saved"], 6)


class RestoreArchidektRawTests(unittest.TestCase):
    def test_extracts_google_drive_file_id(self):
        url = "https://drive.google.com/file/d/11Ahbt7xHAaQqvEwVdJE2zXzXYNna0IeG/view?usp=drive_link"
        self.assertEqual(raw_restore.extract_drive_file_id(url), "11Ahbt7xHAaQqvEwVdJE2zXzXYNna0IeG")
        self.assertEqual(raw_restore.extract_drive_file_id("11Ahbt7xHAaQqvEwVdJE2zXzXYNna0IeG"), "11Ahbt7xHAaQqvEwVdJE2zXzXYNna0IeG")

    def test_parses_drive_virus_warning_download_form(self):
        body = b'''<!DOCTYPE html><html><body>
        <form id="download-form" action="https://drive.usercontent.google.com/download" method="get">
        <input type="hidden" name="id" value="file-123">
        <input type="hidden" name="export" value="download">
        <input type="hidden" name="confirm" value="t">
        <input type="hidden" name="uuid" value="abc-123">
        </form></body></html>'''
        url = raw_restore._drive_warning_download_url(body, "file-123")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "drive.usercontent.google.com")
        self.assertEqual(query["id"], ["file-123"])
        self.assertEqual(query["confirm"], ["t"])
        self.assertEqual(query["uuid"], ["abc-123"])

    def test_extracts_expected_files_from_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "Archive.zip"
            out_dir = root / "raw"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("fetch_manifest.jsonl", '{"ok": true}\n')
                archive.writestr("raw_deck_details.jsonl", '{"deck_id": 1}\n')
                archive.writestr("raw_deck_search_pages.jsonl", '{"page": 1}\n')
                archive.writestr("notes.txt", "ignored\n")

            summary = raw_restore.extract_raw_archive(archive_path, out_dir)

            self.assertEqual(
                {Path(path).name for path in summary["extracted"]},
                raw_restore.EXPECTED_RAW_FILES,
            )
            self.assertFalse((out_dir / "notes.txt").exists())
            second = raw_restore.extract_raw_archive(archive_path, out_dir)
            self.assertEqual(len(second["extracted"]), 0)
            self.assertEqual({Path(path).name for path in second["skipped_existing"]}, raw_restore.EXPECTED_RAW_FILES)

    def test_restore_runs_processing_by_default_without_y2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "Archive.zip"
            raw_dir = root / "raw"
            processed_dir = root / "processed"
            payload = deck(601, normal_cards(), edhBracket=3)
            raw_record = {
                "record_type": "archidekt_deck_detail",
                "run_id": "restore-test",
                "fetched_at": "2026-05-13T00:00:00+00:00",
                "deck_id": 601,
                "detail_url": "https://archidekt.com/api/decks/601/",
                "status": 200,
                "response": payload,
            }
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("fetch_manifest.jsonl", '{"record_type": "manifest"}\n')
                archive.writestr("raw_deck_details.jsonl", json.dumps(raw_record) + "\n")
                archive.writestr("raw_deck_search_pages.jsonl", '{"record_type": "search"}\n')

            args = raw_restore.parse_args([
                "--archive",
                str(archive_path),
                "--out-dir",
                str(raw_dir),
                "--processed-dir",
                str(processed_dir),
                "--process-overwrite",
            ])
            summary = raw_restore.run(args)

            decks = read_jsonl(processed_dir / "decks.jsonl")
            self.assertEqual(summary["process"]["accepted_decks"], 1)
            self.assertEqual(decks[0]["deck_id"], 601)
            self.assertIsNone(decks[0]["edhpowerlevel"])


class RestoreArchidektProcessedTests(unittest.TestCase):
    def test_extracts_expected_processed_files_from_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "processed.zip"
            out_dir = root / "processed"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for filename in processed_restore.REQUIRED_PROCESSED_FILES:
                    archive.writestr(f"archidekt/{filename}", '{"ok": true}\n')
                archive.writestr("archidekt/bag_of_cards.jsonl", '{"feature": true}\n')
                archive.writestr("archidekt/ignored.txt", "ignored\n")

            summary = processed_restore.extract_processed_archive(archive_path, out_dir)

            self.assertEqual(
                {Path(path).name for path in summary["extracted"]},
                processed_restore.REQUIRED_PROCESSED_FILES | {"bag_of_cards.jsonl"},
            )
            self.assertFalse((out_dir / "ignored.txt").exists())

    def test_processed_report_summarizes_decks_and_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            deck_one_mainboard = [
                {
                    "oracle_uid": "commander-a",
                    "oracle_name": "Commander A",
                    "quantity": 1,
                    "is_commander": True,
                },
                {"oracle_uid": "card-a", "oracle_name": "Card A", "quantity": 99, "is_commander": False},
            ]
            deck_two_mainboard = [
                {
                    "oracle_uid": "commander-b",
                    "oracle_name": "Commander B",
                    "quantity": 1,
                    "is_commander": True,
                },
                {"oracle_uid": "card-b", "oracle_name": "Card B", "quantity": 99, "is_commander": False},
            ]
            decks = [
                {
                    "snapshot_id": "snap-1",
                    "deck_id": 1,
                    "mainboard": deck_one_mainboard,
                    "mainboard_count": 100,
                    "archidekt_edh_bracket": 2,
                    "edhpowerlevel": {"commander_bracket": 3, "power_level": "7.5"},
                    "validation_trace": {"commander_color_identity": ["White", "Blue"]},
                    "view_count": 1200,
                    "archidekt_updated_at": "2026-05-01T00:00:00Z",
                },
                {
                    "snapshot_id": "snap-2",
                    "deck_id": 2,
                    "mainboard": deck_two_mainboard,
                    "mainboard_count": 100,
                    "archidekt_edh_bracket": 4,
                    "edhpowerlevel": None,
                    "validation_trace": {"commander_color_identity": ["Black"]},
                    "view_count": 1800,
                    "archidekt_updated_at": "2026-05-02T00:00:00Z",
                },
            ]
            for filename in processed_restore.REQUIRED_PROCESSED_FILES:
                (out_dir / filename).write_text("", encoding="utf-8")
            with (out_dir / "decks.jsonl").open("w", encoding="utf-8") as handle:
                for deck_payload in decks:
                    handle.write(json.dumps(deck_payload) + "\n")
            with (out_dir / "cards.jsonl").open("w", encoding="utf-8") as handle:
                for oracle_uid in ["commander-a", "card-a", "commander-b", "card-b"]:
                    handle.write(json.dumps({"oracle_uid": oracle_uid}) + "\n")
            for filename in ("deck_features.jsonl", "bag_of_cards.jsonl"):
                with (out_dir / filename).open("w", encoding="utf-8") as handle:
                    for deck_payload in decks:
                        handle.write(json.dumps({"snapshot_id": deck_payload["snapshot_id"]}) + "\n")

            report = processed_restore.build_processed_report(out_dir)

            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["decks"]["total_snapshots"], 2)
            self.assertEqual(report["decks"]["archidekt_edh_brackets"], {"2": 1, "4": 1})
            self.assertEqual(report["decks"]["edhpowerlevel"]["labeled"], 1)
            self.assertEqual(report["decks"]["edhpowerlevel"]["missing"], 1)
            self.assertEqual(report["decks"]["color_identities"], {"B": 1, "WU": 1})
            self.assertTrue(report["checks"]["card_reference_coverage"]["covers_all_references"])


class EDHPowerLevelLabelValidationTests(unittest.TestCase):
    def test_selects_stratified_sample_and_compares_payloads(self):
        decks = [
            {"snapshot_id": f"snap-{i}", "edhpowerlevel": {"commander_bracket": (i % 5) + 1}}
            for i in range(20)
        ]
        sample = label_validator.select_stratified_sample(decks, 10)
        brackets = {deck["edhpowerlevel"]["commander_bracket"] for deck in sample}
        self.assertEqual(brackets, {1, 2, 3, 4, 5})

        sample_without_first = label_validator.select_stratified_sample(decks, 10, {"snap-0"})
        self.assertNotIn("snap-0", {deck["snapshot_id"] for deck in sample_without_first})

        payload = {
            "commander_bracket": 3,
            "power_level": "7.0",
            "started_at": "ignore",
            "snapshot_id": "ignore",
        }
        self.assertEqual(
            label_validator.comparable_payload(payload),
            {"commander_bracket": 3, "power_level": "7.0"},
        )


class EDHPowerLevelLabelRefreshTests(unittest.TestCase):
    def test_refresh_target_selection_respects_existing_labels_and_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            decks_path = Path(tmp) / "decks.jsonl"
            args = label_refresher.parse_args(["--decks-path", str(decks_path), "--refresh-existing"])

            label_refresher.append_jsonl(
                decks_path,
                {
                    "snapshot_id": "snap-labeled",
                    "deck_id": 1,
                    "edhpowerlevel": {"commander_bracket": 2},
                    "mainboard": [],
                },
            )
            label_refresher.append_jsonl(
                decks_path,
                {
                    "snapshot_id": "snap-missing",
                    "deck_id": 2,
                    "edhpowerlevel": None,
                    "mainboard": [],
                },
            )
            progress = {"snap-labeled": {"snapshot_id": "snap-labeled", "commander_bracket": 3}}

            targets, already_done = label_refresher.load_targets(decks_path, args, progress)

            self.assertEqual(already_done, 1)
            self.assertEqual([target["snapshot_id"] for target in targets], ["snap-missing"])


class ProcessArchidektRawTests(unittest.TestCase):
    def run_processor(self, raw_decks, overwrite=True):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        raw_dir = root / "raw"
        out_dir = root / "processed"
        write_raw_details(raw_dir, raw_decks)
        # --skip-y2 keeps the unit tests offline; Phase B is exercised
        # separately via a smoke test against the real EDHPowerLevel page.
        args = ["--raw-dir", str(raw_dir), "--out-dir", str(out_dir), "--skip-y2"]
        if overwrite:
            args.append("--overwrite")
        summary = processor.run(processor.parse_args(args))
        return tmp, out_dir, summary

    def test_processor_accepts_multiple_commanders(self):
        cards = [
            card_row(
                "commander-w",
                categories=["Commander", "Creature"],
                oracle_data=oracle("commander-w", "White Commander", colors=["White"], types=["Creature"]),
            ),
            card_row(
                "commander-u",
                categories=["Commander", "Creature"],
                oracle_data=oracle("commander-u", "Blue Commander", colors=["Blue"], types=["Creature"]),
            ),
        ]
        cards.extend(card_row(f"card-{index}", categories=["Artifact"]) for index in range(98))
        tmp, out_dir, summary = self.run_processor([deck(1, cards)])
        self.addCleanup(tmp.cleanup)

        decks = read_jsonl(out_dir / "decks.jsonl")

        self.assertEqual(summary["accepted_decks"], 1)
        self.assertEqual(decks[0]["mainboard_count"], 100)
        self.assertEqual(set(decks[0]["commander_oracle_uids"]), {"commander-w", "commander-u"})
        # mainboard now lives inline on decks.jsonl (no deck_cards.jsonl)
        self.assertEqual(len(decks[0]["mainboard"]), 100)
        self.assertIsNone(decks[0]["edhpowerlevel"])
        self.assertFalse((out_dir / "deck_cards.jsonl").exists())

    def test_y2_refresh_existing_targets_already_labeled_decks(self):
        with tempfile.TemporaryDirectory() as tmp:
            decks_path = Path(tmp) / "decks.jsonl"
            processor.append_jsonl(
                decks_path,
                {
                    "snapshot_id": "snap-labeled",
                    "edhpowerlevel": {"commander_bracket": 2},
                },
            )
            processor.append_jsonl(decks_path, {"snapshot_id": "snap-missing", "edhpowerlevel": None})

            self.assertEqual(
                processor._decks_to_query_y2(decks_path, retry_failed=False, refresh_existing=False),
                ["snap-missing"],
            )
            self.assertEqual(
                processor._decks_to_query_y2(decks_path, retry_failed=False, refresh_existing=True),
                ["snap-labeled", "snap-missing"],
            )

    def test_processor_accepts_renamed_premier_commander_category(self):
        cards = [
            card_row(
                "baba",
                categories=["My Baeba"],
                oracle_data=oracle("baba", "Baba Lysaga, Night Witch", colors=["Black", "Green"], types=["Creature"]),
            )
        ]
        cards.extend(card_row(f"card-{index}", categories=["Artifact"]) for index in range(99))
        raw_deck = deck(
            17,
            cards,
            categories=base_categories(extra=[{"name": "My Baeba", "includedInDeck": True, "isPremier": True}]),
        )

        tmp, out_dir, summary = self.run_processor([raw_deck])
        self.addCleanup(tmp.cleanup)

        decks = read_jsonl(out_dir / "decks.jsonl")
        self.assertEqual(summary["accepted_decks"], 1)
        self.assertEqual(decks[0]["commander_oracle_uids"], ["baba"])
        self.assertIn("mybaeba", decks[0]["validation_trace"]["commander_categories"])

    def test_processor_excludes_non_mainboard_and_keeps_tokens_strategy(self):
        cards = normal_cards(99)
        cards.append(card_row("token-strategy", categories=["Tokens"], oracle_data=oracle("token-strategy", "Token Strategy")))
        cards.extend(
            [
                card_row("maybe", categories=["Maybeboard"], oracle_data=oracle("maybe", legality="banned")),
                card_row("side", categories=["Sideboard"]),
                card_row("extra", categories=["Tokens & Extras"]),
                card_row("companion", categories=["Creature"], companion=True),
                card_row("deleted", categories=["Artifact"], deleted_at="2026-05-05T00:00:00Z"),
                card_row("package", categories=["Package"]),
            ]
        )
        raw_deck = deck(
            2,
            cards,
            extra_categories=[{"name": "Package", "includedInDeck": False, "isPremier": False}],
        )

        tmp, out_dir, summary = self.run_processor([raw_deck])
        self.addCleanup(tmp.cleanup)

        self.assertEqual(summary["accepted_decks"], 1)
        deck_record = read_jsonl(out_dir / "decks.jsonl")[0]
        names = {row["oracle_name"] for row in deck_record["mainboard"]}

        self.assertEqual(deck_record["mainboard_count"], 100)
        self.assertIn("Token Strategy", names)
        self.assertNotIn("maybe", names)
        trace = deck_record["validation_trace"]
        self.assertEqual(trace["excluded_rows"]["excluded_category"], 4)
        self.assertEqual(trace["excluded_rows"]["companion"], 1)
        self.assertEqual(trace["excluded_rows"]["deleted"], 1)

    def test_processor_rejects_invalid_decks_with_trace(self):
        invalid_decks = [
            deck(10, normal_cards(), private=True),
            deck(11, normal_cards(), viewCount=999),
            deck(12, normal_cards(), edhBracket=5),
            deck(
                13,
                normal_cards(99)
                + [card_row("banned", oracle_data=oracle("banned", "Banned Card", legality="banned"))],
            ),
            deck(
                14,
                [normal_cards()[0]]
                + [card_row("duplicate", quantity=2, oracle_data=oracle("duplicate", "Duplicate Spell"))]
                + [card_row(f"filler-{index}") for index in range(97)],
            ),
            deck(
                15,
                [
                    card_row(
                        "white-commander",
                        categories=["Commander", "Creature"],
                        oracle_data=oracle("white-commander", colors=["White"], types=["Creature"]),
                    ),
                    card_row("blue-card", oracle_data=oracle("blue-card", "Blue Card", colors=["Blue"])),
                ]
                + [card_row(f"colorless-{index}") for index in range(98)],
            ),
            deck(16, normal_cards(99)),
        ]

        tmp, out_dir, summary = self.run_processor(invalid_decks)
        self.addCleanup(tmp.cleanup)

        rejected = read_jsonl(out_dir / "rejected_decks.jsonl")
        reasons_by_deck = {record["deck_id"]: set(record["rejection_reasons"]) for record in rejected}

        self.assertEqual(summary["accepted_decks"], 0)
        self.assertEqual(summary["rejected_decks"], len(invalid_decks))
        self.assertIn("private", reasons_by_deck[10])
        self.assertIn("low_view_count", reasons_by_deck[11])
        self.assertIn("missing_or_invalid_bracket", reasons_by_deck[12])
        self.assertIn("illegal_commander_card", reasons_by_deck[13])
        self.assertIn("duplicate_nonbasic", reasons_by_deck[14])
        self.assertIn("color_identity_violation", reasons_by_deck[15])
        self.assertIn("mainboard_count_not_100", reasons_by_deck[16])
        self.assertIn("included_quantity", rejected[-1]["trace"])

    def test_repeated_processing_deduplicates_cards_and_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            out_dir = root / "processed"
            raw_deck = deck(
                20,
                [
                    card_row(
                        "white-commander",
                        categories=["Commander", "Creature"],
                        oracle_data=oracle("white-commander", colors=["White"], types=["Creature"]),
                    ),
                    card_row(
                        "plains",
                        quantity=99,
                        categories=["Land"],
                        oracle_data=oracle(
                            "plains",
                            "Plains",
                            colors=["White"],
                            types=["Land"],
                            super_types=["Basic"],
                        ),
                    ),
                ],
            )
            write_raw_details(raw_dir, [raw_deck])

            args = processor.parse_args(
                ["--raw-dir", str(raw_dir), "--out-dir", str(out_dir), "--skip-y2"]
            )
            first_summary = processor.run(args)
            second_summary = processor.run(args)

            self.assertEqual(first_summary["accepted_decks"], 1)
            self.assertEqual(second_summary["skipped_existing_snapshots"], 1)
            self.assertEqual(len(read_jsonl(out_dir / "decks.jsonl")), 1)
            self.assertEqual(len(read_jsonl(out_dir / "cards.jsonl")), 2)


edhpl_client = load_module("edhpowerlevel_client", "scripts/edhpowerlevel_client.py")


class EDHPowerLevelParserTests(unittest.TestCase):
    SAMPLE_BODY = """⚡
Power Level
8.40 / 10
⚖️
Tipping Point
4
⏱️
Efficiency
6.20 / 10
💥
Impact
512.34
🎯
Score
650 / 1000
🕹️
Average Playability
85.5%
beta Commander Bracket: 4
"""

    def test_parses_all_visible_fields(self):
        parsed = edhpl_client._parse_result(self.SAMPLE_BODY)
        self.assertEqual(parsed["commander_bracket"], 4)
        self.assertEqual(parsed["power_level"], "8.40")
        self.assertEqual(parsed["tipping_point"], "4")
        self.assertEqual(parsed["efficiency"], "6.20")
        self.assertEqual(parsed["impact"], "512.34")
        self.assertEqual(parsed["score"], "650")
        self.assertEqual(parsed["average_playability"], "85.5")

    def test_decklist_text_builds_mtgo_format(self):
        mainboard = [
            {"oracle_name": "Sol Ring", "quantity": 1},
            {"oracle_name": "Forest", "quantity": 8},
            {"oracle_name": "Skip", "quantity": 0},  # filtered out
        ]
        text = edhpl_client.decklist_text(mainboard)
        self.assertEqual(text, "1 Sol Ring\n8 Forest")


class ProcessY2EnrichmentTests(unittest.TestCase):
    """Phase B with the Playwright client patched out."""

    def _seed_decks(self, out_dir, n=3):
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "decks.jsonl").open("w", encoding="utf-8") as handle:
            for i in range(n):
                handle.write(json.dumps({
                    "snapshot_id": f"snap-{i}",
                    "deck_id": 1000 + i,
                    "mainboard": [{"oracle_name": "Sol Ring", "quantity": 1}],
                    "edhpowerlevel": None,
                }))
                handle.write("\n")

    def test_phase_b_enriches_decks_and_skips_already_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self._seed_decks(out_dir, n=3)

            class FakeClient:
                def __init__(self, *a, **kw):
                    self.calls = []

                def __enter__(self): return self
                def __exit__(self, *a): pass

                def analyze(self, decklist):
                    self.calls.append(decklist)
                    return {"commander_bracket": 3, "power_level": "5.0"}

            fake_module = type("M", (), {
                "EDHPowerLevelClient": FakeClient,
                "decklist_text": lambda mb: "1 Sol Ring",
            })
            import sys as _sys
            _sys.modules["edhpowerlevel_client"] = fake_module

            args = processor.parse_args([
                "--raw-dir", str(out_dir / "raw"),
                "--out-dir", str(out_dir),
                "--y2-only",
                "--y2-sleep", "0",
                "--y2-flush-every", "1",
            ])
            first = processor.run(args)
            self.assertEqual(first["y2_succeeded"], 3)
            self.assertEqual(first["y2_failed"], 0)
            self.assertEqual(first["y2_phase"]["bracket_distribution"], {3: 3})

            decks = read_jsonl(out_dir / "decks.jsonl")
            for d in decks:
                self.assertEqual(d["edhpowerlevel"]["commander_bracket"], 3)

            # Second run: nothing missing, no new attempts.
            second = processor.run(args)
            self.assertEqual(second.get("y2_attempted", 0), 0)
            self.assertEqual(second["y2_phase"]["status"], "complete")

            _sys.modules.pop("edhpowerlevel_client", None)

    def test_phase_b_uses_parallel_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self._seed_decks(out_dir, n=6)
            lock = threading.Lock()
            stats = {"active": 0, "max_active": 0}

            class FakeClient:
                def __init__(self, *a, **kw):
                    pass

                def __enter__(self): return self
                def __exit__(self, *a): pass

                def analyze(self, decklist):
                    with lock:
                        stats["active"] += 1
                        stats["max_active"] = max(stats["max_active"], stats["active"])
                    time.sleep(0.02)
                    with lock:
                        stats["active"] -= 1
                    return {"commander_bracket": 4, "power_level": "7.0"}

            fake_module = type("M", (), {
                "EDHPowerLevelClient": FakeClient,
                "decklist_text": lambda mb: "1 Sol Ring",
            })
            import sys as _sys
            _sys.modules["edhpowerlevel_client"] = fake_module

            try:
                args = processor.parse_args([
                    "--raw-dir", str(out_dir / "raw"),
                    "--out-dir", str(out_dir),
                    "--y2-only",
                    "--y2-sleep", "0",
                    "--workers", "3",
                    "--y2-flush-every", "10",
                ])
                summary = processor.run(args)
            finally:
                _sys.modules.pop("edhpowerlevel_client", None)

            self.assertEqual(summary["y2_succeeded"], 6)
            self.assertEqual(summary["y2_phase"]["workers"], 3)
            self.assertGreaterEqual(stats["max_active"], 2)

    def test_phase_b_preflights_real_playwright_before_spawning_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self._seed_decks(out_dir, n=2)

            original = processor._ensure_playwright_chromium_ready
            processor._ensure_playwright_chromium_ready = lambda: (_ for _ in ()).throw(RuntimeError("install chromium"))
            try:
                args = processor.parse_args([
                    "--raw-dir", str(out_dir / "raw"),
                    "--out-dir", str(out_dir),
                    "--y2-only",
                    "--workers", "2",
                ])
                summary = processor.run(args)
            finally:
                processor._ensure_playwright_chromium_ready = original

            self.assertEqual(summary["y2_phase"]["status"], "error")
            self.assertEqual(summary["y2_phase"]["workers"], 2)
            self.assertEqual(summary.get("y2_attempted", 0), 0)
            self.assertIn("install chromium", summary["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
