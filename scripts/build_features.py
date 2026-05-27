#!/usr/bin/env python3
"""Build Deck Features and Bag of Cards from processed Archidekt JSONL.

This script consumes the outputs of ``process_archidekt_raw.py`` and emits two
modeling-ready tables, one row per accepted deck snapshot:

* ``deck_features.jsonl`` — every numeric / boolean feature described in
  ``documents/backbone.md`` sections 11.1 (A through J) and 11.2 (K, L, M),
  computed strictly from data observable in the Archidekt raw payload.
* ``bag_of_cards.jsonl`` — sparse oracle_uid -> quantity mapping per snapshot,
  ready to be vectorised with sklearn's ``DictVectorizer`` or scipy sparse
  builders.

Printing-level fields (``rarity`` and ``prices``) are not part of the
``oracleCard`` payload and therefore not persisted in ``cards.jsonl``. When
``raw_deck_details.jsonl`` is available the script joins it back in by
``(deck_id, deck_row_id)`` so the rarity and price features defined in 11.1.I
and 11.1.J can be computed. Pass ``--no-printing-features`` to skip that join
entirely (those features come out as 0/None).

The script writes a manifest summarising the run for auditability.
"""

from __future__ import annotations

import argparse
import json
import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_RAW_DIR = Path("data/raw/archidekt")

OUTPUT_FILES = (
    "deck_features.jsonl",
    "bag_of_cards.jsonl",
    "feature_manifest.jsonl",
)

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

# NOTE: Backbone §11.1.F (Archidekt categories) was deliberately removed from
# the implementation. Empirical audit of 12.950 decks showed 22.8% have no
# per-card category that matches any standard functional name (Ramp / Draw /
# Removal / ...) — instead they use the user's own labels (e.g., "Artifact",
# "Dubious Snacks", "Beaters") or generic type buckets. For those decks the
# whole section would emit a constant zero vector, which is both uninformative
# and a confound: it lets the model latch onto "categorisation style" rather
# than deck composition. See backbone.md §11.1.F for the full justification.

# Specific keywords called out in 11.2.K. ``protection_keyword_count`` is
# handled separately because Archidekt encodes Protection variants as
# "Protection from X" strings.
TRACKED_KEYWORDS: Tuple[str, ...] = (
    "Flying",
    "Trample",
    "Haste",
    "Hexproof",
    "Ward",
    "Indestructible",
    "Lifelink",
    "Menace",
    "Vigilance",
    "Deathtouch",
    "Flash",
    "Equip",
    "Annihilator",
    "Cascade",
)

TRACKED_LAYOUTS: Tuple[str, ...] = (
    "normal",
    "transform",
    "modal_dfc",
    "split",
    "adventure",
)

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


def safe_mean(values: List[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def safe_median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def safe_stdev(values: List[float]) -> Optional[float]:
    return statistics.pstdev(values) if len(values) > 1 else (0.0 if values else None)


def color_symbols(values: Iterable[Any]) -> Set[str]:
    out: Set[str] = set()
    for value in values or []:
        symbol = COLOR_NAME_TO_SYMBOL.get(str(value))
        if symbol:
            out.add(symbol)
    return out


def is_basic_land(oracle: Dict[str, Any]) -> bool:
    name = oracle.get("name")
    super_types = set(oracle.get("superTypes") or [])
    types = set(oracle.get("types") or [])
    return name in BASIC_LAND_NAMES or ("Basic" in super_types and "Land" in types)


def load_card_index(cards_path: Path) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for record in iter_jsonl(cards_path) or []:
        oracle_uid = record.get("oracle_uid")
        oracle = record.get("raw_oracle_card") or {}
        if isinstance(oracle_uid, str) and oracle:
            index[oracle_uid] = oracle
    return index


def load_printing_lookup(raw_path: Path) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """Map (deck_id, deck_row_id) -> {rarity, prices} from the raw payloads.

    Prices and rarity are properties of a specific printing, so they live on
    the deck row's ``card`` object (not on ``card.oracleCard``). This pass is
    O(N rows) — roughly 100 rows per deck — and only stores what feature
    extraction needs.
    """
    lookup: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for record in iter_jsonl(raw_path) or []:
        if record.get("status") not in (None, 200):
            continue
        deck = record.get("response") or {}
        deck_id = record.get("deck_id") or deck.get("id")
        if not isinstance(deck_id, int):
            continue
        for row in deck.get("cards") or []:
            if not isinstance(row, dict):
                continue
            row_id = row.get("id")
            if not isinstance(row_id, int):
                continue
            card = row.get("card") or {}
            lookup[(deck_id, row_id)] = {
                "rarity": card.get("rarity"),
                "prices": card.get("prices") or {},
            }
    return lookup


def card_price_paper_nonfoil(prices: Dict[str, Any]) -> Optional[float]:
    """Pick a representative paper non-foil price.

    Archidekt exposes several vendors; we prefer TCGPlayer market (``tcg``)
    since it's the most widely used reference. Falls back through other paper
    vendors when ``tcg`` is missing or zero. Returns ``None`` when no usable
    paper price exists.
    """
    paper_fields = ("tcg", "ck", "cm", "scg", "mp", "cardTrader")
    for key in paper_fields:
        value = prices.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def card_cmc(oracle: Dict[str, Any]) -> float:
    # The Archidekt deck row carries a ``custom_cmc`` field the user can set
    # to override the canonical mana value; ~19% of decks use it on at least
    # one row, with values that mix legitimate uses (X-spells) and subjective
    # preference. We deliberately ignore it and always use ``oracleCard.cmc``
    # so the curve features reflect the canonical card cost — see
    # backbone.md §11.1.D for rationale.
    cmc = oracle.get("cmc")
    if isinstance(cmc, (int, float)):
        return float(cmc)
    return 0.0


def cmc_bucket(cmc: float) -> str:
    if cmc <= 0:
        return "cmc_0_count"
    if cmc >= 6:
        return "cmc_6_plus_count"
    return f"cmc_{int(cmc)}_count"


def build_deck_features(
    deck_record: Dict[str, Any],
    card_index: Dict[str, Dict[str, Any]],
    printing_lookup: Optional[Dict[Tuple[int, int], Dict[str, Any]]],
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Return ({feature_name: value, ...}, {oracle_uid: quantity}).

    The bag-of-cards mapping is computed alongside features to keep both
    derivations consistent (same mainboard view, same quantity treatment).
    """
    mainboard = deck_record.get("mainboard") or []
    deck_id = deck_record.get("deck_id")
    snapshot_id = deck_record.get("snapshot_id")
    metadata = deck_record.get("raw_deck_metadata") or {}

    # --- accumulators -------------------------------------------------------
    bag: Counter = Counter()
    distinct_oracle_uids: Set[str] = set()
    commander_quantity = 0
    non_commander_quantity = 0
    has_companion = False  # process step already excludes them

    type_counts: Counter = Counter()
    cmc_counts: Counter = Counter()
    cmc_values_all: List[float] = []
    cmc_values_nonland: List[float] = []

    edhrec_ranks: List[float] = []
    salts: List[float] = []

    land_count = 0
    nonland_count = 0
    basic_land_count = 0
    nonbasic_land_count = 0
    land_mana_production = {color: 0 for color in ("W", "U", "B", "R", "G", "C")}
    lands_multi_color = 0
    lands_colorless_production = 0

    # Archidekt categories (backbone §11.1.F) intentionally not accumulated —
    # see CATEGORY_FEATURE_MAP comment above for rationale.

    game_changer_count = 0
    extra_turns_count = 0
    tutor_count = 0
    mass_land_denial_count = 0
    two_card_combo_singleton_count = 0

    cards_with_atomic_combos = 0
    cards_with_potential_combos = 0
    atomic_combo_refs_total = 0
    potential_combo_refs_total = 0
    atomic_combo_refs_unique: Set[str] = set()
    potential_combo_refs_unique: Set[str] = set()
    two_card_combo_ids_total = 0
    two_card_combo_ids_unique: Set[str] = set()

    keyword_total = 0
    distinct_keywords: Set[str] = set()
    keyword_specific_counts: Counter = Counter()
    protection_keyword_count = 0

    legendary_count = 0
    snow_count = 0
    distinct_subtypes: Set[str] = set()
    subtype_counts: Counter = Counter()
    equipment_subtype_count = 0
    aura_subtype_count = 0
    vehicle_subtype_count = 0

    multiface_card_count = 0
    layout_counts: Counter = Counter()
    cards_with_faces_count = 0
    total_face_count = 0
    max_faces_on_card = 0

    rarity_counts: Counter = Counter()
    prices_paper: List[float] = []

    deck_color_identity: Set[str] = set()

    # --- iterate mainboard rows --------------------------------------------
    for row in mainboard:
        oracle_uid = row.get("oracle_uid")
        quantity = int(row.get("quantity") or 0)
        if not oracle_uid or quantity <= 0:
            continue

        oracle = card_index.get(oracle_uid) or {}
        bag[oracle_uid] += quantity
        distinct_oracle_uids.add(oracle_uid)

        is_commander = bool(row.get("is_commander"))
        if is_commander:
            commander_quantity += quantity
        else:
            non_commander_quantity += quantity

        # type buckets
        types = set(oracle.get("types") or [])
        super_types = set(oracle.get("superTypes") or [])
        sub_types = set(oracle.get("subTypes") or [])

        is_land = "Land" in types
        is_creature = "Creature" in types
        is_instant = "Instant" in types
        is_sorcery = "Sorcery" in types
        is_artifact = "Artifact" in types
        is_enchantment = "Enchantment" in types
        is_planeswalker = "Planeswalker" in types

        if is_creature:
            type_counts["creature_count"] += quantity
        if is_instant:
            type_counts["instant_count"] += quantity
        if is_sorcery:
            type_counts["sorcery_count"] += quantity
        if is_artifact:
            type_counts["artifact_count"] += quantity
        if is_enchantment:
            type_counts["enchantment_count"] += quantity
        if is_planeswalker:
            type_counts["planeswalker_count"] += quantity
        if is_land:
            land_count += quantity
            if is_basic_land(oracle):
                basic_land_count += quantity
            else:
                nonbasic_land_count += quantity

            mp = oracle.get("manaProduction") or {}
            produces = [c for c in ("W", "U", "B", "R", "G", "C") if mp.get(c)]
            for color in produces:
                land_mana_production[color] += quantity
            non_c_produces = [c for c in produces if c != "C"]
            if len(non_c_produces) > 1:
                lands_multi_color += quantity
            if "C" in produces:
                lands_colorless_production += quantity
        else:
            nonland_count += quantity

        # NOTE: ``permanent_count`` was removed (it was incorrectly excluding
        # lands, making it identical to ``nonland_permanent_count``). Lands
        # are permanents in MTG; if we ever bring back a generic permanent
        # count, the condition must be "not (instant or sorcery)".
        if not is_land and (is_creature or is_artifact or is_enchantment or is_planeswalker):
            type_counts["nonland_permanent_count"] += quantity
        if not is_creature and not is_land:
            type_counts["noncreature_spell_count"] += quantity

        # curve
        cmc = card_cmc(oracle)
        cmc_values_all.extend([cmc] * quantity)
        if not is_land:
            cmc_values_nonland.extend([cmc] * quantity)
            cmc_counts[cmc_bucket(cmc)] += quantity

        # Archidekt per-row categories are intentionally NOT aggregated into
        # features — they are user-defined free text and ~23% of decks have
        # no category that maps to the standard functional vocabulary, which
        # would emit constant-zero columns. The categories field is still
        # preserved on each mainboard row for downstream analyses that want
        # to inspect deck-authoring conventions directly.

        # bracket flags
        if oracle.get("gameChanger"):
            game_changer_count += quantity
        if oracle.get("extraTurns"):
            extra_turns_count += quantity
        if oracle.get("tutor"):
            tutor_count += quantity
        if oracle.get("massLandDenial"):
            mass_land_denial_count += quantity
        if oracle.get("twoCardComboSingelton"):
            two_card_combo_singleton_count += quantity

        # combos
        atomic = oracle.get("atomicCombos") or []
        potential = oracle.get("potentialCombos") or []
        two_card_ids = oracle.get("twoCardComboIds") or []

        if atomic:
            cards_with_atomic_combos += quantity
            atomic_combo_refs_total += len(atomic) * quantity
            atomic_combo_refs_unique.update(str(x) for x in atomic)
        if potential:
            cards_with_potential_combos += quantity
            potential_combo_refs_total += len(potential) * quantity
            potential_combo_refs_unique.update(str(x) for x in potential)
        if two_card_ids:
            two_card_combo_ids_total += len(two_card_ids) * quantity
            two_card_combo_ids_unique.update(str(x) for x in two_card_ids)

        # popularity / salt
        edhrec_rank = oracle.get("edhrecRank")
        if isinstance(edhrec_rank, (int, float)):
            edhrec_ranks.extend([float(edhrec_rank)] * quantity)
        salt = oracle.get("salt")
        if isinstance(salt, (int, float)):
            salts.extend([float(salt)] * quantity)

        # keywords
        keywords = oracle.get("keywords") or []
        keyword_total += len(keywords) * quantity
        for keyword in keywords:
            keyword_str = str(keyword)
            distinct_keywords.add(keyword_str)
            if keyword_str in TRACKED_KEYWORDS:
                keyword_specific_counts[keyword_str] += quantity
            if keyword_str.startswith("Protection"):
                protection_keyword_count += quantity

        # supertypes / subtypes
        if "Legendary" in super_types:
            legendary_count += quantity
        if "Snow" in super_types:
            snow_count += quantity
        for subtype in sub_types:
            distinct_subtypes.add(subtype)
            subtype_counts[subtype] += quantity
        if "Equipment" in sub_types:
            equipment_subtype_count += quantity
        if "Aura" in sub_types:
            aura_subtype_count += quantity
        if "Vehicle" in sub_types:
            vehicle_subtype_count += quantity

        # layouts / faces
        layout = str(oracle.get("layout") or "")
        if layout:
            layout_counts[layout] += quantity
        faces = oracle.get("faces") or []
        if faces:
            multiface_card_count += quantity
            cards_with_faces_count += quantity
            total_face_count += len(faces) * quantity
            if len(faces) > max_faces_on_card:
                max_faces_on_card = len(faces)

        # printing-level (rarity + price)
        if printing_lookup is not None and isinstance(deck_id, int):
            row_id = row.get("deck_row_id")
            if isinstance(row_id, int):
                printing = printing_lookup.get((deck_id, row_id))
                if printing:
                    rarity = printing.get("rarity")
                    if rarity:
                        rarity_counts[str(rarity).casefold()] += quantity
                    price = card_price_paper_nonfoil(printing.get("prices") or {})
                    if price is not None:
                        prices_paper.extend([price] * quantity)

        # color identity (for deck colors)
        deck_color_identity.update(color_symbols(oracle.get("colorIdentity") or []))

    # --- assemble feature row ----------------------------------------------
    features: Dict[str, Any] = {}

    # Identification and labels — y1 = Archidekt community bracket,
    # y2 = EDHPowerLevel "recommended Commander Bracket" (populated by
    # Phase B of process_archidekt_raw.py). y2 may be missing (None) for
    # decks not yet enriched, or a dict carrying an `error` field if the
    # last attempt failed.
    features["snapshot_id"] = snapshot_id
    features["deck_id"] = deck_id
    features["fetched_at"] = deck_record.get("fetched_at")
    features["archidekt_edh_bracket"] = deck_record.get("archidekt_edh_bracket")
    edhpl = deck_record.get("edhpowerlevel")
    features["edhpowerlevel_bracket"] = (
        edhpl.get("commander_bracket")
        if isinstance(edhpl, dict) and not edhpl.get("error")
        else None
    )
    features["edhpowerlevel"] = edhpl
    features["view_count"] = deck_record.get("view_count")
    features["commander_oracle_uids"] = deck_record.get("commander_oracle_uids") or []
    features["mainboard_count"] = deck_record.get("mainboard_count")

    # A. Basic structure
    features["unique_card_count"] = len(distinct_oracle_uids)
    features["non_commander_card_count"] = non_commander_quantity
    features["commander_card_count"] = commander_quantity
    features["has_companion"] = has_companion

    # B. Colors
    features["deck_color_count"] = len(deck_color_identity)
    for color in ("W", "U", "B", "R", "G"):
        features[f"has_{color}"] = color in deck_color_identity

    # C. Mana base
    features["land_count"] = land_count
    features["nonland_count"] = nonland_count
    features["basic_land_count"] = basic_land_count
    features["nonbasic_land_count"] = nonbasic_land_count
    for color in ("W", "U", "B", "R", "G", "C"):
        features[f"land_mana_production_{color}"] = land_mana_production[color]
    features["lands_that_produce_multiple_colors_count"] = lands_multi_color
    features["lands_that_produce_colorless_count"] = lands_colorless_production

    # D. Curve. ``cmc_min``/``cmc_max`` were dropped (low signal: nearly every
    # deck has min=0 from basic lands and max set by a single high-CMC card).
    features["cmc_mean"] = safe_mean(cmc_values_all)
    features["cmc_median"] = safe_median(cmc_values_all)
    features["cmc_std"] = safe_stdev(cmc_values_all)
    features["nonland_cmc_mean"] = safe_mean(cmc_values_nonland)
    features["nonland_cmc_median"] = safe_median(cmc_values_nonland)
    features["nonland_cmc_std"] = safe_stdev(cmc_values_nonland)
    for bucket in (
        "cmc_0_count",
        "cmc_1_count",
        "cmc_2_count",
        "cmc_3_count",
        "cmc_4_count",
        "cmc_5_count",
        "cmc_6_plus_count",
    ):
        features[bucket] = int(cmc_counts.get(bucket, 0))

    # E. Card types. ``permanent_count`` was removed because its previous
    # definition incorrectly excluded lands (which are permanents in MTG),
    # making it identical to ``nonland_permanent_count``.
    for type_field in (
        "creature_count",
        "instant_count",
        "sorcery_count",
        "artifact_count",
        "enchantment_count",
        "planeswalker_count",
        "noncreature_spell_count",
        "nonland_permanent_count",
    ):
        features[type_field] = int(type_counts.get(type_field, 0))
    # land_count already set above

    # F. Archidekt categories: removed (see module-level note + backbone §11.1.F).

    # G. Bracket flags
    features["game_changer_count"] = game_changer_count
    features["extra_turns_count"] = extra_turns_count
    features["tutor_count"] = tutor_count
    features["mass_land_denial_count"] = mass_land_denial_count
    features["two_card_combo_singleton_count"] = two_card_combo_singleton_count

    # H. Combos
    features["cards_with_atomic_combos_count"] = cards_with_atomic_combos
    features["cards_with_potential_combos_count"] = cards_with_potential_combos
    features["atomic_combo_refs_total"] = atomic_combo_refs_total
    features["potential_combo_refs_total"] = potential_combo_refs_total
    features["unique_atomic_combo_refs_count"] = len(atomic_combo_refs_unique)
    features["unique_potential_combo_refs_count"] = len(potential_combo_refs_unique)
    features["two_card_combo_ids_total"] = two_card_combo_ids_total
    features["unique_two_card_combo_ids_count"] = len(two_card_combo_ids_unique)

    # I. Popularity, price, salt
    # ``edhrec_rank_min`` and ``salt_max`` were dropped — both reflect a
    # single dominant card (any deck has a top-100 EDHREC staple like Sol
    # Ring or Command Tower; salt_max is usually a single salty card) and
    # don't characterise the deck's popularity/salt profile. mean/median/std
    # cover that.
    features["edhrec_rank_mean"] = safe_mean(edhrec_ranks)
    features["edhrec_rank_median"] = safe_median(edhrec_ranks)
    features["edhrec_rank_std"] = safe_stdev(edhrec_ranks)
    features["salt_mean"] = safe_mean(salts)
    features["salt_median"] = safe_median(salts)
    features["salt_std"] = safe_stdev(salts)
    # ``high_salt_card_count`` was dropped — the salt>=1.0 threshold was
    # arbitrary; salt_mean/median/std already characterise the salt profile.

    # ``price_max`` was dropped — usually a single expensive card dominates
    # and doesn't characterise overall deck price level.
    features["price_total"] = sum(prices_paper) if prices_paper else None
    features["price_mean"] = safe_mean(prices_paper)
    features["price_median"] = safe_median(prices_paper)
    features["price_std"] = safe_stdev(prices_paper)

    # J. Rarity. ``rare_mythic_count`` was dropped (literally a sum of two
    # other columns — redundant signal for any linear model).
    common_count = int(rarity_counts.get("common", 0))
    uncommon_count = int(rarity_counts.get("uncommon", 0))
    rare_count = int(rarity_counts.get("rare", 0))
    mythic_count = int(rarity_counts.get("mythic", 0))
    features["common_count"] = common_count
    features["uncommon_count"] = uncommon_count
    features["rare_count"] = rare_count
    features["mythic_count"] = mythic_count

    # K. Keywords. ``keyword_count_mean``/``keyword_count_std`` were dropped:
    # noisy because Archidekt/Scryfall include flavor and set-specific
    # keywords (e.g., "Allons-y!") that inflate the per-card count without
    # carrying signal about deck composition.
    features["keyword_total_count"] = keyword_total
    features["distinct_keyword_count"] = len(distinct_keywords)
    for keyword in TRACKED_KEYWORDS:
        features[f"{keyword.lower()}_count"] = int(keyword_specific_counts.get(keyword, 0))
    features["protection_keyword_count"] = protection_keyword_count

    # L. Super/subtypes
    features["legendary_count"] = legendary_count
    features["snow_count"] = snow_count
    features["distinct_subtype_count"] = len(distinct_subtypes)
    features["most_common_subtype_count"] = (
        max(subtype_counts.values()) if subtype_counts else 0
    )
    features["equipment_subtype_count"] = equipment_subtype_count
    features["aura_subtype_count"] = aura_subtype_count
    features["vehicle_subtype_count"] = vehicle_subtype_count

    # M. Layouts / faces
    features["multiface_card_count"] = multiface_card_count
    for layout in TRACKED_LAYOUTS:
        features[f"layout_{layout}_count"] = int(layout_counts.get(layout, 0))
    features["cards_with_faces_count"] = cards_with_faces_count
    features["total_face_count"] = total_face_count
    features["max_faces_on_card"] = max_faces_on_card

    # Light deck-level metadata that's handy for EDA without re-joining.
    features["deck_name"] = metadata.get("name")
    features["archidekt_updated_at"] = deck_record.get("archidekt_updated_at")

    return features, dict(bag)


def existing_snapshot_ids(out_dir: Path) -> Set[str]:
    out: Set[str] = set()
    for record in iter_jsonl(out_dir / "deck_features.jsonl") or []:
        sid = record.get("snapshot_id")
        if isinstance(sid, str):
            out.add(sid)
    return out


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Deck Features and Bag of Cards from processed Archidekt JSONL.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Directory containing decks.jsonl and cards.jsonl.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help="Directory containing raw_deck_details.jsonl (for printing-level features).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for feature outputs (defaults to --processed-dir).",
    )
    parser.add_argument(
        "--no-printing-features",
        action="store_true",
        help="Skip loading raw for rarity/price features; those columns come out 0/None.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing feature outputs instead of appending only new snapshots.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    processed_dir: Path = args.processed_dir
    out_dir: Path = args.out_dir or processed_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    decks_path = processed_dir / "decks.jsonl"
    cards_path = processed_dir / "cards.jsonl"

    if not decks_path.exists():
        raise FileNotFoundError(
            f"Expected {decks_path} — run process-archidekt-raw first."
        )

    if args.overwrite:
        for filename in OUTPUT_FILES:
            path = out_dir / filename
            if path.exists():
                path.unlink()

    features_path = out_dir / "deck_features.jsonl"
    bag_path = out_dir / "bag_of_cards.jsonl"
    manifest_path = out_dir / "feature_manifest.jsonl"

    card_index = load_card_index(cards_path)

    printing_lookup: Optional[Dict[Tuple[int, int], Dict[str, Any]]] = None
    raw_details_path = args.raw_dir / "raw_deck_details.jsonl"
    if not args.no_printing_features:
        if raw_details_path.exists():
            printing_lookup = load_printing_lookup(raw_details_path)
        else:
            printing_lookup = None

    already_built = existing_snapshot_ids(out_dir) if not args.overwrite else set()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    summary: Dict[str, Any] = {
        "record_type": "archidekt_feature_manifest",
        "run_id": run_id,
        "started_at": utc_now_iso(),
        "finished_at": None,
        "parameters": {
            "processed_dir": str(processed_dir),
            "raw_dir": str(args.raw_dir),
            "out_dir": str(out_dir),
            "include_printing_features": not args.no_printing_features,
            "printing_lookup_loaded": printing_lookup is not None,
            "overwrite": bool(args.overwrite),
        },
        "cards_indexed": len(card_index),
        "printing_rows_indexed": len(printing_lookup) if printing_lookup else 0,
        "decks_processed": 0,
        "decks_skipped_existing": 0,
        "decks_failed": 0,
        "errors": [],
    }

    for deck_record in iter_jsonl(decks_path) or []:
        sid = deck_record.get("snapshot_id")
        if not isinstance(sid, str):
            summary["decks_failed"] += 1
            summary["errors"].append({"reason": "missing_snapshot_id", "deck_id": deck_record.get("deck_id")})
            continue
        if sid in already_built:
            summary["decks_skipped_existing"] += 1
            continue

        try:
            features, bag = build_deck_features(deck_record, card_index, printing_lookup)
        except Exception as exc:  # surface but keep going so one bad deck doesn't abort
            summary["decks_failed"] += 1
            summary["errors"].append({"reason": "feature_build_error", "snapshot_id": sid, "error": str(exc)})
            continue

        append_jsonl(features_path, features)
        append_jsonl(
            bag_path,
            {
                "snapshot_id": sid,
                "deck_id": deck_record.get("deck_id"),
                "archidekt_edh_bracket": deck_record.get("archidekt_edh_bracket"),
                "counts": bag,
            },
        )
        already_built.add(sid)
        summary["decks_processed"] += 1

    summary["finished_at"] = utc_now_iso()
    append_jsonl(manifest_path, summary)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
