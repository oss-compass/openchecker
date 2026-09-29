import json

from openchecker.checkers.document_checker import check_readme_opensource


def test_readme_opensource_rejects_empty_and_non_list_documents(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.OpenSource"
    monkeypatch.chdir(tmp_path)

    for data in ([], {"Name": "project"}):
        readme.write_text(json.dumps(data), encoding="utf-8")
        valid, error = check_readme_opensource("https://github.com/owner/repo")
        assert valid is False
        assert error
