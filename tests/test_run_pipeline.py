import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_pipeline


class RunPipelineCliTests(unittest.TestCase):
    def write_initialized_inputs(self, processed: Path) -> None:
        processed.mkdir(parents=True)
        for name in ["decks.jsonl", "cards.jsonl", "deck_features.jsonl", "bag_of_cards.jsonl"]:
            (processed / name).write_text("{}\n", encoding="utf-8")
        (processed / "modeling_snapshot_ids.json").write_text("[]\n", encoding="utf-8")

    def test_no_command_defaults_to_init(self):
        args = run_pipeline.parse_args(["--dry-run", "--experiments-manifest-url", "manifest.json"])

        self.assertEqual(args.command, "init")
        self.assertTrue(args.dry_run)

    def test_init_dry_run_has_only_init_stages(self):
        args = run_pipeline.parse_args([
            "init",
            "--dry-run",
            "--experiments-manifest-url",
            "manifest.json",
        ])

        stages = run_pipeline.build_stage_plan(args)
        stage_names = [stage.name for stage in stages]

        self.assertIn("restore_processed", stage_names)
        self.assertIn("phase_b_eda_divergence", stage_names)
        self.assertIn("phase_c_preprocessing", stage_names)
        self.assertIn("restore_public_experiments", stage_names)
        self.assertNotIn("phase_d_spot_check", stage_names)
        self.assertNotIn("phase_e_nested_cv", stage_names)

    def test_spot_checking_requires_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = run_pipeline.parse_args([
                "spot-checking",
                "--processed-dir",
                str(Path(tmp) / "processed"),
                "--dry-run",
            ])

            with self.assertRaisesRegex(FileNotFoundError, "run-mtg-pipeline init"):
                run_pipeline.run(args)

    def test_spot_checking_dry_run_publishes_bundle_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "spot-checking",
                "--processed-dir",
                str(processed),
                "--dry-run",
            ])

            with contextlib.redirect_stdout(io.StringIO()):
                manifest = run_pipeline.run(args)

            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(
                [stage["name"] for stage in manifest["stages"]],
                ["phase_d_spot_check", "check_drive_write", "upload_spot_check_bundle"],
            )
            self.assertEqual(manifest["stages"][0]["status"], "dry_run")

    def test_spot_checking_run_local_skips_bundle_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "spot-checking",
                "--processed-dir",
                str(processed),
                "--run-local",
                "--dry-run",
            ])

            stages = run_pipeline.build_stage_plan(args)

            self.assertEqual([stage.name for stage in stages], ["phase_d_spot_check"])

    def test_train_dry_run_builds_check_write_and_phase_e(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            manifest_path = root / "manifest.json"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "train",
                "--processed-dir",
                str(processed),
                "--manifest-path",
                str(manifest_path),
                "--model",
                "random_forest",
                "--feature",
                "df",
                "--dry-run",
            ])

            with contextlib.redirect_stdout(io.StringIO()):
                manifest = run_pipeline.run(args)

            names = [stage["name"] for stage in manifest["stages"]]
            self.assertEqual(names, ["check_drive_write", "phase_e_nested_cv", "publish_experiments_manifest"])
            phase_e_command = manifest["stages"][1]["command"]
            self.assertIn("--model", phase_e_command)
            self.assertIn("random_forest", phase_e_command)
            self.assertIn("--feature", phase_e_command)
            self.assertIn("df", phase_e_command)

    def test_train_run_local_skips_write_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "train",
                "--processed-dir",
                str(processed),
                "--model",
                "random_forest",
                "--feature",
                "df",
                "--run-local",
                "--dry-run",
            ])

            stages = run_pipeline.build_stage_plan(args)

            self.assertEqual([stage.name for stage in stages], ["phase_e_nested_cv"])

    def test_train_without_write_permission_fails_before_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "train",
                "--processed-dir",
                str(processed),
                "--manifest-path",
                str(root / "manifest.json"),
                "--model",
                "random_forest",
                "--feature",
                "df",
                "--rclone-bin",
                "false",
            ])

            failed = subprocess.CompletedProcess(args=["rclone"], returncode=1)
            with mock.patch.object(run_pipeline.subprocess, "run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "Sem permissão de escrita"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        run_pipeline.run(args)

            saved = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["stages"], [])

    def test_analyze_requires_phase_e_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "analyze",
                "--processed-dir",
                str(processed),
                "--experiment-dir",
                str(root / "experiments"),
                "--dry-run",
            ])

            with self.assertRaisesRegex(FileNotFoundError, "No Phase E outputs"):
                run_pipeline.run(args)

    def test_analyze_dry_run_lists_phases_f_through_j(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            experiments = root / "experiments"
            self.write_initialized_inputs(processed)
            (experiments / "df_random_forest").mkdir(parents=True)
            (experiments / "df_random_forest" / "metrics_per_fold.json").write_text("{}\n", encoding="utf-8")
            args = run_pipeline.parse_args([
                "analyze",
                "--processed-dir",
                str(processed),
                "--experiment-dir",
                str(experiments),
                "--dry-run",
            ])

            with contextlib.redirect_stdout(io.StringIO()):
                manifest = run_pipeline.run(args)

            self.assertEqual(
                [stage["name"] for stage in manifest["stages"]],
                ["phase_f_verify", "phase_g_voting", "phase_h_best_models", "phase_i_compare_y2", "phase_j_interpret"],
            )

    def test_full_skip_training_runs_b_through_j(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            experiments = root / "experiments"
            self.write_initialized_inputs(processed)
            args = run_pipeline.parse_args([
                "full",
                "--skip-training",
                "--run-local",
                "--processed-dir",
                str(processed),
                "--experiment-dir",
                str(experiments),
                "--dry-run",
            ])

            stages = run_pipeline.build_stage_plan(args)
            names = [stage.name for stage in stages]
            self.assertNotIn("phase_e_nested_cv", names)
            for expected in (
                "phase_b_eda_divergence",
                "phase_c_preprocessing",
                "phase_d_spot_check",
                "phase_f_verify",
                "phase_g_voting",
                "phase_h_best_models",
                "phase_i_compare_y2",
                "phase_j_interpret",
            ):
                self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
