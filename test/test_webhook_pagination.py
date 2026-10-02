from unittest.mock import Mock, patch

from openchecker.checkers.webhooks_checker import get_webhooks


def test_github_webhooks_include_second_page():
    first = Mock(status_code=200)
    first.json.return_value = [{"id": n} for n in range(100)]
    second = Mock(status_code=200)
    second.json.return_value = [{"id": 100}]
    with patch("openchecker.checkers.webhooks_checker.requests.get", side_effect=[first, second]) as get:
        hooks, error = get_webhooks("https://github.com/owner/repo", "token")

    assert error is None
    assert [hook["id"] for hook in hooks] == list(range(101))
    assert "page=2" in get.call_args_list[1].args[0]
    assert all(call.kwargs["timeout"] == 10 for call in get.call_args_list)


def test_failed_followup_page_does_not_report_incomplete_hooks():
    first = Mock(status_code=200)
    first.json.return_value = [{"id": n} for n in range(100)]
    second = Mock(status_code=403)
    with patch("openchecker.checkers.webhooks_checker.requests.get", side_effect=[first, second]):
        hooks, error = get_webhooks("https://gitee.com/owner/repo", "token")

    assert hooks == []
    assert "HTTP 403" in error


def test_malformed_response_does_not_escape_checker():
    malformed = Mock(status_code=200)
    malformed.json.side_effect = ValueError("bad JSON")
    with patch("openchecker.checkers.webhooks_checker.requests.get", return_value=malformed):
        hooks, error = get_webhooks("https://github.com/owner/repo", "token")

    assert hooks == []
    assert error == "Invalid webhook response"
