"""Release API calls must use the configured GitHub credential."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))

from openchecker import platform_adapter


def test_github_releases_use_configured_token():
    adapter = platform_adapter.GitHubAdapter({"Github": {"access_key": "configured-token"}})
    api = Mock()
    with patch.object(platform_adapter, "GhApi", return_value=api) as gh_api:
        with patch.object(
            platform_adapter, "paged", return_value=[[{"tag_name": "v1"}]]
        ) as pages:
            releases, error = adapter.get_releases("https://github.com/example/project")

    assert error is None
    assert releases == [{"tag_name": "v1"}]
    gh_api.assert_called_once_with(owner="example", repo="project", token="configured-token")
    pages.assert_called_once_with(api.repos.list_releases, "example", "project", per_page=10)
