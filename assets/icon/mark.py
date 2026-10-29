"""AzurKit's mark, ``AzurKit.svg`` (D891: round 2's F2, the water and fire
pieces' places swapped): a disc of the four elements broken in four, the gold
air piece lifted out of it. It is the site's favicon as it is, and the Mac
app's icon on an azure tile (``tile.py``, D892).

Original geometry only: circles, arcs, polylines and SVG turbulence filters
computed here. The looks follow words (four zones, element colours, a jagged
break showing pinkish granite); no game texture, pixel, vertex or render is
read, traced or sampled (D3, D890).

Stdlib only; ``render.py`` writes it and every icon made from it.
"""
import math

# Element looks: surface colours pushed toward each element's hue (the
# owner: "make the disc the color of the elements").
EL = {
    "air": dict(  # gold
        band="#c49a3c", fil="#5a3c10", ring="#a8883e", ringline="#f0dc8c",
        rim="#d4a440", hub=("#fff0b0", "#d0a040", "#5a3c08"), seed=11),
    "water": dict(  # blue
        band="#2f6aae", fil="#b8d4ee", ring="#3c6c9e", ringline="#c8e0f4",
        rim="#4a9ae8", hub=("#d0ecff", "#2a70c8", "#061a44"), seed=23),
    "fire": dict(  # red
        band="#b23a24", fil="#3a0e06", ring="#d09a60", ringline="#4a1606",
        rim="#e2553a", hub=("#ffb49a", "#cc2c1c", "#3e0606"), seed=37),
    "earth": dict(  # green
        band="#3f7c36", fil="#dce6ac", ring="#90a270", ringline="#1e3014",
        rim="#244a2c", hub=("#bcf4a0", "#2c9a3c", "#022c0e"), seed=53),
}
GRANITE = "#a8887a"
EDGE = "#140e0a"

# Jagged break lines, one per seam (math angle 0 = east, CCW). Points are
# (radius as a fraction of R, angular offset in degrees): straight through
# the hub (a clean four-gem centre), an L-shaped step in the arc ring, then
# smaller jags out to past the rim.
SEAMS = {
    45: [(0, 0), (0.39, 0), (0.39, 15), (0.50, 15), (0.55, 7), (0.63, 9),
         (0.69, 1), (0.77, 4), (0.85, -3), (0.93, 0), (1.15, -1)],
    135: [(0, 0), (0.42, 0), (0.42, -14), (0.52, -14), (0.57, -5), (0.64, -7),
          (0.71, 2), (0.79, -1), (0.87, 4), (0.94, 1), (1.15, 2)],
    225: [(0, 0), (0.40, 0), (0.40, 15), (0.51, 15), (0.56, 6), (0.65, 8),
          (0.72, -1), (0.80, 3), (0.89, -4), (1.15, -2)],
    315: [(0, 0), (0.41, 0), (0.41, -13), (0.51, -13), (0.56, -3), (0.64, -6),
          (0.71, 3), (0.79, 0), (0.87, 5), (0.95, 2), (1.15, 3)],
}
# Seams on the diagonals (D115), so the four hues are not a "+" quartered logo.
# Each fragment spans [start, start + 90]: air top, water left, earth bottom,
# fire right (D891 swapped round 2's water and fire). The light is fixed in the
# canvas (upper left).
QUARTERS = [("air", 45), ("water", 135), ("earth", 225), ("fire", 315)]


def f(v):
    return f"{v:.1f}"


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy - r * math.sin(a)


def pts(p):
    return " ".join(f"{f(x)},{f(y)}" for x, y in p)


def seam_points(cx, cy, R, seam):
    return [polar(cx, cy, rf * R, seam + d) for rf, d in SEAMS[seam]]


def frag_polygon(cx, cy, R, start):
    a = seam_points(cx, cy, R, start)
    end = (start + 90) % 360
    b = seam_points(cx, cy, R, end)
    a0 = start + SEAMS[start][-1][1]
    a1 = start + 90 + SEAMS[end][-1][1]
    arc = [polar(cx, cy, 1.15 * R, a0 + (a1 - a0) * k / 24) for k in range(1, 24)]
    return a + arc + b[::-1]


def annulus(cx, cy, r1, r2):
    def circ(r):
        return (f"M{f(cx + r)},{f(cy)} A{f(r)},{f(r)} 0 1,0 {f(cx - r)},{f(cy)} "
                f"A{f(r)},{f(r)} 0 1,0 {f(cx + r)},{f(cy)} Z")
    return f'<path fill-rule="evenodd" d="{circ(r2)} {circ(r1)}"'


def local(cx, cy, r, deg, t, u):
    """Point at tangential offset t and radial offset u from (r, deg)."""
    a = math.radians(deg)
    ux, uy = math.cos(a), -math.sin(a)
    tx, ty = -math.sin(a), -math.cos(a)
    return cx + (r + u) * ux + t * tx, cy + (r + u) * uy + t * ty


def filters():
    out = []
    for name, e in EL.items():
        out.append(
            f'<filter id="mot_{name}" filterUnits="userSpaceOnUse" x="-200" y="-200" '
            f'width="1424" height="1424" color-interpolation-filters="sRGB">'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.034" numOctaves="4" '
            f'seed="{e["seed"]}" result="n"/>'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.22" numOctaves="2" '
            f'seed="{e["seed"] + 1}" result="s"/>'
            '<feColorMatrix in="n" type="matrix" values="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 0 1" result="g"/>'
            '<feColorMatrix in="s" type="matrix" values="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 0 1" result="sg"/>'
            '<feComponentTransfer in="sg" result="sp"><feFuncR type="discrete" tableValues="0.74 0.9 1 1 1 1 1"/>'
            '<feFuncG type="discrete" tableValues="0.74 0.9 1 1 1 1 1"/>'
            '<feFuncB type="discrete" tableValues="0.74 0.9 1 1 1 1 1"/></feComponentTransfer>'
            '<feComposite in="SourceGraphic" in2="g" operator="arithmetic" k1="0.8" k2="0.6" result="m"/>'
            '<feComposite in="m" in2="sp" operator="arithmetic" k1="1.06" result="m2"/>'
            '<feComposite in="m2" in2="SourceGraphic" operator="in"/></filter>')
    # Speckled pinkish granite for the broken faces.
    out.append(
        '<filter id="granite" filterUnits="userSpaceOnUse" x="-200" y="-200" width="1424" '
        'height="1424" color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.35" numOctaves="2" seed="5" result="s"/>'
        '<feColorMatrix in="s" type="matrix" values="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 0 1" result="g"/>'
        '<feComponentTransfer in="g" result="t"><feFuncR type="discrete" tableValues="0.45 0.7 0.8 0.8 0.9 1"/>'
        '<feFuncG type="discrete" tableValues="0.45 0.7 0.8 0.8 0.9 1"/>'
        '<feFuncB type="discrete" tableValues="0.45 0.7 0.8 0.8 0.9 1"/></feComponentTransfer>'
        '<feComposite in="SourceGraphic" in2="t" operator="arithmetic" k1="1.3" result="m"/>'
        '<feComposite in="m" in2="SourceGraphic" operator="in"/></filter>')
    # Foam mottling for water's rim, flecks for fire's.
    out.append(
        '<filter id="foam" filterUnits="userSpaceOnUse" x="-200" y="-200" width="1424" '
        'height="1424" color-interpolation-filters="sRGB">'
        '<feTurbulence type="turbulence" baseFrequency="0.05" numOctaves="3" seed="7" result="n"/>'
        '<feColorMatrix in="n" type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 2.0 0 0 0 -0.62" result="w"/>'
        '<feComposite in="w" in2="SourceGraphic" operator="in" result="wc"/>'
        '<feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="wc"/></feMerge></filter>')
    out.append(
        '<filter id="soft" x="-30%" y="-30%" width="160%" height="160%">'
        '<feGaussianBlur stdDeviation="16"/></filter>')
    return "".join(out)


def gradients(cx, cy, R, tag):
    out = []
    for name, e in EL.items():
        hi, mid, lo = e["hub"]
        out.append(
            f'<radialGradient id="hub_{name}{tag}" gradientUnits="userSpaceOnUse" '
            f'cx="{f(cx)}" cy="{f(cy)}" r="{f(0.36 * R)}" fx="{f(cx - 0.13 * R)}" fy="{f(cy - 0.15 * R)}">'
            f'<stop offset="0" stop-color="{hi}"/><stop offset="0.45" stop-color="{mid}"/>'
            f'<stop offset="1" stop-color="{lo}"/></radialGradient>')
    out.append(
        f'<radialGradient id="spec{tag}" gradientUnits="userSpaceOnUse" cx="{f(cx - 0.11 * R)}" '
        f'cy="{f(cy - 0.15 * R)}" r="{f(0.13 * R)}">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0.95"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')
    out.append(
        f'<radialGradient id="sheen{tag}" gradientUnits="userSpaceOnUse" cx="{f(cx - 0.45 * R)}" '
        f'cy="{f(cy - 0.55 * R)}" r="{f(1.1 * R)}">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0.28"/>'
        '<stop offset="0.6" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0.22"/></radialGradient>')
    return "".join(out)


def rim_motif(name, cx, cy, R):
    r_in, r_out = 0.84 * R, R
    rm = (r_in + r_out) / 2
    e = EL[name]
    s = [f'{annulus(cx, cy, r_in, r_out)} fill="{e["rim"]}" filter="url(#mot_{name})"/>']
    if name == "air":  # a lace of round-topped arches
        n, w = 40, math.pi * rm / 40 * 0.78
        for k in range(n):
            a = k * 360 / n + 4.5
            p = [local(cx, cy, r_in, a, -w, 3), local(cx, cy, r_in, a, -w, 0.55 * (r_out - r_in))]
            top = 0.55 * (r_out - r_in)
            for j in range(1, 12):
                th = math.pi * j / 12
                p.append(local(cx, cy, r_in, a, -w * math.cos(th), top + w * math.sin(th)))
            p += [local(cx, cy, r_in, a, w, top), local(cx, cy, r_in, a, w, 3)]
            s.append(f'<polygon points="{pts(p)}" fill="#f8eca0" stroke="#3a2a08" '
                     f'stroke-width="3" stroke-linejoin="round"/>')
    elif name == "water":  # a rippling wave with foam, and a pale marble lip
        s.append(f'{annulus(cx, cy, r_in, r_out)} fill="#3e8ce0" filter="url(#foam)" opacity="0.85"/>')
        for ph, col, wd in ((0, "#0e2c58", 5), (1.1, "#e4f6ff", 3)):
            p = [polar(cx, cy, rm + 0.022 * R * math.sin(14 * math.radians(t) + ph), t)
                 for t in range(0, 361, 2)]
            s.append(f'<polyline points="{pts(p)}" fill="none" stroke="{col}" stroke-width="{wd}"/>')
        s.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R - 6)}" fill="none" '
                 f'stroke="#9cc0cc" stroke-width="12"/>')
    elif name == "fire":  # dark half-discs along the outer edge, like flame tongues
        n = 34
        for k in range(n):
            x, y = polar(cx, cy, R, k * 360 / n + 3)
            s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.05 * R)}" fill="#34100a"/>')
        s.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r_in + 3)}" fill="none" '
                 f'stroke="#f4b890" stroke-width="3" opacity="0.8"/>')
    elif name == "earth":  # pale pointed studs pointing to the centre
        n, w, h = 34, 0.026 * R, 0.13 * R
        for k in range(n):
            a = k * 360 / n + 2
            p = [local(cx, cy, r_in, a, -w, h + 1), local(cx, cy, r_in, a, w, h + 1),
                 local(cx, cy, r_in, a, 0.9 * w, 0.55 * h), local(cx, cy, r_in, a, 0, 0.12 * h),
                 local(cx, cy, r_in, a, -0.9 * w, 0.55 * h)]
            s.append(f'<polygon points="{pts(p)}" fill="#dfe6bc" stroke="#43543a" stroke-width="2.5" '
                     f'stroke-linejoin="round"/>')
    for r, wd in ((r_in, 4), (R - 1, 5)):
        s.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="none" stroke="{EDGE}" '
                 f'stroke-width="{wd}" opacity="0.85"/>')
    return "".join(s)


def ring_motif(name, cx, cy, R):
    r1, r2 = 0.36 * R, 0.52 * R
    e = EL[name]
    s = [f'{annulus(cx, cy, r1, r2)} fill="{e["ring"]}" filter="url(#mot_{name})"/>']
    lc = e["ringline"]
    clip = f'clip_ring_{name}_{int(cx)}_{int(cy)}'
    s.append(f'<clipPath id="{clip}">{annulus(cx, cy, r1, r2)}/></clipPath><g clip-path="url(#{clip})">')
    if name == "air":  # a rosette of overlapping circles
        for k in range(12):
            x, y = polar(cx, cy, 0.44 * R, k * 30 + 15)
            s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.085 * R)}" fill="none" '
                     f'stroke="{lc}" stroke-width="3"/>')
    elif name == "water":  # stacked wave crests
        for k in range(20):
            x, y = polar(cx, cy, 0.37 * R, k * 18)
            s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.1 * R)}" fill="none" '
                     f'stroke="{lc}" stroke-width="3"/>')
    elif name == "fire":  # a crown of pointed arches
        n = 18
        for k in range(n):
            a0, a1 = k * 360 / n, (k + 1) * 360 / n
            p = [polar(cx, cy, r1, a0)]
            for j in range(1, 8):
                t = j / 8
                am = a0 + (a1 - a0) * t
                rr = r1 + (r2 - r1 - 4) * math.sin(math.pi * t) ** 0.6
                p.append(polar(cx, cy, rr, am))
            p.append(polar(cx, cy, r1, a1))
            s.append(f'<polyline points="{pts(p)}" fill="none" stroke="{lc}" stroke-width="3.5"/>')
    elif name == "earth":  # a pointed star
        n = 16
        p = []
        for k in range(2 * n + 1):
            p.append(polar(cx, cy, r2 - 4 if k % 2 == 0 else r1 + 4, k * 180 / n))
        s.append(f'<polyline points="{pts(p)}" fill="none" stroke="{lc}" stroke-width="3"/>')
        p2 = [polar(cx, cy, r2 - 4 if k % 2 else r1 + 4, k * 180 / n) for k in range(2 * n + 1)]
        s.append(f'<polyline points="{pts(p2)}" fill="none" stroke="{lc}" stroke-width="2" opacity="0.5"/>')
    s.append("</g>")
    for r in (r1, r2):
        s.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="none" stroke="{EDGE}" '
                 f'stroke-width="3.5" opacity="0.8"/>')
    return "".join(s)


def filigree(name, cx, cy, R):
    """An engraved vine with curls across the stone band (our own mark)."""
    col = EL[name]["fil"]
    p = [polar(cx, cy, 0.70 * R + 0.045 * R * math.sin(math.radians(12 * t)), t)
         for t in range(0, 361, 2)]
    s = [f'<polyline points="{pts(p)}" fill="none" stroke="{col}" stroke-width="3.5" opacity="0.4"/>']
    for k in range(24):
        t = k * 15 + 7.5
        rr = 0.70 * R + 0.045 * R * math.sin(math.radians(12 * t))
        x, y = polar(cx, cy, rr + (0.045 * R if k % 2 == 0 else -0.045 * R), t)
        s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(0.022 * R)}" fill="none" stroke="{col}" '
                 f'stroke-width="3" opacity="0.4"/>')
    return "".join(s)


def fragment_face(name, start, cx, cy, R, tag):
    e = EL[name]
    cid = f"frag_{name}{tag}"
    poly = frag_polygon(cx, cy, R, start)
    s = [f'<clipPath id="{cid}"><polygon points="{pts(poly)}"/></clipPath>',
         f'<clipPath id="c{cid}"><circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}"/></clipPath>',
         f'<g clip-path="url(#{cid})"><g clip-path="url(#c{cid})">',
         f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}" fill="{e["band"]}" filter="url(#mot_{name})"/>',
         filigree(name, cx, cy, R),
         ring_motif(name, cx, cy, R),
         rim_motif(name, cx, cy, R),
         f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(0.36 * R)}" fill="url(#hub_{name}{tag})"/>',
         f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(0.36 * R)}" fill="{e["hub"][1]}" '
         f'filter="url(#mot_{name})" opacity="0.35"/>',
         f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(0.36 * R)}" fill="none" stroke="#f4e2a8" '
         f'stroke-width="4" opacity="0.7"/>',
         f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(0.36 * R + 3)}" fill="none" stroke="{EDGE}" stroke-width="4"/>',
         f'<ellipse cx="{f(cx - 0.11 * R)}" cy="{f(cy - 0.15 * R)}" rx="{f(0.13 * R)}" '
         f'ry="{f(0.08 * R)}" transform="rotate(-35 {f(cx - 0.11 * R)} {f(cy - 0.15 * R)})" '
         f'fill="url(#spec{tag})"/>',
         f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}" fill="url(#sheen{tag})"/>']
    # The broken edges: a strip of raw granite along both breaks, then a dark line.
    for seam in (start, (start + 90) % 360):
        sp = seam_points(cx, cy, R, seam)
        s.append(f'<polyline points="{pts(sp)}" fill="none" stroke="{GRANITE}" stroke-width="16" '
                 f'stroke-linejoin="miter" filter="url(#granite)"/>')
        s.append(f'<polyline points="{pts(sp)}" fill="none" stroke="{EDGE}" stroke-width="4" '
                 f'stroke-linejoin="miter"/>')
    s.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R - 1.5)}" fill="none" stroke="{EDGE}" stroke-width="4"/>')
    s.append("</g></g>")
    return "".join(s)


def fragment_side(name, start, cx, cy, R, tag, depth):
    """The slab's thickness, seen below the face: granite with a dark rim."""
    cid = f"side_{name}{tag}"
    poly = frag_polygon(cx, cy, R, start)
    return (f'<clipPath id="{cid}"><polygon points="{pts(poly)}"/></clipPath>'
            f'<g transform="translate(0 {f(depth)})" clip-path="url(#{cid})">'
            f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}" fill="#8a6a5c" filter="url(#granite)"/>'
            f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R - depth * 0.6)}" fill="none" '
            f'stroke="#2a1c14" stroke-width="{f(depth * 1.3)}"/>'
            f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}" fill="#000" opacity="0.3"/></g>')


def head():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" '
            'width="1024" height="1024">')


def disc(cx, cy, R, explode, depth, tag, moves=None, drop=0):
    """Four fragments; moves[name] = (dx, dy, rot) lifts a piece out; drop > 0
    gives each piece its own soft ground shadow (a free shape's)."""
    moves = moves or {}
    s = []
    if drop:
        for name, start in QUARTERS:
            bis = start + 45
            dx, dy = explode * math.cos(math.radians(bis)), -explode * math.sin(math.radians(bis))
            mx, my, rot = moves.get(name, (0, 0, 0))
            pc = polar(cx, cy, 0.5 * R, bis)
            s.append(f'<g transform="translate({f(dx + mx)} {f(dy + my + drop)}) '
                     f'rotate({rot} {f(pc[0])} {f(pc[1])})" opacity="0.4" filter="url(#soft)">'
                     f'<clipPath id="gs_{name}{tag}"><polygon points="{pts(frag_polygon(cx, cy, R, start))}"/>'
                     f'</clipPath><circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}" fill="#000" '
                     f'clip-path="url(#gs_{name}{tag})"/></g>')
    order = [q for q in QUARTERS if q[0] not in moves] + [q for q in QUARTERS if q[0] in moves]
    lifted = False
    for name, start in order:
        bis = start + 45
        dx, dy = explode * math.cos(math.radians(bis)), -explode * math.sin(math.radians(bis))
        mx, my, rot = moves.get(name, (0, 0, 0))
        if name in moves and not lifted:
            # its shadow falls on the pieces still in place
            pc = polar(cx, cy, 0.5 * R, bis)
            rest = "".join(f'<polygon points="{pts(frag_polygon(cx, cy, R, st))}"/>'
                           for nm, st in QUARTERS if nm not in moves)
            s.append(f'<clipPath id="rest{tag}">{rest}</clipPath><clipPath id="rc{tag}">'
                     f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}"/></clipPath>'
                     f'<g clip-path="url(#rest{tag})"><g clip-path="url(#rc{tag})">')
            s.append(f'<g transform="translate({f(dx + mx * 0.45 + 10)} {f(dy + my * 0.45 + 26)}) '
                     f'rotate({rot} {f(pc[0])} {f(pc[1])})" opacity="0.55" filter="url(#soft)">'
                     f'<clipPath id="shad{tag}"><polygon points="{pts(frag_polygon(cx, cy, R, start))}"/>'
                     f'</clipPath><circle cx="{f(cx)}" cy="{f(cy)}" r="{f(R)}" fill="#000" '
                     f'clip-path="url(#shad{tag})"/></g></g></g>')
            lifted = True
        pc = polar(cx, cy, 0.5 * R, bis)
        tr = f'translate({f(dx + mx)} {f(dy + my)}) rotate({rot} {f(pc[0])} {f(pc[1])})'
        s.append(f'<g transform="{tr}">{fragment_side(name, start, cx, cy, R, tag, depth)}'
                 f'{fragment_face(name, start, cx, cy, R, tag)}</g>')
    return "".join(s)


def svg() -> str:
    """The mark: the 1024 master (``AzurKit.svg``)."""
    # The top (air) piece is lifted out of the disc: the one being collected.
    cx, cy, R = 512, 585, 340
    mv = {"air": (16, -150, -6)}
    s = [head(), "<defs>", filters(), gradients(cx, cy, R, ""), "</defs>",
         disc(cx, cy, R, 5, 18, "", mv, drop=24),
         "</svg>"]
    return "".join(s)
