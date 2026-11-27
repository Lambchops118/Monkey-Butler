"""Convert a small line-art SVG subset into Pygame-ready JSON.

Usage: python InfoPanel/graphics/convert_svg.py drawing.svg
Supported: line, polyline, polygon, rect, and paths with M/L/H/V/C/Q/Z.
Curves are sampled at a fixed number of steps. Unsupported elements fail loudly.
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
TOKEN = re.compile(rf"[MLHVQCZmlhvqcz]|{NUMBER}")
PARAMS = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'Q': 4, 'Z': 0}


def _numbers(value):
    return [float(n) for n in re.findall(NUMBER, value)]


def _path(data):
    tokens = TOKEN.findall(data)
    if re.sub(r"[\s,]", "", data) != ''.join(tokens):
        raise ValueError('Unsupported path command or syntax')
    paths, points = [], []
    x = y = sx = sy = 0.0
    i, command = 0, None
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
        if command is None:
            raise ValueError('Path starts without a command')
        kind = command.upper()
        if kind == 'Z':
            if points:
                points.append([sx, sy])
                paths.append(points)
                points = []
            x, y = sx, sy
            command = None
            continue
        count = PARAMS[kind]
        if i + count > len(tokens) or any(t.isalpha() for t in tokens[i:i + count]):
            raise ValueError(f'Incomplete {command} path command')
        values = list(map(float, tokens[i:i + count]))
        i += count
        relative = command.islower()
        if kind == 'H':
            target = (values[0] + x if relative else values[0], y)
        elif kind == 'V':
            target = (x, values[0] + y if relative else values[0])
        else:
            pairs = [(values[j], values[j + 1]) for j in range(0, count, 2)]
            if relative:
                pairs = [(a + x, b + y) for a, b in pairs]
            target = pairs[-1]
        if kind == 'M':
            if points:
                paths.append(points)
            points = [[*target]]
            sx, sy = target
            command = 'l' if relative else 'L'
        elif kind in ('C', 'Q'):
            steps = 16
            for step in range(1, steps + 1):
                t = step / steps
                u = 1 - t
                if kind == 'Q':
                    cx, cy = pairs[0]
                    px = u*u*x + 2*u*t*cx + t*t*target[0]
                    py = u*u*y + 2*u*t*cy + t*t*target[1]
                else:
                    a, b = pairs[:2]
                    px = u**3*x + 3*u*u*t*a[0] + 3*u*t*t*b[0] + t**3*target[0]
                    py = u**3*y + 3*u*u*t*a[1] + 3*u*t*t*b[1] + t**3*target[1]
                points.append([round(px, 4), round(py, 4)])
        else:
            points.append([*target])
        x, y = target
    if points:
        paths.append(points)
    return paths


def convert(source):
    root = ET.parse(source).getroot()
    view = _numbers(root.attrib.get('viewBox', ''))
    if len(view) != 4 or view[2] <= 0 or view[3] <= 0:
        raise ValueError('SVG needs a positive viewBox')
    paths = []
    def visit(element):
        tag = element.tag.rsplit('}', 1)[-1]
        if tag in ('svg', 'g'):
            if 'transform' in element.attrib:
                raise ValueError('Group transforms must be flattened in the editor')
            for child in element:
                visit(child)
            return
        if tag in ('title', 'desc', 'metadata', 'namedview'):
            return
        if 'transform' in element.attrib:
            raise ValueError(f'Transform on {tag} must be flattened in the editor')
        a = element.attrib
        if tag == 'path':
            shape = _path(a['d'])
        elif tag == 'line':
            shape = [[[float(a['x1']), float(a['y1'])], [float(a['x2']), float(a['y2'])]]]
        elif tag in ('polyline', 'polygon'):
            nums = _numbers(a['points'])
            if len(nums) < 4 or len(nums) % 2:
                raise ValueError(f'Invalid {tag} points')
            pts = [[nums[j], nums[j+1]] for j in range(0, len(nums), 2)]
            if tag == 'polygon':
                pts.append(pts[0])
            shape = [pts]
        elif tag == 'rect':
            x, y = float(a['x']), float(a['y'])
            w, h = float(a['width']), float(a['height'])
            shape = [[[x,y], [x+w,y], [x+w,y+h], [x,y+h], [x,y]]]
        else:
            raise ValueError(f'Unsupported SVG element: {tag}')
        paths.extend(p for p in shape if len(p) >= 2)
    visit(root)
    return {'version': 1, 'viewBox': view, 'paths': paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('svg', type=Path)
    args = parser.parse_args()
    output = args.svg.with_suffix('.json')
    output.write_text(json.dumps(convert(args.svg), separators=(',', ':')) + '\n')
    print(output)


if __name__ == '__main__':
    main()
