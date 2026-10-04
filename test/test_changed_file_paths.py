import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from checkers.changed_files_checker import changed_files_detector


@unittest.skipIf(os.name == "nt", "POSIX filename characters are not valid on Windows")
class ChangedFilePathsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.original_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.original_cwd)
        self.git("init", "-q")
        self.git("config", "user.name", "Test Author")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "core.quotePath", "true")
        self.git("config", "diff.renames", "true")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
             "-C", str(self.repo), *args],
            stderr=subprocess.STDOUT,
        )

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "--allow-empty", "-qm", "test fixture")
        return self.git("rev-parse", "HEAD").decode("ascii").strip()

    def scan(self, base):
        os.chdir(self.root)
        payload = {"scan_results": {}}
        changed_files_detector("https://github.com/example/repo", payload, base)
        return payload["scan_results"]["changed-files-since-commit-detector"]

    def test_added_paths_round_trip_independently_of_git_quoting(self):
        base = self.commit()
        names = ["normal.txt", "中文.txt", "tab\tname.txt", "line\nname.txt",
                 "carriage\rreturn.txt", 'quote"name.txt', "back\\slash.txt",
                 " leading.txt", "trailing.txt "]
        for name in names:
            (self.repo / name).write_text(name, encoding="utf-8")
        self.commit()

        for quote_paths in ("true", "false"):
            with self.subTest(core_quotePath=quote_paths):
                self.git("config", "core.quotePath", quote_paths)
                result = self.scan(base)
                self.assertCountEqual(result["changed_files"], names)
                self.assertCountEqual(result["new_files"], names)
                for category in ("rename_files", "deleted_files", "modified_files"):
                    self.assertEqual(result[category], [])

    def test_change_filters_preserve_paths(self):
        modified = "修改\tfile.txt"
        deleted = "删除\nfile.txt"
        renamed = "重命名\rfile.txt"
        for name, content in ((modified, "before\n"), (deleted, "delete me\n"),
                              ("old.txt", "retain this unique content\n")):
            (self.repo / name).write_text(content, encoding="utf-8")
        base = self.commit()
        (self.repo / modified).write_text("after\n", encoding="utf-8")
        (self.repo / deleted).unlink()
        (self.repo / "old.txt").rename(self.repo / renamed)
        self.commit()

        result = self.scan(base)

        self.assertCountEqual(result["changed_files"], [modified, deleted, renamed])
        self.assertEqual(result["modified_files"], [modified])
        self.assertEqual(result["deleted_files"], [deleted])
        self.assertEqual(result["rename_files"], [renamed])
        self.assertEqual(result["new_files"], [])

    def test_unchanged_repository_returns_empty_lists(self):
        base = self.commit()

        result = self.scan(base)

        self.assertTrue(result)
        self.assertTrue(all(paths == [] for paths in result.values()))


if __name__ == "__main__":
    unittest.main()
