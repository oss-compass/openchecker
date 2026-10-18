import datetime
import unittest
import jwt
from openchecker.token_operator import createTokenForUser, validate_jwt, decode_jwt, refresh_token, get_token_expiration, is_token_expired, createTokenWithPayload

class TestJWTFunctions(unittest.TestCase):

    def setUp(self):
        # 测试用的secret_key
        self.secret_key = "test_secret_key"

    def test_createTokenForUser(self):
        """测试为用户创建JWT token"""
        # Mock a user
        class MockUser:
            def __init__(self, id, name):
                self.id = id
                self.name = name

        user = MockUser(123, "test_user")
        token = createTokenForUser(user.id)
        self.assertIsNotNone(token)

        decoded_token = jwt.decode(token, self.secret_key, algorithms=['HS256'])
        self.assertEqual(decoded_token['user_id'], user.id)
        self.assertEqual(decoded_token['user_name'], user.name)
        self.assertIn('exp', decoded_token)

    def test_createTokenWithPayload(self):
        """测试使用自定义payload创建JWT token"""
        payload = {'user_id': 123, 'user_name': 'test_user', 'role': 'admin'}
        token = createTokenWithPayload(payload, expires_minutes=60)
        self.assertIsNotNone(token)

        decoded_token = decode_jwt(token)
        self.assertIsNotNone(decoded_token)
        self.assertEqual(decoded_token['user_id'], 123)
        self.assertEqual(decoded_token['user_name'], 'test_user')
        self.assertEqual(decoded_token['role'], 'admin')

    def test_validate_jwt_valid_token(self):
        """测试有效token的验证"""
        # Mock a user
        class MockUser:
            def __init__(self, id, name):
                self.id = id
                self.name = name

        user = MockUser(123, "test_user")
        token = createTokenForUser(user.id)
        result = validate_jwt(token)
        self.assertTrue(result)

    def test_validate_jwt_invalid_token(self):
        """测试无效token的验证"""
        invalid_token = "invalid_token"
        result = validate_jwt(invalid_token)
        self.assertFalse(result)

    def test_decode_jwt(self):
        """测试JWT token解码"""
        payload = {'user_id': 123, 'user_name': 'test_user'}
        token = createTokenWithPayload(payload)
        
        decoded = decode_jwt(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['user_id'], 123)
        self.assertEqual(decoded['user_name'], 'test_user')

    def test_decode_jwt_invalid_token(self):
        """测试无效token的解码"""
        invalid_token = "invalid_token"
        decoded = decode_jwt(invalid_token)
        self.assertIsNone(decoded)

    def test_refresh_token(self):
        """测试token刷新"""
        payload = {'user_id': 123, 'user_name': 'test_user'}
        original_token = createTokenWithPayload(payload, expires_minutes=1)
        
        refreshed_token = refresh_token(original_token)
        self.assertIsNotNone(refreshed_token)
        self.assertNotEqual(original_token, refreshed_token)

    def test_refresh_token_invalid_token(self):
        """测试无效token的刷新"""
        invalid_token = "invalid_token"
        refreshed_token = refresh_token(invalid_token)
        self.assertIsNone(refreshed_token)

    def test_get_token_expiration(self):
        """测试获取token过期时间"""
        payload = {'user_id': 123, 'user_name': 'test_user'}
        token = createTokenWithPayload(payload, expires_minutes=30)
        
        exp_time = get_token_expiration(token)
        self.assertIsNotNone(exp_time)
        self.assertIsInstance(exp_time, datetime.datetime)

    def test_is_token_expired(self):
        """测试token过期检查"""
        payload = {'user_id': 123, 'user_name': 'test_user'}
        token = createTokenWithPayload(payload, expires_minutes=1)
        
        # 等待token过期（这里只是测试逻辑，实际测试中可能需要模拟时间）
        expired = is_token_expired(token)
        # 由于token刚创建，应该未过期
        self.assertFalse(expired)

    def test_is_token_expired_invalid_token(self):
        """测试无效token的过期检查"""
        invalid_token = "invalid_token"
        expired = is_token_expired(invalid_token)
        self.assertTrue(expired)

if __name__ == '__main__':
    unittest.main()