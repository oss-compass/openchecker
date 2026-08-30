import re
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Any

# project_url、version_number、commit_hash 等字段最终会被 format 进 shell 脚本执行
# （见 constans.py 的 shell_script_handlers），因此必须限制为不含 shell 元字符的白名单格式
SUPPORTED_PROJECT_URL_PATTERN = re.compile(
    r'^https://(?:www\.)?(?:github|gitee|gitcode)\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
)
VERSION_NUMBER_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+/-]*$')
COMMIT_HASH_PATTERN = re.compile(r'^[0-9a-fA-F]{7,64}$')


def is_valid_project_url(project_url) -> bool:
    """
    校验 project_url 是否为受支持平台的合法仓库地址

    Args:
        project_url: 项目地址

    Returns:
        bool: 是否合法
    """
    return bool(isinstance(project_url, str) and SUPPORTED_PROJECT_URL_PATTERN.match(project_url))


def is_valid_version_number(version_number) -> bool:
    """
    校验 version_number 是否为不含 shell 元字符的合法 tag 名

    Args:
        version_number: 版本号

    Returns:
        bool: 是否合法
    """
    return bool(isinstance(version_number, str) and VERSION_NUMBER_PATTERN.match(version_number))


def is_valid_commit_hash(commit_hash) -> bool:
    """
    校验 commit_hash 是否为合法的 git 哈希（兼容 SHA-1/SHA-256 及短哈希）

    Args:
        commit_hash: 提交哈希

    Returns:
        bool: 是否合法
    """
    return bool(isinstance(commit_hash, str) and COMMIT_HASH_PATTERN.match(commit_hash))


def normalize_project_url(project_url: str) -> str:
    """
    去除 project_url 结尾的 .git 后缀

    只处理后缀而非替换所有 .git，避免破坏 .github 等本身含 .git 的仓库名

    Args:
        project_url: 项目地址

    Returns:
        str: 去除 .git 后缀后的地址
    """
    if isinstance(project_url, str) and project_url.endswith('.git'):
        return project_url[:-len('.git')]
    return project_url

def shell_exec(shell_script, param=None):
    """
    Execute shell script using bash
    
    Args:
        shell_script: Shell script to execute
        param: Optional parameter to append to script
        
    Returns:
        Tuple of (stdout, stderr) - stderr is None on success
    """
    if param is not None:
        cmd = ["/bin/bash", "-c", shell_script + " " + param]
    else:
        cmd = ["/bin/bash", "-c", shell_script]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    shell_output, error = process.communicate()

    if process.returncode == 0:
        return shell_output, None
    else:
        return None, error

def get_platform_type(url):
    """
    根据URL判断代码托管平台类型
    """
    if "github.com" in url:
        return "github"
    elif "gitee.com" in url:
        return "gitee"
    elif "gitcode.com" in url:
        return "gitcode"
    else:
        return "github"
    

def list_workflow_files(repo_path: str, platform_type: str) -> List[str]:
    """
    扫描并返回所有工作流文件路径
    
    Args:
        repo_path: 仓库根目录路径
        
    Returns:
        工作流文件路径列表
    """
    workflow_files = []
    if platform_type == "gitee":
        workflows_dir = Path(repo_path) / ".workflows"
    else:
        workflows_dir = Path(repo_path) / f".{platform_type}" / "workflows"
    if workflows_dir.exists():
        for file_path in workflows_dir.glob("*.yml"):
            workflow_files.append(str(file_path))
        for file_path in workflows_dir.glob("*.yaml"):
            workflow_files.append(str(file_path))
    
    return workflow_files