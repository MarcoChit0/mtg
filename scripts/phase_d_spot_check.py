#!/usr/bin/env python3
"""Phase D — spot-check candidate algorithms on DF and BC representations."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
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
from sklearn.svm import LinearSVC, SVC
from sklearn.tree import DecisionTreeClassifier

try:
    from preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector  # type: ignore


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents")
DEFAULT_EXPERIMENT_DIR = Path("experiments/spot_check")

ALGORITHMS = (
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "naive_bayes",
    "logistic_regression",
    "linear_svc",
    "svc_rbf",
    "svc_poly",
    "knn",
)

REPRESENTATIONS = ("DF", "BC")
DF_ALGORITHMS = ALGORITHMS
BC_ALGORITHMS = (
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "naive_bayes",
    "logistic_regression",
    "linear_svc",
    "knn",
)


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


def estimator_for(name: str, representation: str, random_state: int, n_jobs: int) -> Optional[BaseEstimator]:
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
        return LogisticRegression(max_iter=1000, solver=solver, random_state=random_state, n_jobs=n_jobs)
    if name == "linear_svc":
        return LinearSVC(random_state=random_state, max_iter=5000)
    if name == "svc_rbf":
        if representation != "DF":
            return None
        return SVC(kernel="rbf", gamma="scale", random_state=random_state, cache_size=1000)
    if name == "svc_poly":
        if representation != "DF":
            return None
        return SVC(kernel="poly", degree=3, gamma="scale", random_state=random_state, cache_size=1000)
    if name == "knn":
        return KNeighborsClassifier()
    raise ValueError(f"Unknown algorithm: {name}")


def needs_df_scaling(name: str) -> bool:
    return name in {"logistic_regression", "linear_svc", "svc_rbf", "svc_poly", "knn"}


def bc_uses_tfidf(name: str) -> bool:
    # Phase D keeps TF-IDF disabled so spot-checking isolates the effect of
    # algorithm choice and BC vocabulary pruning. TF-IDF remains available in
    # the preprocessing transformer for later pipeline/hyperparameter phases.
    return False


def metric_record(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def run_one(
    *,
    algorithm: str,
    representation: str,
    bc_min_df: Optional[int],
    features_train: Sequence[Mapping[str, Any]],
    features_test: Sequence[Mapping[str, Any]],
    bags_train: Sequence[Mapping[str, Any]],
    bags_test: Sequence[Mapping[str, Any]],
    y_train: np.ndarray,
    y_test: np.ndarray,
    random_state: int,
    n_jobs: int,
) -> Dict[str, Any]:
    started = time.monotonic()
    result: Dict[str, Any] = {
        "algorithm": algorithm,
        "representation": representation,
        "bc_min_df": bc_min_df,
        "use_tfidf": bool(representation == "BC" and bc_uses_tfidf(algorithm)),
        "status": "ok",
        "error": None,
        "fit_seconds": None,
        "predict_seconds": None,
    }

    estimator = estimator_for(algorithm, representation, random_state, n_jobs)
    if estimator is None:
        result.update({
            "status": "skipped",
            "error": f"{algorithm} is not enabled for {representation} in this spot-check design",
            "elapsed_seconds": round(time.monotonic() - started, 3),
        })
        return result

    try:
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
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result
    except Exception as exc:
        result.update({
            "status": "error",
            "error": str(exc),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        })
        return result


def _run_one_worker(kwargs: Dict[str, Any], queue: mp.Queue) -> None:
    queue.put(run_one(**kwargs))


def run_one_with_timeout(max_seconds: Optional[float], **kwargs: Any) -> Dict[str, Any]:
    if max_seconds is None:
        return run_one(**kwargs)

    started = time.monotonic()
    queue: mp.Queue = mp.Queue(maxsize=1)
    process = mp.Process(target=_run_one_worker, args=(kwargs, queue))
    process.start()
    process.join(max_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        return {
            "algorithm": kwargs["algorithm"],
            "representation": kwargs["representation"],
            "bc_min_df": kwargs["bc_min_df"],
            "use_tfidf": bool(kwargs["representation"] == "BC" and bc_uses_tfidf(kwargs["algorithm"])),
            "status": "timeout",
            "error": f"stopped after exceeding {max_seconds:.3f}s, 10x the largest completed spot-check runtime",
            "fit_seconds": None,
            "predict_seconds": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    if process.exitcode != 0:
        return {
            "algorithm": kwargs["algorithm"],
            "representation": kwargs["representation"],
            "bc_min_df": kwargs["bc_min_df"],
            "use_tfidf": bool(kwargs["representation"] == "BC" and bc_uses_tfidf(kwargs["algorithm"])),
            "status": "error",
            "error": f"worker exited with code {process.exitcode}",
            "fit_seconds": None,
            "predict_seconds": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    if queue.empty():
        return {
            "algorithm": kwargs["algorithm"],
            "representation": kwargs["representation"],
            "bc_min_df": kwargs["bc_min_df"],
            "use_tfidf": bool(kwargs["representation"] == "BC" and bc_uses_tfidf(kwargs["algorithm"])),
            "status": "error",
            "error": "worker finished without returning a result",
            "fit_seconds": None,
            "predict_seconds": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    return queue.get()


def select_best_bc_min_df(results: Sequence[Mapping[str, Any]]) -> Optional[int]:
    by_bc_min_df: Dict[int, List[float]] = defaultdict(list)
    for record in results:
        if record.get("status") != "ok" or record.get("representation") != "BC":
            continue
        bc_min_df = record.get("bc_min_df")
        if isinstance(bc_min_df, int):
            by_bc_min_df[bc_min_df].append(float(record["macro_f1"]))
    if not by_bc_min_df:
        return None
    averages = {
        bc_min_df: sum(scores) / len(scores)
        for bc_min_df, scores in by_bc_min_df.items()
        if scores
    }
    return max(averages, key=averages.get)


def algorithms_for_representation(representation: str, algorithms: Sequence[str]) -> List[str]:
    valid = DF_ALGORITHMS if representation == "DF" else BC_ALGORITHMS
    return [algorithm for algorithm in algorithms if algorithm in valid]


def finalist_ranking_by_representation(
    results: Sequence[Mapping[str, Any]],
    best_bc_min_df: Optional[int],
    algorithms: Sequence[str],
) -> Dict[str, List[Dict[str, Any]]]:
    rankings: Dict[str, List[Dict[str, Any]]] = {}
    for representation in REPRESENTATIONS:
        rows: List[Dict[str, Any]] = []
        for algorithm in algorithms_for_representation(representation, algorithms):
            scores = [
                float(r["macro_f1"])
                for r in results
                if (
                    r.get("status") == "ok"
                    and r.get("algorithm") == algorithm
                    and r.get("representation") == representation
                    and (representation == "DF" or r.get("bc_min_df") == best_bc_min_df)
                )
            ]
            rows.append({
                "representation": representation,
                "algorithm": algorithm,
                "macro_f1": scores[0] if scores else None,
                "eligible_for_nested_cv": bool(scores),
                "reason": "" if scores else "missing_successful_result",
            })
        rows.sort(key=lambda row: (row["eligible_for_nested_cv"], row["macro_f1"] or -1), reverse=True)
        for idx, row in enumerate(rows, start=1):
            row["rank"] = idx
            row["selected"] = bool(row["eligible_for_nested_cv"] and idx <= 5)
        rankings[representation] = rows
    return rankings


def finalist_ranking(results: Sequence[Mapping[str, Any]], best_bc_min_df: Optional[int]) -> List[Dict[str, Any]]:
    """Legacy cross-representation ranking kept for backward compatibility."""
    rows: List[Dict[str, Any]] = []
    for algorithm in ALGORITHMS:
        df_scores = [
            float(r["macro_f1"])
            for r in results
            if r.get("status") == "ok" and r.get("algorithm") == algorithm and r.get("representation") == "DF"
        ]
        bc_scores = [
            float(r["macro_f1"])
            for r in results
            if (
                r.get("status") == "ok"
                and r.get("algorithm") == algorithm
                and r.get("representation") == "BC"
                and r.get("bc_min_df") == best_bc_min_df
            )
        ]
        eligible = bool(df_scores and bc_scores)
        scores = df_scores + bc_scores
        rows.append({
            "algorithm": algorithm,
            "df_macro_f1": df_scores[0] if df_scores else None,
            "bc_macro_f1": bc_scores[0] if bc_scores else None,
            "mean_macro_f1": (sum(scores) / len(scores)) if scores else None,
            "eligible_for_nested_cv": eligible,
            "reason": "" if eligible else "missing_successful_result_in_one_representation",
        })
    rows.sort(key=lambda row: (row["eligible_for_nested_cv"], row["mean_macro_f1"] or -1), reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
        row["selected"] = bool(row["eligible_for_nested_cv"] and sum(1 for r in rows[:idx] if r["eligible_for_nested_cv"]) <= 5)
    return rows


def format_float(value: Any) -> str:
    return "" if value is None else f"{float(value):.4f}"


def write_report(
    *,
    path: Path,
    results: Sequence[Mapping[str, Any]],
    rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    best_bc_min_df: Optional[int],
    args: argparse.Namespace,
) -> None:
    ok = [r for r in results if r.get("status") == "ok"]
    skipped = [r for r in results if r.get("status") == "skipped"]
    timed_out = [r for r in results if r.get("status") == "timeout"]
    errors = [r for r in results if r.get("status") == "error"]
    selected_df = ", ".join(
        f"`{row['algorithm']}`" for row in rankings.get("DF", []) if row.get("selected")
    )
    selected_bc = ", ".join(
        f"`{row['algorithm']}`" for row in rankings.get("BC", []) if row.get("selected")
    )

    lines: List[str] = [
        "# Spot-checking — Fase D",
        "",
        "## Objetivo",
        "",
        "Avaliar rapidamente os algoritmos candidatos em hold-out 80/20 estratificado por `y1`, usando as duas representações do projeto: Deck Features (`DF`) e Bag of Cards (`BC`). Esta fase escolhe 5 algoritmos finalistas por representação; os conjuntos de DF e BC podem ser diferentes.",
        "",
        "## Configuração",
        "",
        f"- `processed_dir`: `{args.processed_dir}`",
        f"- `random_state`: `{args.random_state}`",
        f"- `test_size`: `{args.test_size}`",
        f"- `bc_min_df_values`: `{', '.join(map(str, args.bc_min_df_values))}`",
        f"- `best_bc_min_df`: `{best_bc_min_df}`",
        "- `use_tfidf`: `False` nesta etapa",
        f"- Combinações com sucesso: {len(ok)}",
        f"- Combinações puladas: {len(skipped)}",
        f"- Combinações interrompidas por tempo: {len(timed_out)}",
        f"- Combinações com erro: {len(errors)}",
        "",
        "## Resultados por combinação",
        "",
        "| Representação | Algoritmo | bc_min_df | TF-IDF | Status | Macro-F1 | Accuracy | Precision macro | Recall macro | Features | Tempo total (s) |",
        "|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(results, key=lambda item: (str(item.get("representation")), str(item.get("algorithm")), item.get("bc_min_df") or 0)):
        lines.append(
            "| {rep} | `{alg}` | {bc_min_df} | {tfidf} | {status} | {f1} | {acc} | {prec} | {rec} | {nf} | {sec} |".format(
                rep=r.get("representation"),
                alg=r.get("algorithm"),
                bc_min_df=r.get("bc_min_df") if r.get("bc_min_df") is not None else "",
                tfidf="sim" if r.get("use_tfidf") else "não",
                status=r.get("status"),
                f1=format_float(r.get("macro_f1")),
                acc=format_float(r.get("accuracy")),
                prec=format_float(r.get("precision_macro")),
                rec=format_float(r.get("recall_macro")),
                nf=r.get("n_features", ""),
                sec=format_float(r.get("elapsed_seconds")),
            )
        )

    lines.extend([
        "",
        "## Ranking dos algoritmos por representação",
        "",
        "O ranking é separado por representação. Para BC, usa apenas o `bc_min_df` escolhido. Os kernels não-lineares de SVM (`svc_rbf`, `svc_poly`) são avaliados só em DF; em BC, o custo de kernel não-linear sobre matriz esparsa de alta dimensionalidade não é adequado para este projeto. Gradient Boosting foi testado em BC com limite de tempo de 10x o maior tempo já observado nas demais runs; se exceder esse limite, é interrompido e removido dos finalistas.",
        "",
    ])
    for representation in REPRESENTATIONS:
        lines.extend([
            f"### {representation}",
            "",
            "| Rank | Algoritmo | Macro-F1 | Elegível | Selecionado | Observação |",
            "|---:|---|---:|---|---|---|",
        ])
        for row in rankings.get(representation, []):
            lines.append(
                f"| {row['rank']} | `{row['algorithm']}` | {format_float(row.get('macro_f1'))} | {'sim' if row.get('eligible_for_nested_cv') else 'não'} | {'sim' if row.get('selected') else 'não'} | {row.get('reason') or ''} |"
            )
        lines.append("")

    lines.extend([
        "",
        "## Finalistas preliminares",
        "",
        f"- DF: {selected_df or '_nenhum_'}",
        f"- BC: {selected_bc or '_nenhum_'}",
        "",
        "## Problemas encontrados",
        "",
    ])
    if skipped or timed_out or errors:
        for r in skipped + timed_out + errors:
            bc_context = f" com `bc_min_df={r.get('bc_min_df')}`" if r.get("bc_min_df") is not None else ""
            lines.append(f"- `{r.get('algorithm')}` em `{r.get('representation')}`{bc_context}: {r.get('status')} — {r.get('error')}")
    else:
        lines.append("- Nenhum problema operacional encontrado.")

    lines.extend([
        "",
        "## Próximo passo",
        "",
        "Revisar este report e confirmar os 5 algoritmos finalistas de DF e os 5 finalistas de BC antes de rodar a nested CV da Fase E.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase-D spot-checking.")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument(
        "--bc-min-df-values",
        "--min-df-values",
        dest="bc_min_df_values",
        type=int,
        nargs="+",
        default=[1, 5, 10, 20],
        help="BC-only document-frequency thresholds for pruning cards. `--min-df-values` is a deprecated alias.",
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
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    features, bags = load_modeling_data(args.processed_dir)
    y = target_vector(features)

    if args.max_rows is not None and args.max_rows < len(y):
        indices = np.arange(len(y))
        sample_idx, _ = train_test_split(
            indices,
            train_size=args.max_rows,
            stratify=y,
            random_state=args.random_state,
        )
        sample_idx = np.sort(sample_idx)
        features = [features[i] for i in sample_idx]
        bags = [bags[i] for i in sample_idx]
        y = y[sample_idx]

    indices = np.arange(len(y))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=args.test_size,
        stratify=y,
        random_state=args.random_state,
    )
    features_train = [features[i] for i in train_idx]
    features_test = [features[i] for i in test_idx]
    bags_train = [bags[i] for i in train_idx]
    bags_test = [bags[i] for i in test_idx]
    y_train = y[train_idx]
    y_test = y[test_idx]

    results: List[Dict[str, Any]] = []
    for representation in args.representations:
        bc_min_df_values = args.bc_min_df_values if representation == "BC" else [None]
        for bc_min_df in bc_min_df_values:
            for algorithm in algorithms_for_representation(representation, args.algorithms):
                completed_times = [
                    float(record["elapsed_seconds"])
                    for record in results
                    if record.get("status") == "ok" and record.get("elapsed_seconds") is not None
                ]
                timeout_seconds = None
                if representation == "BC" and algorithm == "gradient_boosting" and completed_times:
                    timeout_seconds = 10 * max(completed_times)

                result = run_one_with_timeout(
                    timeout_seconds,
                    algorithm=algorithm,
                    representation=representation,
                    bc_min_df=bc_min_df,
                    features_train=features_train,
                    features_test=features_test,
                    bags_train=bags_train,
                    bags_test=bags_test,
                    y_train=y_train,
                    y_test=y_test,
                    random_state=args.random_state,
                    n_jobs=args.n_jobs,
                )
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
                results.append(result)

    best_bc_min_df = select_best_bc_min_df(results)
    rankings = finalist_ranking_by_representation(results, best_bc_min_df, args.algorithms)

    args.experiment_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.experiment_dir / "results.jsonl", results)
    timed_out = [record for record in results if record.get("status") == "timeout"]
    summary = {
        "parameters": {
            "processed_dir": str(args.processed_dir),
            "random_state": args.random_state,
            "test_size": args.test_size,
            "bc_min_df_values": args.bc_min_df_values,
            "algorithms": args.algorithms,
            "representations": args.representations,
            "max_rows": args.max_rows,
        },
        "n_rows": int(len(y)),
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "class_counts": {str(label): int((y == label).sum()) for label in sorted(set(y))},
        "best_bc_min_df": best_bc_min_df,
        "timeouts": timed_out,
        "rankings": rankings,
    }
    write_json(args.experiment_dir / "summary.json", summary)
    write_report(
        path=args.docs_dir / "spot_check_results.md",
        results=results,
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
