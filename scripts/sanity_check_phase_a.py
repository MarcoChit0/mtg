#!/usr/bin/env python3
"""Sanity check for Phase A of the action plan (A.1 scrapper + A.3 features).

Samples 30 decks stratified by y1 from ``decks.jsonl``, re-fetches each from
the Archidekt API, filters out decks whose page was updated AFTER our scrap,
and then verifies:

  A.1  saved bracket / mainboard size / commander uids / color identity match
       the current live state.
  A.3  re-running ``build_deck_features`` on the saved record reproduces every
       feature in ``deck_features.jsonl``.

A.2 lives in ``validate_edhpowerlevel_labels.py`` and is run separately.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from build_features import (  # type: ignore
        build_deck_features,
        load_card_index,
        load_printing_lookup,
    )
    from process_archidekt_raw import (  # type: ignore
        commander_category_names,
        excluded_category_names,
        is_commander_category,
        normalize_category,
        row_exclusion_reasons,
    )
except ImportError:
    from scripts.build_features import (  # type: ignore
        build_deck_features,
        load_card_index,
        load_printing_lookup,
    )
    from scripts.process_archidekt_raw import (  # type: ignore
        commander_category_names,
        excluded_category_names,
        is_commander_category,
        normalize_category,
        row_exclusion_reasons,
    )


DECK_API = "https://archidekt.com/api/decks/{deck_id}/"
USER_AGENT = "Mozilla/5.0 (mtg-sanity-check)"


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def fetch_deck_live(deck_id: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        DECK_API.format(deck_id=deck_id),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stratified_sample(
    decks: List[Dict[str, Any]],
    per_bracket: int,
    seed: int,
) -> List[Dict[str, Any]]:
    by_bracket: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for deck in decks:
        by_bracket[deck.get("archidekt_edh_bracket")].append(deck)
    rng = random.Random(seed)
    sample: List[Dict[str, Any]] = []
    for bracket in sorted(by_bracket):
        bucket = list(by_bracket[bracket])
        rng.shuffle(bucket)
        sample.extend(bucket[:per_bracket])
    return sample


def live_commander_names(live: Dict[str, Any]) -> List[str]:
    commander_cats = commander_category_names(live)
    excluded_cats = excluded_category_names(live)
    names: List[str] = []
    for card in live.get("cards") or []:
        if row_exclusion_reasons(card, excluded_cats):
            continue
        if is_commander_category(card.get("categories") or [], commander_cats):
            oracle = (card.get("card") or {}).get("oracleCard") or {}
            name = oracle.get("name")
            if name:
                names.append(name)
    return sorted(set(names))


def saved_commander_names(deck: Dict[str, Any], card_index: Dict[str, Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for row in deck.get("mainboard") or []:
        if row.get("is_commander"):
            oracle = card_index.get(row.get("oracle_uid") or "") or {}
            name = oracle.get("name") or row.get("oracle_name")
            if name:
                names.append(name)
    return sorted(set(names))


def live_color_identity(live: Dict[str, Any]) -> List[str]:
    commander_cats = commander_category_names(live)
    excluded_cats = excluded_category_names(live)
    colors: set = set()
    for card in live.get("cards") or []:
        if row_exclusion_reasons(card, excluded_cats):
            continue
        if is_commander_category(card.get("categories") or [], commander_cats):
            oracle = (card.get("card") or {}).get("oracleCard") or {}
            for color in oracle.get("colorIdentity") or []:
                colors.add(color)
    return sorted(colors)


def saved_color_identity(deck: Dict[str, Any], card_index: Dict[str, Dict[str, Any]]) -> List[str]:
    colors: set = set()
    for row in deck.get("mainboard") or []:
        if row.get("is_commander"):
            oracle = card_index.get(row.get("oracle_uid") or "") or {}
            for color in oracle.get("colorIdentity") or []:
                colors.add(color)
    return sorted(colors)


def feature_diff(expected: Dict[str, Any], actual: Dict[str, Any]) -> List[Tuple[str, Any, Any]]:
    diffs: List[Tuple[str, Any, Any]] = []
    keys = set(expected) | set(actual)
    for key in sorted(keys):
        e = expected.get(key)
        a = actual.get(key)
        if isinstance(e, float) or isinstance(a, float):
            if e is None and a is None:
                continue
            if e is None or a is None:
                diffs.append((key, e, a))
                continue
            if abs(float(e) - float(a)) > 1e-6:
                diffs.append((key, e, a))
        else:
            if e != a:
                diffs.append((key, e, a))
    return diffs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decks-path", type=Path, default=Path("data/processed/archidekt/decks.jsonl"))
    parser.add_argument("--cards-path", type=Path, default=Path("data/processed/archidekt/cards.jsonl"))
    parser.add_argument("--features-path", type=Path, default=Path("data/processed/archidekt/deck_features.jsonl"))
    parser.add_argument("--raw-path", type=Path, default=Path("data/raw/archidekt/raw_deck_details.jsonl"))
    parser.add_argument("--per-bracket", type=int, default=10, help="Decks per y1 bracket (3 brackets x 10 = 30).")
    parser.add_argument("--seed", type=int, default=20260514)
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--report", type=Path, default=Path("documents/sample_reports/sanity_check_phase_a.md"))
    parser.add_argument("--json-report", type=Path, default=Path("data/processed/archidekt/sanity_check_phase_a.json"))
    args = parser.parse_args(argv)

    print(f"Loading decks from {args.decks_path}...", file=sys.stderr)
    decks = list(iter_jsonl(args.decks_path))
    print(f"  {len(decks)} decks loaded.", file=sys.stderr)

    print(f"Loading card index from {args.cards_path}...", file=sys.stderr)
    card_index = load_card_index(args.cards_path)
    print(f"  {len(card_index)} cards loaded.", file=sys.stderr)

    print(f"Loading printing lookup from {args.raw_path}...", file=sys.stderr)
    printing_lookup = load_printing_lookup(args.raw_path)
    print(f"  {len(printing_lookup)} printings loaded.", file=sys.stderr)

    print("Loading saved features...", file=sys.stderr)
    features_by_snapshot: Dict[str, Dict[str, Any]] = {}
    for row in iter_jsonl(args.features_path):
        features_by_snapshot[row.get("snapshot_id")] = row
    print(f"  {len(features_by_snapshot)} feature rows loaded.", file=sys.stderr)

    sample = stratified_sample(decks, args.per_bracket, args.seed)
    print(f"\nSampled {len(sample)} decks (stratified by y1, {args.per_bracket}/bracket).", file=sys.stderr)

    results: List[Dict[str, Any]] = []
    for index, deck in enumerate(sample, 1):
        deck_id = deck.get("deck_id")
        snapshot_id = deck.get("snapshot_id")
        fetched_at = parse_iso(deck.get("fetched_at"))
        saved_updated_at = parse_iso(deck.get("archidekt_updated_at"))

        entry: Dict[str, Any] = {
            "index": index,
            "deck_id": deck_id,
            "snapshot_id": snapshot_id,
            "y1": deck.get("archidekt_edh_bracket"),
            "fetched_at": deck.get("fetched_at"),
            "saved_updated_at": deck.get("archidekt_updated_at"),
        }

        try:
            print(f"  [{index}/{len(sample)}] fetching deck {deck_id}...", file=sys.stderr)
            live = fetch_deck_live(deck_id)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            entry["status"] = "fetch_failed"
            entry["error"] = str(exc)
            results.append(entry)
            time.sleep(args.sleep)
            continue

        live_updated_at = parse_iso(live.get("updatedAt"))
        entry["live_updated_at"] = live.get("updatedAt")

        # A.1: filter — only compare if deck unchanged since scrap.
        if fetched_at and live_updated_at and live_updated_at > fetched_at:
            entry["status"] = "skipped_changed_since_scrap"
            entry["a1"] = {"skipped": True}
        else:
            saved_size = sum(int(r.get("quantity") or 0) for r in deck.get("mainboard") or [])
            live_size = sum(
                int(c.get("quantity") or 0)
                for c in live.get("cards") or []
                if not c.get("deletedAt") and not c.get("companion")
            )
            saved_cmdrs = saved_commander_names(deck, card_index)
            live_cmdrs = live_commander_names(live)
            saved_colors = saved_color_identity(deck, card_index)
            live_colors = live_color_identity(live)
            live_bracket = live.get("edhBracket")

            a1: Dict[str, Any] = {"skipped": False}
            a1["size_match"] = saved_size == 100
            a1["live_size_includes_zones"] = live_size  # informational
            a1["bracket_match"] = live_bracket == deck.get("archidekt_edh_bracket")
            a1["bracket_saved"] = deck.get("archidekt_edh_bracket")
            a1["bracket_live"] = live_bracket
            a1["commander_match"] = saved_cmdrs == live_cmdrs
            a1["commanders_saved"] = saved_cmdrs
            a1["commanders_live"] = live_cmdrs
            a1["color_match"] = saved_colors == live_colors
            a1["colors_saved"] = saved_colors
            a1["colors_live"] = live_colors
            a1["all_match"] = all([
                a1["size_match"],
                a1["bracket_match"],
                a1["commander_match"],
                a1["color_match"],
            ])
            entry["a1"] = a1
            entry["status"] = "ok"

        # A.3: re-compute features and diff against stored.
        try:
            recomputed, _bag = build_deck_features(deck, card_index, printing_lookup)
        except Exception as exc:
            entry["a3"] = {"error": str(exc)}
        else:
            stored = features_by_snapshot.get(snapshot_id) or {}
            metadata_fields = {"snapshot_id", "deck_id", "fetched_at", "archidekt_edh_bracket", "archidekt_updated_at"}
            stored_features = {k: v for k, v in stored.items() if k not in metadata_fields}
            recomputed_features = {k: v for k, v in recomputed.items() if k not in metadata_fields}
            diffs = feature_diff(stored_features, recomputed_features)
            entry["a3"] = {
                "diff_count": len(diffs),
                "diffs": diffs[:20],
                "match": len(diffs) == 0,
            }

        results.append(entry)
        time.sleep(args.sleep)

    # ------------------------------------------------------------------- summary
    a1_ok = sum(1 for r in results if r.get("a1", {}).get("all_match"))
    a1_skipped = sum(1 for r in results if r.get("status") == "skipped_changed_since_scrap")
    a1_fail = sum(1 for r in results if r.get("a1") and not r["a1"].get("skipped") and not r["a1"].get("all_match"))
    fetch_fail = sum(1 for r in results if r.get("status") == "fetch_failed")
    a3_ok = sum(1 for r in results if r.get("a3", {}).get("match"))
    a3_fail = sum(1 for r in results if r.get("a3", {}).get("match") is False)
    a3_err = sum(1 for r in results if r.get("a3", {}).get("error"))

    summary = {
        "sample_size": len(results),
        "a1_ok": a1_ok,
        "a1_skipped_changed": a1_skipped,
        "a1_mismatch": a1_fail,
        "fetch_failed": fetch_fail,
        "a3_match": a3_ok,
        "a3_mismatch": a3_fail,
        "a3_error": a3_err,
        "results": results,
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------- markdown
    lines: List[str] = []
    lines.append("# Sanity Check — Fase A")
    lines.append("")
    lines.append(f"- Amostra: **{len(results)} decks** (estratificado por y1, seed {args.seed}).")
    lines.append("- A.1: compara estado salvo vs Archidekt ao vivo, filtrando decks alterados após o scrap.")
    lines.append("- A.3: re-roda `build_deck_features` sobre o registro salvo e diffa contra `deck_features.jsonl`.")
    lines.append("- A.2 (calculadora) é coberta por `validate_edhpowerlevel_labels.py` separadamente.")
    lines.append("")
    lines.append("## Resumo")
    lines.append("")
    lines.append(f"| Métrica | Valor |")
    lines.append(f"|---|---|")
    lines.append(f"| Falhas de fetch | {fetch_fail} |")
    lines.append(f"| A.1 OK (todos campos) | {a1_ok} |")
    lines.append(f"| A.1 mismatch | {a1_fail} |")
    lines.append(f"| A.1 pulado (deck mudou após scrap) | {a1_skipped} |")
    lines.append(f"| A.3 features idênticas | {a3_ok} |")
    lines.append(f"| A.3 features divergem | {a3_fail} |")
    lines.append(f"| A.3 erro de execução | {a3_err} |")
    lines.append("")
    lines.append("## Detalhe por deck")
    lines.append("")
    lines.append("| # | deck_id | y1 | A.1 | Δ a.3 | obs |")
    lines.append("|---:|---|---:|---|---:|---|")
    for r in results:
        a1 = r.get("a1") or {}
        a3 = r.get("a3") or {}
        if r.get("status") == "fetch_failed":
            a1_cell = "fetch fail"
        elif a1.get("skipped"):
            a1_cell = "skip"
        elif a1.get("all_match"):
            a1_cell = "OK"
        else:
            broken = []
            if not a1.get("size_match"):
                broken.append("size")
            if not a1.get("bracket_match"):
                broken.append(f"bracket({a1.get('bracket_saved')}→{a1.get('bracket_live')})")
            if not a1.get("commander_match"):
                broken.append("cmdr")
            if not a1.get("color_match"):
                broken.append("color")
            a1_cell = ", ".join(broken) or "?"
        a3_cell = a3.get("diff_count")
        if "error" in a3:
            a3_cell = "err"
        obs = ""
        if a1.get("skipped"):
            obs = f"live updatedAt > fetched_at"
        elif r.get("status") == "fetch_failed":
            obs = (r.get("error") or "")[:60]
        lines.append(f"| {r.get('index')} | [{r.get('deck_id')}](https://archidekt.com/decks/{r.get('deck_id')}) | {r.get('y1')} | {a1_cell} | {a3_cell} | {obs} |")
    lines.append("")
    lines.append("## Decks com divergência (detalhes)")
    lines.append("")
    any_diff = False
    for r in results:
        a1 = r.get("a1") or {}
        a3 = r.get("a3") or {}
        if a1.get("skipped"):
            continue
        if a1.get("all_match") and a3.get("match"):
            continue
        any_diff = True
        lines.append(f"### Deck {r.get('deck_id')}  (y1={r.get('y1')})")
        if r.get("status") == "fetch_failed":
            lines.append(f"- **fetch falhou**: `{r.get('error')}`")
        if not a1.get("all_match") and not a1.get("skipped"):
            lines.append("- **A.1**:")
            if not a1.get("size_match"):
                lines.append(f"  - tamanho salvo != 100 ou divergência (live size pre-filtro: {a1.get('live_size_includes_zones')})")
            if not a1.get("bracket_match"):
                lines.append(f"  - bracket: salvo={a1.get('bracket_saved')} live={a1.get('bracket_live')}")
            if not a1.get("commander_match"):
                lines.append(f"  - commanders salvos: {a1.get('commanders_saved')}")
                lines.append(f"  - commanders live: {a1.get('commanders_live')}")
            if not a1.get("color_match"):
                lines.append(f"  - cores salvas: {a1.get('colors_saved')}  · live: {a1.get('colors_live')}")
        if a3.get("match") is False:
            lines.append(f"- **A.3**: {a3.get('diff_count')} features divergentes (primeiras):")
            for k, e, a in a3.get("diffs") or []:
                lines.append(f"  - `{k}`: salvo={e}  recomputado={a}")
        if a3.get("error"):
            lines.append(f"- **A.3 erro**: `{a3.get('error')}`")
        lines.append("")
    if not any_diff:
        lines.append("_Nenhum deck divergente entre os comparados._")
        lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nJSON: {args.json_report}")
    print(f"Markdown: {args.report}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    return 0 if (a1_fail == 0 and a3_fail == 0 and a3_err == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
