from unittest.mock import Mock, patch

from openchecker.checkers.url_checker import url_checker


def test_all_successful_http_responses_are_accessible():
    for status, accessible in [(200, True), (204, True), (206, True), (302, False), (404, False)]:
        payload = {"scan_results": {}}
        with patch("openchecker.checkers.url_checker.requests.get", return_value=Mock(status_code=status)):
            url_checker("https://example.com/project", payload)
        assert payload["scan_results"]["url-checker"] == {
            "status_code": status, "is_accessible": accessible
        }
