"""Run the FLUX logo script with local PNGs and a controlled HTTP response."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

try:
    import requests
    from PIL import Image, ImageFont
except ImportError:
    requests = Image = ImageFont = None

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'logo' / 'merge2.py'


@unittest.skipIf(Image is None, 'Pillow and requests are required')
class TestFluxLogoFilenames(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = self.root / 'imgs' / 'dall-e'
        self.outputs = self.root / 'imgs' / 'flux'
        self.inputs.mkdir(parents=True)
        self.outputs.mkdir(parents=True)
        png = io.BytesIO()
        Image.new('RGB', (8, 8), (3, 168, 158)).save(png, format='PNG')
        response = requests.Response()
        response.status_code = 200
        response._content = png.getvalue()
        post_patch = patch('requests.post', return_value=response)
        self.post = post_patch.start()
        self.addCleanup(post_patch.stop)
        font = ImageFont.load_default()
        font_patch = patch('PIL.ImageFont.truetype', return_value=font)
        font_patch.start()
        self.addCleanup(font_patch.stop)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def run_script(self):
        with contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(SCRIPT), run_name='__main__')

    def assert_project(self, project, prompt_name):
        Image.new('RGB', (8, 8)).save(self.inputs / (project + '.png'))
        self.run_script()
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.kwargs['json']['inputs'],
                         'name logo for software ' + prompt_name)
        self.assertEqual([p.name for p in self.outputs.iterdir()], [project + '.png'])
        with Image.open(self.outputs / (project + '.png')) as image:
            self.assertEqual(image.getpixel((0, 0)), (3, 168, 158))

    def test_ftp_project_keeps_filename(self):
        self.assert_project('ohos_ftp_srv', 'ftp server')

    def test_vulkan_project_keeps_filename(self):
        self.assert_project('vulkan-validationlayers', 'vulkan')

    def test_mmkv_project_keeps_filename(self):
        self.assert_project('tencent-mmkv', 'mmkv')

    def test_libpag_project_keeps_filename(self):
        self.assert_project('tencent-libpag', 'libpag')

    def test_unmapped_project(self):
        self.assert_project('axios', 'axios')

    def test_alias_output_is_recognized_on_rerun(self):
        Image.new('RGB', (8, 8)).save(self.inputs / 'tencent-mmkv.png')
        self.run_script()
        self.run_script()
        self.assertEqual(self.post.call_count, 1)

    def test_existing_output_is_skipped(self):
        Image.new('RGB', (8, 8)).save(self.inputs / 'tencent-mmkv.png')
        destination = self.outputs / 'tencent-mmkv.png'
        Image.new('RGB', (8, 8), (255, 0, 0)).save(destination)
        before = destination.read_bytes()
        self.run_script()
        self.post.assert_not_called()
        self.assertEqual(destination.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
