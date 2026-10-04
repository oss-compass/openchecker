from unittest.mock import patch

from openchecker.platform_adapter import GitHubAdapter


def test_github_release_listing_uses_configured_access_token():
    adapter = GitHubAdapter({'Github': {'access_key': 'test-token'}})
    with patch('openchecker.platform_adapter.GhApi') as api:
        with patch('openchecker.platform_adapter.paged', return_value=[[{'tag_name': 'v1'}]]) as pages:
            releases, error = adapter.get_releases('https://github.com/example/repo')

    assert error is None
    assert releases == [{'tag_name': 'v1'}]
    api.assert_called_once_with(owner='example', repo='repo', token='test-token')
    pages.assert_called_once()
