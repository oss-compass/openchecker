import subprocess
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Tuple, Any


def get_project_dir_name(project_url: str) -> str:
    """
    从项目 URL 派生仓库在本地的目录名：owner__repo

    只用 basename 会在不同 owner/平台的同名仓库间碰撞（例如
    github.com/o1/foo 与 gitee.com/o2/foo 共用 repos/foo），
    download-checkout 发现目录已存在会跳过 clone，导致用 o1 的代码
    生成 o2 的扫描报告。

    Args:
        project_url: 项目地址

    Returns:
        str: 仓库目录名
    """
    parts = [part for part in urlparse(project_url).path.split('/') if part]
    if not parts:
        return ''
    repo = parts[-1]
    if repo.endswith('.git'):
        repo = repo[:-len('.git')]
    owner = parts[-2] if len(parts) >= 2 else ''
    name = f"{owner}__{repo}" if owner else repo
    # 加平台前缀，避免不同平台的同名仓库（owner 也可能相同）共用目录
    host = urlparse(project_url).netloc.removeprefix('www.')
    platform = {'github.com': 'github', 'gitee.com': 'gitee', 'gitcode.com': 'gitcode'}.get(host, host)
    return f"{platform}__{name}"


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