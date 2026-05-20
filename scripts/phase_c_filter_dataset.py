#!/usr/bin/env python3
"""Phase C.1 — freeze the modelable Archidekt snapshot set.

The modeling target is y1 (Archidekt bracket), but the project intentionally
keeps only snapshots where both y1 and y2 are in {2, 3, 4}. The excluded decks
are written separately for qualitative analysis and auditability.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - exercised by console script and direct import tests
    from preprocessing import iter_jsonl, split_modeling_records, write_jsonl  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.preprocessing import iter_jsonl, split_modeling_records, write_jsonl  # type: ignore


DEFAULT_PROCESSED_DIR = Path("data/processed/archidekt")
DEFAULT_DOCS_DIR = Path("documents/reports/results")
REPORT_FILENAME = "phase_c_preprocessing.md"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_snapshot_ids(path: Path, snapshot_ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for index, snapshot_id in enumerate(snapshot_ids):
            comma = "," if index < len(snapshot_ids) - 1 else ""
            handle.write(json.dumps(snapshot_id, ensure_ascii=False))
            handle.write(comma)
            handle.write("\n")
        handle.write("]\n")


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    """Render preprocessing_report.md from the Phase-C run summary.

    The C.1 filter numbers come from the live manifest; the C.2/C.3/C.4 sections
    document the methodology baked into scripts/preprocessing.py — those don't
    change between runs but they belong in the report alongside the runtime
    output so the reader sees the full Fase-C picture.
    """
    reasons = summary.get("exclusion_reasons") or {}
    reason_rows = sorted(
        ((reason, count) for reason, count in reasons.items() if reason != "included"),
        key=lambda item: (-int(item[1]), item[0]),
    )
    outputs = summary.get("outputs") or {}

    lines: List[str] = [
        "# Report da Fase C — Pré-processamento",
        "",
        f"*Gerado automaticamente em `{summary.get('generated_at', utc_now_iso())}`.*",
        "",
        "## Objetivo",
        "",
        "Congelar a base modelável (`y1, y2 ∈ {2,3,4}`) e registrar as transformações sem vazamento aplicadas pelos modelos das Fases D e E. O alvo único é `y1` (`archidekt_edh_bracket`); `y2` é preservado para comparação descritiva (Fase G), nunca como feature.",
        "",
        "## Entrada e saída",
        "",
        "| Item | Valor |",
        "|---|---|",
        f"| Origem | `{summary.get('source', '')}` |",
        f"| Snapshot ids modeláveis | `{outputs.get('snapshot_ids', '')}` |",
        f"| Decks excluídos (audit) | `{outputs.get('excluded', '')}` |",
        f"| Manifesto JSON | `{outputs.get('manifest', '')}` |",
        "",
        "## C.1 Filtro da base modelável",
        "",
        "Mantém apenas decks com `y1 ∈ {2,3,4}` e `y2 ∈ {2,3,4}`. Os excluídos não são removidos do snapshot original — ficam preservados em `modeling_excluded.jsonl` para análise qualitativa (Fase B) e auditoria.",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Total de decks no snapshot | {summary.get('total_decks', 0):,} |",
        f"| Decks incluídos | {summary.get('included', 0):,} |",
        f"| Decks excluídos | {summary.get('excluded', 0):,} |",
        "",
    ]

    if reason_rows:
        lines.extend([
            "### Motivos de exclusão",
            "",
            "| Motivo | Quantidade |",
            "|---|---:|",
        ])
        for reason, count in reason_rows:
            lines.append(f"| `{reason}` | {int(count):,} |")
        lines.append("")

    lines.extend([
        "## C.2 Deck Features",
        "",
        "Aplicado fold a fold pelos modelos da Fase D/E (fit apenas no treino do fold), via `scripts/preprocessing.py::DeckFeaturePreprocessor`:",
        "",
        "- inferência das colunas numéricas permitidas, excluindo `y1`, `y2`, `delta`, `abs_delta`, `edhpowerlevel`, `edhpowerlevel_bracket` e metadados;",
        "- imputação por mediana do treino para colunas `edhrec_rank_*` e `salt_*`;",
        "- winsorização de `price_total` no p99 do treino;",
        "- remoção de colunas com variância zero no treino;",
        "- `StandardScaler` opcional (ligado para `logistic_regression`, `linear_svc` e `knn`; desligado para árvores, ensembles e Naive Bayes).",
        "",
        "## C.3 Bag of Cards",
        "",
        "Aplicado fold a fold pelos modelos da Fase D/E, via `scripts/preprocessing.py::BagOfCardsPreprocessor`:",
        "",
        "- contagem por carta usando somente o treino do fold (sem vazamento de cartas de teste);",
        "- pruning por `bc_min_df` (valor decidido na Fase D entre `{5, 10, 20}`);",
        "- matriz `scipy.sparse.csr_matrix`;",
        "- variante `use_tfidf` disponível mas **desligada** na Fase D; pode ser ativada como hiperparâmetro em fases posteriores para algoritmos que se beneficiam de IDF (ex.: `LinearSVC`). Permanece incompatível com `MultinomialNB`.",
        "",
        "## C.4 Antivazamento",
        "",
        "- Toda transformação faz `fit` apenas no treino do fold (nunca no teste).",
        "- `y2`, `delta`, `abs_delta` e todos os campos `edhpowerlevel.*` (score, power_level, etc.) **nunca** entram em `X` — bloqueio explícito em `is_leakage_column`.",
        "- `y1` é o único target; não há modelo previsto para `y2`.",
        "- Os mesmos folds são usados para todos os algoritmos em cada repeat (ver `experiments/folds.json` gerado pela Fase E).",
        "",
        "## Saídas geradas",
        "",
    ])
    for label, value in outputs.items():
        lines.append(f"- `{label}`: `{value}`")
    if not outputs:
        lines.append("- _nenhuma saída registrada nesta rodada_")
    lines.append("")
    lines.extend([
        "## Próximo passo",
        "",
        "Executar `uv run run-mtg-pipeline spot-checking` para a Fase D — o filtro acima alimenta o seletor top-5 por representação que define o conjunto da Fase E.",
        "",
    ])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter Phase-C modelable decks and write excluded deck audit records.",
    )
    parser.add_argument(
        "--features-path",
        type=Path,
        default=DEFAULT_PROCESSED_DIR / "deck_features.jsonl",
        help="Input deck_features.jsonl produced by build-archidekt-features.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Directory for modeling_snapshot_ids.json, modeling_excluded.jsonl, and manifest.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=None,
        help=(
            "Directory where preprocessing_report.md is written. Defaults to None "
            "(no markdown report). The pipeline passes documents/ here; tests can omit it."
        ),
    )
    parser.add_argument(
        "--snapshot-ids-name",
        default="modeling_snapshot_ids.json",
        help="Output filename for included snapshot ids.",
    )
    parser.add_argument(
        "--excluded-name",
        default="modeling_excluded.jsonl",
        help="Output filename for excluded deck audit rows.",
    )
    parser.add_argument(
        "--manifest-name",
        default="modeling_dataset_manifest.json",
        help="Output filename for the Phase-C filter manifest.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    features_path: Path = args.features_path
    if not features_path.exists():
        raise FileNotFoundError(f"Expected {features_path} — run build-archidekt-features first.")

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_ids_path = out_dir / args.snapshot_ids_name
    excluded_path = out_dir / args.excluded_name
    manifest_path = out_dir / args.manifest_name

    records = list(iter_jsonl(features_path))
    included, excluded, reasons = split_modeling_records(records)
    snapshot_ids = [record["snapshot_id"] for record in included if isinstance(record.get("snapshot_id"), str)]

    write_snapshot_ids(snapshot_ids_path, snapshot_ids)
    write_jsonl(excluded_path, excluded)

    reason_dict = dict(sorted(reasons.items()))
    summary: Dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "source": str(features_path),
        "total_decks": len(records),
        "included": len(included),
        "excluded": len(excluded),
        "exclusion_reasons": reason_dict,
        "outputs": {
            "snapshot_ids": str(snapshot_ids_path),
            "excluded": str(excluded_path),
            "manifest": str(manifest_path),
        },
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    docs_dir: Optional[Path] = args.docs_dir
    if docs_dir is not None:
        report_path = docs_dir / REPORT_FILENAME
        write_report(report_path, summary)
        summary["outputs"]["report"] = str(report_path)

    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

