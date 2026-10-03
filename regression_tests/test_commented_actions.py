from openchecker.checkers.pinned_dependencies_checker import _collect_actions


def test_commented_uses_is_not_a_dependency(tmp_path):
    workflow_dir = tmp_path / '.github' / 'workflows'
    workflow_dir.mkdir(parents=True)
    (workflow_dir / 'build.yml').write_text(
        'name: Build\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n'
        '    steps:\n      # - uses: fake/action@main\n'
        '      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n',
        encoding='utf-8'
    )

    dependencies = _collect_actions(tmp_path, 'github')

    assert len(dependencies) == 1
    assert dependencies[0]['name'] == 'actions/checkout'
    assert dependencies[0]['line_number'] == 8
