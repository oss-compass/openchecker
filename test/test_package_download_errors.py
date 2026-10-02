from unittest.mock import Mock, patch

from openchecker.checkers.standard_command_checker import get_package_info


def response(status, data):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


def test_empty_download_period_returns_zero_without_index_error():
    metadata = response(200, {"description": "A package", "versions": {}})
    downloads = response(200, {"downloads": []})
    with patch("openchecker.checkers.standard_command_checker.requests.get", side_effect=[metadata, downloads]):
        result, error = get_package_info("https://gitee.com/owner/package")

    assert error is None
    assert result["down_count"] == 0
    assert result["day_enter"] == ""


def test_download_api_failure_returns_an_error_instead_of_none():
    metadata = response(200, {"description": "A package", "versions": {}})
    downloads = response(503, {})
    with patch("openchecker.checkers.standard_command_checker.requests.get", side_effect=[metadata, downloads]):
        result, error = get_package_info("https://gitee.com/owner/package")

    assert "HTTP 503" in error
    assert result["description"] == "A package"
