import re
import yaml
from typing import List, Dict, Tuple, Any
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager

COMMAND = 'ci-tests-checker'

# CI 测试调用正则映射表：工具名 -> 匹配测试命令的正则表达式
# 覆盖主流生态的测试入口，与 OSSF Scorecard 的 CI-Tests 检查语义保持一致，
# 目的是从 workflow 的 run 指令中识别“项目确实在 CI 里跑测试”这一事实。
CI_TEST_PATTERNS = {
    "pytest": r"(python -m )?pytest|py\.test",
    "node": r"npm (run )?test|yarn test|pnpm test",
    "go": r"go test",
    "maven": r"mvn .*(test|verify)",
    "gradle": r"(\./)?gradlew? .*test",
    "cargo": r"cargo test",
    "make": r"make test",
    "tox": r"tox",
    "dotnet": r"dotnet test",
    "ruby": r"(bundle exec )?(rspec|rake test)",
    "sbt": r"sbt test",
}


def _match_ci_test_tools(run_command: str) -> List[str]:
    """
    在单条 run 指令中匹配 CI 测试调用，返回命中的工具名列表。

    使用 search 而不是 match：测试命令经常出现在
    `cd subdir && pytest -q` 这类复合指令的中间，不能用整段匹配。
    """
    matched_tools = []
    for tool_name, pattern in CI_TEST_PATTERNS.items():
        if re.search(pattern, run_command):
            matched_tools.append(tool_name)
    return matched_tools


def _parse_workflow_for_ci_tests(workflow_content: str) -> List[Dict[str, str]]:
    """
    解析工作流内容，检测其中运行的 CI 测试。

    遍历 jobs.*.steps[].run，为每个命中的测试命令记录
    {"tool_name": ..., "snippet": ...}，snippet 保留原始 run 指令作为证据。
    当 YAML 解析失败时退化为对原始文本做正则匹配，避免因语法问题漏报。
    """
    detected_tests = []

    try:
        workflow = yaml.safe_load(workflow_content)
        if not isinstance(workflow, dict):
            return detected_tests

        jobs = workflow.get("jobs", {})
        if not isinstance(jobs, dict):
            return detected_tests

        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            if not isinstance(steps, list):
                continue

            for step in steps:
                if not isinstance(step, dict):
                    continue

                run_command = step.get("run", "")
                if not isinstance(run_command, str) or not run_command.strip():
                    continue

                for tool_name in _match_ci_test_tools(run_command):
                    detected_tests.append({
                        "tool_name": tool_name,
                        "snippet": run_command.strip(),
                    })

    except yaml.YAMLError:
        # YAML 解析失败时退化为原始文本匹配，保证坏 YAML 也能给出证据
        for tool_name, pattern in CI_TEST_PATTERNS.items():
            match = re.search(pattern, workflow_content)
            if match:
                detected_tests.append({
                    "tool_name": tool_name,
                    "snippet": match.group(0).strip(),
                })

    return detected_tests


def detect_ci_test_workflows(repo_path: str, platform_type: str) -> List[Dict]:
    """
    检测工作流中运行的 CI 测试。

    返回每个命中测试命令的 {file_path, tool_name, snippet} 证据条目，
    供上层判断项目是否在 CI 中真实执行测试。
    """
    test_workflows = []
    workflow_files = list_workflow_files(repo_path, platform_type)
    for workflow_file in workflow_files:
        try:
            with open(workflow_file, 'r', encoding='utf-8') as f:
                workflow_content = f.read()

            for detected in _parse_workflow_for_ci_tests(workflow_content):
                test_workflows.append({
                    "file_path": str(workflow_file),
                    "tool_name": detected["tool_name"],
                    "snippet": detected["snippet"],
                })
        except Exception:
            # 单个工作流读取失败不应中断整体扫描，跳过继续处理其它文件
            continue

    return test_workflows


def ci_tests_checker(project_url: str, res_payload: dict) -> None:
    """
    CI-Tests 指标检测
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#ci-tests
    """
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)

    test_workflows = detect_ci_test_workflows(repo_path, platform_type)

    res_payload["scan_results"][COMMAND] = {
        "test_workflows": test_workflows,
        "has_ci_tests": bool(test_workflows),
    }
