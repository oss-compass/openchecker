"""Platform download failures must not become successful zero-download scans."""

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
from platform_adapter import PlatformManager


def response(status, data=None):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


class PlatformDownloadErrorsTest(unittest.TestCase):
    def setUp(self):
        self.manager_patch = patch.object(
            checker, "platform_manager", PlatformManager(CONFIG))
        self.manager_patch.start()
        self.addCleanup(self.manager_patch.stop)
        self.metadata = {"description": "demo", "homepage": "https://example.org"}
        self.url = "https://gitcode.com/example/demo"

    def run_checker(self, download_response):
        replies = [response(404), response(200, self.metadata), download_response]
        payload = {"scan_results": {}}
        with patch.object(checker.requests, "get", side_effect=replies):
            checker.package_info_checker(self.url, payload)
        return payload["scan_results"]["package-info"]

    def test_failed_download_request_is_reported_as_scan_error(self):
        for status in (403, 404, 500):
            with self.subTest(status=status):
                result = self.run_checker(response(status))
                self.assertIn("error", result)
                self.assertNotIn("down_count", result)

    def test_download_connection_error_is_reported(self):
        result = self.run_checker(checker.requests.ConnectionError("offline"))
        self.assertEqual(result, {"error": "offline"})

    def test_successful_downloads_are_preserved(self):
        result = self.run_checker(response(200, {"download_statistics_detail": [
            {"pdate": "2026-10-02", "today_dl_cnt": 3},
            {"pdate": "2026-10-01", "today_dl_cnt": 4},
        ]}))
        self.assertEqual(result, {
            "description": "demo", "home_url": "https://example.org",
            "dependent_count": False, "down_count": 7,
            "day_enter": "2026-10-01 - 2026-10-02",
        })

    def test_successful_empty_downloads_still_count_zero(self):
        result = self.run_checker(response(200, {"download_statistics_detail": []}))
        self.assertNotIn("error", result)
        self.assertEqual(result["down_count"], 0)

    def test_platforms_without_download_statistics_keep_existing_result(self):
        for host in ("github.com", "gitee.com"):
            with self.subTest(host=host):
                with patch.object(checker.requests, "get", side_effect=[
                        response(404), response(200, self.metadata)]):
                    result, error = checker.get_package_info(f"https://{host}/example/demo")
                self.assertIsNone(error)
                self.assertEqual(result["down_count"], 0)

    def test_repository_error_takes_precedence(self):
        with patch.object(checker.requests, "get", side_effect=[
                response(404), response(404), response(403)]):
            result, error = checker.get_package_info(self.url)
        self.assertEqual(error, "Repository not found")
        self.assertIs(result["down_count"], False)


if __name__ == "__main__":
    unittest.main()
