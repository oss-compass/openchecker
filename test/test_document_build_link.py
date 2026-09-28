"""Exercise build-document results without making LLM or clone requests."""

import importlib.util
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class BuildDocumentLinkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        previous = os.getcwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, previous)
        Path("example").mkdir()
        self.completion = Mock(return_value="NO")
        backoff = types.ModuleType("exponential_backoff")
        backoff.completion_with_backoff = self.completion
        log = types.ModuleType("logger")
        log.get_logger = logging.getLogger
        source = Path(__file__).resolve().parents[1] / "openchecker/checkers/document_checker.py"
        spec = importlib.util.spec_from_file_location("document_checker_under_test", source)
        self.checker = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"exponential_backoff": backoff, "logger": log}):
            spec.loader.exec_module(self.checker)

    def test_recognized_build_link_is_in_scan_result(self):
        Path("example/README.md").write_text(
            "Build instructions: https://gitee.com/openharmony-tpc/docs/blob/master/OpenHarmony_har_usage.md",
            encoding="utf-8",
        )
        payload = {"scan_results": {}}
        self.checker.build_doc_checker("https://example.org/example.git", payload)
        self.assertEqual(payload["scan_results"]["build-doc-checker"],
                         {"build-doc-checker": [os.path.join("example", "README.md")]})
        self.completion.assert_not_called()

    def test_llm_positive_result_is_preserved(self):
        Path("example/README.md").write_text("Build instructions", encoding="utf-8")
        self.completion.return_value = "YES"
        result, error = self.checker.check_doc_content("https://example.org/example.git", "build-doc")
        self.assertEqual(result, [os.path.join("example", "README.md")])
        self.assertIsNone(error)

    def test_link_does_not_short_circuit_api_document_check(self):
        Path("example/README.md").write_text(
            "https://gitee.com/openharmony-tpc/docs/blob/master/OpenHarmony_har_usage.md",
            encoding="utf-8",
        )
        result, error = self.checker.check_doc_content("https://example.org/example.git", "api-doc")
        self.assertEqual(result, [])
        self.assertIsNone(error)
        self.completion.assert_called_once()


if __name__ == "__main__":
    unittest.main()
