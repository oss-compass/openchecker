import re
import yaml
from typing import List, Dict, Tuple, Any
from pathlib import Path
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager

COMMAND = 'sast-checker'

# SAST工具正则表达式映射
# uses 的真实格式为 owner/repo[/path]@ref（如 github/codeql-action/analyze@v3），
# 模式不能以 $ 结尾，且 owner 前缀必须与实际 action 一致
SAST_TOOL_PATTERNS = {
    "codeql": r"github/codeql-action/",
    "snyk": r"snyk/actions/",
    "pysa": r"facebook/pysa-action(?=@|$)",
    "qodana": r"JetBrains/qodana-action(?=@|$)",
}

def _parse_workflow_for_sast_tools(workflow_content: str) -> List[str]:
    """
    解析工作流内容，检测SAST工具使用
    """
    detected_tools = []
    
    try:
        workflow = yaml.safe_load(workflow_content)
        if not isinstance(workflow, dict):
            return detected_tools
        
        jobs = workflow.get("jobs", {})
        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue
                
            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                    
                uses = step.get("uses", "")
                if not uses:
                    continue
                
                # 检查各种SAST工具模式
                for tool_name, pattern in SAST_TOOL_PATTERNS.items():
                    if re.match(pattern, uses):
                        detected_tools.append(tool_name)
                        
    except yaml.YAMLError:
        # 如果YAML解析失败，尝试用正则表达式检测
        for tool_name, pattern in SAST_TOOL_PATTERNS.items():
            if re.search(f'uses:\\s*["\']?{pattern}["\']?', workflow_content):
                detected_tools.append(tool_name)
    
    return list(set(detected_tools)) 


def detect_workflows(repo_path: str, platform_type: str) -> List[Dict]:
    """
    检测 Actions工作流中的SAST工具配置
    """
    sast_workflows = []
    workflow_files = list_workflow_files(repo_path, platform_type)
    for workflow_file in workflow_files:
        try:
            with open(workflow_file, 'r', encoding='utf-8') as f:
                workflow_content = f.read()
                detected_tools = _parse_workflow_for_sast_tools(workflow_content)
                
                for tool_type in detected_tools:
                    sast_workflows.append({
                        "file_path": str(workflow_file),
                        "type": tool_type,
                        "tool_name": tool_type
                    })
        except Exception as e:
            pass
    
    return sast_workflows


def detect_sonar_config(project_dir: str) -> List[Dict]:
    """
    检测项目中的SonarCloud配置
    """
    sonar_configs = []
    project_path = Path(project_dir)
    
    # 查找pom.xml文件
    for pom_file in project_path.rglob("pom.xml"):
        try:
            with open(pom_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检测sonar.host.url配置
            pattern = r'<sonar\.host\.url>\s*(\S+)\s*</sonar\.host\.url>'
            match = re.search(pattern, content)
            
            if match:
                sonar_configs.append({
                    "file_path": str(pom_file),
                    "type": "sonar",
                    "url": match.group(1),
                    "tool_name": "sonar"
                })
        except Exception as e:
            continue
    
    return sonar_configs



def sast_checker(project_url: str, res_payload: dict) -> None:
    """ 
    SAST 工具检查 
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#sast
    """
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)
    
    workflows = detect_workflows(repo_path, platform_type)
    sonar_configs = detect_sonar_config(repo_path)  
    
    res_payload["scan_results"][COMMAND] = {
        "sast_workflows": workflows,
        "sonar_configs": sonar_configs
    }
