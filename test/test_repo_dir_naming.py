#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Repository Directory Naming Tests

此前仓库目录名仅由 URL basename 派生，github.com/o1/foo 与 gitee.com/o2/foo
共用 repos/foo：download-checkout 发现目录已存在会跳过 clone，直接在 o1 的
代码上执行 o2 的扫描并出报告。本模块验证统一的 owner__repo 目录名派生，以及
shell 模板与各 checker 派生结果的一致性。

Author: OpenChecker Team
"""

import unittest
import os
import subprocess
import tempfile
import shutil
import re

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'openchecker'))

from common import get_project_dir_name
from constans import shell_script_handlers

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'binary_checker.sh')


class TestProjectDirName(unittest.TestCase):
    """get_project_dir_name 单元测试"""

    def test_same_basename_different_owners_do_not_collide(self):
        """不同 owner/平台的同名仓库必须派生出不同目录名"""
        self.assertNotEqual(
            get_project_dir_name("https://github.com/o1/foo"),
            get_project_dir_name("https://gitee.com/o2/foo")
        )
        self.assertEqual(get_project_dir_name("https://github.com/o1/foo"), "github__o1__foo")
        self.assertEqual(get_project_dir_name("https://gitee.com/o2/foo"), "gitee__o2__foo")

    def test_git_suffix_stripped(self):
        self.assertEqual(get_project_dir_name("https://github.com/owner/repo.git"),
                         "github__owner__repo")

    def test_repo_names_containing_git_preserved(self):
        """仓库名本身含 .git 的（如 .github）不应被破坏"""
        self.assertEqual(get_project_dir_name("https://github.com/owner/.github"),
                         "github__owner__.github")

    def test_same_repo_on_different_platforms_do_not_collide(self):
        """不同平台的同名仓库（owner 也可能相同）派生出不同目录名"""
        self.assertEqual(get_project_dir_name("https://github.com/mirrors/linux"),
                         "github__mirrors__linux")
        self.assertEqual(get_project_dir_name("https://gitee.com/mirrors/linux"),
                         "gitee__mirrors__linux")
        self.assertNotEqual(
            get_project_dir_name("https://github.com/mirrors/linux"),
            get_project_dir_name("https://gitee.com/mirrors/linux")
        )


class TestShellTemplateConsistency(unittest.TestCase):
    """shell 模板与 Python 侧目录名一致性测试"""

    def extract_shell_project_name(self, script):
        match = re.search(r'project_name="([^"]+)"', script)
        self.assertIsNotNone(match, f"project_name not embedded in script: {script[:200]!r}")
        return match.group(1)

    def test_download_checkout_uses_derived_name(self):
        """download-checkout 模板嵌入的目录名必须与 get_project_dir_name 一致"""
        for url in ("https://github.com/o1/foo.git",
                    "https://gitee.com/owner/repo",
                    "https://gitcode.com/org/.github"):
            with self.subTest(url=url):
                script = shell_script_handlers["download-checkout"].format(
                    project_url=url,
                    project_dir_name=get_project_dir_name(url),
                    version_number="None")
                self.assertEqual(self.extract_shell_project_name(script),
                                 get_project_dir_name(url))

    def test_all_shell_templates_use_derived_name(self):
        """所有基于 BASE_SCRIPT 的模板都不再用 basename 派生目录名"""
        for name, script in shell_script_handlers.items():
            with self.subTest(script=name):
                rendered = script.format(
                    project_url="https://github.com/owner/repo",
                    project_dir_name="github__owner__repo",
                    version_number="None",
                    sonar_host="https://sonar.example.com", sonar_port="9000",
                    sonar_token="t", sonar_project_name="p", scan_timeout_s="1")
                self.assertNotIn("$(basename", rendered)
                self.assertIn('project_name="github__owner__repo"', rendered)
                self.assertIn('"$project_name"', rendered)


class TestCollisionPrevention(unittest.TestCase):
    """碰撞场景端到端测试：o1 的目录已存在时，o2 同名仓库必须 clone 到独立目录"""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("git"):
            raise unittest.SkipTest("git command is required")

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="openchecker_collision_")
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)
        # 构造两个不同 owner 的同名仓库
        for owner, marker in (("o1", "from-o1"), ("o2", "from-o2")):
            repo_dir = os.path.join(self.workdir, f"repo_{owner}")
            os.makedirs(repo_dir)
            with open(os.path.join(repo_dir, f"marker_{owner}.txt"), "w") as f:
                f.write(marker)
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
            subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                            "commit", "-qm", "init"], cwd=repo_dir, check=True)
        # 模拟 o1 的扫描已把代码留在 repos/ 下（沿用旧布局的目录名 foo）
        subprocess.run(["git", "clone", "-q",
                        "file://" + os.path.join(self.workdir, "repo_o1"),
                        os.path.join(self.workdir, "repos", "foo")], check=True)

    def test_second_same_name_repo_gets_own_directory(self):
        repos_dir = os.path.join(self.workdir, "repos")
        script = shell_script_handlers["download-checkout"].format(
            project_url="file://" + os.path.join(self.workdir, "repo_o2"),
            project_dir_name="gitee__o2__foo",
            version_number="None")

        result = subprocess.run(["/bin/bash", "-c", script],
                                cwd=repos_dir, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

        # o2 的代码必须落在自己的目录里，且内容来自 o2
        o2_marker = os.path.join(repos_dir, "gitee__o2__foo", "marker_o2.txt")
        self.assertTrue(os.path.isfile(o2_marker), "o2 repo was not cloned")
        with open(o2_marker) as f:
            self.assertEqual(f.read(), "from-o2")
        # o1 的旧目录不被复用也不被破坏
        with open(os.path.join(repos_dir, "foo", "marker_o1.txt")) as f:
            self.assertEqual(f.read(), "from-o1")


class TestBinaryCheckerScriptDirArg(unittest.TestCase):
    """binary_checker.sh 使用第二参数（派生目录名）并与 Python 侧一致"""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("git"):
            raise unittest.SkipTest("git command is required")

    def test_explicit_dir_name_is_used(self):
        workdir = tempfile.mkdtemp(prefix="openchecker_binc_")
        self.addCleanup(shutil.rmtree, workdir, ignore_errors=True)
        repo_dir = os.path.join(workdir, "repo_src")
        os.makedirs(repo_dir)
        with open(os.path.join(repo_dir, "lib.so"), "wb") as f:
            f.write(b"\x7fELF-binary")
        subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "init"], cwd=repo_dir, check=True)

        url = "https://github.com/owner/repo"
        result = subprocess.run(
            ["bash", SCRIPT_PATH, "file://" + repo_dir, get_project_dir_name(url)],
            cwd=workdir, capture_output=True, text=True, timeout=60)

        # clone 到 github__owner__repo 目录，而不是源目录 repo_src
        self.assertTrue(os.path.isdir(os.path.join(workdir, "github__owner__repo")))
        self.assertIn("Binary file found: github__owner__repo/lib.so", result.stdout)


if __name__ == '__main__':
    unittest.main()
