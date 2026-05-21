#!/usr/bin/env python3
"""Phase E — leakage-safe nested cross-validation for the selected models."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import sklearn
from scipy import sparse
from scipy.stats import friedmanchisquare, rankdata, studentized_range, wilcoxon
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import ParameterGrid, StratifiedKFold, train_test_split
from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

try:
    from preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector, y2_value  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.preprocessing import BagOfCardsPreprocessor, DeckFeaturePreprocessor, iter_jsonl, target_vector, y2_value  # type: ignore

try:
    from sync_experiments_drive import (  # type: ignore
        bundle_has_content,
        upload_bundle as upload_bundle_archive,
        upload_model as upload_model_archive,
    )
except ImportError:  # pragma: no cover
    from scripts.sync_experiments_drive import (  # type: ignore
        bundle_has_content,
        upload_bundle as upload_bundle_archive,
        upload_model as upload_model_archive,
    )


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
NESTED_CV_REPORT_FILENAME = "phase_e_nested_cv.md"
STATS_REPORT_FILENAME = "phase_e_statistical_tests.md"
DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_EXPERIMENTS_DRIVE_REMOTE = os.environ.get("MTG_EXPERIMENTS_DRIVE_REMOTE", "mtg-experiments:")
DEFAULT_SPOT_CHECK_SUMMARY = Path("experiments/spot_check/summary.json")
SELECTED_ALGORITHMS = (
    "decision_tree",
    "gradient_boosting",
    "knn",
    "linear_svc",
    "logistic_regression",
    "naive_bayes",
    "random_forest",
)
REPRESENTATIONS = ("DF", "BC")
LABELS = [2, 3, 4]
FEATURE_CHOICES = tuple(representation.lower() for representation in REPRESENTATIONS)


@dataclass(frozen=True)
class VotingSpec:
    name: str
    description: str
    bc_count: Optional[int]
    df_count: Optional[int]


VOTING_SPECS: Tuple[VotingSpec, ...] = (
    VotingSpec("voting_top3_BC", "Top-3 modelos BC", 3, 0),
    VotingSpec("voting_top5_BC", "Top-5 modelos BC", 5, 0),
    VotingSpec("voting_top3_DF", "Top-3 modelos DF", 0, 3),
    VotingSpec("voting_top5_DF", "Top-5 modelos DF", 0, 5),
    VotingSpec("voting_top3_BC_DF", "Top-3 BC + Top-3 DF", 3, 3),
    VotingSpec("voting_all", "Todos os modelos individuais disponíveis", None, None),
)


class SparseToDenseTransformer(BaseEstimator, TransformerMixin):
    """Convert sparse BC matrices to dense arrays for estimators that need dense X."""

    def fit(self, X: Any, y: Any = None) -> "SparseToDenseTransformer":
        return self

    def transform(self, X: Any) -> np.ndarray:
        if sparse.issparse(X):
            return X.toarray()
        return np.asarray(X)


def sklearn_at_least(major: int, minor: int) -> bool:
    """Return whether the imported sklearn is at least major.minor."""
    try:
        current = tuple(int(part) for part in sklearn.__version__.split(".")[:2])
    except (AttributeError, TypeError, ValueError):
        return False
    return current >= (major, minor)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def print_progress(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "?"
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def progress_bar(completed: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    completed = max(0, min(completed, total))
    filled = int(round(width * completed / total))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def print_outer_fold_progress(
    *,
    model_name: str,
    completed: int,
    total: int,
    started: float,
    quiet: bool,
    note: str = "",
) -> None:
    if quiet:
        return
    elapsed = time.monotonic() - started
    remaining = max(total - completed, 0)
    eta = (elapsed / completed * remaining) if completed else None
    suffix = f" | {note}" if note else ""
    print(
        f"[Phase E {model_name}] {progress_bar(completed, total)} "
        f"{completed}/{total} outer folds | remaining={remaining} | elapsed={format_duration(elapsed)} "
        f"| eta={format_duration(eta)}{suffix}",
        file=sys.stderr,
        flush=True,
    )


def print_inner_grid_progress(
    *,
    model_name: str,
    fold_id: str,
    completed: int,
    total: int,
    started: float,
    quiet: bool,
    note: str = "",
) -> None:
    if quiet:
        return
    elapsed = time.monotonic() - started
    remaining = max(total - completed, 0)
    eta = (elapsed / completed * remaining) if completed else None
    suffix = f" | {note}" if note else ""
    print(
        f"[Phase E {model_name} outer={fold_id}] {progress_bar(completed, total)} "
        f"{completed}/{total} grid configs trained | remaining={remaining} "
        f"| elapsed={format_duration(elapsed)} | eta={format_duration(eta)}{suffix}",
        file=sys.stderr,
        flush=True,
    )


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
    return algorithm in {"logistic_regression", "linear_svc", "knn"}


def estimator_for(algorithm: str, representation: str, random_state: int, n_jobs: int) -> BaseEstimator:
    if algorithm == "decision_tree":
        return DecisionTreeClassifier(random_state=random_state)
    if algorithm == "gradient_boosting":
        return HistGradientBoostingClassifier(random_state=random_state)
    if algorithm == "knn":
        return KNeighborsClassifier(n_jobs=n_jobs)
    if algorithm == "logistic_regression":
        # l1_ratio swept by the grid covers the full regularization spectrum:
        # 0.0 ≡ L2, 0.5 = ElasticNet mix, 1.0 ≡ L1. sklearn >=1.8 deprecated
        # explicit penalty=... in favor of l1_ratio/C, while older sklearn
        # needs penalty='elasticnet' for l1_ratio to have effect.
        kwargs = dict(
            max_iter=5000,
            solver="saga",
            random_state=random_state,
        )
        if not sklearn_at_least(1, 8):
            kwargs["penalty"] = "elasticnet"
        return LogisticRegression(**kwargs)
    if algorithm == "random_forest":
        return RandomForestClassifier(random_state=random_state, n_jobs=n_jobs)
    if algorithm == "linear_svc":
        return LinearSVC(random_state=random_state, dual="auto", loss="squared_hinge", max_iter=10000)
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
        if algorithm in {"gradient_boosting", "decision_tree"}:
            # HistGradientBoosting expects dense; DecisionTree's sparse split is slow
            # at this dimensionality, so we densify both for symmetry with spot-check.
            steps.append(("dense", SparseToDenseTransformer()))
        steps.append(("clf", estimator_for(algorithm, representation, random_state, n_jobs)))
    else:
        raise ValueError(f"Unknown representation: {representation}")
    return Pipeline(steps)


MAX_GRID_CONFIGS = 192


def full_param_grid(algorithm: str, representation: str) -> Dict[str, List[Any]]:
    """Hyperparameter grids kept below the project's practical budget.

    The budget is an order-of-magnitude guardrail, not a hard 128-config cap:
    grids up to 192 configurations are acceptable, while larger searches are
    avoided to keep nested CV feasible.
    """
    if algorithm == "decision_tree":
        return {
            "clf__max_depth": [None, 5, 10, 20, 40],
            "clf__min_samples_leaf": [1, 2, 5, 10],
            "clf__ccp_alpha": [0.0, 0.005],
            "clf__criterion": ["gini", "entropy"],
            "clf__class_weight": [None, "balanced"],
        }
    if algorithm == "gradient_boosting":
        return {
            "clf__max_iter": [100, 200, 300, 500],
            "clf__learning_rate": [0.01, 0.05, 0.1],
            "clf__max_leaf_nodes": [15, 31, 63],
            "clf__l2_regularization": [0.0, 0.1],
            "clf__class_weight": [None, "balanced"],
        }
    if algorithm == "knn":
        return {
            "clf__n_neighbors": [1, 3, 5, 7, 9, 11, 13, 15, 19, 25, 31, 41, 51, 71, 101],
            "clf__weights": ["uniform", "distance"],
            "clf__p": [1, 2],
        }
    if algorithm == "logistic_regression":
        # 16 C × 2 class_weight × 3 l1_ratio = 96 configs.
        # l1_ratio covers L2, ElasticNet, and L1 in sklearn >=1.8; older
        # sklearn gets penalty='elasticnet' in estimator_for for compatibility.
        return {
            "clf__C": [
                0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3,
                1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0,
            ],
            "clf__class_weight": [None, "balanced"],
            "clf__l1_ratio": [0.0, 0.5, 1.0],
        }
    if algorithm == "random_forest":
        return {
            "clf__n_estimators": [100, 250, 500, 1000],
            "clf__max_depth": [10, 20, 40, None],
            "clf__max_features": ["sqrt", "log2"],
            "clf__min_samples_leaf": [1, 2, 4],
            "clf__class_weight": [None, "balanced"],
        }
    if algorithm == "linear_svc":
        # 24 C × 2 class_weight × 2 penalty = 96 configs.
        # fit_intercept removed (default True is essentially universal best per
        # Hastie et al. §4.4 and LIBLINEAR/Fan et al. 2008); budget recycled
        # into finer C resolution.
        return {
            "clf__C": [
                0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005,
                0.01, 0.02, 0.05, 0.1, 0.2, 0.5,
                1.0, 2.0, 5.0, 10.0, 20.0, 50.0,
                100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0,
            ],
            "clf__class_weight": [None, "balanced"],
            "clf__penalty": ["l1", "l2"],
        }
    if algorithm == "naive_bayes" and representation == "BC":
        return {
            "clf__alpha": list(np.logspace(-4, 2, 48)),
            "clf__fit_prior": [True, False],
        }
    if algorithm == "naive_bayes" and representation == "DF":
        return {"clf__var_smoothing": list(np.logspace(-12, -3, 96))}
    raise ValueError(f"No grid for {representation}/{algorithm}")


def shrink_grid(grid: Mapping[str, Sequence[Any]], max_values: Optional[int]) -> Dict[str, List[Any]]:
    if max_values is None:
        return {key: list(values) for key, values in grid.items()}
    return {key: list(values)[:max_values] for key, values in grid.items()}


def resolve_model_selection(args: argparse.Namespace) -> Tuple[List[str], List[str]]:
    representations = [str(args.feature).upper()] if args.feature else list(args.representations)
    algorithms = [str(args.model)] if args.model else list(args.algorithms)
    return representations, algorithms


def read_spot_check_selection(summary_path: Path) -> Dict[str, List[str]]:
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Spot-check selection not found at {summary_path}. "
            f"Run `uv run run-mtg-pipeline spot-checking` to generate it, "
            f"or pass `--no-from-spot-check` to train every algorithm × representation directly."
        )
    summary = read_json(summary_path)
    selection = summary.get("selection") or {}
    if not selection.get("top5_DF") and not selection.get("top5_BC"):
        raise ValueError(
            f"Spot-check summary at {summary_path} has empty top-5 lists. "
            f"Re-run phase-d-spot-check or pass `--no-from-spot-check`."
        )
    return {
        "DF": list(selection.get("top5_DF") or []),
        "BC": list(selection.get("top5_BC") or []),
    }


def build_model_plan(
    args: argparse.Namespace,
    representations: Sequence[str],
    algorithms: Sequence[str],
) -> List[Tuple[str, str]]:
    """Decide which (representation, algorithm) pairs to train.

    With --from-spot-check we take the union of top-5 BC and top-5 DF (5 to 7
    algorithms) and train *each algorithm in both requested representations* —
    not only in the side where it placed in the top-5. That keeps the BC vs DF
    comparison fair for every algorithm that survived the spot-check.
    """
    if args.from_spot_check and args.model is None and args.feature is None:
        per_rep = read_spot_check_selection(args.spot_check_summary)
        union = sorted(set(per_rep.get("DF", [])) | set(per_rep.get("BC", [])))
        if not union:
            raise ValueError(
                "Spot-check selection is empty; re-run phase-d-spot-check or drop --from-spot-check."
            )
        plan: List[Tuple[str, str]] = []
        for rep in representations:
            for alg in union:
                plan.append((rep, alg))
        return plan
    return [(rep, alg) for rep in representations for alg in algorithms]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def checkpoint_signature_payload(
    *,
    model_name: str,
    representation: str,
    algorithm: str,
    folds: Sequence[Mapping[str, Any]],
    grid: Mapping[str, Sequence[Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "model_id": model_name,
        "representation": representation,
        "algorithm": algorithm,
        "bc_min_df": args.bc_min_df,
        "use_tfidf": args.use_tfidf,
        "outer_splits": args.outer_splits,
        "inner_splits": args.inner_splits,
        "repeats": args.repeats,
        "random_state": args.random_state,
        "max_rows": args.max_rows,
        "max_grid_values": args.max_grid_values,
        "grid": jsonable(grid),
        "fold_ids": [str(fold["fold_id"]) for fold in folds],
    }


def checkpoint_signature_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(jsonable(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def fold_checkpoint_path(checkpoint_dir: Path, fold_id: str) -> Path:
    return checkpoint_dir / f"{fold_id}.json"


def load_fold_checkpoint(path: Path, signature_id: str) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("signature_id") != signature_id:
        return None
    required = {"metrics", "best_params", "predictions", "cv_results"}
    if not required.issubset(payload):
        return None
    return payload


def write_checkpoint_state(
    *,
    out_dir: Path,
    signature_id: str,
    signature: Mapping[str, Any],
    checkpoint_dir: Path,
    completed_fold_ids: Sequence[str],
    total_folds: int,
) -> None:
    write_json_atomic(out_dir / "checkpoint_state.json", {
        "schema_version": 1,
        "signature_id": signature_id,
        "signature": jsonable(signature),
        "checkpoint_dir": str(checkpoint_dir),
        "completed_fold_ids": list(completed_fold_ids),
        "completed_folds": len(completed_fold_ids),
        "total_folds": total_folds,
        "updated_at": utc_now(),
    })


def enqueue_drive_upload(
    *,
    executor: ThreadPoolExecutor,
    model_name: str,
    args: argparse.Namespace,
) -> Future:
    print_progress(
        f"[Phase E drive] scheduling upload for {model_name} to {args.experiments_drive_remote}",
        args.quiet_progress,
    )
    return executor.submit(
        upload_model_archive,
        model_name,
        experiment_dir=args.experiment_dir,
        remote=args.experiments_drive_remote,
        rclone_bin=args.rclone_bin,
    )


def enqueue_bundle_drive_upload(
    *,
    executor: ThreadPoolExecutor,
    bundle_id: str,
    args: argparse.Namespace,
) -> Future:
    print_progress(
        f"[Phase E drive] scheduling bundle upload {bundle_id} → {args.experiments_drive_remote}",
        args.quiet_progress,
    )
    return executor.submit(
        upload_bundle_archive,
        bundle_id,
        experiment_dir=args.experiment_dir,
        remote=args.experiments_drive_remote,
        rclone_bin=args.rclone_bin,
    )


def collect_drive_uploads(
    upload_futures: Sequence[Tuple[str, Future]],
    *,
    quiet: bool,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    records: List[Dict[str, Any]] = []
    problems: List[str] = []
    for model_name, future in upload_futures:
        try:
            record = future.result()
        except Exception as exc:  # Upload failure must not invalidate model metrics.
            record = {
                "status": "failed",
                "model_id": model_name,
                "error": str(exc),
            }
        records.append(record)
        status = record.get("status")
        if status != "ok":
            problems.append(f"Drive upload failed for {model_name}: {record.get('error') or status}")
        if not quiet:
            print(
                f"[Phase E drive] upload {model_name}: {status}",
                file=sys.stderr,
                flush=True,
            )
    return records, problems


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


def inner_grid_search_with_progress(
    *,
    estimator: Pipeline,
    param_grid: Mapping[str, Sequence[Any]],
    scoring: str,
    cv: StratifiedKFold,
    x_train: Sequence[Mapping[str, Any]],
    y_train: np.ndarray,
    model_name: str,
    fold_id: str,
    quiet: bool,
) -> Dict[str, Any]:
    if scoring != "f1_macro":
        raise ValueError(f"Unsupported scoring: {scoring}")

    candidates = list(ParameterGrid(param_grid))
    total = len(candidates)
    if total == 0:
        raise ValueError("Empty hyperparameter grid.")

    fold_started = time.monotonic()
    update_every = max(1, total // 100)
    split_indices = list(cv.split(np.arange(len(y_train)), y_train))
    split_scores: List[List[float]] = []
    split_fit_times: List[List[float]] = []
    split_score_times: List[List[float]] = []

    print_inner_grid_progress(
        model_name=model_name,
        fold_id=fold_id,
        completed=0,
        total=total,
        started=fold_started,
        quiet=quiet,
        note="starting inner grid",
    )

    for config_index, params in enumerate(candidates, start=1):
        candidate_scores: List[float] = []
        candidate_fit_times: List[float] = []
        candidate_score_times: List[float] = []
        for inner_train_idx, inner_valid_idx in split_indices:
            candidate = clone(estimator)
            candidate.set_params(**params)
            x_inner_train = subset_rows(x_train, inner_train_idx)
            x_inner_valid = subset_rows(x_train, inner_valid_idx)
            y_inner_train = y_train[inner_train_idx]
            y_inner_valid = y_train[inner_valid_idx]

            fit_started = time.monotonic()
            candidate.fit(x_inner_train, y_inner_train)
            candidate_fit_times.append(time.monotonic() - fit_started)

            score_started = time.monotonic()
            y_inner_pred = candidate.predict(x_inner_valid)
            candidate_score_times.append(time.monotonic() - score_started)
            candidate_scores.append(float(f1_score(y_inner_valid, y_inner_pred, average="macro", zero_division=0)))

        split_scores.append(candidate_scores)
        split_fit_times.append(candidate_fit_times)
        split_score_times.append(candidate_score_times)

        if config_index == 1 or config_index == total or config_index % update_every == 0:
            print_inner_grid_progress(
                model_name=model_name,
                fold_id=fold_id,
                completed=config_index,
                total=total,
                started=fold_started,
                quiet=quiet,
            )

    mean_scores = np.asarray([np.mean(scores) for scores in split_scores], dtype=float)
    std_scores = np.asarray([np.std(scores, ddof=0) for scores in split_scores], dtype=float)
    ranks = rankdata(-mean_scores, method="min").astype(int)
    best_index = int(np.argmax(mean_scores))
    best_params = candidates[best_index]

    best_estimator = clone(estimator)
    best_estimator.set_params(**best_params)
    best_estimator.fit(x_train, y_train)

    cv_results: Dict[str, Any] = {
        "params": candidates,
        "mean_test_score": mean_scores,
        "std_test_score": std_scores,
        "rank_test_score": ranks,
        "mean_fit_time": np.asarray([np.mean(times) for times in split_fit_times], dtype=float),
        "std_fit_time": np.asarray([np.std(times, ddof=0) for times in split_fit_times], dtype=float),
        "mean_score_time": np.asarray([np.mean(times) for times in split_score_times], dtype=float),
        "std_score_time": np.asarray([np.std(times, ddof=0) for times in split_score_times], dtype=float),
    }
    for split_index in range(len(split_indices)):
        cv_results[f"split{split_index}_test_score"] = np.asarray(
            [scores[split_index] for scores in split_scores],
            dtype=float,
        )

    return {
        "best_estimator": best_estimator,
        "best_params": best_params,
        "best_score": float(mean_scores[best_index]),
        "cv_results": cv_results,
    }


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
    grid = shrink_grid(full_param_grid(algorithm, representation), args.max_grid_values)
    signature = checkpoint_signature_payload(
        model_name=model_name,
        representation=representation,
        algorithm=algorithm,
        folds=folds,
        grid=grid,
        args=args,
    )
    signature_id = checkpoint_signature_id(signature)
    checkpoint_dir = out_dir / "checkpoints" / signature_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    fold_metrics_by_id: Dict[str, Dict[str, Any]] = {}
    best_params_by_id: Dict[str, Dict[str, Any]] = {}
    predictions_by_id: Dict[str, List[Dict[str, Any]]] = {}
    cv_results_by_id: Dict[str, List[Dict[str, Any]]] = {}
    fold_ids = [str(fold["fold_id"]) for fold in folds]
    model_started = time.monotonic()

    if not args.force_rerun:
        for fold in folds:
            fold_id = str(fold["fold_id"])
            checkpoint = load_fold_checkpoint(fold_checkpoint_path(checkpoint_dir, fold_id), signature_id)
            if checkpoint is None:
                continue
            fold_metrics_by_id[fold_id] = checkpoint["metrics"]
            best_params_by_id[fold_id] = checkpoint["best_params"]
            predictions_by_id[fold_id] = checkpoint["predictions"]
            cv_results_by_id[fold_id] = checkpoint["cv_results"]

    completed_ids = [fold_id for fold_id in fold_ids if fold_id in fold_metrics_by_id]
    write_checkpoint_state(
        out_dir=out_dir,
        signature_id=signature_id,
        signature=signature,
        checkpoint_dir=checkpoint_dir,
        completed_fold_ids=completed_ids,
        total_folds=len(folds),
    )
    print_outer_fold_progress(
        model_name=model_name,
        completed=len(completed_ids),
        total=len(folds),
        started=model_started,
        quiet=args.quiet_progress,
        note="resumed from checkpoint" if completed_ids else "starting",
    )

    for fold_index, fold in enumerate(folds, start=1):
        fold_id = str(fold["fold_id"])
        if fold_id in fold_metrics_by_id:
            print_progress(
                f"[Phase E model {model_index}/{total_models} fold {fold_index}/{len(folds)}] SKIP  "
                f"model={model_name} | outer={fold_id} | checkpoint=complete",
                args.quiet_progress,
            )
            continue

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
        config_parts = [
            f"model={model_name}",
            f"representation={representation}",
            f"algorithm={algorithm}",
            f"outer={fold_id}",
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
        completed_before_fold = len([current_fold_id for current_fold_id in fold_ids if current_fold_id in fold_metrics_by_id])
        print_outer_fold_progress(
            model_name=model_name,
            completed=completed_before_fold,
            total=len(folds),
            started=model_started,
            quiet=args.quiet_progress,
            note=f"running outer={fold_id}",
        )
        print_progress(
            f"\n[Phase E model {model_index}/{total_models} fold {fold_index}/{len(folds)}] START "
            + " | ".join(config_parts),
            args.quiet_progress,
        )
        x_train = subset_rows(rows, train_idx)
        x_test = subset_rows(rows, test_idx)
        y_train = y[train_idx]
        y_test = y[test_idx]
        if args.grid_n_jobs != 1:
            print_progress(
                "[Phase E] Note: --grid-n-jobs is ignored by the custom progress-aware grid search; "
                "use --estimator-n-jobs for estimator-level parallelism.",
                args.quiet_progress,
            )
        search = inner_grid_search_with_progress(
            estimator=pipeline,
            param_grid=grid,
            scoring="f1_macro",
            cv=inner_cv,
            x_train=x_train,
            y_train=y_train,
            model_name=model_name,
            fold_id=fold_id,
            quiet=args.quiet_progress,
        )
        y_pred = search["best_estimator"].predict(x_test)
        fold_cv_results = cv_results_for_fold(
            search["cv_results"],
            model_name=model_name,
            representation=representation,
            algorithm=algorithm,
            repeat_seed=int(fold["repeat_seed"]),
            outer_fold=int(fold["outer_fold"]),
            fold_id=fold_id,
        )

        metrics = metric_record(y_test, y_pred)
        metrics.update({
            "model_id": model_name,
            "representation": representation,
            "algorithm": algorithm,
            "repeat_seed": int(fold["repeat_seed"]),
            "outer_fold": int(fold["outer_fold"]),
            "fold_id": fold_id,
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
            "inner_best_macro_f1": float(search["best_score"]),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        })
        best_param_record = {
            "model_id": model_name,
            "repeat_seed": int(fold["repeat_seed"]),
            "outer_fold": int(fold["outer_fold"]),
            "fold_id": fold_id,
            "best_params": search["best_params"],
            "inner_best_macro_f1": float(search["best_score"]),
        }

        fold_predictions: List[Dict[str, Any]] = []
        for idx, true_value, pred_value in zip(test_idx, y_test, y_pred):
            feature_row = feature_rows[int(idx)]
            fold_predictions.append({
                "model_id": model_name,
                "representation": representation,
                "algorithm": algorithm,
                "repeat_seed": int(fold["repeat_seed"]),
                "outer_fold": int(fold["outer_fold"]),
                "fold_id": fold_id,
                "row_index": int(idx),
                "snapshot_id": feature_row.get("snapshot_id"),
                "deck_id": feature_row.get("deck_id"),
                "y_true": int(true_value),
                "y_pred": int(pred_value),
                "y2": y2_value(feature_row),
            })
        fold_checkpoint = {
            "schema_version": 1,
            "signature_id": signature_id,
            "signature": jsonable(signature),
            "model_id": model_name,
            "representation": representation,
            "algorithm": algorithm,
            "fold_id": fold_id,
            "completed_at": utc_now(),
            "metrics": metrics,
            "best_params": best_param_record,
            "predictions": fold_predictions,
            "cv_results": fold_cv_results,
        }
        write_json_atomic(fold_checkpoint_path(checkpoint_dir, fold_id), fold_checkpoint)
        fold_metrics_by_id[fold_id] = metrics
        best_params_by_id[fold_id] = best_param_record
        predictions_by_id[fold_id] = fold_predictions
        cv_results_by_id[fold_id] = fold_cv_results
        completed_ids = [current_fold_id for current_fold_id in fold_ids if current_fold_id in fold_metrics_by_id]
        write_checkpoint_state(
            out_dir=out_dir,
            signature_id=signature_id,
            signature=signature,
            checkpoint_dir=checkpoint_dir,
            completed_fold_ids=completed_ids,
            total_folds=len(folds),
        )
        print(json.dumps({
            "model_id": model_name,
            "fold_id": fold_id,
            "macro_f1": metrics["macro_f1"],
            "best_params": search["best_params"],
            "elapsed_seconds": metrics["elapsed_seconds"],
        }, ensure_ascii=False, sort_keys=True))
        print_progress(
            f"[Phase E model {model_index}/{total_models} fold {fold_index}/{len(folds)}] DONE  "
            f"model={model_name} | outer={fold_id} | macro_f1={metrics['macro_f1']:.4f} "
            f"| inner_best={search['best_score']:.4f} | elapsed={metrics['elapsed_seconds']}s "
            f"| best_params={search['best_params']}",
            args.quiet_progress,
        )
        print_outer_fold_progress(
            model_name=model_name,
            completed=len(completed_ids),
            total=len(folds),
            started=model_started,
            quiet=args.quiet_progress,
        )

    missing_fold_ids = [fold_id for fold_id in fold_ids if fold_id not in fold_metrics_by_id]
    if missing_fold_ids:
        raise RuntimeError(f"Model {model_name} did not complete all outer folds: missing={missing_fold_ids}")

    fold_metrics = [fold_metrics_by_id[fold_id] for fold_id in fold_ids]
    best_params = [best_params_by_id[fold_id] for fold_id in fold_ids]
    predictions = [
        prediction
        for fold_id in fold_ids
        for prediction in predictions_by_id[fold_id]
    ]
    cv_results = [
        record
        for fold_id in fold_ids
        for record in cv_results_by_id[fold_id]
    ]
    metrics_payload = {
        "model_id": model_name,
        "representation": representation,
        "algorithm": algorithm,
        "folds": fold_metrics,
        "aggregate": aggregate_metrics(fold_metrics),
        "checkpoint": {
            "signature_id": signature_id,
            "checkpoint_dir": str(checkpoint_dir),
            "completed_folds": len(fold_metrics),
            "total_folds": len(folds),
        },
    }
    write_json(out_dir / "metrics_per_fold.json", metrics_payload)
    write_json(out_dir / "best_hyperparams_per_fold.json", best_params)
    write_jsonl(out_dir / "cv_results_per_fold.jsonl", cv_results)
    write_jsonl(out_dir / "predictions_per_fold.jsonl", predictions)
    return metrics_payload


def cv_results_for_fold(
    cv_results: Mapping[str, Any],
    *,
    model_name: str,
    representation: str,
    algorithm: str,
    repeat_seed: int,
    outer_fold: int,
    fold_id: str,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    params = cv_results.get("params", [])
    split_score_keys = sorted(
        key for key in cv_results
        if key.startswith("split") and key.endswith("_test_score")
    )
    for index, config in enumerate(params):
        record: Dict[str, Any] = {
            "model_id": model_name,
            "representation": representation,
            "algorithm": algorithm,
            "repeat_seed": repeat_seed,
            "outer_fold": outer_fold,
            "fold_id": fold_id,
            "config_index": int(index),
            "params": jsonable(config),
            "mean_test_macro_f1": jsonable(cv_results["mean_test_score"][index]),
            "std_test_macro_f1": jsonable(cv_results["std_test_score"][index]),
            "rank_test_macro_f1": jsonable(cv_results["rank_test_score"][index]),
            "mean_fit_time": jsonable(cv_results["mean_fit_time"][index]),
            "std_fit_time": jsonable(cv_results["std_fit_time"][index]),
            "mean_score_time": jsonable(cv_results["mean_score_time"][index]),
            "std_score_time": jsonable(cv_results["std_score_time"][index]),
        }
        for key in split_score_keys:
            record[key.replace("_test_score", "_test_macro_f1")] = jsonable(cv_results[key][index])
        records.append(record)
    return records


def load_existing_model_metrics(experiment_dir: Path, model_name: str) -> Optional[Dict[str, Any]]:
    path = experiment_dir / model_name / "metrics_per_fold.json"
    if not path.exists():
        return None
    return read_json(path)


def read_oof_predictions(model_dir: Path) -> List[Dict[str, Any]]:
    """Read out-of-fold predictions persisted by a base model."""
    path = model_dir / "predictions_per_fold.jsonl"
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def select_voting_members(
    model_metrics: Sequence[Mapping[str, Any]],
    spec: VotingSpec,
) -> Optional[List[str]]:
    """Return ordered list of model_ids that should participate in the ensemble."""
    by_rep: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in model_metrics:
        rep = str(row.get("representation"))
        aggregate = row.get("aggregate") or {}
        if aggregate.get("macro_f1_mean") is None:
            continue
        by_rep[rep].append(row)
    for rep in by_rep:
        by_rep[rep].sort(key=lambda m: float(m["aggregate"]["macro_f1_mean"]), reverse=True)

    if spec.bc_count is None and spec.df_count is None:
        chosen = list(by_rep.get("BC", [])) + list(by_rep.get("DF", []))
        if len(chosen) < 2:
            return None
        return [str(row["model_id"]) for row in chosen]

    bc_need = spec.bc_count or 0
    df_need = spec.df_count or 0
    if len(by_rep.get("BC", [])) < bc_need or len(by_rep.get("DF", [])) < df_need:
        return None
    chosen = list(by_rep.get("BC", []))[:bc_need] + list(by_rep.get("DF", []))[:df_need]
    return [str(row["model_id"]) for row in chosen]


def hard_vote(
    predictions: Sequence[int] | Mapping[str, int],
    *,
    member_scores: Optional[Mapping[str, float]] = None,
) -> int:
    """Majority vote with macro-F1 tie-break and deterministic fallback."""
    if isinstance(predictions, Mapping):
        prediction_items = [(str(member), int(prediction)) for member, prediction in predictions.items()]
    else:
        prediction_items = [(str(index), int(prediction)) for index, prediction in enumerate(predictions)]
    counts = Counter(prediction for _member, prediction in prediction_items)
    if not counts:
        raise ValueError("Cannot vote over an empty list of predictions")
    max_count = max(counts.values())
    tied_labels = [label for label, count in counts.items() if count == max_count]
    if len(tied_labels) == 1:
        return tied_labels[0]
    if member_scores:
        label_scores: Dict[int, float] = {}
        for label in tied_labels:
            scores = [
                float(member_scores[member])
                for member, prediction in prediction_items
                if prediction == label and member in member_scores
            ]
            label_scores[label] = float(np.mean(scores)) if scores else -math.inf
        best_score = max(label_scores.values())
        tied_labels = [label for label in tied_labels if label_scores[label] == best_score]
    return min(tied_labels)


def compute_voting_metrics(
    members: Sequence[str],
    experiment_dir: Path,
    member_scores: Optional[Mapping[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Compute hard-voting per (fold, row) and per-fold metrics."""
    member_predictions: Dict[str, List[Dict[str, Any]]] = {}
    for member_id in members:
        rows = read_oof_predictions(experiment_dir / member_id)
        if not rows:
            return None
        member_predictions[member_id] = rows

    by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for member_id, rows in member_predictions.items():
        for row in rows:
            key = (str(row["fold_id"]), int(row["row_index"]))
            entry = by_key.setdefault(key, {
                "fold_id": str(row["fold_id"]),
                "row_index": int(row["row_index"]),
                "snapshot_id": row.get("snapshot_id"),
                "deck_id": row.get("deck_id"),
                "y_true": int(row["y_true"]),
                "y2": row.get("y2"),
                "per_member_preds": {},
            })
            entry["per_member_preds"][member_id] = int(row["y_pred"])

    expected = len(members)
    voted_rows: List[Dict[str, Any]] = []
    for entry in by_key.values():
        if len(entry["per_member_preds"]) != expected:
            return None
        entry["y_pred"] = int(hard_vote(entry["per_member_preds"], member_scores=member_scores))
        voted_rows.append(entry)

    by_fold: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in voted_rows:
        by_fold[entry["fold_id"]].append(entry)

    fold_metrics: List[Dict[str, Any]] = []
    for fold_id in sorted(by_fold):
        rows = by_fold[fold_id]
        y_true = np.asarray([r["y_true"] for r in rows], dtype=int)
        y_pred = np.asarray([r["y_pred"] for r in rows], dtype=int)
        metric = metric_record(y_true, y_pred)
        metric.update({
            "fold_id": fold_id,
            "n_test": len(rows),
        })
        fold_metrics.append(metric)

    return {
        "fold_metrics": fold_metrics,
        "aggregate": aggregate_metrics(fold_metrics),
        "predictions": voted_rows,
    }


def run_voting_ensembles(
    model_metrics: Sequence[Mapping[str, Any]],
    *,
    experiment_dir: Path,
    quiet: bool,
) -> Dict[str, Any]:
    """Compute all configured voting ensembles using saved OOF predictions."""
    voting_dir = experiment_dir / "voting"
    voting_dir.mkdir(parents=True, exist_ok=True)
    ensembles: List[Dict[str, Any]] = []
    problems: List[str] = []
    member_scores = {
        str(row["model_id"]): float((row.get("aggregate") or {})["macro_f1_mean"])
        for row in model_metrics
        if (row.get("aggregate") or {}).get("macro_f1_mean") is not None
    }
    for spec in VOTING_SPECS:
        members = select_voting_members(model_metrics, spec)
        if not members:
            print_progress(f"[Phase E voting] skip {spec.name}: insufficient members", quiet)
            ensembles.append({
                "voting_id": spec.name,
                "description": spec.description,
                "status": "skipped",
                "reason": "insufficient_members",
                "members": [],
            })
            continue
        result = compute_voting_metrics(members, experiment_dir, member_scores=member_scores)
        if result is None:
            problems.append(f"voting {spec.name}: missing or misaligned predictions for members {members}")
            ensembles.append({
                "voting_id": spec.name,
                "description": spec.description,
                "status": "skipped",
                "reason": "missing_predictions",
                "members": members,
            })
            continue
        record = {
            "voting_id": spec.name,
            "description": spec.description,
            "status": "ok",
            "members": members,
            "n_members": len(members),
            "folds": result["fold_metrics"],
            "aggregate": result["aggregate"],
        }
        out_dir = voting_dir / spec.name
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "metrics_per_fold.json", {
            "voting_id": spec.name,
            "description": spec.description,
            "members": members,
            "folds": result["fold_metrics"],
            "aggregate": result["aggregate"],
        })
        write_jsonl(out_dir / "predictions_per_fold.jsonl", [
            {
                "voting_id": spec.name,
                "fold_id": entry["fold_id"],
                "row_index": entry["row_index"],
                "snapshot_id": entry.get("snapshot_id"),
                "deck_id": entry.get("deck_id"),
                "y_true": entry["y_true"],
                "y_pred": entry["y_pred"],
                "y2": entry.get("y2"),
                "per_member_preds": entry["per_member_preds"],
            }
            for entry in result["predictions"]
        ])
        ensembles.append(record)
        print_progress(
            f"[Phase E voting] {spec.name}: macro_f1_mean={record['aggregate']['macro_f1_mean']:.4f}"
            f" ± {record['aggregate']['macro_f1_std']:.4f} | members={members}",
            quiet,
        )
    write_json(voting_dir / "voting_summary.json", {"ensembles": ensembles})
    return {"ensembles": ensembles, "problems": problems}


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
        "Treinar os modelos individuais (10 a 14, cada algoritmo da união `A_DF ∪ A_BC` em ambas as representações), sempre prevendo `y1`, com nested cross-validation sem vazamento entre folds.",
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
        "- `experiments/<representação>_<algoritmo>/cv_results_per_fold.jsonl`",
        "- `experiments/<representação>_<algoritmo>/predictions_per_fold.jsonl`",
        "- `experiments/<representação>_<algoritmo>/checkpoint_state.json`",
        "- `experiments/<representação>_<algoritmo>/checkpoints/<assinatura>/<outer_fold>.json`",
        "- `experiments/archives/<representação>_<algoritmo>.zip` quando upload via Drive estiver habilitado",
        "- `documents/reports/results/phase_e_nested_cv.md`",
        "- `documents/reports/results/phase_e_statistical_tests.md`",
        "",
        "## Google Drive",
        "",
    ])
    uploads = summary.get("drive_uploads") or []
    if uploads:
        for upload in uploads:
            model = upload.get("model_id", "_geral_")
            lines.append(f"- `{model}`: {upload.get('status')}")
    else:
        lines.append("- Nenhum upload registrado nesta rodada.")

    lines.extend([
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


def write_voting_report(
    path: Path,
    ensembles: Sequence[Mapping[str, Any]],
    models: Sequence[Mapping[str, Any]],
) -> None:
    lines: List[str] = [
        "# Ensembles por votação",
        "",
        "Hard voting majoritário a partir das predições out-of-fold dos modelos individuais. Sem retreino. Empates são resolvidos pela maior macro-F1 média dos membros que votaram em cada classe; empate residual usa o menor rótulo numérico para manter reprodutibilidade.",
        "",
        "## Ensembles",
        "",
        "| Ensemble | Status | n_membros | Membros | Macro-F1 média | Macro-F1 dp | Accuracy média | Precision macro | Recall macro |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for ensemble in ensembles:
        agg = ensemble.get("aggregate") or {}
        members = ensemble.get("members") or []
        if ensemble.get("status") == "ok":
            lines.append(
                "| `{name}` | ok | {n} | {members} | {f1:.4f} | {f1_std:.4f} | {acc:.4f} | {prec:.4f} | {rec:.4f} |".format(
                    name=ensemble["voting_id"],
                    n=ensemble.get("n_members", len(members)),
                    members=", ".join(f"`{m}`" for m in members),
                    f1=agg.get("macro_f1_mean", 0.0),
                    f1_std=agg.get("macro_f1_std", 0.0),
                    acc=agg.get("accuracy_mean", 0.0),
                    prec=agg.get("precision_macro_mean", 0.0),
                    rec=agg.get("recall_macro_mean", 0.0),
                )
            )
        else:
            lines.append(
                f"| `{ensemble['voting_id']}` | {ensemble.get('status')} | {len(members)} | "
                f"{', '.join(f'`{m}`' for m in members) or '_n/a_'} |  |  |  |  |  |"
            )

    lines.extend([
        "",
        "## Modelos individuais (referência)",
        "",
        "| Modelo | Macro-F1 média | Macro-F1 dp |",
        "|---|---:|---:|",
    ])
    for row in models:
        agg = row.get("aggregate") or {}
        if agg.get("macro_f1_mean") is None:
            continue
        lines.append(
            f"| `{row['model_id']}` | {agg['macro_f1_mean']:.4f} | {agg.get('macro_f1_std', 0.0):.4f} |"
        )
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
    parser.add_argument(
        "--model",
        choices=SELECTED_ALGORITHMS,
        default=None,
        help="Model/algorithm to run. If omitted, runs all selected algorithms.",
    )
    parser.add_argument(
        "--feature",
        choices=FEATURE_CHOICES,
        default=None,
        help="Feature representation to run: `df` or `bc`. If omitted, runs both selected representations.",
    )
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument("--experiments-drive-remote", default=DEFAULT_EXPERIMENTS_DRIVE_REMOTE)
    parser.add_argument("--rclone-bin", default="rclone")
    parser.add_argument("--run-local", action="store_true", help="Do not upload completed model archives to Drive.")
    parser.add_argument(
        "--wait-drive-upload",
        dest="wait_drive_upload",
        action="store_true",
        default=True,
        help="Wait for background Drive uploads before exiting. Enabled by default.",
    )
    parser.add_argument(
        "--no-wait-drive-upload",
        dest="wait_drive_upload",
        action="store_false",
        help="Do not wait for background Drive uploads before writing the final summary.",
    )
    parser.add_argument("--representations", nargs="+", choices=REPRESENTATIONS, default=list(REPRESENTATIONS))
    parser.add_argument("--algorithms", nargs="+", choices=SELECTED_ALGORITHMS, default=list(SELECTED_ALGORITHMS))
    parser.add_argument("--bc-min-df", type=int, default=10)
    parser.add_argument("--use-tfidf", action="store_true")
    parser.add_argument("--outer-splits", type=int, default=5)
    parser.add_argument("--inner-splits", type=int, default=3)
    parser.add_argument("--repeats", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--grid-n-jobs",
        type=int,
        default=1,
        help="Reserved for future grid-level parallelism. Current progress-aware grid search runs sequentially.",
    )
    parser.add_argument("--grid-verbose", type=int, default=0, help="Reserved for future grid-search verbosity.")
    parser.add_argument("--estimator-n-jobs", type=int, default=-1)
    parser.add_argument("--max-rows", type=int, default=None, help="Optional stratified sample size for smoke tests.")
    parser.add_argument(
        "--max-grid-values",
        type=int,
        default=None,
        help="For smoke tests, keep only the first N values of each hyperparameter grid.",
    )
    parser.add_argument(
        "--no-merge-existing-models",
        dest="merge_existing_models",
        action="store_false",
        help="When running a subset, do not include already saved model metrics in the summary comparison.",
    )
    parser.set_defaults(merge_existing_models=True)
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore completed outer-fold checkpoints and recompute selected models.",
    )
    parser.add_argument(
        "--from-spot-check",
        action="store_true",
        help="Read top-5 per representation from --spot-check-summary and use them as the model plan.",
    )
    parser.add_argument(
        "--spot-check-summary",
        type=Path,
        default=DEFAULT_SPOT_CHECK_SUMMARY,
        help="Path to spot_check/summary.json with the top-5 selection.",
    )
    parser.add_argument(
        "--skip-voting",
        action="store_true",
        default=True,
        help="Compatibility flag; voting is not computed automatically by Phase E.",
    )
    parser.add_argument("--quiet-progress", action="store_true", help="Hide human-readable progress messages.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    started = time.monotonic()
    selected_representations, selected_algorithms = resolve_model_selection(args)
    drive_upload_records: List[Dict[str, Any]] = []
    drive_upload_problems: List[str] = []
    upload_futures: List[Tuple[str, Future]] = []
    upload_executor: Optional[ThreadPoolExecutor] = None
    upload_enabled = bool(args.experiments_drive_remote) and not args.run_local
    if args.run_local:
        drive_upload_records.append({"status": "skipped_run_local"})
    elif not args.experiments_drive_remote:
        drive_upload_records.append({"status": "skipped_no_remote", "env": "MTG_EXPERIMENTS_DRIVE_REMOTE"})
    else:
        upload_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phase-e-drive-upload")

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

    model_plan = build_model_plan(args, selected_representations, selected_algorithms)
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
        if upload_enabled and upload_executor is not None:
            upload_futures.append((
                str(result["model_id"]),
                enqueue_drive_upload(executor=upload_executor, model_name=str(result["model_id"]), args=args),
            ))

    result_by_model = {str(result["model_id"]): result for result in results}
    model_sources = {str(result["model_id"]): "current_run" for result in results}
    if args.merge_existing_models and args.max_rows is None:
        comparison_plan = [
            (representation, algorithm)
            for representation in selected_representations
            for algorithm in SELECTED_ALGORITHMS
        ]
        for representation, algorithm in comparison_plan:
            existing_model_name = model_id(representation, algorithm)
            if existing_model_name in result_by_model:
                continue
            existing = load_existing_model_metrics(args.experiment_dir, existing_model_name)
            if existing is not None:
                result_by_model[existing_model_name] = existing
                model_sources[existing_model_name] = "existing_artifact"

    combined_results = [
        result_by_model[model_id(representation, algorithm)]
        for representation in selected_representations
        for algorithm in SELECTED_ALGORITHMS
        if model_id(representation, algorithm) in result_by_model
    ]

    stats = statistical_payload(combined_results)

    # The shared bundle (seeds.json/folds.json) is uploaded after the per-model
    # archives so collaborators that restore from the manifest can reproduce
    # the experimental setup end-to-end. Voting is intentionally outside
    # Phase E in the updated project plan.
    if upload_enabled and upload_executor is not None:
        for bundle_id in ("shared",):
            if bundle_has_content(bundle_id, experiment_dir=args.experiment_dir):
                upload_futures.append((
                    f"bundle:{bundle_id}",
                    enqueue_bundle_drive_upload(executor=upload_executor, bundle_id=bundle_id, args=args),
                ))

    if upload_executor is not None:
        if args.wait_drive_upload:
            records, problems = collect_drive_uploads(upload_futures, quiet=args.quiet_progress)
            drive_upload_records.extend(records)
            drive_upload_problems.extend(problems)
            upload_executor.shutdown(wait=True)
        else:
            drive_upload_records.extend([
                {"status": "pending", "model_id": model_name}
                for model_name, _future in upload_futures
            ])
            upload_executor.shutdown(wait=False, cancel_futures=False)

    summary: Dict[str, Any] = {
        "status": "ok",
        "n_rows": int(len(y)),
        "class_counts": {str(label): int((y == label).sum()) for label in sorted(set(y))},
        "parameters": {
            "processed_dir": str(args.processed_dir),
            "docs_dir": str(args.docs_dir),
            "experiment_dir": str(args.experiment_dir),
            "experiments_drive_remote": args.experiments_drive_remote,
            "run_local": args.run_local,
            "wait_drive_upload": args.wait_drive_upload,
            "model_selector": args.model,
            "representations": selected_representations,
            "algorithms": selected_algorithms,
            "bc_min_df": args.bc_min_df,
            "use_tfidf": args.use_tfidf,
            "outer_splits": args.outer_splits,
            "inner_splits": args.inner_splits,
            "repeats": args.repeats,
            "random_state": args.random_state,
            "grid_n_jobs": args.grid_n_jobs,
            "grid_verbose": args.grid_verbose,
            "estimator_n_jobs": args.estimator_n_jobs,
            "max_rows": args.max_rows,
            "max_grid_values": args.max_grid_values,
            "merge_existing_models": args.merge_existing_models,
            "force_rerun": args.force_rerun,
            "from_spot_check": args.from_spot_check,
            "spot_check_summary": str(args.spot_check_summary),
            "skip_voting": args.skip_voting,
        },
        "model_sources": model_sources,
        "model_plan": [{"representation": rep, "algorithm": alg} for rep, alg in model_plan],
        "models": combined_results,
        "statistics": stats,
        "drive_uploads": drive_upload_records,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "problems": drive_upload_problems,
    }
    write_json(args.experiment_dir / "nested_cv_summary.json", summary)
    write_json(args.experiment_dir / "statistical_tests.json", stats)
    args.docs_dir.mkdir(parents=True, exist_ok=True)
    write_stats_report(args.docs_dir / STATS_REPORT_FILENAME, stats)
    write_report(args.docs_dir / NESTED_CV_REPORT_FILENAME, summary, stats)
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
