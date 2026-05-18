import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preprocessing = load_module("phase_c_preprocessing", "scripts/preprocessing.py")
phase_c_filter = load_module("phase_c_filter_dataset", "scripts/phase_c_filter_dataset.py")


class PhaseCFilterTests(unittest.TestCase):
    def test_filters_modeling_records_and_writes_audit_outputs(self):
        records = [
            {
                "snapshot_id": "s1",
                "deck_id": 1,
                "archidekt_edh_bracket": 2,
                "edhpowerlevel": {"commander_bracket": 2},
            },
            {
                "snapshot_id": "s2",
                "deck_id": 2,
                "archidekt_edh_bracket": 3,
                "edhpowerlevel": {"commander_bracket": 5},
            },
            {
                "snapshot_id": "s3",
                "deck_id": 3,
                "archidekt_edh_bracket": 1,
                "edhpowerlevel": {"commander_bracket": 3},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            features_path = root / "deck_features.jsonl"
            with features_path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record))
                    handle.write("\n")

            args = phase_c_filter.parse_args(["--features-path", str(features_path), "--out-dir", str(root)])
            summary = phase_c_filter.run(args)

            snapshot_ids = json.loads((root / "modeling_snapshot_ids.json").read_text())
            excluded = [
                json.loads(line)
                for line in (root / "modeling_excluded.jsonl").read_text().splitlines()
                if line.strip()
            ]

            self.assertEqual(snapshot_ids, ["s1"])
            self.assertEqual(summary["included"], 1)
            self.assertEqual(summary["excluded"], 2)
            self.assertEqual(summary["exclusion_reasons"]["included"], 1)
            self.assertEqual({row["reason"] for row in excluded}, {"y2_out_of_range:5", "y1_out_of_range:1"})


class DeckFeaturePreprocessorTests(unittest.TestCase):
    def test_fits_train_only_imputation_winsorization_scaling_and_no_leakage(self):
        train = [
            {
                "archidekt_edh_bracket": 2,
                "edhpowerlevel_bracket": 4,
                "edhpowerlevel": {"commander_bracket": 4},
                "delta": 2,
                "deck_id": 100,
                "snapshot_id": "train-1",
                "edhrec_rank_mean": 10,
                "salt_mean": 0.2,
                "price_total": 100,
                "land_count": 36,
                "has_W": True,
                "mainboard_count": 100,
            },
            {
                "archidekt_edh_bracket": 3,
                "edhpowerlevel_bracket": 3,
                "edhpowerlevel": {"commander_bracket": 3},
                "delta": 0,
                "deck_id": 101,
                "snapshot_id": "train-2",
                "edhrec_rank_mean": 30,
                "salt_mean": 0.6,
                "price_total": 1000,
                "land_count": 38,
                "has_W": False,
                "mainboard_count": 100,
            },
        ]
        test = [
            {
                "archidekt_edh_bracket": 4,
                "edhpowerlevel_bracket": 2,
                "edhpowerlevel": {"commander_bracket": 2},
                "delta": -2,
                "deck_id": 999,
                "snapshot_id": "test-1",
                "edhrec_rank_mean": None,
                "salt_mean": None,
                "price_total": 5000,
                "land_count": 40,
                "has_W": True,
                "mainboard_count": 100,
            }
        ]

        transformer = preprocessing.DeckFeaturePreprocessor(scale=True)
        train_matrix = transformer.fit_transform(train)
        test_matrix = transformer.transform(test)
        names = transformer.get_feature_names_out().tolist()

        self.assertNotIn("edhpowerlevel_bracket", names)
        self.assertNotIn("delta", names)
        self.assertNotIn("deck_id", names)
        self.assertNotIn("mainboard_count", names)
        self.assertIn("price_total", names)
        self.assertEqual(transformer.impute_values_["edhrec_rank_mean"], 20.0)
        self.assertEqual(transformer.impute_values_["salt_mean"], 0.4)
        self.assertLess(transformer.price_total_cap_, 1000.1)
        self.assertEqual(train_matrix.shape[1], len(names))
        self.assertTrue(np.isfinite(test_matrix).all())

    def test_can_leave_tree_features_unscaled(self):
        records = [
            {"archidekt_edh_bracket": 2, "edhpowerlevel_bracket": 2, "land_count": 35, "price_total": 10},
            {"archidekt_edh_bracket": 3, "edhpowerlevel_bracket": 3, "land_count": 37, "price_total": 20},
        ]
        transformer = preprocessing.DeckFeaturePreprocessor(scale=False, drop_zero_variance=False)
        matrix = transformer.fit_transform(records)
        names = transformer.get_feature_names_out().tolist()

        self.assertEqual(matrix[:, names.index("land_count")].tolist(), [35.0, 37.0])


class BagOfCardsPreprocessorTests(unittest.TestCase):
    def test_prunes_by_train_min_df_and_ignores_unseen_cards(self):
        train = [
            {"snapshot_id": "a", "counts": {"sol-ring": 1, "rare-a": 1}},
            {"snapshot_id": "b", "counts": {"sol-ring": 1, "rare-b": 1}},
            {"snapshot_id": "c", "counts": {"sol-ring": 1, "rare-a": 1}},
        ]
        test = [{"snapshot_id": "d", "counts": {"sol-ring": 1, "unseen": 4}}]

        vectorizer = preprocessing.BagOfCardsPreprocessor(min_df=2, use_tfidf=False)
        train_matrix = vectorizer.fit_transform(train)
        test_matrix = vectorizer.transform(test)

        self.assertEqual(vectorizer.get_feature_names_out().tolist(), ["rare-a", "sol-ring"])
        self.assertEqual(train_matrix.shape, (3, 2))
        self.assertEqual(test_matrix.shape, (1, 2))
        self.assertEqual(test_matrix.toarray().tolist(), [[0.0, 1.0]])

    def test_tfidf_variant_keeps_sparse_shape(self):
        records = [
            {"counts": {"a": 1, "b": 1}},
            {"counts": {"a": 1}},
        ]
        vectorizer = preprocessing.BagOfCardsPreprocessor(min_df=1, use_tfidf=True)
        matrix = vectorizer.fit_transform(records)

        self.assertEqual(matrix.shape, (2, 2))
        self.assertTrue(np.isfinite(matrix.data).all())
        self.assertFalse(np.allclose(matrix.toarray(), [[1.0, 1.0], [1.0, 0.0]]))


if __name__ == "__main__":
    unittest.main()

