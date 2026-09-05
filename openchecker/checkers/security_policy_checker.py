import os
import re
from typing import List, Dict, Tuple, Any
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager


COMMAND = 'security-policy-checker'


def find_security_policy_files(repo_path: str, platform_type: str) -> List[str]:
    """
    查找安全策略文件
    """
    # 支持的安全策略文件名模式（不区分大小写）
    security_file_patterns = [
        "security.md",
        "security.markdown", 
        "security.adoc",
        "security.rst",
        f".{platform_type}/security.md",
        f".{platform_type}/security.markdown",
        f".{platform_type}/security.adoc", 
        f".{platform_type}/security.rst",
        "docs/security.md",
        "docs/security.markdown",
        "docs/security.adoc",
        "docs/security.rst",
        "doc/security.rst"
    ]
    
    found_files = set()

    # glob 大小写敏感，upper() 只能匹配全大写文件名（如 SECURITY.MD），
    # 匹配不到 SECURITY.md 等常见命名，这里改为按目录实际条目做大小写不敏感匹配
    for pattern in security_file_patterns:
        sub_dir, file_name = os.path.split(pattern)
        search_dir = os.path.join(repo_path, sub_dir) if sub_dir else repo_path
        if not os.path.isdir(search_dir):
            continue
        for entry in os.listdir(search_dir):
            if entry.lower() == file_name:
                found_files.add(os.path.join(search_dir, entry))

    return sorted(found_files)


def analyze_security_policy_content(file_path: str) -> Dict:
    """
    分析安全策略文件内容，提取关键信息
    
    Args:
        file_path: 安全策略文件路径
        
    Returns:
        包含分析结果的字典
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return {
            'file_size': 0,
            'urls': [],
            'emails': [],
            'disclosure_keywords': []
        }
    
    # 正则表达式模式（与Go版本保持一致）
    url_pattern = r'(?:https?)://[a-zA-Z0-9./?=_%:-]*'
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}\b'
    disclosure_pattern = r'(?i)(\b[0-9]{1,4}\b|Disclos|Vuln)'
    
    # 提取信息
    urls = re.findall(url_pattern, content)
    emails = re.findall(email_pattern, content) 
    disclosure_matches = re.findall(disclosure_pattern, content)
    
    return {
        'file_size': len(content),
        'urls': urls,
        'emails': emails, 
        'disclosure_keywords': disclosure_matches
    }


def security_policy_checker(project_url: str, res_payload: dict) -> None:
    """ 
    Security-Policy 指标检测 
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#security_policy
    """
    
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)
    policy_files = find_security_policy_files(repo_path, platform_type)
    content_analysis = {}
    if policy_files:
        content_analysis = analyze_security_policy_content(policy_files[0])
    
    res_payload["scan_results"][COMMAND] = content_analysis