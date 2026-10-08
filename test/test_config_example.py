"""The configuration copy in the quick-start guide must work in a checkout."""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from openchecker.helper import read_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestConfigExample(unittest.TestCase):
    def test_quick_start_configuration_copy(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        command = re.search(r"cp (config/\S+) (config/config\.ini)\b", readme)
        self.assertIsNotNone(command)
        source, destination = command.groups()

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / destination
            target.parent.mkdir(parents=True)
            shutil.copyfile(PROJECT_ROOT / source, target)
            copied = read_config(str(target))

        current = read_config(str(PROJECT_ROOT / "config/config.ini"))
        self.assertEqual(set(copied), set(current))
        for section in current:
            with self.subTest(section=section):
                self.assertEqual(set(copied[section]), set(current[section]))
        self.assertEqual(copied["RabbitMQ"]["port"], "5672")
        self.assertEqual(copied["OpenCheck"]["repos_dir"], "/tmp/repos")

    def test_existing_configuration_section_lookup(self):
        filename = str(PROJECT_ROOT / "config/config.ini")
        configuration = read_config(filename)
        self.assertEqual(read_config(filename, "RabbitMQ"), configuration["RabbitMQ"])

    def test_existing_configuration_values_are_strings(self):
        configuration = read_config(str(PROJECT_ROOT / "config/config.ini"))
        self.assertEqual(configuration["RabbitMQ"]["port"], "5672")
        self.assertIsInstance(configuration["OpenCheck"]["port"], str)
        self.assertEqual(configuration["OpenCheck"]["repos_dir"], "/tmp/repos")
