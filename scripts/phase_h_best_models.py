"""
Phase H — Best model selection per representation.

Ranks all individual models (from Phase E) and voting ensembles (from Phase G)
by macro-F1 mean over the outer folds. Selects melhor_BC and melhor_DF among
individual models. Generates the full comparison report and saves the selection
artefact consumed by Phase J.

Usage
-----
    uv run phase-h-best-models

Outputs
-------
- documents/reports/results/phase_h_best_models.md  (auto-generated, overwritten each run)
- experiments/best_models.json                       (selection artefact for Phase J)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_OUTER_FOLDS = 15
CLASSES = [2, 3, 4]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_jsonl(path: Path) -> List[Dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_individual_models(
    experiment_dir: Path,
    spot_check_summary: Path,
) -> List[Dict]:
    """Load metrics for all individual models from Phase E."""
    # Discover expected models from spot-check union
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

    models = []
    for model_id in sorted(set(expected)):
        model_dir = experiment_dir / model_id
        metrics_path = model_dir / "metrics_per_fold.json"
        if not metrics_path.exists():
            print(f"  AVISO: {model_id} — metrics_per_fold.json não encontrado, pulando.",
                  file=sys.stderr)
            continue

        metrics = read_json(metrics_path)
        folds = metrics.get("folds", [])
        n_folds = len(folds)

        if n_folds == 0:
            print(f"  AVISO: {model_id} — sem folds, pulando.", file=sys.stderr)
            continue

        f1s = [f["macro_f1"] for f in folds if "macro_f1" in f]
        accs = [f["accuracy"] for f in folds if "accuracy" in f]
        precs = [f["precision_macro"] for f in folds if "precision_macro" in f]
        recs = [f["recall_macro"] for f in folds if "recall_macro" in f]

        parts = model_id.split("_", 1)
        rep = parts[0].upper()
        algo = parts[1]

        models.append({
            "model_id": model_id,
            "representation": rep,
            "algorithm": algo,
            "n_folds": n_folds,
            "macro_f1_mean": statistics.mean(f1s),
            "macro_f1_std": statistics.stdev(f1s) if len(f1s) > 1 else 0.0,
            "accuracy_mean": statistics.mean(accs) if accs else None,
            "precision_mean": statistics.mean(precs) if precs else None,
            "recall_mean": statistics.mean(recs) if recs else None,
            "fold_f1s": f1s,
            "predictions_path": model_dir / "predictions_per_fold.jsonl",
            "hyperparams_path": model_dir / "best_hyperparams_per_fold.json",
        })

    return models


def load_ensemble_models(voting_dir: Path) -> List[Dict]:
    """Load metrics for all Phase G voting ensembles."""
    ensembles = []
    for d in sorted(voting_dir.iterdir()):
        if not d.is_dir():
            continue
        metrics_path = d / "metrics_per_fold.json"
        if not metrics_path.exists():
            continue

        metrics = read_json(metrics_path)
        folds = metrics.get("folds", [])
        f1s = [f["macro_f1"] for f in folds if "macro_f1" in f]
        accs = [f["accuracy"] for f in folds if "accuracy" in f]

        if not f1s:
            continue

        ensembles.append({
            "voting_id": metrics.get("voting_id", d.name),
            "description": metrics.get("description", ""),
            "members": metrics.get("members", []),
            "n_members": metrics.get("n_members", len(metrics.get("members", []))),
            "n_folds": len(f1s),
            "macro_f1_mean": statistics.mean(f1s),
            "macro_f1_std": statistics.stdev(f1s) if len(f1s) > 1 else 0.0,
            "accuracy_mean": statistics.mean(accs) if accs else None,
            "fold_f1s": f1s,
            "predictions_path": d / "predictions_per_fold.jsonl",
        })

    return ensembles


# ---------------------------------------------------------------------------
# Ranking & selection
# ---------------------------------------------------------------------------

def rank_models(models: List[Dict]) -> List[Dict]:
    """Sort by macro_f1_mean desc, then macro_f1_std asc (stability)."""
    return sorted(models, key=lambda m: (-m["macro_f1_mean"], m["macro_f1_std"]))


def select_best(
    models: List[Dict],
    representation: str,
) -> Optional[Dict]:
    """Select the best individual model for a given representation."""
    candidates = [m for m in models if m["representation"] == representation]
    if not candidates:
        return None
    ranked = rank_models(candidates)
    return ranked[0]


# ---------------------------------------------------------------------------
# Confusion matrix from OOF predictions
# ---------------------------------------------------------------------------

def aggregate_confusion_matrix(predictions_path: Path) -> Tuple[List[List[int]], List[int]]:
    """
    Aggregate confusion matrix across all OOF folds.
    Returns (cm, labels) where cm[i][j] = count of true=labels[i], pred=labels[j].
    Each deck appears once per repeat (3×) — all predictions are used as-is.
    """
    rows = read_jsonl(predictions_path)
    labels = CLASSES
    label_idx = {c: i for i, c in enumerate(labels)}
    n = len(labels)
    cm = [[0] * n for _ in range(n)]
    for r in rows:
        true = r.get("y_true")
        pred = r.get("y_pred")
        if true in label_idx and pred in label_idx:
            cm[label_idx[true]][label_idx[pred]] += 1
    return cm, labels


def cm_to_markdown(cm: List[List[int]], labels: List[int], title: str) -> List[str]:
    """Render a confusion matrix as a markdown table."""
    lines = [f"**{title}** — linhas = verdadeiro, colunas = previsto\n"]
    header = "| True \\ Pred |" + "".join(f" {lb} |" for lb in labels)
    sep = "|---|" + "---|" * len(labels)
    lines.append(header)
    lines.append(sep)
    for i, lb in enumerate(labels):
        row_total = sum(cm[i])
        cells = "".join(f" {cm[i][j]} |" for j in range(len(labels)))
        lines.append(f"| **{lb}** |{cells} *(n={row_total})*")
    return lines


# ---------------------------------------------------------------------------
# Hyperparameter summary
# ---------------------------------------------------------------------------

def summarise_hyperparams(hyperparams_path: Path) -> Tuple[Dict, List[Dict]]:
    """
    Return (most_common_params, per_fold_list).
    most_common_params: the config that appeared most often across outer folds.
    """
    data = read_json(hyperparams_path)
    if not data:
        return {}, []

    # Count configs
    from collections import Counter
    config_counts: Counter = Counter()
    per_fold = []
    for entry in data:
        params = entry.get("best_params", {})
        key = json.dumps(params, sort_keys=True)
        config_counts[key] += 1
        per_fold.append({
            "fold_id": entry.get("fold_id"),
            "params": params,
            "inner_best_macro_f1": entry.get("inner_best_macro_f1"),
        })

    most_common_key = config_counts.most_common(1)[0][0]
    most_common = json.loads(most_common_key)
    return most_common, per_fold


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt(v: Optional[float], decimals: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def render_report(
    individual_models: List[Dict],
    ensemble_models: List[Dict],
    best_bc: Optional[Dict],
    best_df: Optional[Dict],
) -> str:
    lines: List[str] = []

    lines.append("# Fase H — Seleção do Melhor Modelo por Representação\n")
    lines.append(
        "Ranqueamento dos modelos individuais (Fase E) e ensembles de votação (Fase G) "
        "por macro-F1 médio nos outer folds. Seleção de `melhor_BC` e `melhor_DF` "
        "entre os modelos individuais (backbone §13.8). Desempate por menor desvio padrão.\n"
    )

    # ------------------------------------------------------------------
    # 1. Ranking completo — individuais
    # ------------------------------------------------------------------
    lines.append("## 1. Ranking — Modelos individuais\n")
    lines.append("| # | Modelo | Repr. | Algoritmo | Macro-F1 média | Macro-F1 dp | Accuracy média | Folds |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|")

    ranked_ind = rank_models(individual_models)
    for i, m in enumerate(ranked_ind, 1):
        selected = ""
        if best_bc and m["model_id"] == best_bc["model_id"]:
            selected = " ★BC"
        if best_df and m["model_id"] == best_df["model_id"]:
            selected = " ★DF"
        lines.append(
            f"| {i} | `{m['model_id']}`{selected} | {m['representation']} | {m['algorithm']} "
            f"| {_fmt(m['macro_f1_mean'])} | {_fmt(m['macro_f1_std'])} "
            f"| {_fmt(m['accuracy_mean'])} | {m['n_folds']}/{EXPECTED_OUTER_FOLDS} |"
        )

    # ------------------------------------------------------------------
    # 2. BC vs DF por algoritmo
    # ------------------------------------------------------------------
    lines.append("\n## 2. Comparação BC vs DF por algoritmo\n")
    lines.append("| Algoritmo | BC macro-F1 | BC dp | DF macro-F1 | DF dp | Δ (DF − BC) |")
    lines.append("|---|---:|---:|---:|---:|---:|")

    algo_map: Dict[str, Dict] = {}
    for m in individual_models:
        algo_map.setdefault(m["algorithm"], {})[m["representation"]] = m

    for algo in sorted(algo_map.keys()):
        bc = algo_map[algo].get("BC")
        df = algo_map[algo].get("DF")
        bc_f1 = bc["macro_f1_mean"] if bc else None
        df_f1 = df["macro_f1_mean"] if df else None
        bc_std = bc["macro_f1_std"] if bc else None
        df_std = df["macro_f1_std"] if df else None
        delta = (df_f1 - bc_f1) if (df_f1 is not None and bc_f1 is not None) else None
        delta_str = (f"+{delta:.4f}" if delta >= 0 else f"{delta:.4f}") if delta is not None else "—"
        lines.append(
            f"| {algo} | {_fmt(bc_f1)} | {_fmt(bc_std)} "
            f"| {_fmt(df_f1)} | {_fmt(df_std)} | {delta_str} |"
        )

    # ------------------------------------------------------------------
    # 3. Ensembles de votação
    # ------------------------------------------------------------------
    lines.append("\n## 3. Ensembles de votação (Fase G)\n")
    lines.append("| Ensemble | Membros | Folds | Macro-F1 média | Macro-F1 dp |")
    lines.append("|---|---|---:|---:|---:|")

    ranked_ens = rank_models(ensemble_models)
    for e in ranked_ens:
        members_str = ", ".join(f"`{m}`" for m in e["members"])
        lines.append(
            f"| `{e['voting_id']}` | {members_str} "
            f"| {e['n_folds']}/{EXPECTED_OUTER_FOLDS} "
            f"| {_fmt(e['macro_f1_mean'])} | {_fmt(e['macro_f1_std'])} |"
        )

    # Ganho de ensembles vs melhor individual por representação
    lines.append("\n### Ganho dos ensembles vs melhor modelo individual\n")
    lines.append("| Ensemble | Melhor individual (referência) | Delta macro-F1 |")
    lines.append("|---|---|---:|")

    best_bc_f1 = best_bc["macro_f1_mean"] if best_bc else None
    best_df_f1 = best_df["macro_f1_mean"] if best_df else None

    for e in ranked_ens:
        vid = e["voting_id"]
        e_f1 = e["macro_f1_mean"]
        # Determine reference: BC-only ensembles compare to best_BC, DF-only to best_DF, mixed to best overall
        if "BC_DF" in vid or "all" in vid:
            ref_f1 = max(f for f in [best_bc_f1, best_df_f1] if f is not None)
            ref_name = "melhor individual geral"
        elif "_BC" in vid:
            ref_f1 = best_bc_f1
            ref_name = f"`{best_bc['model_id']}`" if best_bc else "—"
        else:
            ref_f1 = best_df_f1
            ref_name = f"`{best_df['model_id']}`" if best_df else "—"

        if ref_f1 is not None:
            delta = e_f1 - ref_f1
            delta_str = f"+{delta:.4f}" if delta >= 0 else f"{delta:.4f}"
        else:
            delta_str = "—"
        lines.append(f"| `{vid}` | {ref_name} | {delta_str} |")

    # ------------------------------------------------------------------
    # 4. Seleção final
    # ------------------------------------------------------------------
    lines.append("\n## 4. Seleção final\n")

    for label, best in [("BC", best_bc), ("DF", best_df)]:
        if best is None:
            lines.append(f"### melhor_{label}: não encontrado\n")
            continue
        rank_in_rep = [i + 1 for i, m in enumerate(
            rank_models([m for m in individual_models if m["representation"] == label])
        ) if m["model_id"] == best["model_id"]]
        rank_str = f"rank {rank_in_rep[0]}" if rank_in_rep else "rank 1"

        lines.append(f"### melhor_{label}: `{best['model_id']}`\n")
        lines.append(f"- **Algoritmo**: {best['algorithm']}")
        lines.append(f"- **Representação**: {best['representation']}")
        lines.append(f"- **Macro-F1 média**: {_fmt(best['macro_f1_mean'])} ± {_fmt(best['macro_f1_std'])}")
        lines.append(f"- **Accuracy média**: {_fmt(best['accuracy_mean'])}")
        lines.append(f"- **Folds**: {best['n_folds']}/{EXPECTED_OUTER_FOLDS}")
        lines.append(f"- **Posição no ranking {label}**: {rank_str}")
        lines.append(f"- **Justificativa**: maior macro-F1 médio na representação {label}; "
                     f"desempate por desvio padrão não foi necessário.")
        lines.append("")

    # ------------------------------------------------------------------
    # 5. Hiperparâmetros por fold dos modelos selecionados
    # ------------------------------------------------------------------
    lines.append("## 5. Hiperparâmetros por fold — modelos selecionados\n")

    for label, best in [("BC", best_bc), ("DF", best_df)]:
        if best is None:
            continue
        lines.append(f"### {best['model_id']}\n")
        most_common, per_fold = summarise_hyperparams(best["hyperparams_path"])
        lines.append(f"**Configuração mais frequente** (across {best['n_folds']} outer folds):")
        for k, v in sorted(most_common.items()):
            # strip clf__ prefix for readability
            key = k.replace("clf__", "")
            lines.append(f"- `{key}` = `{v}`")
        lines.append("")

        lines.append("| Fold | inner macro-F1 | Parâmetros |")
        lines.append("|---|---:|---|")
        for entry in per_fold:
            params_str = ", ".join(
                f"`{k.replace('clf__', '')}={v}`" for k, v in sorted(entry["params"].items())
            )
            inner_f1 = _fmt(entry.get("inner_best_macro_f1"))
            lines.append(f"| {entry['fold_id']} | {inner_f1} | {params_str} |")
        lines.append("")

    # ------------------------------------------------------------------
    # 6. Matrizes de confusão agregadas
    # ------------------------------------------------------------------
    lines.append("## 6. Matrizes de confusão agregadas (OOF — todos os folds)\n")
    lines.append(
        "> Cada deck aparece 3× nas predições OOF (uma vez por repeat). "
        "Total: 12.135 × 3 = 36.405 entradas.\n"
    )

    for label, best in [("BC", best_bc), ("DF", best_df)]:
        if best is None:
            continue
        if not best["predictions_path"].exists():
            lines.append(f"*{best['model_id']}: predictions_per_fold.jsonl não encontrado.*\n")
            continue
        cm, labels = aggregate_confusion_matrix(best["predictions_path"])
        cm_lines = cm_to_markdown(cm, labels, title=best["model_id"])
        lines.extend(cm_lines)
        lines.append("")

        # Per-class precision/recall from confusion matrix
        lines.append(f"**Métricas por classe — {best['model_id']}** (calculadas sobre a matriz agregada)\n")
        lines.append("| Classe | Precisão | Recall | F1 |")
        lines.append("|---|---:|---:|---:|")
        n = len(labels)
        for i, cl in enumerate(labels):
            tp = cm[i][i]
            fp = sum(cm[j][i] for j in range(n)) - tp
            fn = sum(cm[i][j] for j in range(n)) - tp
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            lines.append(f"| {cl} | {prec:.4f} | {rec:.4f} | {f1:.4f} |")
        lines.append("")

    # ------------------------------------------------------------------
    # 7. Artefatos
    # ------------------------------------------------------------------
    lines.append("## 7. Artefatos\n")
    lines.append("- `experiments/best_models.json` — seleção consumida pela Fase J")
    lines.append("- `documents/reports/results/phase_h_best_models.md` — este relatório")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Save selection artefact
# ---------------------------------------------------------------------------

def save_best_models_json(
    best_bc: Optional[Dict],
    best_df: Optional[Dict],
    output_path: Path,
) -> None:
    """Save best_models.json for consumption by Phase J."""
    selection = {}
    for key, best in [("best_BC", best_bc), ("best_DF", best_df)]:
        if best is None:
            selection[key] = None
            continue
        selection[key] = {
            "model_id": best["model_id"],
            "representation": best["representation"],
            "algorithm": best["algorithm"],
            "macro_f1_mean": best["macro_f1_mean"],
            "macro_f1_std": best["macro_f1_std"],
            "n_folds": best["n_folds"],
            "predictions_path": str(best["predictions_path"]),
            "hyperparams_path": str(best["hyperparams_path"]),
        }
    write_json(output_path, selection)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    import sys as _sys
    print(msg, flush=True, file=_sys.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase H — Best model selection per representation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--experiment-dir",
        dest="experiment_dir",
        type=Path,
        default=Path("experiments"),
        metavar="DIR",
    )
    parser.add_argument(
        "--docs-dir",
        dest="docs_dir",
        type=Path,
        default=Path("documents/reports/results"),
        metavar="DIR",
    )
    parser.add_argument(
        "--spot-check-summary",
        dest="spot_check_summary",
        type=Path,
        default=Path("experiments/spot_check/summary.json"),
        metavar="PATH",
    )
    args = parser.parse_args()

    voting_dir = args.experiment_dir / "voting"
    report_path = args.docs_dir / "phase_h_best_models.md"
    best_models_path = args.experiment_dir / "best_models.json"

    log("[Phase H] Iniciando seleção do melhor modelo por representação...")

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    log("[Phase H] Carregando modelos individuais (Fase E)...")
    individual_models = load_individual_models(args.experiment_dir, args.spot_check_summary)
    log(f"[Phase H] {len(individual_models)} modelo(s) individual(is) carregado(s).")

    log("[Phase H] Carregando ensembles de votação (Fase G)...")
    ensemble_models = load_ensemble_models(voting_dir)
    log(f"[Phase H] {len(ensemble_models)} ensemble(s) carregado(s).")

    if not individual_models:
        sys.exit("[Phase H] Nenhum modelo individual encontrado. Execute a Fase E primeiro.")

    # ------------------------------------------------------------------
    # Ranking & selection
    # ------------------------------------------------------------------
    log("[Phase H] Ranqueando e selecionando melhores modelos...")
    best_bc = select_best(individual_models, "BC")
    best_df = select_best(individual_models, "DF")

    if best_bc:
        log(f"  melhor_BC: {best_bc['model_id']} — macro-F1={best_bc['macro_f1_mean']:.4f} ± {best_bc['macro_f1_std']:.4f}")
    if best_df:
        log(f"  melhor_DF: {best_df['model_id']} — macro-F1={best_df['macro_f1_mean']:.4f} ± {best_df['macro_f1_std']:.4f}")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    log("[Phase H] Gerando relatório...")
    report = render_report(individual_models, ensemble_models, best_bc, best_df)
    write_text(report_path, report)
    log(f"[Phase H] Relatório → {report_path}")

    # ------------------------------------------------------------------
    # Save artefact
    # ------------------------------------------------------------------
    save_best_models_json(best_bc, best_df, best_models_path)
    log(f"[Phase H] best_models.json → {best_models_path}")

    log("[Phase H] Concluído.")


if __name__ == "__main__":
    main()
