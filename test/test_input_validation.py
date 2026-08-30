#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Input Validation Tests

project_url、version_number、commit_hash 会被 agent 展开进 shell 脚本执行，
本模块验证入口处（API 与 agent）对它们的校验，防止命令注入。

Author: OpenChecker Team
"""

import unittest
from unittest.mock import Mock, patch
import json

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from openchecker.common import (
    is_valid_project_url,
    is_valid_version_number,
    is_valid_commit_hash,
    normalize_project_url
)


class TestProjectUrlValidation(unittest.TestCase):
    """project_url 校验测试"""

    def test_valid_urls(self):
        """合法的 github/gitee/gitcode 仓库地址应通过校验"""
        valid_urls = [
            "https://github.com/owner/repo",
            "https://github.com/owner/repo.git",
            "https://www.github.com/owner/repo",
            "https://github.com/openharmony-sig/tools_oat",
            "https://gitee.com/owner/repo",
            "https://gitee.com/owner/repo.git",
            "https://gitcode.com/owner/repo",
            "https://github.com/owner/.github",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(is_valid_project_url(url))

    def test_rejects_command_injection_payloads(self):
        """含 shell 元字符的注入 payload 应被拒绝"""
        injection_payloads = [
            "https://github.com/a/b; touch /tmp/pwned; true",
            "https://github.com/a/b && touch /tmp/pwned",
            "https://github.com/a/b| touch /tmp/pwned",
            "https://github.com/a/b$(touch /tmp/pwned)",
            "https://github.com/a/b`touch /tmp/pwned`",
            "https://github.com/a/b\ntouch /tmp/pwned",
            "https://github.com/a/b > /tmp/pwned",
        ]
        for url in injection_payloads:
            with self.subTest(url=url):
                self.assertFalse(is_valid_project_url(url))

    def test_rejects_non_https_or_unsupported_platforms(self):
        """非 https 或不受支持的平台地址应被拒绝"""
        invalid_urls = [
            "http://github.com/owner/repo",
            "file:///tmp/repo",
            "git://github.com/owner/repo",
            "ssh://git@github.com/owner/repo",
            "https://evil.com/owner/repo",
            "https://github.com/owner",
            "https://github.com/owner/repo/extra",
            "https://github.com/owner/repo -oProxyCommand=evil",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(is_valid_project_url(url))

    def test_rejects_none_and_non_string(self):
        """None 或非字符串输入应被拒绝"""
        for value in (None, 123, ["https://github.com/a/b"], {}, b"https://github.com/a/b"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_project_url(value))


class TestVersionNumberValidation(unittest.TestCase):
    """version_number 校验测试"""

    def test_valid_version_numbers(self):
        """常见 tag 格式应通过校验"""
        valid_versions = [
            "v1.0.0",
            "1.2.3",
            "1.0.0-alpha",
            "2024.01",
            "v2.0.0+build.1",
            "release/v1.0",
        ]
        for version in valid_versions:
            with self.subTest(version=version):
                self.assertTrue(is_valid_version_number(version))

    def test_rejects_injection_payloads(self):
        """含 shell 元字符的版本号应被拒绝（会被插入 shell 条件判断与 git checkout）"""
        injection_payloads = [
            'None ] && touch /tmp/pwned ; : || [ x',
            'v1.0"; touch /tmp/pwned; "',
            '$(touch /tmp/pwned)',
            '`touch /tmp/pwned`',
            'v1.0; rm -rf /',
            'v1.0 | touch /tmp/pwned',
            '-oProxyCommand=evil',
        ]
        for version in injection_payloads:
            with self.subTest(version=version):
                self.assertFalse(is_valid_version_number(version))

    def test_rejects_none_and_non_string(self):
        """None 或非字符串输入应被拒绝"""
        for value in (None, 123, [], {}):
            with self.subTest(value=value):
                self.assertFalse(is_valid_version_number(value))


class TestCommitHashValidation(unittest.TestCase):
    """commit_hash 校验测试"""

    def test_valid_commit_hashes(self):
        """合法的 git 哈希应通过校验"""
        valid_hashes = [
            "327d7ec",
            "327d7ecf8da82530d90b3f8b7c5c8d1e2f3a4b5c",
            "327D7EC",
            "a" * 64,
        ]
        for commit_hash in valid_hashes:
            with self.subTest(commit_hash=commit_hash):
                self.assertTrue(is_valid_commit_hash(commit_hash))

    def test_rejects_invalid_commit_hashes(self):
        """非法哈希（含非十六进制字符、option 字符串等）应被拒绝"""
        invalid_hashes = [
            "HEAD",
            "--output=/tmp/pwned..HEAD",
            "main",
            "v1.0.0",
            "123456",  # 少于 7 位
            "g27d7ecf8da82530d90b3f8b7c5c8d1e2f3a4b5c",  # 含非十六进制字符
            "327d7ec; touch /tmp/pwned",
        ]
        for commit_hash in invalid_hashes:
            with self.subTest(commit_hash=commit_hash):
                self.assertFalse(is_valid_commit_hash(commit_hash))


class TestNormalizeProjectUrl(unittest.TestCase):
    """.git 后缀处理测试"""

    def test_strips_trailing_git_suffix(self):
        self.assertEqual(normalize_project_url("https://github.com/owner/repo.git"),
                         "https://github.com/owner/repo")

    def test_preserves_dot_github_repo_name(self):
        """仓库名本身含 .git 的（如 .github）不应被破坏"""
        self.assertEqual(normalize_project_url("https://github.com/owner/.github"),
                         "https://github.com/owner/.github")

    def test_preserves_url_without_suffix(self):
        self.assertEqual(normalize_project_url("https://gitee.com/owner/repo"),
                         "https://gitee.com/owner/repo")

    def test_handles_none(self):
        self.assertIsNone(normalize_project_url(None))


class TestOpenCheckApiValidation(unittest.TestCase):
    """API 入口请求体校验测试"""

    @classmethod
    def setUpClass(cls):
        # main.py 使用顶层导入的 user_manager（而非 openchecker.user_manager），
        # 测试直接在该模块实例中注册用户，避免 createUser 只更新 userList 不更新
        # usernameTable 的行为影响
        import user_manager
        from user_manager import User
        cls.test_user = User("opencheck-api-test-user-id", "opencheck_api_test_user",
                             "opencheck_api_test_pass")
        user_manager.userList.append(cls.test_user)
        user_manager.usernameTable[cls.test_user.name] = cls.test_user
        user_manager.useridTable[cls.test_user.id] = cls.test_user

    def setUp(self):
        from openchecker.main import app
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        response = self.client.post('/auth', json={
            "username": "opencheck_api_test_user",
            "password": "opencheck_api_test_pass"
        })
        self.assertEqual(response.status_code, 200)
        self.auth_headers = {'Authorization': f"Bearer {json.loads(response.data)['access_token']}"}

    def valid_payload(self):
        return {
            "commands": ["osv-scanner"],
            "project_url": "https://github.com/owner/repo",
            "callback_url": "https://callback.example.com/result",
            "task_metadata": {}
        }

    @patch('openchecker.main.publish_message')
    def test_valid_request_published(self, mock_publish):
        """合法请求应正常发布到队列"""
        response = self.client.post('/opencheck', headers=self.auth_headers,
                                    json=self.valid_payload())
        self.assertEqual(response.status_code, 200)
        mock_publish.assert_called_once()

    @patch('openchecker.main.publish_message')
    def test_missing_required_field_rejected(self, mock_publish):
        """缺少必填字段应返回 400"""
        for field in ("commands", "project_url", "callback_url"):
            with self.subTest(field=field):
                payload = self.valid_payload()
                del payload[field]
                response = self.client.post('/opencheck', headers=self.auth_headers, json=payload)
                self.assertEqual(response.status_code, 400)
                mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_injection_project_url_rejected(self, mock_publish):
        """注入 payload 的 project_url 应返回 400 且不发布到队列"""
        payload = self.valid_payload()
        payload["project_url"] = "https://github.com/a/b; touch /tmp/pwned; true"
        response = self.client.post('/opencheck', headers=self.auth_headers, json=payload)
        self.assertEqual(response.status_code, 400)
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_injection_commit_hash_rejected(self, mock_publish):
        """注入 payload 的 commit_hash 应返回 400"""
        payload = self.valid_payload()
        payload["commit_hash"] = "--output=/tmp/pwned..HEAD"
        response = self.client.post('/opencheck', headers=self.auth_headers, json=payload)
        self.assertEqual(response.status_code, 400)
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_injection_version_number_rejected(self, mock_publish):
        """task_metadata 中注入 payload 的 version_number 应返回 400"""
        payload = self.valid_payload()
        payload["task_metadata"] = {"version_number": 'None ] && touch /tmp/pwned ; : || [ x'}
        response = self.client.post('/opencheck', headers=self.auth_headers, json=payload)
        self.assertEqual(response.status_code, 400)
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_non_list_commands_rejected(self, mock_publish):
        """commands 不是字符串列表应返回 400"""
        payload = self.valid_payload()
        payload["commands"] = "osv-scanner"
        response = self.client.post('/opencheck', headers=self.auth_headers, json=payload)
        self.assertEqual(response.status_code, 400)
        mock_publish.assert_not_called()

    def test_missing_body_rejected(self):
        """缺少请求体应返回 400 而非 500"""
        response = self.client.post('/opencheck', headers=self.auth_headers)
        self.assertEqual(response.status_code, 400)


class TestAgentCallbackValidation(unittest.TestCase):
    """agent 消费入口校验测试：注入消息必须在执行任何 shell 脚本前被拒绝"""

    def make_message_body(self, **overrides):
        message = {
            "command_list": ["osv-scanner"],
            "project_url": "https://github.com/owner/repo",
            "commit_hash": None,
            "access_token": None,
            "callback_url": "https://callback.example.com/result",
            "task_metadata": {}
        }
        message.update(overrides)
        return json.dumps(message).encode('utf-8')

    def run_callback(self, body):
        from openchecker.agent import callback_func
        ch = Mock()
        method = Mock()
        method.delivery_tag = 1
        properties = Mock()
        callback_func(ch, method, properties, body)
        return ch

    @patch('openchecker.agent.shell_exec')
    def test_injection_project_url_nacked_without_execution(self, mock_shell_exec):
        """project_url 注入 payload 应被 nack 且不执行任何 shell 脚本"""
        body = self.make_message_body(
            project_url="https://github.com/a/b; touch /tmp/pwned; true")
        ch = self.run_callback(body)
        mock_shell_exec.assert_not_called()
        ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)

    @patch('openchecker.agent.shell_exec')
    def test_injection_version_number_nacked_without_execution(self, mock_shell_exec):
        """version_number 注入 payload 应被 nack 且不执行任何 shell 脚本"""
        body = self.make_message_body(
            task_metadata={"version_number": 'None ] && touch /tmp/pwned ; : || [ x'})
        ch = self.run_callback(body)
        mock_shell_exec.assert_not_called()
        ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)

    @patch('openchecker.agent.shell_exec')
    def test_injection_commit_hash_nacked_without_execution(self, mock_shell_exec):
        """commit_hash 注入 payload 应被 nack 且不执行任何 shell 脚本"""
        body = self.make_message_body(commit_hash="327d7ec; touch /tmp/pwned")
        ch = self.run_callback(body)
        mock_shell_exec.assert_not_called()
        ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)

    @patch('openchecker.agent.shell_exec')
    def test_missing_project_url_nacked(self, mock_shell_exec):
        """project_url 缺失时应 nack 消息（否则 prefetch 占满导致 agent 卡死）"""
        body = self.make_message_body(project_url=None)
        ch = self.run_callback(body)
        mock_shell_exec.assert_not_called()
        ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)

    @patch('openchecker.agent.shell_exec')
    def test_valid_url_normalized_before_execution(self, mock_shell_exec):
        """合法 URL 应去除 .git 后缀后正常处理"""
        body = self.make_message_body(project_url="https://github.com/owner/repo.git")
        self.run_callback(body)
        self.assertTrue(mock_shell_exec.called)
        download_script = mock_shell_exec.call_args_list[0][0][0]
        self.assertIn("https://github.com/owner/repo", download_script)
        self.assertNotIn("repo.git", download_script)


if __name__ == '__main__':
    unittest.main()
