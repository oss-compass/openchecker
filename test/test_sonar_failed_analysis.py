import json
import unittest
from unittest.mock import Mock, patch

from checkers import sonar_checker


class SonarFailedAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "host": "https://sonar.example",
            "report_max_wait_time_s": "30",
            "report_check_interval_s": "1",
        }
        self.measures = {
            "component": {"key": "github_example_repo", "measures": [
                {"metric": "coverage", "value": "90.0"}
            ]}
        }
        self.get = self.enter_patch(patch.object(sonar_checker.requests, "get"))
        self.enter_patch(patch.object(sonar_checker.time, "sleep"))

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def response(self, payload):
        return Mock(status_code=200, text=json.dumps(payload))

    def query(self):
        return sonar_checker._query_sonar_measures("github_example_repo", self.config)

    def test_failed_and_canceled_tasks_do_not_return_old_measures(self):
        for status in ("FAILED", "CANCELED"):
            with self.subTest(status=status):
                self.get.reset_mock()
                task = {"id": "latest-task", "status": status}
                self.get.side_effect = [
                    self.response({"queue": [], "current": task}),
                    self.response(self.measures),
                ]

                result = self.query()

                self.assertIn("error", result)
                self.assertNotIn("component", result)
                self.assertEqual(result["analysis_error"]["status"], status)
                self.assertEqual(result["analysis_error"]["task"], task)
                self.get.assert_called_once()
                self.assertTrue(self.get.call_args.args[0].endswith("/api/ce/component"))

    def test_in_progress_task_can_finish_successfully(self):
        self.get.side_effect = [
            self.response({"current": {"status": "IN_PROGRESS"}}),
            self.response({"current": {"status": "SUCCESS"}}),
            self.response(self.measures),
        ]

        self.assertEqual(self.query(), self.measures)
        self.assertEqual(self.get.call_count, 3)

    def test_queued_task_takes_precedence_over_previous_failure(self):
        self.get.side_effect = [
            self.response({"queue": [{"id": "new", "status": "PENDING"}],
                           "current": {"id": "old", "status": "FAILED"}}),
            self.response({"queue": [], "current": {"id": "new", "status": "SUCCESS"}}),
            self.response(self.measures),
        ]

        self.assertEqual(self.query(), self.measures)
        self.assertEqual(self.get.call_count, 3)

    def test_public_checker_keeps_failure_in_scan_payload(self):
        self.get.side_effect = [
            self.response({"queue": [], "current": {"id": "latest", "status": "FAILED"}}),
            self.response(self.measures),
        ]
        payload = {"scan_results": {}}
        with patch.object(sonar_checker, "_check_sonar_project_exists", return_value=True), \
                patch.object(sonar_checker, "shell_exec", return_value=(b"uploaded", None)):
            sonar_checker.sonar_checker(
                "https://github.com/example/repo", payload, {"SonarQube": self.config}
            )

        result = payload["scan_results"]["sonar-scanner"]
        self.assertIn("error", result)
        self.assertNotIn("component", result)
        self.assertEqual(result["analysis_error"]["status"], "FAILED")
        self.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
