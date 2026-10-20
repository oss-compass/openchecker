"""Exercise Sonar configuration evidence through the native public scanner."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openchecker'))
from checkers import sast_checker as checker


class SonarPomEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repository'
        self.repo.mkdir()
        # Respect the existing relative repository-name resolution contract.
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp.cleanup()

    def pom(self, content, directory=''):
        path = self.repo / directory / 'pom.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return str(Path('repository') / directory / 'pom.xml')

    def scan(self, platform='github'):
        payload = {'scan_results': {'existing': {'kept': True}}}
        checker.sast_checker('https://' + platform + '.com/example/repository', payload)
        self.assertEqual(payload['scan_results']['existing'], {'kept': True})
        self.assertEqual(payload['scan_results'][checker.COMMAND]['sast_workflows'], [])
        return payload['scan_results'][checker.COMMAND]['sonar_configs']

    def expected(self, path, url):
        return {'file_path': path, 'type': 'sonar', 'url': url, 'tool_name': 'sonar'}

    def test_commented_property_is_not_configuration(self):
        self.pom('<project><properties><!-- <sonar.host.url>https://old.example</sonar.host.url> -->'
                 '</properties></project>')
        self.assertEqual(self.scan(), [])

    def test_active_property_after_comment_supplies_evidence(self):
        path = self.pom('<project><properties><!-- <sonar.host.url>https://old.example</sonar.host.url> -->'
                        '<sonar.host.url>https://active.example</sonar.host.url></properties></project>')
        self.assertEqual(self.scan(), [self.expected(path, 'https://active.example')])

    def test_cdata_is_url_text(self):
        path = self.pom('<project><properties><sonar.host.url><![CDATA[https://sonar.example/path?a=1&b=2]]>'
                        '</sonar.host.url></properties></project>')
        self.assertEqual(self.scan(), [self.expected(path, 'https://sonar.example/path?a=1&b=2')])

    def test_escaped_url_is_decoded(self):
        path = self.pom('<project><properties><sonar.host.url>https://sonar.example/?a=1&amp;b=2'
                        '</sonar.host.url></properties></project>')
        self.assertEqual(self.scan(), [self.expected(path, 'https://sonar.example/?a=1&b=2')])

    def test_prefixed_xml_property_is_detected(self):
        path = self.pom('<m:project xmlns:m="http://maven.apache.org/POM/4.0.0"><m:properties>'
                        '<m:sonar.host.url>https://sonar.example</m:sonar.host.url>'
                        '</m:properties></m:project>')
        self.assertEqual(self.scan(), [self.expected(path, 'https://sonar.example')])

    def test_malformed_xml_is_not_configuration_evidence(self):
        self.pom('<project><properties><sonar.host.url>https://sonar.example</sonar.host.url>')
        self.assertEqual(self.scan(), [])

    def test_plain_and_default_namespace_work_on_all_platforms(self):
        path = self.pom('<project xmlns="http://maven.apache.org/POM/4.0.0"><properties>'
                        '<sonar.host.url>\n  https://sonar.example  \n</sonar.host.url>'
                        '</properties></project>')
        for platform in ('github', 'gitee', 'gitcode'):
            with self.subTest(platform=platform):
                self.assertEqual(self.scan(platform), [self.expected(path, 'https://sonar.example')])

    def test_independent_modules_keep_their_paths(self):
        first = self.pom('<project><properties><sonar.host.url>https://one.example</sonar.host.url>'
                         '</properties></project>', 'module-one')
        second = self.pom('<project><properties><sonar.host.url>https://two.example</sonar.host.url>'
                          '</properties></project>', 'module-two')
        self.assertCountEqual(self.scan(), [self.expected(first, 'https://one.example'),
                                           self.expected(second, 'https://two.example')])

    def test_empty_and_missing_properties_remain_absent(self):
        self.pom('<project><properties><sonar.host.url>  </sonar.host.url></properties></project>')
        self.pom('<project><properties><name>other</name></properties></project>', 'other')
        self.assertEqual(self.scan(), [])


if __name__ == '__main__':
    unittest.main()
