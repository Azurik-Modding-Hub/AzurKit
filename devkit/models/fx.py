"""``python -m devkit models fx LEAF [ARGS ...]``: read, plan and clone
the fx graphs of characters.xbr and fx.xbr (Modkit's ``azurik-mod fx``,
Step 2.157, D443, D446; ported in Step 4.15a6).

- ``list`` the named graphs of characters.xbr and fx.xbr;
- ``show KEY`` a graph's records (type, parent, bind name, inherit mode,
  attributes by name, a pSystem's renderer and components and a
  pBurstEmitter's targets), links (plugs by name, weight, factor, curve),
  the resources its records name (meshes, materials with their rows'
  blend, opacity, alpha reference, flags and stage textures, textures
  with their format, size and frames);
- ``closure KEY`` what it reaches through relocated fields;
- ``texture KEY --record N --png OUT`` a texture one of its records draws,
  decoded, for editing (a game asset: never commit it);
- ``templates`` the named grafts and the effects templates
  (``tools.characters.fx_templates``);
- ``plan --player-character NAME`` what a variant's (or a W23 overlay's)
  clone adds: its edits, grafts, copies and new textures, with their
  sizes, and each of its ``effects`` rows (Step 2.167b: the template, its
  columns and values, the projectile W30 makes and what it appends; Step
  2.167c: a shield's or beam's own graph, its records, grafts and
  entries, its holder where a build places it unplaced), or its refusal;
  writes nothing;
- ``clone KEY --as NEWKEY [--edits FILE] --out DIR`` a folder of edits
  (``DIR/gamedata/<archive>``, ``DIR/gamedata/index/index.xbr``) that
  ``core.iso``'s ``read(files=)`` and ``pack`` lay into an image, with
  KEY's clone added under NEWKEY.

Every leaf reads ``--iso``'s image, else the one AzurKit finds
(``devkit.models.image``), in process and prints names, decoded numbers,
sizes and sha256[:12], never a byte. What ``texture`` and ``clone`` write is
a game asset, outside this checkout and the images' folders (D36). A
refusal is one ``fx LEAF: ...`` line on stderr and exit 1 (D35); a usage
error exits 2."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from devkit.models import image

ARCHIVE_FILES = {"characters": "characters.xbr", "fx": "fx.xbr"}
INDEX_PATH = "gamedata/index/index.xbr"


def _read(iso: Path, archive: str) -> bytes:
    return image.read(iso, f"gamedata/{ARCHIVE_FILES[archive]}")[0]


def _schema(iso: Path):
    from azurkit.core.xbr.graph import Schema
    return Schema(image.read(iso, "default.xbe")[0])


def _sha12(data) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _fail(verb: str, exc: Exception) -> int:
    print(f"fx {verb}: {exc}", file=sys.stderr)
    return 1


def _graph(data: bytes, key: str, schema):
    from azurkit.core.xbr.graph import Graph
    from azurkit.core.xbr.nodes import named_resources, parse_toc
    toc = parse_toc(data)
    index = next((i for i, n in named_resources(data).items() if n.casefold() == key.casefold()), None)
    if index is None or toc[index].tag != "node":
        raise ValueError(f"no graph {key!r} (fx list names them)")
    return index, Graph(data, toc, toc[index], schema)


def _find(iso: Path, key: str, archive: str | None) -> tuple[str, bytes]:
    """The archive holding ``key`` (``archive`` if given, else the first of
    characters and fx that names it) and its bytes."""
    from azurkit.core.xbr.nodes import named_resources
    for name in [archive] if archive else list(ARCHIVE_FILES):
        data = _read(iso, name)
        if any(n.casefold() == key.casefold() for n in named_resources(data).values()):
            return name, data
    raise ValueError(f"no graph {key!r} in {archive or 'characters or fx'}.xbr (fx list names them)")


def surf_words(data, toc, index: int) -> str:
    """A ``surf``'s kind in words: its format and size, or its frames."""
    from azurkit.tools.characters import textures
    e = toc[index]
    i = textures.info(bytes(data[e.file_offset:e.file_offset + e.size]))
    if "list" in i:
        return f"a list of {len(i['list'])} frames ({', '.join(str(f) for f in i['list'])})"
    fmt = {v: k.upper() for k, v in textures.FORMATS.items()}.get(i["format"], f"format 0x{i['format']:X}")
    return f"{fmt} {i['width']}x{i['height']}"


# --------------------------------------------------------------------------- leafs
def cmd_fx_list(args) -> int:
    from azurkit.core.xbr.nodes import named_resources, parse_toc, record_offsets
    try:
        iso = image.find(args.iso)
        n = 0
        for archive in [args.archive] if args.archive else list(ARCHIVE_FILES):
            data = _read(iso, archive)
            toc = parse_toc(data)
            for i, key in sorted(named_resources(data).items(), key=lambda kv: kv[1]):
                if toc[i].tag != "node" or (args.match and args.match.casefold() not in key.casefold()):
                    continue
                recs = record_offsets(data, toc[i].file_offset)
                print(f"{ARCHIVE_FILES[archive]:15} TOC {i:5}  {key}  {len(recs)} records, {toc[i].size} B")
                n += 1
    except (OSError, ValueError) as exc:
        return _fail("list", exc)
    print(f"{n} graphs")
    return 0


def _show(data: bytes, key: str, schema, only: int | None) -> dict:
    """``key``'s graph as a document: records, links, resources."""
    from azurkit.core.xbr.clone import refs_in
    from azurkit.core.xbr.graph import bind_name
    from azurkit.core.xbr.nodes import parse_toc
    from azurkit.tools.characters import fx_edit, render
    index, g = _graph(data, key, schema)
    toc = parse_toc(data)
    refs = dict(refs_in(data, toc, index))
    doc = {"key": key, "toc": index, "bytes": toc[index].size, "records": len(g.recs), "ndbg": g.ndbg_index,
           "nodes": []}
    for r, ro in enumerate(g.recs):
        if ro is None or (only is not None and r != only):
            continue
        kind = g.types[r]
        rec = {"record": r, "name": g.names[r], "type": kind}
        if g.is_dag(r):
            rec["parent"] = g.parent(r)
        if schema.is_a(kind, "transform"):
            rec["inherit"] = g.xform_fields(r)["mode"]
            if (b := bind_name(g.s, ro)) is not None:
                rec["bind"] = b
        rec["attributes"] = {schema.attr(kind, k): round(v, 6) for k, v in enumerate(g.attrs(r))}
        rec["links"] = [{"src_plug": g.plug_name(r, lk.src_plug), "dst": lk.dst, "dst_name": g.names[lk.dst],
                         "dst_plug": g.plug_name(lk.dst, lk.dst_plug), "weight": round(lk.weight, 6),
                         "factor": round(lk.factor, 6), "curve": lk.curve != 1} for lk in g.links(r)]
        named = [(role, struct.unpack_from("<I", g.s, f)[0]) for f, role in fx_edit.index_fields(g.s, kind, ro)]
        if named:   # a pSystem's renderer and components, a pBurstEmitter's targets (Step 2.167a)
            rec["indices"] = [{"role": role, "record": v, "name": g.names[v]} for role, v in named]
        owned = [f for f in fx_edit.owned_fields(schema, g.s, kind, ro) if f in refs]
        res = []
        for f in owned:
            t = refs[f]
            item = {"field": f"+0x{f - ro:X}" if 0 <= f - ro < 0x80 else "descriptor", "toc": t, "tag": toc[t].tag,
                    "bytes": toc[t].size}
            if toc[t].tag == "surf":
                item["texture"] = surf_words(data, toc, t)
            elif toc[t].tag == "rdms":
                gshd, row = struct.unpack_from("<II", data, toc[t].file_offset + 4)
                m = render.material(data, toc, gshd, row)
                item["material"] = {"gshd": gshd, "row": row, "blend": m.get("blend"),
                                    "opacity": round(m.get("opacity", 0.0), 6),
                                    "alpha_ref": round(m.get("alpha_ref", 0.0), 6), "flags": m.get("flags"),
                                    "stages": [{"toc": s, "texture": surf_words(data, toc, s)}
                                               for s in m.get("textures", [])]}
            elif toc[t].tag == "gshd" and kind == "shader":
                item["row"] = struct.unpack_from("<I", g.s, ro + 0x1C)[0]
            res.append(item)
        if res:
            rec["resources"] = res
        doc["nodes"].append(rec)
    return doc


def cmd_fx_show(args) -> int:
    try:
        iso = image.find(args.iso)
        archive, data = _find(iso, args.key, args.archive)
        doc = _show(data, args.key, _schema(iso), args.record)
    except (OSError, ValueError) as exc:
        return _fail("show", exc)
    if args.json:
        print(json.dumps(doc, indent=1))
        return 0
    print(f"{doc['key']} ({ARCHIVE_FILES[archive]} TOC {doc['toc']}): {doc['records']} records, {doc['bytes']} B, "
          f"ndbg {doc['ndbg']}")
    for rec in doc["nodes"]:
        head = [f"[{rec['record']}] {rec['name']} ({rec['type']})"]
        if rec.get("parent") is not None:
            head.append(f"parent [{rec['parent']}]")
        if "inherit" in rec:
            head.append(f"inherit {rec['inherit']}")
        if "bind" in rec:
            head.append(f"bound to {rec['bind']}")
        print("  " + ", ".join(head))
        print("    " + ", ".join(f"{k} {v:g}" for k, v in rec["attributes"].items()))
        for role in dict.fromkeys(i["role"] for i in rec.get("indices", [])):
            print(f"    {role}: " + ", ".join(f"[{i['record']}] {i['name']}" for i in rec["indices"] if i["role"] == role))
        for lk in rec["links"]:
            print(f"    link {lk['src_plug']} -> [{lk['dst']}] {lk['dst_name']}.{lk['dst_plug']} x {lk['weight']:g}"
                  f"{' (curve)' if lk['curve'] else ''} x {lk['factor']:g}")
        for item in rec.get("resources", []):
            line = f"    {item['field']}: {item['tag']} {item['toc']} ({item['bytes']} B)"
            if "texture" in item:
                line += f", {item['texture']}"
            if "row" in item:
                line += f", row {item['row']}"
            if "material" in item:
                m = item["material"]
                line += (f", material gshd {m['gshd']} row {m['row']}: blend {m['blend']}, opacity {m['opacity']:g}, "
                         f"alpha_ref {m['alpha_ref']:g}, flags 0x{m['flags']:X}; "
                         + "; ".join(f"stage {k} surf {s['toc']} {s['texture']}" for k, s in enumerate(m["stages"])))
            print(line)
    return 0


def cmd_fx_closure(args) -> int:
    from azurkit.core.xbr.clone import closure
    from azurkit.core.xbr.nodes import parse_toc
    try:
        if args.key is None and args.toc is None:
            raise ValueError("a KEY or --toc N")
        iso = image.find(args.iso)
        if args.toc is not None:
            archive = args.archive or "characters"
            data = _read(iso, archive)
            roots = [args.toc]
        else:
            archive, data = _find(iso, args.key, args.archive)
            roots = [_graph(data, args.key, _schema(iso))[0]]
        toc = parse_toc(data)
        reached = closure(data, roots)
    except (OSError, ValueError) as exc:
        return _fail("closure", exc)
    for i in reached:
        e = toc[i]
        print(f"{i:6} {e.tag} {e.size:8} B  sha256 {_sha12(data[e.file_offset:e.file_offset + e.size])}")
    print(f"{len(reached)} entries, {sum(toc[i].size for i in reached)} B ({ARCHIVE_FILES[archive]})")
    return 0


def cmd_fx_texture(args) -> int:
    from azurkit.core.xbr.clone import refs_in
    from azurkit.core.xbr.nodes import parse_toc
    from azurkit.tools.characters import fx_edit, render, textures
    from azurkit.tools.characters.draw import png_rgba
    try:
        iso = image.find(args.iso)
        out = image.output(args.png, iso, file=True)
        archive, data = _find(iso, args.key, args.archive)
        schema = _schema(iso)
        index, g = _graph(data, args.key, schema)
        toc = parse_toc(data)
        refs = dict(refs_in(data, toc, index))
        r = args.record
        if not 0 <= r < len(g.recs) or g.recs[r] is None:
            raise ValueError(f"{args.key} has no record {r}")
        ro = g.recs[r]
        if schema.is_a(g.types[r], "pRendererB") and ro + 0x18 in refs:
            surf = refs[ro + 0x18]
        elif g.types[r] == "platform":
            fields = fx_edit.lod_fields(g.s, ro)
            if not fields or fields[0][0] not in refs:
                raise ValueError(f"[{r}] {g.names[r]} draws no mesh")
            gshd, row = struct.unpack_from("<II", data, toc[refs[fields[0][0]]].file_offset + 4)
            stages = render.material(data, toc, gshd, row).get("textures", [])
            if not 0 <= args.stage < len(stages):
                raise ValueError(f"[{r}] {g.names[r]}'s material has {len(stages)} stages")
            surf = stages[args.stage]
        else:
            raise ValueError(f"[{r}] {g.names[r]} is a {g.types[r]}: a pRendererB or a platform draws a texture")
        e = toc[surf]
        payload = bytes(data[e.file_offset:e.file_offset + e.size])
        i = textures.info(payload)
        frame = surf
        if "list" in i:
            if not 0 <= args.frame < len(i["list"]):
                raise ValueError(f"surf {surf} is a list of {len(i['list'])} frames")
            frame = i["list"][args.frame]
            e = toc[frame]
            payload = bytes(data[e.file_offset:e.file_offset + e.size])
        img = textures.levels(payload)[0]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png_rgba(img))
    except (OSError, ValueError) as exc:
        return _fail("texture", exc)
    print(f"[{r}] {g.names[r]}: surf {frame} ({surf_words(data, toc, frame)}) -> {out} "
          f"(a game asset: never commit or share it)")
    return 0


def cmd_fx_templates(args) -> int:
    from azurkit.tools.characters import fx_templates
    print('grafts (a recipe\'s "fx_grafts": [{"template": "<name>", "parent": <a DAG record of the clone>}]):')
    for name, g in fx_templates.GRAFTS.items():
        print(f"{name}: {ARCHIVE_FILES[g.archive]} {g.key}")
        print(f"  {g.what}")
        for r, rec, kind in g.records:
            print(f"  [{r}] {rec} ({kind})")
    print("templates (D538: a recipe's or a weapon style's \"effects\": [{\"template\": \"<name>\", \"columns\": "
          "[...], <param>: <value>}]; projectiles on X42, Step 2.167b; shields and beams on X38's bound keys, "
          "Step 2.167c):")
    for name, t in fx_templates.TEMPLATES.items():
        print(f"{name} ({t.group}, {t.engine}, at the {t.anchor}): {t.title}")
        print(f"  {t.what}")
        parts = [f"sets {', '.join(t.sets) or 'none'}"]
        if t.engine == "bound":
            parts += [f"holder {'bound to m_root' if t.anchor in ('centre', 'front') else 'placed by the build'}"
                      + (f", turned {tuple(t.turn)}" if any(t.turn) else "")]
        if t.engine == "throw":
            parts += [f"body {t.body.get('key') or 'authored ' + t.body['authored']}"
                      + (f" (in {t.body['pose']}'s pose)" if "pose" in t.body else ""),
                      f"impact {t.impact['key'] if t.impact else 'none'}", f"hit {t.hit or 'plain'}"]
        print("  " + "; ".join(parts))
        print("  " + ", ".join(f"{p} {v['default']:g} ({v['range'][0]:g} to {v['range'][1]:g}"
                               + (f", or auto: the {v['auto']}" if "auto" in v else "") + ")"
                               for p, v in t.params.items())
              + (f"; colour {tuple(t.colour['default'])}" if t.colour else ""))
    return 0


def _variant(args):
    from azurkit.tools.characters import _player_variants as variants
    name = args.player_character
    variant = variants.resolve(name, args.player_variant_file) or variants.overlay(name)
    if variant is None:
        raise ValueError(f"{name!r} is neither a variant nor a species with an own-build overlay")
    return variant


def cmd_fx_plan(args) -> int:
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import fx_edit
    from azurkit.tools.characters.fx_templates import template_sha
    from azurkit.tools.characters.ports import XbrDocument
    try:
        iso = image.find(args.iso)
        variant = _variant(args)
        stand = (variant.fx_ring or {}).get("stand") or {}
        if not variant.fx_edits and not stand.get("fx") and not variant.effects:
            print(f"{variant.name}: no fx edits, so no clone (and no X40)")
            return 0
        config_xbr, xbe, fx, index_xbr = image.read(iso, "gamedata/config.xbr", "default.xbe",
                                                    f"gamedata/{ARCHIVE_FILES['fx']}", INDEX_PATH)
        config = XbrDocument.from_bytes(config_xbr)
        body = config.keyed_section("critters_engine").find_cell(variant.base, "body", None).string_value
        characters = _read(iso, "characters")
        folder = variants.fx_folder(variant)
        plans = []
        if variant.fx_edits:
            clone = fx_edit.Clone(characters, fx_edit.default_key(body), xbe, fx_xbr=fx, folder=folder)
            clone.apply(variant.fx, variant.fx_grafts)
            plans.append((clone, fx_edit.default_key(body), fx_edit.clone_key(body), "X40: the player alone",
                          len(variant.fx), clone.plan()))
        if stand.get("fx"):   # the ring's stand graph's own clone (Step 2.155b, D501)
            try:
                clone = fx_edit.Clone(characters, stand["key"], xbe, folder=folder)
                clone.apply(stand["fx"])
                plans.append((clone, stand["key"], fx_edit.stand_key(body), "X38's stand key: the player alone",
                              len(stand["fx"]), clone.plan()))
            except ValueError as exc:
                raise ValueError(f"fx_ring.stand.{exc}") from None
        rows = [_effect_plan(e, characters, xbe, fx, index_xbr)
                for e in variant.effects if e.template.engine == "throw"]
        bound = [_bound_plan(e, k, body, characters, xbe, fx)
                 for k, e in enumerate(e for e in variant.effects if e.template.engine == "bound")]
    except (OSError, ValueError) as exc:
        return _fail("plan", exc)
    for clone, key, as_key, who, edits, plan in plans:
        print(f"{variant.name} ({variant.source}, recipe {variant.sha}): {key} -> {as_key} ({who})")
        print(f"  {plan['records']} records ({len(clone.source.recs)} its own), {edits} edits on "
              f"{', '.join(f'[{r}] {clone.names[r]}' for r in plan['edited'])}")
        for g in plan["grafts"]:
            print(f"  graft {g['template'] or 'from'} ({g['from']}): "
                  + ", ".join(f"[{n}] <- {what}" for n, what in g["records"].items()))
        for tag, source, size in plan["entries"]:
            where = f"{source[0]} {source[1]}" if isinstance(source, tuple) else source
            print(f"  new {tag:4} {size:8} B  from {where}")
        print(f"  {len(plan['entries']) + 1} entries appended, {plan['bytes']} B of payload; {len(plan['shared'])} "
              "vanilla textures shared; every NPC keeps the vanilla graph")
    for effect, info, scale in rows:
        t = effect.template
        print(f"{variant.name} ({variant.source}, recipe {variant.sha}): effects row {t.name}@{template_sha(t.name)} "
              f"({t.group}, {t.engine}, at the {t.anchor}) on {', '.join(effect.columns)}")
        print("  " + ", ".join(f"{p} {v:g}" if v != "auto" else f"{p} auto" for p, v in effect.values.items())
              + (f"; colour {tuple(round(c, 4) for c in effect.colour)}" if effect.colour is not None else ""))
        flash = ", with X32's small flash (D700)" if t.hit else ""
        print(f"  W30: debug wearing {'our own arrow' if 'authored' in t.body else 'a copy of ' + info['source']} "
              f"at x{scale:.3f}" + (f", {info['recoloured']} texture(s) recoloured" if info["recoloured"] else "")
              + f"; its fx a clone of the boulder's with {', '.join(t.sets) or 'nothing'} grafted ({info['grafted']} "
              f"records); its break {'a copy of ' + info['impact'] if info['impact'] else 'none'}; its hits the "
              f"player's (X42){flash}")
        print(f"  {len(info['named'])} named entries ({', '.join(info['named'])}) appended, {info['bytes']} B of "
              "payload; the game's bodies, clips and graphs stay vanilla")
    for effect, key, made, b, plan in bound:
        t = effect.template
        print(f"{variant.name} ({variant.source}, recipe {variant.sha}): effects row {t.name}@{template_sha(t.name)} "
              f"({t.group}, {t.engine}, at the {t.anchor}) on {', '.join(effect.columns)}")
        print("  " + ", ".join(f"{p} {v:g}" if v != "auto" else f"{p} auto (the build's reach)"
                               for p, v in effect.values.items())
              + (f"; colour {tuple(round(c, 4) for c in effect.colour)}" if effect.colour is not None else ""))
        print(f"  X38's bound key {key}: {plan['records']} records ({', '.join(g['template'] for g in plan['grafts'])}"
              f" grafted on {plan['key']}), under its effectOrigin root (the wearer's model), its holder "
              + ("bound to m_root" if t.anchor in ("centre", "front") else "where the build places it")
              + f"; shown at {len(b.show)} attribute(s), fading over {b.fade:g} s, its tail {b.tail:g} s")
        print(f"  {len(made)} entries appended, {sum(len(r.payload) for r in made)} B of payload; the game's graphs "
              "stay vanilla")
    return 0


def _effect_plan(effect, characters: bytes, xbe: bytes, fx: bytes, index: bytes):
    """An ``effects`` row's projectile as a build makes it (Step 2.167b):
    (the row, ``_player_throw.write_template``'s info, ``debug``'s scale);
    a shield or beam row never loads (E3)."""
    from azurkit.tools.characters import _player_throw as throws
    scale = throws.template_scale(characters, effect.template, float(effect.values["size"]))
    try:
        _, _, info = throws.write_template(characters, index, xbe, fx, effect, scale)
    except ValueError as exc:
        raise ValueError(f"effects row {effect.template.name}: {exc}") from None
    return effect, info, scale


def _bound_plan(effect, k: int, body: str, characters: bytes, xbe: bytes, fx: bytes):
    """A shield or beam ``effects`` row's graph as a build makes it (Step
    2.167c; ``_player_fx_ring.bound_graph``): its holder bound to m_root,
    or unplaced where a build places it, each ``auto`` at the param's
    default."""
    from azurkit.core.xbr.nodes import parse_toc
    from azurkit.tools.characters import _player_fx_ring as fx_ring
    t = effect.template
    key = fx_ring.bound_key(body, t.name, k)
    values = {p: t.params[p]["default"] if v == "auto" else v for p, v in effect.values.items()}
    try:
        made, b, plan = fx_ring.bound_graph(characters, xbe, fx, effect, key, len(parse_toc(characters)),
                                            marker=fx_ring.CENTRE if t.anchor in ("centre", "front") else None,
                                            values=values)
    except ValueError as exc:
        raise ValueError(f"effects row {t.name}: {exc}") from None
    return effect, key, made, b, plan


def cmd_fx_clone(args) -> int:
    from azurkit.core.xbr.append import append_resources, check_key
    from azurkit.tools.characters import fx_edit
    from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records
    try:
        iso = image.find(args.iso)
        edits_file = Path(args.edits) if args.edits else None
        out = image.output(args.out, iso)
        archive, data = _find(iso, args.key, args.archive)
        if not args.allow_modded_input and not _vanilla(data, archive):
            raise ValueError(f"{iso}'s {ARCHIVE_FILES[archive]} isn't vanilla: build from vanilla (D27), or pass "
                             "--allow-modded-input")
        check_key(args.as_key.casefold())
        edits = json.loads(edits_file.read_text(encoding="utf-8")) if edits_file else {}
        if not isinstance(edits, dict) or set(edits) - {"fx", "fx_grafts"}:
            raise ValueError("--edits: a JSON object of fx and fx_grafts, as a recipe's")
        _check_edits(edits)
        donors = {"fx": _read(iso, "fx")} if archive == "characters" else {}
        clone = fx_edit.Clone(data, args.key, image.read(iso, "default.xbe")[0], fx_xbr=donors.get("fx"),
                              folder=edits_file.parent if edits_file else None, archive=archive)
        clone.apply(edits.get("fx", []), edits.get("fx_grafts", []))
        new = clone.build(args.as_key)
        grown = append_resources(data, new)
        index = add_index_records(image.read(iso, INDEX_PATH)[0],
                                  [IndexRecord(r.name, ARCHIVE_FILES[archive], r.tag) for r in new if r.name])
        (out / "gamedata" / "index").mkdir(parents=True, exist_ok=True)
        (out / "gamedata" / ARCHIVE_FILES[archive]).write_bytes(grown)
        (out / INDEX_PATH).write_bytes(index)
    except (OSError, ValueError) as exc:   # json.JSONDecodeError is a ValueError
        return _fail("clone", exc)
    print(f"{args.key} -> {args.as_key.casefold()} ({ARCHIVE_FILES[archive]}): {len(new)} entries appended "
          f"({sum(len(r.payload) for r in new)} B), {len(clone.recs)} records")
    print(f"wrote {out / 'gamedata' / ARCHIVE_FILES[archive]} (sha256 {_sha12(grown)}) and {out / INDEX_PATH} "
          f"(sha256 {_sha12(index)}): core.iso's read(files=) and pack lay the folder into an image. A graph under "
          "a new key plays only when something loads it (a variant's player clone, an effect record's key)")
    return 0


def _vanilla(data: bytes, archive: str) -> bool:
    """Whether ``data`` is a release's vanilla ``archive`` (its manifest's sha256)."""
    from azurkit.core import gate
    sha = hashlib.sha256(data).hexdigest()
    return any(r.files.get(f"gamedata/{ARCHIVE_FILES[archive]}", (0, ""))[1] == sha for r in gate.RELEASES)


def _check_edits(edits: dict) -> None:
    """An --edits file's fields, checked as a swap body's recipe's are: on a
    stand-in base, since one on garret4's own body takes only colours
    (Step 2.170c)."""
    from azurkit.tools.characters import _player_variants as variants
    variants._variant("edits", {"base": "edits", **edits}, "edits")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit models fx",
                                description="The fx graphs of characters.xbr and fx.xbr: read them, plan a variant's "
                                            "player clone, and clone one under a new key (Step 2.157).",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    fsub = p.add_subparsers(dest="leaf", required=True, metavar="LEAF")

    def leaf(name: str, run, line: str, archive: bool = True) -> argparse.ArgumentParser:
        q = fsub.add_parser(name, help=line, description=line)
        q.add_argument("--iso", default=None, metavar="PATH",
                       help="the image to read (default: the vanilla one AzurKit finds, USA's first)")
        if archive:
            q.add_argument("--archive", choices=sorted(ARCHIVE_FILES), default=None,
                           help="characters or fx (default: whichever names KEY)")
        q.set_defaults(run=run)
        return q

    q = leaf("list", cmd_fx_list, "The named graphs: key, TOC index, records, size")
    q.add_argument("--match", default=None, metavar="TEXT", help="Only keys holding TEXT")
    q = leaf("show", cmd_fx_show, "A graph's records, links, materials and textures")
    q.add_argument("key")
    q.add_argument("--record", type=int, default=None, metavar="N", help="Only record N")
    q.add_argument("--json", action="store_true", help="The same as JSON")
    q = leaf("closure", cmd_fx_closure, "What a graph (or a TOC entry) reaches through relocated fields")
    q.add_argument("key", nargs="?", default=None)
    q.add_argument("--toc", type=int, default=None, metavar="N", help="A TOC entry instead of a key")
    q = leaf("texture", cmd_fx_texture, "A texture a record draws, decoded to a PNG (a game asset: never commit it)")
    q.add_argument("key")
    q.add_argument("--record", type=int, required=True, metavar="N")
    q.add_argument("--stage", type=int, default=0, metavar="K", help="A platform material's stage (default 0)")
    q.add_argument("--frame", type=int, default=0, metavar="F", help="An animated list's frame (default 0)")
    q.add_argument("--png", required=True, metavar="OUT",
                   help="The PNG to write, outside the checkout and the images' folders")
    fsub.add_parser("templates", help="The named grafts a recipe's fx_grafts may use, and the effects templates",
                    description="The named grafts a recipe's fx_grafts may use, and the effects templates"
                    ).set_defaults(run=cmd_fx_templates)
    q = leaf("plan", cmd_fx_plan, "What a variant's player clone adds, writing nothing", archive=False)
    q.add_argument("--player-character", required=True, metavar="NAME", help="A variant, or a species' overlay")
    q.add_argument("--player-variant-file", default=None, metavar="FILE", help="A file of user recipes")
    q = leaf("clone", cmd_fx_clone, "A folder of edits with a graph cloned under a new key")
    q.add_argument("key")
    q.add_argument("--as", dest="as_key", required=True, metavar="NEWKEY", help="The clone's key (lower case)")
    q.add_argument("--edits", default=None, metavar="FILE.json",
                   help='{"fx": [...], "fx_grafts": [...]} as a recipe\'s')
    q.add_argument("--out", required=True, metavar="DIR",
                   help="A new or empty folder, outside the checkout and the images' folders")
    q.add_argument("--allow-modded-input", action="store_true", help="Clone from a non-vanilla archive (D27)")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
