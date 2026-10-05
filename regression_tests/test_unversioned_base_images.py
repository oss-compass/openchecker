from pathlib import Path

from checkers.pinned_dependencies_checker import _collect_docker_dependencies


def test_unversioned_base_images_are_reported_as_unpinned(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\nFROM alpine\nFROM ubuntu\nFROM debian\n", encoding="utf-8")

    dependencies = _collect_docker_dependencies(tmp_path)

    assert [item["name"] for item in dependencies] == ["alpine", "ubuntu", "debian"]
    assert all(item["version"] == "latest" and item["is_pinned"] is False for item in dependencies)
