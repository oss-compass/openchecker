from openchecker.checkers.security_policy_checker import analyze_security_policy_content


def test_security_policy_extracts_complete_urls_and_keywords(tmp_path):
    policy = tmp_path / "SECURITY.md"
    policy.write_text("Report vulnerabilities at https://example.org/security/report or security@example.org. Disclosure within 90 days.", encoding="utf-8")

    result = analyze_security_policy_content(str(policy))

    assert result["urls"] == ["https://example.org/security/report"]
    assert result["emails"] == ["security@example.org"]
    assert "vulnerabilities" in result["disclosure_keywords"]
    assert "Disclosure" in result["disclosure_keywords"]
    assert "90" in result["disclosure_keywords"]
