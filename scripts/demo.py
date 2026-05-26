#!/usr/bin/env python3
"""Build and serve the local browser demo for the MTG project."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse


LABELS = [2, 3, 4]
DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_DEMO_DIR = Path("demo")
DEFAULT_ASSET_DIR = DEFAULT_DEMO_DIR / "assets"

INDIVIDUAL_MODEL_IDS = [
    "df_gradient_boosting",
    "df_random_forest",
    "df_decision_tree",
    "df_logistic_regression",
    "df_linear_svc",
    "df_naive_bayes",
    "bc_gradient_boosting",
    "bc_random_forest",
    "bc_logistic_regression",
    "bc_linear_svc",
    "bc_naive_bayes",
    "bc_decision_tree",
]

ENSEMBLE_DEFINITIONS = {
    "voting_top3_BC": [
        "bc_gradient_boosting",
        "bc_random_forest",
        "bc_logistic_regression",
    ],
    "voting_top5_BC": [
        "bc_gradient_boosting",
        "bc_random_forest",
        "bc_logistic_regression",
        "bc_linear_svc",
        "bc_naive_bayes",
    ],
    "voting_top3_DF": [
        "df_gradient_boosting",
        "df_random_forest",
        "df_decision_tree",
    ],
    "voting_top5_DF": [
        "df_gradient_boosting",
        "df_random_forest",
        "df_decision_tree",
        "df_logistic_regression",
        "df_linear_svc",
    ],
    "voting_top3_BC_DF": [
        "bc_gradient_boosting",
        "bc_random_forest",
        "bc_logistic_regression",
        "df_gradient_boosting",
        "df_random_forest",
        "df_decision_tree",
    ],
    "voting_all": INDIVIDUAL_MODEL_IDS,
}

KEY_FEATURES = [
    "game_changer_count",
    "tutor_count",
    "mass_land_denial_count",
    "extra_turns_count",
    "unique_atomic_combo_refs_count",
    "potential_combo_refs_total",
    "price_total",
    "salt_mean",
    "edhrec_rank_mean",
    "deck_color_count",
    "land_count",
    "nonland_cmc_mean",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def finite_or_none(value: Any, *, ndigits: int = 3) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, ndigits)


def model_label(model_id: str) -> str:
    if model_id.startswith("df_"):
        return "DF " + model_id[3:].replace("_", " ")
    if model_id.startswith("bc_"):
        return "BC " + model_id[3:].replace("_", " ")
    return model_id.replace("_", " ")


def representation_for(model_id: str) -> str:
    if model_id.startswith("df_"):
        return "DF"
    if model_id.startswith("bc_"):
        return "BC"
    return "BC+DF"


def algorithm_for(model_id: str) -> str:
    if model_id.startswith(("df_", "bc_")):
        return model_id[3:]
    return "hard_voting"


def majority_label(values: Sequence[int], *, tie_scores: Optional[Mapping[int, float]] = None) -> Tuple[int, List[int], float]:
    counts = Counter(int(value) for value in values)
    max_count = max(counts.values())
    candidates = [label for label, count in counts.items() if count == max_count]
    if tie_scores:
        best_score = max(float(tie_scores.get(label, 0.0)) for label in candidates)
        candidates = [label for label in candidates if float(tie_scores.get(label, 0.0)) == best_score]
    label = min(candidates)
    count_vector = [counts.get(label_value, 0) for label_value in LABELS]
    confidence = counts[label] / max(1, len(values))
    return label, count_vector, round(confidence, 3)


def classification_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> Dict[str, Any]:
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    label_to_idx = {label: idx for idx, label in enumerate(LABELS)}
    for true, pred in zip(y_true, y_pred):
        if true in label_to_idx and pred in label_to_idx:
            matrix[label_to_idx[true]][label_to_idx[pred]] += 1

    per_class = []
    f1_values = []
    recall_values = []
    precision_values = []
    total = sum(sum(row) for row in matrix)
    correct = sum(matrix[idx][idx] for idx in range(len(LABELS)))
    for idx, label in enumerate(LABELS):
        tp = matrix[idx][idx]
        fp = sum(matrix[row][idx] for row in range(len(LABELS)) if row != idx)
        fn = sum(matrix[idx][col] for col in range(len(LABELS)) if col != idx)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1)
        per_class.append({
            "label": label,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        })
    return {
        "n": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "macro_f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else 0.0,
        "precision_macro": round(sum(precision_values) / len(precision_values), 4) if precision_values else 0.0,
        "recall_macro": round(sum(recall_values) / len(recall_values), 4) if recall_values else 0.0,
        "confusion_matrix": matrix,
        "per_class": per_class,
    }


def exact_agreement(values_a: Sequence[int], values_b: Sequence[int]) -> float:
    if not values_a:
        return 0.0
    return round(sum(1 for a, b in zip(values_a, values_b) if a == b) / len(values_a), 4)


def mean_abs_delta(values_a: Sequence[int], values_b: Sequence[int]) -> float:
    if not values_a:
        return 0.0
    return round(sum(abs(int(a) - int(b)) for a, b in zip(values_a, values_b)) / len(values_a), 4)


def load_modeling_ids(processed_dir: Path) -> set[str]:
    return set(read_json(processed_dir / "modeling_snapshot_ids.json"))


def load_deck_features(processed_dir: Path, modeling_ids: set[str], limit: Optional[int]) -> Dict[str, Dict[str, Any]]:
    decks: Dict[str, Dict[str, Any]] = {}
    for record in iter_jsonl(processed_dir / "deck_features.jsonl"):
        snapshot_id = record.get("snapshot_id")
        if snapshot_id not in modeling_ids:
            continue
        y1 = int(record["archidekt_edh_bracket"])
        y2 = int(record["edhpowerlevel_bracket"])
        features = {name: finite_or_none(record.get(name)) for name in KEY_FEATURES}
        price_total = finite_or_none(record.get("price_total"), ndigits=2)
        if price_total is not None:
            features["price_total"] = price_total
        decks[snapshot_id] = {
            "snapshot_id": snapshot_id,
            "deck_id": int(record["deck_id"]),
            "name": record.get("deck_name") or f"Deck {record['deck_id']}",
            "view_count": int(record.get("view_count") or 0),
            "y1": y1,
            "y2": y2,
            "delta": y2 - y1,
            "abs_delta": abs(y2 - y1),
            "colors": "".join(color for color in "WUBRG" if record.get(f"has_{color}")),
            "features": features,
            "power_level": finite_or_none((record.get("edhpowerlevel") or {}).get("power_level"), ndigits=2),
            "archidekt_url": f"https://archidekt.com/decks/{record['deck_id']}",
        }
        if limit is not None and len(decks) >= limit:
            break
    return decks


def enrich_decks_from_raw(processed_dir: Path, decks: Dict[str, Dict[str, Any]]) -> None:
    wanted = set(decks)
    for record in iter_jsonl(processed_dir / "decks.jsonl"):
        snapshot_id = record.get("snapshot_id")
        if snapshot_id not in wanted:
            continue
        commanders = []
        sample_cards = []
        basic_names = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
        for card in record.get("mainboard", []):
            name = card.get("oracle_name") or ""
            quantity = int(card.get("quantity") or 0)
            if card.get("is_commander"):
                commanders.append(name)
            elif name not in basic_names and len(sample_cards) < 18:
                sample_cards.append({
                    "name": name,
                    "quantity": quantity,
                    "categories": card.get("categories") or [],
                })
        decks[snapshot_id]["commanders"] = commanders
        decks[snapshot_id]["sample_cards"] = sample_cards
        wanted.remove(snapshot_id)
        if not wanted:
            break
    for deck in decks.values():
        deck.setdefault("commanders", [])
        deck.setdefault("sample_cards", [])


def load_individual_predictions(experiment_dir: Path) -> Tuple[Dict[str, Dict[Tuple[str, str], int]], Dict[str, Dict[str, List[int]]]]:
    entry_predictions: Dict[str, Dict[Tuple[str, str], int]] = {}
    deck_predictions: Dict[str, Dict[str, List[int]]] = {}
    for model_id in INDIVIDUAL_MODEL_IDS:
        path = experiment_dir / model_id / "predictions_per_fold.jsonl"
        if not path.exists():
            continue
        entry_predictions[model_id] = {}
        deck_predictions[model_id] = defaultdict(list)
        for record in iter_jsonl(path):
            snapshot_id = record["snapshot_id"]
            fold_id = record["fold_id"]
            y_pred = int(record["y_pred"])
            entry_predictions[model_id][(snapshot_id, fold_id)] = y_pred
            deck_predictions[model_id][snapshot_id].append(y_pred)
    return entry_predictions, deck_predictions


def ensemble_vote(predictions: Sequence[Tuple[str, int]], model_scores: Mapping[str, float]) -> int:
    counts = Counter(label for _, label in predictions)
    max_count = max(counts.values())
    candidates = [label for label, count in counts.items() if count == max_count]
    if len(candidates) == 1:
        return candidates[0]
    score_by_label = {}
    for label in candidates:
        voters = [model_id for model_id, pred in predictions if pred == label]
        score_by_label[label] = max(model_scores.get(model_id, 0.0) for model_id in voters)
    best_score = max(score_by_label.values())
    return min(label for label, score in score_by_label.items() if score == best_score)


def build_ensemble_predictions(
    entry_predictions: Mapping[str, Mapping[Tuple[str, str], int]],
    model_scores: Mapping[str, float],
) -> Dict[str, Dict[str, List[int]]]:
    ensembles: Dict[str, Dict[str, List[int]]] = {}
    for ensemble_id, members in ENSEMBLE_DEFINITIONS.items():
        available_members = [member for member in members if member in entry_predictions]
        if not available_members:
            continue
        keys = sorted(set.intersection(*(set(entry_predictions[member]) for member in available_members)))
        per_deck: Dict[str, List[int]] = defaultdict(list)
        for key in keys:
            votes = [(member, entry_predictions[member][key]) for member in available_members]
            y_pred = ensemble_vote(votes, model_scores)
            per_deck[key[0]].append(y_pred)
        ensembles[ensemble_id] = per_deck
    return ensembles


def load_model_metrics(experiment_dir: Path, model_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    metrics: Dict[str, Dict[str, Any]] = {}
    for model_id in model_ids:
        path = experiment_dir / model_id / "metrics_per_fold.json"
        if not path.exists():
            continue
        payload = read_json(path)
        aggregate = payload.get("aggregate", {})
        metrics[model_id] = {
            "macro_f1_mean": finite_or_none(aggregate.get("macro_f1_mean"), ndigits=4),
            "macro_f1_std": finite_or_none(aggregate.get("macro_f1_std"), ndigits=4),
            "accuracy_mean": finite_or_none(aggregate.get("accuracy_mean"), ndigits=4),
            "precision_macro_mean": finite_or_none(aggregate.get("precision_macro_mean"), ndigits=4),
            "recall_macro_mean": finite_or_none(aggregate.get("recall_macro_mean"), ndigits=4),
            "n_folds": len(payload.get("folds") or []),
        }
    return metrics


def build_predictions_asset(
    decks: Mapping[str, Dict[str, Any]],
    deck_predictions: Mapping[str, Mapping[str, List[int]]],
    model_metrics: Mapping[str, Dict[str, Any]],
) -> Dict[str, Any]:
    deck_order = sorted(decks, key=lambda snapshot_id: (-decks[snapshot_id]["view_count"], decks[snapshot_id]["name"]))
    y_true = [int(decks[snapshot_id]["y1"]) for snapshot_id in deck_order]
    y2 = [int(decks[snapshot_id]["y2"]) for snapshot_id in deck_order]

    models = []
    for model_id, predictions_by_deck in deck_predictions.items():
        mode_predictions = []
        confidences = []
        count_vectors = []
        available_snapshot_ids = []
        for snapshot_id in deck_order:
            predictions = predictions_by_deck.get(snapshot_id, [])
            if not predictions:
                mode_predictions.append(None)
                confidences.append(0)
                count_vectors.append([0, 0, 0])
                continue
            label, counts, confidence = majority_label(predictions)
            mode_predictions.append(label)
            confidences.append(confidence)
            count_vectors.append(counts)
            available_snapshot_ids.append(snapshot_id)

        valid_indices = [idx for idx, pred in enumerate(mode_predictions) if pred is not None]
        valid_y_true = [y_true[idx] for idx in valid_indices]
        valid_y2 = [y2[idx] for idx in valid_indices]
        valid_pred = [mode_predictions[idx] for idx in valid_indices]
        metrics_y1 = classification_metrics(valid_y_true, valid_pred)
        metrics_y2 = classification_metrics(valid_y2, valid_pred)
        global_metrics = dict(model_metrics.get(model_id, {}))
        global_metrics.update({
            "deck_level_macro_f1_y1": metrics_y1["macro_f1"],
            "deck_level_accuracy_y1": metrics_y1["accuracy"],
            "deck_level_macro_f1_y2": metrics_y2["macro_f1"],
            "exact_agreement_y2": exact_agreement(valid_pred, valid_y2),
            "mean_abs_delta_y2": mean_abs_delta(valid_pred, valid_y2),
            "n_decks": len(valid_indices),
        })
        models.append({
            "id": model_id,
            "label": model_label(model_id),
            "type": "ensemble" if model_id.startswith("voting_") else "individual",
            "representation": representation_for(model_id),
            "algorithm": algorithm_for(model_id),
            "members": ENSEMBLE_DEFINITIONS.get(model_id, []),
            "global_metrics": global_metrics,
            "predictions": mode_predictions,
            "confidence": confidences,
            "counts": count_vectors,
        })
    return {
        "labels": LABELS,
        "deck_order": deck_order,
        "models": models,
    }


def build_assets(args: argparse.Namespace) -> Dict[str, Any]:
    processed_dir = args.processed_dir
    experiment_dir = args.experiment_dir
    asset_dir = args.asset_dir
    modeling_ids = load_modeling_ids(processed_dir)
    decks = load_deck_features(processed_dir, modeling_ids, args.limit_decks)
    enrich_decks_from_raw(processed_dir, decks)

    entry_predictions, individual_deck_predictions = load_individual_predictions(experiment_dir)
    individual_metrics = load_model_metrics(experiment_dir, list(individual_deck_predictions))
    model_scores = {
        model_id: float(metrics.get("macro_f1_mean") or metrics.get("deck_level_macro_f1_y1") or 0.0)
        for model_id, metrics in individual_metrics.items()
    }
    ensemble_predictions = build_ensemble_predictions(entry_predictions, model_scores)
    all_predictions: Dict[str, Mapping[str, List[int]]] = {}
    all_predictions.update(individual_deck_predictions)
    all_predictions.update(ensemble_predictions)

    predictions_asset = build_predictions_asset(decks, all_predictions, individual_metrics)
    deck_order = predictions_asset["deck_order"]
    deck_list = [decks[snapshot_id] for snapshot_id in deck_order]

    y1_values = [deck["y1"] for deck in deck_list]
    y2_values = [deck["y2"] for deck in deck_list]
    manifest = {
        "generated_at": utc_now_iso(),
        "source": {
            "processed_dir": str(processed_dir),
            "experiment_dir": str(experiment_dir),
            "prediction_protocol": "OOF predictions from Phase E plus hard-voting ensembles rebuilt from aligned OOF rows.",
        },
        "dataset": {
            "n_decks": len(deck_list),
            "labels": LABELS,
            "exact_y1_y2_agreement": exact_agreement(y1_values, y2_values),
            "mean_abs_y1_y2_delta": mean_abs_delta(y1_values, y2_values),
        },
        "models": [
            {
                "id": model["id"],
                "label": model["label"],
                "type": model["type"],
                "representation": model["representation"],
                "algorithm": model["algorithm"],
                "members": model["members"],
                "global_metrics": model["global_metrics"],
            }
            for model in predictions_asset["models"]
        ],
    }

    write_json(asset_dir / "manifest.json", manifest)
    write_json(asset_dir / "decks.json", deck_list)
    write_json(asset_dir / "predictions.json", predictions_asset)
    return manifest


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and serve the local MTG browser demo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build demo JSON assets from local project artifacts.")
    add_common_args(build)
    build.add_argument("--limit-decks", type=int, default=None, help="Optional development limit.")

    serve = subparsers.add_parser("serve", help="Serve the demo locally.")
    add_common_args(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-build", action="store_true", help="Serve existing assets without rebuilding first.")
    serve.add_argument("--limit-decks", type=int, default=None, help="Optional development limit passed to build.")
    return parser.parse_args(argv)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)


def serve_demo(args: argparse.Namespace) -> int:
    if not args.no_build:
        manifest = build_assets(args)
        print(f"Built demo assets for {manifest['dataset']['n_decks']} decks.")
    if not (args.demo_dir / "index.html").exists():
        raise FileNotFoundError(f"Missing demo entrypoint: {args.demo_dir / 'index.html'}")

    root = args.demo_dir.resolve()

    class DemoHandler(BaseHTTPRequestHandler):
        server_version = "MTGDemo/1.0"

        def log_message(self, format: str, *handler_args: Any) -> None:
            return

        def do_GET(self) -> None:
            self._serve_file(send_body=True)

        def do_HEAD(self) -> None:
            self._serve_file(send_body=False)

        def _serve_file(self, *, send_body: bool) -> None:
            parsed = urlparse(self.path)
            requested = unquote(parsed.path).lstrip("/")
            if requested in {"", "/"}:
                requested = "index.html"
            target = (root / requested).resolve()
            if root not in target.parents and target != root:
                self.send_error(403)
                return
            if target.is_dir():
                target = target / "index.html"
            if not target.exists() or not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if send_body:
                self.wfile.write(body)

    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving MTG demo at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped demo server.")
    finally:
        server.server_close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            manifest = build_assets(args)
            print(json.dumps(manifest["dataset"], ensure_ascii=False, indent=2))
            return 0
        if args.command == "serve":
            return serve_demo(args)
    except Exception as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
