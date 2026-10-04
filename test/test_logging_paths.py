"""Exercise file logging in isolated processes with real temporary files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LoggingPathTests(unittest.TestCase):
    def configure(self, path, directory, enable_file=True):
        script = '''
import json, logging, sys
from logger import setup_logging, get_logger
setup_logging(log_file=sys.argv[1], log_dir=sys.argv[2], enable_console=False,
              enable_file=sys.argv[3] == 'true')
get_logger('openchecker').error('unique-error-marker')
logging.shutdown()
'''
        env = dict(os.environ)
        env.pop('LOG_LEVEL', None)
        return subprocess.run(
            [sys.executable, '-c', script, str(path), str(directory), str(enable_file).lower()],
            env=env, capture_output=True, text=True, check=True,
        )

    def test_creates_explicit_file_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom' / 'nested' / 'service.log'
            self.configure(path, Path(directory) / 'unused-default')
            self.assertTrue(path.is_file())
            self.assertTrue(path.with_name('service_error.log').is_file())

    def test_suffixless_log_has_separate_error_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'service'
            self.configure(path, directory)
            messages = [json.loads(line)['message'] for line in path.read_text().splitlines()]
            self.assertEqual(messages.count('unique-error-marker'), 1)
            self.assertTrue(path.with_name('service_error.log').is_file())

    def test_log_suffix_in_parent_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / 'service.log.archive'
            parent.mkdir()
            path = parent / 'output.log'
            self.configure(path, parent)
            self.assertTrue(parent.joinpath('output_error.log').is_file())

    def test_alternate_extension_has_separate_error_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'service.txt'
            self.configure(path, directory)
            self.assertTrue(path.with_name('service_error.txt').is_file())

    def test_console_only_does_not_create_file_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            unused = Path(directory) / 'unused'
            self.configure(unused / 'service.log', unused, enable_file=False)
            self.assertFalse(unused.exists())

    def test_default_log_suffix_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'service.log'
            self.configure(path, directory)
            self.assertTrue(path.is_file())
            error_file = path.with_name('service_error.log')
            self.assertEqual(json.loads(error_file.read_text())['message'], 'unique-error-marker')


if __name__ == '__main__':
    unittest.main()
