from unittest.mock import patch

from openchecker.checkers.binary_checker import binary_checker


def test_binary_script_error_keeps_original_message():
    for error, expected in ((b'bad byte: \xff', 'bad byte: \ufffd'), ('script failed', 'script failed')):
        payload = {'scan_results': {}}
        with patch('openchecker.checkers.binary_checker.shell_exec', return_value=(None, error)):
            binary_checker('https://github.com/example/repo', payload)
        assert payload['scan_results']['binary-checker'] == {'error': expected}
