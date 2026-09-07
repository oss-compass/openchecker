"""Regression tests for fuzzing_checker's handling of the languages-detector output.

shell_exec returns the raw bytes written by the subprocess. The
languages-detector script prints github-linguist's JSON breakdown
({"language": [files...]}), so the output must be decoded and parsed as
JSON before use. fuzzing_checker instead iterated the bytes object
directly - iterating bytes yields ints - and called .lower() on each,
raising AttributeError and replacing the whole fuzzing-checker result
with an error object whenever language detection succeeded.

These tests patch shell_exec and the URL parser, so no clone or network
access is required.
"""
import json

import pytest

from checkers import fuzzing_checker as fc


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    return repo


def run_fuzzing_checker(monkeypatch, repo, linguist_output):
    monkeypatch.setattr(fc.platform_manager, "parse_project_url",
                        lambda url: ("owner", str(repo)))
    monkeypatch.setattr(fc, "shell_exec",
                        lambda script: linguist_output)
    payload = {"scan_results": {}}
    fc.fuzzing_checker("https://github.com/owner/demo", payload)
    return payload["scan_results"]["fuzzing-checker"]


def test_language_results_are_reported_when_linguist_succeeds(monkeypatch, repo):
    (repo / "fuzz.py").write_text("import atheris\n", encoding="utf-8")
    output = json.dumps({"Python": ["demo/fuzz.py"]}).encode("utf-8")
    results = run_fuzzing_checker(monkeypatch, repo, (output, None))
    tools = {result["tool"]: result for result in results}
    assert tools["Python Atheris"]["found"] is True
    assert tools["Python Atheris"]["files"] == [str(repo / "fuzz.py")]
    # Languages that were not detected are not reported.
    assert "GO NATIVE" not in tools


def test_clusterfuzz_lite_result_is_not_lost(monkeypatch, repo):
    (repo / ".clusterfuzzlite").mkdir()
    (repo / ".clusterfuzzlite" / "Dockerfile").write_text(
        "FROM gcr.io/oss-fuzz-base/base-builder\n", encoding="utf-8")
    output = json.dumps({"Python": ["demo/fuzz.py"]}).encode("utf-8")
    results = run_fuzzing_checker(monkeypatch, repo, (output, None))
    tools = {result["tool"]: result for result in results}
    assert tools["ClusterFuzzLite"]["found"] is True


def test_all_languages_checked_when_detection_fails(monkeypatch, repo):
    # On error the checker keeps its fallback of checking every language.
    results = run_fuzzing_checker(monkeypatch, repo, (None, b"linguist failed"))
    tools = {result["tool"] for result in results}
    assert "GO NATIVE" in tools
    assert "Python Atheris" in tools
    assert all(result["found"] is False for result in results)


def test_all_languages_checked_when_output_is_not_json(monkeypatch, repo):
    results = run_fuzzing_checker(monkeypatch, repo, (b"not json", None))
    tools = {result["tool"] for result in results}
    assert "GO NATIVE" in tools
    assert "Python Atheris" in tools
