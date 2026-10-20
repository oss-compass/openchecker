"""Check reported Action values and pinning through real workflow files."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openchecker'))
from checkers import pinned_dependencies_checker as checker

SHA = '0123456789abcdef0123456789abcdef01234567'
REFERENCE = 'actions/checkout@' + SHA
HEADER = 'name: Test\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n'


class ActionYamlValueTests(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repository'
        self.repo.mkdir()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp.cleanup()

    def scan(self, content, platform='github'):
        directory = '.workflows' if platform == 'gitee' else '.' + platform + '/workflows'
        path = self.repo / directory / 'test.yml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        payload = {'scan_results': {'existing': 'preserved'}}
        checker.pinned_dependencies_checker('https://' + platform + '.com/example/repository', payload)
        self.assertEqual(payload['scan_results']['existing'], 'preserved')
        result = payload['scan_results'][checker.COMMAND]
        self.assertEqual(result['analysis_results']['total_dependencies'], len(result['dependencies']))
        return result

    def assert_pinned_action(self, result, line, snippet, name='actions/checkout'):
        dependencies = result['dependencies']
        self.assertEqual(len(dependencies), 1)
        action = dependencies[0]
        self.assertEqual((action['name'], action['version'], action['dep_type']), (name, SHA, 'Action'))
        self.assertEqual(action['line_number'], line)
        self.assertEqual(action['snippet'], snippet)
        self.assertTrue(action['is_pinned'])
        analysis = result['analysis_results']
        self.assertEqual((analysis['pinned_count'], analysis['unpinned_count']), (1, 0))
        self.assertEqual(analysis['findings'], [])
        if name.startswith('actions/'):
            self.assertTrue(action['is_owned'])
            self.assertEqual(analysis['actions']['owned'], {'pinned': 1, 'total': 1})

    def test_plain_reference_retains_existing_result(self):
        text = '- uses: ' + REFERENCE
        self.assert_pinned_action(self.scan(HEADER + '      ' + text + '\n'), 7, text)

    def test_single_quoted_reference(self):
        text = "- uses: '" + REFERENCE + "'"
        self.assert_pinned_action(self.scan(HEADER + '      ' + text + '\n'), 7, text)

    def test_double_quoted_reference(self):
        text = '- uses: "' + REFERENCE + '"'
        self.assert_pinned_action(self.scan(HEADER + '      ' + text + '\n'), 7, text)

    def test_yaml_escape_is_decoded_before_classification(self):
        text = '- uses: "actions/checkout@\\x30' + SHA[1:] + '"'
        self.assert_pinned_action(self.scan(HEADER + '      ' + text + '\n'), 7, text)

    def test_quoted_key_and_flow_step(self):
        text = '- {"uses": "' + REFERENCE + '"}'
        self.assert_pinned_action(self.scan(HEADER + '      ' + text + '\n'), 7, text)

    def test_folded_reference_points_to_uses_key(self):
        content = HEADER + '      - uses: >-\n          ' + REFERENCE + '\n'
        self.assert_pinned_action(self.scan(content), 7, '- uses: >-')

    def test_scalar_alias_points_to_using_key(self):
        content = 'env:\n  ACTION_REF: &action "' + REFERENCE + '"\n' + HEADER + '      - uses: *action\n'
        self.assert_pinned_action(self.scan(content), 9, '- uses: *action')

    def test_merged_step_retains_property_definition_location(self):
        content = 'x-step: &shared\n  uses: "' + REFERENCE + '"\n' + HEADER + '      - <<: *shared\n'
        self.assert_pinned_action(self.scan(content), 2, 'uses: "' + REFERENCE + '"')

    def test_merge_override_reports_only_effective_action(self):
        content = ('x-step: &shared\n  uses: "' + REFERENCE + '"\n' + HEADER
                   + '      - <<: *shared\n        uses: "third/action@' + SHA + '"\n')
        self.assert_pinned_action(self.scan(content), 10, 'uses: "third/action@' + SHA + '"', 'third/action')

    def test_quoted_reusable_job_is_a_dependency(self):
        text = 'uses: "third/workflows/reuse.yml@' + SHA + '"'
        content = 'name: Reuse\non: push\njobs:\n  reuse:\n    ' + text + '\n'
        self.assert_pinned_action(self.scan(content), 5, text, 'third/workflows/reuse.yml')

    def test_non_action_text_is_not_dependency_evidence(self):
        content = (HEADER + '      - run: |\n          echo "uses: madeup/action@main"\n'
                   + '        env:\n          NOTES: "uses: fake/action@main"\n'
                   + '      - uses: ' + REFERENCE + '\n')
        self.assert_pinned_action(self.scan(content), 11, '- uses: ' + REFERENCE)

    def test_branch_reference_stays_unpinned(self):
        result = self.scan(HEADER + '      - uses: third/action@main\n')
        self.assertEqual(len(result['dependencies']), 1)
        self.assertFalse(result['dependencies'][0]['is_pinned'])
        self.assertEqual(result['analysis_results']['unpinned_count'], 1)

    def test_local_action_stays_excluded(self):
        self.assertEqual(self.scan(HEADER + '      - uses: ./local-action\n')['dependencies'], [])

    def test_non_string_uses_stays_excluded(self):
        self.assertEqual(self.scan(HEADER + '      - uses: false\n')['dependencies'], [])

    def test_platform_workflow_discovery_preserves_decoded_value(self):
        text = '- uses: "' + REFERENCE + '"'
        for platform in ('github', 'gitee', 'gitcode'):
            with self.subTest(platform=platform):
                self.assert_pinned_action(self.scan(HEADER + '      ' + text + '\n', platform), 7, text)


if __name__ == '__main__':
    unittest.main()
