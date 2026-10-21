# -*- coding: utf-8 -*-
"""security_policy_checker 正则回归测试。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "openchecker"))

from checkers.security_policy_checker import analyze_security_policy_content


POLICY = """# Security Policy

## Reporting a Vulnerability

Please report vulnerabilities to security@example.com.
We aim to respond within 90 days. See https://example.com/security.
"""


class TestAnalyzeSecurityPolicyContent(unittest.TestCase):
    def test_policy_file_is_analyzed_without_regex_crash(self):
        """disclosure_pattern 曾写作 \b*（nothing to repeat）：re.findall 对任何
        非空政策文件抛 re.error，security-policy 检测对每个有政策的仓库都
        只返回 {"error": "nothing to repeat at position 7"}——恰好是该检测
        存在的意义所在的那些仓库。"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(POLICY)
            path = f.name
        try:
            result = analyze_security_policy_content(path)
        finally:
            os.unlink(path)
        self.assertIn("security@example.com", result["emails"])
        self.assertTrue(len(result["urls"]) > 0)
        self.assertIsInstance(result["disclosure_keywords"], list)


if __name__ == "__main__":
    unittest.main()
