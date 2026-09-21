"""
平台适配器测试模块

测试GitHub、Gitee、GitCode平台适配器的功能。
"""

import io
import shutil
import stat
import tempfile
import unittest
import sys
import os
import zipfile
from unittest.mock import Mock, patch

import requests

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from openchecker.platform_adapter import (
    PlatformAdapter, 
    GitHubAdapter, 
    GiteeAdapter, 
    GitCodeAdapter, 
    PlatformManager,
    _extract_zip_safely,
    _normalize_version,
    _pick_extracted_root
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
        expected_url = "https://raw.gitcode.com/owner/repo/archive/refs/heads/v1.0.0.zip"
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


def _build_zip(entries):
    """
    构造内存中的zip归档

    Args:
        entries: [(条目名, 内容)] 列表

    Returns:
        bytes: zip归档的二进制内容
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def _mock_response(content=b"", status_code=200):
    """构造requests响应对象的mock"""
    response = Mock()
    response.status_code = status_code
    response.content = content
    return response


class TestDownloadProjectSource(unittest.TestCase):
    """源码归档下载测试类"""

    def setUp(self):
        """测试前准备"""
        file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(file_dir)
        config_file = os.path.join(project_root, "config", "config.ini")
        self.config = read_config(config_file)
        self.platform_manager = PlatformManager(self.config)
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_normalize_version_placeholders(self):
        """测试版本号占位值归一化"""
        self.assertIsNone(_normalize_version(None))
        self.assertIsNone(_normalize_version(""))
        self.assertIsNone(_normalize_version("None"))
        self.assertIsNone(_normalize_version("  None  "))
        self.assertEqual(_normalize_version("v1.0.0"), "v1.0.0")

    def test_extract_zip_safely_rejects_path_traversal(self):
        """测试解压时拒绝路径穿越条目"""
        archive_path = os.path.join(self.temp_dir, "traversal.zip")
        with zipfile.ZipFile(archive_path, 'w') as archive:
            archive.writestr("../traversal-evil.txt", "boom")

        with zipfile.ZipFile(archive_path) as archive:
            with self.assertRaises(ValueError):
                _extract_zip_safely(archive, os.path.join(self.temp_dir, "out"))

        escaped = os.path.join(os.path.dirname(self.temp_dir), "traversal-evil.txt")
        self.assertFalse(os.path.exists(escaped))

    def test_extract_zip_safely_rejects_symbolic_link(self):
        """测试解压时拒绝符号链接条目"""
        archive_path = os.path.join(self.temp_dir, "symlink.zip")
        with zipfile.ZipFile(archive_path, 'w') as archive:
            link = zipfile.ZipInfo("repo-v1.0.0/link")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "target")

        with zipfile.ZipFile(archive_path) as archive:
            with self.assertRaises(ValueError):
                _extract_zip_safely(archive, os.path.join(self.temp_dir, "out"))

    def test_extract_zip_safely_allows_nested_entries(self):
        """测试正常嵌套条目可以解压"""
        archive_path = os.path.join(self.temp_dir, "nested.zip")
        with zipfile.ZipFile(archive_path, 'w') as archive:
            archive.writestr("repo-v1.0.0/README.md", "hello")

        out_dir = os.path.join(self.temp_dir, "out")
        with zipfile.ZipFile(archive_path) as archive:
            _extract_zip_safely(archive, out_dir)

        self.assertTrue(os.path.exists(os.path.join(out_dir, "repo-v1.0.0", "README.md")))

    def test_pick_extracted_root_descends_single_wrapper(self):
        """测试剥离归档自带的单层包装目录"""
        wrapper = os.path.join(self.temp_dir, "repo-v1.0.0")
        os.makedirs(wrapper)
        self.assertEqual(_pick_extracted_root(self.temp_dir), wrapper)

    def test_pick_extracted_root_keeps_flat_archive(self):
        """测试平铺归档不做目录下钻"""
        for name in ("README.md", "setup.py"):
            with open(os.path.join(self.temp_dir, name), 'w') as handle:
                handle.write("hello")
        self.assertEqual(_pick_extracted_root(self.temp_dir), self.temp_dir)

    @patch('openchecker.platform_adapter.requests.get')
    def test_download_project_source_success(self, mock_get):
        """测试下载并解压带单层包装目录的源码归档"""
        mock_get.return_value = _mock_response(
            _build_zip([("repo-1.0.0/README.md", "hello")])
        )
        adapter = GitHubAdapter(self.config)

        success, error = adapter.download_project_source(
            "https://github.com/owner/repo", "1.0.0", self.temp_dir
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "repo", "README.md")))
        # 临时目录必须被清理，避免repos_dir中残留.hidden目录
        leftovers = [name for name in os.listdir(self.temp_dir) if name.startswith(".repo-")]
        self.assertEqual(leftovers, [])

    @patch('openchecker.platform_adapter.requests.get')
    def test_download_project_source_flat_archive(self, mock_get):
        """测试下载平铺结构的源码归档"""
        mock_get.return_value = _mock_response(
            _build_zip([("README.md", "hello"), ("setup.py", "pass")])
        )
        adapter = GiteeAdapter(self.config)

        success, error = adapter.download_project_source(
            "https://gitee.com/owner/repo", "v1.0.0", self.temp_dir
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "repo", "setup.py")))

    @patch('openchecker.platform_adapter.requests.get')
    def test_download_project_source_skips_existing_directory(self, mock_get):
        """测试源码目录已存在时跳过重复下载"""
        os.makedirs(os.path.join(self.temp_dir, "repo"))
        adapter = GitHubAdapter(self.config)

        success, error = adapter.download_project_source(
            "https://github.com/owner/repo", "1.0.0", self.temp_dir
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        mock_get.assert_not_called()

    @patch('openchecker.platform_adapter.requests.get')
    def test_download_project_source_http_error(self, mock_get):
        """测试归档下载返回非200状态码"""
        mock_get.return_value = _mock_response(status_code=404)
        adapter = GitHubAdapter(self.config)

        success, error = adapter.download_project_source(
            "https://github.com/owner/repo", "1.0.0", self.temp_dir
        )

        self.assertFalse(success)
        self.assertIn("404", error)

    @patch('openchecker.platform_adapter.requests.get')
    def test_download_project_source_timeout(self, mock_get):
        """测试归档下载超时"""
        mock_get.side_effect = requests.Timeout("timed out")
        adapter = GitHubAdapter(self.config)

        success, error = adapter.download_project_source(
            "https://github.com/owner/repo", "1.0.0", self.temp_dir
        )

        self.assertFalse(success)
        self.assertIn("Timeout", error)

    def test_download_project_source_without_version(self):
        """测试未指定版本时回退到克隆路径"""
        adapter = GitHubAdapter(self.config)

        success, error = adapter.download_project_source(
            "https://github.com/owner/repo", "None", self.temp_dir
        )

        self.assertFalse(success)
        self.assertIn("Version number", error)

    def test_github_download_headers_use_bearer_token(self):
        """测试GitHub归档下载请求头携带token"""
        adapter = GitHubAdapter(self.config)
        headers = adapter.get_download_headers()

        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_gitee_download_headers_without_auth(self):
        """测试Gitee归档下载请求头不携带鉴权信息"""
        adapter = GiteeAdapter(self.config)
        self.assertEqual(adapter.get_download_headers(), {})

    @patch('openchecker.platform_adapter.PlatformManager.get_adapter', return_value=None)
    def test_platform_manager_download_unsupported_platform(self, mock_get_adapter):
        """测试平台管理器拒绝不支持的平台"""
        success, error = self.platform_manager.download_project_source(
            "https://unsupported.com/owner/repo", "1.0.0", self.temp_dir
        )

        self.assertFalse(success)
        self.assertIn("Unsupported platform", error)

    @patch('openchecker.platform_adapter.GitHubAdapter.download_project_source')
    def test_platform_manager_routes_to_adapter(self, mock_download):
        """测试平台管理器把下载请求路由到具体适配器"""
        mock_download.return_value = (True, None)

        success, error = self.platform_manager.download_project_source(
            "https://github.com/owner/repo", "1.0.0", self.temp_dir
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        mock_download.assert_called_once_with(
            "https://github.com/owner/repo", "1.0.0", self.temp_dir
        )


if __name__ == '__main__':
    unittest.main() 