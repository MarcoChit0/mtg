#!/usr/bin/env python3
"""Phase C preprocessing utilities for Archidekt modeling.

The helpers in this module are deliberately sklearn-compatible so later
phases can place them inside hold-out, cross-validation, and GridSearchCV
pipelines without leaking validation-fold information into the transforms.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.preprocessing import StandardScaler


MODELING_BRACKETS = frozenset({2, 3, 4})

TARGET_COLUMNS = frozenset({"archidekt_edh_bracket", "y1"})
LEAKAGE_COLUMNS = frozenset({
    "edhpowerlevel",
    "edhpowerlevel_bracket",
    "y2",
    "delta",
    "abs_delta",
})
METADATA_COLUMNS = frozenset({
    "snapshot_id",
    "deck_id",
    "deck_name",
    "fetched_at",
    "archidekt_updated_at",
    "commander_oracle_uids",
})

EDHREC_PREFIX = "edhrec_rank_"
SALT_PREFIX = "salt_"


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_number}") from exc


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
        return int(number) if number.is_integer() else None
    return None


def y1_value(record: Mapping[str, Any]) -> Optional[int]:
    return _as_int(record.get("archidekt_edh_bracket", record.get("y1")))


def y2_value(record: Mapping[str, Any]) -> Optional[int]:
    direct = _as_int(record.get("edhpowerlevel_bracket", record.get("y2")))
    if direct is not None:
        return direct
    edhpowerlevel = record.get("edhpowerlevel")
    if isinstance(edhpowerlevel, Mapping):
        return _as_int(edhpowerlevel.get("commander_bracket"))
    return None


def modeling_filter_reason(record: Mapping[str, Any]) -> str:
    y1 = y1_value(record)
    y2 = y2_value(record)
    if y1 not in MODELING_BRACKETS:
        return f"y1_out_of_range:{y1}"
    if y2 not in MODELING_BRACKETS:
        return f"y2_out_of_range:{y2}"
    return "included"


def split_modeling_records(
    records: Iterable[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Counter]:
    """Split Phase-C modelable records from excluded rows.

    Included rows keep the original feature payload. Excluded rows are compact
    audit records so the qualitative Phase-B/Fase-G analysis can recover which
    decks fell outside the modeling label space.
    """
    included: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    reasons: Counter = Counter()

    for record in records:
        reason = modeling_filter_reason(record)
        reasons[reason] += 1
        if reason == "included":
            included.append(dict(record))
            continue
        excluded.append({
            "snapshot_id": record.get("snapshot_id"),
            "deck_id": record.get("deck_id"),
            "y1": y1_value(record),
            "y2": y2_value(record),
            "reason": reason,
        })
    return included, excluded, reasons


def is_leakage_column(name: str) -> bool:
    return (
        name in TARGET_COLUMNS
        or name in LEAKAGE_COLUMNS
        or name in METADATA_COLUMNS
        or name.startswith("edhpowerlevel.")
        or name.startswith("epl_")
    )


def is_numeric_like(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (bool, int, float, np.bool_, np.integer, np.floating)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def infer_deck_feature_columns(records: Sequence[Mapping[str, Any]]) -> List[str]:
    """Infer numeric Deck Feature columns while dropping labels and leakage."""
    candidates = set()
    invalid = set()
    for record in records:
        for key, value in record.items():
            if is_leakage_column(key):
                continue
            if is_numeric_like(value):
                candidates.add(key)
            else:
                invalid.add(key)
    return sorted(candidates - invalid)


def _records_to_matrix(records: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> np.ndarray:
    matrix = np.empty((len(records), len(columns)), dtype=float)
    for row_idx, record in enumerate(records):
        for col_idx, column in enumerate(columns):
            value = record.get(column)
            if value is None or value == "":
                matrix[row_idx, col_idx] = np.nan
            elif isinstance(value, bool):
                matrix[row_idx, col_idx] = float(value)
            else:
                try:
                    matrix[row_idx, col_idx] = float(value)
                except (TypeError, ValueError):
                    matrix[row_idx, col_idx] = np.nan
    return matrix


class DeckFeaturePreprocessor(BaseEstimator, TransformerMixin):
    """Leakage-safe preprocessing for aggregate Deck Features.

    Fit-time state:
    - medians for ``edhrec_rank_*`` and ``salt_*`` columns;
    - p99 cap for ``price_total``;
    - zero-variance feature mask;
    - optional ``StandardScaler`` parameters.
    """

    def __init__(
        self,
        feature_columns: Optional[Sequence[str]] = None,
        scale: bool = False,
        drop_zero_variance: bool = True,
        winsorize_price_total: bool = True,
    ) -> None:
        self.feature_columns = feature_columns
        self.scale = scale
        self.drop_zero_variance = drop_zero_variance
        self.winsorize_price_total = winsorize_price_total

    def fit(self, X: Sequence[Mapping[str, Any]], y: Any = None) -> "DeckFeaturePreprocessor":
        records = list(X)
        if self.feature_columns is None:
            self.feature_columns_ = infer_deck_feature_columns(records)
        else:
            self.feature_columns_ = list(self.feature_columns)

        matrix = _records_to_matrix(records, self.feature_columns_)
        self.impute_values_: Dict[str, float] = {}
        for idx, column in enumerate(self.feature_columns_):
            if column.startswith(EDHREC_PREFIX) or column.startswith(SALT_PREFIX):
                values = matrix[:, idx]
                finite = values[np.isfinite(values)]
                self.impute_values_[column] = float(np.median(finite)) if finite.size else 0.0

        matrix = self._apply_imputation(matrix.copy())

        self.price_total_cap_: Optional[float] = None
        if self.winsorize_price_total and "price_total" in self.feature_columns_:
            idx = self.feature_columns_.index("price_total")
            finite = matrix[:, idx][np.isfinite(matrix[:, idx])]
            if finite.size:
                self.price_total_cap_ = float(np.percentile(finite, 99))
                matrix[:, idx] = np.minimum(matrix[:, idx], self.price_total_cap_)

        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

        if self.drop_zero_variance:
            variances = np.var(matrix, axis=0)
            self.keep_mask_ = variances > 0.0
        else:
            self.keep_mask_ = np.ones(len(self.feature_columns_), dtype=bool)
        self.output_feature_names_ = [
            column for column, keep in zip(self.feature_columns_, self.keep_mask_) if keep
        ]

        matrix = matrix[:, self.keep_mask_]
        self.scaler_: Optional[StandardScaler] = None
        if self.scale:
            self.scaler_ = StandardScaler()
            self.scaler_.fit(matrix)
        return self

    def transform(self, X: Sequence[Mapping[str, Any]]) -> np.ndarray:
        matrix = _records_to_matrix(list(X), self.feature_columns_)
        matrix = self._apply_imputation(matrix)

        if self.price_total_cap_ is not None and "price_total" in self.feature_columns_:
            idx = self.feature_columns_.index("price_total")
            matrix[:, idx] = np.minimum(matrix[:, idx], self.price_total_cap_)

        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        matrix = matrix[:, self.keep_mask_]
        if self.scaler_ is not None:
            matrix = self.scaler_.transform(matrix)
        return matrix

    def _apply_imputation(self, matrix: np.ndarray) -> np.ndarray:
        for column, value in getattr(self, "impute_values_", {}).items():
            idx = self.feature_columns_.index(column)
            missing = ~np.isfinite(matrix[:, idx])
            matrix[missing, idx] = value
        return matrix

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return np.asarray(self.output_feature_names_, dtype=object)


def _counts(record: Mapping[str, Any]) -> Mapping[str, Any]:
    counts = record.get("counts", record)
    return counts if isinstance(counts, Mapping) else {}


class BagOfCardsPreprocessor(BaseEstimator, TransformerMixin):
    """Sparse bag-of-cards vectorizer with train-fold pruning and optional TF-IDF."""

    def __init__(self, min_df: int = 10, use_tfidf: bool = False, dtype: Any = np.float64) -> None:
        self.min_df = min_df
        self.use_tfidf = use_tfidf
        self.dtype = dtype

    def fit(self, X: Sequence[Mapping[str, Any]], y: Any = None) -> "BagOfCardsPreprocessor":
        if self.min_df < 1:
            raise ValueError("min_df must be >= 1")
        document_frequency: Counter = Counter()
        for record in X:
            present = {card for card, qty in _counts(record).items() if float(qty or 0) > 0}
            document_frequency.update(present)

        self.vocabulary_ = {
            card: idx
            for idx, card in enumerate(sorted(card for card, df in document_frequency.items() if df >= self.min_df))
        }
        matrix = self._build_matrix(X)
        self.tfidf_transformer_: Optional[TfidfTransformer] = None
        if self.use_tfidf:
            self.tfidf_transformer_ = TfidfTransformer(use_idf=True, norm="l2")
            self.tfidf_transformer_.fit(matrix)
        return self

    def transform(self, X: Sequence[Mapping[str, Any]]) -> sparse.csr_matrix:
        matrix = self._build_matrix(X)
        if self.tfidf_transformer_ is not None:
            matrix = self.tfidf_transformer_.transform(matrix)
        return matrix

    def _build_matrix(self, X: Sequence[Mapping[str, Any]]) -> sparse.csr_matrix:
        rows: List[int] = []
        cols: List[int] = []
        data: List[float] = []
        for row_idx, record in enumerate(X):
            for card, qty in _counts(record).items():
                col_idx = self.vocabulary_.get(card)
                if col_idx is None:
                    continue
                value = float(qty or 0)
                if value <= 0:
                    continue
                rows.append(row_idx)
                cols.append(col_idx)
                data.append(value)
        return sparse.csr_matrix(
            (np.asarray(data, dtype=self.dtype), (rows, cols)),
            shape=(len(X), len(self.vocabulary_)),
            dtype=self.dtype,
        )

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        names = [None] * len(self.vocabulary_)
        for card, idx in self.vocabulary_.items():
            names[idx] = card
        return np.asarray(names, dtype=object)


def target_vector(records: Sequence[Mapping[str, Any]]) -> np.ndarray:
    values = [y1_value(record) for record in records]
    if any(value is None for value in values):
        raise ValueError("All modeling records must carry archidekt_edh_bracket/y1")
    return np.asarray(values, dtype=int)

