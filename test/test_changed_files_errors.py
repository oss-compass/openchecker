"""Differentiate failed Git scans from successful, empty diffs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from openchecker.checkers.changed_files_checker import changed_files_detector


COMMAND = "changed-files-since-commit-detector"


@unittest.skipUnless(shutil.which("git"), "Git is required for integration tests")
class ChangedFilesErrorsTest(unittest.TestCase):
    """Exercise the public checker with real local repositories/processes."""

    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "sample"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Regression Test")
        self.git("config", "user.email", "regression@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / "tracked.txt").write_text("before\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.repo / "tracked.txt").write_text("after\n", encoding="utf-8")
        (self.repo / "added.txt").write_text("new\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "changes")
        self.head = self.git("rev-parse", "HEAD").strip()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.original_cwd)

    def git(self, *args):
        """Run real Git against this test's isolated repository."""
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args],
            stderr=subprocess.STDOUT, text=True)

    def scan(self, revision, project="sample"):
        """Return the checker result while validating unrelated scan state."""
        payload = {"scan_results": {"previous": {"ok": True}}}
        changed_files_detector(
            f"https://github.com/example/{project}.git", payload, revision)
        self.assertEqual(payload["scan_results"]["previous"], {"ok": True})
        self.assertEqual(Path.cwd(), self.root)
        return payload["scan_results"][COMMAND]

    def assert_scan_failed(self, revision):
        """A failed invocation must have an error, not success-shaped lists."""
        result = self.scan(revision)
        self.assertEqual(set(result), {"error"})
        self.assertTrue(result["error"])

    def test_unknown_revision_is_an_error(self):
        self.assert_scan_failed("missing-reference")

    def test_unknown_commit_hash_is_an_error(self):
        self.assert_scan_failed("f" * 40)

    def test_filename_cannot_hide_an_unknown_revision(self):
        # Without the revision/path separator Git accepts this as a pathspec
        # and reports success, although the requested revision does not exist.
        (self.repo / "missing-reference..HEAD").write_text(
            "untracked collision", encoding="utf-8")
        self.assert_scan_failed("missing-reference")

    def test_filename_cannot_break_a_valid_revision(self):
        (self.repo / f"{self.base}..HEAD").write_text(
            "untracked collision", encoding="utf-8")
        result = self.scan(self.base)
        self.assertNotIn("error", result)
        self.assertEqual(result["changed_files"], ["added.txt", "tracked.txt"])

    def test_missing_git_executable_is_an_error(self):
        empty_path = self.root / "empty-path"
        empty_path.mkdir()
        # Exercise a real launch failure; subprocess results are not mocked.
        with patch.dict(os.environ, {"PATH": str(empty_path)}):
            self.assert_scan_failed(self.base)

    def test_valid_unchanged_revision_returns_empty_lists(self):
        self.assertEqual(self.scan(self.head), {
            "changed_files": [], "new_files": [], "rename_files": [],
            "deleted_files": [], "modified_files": []})

    def test_valid_changed_revision_preserves_categories(self):
        self.assertEqual(self.scan(self.base), {
            "changed_files": ["added.txt", "tracked.txt"],
            "new_files": ["added.txt"], "rename_files": [],
            "deleted_files": [], "modified_files": ["tracked.txt"]})

    def test_missing_revision_keeps_existing_error(self):
        self.assertEqual(self.scan(None), {"error": "No commit hash provided"})

    def test_missing_repository_keeps_existing_error(self):
        result = self.scan(self.base, project="missing")
        self.assertEqual(set(result), {"error"})
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
