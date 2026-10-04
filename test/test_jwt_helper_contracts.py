"""Exercise real JWT helpers with a temporary configuration and user registry."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


class JWTHelperContractTests(unittest.TestCase):
    def run_helper(self, assertions, timezone='UTC0'):
        source = Path(__file__).resolve().parents[1] / 'openchecker'
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config'
            config.mkdir()
            (config / 'config.ini').write_text(
                '[UserManager]\ndefault_username=fixture-user\ndefault_password=fixture-password\n'
                '[JWT]\nsecret_key=local-test-secret-not-for-production\nexpires_minutes=30\n',
                encoding='utf-8',
            )
            script = '''
import time
if hasattr(time, 'tzset'):
    time.tzset()
import token_operator as tokens
import user_manager
''' + assertions
            result = subprocess.run(
                [sys.executable, '-c', script], cwd=directory,
                env=dict(os.environ, PYTHONPATH=str(source), TZ=timezone),
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_registered_user_token_round_trip(self):
        self.run_helper('''
user = user_manager.userList[0]
assert user_manager.indexUserWithID(user.id) is user
token = tokens.createTokenForUser(user.id)
assert tokens.validate_jwt(token)
payload = tokens.decode_jwt(token)
assert payload['user_id'] == user.id
assert payload['user_name'] == user.name
''')

    def test_unknown_user_returns_none(self):
        self.run_helper("assert tokens.createTokenForUser('unknown-id') is None")

    @unittest.skipUnless(hasattr(time, 'tzset'), 'requires POSIX timezones')
    def test_valid_tokens_are_not_expired_in_any_host_timezone(self):
        for timezone in ('UTC0', 'EST5', 'CST-8'):
            with self.subTest(timezone=timezone):
                self.run_helper('''
token = tokens.createTokenWithPayload({'user_id': 'fixture', 'user_name': 'fixture'}, 30)
assert tokens.decode_jwt(token) is not None
assert not tokens.is_token_expired(token)
''', timezone)

    def test_expired_and_invalid_tokens_remain_expired(self):
        self.run_helper('''
token = tokens.createTokenWithPayload({'user_id': 'fixture', 'user_name': 'fixture'}, -1)
assert tokens.is_token_expired(token)
assert tokens.is_token_expired('not-a-token')
''', 'EST5')


if __name__ == '__main__':
    unittest.main()
