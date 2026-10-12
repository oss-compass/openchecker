"""Archive URLs must preserve valid Git tag names on the HTTP wire."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "openchecker"))
import helper

CONFIG = {name: {"access_key": "test-token"}
          for name in ("Github", "Gitee", "GitCode")}
spec = importlib.util.spec_from_file_location(
    "archive_test_adapter", ROOT / "openchecker" / "platform_adapter.py")
adapter_module = importlib.util.module_from_spec(spec)
with patch.object(helper, "read_config", return_value=CONFIG):
    spec.loader.exec_module(adapter_module)


class ArchiveTagEncodingTest(unittest.TestCase):
    def test_tag_survives_request_preparation(self):
        for adapter_class, host in (
            (adapter_module.GitHubAdapter, "github.com"),
            (adapter_module.GiteeAdapter, "gitee.com"),
            (adapter_module.GitCodeAdapter, "gitcode.com"),
        ):
            for tag in ("v1.0.0", "release/v1.0", "v1#fix", "v1%2Ffix", "版本1"):
                with self.subTest(platform=host, tag=tag):
                    url = adapter_class(CONFIG).get_zipball_url(
                        f"https://{host}/owner/repo", tag)
                    prepared = requests.Request("GET", url).prepare()
                    # path_url is the target requests actually sends to the server;
                    # fragments never reach the archive endpoint.
                    wire_path = urlsplit(prepared.path_url).path
                    self.assertTrue(unquote(wire_path).endswith(f"/{tag}.zip"),
                                    prepared.path_url)
                    self.assertEqual(urlsplit(prepared.url).fragment, "")
                    self.assertEqual(urlsplit(prepared.url).query, "")


if __name__ == "__main__":
    unittest.main()
