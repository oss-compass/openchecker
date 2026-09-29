from unittest.mock import patch

from openchecker.checkers.document_checker import check_doc_content


def test_build_doc_link_reports_the_matching_document(tmp_path, monkeypatch):
    document_dir = tmp_path / "repo" / "docs"
    document_dir.mkdir(parents=True)
    document = document_dir / "build.md"
    document.write_text("See https://gitee.com/openharmony-tpc/docs/blob/master/OpenHarmony_har_usage.md", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with patch("openchecker.checkers.document_checker.completion_with_backoff") as completion:
        files, error = check_doc_content("https://github.com/owner/repo", "build-doc")

    assert error is None
    assert [path.replace("\\", "/") for path in files] == ["repo/docs/build.md"]
    completion.assert_not_called()
