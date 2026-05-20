#!/usr/bin/env python3
"""Phase D — spot-check candidate algorithms on DF and BC representations.

Re-designed (2026-05-19) per professor feedback:
- Pool restricted to 7 algorithms viable in both BC and DF (SVC RBF/Poly removed).
- N=5 repetitions per (algorithm, representation, bc_min_df) using seeds {1..5},
  reporting mean and standard deviation of macro-F1.
- Top-5 finalists picked independently per representation; the union goes to Phase E.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from sklearn.base import BaseEstimator
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

try:
    from preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector  # type: ignore


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
REPORT_FILENAME = "phase_d_spot_checking.md"
BOXPLOT_DF_RELATIVE_PATH = Path("figures/spot_check/macro_f1_boxplot_df.png")
BOXPLOT_BC_RELATIVE_PATH = Path("figures/spot_check/macro_f1_boxplot_bc.png")
DF_BOX_COLOR = "#DD8452"
BC_BOX_COLOR = "#4C72B0"
DEFAULT_EXPERIMENT_DIR = Path("experiments/spot_check")

# Phase D pool — restricted to algorithms that run in both BC and DF.
ALGORITHMS = (
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "naive_bayes",
    "logistic_regression",
    "linear_svc",
    "knn",
)

REPRESENTATIONS = ("DF", "BC")
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
TOPK_PER_REPRESENTATION = 5
METRIC_KEYS = ("macro_f1", "accuracy", "precision_macro", "recall_macro")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def load_modeling_data(processed_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ids_path = processed_dir / "modeling_snapshot_ids.json"
    if not ids_path.exists():
        raise FileNotFoundError(f"Missing {ids_path}; run phase-c-filter-dataset first.")
    snapshot_ids = load_json(ids_path)
    id_set = set(snapshot_ids)

    feature_by_id = {
        record["snapshot_id"]: record
        for record in iter_jsonl(processed_dir / "deck_features.jsonl")
        if record.get("snapshot_id") in id_set
    }
    bag_by_id = {
        record["snapshot_id"]: record
        for record in iter_jsonl(processed_dir / "bag_of_cards.jsonl")
        if record.get("snapshot_id") in id_set
    }

    missing_features = [sid for sid in snapshot_ids if sid not in feature_by_id]
    missing_bags = [sid for sid in snapshot_ids if sid not in bag_by_id]
    if missing_features or missing_bags:
        raise ValueError(
            f"Modeling ids are not aligned: missing_features={len(missing_features)}, missing_bags={len(missing_bags)}"
        )

    features = [feature_by_id[sid] for sid in snapshot_ids]
    bags = [bag_by_id[sid] for sid in snapshot_ids]
    return features, bags


def estimator_for(name: str, representation: str, random_state: int, n_jobs: int) -> BaseEstimator:
    if name == "decision_tree":
        return DecisionTreeClassifier(random_state=random_state)
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=100, random_state=random_state, n_jobs=n_jobs)
    if name == "gradient_boosting":
        return HistGradientBoostingClassifier(random_state=random_state)
    if name == "naive_bayes":
        return MultinomialNB() if representation == "BC" else GaussianNB()
    if name == "logistic_regression":
        solver = "saga" if representation == "BC" else "lbfgs"
        return LogisticRegression(max_iter=1000, solver=solver, random_state=random_state)
    if name == "linear_svc":
        return LinearSVC(random_state=random_state, max_iter=5000)
    if name == "knn":
        return KNeighborsClassifier()
    raise ValueError(f"Unknown algorithm: {name}")


def needs_df_scaling(name: str) -> bool:
    return name in {"logistic_regression", "linear_svc", "knn"}


def bc_uses_tfidf(name: str) -> bool:
    # Phase D keeps TF-IDF disabled so spot-checking isolates the effect of
    # algorithm choice and BC vocabulary pruning.
    return False


def metric_record(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def combo_label(algorithm: str, representation: str, bc_min_df: Optional[int]) -> str:
    parts = [
        f"representation={representation}",
        f"algorithm={algorithm}",
        f"use_tfidf={representation == 'BC' and bc_uses_tfidf(algorithm)}",
    ]
    if bc_min_df is not None:
        parts.append(f"bc_min_df={bc_min_df}")
    if representation == "DF":
        parts.append(f"scale={needs_df_scaling(algorithm)}")
    if representation == "BC" and algorithm == "gradient_boosting":
        parts.append("dense_conversion=True")
    return " | ".join(parts)


def print_progress(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def run_single_seed(
    *,
    algorithm: str,
    representation: str,
    bc_min_df: Optional[int],
    features: Sequence[Mapping[str, Any]],
    bags: Sequence[Mapping[str, Any]],
    y: np.ndarray,
    test_size: float,
    seed: int,
    n_jobs: int,
) -> Dict[str, Any]:
    started = time.monotonic()
    result: Dict[str, Any] = {
        "algorithm": algorithm,
        "representation": representation,
        "bc_min_df": bc_min_df,
        "use_tfidf": bool(representation == "BC" and bc_uses_tfidf(algorithm)),
        "seed": int(seed),
        "status": "ok",
        "error": None,
        "fit_seconds": None,
        "predict_seconds": None,
    }

    try:
        indices = np.arange(len(y))
        train_idx, test_idx = train_test_split(
            indices,
            test_size=test_size,
            stratify=y,
            random_state=seed,
        )
        features_train = [features[i] for i in train_idx]
        features_test = [features[i] for i in test_idx]
        bags_train = [bags[i] for i in train_idx]
        bags_test = [bags[i] for i in test_idx]
        y_train = y[train_idx]
        y_test = y[test_idx]

        if representation == "DF":
            transformer = DeckFeaturePreprocessor(scale=needs_df_scaling(algorithm))
            x_train = transformer.fit_transform(features_train)
            x_test = transformer.transform(features_test)
        else:
            assert bc_min_df is not None
            transformer = BagOfCardsPreprocessor(min_df=bc_min_df, use_tfidf=bc_uses_tfidf(algorithm))
            x_train = transformer.fit_transform(bags_train)
            x_test = transformer.transform(bags_test)
            if algorithm == "gradient_boosting":
                x_train = x_train.toarray()
                x_test = x_test.toarray()

        estimator = estimator_for(algorithm, representation, seed, n_jobs)
        fit_started = time.monotonic()
        estimator.fit(x_train, y_train)
        result["fit_seconds"] = round(time.monotonic() - fit_started, 3)

        predict_started = time.monotonic()
        y_pred = estimator.predict(x_test)
        result["predict_seconds"] = round(time.monotonic() - predict_started, 3)
        result.update(metric_record(y_test, y_pred))
        result["n_train"] = int(len(y_train))
        result["n_test"] = int(len(y_test))
        result["n_features"] = int(x_train.shape[1])
    except Exception as exc:
        result.update({
            "status": "error",
            "error": str(exc),
        })
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def aggregate_combination(per_seed_results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    successes = [row for row in per_seed_results if row.get("status") == "ok"]
    summary: Dict[str, Any] = {
        "n_seeds_total": len(per_seed_results),
        "n_seeds_ok": len(successes),
        "n_seeds_error": len(per_seed_results) - len(successes),
        "seeds_used": [int(row["seed"]) for row in per_seed_results],
        "seeds_ok": [int(row["seed"]) for row in successes],
        "errors": [row for row in per_seed_results if row.get("status") != "ok"],
    }
    if not successes:
        summary["status"] = "error"
        return summary
    summary["status"] = "ok"
    for key in METRIC_KEYS:
        values = np.asarray([float(row[key]) for row in successes], dtype=float)
        summary[f"{key}_mean"] = float(values.mean())
        summary[f"{key}_std"] = float(values.std(ddof=1)) if values.size > 1 else 0.0
        summary[f"{key}_values"] = [float(v) for v in values]
    fit_values = np.asarray([row.get("fit_seconds") or 0.0 for row in successes], dtype=float)
    summary["fit_seconds_mean"] = float(fit_values.mean())
    summary["n_features_first"] = int(successes[0].get("n_features", 0))
    summary["n_train"] = int(successes[0].get("n_train", 0))
    summary["n_test"] = int(successes[0].get("n_test", 0))
    return summary


def select_best_bc_min_df(combinations: Sequence[Mapping[str, Any]]) -> Optional[int]:
    by_value: Dict[int, List[float]] = defaultdict(list)
    for combo in combinations:
        if combo.get("representation") != "BC":
            continue
        if combo["aggregate"].get("status") != "ok":
            continue
        bc_min_df = combo.get("bc_min_df")
        if isinstance(bc_min_df, int):
            by_value[bc_min_df].append(float(combo["aggregate"]["macro_f1_mean"]))
    if not by_value:
        return None
    averages = {value: sum(scores) / len(scores) for value, scores in by_value.items() if scores}
    return max(averages, key=averages.get)


def ranking_for_representation(
    combinations: Sequence[Mapping[str, Any]],
    representation: str,
    *,
    bc_min_df_filter: Optional[int],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for combo in combinations:
        if combo.get("representation") != representation:
            continue
        if representation == "BC" and combo.get("bc_min_df") != bc_min_df_filter:
            continue
        aggregate = combo["aggregate"]
        ok = aggregate.get("status") == "ok"
        rows.append({
            "representation": representation,
            "algorithm": combo["algorithm"],
            "bc_min_df": combo.get("bc_min_df"),
            "macro_f1_mean": aggregate.get("macro_f1_mean") if ok else None,
            "macro_f1_std": aggregate.get("macro_f1_std") if ok else None,
            "accuracy_mean": aggregate.get("accuracy_mean") if ok else None,
            "accuracy_std": aggregate.get("accuracy_std") if ok else None,
            "precision_macro_mean": aggregate.get("precision_macro_mean") if ok else None,
            "recall_macro_mean": aggregate.get("recall_macro_mean") if ok else None,
            "n_seeds_ok": aggregate.get("n_seeds_ok", 0),
            "eligible": ok,
            "reason": "" if ok else "missing_successful_result",
        })
    rows.sort(key=lambda row: (row["eligible"], row["macro_f1_mean"] or -math.inf), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
        row["selected"] = bool(row["eligible"] and idx <= TOPK_PER_REPRESENTATION)
    return rows


def selected_algorithms(ranking: Sequence[Mapping[str, Any]]) -> List[str]:
    return [row["algorithm"] for row in ranking if row.get("selected")]


def format_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return ""


def collect_focused_macro_f1(
    combinations: Sequence[Mapping[str, Any]],
    best_bc_min_df: Optional[int],
) -> Tuple[Dict[str, List[float]], Dict[str, List[float]]]:
    """Return per-algorithm macro_f1 values for BC (at best_bc_min_df) and DF.

    Used by both the per-seed markdown table and the boxplot.
    """
    df_data: Dict[str, List[float]] = {}
    bc_data: Dict[str, List[float]] = {}
    for combo in combinations:
        aggregate = combo.get("aggregate") or {}
        if aggregate.get("status") != "ok":
            continue
        rep = combo.get("representation")
        algorithm = combo.get("algorithm")
        values = list(aggregate.get("macro_f1_values") or [])
        if not algorithm or not values:
            continue
        if rep == "DF":
            df_data[algorithm] = values
        elif rep == "BC" and combo.get("bc_min_df") == best_bc_min_df:
            bc_data[algorithm] = values
    return bc_data, df_data


def plot_macro_f1_boxplot(
    data: Mapping[str, Sequence[float]],
    *,
    figure_path: Path,
    representation: str,
    color: str,
    n_seeds: int,
    bc_min_df: Optional[int] = None,
) -> Optional[Path]:
    """Boxplot per algorithm for a SINGLE representation (BC or DF).

    `data` maps algorithm → list of per-seed macro-F1 values. Algorithms are
    sorted by descending mean so the strongest sits on the left. Each box gets
    the raw seed points overlaid as black dots so the reader can count "n_seeds
    dots". Returns the saved path or None when there's nothing to plot.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    algorithms = sorted(
        (alg for alg, values in data.items() if values),
        key=lambda alg: -float(np.mean(data[alg])),
    )
    if not algorithms:
        return None

    values_list: List[List[float]] = [list(data[alg]) for alg in algorithms]
    positions: List[int] = list(range(len(algorithms)))

    fig, ax = plt.subplots(figsize=(max(7.0, 1.2 * len(algorithms)), 5.0))
    ax.boxplot(
        values_list,
        positions=positions,
        widths=0.6,
        patch_artist=True,
        medianprops=dict(color="black", linewidth=1.6),
        whiskerprops=dict(color="black"),
        capprops=dict(color="black"),
        boxprops=dict(facecolor=color, alpha=0.75, edgecolor="black"),
        flierprops=dict(marker="o", markerfacecolor=color, markeredgecolor="black", markersize=4),
    )
    for pos, values in zip(positions, values_list):
        jitter = np.linspace(-0.1, 0.1, num=len(values))
        ax.scatter(
            np.full_like(jitter, pos) + jitter,
            values,
            color="black",
            s=14,
            zorder=3,
            alpha=0.75,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels(algorithms, rotation=15, ha="right")
    ax.set_ylabel("Macro-F1")
    title_suffix = (
        f" (bc_min_df={bc_min_df})"
        if representation == "BC" and bc_min_df is not None
        else ""
    )
    ax.set_title(f"Macro-F1 — {representation}{title_suffix} | {n_seeds} seeds")
    ax.grid(axis="y", alpha=0.3)

    flat = [v for values in values_list for v in values]
    if flat:
        y_min, y_max = min(flat), max(flat)
        margin = max(0.02, (y_max - y_min) * 0.1)
        ax.set_ylim(max(0.0, y_min - margin), min(1.0, y_max + margin))

    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return figure_path


def write_report(
    *,
    path: Path,
    combinations: Sequence[Mapping[str, Any]],
    rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    best_bc_min_df: Optional[int],
    args: argparse.Namespace,
) -> None:
    ok = [c for c in combinations if c["aggregate"].get("status") == "ok"]
    errors = [c for c in combinations if c["aggregate"].get("status") != "ok"]
    top_df = ", ".join(f"`{row['algorithm']}`" for row in rankings.get("DF", []) if row.get("selected"))
    top_bc = ", ".join(f"`{row['algorithm']}`" for row in rankings.get("BC", []) if row.get("selected"))
    union = sorted({row["algorithm"] for rows in rankings.values() for row in rows if row.get("selected")})

    lines: List[str] = [
        "# Spot-checking — Fase D",
        "",
        "## Objetivo",
        "",
        "Avaliar os 7 algoritmos candidatos viáveis em ambas as representações (BC e DF) com N=5 repetições, reportando média e desvio padrão da macro-F1. A saída define `A_DF` e `A_BC` (top-5 por representação) que alimentam a Fase E.",
        "",
        "## Configuração",
        "",
        f"- `processed_dir`: `{args.processed_dir}`",
        f"- `seeds`: `{', '.join(map(str, args.seeds))}` (hold-out estratificado 80/20 estratificado por `y1`)",
        f"- `test_size`: `{args.test_size}`",
        f"- `bc_min_df_values`: `{', '.join(map(str, args.bc_min_df_values))}`",
        f"- `best_bc_min_df`: `{best_bc_min_df}`",
        "- `use_tfidf`: `False` nesta etapa",
        f"- Combinações com sucesso: {len(ok)}",
        f"- Combinações com erro: {len(errors)}",
        "",
        "## Hiperparâmetros testados (defaults sklearn, com ajustes mínimos)",
        "",
        "| Algoritmo | DF | BC | Hiperparâmetros |",
        "|---|---|---|---|",
        "| Decision Tree | sim | sim | `DecisionTreeClassifier(random_state=seed)` |",
        "| Random Forest | sim | sim | `RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=-1)` |",
        "| Gradient Boosting | sim | sim | `HistGradientBoostingClassifier(random_state=seed)`; em BC há conversão controlada de sparse para dense |",
        "| Naive Bayes | sim | sim | DF: `GaussianNB()`; BC: `MultinomialNB()` |",
        "| Logistic Regression | sim | sim | DF: `LogisticRegression(max_iter=1000, solver='lbfgs', random_state=seed)`; BC: `LogisticRegression(max_iter=1000, solver='saga', random_state=seed)` |",
        "| LinearSVC | sim | sim | `LinearSVC(random_state=seed, max_iter=5000)` |",
        "| KNN | sim | sim | `KNeighborsClassifier()`; DF é escalado com `StandardScaler` |",
        "",
        "SVC RBF/Poly foram **excluídos do pool** porque a regra do projeto é manter apenas algoritmos viáveis nas duas representações.",
        "",
        "## Notas metodológicas",
        "",
        "**Hiperparâmetros.** 5 dos 7 algoritmos rodam **100% com defaults do scikit-learn** (`DecisionTree`, `RandomForest`, `HistGradientBoosting`, `NaiveBayes`, `KNN`) — apenas com `random_state=seed` para reprodutibilidade onde aplicável. Apenas dois sofrem ajustes mínimos por estabilidade numérica:",
        "",
        "| Algoritmo | Desvio do default | Justificativa |",
        "|---|---|---|",
        "| `LogisticRegression` (BC) | `solver='saga'`, `max_iter=1000` | `lbfgs` (default) não suporta bem matriz esparsa de alta dimensionalidade; `saga` é o solver oficial para esse caso. |",
        "| `LogisticRegression` (DF) | `max_iter=1000` | `max_iter=100` (default) emite warning de convergência na escala 12k×102. |",
        "| `LinearSVC` | `max_iter=5000` | `max_iter=1000` (default) emite warning de convergência na nossa base. |",
        "",
        "O sweep estruturado de hiperparâmetros acontece **apenas na Fase E** (grids ≤192 configs por algoritmo). A Fase D é estritamente um filtro de viabilidade com defaults — escolher hiperparâmetros aqui contaminaria a decisão do top-5 com um sweep escondido.",
        "",
        "**Estratificação do hold-out.** Cada uma das 5 repetições faz `train_test_split(..., stratify=y, random_state=seed)` com `test_size=0.2`. Tanto treino (80%) quanto teste (20%) preservam a proporção original de classes em `y1` (Archidekt bracket). Isso importa porque `y1=3` é maioria (~52%) e `y1=2` é minoritária (~21%) na base modelável (12.135 decks) — sem estratificação, splits desfavoráveis poderiam concentrar a minoria no teste e enviesar a macro-F1 (que penaliza igualmente todas as classes).",
        "",
        "A Fase D **não** tem CV interna: é hold-out 80/20 repetido 5x com seeds distintas mas determinísticas (`{1,2,3,4,5}`). A nested CV completa (`StratifiedKFold(5) × 3 repeats = 15 outer folds`) só aparece na Fase E.",
        "",
    ]

    # ----- Per-seed table (BC at best_bc_min_df + DF) -----
    bc_focus, df_focus = collect_focused_macro_f1(combinations, best_bc_min_df)
    seed_headers = " | ".join(f"seed={s}" for s in args.seeds)
    lines.extend([
        f"## Macro-F1 por seed — BC (`bc_min_df={best_bc_min_df}`) vs DF",
        "",
        "Cada linha mostra os 5 valores brutos de macro-F1 (um por seed) somados à média e desvio padrão. Permite inspecionar a estabilidade de cada algoritmo separadamente da tabela completa de combinações.",
        "",
        f"| Algoritmo | Rep | {seed_headers} | Média | DP |",
        "|---|---|" + ("---:|" * (len(args.seeds) + 2)),
    ])

    def _per_seed_row(algorithm: str, rep: str, values: List[float]) -> str:
        cells = [format_float(v) for v in values]
        while len(cells) < len(args.seeds):
            cells.append("")
        mean = float(np.mean(values)) if values else None
        std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        return (
            f"| `{algorithm}` | {rep} | "
            + " | ".join(cells)
            + f" | {format_float(mean)} | {format_float(std)} |"
        )

    seed_rows: List[Tuple[str, str, List[float], float]] = []
    for algorithm, values in bc_focus.items():
        mean = float(np.mean(values)) if values else 0.0
        seed_rows.append((algorithm, "BC", values, mean))
    for algorithm, values in df_focus.items():
        mean = float(np.mean(values)) if values else 0.0
        seed_rows.append((algorithm, "DF", values, mean))
    seed_rows.sort(key=lambda row: (row[1], -row[3]))
    for algorithm, rep, values, _mean in seed_rows:
        lines.append(_per_seed_row(algorithm, rep, values))

    # ----- Boxplots (one per representation) -----
    df_figure_path = args.docs_dir / BOXPLOT_DF_RELATIVE_PATH
    bc_figure_path = args.docs_dir / BOXPLOT_BC_RELATIVE_PATH
    df_saved = plot_macro_f1_boxplot(
        df_focus,
        figure_path=df_figure_path,
        representation="DF",
        color=DF_BOX_COLOR,
        n_seeds=len(args.seeds),
    )
    bc_saved = plot_macro_f1_boxplot(
        bc_focus,
        figure_path=bc_figure_path,
        representation="BC",
        color=BC_BOX_COLOR,
        n_seeds=len(args.seeds),
        bc_min_df=best_bc_min_df,
    )
    lines.extend([
        "",
        "## Boxplots: Macro-F1 por algoritmo",
        "",
        f"Distribuição dos {len(args.seeds)} valores de macro-F1 por algoritmo em cada representação. Os pontos pretos sobrepostos são as seeds individuais. Algoritmos ordenados pela média decrescente dentro de cada figura.",
        "",
        "### Deck Features (DF)",
        "",
    ])
    if df_saved is not None:
        lines.append(f"![Boxplot Macro-F1 DF](./{BOXPLOT_DF_RELATIVE_PATH.as_posix()})")
        lines.append("")
    else:
        lines.append("_Boxplot DF não gerado: dados insuficientes._")
        lines.append("")
    lines.extend([
        f"### Bag of Cards (BC, `bc_min_df={best_bc_min_df}`)",
        "",
    ])
    if bc_saved is not None:
        lines.append(f"![Boxplot Macro-F1 BC](./{BOXPLOT_BC_RELATIVE_PATH.as_posix()})")
        lines.append("")
    else:
        lines.append("_Boxplot BC não gerado: dados insuficientes._")
        lines.append("")

    lines.extend([
        "## Resultados por combinação (média ± desvio padrão sobre 5 seeds)",
        "",
        "| Representação | Algoritmo | bc_min_df | Status | n_ok | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro | Recall macro | Features | Fit médio (s) |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for combo in sorted(
        combinations,
        key=lambda c: (str(c.get("representation")), str(c.get("algorithm")), c.get("bc_min_df") or 0),
    ):
        agg = combo["aggregate"]
        lines.append(
            "| {rep} | `{alg}` | {bc_min_df} | {status} | {nok} | {f1m} | {f1s} | {accm} | {pm} | {rm} | {nf} | {fit} |".format(
                rep=combo.get("representation"),
                alg=combo.get("algorithm"),
                bc_min_df=combo.get("bc_min_df") if combo.get("bc_min_df") is not None else "",
                status=agg.get("status"),
                nok=agg.get("n_seeds_ok", 0),
                f1m=format_float(agg.get("macro_f1_mean")),
                f1s=format_float(agg.get("macro_f1_std")),
                accm=format_float(agg.get("accuracy_mean")),
                pm=format_float(agg.get("precision_macro_mean")),
                rm=format_float(agg.get("recall_macro_mean")),
                nf=agg.get("n_features_first", ""),
                fit=format_float(agg.get("fit_seconds_mean"), digits=2),
            )
        )

    lines.extend([
        "",
        "## Ranking por representação",
        "",
        f"BC usa apenas o `bc_min_df` escolhido (`{best_bc_min_df}`). DF é ranqueado direto. Top-{TOPK_PER_REPRESENTATION} por representação alimenta a Fase E.",
        "",
    ])
    for representation in REPRESENTATIONS:
        lines.extend([
            f"### {representation}",
            "",
            "| Rank | Algoritmo | Macro-F1 média | Macro-F1 dp | n_ok | Selecionado (top-5) | Observação |",
            "|---:|---|---:|---:|---:|---|---|",
        ])
        for row in rankings.get(representation, []):
            lines.append(
                f"| {row['rank']} | `{row['algorithm']}` | {format_float(row.get('macro_f1_mean'))} | "
                f"{format_float(row.get('macro_f1_std'))} | {row.get('n_seeds_ok', 0)} | "
                f"{'sim' if row.get('selected') else 'não'} | {row.get('reason') or ''} |"
            )
        lines.append("")

    lines.extend([
        "## Top-5 por representação",
        "",
        f"- `A_DF` = {top_df or '_nenhum_'}",
        f"- `A_BC` = {top_bc or '_nenhum_'}",
        f"- União (algoritmos a treinar na Fase E): `{', '.join(union) or '—'}`",
        "",
        f"Total de modelos da Fase E: {len(union) * 2} — cada algoritmo da união `A_DF ∪ A_BC` é treinado em DF e em BC. Se um algoritmo aparece em apenas uma das listas, ele ainda entra nas duas representações para manter a comparação BC vs DF pareada.",
        "",
        "## Problemas encontrados",
        "",
    ])
    if errors:
        for combo in errors:
            agg = combo["aggregate"]
            problems = agg.get("errors", [])
            for err in problems:
                bc_context = f" com `bc_min_df={err.get('bc_min_df')}`" if err.get("bc_min_df") is not None else ""
                lines.append(
                    f"- `{err.get('algorithm')}` em `{err.get('representation')}`{bc_context} (seed={err.get('seed')}): {err.get('error')}"
                )
    else:
        lines.append("- Nenhum problema operacional encontrado.")

    lines.extend([
        "",
        "## Próximo passo",
        "",
        "Rodar a nested CV da Fase E sobre `|A_uniao| × 2` modelos (cada algoritmo da união `A_DF ∪ A_BC` treinado em ambas as representações). As listas são lidas automaticamente de `experiments/spot_check/summary.json`.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase-D spot-checking (N=5 repetitions per combination).")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=list(DEFAULT_SEEDS),
        help="Seeds used for the N repetitions (default 1..5).",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument(
        "--bc-min-df-values",
        "--min-df-values",
        dest="bc_min_df_values",
        type=int,
        nargs="+",
        default=[5, 10, 20],
        help="BC-only document-frequency thresholds for pruning cards.",
    )
    parser.add_argument("--algorithms", nargs="+", choices=ALGORITHMS, default=list(ALGORITHMS))
    parser.add_argument("--representations", nargs="+", choices=REPRESENTATIONS, default=list(REPRESENTATIONS))
    parser.add_argument("--n-jobs", type=int, default=-1)
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional stratified sample size for smoke tests. Omit for the full Phase-D run.",
    )
    parser.add_argument("--quiet-progress", action="store_true", help="Hide human-readable progress messages.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    invalid_bc_min_df = [value for value in args.bc_min_df_values if value < 5]
    if invalid_bc_min_df:
        raise ValueError(f"Phase D only supports BC bc_min_df >= 5; got {invalid_bc_min_df}")
    if not args.seeds:
        raise ValueError("Phase D needs at least one seed; default is 1..5.")

    features, bags = load_modeling_data(args.processed_dir)
    y = target_vector(features)

    if args.max_rows is not None and args.max_rows < len(y):
        indices = np.arange(len(y))
        sample_idx, _ = train_test_split(
            indices,
            train_size=args.max_rows,
            stratify=y,
            random_state=args.seeds[0],
        )
        sample_idx = np.sort(sample_idx)
        features = [features[i] for i in sample_idx]
        bags = [bags[i] for i in sample_idx]
        y = y[sample_idx]

    planned: List[Tuple[str, Optional[int], str]] = []
    for representation in args.representations:
        bc_values = args.bc_min_df_values if representation == "BC" else [None]
        for bc_min_df in bc_values:
            for algorithm in args.algorithms:
                planned.append((representation, bc_min_df, algorithm))

    per_seed_results: List[Dict[str, Any]] = []
    combinations: List[Dict[str, Any]] = []
    total_runs = len(planned) * len(args.seeds)
    completed_runs = 0
    for combo_index, (representation, bc_min_df, algorithm) in enumerate(planned, start=1):
        combo_started = time.monotonic()
        seed_records: List[Dict[str, Any]] = []
        for seed in args.seeds:
            completed_runs += 1
            print_progress(
                f"\n[Phase D run {completed_runs}/{total_runs}] START {combo_label(algorithm, representation, bc_min_df)} | seed={seed}",
                args.quiet_progress,
            )
            row = run_single_seed(
                algorithm=algorithm,
                representation=representation,
                bc_min_df=bc_min_df,
                features=features,
                bags=bags,
                y=y,
                test_size=args.test_size,
                seed=int(seed),
                n_jobs=args.n_jobs,
            )
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
            per_seed_results.append(row)
            seed_records.append(row)
            f1_text = f" | macro_f1={row['macro_f1']:.4f}" if row.get("macro_f1") is not None else ""
            print_progress(
                f"[Phase D run {completed_runs}/{total_runs}] DONE  {combo_label(algorithm, representation, bc_min_df)}"
                f" | seed={seed} | status={row.get('status')} | elapsed={row.get('elapsed_seconds')}s{f1_text}",
                args.quiet_progress,
            )
        aggregate = aggregate_combination(seed_records)
        aggregate["elapsed_seconds_total"] = round(time.monotonic() - combo_started, 3)
        combinations.append({
            "combination_index": combo_index,
            "representation": representation,
            "algorithm": algorithm,
            "bc_min_df": bc_min_df,
            "aggregate": aggregate,
        })
        if aggregate.get("status") == "ok":
            print_progress(
                f"[Phase D combo {combo_index}/{len(planned)}] AGG   "
                f"{combo_label(algorithm, representation, bc_min_df)} | "
                f"macro_f1_mean={aggregate['macro_f1_mean']:.4f} ± {aggregate['macro_f1_std']:.4f}",
                args.quiet_progress,
            )

    best_bc_min_df = select_best_bc_min_df(combinations)
    rankings = {
        "DF": ranking_for_representation(combinations, "DF", bc_min_df_filter=None),
        "BC": ranking_for_representation(combinations, "BC", bc_min_df_filter=best_bc_min_df),
    }
    top5_df = selected_algorithms(rankings["DF"])
    top5_bc = selected_algorithms(rankings["BC"])
    union_algorithms = sorted(set(top5_df) | set(top5_bc))

    args.experiment_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.experiment_dir / "results.jsonl", per_seed_results)
    write_jsonl(args.experiment_dir / "combinations.jsonl", combinations)
    summary = {
        "parameters": {
            "processed_dir": str(args.processed_dir),
            "seeds": list(args.seeds),
            "test_size": args.test_size,
            "bc_min_df_values": args.bc_min_df_values,
            "algorithms": args.algorithms,
            "representations": args.representations,
            "max_rows": args.max_rows,
        },
        "n_rows": int(len(y)),
        "n_seeds": len(args.seeds),
        "class_counts": {str(label): int((y == label).sum()) for label in sorted(set(y))},
        "best_bc_min_df": best_bc_min_df,
        "rankings": rankings,
        "selection": {
            "top5_DF": top5_df,
            "top5_BC": top5_bc,
            "union": union_algorithms,
        },
    }
    write_json(args.experiment_dir / "summary.json", summary)
    write_report(
        path=args.docs_dir / REPORT_FILENAME,
        combinations=combinations,
        rankings=rankings,
        best_bc_min_df=best_bc_min_df,
        args=args,
    )
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
