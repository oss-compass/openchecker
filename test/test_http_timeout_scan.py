#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenChecker HTTP Timeout Regression Tests

requests 调用不传 timeout 时可能无限挂起；agent 的消费线程池只有 1 个
worker，任何外呼挂起都会停止整个 agent 的消息处理。这与 Bandit B113
（requests call without timeout）的检查目标一致，本模块用 AST 扫描
openchecker/ 全部源码，固化"每个 requests 调用必须显式设置 timeout"的约束。

Author: OpenChecker Team
"""

import ast
import os
import unittest

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

OPENCHECKER_DIR = os.path.join(os.path.dirname(__file__), '..', 'openchecker')
HTTP_VERBS = {'get', 'post', 'request', 'put', 'delete', 'head', 'options', 'patch'}
# exponential_backoff.post_with_backoff 通过 kwargs.setdefault 注入默认 timeout，
# 由 test_request_timeouts.py 单独覆盖；此处的字面调用不含 timeout 关键字
TIMEOUT_INJECTED_VIA_KWARGS = {'exponential_backoff.py'}


def iter_requests_calls(tree):
    """yield (node, verb) for every requests.<verb>(...) call in the AST"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute)
                and func.attr in HTTP_VERBS
                and isinstance(func.value, ast.Name)
                and func.value.id == 'requests'):
            yield node, func.attr


class TestAllRequestsCallsHaveTimeout(unittest.TestCase):
    """AST 级回归测试：openchecker/ 下所有 requests 调用必须显式传 timeout"""

    def test_every_requests_call_has_timeout(self):
        violations = []
        for root, _, filenames in os.walk(OPENCHECKER_DIR):
            for filename in sorted(filenames):
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(root, filename)
                rel_path = os.path.relpath(path, OPENCHECKER_DIR)
                with open(path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read(), filename=rel_path)
                for node, verb in iter_requests_calls(tree):
                    if rel_path.replace(os.sep, '/') in TIMEOUT_INJECTED_VIA_KWARGS:
                        continue
                    has_timeout = any(kw.arg == 'timeout' for kw in node.keywords)
                    if not has_timeout:
                        violations.append(f"{rel_path}:{node.lineno} requests.{verb}(...) without timeout")
        self.assertEqual(violations, [],
                         "requests calls without explicit timeout (cf. Bandit B113):\n"
                         + "\n".join(violations))


if __name__ == '__main__':
    unittest.main()
