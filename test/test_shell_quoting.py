#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Shell Quoting Defense-in-Depth Tests

OWASP 命令注入防护要求分层：输入白名单（见 test_input_validation.py）+
shell 元字符转义。本模块验证转义层独立生效：即使绕过 API 校验直接把敌意
project_url 渲染进脚本（例如 agent.ruby_licenses 使用被扫描仓库内容派生的
vcs_url，属于仓库内容驱动的输入，校验层无法覆盖），bash 执行时也不会产生
命令注入。

Author: OpenChecker Team
"""

import unittest
import json
import os
import subprocess
import tempfile
import shutil
from unittest.mock import patch

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'openchecker'))

from constans import shell_script_handlers
from shlex import quote as shell_quote


HOSTILE_URL = "https://github.com/a/b; touch {marker}; true"


class TestShellQuotingDefenseInDepth(unittest.TestCase):
    """shlex.quote 转义层测试：敌意 URL 渲染进脚本后执行不产生副作用"""

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="openchecker_quote_")
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)
        self.marker = os.path.join(self.workdir, "pwned_marker")

    def render_and_execute(self, handler_name, hostile_url):
        # 与调用点一致：先 shlex.quote 再 format（见 agent.py / fuzzing_checker.py）；
        # 传入完整参数集，format 只取模板实际使用的字段
        script = shell_script_handlers[handler_name].format(
            project_url=shell_quote(hostile_url), version_number="None",
            sonar_host="https://sonar.example.com", sonar_port="9000",
            sonar_token="token", sonar_project_name="proj", scan_timeout_s="1")
        # 与 agent 一致的真实执行方式
        return subprocess.run(["/bin/bash", "-c", script],
                              cwd=self.workdir, capture_output=True,
                              text=True, timeout=60)

    def test_injected_command_not_executed_across_handlers(self):
        """所有含 project_url 的 handler：注入命令不得执行"""
        for handler in shell_script_handlers:
            with self.subTest(handler=handler):
                if os.path.exists(self.marker):
                    os.remove(self.marker)
                self.render_and_execute(
                    handler, HOSTILE_URL.format(marker=self.marker))
                self.assertFalse(os.path.exists(self.marker),
                                 f"injection executed via {handler}")

    def test_quoted_url_still_reaches_git_clone(self):
        """合法 URL 经转义后功能不变：git clone 收到完整 URL 参数"""
        # bash 单引号包裹的 URL 被还原为单参数，clone 尝试访问（此处必然失败，
        # 但 stderr 必须是 git 的 clone 错误，而不是命令未找到/语法错误）
        url = "https://github.com/oss-compass/openchecker.git"
        script = shell_script_handlers["download-checkout"].format(
            project_url=url, version_number="None")
        self.assertIn(f"git clone  {url} ", script)
        result = subprocess.run(["/bin/bash", "-c", script],
                                cwd=self.workdir, capture_output=True,
                                text=True, timeout=120)
        self.assertIn("Cloning into", result.stderr + result.stdout)

    def test_ruby_licenses_repo_content_derived_url_is_quoted(self):
        """ruby_licenses 使用 ORT 输出（仓库内容）中的 vcs_url，
        该输入不受 API 校验保护，必须被转义后才能进入 shell"""
        from openchecker.agent import ruby_licenses

        hostile_vcs = HOSTILE_URL.format(marker="/tmp/ruby_licenses_pwned_marker")
        data = {"analyzer": {"result": {"packages": [
            {"declared_licenses": [], "homepage_url": "",
             "vcs_processed": {"url": hostile_vcs}}
        ]}}}

        captured = {}

        def fake_shell_exec(script, param=None):
            captured["script"] = script
            return b"{}", None

        with patch("openchecker.agent.shell_exec", side_effect=fake_shell_exec):
            ruby_licenses(data)

        self.assertIn("'%s'" % hostile_vcs, captured["script"],
                      "vcs_url was not shell-quoted before formatting")
        self.assertNotIn("touch /tmp/ruby_licenses_pwned_marker", captured["script"].replace(
            "'%s'" % hostile_vcs, ""))
        self.assertFalse(os.path.exists("/tmp/ruby_licenses_pwned_marker"))


if __name__ == '__main__':
    unittest.main()
