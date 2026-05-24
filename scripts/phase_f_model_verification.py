#!/usr/bin/env python3
"""Phase F — Model verification: completeness, GroupKFold robustness, statistical tests.

Usage
-----
# Run with whatever models are currently available (partial Phase E is OK):
    uv run phase-f-model-verification

# Require ALL 12 expected models to be complete before running (use after Phase E is done):
    uv run phase-f-model-verification --all

# Override minimum folds required to consider a model "complete":
    uv run phase-f-model-verification --min-folds 5

Design
------
F.1  Completeness check
     - Discovers models by scanning experiments/<rep>_<algo>/ directories.
     - Without --all: operates on every model that meets --min-folds threshold;
       warns about missing or incomplete models.
     - With --all: aborts if any model in A_union × {df, bc} is absent or
       has fewer than 15/15 outer folds.

F.2  GroupKFold by commander signature
     - Builds a GroupKFold(n_splits=5) split by commander_oracle_uids.
     - Uses the most-frequent best hyperparams from Phase E (no new grid search).
     - Reports macro-F1 and the gap vs. stratified nested CV mean.
     - Works on models available at run time; skips missing ones.

F.3  Statistical tests
     - Friedman (all available models) + Nemenyi post-hoc.
     - Wilcoxon signed-rank for all pairs of available models.
     - Identical methodology to Phase E; re-run here on the final set.

Outputs
-------
- documents/reports/results/phase_f_model_verification.md
- documents/reports/results/phase_f_statistical_tests.md
- experiments/model_verification/group_kfold_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.stats import friedmanchisquare, wilcoxon
from sklearn.model_selection import GroupKFold
from sklearn.metrics import f1_score

try:
    from preprocessing import (  # type: ignore
        BagOfCardsPreprocessor,
        DeckFeaturePreprocessor,
        iter_jsonl,
        target_vector,
    )
except ImportError:
    from scripts.preprocessing import (  # type: ignore
        BagOfCardsPreprocessor,
        DeckFeaturePreprocessor,
        iter_jsonl,
        target_vector,
    )

try:
    from phase_e_nested_cv import (  # type: ignore
        SparseToDenseTransformer,
        jsonable,
        pipeline_for,
    )
except ImportError:
    from scripts.phase_e_nested_cv import (  # type: ignore
        SparseToDenseTransformer,
        jsonable,
        pipeline_for,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
DEFAULT_SPOT_CHECK_SUMMARY = Path("experiments/spot_check/summary.json")

REQUIRED_FILES = [
    "metrics_per_fold.json",
    "best_hyperparams_per_fold.json",
    "predictions_per_fold.jsonl",
]
# Optional files — their absence generates a warning but does not exclude the model
OPTIONAL_FILES = [
    "cv_results_per_fold.jsonl",
    "checkpoint_state.json",
]
EXPECTED_OUTER_FOLDS = 15
LABELS = [2, 3, 4]

REPORT_VERIFICATION = "phase_f_model_verification.md"
REPORT_STATS = "phase_f_statistical_tests.md"
GROUP_KFOLD_RESULTS = "group_kfold_results.json"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def discover_models(
    experiment_dir: Path,
    spot_check_summary: Path,
    require_all: bool,
    min_folds: int,
) -> Tuple[List[Dict], List[str]]:
    """Return (complete_models, warnings).

    Each element of complete_models is a dict with:
        model_id, algorithm, representation, n_folds, metrics, hyperparams, predictions_path
    """
    # Build expected model list from spot-check summary
    expected: List[str] = []
    if spot_check_summary.exists():
        summary = read_json(spot_check_summary)
        algos = summary.get("selection", {}).get("union", [])
        for rep in ("df", "bc"):
            for algo in algos:
                expected.append(f"{rep}_{algo}")
    else:
        # Fall back: scan directories
        for d in sorted(experiment_dir.iterdir()):
            if d.is_dir() and (d / "metrics_per_fold.json").exists():
                name = d.name
                parts = name.split("_", 1)
                if len(parts) == 2 and parts[0] in ("df", "bc"):
                    expected.append(name)

    warnings: List[str] = []
    complete: List[Dict] = []

    for model_id in sorted(set(expected)):
        model_dir = experiment_dir / model_id
        issues = []

        # Check directory and required files
        if not model_dir.exists():
            issues.append(f"directory not found: {model_dir}")
        else:
            for fname in REQUIRED_FILES:
                if not (model_dir / fname).exists():
                    issues.append(f"missing required file: {fname}")
            for fname in OPTIONAL_FILES:
                if not (model_dir / fname).exists():
                    warnings.append(f"[OPTIONAL MISSING] {model_id}: {fname} not found")

        if issues:
            msg = f"[INCOMPLETE] {model_id}: " + "; ".join(issues)
            warnings.append(msg)
            if require_all:
                print(f"ERROR — {msg}", file=sys.stderr)
            continue

        # Check fold count
        metrics = read_json(model_dir / "metrics_per_fold.json")
        folds_list = metrics.get("folds", [])
        n_folds = len(folds_list)

        if n_folds < min_folds:
            msg = f"[INCOMPLETE] {model_id}: only {n_folds}/{EXPECTED_OUTER_FOLDS} folds complete"
            warnings.append(msg)
            if require_all:
                print(f"ERROR — {msg}", file=sys.stderr)
            continue

        if n_folds < EXPECTED_OUTER_FOLDS:
            warnings.append(
                f"[PARTIAL] {model_id}: {n_folds}/{EXPECTED_OUTER_FOLDS} folds — "
                "included in analysis but statistics may be less reliable"
            )

        parts = model_id.split("_", 1)
        hyperparams = read_json(model_dir / "best_hyperparams_per_fold.json")

        complete.append(
            {
                "model_id": model_id,
                "representation": parts[0].upper(),
                "algorithm": parts[1],
                "n_folds": n_folds,
                "metrics": metrics,
                "hyperparams": hyperparams,
                "predictions_path": model_dir / "predictions_per_fold.jsonl",
            }
        )

    blocking_warnings = [w for w in warnings if w.startswith("[INCOMPLETE]")]
    if require_all and blocking_warnings:
        sys.exit(
            "\nAborted — use without --all to run with partial results, "
            "or wait for Phase E to complete.\n"
        )

    return complete, warnings


# ---------------------------------------------------------------------------
# F.1 — Completeness summary
# ---------------------------------------------------------------------------

def check_consistency(models: List[Dict], experiment_dir: Path) -> List[str]:
    """Cross-check that all models share the same fold IDs and label set."""
    issues: List[str] = []
    fold_id_sets: Dict[str, List[str]] = {}
    for m in models:
        fold_ids = [f["fold_id"] for f in m["metrics"]["folds"]]
        fold_id_sets[m["model_id"]] = fold_ids

    if not fold_id_sets:
        return issues

    reference_id = next(iter(fold_id_sets))
    reference_folds = fold_id_sets[reference_id]

    for model_id, fold_ids in fold_id_sets.items():
        if fold_ids != reference_folds:
            issues.append(
                f"{model_id}: fold IDs differ from {reference_id} — "
                f"may be from a different run"
            )

    return issues


# ---------------------------------------------------------------------------
# F.2 — GroupKFold by commander
# ---------------------------------------------------------------------------

def commander_signature(oracle_uids: Any) -> str:
    """Convert commander_oracle_uids list to a stable string group key."""
    if not oracle_uids:
        return "__unknown__"
    if isinstance(oracle_uids, list):
        return "|".join(sorted(str(u) for u in oracle_uids))
    return str(oracle_uids)


def most_common_hyperparams(hyperparams_per_fold: List[Dict]) -> Dict:
    """Return the hyperparameter config that appeared most often across folds."""
    if not hyperparams_per_fold:
        return {}
    # Serialise each config to a stable JSON string for counting
    counts: Counter = Counter(
        json.dumps(h, sort_keys=True) for h in hyperparams_per_fold
    )
    best_json, _ = counts.most_common(1)[0]
    return json.loads(best_json)


def run_group_kfold(
    model: Dict,
    processed_dir: Path,
    n_splits: int = 5,
    quiet: bool = False,
) -> Dict:
    """Run GroupKFold(n_splits) by commander and return results dict."""
    model_id = model["model_id"]
    rep = model["representation"]  # "DF" or "BC"
    algo = model["algorithm"]

    if not quiet:
        print(f"  [F.2] GroupKFold — {model_id} ...", file=sys.stderr)

    # Load dataset
    df_path = processed_dir / "deck_features.jsonl"
    bc_path = processed_dir / "bag_of_cards.jsonl"

    records = list(iter_jsonl(df_path))
    y = target_vector(records)

    # Build group array from commander_oracle_uids
    groups = np.array(
        [commander_signature(r.get("commander_oracle_uids")) for r in records]
    )

    # Choose best hyperparams (most common across folds)
    hp_list = model["hyperparams"]
    if isinstance(hp_list, list):
        chosen_hp = most_common_hyperparams(hp_list)
    elif isinstance(hp_list, dict):
        # May be keyed by fold_id
        chosen_hp = most_common_hyperparams(list(hp_list.values()))
    else:
        chosen_hp = {}

    # Build preprocessing + estimator pipeline (same as Phase E)
    # Extract scalar hyperparams that pipeline_for needs at construction time;
    # the rest (clf__*) are set via pipeline.set_params() after construction.
    try:
        pipeline = pipeline_for(
            algo,
            rep,
            bc_min_df=10,
            use_tfidf=False,
            random_state=42,
            n_jobs=1,
        )
        # Apply chosen hyperparameters (prefix clf__ or prep__ as stored)
        clf_params = {k: v for k, v in chosen_hp.items() if k.startswith("clf__")}
        if clf_params:
            pipeline.set_params(**clf_params)
    except Exception as exc:
        return {
            "model_id": model_id,
            "status": "error",
            "error": str(exc),
            "macro_f1_group_mean": None,
            "macro_f1_group_std": None,
            "gap_vs_stratified": None,
        }

    # Raw records — the pipeline_for pipelines include the preprocessor step,
    # so we pass raw records directly and let the pipeline handle the transform.
    if rep == "BC":
        bc_records = list(iter_jsonl(bc_path))
        X_raw = bc_records
    else:
        X_raw = records  # list of dicts

    gkf = GroupKFold(n_splits=n_splits)
    fold_f1s: List[float] = []
    fold_ids_out: List[str] = []

    for fold_idx, (train_idx, test_idx) in enumerate(gkf.split(X_raw, y, groups=groups)):
        t0 = time.monotonic()
        X_train_raw = [X_raw[i] for i in train_idx]
        X_test_raw = [X_raw[i] for i in test_idx]
        y_train = y[train_idx]
        y_test = y[test_idx]

        # Clone pipeline so each fold starts fresh (fit on training partition only)
        from sklearn.base import clone as sklearn_clone
        fold_pipeline = sklearn_clone(pipeline)

        try:
            fold_pipeline.fit(X_train_raw, y_train)
            y_pred = fold_pipeline.predict(X_test_raw)
            f1 = f1_score(y_test, y_pred, average="macro", labels=LABELS, zero_division=0)
        except Exception as exc:
            if not quiet:
                print(f"    fold {fold_idx+1} error: {exc}", file=sys.stderr)
            f1 = float("nan")

        fold_f1s.append(f1)
        fold_ids_out.append(f"g{fold_idx+1}")
        elapsed = time.monotonic() - t0
        if not quiet:
            print(
                f"    fold {fold_idx+1}/{n_splits} — macro-F1={f1:.4f} ({elapsed:.1f}s)",
                file=sys.stderr,
            )

    valid_f1s = [v for v in fold_f1s if math.isfinite(v)]
    macro_f1_mean = float(np.mean(valid_f1s)) if valid_f1s else None
    macro_f1_std = float(np.std(valid_f1s, ddof=1)) if len(valid_f1s) > 1 else None

    # Gap vs stratified nested CV mean
    stratified_mean = model["metrics"].get("aggregate", {}).get("macro_f1_mean")
    gap = (
        round(stratified_mean - macro_f1_mean, 4)
        if (stratified_mean is not None and macro_f1_mean is not None)
        else None
    )

    return {
        "model_id": model_id,
        "status": "ok",
        "chosen_hyperparams": chosen_hp,
        "n_splits": n_splits,
        "fold_f1s": fold_f1s,
        "fold_ids": fold_ids_out,
        "macro_f1_group_mean": macro_f1_mean,
        "macro_f1_group_std": macro_f1_std,
        "macro_f1_stratified_mean": stratified_mean,
        "gap_vs_stratified": gap,
    }


# ---------------------------------------------------------------------------
# F.3 — Statistical tests
# ---------------------------------------------------------------------------

def load_fold_scores(models: List[Dict]) -> Dict[str, List[float]]:
    """Return {model_id: [macro_f1_fold0, ..., macro_f1_foldN]} from metrics."""
    scores: Dict[str, List[float]] = {}
    for m in models:
        fold_f1s = [f["macro_f1"] for f in m["metrics"]["folds"]]
        scores[m["model_id"]] = fold_f1s
    return scores


def run_statistical_tests(scores: Dict[str, List[float]]) -> Dict:
    """Friedman + Nemenyi + Wilcoxon signed-rank."""
    model_ids = sorted(scores.keys())
    n_models = len(model_ids)

    if n_models < 2:
        return {"error": "Need at least 2 models for statistical tests"}

    # Align fold counts to minimum
    min_folds = min(len(scores[m]) for m in model_ids)
    score_matrix = np.array([scores[m][:min_folds] for m in model_ids])  # (n_models, n_folds)

    # --- Friedman ---
    friedman_stat, friedman_p = friedmanchisquare(*score_matrix)

    # --- Nemenyi (CD) ---
    # CD = q_alpha * sqrt(k(k+1) / (6N))  where k=n_models, N=n_folds
    # q_alpha for alpha=0.05 from Studentized range / sqrt(2)
    k = n_models
    N = min_folds
    try:
        from scipy.stats import studentized_range  # type: ignore
        q_alpha = studentized_range.ppf(0.95, k, df=1e9) / math.sqrt(2)
    except Exception:
        # Fallback table values for common k
        q_table = {2: 1.960, 3: 2.344, 4: 2.569, 5: 2.728, 6: 2.850,
                   7: 2.949, 8: 3.031, 9: 3.102, 10: 3.164,
                   11: 3.219, 12: 3.268, 13: 3.313, 14: 3.354, 15: 3.391}
        q_alpha = q_table.get(k, 3.5)
    cd = q_alpha * math.sqrt(k * (k + 1) / (6 * N))

    # --- Ranks ---
    # Higher F1 = better = lower rank (rank 1 = best)
    ranks = np.zeros_like(score_matrix)
    for col in range(N):
        col_scores = score_matrix[:, col]
        col_ranks = rankdata_desc(col_scores)
        ranks[:, col] = col_ranks
    mean_ranks = ranks.mean(axis=1)

    rank_table = sorted(
        zip(model_ids, mean_ranks.tolist()), key=lambda x: x[1]
    )

    # --- Nemenyi pairwise ---
    nemenyi_pairs = []
    for i in range(n_models):
        for j in range(i + 1, n_models):
            diff = abs(mean_ranks[i] - mean_ranks[j])
            nemenyi_pairs.append(
                {
                    "model_a": model_ids[i],
                    "model_b": model_ids[j],
                    "rank_diff": round(diff, 4),
                    "significant": bool(diff > cd),
                }
            )

    # --- Wilcoxon pairwise ---
    wilcoxon_pairs = []
    for i in range(n_models):
        for j in range(i + 1, n_models):
            a = score_matrix[i]
            b = score_matrix[j]
            try:
                stat, p = wilcoxon(a, b, alternative="two-sided", zero_method="wilcox")
                wilcoxon_pairs.append(
                    {
                        "model_a": model_ids[i],
                        "model_b": model_ids[j],
                        "statistic": round(float(stat), 4),
                        "p_value": float(p),
                        "significant_05": bool(p < 0.05),
                    }
                )
            except Exception:
                wilcoxon_pairs.append(
                    {
                        "model_a": model_ids[i],
                        "model_b": model_ids[j],
                        "statistic": None,
                        "p_value": None,
                        "significant_05": None,
                    }
                )

    return {
        "n_models": n_models,
        "n_folds_used": min_folds,
        "friedman": {
            "statistic": round(float(friedman_stat), 4),
            "p_value": float(friedman_p),
        },
        "nemenyi": {
            "critical_difference": round(cd, 4),
            "alpha": 0.05,
            "pairs": nemenyi_pairs,
        },
        "ranks": [{"model_id": mid, "mean_rank": round(r, 4)} for mid, r in rank_table],
        "wilcoxon": wilcoxon_pairs,
    }


def rankdata_desc(scores: np.ndarray) -> np.ndarray:
    """Rank scores descending (highest score = rank 1)."""
    order = np.argsort(-scores)  # descending
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    # Handle ties: average rank
    unique_scores = np.unique(scores)[::-1]
    for val in unique_scores:
        mask = scores == val
        if mask.sum() > 1:
            ranks[mask] = ranks[mask].mean()
    return ranks


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def render_verification_report(
    models: List[Dict],
    warnings: List[str],
    consistency_issues: List[str],
    group_kfold_results: List[Dict],
    require_all: bool,
) -> str:
    lines: List[str] = []
    lines.append("# Verificação de Modelos — Fase F\n")

    # --- F.1 ---
    lines.append("## F.1 Completude\n")
    lines.append(f"Modelos incluídos na análise: **{len(models)}**\n")
    lines.append(f"Flag `--all`: {'sim' if require_all else 'não'} — "
                 f"{'todos os modelos exigidos' if require_all else 'modelos parciais aceitos'}\n")

    lines.append("\n| Modelo | Representação | Algoritmo | Folds | Macro-F1 média | Macro-F1 dp |")
    lines.append("|---|---|---|---:|---:|---:|")
    for m in sorted(models, key=lambda x: x["model_id"]):
        agg = m["metrics"].get("aggregate", {})
        f1m = agg.get("macro_f1_mean")
        f1s = agg.get("macro_f1_std")
        f1m_str = f"{f1m:.4f}" if f1m is not None else "—"
        f1s_str = f"{f1s:.4f}" if f1s is not None else "—"
        lines.append(
            f"| `{m['model_id']}` | {m['representation']} | {m['algorithm']} "
            f"| {m['n_folds']}/{EXPECTED_OUTER_FOLDS} | {f1m_str} | {f1s_str} |"
        )

    if warnings:
        lines.append("\n### Avisos\n")
        for w in warnings:
            lines.append(f"- {w}")

    if consistency_issues:
        lines.append("\n### Problemas de consistência\n")
        for issue in consistency_issues:
            lines.append(f"- ⚠️ {issue}")
    else:
        lines.append("\n✅ Todos os modelos compartilham os mesmos fold IDs.\n")

    # --- F.2 ---
    lines.append("\n## F.2 GroupKFold por Comandante\n")
    lines.append(
        "Avalia cada modelo com `GroupKFold(n_splits=5)` agrupando decks pelo mesmo "
        "comandante (ou par de comandantes). Um gap grande indica que o modelo depende "
        "de padrões associados a comandantes específicos já vistos no treino.\n"
    )

    if group_kfold_results:
        lines.append(
            "| Modelo | Macro-F1 grupo (média) | Macro-F1 grupo (dp) "
            "| Macro-F1 estratificado | Gap (Estratif. − Grupo) |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        for r in sorted(group_kfold_results, key=lambda x: x["model_id"]):
            if r.get("status") != "ok":
                lines.append(
                    f"| `{r['model_id']}` | erro | — | — | — |"
                )
                continue
            gm = r.get("macro_f1_group_mean")
            gs = r.get("macro_f1_group_std")
            sm = r.get("macro_f1_stratified_mean")
            gap = r.get("gap_vs_stratified")
            gm_str  = f"{gm:.4f}"  if gm  is not None else "—"
            gs_str  = f"{gs:.4f}"  if gs  is not None else "—"
            sm_str  = f"{sm:.4f}"  if sm  is not None else "—"
            gap_str = f"{gap:+.4f}" if gap is not None else "—"
            lines.append(
                f"| `{r['model_id']}` "
                f"| {gm_str} "
                f"| {gs_str} "
                f"| {sm_str} "
                f"| {gap_str} |"
            )
    else:
        lines.append("_GroupKFold não executado (use `--group-kfold` para ativar)._\n")

    # --- files ---
    lines.append("\n## Artefatos\n")
    lines.append("- `experiments/model_verification/group_kfold_results.json`")
    lines.append("- `documents/reports/results/phase_f_model_verification.md`")
    lines.append("- `documents/reports/results/phase_f_statistical_tests.md`")

    return "\n".join(lines) + "\n"


def render_stats_report(stats: Dict, models: List[Dict]) -> str:
    lines: List[str] = []
    lines.append("# Testes Estatísticos — Fase F\n")

    if "error" in stats:
        lines.append(f"⚠️ {stats['error']}\n")
        return "\n".join(lines) + "\n"

    lines.append(f"Modelos incluídos: **{stats['n_models']}** · "
                 f"Folds usados por modelo: **{stats['n_folds_used']}**\n")

    fr = stats["friedman"]
    lines.append(f"**Friedman**: statistic={fr['statistic']}, p={fr['p_value']:.6f}\n")

    nem = stats["nemenyi"]
    lines.append(f"**Nemenyi**: diferença crítica={nem['critical_difference']:.4f} para alpha=0.05\n")

    lines.append("\n## Ranks Médios\n")
    lines.append("| Modelo | Rank médio |")
    lines.append("|---|---:|")
    for r in stats["ranks"]:
        lines.append(f"| `{r['model_id']}` | {r['mean_rank']:.4f} |")

    sig_pairs = [p for p in nem["pairs"] if p["significant"]]
    lines.append(f"\n## Nemenyi — pares significativos (CD={nem['critical_difference']:.4f})\n")
    if sig_pairs:
        lines.append("| Modelo A | Modelo B | Diferença de rank |")
        lines.append("|---|---|---:|")
        for p in sorted(sig_pairs, key=lambda x: -x["rank_diff"]):
            lines.append(
                f"| `{p['model_a']}` | `{p['model_b']}` | {p['rank_diff']:.4f} |"
            )
    else:
        lines.append("_Nenhum par com diferença significativa._\n")

    lines.append("\n## Wilcoxon Pareado\n")
    lines.append("| Modelo A | Modelo B | Statistic | p-value | Significativo (α=0.05) |")
    lines.append("|---|---|---:|---:|:---:|")
    for p in stats["wilcoxon"]:
        stat = f"{p['statistic']:.4f}" if p["statistic"] is not None else "—"
        pval = f"{p['p_value']:.6f}" if p["p_value"] is not None else "—"
        sig = "✓" if p["significant_05"] else ""
        lines.append(
            f"| `{p['model_a']}` | `{p['model_b']}` | {stat} | {pval} | {sig} |"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase F — Model verification, GroupKFold, and statistical tests.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--all",
        dest="require_all",
        action="store_true",
        default=False,
        help=(
            "Require ALL models in A_union × {df, bc} to have 15/15 folds. "
            "Abort if any model is missing or incomplete. "
            "Use this flag after Phase E is fully done."
        ),
    )
    parser.add_argument(
        "--min-folds",
        type=int,
        default=5,
        metavar="N",
        help="Minimum number of outer folds a model must have to be included.",
    )
    parser.add_argument(
        "--group-kfold",
        action="store_true",
        default=False,
        help=(
            "Run the GroupKFold robustness check (F.2). Slower — re-trains each "
            "model with the most common best hyperparams from Phase E."
        ),
    )
    parser.add_argument(
        "--group-kfold-splits",
        type=int,
        default=5,
        metavar="K",
        help="Number of GroupKFold splits for F.2.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        metavar="DIR",
    )
    parser.add_argument(
        "--experiment-dir",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR,
        metavar="DIR",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        metavar="DIR",
    )
    parser.add_argument(
        "--spot-check-summary",
        type=Path,
        default=DEFAULT_SPOT_CHECK_SUMMARY,
        metavar="PATH",
    )
    parser.add_argument("--quiet", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr, flush=True)

    log("[Phase F] Iniciando verificação de modelos...")

    # ------------------------------------------------------------------
    # F.1 — Completeness
    # ------------------------------------------------------------------
    log("[Phase F] F.1 — Verificando completude dos modelos...")
    models, warnings = discover_models(
        experiment_dir=args.experiment_dir,
        spot_check_summary=args.spot_check_summary,
        require_all=args.require_all,
        min_folds=args.min_folds,
    )

    if not models:
        sys.exit("[Phase F] Nenhum modelo disponível. Rode a Fase E primeiro.")

    log(f"[Phase F] {len(models)} modelo(s) disponível(is): "
        + ", ".join(m["model_id"] for m in models))

    for w in warnings:
        log(f"  AVISO: {w}")

    consistency_issues = check_consistency(models, args.experiment_dir)
    for issue in consistency_issues:
        log(f"  CONSISTÊNCIA: {issue}")

    # ------------------------------------------------------------------
    # F.2 — GroupKFold (optional)
    # ------------------------------------------------------------------
    group_kfold_results: List[Dict] = []
    if args.group_kfold:
        log("[Phase F] F.2 — GroupKFold por comandante...")
        for m in models:
            result = run_group_kfold(
                model=m,
                processed_dir=args.processed_dir,
                n_splits=args.group_kfold_splits,
                quiet=args.quiet,
            )
            group_kfold_results.append(result)
            if result.get("status") == "ok":
                gap = result.get("gap_vs_stratified")
                log(
                    f"  {m['model_id']}: group-F1={result['macro_f1_group_mean']:.4f} "
                    f"| stratified={result['macro_f1_stratified_mean']:.4f} "
                    f"| gap={gap:+.4f}"
                )

        gkf_path = args.experiment_dir / "model_verification" / GROUP_KFOLD_RESULTS
        write_json(gkf_path, group_kfold_results)
        log(f"[Phase F] GroupKFold results → {gkf_path}")
    else:
        log("[Phase F] F.2 — GroupKFold desativado (use --group-kfold para ativar)")

    # ------------------------------------------------------------------
    # F.3 — Statistical tests
    # ------------------------------------------------------------------
    log("[Phase F] F.3 — Testes estatísticos...")
    fold_scores = load_fold_scores(models)
    stats = run_statistical_tests(fold_scores)

    friedman_p = stats.get("friedman", {}).get("p_value", 1.0)
    log(
        f"  Friedman: statistic={stats.get('friedman', {}).get('statistic', '?')}, "
        f"p={friedman_p:.6f}"
    )
    if "nemenyi" in stats:
        log(f"  Nemenyi CD={stats['nemenyi']['critical_difference']:.4f}")
        sig_count = sum(1 for p in stats["nemenyi"]["pairs"] if p["significant"])
        log(f"  Pares Nemenyi significativos: {sig_count}")

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    verification_report = render_verification_report(
        models=models,
        warnings=warnings,
        consistency_issues=consistency_issues,
        group_kfold_results=group_kfold_results,
        require_all=args.require_all,
    )
    stats_report = render_stats_report(stats, models)

    vpath = args.docs_dir / REPORT_VERIFICATION
    spath = args.docs_dir / REPORT_STATS
    write_text(vpath, verification_report)
    write_text(spath, stats_report)

    log(f"[Phase F] Relatório de verificação → {vpath}")
    log(f"[Phase F] Relatório de testes estatísticos → {spath}")
    log("[Phase F] Concluído.")


if __name__ == "__main__":
    main()
