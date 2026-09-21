"""
平台适配器模块

提供对GitHub、Gitee、GitCode等代码托管平台的统一接口。
支持获取releases、仓库信息、下载统计、源码归档下载等功能。
"""

import re
import json
from logger import get_logger
import requests
from typing import Dict, List, Tuple, Optional, Any
from urllib.parse import urlparse
from ghapi.all import GhApi, paged
from helper import read_config
import os
import io
import shutil
import stat
import tempfile
import zipfile

logger = get_logger('openchecker.platform_adapter')

# 获取配置
file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(file_dir)
config_file = os.path.join(project_root, "config", "config.ini")
config = read_config(config_file)

# 下载源码归档的超时时间（秒），避免第三方归档服务长时间挂起agent线程
ARCHIVE_DOWNLOAD_TIMEOUT = 30


def _normalize_version(version_number: Optional[str]) -> Optional[str]:
    """
    将消息协议中的版本号占位值统一转换为None

    未指定版本时version_number会以字符串"None"传入，直接拼接到归档地址
    上会得到非法的下载链接，因此这里统一收敛处理。

    Args:
        version_number: 原始版本号

    Returns:
        Optional[str]: 规范化后的版本号，未指定版本时返回None
    """
    if version_number is None:
        return None
    version = str(version_number).strip()
    if not version or version == "None":
        return None
    return version


def _extract_zip_safely(archive: zipfile.ZipFile, dest_dir: str) -> None:
    """
    解压归档文件，并拒绝可能逃逸出目标目录的条目

    源码归档来自第三方服务，必须同时防御路径穿越（../）和符号链接条目，
    否则恶意归档可以覆盖agent工作目录之外的文件。

    Args:
        archive: 已打开的zip归档
        dest_dir: 解压目标目录

    Raises:
        ValueError: 归档中包含不安全的条目
    """
    dest_root = os.path.abspath(dest_dir)
    for member in archive.infolist():
        member_path = os.path.abspath(os.path.join(dest_root, member.filename))
        if member_path != dest_root and not member_path.startswith(dest_root + os.sep):
            raise ValueError(f"Unsafe path in archive: {member.filename}")
        # zip将Unix文件模式保存在external_attr的高16位
        if stat.S_ISLNK(member.external_attr >> 16):
            raise ValueError(f"Symbolic link entry is not allowed: {member.filename}")
    archive.extractall(dest_root)


def _pick_extracted_root(dest_dir: str) -> str:
    """
    返回真正存放源码的目录

    GitHub/Gitee的归档会额外包一层<repo>-<ref>/目录，而部分GitCode归档
    是平铺的，因此只在解压结果只有一个目录时才向下钻取。

    Args:
        dest_dir: 解压目标目录

    Returns:
        str: 源码所在目录
    """
    entries = os.listdir(dest_dir)
    if len(entries) == 1:
        candidate = os.path.join(dest_dir, entries[0])
        if os.path.isdir(candidate):
            return candidate
    return dest_dir


class PlatformAdapter:
    """平台适配器基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    def get_platform_name(self) -> str:
        """获取平台名称"""
        raise NotImplementedError
        
    def parse_project_url(self, project_url: str) -> Tuple[str, str]:
        """
        解析项目URL，提取owner和repo名称
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[str, str]: (owner_name, repo_name)
        """
        raise NotImplementedError
        
    def get_releases(self, project_url: str) -> Tuple[List[Dict], Optional[str]]:
        """
        获取项目所有releases
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[List[Dict], Optional[str]]: (releases列表, 错误信息)
        """
        raise NotImplementedError
        
    def get_zipball_url(self, project_url: str, tag: str) -> Optional[str]:
        """
        获取指定tag的zipball下载URL
        
        Args:
            project_url: 项目URL
            tag: 标签名称
            
        Returns:
            Optional[str]: zipball URL
        """
        raise NotImplementedError
        
    def get_repo_info(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """
        获取仓库基本信息
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[Dict, Optional[str]]: (仓库信息, 错误信息)
        """
        raise NotImplementedError
        
    def get_download_stats(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """
        获取下载统计信息
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[Dict, Optional[str]]: (下载统计, 错误信息)
        """
        raise NotImplementedError

    def get_download_headers(self) -> Dict[str, str]:
        """
        获取下载源码归档时使用的HTTP请求头

        Returns:
            Dict[str, str]: 请求头，默认不携带鉴权信息
        """
        return {}

    def download_project_source(
        self,
        project_url: str,
        version_number: str = "None",
        dest_root: str = "."
    ) -> Tuple[bool, Optional[str]]:
        """
        下载并解压指定版本的源码归档

        与git clone相比，归档下载只取一个快照，对仅检查文件内容的检查器
        代价更低，因此agent优先使用该路径；但归档不包含.git目录，需要git
        元数据的检查器必须继续使用download-checkout脚本。

        Args:
            project_url: 项目URL
            version_number: 版本号或标签，未指定时直接失败以便回退到克隆
            dest_root: 存放<repo_name>目录的父目录

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        tag = _normalize_version(version_number)
        if tag is None:
            return False, "Version number is required to download a source archive"

        archive_url = self.get_zipball_url(project_url, tag)
        if not archive_url:
            return False, f"Failed to build archive URL for {project_url}"

        try:
            _owner_name, repo_name = self.parse_project_url(project_url)
        except ValueError as e:
            return False, str(e)

        target_dir = os.path.join(dest_root, repo_name)
        if os.path.exists(target_dir):
            # 目录已存在说明本次任务下载过源码，重复解压会覆盖其他检查器的产物
            logger.info(f"Source directory already exists, skip download: {target_dir}")
            return True, None

        staging_dir = tempfile.mkdtemp(prefix=f".{repo_name}-", dir=dest_root)
        try:
            response = requests.get(
                archive_url,
                headers=self.get_download_headers(),
                timeout=ARCHIVE_DOWNLOAD_TIMEOUT
            )
            if response.status_code != 200:
                return False, f"Failed to download archive {archive_url}, status code: {response.status_code}"

            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                _extract_zip_safely(archive, staging_dir)

            if not os.listdir(staging_dir):
                return False, f"Downloaded archive is empty: {archive_url}"

            # 先解压到临时目录再整体重命名，避免失败时留下半成品源码目录
            os.replace(_pick_extracted_root(staging_dir), target_dir)
        except requests.Timeout:
            return False, f"Timeout while downloading archive: {archive_url}"
        except requests.RequestException as e:
            return False, f"Failed to download archive {archive_url}: {e}"
        except zipfile.BadZipFile as e:
            return False, f"Invalid archive downloaded from {archive_url}: {e}"
        except ValueError as e:
            return False, str(e)
        except OSError as e:
            return False, f"Failed to extract archive {archive_url}: {e}"
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

        logger.info(f"Source archive downloaded via {self.get_platform_name()}: {target_dir}")
        return True, None


class GitHubAdapter(PlatformAdapter):
    """GitHub平台适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.access_token = config["Github"]["access_key"]
        
    def get_download_headers(self) -> Dict[str, str]:
        """
        获取源码归档下载时的HTTP请求头

        GitHub的归档地址会重定向到codeload，但私有仓库的归档请求仍
        需要鉴权，因此这里复用与get_repo_info一致的Bearer token；
        该请求头对公开仓库的匿名下载同样有效。

        Returns:
            Dict[str, str]: GitHub归档下载请求头
        """
        return {
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {self.access_token}'
        }

    def get_platform_name(self) -> str:
        return "github"
        
    def parse_project_url(self, project_url: str) -> Tuple[str, str]:
        """解析GitHub项目URL"""
        # 支持多种GitHub URL格式：
        # https://github.com/owner/repo.git
        # https://github.com/owner/repo
        # https://www.github.com/owner/repo
        pattern = r"https://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?$"
        match = re.match(pattern, project_url)
        if match:
            owner_name, repo_name = match.groups()
            return owner_name, repo_name
        else:
            raise ValueError(f"Invalid GitHub URL format: {project_url}")
            
    def get_releases(self, project_url: str) -> Tuple[List[Dict], Optional[str]]:
        """获取GitHub releases"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            api = GhApi(owner=owner_name, repo=repo_name)
            
            all_releases = []
            for page in paged(api.repos.list_releases, owner_name, repo_name, per_page=10):
                all_releases.extend(page)
            return all_releases, None
        except Exception as e:
            logger.error(f"Failed to get GitHub releases for repo: {project_url}, Error: {e}")
            return [], f"Failed to get releases for repo: {project_url}"
            
    def get_zipball_url(self, project_url: str, tag: str) -> Optional[str]:
        """获取GitHub zipball URL"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            return f"https://github.com/{owner_name}/{repo_name}/archive/refs/tags/{tag}.zip"
        except ValueError:
            return None
            
    def get_repo_info(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """获取GitHub仓库信息"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            url = f"https://api.github.com/repos/{owner_name}/{repo_name}"
            
            headers = {
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                repo_json = response.json()
                return {
                    "homepage": repo_json.get('homepage', ''),
                    "description": repo_json.get('description', '')
                }, None
            elif response.status_code == 403:
                return {}, "GitHub token limit exceeded"
            else:
                return {}, "Repository not found"
        except Exception as e:
            logger.error(f"Failed to get GitHub repo info for {project_url}: {e}")
            return {}, str(e)
            
    def get_download_stats(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """GitHub不直接提供下载统计，返回空结果"""
        return {"download_count": 0, "period": ""}, None


class GiteeAdapter(PlatformAdapter):
    """Gitee平台适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.access_token = config["Gitee"]["access_key"]
        
    def get_platform_name(self) -> str:
        return "gitee"
        
    def parse_project_url(self, project_url: str) -> Tuple[str, str]:
        """解析Gitee项目URL"""
        # 支持多种Gitee URL格式：
        # https://gitee.com/owner/repo.git
        # https://gitee.com/owner/repo
        # https://www.gitee.com/owner/repo
        pattern = r"https://(?:www\.)?gitee\.com/([^/]+)/([^/]+?)(?:\.git)?$"
        match = re.match(pattern, project_url)
        if match:
            owner_name, repo_name = match.groups()
            return owner_name, repo_name
        else:
            raise ValueError(f"Invalid Gitee URL format: {project_url}")
            
    def get_releases(self, project_url: str) -> Tuple[List[Dict], Optional[str]]:
        """获取Gitee releases"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            url = f"https://gitee.com/api/v5/repos/{owner_name}/{repo_name}/releases"
            
            headers = {'Accept': 'application/json'}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                releases = response.json()
                return releases, None
            else:
                return [], "Not found"
        except Exception as e:
            logger.error(f"Failed to get Gitee releases for repo: {project_url}, Error: {e}")
            return [], f"Failed to get releases for repo: {project_url}"
            
    def get_zipball_url(self, project_url: str, tag: str) -> Optional[str]:
        """获取Gitee zipball URL"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            return f"https://gitee.com/{owner_name}/{repo_name}/repository/archive/{tag}.zip"
        except ValueError:
            return None
            
    def get_repo_info(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """获取Gitee仓库信息"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            url = f"https://gitee.com/api/v5/repos/{owner_name}/{repo_name}?access_token={self.access_token}"
            
            response = requests.get(url)
            if response.status_code == 200:
                repo_json = response.json()
                return {
                    "homepage": repo_json.get('homepage', ''),
                    "description": repo_json.get('description', '')
                }, None
            elif response.status_code == 403:
                return {}, "Gitee token limit exceeded"
            else:
                return {}, "Repository not found"
        except Exception as e:
            logger.error(f"Failed to get Gitee repo info for {project_url}: {e}")
            return {}, str(e)
            
    def get_download_stats(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """Gitee不直接提供下载统计，返回空结果"""
        return {"download_count": 0, "period": ""}, None


class GitCodeAdapter(PlatformAdapter):
    """GitCode平台适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.access_token = config["GitCode"]["access_key"]
        
    def get_platform_name(self) -> str:
        return "gitcode"
        
    def parse_project_url(self, project_url: str) -> Tuple[str, str]:
        """解析GitCode项目URL"""
        # 支持多种GitCode URL格式：
        # https://gitcode.com/owner/repo.git
        # https://gitcode.com/owner/repo
        # https://www.gitcode.com/owner/repo
        pattern = r"https://(?:www\.)?gitcode\.com/([^/]+)/([^/]+?)(?:\.git)?$"
        match = re.match(pattern, project_url)
        if match:
            owner_name, repo_name = match.groups()
            return owner_name, repo_name
        else:
            raise ValueError(f"Invalid GitCode URL format: {project_url}")
            
    def get_releases(self, project_url: str) -> Tuple[List[Dict], Optional[str]]:
        """获取GitCode releases"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            url = f"https://api.gitcode.com/api/v5/repos/{owner_name}/{repo_name}/releases?access_token={self.access_token}"
            
            headers = {'Accept': 'application/json'}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                releases = response.json()
                return releases, None
            else:
                return [], "Not found"
        except Exception as e:
            logger.error(f"Failed to get GitCode releases for repo: {project_url}, Error: {e}")
            return [], f"Failed to get releases for repo: {project_url}"
            
    def get_zipball_url(self, project_url: str, tag: str) -> Optional[str]:
        """获取GitCode zipball URL"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            return f"https://raw.gitcode.com/{owner_name}/{repo_name}/archive/refs/heads/{tag}.zip"
        except ValueError:
            return None
            
    def get_repo_info(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """获取GitCode仓库信息"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            url = f"https://api.gitcode.com/api/v5/repos/{owner_name}/{repo_name}?access_token={self.access_token}"
            
            response = requests.get(url)
            if response.status_code == 200:
                repo_json = response.json()
                return {
                    "homepage": repo_json.get('homepage', ''),
                    "description": repo_json.get('description', '')
                }, None
            elif response.status_code == 403:
                return {}, "GitCode token limit exceeded"
            else:
                return {}, "Repository not found"
        except Exception as e:
            logger.error(f"Failed to get GitCode repo info for {project_url}: {e}")
            return {}, str(e)
            
    def get_download_stats(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """获取GitCode下载统计"""
        try:
            owner_name, repo_name = self.parse_project_url(project_url)
            url = f"https://api.gitcode.com/api/v5/repos/{owner_name}/{repo_name}/download_statistics?access_token={self.access_token}"
            
            response = requests.get(url)
            if response.status_code == 200:
                down_json = response.json()
                down_list = down_json.get('download_statistics_detail', [])
                down_count = sum(ch.get('today_dl_cnt', 0) for ch in down_list)
                
                if down_list:
                    day_enter = f"{down_list[-1].get('pdate', '')} - {down_list[0].get('pdate', '')}"
                else:
                    day_enter = ""
                    
                return {
                    "download_count": down_count,
                    "period": day_enter
                }, None
            elif response.status_code == 403:
                return {}, "GitCode token limit exceeded"
            else:
                return {}, "Download statistics not found"
        except Exception as e:
            logger.error(f"Failed to get GitCode download stats for {project_url}: {e}")
            return {}, str(e)


class PlatformManager:
    """平台管理器，提供统一的平台操作接口"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adapters = {
            "github": GitHubAdapter(config),
            "gitee": GiteeAdapter(config),
            "gitcode": GitCodeAdapter(config)
        }
        
    def get_adapter(self, project_url: str) -> Optional[PlatformAdapter]:
        """
        根据项目URL获取对应的平台适配器
        
        Args:
            project_url: 项目URL
            
        Returns:
            Optional[PlatformAdapter]: 平台适配器实例
        """
        if "github.com" in project_url:
            return self.adapters["github"]
        elif "gitee.com" in project_url:
            return self.adapters["gitee"]
        elif "gitcode.com" in project_url:
            return self.adapters["gitcode"]
        else:
            return None
            
    def parse_project_url(self, project_url: str) -> Tuple[str, str]:
        """
        解析项目URL，提取owner和repo名称
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[str, str]: (owner_name, repo_name)
        """
        adapter = self.get_adapter(project_url)
        if adapter:
            return adapter.parse_project_url(project_url)
        else:
            raise ValueError(f"Unsupported platform for URL: {project_url}")
            
    def get_releases(self, project_url: str) -> Tuple[List[Dict], Optional[str]]:
        """
        获取项目所有releases
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[List[Dict], Optional[str]]: (releases列表, 错误信息)
        """
        adapter = self.get_adapter(project_url)
        if adapter:
            return adapter.get_releases(project_url)
        else:
            return [], "Unsupported platform"
            
    def get_zipball_url(self, project_url: str, tag: str) -> Optional[str]:
        """
        获取指定tag的zipball下载URL
        
        Args:
            project_url: 项目URL
            tag: 标签名称
            
        Returns:
            Optional[str]: zipball URL
        """
        adapter = self.get_adapter(project_url)
        if adapter:
            return adapter.get_zipball_url(project_url, tag)
        else:
            return None
            
    def get_repo_info(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """
        获取仓库基本信息
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[Dict, Optional[str]]: (仓库信息, 错误信息)
        """
        adapter = self.get_adapter(project_url)
        if adapter:
            return adapter.get_repo_info(project_url)
        else:
            return {}, "Unsupported platform"
            
    def get_download_stats(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """
        获取下载统计信息
        
        Args:
            project_url: 项目URL
            
        Returns:
            Tuple[Dict, Optional[str]]: (下载统计, 错误信息)
        """
        adapter = self.get_adapter(project_url)
        if adapter:
            return adapter.get_download_stats(project_url)
        else:
            return {}, "Unsupported platform"

    def download_project_source(
        self,
        project_url: str,
        version_number: str = "None",
        dest_root: str = "."
    ) -> Tuple[bool, Optional[str]]:
        """
        下载指定版本的源码归档

        Args:
            project_url: 项目URL
            version_number: 版本号或标签
            dest_root: 存放<repo_name>目录的父目录

        Returns:
            Tuple[bool, Optional[str]]: (是否成功, 错误信息)
        """
        adapter = self.get_adapter(project_url)
        if adapter:
            return adapter.download_project_source(project_url, version_number, dest_root)
        else:
            return False, f"Unsupported platform for URL: {project_url}"


# 全局平台管理器实例
platform_manager = PlatformManager(config) 