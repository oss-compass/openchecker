"""Check source locations using real workflow files and the native YAML loader."""

import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openchecker'))
from checkers import dangerous_workflow_checker as checker


class DangerousWorkflowLineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name) / 'project'
        self.workflows = self.repo / '.github' / 'workflows'
        self.workflows.mkdir(parents=True)

    def scan(self, content, newline=None):
        self.content = textwrap.dedent(content).lstrip('\n')
        self.path = self.workflows / 'check.yml'
        with self.path.open('w', encoding='utf-8', newline=newline) as stream:
            stream.write(self.content)
        return checker.check_workflow_file(self.path, str(self.repo), 'github')

    def line_of(self, text):
        return self.content.splitlines().index(text) + 1

    def assert_location(self, finding, source, kind):
        self.assertEqual(finding['line'], self.line_of(source))
        self.assertEqual(finding['type'], kind)
        self.assertEqual(finding['file'], str(self.path.relative_to(self.repo)))

    def test_checkout_uses_source_line_after_name_and_comments(self):
        result = self.scan('''
            name: checkout
            on: pull_request_target

            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - name: fetch code
                    # The action is not the first line of this step.
                    uses: actions/checkout@v4
                    with:
                      ref: ${{ github.event.pull_request.head.sha }}
        ''')
        finding, = result['dangerous_patterns']
        self.assert_location(finding, '        uses: actions/checkout@v4',
                             'untrusted_checkout')
        self.assertEqual(finding['job'], 'build')
        self.assertEqual(finding['snippet'], '${{ github.event.pull_request.head.sha }}')

    def test_block_script_findings_point_to_run_key(self):
        result = self.scan('''
            on: issues
            jobs:
              report:
                steps:
                  - name: display
                    run: |
                      echo "${{ github.event.issue.title }}"
                      echo "${{ github.event.issue.body }}"
        ''')
        self.assertEqual(len(result['dangerous_patterns']), 2)
        for finding in result['dangerous_patterns']:
            self.assert_location(finding, '        run: |', 'script_injection')

    def test_multiple_jobs_keep_distinct_source_locations(self):
        result = self.scan('''
            on: issues
            jobs:
              first:
                steps:
                  - run: echo "${{ github.event.issue.title }}"

              second:
                steps:
                  - run: echo safe
                  - run: echo "${{ github.event.issue.body }}"
        ''')
        first, second = result['dangerous_patterns']
        self.assert_location(first, '      - run: echo "${{ github.event.issue.title }}"',
                             'script_injection')
        self.assert_location(second, '      - run: echo "${{ github.event.issue.body }}"',
                             'script_injection')
        self.assertEqual([first['job'], second['job']], ['first', 'second'])

    def test_flow_mapping_keeps_its_actual_line(self):
        result = self.scan('''
            on: issues

            jobs:
              report:
                steps:
                  - {name: inline, run: 'echo "${{ github.event.issue.title }}"'}
        ''')
        finding, = result['dangerous_patterns']
        self.assert_location(finding,
            '      - {name: inline, run: \'echo "${{ github.event.issue.title }}"\'}',
            'script_injection')

    def test_alias_keeps_the_defining_source_line(self):
        result = self.scan('''
            on: issues
            jobs:
              report:
                steps:
                  - &display
                    run: echo "${{ github.event.issue.title }}"
                  - *display
        ''')
        self.assertEqual(len(result['dangerous_patterns']), 2)
        for finding in result['dangerous_patterns']:
            self.assert_location(finding,
                '        run: echo "${{ github.event.issue.title }}"', 'script_injection')

    def test_merge_inherits_source_line(self):
        result = self.scan('''
            on: issues
            jobs:
              report:
                steps:
                  - &display
                    run: echo "${{ github.event.issue.title }}"
                  - <<: *display
                    name: inherited
        ''')
        self.assertEqual(len(result['dangerous_patterns']), 2)
        for finding in result['dangerous_patterns']:
            self.assert_location(finding,
                '        run: echo "${{ github.event.issue.title }}"', 'script_injection')

    def test_merge_override_uses_override_line_and_value(self):
        result = self.scan('''
            on: issues
            jobs:
              report:
                steps:
                  - &display
                    run: echo safe
                  - <<: *display
                    run: echo "${{ github.event.issue.body }}"
        ''')
        finding, = result['dangerous_patterns']
        self.assert_location(finding,
            '        run: echo "${{ github.event.issue.body }}"', 'script_injection')
        self.assertEqual(finding['snippet'], 'github.event.issue.body')

    def test_unicode_and_crlf_count_physical_lines(self):
        result = self.scan('''
            # 安全扫描

            on: issues
            jobs:
              report:
                steps:
                  - name: 显示标题
                    run: >-
                      echo "${{ github.event.issue.title }}"
        ''', newline='\r\n')
        finding, = result['dangerous_patterns']
        self.assert_location(finding, '        run: >-', 'script_injection')

    def test_public_scan_reports_source_location(self):
        self.scan('''
            name: report
            on: issues

            jobs:
              report:
                steps:
                  - run: echo "${{ github.event.issue.title }}"
        ''')
        previous = os.getcwd()
        try:
            os.chdir(self.repo.parent)
            payload = {'scan_results': {}}
            checker.dangerous_workflow_checker('https://github.com/example/project', payload)
        finally:
            os.chdir(previous)
        workflow, = payload['scan_results'][checker.COMMAND]
        finding, = workflow['dangerous_patterns']
        self.assert_location(finding,
            '      - run: echo "${{ github.event.issue.title }}"', 'script_injection')

    def test_plain_dictionary_helpers_keep_step_index_fallback(self):
        workflow = yaml.safe_load('''
            on: pull_request_target
            jobs:
              report:
                steps:
                  - uses: actions/checkout@v4
                    with:
                      ref: ${{ github.event.pull_request.head.sha }}
                  - run: echo "${{ github.event.issue.title }}"
        ''')
        checkout, = checker.check_untrusted_checkout(workflow, 'check.yml', 'github')
        injection, = checker.check_script_injection(workflow, 'check.yml', 'github')
        self.assertEqual(checkout['line'], 1)
        self.assertEqual(injection['line'], 2)

    def test_safe_workflow_has_no_findings(self):
        result = self.scan('''
            on: push
            jobs:
              report:
                steps:
                  - uses: actions/checkout@v4
                  - run: echo "$TITLE"
                    env:
                      TITLE: ${{ github.event.issue.title }}
        ''')
        self.assertEqual(result['dangerous_patterns'], [])

    def test_loader_keeps_safe_load_isolated(self):
        self.scan('on: push\njobs: {}\n')
        mapping = yaml.safe_load('run: echo hello\n')
        self.assertIs(type(mapping), dict)
        self.assertEqual(mapping, {'run': 'echo hello'})
        result = self.scan('!!python/tuple [1, 2]\n')
        self.assertEqual(result['dangerous_patterns'], [])


if __name__ == '__main__':
    unittest.main()
