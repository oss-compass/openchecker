"""Report Docker base images, not instructions inside inline file contents."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openchecker'))
from checkers import pinned_dependencies_checker as checker


class DockerfileHeredocDependencyTests(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repository'
        self.repo.mkdir()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.temp.cleanup()

    def scan(self, content):
        (self.repo / 'Dockerfile').write_text(content, encoding='utf-8')
        result = {'scan_results': {'existing': 'preserved'}}
        checker.pinned_dependencies_checker(
            'https://github.com/example/repository', result)
        self.assertEqual(result['scan_results']['existing'], 'preserved')
        return result['scan_results'][checker.COMMAND]

    def assert_images(self, content, expected):
        result = self.scan(content)
        images = [item for item in result['dependencies']
                  if item['dep_type'] == checker.DEPENDENCY_TYPE_DOCKER_IMAGE]
        self.assertEqual([(item['name'], item['line_number']) for item in images],
                         expected)
        self.assertEqual(result['analysis_results']['total_dependencies'],
                         len(expected))

    def test_copy_inline_file_is_not_a_base_image(self):
        self.assert_images(
            '# syntax=docker/dockerfile:1\nFROM python:3.12\n'
            "COPY <<'EOF' /example.Dockerfile\n"
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 2), ('node', 6)])

    def test_run_redirected_file_is_not_a_base_image(self):
        self.assert_images(
            'FROM python:3.12\nRUN cat <<EOF > /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_quoted_delimiter_and_tab_stripping(self):
        self.assert_images(
            'FROM python:3.12\nRUN cat <<-"EOF" > /example.Dockerfile\n'
            '\tFROM example/inline-content:latest\n\tEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_multiple_inline_files_are_consumed_in_order(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<FIRST <<SECOND /examples/\n'
            'FROM example/first:latest\nFIRST\n'
            'FROM example/second:latest\nSECOND\nFROM node:22\n',
            [('python', 1), ('node', 7)])

    def test_continued_header_keeps_its_inline_payload(self):
        self.assert_images(
            'FROM python:3.12\nRUN cat \\\n'
            '    <<EOF > /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 6)])

    def test_quoted_operator_does_not_hide_following_images(self):
        self.assert_images(
            'FROM python:3.12\nRUN printf "%s" "<<EOF"\nFROM node:22\n',
            [('python', 1), ('node', 3)])

    def test_json_command_does_not_hide_following_images(self):
        self.assert_images(
            'FROM python:3.12\nRUN ["printf", "<<EOF"]\nFROM node:22\n',
            [('python', 1), ('node', 3)])

    def test_partly_quoted_delimiter(self):
        self.assert_images(
            "FROM python:3.12\nCOPY <<E'O'F /example.Dockerfile\n"
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_escaped_delimiter(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<E\\OF /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_delimiter_prefix_is_still_inline_data(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<EOF /example.Dockerfile\n'
            'EOFX\nFROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 6)])

    def test_tab_stripping_does_not_strip_spaces(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<-EOF /example.Dockerfile\n'
            ' EOF\nFROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 6)])

    def test_commented_header_does_not_hide_following_images(self):
        self.assert_images(
            'FROM python:3.12\n# RUN <<EOF\nFROM node:22\n',
            [('python', 1), ('node', 3)])

    def test_environment_value_does_not_start_inline_data(self):
        self.assert_images(
            'FROM python:3.12\nENV MARKER=<<EOF\nFROM node:22\n',
            [('python', 1), ('node', 3)])

    def test_onbuild_copy_inline_file(self):
        self.assert_images(
            'FROM python:3.12\nONBUILD COPY <<EOF /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_add_inline_file(self):
        self.assert_images(
            'FROM python:3.12\nADD <<EOF /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_backtick_continuation_with_comment_and_empty_line(self):
        self.assert_images(
            '# escape=`\nFROM python:3.12\nRUN cat `\n# comment\n\n'
            '    <<EOF > /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 2), ('node', 9)])

    def test_escaped_literal_operator(self):
        self.assert_images(
            'FROM python:3.12\nRUN printf "%s" \\<\\<EOF\nFROM node:22\n',
            [('python', 1), ('node', 3)])

    def test_json_command_after_flags(self):
        self.assert_images(
            'FROM python:3.12\nRUN --network=none ["printf", "<<EOF"]\n'
            'FROM node:22\n', [('python', 1), ('node', 3)])

    def test_numbered_file_descriptor(self):
        self.assert_images(
            'FROM python:3.12\nRUN cat 3<<EOF <&3 > /example.Dockerfile\n'
            'FROM example/inline-content:latest\nEOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_here_string_does_not_hide_following_images(self):
        self.assert_images(
            'FROM python:3.12\nSHELL ["/bin/bash", "-c"]\n'
            'RUN cat <<<EOF\nFROM node:22\n',
            [('python', 1), ('node', 4)])

    def test_escaped_dollar_in_double_quoted_delimiter(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<"\\$EOF" /example.Dockerfile\n'
            'FROM example/inline-content:latest\n$EOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_backslash_is_literal_inside_single_quotes(self):
        self.assert_images(
            "FROM python:3.12\nCOPY <<'\\$EOF' /example.Dockerfile\n"
            'FROM example/inline-content:latest\n\\$EOF\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_empty_marker_does_not_hide_following_images(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<"" /example.Dockerfile\nFROM node:22\n',
            [('python', 1), ('node', 3)])

    def test_modifier_expression_does_not_hide_following_images(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<${MARKER:-EOF} /example.Dockerfile\n'
            'FROM node:22\n', [('python', 1), ('node', 3)])

    def test_single_quoted_modifier_text_is_a_literal_delimiter(self):
        self.assert_images(
            "FROM python:3.12\nCOPY <<'${MARKER:-EOF}' /example.Dockerfile\n"
            'FROM example/inline-content:latest\n${MARKER:-EOF}\nFROM node:22\n',
            [('python', 1), ('node', 5)])

    def test_delimiter_can_contain_an_escaped_space(self):
        self.assert_images(
            'FROM python:3.12\nCOPY <<E\\ OF /example.Dockerfile\n'
            'FROM example/inline-content:latest\nE OF\nFROM node:22\n',
            [('python', 1), ('node', 5)])


if __name__ == '__main__':
    unittest.main()
