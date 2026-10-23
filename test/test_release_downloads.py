"""Release scans against a counting loopback HTTP server, without hosted APIs."""

from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import re
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

import requests
from checkers import release_checker


def archive_bytes(size=0):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("project/CHANGELOG", "Release notes")
        archive.writestr("project/bom.spdx.json", "{}")
        archive.writestr("project/data.bin", b"x" * size)
    return buffer.getvalue()


class ReleaseHTTPFixture:
    """Only replace the platform adapter; HTTP and ZIP parsing stay real."""

    def __init__(self, releases, archives, delay=0):
        self.releases = releases
        self.archives = archives
        self.delay = delay
        self.requests = Counter()
        self.bytes_sent = Counter()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.requests[self.path] += 1
                if fixture.delay:
                    time.sleep(fixture.delay)
                if self.path == "/releases":
                    status, body = 200, json.dumps(fixture.releases).encode("utf-8")
                else:
                    response = fixture.archives.get(self.path, (404, b"not found"))
                    if isinstance(response, list):
                        response = response[min(fixture.requests[self.path] - 1, len(response) - 1)]
                    status, body = response
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                fixture.bytes_sent[self.path] += len(body)
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:{}".format(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.adapter_patch = patch.dict(
            release_checker.platform_manager.adapters, {"github": self}
        )
        self.adapter_patch.start()
        return self

    def __exit__(self, *args):
        self.adapter_patch.stop()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def get_releases(self, project_url):
        response = requests.get(self.url + "/releases", timeout=5)
        return response.json(), None

    def get_zipball_url(self, project_url, tag):
        return self.url + "/" + tag + ".zip"

    def reset_counts(self):
        self.requests.clear()
        self.bytes_sent.clear()


class TestReleaseDownloads(unittest.TestCase):
    project_url = "https://github.com/example/project"

    def scan(self):
        payload = {"scan_results": {"other-checker": {"unchanged": True}}}
        release_checker.release_checker(self.project_url, payload)
        self.assertEqual(payload["scan_results"]["other-checker"], {"unchanged": True})
        return payload["scan_results"]["release-checker"]

    def test_each_stable_archive_is_downloaded_once(self):
        releases = [{"tag_name": "v1", "assets": [{"name": "project.asc"}]},
                    {"tag_name": "draft", "draft": True},
                    {"tag_name": "preview", "prerelease": True},
                    {"tag_name": "v2", "assets": []}]
        archive = archive_bytes(1024)
        with ReleaseHTTPFixture(releases, {"/v1.zip": (200, archive),
                                          "/v2.zip": (200, archive)}) as fixture:
            result = self.scan()
            self.assertEqual(fixture.requests, {"/releases": 3, "/v1.zip": 1, "/v2.zip": 1})
            self.assertEqual(fixture.bytes_sent["/v1.zip"], len(archive))
            self.assertEqual(fixture.bytes_sent["/v2.zip"], len(archive))
        self.assertEqual([e["tag"] for e in result["notes"]["release_contents"]], ["v1", "v2"])
        self.assertEqual(result["notes"]["release_contents"][0]["content_files"],
                         ["project/CHANGELOG"])
        self.assertEqual(result["signed-release-checker"]["signed_files"][0]["signature_files"],
                         ["project.asc"])

    def test_empty_archives_are_also_reused(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w"):
            pass
        with ReleaseHTTPFixture([{"tag_name": "empty"}],
                                {"/empty.zip": (200, buffer.getvalue())}) as fixture:
            result = self.scan()
            self.assertEqual(fixture.requests["/empty.zip"], 1)
        for content_type in ("notes", "sbom"):
            self.assertFalse(result[content_type]["release_contents"][0]["has_content"])
            self.assertIsNone(result[content_type]["release_contents"][0]["error"])

    def test_new_scan_reads_new_content_at_the_same_url(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w"):
            pass
        with ReleaseHTTPFixture([{"tag_name": "v1"}],
                                {"/v1.zip": (200, archive_bytes())}) as fixture:
            first = self.scan()
            fixture.archives["/v1.zip"] = (200, buffer.getvalue())
            second = self.scan()
            self.assertEqual(fixture.requests["/v1.zip"], 2)
        self.assertTrue(first["notes"]["release_contents"][0]["has_content"])
        self.assertFalse(second["notes"]["release_contents"][0]["has_content"])

    def test_http_failure_can_recover_for_the_second_content_check(self):
        with ReleaseHTTPFixture([{"tag_name": "v1"}],
                                {"/v1.zip": [(503, b"unavailable"),
                                             (200, archive_bytes())]}) as fixture:
            result = self.scan()
            self.assertEqual(fixture.requests["/v1.zip"], 2)
        self.assertEqual(result["notes"]["release_contents"][0]["error"],
                         "Failed to download release zip: 503")
        self.assertIsNone(result["sbom"]["release_contents"][0]["error"])

    def test_invalid_zip_can_recover_for_the_second_content_check(self):
        with ReleaseHTTPFixture([{"tag_name": "v1"}],
                                {"/v1.zip": [(200, b"not a ZIP"),
                                             (200, archive_bytes())]}) as fixture:
            result = self.scan()
            self.assertEqual(fixture.requests["/v1.zip"], 2)
        self.assertEqual(result["notes"]["release_contents"][0]["error"], "Invalid zip file")
        self.assertIsNone(result["sbom"]["release_contents"][0]["error"])

    def test_direct_content_checks_keep_independent_downloads(self):
        with ReleaseHTTPFixture([{"tag_name": "v1"}],
                                {"/v1.zip": (200, archive_bytes())}) as fixture:
            for _ in range(2):
                result, error = release_checker.check_release_contents(self.project_url)
                self.assertIsNone(error)
                self.assertTrue(result["release_contents"][0]["has_content"])
            self.assertEqual(fixture.requests["/v1.zip"], 2)

    def test_reused_archive_is_matched_against_each_requested_pattern(self):
        # Exercise both existing matcher branches. The separately reported
        # SBOM pattern-factory bug is not changed by download reuse.
        with ReleaseHTTPFixture([{"tag_name": "v1"}],
                                {"/v1.zip": (200, archive_bytes())}) as fixture, \
                patch.object(release_checker, "_get_file_patterns", side_effect=[
                    ["changelog"], [re.compile(r".+\.spdx\.json$")]]):
            result = self.scan()
            self.assertEqual(fixture.requests["/v1.zip"], 1)
        self.assertEqual(result["notes"]["release_contents"][0]["content_files"],
                         ["project/CHANGELOG"])
        self.assertEqual(result["sbom"]["release_contents"][0]["content_files"],
                         ["project/bom.spdx.json"])

    def test_archive_failure_does_not_hide_other_releases_or_signatures(self):
        releases = [{"tag_name": tag, "assets": [{"name": "project.asc"}]}
                    for tag in ("v1", "broken", "v2")]
        archives = {"/v1.zip": (200, archive_bytes()),
                    "/broken.zip": (503, b"unavailable"),
                    "/v2.zip": (200, archive_bytes())}
        with ReleaseHTTPFixture(releases, archives):
            payload = {"scan_results": {}}
            release_checker.release_checker(self.project_url, payload)
        result = payload["scan_results"]["release-checker"]
        for content_type in ("notes", "sbom"):
            entries = result[content_type]["release_contents"]
            self.assertEqual([entry["tag"] for entry in entries], ["v1", "broken", "v2"])
            self.assertIsNone(entries[0]["error"])
            self.assertEqual(entries[1]["error"], "Failed to download release zip: 503")
            self.assertIsNone(entries[2]["error"])
        self.assertTrue(result["notes"]["release_contents"][2]["has_content"])
        self.assertEqual(len(result["signed-release-checker"]["signed_files"]), 3)


if __name__ == "__main__":
    unittest.main()
