"""The release checker needs every page, not only the newest releases."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "openchecker"))
import helper

CONFIG = {name: {"access_key": "test-token"}
          for name in ("Github", "Gitee", "GitCode")}
spec = importlib.util.spec_from_file_location(
    "pagination_test_adapter", ROOT / "openchecker" / "platform_adapter.py")
adapter_module = importlib.util.module_from_spec(spec)
with patch.object(helper, "read_config", return_value=CONFIG):
    spec.loader.exec_module(adapter_module)


def response(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


class GiteeReleasePaginationTest(unittest.TestCase):
    def setUp(self):
        self.adapter = adapter_module.GiteeAdapter(CONFIG)
        self.url = "https://gitee.com/owner/repo"
        self.first_page = [{"id": n, "tag_name": f"v{n}"} for n in range(100)]

    def test_collects_releases_after_the_first_full_page(self):
        older_release = {"id": 100, "tag_name": "v100"}
        with patch.object(adapter_module.requests, "get", side_effect=[
            response(self.first_page), response([older_release])
        ]) as get:
            releases, error = self.adapter.get_releases(self.url)
        self.assertIsNone(error)
        self.assertEqual(releases, self.first_page + [older_release])
        self.assertEqual([call.kwargs["params"]["page"] for call in get.call_args_list], [1, 2])
        self.assertTrue(all(call.kwargs["params"]["per_page"] == 100 for call in get.call_args_list))

    def test_empty_repository_stops_after_one_request(self):
        with patch.object(adapter_module.requests, "get", return_value=response([])) as get:
            self.assertEqual(self.adapter.get_releases(self.url), ([], None))
        get.assert_called_once()

    def test_exact_page_boundary_stops_at_empty_page(self):
        with patch.object(adapter_module.requests, "get", side_effect=[
            response(self.first_page), response([])
        ]) as get:
            self.assertEqual(self.adapter.get_releases(self.url), (self.first_page, None))
        self.assertEqual(get.call_count, 2)

    def test_later_http_error_does_not_report_partial_success(self):
        with patch.object(adapter_module.requests, "get", side_effect=[
            response(self.first_page), response({}, 503)
        ]):
            releases, error = self.adapter.get_releases(self.url)
        self.assertEqual(releases, [])
        self.assertTrue(error)

    def test_later_invalid_json_does_not_report_partial_success(self):
        invalid = Mock(status_code=200, json=Mock(side_effect=ValueError("invalid JSON")))
        with patch.object(adapter_module.requests, "get", side_effect=[response(self.first_page), invalid]):
            releases, error = self.adapter.get_releases(self.url)
        self.assertEqual(releases, [])
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
