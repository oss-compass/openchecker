"""Exercise chat retry policy with the real OpenAI SDK and an HTTP transport."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import httpx
import openai

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))
# Embedding frameworks are unrelated to chat retry policy; no model is loaded.
with patch.dict(sys.modules, {"torch": Mock(), "transformers": Mock()}):
    import llm


class ChatRetryErrorsTest(unittest.TestCase):
    def make_handler(self, transport):
        client = openai.OpenAI(
            api_key="test-token", base_url="https://example.invalid/v1",
            # Isolate the outer retry policy from the SDK's own retries.
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(transport)),
        )
        self.addCleanup(client.close)
        handler = llm.ChatCompletionHandler.__new__(llm.ChatCompletionHandler)
        handler.client = client
        handler.model = "test-model"
        return handler

    @staticmethod
    def success():
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0,
            "model": "test-model", "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ok"},
            }],
        })

    def test_permanent_http_errors_fail_without_outer_retries(self):
        for status, error_type in (
                (400, openai.BadRequestError), (401, openai.AuthenticationError),
                (403, openai.PermissionDeniedError), (404, openai.NotFoundError),
                (422, openai.UnprocessableEntityError)):
            with self.subTest(status=status):
                transport = Mock(return_value=httpx.Response(
                    status, json={"error": {"message": "permanent failure"}}))
                handler = self.make_handler(transport)
                with patch.object(llm.time, "sleep") as sleep:
                    with self.assertRaises(error_type):
                        handler.non_streaming_chat([{"role": "user", "content": "hello"}])
                self.assertEqual(transport.call_count, 1)
                sleep.assert_not_called()

    def test_transient_http_errors_can_recover(self):
        for status in (408, 409, 429, 500, 502, 503):
            with self.subTest(status=status):
                transport = Mock(side_effect=[
                    httpx.Response(status, json={"error": {"message": "try again"}}),
                    self.success(),
                ])
                handler = self.make_handler(transport)
                with patch.object(llm.time, "sleep") as sleep:
                    self.assertEqual(handler.non_streaming_chat([]), "ok")
                self.assertEqual(transport.call_count, 2)
                sleep.assert_called_once()

    def test_connection_and_timeout_errors_can_recover(self):
        for error_type in (httpx.ConnectError, httpx.ReadTimeout):
            with self.subTest(error=error_type.__name__):
                transport = Mock(side_effect=[error_type("offline"), self.success()])
                handler = self.make_handler(transport)
                with patch.object(llm.time, "sleep") as sleep:
                    self.assertEqual(handler.non_streaming_chat([]), "ok")
                self.assertEqual(transport.call_count, 2)
                sleep.assert_called_once()

    def test_non_api_errors_are_not_retried(self):
        failure = ValueError("invalid input")
        operation = Mock(side_effect=failure)
        wrapped = llm.retry_with_exponential_backoff(operation, max_retries=2)
        with patch.object(llm.time, "sleep") as sleep:
            with self.assertRaises(ValueError) as caught:
                wrapped()
        self.assertIs(caught.exception, failure)
        operation.assert_called_once()
        sleep.assert_not_called()

    def test_retry_exhaustion_preserves_sdk_error(self):
        failure = openai.RateLimitError(
            "limited", response=httpx.Response(
                429, request=httpx.Request("POST", "https://example.invalid/v1")),
            body={"error": "limited"},
        )
        operation = Mock(side_effect=failure)
        wrapped = llm.retry_with_exponential_backoff(operation, max_retries=2)
        with patch.object(llm.time, "sleep") as sleep:
            with self.assertRaises(openai.RateLimitError) as caught:
                wrapped()
        self.assertIs(caught.exception, failure)
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_custom_retry_errors_are_honored(self):
        operation = Mock(side_effect=[ValueError("retry me"), "ok"])
        wrapped = llm.retry_with_exponential_backoff(
            operation, errors=(ValueError,), max_retries=1)
        with patch.object(llm.time, "sleep") as sleep:
            self.assertEqual(wrapped(), "ok")
        self.assertEqual(operation.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
