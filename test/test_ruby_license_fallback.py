import json
import unittest
from unittest.mock import patch

from openchecker import agent


def package(licenses, vcs_url):
    return {"purl": "pkg:gem/example@1", "declared_licenses": licenses,
            "vcs_processed": {"url": vcs_url}}


class RubyLicenseFallbackTests(unittest.TestCase):
    def test_dependency_metadata_cannot_inject_shell_commands(self):
        item = package([], "https://github.com/example/repo;touch /tmp/unwanted")
        data = {"analyzer": {"result": {"packages": [item]}}}

        with patch.object(agent, "shell_exec") as execute:
            agent.ruby_licenses(data)

        execute.assert_not_called()
        self.assertEqual(item["declared_licenses"], [])

    def test_missing_license_field_accepts_detected_license(self):
        item = package(None, "https://github.com/example/repo.git")
        data = {"analyzer": {"result": {"packages": [item]}}}
        report = json.dumps({"licenses": [{"meta": {"title": "MIT"}}]}).encode()

        with patch.object(agent, "shell_exec", return_value=(report, None)) as execute:
            agent.ruby_licenses(data)

        self.assertEqual(item["declared_licenses"], ["MIT"])
        script = execute.call_args.args[0]
        self.assertIn("https://github.com/example/repo", script)

    def test_undetected_license_remains_unlicensed(self):
        item = package([], "https://github.com/example/repo")
        data = {"analyzer": {"result": {"packages": [item]}}}

        with patch.object(agent, "shell_exec", return_value=(b'{"licenses": []}', None)):
            agent.ruby_licenses(data)

        self.assertEqual(item["declared_licenses"], [])

    def test_missing_license_without_match_stays_in_unlicensed_report(self):
        item = package(None, "https://github.com/example/repo")
        data = {"analyzer": {"result": {"packages": [item]}}}

        with patch.object(agent, "shell_exec", return_value=(b'{"licenses": []}', None)):
            result = agent.dependency_checker_output_process(json.dumps(data).encode())

        self.assertEqual(result["packages_without_license_detect"], [item["purl"]])
        self.assertEqual(result["packages_with_license_detect"], [])


if __name__ == "__main__":
    unittest.main()
