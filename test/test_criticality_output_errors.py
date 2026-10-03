from unittest.mock import Mock, patch

from openchecker.checkers.standard_command_checker import run_criticality_score


def test_reads_nested_json_from_stdout():
    process = Mock(returncode=0, stdout='{"details": {"count": 1}, "criticality_score": 0.8}', stderr='')
    with patch("openchecker.checkers.standard_command_checker.subprocess.run", return_value=process):
        assert run_criticality_score("https://github.com/owner/repo") == ({"criticality_score": 0.8}, None)


def test_reads_json_after_log_prefix_on_stderr():
    process = Mock(returncode=0, stdout='', stderr='INFO: score follows: {"criticality_score": 0}')
    with patch("openchecker.checkers.standard_command_checker.subprocess.run", return_value=process):
        assert run_criticality_score("https://github.com/owner/repo") == ({"criticality_score": 0}, None)


def test_success_without_score_returns_an_error_tuple():
    process = Mock(returncode=0, stdout='{"other": 1}', stderr='')
    with patch("openchecker.checkers.standard_command_checker.subprocess.run", return_value=process):
        result, error = run_criticality_score("https://github.com/owner/repo")
    assert result is None
    assert "parse" in error.lower()
