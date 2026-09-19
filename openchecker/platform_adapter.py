"""
平台适配器模块

提供对GitHub、Gitee、GitCode等代码托管平台的统一接口。
支持获取releases、仓库信息、下载统计等功能。
"""

import abc
import re
import json
from logger import get_logger
import requests
from typing import Dict, List, Tuple, Optional, Any
from urllib.parse import urlparse
from ghapi.all import GhApi, paged
from helper import read_config
import os

logger = get_logger('openchecker.platform_adapter')

# 获取配置
file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(file_dir)
config_file = os.path.join(project_root, "config", "config.ini")
config = read_config(config_file)


class PlatformAdapter(abc.ABC):
    """平台适配器抽象基类。

    所有代码托管平台适配器（GitHub、Gitee、GitCode 等）都必须继承本类并实现
    下面全部六个抽象方法。本类同时约定了适配器对上层暴露的统一契约：

    * 查询类方法（``get_releases`` / ``get_repo_info`` / ``get_download_stats``）在遇到网络
      异常、鉴权失败、资源不存在等情况时不得向上抛出异常，而应返回 ``(空结果, 错误信息)``
      二元组，交由调用方决定降级处理还是记录告警。
    * ``get_zipball_url`` 在 URL 非法或该平台不支持时返回 ``None``。
    * ``parse_project_url`` 遇到非法 URL 时必须抛出 ``ValueError``，因为这属于调用方
      参数错误，而不是可以静默恢复的运行时故障。
    * 错误信息只用于日志与报告展示，禁止携带 access_key / token 等凭据。

    这里使用 ``abc.ABC`` + ``@abc.abstractmethod`` 取代原先在每个方法体中直接
    ``raise NotImplementedError`` 的写法：抽象基类会在实例化阶段就拒绝实现不完整的
    子类（抛出 ``TypeError`` 并列出缺失的方法名），而旧写法只有在真正调用到未实现的
    方法时才会暴露问题；对于常驻的队列消费者进程，这种延迟暴露往往意味着线上事故。
    """

    def __init__(self, config: Dict[str, Any]):
        """保存完整配置，具体适配器再从各自的分区读取 access_key。

        Args:
            config: 由 ``helper.read_config`` 解析出的完整配置字典。
        """
        self.config = config

    @abc.abstractmethod
    def get_platform_name(self) -> str:
        """返回平台唯一标识。

        返回值例如 ``"github"``、``"gitee"``、``"gitcode"``，必须与
        ``PlatformManager.adapters`` 中的键保持一致，用于日志、报告与平台路由。

        Returns:
            str: 平台标识。
        """

    @abc.abstractmethod
    def parse_project_url(self, project_url: str) -> Tuple[str, str]:
        """解析项目 URL，提取 owner 与 repo 名称。

        Args:
            project_url: 项目 URL，支持带或不带 ``.git`` 后缀、带或不带 ``www.`` 前缀的常见写法。

        Returns:
            Tuple[str, str]: ``(owner_name, repo_name)``。

        Raises:
            ValueError: 当 URL 不属于当前平台或格式非法时抛出，调用方需据此判断项目地址是否有效。
        """

    @abc.abstractmethod
    def get_releases(self, project_url: str) -> Tuple[List[Dict], Optional[str]]:
        """获取项目全部 release。

        Args:
            project_url: 项目 URL。

        Returns:
            Tuple[List[Dict], Optional[str]]: ``(releases 列表, 错误信息)``。
            成功时错误信息为 ``None``；失败时返回空列表并给出可读的错误原因，不向上抛出异常。
        """

    @abc.abstractmethod
    def get_zipball_url(self, project_url: str, tag: str) -> Optional[str]:
        """获取指定 tag 的源码压缩包下载地址。

        Args:
            project_url: 项目 URL。
            tag: 标签或版本名称。

        Returns:
            Optional[str]: 下载 URL；URL 非法或该平台不支持时返回 ``None``。
        """

    @abc.abstractmethod
    def get_repo_info(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """获取仓库基本信息。

        Args:
            project_url: 项目 URL。

        Returns:
            Tuple[Dict, Optional[str]]: ``(仓库信息, 错误信息)``。仓库信息至少包含
            ``homepage`` 与 ``description`` 两个键（缺失时以空字符串补齐）；失败时返回
            空字典并给出错误原因，不向上抛出异常。
        """

    @abc.abstractmethod
    def get_download_stats(self, project_url: str) -> Tuple[Dict, Optional[str]]:
        """获取下载统计信息。

        Args:
            project_url: 项目 URL。

        Returns:
            Tuple[Dict, Optional[str]]: ``(下载统计, 错误信息)``。统计字典包含
            ``download_count`` 与 ``period`` 两个键；对于不提供下载统计能力的平台（如
            GitHub、Gitee），返回计数为 0 的空统计结果而非报错。
        """


class GitHubAdapter(PlatformAdapter):
    """GitHub平台适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.access_token = config["Github"]["access_key"]
        
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


# 全局平台管理器实例
platform_manager = PlatformManager(config) 