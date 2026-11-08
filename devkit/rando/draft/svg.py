"""Reach's pictures: what each movement tier reaches from a level's spawn.

``azurik-mod rando derive LEVEL --svg DIR`` (Step R1.3c) writes one SVG per
tier, ``<level>.svg`` (safe) and ``<level>_<tier>.svg``: the walkable
floors coloured by the first rung of the coverage ladder that reaches them
(no item, air 1-3, behind a gate, probe-needed movement, not reached),
the water, the gates' members, the exits, the pickups (filled when the
tier reaches them with no item) and the spawn, with a 50 m scale bar, no
axis ticks.  The floors are one embedded PNG (stdlib ``zlib``); the rest is
vector.  The pictures show geometry, so they stay outside the repository.
"""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from devkit.rando.draft.gates import PROBE_LADDER, SKIP_CLASS
from azurkit.tools.randomizer.draft.geometry import CELL
from azurkit.tools.randomizer.draft.wiring import TIERS

SURFACE, INK = "#fcfcfb", "#0b0b0b"
AIR_RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
GATE_C, PROBE_C, NONE_C, WATER_C, KILL_C = "#eb6834", "#1baf7a", "#d6d5d0", "#e4ecf1", "#d03b3b"
STATES = ["reached with no item", "needs air 1", "needs air 2", "needs air 3", "behind a gate (with air 3)",
          "only with probe-needed edges", "not reached"]
MARK = {"major": 5.0, "obsidian": 3.0, "cluster": 2.5, "gem": 1.6, "consumable": 2.5}


def _rgb(c):
    return np.array([int(c[k:k + 2], 16) for k in (1, 3, 5)], dtype=np.float64)


def _png(img: np.ndarray) -> bytes:
    """An RGB uint8 image (rows top to bottom) as PNG bytes."""
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def zone_states(A, ti):
    """Per logic node: the first ladder rung that reaches it at tier ti (0-3
    air, 4 gates open, 5 every probe class, 6 not reached)."""
    n = A.W["logic"].nreg + A.wg.n
    state = np.full(n, 6, dtype=np.int8)
    ladder = [(0, (), False), (1, (), False), (2, (), False), (3, (), False), (3, (), True),
              (3, (SKIP_CLASS,) + PROBE_LADDER, True)]
    for st, (air, probes, gopen) in enumerate(ladder):
        seen = A.bfs("logic", ti, air, probes, gopen, A.spawn["logic"])
        idx = np.fromiter(seen, dtype=np.int64, count=len(seen))
        state[idx] = np.minimum(state[idx], st)
    return state


def render(A, out: Path) -> list[Path]:
    """Write the level's per-tier SVGs into ``out``; returns their paths."""
    lv, w, wg = A.lv, A.W["logic"], A.wg
    nb, NX = w.nreg, lv.NX
    ix, iy = w.col % NX, w.col // NX
    wix, wiy = (wg.col % NX, wg.col // NX) if len(wg.col) else (np.zeros(0, int), np.zeros(0, int))
    x0 = int(min(ix.min(), wix.min() if len(wix) else ix.min())) - 20
    x1 = int(max(ix.max(), wix.max() if len(wix) else ix.max())) + 20
    y0 = int(min(iy.min(), wiy.min() if len(wiy) else iy.min())) - 20
    y1 = int(max(iy.max(), wiy.max() if len(wiy) else iy.max())) + 20
    W_, H_ = x1 - x0 + 1, y1 - y0 + 1

    def to_img(X, Y):        # world -> picture units (cells), y up
        return (np.asarray(X) - lv.x0) / CELL - x0, H_ - ((np.asarray(Y) - lv.y0) / CELL - y0)
    pal = np.array([_rgb(c) for c in AIR_RAMP + [GATE_C, PROBE_C, NONE_C]])
    surface = _rgb(SURFACE)
    order = np.argsort(w.z, kind="stable")       # higher samples drawn last
    o = order[w.reg[order] >= 0]
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for ti, tname in enumerate(TIERS):
        state = zone_states(A, ti)
        img = np.ones((H_, W_, 3)) * surface
        if len(wg.col):
            ok = wg.lab >= 0
            img[wiy - y0, wix - x0] = np.where(ok[:, None], _rgb(WATER_C), _rgb(KILL_C) * 0.35 + surface * 0.65)
            cw = np.array([pal[s] if s < 6 else _rgb(WATER_C) for s in range(7)])
            img[wiy[ok] - y0, wix[ok] - x0] = cw[state[nb + wg.lab[ok]]] * 0.35 + surface * 0.65
        img[iy[o] - y0, ix[o] - x0] = pal[state[w.reg[o]]]
        png = _png(np.ascontiguousarray(img[::-1].round().astype(np.uint8)))
        S = 1100.0 / max(W_, H_)          # picture units -> SVG px
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W_ * S + 260:.0f}" height="{H_ * S + 40:.0f}" '
                 f'font-family="sans-serif" font-size="9">',
                 f'<rect width="100%" height="100%" fill="{SURFACE}"/>',
                 f'<g transform="translate(0,34) scale({S:.5f})">',
                 f'<image width="{W_}" height="{H_}" style="image-rendering:pixelated" '
                 f'href="data:image/png;base64,{base64.b64encode(png).decode()}"/>']
        for g in A.gates:
            tri = np.nonzero(np.isin(lv.tri_owner, g["members"]))[0]
            if not len(tri):
                continue
            P = lv.P[tri].reshape(-1, 3)
            gx, gy = to_img(P[:, 0], P[:, 1])
            parts.append(f'<rect x="{gx.min():.1f}" y="{gy.min():.1f}" width="{gx.max() - gx.min():.1f}" '
                         f'height="{gy.max() - gy.min():.1f}" fill="none" stroke="{INK}" stroke-width="{1 / S:.2f}"/>')
            if g.get("merges") or g.get("water_merges"):
                parts.append(f'<text x="{gx.max():.1f}" y="{gy.min():.1f}" font-size="{8 / S:.1f}" fill="{INK}">'
                             f'{escape(g["id"].split(".", 1)[1])}</text>')
        for e in A.gen.get("exits", []):
            names = [m[1] for m in A.HINT_NAMES.findall(e["gate_hint"] or "")]
            oi = next((oi for nm in names for oi in lv.by_name.get(nm, [])), None)
            if oi is None:
                continue
            P = lv.P[lv.tris_of(oi)].reshape(-1, 3)
            px, py = to_img(P[:, 0].mean(), P[:, 1].mean())
            r = 4 / S
            fill = INK if A.obj_at.get(e["id"], {}).get("nodes") else SURFACE
            parts.append(f'<path d="M{px:.1f},{py - r:.1f} L{px + r:.1f},{py + r:.1f} L{px - r:.1f},{py + r:.1f} Z" '
                         f'fill="{fill}" stroke="{INK}" stroke-width="{1 / S:.2f}"/>'
                         f'<text x="{px + r:.1f}" y="{py:.1f}" font-size="{8 / S:.1f}">{escape(e["dest_level"])}</text>')
        for lid, ent in A.loc.items():
            pts, _ = lv.rec_points(lid)
            px, py = to_img(pts[0][0], pts[0][1])
            m = ent["logic"]
            got = m["node"] is not None and state[m["node"]] == 0 and m["ranks"][ti] == 0 and not ent.get("gate_need") \
                and not ent.get("doors")
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{MARK.get(ent["class"], 2.0) / S:.2f}" '
                         f'fill="{INK if got else SURFACE}" stroke="{INK}" stroke-width="{0.6 / S:.2f}"/>')
        for sid in A.spawn_ids[0]:
            q = lv.rec_points(sid)[0][0]
            px, py = to_img(q[0], q[1])
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{6 / S:.2f}" fill="none" stroke="{INK}" '
                         f'stroke-width="{1.6 / S:.2f}"/><text x="{px + 7 / S:.1f}" y="{py:.1f}" font-size="{9 / S:.1f}" '
                         f'font-weight="bold">spawn</text>')
        bar = 50.0 / CELL
        parts.append(f'<line x1="{W_ * 0.04:.1f}" y1="{H_ * 0.97:.1f}" x2="{W_ * 0.04 + bar:.1f}" y2="{H_ * 0.97:.1f}" '
                     f'stroke="{INK}" stroke-width="{2 / S:.2f}"/><text x="{W_ * 0.04:.1f}" y="{H_ * 0.97 - 4 / S:.1f}" '
                     f'font-size="{8 / S:.1f}">50 m</text></g>')
        rows = {r["state"]: r["items"] for r in A.cov["tiers"][tname]}
        top = A.cov["tiers"][tname]
        parts.append(f'<text x="6" y="14" font-size="11">{escape(A.name)}: what the {tname} movement tier reaches from '
                     f'the spawn (draft, D108 Q255/Q256)</text><text x="6" y="28">pool locations reached: '
                     f'{rows["nothing"]} with no item, {rows["air powers"]} with every air level, {top[-1]["items"]} with '
                     f'gates open and every probe-needed edge; of {top[0]["of"]}</text>')
        lx = W_ * S + 12
        for k, (c, lab) in enumerate(zip(AIR_RAMP + [GATE_C, PROBE_C, NONE_C, WATER_C], STATES + ["water (swim region)"])):
            parts.append(f'<rect x="{lx:.0f}" y="{40 + 14 * k}" width="10" height="10" fill="{c}"/>'
                         f'<text x="{lx + 14:.0f}" y="{49 + 14 * k}">{escape(lab)}</text>')
        parts.append("</svg>\n")
        fn = out / (f"{A.name}.svg" if tname == "safe" else f"{A.name}_{tname}.svg")
        fn.write_text("".join(parts), encoding="utf-8")
        files.append(fn)
    return files
