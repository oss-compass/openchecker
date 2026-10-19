"""Exercise native Requests against a loopback GitCode release API fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit, urlunsplit

import requests

from openchecker import platform_adapter


class GitCodeReleasePaginationTest(unittest.TestCase):
    """The fixture follows the documented page/per_page and JSON-array contract."""

    def setUp(self):
        self.releases = []
        self.calls = []
        self.fail_page = None
        self.fail_status = 500
        self.bad_json_page = None
        self.wrong_shape_page = None
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                page = int(query.get("page", ["1"])[0])
                size = int(query.get("per_page", ["20"])[0])
                case.calls.append({
                    "page": page, "size": size, "path": parsed.path,
                    "token": query.get("access_token"),
                    "accept": self.headers.get("Accept")})
                status = case.fail_status if page == case.fail_page else 200
                if page == case.bad_json_page:
                    body = b"not JSON"
                elif page == case.wrong_shape_page:
                    body = b'{"message":"unexpected response"}'
                else:
                    body = json.dumps(case.releases[
                        (page - 1) * size:page * size]).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.worker = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01},
            daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)
        self.session = requests.Session()
        self.session.trust_env = False
        self.addCleanup(self.session.close)
        self.adapter = platform_adapter.GitCodeAdapter({
            "GitCode": {"access_key": "fixture-token"}})

        def loopback_get(url, **kwargs):
            parsed = urlsplit(url)
            self.assertEqual(parsed.netloc, "api.gitcode.com")
            self.assertEqual(parsed.path, "/api/v5/repos/example/sample/releases")
            local = urlunsplit((
                "http", f"127.0.0.1:{self.server.server_port}",
                parsed.path, parsed.query, ""))
            kwargs.setdefault("timeout", 2)
            return self.session.get(local, **kwargs)

        # Redirect only the outbound destination. Requests serialization,
        # socket I/O, status handling and JSON decoding are real.
        self.redirect = patch.object(platform_adapter.requests, "get", loopback_get)
        self.redirect.start()
        self.addCleanup(self.redirect.stop)

    def stop_server(self):
        self.server.shutdown()
        self.worker.join(timeout=2)
        self.server.server_close()

    def set_releases(self, count):
        self.releases = [{
            "tag_name": f"v{index}", "name": f"Release {index}",
            "prerelease": False, "draft": False,
            "assets": [{"name": f"package-{index}.zip"}],
            "body": f"Notes {index}"} for index in range(count)]

    def read(self):
        return self.adapter.get_releases("https://gitcode.com/example/sample")

    def test_collects_all_pages_in_order(self):
        self.set_releases(101)
        releases, error = self.read()
        self.assertIsNone(error)
        self.assertEqual(releases, self.releases)
        self.assertEqual([call["page"] for call in self.calls], [1, 2])
        self.assertTrue(all(call["size"] == 100 for call in self.calls))

    def test_full_final_page_is_followed_by_an_empty_page(self):
        self.set_releases(200)
        releases, error = self.read()
        self.assertIsNone(error)
        self.assertEqual(releases, self.releases)
        self.assertEqual([call["page"] for call in self.calls], [1, 2, 3])

    def test_signed_release_checker_sees_later_page_assets(self):
        from openchecker.checkers.release_checker import check_signed_release

        self.set_releases(101)
        self.releases[-1]["assets"].append({"name": "package-100.zip.asc"})
        # Use the real manager and checker with this fixture's adapter config.
        with patch.dict(platform_adapter.platform_manager.adapters,
                        {"gitcode": self.adapter}):
            result, error = check_signed_release(
                "https://gitcode.com/example/sample")
        self.assertIsNone(error)
        self.assertTrue(result["is_released"])
        self.assertEqual(len(result["signed_files"]), 101)
        self.assertEqual(result["signed_files"][-1]["tag"], "v100")
        self.assertEqual(result["signed_files"][-1]["signature_files"],
                         ["package-100.zip.asc"])

    def test_empty_repository(self):
        self.assertEqual(self.read(), ([], None))
        self.assertEqual(len(self.calls), 1)

    def test_single_page_preserves_fields_and_authentication(self):
        self.set_releases(3)
        self.assertEqual(self.read(), (self.releases, None))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["token"], ["fixture-token"])
        self.assertEqual(self.calls[0]["accept"], "application/json")

    def test_later_http_failure_does_not_return_partial_results(self):
        self.set_releases(101)
        self.fail_page = 2
        self.assertEqual(self.read(), ([], "Not found"))

    def test_later_invalid_json_does_not_return_partial_results(self):
        self.set_releases(101)
        self.bad_json_page = 2
        releases, error = self.read()
        self.assertEqual(releases, [])
        self.assertTrue(error)

    def test_later_non_array_json_does_not_return_partial_results(self):
        self.set_releases(101)
        self.wrong_shape_page = 2
        releases, error = self.read()
        self.assertEqual(releases, [])
        self.assertTrue(error)

    def test_first_page_http_failure_preserves_error_contract(self):
        self.fail_page = 1
        self.fail_status = 403
        self.assertEqual(self.read(), ([], "Not found"))

    def test_invalid_project_url_does_not_make_a_request(self):
        releases, error = self.adapter.get_releases("https://gitcode.com/example")
        self.assertEqual(releases, [])
        self.assertTrue(error)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
