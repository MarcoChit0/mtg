import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_pipeline


class RunPipelinePlanTests(unittest.TestCase):
    def test_processed_drive_plan_preserves_frozen_features_by_default(self):
        args = run_pipeline.parse_args([
            "--data-source",
            "processed-drive",
            "--processed-archive",
            "processed.zip",
            "--skip-reports",
        ])

        stages = run_pipeline.build_stage_plan(args)
        by_name = {stage.name: stage for stage in stages}

        self.assertIsNotNone(by_name["restore_processed"].command)
        self.assertIsNone(by_name["build_features"].command)
        self.assertEqual(by_name["build_features"].reason, "skipped_preserve_processed_snapshot")
        self.assertIsNotNone(by_name["phase_c_preprocessing"].command)
        self.assertFalse(by_name["phase_d_spot_check"].implemented)

    def test_raw_drive_plan_keeps_live_y2_opt_in(self):
        args = run_pipeline.parse_args([
            "--data-source",
            "raw-drive",
            "--raw-archive",
            "data/raw/archidekt/Archive.zip",
            "--skip-reports",
        ])

        stages = run_pipeline.build_stage_plan(args)
        process = next(stage for stage in stages if stage.name == "process_raw")

        self.assertIn("--skip-y2", process.command)

    def test_manifest_records_skipped_future_stages_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed = root / "processed"
            processed.mkdir()
            (processed / "decks.jsonl").write_text("{}\n", encoding="utf-8")
            (processed / "cards.jsonl").write_text("{}\n", encoding="utf-8")
            manifest_path = root / "manifest.json"

            args = run_pipeline.parse_args([
                "--data-source",
                "local",
                "--processed-dir",
                str(processed),
                "--skip-reports",
                "--dry-run",
                "--manifest-path",
                str(manifest_path),
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                manifest = run_pipeline.run(args)
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(saved["status"], "ok")
            statuses = {stage["name"]: stage["status"] for stage in saved["stages"]}
            self.assertEqual(statuses["build_features"], "dry_run")
            self.assertEqual(statuses["phase_d_spot_check"], "pending")


if __name__ == "__main__":
    unittest.main()
