"""Regression tests for release_checker SBOM detection.

_get_file_patterns returned the SBOM pattern as a plain string even
though it is a regular expression. _check_zip_contents dispatches on
the pattern type: plain strings are compared against the file's
basename with exact equality (meant for the release-notes keyword
list), while compiled patterns are passed to re.match. A string regex
therefore took the equality branch and could never equal a real
filename, so no release was ever reported as containing SBOM files.

The SBOM pattern also used the character class [a?] where the optional
quantifier a? was intended, so the .spdx.yml variant could not match
even once the pattern is compiled.

These tests patch the platform adapter calls and requests.get, so no
network access is required.
"""
import io
import zipfile

from checkers import release_checker as rc


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


def make_zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


RELEASES = [
    {
        "tag_name": "v1.0.0",
        "name": "release 1.0.0",
        "draft": False,
        "prerelease": False,
        "assets": [],
    }
]


def check_release(monkeypatch, zip_files, content_type):
    monkeypatch.setattr(rc, "get_all_releases_with_assets",
                        lambda url: (RELEASES, None))
    monkeypatch.setattr(rc, "_get_zipball_url",
                        lambda url, owner, repo, tag: "http://example.com/zip")
    monkeypatch.setattr(rc.requests, "get",
                        lambda url, timeout: FakeResponse(make_zip_bytes(zip_files)))
    return rc.check_release_contents(
        "https://github.com/owner/demo", content_type)


def test_cdx_sbom_files_are_detected(monkeypatch):
    result, error = check_release(
        monkeypatch,
        {"demo-v1.0.0/sbom.cdx.json": "{}",
         "demo-v1.0.0/README.md": "readme"},
        "sbom")
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/sbom.cdx.json"]


def test_spdx_yaml_and_yml_variants_are_detected(monkeypatch):
    result, error = check_release(
        monkeypatch,
        {"demo-v1.0.0/bom.spdx.yaml": "",
         "demo-v1.0.0/bom.spdx.yml": ""},
        "sbom")
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/bom.spdx.yaml",
                                      "demo-v1.0.0/bom.spdx.yml"]


def test_release_without_sbom_files_is_reported_as_empty(monkeypatch):
    result, error = check_release(
        monkeypatch,
        {"demo-v1.0.0/README.md": "readme",
         "demo-v1.0.0/pkg.zip": "binary"},
        "sbom")
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is False
    assert entry["content_files"] == []


def test_notes_keyword_filenames_still_match_exactly(monkeypatch):
    result, error = check_release(
        monkeypatch,
        {"demo-v1.0.0/changelog": "changes"},
        "notes")
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/changelog"]
