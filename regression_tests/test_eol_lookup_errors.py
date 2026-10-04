from checkers import standard_command_checker


def test_eol_config_error_is_reported(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("EOL data unavailable")

    monkeypatch.setattr(standard_command_checker, "open", fail, raising=False)
    result, error = standard_command_checker.get_eol_info("https://github.com/example/repo")
    assert result == {"eol_status": "", "eol_release": "", "eol_time": ""}
    assert error == "EOL data unavailable"
