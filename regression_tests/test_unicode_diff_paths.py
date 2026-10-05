import subprocess

from checkers.changed_files_checker import _get_diff_files


def test_changed_files_preserve_unicode_and_spaces(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "--allow-empty", "-m", "base")
    base = git("rev-parse", "HEAD").stdout.decode("ascii").strip()
    (tmp_path / "中文 file.txt").write_text("content", encoding="utf-8")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-m", "add file")

    monkeypatch.chdir(tmp_path)
    assert _get_diff_files(base) == ["中文 file.txt"]
