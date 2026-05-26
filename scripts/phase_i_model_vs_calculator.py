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
from typing import Dict, List, Optional

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


def comparable_rows(rows: List[Dict], *, label_key: str) -> List[Dict]:
    """Rows with valid y2 and a valid comparison label."""
    return [
        r for r in rows
        if r.get("y2") is not None
        and r.get(label_key) is not None
        and r["y2"] in CLASSES
        and r[label_key] in CLASSES
    ]


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


def compute_agreement_metrics(
    rows: List[Dict],
    *,
    label_key: str = "y_pred",
    matrix_key: str = "cm_label_vs_y2",
) -> Dict:
    """
    Compute agreement metrics between a chosen label column and y2.

    Returns dict with:
      n, exact_agreement, near_agreement, mean_abs_delta,
      macro_f1_vs_y2, matrix_key (rows=label, cols=y2)
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "exact_agreement": None, "near_agreement": None,
                "mean_abs_delta": None, "macro_f1_vs_y2": None,
                matrix_key: None}

    y_label = [r[label_key] for r in rows]
    y2      = [r["y2"] for r in rows]

    exact = sum(1 for p, t in zip(y_label, y2) if p == t)
    near  = sum(1 for p, t in zip(y_label, y2) if abs(p - t) <= 1)
    deltas = [abs(p - t) for p, t in zip(y_label, y2)]

    # confusion matrix: rows = chosen label, cols = y2
    label_idx = {c: i for i, c in enumerate(CLASSES)}
    nc = len(CLASSES)
    cm = [[0] * nc for _ in range(nc)]
    for p, t in zip(y_label, y2):
        if p in label_idx and t in label_idx:
            cm[label_idx[p]][label_idx[t]] += 1

    return {
        "n": n,
        "exact_agreement": exact / n,
        "near_agreement":  near  / n,
        "mean_abs_delta":  statistics.mean(deltas),
        "macro_f1_vs_y2":  macro_f1(y2, y_label, CLASSES),
        matrix_key:        cm,
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
        "concordant": compute_agreement_metrics(
            concordant,
            label_key="y_pred",
            matrix_key="cm_pred_vs_y2",
        ),
        "discordant": compute_agreement_metrics(
            discordant,
            label_key="y_pred",
            matrix_key="cm_pred_vs_y2",
        ),
    }


def selected_algorithms_from_spot_check(summary: object) -> List[str]:
    """Read A_union from both current and legacy spot-check summary formats."""
    if not isinstance(summary, dict):
        return []

    legacy_union = summary.get("selection", {}).get("union", [])
    if legacy_union:
        return sorted({str(algo) for algo in legacy_union})

    rankings = summary.get("rankings", {})
    selected = set()
    if isinstance(rankings, dict):
        for representation in ("DF", "BC"):
            rows = rankings.get(representation, [])
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("selected"):
                        algorithm = row.get("algorithm")
                        if algorithm:
                            selected.add(str(algorithm))
    return sorted(selected)


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
        algos = selected_algorithms_from_spot_check(summary)
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
        members: List[str] = []
        if metrics_path.exists():
            m = read_json(metrics_path)
            folds = m.get("folds", [])
            f1s = [f["macro_f1"] for f in folds if "macro_f1" in f]
            if f1s:
                macro_f1_y1 = statistics.mean(f1s)
            members = [str(member) for member in m.get("members", [])]

        member_reps = {
            member.split("_", 1)[0].upper()
            for member in members
            if member.startswith(("bc_", "df_"))
        }
        if len(member_reps) == 1:
            representation = next(iter(member_reps))
        elif len(member_reps) > 1:
            representation = "BC+DF"
        else:
            representation = "ensemble"

        ensembles.append({
            "model_id": d.name,
            "type": "ensemble",
            "representation": representation,
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


def _signed_gap(row: Dict) -> Optional[float]:
    f1 = row.get("macro_f1_y1")
    ea = row["metrics"].get("exact_agreement")
    if f1 is None or ea is None:
        return None
    return f1 - ea


def _abs_gap(row: Dict) -> float:
    gap = _signed_gap(row)
    return abs(gap) if gap is not None else -1.0


def _global_highlight_justification(kind: str, row: Dict) -> str:
    exact = _pct(row["metrics"]["exact_agreement"])
    gap = _fmt(_abs_gap(row))
    if kind == "maior concordância":
        return f"maior concordância exata com y2 entre todos os modelos ({exact})"
    if kind == "menor concordância":
        return f"menor concordância exata com y2 entre todos os modelos ({exact})"
    if kind == "maior gap absoluto":
        return f"maior distância absoluta entre macro-F1(y1) e concordância com y2 entre todos os modelos ({gap})"
    if kind == "menor gap absoluto":
        return f"menor distância absoluta entre macro-F1(y1) e concordância com y2 entre todos os modelos ({gap})"
    return ""


def cm_to_markdown(
    cm: List[List[int]],
    labels: List[int],
    title: str,
    *,
    row_label: str,
    row_description: str,
) -> List[str]:
    """Render confusion matrix (rows=chosen label, cols=y2) as markdown."""
    lines = [f"**{title}** — linhas = {row_description}, colunas = y2 (calculadora)\n"]
    header = f"| {row_label} \\ y2 |" + "".join(f" {lb} |" for lb in labels)
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
    baseline: Dict,
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
    lines.append(
        "**Importante**: a Fase I não treina nem retreina modelos. "
        "Ela apenas lê as predições out-of-fold já salvas pela Fase E "
        "(`experiments/<modelo>/predictions_per_fold.jsonl`) e pela Fase G "
        "(`experiments/voting/<ensemble>/predictions_per_fold.jsonl`) e compara "
        "`ŷ1` com `y2`.\n"
    )

    # ------------------------------------------------------------------
    # 1. Referência direta — y1 vs y2
    # ------------------------------------------------------------------
    lines.append("## 1. Referência direta: y1 real do Archidekt vs y2\n")
    lines.append(
        "Esta é a comparação sem modelo: `y1` é o bracket real extraído do Archidekt "
        "e `y2` é o bracket calculado pela EDHPowerLevel. Ela é calculada na mesma "
        "base OOF usada pelos modelos, para manter a comparação direta com `ŷ1`.\n"
    )
    lines.append("| Comparação | n | Concord. exata | Concord. ±1 | Delta abs. médio | Macro-F1 vs y2 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(
        f"| `y1` real vs `y2` | {baseline['n']} "
        f"| {_pct(baseline['exact_agreement'])} "
        f"| {_pct(baseline['near_agreement'])} "
        f"| {_fmt(baseline['mean_abs_delta'], 3)} "
        f"| {_fmt(baseline['macro_f1_vs_y2'])} |"
    )
    lines.append("")
    lines.extend(cm_to_markdown(
        baseline["cm_y1_vs_y2"],
        CLASSES,
        "`y1` real vs `y2`",
        row_label="y1",
        row_description="y1 real do Archidekt",
    ))
    lines.append("")

    # ------------------------------------------------------------------
    # 2. Tabela completa — todos os modelos
    # ------------------------------------------------------------------
    lines.append("## 2. Concordância de ŷ1 com y2 — todos os modelos\n")
    lines.append(
        "Aqui `ŷ1` é o label predito por cada modelo treinado em `y1`. "
        "A tabela usa exatamente as mesmas métricas da seção anterior, agora trocando "
        "`y1` real por `ŷ1`.\n"
    )
    lines.append(
        "| Modelo | Tipo | Repr. | Macro-F1 (y1) | Concord. exata ŷ1=y2 | Concord. ±1 | "
        "Delta abs. médio | Macro-F1 vs y2 |"
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
    # 3. Absolute gap: macro-F1(y1) vs exact agreement with y2
    # ------------------------------------------------------------------
    lines.append("\n## 3. Gap absoluto entre desempenho em y1 e concordância com y2\n")
    lines.append(
        "> Aqui o gap é uma distância absoluta: "
        "`abs(macro-F1 em y1 − concordância exata entre ŷ1 e y2)`. "
        "Quanto maior o valor, maior o desalinhamento entre o desempenho do modelo "
        "no alvo comunitário e sua concordância com a calculadora. "
        "A tabela está ordenada por esse gap absoluto.\n"
    )
    lines.append("| Modelo | Tipo | Repr. | Macro-F1 (y1) | Concord. exata (y2) | Gap absoluto | Diferença assinada |")
    lines.append("|---|---|---|---:|---:|---:|---:|")

    gap_sorted = sorted(
        results,
        key=_abs_gap,
        reverse=True,
    )
    for r in gap_sorted:
        f1 = r["macro_f1_y1"]
        ea = r["metrics"]["exact_agreement"]
        signed_gap = _signed_gap(r)
        abs_gap = abs(signed_gap) if signed_gap is not None else None
        lines.append(
            f"| `{r['model_id']}` | {r['type']} | {r['representation']} "
            f"| {_fmt(f1)} | {_pct(ea)} | {_fmt(abs_gap)} | {_delta_str(signed_gap)} |"
        )

    # ------------------------------------------------------------------
    # 4. Análise por subconjunto: y1==y2 vs y1!=y2
    # ------------------------------------------------------------------
    lines.append("\n## 4. Análise por subconjunto: decks concordantes vs discordantes\n")
    lines.append(
        "> **Concordante**: decks onde `y1 == y2` — comunidade e calculadora atribuem o mesmo bracket.\n"
        "> **Discordante**: decks onde `y1 != y2` — as fontes divergem.\n"
        "> Métricas: concordância exata entre ŷ1 e y2 dentro de cada subconjunto. "
        "A tabela está ordenada pela concordância no subconjunto discordante, "
        "que é onde a divergência entre as fontes aparece.\n"
    )
    lines.append(
        "| Modelo | Tipo | Concord. exata (todos) | "
        "Concord. exata (y1=y2, n≈7395×3) | Concord. exata (y1≠y2, n≈4740×3) |"
    )
    lines.append("|---|---|---:|---:|---:|")

    subset_sorted = sorted(
        results,
        key=lambda r: r["subset"]["discordant"]["exact_agreement"] or 0,
        reverse=True,
    )
    for r in subset_sorted:
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
    # 5. Global highlights
    # ------------------------------------------------------------------
    best_agree = sorted_results[0]
    worst_agree = sorted_results[-1]
    largest_gap = gap_sorted[0]
    smallest_gap = gap_sorted[-1]
    highlight_rows = [
        ("maior concordância", best_agree),
        ("menor concordância", worst_agree),
        ("maior gap absoluto", largest_gap),
        ("menor gap absoluto", smallest_gap),
    ]

    lines.append("\n## 5. Destaques globais\n")
    lines.append(
        "Considerando todos os modelos e ensembles juntos, seleciono apenas quatro casos: "
        "maior concordância, menor concordância, maior gap absoluto e menor gap absoluto. "
        "Isso mantém a seção focada nos extremos realmente informativos, independente de "
        "a origem ser `BC`, `DF` ou `BC+DF`.\n"
    )
    lines.append(
        "| Caso | Modelo | Tipo | Repr. | Concord. exata | Macro-F1 (y1) | "
        "Gap absoluto | Diferença assinada | Justificativa |"
    )
    lines.append("|---|---|---|---|---:|---:|---:|---:|---|")
    for case, row in highlight_rows:
        signed_gap = _signed_gap(row)
        lines.append(
            f"| {case} | `{row['model_id']}` | {row['type']} | {row['representation']} "
            f"| {_pct(row['metrics']['exact_agreement'])} "
            f"| {_fmt(row['macro_f1_y1'])} "
            f"| {_fmt(_abs_gap(row))} "
            f"| {_delta_str(signed_gap)} "
            f"| {_global_highlight_justification(case, row)} |"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # 6. Confusion matrices — global highlights
    # ------------------------------------------------------------------
    lines.append("## 6. Matrizes de confusão ŷ1 × y2 — destaques globais\n")
    lines.append(
        "> Linhas = ŷ1 (o que o modelo previu para bracket comunitário), "
        "colunas = y2 (o que a calculadora atribuiu). "
        "A diagonal principal = concordância exata ŷ1 = y2.\n"
    )
    lines.append(
        f"As matrizes abaixo somam {results[0]['metrics']['n'] if results else 0} entradas "
        "porque são calculadas sobre predições OOF: 12.135 decks × 3 repeats. "
        "Assim, cada deck pode contribuir até três vezes, uma por repeat.\n"
    )

    seen_models = set()
    for case, row in highlight_rows:
        if row["model_id"] in seen_models:
            continue
        seen_models.add(row["model_id"])
        roles = [
            role
            for role, role_row in highlight_rows
            if role_row["model_id"] == row["model_id"]
        ]
        role_str = ", ".join(roles)
        justification = "; ".join(
            _global_highlight_justification(role, row)
            for role in roles
        )
        lines.append(f"### `{row['model_id']}` ({role_str})\n")
        lines.append(f"Justificativa: {justification}.\n")
        cm_lines = cm_to_markdown(
            row["metrics"]["cm_pred_vs_y2"],
            CLASSES,
            row["model_id"],
            row_label="ŷ1",
            row_description="ŷ1 (previsto pelo modelo)",
        )
        lines.extend(cm_lines)
        lines.append("")

    # ------------------------------------------------------------------
    # 7. Discussão comparativa
    # ------------------------------------------------------------------
    lines.append("## 7. Discussão comparativa\n")
    lines.append(
        "A leitura global destaca apenas os extremos relevantes. Maior concordância "
        "identifica o modelo mais próximo da calculadora; menor concordância identifica "
        "o mais distante; maior gap absoluto mostra onde desempenho em `y1` e concordância "
        "com `y2` mais se separam; menor gap absoluto mostra o caso em que essas duas "
        "medidas ficam mais próximas.\n"
    )

    # ------------------------------------------------------------------
    # 8. Comparação compacta y1 vs y2 e melhor ŷ1 vs y2
    # ------------------------------------------------------------------
    best = best_agree
    lines.append("## 8. Comparação compacta: `y1` vs `y2` e melhor `ŷ1` vs `y2`\n")
    lines.append("| Comparação | Concord. exata | Concord. ±1 | Delta abs. médio | Macro-F1 vs y2 |")
    lines.append("|---|---:|---:|---:|---:|")
    lines.append(
        f"| `y1` real vs `y2` "
        f"| {_pct(baseline['exact_agreement'])} "
        f"| {_pct(baseline['near_agreement'])} "
        f"| {_fmt(baseline['mean_abs_delta'], 3)} "
        f"| {_fmt(baseline['macro_f1_vs_y2'])} |"
    )
    lines.append(
        f"| melhor `ŷ1` vs `y2` (`{best['model_id']}`) "
        f"| {_pct(best['metrics']['exact_agreement'])} "
        f"| {_pct(best['metrics']['near_agreement'])} "
        f"| {_fmt(best['metrics']['mean_abs_delta'], 3)} "
        f"| {_fmt(best['metrics']['macro_f1_vs_y2'])} |"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 9. Artefatos
    # ------------------------------------------------------------------
    lines.append("## 9. Artefatos\n")
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

        valid = comparable_rows(rows, label_key="y_pred")

        metrics = compute_agreement_metrics(
            valid,
            label_key="y_pred",
            matrix_key="cm_pred_vs_y2",
        )
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

    baseline_rows = comparable_rows(
        read_jsonl(all_models[0]["predictions_path"]),
        label_key="y_true",
    )
    baseline = compute_agreement_metrics(
        baseline_rows,
        label_key="y_true",
        matrix_key="cm_y1_vs_y2",
    )

    # ------------------------------------------------------------------
    # Generate report
    # ------------------------------------------------------------------
    log("[Phase I] Gerando relatorio...")
    report = render_report(all_models, results, baseline)
    write_text(report_path, report)
    log(f"[Phase I] Relatorio -> {report_path}")
    log("[Phase I] Concluido.")


if __name__ == "__main__":
    main()
