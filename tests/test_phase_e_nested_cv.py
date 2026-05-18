import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts import phase_e_nested_cv


class PhaseENestedCVTests(unittest.TestCase):
    def test_smoke_run_writes_nested_cv_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            docs = root / "documents"
            experiments = root / "experiments"
            processed.mkdir()

            snapshot_ids = []
            with (processed / "deck_features.jsonl").open("w", encoding="utf-8") as features_handle, (
                processed / "bag_of_cards.jsonl"
            ).open("w", encoding="utf-8") as bags_handle:
                for idx in range(90):
                    label = 2 + (idx % 3)
                    snapshot_id = f"s{idx}"
                    snapshot_ids.append(snapshot_id)
                    features = {
                        "snapshot_id": snapshot_id,
                        "deck_id": idx,
                        "archidekt_edh_bracket": label,
                        "edhpowerlevel_bracket": label,
                        "feature_a": float(idx % 7),
                        "feature_b": float(label),
                    }
                    bag = {
                        "snapshot_id": snapshot_id,
                        "counts": {
                            f"card_{label}": 1,
                            f"shared_{idx % 5}": 1,
                        },
                    }
                    features_handle.write(json.dumps(features) + "\n")
                    bags_handle.write(json.dumps(bag) + "\n")
            (processed / "modeling_snapshot_ids.json").write_text(
                json.dumps(snapshot_ids),
                encoding="utf-8",
            )

            args = phase_e_nested_cv.parse_args([
                "--processed-dir",
                str(processed),
                "--docs-dir",
                str(docs),
                "--experiment-dir",
                str(experiments),
                "--representations",
                "DF",
                "--algorithms",
                "naive_bayes",
                "--outer-splits",
                "2",
                "--inner-splits",
                "2",
                "--repeats",
                "1",
                "--max-grid-values",
                "1",
                "--quiet-progress",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                summary = phase_e_nested_cv.run(args)

            self.assertEqual(summary["status"], "ok")
            self.assertTrue((experiments / "df_naive_bayes" / "metrics_per_fold.json").exists())
            self.assertTrue((experiments / "df_naive_bayes" / "predictions_per_fold.jsonl").exists())
            self.assertTrue((experiments / "seeds.json").exists())
            self.assertTrue((experiments / "folds.json").exists())
            self.assertTrue((docs / "nested_cv_report.md").exists())
            self.assertTrue((docs / "statistical_tests.md").exists())


if __name__ == "__main__":
    unittest.main()
