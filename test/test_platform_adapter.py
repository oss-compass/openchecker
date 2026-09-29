"""
平台适配器测试模块

测试GitHub、Gitee、GitCode平台适配器的功能。
"""

import unittest
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from openchecker.platform_adapter import (
    PlatformAdapter, 
    GitHubAdapter, 
    GiteeAdapter, 
    GitCodeAdapter, 
    PlatformManager
)
from openchecker.helper import read_config


class TestPlatformAdapter(unittest.TestCase):
    """平台适配器测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 获取配置
        file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(file_dir)
        config_file = os.path.join(project_root, "config", "config.ini")
        self.config = read_config(config_file)
        self.platform_manager = PlatformManager(self.config)
        
    def test_github_adapter_creation(self):
        """测试GitHub适配器创建"""
        adapter = GitHubAdapter(self.config)
        self.assertEqual(adapter.get_platform_name(), "github")
        
    def test_gitee_adapter_creation(self):
        """测试Gitee适配器创建"""
        adapter = GiteeAdapter(self.config)
        self.assertEqual(adapter.get_platform_name(), "gitee")
        
    def test_gitcode_adapter_creation(self):
        """测试GitCode适配器创建"""
        adapter = GitCodeAdapter(self.config)
        self.assertEqual(adapter.get_platform_name(), "gitcode")
        
    def test_github_url_parsing(self):
        """测试GitHub URL解析"""
        adapter = GitHubAdapter(self.config)
        project_url = "https://github.com/owner/repo.git"
        owner, repo = adapter.parse_project_url(project_url)
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        
    def test_gitee_url_parsing(self):
        """测试Gitee URL解析"""
        adapter = GiteeAdapter(self.config)
        project_url = "https://gitee.com/owner/repo.git"
        owner, repo = adapter.parse_project_url(project_url)
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        
    def test_gitcode_url_parsing(self):
        """测试GitCode URL解析"""
        adapter = GitCodeAdapter(self.config)
        project_url = "https://gitcode.com/owner/repo.git"
        owner, repo = adapter.parse_project_url(project_url)
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        
    def test_platform_manager_get_adapter(self):
        """测试平台管理器获取适配器"""
        # GitHub
        github_url = "https://github.com/owner/repo.git"
        adapter = self.platform_manager.get_adapter(github_url)
        self.assertIsInstance(adapter, GitHubAdapter)
        
        # Gitee
        gitee_url = "https://gitee.com/owner/repo.git"
        adapter = self.platform_manager.get_adapter(gitee_url)
        self.assertIsInstance(adapter, GiteeAdapter)
        
        # GitCode
        gitcode_url = "https://gitcode.com/owner/repo.git"
        adapter = self.platform_manager.get_adapter(gitcode_url)
        self.assertIsInstance(adapter, GitCodeAdapter)
        
        # 不支持的平台
        unsupported_url = "https://unsupported.com/owner/repo.git"
        adapter = self.platform_manager.get_adapter(unsupported_url)
        self.assertIsNone(adapter)
        
    def test_platform_manager_parse_project_url(self):
        """测试平台管理器解析项目URL"""
        # GitHub
        github_url = "https://github.com/owner/repo.git"
        owner, repo = self.platform_manager.parse_project_url(github_url)
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        
        # Gitee
        gitee_url = "https://gitee.com/owner/repo.git"
        owner, repo = self.platform_manager.parse_project_url(gitee_url)
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        
        # GitCode
        gitcode_url = "https://gitcode.com/owner/repo.git"
        owner, repo = self.platform_manager.parse_project_url(gitcode_url)
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        
    def test_github_zipball_url(self):
        """测试GitHub zipball URL生成"""
        adapter = GitHubAdapter(self.config)
        project_url = "https://github.com/owner/repo.git"
        tag = "v1.0.0"
        zipball_url = adapter.get_zipball_url(project_url, tag)
        expected_url = "https://github.com/owner/repo/archive/refs/tags/v1.0.0.zip"
        self.assertEqual(zipball_url, expected_url)
        
    def test_gitee_zipball_url(self):
        """测试Gitee zipball URL生成"""
        adapter = GiteeAdapter(self.config)
        project_url = "https://gitee.com/owner/repo.git"
        tag = "v1.0.0"
        zipball_url = adapter.get_zipball_url(project_url, tag)
        expected_url = "https://gitee.com/owner/repo/repository/archive/v1.0.0.zip"
        self.assertEqual(zipball_url, expected_url)
        
    def test_gitcode_zipball_url(self):
        """测试GitCode zipball URL生成"""
        adapter = GitCodeAdapter(self.config)
        project_url = "https://gitcode.com/owner/repo.git"
        tag = "v1.0.0"
        zipball_url = adapter.get_zipball_url(project_url, tag)
        expected_url = "https://gitcode.com/owner/repo/-/archive/v1.0.0/repo-v1.0.0.zip"
        self.assertEqual(zipball_url, expected_url)
        
    def test_invalid_url_format(self):
        """测试无效URL格式"""
        adapter = GitHubAdapter(self.config)
        invalid_url = "https://invalid.com/owner/repo.git"
        
        with self.assertRaises(ValueError):
            adapter.parse_project_url(invalid_url)
            
    def test_platform_manager_unsupported_platform(self):
        """测试平台管理器处理不支持的平台"""
        unsupported_url = "https://unsupported.com/owner/repo.git"
        
        with self.assertRaises(ValueError):
            self.platform_manager.parse_project_url(unsupported_url)


if __name__ == '__main__':
    unittest.main() 