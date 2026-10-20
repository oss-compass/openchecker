"""Check permission evidence against real workflow files and the public scanner."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openchecker'))
from checkers import token_permissions_checker as checker


class PermissionSourceLineTests(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repository'
        self.repo.mkdir()
        # The existing scanner resolves URL repository names relative to cwd.
        # Exercise that contract without replacing the platform adapter.
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp.cleanup()

    def scan(self, text, platform='github'):
        directory = '.workflows' if platform == 'gitee' else '.' + platform + '/workflows'
        workflow = self.repo / directory / 'check.yml'
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(text, encoding='utf-8')
        payload = {'scan_results': {}}
        checker.token_permissions_checker('https://' + platform + '.com/example/repository', payload)
        return payload['scan_results'][checker.COMMAND]

    def row(self, result, name=None, job=None):
        rows = [row for row in result['token_permissions']
                if row['name'] == name and row.get('job_name') == job]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_top_scalar_after_comments_and_blank_lines(self):
        result = self.scan('# comment\nname: CI\n\npermissions: read-all\njobs: {}\n')
        self.assertEqual(self.row(result)['line_number'], 4)
        self.assertEqual(self.row(result)['permission_level'], 'read')

    def test_block_permissions_each_have_their_own_line(self):
        result = self.scan('name: CI\npermissions:\n  contents: read\n  packages: write\n  actions: none\njobs: {}\n')
        for name, line, value in [('contents', 3, 'read'), ('packages', 4, 'write'), ('actions', 5, 'none')]:
            with self.subTest(name=name):
                row = self.row(result, name)
                self.assertEqual(row['line_number'], line)
                self.assertEqual(row['value'], value)
                self.assertEqual(row['permission_level'], value)

    def test_flow_permission_mapping(self):
        result = self.scan('name: CI\n\npermissions: {contents: read, packages: write}\njobs: {}\n')
        self.assertEqual(self.row(result, 'contents')['line_number'], 3)
        self.assertEqual(self.row(result, 'packages')['line_number'], 3)

    def test_job_scalar_uses_its_declaration(self):
        result = self.scan('permissions: read-all\njobs:\n  build:\n    runs-on: ubuntu-latest\n    permissions: write-all\n')
        self.assertEqual(self.row(result, job='build')['line_number'], 5)
        self.assertEqual(self.row(result, job='build')['permission_level'], 'write')

    def test_job_block_permissions(self):
        result = self.scan('permissions: read-all\njobs:\n  build:\n    permissions:\n      contents: read\n      packages: write\n')
        self.assertEqual(self.row(result, 'contents', 'build')['line_number'], 5)
        self.assertEqual(self.row(result, 'packages', 'build')['line_number'], 6)

    def test_flow_job_and_permission_maps(self):
        result = self.scan('name: CI\npermissions: read-all\n\njobs: {build: {permissions: {contents: read}}}\n')
        self.assertEqual(self.row(result, 'contents', 'build')['line_number'], 4)

    def test_repeated_scope_names_in_different_jobs(self):
        result = self.scan('permissions: read-all\njobs:\n  first:\n    permissions:\n      contents: read\n  second:\n    permissions:\n      contents: write\n')
        self.assertEqual(self.row(result, 'contents', 'first')['line_number'], 5)
        self.assertEqual(self.row(result, 'contents', 'second')['line_number'], 8)

    def test_alias_reports_the_editable_anchor_definition(self):
        result = self.scan('permissions: &safe\n  contents: read\n  packages: read\njobs:\n  build:\n    permissions: *safe\n')
        self.assertEqual(self.row(result, 'contents', 'build')['line_number'], 2)
        self.assertEqual(self.row(result, 'packages', 'build')['line_number'], 3)

    def test_scalar_alias_reports_its_permissions_declaration(self):
        result = self.scan('permissions: &all read-all\njobs:\n  build:\n    permissions: *all\n')
        self.assertEqual(self.row(result, job='build')['line_number'], 4)

    def test_existing_yaml_merge_and_explicit_override_marks(self):
        # Parser compatibility control; no claim that every platform accepts merges.
        result = self.scan('permissions: &safe\n  contents: read\n  packages: read\njobs:\n  build:\n    permissions:\n      <<: *safe\n      contents: write\n')
        self.assertEqual(self.row(result, 'contents', 'build')['line_number'], 8)
        self.assertEqual(self.row(result, 'packages', 'build')['line_number'], 3)
        self.assertEqual(self.row(result, 'contents', 'build')['value'], 'write')

    def test_comments_and_strings_are_not_declarations(self):
        result = self.scan('# permissions: write-all\nenv:\n  EXAMPLE: "permissions: {contents: write}"\npermissions:\n  contents: read\njobs: {}\n')
        self.assertEqual(self.row(result, 'contents')['line_number'], 5)

    def test_native_discovery_for_all_supported_platforms(self):
        for platform in ('github', 'gitee', 'gitcode'):
            with self.subTest(platform=platform):
                result = self.scan('name: CI\npermissions: read-all\njobs: {}\n', platform)
                self.assertEqual(result['num_workflows'], 1)
                row = self.row(result)
                self.assertEqual(row['line_number'], 2)
                self.assertEqual(Path(row['file_path']).name, 'check.yml')

    def test_undeclared_permissions_keep_existing_fallback(self):
        result = self.scan('name: CI\njobs:\n  build:\n    runs-on: ubuntu-latest\n')
        for row in result['token_permissions']:
            self.assertEqual(row['line_number'], 1)
            self.assertEqual(row['permission_level'], 'undeclared')

    def test_empty_and_invalid_documents_keep_existing_behavior(self):
        for text in ('', '# only a comment\n', 'permissions: [\n'):
            with self.subTest(text=text):
                result = self.scan(text)
                self.assertEqual(result, {'num_workflows': 0, 'token_permissions': []})

    def test_dictionary_only_helpers_keep_existing_metadata(self):
        rows = checker._extract_top_level_permissions({'permissions': {'contents': 'write'}}, 'check.yml')
        self.assertEqual(rows, [{'file_path': 'check.yml', 'location_type': 'top', 'name': 'contents',
                                 'value': 'write', 'permission_level': 'write', 'line_number': 1}])


if __name__ == '__main__':
    unittest.main()
