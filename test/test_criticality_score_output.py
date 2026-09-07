"""Regression tests for run_criticality_score's output handling.

run_criticality_score had two unhandled failure paths for a
successful command run (returncode 0):

- When the regex found no JSON object in the output (e.g. the tool
  logged something else), the function fell through without a return
  statement and returned None, crashing criticality_score_checker's
  tuple unpacking with "cannot unpack non-iterable NoneType object".
- When the matched JSON parsed but had no "criticality_score" key,
  the KeyError escaped the except clause (which only catches
  json.JSONDecodeError) and propagated through the checker.

(The tool itself prints the score JSON to stderr via a default
logging.StreamHandler, so reading result.stderr is correct.)

These tests patch subprocess.run, so the criticality_score CLI is
not required.
"""
from checkers import standard_command_checker as scc


class FakeCompleted:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_checker(monkeypatch, completed):
    monkeypatch.setattr(scc.subprocess, "run",
                        lambda cmd, **kwargs: completed)
    payload = {"scan_results": {}}
    scc.criticality_score_checker("https://github.com/owner/demo", payload)
    return payload["scan_results"]["criticality-score"]


def test_output_without_json_reports_parse_error(monkeypatch):
    result = run_checker(
        monkeypatch,
        FakeCompleted(0, stderr="INFO: no score computed\n"))
    assert result == {"error": "Failed to parse criticality score JSON."}


def test_json_without_score_key_reports_parse_error(monkeypatch):
    result = run_checker(
        monkeypatch,
        FakeCompleted(0, stderr='{"url": "https://github.com/owner/demo"}'))
    assert result == {"error": "Failed to parse criticality score JSON."}


def test_score_json_is_reported(monkeypatch):
    stderr = ('INFO:root:{\n'
              '    "url": "https://github.com/owner/demo",\n'
              '    "criticality_score": 0.61\n'
              '}')
    result = run_checker(monkeypatch, FakeCompleted(0, stderr=stderr))
    assert result == {"criticality_score": 0.61}


def test_command_failure_reports_error(monkeypatch):
    result = run_checker(
        monkeypatch,
        FakeCompleted(1, stderr="boom"))
    assert result == {"error": "Criticality score command failed."}


def test_non_github_url_is_rejected_without_running_the_tool(monkeypatch):
    def fail(cmd, **kwargs):
        raise AssertionError("subprocess.run must not be called")
    monkeypatch.setattr(scc.subprocess, "run", fail)
    payload = {"scan_results": {}}
    scc.criticality_score_checker("https://gitee.com/owner/demo", payload)
    assert payload["scan_results"]["criticality-score"] == {
        "error": "URL is not supported by criticality score."}
