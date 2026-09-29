from openchecker.checkers.pinned_dependencies_checker import _is_version_pinned


def test_movable_tags_are_not_pinned():
    assert not _is_version_pinned("v1")
    assert not _is_version_pinned("1.2.3")
    assert not _is_version_pinned("main")
    assert _is_version_pinned("a" * 40)
    assert _is_version_pinned("sha256:" + "a" * 64)
