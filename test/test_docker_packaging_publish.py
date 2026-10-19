"""Exercise Docker publication detection with real YAML and workflow files."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DockerPackagingPublishTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        adapter = types.ModuleType('platform_adapter')
        adapter.platform_manager = types.SimpleNamespace(
            parse_project_url=lambda url: ('example', str(self.repo)))
        common = load_module('docker_packaging_common', 'openchecker/common.py')
        with patch.dict(sys.modules, {'platform_adapter': adapter, 'common': common}):
            self.checker = load_module(
                'docker_packaging_under_test', 'openchecker/checkers/packaging_checker.py')

    def scan(self, steps, prefix='', extension='yml'):
        content = (prefix + 'name: build\non: push\njobs:\n  build:\n'
                   '    runs-on: ubuntu-latest\n    steps:\n' + steps)
        workflow = self.repo / '.github' / 'workflows' / ('build.' + extension)
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(content, encoding='utf-8')
        payload = {'scan_results': {}}
        self.checker.packaging_checker('https://github.com/example/project', payload)
        result, = payload['scan_results']['packaging-checker']
        self.assertEqual(result['file_path'], str(workflow))
        return result, content

    def test_build_only_inputs_are_not_publication(self):
        for inputs in ('', '        with:\n          push: false\n',
                       '        with:\n          push: "false"\n',
                       '        with:\n          load: true\n',
                       '        with:\n          outputs: type=local,dest=out\n',
                       '        with:\n          outputs: type=docker,dest=image.tar\n',
                       '        with:\n          outputs: type=image,push=false\n'):
            with self.subTest(inputs=inputs):
                result, _ = self.scan('      - uses: docker/build-push-action@v6\n' + inputs)
                self.assertFalse(result['matched'])
                self.assertEqual(result['line_number'], 0)

    def test_explicit_push_is_detected_at_the_uses_line(self):
        for value in ('true', '"true"', "'TRUE'"):
            with self.subTest(value=value):
                result, content = self.scan(
                    '      - uses: docker/build-push-action@v6\n'
                    '        with:\n          push: ' + value + '\n')
                self.assertTrue(result['matched'])
                self.assertEqual(result['line_number'],
                                 content.splitlines().index(
                                     '      - uses: docker/build-push-action@v6') + 1)

    def test_conditional_push_remains_potential_publication(self):
        result, _ = self.scan(
            '      - uses: docker/build-push-action@v6\n'
            '        with:\n          push: ${{ github.event_name != \'pull_request\' }}\n')
        self.assertTrue(result['matched'])

    def test_registry_outputs_publish_without_push_shorthand(self):
        for outputs in ('type=registry', 'type=registry,name=example/app',
                        'type=image,name=example/app,push=true',
                        '|\n            type=local,dest=out\n'
                        '            type=registry,name=example/app',
                        '\'type=image,"name=app:a,app:b",push=true\''):
            with self.subTest(outputs=outputs):
                result, _ = self.scan(
                    '      - uses: docker/build-push-action@v6\n'
                    '        with:\n          push: false\n          outputs: ' + outputs + '\n')
                self.assertTrue(result['matched'])

    def test_dynamic_outputs_remain_potential_publication(self):
        result, _ = self.scan(
            '      - uses: docker/build-push-action@v6\n'
            '        with:\n          outputs: ${{ matrix.outputs }}\n')
        self.assertTrue(result['matched'])

    def test_push_setting_belongs_to_the_same_step(self):
        result, _ = self.scan(
            '      - uses: docker/build-push-action@v6\n'
            '        with:\n          push: false\n'
            '      - uses: example/unrelated@v1\n'
            '        with:\n          push: true\n')
        self.assertFalse(result['matched'])

    def test_later_publishing_step_supplies_the_evidence_line(self):
        result, content = self.scan(
            '      - uses: docker/build-push-action@v6\n'
            '        with:\n          push: false\n'
            '      - uses: docker/build-push-action@v7\n'
            '        with:\n          push: true\n')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'],
                         content.splitlines().index('      - uses: docker/build-push-action@v7') + 1)

    def test_quoted_action_and_pinned_revision_are_supported(self):
        result, _ = self.scan(
            '      - "uses": "docker/build-push-action@' + 'a' * 40 + '"\n'
            '        with:\n          push: true\n', extension='yaml')
        self.assertTrue(result['matched'])
        self.assertEqual(result['line_number'], 7)

    def test_comments_and_other_fields_are_not_action_steps(self):
        result, _ = self.scan(
            '      # - uses: docker/build-push-action@v6\n'
            '      #   with: {push: true}\n'
            '      - name: "uses: docker/build-push-action@v6"\n'
            '        run: echo building\n',
            prefix='env:\n  uses: docker/build-push-action@v6\n  push: true\n')
        self.assertFalse(result['matched'])

    def test_similarly_named_action_is_not_the_official_action(self):
        result, _ = self.scan(
            '      - uses: docker/build-push-action-extra@v6\n'
            '        with:\n          push: true\n')
        self.assertFalse(result['matched'])

    def test_docker_cli_and_other_existing_publishers_are_preserved(self):
        for steps in ('      - run: docker push example/app\n',
                      '      - run: cargo publish\n',
                      '      - uses: pypa/gh-action-pypi-publish@release/v1\n'):
            with self.subTest(steps=steps):
                result, _ = self.scan(steps)
                self.assertTrue(result['matched'])

    def test_reusable_job_and_missing_file_do_not_raise(self):
        result, _ = self.scan('      - run: echo build\n',
                              prefix='description: example\n')
        self.assertFalse(result['matched'])
        workflow = Path(result['file_path'])
        workflow.write_text('jobs:\n  reuse:\n    uses: example/workflows/.github/workflows/build.yml@v1\n',
                            encoding='utf-8')
        self.assertFalse(self.checker.is_packaging_workflow(str(workflow))['matched'])
        self.assertFalse(self.checker.is_packaging_workflow(
            str(self.repo / 'missing.yml'))['matched'])


if __name__ == '__main__':
    unittest.main()
