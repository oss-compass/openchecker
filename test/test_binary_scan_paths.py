"""Run the real binary checker script on real local files; no network or mocks.

Main selects an isolated source tree with OPENCHECKER_SOURCE_ROOT and an
existing Bash with OPENCHECKER_BASH. No software is installed by this test.
"""
import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(os.environ.get(
    'OPENCHECKER_SOURCE_ROOT', str(Path(__file__).resolve().parents[1])))
BASH = os.environ.get('OPENCHECKER_BASH') or shutil.which('bash')
# A complete one-pixel PNG, inspected by the actual system `file` utility.
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5S8AAAAASUVORK5CYII=')


def bash_path(path):
    path = Path(path).resolve()
    value = path.as_posix()
    if os.name == 'nt' and path.drive:
        return '/' + path.drive[0].lower() + value[2:]
    return value


class BinaryScanPathTests(unittest.TestCase):
    def scan(self, binary_paths, text_paths=()):
        self.assertTrue(BASH, 'An existing Bash is required; set OPENCHECKER_BASH')
        script = SOURCE_ROOT / 'scripts' / 'binary_checker.sh'
        self.assertTrue(script.is_file(), str(script))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # The actual script sees this checkout and does not call git clone.
            repo = root / 'demo'
            repo.mkdir()
            for relative in binary_paths:
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(PNG)
            for relative in text_paths:
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('plain text only\n', encoding='utf-8')
            result = subprocess.run(
                [BASH, bash_path(script), 'https://github.com/example/demo'],
                cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            lines = result.stdout.decode('utf-8').splitlines()
            prefix = 'Binary file found: '
            # Retain whole paths; do not reproduce the production Python parser.
            return sorted(line[len(prefix):] for line in lines if line.startswith(prefix))

    def test_space_in_filename(self):
        self.assertEqual(self.scan(['my icon.png']), ['demo/my icon.png'])

    def test_spaces_in_parent_directories(self):
        self.assertEqual(self.scan(['build output/static images/icon.png']),
                         ['demo/build output/static images/icon.png'])

    def test_repeated_spaces_and_unrelated_files(self):
        paths = ['one  icon.png', 'another image.png', 'plain.png']
        self.assertEqual(self.scan(paths, ['notes here.txt']),
                         sorted('demo/' + name for name in paths))

    def test_glob_characters_are_literal(self):
        # The '*' name is valid on POSIX only; square brackets are valid on Windows too.
        names = ['icon[1].png', 'icon1.png']
        if os.name != 'nt':
            names.append('star*.png')
        self.assertEqual(self.scan(names), sorted('demo/' + name for name in names))

    def test_original_simple_binary_and_text_control(self):
        self.assertEqual(self.scan(['icon.png'], ['readme.txt']), ['demo/icon.png'])

    def test_existing_git_and_test_exclusions_control(self):
        self.assertEqual(self.scan(['.git/private.png', 'test/example.png', 'keep.png']),
                         ['demo/keep.png'])


if __name__ == '__main__':
    unittest.main()
