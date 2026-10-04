from unittest.mock import Mock, patch

import requests
from openchecker.checkers.bestpractices_checker import bestpractices_checker


def test_request_failure_is_reported_as_an_error():
    payload = {'scan_results': {}}
    with patch('openchecker.checkers.bestpractices_checker.requests.get', side_effect=requests.Timeout('timed out')):
        bestpractices_checker('https://github.com/example/repo', payload)
    assert payload['scan_results']['bestpractices-checker'] == {'error': 'timed out'}


def test_empty_successful_response_has_no_badge():
    payload = {'scan_results': {}}
    response = Mock()
    response.json.return_value = []
    with patch('openchecker.checkers.bestpractices_checker.requests.get', return_value=response):
        bestpractices_checker('https://github.com/example/repo', payload)
    assert payload['scan_results']['bestpractices-checker'] == {}
