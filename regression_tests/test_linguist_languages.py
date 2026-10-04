from unittest.mock import patch

from openchecker.checkers.fuzzing_checker import fuzzing_checker


def test_linguist_json_bytes_selects_language_scanners():
    payload = {'scan_results': {}}
    with patch('openchecker.checkers.fuzzing_checker.platform_manager.parse_project_url', return_value=('owner', 'repo')):
        with patch('openchecker.checkers.fuzzing_checker.shell_exec', return_value=(b'{"Python": 1200, "Go": 500}', None)):
            with patch('openchecker.checkers.fuzzing_checker.check_clusterfuzz_lite', return_value={"tool": "ClusterFuzzLite"}):
                with patch('openchecker.checkers.fuzzing_checker.check_language_fuzzing', return_value=[]) as scan:
                    fuzzing_checker('https://github.com/owner/repo', payload)

    scan.assert_called_once_with('repo', ['python', 'go'])
    assert payload['scan_results']['fuzzing-checker'] == [{"tool": "ClusterFuzzLite"}]


def test_invalid_linguist_output_falls_back_without_crashing():
    payload = {'scan_results': {}}
    with patch('openchecker.checkers.fuzzing_checker.platform_manager.parse_project_url', return_value=('owner', 'repo')):
        with patch('openchecker.checkers.fuzzing_checker.shell_exec', return_value=(b'not json', None)):
            with patch('openchecker.checkers.fuzzing_checker.check_clusterfuzz_lite', return_value={}):
                with patch('openchecker.checkers.fuzzing_checker.check_language_fuzzing', return_value=[]) as scan:
                    fuzzing_checker('https://github.com/owner/repo', payload)
    scan.assert_called_once_with('repo', [])
