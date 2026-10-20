import re
from logger import get_logger

logger = get_logger('openchecker.checkers.dangerous_workflow_checker')
import yaml
from pathlib import Path
from typing import Any, List, Dict
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager


COMMAND = 'dangerous-workflow-checker'


def has_dangerous_trigger(workflow: Dict[str, Any]) -> bool:
    """检查是否使用危险触发器"""
    # YAML 会把 'on' 解析为 True，所以我们需要检查两种可能的键
    on_events = workflow.get('on', workflow.get(True, {}))

    dangerous_triggers = ['pull_request_target', 'workflow_run']
    
    if isinstance(on_events, str):
        return on_events in dangerous_triggers
    elif isinstance(on_events, list):
        return any(trigger in dangerous_triggers for trigger in on_events)
    elif isinstance(on_events, dict):
        return any(trigger in dangerous_triggers for trigger in on_events.keys())
    else:
        return False


def is_untrusted_ref(ref: str, platform_type: str) -> bool:
    """检查引用是否不信任"""
    untrusted_patterns = [
        f"{platform_type}.event.pull_request.head",
        f"{platform_type}.event.pull_request",
        f"{platform_type}.event.workflow_run"
    ]
    
    return any(pattern in ref for pattern in untrusted_patterns)
    
    
def find_dangerous_variables(script: str, platform_type: str) -> List[str]:
    """查找脚本中的危险变量"""
    dangerous_vars = []
    
    # 不信任的上下文模式
    dangerous_patterns = [
        rf'{platform_type}\.event\.issue\.title',
        rf'{platform_type}\.event\.issue\.body',
        rf'{platform_type}\.event\.pull_request\.title',
        rf'{platform_type}\.event\.pull_request\.body',
        rf'{platform_type}\.event\.comment\.body',
        rf'{platform_type}\.event\.review\.body',
        rf'{platform_type}\.event\.review_comment\.body',
        rf'{platform_type}\.event\..*\.message',
        rf'{platform_type}\.event\..*\.author\.',
        rf'{platform_type}\.event\.pull_request\.head\.ref',
        rf'{platform_type}\.event\.pull_request\.head\.label',
        rf'{platform_type}\.head_ref'
    ]
    
    # 查找所有 ${{ }} 表达式
    pattern = re.compile(r'\$\{\{([^}]+)\}\}')
    
    for match in pattern.finditer(script):
        variable = match.group(1).strip()
        
        # 检查变量是否匹配危险模式
        for dangerous_pattern in dangerous_patterns:
            if re.search(dangerous_pattern, variable):
                dangerous_vars.append(variable)
                break
    
    return dangerous_vars


def check_untrusted_checkout(workflow: Dict[str, Any], file_path: str, platform_type: str) -> List[Dict[str, Any]]:
    """检查不信任代码检出"""
    dangerous_patterns = []
    # 检查是否使用危险触发器
    if not has_dangerous_trigger(workflow):
        return dangerous_patterns
    
    jobs = workflow.get('jobs', {})
    if not isinstance(jobs, dict):
        return dangerous_patterns
    
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        
        steps = job.get('steps', [])
        if not isinstance(steps, list):
            continue
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            
            # 检查是否使用 actions/checkout
            uses = step.get('uses', '')
            if not isinstance(uses, str) or 'actions/checkout' not in uses:
                continue
            
            # 检查 ref 参数
            with_params = step.get('with', {})
            if not isinstance(with_params, dict):
                continue
            
            ref = with_params.get('ref', '')
            if not isinstance(ref, str):
                continue
            
            # 检查是否使用不信任的引用
            if is_untrusted_ref(ref, platform_type):
                dangerous_patterns.append({
                    "type": "untrusted_checkout",
                    "file": file_path,
                    "line": i + 1,
                    "job": job_id,
                    "snippet": ref,
                    "message": f"使用不信任的代码检出引用: {ref}"
                })
    
    return dangerous_patterns


def check_script_injection(workflow: Dict[str, Any], file_path: str, platform_type: str) -> List[Dict[str, Any]]:
    """检查脚本注入"""
    dangerous_patterns = []
    
    jobs = workflow.get('jobs', {})
    if not isinstance(jobs, dict):
        return dangerous_patterns
    
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        
        steps = job.get('steps', [])
        if not isinstance(steps, list):
            continue
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            
            run_script = step.get('run', '')
            if not isinstance(run_script, str):
                continue
            
            # 检查脚本中的危险变量
            dangerous_vars = find_dangerous_variables(run_script, platform_type)
            for var in dangerous_vars:
                dangerous_patterns.append({
                    "type": "script_injection",
                    "file": file_path,
                    "line": i + 1,
                    "job": job_id,
                    "snippet": var,
                    "message": f"脚本注入风险: 使用了不信任的上下文变量 {var}"
                })
    
    return dangerous_patterns


def check_workflow_file(workflow_file: Path, repo_path: str, platform_type: str) -> List[Dict[str, Any]]:
    """检查单个工作流文件"""

    relative_path = str(workflow_file.relative_to(Path(repo_path)))
    dangerous_patterns = [] 
    workflow_file_item = {
        "workflow_file": relative_path,
        "dangerous_patterns": dangerous_patterns
    }
    try:
        with open(workflow_file, 'r', encoding='utf-8') as f:
            content = f.read()
        workflow = yaml.safe_load(content)
        if not workflow or not isinstance(workflow, dict):
            return workflow_file_item
        # 1. 检查不信任代码检出
        dangerous_patterns.extend(check_untrusted_checkout(workflow, relative_path, platform_type))
        # 2. 检查脚本注入
        dangerous_patterns.extend(check_script_injection(workflow, relative_path, platform_type))
    except Exception as e:
        logger.warning('failed to analyse workflow: %s', e)
    return workflow_file_item
    
    



def dangerous_workflow_checker(project_url: str, res_payload: dict) -> None:
    """
    检查仓库中的危险工作流,
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#dangerous-workflow
    """
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)
    workflow_files = list_workflow_files(repo_path, platform_type)
    workflows_file_detail = []
    for workflow_file in workflow_files:
        workflows_file_detail.append(check_workflow_file(Path(workflow_file), repo_path, platform_type))
        
    res_payload["scan_results"][COMMAND] = workflows_file_detail
    
