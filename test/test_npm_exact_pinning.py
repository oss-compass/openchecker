import json

from openchecker.checkers.pinned_dependencies_checker import _parse_package_json


def test_npm_specs_only_count_exact_versions_as_pinned(tmp_path):
    package_file = tmp_path / "package.json"
    package_file.write_text(json.dumps({"dependencies": {
        "exact": "1.2.3",
        "prerelease": "2.0.0-rc.1",
        "latest": "latest",
        "major-range": "1",
        "branch": "github:owner/repo#main",
        "local": "file:../local",
        "caret": "^1.2.3",
    }}), encoding="utf-8")

    dependencies = {item["name"]: item for item in _parse_package_json(package_file)}
    assert {name for name, item in dependencies.items() if item["is_pinned"]} == {
        "exact", "prerelease"
    }
