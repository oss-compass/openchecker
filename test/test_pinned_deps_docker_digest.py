"""Regression tests for pinned_dependencies_checker's Docker digest handling.

_parse_docker_image checked for ':' before '@', so a digest-pinned
image reference (FROM image@sha256:<64 hex>) - the canonical way to
pin a Docker image - was split at the ':' inside 'sha256:' instead of
at '@'. The dependency was then recorded with a mangled name
('image@sha256') and a bare hex digest as the version, which
_is_version_pinned does not recognize, so digest-pinned images were
reported as unpinned.
"""
from checkers import pinned_dependencies_checker as pdc

DIGEST = "sha256:" + "a1" * 32


def make_repo(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    return repo


def collect(repo):
    return pdc.collect_dependencies(str(repo), "github")


def docker_deps(deps):
    return [d for d in deps if d["dep_type"] == "Docker"]


def test_digest_pinned_image_is_reported_as_pinned(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "Dockerfile").write_text(f"FROM python@{DIGEST}\n", encoding="utf-8")
    deps = collect(repo)
    assert len(docker_deps(deps)) == 1
    dep = docker_deps(deps)[0]
    assert dep["name"] == "python"
    assert dep["version"] == DIGEST
    assert dep["is_pinned"] is True
    analysis = pdc.analyze_pinning(deps)
    assert analysis["pinned_count"] == 1
    assert analysis["unpinned_count"] == 0


def test_tag_pinned_image_is_still_reported_as_pinned(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    deps = collect(repo)
    assert len(docker_deps(deps)) == 1
    dep = docker_deps(deps)[0]
    assert dep["name"] == "python"
    assert dep["version"] == "3.11-slim"
    assert dep["is_pinned"] is True


def test_floating_tag_is_reported_as_unpinned(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "Dockerfile").write_text("FROM node:latest\n", encoding="utf-8")
    deps = collect(repo)
    assert len(docker_deps(deps)) == 1
    dep = docker_deps(deps)[0]
    assert dep["is_pinned"] is False


def test_registry_with_port_is_parsed_correctly(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "Dockerfile").write_text(
        "FROM myregistry.example:5000/app:2.1\n", encoding="utf-8")
    deps = collect(repo)
    assert len(docker_deps(deps)) == 1
    dep = docker_deps(deps)[0]
    assert dep["name"] == "myregistry.example:5000/app"
    assert dep["version"] == "2.1"
    assert dep["is_pinned"] is True
