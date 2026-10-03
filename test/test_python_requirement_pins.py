from openchecker.checkers.pinned_dependencies_checker import _parse_requirements_file


def test_exact_requirements_with_extras_and_markers_are_pinned(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "requests[socks]==2.31.0\n"
        "package==1.0 ; python_version >= '3.9'\n"
        "wildcard==1.*\n"
        "compatible~=2.0\n"
        "arbitrary===1.0\n"
        "range>=1,<2\n",
        encoding="utf-8",
    )

    dependencies = {item["name"]: item for item in _parse_requirements_file(requirements)}

    assert {name for name, item in dependencies.items() if item["is_pinned"]} == {
        "requests", "package"
    }
