import re
import yaml
from typing import List, Dict, Tuple, Any
from pathlib import Path
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager

COMMAND = 'packaging-checker'

def _match_pattern_group(content: str, lines: List[str], pattern_group: Dict[str, str]) -> bool:
    """
    检查模式组是否匹配
    
    Args:
        content: 文件内容
        lines: 文件行列表
        pattern_group: 模式组
        
    Returns:
        是否匹配
    """
    # 如果只有一个模式，直接匹配
    if len(pattern_group) == 1:
        pattern = list(pattern_group.values())[0]
        return bool(re.search(pattern, content, re.IGNORECASE | re.MULTILINE))
    
    # 多个模式需要都匹配
    for pattern in pattern_group.values():
        if not re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            return False
    
    return True


def _find_pattern_line(lines: List[str], pattern: str) -> int:
    """
    查找模式匹配的行号
    
    Args:
        lines: 文件行列表
        pattern: 正则表达式模式
        
    Returns:
        行号 (1-based)
    """
    for i, line in enumerate(lines):
        if re.search(pattern, line, re.IGNORECASE):
            return i + 1
    if pattern.startswith('run:.*'):
        command_pattern = pattern[len('run:.*'):]
        for i, line in enumerate(lines):
            if re.search(command_pattern, line, re.IGNORECASE):
                return i + 1
    return 1


def _include_multiline_commands(content: str) -> str:
    """Expose YAML block commands to the existing publish patterns."""
    try:
        workflow = yaml.safe_load(content)
    except yaml.YAMLError:
        return content
    if not isinstance(workflow, dict) or not isinstance(workflow.get('jobs'), dict):
        return content
    command_lines = []
    for job in workflow['jobs'].values():
        if not isinstance(job, dict) or not isinstance(job.get('steps'), list):
            continue
        for step in job['steps']:
            if isinstance(step, dict) and isinstance(step.get('run'), str):
                command_lines.append('run: ' + ' '.join(step['run'].split()))
    return content + '\n' + '\n'.join(command_lines)


def create_workflow_match(matched: bool, file_path: str, line_number: int) -> Dict[str, Any]:
    """创建工作流匹配结果"""
    return {
        "matched": matched,
        "file_path": file_path,
        "line_number": line_number
    }


def is_packaging_workflow(file_path: str) -> Dict[str, Any]:
    """
    检查 Actions 工作流是否为打包工作流
    
    Args:
        file_path: 工作流文件路径
        
    Returns:
        Dict[str, Any]: 匹配结果
    """
    # 定义打包工作流的模式
    packaging_patterns = [
        # Node.js 打包
        {
            "setup": r"uses:\s*actions/setup-node",
            "registry": r"registry-url:\s*https://registry\.npmjs\.org",
            "publish": r"run:.*npm.*publish"
        },
        # Java Maven 打包
        {
            "setup": r"uses:\s*actions/setup-java",
            "publish": r"run:.*mvn.*deploy"
        },
        # Java Gradle 打包
        {
            "setup": r"uses:\s*actions/setup-java",
            "publish": r"run:.*gradle.*publish"
        },
        # Python 打包
        {
            "publish": r"uses:\s*pypa/gh-action-pypi-publish"
        },
        # Python semantic-release
        {
            "publish": r"uses:\s*relekang/python-semantic-release"
        },
        # Ruby 打包
        {
            "publish": r"run:.*gem.*push"
        },
        # NuGet 打包
        {
            "publish": r"run:.*nuget.*push"
        },
        # Docker 打包
        {
            "publish": r"run:.*docker.*push"
        },
        # Docker build-push-action
        {
            "publish": r"uses:\s*docker/build-push-action"
        },
        # Go 打包
        {
            "setup": r"uses:\s*actions/setup-go",
            "publish": r"uses:\s*goreleaser/goreleaser-action"
        },
        # Rust 打包
        {
            "publish": r"run:.*cargo.*publish"
        },
        # Ko 容器打包
        {
            "publish": r"uses:\s*imjasonh/setup-ko"
        },
        # Ko 容器打包 (备选)
        {
            "publish": r"uses:\s*ko-build/setup-ko"
        },
        # Semantic Release
        {
            "publish": r"run:.*npx.*semantic-release"
        },
        # Scala sbt-ci-release
        {
            "publish": r"run:.*sbt.*ci-release"
        }
    ]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        searchable_content = _include_multiline_commands(content)
        
        # 检查每个打包模式
        for pattern_group in packaging_patterns:
            if _match_pattern_group(searchable_content, lines, pattern_group):
                line_num = _find_pattern_line(lines, list(pattern_group.values())[0])
                return create_workflow_match(
                    matched=True,
                    file_path=file_path,
                    line_number=line_num
                )
        
        return create_workflow_match(
            matched=False,
            file_path=file_path,
            line_number=0
        )
        
    except Exception as e:
        return create_workflow_match(
            matched=False,
            file_path=file_path,
            line_number=0
        )



def packaging_checker(project_url: str, res_payload: dict) -> None:
    """
    执行打包检查
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#packaging
    """
    
    packaging_workflow_data = []
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)
    workflow_files = list_workflow_files(repo_path, platform_type)
    for file_path in workflow_files:
        packaging_workflow = is_packaging_workflow(file_path)   
        packaging_workflow_data.append(packaging_workflow) 
    
    res_payload["scan_results"][COMMAND] = packaging_workflow_data
