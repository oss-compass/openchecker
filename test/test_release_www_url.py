"""Actual release checker + adapters + ZIP parser; only HTTP is simulated.

Requires Main's existing requests package; never installs dependencies.
The unused GitHub SDK and logging import are isolated, not the URL/checker code.
"""
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import requests


def load_modules(source_root):
    root = Path(source_root) / "openchecker"
    logger = types.ModuleType("logger")
    logger.get_logger = logging.getLogger
    ghapi = types.ModuleType("ghapi")
    ghapi.__path__ = []
    ghapi_all = types.ModuleType("ghapi.all")

    def unused_github_sdk(*args, **kwargs):
        raise AssertionError("GitHub SDK must not run in the Gitee/GitCode regressions")

    ghapi_all.GhApi = unused_github_sdk
    ghapi_all.paged = unused_github_sdk
    isolated = {"logger": logger, "ghapi": ghapi, "ghapi.all": ghapi_all}

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    # Existing helper, real ConfigParser, adapter classes and manager all execute.
    with patch.dict(sys.modules, isolated):
        load("helper", root / "helper.py")
        adapter = load("platform_adapter", root / "platform_adapter.py")
        checker = load("_release_www_regression", root / "checkers/release_checker.py")
    return checker, adapter


def response(status=200, body=b"", payload=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode("utf-8") if payload is not None else body
    result.encoding = "utf-8"
    return result


class ReleaseWWWURLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get("OPEN_SOURCE_ROOT", str(Path(__file__).resolve().parents[1]))
        cls.fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        fixture_root = Path(cls.fixture.name)
        for relative in ("openchecker/helper.py", "openchecker/platform_adapter.py",
                         "openchecker/checkers/release_checker.py"):
            destination = fixture_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(root) / relative, destination)
        (fixture_root / "config").mkdir()
        (fixture_root / "config/config.ini").write_text(
            "[Github]\naccess_key=offline-token\n[Gitee]\naccess_key=offline-token\n"
            "[GitCode]\naccess_key=offline-token\n", encoding="utf-8")
        cls.checker, cls.adapter = load_modules(fixture_root)

    def setUp(self):
        data = io.BytesIO()
        with zipfile_context(data) as archive:
            archive.writestr("demo/changelog", "release changes")
            archive.writestr("demo/CHANGELOG.md", "existing notes extension policy is unchanged")
            archive.writestr("demo/manifest.spdx.yml", "excluded existing SBOM bug")
        self.archive_bytes = data.getvalue()
        self.releases = [{"tag_name": "v1.0.0", "name": "version one",
                          "draft": False, "prerelease": False, "assets": []}]
        self.calls = []

    def http_boundary(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "/releases" in url:
            return response(payload=self.releases)
        if url.endswith("/v1.0.0.zip"):
            self.assertEqual(kwargs.get("timeout"), 30)
            return response(body=self.archive_bytes)
        raise AssertionError("Unexpected HTTP endpoint: " + url)

    def assert_scan(self, url):
        # Prove this is already accepted by the COMPLETE existing adapter.
        self.assertEqual(self.adapter.platform_manager.parse_project_url(url), ("owner", "demo"))
        with patch.object(requests, "get", side_effect=self.http_boundary):
            result, error = self.checker.check_release_contents(url, "notes")
        self.assertIsNone(error)
        self.assertTrue(result["is_released"])
        self.assertEqual(result["release_contents"], [{
            "tag": "v1.0.0", "release_name": "version one", "has_content": True,
            "content_files": ["demo/changelog"], "error": None,
        }])
        self.assertEqual(len(self.calls), 2)
        self.assertIn("/owner/demo/releases", self.calls[0][0])
        self.assertNotIn("www.", self.calls[0][0])
        self.assertTrue(self.calls[1][0].endswith("/v1.0.0.zip"))

    def test_supported_www_urls_reach_actual_release_and_zip_path(self):
        for host in ("gitee.com", "gitcode.com"):
            for suffix in ("", ".git"):
                with self.subTest(host=host, suffix=suffix):
                    self.calls.clear()
                    self.assert_scan(f"https://www.{host}/owner/demo{suffix}")

    def test_existing_non_www_urls_are_unchanged(self):
        for host in ("gitee.com", "gitcode.com"):
            with self.subTest(host=host):
                self.calls.clear()
                self.assert_scan(f"https://{host}/owner/demo.git")

    def test_www_keeps_existing_draft_and_prerelease_filter(self):
        self.releases = [dict(self.releases[0], draft=True),
                         dict(self.releases[0], prerelease=True)]
        with patch.object(requests, "get", side_effect=self.http_boundary):
            result, error = self.checker.check_release_contents("https://www.gitee.com/owner/demo", "notes")
        self.assertIsNone(error)
        self.assertEqual(result, {"is_released": False, "release_contents": []})
        self.assertEqual(len(self.calls), 1)

    def test_www_keeps_archive_http_failure_in_result(self):
        def http_failure(url, **kwargs):
            return response(payload=self.releases) if "/releases" in url else response(status=404)
        with patch.object(requests, "get", side_effect=http_failure):
            result, error = self.checker.check_release_contents("https://www.gitee.com/owner/demo.git", "notes")
        self.assertIsNone(error)
        entry = result["release_contents"][0]
        self.assertFalse(entry["has_content"])
        self.assertEqual(entry["error"], "Failed to download release zip: 404")

    def test_unsupported_platform_or_content_type_does_not_request_http(self):
        for url, kind in (("https://unsupported.example/owner/demo", "notes"),
                          ("https://www.gitee.com/owner/demo", "unknown")):
            with self.subTest(url=url, kind=kind):
                with patch.object(requests, "get", side_effect=AssertionError("HTTP not expected")) as get:
                    result, error = self.checker.check_release_contents(url, kind)
                get.assert_not_called()
                self.assertIsNotNone(error)
                self.assertFalse(result["is_released"])


def zipfile_context(buffer):
    # Real stdlib ZIP creation, never a fake archive parser.
    import zipfile
    return zipfile.ZipFile(buffer, "w")


if __name__ == "__main__":
    unittest.main()
