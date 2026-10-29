"""AzurKit's macOS app icon: the mark (``AzurKit.svg``, D891) centred on an
azure tile (D892), so macOS shows our tile and not its grey one.

The tile is the n=5 superellipse of half-side 412 centred in the 1024 canvas
(Apple's macOS grid: an 824 tile inset 100), a #4aa3ff > #0b4fc4 gradient with a
white 24 % glow, and a drop shadow under it (+12 down, blur 16, black 32 %). The
mark goes in unchanged (its own lighting, shadows and textures), scaled and
moved as one group so its opaque art spans ``frac`` of the tile's height,
centred on the tile. Under the art, a navy (#04163c) contact shadow of the
art's own silhouette keeps the blue water piece off the azure tile.

AzurKit-tile.svg is the master (64 px and up), AzurKit-tile-small.svg the 16
and 32 px one (a larger mark, a stronger shadow). Stdlib only; ``render.py``
writes them.
"""
import math
import re

TILE_C, TILE_HALF = 512, 412          # Apple's 824 tile, inset 100
# The mark's opaque art (alpha >= 64 in its 1024 render): x 166..858, y 89..949.
# Its soft ground shadows reach x 128..896, y 74..993.
ART_X0, ART_Y0, ART_X1, ART_Y1 = 166, 89, 858, 949

# name: (art height / tile height, halo dilate radius and blur in tile units, halo opacity)
VARIANTS = {
    "AzurKit-tile": (0.78, 10, 0.55),
    "AzurKit-tile-small": (0.90, 30, 0.85),
}


def f(v):
    return f"{v:.1f}"


def squircle(cx, cy, half, n=5.0, k=480):
    p = []
    for i in range(k):
        t = 2 * math.pi * i / k
        c, s_ = math.cos(t), math.sin(t)
        p.append((cx + half * math.copysign(abs(c) ** (2 / n), c),
                  cy + half * math.copysign(abs(s_) ** (2 / n), s_)))
    return "M" + " L".join(f"{f(x)},{f(y)}" for x, y in p) + " Z"


def _inner(mark):
    """The mark's content inside its one 1024 ``<svg>``: drawn, never an image."""
    m = re.fullmatch(r'\s*<svg [^>]*viewBox="0 0 1024 1024"[^>]*>(.*)</svg>\s*', mark, re.S)
    assert m, "AzurKit.svg is not the expected single 1024 <svg>"
    inner = m.group(1)
    assert "<image" not in inner and "href" not in inner and "data:" not in inner
    assert not re.search(r'id="tk_', inner)
    return inner


def make(inner, frac, halo_r, halo_op):
    tile = squircle(TILE_C, TILE_C, TILE_HALF)
    k = frac * 2 * TILE_HALF / (ART_Y1 - ART_Y0)
    tx = TILE_C - k * (ART_X0 + ART_X1) / 2
    ty = TILE_C - k * (ART_Y0 + ART_Y1) / 2
    # the art's opaque silhouette, grown by halo_r, softened, navy, a little low, under the art
    # (one filter on the art's group: no <use>, the art is drawn once)
    filt = ""
    if halo_op > 0:
        filt = (f'<filter id="tk_halo" filterUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024">'
                f'<feComponentTransfer in="SourceAlpha" result="a"><feFuncA type="linear" slope="4"/>'
                f'</feComponentTransfer>'
                f'<feMorphology in="a" operator="dilate" radius="{f(halo_r)}" result="d"/>'
                f'<feGaussianBlur in="d" stdDeviation="{f(halo_r * 0.8)}" result="b"/>'
                f'<feOffset in="b" dy="{f(halo_r * 0.5)}" result="o"/>'
                f'<feFlood flood-color="#04163c" flood-opacity="{halo_op}"/>'
                f'<feComposite in2="o" operator="in" result="h"/>'
                f'<feMerge><feMergeNode in="h"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">'
           '<defs>'
           '<linearGradient id="tk_tile" x1="0" y1="0" x2="0" y2="1">'
           '<stop offset="0" stop-color="#4aa3ff"/><stop offset="1" stop-color="#0b4fc4"/></linearGradient>'
           '<radialGradient id="tk_glow" cx="0.3" cy="0.18" r="0.7">'
           '<stop offset="0" stop-color="#fff" stop-opacity="0.24"/>'
           '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
           '<filter id="tk_blur16" x="-30%" y="-30%" width="160%" height="160%">'
           '<feGaussianBlur stdDeviation="16"/></filter>'
           f'{filt}'
           f'<clipPath id="tk_clip"><path d="{tile}"/></clipPath>'
           '</defs>'
           f'<path d="{tile}" transform="translate(0 12)" fill="#000" opacity="0.32" filter="url(#tk_blur16)"/>'
           f'<path d="{tile}" fill="url(#tk_tile)"/>'
           f'<path d="{tile}" fill="url(#tk_glow)"/>'
           '<g clip-path="url(#tk_clip)"><g' + (' filter="url(#tk_halo)"' if halo_op > 0 else '') + '>'
           f'<g transform="translate({tx:.3f} {ty:.3f}) scale({k:.5f})">{inner}</g></g></g></svg>')
    box = (tx + k * ART_X0, tx + k * ART_X1, ty + k * ART_Y0, ty + k * ART_Y1)
    return svg, k, box


def svgs(mark: str) -> dict[str, str]:
    """``{file name: SVG}``: the tiles of the mark ``mark`` (``AzurKit.svg``'s text)."""
    inner = _inner(mark)
    return {f"{name}.svg": make(inner, *variant)[0] for name, variant in VARIANTS.items()}
