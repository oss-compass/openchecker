"""Regression tests for check_readme_opensource's non-list JSON handling.

A README.OpenSource file that contains valid JSON which is not a list
(e.g. a single object) fell through check_readme_opensource without
hitting any return statement, so the function returned None and
readme_opensource_checker's tuple unpacking raised "cannot unpack
non-iterable NoneType object". The scan result then carried a Python
crash message instead of the intended "not properly formatted"
outcome.
"""
import json

from checkers import document_checker as dc


def make_repo(tmp_path, monkeypatch, readme_content):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "demo"
    repo.mkdir()
    if readme_content is not None:
        (repo / "README.OpenSource").write_text(readme_content, encoding="utf-8")
    return repo


def test_non_list_json_is_reported_as_not_properly_formatted(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch, json.dumps({"Name": "demo"}))
    result, error = dc.check_readme_opensource("https://github.com/owner/demo")
    assert result is False
    assert error == "The README.OpenSource file exists and is not properly formatted."


def test_checker_reports_not_properly_formatted_for_non_list_json(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch, json.dumps({"Name": "demo"}))
    payload = {"scan_results": {}}
    dc.readme_opensource_checker("https://github.com/owner/demo", payload)
    assert payload["scan_results"]["readme-opensource-checker"] == {
        "error": "The README.OpenSource file exists and is not properly formatted."}


def test_valid_entries_are_reported_as_valid(tmp_path, monkeypatch):
    content = json.dumps([{
        "Name": "demo",
        "License": "MIT",
        "License File": "LICENSE",
        "Version Number": "1.0",
        "Owner": "owner",
        "Upstream URL": "https://example.com",
        "Description": "demo project",
    }])
    make_repo(tmp_path, monkeypatch, content)
    result, error = dc.check_readme_opensource("https://github.com/owner/demo")
    assert result is True
    assert error is None


def test_invalid_json_is_reported_as_not_properly_formatted(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch, "{not json")
    result, error = dc.check_readme_opensource("https://github.com/owner/demo")
    assert result is False
    assert error == "README.OpenSource is not properly formatted."


def test_missing_file_is_reported_as_missing(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch, None)
    result, error = dc.check_readme_opensource("https://github.com/owner/demo")
    assert result is False
    assert error == "README.OpenSource does not exist."
