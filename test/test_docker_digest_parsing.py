from openchecker.checkers.pinned_dependencies_checker import _is_docker_image_pinned, _parse_docker_image


def test_docker_image_digest_is_kept_with_algorithm():
    digest = "sha256:" + "a" * 64
    assert _parse_docker_image("registry.example:5000/team/image@" + digest) == ("registry.example:5000/team/image", digest)
    assert _is_docker_image_pinned(digest)
    assert not _is_docker_image_pinned("sha256:" + "z" * 64)


def test_registry_port_is_not_treated_as_an_image_tag():
    assert _parse_docker_image("registry.example:5000/team/image") == ("registry.example:5000/team/image", "latest")
