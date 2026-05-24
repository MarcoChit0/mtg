"""
Phase I — Comparison of model predictions vs. calculator (y2).

Descriptive analysis only — no retraining, no new folds, no new target.
Loads OOF predictions from Phase E (individual models) and Phase G (voting
ensembles) and compares ŷ1 (predicted by models trained on y1) against y2
(EDHPowerLevel calculator).

y2 is NEVER used as training target (backbone §5). This phase measures
alignment between what the models learned from community labels and what the
calculator computes automatically.

Usage
-----
    uv run --no-sync python -m scripts.phase_i_model_vs_calculator

Outputs
-------
- documents/reports/results/phase_i_model_vs_calculator.md  (auto-generated)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASSES = [2, 3, 4]
EXPECTED_OUTER_FOLDS = 15


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


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
# Metrics computation (manual — no sklearn dependency for this phase)
# ---------------------------------------------------------------------------

def macro_f1(y_true: List[int], y_pred: List[int], classes: List[int]) -> float:
    """Compute macro-F1 manually from two label lists."""
    f1s = []
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return statistics.mean(f1s)


def compute_agreement_metrics(rows: List[Dict]) -> Dict:
    """
    Compute agreement metrics between ŷ1 (y_pred) and y2.

    Returns dict with:
      n, exact_agreement, near_agreement, mean_abs_delta,
      macro_f1_vs_y2, cm_pred_vs_y2 (rows=ŷ1, cols=y2)
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "exact_agreement": None, "near_agreement": None,
                "mean_abs_delta": None, "macro_f1_vs_y2": None,
                "cm_pred_vs_y2": None}

    y_pred = [r["y_pred"] for r in rows]
    y2     = [r["y2"]    for r in rows]

    exact = sum(1 for p, t in zip(y_pred, y2) if p == t)
    near  = sum(1 for p, t in zip(y_pred, y2) if abs(p - t) <= 1)
    deltas = [abs(p - t) for p, t in zip(y_pred, y2)]

    # confusion matrix: rows = ŷ1 (predicted), cols = y2
    label_idx = {c: i for i, c in enumerate(CLASSES)}
    nc = len(CLASSES)
    cm = [[0] * nc for _ in range(nc)]
    for p, t in zip(y_pred, y2):
        if p in label_idx and t in label_idx:
            cm[label_idx[p]][label_idx[t]] += 1

    return {
        "n": n,
        "exact_agreement": exact / n,
        "near_agreement":  near  / n,
        "mean_abs_delta":  statistics.mean(deltas),
        "macro_f1_vs_y2":  macro_f1(y2, y_pred, CLASSES),
        "cm_pred_vs_y2":   cm,
    }


def compute_subset_metrics(rows: List[Dict]) -> Dict:
    """
    Compute agreement metrics separately for:
      - concordant: decks where y_true == y2 (community and calculator agree)
      - discordant: decks where y_true != y2 (community and calculator disagree)
    """
    concordant = [r for r in rows if r["y_true"] == r["y2"]]
    discordant = [r for r in rows if r["y_true"] != r["y2"]]
    return {
        "concordant": compute_agreement_metrics(concordant),
        "discordant": compute_agreement_metrics(discordant),
    }


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def load_individual_models(
    experiment_dir: Path,
    spot_check_summary: Path,
) -> List[Dict]:
    """Discover individual models from Phase E and load their predictions."""
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
        preds_path = model_dir / "predictions_per_fold.jsonl"
        metrics_path = model_dir / "metrics_per_fold.json"

        if not preds_path.exists():
            print(f"  AVISO: {model_id} — predictions_per_fold.jsonl ausente, pulando.",
                  file=sys.stderr)
            continue

        # Load macro_f1_y1 from nested CV metrics
        macro_f1_y1 = None
        if metrics_path.exists():
            m = read_json(metrics_path)
            folds = m.get("folds", [])
            f1s = [f["macro_f1"] for f in folds if "macro_f1" in f]
            if f1s:
                macro_f1_y1 = statistics.mean(f1s)

        parts = model_id.split("_", 1)
        models.append({
            "model_id": model_id,
            "type": "individual",
            "representation": parts[0].upper(),
            "algorithm": parts[1],
            "macro_f1_y1": macro_f1_y1,
            "predictions_path": preds_path,
        })

    return models


def load_ensemble_models(voting_dir: Path) -> List[Dict]:
    """Discover voting ensembles from Phase G and load their predictions."""
    ensembles = []
    for d in sorted(voting_dir.iterdir()):
        if not d.is_dir():
            continue
        preds_path = d / "predictions_per_fold.jsonl"
        metrics_path = d / "metrics_per_fold.json"
        if not preds_path.exists():
            continue

        macro_f1_y1 = None
        if metrics_path.exists():
            m = read_json(metrics_path)
            folds = m.get("folds", [])
            f1s = [f["macro_f1"] for f in folds if "macro_f1" in f]
            if f1s:
                macro_f1_y1 = statistics.mean(f1s)

        ensembles.append({
            "model_id": d.name,
            "type": "ensemble",
            "representation": "BC+DF" if ("BC_DF" in d.name or "all" in d.name)
                              else ("BC" if "_BC" in d.name else "DF"),
            "algorithm": "voting",
            "macro_f1_y1": macro_f1_y1,
            "predictions_path": preds_path,
        })

    return ensembles


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _pct(v: Optional[float]) -> str:
    return f"{v*100:.1f}%" if v is not None else "—"


def _fmt(v: Optional[float], d: int = 4) -> str:
    return f"{v:.{d}f}" if v is not None else "—"


def _delta_str(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"+{v:.4f}" if v >= 0 else f"{v:.4f}"


def cm_to_markdown(cm: List[List[int]], labels: List[int], title: str) -> List[str]:
    """Render confusion matrix (rows=ŷ1, cols=y2) as markdown."""
    lines = [f"**{title}** — linhas = ŷ1 (previsto pelo modelo), colunas = y2 (calculadora)\n"]
    header = "| ŷ1 \\ y2 |" + "".join(f" {lb} |" for lb in labels)
    sep = "|---|" + "---|" * len(labels)
    lines.append(header)
    lines.append(sep)
    for i, lb in enumerate(labels):
        row_total = sum(cm[i])
        cells = "".join(f" {cm[i][j]} |" for j in range(len(labels)))
        lines.append(f"| **{lb}** |{cells} *(n={row_total})*")
    return lines


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def render_report(
    all_models: List[Dict],
    results: List[Dict],
) -> str:
    lines: List[str] = []

    lines.append("# Fase I — Comparação das Predições dos Modelos com a Calculadora (y2)\n")
    lines.append(
        "> Análise **descritiva** — sem retreino, sem novos folds. "
        "Os modelos foram treinados para prever `y1` (bracket comunitário Archidekt). "
        "As predições OOF `ŷ1` são comparadas aqui contra `y2` (EDHPowerLevel calculator) "
        "para medir o grau de alinhamento entre percepção comunitária e avaliação automática. "
        "`y2` nunca foi alvo de treinamento (backbone §5).\n"
    )
    lines.append(
        f"Base: {results[0]['metrics']['n'] if results else 0} entradas OOF "
        "(12.135 decks × 3 repeats). `y2` é estável por deck (0 inconsistências entre folds).\n"
    )

    # ------------------------------------------------------------------
    # 1. Tabela completa — todos os modelos
    # ------------------------------------------------------------------
    lines.append("## 1. Concordância com y2 — todos os modelos\n")
    lines.append(
        "| Modelo | Tipo | Repr. | Macro-F1 (y1) | Concord. exata ŷ1=y2 | Concord. ±1 | "
        "|Δ| médio | Macro-F1 vs y2 |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")

    # Sort by exact agreement desc
    sorted_results = sorted(results, key=lambda r: r["metrics"]["exact_agreement"] or 0, reverse=True)

    for r in sorted_results:
        m = r["metrics"]
        lines.append(
            f"| `{r['model_id']}` | {r['type']} | {r['representation']} "
            f"| {_fmt(r['macro_f1_y1'])} "
            f"| {_pct(m['exact_agreement'])} "
            f"| {_pct(m['near_agreement'])} "
            f"| {_fmt(m['mean_abs_delta'], 3)} "
            f"| {_fmt(m['macro_f1_vs_y2'])} |"
        )

    # ------------------------------------------------------------------
    # 2. Gap: macro-F1(y1) vs concordância exata com y2
    # ------------------------------------------------------------------
    lines.append("\n## 2. Gap entre desempenho em y1 e concordância com y2\n")
    lines.append(
        "> Um gap positivo grande significa que o modelo aprendeu bem `y1` "
        "mas diverge da calculadora — aprendeu particularidades da percepção comunitária. "
        "Gap negativo ou próximo de zero indica alinhamento estrutural entre os dois rótulos.\n"
    )
    lines.append("| Modelo | Tipo | Macro-F1 (y1) | Concord. exata (y2) | Gap (F1 − concord.) |")
    lines.append("|---|---|---:|---:|---:|")

    gap_sorted = sorted(
        results,
        key=lambda r: (
            (r["macro_f1_y1"] or 0) - (r["metrics"]["exact_agreement"] or 0)
        ),
        reverse=True,
    )
    for r in gap_sorted:
        f1 = r["macro_f1_y1"]
        ea = r["metrics"]["exact_agreement"]
        gap = (f1 - ea) if (f1 is not None and ea is not None) else None
        lines.append(
            f"| `{r['model_id']}` | {r['type']} | {_fmt(f1)} "
            f"| {_pct(ea)} | {_delta_str(gap)} |"
        )

    # ------------------------------------------------------------------
    # 3. Análise por subconjunto: y1==y2 vs y1!=y2
    # ------------------------------------------------------------------
    lines.append("\n## 3. Análise por subconjunto: decks concordantes vs discordantes\n")
    lines.append(
        "> **Concordante**: decks onde `y1 == y2` — comunidade e calculadora atribuem o mesmo bracket.\n"
        "> **Discordante**: decks onde `y1 != y2` — as fontes divergem.\n"
        "> Métricas: concordância exata entre ŷ1 e y2 dentro de cada subconjunto.\n"
    )
    lines.append(
        "| Modelo | Tipo | Concord. exata (todos) | "
        "Concord. exata (y1=y2, n≈7395×3) | Concord. exata (y1≠y2, n≈4740×3) |"
    )
    lines.append("|---|---|---:|---:|---:|")

    for r in sorted_results:
        m_all  = r["metrics"]
        m_conc = r["subset"]["concordant"]
        m_disc = r["subset"]["discordant"]
        lines.append(
            f"| `{r['model_id']}` | {r['type']} "
            f"| {_pct(m_all['exact_agreement'])} "
            f"| {_pct(m_conc['exact_agreement'])} "
            f"| {_pct(m_disc['exact_agreement'])} |"
        )

    # ------------------------------------------------------------------
    # 4. Matrizes de confusão — modelos de destaque
    # ------------------------------------------------------------------
    lines.append("\n## 4. Matrizes de confusão ŷ1 × y2 — modelos de destaque\n")
    lines.append(
        "> Linhas = ŷ1 (o que o modelo previu para bracket comunitário), "
        "colunas = y2 (o que a calculadora atribuiu). "
        "A diagonal principal = concordância exata ŷ1 = y2.\n"
    )

    # Best agreement, worst agreement, largest gap
    best_agree  = sorted_results[0]
    worst_agree = sorted_results[-1]
    largest_gap = gap_sorted[0]

    highlight_ids = {best_agree["model_id"], worst_agree["model_id"], largest_gap["model_id"]}
    highlights = [r for r in results if r["model_id"] in highlight_ids]
    # Deduplicate preserving order: best, worst, gap
    seen = set()
    ordered_highlights = []
    for r_ref in [best_agree, worst_agree, largest_gap]:
        for r in highlights:
            if r["model_id"] == r_ref["model_id"] and r["model_id"] not in seen:
                ordered_highlights.append(r)
                seen.add(r["model_id"])

    for r in ordered_highlights:
        m = r["metrics"]
        if m["cm_pred_vs_y2"] is None:
            continue
        role = []
        if r["model_id"] == best_agree["model_id"]:
            role.append("maior concordância com y2")
        if r["model_id"] == worst_agree["model_id"]:
            role.append("menor concordância com y2")
        if r["model_id"] == largest_gap["model_id"]:
            role.append("maior gap F1(y1)−concord.(y2)")
        role_str = ", ".join(role)
        lines.append(f"### `{r['model_id']}` ({role_str})\n")
        cm_lines = cm_to_markdown(m["cm_pred_vs_y2"], CLASSES, r["model_id"])
        lines.extend(cm_lines)
        lines.append("")

    # ------------------------------------------------------------------
    # 5. Narrativa comparativa
    # ------------------------------------------------------------------
    lines.append("## 5. Discussão comparativa\n")

    best  = best_agree
    worst = worst_agree
    gap_m = largest_gap

    best_ea  = best["metrics"]["exact_agreement"]
    worst_ea = worst["metrics"]["exact_agreement"]
    gap_val  = ((gap_m["macro_f1_y1"] or 0) - (gap_m["metrics"]["exact_agreement"] or 0))

    lines.append(
        f"**Maior concordância com y2**: `{best['model_id']}` "
        f"({_pct(best_ea)} de concordância exata). "
        f"Apesar de ter sido treinado exclusivamente em `y1`, este modelo "
        f"alinha suas predições à calculadora em quase {_pct(best_ea)} dos decks — "
        f"indicando que os sinais estruturais capturados pelo modelo coincidem parcialmente "
        f"com os critérios objetivos usados por EDHPowerLevel.\n"
    )
    lines.append(
        f"**Menor concordância com y2**: `{worst['model_id']}` "
        f"({_pct(worst_ea)} de concordância exata). "
        f"A baixa concordância sugere que este modelo captou padrões de percepção comunitária "
        f"mais distantes da lógica da calculadora — possivelmente porque a representação "
        f"ou o algoritmo enfatiza sinais que o usuário do Archidekt considera, "
        f"mas que EDHPowerLevel não pondera da mesma forma.\n"
    )
    lines.append(
        f"**Maior gap F1(y1) − concordância(y2)**: `{gap_m['model_id']}` "
        f"(gap = {_delta_str(gap_val)}). "
        f"Um gap positivo indica que o modelo performa bem em prever `y1`, "
        f"mas essa performance vem de aprender particularidades da percepção comunitária "
        f"que não se traduzem em alinhamento com a calculadora. "
        f"Esse tipo de modelo é o mais informativo para entender a divergência entre as duas fontes.\n"
    )

    # ------------------------------------------------------------------
    # 6. Referência cruzada: concordância base (y1 vs y2 sem modelo)
    # ------------------------------------------------------------------
    lines.append("## 6. Referência: concordância direta y1 vs y2 (Fase B)\n")
    lines.append(
        "Para contextualizar os números acima, a Fase B reportou que `y1` e `y2` "
        "concordam exatamente em **60,9%** dos decks da base modelável, "
        "e dentro de ±1 em **97,7%**. "
        "Os modelos treinados em `y1` tendem a produzir `ŷ1` próximos de `y1`, "
        "portanto espera-se concordância similar com `y2` — ligeiramente diferente "
        "dependendo do viés e representação do algoritmo.\n"
    )

    # ------------------------------------------------------------------
    # 7. Artefatos
    # ------------------------------------------------------------------
    lines.append("## 7. Artefatos\n")
    lines.append("- `documents/reports/results/phase_i_model_vs_calculator.md` — este relatório")
    lines.append("- Todos os dados lidos de `experiments/*/predictions_per_fold.jsonl` (campo `y2`)")
    lines.append("- Nenhum novo artefato gerado em `experiments/` — análise puramente descritiva")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase I — Model predictions vs. calculator (y2) comparison.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--experiment-dir", dest="experiment_dir", type=Path,
                        default=Path("experiments"), metavar="DIR")
    parser.add_argument("--docs-dir", dest="docs_dir", type=Path,
                        default=Path("documents"), metavar="DIR")
    parser.add_argument("--spot-check-summary", dest="spot_check_summary", type=Path,
                        default=Path("experiments/spot_check/summary.json"), metavar="PATH")
    args = parser.parse_args()

    voting_dir  = args.experiment_dir / "voting"
    report_path = args.docs_dir / "reports" / "results" / "phase_i_model_vs_calculator.md"

    log("[Phase I] Iniciando comparacao com a calculadora (y2)...")

    # ------------------------------------------------------------------
    # Discover models
    # ------------------------------------------------------------------
    log("[Phase I] Carregando modelos individuais (Fase E)...")
    individual = load_individual_models(args.experiment_dir, args.spot_check_summary)
    log(f"[Phase I] {len(individual)} modelo(s) individual(is).")

    log("[Phase I] Carregando ensembles (Fase G)...")
    ensembles = load_ensemble_models(voting_dir)
    log(f"[Phase I] {len(ensembles)} ensemble(s).")

    all_models = individual + ensembles
    if not all_models:
        sys.exit("[Phase I] Nenhum modelo encontrado.")

    # ------------------------------------------------------------------
    # Compute metrics for each model
    # ------------------------------------------------------------------
    results = []
    for model in all_models:
        mid = model["model_id"]
        log(f"  [{mid}] computando metricas vs y2...")
        rows = read_jsonl(model["predictions_path"])

        # Filter rows with valid y2
        valid = [r for r in rows if r.get("y2") is not None
                 and r.get("y_pred") is not None
                 and r["y2"] in CLASSES and r["y_pred"] in CLASSES]

        metrics = compute_agreement_metrics(valid)
        subset  = compute_subset_metrics(valid)

        results.append({
            "model_id":       mid,
            "type":           model["type"],
            "representation": model["representation"],
            "algorithm":      model["algorithm"],
            "macro_f1_y1":    model["macro_f1_y1"],
            "metrics":        metrics,
            "subset":         subset,
        })

    # ------------------------------------------------------------------
    # Generate report
    # ------------------------------------------------------------------
    log("[Phase I] Gerando relatorio...")
    report = render_report(all_models, results)
    write_text(report_path, report)
    log(f"[Phase I] Relatorio -> {report_path}")
    log("[Phase I] Concluido.")


if __name__ == "__main__":
    main()
