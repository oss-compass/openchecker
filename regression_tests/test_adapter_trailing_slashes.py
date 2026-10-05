import pytest

from platform_adapter import GitCodeAdapter, GitHubAdapter, GiteeAdapter


@pytest.mark.parametrize("adapter,section,host", [
    (GitHubAdapter, "Github", "github.com"),
    (GiteeAdapter, "Gitee", "gitee.com"),
    (GitCodeAdapter, "GitCode", "gitcode.com"),
])
@pytest.mark.parametrize("suffix", ["/", ".git/"])
def test_repository_urls_accept_one_trailing_slash(adapter, section, host, suffix):
    instance = adapter({section: {"access_key": "token"}})
    assert instance.parse_project_url(f"https://{host}/owner/repo{suffix}") == ("owner", "repo")


def test_repository_urls_still_reject_extra_path_segments():
    adapter = GitHubAdapter({"Github": {"access_key": "token"}})
    with pytest.raises(ValueError):
        adapter.parse_project_url("https://github.com/owner/repo/issues/")
