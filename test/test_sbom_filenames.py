"""SBOM recognition requires a complete supported filename extension."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sbom.sbom_checker import (
    SBOMChecker, CheckRequest, MockRepoClient, Release, check_sbom_for_project,
)


class SBOMFilenameTests(unittest.TestCase):
    def test_all_supported_source_extensions(self):
        checker = SBOMChecker()
        for suffix in ('cdx.json', 'cdx.xml', 'spdx', 'spdx.json', 'spdx.xml',
                       'spdx.yaml', 'spdx.yml', 'spdx.rdf', 'spdx.rdf.xml'):
            for name in ('component.' + suffix, 'COMPONENT.' + suffix.upper()):
                with self.subTest(name=name):
                    self.assertTrue(checker._is_sbom_file(name))

    def test_source_sidecars_do_not_satisfy_sbom_probe(self):
        names = ['component.spdx.json.sig', 'component.cdx.xml.bak',
                 'component.spdx-notes.txt', 'component.spdx.y?ml']
        with patch.dict(os.environ, {'SCORECARD_EXPERIMENTAL': 'true'}):
            result = SBOMChecker().check_sbom(CheckRequest(repo_client=MockRepoClient(files=names)))
        self.assertIsNone(result.error)
        self.assertEqual(result.score, 0)

    def test_release_sidecars_do_not_preempt_real_sbom(self):
        release = Release(assets=[
            {'name': 'component.spdx.json.sig', 'url': 'https://example.org/signature'},
            {'name': 'component.spdx.yml', 'url': 'https://example.org/manifest'},
        ])
        result = SBOMChecker()._check_sbom_releases([release])
        self.assertEqual([item.name for item in result], ['component.spdx.yml'])

    def test_local_scan_does_not_score_signature_or_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            root.mkdir()
            for name in ('component.spdx.json.asc', 'component.cdx.json.bak'):
                (root / name).write_text('not an SBOM', encoding='utf-8')
            previous = os.getcwd()
            try:
                os.chdir(directory)
                with patch.dict(os.environ):
                    result = check_sbom_for_project('https://github.com/example/project.git')
                self.assertEqual(result['status'], 'success')
                self.assertFalse(result['has_sbom'])
                self.assertEqual(result['score'], 0)
                (root / 'component.spdx.yml').write_text('spdxVersion: SPDX-2.3', encoding='utf-8')
                with patch.dict(os.environ):
                    result = check_sbom_for_project('https://github.com/example/project.git')
                self.assertEqual([item['name'] for item in result['sbom_files']], ['component.spdx.yml'])
            finally:
                os.chdir(previous)

    def test_source_scope_still_excludes_nested_and_hidden_files(self):
        for name in ('nested/component.spdx.json', '.component.spdx.json'):
            with self.subTest(name=name):
                self.assertFalse(SBOMChecker()._is_sbom_file(name))


if __name__ == '__main__':
    unittest.main()
