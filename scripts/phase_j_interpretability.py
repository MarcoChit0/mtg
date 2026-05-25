#!/usr/bin/env python3
"""Phase J — Interpretability of the two best models (BC + DF).

Analyses the two models selected by Phase H:
  - bc_gradient_boosting : Bag of Cards representation
  - df_gradient_boosting : Deck Features representation

For DF: trains a final model on all data with modal hyperparams from Phase H,
then computes permutation importance on a stratified hold-out (20%).  Also
computes conditional feature means per predicted bracket and feature differences
between concordant (ŷ1 == y2) vs divergent (ŷ1 != y2) OOF decks.

For BC: uses the 36,405 existing OOF predictions to compute card "lift" per
predicted class (P(card | ŷ1=k) / P(card)) and to identify cards enriched or
depleted in concordant vs divergent decks.  Permutation importance is omitted
for BC because the dense conversion of ~10k features × HistGB would take
hours — lift analysis is more efficient and equally interpretable.

y2 is NEVER used as a training target (backbone §5).  It appears only as a
comparison label in the divergence analysis sections.

Usage:
    uv run --no-sync python -m scripts.phase_j_interpretability
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline

try:
    from preprocessing import (  # type: ignore
        BagOfCardsPreprocessor,
        DeckFeaturePreprocessor,
        iter_jsonl,
        target_vector,
        y2_value,
    )
except ImportError:
    from scripts.preprocessing import (  # type: ignore
        BagOfCardsPreprocessor,
        DeckFeaturePreprocessor,
        iter_jsonl,
        target_vector,
        y2_value,
    )

# ─── Paths ───────────────────────────────────────────────────────────────────

DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
REPORT_FILENAME = "phase_j_interpretability.md"
PHASE_J_DIR = Path("experiments/phase_j_interpretability")

# ─── Constants ───────────────────────────────────────────────────────────────

BC_MIN_DF = 10          # same as Phase E (checkpoint_state.json)
LABELS = [2, 3, 4]
N_PI_REPEATS = 10       # permutation importance repeats (DF model)
VAL_FRACTION = 0.20     # hold-out fraction for PI
RANDOM_STATE = 42
TOP_N_FEATURES_DF = 15  # top features shown in DF report
TOP_N_CARDS_BC = 20     # top cards per class in BC report
TOP_N_DIVERGENCE = 10   # top features/cards in divergence sections
MIN_CARD_DECK_COUNT = 10  # min unique decks containing a card (matches bc_min_df)

# Modal hyperparams across all 15 outer folds (from Phase H analysis)
# DF: 12/15 folds → max_leaf_nodes=31, lr=0.05; BC: 13/15 folds → same config
MODAL_PARAMS: Dict[str, Any] = {
    "class_weight": "balanced",
    "learning_rate": 0.05,
    "max_iter": 200,
    "max_leaf_nodes": 31,
}


# ─── SparseToDenseTransformer (replicated from phase_e_nested_cv) ─────────────

class SparseToDenseTransformer(BaseEstimator, TransformerMixin):
    """Convert sparse BC matrices to dense arrays for HistGB."""

    def fit(self, X: Any, y: Any = None) -> "SparseToDenseTransformer":
        return self

    def transform(self, X: Any) -> np.ndarray:
        from scipy import sparse
        if sparse.issparse(X):
            return X.toarray()
        return np.asarray(X)


# ─── I/O helpers ─────────────────────────────────────────────────────────────

def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def print_step(msg: str) -> None:
    print(f"[Phase J] {msg}", file=sys.stderr, flush=True)


# ─── Data loading ─────────────────────────────────────────────────────────────

def load_modeling_data(
    processed_dir: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (feature_records, bag_records) for the modeling snapshot."""
    ids_path = processed_dir / "modeling_snapshot_ids.json"
    if not ids_path.exists():
        raise FileNotFoundError(f"Missing {ids_path}; run phase-c-filter-dataset first.")
    snapshot_ids: List[str] = read_json(ids_path)
    id_set = set(snapshot_ids)

    features_by_id = {
        r["snapshot_id"]: r
        for r in iter_jsonl(processed_dir / "deck_features.jsonl")
        if r.get("snapshot_id") in id_set
    }
    bags_by_id = {
        r["snapshot_id"]: r
        for r in iter_jsonl(processed_dir / "bag_of_cards.jsonl")
        if r.get("snapshot_id") in id_set
    }
    feature_records = [features_by_id[sid] for sid in snapshot_ids if sid in features_by_id]
    bag_records = [bags_by_id[sid] for sid in snapshot_ids if sid in bags_by_id]
    return feature_records, bag_records


def load_card_names(processed_dir: Path) -> Dict[str, str]:
    """Return {oracle_uid: oracle_name} mapping from cards.jsonl."""
    mapping: Dict[str, str] = {}
    cards_path = processed_dir / "cards.jsonl"
    if not cards_path.exists():
        return mapping
    for r in iter_jsonl(cards_path):
        uid = r.get("oracle_uid")
        name = r.get("oracle_name")
        if uid and name:
            mapping[str(uid)] = str(name)
    return mapping


def load_oof_predictions(model_dir: Path) -> List[Dict[str, Any]]:
    """Load predictions_per_fold.jsonl for a model."""
    pred_path = model_dir / "predictions_per_fold.jsonl"
    if not pred_path.exists():
        raise FileNotFoundError(f"Missing {pred_path}")
    return list(iter_jsonl(pred_path))


def _counts(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Extract card counts from a bag-of-cards record."""
    counts = record.get("counts", record)
    return counts if isinstance(counts, Mapping) else {}


# ─── DF model interpretation ──────────────────────────────────────────────────

def build_df_pipeline(params: Dict[str, Any], random_state: int) -> Pipeline:
    clf = HistGradientBoostingClassifier(random_state=random_state, **params)
    return Pipeline([
        ("prep", DeckFeaturePreprocessor(scale=False)),
        ("clf", clf),
    ])


def compute_modal_params(hyperparams_path: Path) -> Dict[str, Any]:
    """Find most-common hyperparameter configuration across folds."""
    records = read_json(hyperparams_path)
    # Strip 'clf__' prefix and count configs
    configs: List[str] = []
    for r in records:
        stripped = {k.replace("clf__", ""): v for k, v in r["best_params"].items()}
        configs.append(json.dumps(stripped, sort_keys=True))
    modal_json = Counter(configs).most_common(1)[0][0]
    return json.loads(modal_json)


def interpret_df_model(
    feature_records: List[Dict[str, Any]],
    oof_preds_df: List[Dict[str, Any]],
    hyperparams_path: Path,
    *,
    random_state: int = RANDOM_STATE,
    n_pi_repeats: int = N_PI_REPEATS,
    val_fraction: float = VAL_FRACTION,
    top_n: int = TOP_N_FEATURES_DF,
    top_n_div: int = TOP_N_DIVERGENCE,
) -> Dict[str, Any]:
    """Full DF interpretation: PI, directional means, divergence features."""
    print_step("DF — loading modal hyperparams...")
    modal = compute_modal_params(hyperparams_path)
    print_step(f"DF — modal params: {modal}")

    y_all = np.array([r["archidekt_edh_bracket"] for r in feature_records], dtype=int)

    # ── Train/val split (stratified) ──────────────────────────────────────────
    print_step(f"DF — building final model (80/20 split, n={len(feature_records)})...")
    sss = StratifiedShuffleSplit(n_splits=1, test_size=val_fraction, random_state=random_state)
    train_idx, val_idx = next(sss.split(feature_records, y_all))

    X_train = [feature_records[i] for i in train_idx]
    X_val = [feature_records[i] for i in val_idx]
    y_train = y_all[train_idx]
    y_val = y_all[val_idx]

    pipeline = build_df_pipeline(modal, random_state)
    pipeline.fit(X_train, y_train)

    prep = pipeline.named_steps["prep"]
    clf = pipeline.named_steps["clf"]
    feature_names: List[str] = list(prep.output_feature_names_)

    X_val_arr: np.ndarray = prep.transform(X_val)
    y_pred_val: np.ndarray = clf.predict(X_val_arr)

    # ── Permutation importance ────────────────────────────────────────────────
    print_step(f"DF — computing permutation importance (n_repeats={n_pi_repeats})...")
    pi_result = permutation_importance(
        clf, X_val_arr, y_val,
        scoring="f1_macro",
        n_repeats=n_pi_repeats,
        random_state=random_state,
        n_jobs=1,
    )
    pi_means = pi_result.importances_mean
    pi_stds = pi_result.importances_std

    pi_ranked = sorted(
        range(len(feature_names)),
        key=lambda i: pi_means[i],
        reverse=True,
    )
    top_indices = [i for i in pi_ranked if pi_means[i] > 0][:top_n]
    if len(top_indices) < top_n:
        top_indices = pi_ranked[:top_n]

    pi_table = [
        {
            "feature": feature_names[i],
            "pi_mean": float(pi_means[i]),
            "pi_std": float(pi_stds[i]),
        }
        for i in top_indices
    ]

    # ── Directional means (conditional mean per predicted bracket) ────────────
    print_step("DF — computing conditional means per predicted bracket...")
    direction_table = []
    for feat_idx in top_indices:
        row: Dict[str, Any] = {"feature": feature_names[feat_idx]}
        for k in LABELS:
            mask = y_pred_val == k
            if mask.sum() >= 5:
                row[f"mean_pred_{k}"] = float(np.nanmean(X_val_arr[mask, feat_idx]))
            else:
                row[f"mean_pred_{k}"] = None
        # overall mean
        row["mean_overall"] = float(np.nanmean(X_val_arr[:, feat_idx]))
        direction_table.append(row)

    # ── Divergence analysis using OOF predictions ─────────────────────────────
    print_step("DF — computing divergence analysis over OOF predictions...")
    # Build {snapshot_id: feature_vector} mapping from full dataset
    prep_full = build_df_pipeline(modal, random_state).named_steps["prep"]
    full_pipeline = build_df_pipeline(modal, random_state)
    full_pipeline.fit(feature_records, y_all)  # fit on all data for prep state
    prep_full_fitted = full_pipeline.named_steps["prep"]
    feat_names_full: List[str] = list(prep_full_fitted.output_feature_names_)
    X_all_arr: np.ndarray = prep_full_fitted.transform(feature_records)

    sid_to_idx: Dict[str, int] = {r["snapshot_id"]: i for i, r in enumerate(feature_records)}

    concordant_vecs: List[np.ndarray] = []
    divergent_vecs: List[np.ndarray] = []
    for entry in oof_preds_df:
        sid = entry.get("snapshot_id")
        y_pred = entry.get("y_pred")
        y2 = entry.get("y2")
        if sid is None or y_pred is None or y2 is None:
            continue
        idx = sid_to_idx.get(sid)
        if idx is None:
            continue
        vec = X_all_arr[idx]
        if int(y_pred) == int(y2):
            concordant_vecs.append(vec)
        else:
            divergent_vecs.append(vec)

    divergence_table: List[Dict[str, Any]] = []
    if concordant_vecs and divergent_vecs:
        conc_mat = np.stack(concordant_vecs)
        div_mat = np.stack(divergent_vecs)
        conc_means = np.nanmean(conc_mat, axis=0)
        div_means = np.nanmean(div_mat, axis=0)
        # Normalize difference by overall std
        overall_std = np.nanstd(X_all_arr, axis=0)
        delta = div_means - conc_means
        norm_delta = np.where(overall_std > 0, delta / overall_std, 0.0)
        top_div_idx = np.argsort(np.abs(norm_delta))[::-1][:top_n_div]
        for i in top_div_idx:
            divergence_table.append({
                "feature": feat_names_full[i],
                "mean_concordant": float(conc_means[i]),
                "mean_divergent": float(div_means[i]),
                "delta": float(delta[i]),
                "normalized_delta": float(norm_delta[i]),
            })

    return {
        "modal_params": modal,
        "n_train": int(len(train_idx)),
        "n_val": int(len(val_idx)),
        "n_features": len(feature_names),
        "n_concordant_oof": len(concordant_vecs),
        "n_divergent_oof": len(divergent_vecs),
        "permutation_importance": pi_table,
        "directional_means": direction_table,
        "divergence_features": divergence_table,
    }


# ─── BC model interpretation ──────────────────────────────────────────────────

def compute_card_frequencies(
    oof_preds: List[Dict[str, Any]],
    bags_by_sid: Dict[str, Dict[str, Any]],
    *,
    min_deck_count: int = MIN_CARD_DECK_COUNT,
) -> Tuple[
    Dict[int, Dict[str, float]],  # freq_by_class[k][oracle_uid] = fraction
    Dict[str, float],             # overall_freq[oracle_uid] = fraction
    Dict[str, int],               # card_deck_count[oracle_uid] = n unique decks
]:
    """Compute per-class and overall card frequencies over OOF predictions."""
    # Count unique decks containing each card (for min_deck_count filter)
    card_unique_decks: Dict[str, set] = defaultdict(set)
    # Count occurrences per class (using all OOF entries, not deduplicated)
    class_counts: Dict[int, Counter] = {k: Counter() for k in LABELS}
    class_total: Dict[int, int] = {k: 0 for k in LABELS}
    overall_counter: Counter = Counter()
    overall_total = 0

    for entry in oof_preds:
        sid = entry.get("snapshot_id")
        y_pred = entry.get("y_pred")
        if sid is None or y_pred is None:
            continue
        k = int(y_pred)
        if k not in LABELS:
            continue
        bag = bags_by_sid.get(sid)
        if bag is None:
            continue
        cards = _counts(bag)
        class_total[k] += 1
        overall_total += 1
        for oracle_uid, qty in cards.items():
            if float(qty or 0) > 0:
                class_counts[k][oracle_uid] += 1
                overall_counter[oracle_uid] += 1
                card_unique_decks[oracle_uid].add(sid)

    # Build unique deck count
    card_deck_count: Dict[str, int] = {uid: len(sids) for uid, sids in card_unique_decks.items()}

    # Compute frequencies
    freq_by_class: Dict[int, Dict[str, float]] = {}
    for k in LABELS:
        total = class_total[k] if class_total[k] > 0 else 1
        freq_by_class[k] = {uid: cnt / total for uid, cnt in class_counts[k].items()}

    overall_total_safe = overall_total if overall_total > 0 else 1
    overall_freq: Dict[str, float] = {uid: cnt / overall_total_safe for uid, cnt in overall_counter.items()}

    # Apply minimum deck count filter
    keep = {uid for uid, n in card_deck_count.items() if n >= min_deck_count}
    freq_by_class = {k: {uid: f for uid, f in freqs.items() if uid in keep} for k, freqs in freq_by_class.items()}
    overall_freq = {uid: f for uid, f in overall_freq.items() if uid in keep}
    card_deck_count = {uid: n for uid, n in card_deck_count.items() if uid in keep}

    return freq_by_class, overall_freq, card_deck_count


def top_cards_by_lift(
    freq_by_class: Dict[int, Dict[str, float]],
    overall_freq: Dict[str, float],
    card_names: Dict[str, str],
    top_n: int = TOP_N_CARDS_BC,
) -> Dict[int, List[Dict[str, Any]]]:
    """For each class k, return top-N cards by lift = P(card | ŷ1=k) / P(card)."""
    result: Dict[int, List[Dict[str, Any]]] = {}
    for k in LABELS:
        class_freq = freq_by_class.get(k, {})
        lifts = []
        for uid, freq_k in class_freq.items():
            overall = overall_freq.get(uid, 1e-9)
            lift = freq_k / overall if overall > 0 else 0.0
            name = card_names.get(uid, uid)
            lifts.append({
                "oracle_uid": uid,
                "card_name": name,
                "lift": float(lift),
                "freq_in_class": float(freq_k),
                "freq_overall": float(overall),
            })
        lifts.sort(key=lambda x: x["lift"], reverse=True)
        result[k] = lifts[:top_n]
    return result


def compute_divergence_cards(
    oof_preds: List[Dict[str, Any]],
    bags_by_sid: Dict[str, Dict[str, Any]],
    card_names: Dict[str, str],
    *,
    min_deck_count: int = MIN_CARD_DECK_COUNT,
    top_n: int = TOP_N_DIVERGENCE,
) -> Dict[str, Any]:
    """Identify cards enriched in concordant vs divergent OOF predictions."""
    conc_counter: Counter = Counter()
    div_counter: Counter = Counter()
    conc_total = 0
    div_total = 0

    # Also split by direction of divergence
    over_counter: Counter = Counter()   # ŷ1 > y2 (model predicts higher)
    under_counter: Counter = Counter()  # ŷ1 < y2 (model predicts lower)
    over_total = 0
    under_total = 0

    card_unique_decks: Dict[str, set] = defaultdict(set)

    for entry in oof_preds:
        sid = entry.get("snapshot_id")
        y_pred = entry.get("y_pred")
        y2 = entry.get("y2")
        if sid is None or y_pred is None or y2 is None:
            continue
        bag = bags_by_sid.get(sid)
        if bag is None:
            continue
        cards = _counts(bag)
        concordant = int(y_pred) == int(y2)

        if concordant:
            conc_total += 1
            for uid, qty in cards.items():
                if float(qty or 0) > 0:
                    conc_counter[uid] += 1
                    card_unique_decks[uid].add(sid)
        else:
            div_total += 1
            for uid, qty in cards.items():
                if float(qty or 0) > 0:
                    div_counter[uid] += 1
                    card_unique_decks[uid].add(sid)
            # Direction
            if int(y_pred) > int(y2):
                over_total += 1
                for uid, qty in cards.items():
                    if float(qty or 0) > 0:
                        over_counter[uid] += 1
            elif int(y_pred) < int(y2):
                under_total += 1
                for uid, qty in cards.items():
                    if float(qty or 0) > 0:
                        under_counter[uid] += 1

    keep = {uid for uid, sids in card_unique_decks.items() if len(sids) >= min_deck_count}

    def freq_dict(counter: Counter, total: int) -> Dict[str, float]:
        t = total if total > 0 else 1
        return {uid: cnt / t for uid, cnt in counter.items() if uid in keep}

    conc_freq = freq_dict(conc_counter, conc_total)
    div_freq = freq_dict(div_counter, div_total)
    over_freq = freq_dict(over_counter, over_total)
    under_freq = freq_dict(under_counter, under_total)

    all_uids = set(conc_freq) | set(div_freq)

    # Laplace smoothing: avoid near-zero denominators
    # alpha = ~0.05% of OOF entries — ensures lift stays bounded for rare cards
    smooth = 5e-4

    def lift_rows(base_freq: Dict[str, float], ref_freq: Dict[str, float]) -> List[Dict[str, Any]]:
        rows = []
        for uid in all_uids:
            b = base_freq.get(uid, 0.0)
            r = ref_freq.get(uid, 0.0)
            # Require at least a minimum frequency in the base group to avoid noise
            if b < smooth:
                continue
            lift = (b + smooth) / (r + smooth)
            rows.append({
                "oracle_uid": uid,
                "card_name": card_names.get(uid, uid),
                "lift": float(lift),
                "freq_base": float(b),
                "freq_ref": float(r),
            })
        rows.sort(key=lambda x: x["lift"], reverse=True)
        return rows[:top_n]

    # Cards enriched in divergent vs concordant
    div_enriched = lift_rows(div_freq, conc_freq)
    # Cards enriched in concordant vs divergent
    conc_enriched = lift_rows(conc_freq, div_freq)
    # Within divergent: over-predicted vs under-predicted
    over_enriched = lift_rows(over_freq, under_freq)
    under_enriched = lift_rows(under_freq, over_freq)

    return {
        "n_concordant_oof": conc_total,
        "n_divergent_oof": div_total,
        "n_over_predicted_oof": over_total,
        "n_under_predicted_oof": under_total,
        "divergent_enriched": div_enriched,
        "concordant_enriched": conc_enriched,
        "over_predicted_enriched": over_enriched,
        "under_predicted_enriched": under_enriched,
    }


def interpret_bc_model(
    bag_records: List[Dict[str, Any]],
    oof_preds_bc: List[Dict[str, Any]],
    card_names: Dict[str, str],
    *,
    min_deck_count: int = MIN_CARD_DECK_COUNT,
    top_n: int = TOP_N_CARDS_BC,
    top_n_div: int = TOP_N_DIVERGENCE,
) -> Dict[str, Any]:
    """BC interpretation: card lift per class, divergence analysis."""
    print_step(f"BC — building card lookup ({len(bag_records)} decks)...")
    bags_by_sid: Dict[str, Dict[str, Any]] = {r["snapshot_id"]: r for r in bag_records}

    print_step("BC — computing card frequencies and lift per predicted bracket...")
    freq_by_class, overall_freq, card_deck_count = compute_card_frequencies(
        oof_preds_bc, bags_by_sid, min_deck_count=min_deck_count
    )
    top_cards = top_cards_by_lift(freq_by_class, overall_freq, card_names, top_n=top_n)

    print_step("BC — computing divergence card analysis...")
    divergence = compute_divergence_cards(
        oof_preds_bc, bags_by_sid, card_names,
        min_deck_count=min_deck_count, top_n=top_n_div,
    )

    # Overall vocabulary size
    vocab_size = len(overall_freq)

    return {
        "vocab_size": vocab_size,
        "n_oof_entries": len(oof_preds_bc),
        "top_cards_by_class": {str(k): top_cards[k] for k in LABELS},
        "divergence_analysis": divergence,
    }


# ─── Report rendering ─────────────────────────────────────────────────────────

def _fmt(v: Optional[float], decimals: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def render_report(
    df_results: Dict[str, Any],
    bc_results: Dict[str, Any],
    out_path: Path,
) -> None:
    lines: List[str] = []
    a = lines.append

    a("# Fase J — Interpretabilidade dos Melhores Modelos")
    a("")
    a("> Gerado automaticamente por `scripts/phase_j_interpretability.py`.")
    a("> Estimativas de generalização vêm da **Fase E** (nested CV).")
    a("> Este modelo final é treinado em todos os dados **exclusivamente para interpretação**.")
    a("> `y2` aparece apenas como label de comparação — nunca como alvo de treino (backbone §5).")
    a("")

    # ── 0. Configuração ───────────────────────────────────────────────────────
    a("## 0. Configuração")
    a("")
    a("| Parâmetro | Valor |")
    a("|---|---|")
    a(f"| Modelo DF | `df_gradient_boosting` |")
    a(f"| Modelo BC | `bc_gradient_boosting` |")
    a(f"| Hiperparâmetros DF | modal dos 15 outer folds: {df_results['modal_params']} |")
    a(f"| Hiperparâmetros BC | modal dos 15 outer folds: {MODAL_PARAMS} |")
    a(f"| Split treino/val (DF) | {int((1-VAL_FRACTION)*100)}/{int(VAL_FRACTION*100)} — n_train={df_results['n_train']}, n_val={df_results['n_val']} |")
    a(f"| PI n_repeats (DF) | {N_PI_REPEATS} |")
    a(f"| Features DF (após pré-proc.) | {df_results['n_features']} |")
    a(f"| Vocabulário BC (min_df={BC_MIN_DF}) | {bc_results['vocab_size']} cartas |")
    a(f"| OOF entries BC | {bc_results['n_oof_entries']} (12.135 decks × 3 repeats) |")
    a("")

    # ── 1. df_gradient_boosting ───────────────────────────────────────────────
    a("## 1. `df_gradient_boosting` — Deck Features")
    a("")
    a("> **Método**: permutation importance sobre hold-out estratificado (20%).")
    a("> HistGradientBoostingClassifier não expõe `feature_importances_` MDI diretamente;")
    a("> permutation importance é o método recomendado pelo sklearn para este estimador.")
    a("")

    # 1.1 PI table
    a("### 1.1 Importância de features (permutation importance, macro-F1)")
    a("")
    a("| # | Feature | PI médio | PI dp |")
    a("|---|---|---:|---:|")
    for rank, row in enumerate(df_results["permutation_importance"], start=1):
        a(f"| {rank} | `{row['feature']}` | {_fmt(row['pi_mean'])} | {_fmt(row['pi_std'])} |")
    a("")

    # 1.2 Directional means
    a("### 1.2 Direção do efeito por bracket previsto")
    a("")
    a("> Médias do valor da feature condicionadas ao bracket previsto pelo modelo no val set.")
    a("> Interpretação como hipótese analítica — não implica causalidade.")
    a("")
    a("| Feature | Geral | Bracket 2 (pred) | Bracket 3 (pred) | Bracket 4 (pred) |")
    a("|---|---:|---:|---:|---:|")
    for row in df_results["directional_means"]:
        a(
            f"| `{row['feature']}` "
            f"| {_fmt(row.get('mean_overall'), 3)} "
            f"| {_fmt(row.get('mean_pred_2'), 3)} "
            f"| {_fmt(row.get('mean_pred_3'), 3)} "
            f"| {_fmt(row.get('mean_pred_4'), 3)} |"
        )
    a("")

    # 1.3 Divergence
    a("### 1.3 Features associadas à divergência ŷ1 vs y2")
    a("")
    n_conc = df_results["n_concordant_oof"]
    n_div = df_results["n_divergent_oof"]
    a(f"> OOF entries: {n_conc} concordantes (ŷ1=y2), {n_div} divergentes (ŷ1≠y2).")
    a("> `delta` = mean(divergente) − mean(concordante). `norm_delta` = delta / dp_geral.")
    a("")
    a("| Feature | Conc. média | Div. média | Δ | Δ normalizado |")
    a("|---|---:|---:|---:|---:|")
    for row in df_results["divergence_features"]:
        a(
            f"| `{row['feature']}` "
            f"| {_fmt(row['mean_concordant'], 3)} "
            f"| {_fmt(row['mean_divergent'], 3)} "
            f"| {_fmt(row['delta'], 3)} "
            f"| {_fmt(row['normalized_delta'], 3)} |"
        )
    a("")

    # ── 2. bc_gradient_boosting ───────────────────────────────────────────────
    a("## 2. `bc_gradient_boosting` — Bag of Cards")
    a("")
    a("> **Método**: lift analysis sobre as 36.405 predições OOF existentes.")
    a("> `lift[k][carta] = P(carta presente | ŷ1=k) / P(carta presente)`.")
    a("> Permutation importance omitida: conversão densa de ~10k features × HistGB seria inviável.")
    a("> Cartas com menos de " + str(MIN_CARD_DECK_COUNT) + " decks únicos são filtradas.")
    a("")

    # 2.1 Top cards per class
    top_by_class = bc_results["top_cards_by_class"]
    for k in LABELS:
        label_desc = {2: "casual", 3: "médio", 4: "competitivo"}
        a(f"### 2.{k-1}. Top-{TOP_N_CARDS_BC} cartas — Bracket {k} ({label_desc[k]})")
        a("")
        a(f"| # | Carta | Lift | Freq. no bracket | Freq. geral |")
        a("|---|---|---:|---:|---:|")
        for rank, row in enumerate(top_by_class.get(str(k), []), start=1):
            a(
                f"| {rank} | {row['card_name']} "
                f"| {_fmt(row['lift'], 3)} "
                f"| {_pct(row['freq_in_class'])} "
                f"| {_pct(row['freq_overall'])} |"
            )
        a("")

    # 2.4 Divergence
    a(f"### 2.4 Cartas associadas à divergência ŷ1 vs y2")
    div = bc_results["divergence_analysis"]
    n_conc_bc = div["n_concordant_oof"]
    n_div_bc = div["n_divergent_oof"]
    n_over = div["n_over_predicted_oof"]
    n_under = div["n_under_predicted_oof"]
    a(f"> OOF: {n_conc_bc} concordantes, {n_div_bc} divergentes")
    a(f"> ({n_over} super-previstos ŷ1>y2, {n_under} sub-previstos ŷ1<y2).")
    a("")

    a("#### Cartas enriquecidas em decks divergentes (lift vs concordantes)")
    a("")
    a("| # | Carta | Lift | Freq. div. | Freq. conc. |")
    a("|---|---|---:|---:|---:|")
    for rank, row in enumerate(div["divergent_enriched"], start=1):
        a(
            f"| {rank} | {row['card_name']} "
            f"| {_fmt(row['lift'], 3)} "
            f"| {_pct(row['freq_base'])} "
            f"| {_pct(row['freq_ref'])} |"
        )
    a("")

    a("#### Cartas enriquecidas em decks concordantes (lift vs divergentes)")
    a("")
    a("| # | Carta | Lift | Freq. conc. | Freq. div. |")
    a("|---|---|---:|---:|---:|")
    for rank, row in enumerate(div["concordant_enriched"], start=1):
        a(
            f"| {rank} | {row['card_name']} "
            f"| {_fmt(row['lift'], 3)} "
            f"| {_pct(row['freq_base'])} "
            f"| {_pct(row['freq_ref'])} |"
        )
    a("")

    a("#### Cartas enriquecidas em decks super-previstos (ŷ1 > y2)")
    a("")
    a("| # | Carta | Lift | Freq. ŷ1>y2 | Freq. ŷ1<y2 |")
    a("|---|---|---:|---:|---:|")
    for rank, row in enumerate(div["over_predicted_enriched"], start=1):
        a(
            f"| {rank} | {row['card_name']} "
            f"| {_fmt(row['lift'], 3)} "
            f"| {_pct(row['freq_base'])} "
            f"| {_pct(row['freq_ref'])} |"
        )
    a("")

    a("#### Cartas enriquecidas em decks sub-previstos (ŷ1 < y2)")
    a("")
    a("| # | Carta | Lift | Freq. ŷ1<y2 | Freq. ŷ1>y2 |")
    a("|---|---|---:|---:|---:|")
    for rank, row in enumerate(div["under_predicted_enriched"], start=1):
        a(
            f"| {rank} | {row['card_name']} "
            f"| {_fmt(row['lift'], 3)} "
            f"| {_pct(row['freq_base'])} "
            f"| {_pct(row['freq_ref'])} |"
        )
    a("")

    # ── 3. Artefatos ──────────────────────────────────────────────────────────
    a("## 3. Artefatos")
    a("")
    a("| Artefato | Caminho |")
    a("|---|---|")
    a(f"| Hiperparâmetros finais usados | `{PHASE_J_DIR}/final_model_params.json` |")
    a(f"| PI DF (raw) | `{PHASE_J_DIR}/df_permutation_importance.json` |")
    a(f"| Lift BC por classe (raw) | `{PHASE_J_DIR}/bc_card_lift_per_class.json` |")
    a(f"| Análise divergência DF (raw) | `{PHASE_J_DIR}/df_divergence_features.json` |")
    a(f"| Análise divergência BC (raw) | `{PHASE_J_DIR}/bc_divergence_cards.json` |")
    a(f"| Este relatório | `{DEFAULT_DOCS_DIR}/{REPORT_FILENAME}` |")
    a("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print_step(f"Report written to {out_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Phase J — Interpretability of best BC and DF models."
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Directory with deck_features.jsonl, bag_of_cards.jsonl, cards.jsonl",
    )
    parser.add_argument(
        "--experiment-dir",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR,
        help="Base experiments directory",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        help="Output directory for results report",
    )
    parser.add_argument(
        "--n-pi-repeats",
        type=int,
        default=N_PI_REPEATS,
        help="Number of repeats for permutation importance (DF model)",
    )
    args = parser.parse_args(argv)

    # Load best_models.json
    best_models_path = args.experiment_dir / "best_models.json"
    if not best_models_path.exists():
        print(f"[Phase J] ERROR: {best_models_path} not found. Run phase-h-best-models first.", file=sys.stderr)
        sys.exit(1)
    best_models = read_json(best_models_path)

    bc_model_id = best_models["best_BC"]["model_id"]
    df_model_id = best_models["best_DF"]["model_id"]
    print_step(f"Models: BC={bc_model_id}, DF={df_model_id}")

    bc_exp_dir = args.experiment_dir / bc_model_id
    df_exp_dir = args.experiment_dir / df_model_id

    # ── Load data ─────────────────────────────────────────────────────────────
    print_step("Loading modeling data...")
    feature_records, bag_records = load_modeling_data(args.processed_dir)
    print_step(f"Loaded {len(feature_records)} decks (features), {len(bag_records)} decks (bags)")

    print_step("Loading card name mapping...")
    card_names = load_card_names(args.processed_dir)
    print_step(f"Loaded {len(card_names)} card name mappings")

    print_step(f"Loading DF OOF predictions from {df_exp_dir}...")
    oof_preds_df = load_oof_predictions(df_exp_dir)
    print_step(f"DF OOF: {len(oof_preds_df)} entries")

    print_step(f"Loading BC OOF predictions from {bc_exp_dir}...")
    oof_preds_bc = load_oof_predictions(bc_exp_dir)
    print_step(f"BC OOF: {len(oof_preds_bc)} entries")

    # ── DF interpretation ─────────────────────────────────────────────────────
    print_step("=== Starting DF interpretation ===")
    df_hyperparams_path = df_exp_dir / "best_hyperparams_per_fold.json"
    df_results = interpret_df_model(
        feature_records,
        oof_preds_df,
        df_hyperparams_path,
        random_state=RANDOM_STATE,
        n_pi_repeats=args.n_pi_repeats,
    )

    # ── BC interpretation ─────────────────────────────────────────────────────
    print_step("=== Starting BC interpretation ===")
    bc_results = interpret_bc_model(
        bag_records,
        oof_preds_bc,
        card_names,
    )

    # ── Save intermediate artefacts ───────────────────────────────────────────
    print_step("Saving intermediate artefacts...")
    PHASE_J_DIR.mkdir(parents=True, exist_ok=True)

    write_json(
        PHASE_J_DIR / "final_model_params.json",
        jsonable({
            "df_gradient_boosting": df_results["modal_params"],
            "bc_gradient_boosting": MODAL_PARAMS,
            "note": "Modal hyperparams from 15 outer folds (Phase H). Used only for interpretation — generalisation metrics come from Phase E nested CV.",
        }),
    )
    write_json(
        PHASE_J_DIR / "df_permutation_importance.json",
        jsonable(df_results["permutation_importance"]),
    )
    write_json(
        PHASE_J_DIR / "bc_card_lift_per_class.json",
        jsonable(bc_results["top_cards_by_class"]),
    )
    write_json(
        PHASE_J_DIR / "df_divergence_features.json",
        jsonable(df_results["divergence_features"]),
    )
    write_json(
        PHASE_J_DIR / "bc_divergence_cards.json",
        jsonable(bc_results["divergence_analysis"]),
    )

    # ── Render report ─────────────────────────────────────────────────────────
    print_step("Rendering report...")
    report_path = args.docs_dir / REPORT_FILENAME
    render_report(df_results, bc_results, report_path)

    print_step("=== Phase J complete ===")
    print_step(f"Report: {report_path}")


if __name__ == "__main__":
    main()
