import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load_converter():
    spec = importlib.util.spec_from_file_location('convert_svg', ROOT / 'InfoPanel/graphics/convert_svg.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GraphicsConversionTests(unittest.TestCase):
    def test_named_paths_and_curves(self):
        with tempfile.TemporaryDirectory() as directory:
            svg = Path(directory) / 'sample.svg'
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M 10,10 L 30,10 Q 50,10 50,30 Z"/><line x1="0" y1="0" x2="100" y2="100"/></svg>')
            result = load_converter().convert(svg)
            self.assertEqual(result['viewBox'], [0.0, 0.0, 100.0, 100.0])
            self.assertEqual(result['paths'][0][0], [10.0, 10.0])
            self.assertEqual(result['paths'][0][-1], [10.0, 10.0])
            self.assertGreater(len(result['paths'][0]), 10)
            self.assertEqual(len(result['paths']), 2)

    def test_unsupported_command_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            svg = Path(directory) / 'sample.svg'
            svg.write_text('<svg viewBox="0 0 10 10"><path d="M0 0 A5 5 0 0 1 10 10"/></svg>')
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                load_converter().convert(svg)

    def test_renderer_blits_and_caches(self):
        try:
            import pygame
            from InfoPanel.graphics_renderer import GraphicsRenderer
        except ImportError:
            self.skipTest('pygame unavailable')
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'sample.json').write_text(json.dumps({
                'version': 1, 'viewBox': [0, 0, 10, 10],
                'paths': [[[0, 0], [10, 10]]],
            }))
            renderer = GraphicsRenderer(directory)
            target = pygame.Surface((50, 50))
            layout = SimpleNamespace(scale=1, length=lambda n: n, x=lambda n: n, y=lambda n: n)
            renderer.draw(target, layout, 'sample', (5, 5, 20, 20), (0, 255, 100))
            renderer.draw(target, layout, 'sample', (5, 5, 20, 20), (0, 255, 100))
            self.assertEqual(len(renderer._surfaces), 1)
            self.assertEqual(target.get_at((5, 5))[:3], (0, 255, 100))


if __name__ == '__main__':
    unittest.main()
