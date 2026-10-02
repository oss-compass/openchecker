from unittest.mock import Mock, patch

from openchecker.checkers.standard_command_checker import get_code_count


def test_repository_without_recognized_source_has_zero_code_lines():
    cloc = Mock(returncode=0, stdout='{"header": {"n_files": 0}}')
    with patch("openchecker.checkers.standard_command_checker.os.path.exists", return_value=True), \
         patch("openchecker.checkers.standard_command_checker.subprocess.run", return_value=cloc):
        result, error = get_code_count("https://github.com/owner/empty")

    assert error is None
    assert result == {"code_count": 0}
