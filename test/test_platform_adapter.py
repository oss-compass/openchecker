"""
平台适配器测试模块

测试GitHub、Gitee、GitCode平台适配器的功能。
"""

import unittest
import sys
import os
import inspect

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


class TestAdapterUrlParsing(unittest.TestCase):
    """平台 URL 解析的合规性测试"""

    def setUp(self):
        """测试前准备"""
        file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(file_dir)
        config_file = os.path.join(project_root, "config", "config.ini")
        self.config = read_config(config_file)

    def test_github_url_variants(self):
        """测试 GitHub URL 的多种合法写法"""
        adapter = GitHubAdapter(self.config)
        cases = {
            "https://github.com/owner/repo": ("owner", "repo"),
            "https://github.com/owner/repo.git": ("owner", "repo"),
            "https://www.github.com/owner/repo": ("owner", "repo"),
            "https://www.github.com/owner/repo.git": ("owner", "repo"),
        }
        for project_url, expected in cases.items():
            with self.subTest(project_url=project_url):
                self.assertEqual(adapter.parse_project_url(project_url), expected)

    def test_gitee_url_variants(self):
        """测试 Gitee URL 的多种合法写法"""
        adapter = GiteeAdapter(self.config)
        cases = {
            "https://gitee.com/owner/repo": ("owner", "repo"),
            "https://gitee.com/owner/repo.git": ("owner", "repo"),
            "https://www.gitee.com/owner/repo": ("owner", "repo"),
        }
        for project_url, expected in cases.items():
            with self.subTest(project_url=project_url):
                self.assertEqual(adapter.parse_project_url(project_url), expected)

    def test_gitcode_url_variants(self):
        """测试 GitCode URL 的多种合法写法"""
        adapter = GitCodeAdapter(self.config)
        cases = {
            "https://gitcode.com/owner/repo": ("owner", "repo"),
            "https://gitcode.com/owner/repo.git": ("owner", "repo"),
            "https://www.gitcode.com/owner/repo": ("owner", "repo"),
        }
        for project_url, expected in cases.items():
            with self.subTest(project_url=project_url):
                self.assertEqual(adapter.parse_project_url(project_url), expected)

    def test_adapters_reject_foreign_domain(self):
        """测试适配器拒绝解析其他平台的域名"""
        cases = (
            (GitHubAdapter, "https://gitee.com/owner/repo"),
            (GiteeAdapter, "https://github.com/owner/repo"),
            (GitCodeAdapter, "https://gitcode.com.evil.com/owner/repo"),
        )
        for adapter_cls, project_url in cases:
            with self.subTest(adapter=adapter_cls.__name__, project_url=project_url):
                adapter = adapter_cls(self.config)
                with self.assertRaises(ValueError):
                    adapter.parse_project_url(project_url)

    def test_zipball_url_returns_none_for_invalid_url(self):
        """测试非法 URL 生成 zipball 时返回 None 而不是抛异常"""
        for adapter_cls in (GitHubAdapter, GiteeAdapter, GitCodeAdapter):
            with self.subTest(adapter=adapter_cls.__name__):
                adapter = adapter_cls(self.config)
                self.assertIsNone(adapter.get_zipball_url("not-a-url", "v1.0.0"))

    def test_zipball_url_variants(self):
        """测试合法 URL 生成各平台 zipball 地址"""
        cases = (
            (GitHubAdapter, "https://github.com/owner/repo",
             "https://github.com/owner/repo/archive/refs/tags/v1.0.0.zip"),
            (GiteeAdapter, "https://gitee.com/owner/repo",
             "https://gitee.com/owner/repo/repository/archive/v1.0.0.zip"),
            (GitCodeAdapter, "https://gitcode.com/owner/repo",
             "https://raw.gitcode.com/owner/repo/archive/refs/heads/v1.0.0.zip"),
        )
        for adapter_cls, project_url, expected in cases:
            with self.subTest(adapter=adapter_cls.__name__):
                adapter = adapter_cls(self.config)
                self.assertEqual(adapter.get_zipball_url(project_url, "v1.0.0"), expected)

    def test_download_stats_default_for_github_and_gitee(self):
        """测试 GitHub 与 Gitee 默认的下载统计结果"""
        for adapter_cls in (GitHubAdapter, GiteeAdapter):
            with self.subTest(adapter=adapter_cls.__name__):
                adapter = adapter_cls(self.config)
                stats, error = adapter.get_download_stats("https://example.com/owner/repo")
                self.assertIsNone(error)
                self.assertEqual(stats, {"download_count": 0, "period": ""})

    def test_platform_manager_returns_none_for_unsupported_platform(self):
        """测试不支持的平台返回 None"""
        manager = PlatformManager(self.config)
        self.assertIsNone(manager.get_adapter("https://unsupported.com/owner/repo"))

    def test_platform_manager_delegates_zipball_url(self):
        """测试 PlatformManager 对 zipball 请求的转发"""
        manager = PlatformManager(self.config)
        self.assertEqual(
            manager.get_zipball_url("https://github.com/owner/repo", "v1.0.0"),
            "https://github.com/owner/repo/archive/refs/tags/v1.0.0.zip",
        )
        self.assertIsNone(manager.get_zipball_url("https://unsupported.com/owner/repo", "v1.0.0"))


class TestPlatformAdapterContract(unittest.TestCase):
    """PlatformAdapter 抽象基类的实现契约测试"""

    CONTRACT_METHODS = (
        "get_platform_name",
        "parse_project_url",
        "get_releases",
        "get_zipball_url",
        "get_repo_info",
        "get_download_stats",
    )

    def setUp(self):
        """测试前准备"""
        file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(file_dir)
        config_file = os.path.join(project_root, "config", "config.ini")
        self.config = read_config(config_file)

    def test_base_adapter_cannot_be_instantiated(self):
        """测试抽象基类不能被直接实例化"""
        with self.assertRaises(TypeError) as ctx:
            PlatformAdapter(self.config)
        self.assertIn("abstract", str(ctx.exception).lower())

    def test_missing_abstract_method_rejected_at_instantiation(self):
        """测试缺少抽象方法实现的子类在实例化时即被拒绝"""
        class IncompleteAdapter(PlatformAdapter):
            """故意只实现一个方法，验证 ABC 的快速失败行为"""

            def get_platform_name(self):
                return "incomplete"

        with self.assertRaises(TypeError) as ctx:
            IncompleteAdapter(self.config)

        message = str(ctx.exception)
        for method_name in self.CONTRACT_METHODS[1:]:
            self.assertIn(method_name, message)

    def test_complete_subclass_can_be_instantiated(self):
        """测试完整实现全部抽象方法后可以正常实例化"""
        class StubAdapter(PlatformAdapter):
            """最小可用的桩适配器，仅用于校验契约"""

            def get_platform_name(self):
                return "stub"

            def parse_project_url(self, project_url):
                return "owner", "repo"

            def get_releases(self, project_url):
                return [], None

            def get_zipball_url(self, project_url, tag):
                return None

            def get_repo_info(self, project_url):
                return {}, None

            def get_download_stats(self, project_url):
                return {}, None

        adapter = StubAdapter(self.config)
        self.assertEqual(adapter.get_platform_name(), "stub")
        self.assertEqual(adapter.parse_project_url("https://example.com/o/r"), ("owner", "repo"))
        self.assertEqual(adapter.get_releases("https://example.com/o/r"), ([], None))
        self.assertIsNone(adapter.get_zipball_url("https://example.com/o/r", "v1"))
        self.assertEqual(adapter.get_repo_info("https://example.com/o/r"), ({}, None))
        self.assertEqual(adapter.get_download_stats("https://example.com/o/r"), ({}, None))

    def test_abstract_methods_match_contract(self):
        """测试抽象方法集合与接口契约一致"""
        self.assertEqual(
            set(PlatformAdapter.__abstractmethods__),
            set(self.CONTRACT_METHODS),
        )

    def test_builtin_adapters_implement_full_contract(self):
        """测试内置适配器全部实现了契约方法且不再是抽象类"""
        for adapter_cls in (GitHubAdapter, GiteeAdapter, GitCodeAdapter):
            with self.subTest(adapter=adapter_cls.__name__):
                self.assertFalse(
                    inspect.isabstract(adapter_cls),
                    f"{adapter_cls.__name__} should not be abstract",
                )
                adapter = adapter_cls(self.config)
                for method_name in self.CONTRACT_METHODS:
                    method = getattr(adapter, method_name)
                    self.assertTrue(callable(method))
                    self.assertFalse(getattr(method, "__isabstractmethod__", False))

    def test_platform_name_matches_manager_routing(self):
        """测试平台名称与 PlatformManager 的路由结果一致"""
        manager = PlatformManager(self.config)
        cases = (
            ("https://github.com/owner/repo", "github", GitHubAdapter),
            ("https://gitee.com/owner/repo", "gitee", GiteeAdapter),
            ("https://gitcode.com/owner/repo", "gitcode", GitCodeAdapter),
        )
        for project_url, platform_name, adapter_cls in cases:
            with self.subTest(project_url=project_url):
                adapter = manager.get_adapter(project_url)
                self.assertIsInstance(adapter, adapter_cls)
                self.assertEqual(adapter.get_platform_name(), platform_name)

    def test_manager_reuses_configured_adapter_instances(self):
        """测试管理器复用初始化好的适配器实例"""
        manager = PlatformManager(self.config)
        for host, adapter_key in (
            ("github.com", "github"),
            ("gitee.com", "gitee"),
            ("gitcode.com", "gitcode"),
        ):
            with self.subTest(adapter=adapter_key):
                self.assertIs(
                    manager.get_adapter(f"https://{host}/owner/repo"),
                    manager.adapters[adapter_key],
                )


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


if __name__ == '__main__':
    unittest.main() 