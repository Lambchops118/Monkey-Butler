"""Render converted InfoPanel line drawings in design-space boxes."""
import json
from pathlib import Path

import pygame

GRAPHICS_DIR = Path(__file__).resolve().parent / 'graphics'


class GraphicsRenderer:
    def __init__(self, directory=GRAPHICS_DIR):
        self.directory = Path(directory)
        self._graphics = {}
        self._surfaces = {}

    def _load(self, name):
        if not name.isidentifier():
            raise ValueError('Graphic name must be an identifier')
        if name not in self._graphics:
            data = json.loads((self.directory / f'{name}.json').read_text())
            if data.get('version') != 1 or len(data.get('viewBox', [])) != 4:
                raise ValueError(f'Invalid graphic: {name}')
            self._graphics[name] = data
        return self._graphics[name]

    def draw(self, surface, layout, name, box, color, line_width=1):
        """Fit a graphic inside (x, y, w, h) design units, preserving aspect ratio."""
        data = self._load(name)
        bx, by, bw, bh = box
        vx, vy, vw, vh = data['viewBox']
        if bw <= 0 or bh <= 0 or vw <= 0 or vh <= 0:
            raise ValueError('Graphic and target box must have positive size')
        width = max(1, round(layout.length(bw)))
        height = max(1, round(layout.length(bh)))
        key = (name, width, height, tuple(color), line_width)
        if key not in self._surfaces:
            layer = pygame.Surface((width, height), pygame.SRCALPHA)
            factor = min(width / vw, height / vh)
            ox = (width - vw * factor) / 2
            oy = (height - vh * factor) / 2
            for path in data['paths']:
                points = [(round(ox + (x-vx)*factor), round(oy + (y-vy)*factor)) for x, y in path]
                if len(points) >= 2:
                    pygame.draw.lines(layer, color, False, points, max(1, round(line_width * layout.scale)))
            self._surfaces[key] = layer
        surface.blit(self._surfaces[key], (round(layout.x(bx)), round(layout.y(by))))
