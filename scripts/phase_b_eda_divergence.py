#!/usr/bin/env python3
"""Phase B — EDA and direct divergence analysis.

Reads ``data/processed/archidekt/deck_features.jsonl`` (12,950 decks, 114
features + y1 + edhpowerlevel) and produces:

  - ``documents/eda_report.md``
  - ``documents/divergence_report.md``
  - ``documents/figures/eda/*.png``
  - ``documents/figures/divergence/*.png``

Both reports are independent of any modeling: they describe the data and
quantify the divergence between y1 (Archidekt) and y2 (EDHPowerLevel).
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DATA = Path("data/processed/archidekt")
DOCS = Path("documents")
FIG_EDA = DOCS / "figures" / "eda"
FIG_DIV = DOCS / "figures" / "divergence"


def configure_paths(data_dir: Path, docs_dir: Path) -> None:
    global DATA, DOCS, FIG_EDA, FIG_DIV
    DATA = data_dir
    DOCS = docs_dir
    FIG_EDA = DOCS / "figures" / "eda"
    FIG_DIV = DOCS / "figures" / "divergence"


def load_features() -> pd.DataFrame:
    """Load deck_features.jsonl with y1/y2 unpacked from the nested dict."""
    rows = []
    with (DATA / "deck_features.jsonl").open() as fh:
        for line in fh:
            r = json.loads(line)
            epl = r.get("edhpowerlevel") or {}
            r["y1"] = r.get("archidekt_edh_bracket")
            r["y2"] = epl.get("commander_bracket") if isinstance(epl, dict) else None
            for k in ("score", "power_level", "tipping_point", "efficiency", "impact", "average_playability"):
                v = epl.get(k) if isinstance(epl, dict) else None
                try:
                    r[f"epl_{k}"] = float(v) if v not in (None, "") else None
                except (ValueError, TypeError):
                    r[f"epl_{k}"] = None
            r.pop("edhpowerlevel", None)
            rows.append(r)
    return pd.DataFrame(rows)


def load_decks_minimal() -> pd.DataFrame:
    """Load only the snapshot_id + commander identifying info from decks.jsonl.

    Used to enrich the features DataFrame with commander names (the features
    table doesn't store names — it stores aggregate counts).
    """
    rows = []
    with (DATA / "decks.jsonl").open() as fh:
        for line in fh:
            d = json.loads(line)
            commanders = sorted({
                row.get("oracle_name")
                for row in (d.get("mainboard") or [])
                if row.get("is_commander") and row.get("oracle_name")
            })
            rows.append({
                "snapshot_id": d.get("snapshot_id"),
                "commander_signature": " // ".join(commanders) if commanders else None,
                "commander_count": len(commanders),
                "view_count": d.get("view_count"),
                "owner_id": d.get("owner_id"),
            })
    return pd.DataFrame(rows)


# ---------- helpers ----------------------------------------------------------

def save_fig(path: Path, fig: plt.Figure, *, dpi: int = 110) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def fmt_pct(part: float, total: float) -> str:
    return f"{(100*part/total):.1f}%" if total else "n/a"


# ---------- EDA --------------------------------------------------------------

def eda(df: pd.DataFrame, decks: pd.DataFrame) -> str:
    """Generate the EDA markdown report and figures. Returns markdown."""
    FIG_EDA.mkdir(parents=True, exist_ok=True)
    n = len(df)
    md = []
    md.append("# EDA — Análise Exploratória dos Dados")
    md.append("")
    md.append(f"Base: **{n:,} decks** processados (Archidekt y1 ∈ {{2,3,4}}, ≥1.000 views, 100 cartas no mainboard, validados em Commander). Cada deck tem 114 features agregadas (Deck Features) e duas famílias de label: `y1` (Archidekt, percepção do usuário) e `y2` (EDHPowerLevel, calculadora automatizada).")
    md.append("")

    # --- 1. Distribuição dos rótulos
    md.append("## 1. Distribuição dos rótulos")
    md.append("")
    y1_counts = df["y1"].value_counts().sort_index()
    y2_counts = df["y2"].value_counts(dropna=False).sort_index()
    md.append("### y1 (Archidekt)")
    md.append("| Bracket | Decks | % |")
    md.append("|---:|---:|---:|")
    for k, v in y1_counts.items():
        md.append(f"| {k} | {v:,} | {fmt_pct(v, n)} |")
    md.append("")
    md.append("### y2 (EDHPowerLevel)")
    md.append("| Bracket | Decks | % |")
    md.append("|---:|---:|---:|")
    for k, v in y2_counts.items():
        label = str(k) if pd.notna(k) else "missing"
        md.append(f"| {label} | {v:,} | {fmt_pct(v, n)} |")
    md.append("")

    # Bar chart side-by-side
    fig, ax = plt.subplots(figsize=(8, 4))
    brackets = sorted(set(df["y1"].dropna().unique()) | set(df["y2"].dropna().unique()))
    x = np.arange(len(brackets))
    w = 0.4
    y1v = [int((df["y1"] == b).sum()) for b in brackets]
    y2v = [int((df["y2"] == b).sum()) for b in brackets]
    ax.bar(x - w/2, y1v, w, label="y1 (Archidekt)", color="#4C72B0")
    ax.bar(x + w/2, y2v, w, label="y2 (EDHPowerLevel)", color="#C44E52")
    ax.set_xticks(x); ax.set_xticklabels(brackets)
    ax.set_xlabel("Bracket"); ax.set_ylabel("Quantidade de decks")
    ax.set_title("Distribuição de y1 e y2")
    ax.legend()
    save_fig(FIG_EDA / "y1_y2_distribution.png", fig)
    md.append("![y1 vs y2](figures/eda/y1_y2_distribution.png)")
    md.append("")
    md.append(f"**Observação**: a calculadora produz brackets fora de {{2,3,4}} (b1 e b5), enquanto o Archidekt já vem filtrado nesse intervalo. Para a modelagem multiclasse, manteremos apenas decks com **y1 e y2 ∈ {{2,3,4}}** (Fase C). Isso descarta {(df['y2'].isin([1,5]).sum()):,} decks ({fmt_pct((df['y2'].isin([1,5])).sum(), n)}).")
    md.append("")

    # --- 2. Balanceamento de classes (modeling base)
    md.append("## 2. Balanceamento de classes na base modelável")
    md.append("")
    mask_model = df["y1"].isin([2,3,4]) & df["y2"].isin([2,3,4])
    nm = mask_model.sum()
    md.append(f"Base modelável: **{nm:,} decks** (y1 e y2 ∈ {{2,3,4}}).")
    md.append("")
    for label, col in [("y1 (Archidekt)", "y1"), ("y2 (EDHPowerLevel)", "y2")]:
        md.append(f"### {label}")
        c = df.loc[mask_model, col].value_counts().sort_index()
        md.append("| Bracket | Decks | % |")
        md.append("|---:|---:|---:|")
        for k, v in c.items():
            md.append(f"| {k} | {v:,} | {fmt_pct(v, nm)} |")
        md.append("")
    md.append("Conclusão: classe 3 domina em ambos os labels. Macro-F1 será a métrica principal (ver Fase E).")
    md.append("")

    # --- 3. Cores
    md.append("## 3. Cores")
    md.append("")
    cc = df["deck_color_count"].value_counts().sort_index()
    md.append("### Quantidade de cores por deck")
    md.append("| Cores | Decks | % |")
    md.append("|---:|---:|---:|")
    for k, v in cc.items():
        md.append(f"| {int(k)} | {v:,} | {fmt_pct(v, n)} |")
    md.append("")
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(cc.index.astype(int), cc.values, color="#55A868")
    ax.set_xlabel("Quantidade de cores"); ax.set_ylabel("Decks")
    ax.set_title("Distribuição de quantidade de cores por deck")
    save_fig(FIG_EDA / "color_count_distribution.png", fig)
    md.append("![Color count](figures/eda/color_count_distribution.png)")
    md.append("")

    md.append("### Presença de cada cor")
    md.append("| Cor | Decks | % |")
    md.append("|---|---:|---:|")
    for c in ["W","U","B","R","G"]:
        v = int(df[f"has_{c}"].sum())
        md.append(f"| {c} | {v:,} | {fmt_pct(v, n)} |")
    md.append("")
    fig, ax = plt.subplots(figsize=(6, 3.5))
    cols = ["W","U","B","R","G"]
    vals = [int(df[f"has_{c}"].sum()) for c in cols]
    palette = ["#F0E68C", "#6CA9E2", "#444444", "#D55E5E", "#7FBF7F"]
    ax.bar(cols, vals, color=palette)
    ax.set_ylabel("Decks"); ax.set_title("Presença de cada cor")
    save_fig(FIG_EDA / "color_presence.png", fig)
    md.append("![Color presence](figures/eda/color_presence.png)")
    md.append("")

    # --- 4. Estrutura do deck
    md.append("## 4. Estrutura do deck")
    md.append("")
    md.append("Estatísticas básicas (mediana / média / desvio):")
    md.append("")
    struct_feats = ["unique_card_count","commander_card_count","land_count","nonland_count","basic_land_count","nonbasic_land_count"]
    md.append("| Feature | Mediana | Média | Desvio |")
    md.append("|---|---:|---:|---:|")
    for f in struct_feats:
        md.append(f"| `{f}` | {df[f].median():.1f} | {df[f].mean():.2f} | {df[f].std():.2f} |")
    md.append("")

    # --- 5. Curva de mana
    md.append("## 5. Curva de mana")
    md.append("")
    md.append(f"CMC médio por deck (média da base): **{df['cmc_mean'].mean():.2f}** (mediana {df['cmc_mean'].median():.2f}).")
    md.append("")
    cmc_buckets = ["cmc_0_count","cmc_1_count","cmc_2_count","cmc_3_count","cmc_4_count","cmc_5_count","cmc_6_plus_count"]
    avg_curve = df[cmc_buckets].mean()
    fig, ax = plt.subplots(figsize=(8, 3.5))
    labels = ["0","1","2","3","4","5","6+"]
    ax.bar(labels, avg_curve.values, color="#4C72B0")
    ax.set_xlabel("CMC"); ax.set_ylabel("Cartas (média da base)")
    ax.set_title("Curva de mana média (todos os decks)")
    save_fig(FIG_EDA / "mana_curve_avg.png", fig)
    md.append("![Mana curve](figures/eda/mana_curve_avg.png)")
    md.append("")

    # Curva de mana por bracket y1
    fig, ax = plt.subplots(figsize=(9, 4))
    for b, color in zip([2,3,4], ["#55A868","#4C72B0","#C44E52"]):
        sub = df[df["y1"] == b]
        ax.plot(labels, sub[cmc_buckets].mean(), marker="o", label=f"y1={b}", color=color)
    ax.set_xlabel("CMC"); ax.set_ylabel("Cartas (média)")
    ax.set_title("Curva de mana média por bracket Archidekt")
    ax.legend()
    save_fig(FIG_EDA / "mana_curve_by_y1.png", fig)
    md.append("![Mana curve by y1](figures/eda/mana_curve_by_y1.png)")
    md.append("")

    # --- 6. Tipos de carta
    md.append("## 6. Tipos de carta")
    md.append("")
    type_feats = ["creature_count","instant_count","sorcery_count","artifact_count","enchantment_count","planeswalker_count","land_count","nonland_permanent_count"]
    md.append("Médias da base:")
    md.append("")
    md.append("| Tipo | Média |")
    md.append("|---|---:|")
    for f in type_feats:
        md.append(f"| `{f}` | {df[f].mean():.1f} |")
    md.append("")

    # --- 7. Flags de bracket
    md.append("## 7. Flags de bracket (sinais estruturais)")
    md.append("")
    bracket_feats = ["game_changer_count","extra_turns_count","tutor_count","mass_land_denial_count","two_card_combo_singleton_count"]
    md.append("| Flag | Média | Mediana | % decks com ≥1 |")
    md.append("|---|---:|---:|---:|")
    for f in bracket_feats:
        md.append(f"| `{f}` | {df[f].mean():.2f} | {df[f].median():.0f} | {fmt_pct((df[f] >= 1).sum(), n)} |")
    md.append("")

    fig, axes = plt.subplots(1, len(bracket_feats), figsize=(15, 3.5))
    for ax, f in zip(axes, bracket_feats):
        data = [df.loc[df["y1"]==b, f].values for b in [2,3,4]]
        ax.boxplot(data, tick_labels=[2,3,4], showfliers=False)
        ax.set_title(f.replace("_count","").replace("_"," "), fontsize=9)
        ax.set_xlabel("y1")
    fig.suptitle("Flags de bracket por y1 (sem outliers)")
    save_fig(FIG_EDA / "bracket_flags_by_y1.png", fig)
    md.append("![Bracket flags by y1](figures/eda/bracket_flags_by_y1.png)")
    md.append("")

    # --- 8. Popularidade, preço, salt
    md.append("## 8. Popularidade, preço e salt")
    md.append("")
    md.append("| Feature | Média | Mediana | NaN |")
    md.append("|---|---:|---:|---:|")
    for f in ["edhrec_rank_mean","salt_mean","price_total","price_mean"]:
        md.append(f"| `{f}` | {df[f].mean():.2f} | {df[f].median():.2f} | {df[f].isna().sum():,} |")
    md.append("")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, f, title, log in zip(axes,
                                  ["price_total","salt_mean","edhrec_rank_mean"],
                                  ["Preço total ($)","Salt médio","EDHREC rank médio"],
                                  [True, False, False]):
        data = [df.loc[df["y1"]==b, f].dropna().values for b in [2,3,4]]
        ax.boxplot(data, tick_labels=[2,3,4], showfliers=False)
        ax.set_title(title); ax.set_xlabel("y1")
        if log: ax.set_yscale("log")
    fig.suptitle("Popularidade / preço / salt por bracket Archidekt (sem outliers)")
    save_fig(FIG_EDA / "price_salt_edhrec_by_y1.png", fig)
    md.append("![Price/Salt/EDHREC by y1](figures/eda/price_salt_edhrec_by_y1.png)")
    md.append("")

    # --- 9. Combos
    md.append("## 9. Combos")
    md.append("")
    md.append("| Feature | Média | Mediana | % decks com ≥1 |")
    md.append("|---|---:|---:|---:|")
    for f in ["cards_with_atomic_combos_count","atomic_combo_refs_total","unique_atomic_combo_refs_count","two_card_combo_ids_total"]:
        if f in df.columns:
            md.append(f"| `{f}` | {df[f].mean():.2f} | {df[f].median():.0f} | {fmt_pct((df[f] >= 1).sum(), n)} |")
    md.append("")

    # --- 10. Raridade
    md.append("## 10. Raridade")
    md.append("")
    md.append("| Raridade | Média de cartas/deck |")
    md.append("|---|---:|")
    for f in ["common_count","uncommon_count","rare_count","mythic_count"]:
        if f in df.columns:
            md.append(f"| `{f}` | {df[f].mean():.1f} |")
    md.append("")

    # --- 11. Faltantes e outliers
    md.append("## 11. Valores faltantes e outliers")
    md.append("")
    nan_summary = df.isna().sum()
    nan_summary = nan_summary[nan_summary > 0].sort_values(ascending=False)
    if len(nan_summary):
        md.append("Features com valores faltantes:")
        md.append("")
        md.append("| Feature | NaN | % |")
        md.append("|---|---:|---:|")
        for f, v in nan_summary.items():
            md.append(f"| `{f}` | {v:,} | {fmt_pct(v, n)} |")
    else:
        md.append("Nenhuma feature numérica tem valor faltante na base.")
    md.append("")

    md.append("Outliers ilustrativos (top-3 por feature):")
    md.append("")
    md.append("| Feature | Top valores |")
    md.append("|---|---|")
    for f in ["price_total","salt_mean","edhrec_rank_mean","cmc_mean"]:
        top = df[f].dropna().sort_values(ascending=False).head(3).round(2).tolist()
        md.append(f"| `{f}` | {top} |")
    md.append("")

    # --- 12. Top commanders
    if decks is not None and "commander_signature" in decks.columns:
        merged = df.merge(decks[["snapshot_id","commander_signature","commander_count","view_count"]], on="snapshot_id", how="left")
        md.append("## 12. Comandantes mais frequentes")
        md.append("")
        top_cmd = merged["commander_signature"].value_counts().head(15)
        md.append("| Comandante | Decks | % base |")
        md.append("|---|---:|---:|")
        for name, v in top_cmd.items():
            md.append(f"| {name} | {v:,} | {fmt_pct(v, n)} |")
        md.append("")
        md.append(f"Comandantes únicos na base: **{merged['commander_signature'].nunique():,}**.")
        md.append(f"Mediana de decks por comandante: {merged['commander_signature'].value_counts().median():.0f}.")
        md.append(f"Decks com ≥2 comandantes (partner/background/etc): {(merged['commander_count']>=2).sum():,} ({fmt_pct((merged['commander_count']>=2).sum(), n)}).")
        md.append("")

    # --- 13. Correlação
    md.append("## 13. Correlação entre features (top 30 features numéricas)")
    md.append("")
    num = df.select_dtypes(include=[np.number]).copy()
    # Pick informative features (drop snapshot/y, and keep variance > 0)
    drop = {"y1","y2","archidekt_edh_bracket"}
    drop |= {c for c in num.columns if c.startswith("epl_")}
    num = num.drop(columns=[c for c in drop if c in num.columns])
    var = num.var().sort_values(ascending=False)
    keep = var.head(30).index.tolist()
    corr = num[keep].corr()
    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(keep))); ax.set_yticks(range(len(keep)))
    ax.set_xticklabels(keep, rotation=90, fontsize=7)
    ax.set_yticklabels(keep, fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.04)
    ax.set_title("Correlação de Pearson entre top-30 features (por variância)")
    save_fig(FIG_EDA / "feature_correlation.png", fig)
    md.append("![Feature correlation](figures/eda/feature_correlation.png)")
    md.append("")

    return "\n".join(md)


# ---------- Divergência ------------------------------------------------------

def divergence(df: pd.DataFrame, decks: pd.DataFrame) -> str:
    FIG_DIV.mkdir(parents=True, exist_ok=True)
    md = []
    md.append("# Análise Direta da Divergência y1 ↔ y2")
    md.append("")
    md.append("Esta análise é independente de qualquer modelo. Mede diretamente o quão longe a percepção comunitária (Archidekt, `y1`) está da avaliação automatizada (EDHPowerLevel, `y2`) em decks de Commander.")
    md.append("")
    md.append("**Definições**:")
    md.append("```text")
    md.append("delta     = y2 - y1")
    md.append("abs_delta = |y2 - y1|")
    md.append("```")
    md.append("")

    # --- Modelable subset (y1, y2 ∈ {2,3,4}) ---------------------------------
    base = df.dropna(subset=["y1","y2"]).copy()
    base["y1"] = base["y1"].astype(int)
    base["y2"] = base["y2"].astype(int)
    model = base[base["y1"].isin([2,3,4]) & base["y2"].isin([2,3,4])].copy()
    model["delta"] = model["y2"] - model["y1"]
    model["abs_delta"] = model["delta"].abs()
    n = len(model)

    md.append(f"Base usada nesta seção: **{n:,} decks** com y1 e y2 ∈ {{2,3,4}} (subconjunto modelável). Decks com y2 ∈ {{1, 5}} são analisados em separado na seção 7.")
    md.append("")

    # --- 1. Estatísticas de concordância
    md.append("## 1. Estatísticas de concordância")
    md.append("")
    exact = (model["delta"] == 0).sum()
    within1 = (model["abs_delta"] <= 1).sum()
    within2 = (model["abs_delta"] <= 2).sum()
    md.append("| Critério | Decks | % |")
    md.append("|---|---:|---:|")
    md.append(f"| Concordância exata (Δ=0) | {exact:,} | {fmt_pct(exact, n)} |")
    md.append(f"| Concordância dentro de ±1 | {within1:,} | {fmt_pct(within1, n)} |")
    md.append(f"| Concordância dentro de ±2 | {within2:,} | {fmt_pct(within2, n)} |")
    md.append("")
    md.append(f"**|Δ| médio**: {model['abs_delta'].mean():.3f} · **|Δ| mediano**: {model['abs_delta'].median():.0f}")
    md.append("")

    # --- 2. Matriz y1 × y2
    md.append("## 2. Matriz y1 × y2")
    md.append("")
    mat = pd.crosstab(model["y1"], model["y2"], rownames=["y1"], colnames=["y2"])
    md.append("Contagens absolutas:")
    md.append("")
    md.append("| y1 \\ y2 | 2 | 3 | 4 | total |")
    md.append("|---|---:|---:|---:|---:|")
    for y1 in [2,3,4]:
        row = [int(mat.loc[y1, y2]) if y2 in mat.columns and y1 in mat.index else 0 for y2 in [2,3,4]]
        md.append(f"| {y1} | {row[0]:,} | {row[1]:,} | {row[2]:,} | {sum(row):,} |")
    md.append("")
    md.append("Como % por linha (proporção de y2 dado y1):")
    md.append("")
    md.append("| y1 \\ y2 | 2 | 3 | 4 |")
    md.append("|---|---:|---:|---:|")
    for y1 in [2,3,4]:
        if y1 not in mat.index:
            md.append(f"| {y1} | 0% | 0% | 0% |")
            continue
        total_row = mat.loc[y1].sum()
        row = [(int(mat.loc[y1, y2])/total_row*100) if y2 in mat.columns else 0.0 for y2 in [2,3,4]]
        md.append(f"| {y1} | {row[0]:.1f}% | {row[1]:.1f}% | {row[2]:.1f}% |")
    md.append("")

    # Heatmap
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    grid = mat.reindex(index=[2,3,4], columns=[2,3,4], fill_value=0)
    im = ax.imshow(grid.values, cmap="Blues", aspect="auto")
    for i, y1 in enumerate([2,3,4]):
        for j, y2 in enumerate([2,3,4]):
            v = int(grid.loc[y1,y2])
            color = "white" if v > grid.values.max()/2 else "black"
            ax.text(j, i, f"{v}", ha="center", va="center", color=color, fontsize=10)
    ax.set_xticks([0,1,2]); ax.set_xticklabels([2,3,4]); ax.set_xlabel("y2 (EDHPowerLevel)")
    ax.set_yticks([0,1,2]); ax.set_yticklabels([2,3,4]); ax.set_ylabel("y1 (Archidekt)")
    ax.set_title("Matriz y1 × y2 (contagens)")
    fig.colorbar(im, ax=ax)
    save_fig(FIG_DIV / "y1_x_y2_matrix.png", fig)
    md.append("![y1 x y2 matrix](figures/divergence/y1_x_y2_matrix.png)")
    md.append("")

    # --- 3. Distribuição de Δ
    md.append("## 3. Distribuição de Δ = y2 − y1")
    md.append("")
    delta_counts = model["delta"].value_counts().sort_index()
    md.append("| Δ | Decks | % |")
    md.append("|---:|---:|---:|")
    for d in sorted(delta_counts.index):
        v = int(delta_counts[d])
        md.append(f"| {int(d):+d} | {v:,} | {fmt_pct(v, n)} |")
    md.append("")
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(delta_counts.index.astype(int), delta_counts.values, color="#4C72B0")
    ax.set_xlabel("Δ = y2 − y1"); ax.set_ylabel("Decks")
    ax.set_title("Distribuição de Δ (y2 − y1) na base modelável")
    ax.axvline(0, color="grey", linestyle="--", linewidth=0.8)
    save_fig(FIG_DIV / "delta_distribution.png", fig)
    md.append("![Delta distribution](figures/divergence/delta_distribution.png)")
    md.append("")

    md.append("Distribuição de **|Δ|**:")
    abs_counts = model["abs_delta"].value_counts().sort_index()
    md.append("")
    md.append("| |Δ| | Decks | % |")
    md.append("|---:|---:|---:|")
    for d in sorted(abs_counts.index):
        v = int(abs_counts[d])
        md.append(f"| {int(d)} | {v:,} | {fmt_pct(v, n)} |")
    md.append("")
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(abs_counts.index.astype(int), abs_counts.values, color="#55A868")
    ax.set_xlabel("|Δ|"); ax.set_ylabel("Decks")
    ax.set_title("Magnitude da divergência |Δ|")
    save_fig(FIG_DIV / "abs_delta_distribution.png", fig)
    md.append("![Abs delta distribution](figures/divergence/abs_delta_distribution.png)")
    md.append("")

    # --- 4. Direção
    md.append("## 4. Direção da divergência")
    md.append("")
    higher = (model["delta"] > 0).sum()
    lower = (model["delta"] < 0).sum()
    same = (model["delta"] == 0).sum()
    md.append("| Direção | Decks | % |")
    md.append("|---|---:|---:|")
    md.append(f"| y2 > y1 (calculadora classifica acima) | {higher:,} | {fmt_pct(higher, n)} |")
    md.append(f"| y2 = y1 | {same:,} | {fmt_pct(same, n)} |")
    md.append(f"| y2 < y1 (calculadora classifica abaixo) | {lower:,} | {fmt_pct(lower, n)} |")
    md.append("")
    if higher > lower:
        md.append(f"**Tendência**: a calculadora tende a classificar **acima** do Archidekt em {fmt_pct(higher-lower, n)} mais casos. Pode indicar que usuários subestimam decks com sinais objetivos de força (game changers, combos, tutors).")
    elif lower > higher:
        md.append(f"**Tendência**: a calculadora tende a classificar **abaixo** do Archidekt em {fmt_pct(lower-higher, n)} mais casos. Pode indicar que usuários percebem força em sinergias / contexto que a calculadora não capta.")
    else:
        md.append("**Tendência**: divergências são razoavelmente simétricas em direção.")
    md.append("")

    # --- 5. |Δ| por característica
    md.append("## 5. |Δ| por característica do deck")
    md.append("")

    def cut_table(model_df: pd.DataFrame, col: str, title: str, bins=None) -> list[str]:
        rows = []
        rows.append(f"### {title} (`{col}`)")
        rows.append("")
        if bins is None:
            grouped = model_df.groupby(model_df[col])
        else:
            cut = pd.cut(model_df[col], bins=bins, include_lowest=True)
            grouped = model_df.groupby(cut, observed=True)
        rows.append("| Bucket | Decks | % com Δ=0 | |Δ| médio | |Δ| mediano |")
        rows.append("|---|---:|---:|---:|---:|")
        for name, sub in grouped:
            if len(sub) == 0: continue
            zero_pct = (sub["delta"] == 0).mean() * 100
            rows.append(f"| {name} | {len(sub):,} | {zero_pct:.1f}% | {sub['abs_delta'].mean():.3f} | {sub['abs_delta'].median():.0f} |")
        rows.append("")
        return rows

    md += cut_table(model, "deck_color_count", "Quantidade de cores")
    md += cut_table(model, "game_changer_count", "Game Changers")
    md += cut_table(model, "tutor_count", "Tutores")
    md += cut_table(model, "two_card_combo_singleton_count", "Combos de duas cartas (singleton)")

    # Price quintiles
    qedges = model["price_total"].dropna().quantile([0, .2, .4, .6, .8, 1.0]).unique()
    if len(qedges) >= 2:
        md += cut_table(model.dropna(subset=["price_total"]), "price_total", "Preço total (quintis)", bins=qedges)

    # |Δ| por número de cores — figura
    fig, ax = plt.subplots(figsize=(6, 3.5))
    cc_groups = sorted(model["deck_color_count"].dropna().unique())
    means = [model.loc[model["deck_color_count"]==c, "abs_delta"].mean() for c in cc_groups]
    ax.bar([int(c) for c in cc_groups], means, color="#C44E52")
    ax.set_xlabel("Quantidade de cores"); ax.set_ylabel("|Δ| médio")
    ax.set_title("Divergência média por quantidade de cores")
    save_fig(FIG_DIV / "abs_delta_by_color_count.png", fig)
    md.append("![Abs delta by color count](figures/divergence/abs_delta_by_color_count.png)")
    md.append("")

    # |Δ| por game changers — figura
    gc_labels = ["0","1","2","3","4+"]
    gc_buckets = pd.cut(model["game_changer_count"], bins=[-0.5, 0.5, 1.5, 2.5, 3.5, 100], labels=gc_labels)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    means = [model.loc[gc_buckets==b, "abs_delta"].mean() for b in gc_labels]
    counts = [int((gc_buckets==b).sum()) for b in gc_labels]
    bars = ax.bar(gc_labels, means, color="#8172B2")
    for bar, n_b in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"n={n_b:,}",
                ha="center", va="bottom", fontsize=8)
    ax.set_xlabel("Game Changers no deck"); ax.set_ylabel("|Δ| médio")
    ax.set_title("Divergência média por presença de Game Changers")
    ax.margins(y=0.15)
    save_fig(FIG_DIV / "abs_delta_by_game_changers.png", fig)
    md.append("![Abs delta by game changers](figures/divergence/abs_delta_by_game_changers.png)")
    md.append("")

    # --- 6. Direção (Δ>0 vs Δ<0) por feature
    md.append("## 6. Características de decks com Δ>0 vs Δ<0 vs Δ=0")
    md.append("")
    md.append("Comparação de médias entre os três grupos para algumas features-chave:")
    md.append("")
    g_pos = model[model["delta"] > 0]
    g_zero = model[model["delta"] == 0]
    g_neg = model[model["delta"] < 0]
    feats = ["game_changer_count","tutor_count","extra_turns_count","two_card_combo_singleton_count","price_total","salt_mean","edhrec_rank_mean","cmc_mean","land_count"]
    md.append("| Feature | Δ<0 (calc abaixo) | Δ=0 | Δ>0 (calc acima) |")
    md.append("|---|---:|---:|---:|")
    for f in feats:
        md.append(f"| `{f}` | {g_neg[f].mean():.2f} | {g_zero[f].mean():.2f} | {g_pos[f].mean():.2f} |")
    md.append("")

    # --- 7. Decks com y2 ∈ {1, 5}
    md.append("## 7. Decks com y2 ∈ {1, 5} (descartados da modelagem)")
    md.append("")
    extreme = base[base["y2"].isin([1,5])].copy()
    md.append(f"Total: **{len(extreme):,} decks** ({fmt_pct(len(extreme), len(base))} da base com y2 conhecido). y1 está em {{2,3,4}} para todos esses decks.")
    md.append("")
    md.append("Distribuição cruzada y1 × y2 nesses decks extremos:")
    md.append("")
    ext_mat = pd.crosstab(extreme["y1"], extreme["y2"])
    md.append("| y1 \\ y2 | 1 | 5 |")
    md.append("|---|---:|---:|")
    for y1 in sorted(ext_mat.index):
        row = []
        for y2 in [1, 5]:
            v = int(ext_mat.loc[y1, y2]) if y2 in ext_mat.columns else 0
            row.append(v)
        md.append(f"| {int(y1)} | {row[0]:,} | {row[1]:,} |")
    md.append("")

    # Top commanders entre extremos
    if decks is not None and "commander_signature" in decks.columns:
        ext_named = extreme.merge(decks[["snapshot_id","commander_signature"]], on="snapshot_id", how="left")
        for y2_val, label in [(1, "y2 = 1 (calculadora muito casual)"), (5, "y2 = 5 (calculadora cEDH-like)")]:
            sub = ext_named[ext_named["y2"] == y2_val]
            if len(sub) == 0: continue
            md.append(f"### {label} — top 10 comandantes")
            md.append("")
            md.append("| Comandante | Decks |")
            md.append("|---|---:|")
            for name, v in sub["commander_signature"].value_counts().head(10).items():
                md.append(f"| {name} | {v} |")
            md.append("")

    # Médias de algumas features para os extremos vs base
    md.append("### Comparação de médias (decks extremos vs base modelável)")
    md.append("")
    md.append("| Feature | Base modelável | y2=1 | y2=5 |")
    md.append("|---|---:|---:|---:|")
    for f in ["game_changer_count","tutor_count","two_card_combo_singleton_count","price_total","cmc_mean"]:
        b1 = extreme.loc[extreme["y2"]==1, f].mean() if (extreme["y2"]==1).any() else float("nan")
        b5 = extreme.loc[extreme["y2"]==5, f].mean() if (extreme["y2"]==5).any() else float("nan")
        md.append(f"| `{f}` | {model[f].mean():.2f} | {b1:.2f} | {b5:.2f} |")
    md.append("")

    # --- 8. Resumo
    md.append("## 8. Resumo executivo")
    md.append("")
    md.append(f"- **Concordância exata**: {fmt_pct(exact, n)} dos decks na base modelável.")
    md.append(f"- **Concordância dentro de ±1**: {fmt_pct(within1, n)}.")
    md.append(f"- **|Δ| médio**: {model['abs_delta'].mean():.3f}.")
    md.append(f"- **Tendência direcional**: y2>y1 em {fmt_pct(higher, n)} vs y2<y1 em {fmt_pct(lower, n)}.")
    md.append(f"- **Decks com y2 extremo (∉{{2,3,4}})**: {len(extreme):,} ({fmt_pct(len(extreme), len(base))}).")
    md.append("")
    md.append("Esses números são o ponto de partida da Fase G (transferência cross-label) e da Fase I (interpretabilidade): dão a referência contra a qual qualquer modelo será comparado.")
    md.append("")

    return "\n".join(md)


# ---------- main -------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Phase-B EDA and y1-vs-y2 divergence reports.")
    parser.add_argument("--data-dir", type=Path, default=DATA, help="Directory containing deck_features.jsonl and decks.jsonl.")
    parser.add_argument("--docs-dir", type=Path, default=DOCS, help="Directory where reports and figures are written.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    configure_paths(args.data_dir, args.docs_dir)

    print("Loading deck_features.jsonl...")
    df = load_features()
    print(f"  {len(df):,} rows / {len(df.columns)} columns")

    print("Loading deck commander info from decks.jsonl...")
    decks = load_decks_minimal()
    print(f"  {len(decks):,} rows")

    print("Generating EDA report + figures...")
    eda_md = eda(df, decks)
    (DOCS / "eda_report.md").write_text(eda_md, encoding="utf-8")
    print(f"  → {DOCS / 'eda_report.md'}")

    print("Generating divergence report + figures...")
    div_md = divergence(df, decks)
    (DOCS / "divergence_report.md").write_text(div_md, encoding="utf-8")
    print(f"  → {DOCS / 'divergence_report.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
