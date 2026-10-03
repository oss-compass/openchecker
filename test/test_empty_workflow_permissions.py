from unittest.mock import patch

from openchecker.checkers.token_permissions_checker import token_permissions_checker


def test_empty_permissions_maps_are_recorded_and_workflows_counted(tmp_path):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "empty.yml").write_text(
        "permissions: {}\njobs:\n  test:\n    permissions: {}\n",
        encoding="utf-8",
    )
    (workflow_dir / "read.yml").write_text(
        "permissions:\n  contents: read\n", encoding="utf-8"
    )
    payload = {"scan_results": {}}

    with patch("openchecker.checkers.token_permissions_checker.platform_manager") as platform:
        platform.parse_project_url.return_value = ("owner", str(tmp_path))
        token_permissions_checker("https://github.com/owner/repo", payload)

    result = payload["scan_results"]["token-permissions-checker"]
    assert result["num_workflows"] == 2
    assert [entry["permission_level"] for entry in result["token_permissions"]].count("none") == 2
    assert [entry["permission_level"] for entry in result["token_permissions"]].count("read") == 1
