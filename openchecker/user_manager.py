import uuid
from secrets import compare_digest
from helper import read_config

class User:
    def __init__(self, id, username, password, access=['request']):
        self.id = id
        self.name = username
        self.password = password
        self.access = access

    def __str__(self):
        return f"User(id='{str(self.id)}')"

config = read_config('config/config.ini', "UserManager")
userList = [User(str(uuid.uuid5(uuid.NAMESPACE_DNS, config["default_username"])), config["default_username"], config["default_password"])]
# usernameTable and useridTable are derived indexes over userList; they are not
# independent state. Every mutator below must keep both of them in lockstep with
# userList: authenticate() resolves users only through usernameTable while
# identity()/token code resolve them only through useridTable, so a missing or
# stale entry silently becomes a login that succeeds with a revoked name or a
# freshly created user that can never log in.
usernameTable = {u.name: u for u in userList}
useridTable = {u.id: u for u in userList}

def createUser(username, password, access):
    # Usernames must stay unique because authenticate() resolves users through
    # the username index. Returning or overwriting an existing account here
    # would hand the caller another user's credentials and access, so duplicates
    # are rejected before any state is mutated.
    if indexUserWithName(username) is not None:
        raise ValueError(f"username '{username}' is already registered")
    user = User(str(uuid.uuid5(uuid.NAMESPACE_DNS, username)), username, password, access)
    # Register the new user in all three structures in the same call so it is
    # immediately authenticatable and resolvable by id.
    userList.append(user)
    usernameTable[user.name] = user
    useridTable[user.id] = user
    return user

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
        if new_username and new_username != user.name:
            # Refuse a rename that would overwrite another user's index entry.
            # Nothing is applied in that case so a rejected rename cannot
            # partially succeed (e.g. rotate the password but keep the name).
            owner = indexUserWithName(new_username)
            if owner is not None and owner is not user:
                return False
            # Capture the old name before mutating user.name. The previous
            # implementation deleted usernameTable[user.name] after assigning
            # the new name, which removed the entry it had just inserted and
            # left the old name pointing at the renamed user.
            old_name = user.name
            user.name = new_username
            usernameTable.pop(old_name, None)
            usernameTable[new_username] = user
        if new_password:
            user.password = new_password
        if new_access:
            user.access = new_access
        return True
    return False

def delete_user(userID):
    user = indexUserWithID(userID)
    if user:
        # pop(..., None) keeps the documented True/False contract: a user may
        # legitimately have no entry under its current name (created before the
        # indexes were kept in sync, or renamed by an older build), and deleting
        # it must not raise KeyError out of a request handler.
        if user in userList:
            userList.remove(user)
        usernameTable.pop(user.name, None)
        useridTable.pop(userID, None)
        return True
    return False