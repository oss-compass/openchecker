import uuid
from secrets import compare_digest
from helper import read_config

class User:
    def __init__(self, id, username, password, access=None):
        self.id = id
        self.name = username
        self.password = password
        # A mutable default is shared by every user created without one, so a
        # single `user.access.append(...)` would grant the permission to all of
        # them.
        self.access = ['request'] if access is None else list(access)

    def __str__(self):
        return f"User(id='{str(self.id)}')"

config = read_config('config/config.ini', "UserManager")
userList = [User(str(uuid.uuid5(uuid.NAMESPACE_DNS, config["default_username"])), config["default_username"], config["default_password"])]
usernameTable = {u.name: u for u in userList}
useridTable = {u.id: u for u in userList}

def createUser(username, password, access):
    user = User(str(uuid.uuid5(uuid.NAMESPACE_DNS, username)), username, password, access)
    # Index the new user as well: without this the account exists in userList but
    # neither authenticate() nor identity() can find it.
    userList.append(user)
    usernameTable[user.name] = user
    useridTable[user.id] = user

def indexUserWithID(userID):
    return useridTable.get(userID, None)

def indexUserWithName(userName):
    return usernameTable.get(userName, None)

def authenticate(username, password):
    user = usernameTable.get(username, None)
    if user and compare_digest(user.password.encode('utf-8'), password.encode('utf-8')):
        return user
    return None

def identity(payload):
    userID = payload['identity']
    return useridTable.get(userID, None)

def get_all_users():
    return userList

def update_user(userID, new_username=None, new_password=None, new_access=None):
    user = indexUserWithID(userID)
    if user:
        if new_username:
            # Capture the old name first: `user.name` is already the new one
            # by the time the old entry is removed, which used to delete the
            # entry that had just been added.
            old_username = user.name
            user.name = new_username
            usernameTable[new_username] = user
            del usernameTable[old_username]
        if new_password:
            user.password = new_password
        if new_access:
            user.access = new_access
        return True
    return False

def delete_user(userID):
    user = indexUserWithID(userID)
    if user:
        userList.remove(user)
        usernameTable.pop(user.name, None)
        # Drop the id index too, otherwise a deleted account still resolves through
        # identity() and its token keeps working.
        useridTable.pop(user.id, None)
        del useridTable[userID]
        return True
    return False