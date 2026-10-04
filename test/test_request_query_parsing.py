import unittest

from aksk.default_request import DefaultRequest
from aksk.signer import Signer


class RequestQueryParsingTests(unittest.TestCase):
    def request(self, url):
        request = DefaultRequest('example', 'secret')
        request.set_method('GET')
        request.set_timestamp('1700000000000')
        request.set_url(url)
        return request

    def test_url_query_matches_explicit_parameters_when_signing(self):
        parsed = self.request('/scan?name=hello%20world&branch=main')
        explicit = self.request('/scan')
        explicit.add_query_param('name', 'hello world')
        explicit.add_query_param('branch', 'main')
        self.assertEqual(parsed.get_path(), explicit.get_path())
        self.assertEqual(parsed.get_query_params(), explicit.get_query_params())
        self.assertEqual(Signer.sign(parsed), Signer.sign(explicit))

    def test_added_parameter_uses_one_query_separator(self):
        request = self.request('/scan?branch=main')
        request.add_query_param('page', '2')
        self.assertEqual(request.get_url(), '/scan?branch=main&page=2')

    def test_encoded_delimiters_and_blank_values(self):
        request = self.request('/scan?key=a%26b%3Dc&empty=&flag')
        self.assertEqual(request.get_query_params(), {
            'key': 'a%26b%3Dc', 'empty': '', 'flag': '',
        })
        self.assertEqual(request.get_url(), '/scan?key=a%26b%3Dc&empty=&flag=')

    def test_form_spaces_and_literal_plus(self):
        request = self.request('/scan?name=hello+world&literal=%2B')
        self.assertEqual(request.get_query_params(), {
            'name': 'hello%20world', 'literal': '%2B',
        })

    def test_path_only_keeps_explicit_query_parameters(self):
        request = self.request('/scan')
        request.add_query_param('page', '2')
        request.set_url('/other')
        self.assertEqual(request.get_path(), '/other')
        self.assertEqual(request.get_url(), '/other?page=2')

    def test_empty_url_keeps_existing_error(self):
        with self.assertRaises(Warning):
            self.request(' ')


if __name__ == '__main__':
    unittest.main()
