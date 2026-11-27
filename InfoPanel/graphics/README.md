# InfoPanel graphics

Draw line art in an SVG editor, save it here as `<name>.svg`, then run:

```sh
python InfoPanel/graphics/convert_svg.py InfoPanel/graphics/<name>.svg
```

Commit both the SVG and generated JSON. In `InfoPanel/screen.py`, add a `(name, (x, y, width, height))` entry to `GRAPHIC_PLACEMENTS`. Coordinates are in the panel's 2560×1440 design space. Graphics load once and rendered surfaces are cached by size and color.

The converter supports `line`, `polyline`, `polygon`, `rect`, and SVG path commands `M L H V C Q Z` (including relative commands). It samples curves into straight segments. Use strokes with no fills; convert text and shapes to paths and flatten transforms in the SVG editor before exporting. Unsupported SVG elements and transforms produce an error rather than incomplete output. The existing Butler portrait remains separate.
