"""Callback delivery must determine whether an opencheck message is acknowledged."""

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))

from openchecker import agent


def _run_message(tmp_path, callback_result, callback_url="https://example.test/callback"):
    channel = Mock()
    method = Mock(delivery_tag=7)
    message = {
        "project_url": "https://github.com/example/repo",
        "command_list": [],
        "callback_url": callback_url,
    }
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(agent, "config", {"OpenCheck": {"repos_dir": str(tmp_path)}})
        )
        stack.enter_context(
            patch.object(agent, "_download_project_source", return_value=True)
        )
        stack.enter_context(patch.object(agent, "_generate_lock_files"))
        stack.enter_context(patch.object(agent, "_execute_commands"))
        stack.enter_context(patch.object(agent, "_cleanup_project_source"))
        stack.enter_context(
            patch.object(agent, "_send_results", return_value=callback_result)
        )
        agent.callback_func(channel, method, None, json.dumps(message).encode())
    return channel


def test_successful_callback_acknowledges_message(tmp_path):
    channel = _run_message(tmp_path, True)
    channel.basic_ack.assert_called_once_with(delivery_tag=7)
    channel.basic_nack.assert_not_called()


def test_failed_callback_goes_to_dead_letter_queue(tmp_path):
    channel = _run_message(tmp_path, False)
    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=False)


def test_callback_http_accepts_any_success_status():
    with patch.object(agent, "post_with_backoff", return_value=Mock(status_code=204, text="")):
        assert agent.request_url("https://example.test/callback", {}) == ("", None)


def test_send_results_reports_missing_or_failed_callback():
    assert agent._send_results(None, {}) is False
    with patch.object(agent, "request_url", return_value=(None, "HTTP 500")):
        assert agent._send_results("https://example.test/callback", {}) is False
    with patch.object(agent, "request_url", side_effect=RuntimeError("network down")):
        assert agent._send_results("https://example.test/callback", {}) is False
