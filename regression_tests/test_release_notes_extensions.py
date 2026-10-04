import io
import zipfile
from types import SimpleNamespace

from checkers import release_checker


def test_release_notes_with_document_extensions_are_found(monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("project/CHANGELOG.md", "changes")
        zip_file.writestr("project/release_notes.rst", "notes")
        zip_file.writestr("project/release.py", "unrelated")

    monkeypatch.setattr(release_checker.requests, "get", lambda *_args, **_kwargs: SimpleNamespace(status_code=200, content=archive.getvalue()))
    files, error = release_checker._check_zip_contents("https://example.org/archive.zip", release_checker._get_file_patterns("notes"))

    assert error is None
    assert files == ["project/CHANGELOG.md", "project/release_notes.rst"]
