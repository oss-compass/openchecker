import pytest

from checkers import standard_command_checker


@pytest.mark.parametrize("lookup", [
    standard_command_checker.get_type_countries,
    standard_command_checker.get_type_organizations,
])
def test_ossinsight_request_errors_are_reported(monkeypatch, lookup):
    def fail(_url):
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(standard_command_checker.requests, "get", fail)
    result, error = lookup("https://github.com/example/repo", "stargazers")
    assert result is False
    assert error == "service unavailable"
