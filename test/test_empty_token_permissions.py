import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openchecker.checkers import token_permissions_checker as checker


class EmptyTokenPermissionsTests(unittest.TestCase):
    def test_top_level_empty_permissions(self):
        result = checker._extract_top_level_permissions({"permissions": {}}, "ci.yml")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["permission_level"], checker.PERMISSION_LEVEL_NONE)
        self.assertEqual(result[0]["location_type"], checker.PERMISSION_LOCATION_TOP)

    def test_job_empty_permissions_override_top_level(self):
        workflow = {"permissions": "write-all", "jobs": {"test": {"permissions": {}}}}
        result = checker._extract_job_level_permissions(workflow, "ci.yml")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["permission_level"], checker.PERMISSION_LEVEL_NONE)
        self.assertEqual(result[0]["job_name"], "test")

    def test_empty_permission_workflow_is_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("permissions: {}\njobs:\n  test:\n    permissions: {}\n", encoding="utf-8")
            payload = {"scan_results": {}}
            with patch.object(checker.platform_manager, "parse_project_url", return_value=("owner/repo", directory)), patch.object(checker, "list_workflow_files", return_value=[str(workflow)]):
                checker.token_permissions_checker("https://github.com/owner/repo", payload)
            result = payload["scan_results"][checker.COMMAND]
            self.assertEqual(result["num_workflows"], 1)
            self.assertEqual(len(result["token_permissions"]), 2)
            self.assertTrue(all(item["permission_level"] == "none" for item in result["token_permissions"]))

    def test_omitted_permissions_remain_undeclared(self):
        result = checker._extract_top_level_permissions({}, "ci.yml")
        self.assertEqual(result[0]["permission_level"], checker.PERMISSION_LEVEL_UNDECLARED)

    def test_nonempty_permissions_are_unchanged(self):
        for permissions, expected in [("read-all", ["read"]), ("write-all", ["write"]), ({"contents": "read", "actions": "none"}, ["read", "none"])]:
            with self.subTest(permissions=permissions):
                top = checker._extract_top_level_permissions({"permissions": permissions}, "ci.yml")
                jobs = checker._extract_job_level_permissions({"jobs": {"test": {"permissions": permissions}}}, "ci.yml")
                self.assertEqual([item["permission_level"] for item in top], expected)
                self.assertEqual([item["permission_level"] for item in jobs], expected)


if __name__ == "__main__":
    unittest.main()
