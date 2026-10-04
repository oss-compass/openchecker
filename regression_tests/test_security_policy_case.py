from pathlib import Path

from openchecker.checkers.security_policy_checker import find_security_policy_files


def test_mixed_case_policy_names_in_supported_locations(tmp_path):
    (tmp_path / 'Security.Md').write_text('policy', encoding='utf-8')
    platform_dir = tmp_path / '.GitHub'
    platform_dir.mkdir()
    (platform_dir / 'SECURITY.MARKDOWN').write_text('policy', encoding='utf-8')
    docs_dir = tmp_path / 'Docs'
    docs_dir.mkdir()
    (docs_dir / 'SeCuRiTy.rst').write_text('policy', encoding='utf-8')
    (docs_dir / 'other.md').write_text('not a policy', encoding='utf-8')

    found = find_security_policy_files(str(tmp_path), 'github')

    assert {Path(path).name for path in found} == {'Security.Md', 'SECURITY.MARKDOWN', 'SeCuRiTy.rst'}
