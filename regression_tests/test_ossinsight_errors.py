from unittest.mock import patch

from openchecker.checkers.standard_command_checker import (
    get_type_countries, get_type_organizations,
)


def test_request_failure_is_returned_to_caller():
    with patch('openchecker.checkers.standard_command_checker.platform_manager.parse_project_url',
               return_value=('example', 'repo')):
        with patch('openchecker.checkers.standard_command_checker.requests.get',
                   side_effect=RuntimeError('network unavailable')):
            for getter in (get_type_countries, get_type_organizations):
                result, error = getter('https://github.com/example/repo', 'stargazers')
                assert result is False
                assert error == 'network unavailable'
