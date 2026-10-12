"""Dependency counts must describe npm's latest release, not JSON key order."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))
import helper

CONFIG = {name: {"access_key": "test-token"}
          for name in ("Github", "Gitee", "GitCode")}
with patch.object(helper, "read_config", return_value=CONFIG):
    from checkers import standard_command_checker as checker


class NpmLatestDependenciesTest(unittest.TestCase):
    def package_info(self, metadata):
        registry = Mock(status_code=200)
        registry.json.return_value = metadata
        downloads = Mock(status_code=200)
        downloads.json.return_value = {
            "downloads": [{"day": "2026-10-01", "downloads": 7}]}
        with patch.object(checker.requests, "get", side_effect=[registry, downloads]), \
                patch.object(checker.platform_manager, "get_repo_info",
                             return_value=({"description": "demo", "homepage": ""}, None)):
            return checker.get_package_info("https://github.com/example/demo")

    def test_latest_tag_wins_over_last_published_prerelease(self):
        versions = {
            "1.0.0": {"dependencies": {"a": "1", "b": "2"}},
            "2.0.0-beta.1": {"dependencies": {"a": "2"}},
        }
        result, error = self.package_info({
            "dist-tags": {"latest": "1.0.0", "next": "2.0.0-beta.1"},
            "versions": versions,
        })
        self.assertIsNone(error)
        self.assertEqual(result["dependent_count"], 2)
        self.assertEqual(result["down_count"], 7)

    def test_version_object_order_does_not_change_count(self):
        versions = [("1.0.0", {"dependencies": {"a": "1"}}),
                    ("2.0.0", {"dependencies": {"a": "2", "b": "1"}})]
        for entries in (versions, list(reversed(versions))):
            with self.subTest(order=[v[0] for v in entries]):
                result, error = self.package_info({
                    "dist-tags": {"latest": "2.0.0"}, "versions": dict(entries)})
                self.assertIsNone(error)
                self.assertEqual(result["dependent_count"], 2)

    def test_latest_release_without_dependencies_counts_zero(self):
        result, error = self.package_info({
            "dist-tags": {"latest": "2.0.0"},
            "versions": {"2.0.0": {}, "1.0.0": {"dependencies": {"old": "1"}}},
        })
        self.assertIsNone(error)
        self.assertEqual(result["dependent_count"], 0)

    def test_unresolvable_latest_is_an_error(self):
        for tags in ({}, {"latest": "9.0.0"}):
            with self.subTest(tags=tags):
                result, error = self.package_info({
                    "dist-tags": tags,
                    "versions": {"1.0.0": {"dependencies": {"a": "1"}}},
                })
                self.assertIsNotNone(error)
                self.assertIn("latest", error.lower())


if __name__ == "__main__":
    unittest.main()
