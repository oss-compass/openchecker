"""Regression tests for release_checker release-notes detection.

The "notes" patterns are keyword strings ("changelog", "releasenotes",
"release_notes", "release", "release-notes"), but _check_zip_contents
compared them against each archive entry's basename with exact
equality. Real-world note files are named CHANGELOG.md,
ReleaseNotes.md and so on, so the basename never equals the bare
keyword and no release was ever reported as containing release notes.

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


def check_notes(monkeypatch, zip_files):
    monkeypatch.setattr(rc, "get_all_releases_with_assets",
                        lambda url: (RELEASES, None))
    monkeypatch.setattr(rc, "_get_zipball_url",
                        lambda url, owner, repo, tag: "http://example.com/zip")
    monkeypatch.setattr(rc.requests, "get",
                        lambda url, timeout: FakeResponse(make_zip_bytes(zip_files)))
    return rc.check_release_contents(
        "https://github.com/owner/demo", "notes")


def test_changelog_files_with_extensions_are_detected(monkeypatch):
    result, error = check_notes(
        monkeypatch, {"demo-v1.0.0/CHANGELOG.md": "notes"})
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/CHANGELOG.md"]


def test_nested_release_notes_files_are_detected(monkeypatch):
    result, error = check_notes(
        monkeypatch, {"demo-v1.0.0/docs/ReleaseNotes.md": "notes"})
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/docs/ReleaseNotes.md"]


def test_file_matching_several_keywords_is_reported_once(monkeypatch):
    result, error = check_notes(
        monkeypatch, {"demo-v1.0.0/release-notes.md": "notes"})
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/release-notes.md"]


def test_release_without_notes_files_is_reported_as_empty(monkeypatch):
    result, error = check_notes(
        monkeypatch,
        {"demo-v1.0.0/README.md": "readme",
         "demo-v1.0.0/pkg.zip": "binary"})
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is False
    assert entry["content_files"] == []


def test_exact_keyword_filenames_still_match(monkeypatch):
    result, error = check_notes(
        monkeypatch, {"demo-v1.0.0/changelog": "changes"})
    assert error is None
    entry = result["release_contents"][0]
    assert entry["has_content"] is True
    assert entry["content_files"] == ["demo-v1.0.0/changelog"]
