from pathlib import Path

from checkers.pinned_dependencies_checker import _collect_docker_dependencies


def test_from_platform_option_is_not_treated_as_an_image(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text(
        "FROM --platform=linux/amd64 python:3.11 AS build\nFROM node:20\n", encoding="utf-8"
    )

    dependencies = _collect_docker_dependencies(tmp_path)

    assert [(item["name"], item["version"]) for item in dependencies] == [
        ("python", "3.11"), ("node", "20")
    ]
