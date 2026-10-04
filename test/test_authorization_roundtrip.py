import unittest

from aksk.default_request import DefaultRequest
from aksk.signer import Signer


class AuthorizationRoundtripTests(unittest.TestCase):
    def test_signed_request_fields_roundtrip(self):
        request = DefaultRequest('example-access', 'example-secret')
        request.set_method('POST')
        request.set_url('/scan')
        request.set_timestamp('1700000000000')
        request.add_header('Content-Type', 'application/json')
        request.set_body('{"repository":"example"}')
        header = Signer.sign(request)
        self.assertIsNotNone(header)
        self.assertEqual(Signer.get_access_id(header), 'example-access')
        self.assertEqual(Signer.get_timestamp(header), 1700000000000)
        self.assertEqual(Signer.get_signed_headers(header), ['content-type'])
        signature = Signer.get_authorization_field(header, 'signature=')
        self.assertEqual(len(signature), 64)
        canonical = Signer.create_canonical_request(
            request, request.get_timestamp(), 'content-type',
            Signer.calculate_body_hash(request))
        self.assertEqual(signature, Signer.sign_key(canonical, 'example-secret'))

    def test_final_field_does_not_need_trailing_comma(self):
        self.assertEqual(Signer.get_timestamp('SDK-HMAC-SHA256 timestamp=123'), 123)
        self.assertFalse(Signer.get_contain_body('SDK-HMAC-SHA256 containBody=False'))

    def test_fields_are_matched_by_name(self):
        header = 'SDK-HMAC-SHA256 other_timestamp=999,timestamp=123,signature=abc'
        self.assertEqual(Signer.get_timestamp(header), 123)
        self.assertEqual(Signer.get_authorization_field(header, 'missing='), '')

    def test_legacy_access_id_and_equal_sign_in_value(self):
        header = 'SDK-HMAC-SHA256 access_id=legacy,signature=abc=='
        self.assertEqual(Signer.get_access_id(header), 'legacy')
        self.assertEqual(Signer.get_authorization_field(header, 'signature='), 'abc==')

    def test_optional_flags_roundtrip(self):
        request = DefaultRequest('example', 'secret')
        request.set_contain_path(False)
        request.set_contain_body(False)
        request.set_contain_query(False)
        header = Signer.sign(request)
        self.assertFalse(Signer.get_contain_path(header))
        self.assertFalse(Signer.get_contain_body(header))
        self.assertFalse(Signer.get_contain_query(header))

    def test_empty_header_keeps_existing_error(self):
        with self.assertRaises(Warning):
            Signer.get_timestamp(' ')


if __name__ == '__main__':
    unittest.main()
