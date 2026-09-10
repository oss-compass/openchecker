import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from checkers.changed_files_checker import changed_files_detector


@unittest.skipUnless(shutil.which("git"), "Git is required")
class ChangedFilesCheckerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.previous_directory = os.getcwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, self.previous_directory)
        self.repo = Path("sample")
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "core.quotePath", "true")
        self.git("commit", "--allow-empty", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args],
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )

    def detect(self):
        payload = {"scan_results": {}}
        changed_files_detector("https://github.com/example/sample", payload, self.base)
        self.assertEqual(os.getcwd(), self.directory.name)
        return payload["scan_results"]["changed-files-since-commit-detector"]

    def test_preserves_changed_file_names(self):
        names = [" leading space.txt", "中文.txt", "ordinary.txt"]
        if os.name != "nt":
            names.extend(['quote"name.txt', "tab\tname.txt", "line\nname.txt"])
        for name in names:
            (self.repo / name).write_text("content", encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "-qm", "add files")

        result = self.detect()
        self.assertCountEqual(result["changed_files"], names)
        self.assertCountEqual(result["new_files"], names)
        for key in ("rename_files", "deleted_files", "modified_files"):
            self.assertEqual(result[key], [])

    def test_empty_diff(self):
        for files in self.detect().values():
            self.assertEqual(files, [])

    def test_preserves_names_in_change_categories(self):
        for name in ("修改.txt", "删除.txt", "old.txt"):
            (self.repo / name).write_text(name * 20, encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "-qm", "initial files")
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.repo / "修改.txt").write_text("updated", encoding="utf-8")
        (self.repo / "删除.txt").unlink()
        (self.repo / "old.txt").rename(self.repo / "重命名.txt")
        self.git("add", "--all")
        self.git("commit", "-qm", "change files")

        result = self.detect()
        self.assertEqual(result["modified_files"], ["修改.txt"])
        self.assertEqual(result["deleted_files"], ["删除.txt"])
        self.assertEqual(result["rename_files"], ["重命名.txt"])
        self.assertEqual(result["new_files"], [])


if __name__ == "__main__":
    unittest.main()
