from types import SimpleNamespace

import pytest

from checkers import standard_command_checker


@pytest.mark.parametrize("stdout", ["not JSON", "{}", '{"SUM": null}'])
def test_cloc_invalid_output_is_reported(monkeypatch, stdout):
    monkeypatch.setattr(standard_command_checker.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(standard_command_checker.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=stdout))

    assert standard_command_checker.get_code_count("https://github.com/example/repo") == (None, "Invalid cloc JSON output.")
