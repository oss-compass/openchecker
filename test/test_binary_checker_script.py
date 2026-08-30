#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Binary Checker Script Tests

scripts/binary_checker.sh 的归档检测此前在主循环中误用 $1（脚本位置参数，即
仓库 URL）作为 file --mime-type 的输入，导致任何压缩包都走不到
check_compressed_binary 分支，"Binary archive found" 永远不会输出。

本模块通过构造本地 git 仓库端到端验证脚本的检测行为。

Author: OpenChecker Team
"""

import unittest
import os
import subprocess
import tempfile
import zipfile
import shutil

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'binary_checker.sh')

ELF_LIKE_CONTENT = b'\x7fELF' + b'\x00' * 32 + b'binary payload'


class TestBinaryCheckerScript(unittest.TestCase):
    """binary_checker.sh 集成测试（依赖 git 与 file 命令）"""

    @classmethod
    def setUpClass(cls):
        if not (shutil.which('git') and shutil.which('file')):
            raise unittest.SkipTest("git and file commands are required")

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix='openchecker_binary_test_')
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)

        repo_dir = os.path.join(self.workdir, 'src')
        os.makedirs(repo_dir)
        with zipfile.ZipFile(os.path.join(repo_dir, 'app-bundle.zip'), 'w') as archive:
            archive.writestr('lib/app.so', ELF_LIKE_CONTENT)
        with open(os.path.join(repo_dir, 'libtest.so'), 'wb') as f:
            f.write(ELF_LIKE_CONTENT)
        with open(os.path.join(repo_dir, 'readme.txt'), 'w') as f:
            f.write('plain text file')

        subprocess.run(['git', 'init', '-q'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'add', '-A'], cwd=repo_dir, check=True)
        subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',
                        'commit', '-qm', 'init'], cwd=repo_dir, check=True)

        result = subprocess.run(
            ['bash', SCRIPT_PATH, 'file://' + repo_dir],
            cwd=self.workdir, capture_output=True, text=True, timeout=120
        )
        self.result = result

    def assert_reported(self, kind, filename):
        """断言输出中存在 'kind: <path>/filename' 形式的报告行"""
        reported = [line for line in self.result.stdout.splitlines()
                    if line.startswith(f'{kind}: ') and line.rstrip().endswith(f'/{filename}')]
        self.assertTrue(reported, f'{kind} for {filename} not found in: {self.result.stdout!r}')

    def test_binary_archive_detected(self):
        """压缩包内含二进制文件时应输出 Binary archive found（修复前永远不会）"""
        self.assert_reported('Binary archive found', 'app-bundle.zip')

    def test_plain_binary_detected(self):
        """裸二进制文件应输出 Binary file found"""
        self.assert_reported('Binary file found', 'libtest.so')

    def test_text_files_ignored(self):
        """普通文本文件不应出现在结果中"""
        self.assertNotIn('readme.txt', self.result.stdout)

    def test_no_local_outside_function_error(self):
        """不应再有 local: can only be used in a function 的错误输出"""
        self.assertNotIn('local:', self.result.stderr)


if __name__ == '__main__':
    unittest.main()
