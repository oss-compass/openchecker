from pathlib import Path

from openchecker.checkers.pinned_dependencies_checker import _collect_docker_dependencies


def test_compose_service_images_are_collected(tmp_path):
    (tmp_path / 'compose.yaml').write_text(
        'services:\n  api:\n    image: nginx:latest\n  worker:\n    build: .\n'
        'x-example:\n  image: ignored:latest\n', encoding='utf-8'
    )
    (tmp_path / 'Dockerfile').write_text('FROM python:3.12\n', encoding='utf-8')

    dependencies = _collect_docker_dependencies(Path(tmp_path))

    assert {(item['name'], item['version']) for item in dependencies} == {
        ('nginx', 'latest'), ('python', '3.12')
    }
    assert next(item for item in dependencies if item['name'] == 'nginx')['is_pinned'] is False
