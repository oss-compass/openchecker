#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Outbound Request Timeout Tests

agent 的消费线程池只有 1 个 worker 且 prefetch_count=1，外呼请求（回调 POST、
LLM 调用）一旦无超时挂起，整个 agent 会停止处理所有后续任务。本模块验证
外呼请求始终带有超时。

Author: OpenChecker Team
"""

import unittest
from unittest.mock import patch, Mock

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'openchecker'))

import requests

from openchecker.exponential_backoff import (
    post_with_backoff,
    completion_with_backoff,
    HTTP_CONNECT_TIMEOUT_S,
    HTTP_READ_TIMEOUT_S,
    LLM_TIMEOUT_S
)


class TestPostWithBackoff(unittest.TestCase):
    """回调 POST 超时测试"""

    @patch('openchecker.exponential_backoff.requests.post')
    def test_default_timeout_applied(self, mock_post):
        """未显式传 timeout 时应使用默认 (connect, read) 超时，而非 requests 的无限等待"""
        post_with_backoff(url="https://callback.example.com/result", json={"a": 1})
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['timeout'], (HTTP_CONNECT_TIMEOUT_S, HTTP_READ_TIMEOUT_S))

    @patch('openchecker.exponential_backoff.requests.post')
    def test_caller_timeout_respected(self, mock_post):
        """调用方显式传入的 timeout 应被保留"""
        post_with_backoff(url="https://callback.example.com/result", timeout=5)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['timeout'], 5)

    @patch('openchecker.exponential_backoff.requests.post')
    def test_timeout_error_retried(self, mock_post):
        """超时异常应触发退避重试而不是直接失败"""
        mock_post.side_effect = [
            requests.exceptions.ConnectTimeout("timed out"),
            Mock(status_code=200)
        ]
        with patch('openchecker.exponential_backoff.time.sleep'):
            response = post_with_backoff(url="https://callback.example.com/result")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(response.status_code, 200)


class TestCompletionWithBackoff(unittest.TestCase):
    """LLM 调用超时测试"""

    @patch('openchecker.exponential_backoff.OpenAI')
    def test_openai_client_timeout_set(self, mock_openai_cls):
        """OpenAI 客户端应显式设置超时（SDK 默认 600s 过长，单 worker 串行下会长期占位）"""
        mock_client = Mock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="YES"))])

        completion_with_backoff(messages=[{"role": "user", "content": "test"}])

        _, kwargs = mock_openai_cls.call_args
        self.assertEqual(kwargs['timeout'], LLM_TIMEOUT_S)


if __name__ == '__main__':
    unittest.main()
