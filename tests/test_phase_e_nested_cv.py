import json
import contextlib
import io
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from scripts import phase_e_nested_cv


class PhaseENestedCVTests(unittest.TestCase):
    def write_tiny_processed(self, processed: Path) -> None:
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

    def tiny_args(self, processed: Path, docs: Path, experiments: Path, *extra: str):
        return phase_e_nested_cv.parse_args([
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
            *extra,
        ])

    def test_model_selector_algorithm_runs_both_representations(self):
        args = phase_e_nested_cv.parse_args(["--model", "random_forest"])

        representations, algorithms = phase_e_nested_cv.resolve_model_selection(args)

        self.assertEqual(representations, ["DF", "BC"])
        self.assertEqual(algorithms, ["random_forest"])

    def test_feature_selector_runs_one_representation(self):
        args = phase_e_nested_cv.parse_args(["--model", "random_forest", "--feature", "bc"])

        representations, algorithms = phase_e_nested_cv.resolve_model_selection(args)

        self.assertEqual(representations, ["BC"])
        self.assertEqual(algorithms, ["random_forest"])

    def test_omitted_model_and_feature_run_all(self):
        args = phase_e_nested_cv.parse_args([])

        representations, algorithms = phase_e_nested_cv.resolve_model_selection(args)

        self.assertEqual(representations, ["DF", "BC"])
        self.assertEqual(algorithms, list(phase_e_nested_cv.SELECTED_ALGORITHMS))

    def test_smoke_run_writes_nested_cv_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            docs = root / "documents"
            experiments = root / "experiments"
            self.write_tiny_processed(processed)

            args = self.tiny_args(processed, docs, experiments, "--run-local")
            with contextlib.redirect_stdout(io.StringIO()):
                summary = phase_e_nested_cv.run(args)

            self.assertEqual(summary["status"], "ok")
            self.assertTrue((experiments / "df_naive_bayes" / "metrics_per_fold.json").exists())
            self.assertTrue((experiments / "df_naive_bayes" / "checkpoint_state.json").exists())
            checkpoint_dirs = list((experiments / "df_naive_bayes" / "checkpoints").glob("*"))
            self.assertEqual(len(checkpoint_dirs), 1)
            self.assertEqual(len(list(checkpoint_dirs[0].glob("*.json"))), 2)
            self.assertTrue((experiments / "df_naive_bayes" / "cv_results_per_fold.jsonl").exists())
            self.assertTrue((experiments / "df_naive_bayes" / "predictions_per_fold.jsonl").exists())
            self.assertTrue((experiments / "seeds.json").exists())
            self.assertTrue((experiments / "folds.json").exists())
            self.assertTrue((docs / "phase_e_nested_cv.md").exists())
            self.assertTrue((docs / "phase_e_statistical_tests.md").exists())
            self.assertFalse((docs / "phase_e_voting.md").exists())
            self.assertFalse((experiments / "voting").exists())
            self.assertNotIn("voting", summary)

            with mock.patch.object(
                phase_e_nested_cv,
                "inner_grid_search_with_progress",
                side_effect=AssertionError("should resume"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    resumed_summary = phase_e_nested_cv.run(args)

            self.assertEqual(resumed_summary["status"], "ok")
            self.assertEqual(
                resumed_summary["models"][0]["aggregate"]["macro_f1_mean"],
                summary["models"][0]["aggregate"]["macro_f1_mean"],
            )

    def test_run_local_skips_drive_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            docs = root / "documents"
            experiments = root / "experiments"
            self.write_tiny_processed(processed)
            args = self.tiny_args(
                processed,
                docs,
                experiments,
                "--run-local",
                "--experiments-drive-remote",
                "gdrive:MTG/Experiments",
            )

            with mock.patch.object(phase_e_nested_cv, "upload_model_archive") as upload:
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = phase_e_nested_cv.run(args)

            upload.assert_not_called()
            self.assertEqual(summary["drive_uploads"], [{"status": "skipped_run_local"}])

    def test_drive_upload_is_enqueued_after_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            docs = root / "documents"
            experiments = root / "experiments"
            self.write_tiny_processed(processed)
            args = self.tiny_args(
                processed,
                docs,
                experiments,
                "--experiments-drive-remote",
                "gdrive:MTG/Experiments",
            )

            with mock.patch.object(
                phase_e_nested_cv,
                "upload_model_archive",
                return_value={"status": "ok", "model_id": "df_naive_bayes"},
            ) as upload:
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = phase_e_nested_cv.run(args)

            upload.assert_called_once()
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["drive_uploads"][0]["status"], "ok")

    def test_drive_upload_failure_is_recorded_without_failing_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            docs = root / "documents"
            experiments = root / "experiments"
            self.write_tiny_processed(processed)
            args = self.tiny_args(
                processed,
                docs,
                experiments,
                "--experiments-drive-remote",
                "gdrive:MTG/Experiments",
            )

            with mock.patch.object(
                phase_e_nested_cv,
                "upload_model_archive",
                side_effect=RuntimeError("rclone failed"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = phase_e_nested_cv.run(args)

            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["drive_uploads"][0]["status"], "failed")
            self.assertIn("Drive upload failed", summary["problems"][0])

    def test_random_forest_grid_matches_tuning_plan(self):
        grid = phase_e_nested_cv.full_param_grid("random_forest", "DF")

        # Compact grid keeps the main RF knobs while avoiding BC runtime blowup.
        self.assertEqual(grid["clf__n_estimators"], [100, 250, 500])
        self.assertNotIn("clf__max_depth", grid)
        self.assertEqual(grid["clf__max_features"], ["sqrt", "log2"])
        self.assertEqual(grid["clf__min_samples_leaf"], [1, 2])
        self.assertEqual(grid["clf__class_weight"], [None, "balanced"])
        self.assertEqual(phase_e_nested_cv.grid_size(grid), 24)
        self.assertLessEqual(phase_e_nested_cv.grid_size(grid), phase_e_nested_cv.MAX_GRID_CONFIGS)

    def test_tree_and_histgb_grids_match_literature_audit(self):
        tree_grid = phase_e_nested_cv.full_param_grid("decision_tree", "DF")
        histgb_grid = phase_e_nested_cv.full_param_grid("gradient_boosting", "DF")

        self.assertIn("clf__ccp_alpha", tree_grid)
        self.assertNotIn("clf__min_samples_split", tree_grid)
        self.assertNotIn("clf__criterion", tree_grid)
        self.assertEqual(tree_grid["clf__max_depth"], [None, 10, 20])
        self.assertEqual(tree_grid["clf__min_samples_leaf"], [1, 5])
        self.assertEqual(phase_e_nested_cv.grid_size(tree_grid), 24)
        self.assertIn("clf__max_leaf_nodes", histgb_grid)
        self.assertNotIn("clf__max_depth", histgb_grid)
        # learning_rate prioritized over max_iter resolution per Chen & Guestrin
        # 2016 / Ke et al. 2017 (lr is the #1 boosting knob).
        self.assertEqual(histgb_grid["clf__max_iter"], [200, 500])
        self.assertEqual(histgb_grid["clf__learning_rate"], [0.05, 0.1, 0.2])
        self.assertEqual(histgb_grid["clf__max_leaf_nodes"], [15, 31])
        self.assertNotIn("clf__l2_regularization", histgb_grid)
        self.assertEqual(phase_e_nested_cv.grid_size(histgb_grid), 24)

    def test_linear_grids_include_sparse_regularization_knobs(self):
        logistic_grid = phase_e_nested_cv.full_param_grid("logistic_regression", "BC")
        linear_svc_grid = phase_e_nested_cv.full_param_grid("linear_svc", "BC")

        # LR sweeps the full L2 → ElasticNet → L1 spectrum via l1_ratio.
        # C window widened to 5 orders of magnitude (Hastie ESL §4.4) so the
        # optimum at low C (typical with class_weight='balanced' + L1 in BC) is
        # actually inside the grid.
        self.assertEqual(logistic_grid["clf__C"], [0.001, 0.1, 1.0, 100.0])
        self.assertEqual(logistic_grid["clf__l1_ratio"], [0.0, 0.5, 1.0])
        self.assertNotIn("clf__fit_intercept", logistic_grid)
        self.assertEqual(phase_e_nested_cv.grid_size(logistic_grid), 24)
        # LinearSVC keeps L1 vs L2 as explicit penalty (no elasticnet for SVC).
        self.assertEqual(linear_svc_grid["clf__C"], [0.001, 0.01, 0.1, 1.0, 10.0, 100.0])
        self.assertEqual(linear_svc_grid["clf__penalty"], ["l1", "l2"])
        self.assertNotIn("clf__fit_intercept", linear_svc_grid)
        self.assertEqual(phase_e_nested_cv.grid_size(linear_svc_grid), 24)

    def test_small_knob_grids_have_comparable_budget_when_possible(self):
        multinomial_grid = phase_e_nested_cv.full_param_grid("naive_bayes", "BC")
        gaussian_grid = phase_e_nested_cv.full_param_grid("naive_bayes", "DF")

        self.assertEqual(len(multinomial_grid["clf__alpha"]), 12)
        self.assertEqual(phase_e_nested_cv.grid_size(multinomial_grid), 24)
        self.assertEqual(len(gaussian_grid["clf__var_smoothing"]), 24)
        self.assertEqual(phase_e_nested_cv.grid_size(gaussian_grid), 24)

    def test_all_grids_fit_within_max_configs(self):
        for alg in phase_e_nested_cv.SELECTED_ALGORITHMS:
            for rep in phase_e_nested_cv.REPRESENTATIONS:
                grid = phase_e_nested_cv.full_param_grid(alg, rep)
                self.assertEqual(
                    phase_e_nested_cv.grid_size(grid),
                    phase_e_nested_cv.MAX_GRID_CONFIGS,
                    msg=f"{rep}/{alg} should use the compact 24-config Phase-E grid",
                )

    def test_hard_vote_uses_member_macro_f1_for_ties(self):
        winner = phase_e_nested_cv.hard_vote(
            {"weaker": 2, "stronger": 3},
            member_scores={"weaker": 0.61, "stronger": 0.72},
        )

        self.assertEqual(winner, 3)
        self.assertEqual(
            phase_e_nested_cv.hard_vote(
                {"left": 4, "right": 2},
                member_scores={"left": 0.5, "right": 0.5},
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
