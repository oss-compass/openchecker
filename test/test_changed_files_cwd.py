import os
from unittest.mock import patch

from openchecker.checkers.changed_files_checker import changed_files_detector


def test_changed_files_does_not_change_process_directory(tmp_path, monkeypatch):
    (tmp_path / "repo").mkdir()
    monkeypatch.chdir(tmp_path)
    payload = {"scan_results": {}}

    with patch("openchecker.checkers.changed_files_checker._get_diff_files", side_effect=RuntimeError("git failed")):
        try:
            changed_files_detector("https://github.com/owner/repo", payload, "abc123")
        except RuntimeError:
            pass

    assert os.getcwd() == str(tmp_path)


def test_diff_uses_explicit_repository_path():
    from openchecker.checkers.changed_files_checker import _get_diff_files

    with patch("openchecker.checkers.changed_files_checker.subprocess.check_output", return_value="file.txt\n") as command:
        assert _get_diff_files("abc123", "M", "repo") == ["file.txt"]
    assert command.call_args.args[0][:3] == ["git", "-C", "repo"]
