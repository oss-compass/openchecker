from checkers import standard_command_checker


def test_ohpm_failure_is_not_reported_as_a_success(monkeypatch):
    def fail(_path):
        raise RuntimeError("configuration unavailable")

    monkeypatch.setattr(standard_command_checker, "read_config", fail)
    result, error = standard_command_checker.get_ohpm_info("https://gitee.com/example/repo")
    assert result == {"down_count": "", "dependent": "", "bedependent": ""}
    assert error == "configuration unavailable"
