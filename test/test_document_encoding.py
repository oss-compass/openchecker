"""Document checks must pass UTF-8 Markdown to the model without locale damage."""

import builtins
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from checkers import document_checker


class DocumentEncodingTests(unittest.TestCase):
    def setUp(self):
        self.original_directory = os.getcwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        Path("sample").mkdir()
        self.markdown = "# 中文文档\n\nAPI 接口与编译说明 🚀\n"
        Path("sample/README.md").write_text(self.markdown, encoding="utf-8")

    def tearDown(self):
        os.chdir(self.original_directory)
        self.directory.cleanup()

    def check_document(self, doc_type, default_encoding):
        # Exercise real file decoding with the chosen platform default. Explicit
        # encodings still reach the real built-in open unchanged.
        def locale_open(file, mode="r", encoding=None, **kwargs):
            return builtins.open(
                file, mode, encoding=encoding or default_encoding, **kwargs
            )

        with patch.object(document_checker, "open", locale_open, create=True), \
                patch.object(document_checker, "completion_with_backoff",
                             return_value="YES") as completion:
            files, error = document_checker.check_doc_content(
                "https://github.com/example/sample", doc_type
            )

        self.assertIsNone(error)
        self.assertEqual(files, [os.path.join("sample", "README.md")])
        completion.assert_called_once()
        prompt = completion.call_args.kwargs["messages"][0]["content"]
        self.assertIn(self.markdown, prompt)

    def test_api_document_with_gbk_default(self):
        self.check_document("api-doc", "gbk")

    def test_api_document_with_cp1252_default(self):
        self.check_document("api-doc", "cp1252")

    def test_build_document_with_gbk_default(self):
        self.check_document("build-doc", "gbk")

    def test_build_document_with_cp1252_default(self):
        self.check_document("build-doc", "cp1252")


if __name__ == "__main__":
    unittest.main()
