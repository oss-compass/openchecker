from unittest.mock import patch

from openchecker.checkers.binary_checker import binary_checker


def test_binary_output_without_trailing_newline_is_complete():
    payload = {'scan_results': {}}
    output = b'Binary file found: dist/app.exe\nBinary archive found: dist/app.zip'
    with patch('openchecker.checkers.binary_checker.shell_exec', return_value=(output, None)):
        binary_checker('https://github.com/example/repo', payload)

    assert payload['scan_results']['binary-checker'] == {
        'binary_file_list': ['dist/app.exe'],
        'binary_archive_list': ['dist/app.zip'],
    }
