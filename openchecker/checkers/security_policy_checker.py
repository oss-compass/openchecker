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
    file_names = {'security.md', 'security.markdown', 'security.adoc', 'security.rst'}
    directory_names = {f'.{platform_type}'.casefold(), 'docs', 'doc'}
    try:
        with os.scandir(repo_path) as entries:
            root_entries = list(entries)
    except OSError:
        return []

    directories = [repo_path]
    directories.extend(
        entry.path for entry in root_entries
        if entry.is_dir(follow_symlinks=False) and entry.name.casefold() in directory_names
    )
    found_files = []
    for directory in directories:
        try:
            with os.scandir(directory) as entries:
                found_files.extend(
                    entry.path for entry in entries
                    if entry.is_file(follow_symlinks=False) and entry.name.casefold() in file_names
                )
        except OSError:
            continue
    return found_files


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
    url_pattern = r'(http|https)://[a-zA-Z0-9./?=_%:-]*'
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}\b'
    disclosure_pattern = r'(?i)(\b*[0-9]{1,4}\b|(Disclos|Vuln))'
    
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
