import jwt
import datetime
from user_manager import *
from helper import read_config

# 从配置文件读取JWT配置
jwt_config = read_config('config/config.ini', "JWT")
secret_key = jwt_config.get("secret_key", "your_secret_key")
expires_minutes = int(jwt_config.get("expires_minutes", 30))

def createTokenForUser(userID):
    """
    为用户创建JWT token
    
    Args:
        userID: 用户ID
        
    Returns:
        str: JWT token字符串，如果用户不存在则返回None
    """
    userMatch = indexUserWithID(userID)
    if not userMatch:
        return None

    user = userMatch[0]
    expires_in = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_minutes)
    payload = {
        'user_id': user.id,
        'user_name': user.name,
        'exp': expires_in
    }

    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    return jwt_token

def createTokenWithPayload(payload, expires_minutes=None):
    """
    使用自定义payload创建JWT token
    
    Args:
        payload: 要编码的数据字典
        expires_minutes: token过期时间（分钟）
        
    Returns:
        str: JWT token字符串
    """
    if expires_minutes is None:
        expires_minutes = int(jwt_config.get("expires_minutes", 30))
    
    # Copy first: assigning 'exp' on the caller's dict leaks the claim into
    # whatever else reuses that dict.
    payload = dict(payload)
    expires_in = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_minutes)
    payload['exp'] = expires_in
    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    return jwt_token

def validate_jwt(token):
    """
    验证JWT token
    
    Args:
        token: JWT token字符串
        
    Returns:
        bool: 如果token有效返回True，否则返回False
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        userID = payload.get('user_id')
        userName = payload.get('user_name')
        expTime = payload.get('exp')
        
        if not userID or not userName or not expTime:
            return False

        # 检查用户是否仍然存在
        user = indexUserWithID(userID)
        if not user:
            return False

        return True
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False
    except Exception:
        return False

def decode_jwt(token):
    """
    解码JWT token
    
    Args:
        token: JWT token字符串
        
    Returns:
        dict: 解码后的payload，如果token无效则返回None
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None

def refresh_token(token):
    """
    刷新JWT token
    
    Args:
        token: 原始JWT token字符串
        
    Returns:
        str: 新的JWT token字符串，如果原始token无效则返回None
    """
    payload = decode_jwt(token)
    if payload is None:
        return None
    
    # 移除过期时间，创建新的token
    if 'exp' in payload:
        del payload['exp']
    
    return createTokenWithPayload(payload)

def get_token_expiration(token):
    """
    获取token的过期时间
    
    Args:
        token: JWT token字符串
        
    Returns:
        datetime: 过期时间，如果token无效则返回None
    """
    payload = decode_jwt(token)
    if payload is None:
        return None
    
    exp_timestamp = payload.get('exp')
    if exp_timestamp:
        return datetime.datetime.fromtimestamp(exp_timestamp)
    return None

def is_token_expired(token):
    """
    检查token是否已过期
    
    Args:
        token: JWT token字符串
        
    Returns:
        bool: 如果token已过期返回True，否则返回False
    """
    exp_time = get_token_expiration(token)
    if exp_time is None:
        return True
    
    return datetime.datetime.utcnow() > exp_time