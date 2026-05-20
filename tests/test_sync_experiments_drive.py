import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts import sync_experiments_drive


class SyncExperimentsDriveTests(unittest.TestCase):
    def test_create_model_archive_contains_model_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment_dir = Path(tmp) / "experiments"
            model_dir = experiment_dir / "df_random_forest"
            (model_dir / "checkpoints" / "abc").mkdir(parents=True)
            (model_dir / "metrics_per_fold.json").write_text("{}\n", encoding="utf-8")
            (model_dir / "predictions_per_fold.jsonl").write_text("{}\n", encoding="utf-8")
            (model_dir / "cv_results_per_fold.jsonl").write_text("{}\n", encoding="utf-8")
            (model_dir / "checkpoints" / "abc" / "r1_f1.json").write_text("{}\n", encoding="utf-8")

            result = sync_experiments_drive.create_model_archive(
                "df_random_forest",
                experiment_dir=experiment_dir,
            )

            self.assertEqual(result["status"], "ok")
            with zipfile.ZipFile(result["archive_path"]) as archive:
                names = set(archive.namelist())
            self.assertIn("df_random_forest/metrics_per_fold.json", names)
            self.assertIn("df_random_forest/predictions_per_fold.jsonl", names)
            self.assertIn("df_random_forest/cv_results_per_fold.jsonl", names)
            self.assertIn("df_random_forest/checkpoints/abc/r1_f1.json", names)

    def test_extract_model_archive_restores_checkpoint_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_experiments = root / "source" / "experiments"
            model_dir = source_experiments / "df_random_forest"
            model_dir.mkdir(parents=True)
            (model_dir / "checkpoint_state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
            archive = sync_experiments_drive.create_model_archive(
                "df_random_forest",
                experiment_dir=source_experiments,
            )

            target_experiments = root / "target" / "experiments"
            result = sync_experiments_drive.extract_model_archive(
                Path(archive["archive_path"]),
                experiment_dir=target_experiments,
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue((target_experiments / "df_random_forest" / "checkpoint_state.json").exists())

    def test_upload_model_uses_rclone_copyto(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment_dir = Path(tmp) / "experiments"
            model_dir = experiment_dir / "df_random_forest"
            model_dir.mkdir(parents=True)
            (model_dir / "metrics_per_fold.json").write_text("{}\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=["rclone"],
                returncode=0,
                stdout="",
                stderr="",
            )

            with mock.patch.object(sync_experiments_drive.subprocess, "run", return_value=completed) as run:
                result = sync_experiments_drive.upload_model(
                    "df_random_forest",
                    experiment_dir=experiment_dir,
                    remote="gdrive:MTG/Experiments",
                )

            self.assertEqual(result["status"], "ok")
            command = run.call_args.args[0]
            self.assertEqual(command[0:2], ["rclone", "copyto"])
            self.assertTrue(command[2].endswith("df_random_forest.zip"))
            self.assertEqual(command[3], "gdrive:MTG/Experiments/df_random_forest.zip")

    def test_remote_archive_path_supports_remote_root(self):
        self.assertEqual(
            sync_experiments_drive.remote_archive_path("mtg-experiments:", "df_random_forest"),
            "mtg-experiments:df_random_forest.zip",
        )

    def test_download_public_restores_checkpoint_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_experiments = root / "source" / "experiments"
            model_dir = source_experiments / "mock_knn"
            model_dir.mkdir(parents=True)
            (model_dir / "checkpoint_state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            archive = sync_experiments_drive.create_model_archive("mock_knn", experiment_dir=source_experiments)
            manifest_path = root / "experiments_manifest.json"
            manifest_path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "generated_at": "2026-05-19T00:00:00+00:00",
                    "models": [
                        {
                            "model_id": "mock_knn",
                            "filename": "mock_knn.zip",
                            "drive_file_id": "fake-file-id",
                            "size_bytes": Path(archive["archive_path"]).stat().st_size,
                        }
                    ],
                }),
                encoding="utf-8",
            )

            def fake_download(file_id, out_path):
                self.assertEqual(file_id, "fake-file-id")
                out_path.write_bytes(Path(archive["archive_path"]).read_bytes())
                return {"status": "ok", "file_id": file_id, "path": str(out_path)}

            with mock.patch.object(sync_experiments_drive, "download_drive_file", side_effect=fake_download):
                result = sync_experiments_drive.download_public_archives(
                    experiment_dir=root / "target" / "experiments",
                    manifest_url=str(manifest_path),
                    models=["mock_knn"],
                )

            self.assertEqual(result["status"], "ok")
            restored = root / "target" / "experiments" / "mock_knn" / "checkpoint_state.json"
            self.assertTrue(restored.exists())

    def test_publish_manifest_uses_remote_zip_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.CompletedProcess(args=["rclone"], returncode=0, stdout="", stderr="")
            lsjson = subprocess.CompletedProcess(
                args=["rclone"],
                returncode=0,
                stdout=json.dumps([
                    {
                        "Name": "df_random_forest.zip",
                        "Size": 123,
                        "ID": "zip-file-id",
                    }
                ]),
                stderr="",
            )
            remote_manifest = subprocess.CompletedProcess(
                args=["rclone"],
                returncode=0,
                stdout=json.dumps([{"Name": "experiments_manifest.json", "ID": "manifest-id"}]),
                stderr="",
            )

            def fake_run(command, check=False, capture_output=False, text=False):
                if command[1] == "lsjson" and "--include" in command:
                    return lsjson
                if command[1] == "copyto":
                    return completed
                if command[1] == "lsjson":
                    return remote_manifest
                raise AssertionError(command)

            with mock.patch.object(sync_experiments_drive.subprocess, "run", side_effect=fake_run):
                result = sync_experiments_drive.publish_manifest(
                    experiment_dir=Path(tmp) / "experiments",
                    remote="mtg-experiments:",
                )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["manifest"]["models"][0]["drive_file_id"], "zip-file-id")
            manifest_path = Path(result["manifest_path"])
            self.assertTrue(manifest_path.exists())

    def test_check_write_access_returns_failed_for_read_only_remote(self):
        failed = subprocess.CompletedProcess(
            args=["rclone"],
            returncode=1,
            stdout="",
            stderr="permission denied",
        )
        with mock.patch.object(sync_experiments_drive.subprocess, "run", return_value=failed):
            result = sync_experiments_drive.check_write_access(remote="mtg-experiments:")

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["delete"])

    def test_check_write_access_deletes_probe_after_success(self):
        ok = subprocess.CompletedProcess(args=["rclone"], returncode=0, stdout="", stderr="")
        with mock.patch.object(sync_experiments_drive.subprocess, "run", return_value=ok) as run:
            result = sync_experiments_drive.check_write_access(remote="mtg-experiments:")

        self.assertEqual(result["status"], "ok")
        commands = [call.args[0][1] for call in run.call_args_list]
        self.assertEqual(commands, ["copyto", "deletefile"])

    def test_manifest_model_records_errors_for_missing_requested_model(self):
        manifest = {
            "schema_version": 1,
            "models": [
                {
                    "model_id": "df_random_forest",
                    "filename": "df_random_forest.zip",
                    "drive_file_id": "zip-file-id",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "missing model"):
            sync_experiments_drive.manifest_model_records(manifest, models=["bc_random_forest"])


if __name__ == "__main__":
    unittest.main()
