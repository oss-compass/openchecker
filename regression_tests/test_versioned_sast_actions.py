from openchecker.checkers.sast_checker import _parse_workflow_for_sast_tools


def test_versioned_official_sast_actions_are_detected():
    workflow = '''jobs:
  analyze:
    steps:
      - uses: github/codeql-action/analyze@v3
      - uses: JetBrains/qodana-action@v2024.2
      - uses: attacker/github/codeql-action/analyze@v3
'''

    assert set(_parse_workflow_for_sast_tools(workflow)) == {'codeql', 'qodana'}
