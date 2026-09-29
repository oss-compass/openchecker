from unittest.mock import Mock, patch

from openchecker.checkers.bestpractices_checker import bestpractices_checker


def test_bestpractices_query_preserves_repository_url_with_query_and_fragment():
    project_url = "https://github.com/owner/repo?tab=readme#overview"
    payload = {"scan_results": {}}
    response = Mock()
    response.json.return_value = [{"id": 123}]

    with patch("openchecker.checkers.bestpractices_checker.requests.get", return_value=response) as get:
        bestpractices_checker(project_url, payload)

    get.assert_called_once_with("https://www.bestpractices.dev/projects.json", params={"url": project_url}, timeout=10)
    assert payload["scan_results"]["bestpractices-checker"] == {"id": 123}
