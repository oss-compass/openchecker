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
usernameTable = {u.name: u for u in userList}
useridTable = {u.id: u for u in userList}

def createUser(username, password, access):
    user = User(str(uuid.uuid5(uuid.NAMESPACE_DNS, username)), username, password, access)
    userList.append(user)
    # The id/name indexes are built once from the initial userList, so a new user
    # has to be registered in them or it can never be found by authenticate().
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
        if new_username:
            user.name = new_username
            usernameTable[new_username] = user
            del usernameTable[user.name]
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
        del usernameTable[user.name]
        del useridTable[userID]
        return True
    return False