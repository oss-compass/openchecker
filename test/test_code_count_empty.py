"""Exercise the real code-count checker with an installed cloc CLI.

CLOC_TEST_COMMAND may contain a JSON argv list, e.g. ["perl", "/path/cloc"].
Only executable dispatch is adapted in that case; cloc output is never mocked.
"""
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class CodeCountEmptyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get('CLOC_TEST_COMMAND')
        cls.command = json.loads(configured) if configured else ['cloc']
        if not shutil.which(cls.command[0]):
            raise unittest.SkipTest('Install cloc or set CLOC_TEST_COMMAND')
        version = subprocess.run(cls.command + ['--version'], capture_output=True, text=True, check=True)
        print('cloc version:', version.stdout.strip())
        # Unrelated service integrations are not exercised by code-count.
        modules = {}
        for name, attributes in {
            'logger': {'get_logger': logging.getLogger},
            'aksk.default_request': {'DefaultRequest': object},
            'aksk.signer': {'Signer': object},
            'helper': {'read_config': lambda: {}},
            'platform_adapter': {'platform_manager': object()},
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(attributes)
            modules[name] = module
        spec = importlib.util.spec_from_file_location(
            'code_count_under_test', ROOT / 'openchecker/checkers/standard_command_checker.py')
        cls.checker = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(cls.checker)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous_cwd = os.getcwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, self.previous_cwd)
        self.repo = Path('example')
        self.repo.mkdir()
        self.results = []
        real_run = subprocess.run

        def run_cloc(command, **kwargs):
            self.assertEqual(command, ['cloc', 'example', '--json'])
            result = real_run(self.command + command[1:], **kwargs)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.results.append(result.stdout)
            return result

        self.dispatch = patch.object(self.checker.subprocess, 'run', side_effect=run_cloc)
        self.dispatch.start()
        self.addCleanup(self.dispatch.stop)

    def scan(self, expected):
        payload = {'scan_results': {}}
        self.checker.code_count_checker('https://github.com/fixture/example', payload)
        self.assertEqual(payload['scan_results']['code-count'], {'code_count': expected})
        self.assertEqual(len(self.results), 1)

    def test_empty_checkout(self):
        self.scan(0)
        self.assertEqual(json.loads(self.results[0] or '{}'), {})

    def test_only_unrecognized_text(self):
        (self.repo / 'LICENSE').write_text('Example license text\n', encoding='utf-8')
        self.scan(0)
        self.assertEqual(json.loads(self.results[0] or '{}'), {})

    def test_only_empty_source_file(self):
        (self.repo / 'empty.py').write_text('', encoding='utf-8')
        self.scan(0)
        self.assertEqual(json.loads(self.results[0] or '{}'), {})

    def test_comments_still_report_zero(self):
        (self.repo / 'comments.py').write_text('# A comment\n', encoding='utf-8')
        self.scan(0)
        self.assertEqual(json.loads(self.results[0])['SUM']['comment'], 1)

    def test_multiple_languages_keep_their_sum(self):
        (self.repo / 'one.py').write_text('print(1)\n', encoding='utf-8')
        (self.repo / 'two.c').write_text('int one = 1;\nint two = 2;\n', encoding='utf-8')
        self.scan(3)


if __name__ == '__main__':
    unittest.main()

