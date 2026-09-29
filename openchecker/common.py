import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Any
from urllib.parse import urlparse

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
    hostname = urlparse(url).hostname
    if hostname in ("github.com", "www.github.com"):
        return "github"
    elif hostname in ("gitee.com", "www.gitee.com"):
        return "gitee"
    elif hostname in ("gitcode.com", "www.gitcode.com"):
        return "gitcode"
    else:
        return None
    

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
