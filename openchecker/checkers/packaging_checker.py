import csv
import io
import re
import yaml
from typing import List, Dict, Tuple, Any
from pathlib import Path
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager

COMMAND = 'packaging-checker'

def _yaml_mapping_values(node):
    """Read mapping nodes without constructing values or losing source marks."""
    if not isinstance(node, yaml.MappingNode):
        return {}
    return {key.value: value for key, value in node.value
            if isinstance(key, yaml.ScalarNode)}


def _enabled_or_expression(node):
    if not isinstance(node, yaml.ScalarNode):
        return False
    return node.value.strip().lower() == 'true' or '${{' in node.value


def _publishing_docker_outputs(node):
    """Recognize registry exporters and image exporters with push enabled."""
    if not isinstance(node, yaml.ScalarNode):
        return False
    if '${{' in node.value:
        # The workflow can select a publishing exporter at execution time.
        return True
    for fields in csv.reader(io.StringIO(node.value), skipinitialspace=True):
        options = dict(field.strip().split('=', 1) for field in fields if '=' in field)
        if options.get('type') == 'registry':
            return True
        if (options.get('type') == 'image'
                and options.get('push', '').lower() == 'true'):
            return True
    return False


def _docker_publication_line(content):
    """Find a Docker action step configured to publish, keeping its source line.

    Action presence alone is insufficient: push defaults to false. Expressions
    are retained as potential publication; this scanner does not evaluate them.
    """
    workflow = yaml.compose(content, Loader=yaml.SafeLoader)
    jobs = _yaml_mapping_values(_yaml_mapping_values(workflow).get('jobs'))
    for job in jobs.values():
        steps = _yaml_mapping_values(job).get('steps')
        if not isinstance(steps, yaml.SequenceNode):
            continue
        for step in steps.value:
            values = _yaml_mapping_values(step)
            action = values.get('uses')
            if not isinstance(action, yaml.ScalarNode) or not re.fullmatch(
                    r'docker/build-push-action@\S+', action.value, re.IGNORECASE):
                continue
            inputs = _yaml_mapping_values(values.get('with'))
            if (_enabled_or_expression(inputs.get('push'))
                    or _publishing_docker_outputs(inputs.get('outputs'))):
                return action.start_mark.line + 1
    return 0


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
    return 1


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
        
        docker_line = _docker_publication_line(content)
        lines = content.split('\n')
        if docker_line:
            return create_workflow_match(True, file_path, docker_line)
        
        # 检查每个打包模式
        for pattern_group in packaging_patterns:
            if _match_pattern_group(content, lines, pattern_group):
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
