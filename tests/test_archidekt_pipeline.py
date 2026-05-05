import importlib.util
import json
import tempfile
import unittest
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


class ProcessArchidektRawTests(unittest.TestCase):
    def run_processor(self, raw_decks, overwrite=True):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        raw_dir = root / "raw"
        out_dir = root / "processed"
        write_raw_details(raw_dir, raw_decks)
        args = ["--raw-dir", str(raw_dir), "--out-dir", str(out_dir)]
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
        deck_cards = read_jsonl(out_dir / "deck_cards.jsonl")

        self.assertEqual(summary["accepted_decks"], 1)
        self.assertEqual(decks[0]["mainboard_count"], 100)
        self.assertEqual(set(decks[0]["commander_oracle_uids"]), {"commander-w", "commander-u"})
        self.assertEqual(len(deck_cards), 100)

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
        deck_cards = read_jsonl(out_dir / "deck_cards.jsonl")
        names = {row["oracle_name"] for row in deck_cards}

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

            args = processor.parse_args(["--raw-dir", str(raw_dir), "--out-dir", str(out_dir)])
            first_summary = processor.run(args)
            second_summary = processor.run(args)

            self.assertEqual(first_summary["accepted_decks"], 1)
            self.assertEqual(second_summary["skipped_existing_snapshots"], 1)
            self.assertEqual(len(read_jsonl(out_dir / "decks.jsonl")), 1)
            self.assertEqual(len(read_jsonl(out_dir / "cards.jsonl")), 2)


if __name__ == "__main__":
    unittest.main()
