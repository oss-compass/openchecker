from checkers.dangerous_workflow_checker import check_untrusted_checkout


def test_checkout_of_head_ref_is_reported_for_target_workflow():
    workflow = {
        "on": "pull_request_target",
        "jobs": {"build": {"steps": [
            {"uses": "actions/checkout@v4", "with": {"ref": "${{ github.head_ref }}"}},
        ]}},
    }

    findings = check_untrusted_checkout(workflow, "workflow.yml", "github")
    assert len(findings) == 1
    assert findings[0]["snippet"] == "${{ github.head_ref }}"
