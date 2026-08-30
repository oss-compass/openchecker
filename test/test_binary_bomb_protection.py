#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker Binary Checker Decompression Bomb Protection Tests

binary_checker.sh 处理被扫描仓库（不可信来源）中的压缩文件，此前解压时无任何
大小限制：<1MB 的 gz 可解压出 GB 级内容写满磁盘，而 repos_dir 位于 NFS 共享
存储，会造成平台级 DoS。本模块验证解压落盘被限制在安全上限内，且正常压缩包
的检测不受影响。

Author: OpenChecker Team
"""

import unittest
import os
import subprocess
import tempfile
import gzip
import io
import tarfile
import threading
import time
import zipfile
import shutil

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'binary_checker.sh')

ELF_LIKE_CONTENT = b'\x7fELF' + b'\x00' * 32 + b'binary payload'
# 留出余量：限额 256MB，断言解压期间的峰值落盘增量不超过该值加上脚本自身开销
EXPECTED_MAX_DELTA_BYTES = 400 * 1024 * 1024


def disk_avail_bytes(path):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


class TestBinaryCheckerBombProtection(unittest.TestCase):
    """解压炸弹防护集成测试（依赖 git/file/gzip 命令）"""

    @classmethod
    def setUpClass(cls):
        for tool in ('git', 'file', 'gzip'):
            if not shutil.which(tool):
                raise unittest.SkipTest(f"{tool} command is required")

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix='openchecker_bomb_test_')
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)

    def run_script_with_disk_sampling(self, repo_dir):
        """
        运行脚本并采样其执行期间的磁盘可用量。

        脚本在结束时删除解压临时目录，事后测量无法发现瞬时写满磁盘的行为
        （这正是解压炸弹的攻击窗口：解压期间同盘的其它写入全部失败），
        因此在脚本运行期间持续采样并取可用量最低点。
        """
        avail_before = disk_avail_bytes(self.workdir)
        stop = threading.Event()
        min_avail = [avail_before]

        def sample():
            while not stop.is_set():
                min_avail[0] = min(min_avail[0], disk_avail_bytes(self.workdir))
                time.sleep(0.05)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        try:
            result = subprocess.run(
                ['bash', SCRIPT_PATH, 'file://' + repo_dir],
                cwd=self.workdir, capture_output=True, text=True, timeout=180
            )
        finally:
            stop.set()
            sampler.join(timeout=1)
        peak_delta = avail_before - min_avail[0]
        return result, peak_delta

    def make_repo(self, extra_files):
        repo_dir = os.path.join(self.workdir, 'src')
        os.makedirs(repo_dir)
        for name, writer in extra_files.items():
            writer(os.path.join(repo_dir, name))
        subprocess.run(['git', 'init', '-q'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'add', '-A'], cwd=repo_dir, check=True)
        subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',
                        'commit', '-qm', 'init'], cwd=repo_dir, check=True)
        return repo_dir

    @staticmethod
    def write_gzip_bomb(path, expanded_bytes):
        raw = b'\x00' * expanded_bytes
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=1) as f:
            f.write(raw)
        with open(path, 'wb') as f:
            f.write(buf.getvalue())
        return buf.tell()

    def test_gzip_bomb_disk_usage_capped(self):
        """<5MB 的 gz 解压出 1GB 时，解压期间的峰值落盘必须被限制在安全上限内"""
        repo_dir = self.make_repo({'bomb.gz': lambda p: self.write_gzip_bomb(p, 1024 * 1024 * 1024)})

        result, peak_delta = self.run_script_with_disk_sampling(repo_dir)

        self.assertLess(peak_delta, EXPECTED_MAX_DELTA_BYTES,
                        f"unbounded decompression: peak {peak_delta // (1024*1024)}MB written to disk")
        # 被截断的内容应走既有的内层类型检查路径被优雅跳过，而不是崩溃
        # 或误报为 Binary archive found
        self.assertIn('Unsupported inner file type of gzip', result.stdout)
        self.assertNotIn('Binary archive found', result.stdout)

    def test_oversized_zip_disk_usage_capped(self):
        """单个成员展开超过限额的 zip 不得在解压期间写满磁盘"""
        def write_zip(path):
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('huge.bin', b'\x00' * (1024 * 1024 * 1024))

        repo_dir = self.make_repo({'bomb.zip': write_zip})

        result, peak_delta = self.run_script_with_disk_sampling(repo_dir)

        self.assertLess(peak_delta, EXPECTED_MAX_DELTA_BYTES,
                        f"unbounded decompression: peak {peak_delta // (1024*1024)}MB written to disk")

    def test_entry_count_bomb_skipped(self):
        """海量小条目的 zip（不触发单文件大小限制）应因条目数超限被跳过"""
        def write_many_entries_zip(path):
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for i in range(20001):
                    archive.writestr(f'dir{i % 100}/file_{i}.txt', b'x')

        repo_dir = self.make_repo({'many.zip': write_many_entries_zip})

        result, _ = self.run_script_with_disk_sampling(repo_dir)

        self.assertIn('entry count exceeds limit', result.stdout)
        self.assertNotIn('many.zip', [line.split(': ', 1)[1] for line in
                                      result.stdout.splitlines()
                                      if line.startswith('Binary archive found: ')])

    def test_normal_many_file_archive_still_extracted(self):
        """条目数在限额内的多文件压缩包不受影响（含二进制仍被识别）"""
        def write_zip(path):
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for i in range(100):
                    archive.writestr(f'dir{i}/file_{i}.txt', b'plain text')
                archive.writestr('lib/app.so', ELF_LIKE_CONTENT)

        repo_dir = self.make_repo({'many_small.zip': write_zip})

        result, _ = self.run_script_with_disk_sampling(repo_dir)

        reported = [line for line in result.stdout.splitlines()
                    if line.startswith('Binary archive found: ')
                    and line.rstrip().endswith('/many_small.zip')]
        self.assertTrue(reported,
                        f"normal multi-entry zip not detected: {result.stdout!r}")

    def test_normal_tar_gz_archive_still_detected(self):
        """限额不应破坏正常路径：tar.gz 内含二进制文件仍应被识别"""
        def write_tar_gz(path):
            tar_buf = io.BytesIO()
            with tarfile.open(fileobj=tar_buf, mode='w') as archive:
                info = tarfile.TarInfo('lib/app.so')
                info.size = len(ELF_LIKE_CONTENT)
                archive.addfile(info, io.BytesIO(ELF_LIKE_CONTENT))
            tar_buf.seek(0)
            with gzip.open(path, 'wb') as f:
                f.write(tar_buf.read())

        repo_dir = self.make_repo({'release.tar.gz': write_tar_gz})

        result, _ = self.run_script_with_disk_sampling(repo_dir)

        reported = [line for line in result.stdout.splitlines()
                    if line.startswith('Binary archive found: ')
                    and line.rstrip().endswith('/release.tar.gz')]
        self.assertTrue(reported,
                        f"normal tar.gz not detected after hardening: {result.stdout!r}")


if __name__ == '__main__':
    unittest.main()
