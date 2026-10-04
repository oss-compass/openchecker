from checkers.dependency_update_tool_checker import _check_dependency_files


def test_dependabot_is_only_reported_from_github_directory(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "dependabot.yml").write_text("version: 2", encoding="utf-8")
    assert _check_dependency_files(str(tmp_path)) == []

    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "dependabot.yaml").write_text("version: 2", encoding="utf-8")
    tools = _check_dependency_files(str(tmp_path))
    assert len(tools) == 1
    assert tools[0]["name"] == "Dependabot"
    assert tools[0]["files"][0]["path"].replace("\\", "/") == ".github/dependabot.yaml"
