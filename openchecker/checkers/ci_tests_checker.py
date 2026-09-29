import re
from typing import Any, Dict, List, Optional

from common import get_platform_type, list_workflow_files
from logger import get_logger
from platform_adapter import platform_manager

COMMAND = 'ci-tests-checker'

logger = get_logger('openchecker.checkers.ci_tests_checker')

# 各生态常见的测试命令正则（大小写不敏感）。
# 这里只匹配真正“执行测试”的命令，而不是构建/发布命令，
# 以对齐 OSSF Scorecard 的 CI-Tests 语义：
# https://github.com/ossf/scorecard/blob/main/docs/checks.md#ci-tests
TEST_COMMAND_PATTERNS: Dict[str, List[str]] = {
    'python': [
        r'\bpytest\b',
        r'\bpython[0-9.]*\s+-m\s+(pytest|unittest|nose)\b',
        r'\btox\b',
        r'\bnox\b',
    ],
    'nodejs': [
        r'\bnpm\s+(run\s+)?test\b',
        r'\byarn\s+(run\s+)?test\b',
        r'\bpnpm\s+(run\s+)?test\b',
        r'\bjest\b',
        r'\bvitest\b',
        r'\bmocha\b',
    ],
    'java': [
        r'\bmvn\b[^\n]*\btest\b',
        r'\bmvn\b[^\n]*\bverify\b',
        r'\bgradle(w)?\b[^\n]*\btest\b',
        r'\bsbt\s+test\b',
    ],
    'go': [
        r'\bgo\s+test\b',
    ],
    'rust': [
        r'\bcargo\s+test\b',
    ],
    'ruby': [
        r'\brake\s+test\b',
        r'\brspec\b',
        r'\bbundle\s+exec\s+rspec\b',
    ],
    'dotnet': [
        r'\bdotnet\s+test\b',
    ],
    'php': [
        r'\bphpunit\b',
    ],
}


def create_workflow_match(
    matched: bool,
    file_path: str,
    line_number: int,
    ecosystems: Optional[List[str]] = None,
    matches: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    创建工作流匹配结果。

    Args:
        matched: 该工作流是否包含测试命令
        file_path: 工作流文件路径
        line_number: 首个命中的行号（1-based），未命中为 0
        ecosystems: 命中的生态列表（已去重排序）
        matches: 每个生态在每个命中行上的一条记录

    Returns:
        与其它 checker 结构保持一致的结果字典
    """
    return {
        "matched": matched,
        "file_path": file_path,
        "line_number": line_number,
        "ecosystems": ecosystems or [],
        "matches": matches or [],
    }


def _find_pattern_line(lines: List[str], pattern: str) -> int:
    """
    返回首个匹配 pattern 的行号（1-based），未匹配时返回 0。

    Args:
        lines: 文件行列表
        pattern: 正则表达式

    Returns:
        行号（1-based），未匹配时为 0
    """
    for index, line in enumerate(lines):
        if re.search(pattern, line, re.IGNORECASE):
            return index + 1
    return 0


def _all_test_command_pattern() -> str:
    """
    把所有生态的测试命令正则合并为一个 OR 表达式。

    先做一次整体预筛选，可以避免对每个工作流逐条正则匹配，
    只有真正可能命中的文件才会进入逐行扫描。
    """
    patterns = []
    for ecosystem_patterns in TEST_COMMAND_PATTERNS.values():
        patterns.extend(ecosystem_patterns)
    return "|".join("(?:{0})".format(pattern) for pattern in patterns)


def _collect_test_command_matches(lines: List[str]) -> List[Dict[str, Any]]:
    """
    逐行扫描工作流内容，返回每个生态在每个命中行上的一条记录。

    同一生态的多个正则可能命中同一行（例如 `python -m pytest` 会同时
    命中 pytest 与 python -m ... 两条规则），因此内层匹配到第一个
    模式后就 break，保证“每个生态每行只报告一次”，避免结果重复。
    """
    matches = []
    for index, line in enumerate(lines):
        for ecosystem, patterns in TEST_COMMAND_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    matches.append({
                        "ecosystem": ecosystem,
                        "line_number": index + 1,
                        "pattern": pattern,
                        "line": line.strip(),
                    })
                    break
    return matches


def is_ci_test_workflow(file_path: str) -> Dict[str, Any]:
    """
    检查单个 CI 工作流是否会运行测试。

    Args:
        file_path: 工作流文件路径

    Returns:
        Dict[str, Any]: 匹配结果。文件不存在、内容为空或读取失败时
        返回 matched=False 而不会抛出异常，避免单个坏文件中断整个扫描。
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
            content = handle.read()

        # 空文件或只有空白字符的工作流不可能定义测试步骤
        if not content.strip():
            return create_workflow_match(False, file_path, 0)

        lines = content.split('\n')
        combined_pattern = _all_test_command_pattern()

        # 先用合并后的 OR 表达式快速判断，未命中则无需逐行逐条匹配
        if not re.search(combined_pattern, content, re.IGNORECASE):
            return create_workflow_match(False, file_path, 0)

        matches = _collect_test_command_matches(lines)
        if not matches:
            return create_workflow_match(False, file_path, 0)

        ecosystems = sorted({match["ecosystem"] for match in matches})
        return create_workflow_match(
            matched=True,
            file_path=file_path,
            line_number=_find_pattern_line(lines, combined_pattern),
            ecosystems=ecosystems,
            matches=matches,
        )
    except Exception:
        return create_workflow_match(False, file_path, 0)


def ci_tests_checker(project_url: str, res_payload: dict) -> None:
    """
    执行 CI-Tests 检查。
    指标详情介绍
    https://github.com/ossf/scorecard/blob/main/docs/checks.md#ci-tests

    与 scorecard-score 命令不同，本检查只依赖平台适配器发现的工作流文件，
    因此对 Gitee/GitCode 以及无法运行 scorecard 二进制的离线场景同样可用。
    """
    results = {
        "num_workflows": 0,
        "num_workflows_with_tests": 0,
        "has_ci_tests": False,
        "workflows": [],
    }

    try:
        owner_name, repo_path = platform_manager.parse_project_url(project_url)
        platform_type = get_platform_type(project_url)
        workflow_files = list_workflow_files(repo_path, platform_type)

        for workflow_file in workflow_files:
            workflow_result = is_ci_test_workflow(workflow_file)
            results["num_workflows"] += 1
            if workflow_result["matched"]:
                results["num_workflows_with_tests"] += 1
            results["workflows"].append(workflow_result)

        results["has_ci_tests"] = results["num_workflows_with_tests"] > 0
    except Exception as e:
        # 与 agent 中其它 checker 一致：失败时也写入结果，只是附带
        # error 字段并把计数器归零，便于上层统一展示与告警。
        logger.error(f"ci-tests-checker job failed: {project_url}, error: {e}")
        results = {
            "num_workflows": 0,
            "num_workflows_with_tests": 0,
            "has_ci_tests": False,
            "workflows": [],
            "error": str(e),
        }

    res_payload["scan_results"][COMMAND] = results
