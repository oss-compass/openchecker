import re
import yaml
import json
from typing import List, Dict, Tuple, Any
from pathlib import Path
from common import get_platform_type, list_workflow_files
from platform_adapter import platform_manager
from logger import get_logger

logger = get_logger('openchecker.checkers.pinned_dependencies_checker')


COMMAND = 'pinned-dependencies-checker'


# 依赖类型常量
DEPENDENCY_TYPE_ACTION = "Action"
DEPENDENCY_TYPE_DOCKER_IMAGE = "Docker"
DEPENDENCY_TYPE_PYTHON_PIP = "PythonPip"
DEPENDENCY_TYPE_NODEJS_NPM = "NodeJS"
DEPENDENCY_TYPE_SCRIPT_DOWNLOAD = "ScriptDownload"
DEPENDENCY_TYPE_NUGET = "Nuget"

# 固定状态结果常量
PINNING_RESULT_PINNED = "pinned"
PINNING_RESULT_UNPINNED = "unpinned"
PINNING_RESULT_UNKNOWN = "unknown"


def create_dependency(name: str, version: str, dep_type: str, file_path: str, 
                     line_number: int, is_pinned: bool, is_owned: bool = False, 
                     snippet: str = "") -> Dict[str, Any]:
    """创建依赖项字典"""
    return {
        'name': name,
        'version': version,
        'dep_type': dep_type,
        'file_path': file_path,
        'line_number': line_number,
        'is_pinned': is_pinned,
        'is_owned': is_owned,
        'snippet': snippet
    }



def _is_owned_action(action_name: str, platform_type: str) -> bool:
    """判断是否为 官方 Action"""
    owned_orgs = {
        'actions', platform_type, 'microsoft', 'azure', 'docker',
        'codecov', 'coverallsapp', 'softprops'
    }
    org = action_name.split('/')[0].lower()
    return org in owned_orgs


def _parse_docker_image(image_ref: str) -> Tuple[str, str]:
    """解析 Docker 镜像引用"""
    if ':' in image_ref:
        name, tag = image_ref.rsplit(':', 1)
        return name, tag
    elif '@' in image_ref:
        name, digest = image_ref.split('@', 1)
        return name, digest
    else:
        return image_ref, 'latest'


def _is_commit_hash(ref: str) -> bool:
    """判断引用是否为完整的提交哈希"""
    # 完整的 SHA-1 哈希为 40 个十六进制字符
    return re.match(r'^[a-f0-9]{40}$', ref.lower()) is not None


def _is_docker_image_pinned(version: str) -> bool:
    """判断 Docker 镜像是否固定到摘要"""
    # 检查是否为 SHA256 摘要
    return version.startswith('sha256:') and len(version) == 71


def _is_version_pinned(ref: str) -> bool:
    """
    判断引用是否为固定版本
    
    Args:
        ref: 版本引用字符串
        
    Returns:
        bool: 是否为固定版本
    """
    if _is_commit_hash(ref):
        return True
    
    if _is_docker_image_pinned(ref):
        return True
        
    # 更宽松的版本匹配：支持 v3, v1.0, 1.2, v1.0.0 等各种格式
    version_patterns = [
        r'^v?(\d+)(\.\d+)?(\.\d+)?(-[\w\.-]+)?(\+[\w\.-]+)?$',  # 通用版本格式
        r'^v(\d+)$',  # 简单的v3, v4等
        r'^(\d+)\.(\d+)$',  # 1.2, 2.5等
    ]
    # 额外检查：排除一些明显不是版本的标签
    excluded_tags = {'latest', 'main', 'master', 'dev', 'develop', 'head', 'trunk'}
    
    for pattern in version_patterns:
        if re.match(pattern, ref):
            if ref.lower() not in excluded_tags:
                return True
        
    # 其他情况（如分支名main、master等）认为不固定
    return False



def _parse_requirements_file(req_file: Path) -> List[Dict[str, Any]]:
    """解析 requirements.txt 文件"""
    dependencies = []
    
    try:
        with open(req_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # 解析包名和版本
            match = re.match(r'^([a-zA-Z0-9\-_\.]+)([>=<~!]+.*)?', line)
            if match:
                name = match.group(1)
                version_spec = match.group(2) or ""
                
                # 判断是否固定到精确版本
                is_pinned = '==' in version_spec and not any(op in version_spec for op in ['>=', '<=', '>', '<', '~', '!'])
                
                dep = create_dependency(
                    name=name,
                    version=version_spec,
                    dep_type=DEPENDENCY_TYPE_PYTHON_PIP,
                    file_path=str(req_file),
                    line_number=line_num,
                    is_pinned=is_pinned,
                    snippet=line
                )
                dependencies.append(dep)
                
    except Exception as e:
                
        logger.warning('failed to read pinned dependencies: %s', e)
    
    return dependencies


def _parse_package_json(package_file: Path) -> List[Dict[str, Any]]:
    """解析 package.json 文件"""
    dependencies = []
    
    try:
        with open(package_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 处理 dependencies 和 devDependencies
        for dep_type in ['dependencies', 'devDependencies']:
            deps = data.get(dep_type, {})
            for name, version in deps.items():
                # 判断是否固定到精确版本
                is_pinned = not any(char in version for char in ['^', '~', '>', '<', '*'])
                
                dep = create_dependency(
                    name=name,
                    version=version,
                    dep_type=DEPENDENCY_TYPE_NODEJS_NPM,
                    file_path=str(package_file),
                    line_number=0,  # JSON 文件无法确定具体行号
                    is_pinned=is_pinned,
                    snippet=f'"{name}": "{version}"'
                )
                dependencies.append(dep)
                
    except Exception as e:
                
        logger.warning('failed to read pinned dependencies: %s', e)
    
    return dependencies


def _find_download_commands(line: str) -> List[Tuple[str, bool]]:
    """查找行中的下载命令"""
    downloads = []
    
    # 匹配常见的下载命令
    patterns = [
        r'curl\s+.*?(?:https?://[^\s]+)',
        r'wget\s+.*?(?:https?://[^\s]+)',
        r'pip\s+install\s+.*?(?:https?://[^\s]+)',
        r'npm\s+install\s+.*?(?:https?://[^\s]+)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, line, re.IGNORECASE)
        for match in matches:
            # 提取 URL
            url_match = re.search(r'https?://[^\s]+', match)
            if url_match:
                url = url_match.group()
                # 简单判断是否包含版本信息或哈希
                is_pinned = any(keyword in url.lower() for keyword in ['version', 'tag', 'commit', 'sha'])
                downloads.append((url, is_pinned))
    
    return downloads


def collect_dependencies(repo_path: str, platform_type: str) -> List[Dict[str, Any]]:
    """
    收集项目中的所有依赖信息
    
    Args:
        repo_path: 项目根目录路径
        
    Returns:
        依赖列表
    """
    dependencies = []
    repo_path = Path(repo_path)
    
    # 收集 Actions 依赖
    dependencies.extend(_collect_actions(repo_path, platform_type))
    
    # 收集 Docker 依赖
    dependencies.extend(_collect_docker_dependencies(repo_path))
    
    # 收集 Python 依赖
    dependencies.extend(_collect_python_dependencies(repo_path))
    
    # 收集 Node.js 依赖
    dependencies.extend(_collect_nodejs_dependencies(repo_path))
    
    # 收集脚本下载依赖
    dependencies.extend(_collect_script_downloads(repo_path))
    
    return dependencies


def _collect_actions(repo_path: Path, platform_type: str) -> List[Dict[str, Any]]:
    """收集 Actions 工作流中的依赖"""
    dependencies = []
    
    workflow_files = list_workflow_files(repo_path, platform_type)
    for workflow_file in workflow_files:
        try:
            with open(workflow_file, 'r', encoding='utf-8') as f:
                content = f.read()
                data = yaml.safe_load(content)
            
            if not isinstance(data, dict):
                continue
                
            # 解析工作流中的 uses 字段
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                uses_match = re.search(r'uses:\s*([^\s#]+)', line)
                if uses_match:
                    action_ref = uses_match.group(1).strip()
                    
                    # 解析 action 引用格式: owner/repo@ref
                    action_parts = action_ref.split('@')
                    if len(action_parts) == 2:
                        action_name = action_parts[0]
                        ref = action_parts[1]
                        
                        # 判断是否为 官方 Action
                        is_owned = _is_owned_action(action_name, platform_type)
                        
                        # 判断版本是否固定
                        is_pinned = _is_version_pinned(ref)
                        
                        dep = create_dependency(
                            name=action_name,
                            version=ref,
                            dep_type=DEPENDENCY_TYPE_ACTION,
                            file_path=str(workflow_file),
                            line_number=line_num,
                            is_pinned=is_pinned,
                            is_owned=is_owned,
                            snippet=line.strip()
                        )
                        dependencies.append(dep)
                        
        except Exception as e:
                        
            logger.warning('failed to read pinned dependencies: %s', e)
            
    return dependencies



def _collect_docker_dependencies(repo_path: Path) -> List[Dict[str, Any]]:
    """收集 Docker 文件中的依赖"""
    dependencies = []
    
    # 查找 Dockerfile 和 docker-compose.yml
    docker_files = list(repo_path.rglob("Dockerfile*")) + list(repo_path.rglob("docker-compose*.yml"))
    
    for docker_file in docker_files:
        try:
            with open(docker_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                
                # 匹配 FROM 指令
                from_match = re.search(r'^FROM\s+([^\s]+)', line, re.IGNORECASE)
                if from_match:
                    image_ref = from_match.group(1)
                    
                    # 跳过多阶段构建中的别名
                    if image_ref.lower() in ['scratch', 'alpine', 'ubuntu', 'debian']:
                        continue
                        
                    # 解析镜像引用
                    name, version = _parse_docker_image(image_ref)
                    is_pinned = _is_version_pinned(version)
                    
                    dep = create_dependency(
                        name=name,
                        version=version,
                        dep_type=DEPENDENCY_TYPE_DOCKER_IMAGE,
                        file_path=str(docker_file),
                        line_number=line_num,
                        is_pinned=is_pinned,
                        snippet=line
                    )
                    dependencies.append(dep)
                    
        except Exception as e:
                    
            logger.warning('failed to read pinned dependencies: %s', e)
            
    return dependencies


def _collect_python_dependencies(repo_path: Path) -> List[Dict[str, Any]]:
    """收集 Python 包依赖"""
    dependencies = []
    
    # 处理 requirements.txt 文件
    for req_file in repo_path.rglob("requirements*.txt"):
        dependencies.extend(_parse_requirements_file(req_file))
    
    return dependencies


def _collect_nodejs_dependencies(repo_path: Path) -> List[Dict[str, Any]]:
    """收集 Node.js 包依赖"""
    dependencies = []
    
    # 处理 package.json 文件
    for package_file in repo_path.rglob("package.json"):
        dependencies.extend(_parse_package_json(package_file))
    
    return dependencies


def _collect_script_downloads(repo_path: Path) -> List[Dict[str, Any]]:
    """收集脚本中的下载依赖"""
    dependencies = []
    
    # 查找脚本文件
    script_patterns = ["*.sh", "*.bash", "*.py", "*.js"]
    script_files = []
    
    for pattern in script_patterns:
        script_files.extend(repo_path.rglob(pattern))
    
    for script_file in script_files:
        try:
            with open(script_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                # 匹配下载命令
                download_matches = _find_download_commands(line)
                for match in download_matches:
                    url, is_pinned = match
                    
                    dep = create_dependency(
                        name=url,
                        version="",
                        dep_type=DEPENDENCY_TYPE_SCRIPT_DOWNLOAD,
                        file_path=str(script_file),
                        line_number=line_num,
                        is_pinned=is_pinned,
                        snippet=line.strip()
                    )
                    dependencies.append(dep)
                    
        except Exception as e:
                    
            logger.warning('failed to read pinned dependencies: %s', e)
    
    return dependencies


def _generate_unpinned_message(dep: Dict[str, Any]) -> str:
    """生成未固定依赖的消息"""
    if dep['dep_type'] == DEPENDENCY_TYPE_ACTION:
        owner_type = "owned" if dep['is_owned'] else "third-party"
        return f"{owner_type} Action not pinned by hash"
    else:
        return f"{dep['dep_type']} not pinned by hash"


def analyze_pinning(dependencies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析依赖的固定状态
    
    Args:
        dependencies: 依赖列表
        
    Returns:
        分析结果字典
    """
    results = {
        'total_dependencies': len(dependencies),
        'pinned_count': 0,
        'unpinned_count': 0,
        'by_type': {},
        'actions': {
            'owned': {'pinned': 0, 'total': 0},
            'third_party': {'pinned': 0, 'total': 0}
        },
        'findings': []
    }
    
    for dep in dependencies:
        # 总体统计
        if dep['is_pinned']:
            results['pinned_count'] += 1
        else:
            results['unpinned_count'] += 1
        
        # 按类型统计
        dep_type_str = dep['dep_type']
        if dep_type_str not in results['by_type']:
            results['by_type'][dep_type_str] = {'pinned': 0, 'total': 0}
        
        results['by_type'][dep_type_str]['total'] += 1
        if dep['is_pinned']:
            results['by_type'][dep_type_str]['pinned'] += 1
        
        # Actions 特殊处理
        if dep['dep_type'] == DEPENDENCY_TYPE_ACTION:
            if dep['is_owned']:
                results['actions']['owned']['total'] += 1
                if dep['is_pinned']:
                    results['actions']['owned']['pinned'] += 1
            else:
                results['actions']['third_party']['total'] += 1
                if dep['is_pinned']:
                    results['actions']['third_party']['pinned'] += 1
        
        # 记录未固定的依赖
        if not dep['is_pinned']:
            finding = {
                'file': dep['file_path'],
                'line': dep['line_number'],
                'type': dep_type_str,
                'name': dep['name'],
                'version': dep['version'],
                'message': _generate_unpinned_message(dep),
                'snippet': dep['snippet']
            }
            results['findings'].append(finding)
    
    return results



def pinned_dependencies_checker(project_url: str, res_payload: dict) -> None:
    """
    检查项目依赖是否固定到特定版本/哈希值
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#pinned_dependencies
    """
    
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    platform_type = get_platform_type(project_url)
    
    dependencies = collect_dependencies(repo_path, platform_type)
    analysis_results = analyze_pinning(dependencies)
    
    res_payload["scan_results"][COMMAND] = {
        "analysis_results": analysis_results,
        "dependencies": dependencies
    }
