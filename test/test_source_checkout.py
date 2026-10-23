"""Exercise source preparation with real Git repositories and Bash."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))
import agent


@unittest.skipUnless(Path("/bin/bash").is_file() and shutil.which("git"),
                     "source preparation requires Bash and Git")
class TestSourceCheckout(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.work = self.root / "work"
        self.work.mkdir()
        self.original_cwd = Path.cwd()
        self.addCleanup(os.chdir, self.original_cwd)
        self.git("init", "-q", cwd=self.source)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.source)
        (self.source / "version.txt").write_text("release\n", encoding="utf-8")
        self.git("add", "version.txt", cwd=self.source)
        self.git("commit", "-qm", "release fixture", cwd=self.source)
        self.git("tag", "v1.0", cwd=self.source)
        self.git("tag", "-a", "v1.0-annotated", "-m", "release", cwd=self.source)
        (self.source / "version.txt").write_text("default branch\n", encoding="utf-8")
        self.git("commit", "-qam", "default branch fixture", cwd=self.source)
        os.chdir(self.work)

    def git(self, *args, cwd=None):
        return subprocess.run(
            ["git", "-c", "user.name=Checkout Test", "-c",
             "user.email=checkout-test@example.invalid", "-c",
             "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
            cwd=cwd or self.work, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def prepare(self, version="None", source=None):
        return agent._download_project_source(str(source or self.source), version)

    def checked_out_content(self):
        return (self.work / self.source.name / "version.txt").read_text(encoding="utf-8")

    def test_unspecified_version_uses_default_branch(self):
        self.assertTrue(self.prepare())
        self.assertEqual(self.checked_out_content(), "default branch\n")

    def test_null_version_preserves_unspecified_version_behavior(self):
        self.assertTrue(self.prepare(None))
        self.assertEqual(self.checked_out_content(), "default branch\n")

    def test_lightweight_tag_checks_out_release(self):
        self.assertTrue(self.prepare("v1.0"))
        self.assertEqual(self.checked_out_content(), "release\n")

    def test_annotated_tag_checks_out_release(self):
        self.assertTrue(self.prepare("v1.0-annotated"))
        self.assertEqual(self.checked_out_content(), "release\n")

    def test_missing_tag_is_a_preparation_failure(self):
        self.assertFalse(self.prepare("missing-release"))

    def test_tag_names_are_matched_literally(self):
        self.git("tag", "v1x0", "v1.0", cwd=self.source)
        self.git("tag", "-d", "v1.0", cwd=self.source)
        self.assertFalse(self.prepare("v1.0"))

    def test_tag_is_selected_over_same_named_local_branch(self):
        self.git("clone", "-q", str(self.source))
        checkout = self.work / self.source.name
        self.git("branch", "v1.0", cwd=checkout)
        self.assertTrue(self.prepare("v1.0"))
        self.assertEqual(self.checked_out_content(), "release\n")

    def test_clone_failure_is_not_reported_as_success(self):
        self.assertFalse(self.prepare(source=self.root / "missing-repository"))

    def test_cannot_enter_checkout_is_not_reported_as_success(self):
        (self.work / self.source.name).write_text("not a directory", encoding="utf-8")
        self.assertFalse(self.prepare())

    def test_checkout_failure_preserves_local_modifications(self):
        self.git("clone", "-q", str(self.source))
        marker = self.work / self.source.name / "version.txt"
        marker.write_text("local modification\n", encoding="utf-8")
        self.assertFalse(self.prepare("v1.0"))
        self.assertEqual(marker.read_text(encoding="utf-8"), "local modification\n")

    def test_valid_tag_with_shell_metacharacters_is_literal(self):
        self.git("tag", "release/$candidate", "v1.0", cwd=self.source)
        self.assertTrue(self.prepare("release/$candidate"))
        self.assertEqual(self.checked_out_content(), "release\n")

    def test_repository_path_with_spaces_is_one_argument(self):
        spaced_source = self.root / "source with spaces"
        self.source.rename(spaced_source)
        self.source = spaced_source
        self.assertTrue(self.prepare("v1.0"))
        self.assertEqual(self.checked_out_content(), "release\n")

    def test_callback_stops_failed_preparation_and_restores_directory(self):
        message = {
            "project_url": str(self.source),
            "command_list": ["readme-checker"],
            "callback_url": "https://callback.example.invalid/results",
            "task_metadata": {"version_number": "missing-release"},
        }
        channel = Mock()
        method = Mock(delivery_tag=7)
        config = {"OpenCheck": {"repos_dir": str(self.work)}}
        os.chdir(self.root)
        with patch.object(agent, "config", config), \
                patch.object(agent, "_generate_lock_files") as lock_files, \
                patch.object(agent, "_execute_commands") as execute, \
                patch.object(agent, "_cleanup_project_source") as cleanup, \
                patch.object(agent, "_send_results") as send:
            agent.callback_func(channel, method, None, json.dumps(message).encode("utf-8"))
        lock_files.assert_not_called()
        execute.assert_not_called()
        cleanup.assert_not_called()
        send.assert_not_called()
        channel.basic_ack.assert_not_called()
        channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=False)
        self.assertEqual(Path.cwd(), self.root)


if __name__ == "__main__":
    unittest.main()
