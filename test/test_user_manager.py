#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the user_manager module.

The module keeps three pieces of state that must always agree:

* ``userList``      - the authoritative list of users
* ``usernameTable`` - name -> User index used by authenticate()
* ``useridTable``   - id   -> User index used by identity() and the token code

The old mutators only touched ``userList`` (createUser) or deleted the wrong key
(update_user/delete_user), so a renamed user stayed reachable through the old
name, a freshly created user could never authenticate, and deleting a created or
renamed user raised KeyError out of a request handler. These tests pin down the
lockstep behaviour of the three structures plus the True/False contract that
main.py relies on.
"""

import os
import sys
import unittest
import uuid
from unittest import mock

# The production entry point (``python openchecker/main.py``) runs with the
# ``openchecker/`` directory on sys.path, so ``user_manager`` is imported as a
# top-level module and every caller shares one singleton state. Mirror that here
# instead of importing ``openchecker.user_manager`` so the tests exercise the
# very module the application uses.
_OPENCHECKER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "openchecker")
if _OPENCHECKER_DIR not in sys.path:
    sys.path.insert(0, _OPENCHECKER_DIR)

import user_manager


def expected_id(username):
    """Return the deterministic id user_manager derives from ``username``."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, username))

class TestUserFunctions(unittest.TestCase):
    """Unit tests for the user_manager CRUD helpers and their shared indexes."""

    def setUp(self):
        # Snapshot the module-level registries and start every test from an
        # empty, deterministic state. Snapshotting (rather than reloading the
        # module) keeps the User class identity stable for tearDown comparisons.
        self._saved_userList = list(user_manager.userList)
        self._saved_usernameTable = dict(user_manager.usernameTable)
        self._saved_useridTable = dict(user_manager.useridTable)

        del user_manager.userList[:]
        user_manager.usernameTable.clear()
        user_manager.useridTable.clear()

    def tearDown(self):
        # Restore the original state so tests running later in the same process
        # are not affected by the module-level mutations above.
        user_manager.userList[:] = self._saved_userList
        user_manager.usernameTable.clear()
        user_manager.usernameTable.update(self._saved_usernameTable)
        user_manager.useridTable.clear()
        user_manager.useridTable.update(self._saved_useridTable)

    # ------------------------------------------------------------------
    # createUser
    # ------------------------------------------------------------------
    def test_create_user_registers_user_in_list_and_both_indexes(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        self.assertIsInstance(user, user_manager.User)
        self.assertEqual("alice", user.name)
        self.assertEqual(expected_id("alice"), user.id)
        self.assertEqual(["request"], user.access)
        self.assertEqual([user], user_manager.get_all_users())
        self.assertIs(user, user_manager.usernameTable["alice"])
        self.assertIs(user, user_manager.useridTable[user.id])

    def test_created_user_can_authenticate_and_be_resolved(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        # Regression: createUser used to skip both indexes, so none of these
        # lookups could ever find the user that had just been created.
        self.assertIs(user, user_manager.authenticate("alice", "s3cret"))
        self.assertIs(user, user_manager.indexUserWithID(user.id))
        self.assertIs(user, user_manager.indexUserWithName("alice"))
        self.assertIs(user, user_manager.identity({"identity": user.id}))

    def test_create_user_refuses_duplicate_username(self):
        original = user_manager.createUser("alice", "s3cret", ["request"])

        with self.assertRaises(ValueError):
            user_manager.createUser("alice", "hijacked", ["admin"])

        # The rejected registration must not add a second user nor replace the
        # credentials/access of the account that already owns the name.
        self.assertEqual([original], user_manager.get_all_users())
        self.assertIs(original, user_manager.indexUserWithName("alice"))
        self.assertIs(original, user_manager.authenticate("alice", "s3cret"))
        self.assertIs(original, user_manager.indexUserWithID(original.id))
        self.assertEqual(["request"], original.access)

    def test_get_all_users_returns_the_live_list(self):
        alice = user_manager.createUser("alice", "s3cret", ["request"])
        bob = user_manager.createUser("bob", "other-pw", ["request"])

        self.assertEqual([alice, bob], user_manager.get_all_users())

    # ------------------------------------------------------------------
    # update_user
    # ------------------------------------------------------------------
    def test_update_user_rename_updates_indexes_but_keeps_id(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])
        original_id = user.id

        self.assertTrue(user_manager.update_user(user.id, new_username="bob"))

        self.assertEqual("bob", user.name)
        self.assertEqual(original_id, user.id)
        self.assertIsNone(user_manager.indexUserWithName("alice"))
        self.assertIs(user, user_manager.indexUserWithName("bob"))
        self.assertIs(user, user_manager.indexUserWithID(original_id))
        self.assertIs(user, user_manager.identity({"identity": original_id}))

    def test_rename_moves_the_credential_path_to_the_new_name(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        user_manager.update_user(user.id, new_username="bob")

        # Regression: the old name kept authenticating because update_user
        # deleted the freshly inserted key instead of the stale one.
        self.assertIs(user, user_manager.authenticate("bob", "s3cret"))
        self.assertIsNone(user_manager.authenticate("alice", "s3cret"))

    def test_rename_to_an_existing_username_is_refused(self):
        alice = user_manager.createUser("alice", "alice-pw", ["request"])
        bob = user_manager.createUser("bob", "bob-pw", ["request"])

        self.assertFalse(user_manager.update_user(alice.id, new_username="bob"))

        self.assertEqual("alice", alice.name)
        self.assertIs(alice, user_manager.indexUserWithName("alice"))
        self.assertIs(bob, user_manager.indexUserWithName("bob"))
        self.assertIs(alice, user_manager.authenticate("alice", "alice-pw"))
        self.assertIs(bob, user_manager.authenticate("bob", "bob-pw"))

    def test_rename_to_the_current_name_is_a_safe_noop(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        self.assertTrue(user_manager.update_user(user.id, new_username="alice"))

        self.assertEqual("alice", user.name)
        self.assertIs(user, user_manager.indexUserWithName("alice"))
        self.assertIs(user, user_manager.indexUserWithID(user.id))

    def test_update_user_rotates_password_and_access(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        updated = user_manager.update_user(user.id, new_password="rotated", new_access=["request", "admin"])

        self.assertTrue(updated)
        self.assertIs(user, user_manager.authenticate("alice", "rotated"))
        self.assertIsNone(user_manager.authenticate("alice", "s3cret"))
        self.assertEqual(["request", "admin"], user.access)

    def test_update_user_returns_false_for_unknown_id(self):
        self.assertFalse(user_manager.update_user(expected_id("ghost"), new_username="bob"))

    # ------------------------------------------------------------------
    # delete_user
    # ------------------------------------------------------------------
    def test_delete_user_removes_user_from_list_and_indexes(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        self.assertTrue(user_manager.delete_user(user.id))

        self.assertEqual([], user_manager.get_all_users())
        self.assertIsNone(user_manager.indexUserWithName("alice"))
        self.assertIsNone(user_manager.indexUserWithID(user.id))
        self.assertIsNone(user_manager.authenticate("alice", "s3cret"))
        self.assertIsNone(user_manager.identity({"identity": user.id}))

    def test_delete_user_does_not_raise_for_created_user(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        # Regression: createUser never filled usernameTable, so the old
        # delete_user raised KeyError for any user it had created.
        self.assertTrue(user_manager.delete_user(user.id))

    def test_delete_user_does_not_raise_for_renamed_user(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])
        user_manager.update_user(user.id, new_username="bob")

        # Regression: update_user deleted the renamed key, so deleting the
        # renamed user blew up with KeyError instead of returning True.
        self.assertTrue(user_manager.delete_user(user.id))
        self.assertIsNone(user_manager.indexUserWithName("bob"))
        self.assertIsNone(user_manager.indexUserWithID(user.id))
        self.assertEqual([], user_manager.get_all_users())

    def test_delete_user_returns_false_for_unknown_or_deleted_id(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        self.assertFalse(user_manager.delete_user(expected_id("ghost")))
        self.assertTrue(user_manager.delete_user(user.id))
        # Deleting twice must be a safe no-op, not an exception.
        self.assertFalse(user_manager.delete_user(user.id))

    # ------------------------------------------------------------------
    # authenticate
    # ------------------------------------------------------------------
    def test_authenticate_rejects_wrong_credentials(self):
        user_manager.createUser("alice", "s3cret", ["request"])

        self.assertIsNone(user_manager.authenticate("alice", "wrong"))
        self.assertIsNone(user_manager.authenticate("bob", "s3cret"))
        self.assertIsNone(user_manager.authenticate("alice", ""))
        self.assertIsNone(user_manager.authenticate("", "s3cret"))

    def test_authenticate_uses_compare_digest_on_encoded_passwords(self):
        user = user_manager.createUser("alice", "s3cret", ["request"])

        with mock.patch.object(user_manager, "compare_digest", return_value=True) as digest:
            # A wrong password is still accepted when compare_digest reports a
            # match, proving the constant-time comparison result is what decides.
            self.assertIs(user, user_manager.authenticate("alice", "definitely-wrong"))
            digest.assert_called_once_with(b"s3cret", b"definitely-wrong")

        with mock.patch.object(user_manager, "compare_digest", return_value=False):
            self.assertIsNone(user_manager.authenticate("alice", "s3cret"))


if __name__ == '__main__':
    unittest.main()