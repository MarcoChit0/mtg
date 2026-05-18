#!/usr/bin/env python3
"""Phase E — leakage-safe nested cross-validation for the selected models."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from scipy.stats import friedmanchisquare, rankdata, studentized_range, wilcoxon
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

try:
    from preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector, y2_value  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector, y2_value  # type: ignore


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents")
DEFAULT_EXPERIMENT_DIR = Path("experiments")
SELECTED_ALGORITHMS = (
    "gradient_boosting",
    "logistic_regression",
    "random_forest",
    "linear_svc",
    "naive_bayes",
)
REPRESENTATIONS = ("DF", "BC")
LABELS = [2, 3, 4]


class SparseToDenseTransformer(BaseEstimator, TransformerMixin):
    """Convert sparse BC matrices to dense arrays for estimators that need dense X."""

    def fit(self, X: Any, y: Any = None) -> "SparseToDenseTransformer":
        return self

    def transform(self, X: Any) -> np.ndarray:
        if sparse.issparse(X):
            return X.toarray()
        return np.asarray(X)


def read_json(path: Path) -> Any:
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


def print_progress(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def grid_size(grid: Mapping[str, Sequence[Any]]) -> int:
    size = 1
    for values in grid.values():
        size *= len(values)
    return size


def load_modeling_data(processed_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ids_path = processed_dir / "modeling_snapshot_ids.json"
    if not ids_path.exists():
        raise FileNotFoundError(f"Missing {ids_path}; run phase-c-filter-dataset first.")
    snapshot_ids = read_json(ids_path)
    id_set = set(snapshot_ids)

    features_by_id = {
        record["snapshot_id"]: record
        for record in iter_jsonl(processed_dir / "deck_features.jsonl")
        if record.get("snapshot_id") in id_set
    }
    bags_by_id = {
        record["snapshot_id"]: record
        for record in iter_jsonl(processed_dir / "bag_of_cards.jsonl")
        if record.get("snapshot_id") in id_set
    }
    missing_features = [sid for sid in snapshot_ids if sid not in features_by_id]
    missing_bags = [sid for sid in snapshot_ids if sid not in bags_by_id]
    if missing_features or missing_bags:
        raise ValueError(
            f"Modeling ids are not aligned: missing_features={len(missing_features)}, missing_bags={len(missing_bags)}"
        )
    return [features_by_id[sid] for sid in snapshot_ids], [bags_by_id[sid] for sid in snapshot_ids]


def subset_rows(rows: Sequence[Mapping[str, Any]], indices: np.ndarray) -> List[Mapping[str, Any]]:
    return [rows[int(idx)] for idx in indices]


def model_id(representation: str, algorithm: str) -> str:
    return f"{representation.lower()}_{algorithm}"


def needs_df_scaling(algorithm: str) -> bool:
    return algorithm in {"logistic_regression", "linear_svc"}


def estimator_for(algorithm: str, representation: str, random_state: int, n_jobs: int) -> BaseEstimator:
    if algorithm == "gradient_boosting":
        return HistGradientBoostingClassifier(random_state=random_state)
    if algorithm == "logistic_regression":
        solver = "saga" if representation == "BC" else "lbfgs"
        return LogisticRegression(max_iter=2000, solver=solver, random_state=random_state, n_jobs=n_jobs)
    if algorithm == "random_forest":
        return RandomForestClassifier(random_state=random_state, n_jobs=n_jobs)
    if algorithm == "linear_svc":
        return LinearSVC(random_state=random_state, max_iter=10000)
    if algorithm == "naive_bayes":
        return MultinomialNB() if representation == "BC" else GaussianNB()
    raise ValueError(f"Unknown selected algorithm: {algorithm}")


def pipeline_for(
    algorithm: str,
    representation: str,
    *,
    bc_min_df: int,
    use_tfidf: bool,
    random_state: int,
    n_jobs: int,
) -> Pipeline:
    if representation == "DF":
        steps: List[Tuple[str, Any]] = [
            ("prep", DeckFeaturePreprocessor(scale=needs_df_scaling(algorithm))),
            ("clf", estimator_for(algorithm, representation, random_state, n_jobs)),
        ]
    elif representation == "BC":
        steps = [
            ("prep", BagOfCardsPreprocessor(min_df=bc_min_df, use_tfidf=use_tfidf)),
        ]
        if algorithm == "gradient_boosting":
            steps.append(("dense", SparseToDenseTransformer()))
        steps.append(("clf", estimator_for(algorithm, representation, random_state, n_jobs)))
    else:
        raise ValueError(f"Unknown representation: {representation}")
    return Pipeline(steps)


def full_param_grid(algorithm: str, representation: str) -> Dict[str, List[Any]]:
    if algorithm == "gradient_boosting":
        return {
            "clf__max_iter": [100, 300],
            "clf__learning_rate": [0.05, 0.1],
            "clf__max_depth": [3, 5],
        }
    if algorithm == "logistic_regression":
        return {
            "clf__C": [0.01, 0.1, 1.0, 10.0],
            "clf__class_weight": [None, "balanced"],
        }
    if algorithm == "random_forest":
        return {
            "clf__n_estimators": [100, 300],
            "clf__max_features": ["sqrt", "log2"],
            "clf__max_depth": [None, 20],
        }
    if algorithm == "linear_svc":
        return {
            "clf__C": [0.01, 0.1, 1.0, 10.0],
            "clf__class_weight": [None, "balanced"],
        }
    if algorithm == "naive_bayes" and representation == "BC":
        return {"clf__alpha": [0.01, 0.1, 1.0, 10.0]}
    if algorithm == "naive_bayes" and representation == "DF":
        return {"clf__var_smoothing": list(np.logspace(-9, -7, 3))}
    raise ValueError(f"No grid for {representation}/{algorithm}")


def shrink_grid(grid: Mapping[str, Sequence[Any]], max_values: Optional[int]) -> Dict[str, List[Any]]:
    if max_values is None:
        return {key: list(values) for key, values in grid.items()}
    return {key: list(values)[:max_values] for key, values in grid.items()}


def metric_record(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    return {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).astype(int).tolist(),
        "labels": LABELS,
    }


def aggregate_metrics(folds: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    aggregate: Dict[str, Any] = {}
    for metric in ("macro_f1", "accuracy", "precision_macro", "recall_macro"):
        values = np.asarray([float(row[metric]) for row in folds], dtype=float)
        aggregate[f"{metric}_mean"] = float(values.mean()) if values.size else None
        aggregate[f"{metric}_std"] = float(values.std(ddof=1)) if values.size > 1 else 0.0
    total = np.zeros((len(LABELS), len(LABELS)), dtype=int)
    for row in folds:
        total += np.asarray(row["confusion_matrix"], dtype=int)
    aggregate["confusion_matrix_sum"] = total.tolist()
    aggregate["labels"] = LABELS
    return aggregate


def generate_outer_folds(y: np.ndarray, repeats: Sequence[int], outer_splits: int) -> List[Dict[str, Any]]:
    folds: List[Dict[str, Any]] = []
    indices = np.arange(len(y))
    for repeat_seed in repeats:
        splitter = StratifiedKFold(n_splits=outer_splits, shuffle=True, random_state=repeat_seed)
        for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(indices, y), start=1):
            folds.append({
                "repeat_seed": int(repeat_seed),
                "outer_fold": int(fold_idx),
                "fold_id": f"r{repeat_seed}_f{fold_idx}",
                "train_idx": train_idx.astype(int).tolist(),
                "test_idx": test_idx.astype(int).tolist(),
            })
    return folds


def sample_rows(
    features: List[Dict[str, Any]],
    bags: List[Dict[str, Any]],
    y: np.ndarray,
    max_rows: Optional[int],
    random_state: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], np.ndarray]:
    if max_rows is None or max_rows >= len(y):
        return features, bags, y
    indices = np.arange(len(y))
    sample_idx, _ = train_test_split(indices, train_size=max_rows, stratify=y, random_state=random_state)
    sample_idx = np.sort(sample_idx)
    return [features[i] for i in sample_idx], [bags[i] for i in sample_idx], y[sample_idx]


def fit_one_model(
    *,
    representation: str,
    algorithm: str,
    rows: Sequence[Mapping[str, Any]],
    feature_rows: Sequence[Mapping[str, Any]],
    y: np.ndarray,
    folds: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
    model_index: int,
    total_models: int,
) -> Dict[str, Any]:
    model_name = model_id(representation, algorithm)
    out_dir = args.experiment_dir / model_name
    out_dir.mkdir(parents=True, exist_ok=True)
    fold_metrics: List[Dict[str, Any]] = []
    predictions: List[Dict[str, Any]] = []
    best_params: List[Dict[str, Any]] = []

    for fold_index, fold in enumerate(folds, start=1):
        started = time.monotonic()
        train_idx = np.asarray(fold["train_idx"], dtype=int)
        test_idx = np.asarray(fold["test_idx"], dtype=int)
        seed = int(args.random_state + int(fold["repeat_seed"]) * 100 + int(fold["outer_fold"]))
        inner_cv = StratifiedKFold(
            n_splits=args.inner_splits,
            shuffle=True,
            random_state=int(fold["repeat_seed"]) + 100,
        )
        pipeline = pipeline_for(
            algorithm,
            representation,
            bc_min_df=args.bc_min_df,
            use_tfidf=args.use_tfidf,
            random_state=seed,
            n_jobs=args.estimator_n_jobs,
        )
        grid = shrink_grid(full_param_grid(algorithm, representation), args.max_grid_values)
        config_parts = [
            f"model={model_name}",
            f"representation={representation}",
            f"algorithm={algorithm}",
            f"outer={fold['fold_id']}",
            f"inner_splits={args.inner_splits}",
            f"grid_configs={grid_size(grid)}",
            f"train={len(train_idx)}",
            f"test={len(test_idx)}",
        ]
        if representation == "BC":
            config_parts.append(f"bc_min_df={args.bc_min_df}")
            config_parts.append(f"use_tfidf={args.use_tfidf}")
            if algorithm == "gradient_boosting":
                config_parts.append("dense_conversion=True")
        print_progress(
            f"\n[Phase E model {model_index}/{total_models} fold {fold_index}/{len(folds)}] START "
            + " | ".join(config_parts),
            args.quiet_progress,
        )
        search = GridSearchCV(
            estimator=pipeline,
            param_grid=grid,
            scoring="f1_macro",
            cv=inner_cv,
            n_jobs=args.grid_n_jobs,
            refit=True,
            error_score="raise",
        )
        x_train = subset_rows(rows, train_idx)
        x_test = subset_rows(rows, test_idx)
        y_train = y[train_idx]
        y_test = y[test_idx]
        search.fit(x_train, y_train)
        y_pred = search.predict(x_test)

        metrics = metric_record(y_test, y_pred)
        metrics.update({
            "model_id": model_name,
            "representation": representation,
            "algorithm": algorithm,
            "repeat_seed": int(fold["repeat_seed"]),
            "outer_fold": int(fold["outer_fold"]),
            "fold_id": fold["fold_id"],
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
            "inner_best_macro_f1": float(search.best_score_),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        })
        fold_metrics.append(metrics)
        best_params.append({
            "model_id": model_name,
            "repeat_seed": int(fold["repeat_seed"]),
            "outer_fold": int(fold["outer_fold"]),
            "fold_id": fold["fold_id"],
            "best_params": search.best_params_,
            "inner_best_macro_f1": float(search.best_score_),
        })

        for idx, true_value, pred_value in zip(test_idx, y_test, y_pred):
            feature_row = feature_rows[int(idx)]
            predictions.append({
                "model_id": model_name,
                "representation": representation,
                "algorithm": algorithm,
                "repeat_seed": int(fold["repeat_seed"]),
                "outer_fold": int(fold["outer_fold"]),
                "fold_id": fold["fold_id"],
                "row_index": int(idx),
                "snapshot_id": feature_row.get("snapshot_id"),
                "deck_id": feature_row.get("deck_id"),
                "y_true": int(true_value),
                "y_pred": int(pred_value),
                "y2": y2_value(feature_row),
            })
        print(json.dumps({
            "model_id": model_name,
            "fold_id": fold["fold_id"],
            "macro_f1": metrics["macro_f1"],
            "best_params": search.best_params_,
            "elapsed_seconds": metrics["elapsed_seconds"],
        }, ensure_ascii=False, sort_keys=True))
        print_progress(
            f"[Phase E model {model_index}/{total_models} fold {fold_index}/{len(folds)}] DONE  "
            f"model={model_name} | outer={fold['fold_id']} | macro_f1={metrics['macro_f1']:.4f} "
            f"| inner_best={search.best_score_:.4f} | elapsed={metrics['elapsed_seconds']}s "
            f"| best_params={search.best_params_}",
            args.quiet_progress,
        )

    metrics_payload = {
        "model_id": model_name,
        "representation": representation,
        "algorithm": algorithm,
        "folds": fold_metrics,
        "aggregate": aggregate_metrics(fold_metrics),
    }
    write_json(out_dir / "metrics_per_fold.json", metrics_payload)
    write_json(out_dir / "best_hyperparams_per_fold.json", best_params)
    write_jsonl(out_dir / "predictions_per_fold.jsonl", predictions)
    return metrics_payload


def statistical_payload(model_metrics: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_model = {str(row["model_id"]): row for row in model_metrics}
    model_names = sorted(by_model)
    fold_keys = sorted({
        fold["fold_id"]
        for row in model_metrics
        for fold in row.get("folds", [])
    })
    score_matrix: List[List[float]] = []
    usable_folds: List[str] = []
    for fold_key in fold_keys:
        row_scores = []
        missing = False
        for model_name in model_names:
            scores = [
                float(fold["macro_f1"])
                for fold in by_model[model_name].get("folds", [])
                if fold["fold_id"] == fold_key
            ]
            if not scores:
                missing = True
                break
            row_scores.append(scores[0])
        if not missing:
            usable_folds.append(fold_key)
            score_matrix.append(row_scores)

    matrix = np.asarray(score_matrix, dtype=float)
    payload: Dict[str, Any] = {
        "models": model_names,
        "folds": usable_folds,
        "status": "ok" if matrix.shape[0] >= 2 and matrix.shape[1] >= 3 else "insufficient_data",
    }
    if payload["status"] != "ok":
        return payload

    friedman = friedmanchisquare(*[matrix[:, idx] for idx in range(matrix.shape[1])])
    ranks = np.asarray([rankdata(-row, method="average") for row in matrix], dtype=float)
    avg_ranks = ranks.mean(axis=0)
    k = matrix.shape[1]
    n = matrix.shape[0]
    alpha = 0.05
    q_alpha = float(studentized_range.ppf(1 - alpha, k, np.inf) / np.sqrt(2))
    critical_difference = float(q_alpha * np.sqrt(k * (k + 1) / (6 * n)))
    nemenyi_pairs = []
    for i, left in enumerate(model_names):
        for j, right in enumerate(model_names):
            if j <= i:
                continue
            diff = float(abs(avg_ranks[i] - avg_ranks[j]))
            nemenyi_pairs.append({
                "model_a": left,
                "model_b": right,
                "rank_diff": diff,
                "significant_alpha_0_05": bool(diff > critical_difference),
            })

    wilcoxon_pairs = []
    for i, left in enumerate(model_names):
        for j, right in enumerate(model_names):
            if j <= i:
                continue
            try:
                test = wilcoxon(matrix[:, i], matrix[:, j], zero_method="wilcox")
                statistic = float(test.statistic)
                p_value = float(test.pvalue)
            except ValueError:
                statistic = None
                p_value = None
            wilcoxon_pairs.append({
                "model_a": left,
                "model_b": right,
                "statistic": statistic,
                "p_value": p_value,
            })

    payload.update({
        "friedman": {
            "statistic": float(friedman.statistic),
            "p_value": float(friedman.pvalue),
        },
        "average_ranks": {
            model_name: float(rank)
            for model_name, rank in zip(model_names, avg_ranks)
        },
        "nemenyi": {
            "alpha": alpha,
            "critical_difference": critical_difference,
            "pairs": nemenyi_pairs,
        },
        "wilcoxon_pairs": wilcoxon_pairs,
    })
    return payload


def write_report(path: Path, summary: Mapping[str, Any], stats: Mapping[str, Any]) -> None:
    lines: List[str] = [
        "# Nested CV — Fase E",
        "",
        "## Objetivo",
        "",
        "Treinar os 10 modelos definidos na Fase D, sempre prevendo `y1`, com nested cross-validation sem vazamento entre folds.",
        "",
        "## Configuração",
        "",
        f"- Representações: {', '.join(summary['parameters']['representations'])}",
        f"- Algoritmos: {', '.join(summary['parameters']['algorithms'])}",
        f"- Outer CV: {summary['parameters']['outer_splits']} folds × repeats `{', '.join(map(str, summary['parameters']['repeats']))}`",
        f"- Inner CV: {summary['parameters']['inner_splits']} folds",
        f"- `bc_min_df`: {summary['parameters']['bc_min_df']}",
        f"- `use_tfidf`: {summary['parameters']['use_tfidf']}",
        f"- Linhas modeláveis: {summary['n_rows']}",
        "",
        "## Resultados",
        "",
        "| Modelo | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro média | Recall macro média |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["models"]:
        aggregate = row["aggregate"]
        lines.append(
            "| {model} | {f1:.4f} | {f1_std:.4f} | {acc:.4f} | {prec:.4f} | {rec:.4f} |".format(
                model=row["model_id"],
                f1=aggregate["macro_f1_mean"],
                f1_std=aggregate["macro_f1_std"],
                acc=aggregate["accuracy_mean"],
                prec=aggregate["precision_macro_mean"],
                rec=aggregate["recall_macro_mean"],
            )
        )

    lines.extend([
        "",
        "## Testes Estatísticos",
        "",
    ])
    if stats.get("status") == "ok":
        friedman = stats["friedman"]
        lines.append(f"- Friedman: statistic={friedman['statistic']:.4f}, p={friedman['p_value']:.6f}.")
        lines.append(f"- Nemenyi: diferença crítica={stats['nemenyi']['critical_difference']:.4f} para alpha=0.05.")
    else:
        lines.append("- Testes estatísticos não executados: dados insuficientes nesta rodada.")

    lines.extend([
        "",
        "## Artefatos",
        "",
        "- `experiments/seeds.json`",
        "- `experiments/folds.json`",
        "- `experiments/nested_cv_summary.json`",
        "- `experiments/<representação>_<algoritmo>/metrics_per_fold.json`",
        "- `experiments/<representação>_<algoritmo>/best_hyperparams_per_fold.json`",
        "- `experiments/<representação>_<algoritmo>/predictions_per_fold.jsonl`",
        "- `documents/statistical_tests.md`",
        "",
        "## Problemas Encontrados",
        "",
    ])
    problems = summary.get("problems") or []
    if problems:
        for problem in problems:
            lines.append(f"- {problem}")
    else:
        lines.append("- Nenhum problema operacional registrado nesta rodada.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_stats_report(path: Path, stats: Mapping[str, Any]) -> None:
    lines = [
        "# Testes Estatísticos — Fase E",
        "",
    ]
    if stats.get("status") != "ok":
        lines.append("Dados insuficientes para Friedman/Nemenyi/Wilcoxon nesta rodada.")
    else:
        friedman = stats["friedman"]
        lines.extend([
            f"- Friedman statistic: `{friedman['statistic']:.6f}`",
            f"- Friedman p-value: `{friedman['p_value']:.6f}`",
            f"- Nemenyi critical difference (alpha=0.05): `{stats['nemenyi']['critical_difference']:.6f}`",
            "",
            "## Ranks Médios",
            "",
            "| Modelo | Rank médio |",
            "|---|---:|",
        ])
        for model_name, rank in sorted(stats["average_ranks"].items(), key=lambda item: item[1]):
            lines.append(f"| `{model_name}` | {rank:.4f} |")
        significant = [row for row in stats["nemenyi"]["pairs"] if row["significant_alpha_0_05"]]
        lines.extend([
            "",
            "## Nemenyi",
            "",
        ])
        if significant:
            for row in significant:
                lines.append(f"- `{row['model_a']}` vs `{row['model_b']}`: rank diff `{row['rank_diff']:.4f}`.")
        else:
            lines.append("- Nenhum par superou a diferença crítica em alpha=0.05.")
        lines.extend([
            "",
            "## Wilcoxon Pareado",
            "",
            "| Modelo A | Modelo B | Statistic | p-value |",
            "|---|---|---:|---:|",
        ])
        for row in stats["wilcoxon_pairs"]:
            stat = "" if row["statistic"] is None else f"{row['statistic']:.4f}"
            p_value = "" if row["p_value"] is None else f"{row['p_value']:.6f}"
            lines.append(f"| `{row['model_a']}` | `{row['model_b']}` | {stat} | {p_value} |")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase-E nested cross-validation.")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument("--representations", nargs="+", choices=REPRESENTATIONS, default=list(REPRESENTATIONS))
    parser.add_argument("--algorithms", nargs="+", choices=SELECTED_ALGORITHMS, default=list(SELECTED_ALGORITHMS))
    parser.add_argument("--bc-min-df", type=int, default=10)
    parser.add_argument("--use-tfidf", action="store_true")
    parser.add_argument("--outer-splits", type=int, default=5)
    parser.add_argument("--inner-splits", type=int, default=3)
    parser.add_argument("--repeats", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--grid-n-jobs", type=int, default=1)
    parser.add_argument("--estimator-n-jobs", type=int, default=-1)
    parser.add_argument("--max-rows", type=int, default=None, help="Optional stratified sample size for smoke tests.")
    parser.add_argument(
        "--max-grid-values",
        type=int,
        default=None,
        help="For smoke tests, keep only the first N values of each hyperparameter grid.",
    )
    parser.add_argument("--quiet-progress", action="store_true", help="Hide human-readable progress messages.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    started = time.monotonic()
    features, bags = load_modeling_data(args.processed_dir)
    y = target_vector(features)
    features, bags, y = sample_rows(features, bags, y, args.max_rows, args.random_state)
    folds = generate_outer_folds(y, args.repeats, args.outer_splits)

    args.experiment_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.experiment_dir / "seeds.json", {
        "random_state": args.random_state,
        "outer_repeat_seeds": args.repeats,
        "inner_seed_formula": "repeat_seed + 100",
        "estimator_seed_formula": "random_state + repeat_seed * 100 + outer_fold",
    })
    write_json(args.experiment_dir / "folds.json", folds)

    model_plan = [
        (representation, algorithm)
        for representation in args.representations
        for algorithm in args.algorithms
    ]
    results: List[Dict[str, Any]] = []
    for model_index, (representation, algorithm) in enumerate(model_plan, start=1):
        rows = features if representation == "DF" else bags
        result = fit_one_model(
            representation=representation,
            algorithm=algorithm,
            rows=rows,
            feature_rows=features,
            y=y,
            folds=folds,
            args=args,
            model_index=model_index,
            total_models=len(model_plan),
        )
        results.append(result)

    stats = statistical_payload(results)
    summary: Dict[str, Any] = {
        "status": "ok",
        "n_rows": int(len(y)),
        "class_counts": {str(label): int((y == label).sum()) for label in sorted(set(y))},
        "parameters": {
            "processed_dir": str(args.processed_dir),
            "docs_dir": str(args.docs_dir),
            "experiment_dir": str(args.experiment_dir),
            "representations": args.representations,
            "algorithms": args.algorithms,
            "bc_min_df": args.bc_min_df,
            "use_tfidf": args.use_tfidf,
            "outer_splits": args.outer_splits,
            "inner_splits": args.inner_splits,
            "repeats": args.repeats,
            "random_state": args.random_state,
            "grid_n_jobs": args.grid_n_jobs,
            "estimator_n_jobs": args.estimator_n_jobs,
            "max_rows": args.max_rows,
            "max_grid_values": args.max_grid_values,
        },
        "models": results,
        "statistics": stats,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "problems": [],
    }
    write_json(args.experiment_dir / "nested_cv_summary.json", summary)
    write_json(args.experiment_dir / "statistical_tests.json", stats)
    write_stats_report(args.docs_dir / "statistical_tests.md", stats)
    write_report(args.docs_dir / "nested_cv_report.md", summary, stats)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps({
        "status": summary["status"],
        "n_rows": summary["n_rows"],
        "models": [
            {
                "model_id": row["model_id"],
                "macro_f1_mean": row["aggregate"]["macro_f1_mean"],
                "macro_f1_std": row["aggregate"]["macro_f1_std"],
            }
            for row in summary["models"]
        ],
        "elapsed_seconds": summary["elapsed_seconds"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
