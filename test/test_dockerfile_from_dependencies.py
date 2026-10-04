import tempfile
import unittest
from pathlib import Path

from checkers.pinned_dependencies_checker import (
    _collect_docker_dependencies,
    analyze_pinning,
    collect_dependencies,
)


class DockerfileFromDependenciesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_dockerfile(self, content, name="Dockerfile"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_untagged_distribution_images_are_unpinned_dependencies(self):
        self.write_dockerfile("FROM alpine\nFROM ubuntu\nFROM debian\n")

        dependencies = collect_dependencies(str(self.root), "github")

        self.assertEqual([item["name"] for item in dependencies],
                         ["alpine", "ubuntu", "debian"])
        self.assertTrue(all(item["version"] == "latest" for item in dependencies))
        analysis = analyze_pinning(dependencies)
        self.assertEqual(analysis["unpinned_count"], 3)
        self.assertEqual(len(analysis["findings"]), 3)

    def test_platform_flag_is_not_an_image(self):
        for platform in ("linux/amd64", "$BUILDPLATFORM", "${TARGETPLATFORM}"):
            with self.subTest(platform=platform):
                line = f"FROM --platform={platform} python:3.12 AS build"
                path = self.write_dockerfile("# syntax=docker/dockerfile:1\n" + line + "\n")

                dependencies = _collect_docker_dependencies(self.root)

                self.assertEqual(len(dependencies), 1)
                self.assertEqual(dependencies[0]["name"], "python")
                self.assertEqual(dependencies[0]["version"], "3.12")
                self.assertEqual(dependencies[0]["file_path"], str(path))
                self.assertEqual(dependencies[0]["line_number"], 2)
                self.assertEqual(dependencies[0]["snippet"], line)

    def test_reused_stages_are_not_external_dependencies(self):
        self.write_dockerfile(
            "FROM python:3.12 AS build\n"
            "FROM build AS test\n"
            "FROM --platform=$BUILDPLATFORM test AS final\n"
            "FROM scratch\n"
        )

        dependencies = _collect_docker_dependencies(self.root)

        self.assertEqual([item["name"] for item in dependencies], ["python"])

    def test_stage_names_are_local_to_each_dockerfile(self):
        self.write_dockerfile("FROM python:3.12 AS build\nFROM build\n")
        self.write_dockerfile("FROM build\n", "Dockerfile.other")

        dependencies = _collect_docker_dependencies(self.root)

        self.assertCountEqual([item["name"] for item in dependencies],
                              ["python", "build"])
        external_build = next(item for item in dependencies if item["name"] == "build")
        self.assertEqual(Path(external_build["file_path"]).name, "Dockerfile.other")

    def test_stage_definition_does_not_hide_its_own_base_image(self):
        self.write_dockerfile("FROM alpine AS alpine\nFROM alpine\n")

        dependencies = _collect_docker_dependencies(self.root)

        self.assertEqual([item["name"] for item in dependencies], ["alpine"])
        self.assertEqual(dependencies[0]["line_number"], 1)

    def test_comments_and_scratch_are_ignored_with_mixed_case_instructions(self):
        self.write_dockerfile(
            "# FROM ignored:latest\n"
            "  from python:3.12 as build\n"
            "FROM build\n"
            "FROM scratch AS empty\n"
            "FROM empty\n"
        )

        dependencies = _collect_docker_dependencies(self.root)

        self.assertEqual([item["name"] for item in dependencies], ["python"])


if __name__ == "__main__":
    unittest.main()
