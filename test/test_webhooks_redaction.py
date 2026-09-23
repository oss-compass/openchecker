"""Webhook reports must not forward credentials returned by code hosts."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))

from openchecker.checkers import webhooks_checker as checker


def test_webhook_credentials_are_redacted_at_every_depth():
    hook = {
        "id": 42,
        "password": "outer-password",
        "config": {
            "url": "https://example.test/hook",
            "secret": "signing-secret",
            "headers": [{"Authorization": "Bearer private-token"}],
        },
    }
    payload = {"scan_results": {}}

    with patch.object(checker, "get_webhooks", return_value=([hook], None)):
        checker.webhooks_checker("https://github.com/example/repo", payload, "api-token")

    result = payload["scan_results"][checker.COMMAND]
    reported = result["webhooks_hooks"][0]
    assert result["access_token"] is True
    assert reported["id"] == 42
    assert reported["config"]["url"] == "https://example.test/hook"
    assert reported["password"] == "******"
    assert reported["config"]["secret"] == "******"
    assert reported["config"]["headers"][0]["Authorization"] == "******"
    assert hook["config"]["secret"] == "signing-secret"
