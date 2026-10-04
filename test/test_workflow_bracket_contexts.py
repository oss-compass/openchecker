from pathlib import Path
import tempfile
import unittest

import yaml

from checkers.dangerous_workflow_checker import (
    check_workflow_file, find_dangerous_variables, is_untrusted_ref,
)


class WorkflowBracketContextTests(unittest.TestCase):
    def test_untrusted_script_property_forms(self):
        expressions = [
            "github.event.issue.title",
            "github['event']['issue']['title']",
            "github.event.issue['title']",
            "github [ 'event' ].issue [ 'body' ]",
            "github['head_ref']",
            "github.event['pull_request'].head['label']",
            "github['event'].commits[0].message",
            "toJSON(github['event']['comment']['body'])",
        ]
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertEqual(find_dangerous_variables(
                    'echo "${{ ' + expression + ' }}"', 'github'), [expression])

    def test_untrusted_checkout_property_forms(self):
        for expression in [
            "github['event']['pull_request'].head.sha",
            "github.event['workflow_run'].head_sha",
            "github.event.pull_request.head.sha",
        ]:
            with self.subTest(expression=expression):
                self.assertTrue(is_untrusted_ref('${{ ' + expression + ' }}', 'github'))

    def test_literals_and_trusted_contexts_are_not_findings(self):
        for expression in [
            "'github.event.issue.title'",
            "'github[''event''][''issue''][''title'']'",
            "github['sha']", "env['TITLE']",
        ]:
            with self.subTest(expression=expression):
                self.assertEqual(find_dangerous_variables('${{ ' + expression + ' }}', 'github'), [])

    def test_real_yaml_file_reports_original_snippets(self):
        ref = "${{ github['event']['pull_request']['head']['sha'] }}"
        title = "github['event'].issue['title']"
        workflow = {'on': 'pull_request_target', 'jobs': {'scan': {'steps': [
            {'uses': 'actions/checkout@v4', 'with': {'ref': ref}},
            {'run': 'echo "${{ ' + title + ' }}"'},
            {'env': {'TITLE': '${{ ' + title + ' }}'}, 'run': 'echo "$TITLE"'},
        ]}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workflow.yml'
            path.write_text(yaml.safe_dump(workflow), encoding='utf-8')
            result = check_workflow_file(path, directory, 'github')
        findings = result['dangerous_patterns']
        self.assertEqual([f['type'] for f in findings], ['untrusted_checkout', 'script_injection'])
        self.assertEqual([f['snippet'] for f in findings], [ref, title])


if __name__ == '__main__':
    unittest.main()
