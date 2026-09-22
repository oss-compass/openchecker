import os
import glob
import re
import yaml
import json
from typing import List, Dict, Tuple, Any
from pathlib import Path
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager


COMMAND = 'token-permissions-checker'


# 权限级别常量
PERMISSION_LEVEL_NONE = "none"
PERMISSION_LEVEL_READ = "read"
PERMISSION_LEVEL_WRITE = "write"
PERMISSION_LEVEL_UNDECLARED = "undeclared"
PERMISSION_LEVEL_UNKNOWN = "unknown"

# 关注的权限类型
PERMISSIONS_OF_INTEREST = [
    "statuses", "checks", "security-events", "deployments", 
    "contents", "packages", "actions"
]

# 权限位置类型
PERMISSION_LOCATION_TOP = "top"
PERMISSION_LOCATION_JOB = "job"

def _get_permission_level(value: str) -> str:
    """根据权限值确定权限级别"""
    value_lower = value.lower()
    
    if value_lower in ["none"]:
        return PERMISSION_LEVEL_NONE
    elif value_lower in ["read", "read-all"]:
        return PERMISSION_LEVEL_READ
    elif value_lower in ["write", "write-all"]:
        return PERMISSION_LEVEL_WRITE
    else:
        return PERMISSION_LEVEL_UNKNOWN


def _extract_top_level_permissions(workflow: Dict, file_path: str) -> List[Dict[str, Any]]:
    """提取top级别权限配置"""
    permissions = []
    
    if "permissions" not in workflow:
        # 未声明权限
        permissions.append({
            "file_path": file_path,
            "location_type": PERMISSION_LOCATION_TOP,
            "name": None,
            "value": None,
            "permission_level": PERMISSION_LEVEL_UNDECLARED,
            "line_number": 1
        })
        return permissions
    
    perms = workflow["permissions"]
    
    # 处理简化的权限声明 (如 permissions: write-all)
    if isinstance(perms, str):
        permissions.append({
            "file_path": file_path,
            "location_type": PERMISSION_LOCATION_TOP,
            "name": None,
            "value": perms,
            "permission_level": _get_permission_level(perms),
            "line_number": 1
        })
        return permissions
    
    # 处理详细的权限声明
    if isinstance(perms, dict):
        if not perms:
            permissions.append({
                "file_path": file_path,
                "location_type": PERMISSION_LOCATION_TOP,
                "name": None,
                "value": "{}",
                "permission_level": PERMISSION_LEVEL_NONE,
                "line_number": 1
            })
        for perm_name, perm_value in perms.items():
            if perm_name in PERMISSIONS_OF_INTEREST or perm_value == "write":
                permissions.append({
                    "file_path": file_path,
                    "location_type": PERMISSION_LOCATION_TOP,
                    "name": perm_name,
                    "value": str(perm_value),
                    "permission_level": _get_permission_level(str(perm_value)),
                    "line_number": 1
                })
    
    return permissions


def _extract_job_level_permissions(workflow: Dict, file_path: str) -> List[Dict[str, Any]]:
    """提取job级别权限配置"""
    permissions = []
    
    if "jobs" not in workflow:
        return permissions
    
    jobs = workflow["jobs"]
    if not isinstance(jobs, dict):
        return permissions
    
    for job_name, job_config in jobs.items():
        if not isinstance(job_config, dict):
            continue
            
        if "permissions" not in job_config:
            # job级别未声明权限
            permissions.append({
                "file_path": file_path,
                "location_type": PERMISSION_LOCATION_JOB,
                "name": None,
                "value": None,
                "permission_level": PERMISSION_LEVEL_UNDECLARED,
                "line_number": 1,
                "job_name": job_name
            })
            continue
        
        job_perms = job_config["permissions"]
        
        # 处理简化权限声明
        if isinstance(job_perms, str):
            permissions.append({
                "file_path": file_path,
                "location_type": PERMISSION_LOCATION_JOB,
                "name": None,
                "value": job_perms,
                "permission_level": _get_permission_level(job_perms),
                "line_number": 1,
                "job_name": job_name
            })
            continue
        
        # 处理详细权限声明
        if isinstance(job_perms, dict):
            if not job_perms:
                permissions.append({
                    "file_path": file_path,
                    "location_type": PERMISSION_LOCATION_JOB,
                    "name": None,
                    "value": "{}",
                    "permission_level": PERMISSION_LEVEL_NONE,
                    "line_number": 1,
                    "job_name": job_name
                })
            for perm_name, perm_value in job_perms.items():
                if perm_name in PERMISSIONS_OF_INTEREST or perm_value == "write":
                    permissions.append({
                        "file_path": file_path,
                        "location_type": PERMISSION_LOCATION_JOB,
                        "name": perm_name,
                        "value": str(perm_value),
                        "permission_level": _get_permission_level(str(perm_value)),
                        "line_number": 1,
                        "job_name": job_name
                    })
    
    return permissions


def _extract_workflow_permissions(workflow_file: str, repo_path: str) -> List[Dict[str, Any]]:
    """
    从单个workflow文件中提取权限信息
    
    Args:
        workflow_file: workflow文件路径
        repo_path: 仓库根路径
        
    Returns:
        权限信息列表
    """
    permissions = []
    
    try:
        with open(workflow_file, 'r', encoding='utf-8') as f:
            workflow_content = yaml.safe_load(f)
        
        if not workflow_content:
            return permissions
            
        relative_path = os.path.relpath(workflow_file, repo_path)
        
        # 1. 提取top级别权限
        top_permissions = _extract_top_level_permissions(workflow_content, relative_path)
        permissions.extend(top_permissions)
        
        # 2. 提取job级别权限
        job_permissions = _extract_job_level_permissions(workflow_content, relative_path)
        permissions.extend(job_permissions)
        
    except Exception as e:
        pass
        
    return permissions



def token_permissions_checker(project_url: str, res_payload: dict) -> None:
    """ 
    检查workflows的token权限信息 ,
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#token_permissions
    """
    
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)
    results = {
        "num_workflows": 0,
        "token_permissions": []
    }
    workflow_files = list_workflow_files(repo_path, platform_type)
    
    for workflow_file in workflow_files:
        permissions = _extract_workflow_permissions(workflow_file, repo_path)
        if permissions:
            results["num_workflows"] += 1
            results["token_permissions"].extend(permissions)
    
    res_payload["scan_results"][COMMAND] = results
