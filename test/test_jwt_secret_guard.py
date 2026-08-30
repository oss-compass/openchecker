#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker JWT Secret Guard Tests

config/config.ini 模板的 [JWT] secret_key 为公开占位值，且配置文档将其列为
默认值。若部署时未替换，任何人都能用已知密钥伪造合法 JWT 完全绕过认证。
本模块验证服务启动时对默认/空 secret 的 fail-fast 防护。

Author: OpenChecker Team
"""

import unittest

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'openchecker'))

from openchecker.main import ensure_secure_jwt_secret


class TestJwtSecretGuard(unittest.TestCase):
    """启动时 JWT secret 校验测试"""

    def test_known_default_secrets_refused(self):
        """已知默认/占位 secret 必须拒绝启动"""
        for secret in ("your_secret_key", "your_secure_secret_key_here",
                       "changeme", "secret", "Your_Secure_Secret_Key_Here"):
            with self.subTest(secret=secret):
                with self.assertRaises(SystemExit):
                    ensure_secure_jwt_secret(secret)

    def test_empty_or_blank_secret_refused(self):
        """空或空白 secret 必须拒绝启动"""
        for secret in ("", "   "):
            with self.subTest(secret=repr(secret)):
                with self.assertRaises(SystemExit):
                    ensure_secure_jwt_secret(secret)

    def test_strong_secret_accepted(self):
        """强随机 secret 正常启动"""
        ensure_secure_jwt_secret("9f8c1d2e-4b3a-4f5c-8d6e-7a2b1c0d9e8f7a6b5c4d3e2f1a0b")


if __name__ == '__main__':
    unittest.main()
