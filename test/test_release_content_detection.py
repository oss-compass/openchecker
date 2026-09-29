import io
import zipfile
from unittest.mock import Mock, patch

from openchecker.checkers.release_checker import _check_zip_contents, _get_file_patterns


def test_release_archive_finds_notes_and_sbom_files():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        for name in ("repo/CHANGELOG.md", "repo/docs/component.spdx.yaml", "repo/sbom.cdx.json", "repo/README.md"):
            zip_file.writestr(name, "content")

    with patch("openchecker.checkers.release_checker.requests.get", return_value=Mock(status_code=200, content=archive.getvalue())):
        notes, notes_error = _check_zip_contents("https://example.com/archive.zip", _get_file_patterns("notes"))
        sboms, sbom_error = _check_zip_contents("https://example.com/archive.zip", _get_file_patterns("sbom"))

    assert notes_error is None
    assert sbom_error is None
    assert notes == ["repo/CHANGELOG.md"]
    assert sboms == ["repo/docs/component.spdx.yaml", "repo/sbom.cdx.json"]
