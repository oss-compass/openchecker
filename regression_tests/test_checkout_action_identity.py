from openchecker.checkers.dangerous_workflow_checker import check_untrusted_checkout


def test_only_official_checkout_action_is_checked():
    ref = '${{ github.event.pull_request.head.sha }}'
    workflow = {
        'on': 'pull_request_target',
        'jobs': {'scan': {'steps': [
            {'uses': 'example/actions/checkout@v4', 'with': {'ref': ref}},
            {'uses': 'actions/checkout-helper@v4', 'with': {'ref': ref}},
            {'uses': 'actions/checkout@v4', 'with': {'ref': ref}},
        ]}},
    }

    findings = check_untrusted_checkout(workflow, 'workflow.yml', 'github')

    assert len(findings) == 1
    assert findings[0]['line'] == 3
