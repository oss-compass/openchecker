from openchecker.checkers.fuzzing_checker import check_clusterfuzz_lite


def test_comment_header_does_not_hide_clusterfuzz_dockerfile(tmp_path):
    config_dir = tmp_path / ".clusterfuzzlite"
    config_dir.mkdir()
    dockerfile = config_dir / "Dockerfile"
    dockerfile.write_text("# Generated configuration\n\nFROM gcr.io/oss-fuzz-base/base-builder\n", encoding="utf-8")

    assert check_clusterfuzz_lite(str(tmp_path))["found"] is True

    dockerfile.write_text("# A comment only\n  # Another comment\n", encoding="utf-8")
    assert check_clusterfuzz_lite(str(tmp_path))["found"] is False
