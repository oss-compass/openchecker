"""Regression tests for get_package_info's npm download-statistics handling.

Inside the `response.status_code == 200` branch (npm registry
responded), get_package_info queried the npm downloads API and then
checked `elif response.status_code == 404` - the registry response,
which is always 200 in this branch - instead of
`response_down.status_code`. The 404 branch was therefore
unreachable, and when the downloads API returned any non-200 status
the function fell off the end and returned None, crashing
package_info_checker's tuple unpacking with "cannot unpack
non-iterable NoneType object".
"""
from checkers import standard_command_checker as scc


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def run_package_info(monkeypatch, registry_resp, downloads_resp):
    def fake_get(url, *args, **kwargs):
        if url.startswith("https://registry.npmjs.org/"):
            return registry_resp
        if url.startswith("https://api.npmjs.org/downloads/"):
            return downloads_resp
        raise AssertionError("unexpected url: " + url)
    monkeypatch.setattr(scc.requests, "get", fake_get)
    monkeypatch.setattr(scc.platform_manager, "get_repo_info",
                        lambda url: ({"description": "repo desc",
                                      "homepage": "https://example.com"}, None))
    payload = {"scan_results": {}}
    scc.package_info_checker("https://github.com/owner/demo", payload)
    return payload["scan_results"]["package-info"]


def test_downloads_404_reports_not_found_error(monkeypatch):
    result = run_package_info(
        monkeypatch,
        FakeResponse(200, payload={"versions": {"1.0.0": {"dependencies": {}}}}),
        FakeResponse(404))
    assert result == {"error": "Not found"}


def test_downloads_200_reports_package_info(monkeypatch):
    result = run_package_info(
        monkeypatch,
        FakeResponse(200, payload={
            "versions": {"1.0.0": {"dependencies": {"left-pad": "*",
                                                    "ms": "*"}}}}),
        FakeResponse(200, payload={"downloads": [
            {"day": "2026-08-08", "downloads": 3},
            {"day": "2026-09-06", "downloads": 4},
        ]}))
    assert result == {
        "description": "repo desc",
        "home_url": "https://example.com",
        "dependent_count": 2,
        "down_count": 7,
        "day_enter": "2026-08-08 - 2026-09-06",
    }


def test_downloads_other_error_reports_failure(monkeypatch):
    result = run_package_info(
        monkeypatch,
        FakeResponse(200, payload={"versions": {}}),
        FakeResponse(503))
    assert result == {"error": "Failed to get download statistics: HTTP 503"}
