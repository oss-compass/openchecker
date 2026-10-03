from unittest.mock import Mock, patch

from openchecker.checkers.webhooks_checker import get_webhooks


def test_unsupported_and_malformed_repository_urls_return_errors():
    with patch('openchecker.checkers.webhooks_checker.requests.get') as request:
        assert get_webhooks('https://example.com/owner/repo', 'token') == ([], 'Not supported platform.')
        assert get_webhooks('https://github.com/owner', 'token') == ([], 'Invalid project URL format')
        assert get_webhooks('https://github.com/owner/repo/issues', 'token') == ([], 'Invalid project URL format')
        assert get_webhooks('https://[invalid/owner/repo', 'token') == ([], 'Invalid project URL format')
        request.assert_not_called()


def test_trailing_slash_does_not_hide_repository_name():
    response = Mock(status_code=200)
    response.json.return_value = []
    with patch('openchecker.checkers.webhooks_checker.requests.get', return_value=response) as request:
        assert get_webhooks('https://github.com/owner/repo.git/', 'token') == ([], None)
    assert '/repos/owner/repo/hooks' in request.call_args.args[0]
