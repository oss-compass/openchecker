import unittest
import uuid
from secrets import compare_digest
from user_manager import User, createUser, indexUserWithID, indexUserWithName, authenticate, identity

class TestUserFunctions(unittest.TestCase):

    def setUp(self):
        self.config = {
            "default_username": "testuser",
            "default_password": "testpassword"
        }
        self.userList = [User(str(uuid.uuid5(uuid.NAMESPACE_DNS, self.config["default_username"])), self.config["default_username"], self.config["default_password"])]
        self.usernameTable = {u.name: u for u in self.userList}
        self.useridTable = {u.id: u for u in self.userList}

    def test_createUser(self):
        createUser("newuser", "newpassword", ["newaccess"])
        self.assertTrue(any(u.name == "newuser" for u in self.userList))

    def test_created_user_is_indexed(self):
        created = createUser("indexed", "pw", ["request"])
        self.assertIs(indexUserWithName("indexed"), created)
        self.assertIs(indexUserWithID(created.id), created)
        self.assertIsNotNone(authenticate("indexed", "pw"))

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