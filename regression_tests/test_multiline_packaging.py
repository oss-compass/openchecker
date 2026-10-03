from openchecker.checkers.packaging_checker import is_packaging_workflow


def test_publish_command_in_yaml_block_is_detected(tmp_path):
    workflow = tmp_path / 'publish.yml'
    workflow.write_text('''name: Publish
on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v4
        with:
          registry-url: https://registry.npmjs.org
      - run: |
          npm ci
          npm publish
''', encoding='utf-8')

    result = is_packaging_workflow(str(workflow))

    assert result['matched'] is True
    assert result['line_number'] == 7


def test_docker_publish_line_number_points_to_command(tmp_path):
    workflow = tmp_path / 'docker.yml'
    workflow.write_text('jobs:\n  release:\n    steps:\n      - run: |\n          docker build .\n          docker push example/app\n', encoding='utf-8')

    result = is_packaging_workflow(str(workflow))

    assert result['matched'] is True
    assert result['line_number'] == 6
