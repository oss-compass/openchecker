# -*- coding: utf-8 -*-
"""docker 镜像摘要钉版解析回归测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "openchecker"))

from checkers.pinned_dependencies_checker import (
    _parse_docker_image,
    _is_docker_image_pinned,
)


DIGEST = "sha256:" + "a" * 64


class TestParseDockerImage(unittest.TestCase):
    def test_digest_pinned_image_is_recognized(self):
        """FROM ubuntu@sha256:<64hex> 同时含 : 与 @——原实现先查 :，把引用拆成
        ("ubuntu@sha256", "<64hex>")，损坏的名称被记录且摘要钉版镜像被误判
        未钉版（pinned-dependencies 检查恰恰用来奖励摘要钉版这一最佳实践）。
        摘要引用必须优先于 tag 解析。"""
        name, version = _parse_docker_image("ubuntu@" + DIGEST)
        self.assertEqual(name, "ubuntu")
        self.assertEqual(version, DIGEST)
        self.assertTrue(_is_docker_image_pinned(version))

    def test_tag_ref_still_parses(self):
        name, version = _parse_docker_image("ubuntu:22.04")
        self.assertEqual(name, "ubuntu")
        self.assertEqual(version, "22.04")

    def test_registry_port_ref_still_parses(self):
        """带注册表端口的 tag 引用（myreg:5000/img:latest）仍按最后一个冒号拆。"""
        name, version = _parse_docker_image("myreg:5000/img:latest")
        self.assertEqual(name, "myreg:5000/img")
        self.assertEqual(version, "latest")

    def test_bare_name_defaults_to_latest(self):
        name, version = _parse_docker_image("ubuntu")
        self.assertEqual(name, "ubuntu")
        self.assertEqual(version, "latest")


if __name__ == "__main__":
    unittest.main()
