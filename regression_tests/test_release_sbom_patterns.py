import io
import zipfile
from types import SimpleNamespace

from checkers import release_checker


def test_sbom_filenames_in_release_archive_are_matched(monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        for name in ("project/bom.cdx.json", "project/manifest.spdx.yml", "project/manifest.spdx.yaml", "project/source.py"):
            zip_file.writestr(name, "content")

    monkeypatch.setattr(release_checker.requests, "get", lambda *_args, **_kwargs: SimpleNamespace(status_code=200, content=archive.getvalue()))
    files, error = release_checker._check_zip_contents("https://example.org/archive.zip", release_checker._get_file_patterns("sbom"))

    assert error is None
    assert files == ["project/bom.cdx.json", "project/manifest.spdx.yml", "project/manifest.spdx.yaml"]
