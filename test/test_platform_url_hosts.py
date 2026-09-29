from openchecker.common import get_platform_type
from openchecker.platform_adapter import platform_manager


def test_platform_selection_uses_the_url_host():
    assert platform_manager.get_adapter("https://www.github.com/owner/repo").get_platform_name() == "github"
    assert platform_manager.get_adapter("https://github.com.evil.example/owner/repo") is None
    assert platform_manager.get_adapter("https://example.org/github.com/owner/repo") is None
    assert get_platform_type("https://gitee.com.evil.example/owner/repo") is None
