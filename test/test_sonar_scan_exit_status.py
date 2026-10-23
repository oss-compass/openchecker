"""Run the Sonar shell template with real Bash pipelines and GNU timeout.

The scanner/build executables are controlled local programs; no SonarQube
server or project build is needed. Run with PYTHONPATH=openchecker.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from constans import shell_script_handlers


@unittest.skipUnless(os.name == "posix" and shutil.which("bash") and shutil.which("timeout"),
                     "Bash and GNU timeout are required")
class TestSonarScanExitStatus(unittest.TestCase):
    modes = ("general", "maven", "gradle", "gradle-fallback")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "sample"
        self.project.mkdir()
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        # Each pipeline's first command must actually exit with the requested
        # status. For timeout tests, GNU timeout terminates this real process.
        executable = """#!/bin/bash
if [ "$1" = tasks ]; then
    if [ "$SCAN_MODE" = gradle ]; then
        echo sonarqube
    fi
    exit 0
fi
echo "scanner diagnostic: $SCAN_MODE" >&2
if [ "$SCAN_SLEEP" = yes ]; then
    sleep 30
fi
exit "$SCAN_EXIT_CODE"
"""
        for path in (self.bin_dir / "sonar-scanner", self.bin_dir / "mvn",
                     self.project / "gradlew"):
            path.write_text(executable, encoding="utf-8")
            path.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(PATH=str(self.bin_dir) + os.pathsep + self.env["PATH"],
                        SCAN_EXIT_CODE="0", SCAN_SLEEP="no")
        # Do not inherit shell options that could hide the original bug.
        self.env.pop("SHELLOPTS", None)
        self.env.pop("BASH_ENV", None)

    def prepare_mode(self, mode):
        for name in ("pom.xml", "build.gradle"):
            path = self.project / name
            if path.exists():
                path.unlink()
        if mode == "maven":
            (self.project / "pom.xml").write_text("<project/>", encoding="utf-8")
        elif mode.startswith("gradle"):
            (self.project / "build.gradle").touch()
        self.env["SCAN_MODE"] = mode

    def run_scan(self, timeout="5"):
        script = shell_script_handlers["sonar-scanner"].format(
            project_url="https://github.com/example/sample.git",
            sonar_project_name="github_example_sample",
            sonar_host="http://localhost", sonar_port="9000",
            sonar_token="unused", scan_timeout_s=timeout,
        )
        return subprocess.run(
            [shutil.which("bash"), "-c", script], cwd=self.root,
            env=self.env, capture_output=True, encoding="utf-8", timeout=10,
        )

    def test_failed_scans_are_not_reported_as_success(self):
        self.env["SCAN_EXIT_CODE"] = "23"
        for mode in self.modes:
            with self.subTest(mode=mode):
                self.prepare_mode(mode)
                result = self.run_scan()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("scanner diagnostic: " + mode, result.stderr)
                self.assertIn("23", result.stderr)
                self.assertNotIn("扫描成功", result.stdout)

    def test_successful_scans_are_preserved(self):
        for mode in self.modes:
            with self.subTest(mode=mode):
                self.prepare_mode(mode)
                result = self.run_scan()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("扫描成功", result.stdout)
                self.assertIn("scanner diagnostic: " + mode, result.stderr)

    def test_timeouts_reach_the_timeout_handler(self):
        self.env["SCAN_SLEEP"] = "yes"
        for mode in self.modes:
            with self.subTest(mode=mode):
                self.prepare_mode(mode)
                result = self.run_scan(timeout="0.2")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("扫描超时", result.stderr)
                self.assertNotIn("扫描成功", result.stdout)

    def test_checker_does_not_query_old_measures_after_scanner_failure(self):
        from checkers import sonar_checker

        self.env["SCAN_EXIT_CODE"] = "23"
        original_dir = Path.cwd()
        self.addCleanup(os.chdir, original_dir)
        os.chdir(self.root)
        for mode in self.modes:
            with self.subTest(mode=mode):
                self.prepare_mode(mode)
                payload = {"scan_results": {}}
                # The shell template and common.shell_exec execute normally.
                # Only server calls are isolated; an old metric is supplied to
                # expose the false success if the query is wrongly reached.
                with patch.dict(os.environ, self.env, clear=True), \
                        patch.object(sonar_checker, "_check_sonar_project_exists", return_value=True), \
                        patch.object(sonar_checker, "_query_sonar_measures", return_value={
                            "component": {"measures": [{"metric": "bugs", "value": "0"}]}
                        }) as query:
                    sonar_checker.sonar_checker(
                        "https://github.com/example/sample.git", payload,
                        {"SonarQube": {"host": "http://localhost", "scan_timeout_s": "5"}},
                    )
                query.assert_not_called()
                self.assertIn("23", payload["scan_results"]["sonar-scanner"]["error"])
                self.assertNotIn("component", payload["scan_results"]["sonar-scanner"])


if __name__ == "__main__":
    unittest.main()
