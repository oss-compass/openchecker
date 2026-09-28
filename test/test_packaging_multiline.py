"""Exercise the actual packaging checker with temporary workflow files.

Only the configured platform manager is isolated; workflow discovery, YAML
reading, pattern detection, line reporting and result assembly are real.
"""
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackagingMultilineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        adapter = types.ModuleType('platform_adapter')
        adapter.platform_manager = types.SimpleNamespace(
            parse_project_url=lambda url: ('example', str(self.repo)))
        common = load_module('packaging_test_common', 'openchecker/common.py')
        with patch.dict('sys.modules', {'platform_adapter': adapter, 'common': common}):
            self.checker = load_module('packaging_under_test', 'openchecker/checkers/packaging_checker.py')

    def scan(self, steps, extension='yml'):
        workflow = self.repo / '.github' / 'workflows' / ('publish.' + extension)
        workflow.parent.mkdir(parents=True, exist_ok=True)
        content = 'name: publish\non: push\njobs:\n  publish:\n    runs-on: ubuntu-latest\n    steps:\n' + steps
        workflow.write_text(content, encoding='utf-8')
        payload = {'scan_results': {}}
        self.checker.packaging_checker('https://github.com/example/project', payload)
        result, = payload['scan_results']['packaging-checker']
        self.assertEqual(result['file_path'], str(workflow))
        return result, content

    def test_literal_run_detects_publish_after_build(self):
        result, content = self.scan('      - run: |\n          cargo build\n          cargo publish\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], content.splitlines().index('      - run: |') + 1)

    def test_folded_run_joins_command_arguments(self):
        result, _ = self.scan('      - run: >-\n          cargo\n          publish\n', 'yaml')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], 7)

    def test_npm_group_still_requires_setup_registry_and_publish(self):
        setup = ('      - uses: actions/setup-node@v4\n'
                 '        with:\n          registry-url: https://registry.npmjs.org\n')
        result, _ = self.scan(setup + '      - run: |-\n          npm ci\n          npm publish\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], 7)

    def test_unrelated_literal_lines_do_not_form_a_publish_command(self):
        result, _ = self.scan('      - run: |\n          cargo build\n          echo publish\n')
        self.assertFalse(result['matched'])
        self.assertEqual(result['line_number'], 0)

    def test_next_step_name_is_not_part_of_run_block(self):
        result, _ = self.scan('      - run: |\n          cargo build\n'
                              '      - name: cargo publish\n        run: echo done\n')
        self.assertFalse(result['matched'])

    def test_npm_without_registry_remains_unmatched(self):
        result, _ = self.scan('      - uses: actions/setup-node@v4\n'
                              '      - run: |\n          npm publish\n')
        self.assertFalse(result['matched'])

    def test_inline_command_is_unchanged(self):
        result, _ = self.scan('      - run: cargo publish\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], 7)

    def test_action_based_publishing_is_unchanged(self):
        result, _ = self.scan('      - uses: pypa/gh-action-pypi-publish@v1\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], 7)

    def test_chomping_and_explicit_indentation(self):
        for marker in ('|+', '|2-', '>+'):
            with self.subTest(marker=marker):
                result, _ = self.scan('      - run: ' + marker + '\n          cargo publish\n')
                self.assertTrue(result['matched'])
                self.assertEqual(result['line_number'], 7)

    def test_later_action_keeps_its_original_line_number(self):
        result, content = self.scan('      - run: |\n          echo build\n          echo test\n'
                                   '      - uses: pypa/gh-action-pypi-publish@v1\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'],
                         content.splitlines().index('      - uses: pypa/gh-action-pypi-publish@v1') + 1)

    def test_block_step_description_does_not_become_a_command(self):
        result, _ = self.scan('      - name: |\n          cargo publish\n        run: echo build\n')
        self.assertFalse(result['matched'])

    def test_multiline_run_with_non_ascii_step_name(self):
        result, _ = self.scan('      - name: 发布\n        run: |\n          docker push example/image\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], 8)

    def test_run_named_environment_value_is_not_a_step_command(self):
        result, _ = self.scan('      - run: echo build\n        env:\n'
                              '          run: |\n            cargo publish\n')
        self.assertFalse(result['matched'])


if __name__ == '__main__':
    unittest.main()
