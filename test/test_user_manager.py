import unittest
import uuid
from secrets import compare_digest
from openchecker.user_manager import User, createUser, indexUserWithID, indexUserWithName, authenticate, identity

import openchecker.user_manager as user_manager

class TestUserFunctions(unittest.TestCase):

    def setUp(self):
        self.config = {
            "default_username": "testuser",
            "default_password": "testpassword"
        }
        # The module keeps userList/usernameTable/useridTable at module level and
        # the functions under test read those globals. Building private copies
        # here meant every assertion compared the fixtures with themselves while
        # the functions looked somewhere else, so nothing could ever match.
        # Point the module tables at this test's fixture and put them back after.
        self._saved_tables = (
            user_manager.userList[:],
            dict(user_manager.usernameTable),
            dict(user_manager.useridTable),
        )

        first_user = User(str(uuid.uuid5(uuid.NAMESPACE_DNS, self.config["default_username"])),
                          self.config["default_username"],
                          self.config["default_password"])
        user_manager.userList[:] = [first_user]
        user_manager.usernameTable.clear()
        user_manager.useridTable.clear()
        user_manager.usernameTable[first_user.name] = first_user
        user_manager.useridTable[first_user.id] = first_user

        # Same objects createUser()/indexUserWith*() mutates.
        self.userList = user_manager.userList
        self.usernameTable = user_manager.usernameTable
        self.useridTable = user_manager.useridTable

    def tearDown(self):
        saved_list, saved_by_name, saved_by_id = self._saved_tables
        user_manager.userList[:] = saved_list
        user_manager.usernameTable.clear()
        user_manager.usernameTable.update(saved_by_name)
        user_manager.useridTable.clear()
        user_manager.useridTable.update(saved_by_id)

    def test_createUser(self):
        createUser("newuser", "newpassword", ["newaccess"])
        self.assertTrue(any(u.name == "newuser" for u in self.userList))

    def test_indexUserWithID(self):
        first_user = self.userList[0]
        found_user = indexUserWithID(first_user.id)
        self.assertEqual(first_user, found_user)

    def test_indexUserWithName(self):
        first_user = self.userList[0]
        found_user = indexUserWithName(first_user.name)
        self.assertEqual(first_user, found_user)

    def test_authenticate(self):
        user = authenticate(self.config["default_username"], self.config["default_password"])
        self.assertIsNotNone(user)

    def test_identity(self):
        first_user = self.userList[0]
        payload = {'identity': first_user.id}
        found_user = identity(payload)
        self.assertEqual(first_user, found_user)

if __name__ == '__main__':
    unittest.main()