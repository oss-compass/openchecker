from types import SimpleNamespace

import pytest

from checkers import standard_command_checker


@pytest.mark.parametrize("stdout", [
    '{"checks": []}',
    '{"score": 7, "checks": [{}]}',
    '{"score": 7, "checks": 123}',
])
def test_malformed_scorecard_structure_is_reported(monkeypatch, stdout):
    monkeypatch.setattr(
        standard_command_checker.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=stdout),
    )

    assert standard_command_checker.run_scorecard_cli("https://github.com/example/repo") == (
        None, "Invalid scorecard JSON structure."
    )
