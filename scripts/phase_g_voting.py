#!/usr/bin/env python3
"""Phase G — Voting ensembles from Phase E out-of-fold predictions.

Reads pre-computed voting artefacts from experiments/voting/ and produces
the Phase G reports. If voting artefacts are missing or incomplete, re-computes
them from individual model OOF predictions on the fly.

Usage
-----
    # Standard run — reads existing artefacts, regenerates reports
    uv run phase-g-voting

    # Force recompute of voting predictions even if artefacts exist
    uv run phase-g-voting --force-recompute

    # Require all 12 individual models to be present (use after Phase E is done)
    uv run phase-g-voting --all

Design
------
- Simple hard voting (plurality) over OOF predictions of individual Phase E models.
- Three global ensembles: top-3, top-5, and top-7 individual models ranked by
  nested-CV mean macro-F1, regardless of representation.
- Tie-break: class with highest mean macro-F1 among members that voted for it;
  residual tie → smallest numeric label. (backbone §G, action_plan Fase G)
- VOTING_SPECS defines the top-N sizes. Obsolete voting directories from older
  specs are removed to avoid downstream H/I reports loading stale ensembles.
- Fold alignment: each ensemble only uses folds present in ALL its members.
  Reports mean ± std over those folds (15 when Phase E is complete).
- Incrementable: re-running after new Phase E models are added updates a top-N
  ensemble automatically if its member set changed.

Outputs
-------
- experiments/voting/<voting_id>/predictions_per_fold.jsonl  (if recomputed)
- experiments/voting/<voting_id>/metrics_per_fold.json       (if recomputed)
- experiments/voting/voting_summary.json                     (if recomputed)
- documents/reports/results/phase_g_voting.md
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EXPERIMENT_DIR = Path("experiments")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
DEFAULT_SPOT_CHECK_SUMMARY = Path("experiments/spot_check/summary.json")

LABELS = [2, 3, 4]
EXPECTED_FOLDS = 15
REPORT_FILENAME = "phase_g_voting.md"


@dataclass(frozen=True)
class VotingSpec:
    voting_id: str
    description: str
    top_n: int


VOTING_SPECS: Tuple[VotingSpec, ...] = (
    VotingSpec("voting_top3", "Top-3 modelos globais por macro-F1", top_n=3),
    VotingSpec("voting_top5", "Top-5 modelos globais por macro-F1", top_n=5),
    VotingSpec("voting_top7", "Top-7 modelos globais por macro-F1", top_n=7),
)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(_jsonable(rec), ensure_ascii=False, sort_keys=True) + "\n")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def discover_individual_models(
    experiment_dir: Path,
    spot_check_summary: Path,
    require_all: bool,
) -> List[Dict]:
    """Return list of available individual models with their metrics.

    Each entry: {model_id, representation, algorithm, macro_f1_mean, n_folds, fold_f1s}
    """
    expected: List[str] = []
    if spot_check_summary.exists():
        summary = read_json(spot_check_summary)
        algos = summary.get("selection", {}).get("union", [])
        for rep in ("df", "bc"):
            for algo in algos:
                expected.append(f"{rep}_{algo}")
    else:
        for d in sorted(experiment_dir.iterdir()):
            if d.is_dir() and (d / "metrics_per_fold.json").exists():
                parts = d.name.split("_", 1)
                if len(parts) == 2 and parts[0] in ("df", "bc"):
                    expected.append(d.name)

    models: List[Dict] = []
    missing: List[str] = []

    for model_id in sorted(set(expected)):
        metrics_path = experiment_dir / model_id / "metrics_per_fold.json"
        preds_path = experiment_dir / model_id / "predictions_per_fold.jsonl"

        if not metrics_path.exists() or not preds_path.exists():
            missing.append(model_id)
            continue

        metrics = read_json(metrics_path)
        folds = metrics.get("folds", [])
        agg = metrics.get("aggregate", {})

        parts = model_id.split("_", 1)
        models.append({
            "model_id": model_id,
            "representation": parts[0].upper(),
            "algorithm": parts[1],
            "n_folds": len(folds),
            "macro_f1_mean": agg.get("macro_f1_mean", 0.0),
            "macro_f1_std": agg.get("macro_f1_std", 0.0),
            "fold_f1s": [f["macro_f1"] for f in folds],
            "fold_ids": [f["fold_id"] for f in folds],
            "predictions_path": preds_path,
        })

    if require_all and missing:
        sys.exit(
            f"[Phase G] --all exige todos os modelos. Faltando: {missing}\n"
            "Aguarde a Fase E terminar ou remova --all."
        )

    return models


def rank_models(models: List[Dict], representation: Optional[str] = None) -> List[Dict]:
    """Return models sorted by macro_f1_mean descending.

    If representation is given, only models from that representation are ranked.
    Ties use smaller standard deviation, then model_id, for deterministic output.
    """
    if representation is not None:
        models = [m for m in models if m["representation"] == representation]
    return sorted(
        models,
        key=lambda m: (
            -float(m["macro_f1_mean"]),
            float(m.get("macro_f1_std", 0.0)),
            m["model_id"],
        ),
    )


def resolve_members(spec: VotingSpec, models: List[Dict]) -> List[Dict]:
    """Return list of member models for a given VotingSpec."""
    return rank_models(models)[: spec.top_n]


def cleanup_obsolete_ensembles(voting_dir: Path) -> List[str]:
    """Remove stale voting directories not present in VOTING_SPECS."""
    expected = {spec.voting_id for spec in VOTING_SPECS}
    removed: List[str] = []
    if not voting_dir.exists():
        return removed
    for child in sorted(voting_dir.iterdir()):
        if not child.is_dir() or not child.name.startswith("voting_"):
            continue
        if child.name in expected:
            continue
        shutil.rmtree(child)
        removed.append(child.name)
    return removed


# ---------------------------------------------------------------------------
# OOF prediction loading
# ---------------------------------------------------------------------------

def load_oof_predictions(model: Dict) -> Dict[str, Dict[int, int]]:
    """Return {fold_id: {row_index: y_pred}} for a model."""
    fold_preds: Dict[str, Dict[int, int]] = defaultdict(dict)
    for rec in iter_jsonl(model["predictions_path"]):
        fold_preds[rec["fold_id"]][rec["row_index"]] = rec["y_pred"]
    return fold_preds


def load_oof_truth(model: Dict) -> Dict[str, Dict[int, int]]:
    """Return {fold_id: {row_index: y_true}} for a model."""
    fold_truth: Dict[str, Dict[int, int]] = defaultdict(dict)
    for rec in iter_jsonl(model["predictions_path"]):
        fold_truth[rec["fold_id"]][rec["row_index"]] = rec["y_true"]
    return fold_truth


def load_oof_y2(model: Dict) -> Dict[str, Dict[int, int]]:
    """Return {fold_id: {row_index: y2}} for a model."""
    fold_y2: Dict[str, Dict[int, int]] = defaultdict(dict)
    for rec in iter_jsonl(model["predictions_path"]):
        if "y2" in rec and rec["y2"] is not None:
            fold_y2[rec["fold_id"]][rec["row_index"]] = rec["y2"]
    return fold_y2


# ---------------------------------------------------------------------------
# Voting logic
# ---------------------------------------------------------------------------

def hard_vote(
    votes: List[int],
    member_f1s: List[float],
    labels: List[int],
) -> int:
    """Plurality vote with tie-break by member macro-F1.

    Tie-break rule (action_plan Fase G + backbone):
      1. Among tied classes, pick the one whose voting members have the
         highest mean macro-F1.
      2. Residual tie → smallest numeric label.
    """
    counts: Counter = Counter(votes)
    max_count = max(counts.values())
    tied = [label for label, cnt in counts.items() if cnt == max_count]

    if len(tied) == 1:
        return tied[0]

    # Tie-break: mean F1 of members that voted for each tied class
    best_label = None
    best_f1 = -1.0
    for label in sorted(tied):  # sorted ensures residual tie → smallest label
        voters_f1 = [
            f1 for vote, f1 in zip(votes, member_f1s) if vote == label
        ]
        mean_f1 = float(np.mean(voters_f1)) if voters_f1 else 0.0
        if mean_f1 > best_f1:
            best_f1 = mean_f1
            best_label = label

    return best_label  # type: ignore[return-value]


def compute_voting_results(
    spec: VotingSpec,
    members: List[Dict],
    experiment_dir: Path,
) -> Optional[Dict]:
    """Compute hard-voting metrics over shared folds for an ensemble.

    Returns None if members is empty or no shared folds exist.
    """
    if not members:
        return None

    # Load all member OOF predictions
    member_preds: List[Dict[str, Dict[int, int]]] = []
    member_truth: Optional[Dict[str, Dict[int, int]]] = None
    member_y2: Optional[Dict[str, Dict[int, int]]] = None

    for m in members:
        member_preds.append(load_oof_predictions(m))
        if member_truth is None:
            member_truth = load_oof_truth(m)
        if member_y2 is None:
            member_y2 = load_oof_y2(m)

    # Find fold IDs present in ALL members
    shared_folds: Set[str] = set(member_preds[0].keys())
    for mp in member_preds[1:]:
        shared_folds &= set(mp.keys())
    shared_folds_sorted = sorted(shared_folds)

    if not shared_folds_sorted:
        return None

    member_f1s = [m["macro_f1_mean"] for m in members]

    fold_results: List[Dict] = []
    all_predictions: List[Dict] = []

    for fold_id in shared_folds_sorted:
        # Align by row_index
        row_indices = sorted(member_preds[0][fold_id].keys())

        y_true_list: List[int] = []
        y_pred_list: List[int] = []

        for row_idx in row_indices:
            votes = [mp[fold_id].get(row_idx) for mp in member_preds]
            votes = [v for v in votes if v is not None]
            if not votes:
                continue

            y_true = member_truth[fold_id].get(row_idx)  # type: ignore[index]
            if y_true is None:
                continue

            y_pred = hard_vote(votes, member_f1s, LABELS)
            y_true_list.append(y_true)
            y_pred_list.append(y_pred)

            y2_val = member_y2[fold_id].get(row_idx) if member_y2 else None  # type: ignore[index]
            all_predictions.append({
                "voting_id": spec.voting_id,
                "fold_id": fold_id,
                "row_index": row_idx,
                "y_true": y_true,
                "y_pred": y_pred,
                "y2": y2_val,
                "per_member_preds": {
                    m["model_id"]: mp[fold_id].get(row_idx)
                    for m, mp in zip(members, member_preds)
                },
            })

        if not y_true_list:
            continue

        macro_f1 = float(f1_score(y_true_list, y_pred_list, average="macro",
                                   labels=LABELS, zero_division=0))
        acc = float(accuracy_score(y_true_list, y_pred_list))
        prec = float(precision_score(y_true_list, y_pred_list, average="macro",
                                      labels=LABELS, zero_division=0))
        rec = float(recall_score(y_true_list, y_pred_list, average="macro",
                                  labels=LABELS, zero_division=0))
        cm = confusion_matrix(y_true_list, y_pred_list, labels=LABELS).tolist()

        fold_results.append({
            "fold_id": fold_id,
            "n_test": len(y_true_list),
            "macro_f1": macro_f1,
            "accuracy": acc,
            "precision_macro": prec,
            "recall_macro": rec,
            "confusion_matrix": cm,
            "labels": LABELS,
        })

    if not fold_results:
        return None

    f1s = [f["macro_f1"] for f in fold_results]
    accs = [f["accuracy"] for f in fold_results]
    precs = [f["precision_macro"] for f in fold_results]
    recs = [f["recall_macro"] for f in fold_results]

    # Summed confusion matrix
    cm_sum = np.zeros((len(LABELS), len(LABELS)), dtype=int)
    for f in fold_results:
        cm_sum += np.array(f["confusion_matrix"])

    aggregate = {
        "macro_f1_mean": float(np.mean(f1s)),
        "macro_f1_std": float(np.std(f1s, ddof=1)) if len(f1s) > 1 else 0.0,
        "accuracy_mean": float(np.mean(accs)),
        "accuracy_std": float(np.std(accs, ddof=1)) if len(accs) > 1 else 0.0,
        "precision_macro_mean": float(np.mean(precs)),
        "precision_macro_std": float(np.std(precs, ddof=1)) if len(precs) > 1 else 0.0,
        "recall_macro_mean": float(np.mean(recs)),
        "recall_macro_std": float(np.std(recs, ddof=1)) if len(recs) > 1 else 0.0,
        "confusion_matrix_sum": cm_sum.tolist(),
        "labels": LABELS,
    }

    return {
        "voting_id": spec.voting_id,
        "description": spec.description,
        "members": [m["model_id"] for m in members],
        "n_members": len(members),
        "n_folds": len(fold_results),
        "status": "ok",
        "aggregate": aggregate,
        "folds": fold_results,
        "predictions": all_predictions,
    }


# ---------------------------------------------------------------------------
# Artefact loading (existing) vs recompute
# ---------------------------------------------------------------------------

def load_existing_ensemble(voting_dir: Path, voting_id: str) -> Optional[Dict]:
    """Load existing metrics + predictions for an ensemble if available."""
    metrics_path = voting_dir / voting_id / "metrics_per_fold.json"
    preds_path = voting_dir / voting_id / "predictions_per_fold.jsonl"
    if not metrics_path.exists() or not preds_path.exists():
        return None
    metrics = read_json(metrics_path)
    return metrics  # predictions stay on disk


def save_ensemble_artefacts(result: Dict, voting_dir: Path) -> None:
    """Write metrics and predictions for an ensemble to disk."""
    vid = result["voting_id"]
    edir = voting_dir / vid
    edir.mkdir(parents=True, exist_ok=True)

    # metrics (without predictions key)
    metrics = {k: v for k, v in result.items() if k != "predictions"}
    write_json(edir / "metrics_per_fold.json", metrics)

    if "predictions" in result:
        write_jsonl(edir / "predictions_per_fold.jsonl", result["predictions"])


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def render_report(
    ensemble_results: List[Dict],
    individual_models: List[Dict],
    missing_members: Dict[str, List[str]],
) -> str:
    lines: List[str] = []
    lines.append("# Voting Ensembles — Fase G\n")

    # --- Context ---
    lines.append(
        "Ensembles de hard-voting simples construídos sobre as predições "
        "out-of-fold (OOF) geradas na Fase E. Nenhum modelo é retreinado. "
        "Os membros são os top-N modelos individuais globais por macro-F1 média "
        "na Fase E, independente de representação. Em empate de votos, o tie-break "
        "usa a macro-F1 média dos membros que votaram na classe; empate residual → "
        "menor rótulo.\n"
    )

    # --- Individual models for reference ---
    lines.append("## Modelos individuais (referência)\n")
    lines.append("| Modelo | Repr. | Macro-F1 média | Macro-F1 dp | Folds |")
    lines.append("|---|---|---:|---:|---:|")
    for m in sorted(individual_models, key=lambda x: -x["macro_f1_mean"]):
        lines.append(
            f"| `{m['model_id']}` | {m['representation']} "
            f"| {m['macro_f1_mean']:.4f} | {m['macro_f1_std']:.4f} "
            f"| {m['n_folds']}/{EXPECTED_FOLDS} |"
        )

    # --- Ensemble results ---
    lines.append("\n## Resultados dos ensembles\n")
    lines.append(
        "| Ensemble | N | Membros | Folds | Macro-F1 média | Macro-F1 dp | Accuracy média |"
    )
    lines.append("|---|---:|---|---:|---:|---:|---:|")

    for r in ensemble_results:
        if r is None:
            continue
        agg = r["aggregate"]
        members_str = ", ".join(f"`{m}`" for m in r["members"])
        lines.append(
            f"| `{r['voting_id']}` | {r.get('n_members', len(r['members']))} | {members_str} "
            f"| {r.get('n_folds', len(r.get('folds', [])))}/{EXPECTED_FOLDS} "
            f"| {agg['macro_f1_mean']:.4f} "
            f"| {agg['macro_f1_std']:.4f} "
            f"| {agg['accuracy_mean']:.4f} |"
        )

    # --- Comparison: best individual vs best ensemble ---
    lines.append("\n## Comparação: melhor modelo individual vs melhor ensemble\n")

    best_ind = max(individual_models, key=lambda m: m["macro_f1_mean"])
    valid_ens = [r for r in ensemble_results if r is not None]
    if valid_ens:
        best_ens = max(valid_ens, key=lambda r: r["aggregate"]["macro_f1_mean"])
        best_ens_f1 = best_ens["aggregate"]["macro_f1_mean"]
        delta = best_ens_f1 - best_ind["macro_f1_mean"]
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"| Item | Macro-F1 |\n|---|---:|\n"
            f"| Melhor modelo individual (`{best_ind['model_id']}`) "
            f"| {best_ind['macro_f1_mean']:.4f} |\n"
            f"| Melhor ensemble (`{best_ens['voting_id']}`) "
            f"| {best_ens_f1:.4f} |\n"
            f"| Delta (ensemble − individual) | {sign}{delta:.4f} |"
        )

    # --- Missing members warnings ---
    if missing_members:
        lines.append("\n## Avisos — membros ausentes\n")
        for vid, missing in missing_members.items():
            lines.append(
                f"- `{vid}`: membros ausentes → {missing}. "
                "Ensemble não computado ou com membros reduzidos."
            )

    # --- Artefacts ---
    lines.append("\n## Artefatos\n")
    lines.append("- `experiments/voting/<voting_id>/metrics_per_fold.json`")
    lines.append("- `experiments/voting/<voting_id>/predictions_per_fold.jsonl`")
    lines.append("- `experiments/voting/voting_summary.json`")
    lines.append("- `documents/reports/results/phase_g_voting.md`")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase G — Voting ensembles from Phase E OOF predictions.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--all",
        dest="require_all",
        action="store_true",
        default=False,
        help=(
            "Require all expected individual models to be present. "
            "Aborts if any is missing. Use after Phase E is fully done."
        ),
    )
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        default=False,
        help=(
            "Recompute voting predictions from individual OOF even if "
            "experiments/voting/ artefacts already exist."
        ),
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

    log("[Phase G] Iniciando voting ensembles...")

    voting_dir = args.experiment_dir / "voting"

    # ------------------------------------------------------------------
    # Discover individual models
    # ------------------------------------------------------------------
    individual_models = discover_individual_models(
        experiment_dir=args.experiment_dir,
        spot_check_summary=args.spot_check_summary,
        require_all=args.require_all,
    )

    if not individual_models:
        sys.exit("[Phase G] Nenhum modelo individual disponível. Rode a Fase E primeiro.")

    log(f"[Phase G] {len(individual_models)} modelo(s) individual(is) disponível(is).")

    removed_obsolete = cleanup_obsolete_ensembles(voting_dir)
    for voting_id in removed_obsolete:
        log(f"  [{voting_id}] Artefato obsoleto removido.")

    # ------------------------------------------------------------------
    # Process each ensemble spec
    # ------------------------------------------------------------------
    ensemble_results: List[Dict] = []
    missing_members: Dict[str, List[str]] = {}
    summary_ensembles: List[Dict] = []

    for spec in VOTING_SPECS:
        members = resolve_members(spec, individual_models)

        if not members:
            log(f"  [{spec.voting_id}] Sem membros disponíveis — pulando.")
            missing_members[spec.voting_id] = ["todos os membros ausentes"]
            continue

        if len(members) < spec.top_n:
            missing_members[spec.voting_id] = [
                f"{spec.top_n - len(members)} modelo(s) individual(is)"
            ]

        member_ids = [m["model_id"] for m in members]
        log(f"  [{spec.voting_id}] Membros: {member_ids}")

        # Check if existing artefacts are up-to-date
        existing = None
        if not args.force_recompute:
            existing = load_existing_ensemble(voting_dir, spec.voting_id)
            if existing:
                existing_members = existing.get("members", [])
                if set(existing_members) == set(member_ids):
                    log(f"  [{spec.voting_id}] Artefatos existentes OK — reutilizando.")
                    ensemble_results.append(existing)
                    summary_ensembles.append({k: v for k, v in existing.items()
                                              if k != "folds"})
                    continue
                else:
                    log(
                        f"  [{spec.voting_id}] Membros mudaram "
                        f"({existing_members} → {member_ids}) — recomputando."
                    )

        # Recompute
        log(f"  [{spec.voting_id}] Computando voting...")
        result = compute_voting_results(spec, members, args.experiment_dir)

        if result is None:
            log(f"  [{spec.voting_id}] Sem folds compartilhados — pulando.")
            continue

        save_ensemble_artefacts(result, voting_dir)
        n = result["n_folds"]
        f1 = result["aggregate"]["macro_f1_mean"]
        std = result["aggregate"]["macro_f1_std"]
        log(f"  [{spec.voting_id}] macro-F1={f1:.4f}±{std:.4f} ({n} folds) — salvo.")

        ensemble_results.append(result)
        summary_ensembles.append({k: v for k, v in result.items() if k != "predictions"})

    # ------------------------------------------------------------------
    # Write voting_summary.json
    # ------------------------------------------------------------------
    voting_summary_path = voting_dir / "voting_summary.json"
    write_json(voting_summary_path, {"ensembles": summary_ensembles})
    log(f"[Phase G] voting_summary.json → {voting_summary_path}")

    # ------------------------------------------------------------------
    # Generate report
    # ------------------------------------------------------------------
    report = render_report(ensemble_results, individual_models, missing_members)
    report_path = args.docs_dir / REPORT_FILENAME
    write_text(report_path, report)
    log(f"[Phase G] Relatório → {report_path}")
    log("[Phase G] Concluído.")


if __name__ == "__main__":
    main()
