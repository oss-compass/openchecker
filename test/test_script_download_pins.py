"""Exercise download pinning through real script files and the public checker."""

import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openchecker'))
from checkers import pinned_dependencies_checker as checker


COMMIT = '0123456789abcdef0123456789abcdef01234567'
RAW = 'https://raw.githubusercontent.com/example/project/'
HASH = 'a' * 64


class ScriptDownloadPinTests(unittest.TestCase):
    def download(self, command, url):
        result, = checker._find_download_commands(command + ' ' + url)
        self.assertEqual(result[0], url.strip('\'"'))
        return result[1]

    def test_keywords_do_not_establish_a_pin(self):
        for url in ('https://example.org/shared/latest.sh',
                    'https://example.org/tags/v1.2/install.sh',
                    'https://example.org/install?version=latest',
                    'https://example.org/commits/main/install.sh',
                    'https://sha.example.org/install.sh'):
            for command in ('curl', 'wget', 'pip install', 'npm install'):
                with self.subTest(command=command, url=url):
                    self.assertFalse(self.download(command, url))

    def test_raw_github_full_commit_urls_are_pinned(self):
        for url in (RAW + COMMIT + '/install.sh',
                    RAW + COMMIT + '/nested/install.sh?download=1',
                    'https://github.com/example/project/raw/' + COMMIT + '/install.sh'):
            for command in ('curl', 'wget', 'pip install', 'npm install'):
                with self.subTest(command=command, url=url):
                    self.assertTrue(self.download(command, url))

    def test_commit_archives_are_pinned(self):
        for url in ('https://github.com/example/project/archive/' + COMMIT + '.zip',
                    'https://github.com/example/project/archive/' + COMMIT + '.tar.gz',
                    'https://codeload.github.com/example/project/zip/' + COMMIT,
                    'https://codeload.github.com/example/project/tar.gz/' + COMMIT):
            with self.subTest(url=url):
                self.assertTrue(self.download('curl -L', url))

    def test_mutable_and_abbreviated_refs_are_unpinned(self):
        for ref in ('main', 'v1.2.3', COMMIT[:12], COMMIT + '0', 'g' * 40,
                    'refs/heads/' + COMMIT):
            with self.subTest(ref=ref):
                self.assertFalse(self.download('curl', RAW + ref + '/install.sh'))
        self.assertFalse(self.download('wget',
            'https://github.com/example/project/archive/refs/tags/v1.2.3.zip'))

    def test_hashes_in_other_fields_do_not_pin_the_ref(self):
        for url in (RAW + 'main/' + COMMIT + '/install.sh',
                    RAW + 'main/install.sh?commit=' + COMMIT,
                    'https://github.com/example/project/releases/download/' + COMMIT + '/install.sh',
                    'https://example.org/commit/' + COMMIT + '/install.sh'):
            with self.subTest(url=url):
                self.assertFalse(self.download('curl', url))

    def test_host_spoofing_and_http_are_not_commit_pins(self):
        for url in ('https://raw.githubusercontent.com.example.org/example/project/' + COMMIT + '/install.sh',
                    'https://raw.githubusercontent.com@evil.example/example/project/' + COMMIT + '/install.sh',
                    'http://raw.githubusercontent.com/example/project/' + COMMIT + '/install.sh',
                    'https://raw.githubusercontent.com:444/example/project/' + COMMIT + '/install.sh',
                    'https://raw.githubusercontent.com:invalid/example/project/' + COMMIT + '/install.sh'):
            with self.subTest(url=url):
                self.assertFalse(self.download('curl', url))

    def test_pip_accepts_complete_strong_hash_fragments(self):
        for algorithm, length in (('sha256', 64), ('sha384', 96), ('sha512', 128)):
            url = 'https://example.org/demo.whl#' + algorithm + '=' + 'a' * length
            with self.subTest(algorithm=algorithm):
                self.assertTrue(self.download('pip install', url))
        self.assertTrue(self.download('pip install',
            'https://example.org/demo.whl#sha256=' + HASH + '&egg=demo'))

    def test_hash_fragment_is_not_verified_by_other_downloaders(self):
        url = 'https://example.org/demo.whl#sha256=' + HASH
        for command in ('curl', 'wget', 'npm install'):
            with self.subTest(command=command):
                self.assertFalse(self.download(command, url))

    def test_malformed_and_query_hashes_are_unpinned(self):
        for suffix in ('#sha256=latest', '#sha256=' + 'g' * 64,
                       '#sha256=' + 'a' * 63, '#sha256=' + 'a' * 65,
                       '?sha256=' + HASH, '#SHA256=' + HASH,
                       '#sha256=' + HASH + '&sha256=' + 'b' * 64,
                       '#sha256=' + HASH + '&sha1=' + 'a' * 40,
                       '#sha%32%35%36=' + HASH,
                       '#sha1=' + 'a' * 40):
            with self.subTest(suffix=suffix):
                self.assertFalse(self.download('pip install', 'https://example.org/demo.whl' + suffix))

    def test_quoted_urls_keep_the_exact_url(self):
        for quote in ('"', "'"):
            for command in ('curl -L', 'wget', 'pip install'):
                with self.subTest(quote=quote, command=command):
                    self.assertTrue(self.download(command, quote + RAW + COMMIT + '/install.sh' + quote))

    def test_public_scan_counts_and_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'project'
            repo.mkdir()
            script = repo / 'install.sh'
            lines = [
                'curl https://example.org/shared/latest.sh',
                'wget https://example.org/tags/v1.2/install.sh',
                'curl ' + RAW + COMMIT + '/install.sh',
                'pip install https://example.org/demo.whl#sha256=' + HASH,
                'npm install https://example.org/demo?version=latest',
                'curl https://example.org/demo.whl#sha256=' + HASH,
            ]
            script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            previous = os.getcwd()
            try:
                os.chdir(directory)
                payload = {'scan_results': {}}
                checker.pinned_dependencies_checker('https://github.com/example/project', payload)
            finally:
                os.chdir(previous)
            result = payload['scan_results'][checker.COMMAND]
            analysis = result['analysis_results']
            self.assertEqual(analysis['total_dependencies'], 6)
            self.assertEqual(analysis['pinned_count'], 2)
            self.assertEqual(analysis['unpinned_count'], 4)
            self.assertEqual(analysis['by_type']['ScriptDownload'], {'pinned': 2, 'total': 6})
            self.assertEqual([f['line'] for f in analysis['findings']], [1, 2, 5, 6])
            self.assertTrue(all(f['file'] == str(Path('project') / 'install.sh')
                                for f in analysis['findings']))
            self.assertEqual([d['snippet'] for d in result['dependencies']], lines)

    def test_plain_urls_and_non_download_lines(self):
        for command in ('curl', 'wget', 'pip install', 'npm install'):
            with self.subTest(command=command):
                self.assertFalse(self.download(command, 'https://example.org/install.sh'))
        self.assertEqual(checker._find_download_commands('echo hello'), [])
        self.assertEqual(checker._find_download_commands(''), [])


if __name__ == '__main__':
    unittest.main()
