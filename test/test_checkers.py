#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Checkers Module Tests

This module provides comprehensive tests for various checker functionalities
including security, compliance, and quality assessment checkers.

Author: OpenChecker Team
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import os
import re
import tempfile
import shutil
import yaml

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from openchecker.checkers import (
    ci_tests_checker,
    sast_checker,
    security_policy_checker,
    token_permissions_checker,
    fuzzing_checker,
    binary_checker,
    url_checker,
    sonar_checker
)


class TestSASTChecker(unittest.TestCase):
    """SAST检查器测试类"""

    def setUp(self):
        """测试前置设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(self.repo_path)

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_parse_workflow_for_sast_tools_codeql(self):
        """测试检测CodeQL工具"""
        workflow_content = """
        name: Security Analysis
        on: [push, pull_request]
        jobs:
          security:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v2
              - uses: github/codeql-action/analyze@v1
                with:
                  languages: python
        """
        
        detected_tools = sast_checker._parse_workflow_for_sast_tools(workflow_content)
        self.assertIn("codeql", detected_tools)

    def test_parse_workflow_for_sast_tools_snyk(self):
        """测试检测Snyk工具"""
        workflow_content = """
        name: Security Analysis
        jobs:
          security:
            steps:
              - uses: snyk/actions/node@master
                env:
                  SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        """
        
        detected_tools = sast_checker._parse_workflow_for_sast_tools(workflow_content)
        self.assertIn("snyk", detected_tools)

    def test_parse_workflow_invalid_yaml(self):
        """测试无效YAML处理"""
        invalid_yaml = "invalid: yaml: content: ["
        
        # 应该不抛出异常，而是返回空列表或使用正则表达式解析
        detected_tools = sast_checker._parse_workflow_for_sast_tools(invalid_yaml)
        self.assertIsInstance(detected_tools, list)

    @patch('openchecker.checkers.sast_checker.list_workflow_files')
    @patch('openchecker.checkers.sast_checker.platform_manager')
    def test_detect_workflows(self, mock_platform, mock_list_files):
        """测试工作流检测"""
        # 设置模拟
        mock_list_files.return_value = [".github/workflows/security.yml"]
        mock_adapter = Mock()
        mock_adapter.get_file_content.return_value = ("""
        jobs:
          security:
            steps:
              - uses: github/codeql-action/analyze@v1
        """, None)
        mock_platform.get_adapter.return_value = mock_adapter
        
        # 执行测试
        result = sast_checker.detect_workflows(self.repo_path, "github")
        
        # 验证结果
        self.assertIsInstance(result, list)
        if result:
            self.assertIn("tools", result[0])


class TestSecurityPolicyChecker(unittest.TestCase):
    """安全策略检查器测试类"""

    def setUp(self):
        """测试前置设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(self.repo_path)

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_find_security_policy_files_standard(self):
        """测试查找标准安全策略文件"""
        # 创建安全策略文件
        security_file = os.path.join(self.repo_path, "SECURITY.md")
        with open(security_file, 'w') as f:
            f.write("# Security Policy\n\nThis is our security policy.")
        
        # 执行测试
        found_files = security_policy_checker.find_security_policy_files(self.repo_path, "github")
        
        # 验证结果
        self.assertTrue(len(found_files) > 0)
        self.assertTrue(any("SECURITY.md" in f for f in found_files))

    def test_find_security_policy_files_platform_specific(self):
        """测试查找平台特定的安全策略文件"""
        # 创建GitHub特定的安全策略文件
        github_dir = os.path.join(self.repo_path, ".github")
        os.makedirs(github_dir)
        security_file = os.path.join(github_dir, "SECURITY.md")
        with open(security_file, 'w') as f:
            f.write("# GitHub Security Policy")
        
        # 执行测试
        found_files = security_policy_checker.find_security_policy_files(self.repo_path, "github")
        
        # 验证结果
        self.assertTrue(len(found_files) > 0)

    def test_analyze_security_policy_content(self):
        """测试分析安全策略内容"""
        # 创建测试文件
        security_file = os.path.join(self.temp_dir, "security.md")
        security_content = """
        # Security Policy
        
        ## Reporting Security Vulnerabilities
        
        Please report security vulnerabilities to security@example.com
        
        ## Supported Versions
        
        We support the following versions:
        - 2.0.x
        - 1.9.x
        """
        
        with open(security_file, 'w') as f:
            f.write(security_content)
        
        # 执行测试
        result = security_policy_checker.analyze_security_policy_content(security_file)
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertIn("has_reporting_section", result)
        self.assertIn("has_supported_versions", result)


class TestTokenPermissionsChecker(unittest.TestCase):
    """令牌权限检查器测试类"""

    def test_get_permission_level(self):
        """测试权限级别判断"""
        # 测试各种权限级别
        test_cases = [
            ("none", token_permissions_checker.PERMISSION_LEVEL_NONE),
            ("read", token_permissions_checker.PERMISSION_LEVEL_READ),
            ("write", token_permissions_checker.PERMISSION_LEVEL_WRITE),
            ("unknown_value", token_permissions_checker.PERMISSION_LEVEL_UNKNOWN)
        ]
        
        for value, expected in test_cases:
            result = token_permissions_checker._get_permission_level(value)
            self.assertEqual(result, expected)

    def test_extract_top_level_permissions(self):
        """测试提取顶级权限"""
        workflow = {
            "permissions": {
                "contents": "read",
                "actions": "write",
                "packages": "none"
            }
        }
        
        result = token_permissions_checker._extract_top_level_permissions(workflow, "test.yml")
        
        # 验证结果
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        
        # 检查权限项
        permission_names = [p["permission"] for p in result]
        self.assertIn("contents", permission_names)
        self.assertIn("actions", permission_names)


class TestFuzzingChecker(unittest.TestCase):
    """模糊测试检查器测试类"""

    def setUp(self):
        """测试前置设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(self.repo_path)

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_fuzzing_result(self):
        """测试创建模糊测试结果"""
        result = fuzzing_checker.create_fuzzing_result(
            tool_name="libFuzzer",
            found=True,
            files=["fuzz_test.cc"],
            description="Found LibFuzzer implementation"
        )
        
        # 验证结果结构
        self.assertEqual(result["tool"], "libFuzzer")
        self.assertTrue(result["found"])
        self.assertEqual(result["files"], ["fuzz_test.cc"])
        self.assertEqual(result["description"], "Found LibFuzzer implementation")

    def test_detect_go_native_fuzzing(self):
        """测试检测Go原生模糊测试"""
        # 创建Go测试文件
        go_test_file = os.path.join(self.repo_path, "fuzz_test.go")
        go_test_content = """
        package main
        
        import "testing"
        
        func FuzzExample(f *testing.F) {
            f.Add("input")
            f.Fuzz(func(t *testing.T, input string) {
                // Fuzz logic here
            })
        }
        """
        
        with open(go_test_file, 'w') as f:
            f.write(go_test_content)
        
        # 这里需要根据实际的fuzzing_checker实现来调用相应的检测函数
        # 假设有detect_go_fuzzing函数
        # result = fuzzing_checker.detect_go_fuzzing(self.repo_path)
        # self.assertTrue(result["found"])


class TestBinaryChecker(unittest.TestCase):
    """二进制文件检查器测试类"""

    def setUp(self):
        """测试前置设置"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('openchecker.checkers.binary_checker.platform_manager')
    def test_binary_checker_success(self, mock_platform):
        """测试二进制检查器成功执行"""
        # 设置模拟
        mock_platform.download_project_source.return_value = (True, "")
        
        # 创建响应载荷
        res_payload = {"scan_results": {}}
        
        # 执行测试
        project_url = "https://github.com/test/repo"
        binary_checker.binary_checker(project_url, res_payload)
        
        # 验证结果
        self.assertIn("binary-checker", res_payload["scan_results"])

    def test_detect_binary_files(self):
        """测试检测二进制文件"""
        # 创建测试文件
        text_file = os.path.join(self.temp_dir, "text.txt")
        with open(text_file, 'w') as f:
            f.write("This is a text file")
        
        # 创建二进制文件（模拟）
        binary_file = os.path.join(self.temp_dir, "binary.exe")
        with open(binary_file, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05')  # 二进制数据
        
        # 这里需要根据实际的binary_checker实现来测试
        # 通常会检查文件扩展名或内容


class TestURLChecker(unittest.TestCase):
    """URL检查器测试类"""

    @patch('openchecker.checkers.url_checker.platform_manager')
    def test_url_checker_valid_url(self, mock_platform):
        """测试有效URL检查"""
        # 设置模拟
        mock_adapter = Mock()
        mock_adapter.is_valid_project_url.return_value = True
        mock_platform.get_adapter.return_value = mock_adapter
        
        # 创建响应载荷
        res_payload = {"scan_results": {}}
        
        # 执行测试
        project_url = "https://github.com/test/repo"
        url_checker.url_checker(project_url, res_payload)
        
        # 验证结果
        self.assertIn("url-checker", res_payload["scan_results"])

    @patch('openchecker.checkers.url_checker.platform_manager')
    def test_url_checker_invalid_url(self, mock_platform):
        """测试无效URL检查"""
        # 设置模拟
        mock_platform.get_adapter.return_value = None
        
        # 创建响应载荷
        res_payload = {"scan_results": {}}
        
        # 执行测试
        project_url = "invalid-url"
        url_checker.url_checker(project_url, res_payload)
        
        # 验证结果
        self.assertIn("url-checker", res_payload["scan_results"])


class TestSonarChecker(unittest.TestCase):
    """SonarQube检查器测试类"""

    def setUp(self):
        """测试前置设置"""
        self.test_config = {
            "SonarQube": {
                "host": "localhost",
                "port": "9000",
                "token": "test_token"
            }
        }

    @patch('openchecker.checkers.sonar_checker.platform_manager')
    @patch('openchecker.checkers.sonar_checker._check_sonar_project_exists')
    @patch('openchecker.checkers.sonar_checker.shell_exec')
    def test_sonar_checker_success(self, mock_shell, mock_exists, mock_platform):
        """测试SonarQube检查器成功执行"""
        # 设置模拟
        mock_platform.parse_project_url.return_value = ("owner", "repo")
        mock_adapter = Mock()
        mock_adapter.get_platform_name.return_value = "github"
        mock_platform.get_adapter.return_value = mock_adapter
        mock_exists.return_value = True
        mock_shell.return_value = ("Success", None)
        
        # 创建响应载荷
        res_payload = {"scan_results": {}}
        
        # 执行测试
        project_url = "https://github.com/owner/repo"
        sonar_checker.sonar_checker(project_url, res_payload, self.test_config)
        
        # 验证结果
        mock_shell.assert_called_once()

    @patch('openchecker.checkers.sonar_checker.requests.get')
    def test_check_sonar_project_exists(self, mock_get):
        """测试检查SonarQube项目是否存在"""
        # 设置模拟响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"components": [{"key": "test_project"}]}
        mock_get.return_value = mock_response
        
        # 这里需要根据实际的sonar_checker实现来测试
        # result = sonar_checker._check_sonar_project_exists("test_project", self.test_config["SonarQube"])
        # self.assertTrue(result)


class TestCITestsChecker(unittest.TestCase):
    """CI-Tests检查器测试类"""

    def setUp(self):
        """测试前置设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.temp_dir, "test_repo")
        os.makedirs(self.repo_path)
        self.workflows_dir = os.path.join(self.repo_path, ".github", "workflows")
        os.makedirs(self.workflows_dir)

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _write_workflow(self, name, content):
        """在工作流目录中写入一个工作流文件并返回其绝对路径"""
        file_path = os.path.join(self.workflows_dir, name)
        with open(file_path, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return file_path

    def test_test_command_patterns_cover_all_ecosystems(self):
        """测试各生态都配置了可编译的测试命令正则"""
        expected_ecosystems = ["python", "nodejs", "java", "go", "rust", "ruby", "dotnet", "php"]

        for ecosystem in expected_ecosystems:
            self.assertIn(ecosystem, ci_tests_checker.TEST_COMMAND_PATTERNS)
            patterns = ci_tests_checker.TEST_COMMAND_PATTERNS[ecosystem]
            self.assertTrue(patterns, f"{ecosystem} 的测试命令模式不能为空")
            for pattern in patterns:
                # 编译失败的正则会在扫描时静默失效，这里显式校验
                re.compile(pattern)

    def test_collect_test_command_matches_per_ecosystem(self):
        """测试每个生态的代表性测试命令都能被识别，且每个生态每行只记一次"""
        cases = [
            ("        run: pytest -q", "python"),
            ("        run: python -m unittest discover", "python"),
            ("        run: tox -e py39", "python"),
            ("        run: nox", "python"),
            ("      - run: npm test", "nodejs"),
            ("      - run: yarn test", "nodejs"),
            ("      - run: pnpm test", "nodejs"),
            ("      - run: npx jest --ci", "nodejs"),
            ("      - run: npx vitest run", "nodejs"),
            ("      - run: mocha test/**/*.js", "nodejs"),
            ("      - run: mvn -B test", "java"),
            ("      - run: gradle test", "java"),
            ("      - run: sbt test", "java"),
            ("      - run: go test ./...", "go"),
            ("      - run: cargo test --all", "rust"),
            ("      - run: rake test", "ruby"),
            ("      - run: bundle exec rspec", "ruby"),
            ("      - run: dotnet test", "dotnet"),
            ("      - run: phpunit --coverage-text", "php"),
        ]

        for line, expected_ecosystem in cases:
            matches = ci_tests_checker._collect_test_command_matches([line])
            ecosystems = [match["ecosystem"] for match in matches]
            self.assertIn(expected_ecosystem, ecosystems, msg=f"未识别: {line}")
            # 同一生态的多个正则命中同一行时只能报告一次
            self.assertEqual(ecosystems.count(expected_ecosystem), 1, msg=f"重复匹配: {line}")

    def test_collect_test_command_matches_ignores_build_only_workflow(self):
        """测试只构建/发布的工作流不会误报为测试"""
        lines = [
            "name: Release",
            "on:",
            "  push:",
            "    tags: ['v*']",
            "jobs:",
            "  publish:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - run: npm run build",
            "      - run: docker build -t app .",
            "      - run: npm publish",
        ]

        self.assertEqual(ci_tests_checker._collect_test_command_matches(lines), [])

    def test_all_test_command_pattern_and_find_pattern_line(self):
        """测试合并正则以及行号定位辅助函数"""
        combined = ci_tests_checker._all_test_command_pattern()

        self.assertTrue(re.search(combined, "      - run: cargo test", re.IGNORECASE))
        self.assertFalse(re.search(combined, "      - run: npm run build", re.IGNORECASE))

        lines = ["name: CI", "      - run: dotnet test"]
        self.assertEqual(ci_tests_checker._find_pattern_line(lines, combined), 2)
        # 未匹配时返回 0，调用方据此区分“没有命中”与“命中第一行”
        self.assertEqual(ci_tests_checker._find_pattern_line(["name: CI"], r"\bpytest\b"), 0)

    def test_create_workflow_match_defaults_are_independent(self):
        """测试默认参数不会在多次调用间共享可变对象"""
        first = ci_tests_checker.create_workflow_match(False, "a.yml", 0)
        second = ci_tests_checker.create_workflow_match(False, "b.yml", 0)

        self.assertEqual(first["ecosystems"], [])
        self.assertEqual(first["matches"], [])
        self.assertEqual(second["ecosystems"], [])

        first["ecosystems"].append("python")
        self.assertEqual(second["ecosystems"], [])

        detailed = ci_tests_checker.create_workflow_match(
            matched=True,
            file_path="ci.yml",
            line_number=3,
            ecosystems=["go"],
            matches=[{"ecosystem": "go", "line_number": 3}],
        )
        self.assertTrue(detailed["matched"])
        self.assertEqual(detailed["ecosystems"], ["go"])
        self.assertEqual(detailed["matches"][0]["ecosystem"], "go")

    def test_is_ci_test_workflow_detects_tests(self):
        """测试包含测试命令的工作流会被正向识别"""
        file_path = self._write_workflow(
            "ci.yml",
            "name: CI\non: [push]\njobs:\n  test:\n    steps:\n      - run: pytest -q\n"
        )

        result = ci_tests_checker.is_ci_test_workflow(file_path)

        self.assertTrue(result["matched"])
        self.assertEqual(result["file_path"], file_path)
        self.assertIn("python", result["ecosystems"])
        self.assertEqual(result["line_number"], 6)
        self.assertEqual(result["matches"][0]["ecosystem"], "python")

    def test_is_ci_test_workflow_negative(self):
        """测试只构建/发布的工作流不会被识别为测试"""
        file_path = self._write_workflow(
            "release.yml",
            "name: Release\njobs:\n  publish:\n    steps:\n      - run: npm run build\n"
        )

        result = ci_tests_checker.is_ci_test_workflow(file_path)

        self.assertFalse(result["matched"])
        self.assertEqual(result["ecosystems"], [])
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["line_number"], 0)

    def test_is_ci_test_workflow_empty_and_missing_files(self):
        """测试空文件与不存在的文件都返回未匹配且不抛异常"""
        empty_file = self._write_workflow("empty.yml", "   \n")
        empty_result = ci_tests_checker.is_ci_test_workflow(empty_file)
        self.assertFalse(empty_result["matched"])
        self.assertEqual(empty_result["ecosystems"], [])

        missing_file = os.path.join(self.workflows_dir, "missing.yml")
        missing_result = ci_tests_checker.is_ci_test_workflow(missing_file)
        self.assertFalse(missing_result["matched"])
        self.assertEqual(missing_result["file_path"], missing_file)

    @patch('openchecker.checkers.ci_tests_checker.list_workflow_files')
    @patch('openchecker.checkers.ci_tests_checker.platform_manager')
    def test_ci_tests_checker_aggregation(self, mock_platform, mock_list_files):
        """测试聚合结果：工作流总数、含测试数、总体标志与逐文件生态"""
        workflow_with_tests = self._write_workflow(
            "ci.yml",
            "name: CI\njobs:\n  test:\n    steps:\n      - run: go test ./...\n"
        )
        workflow_without_tests = self._write_workflow(
            "release.yml",
            "name: Release\njobs:\n  publish:\n    steps:\n      - run: docker push app:latest\n"
        )

        mock_platform.parse_project_url.return_value = ("owner", "repo")
        mock_list_files.return_value = [workflow_with_tests, workflow_without_tests]

        res_payload = {"scan_results": {}}

        ci_tests_checker.ci_tests_checker("https://github.com/owner/repo", res_payload)

        result = res_payload["scan_results"]["ci-tests-checker"]
        self.assertEqual(result["num_workflows"], 2)
        self.assertEqual(result["num_workflows_with_tests"], 1)
        self.assertTrue(result["has_ci_tests"])
        self.assertEqual(len(result["workflows"]), 2)

        by_path = {workflow["file_path"]: workflow for workflow in result["workflows"]}
        self.assertTrue(by_path[workflow_with_tests]["matched"])
        self.assertIn("go", by_path[workflow_with_tests]["ecosystems"])
        self.assertFalse(by_path[workflow_without_tests]["matched"])
        self.assertEqual(by_path[workflow_without_tests]["ecosystems"], [])

    @patch('openchecker.checkers.ci_tests_checker.list_workflow_files')
    @patch('openchecker.checkers.ci_tests_checker.platform_manager')
    def test_ci_tests_checker_without_tests(self, mock_platform, mock_list_files):
        """测试仓库没有任何测试工作流时 has_ci_tests 为 False"""
        workflow = self._write_workflow("docs.yml", "name: Docs\njobs:\n  build:\n    steps:\n      - run: make docs\n")

        mock_platform.parse_project_url.return_value = ("owner", "repo")
        mock_list_files.return_value = [workflow]

        res_payload = {"scan_results": {}}

        ci_tests_checker.ci_tests_checker("https://gitee.com/owner/repo", res_payload)

        result = res_payload["scan_results"]["ci-tests-checker"]
        self.assertEqual(result["num_workflows"], 1)
        self.assertEqual(result["num_workflows_with_tests"], 0)
        self.assertFalse(result["has_ci_tests"])

    @patch('openchecker.checkers.ci_tests_checker.platform_manager')
    def test_ci_tests_checker_error_path(self, mock_platform):
        """测试解析项目 URL 失败时写入 error 并归零计数器"""
        mock_platform.parse_project_url.side_effect = ValueError("invalid project url")

        res_payload = {"scan_results": {}}

        ci_tests_checker.ci_tests_checker("not-a-url", res_payload)

        result = res_payload["scan_results"]["ci-tests-checker"]
        self.assertIn("error", result)
        self.assertIn("invalid project url", result["error"])
        self.assertEqual(result["num_workflows"], 0)
        self.assertEqual(result["num_workflows_with_tests"], 0)
        self.assertFalse(result["has_ci_tests"])
        self.assertEqual(result["workflows"], [])


class TestCheckersIntegration(unittest.TestCase):
    """检查器集成测试类"""

    def setUp(self):
        """集成测试前置设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.temp_dir, "test_project")
        os.makedirs(self.project_path)

    def tearDown(self):
        """集成测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_multiple_checkers_workflow(self):
        """测试多检查器工作流"""
        # 创建测试项目结构
        workflows_dir = os.path.join(self.project_path, ".github", "workflows")
        os.makedirs(workflows_dir)
        
        # 创建安全工作流文件
        workflow_file = os.path.join(workflows_dir, "security.yml")
        with open(workflow_file, 'w') as f:
            f.write("""
            name: Security
            jobs:
              security:
                steps:
                  - uses: github/codeql-action/analyze@v1
            """)
        
        # 创建安全策略文件
        security_file = os.path.join(self.project_path, "SECURITY.md")
        with open(security_file, 'w') as f:
            f.write("# Security Policy")
        
        # 测试各种检查器的集成
        res_payload = {"scan_results": {}}
        
        # 这里可以集成测试多个检查器
        # 例如：安全策略检查 + SAST检查
        found_security_files = security_policy_checker.find_security_policy_files(self.project_path, "github")
        self.assertTrue(len(found_security_files) > 0)

    def test_checker_error_handling(self):
        """测试检查器错误处理"""
        res_payload = {"scan_results": {}}
        
        # 测试无效项目URL
        try:
            url_checker.url_checker("invalid://url", res_payload)
            # 应该正常处理错误，不抛出异常
            self.assertIn("url-checker", res_payload["scan_results"])
        except Exception as e:
            self.fail(f"检查器应该处理错误而不是抛出异常: {e}")


if __name__ == '__main__':
    # 设置测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestSASTChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestSecurityPolicyChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestTokenPermissionsChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestFuzzingChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestBinaryChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestURLChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestSonarChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestCheckersIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite) 