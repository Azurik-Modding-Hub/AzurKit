"""Effects templates as data (Step 2.167a, D538: "Projectiles", "Shields",
"Beams", "Per-variant clones by default"): ``fx_templates.json`` beside
this module holds

- **grafts**, the named record sets a recipe's ``fx_grafts`` take
  (``{"template": NAME, "parent": record}``, :mod:`~azurik_mod.assets.fx_edit`):
  a donor graph (``archive``, ``key``) and its records, each
  ``[index, name, type]``, checked against the donor at build (a set
  must hold every record its records name: links, a pSystem's renderer
  and components, a burst's targets), and what it is; and
- **templates**, the nine effects (``group`` projectile, shield or beam)
  a recipe's or a weapon style's ``effects`` rows name (:func:`effects`;
  Step 2.167b, D538's E2, builds the projectiles,
  :mod:`~azurik_mod.patches._player_throw`; Step 2.167c, E3, the shields
  and beams, :mod:`~azurik_mod.patches._player_fx_ring`): the ``engine`` that plays
  it (``throw``: X42's critter throw, the projectile a ``body`` of the
  game's or one we author, its ``impact`` graph and ``hit`` record;
  ``bound``: X38's ring, its sets hanging under the ``holder`` graft in a
  graph of its own (Step 2.167c), under the graph's ``effectOrigin`` root
  (another holder, which the game binds to the wearer's model, AZ-709):
  the holder bound by an ``anchor`` edit to
  the marker of its ``anchor`` role (``centre`` and ``front``: ``m_root``,
  garret4's own, X16's on any other body), which sets the holder's
  translate, rotate and scale every frame (0x68DE0), so no template writes
  those; or, for ``feet`` and ``hand``, placed by the build, ``turn`` its
  rotate), its
  ``sets`` (grafts), fixed ``edits`` by record name, ``params`` (a
  default inside a display ``range``, D23/D42: a hint, never a clamp, and
  what each ``writes``: a record's attribute times ``factor``, or an
  engine field; ``auto`` ``reach``: the column's box reach), its
  ``colour`` (renderer colours it writes, textures it recolours) and
  what the engine ``show``\\ s (an attribute raised to a value while the
  effect plays).

The defaults are starting numbers: the sittings tune them (a look that
fails is a template number, not code).  :func:`load` checks a document
with no game data, every refusal a :class:`ValueError` naming the field
(D35); the module's :data:`GRAFTS` and :data:`TEMPLATES` are the shipped
file's.  What needs the game (each set grafts and reads as its donor
records, each written attribute is its record's type's, each body,
impact and hit is the game's) is ``tests/test_xbr_clone.py``'s.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

PATH = Path(__file__).with_name("fx_templates.json")
GROUPS = {"projectile": "throw", "shield": "bound", "beam": "bound"}
"""Each template group and the engine that plays it."""
ROLES = ("centre", "feet", "hand", "front")
"""The anchor roles: where on the body a template plays."""
ENGINE_FIELDS = {"throw": ("speed", "arc", "life", "radius", "size"), "bound": ("fade",)}
"""The fields a param may write in its engine's table rather than in a
record: X42's speed (m/s), arc, life (s), hit radius and the body's size
(m); X38's fade (s)."""
AUTO = ("reach",)
"""What a param's ``auto`` may take its value from."""
HOLDER = "holder"
"""The graft a bound template's sets hang under."""
_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
_TEMPLATE_KEYS = ("group", "title", "what", "engine", "anchor", "sets", "params", "show")
PLACED = ("feet", "hand")
"""The anchor roles whose holder the build places (no marker binds it): the
feet the model's origin, the hand the action point at the row's hit."""
BOUND_ROWS = 3
"""The most bound rows (shields and beams) a build plays: X38's table holds
five keys, the body's own graph's and a stand's among them (Step 2.167c)."""
_THROW_KEYS = ("body", "impact", "hit")


@dataclass(frozen=True)
class Graft:
    """A named graft: the donor graph (``archive``, ``key``), its records
    with the names and types they must have, and what it is."""
    archive: str
    key: str
    records: tuple[tuple[int, str, str], ...]
    what: str


@dataclass(frozen=True)
class Template:
    """One effects template (the module docstring); ``params``,
    ``colour``, ``body`` and ``impact`` as the file holds them."""
    name: str
    group: str
    title: str
    what: str
    engine: str
    anchor: str
    sets: tuple[str, ...]
    edits: tuple[dict, ...]
    params: dict
    colour: dict | None
    show: tuple[dict, ...]
    body: dict | None = None
    impact: dict | None = None
    hit: str | None = None
    turn: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _keys(where: str, given, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict:
    if not isinstance(given, dict):
        raise ValueError(f"{where}: {given!r} is not an object")
    unknown = sorted(set(given) - set(required) - set(optional))
    if unknown:
        raise ValueError(f"{where}: unknown key {', '.join(map(repr, unknown))}")
    missing = [k for k in required if k not in given]
    if missing:
        raise ValueError(f"{where}: missing {', '.join(map(repr, missing))}")
    return given


def _num(where: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where}: {value!r} is not a finite number")
    return float(value)


def _text(where: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {value!r} is not a name")
    return value


def _list(where: str, value) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{where}: {value!r} is not a list")
    return value


def _donor(where: str, spec: dict) -> None:
    """``spec``'s ``archive`` (characters or fx) and lower-case ``key``."""
    from azurkit.tools.characters.fx_edit import ARCHIVES
    if spec["archive"] not in ARCHIVES:
        raise ValueError(f"{where}.archive: {spec['archive']!r} is not one of {', '.join(ARCHIVES)}")
    if _text(f"{where}.key", spec["key"]) != spec["key"].casefold():
        raise ValueError(f"{where}.key: {spec['key']!r} is not lower case (the archives' keys are looked up so)")


def _graft(where: str, spec) -> Graft:
    _keys(where, spec, ("archive", "key", "records", "what"))
    _donor(where, spec)
    records = _list(f"{where}.records", spec["records"])
    if not records:
        raise ValueError(f"{where}.records: a graft takes at least one record")
    for j, rec in enumerate(records):
        if (not isinstance(rec, list) or len(rec) != 3 or isinstance(rec[0], bool) or not isinstance(rec[0], int)
                or rec[0] < 0 or not all(isinstance(t, str) and t for t in rec[1:])):
            raise ValueError(f"{where}.records[{j}]: {rec!r} is not [index, name, type]")
        if j and rec[0] <= records[j - 1][0]:
            raise ValueError(f"{where}.records[{j}]: record {rec[0]} comes after {records[j - 1][0]} (the donor's "
                             "order, each once)")
    return Graft(spec["archive"], spec["key"], tuple(tuple(r) for r in records), _text(f"{where}.what", spec["what"]))


def scope(template: Template, grafts: dict[str, Graft]) -> dict[str, tuple[str, int, str] | None]:
    """The records ``template`` may name, by name: (graft, donor index,
    type), or None for a name two of its records hold (never written)."""
    out: dict[str, tuple[str, int, str] | None] = {}
    for g in ((HOLDER,) if template.engine == "bound" else ()) + template.sets:
        for r, name, kind in grafts[g].records:
            out[name] = None if name in out else (g, r, kind)
    return out


def _record(where: str, name, names: dict, attrs=()) -> tuple[str, int, str]:
    if _text(where, name) not in names:
        raise ValueError(f"{where}: {name!r} is no record of the template's sets")
    if names[name] is None:
        raise ValueError(f"{where}: two records of the template's sets are named {name!r}")
    held = [a for a in attrs if isinstance(a, str) and a.startswith(("translate", "rotate", "scale"))]
    if names[name][0] == HOLDER and held:
        raise ValueError(f"{where}: {name}.{held[0]} is the holder's, which its anchor's marker sets every frame "
                         "(0x68DE0): write a record under it")
    return names[name]


def _template(where: str, name: str, spec, grafts: dict[str, Graft]) -> Template:
    from azurkit.tools.characters.fx_edit import INHERIT_MODES
    _keys(where, spec, _TEMPLATE_KEYS, ("edits", "colour", "turn") + _THROW_KEYS)
    group = spec["group"]
    if group not in GROUPS:
        raise ValueError(f"{where}.group: {group!r} is not one of {', '.join(GROUPS)}")
    engine = spec["engine"]
    if engine != GROUPS[group]:
        raise ValueError(f"{where}.engine: {engine!r}: a {group} plays on {GROUPS[group]}")
    if spec["anchor"] not in ROLES:
        raise ValueError(f"{where}.anchor: {spec['anchor']!r} is not one of {', '.join(ROLES)}")
    sets = _list(f"{where}.sets", spec["sets"])
    for j, g in enumerate(sets):
        if g not in grafts or g == HOLDER:
            raise ValueError(f"{where}.sets[{j}]: {g!r} is not a graft (not the holder)")
    if engine == "bound" and not sets:
        raise ValueError(f"{where}.sets: a bound template plays its sets, and it has none")
    if engine == "throw":
        _keys(where, {k: spec[k] for k in _THROW_KEYS if k in spec}, _THROW_KEYS)
    elif any(k in spec for k in _THROW_KEYS):
        raise ValueError(f"{where}: a {group} has no {', '.join(k for k in _THROW_KEYS if k in spec)}")
    if not isinstance(spec["params"], dict):
        raise ValueError(f"{where}.params: {spec['params']!r} is not an object")
    turn = (0.0, 0.0, 0.0)
    if "turn" in spec:
        if engine != "bound" or spec["anchor"] not in PLACED:
            raise ValueError(f"{where}.turn: only a holder the build places ({', '.join(PLACED)}) takes a turn")
        turn = _list(f"{where}.turn", spec["turn"])
        if len(turn) != 3:
            raise ValueError(f"{where}.turn: {turn!r} is not [rx, ry, rz] (radians)")
        turn = tuple(_num(f"{where}.turn", r) for r in turn)
    t = Template(name, group, _text(f"{where}.title", spec["title"]), _text(f"{where}.what", spec["what"]), engine,
                 spec["anchor"], tuple(sets), tuple(_list(f"{where}.edits", spec.get("edits", []))), spec["params"],
                 spec.get("colour"), tuple(_list(f"{where}.show", spec["show"])), spec.get("body"),
                 spec.get("impact"), spec.get("hit"), turn)
    names = scope(t, grafts)
    for j, edit in enumerate(t.edits):
        at = f"{where}.edits[{j}]"
        _keys(at, edit, ("record",), ("set", "inherit"))
        written = edit["set"] if isinstance(edit.get("set"), dict) else ()
        kind = _record(f"{at}.record", edit["record"], names, written)[2]
        if ("set" in edit) == ("inherit" in edit):
            raise ValueError(f"{at}: one of set and inherit")
        if "inherit" in edit and (kind != "transform" or edit["inherit"] not in INHERIT_MODES):
            raise ValueError(f"{at}.inherit: {edit['inherit']!r} on a {kind} (a transform's, one of "
                             f"{', '.join(map(str, INHERIT_MODES))})")
        if "set" in edit and (not isinstance(edit["set"], dict) or not edit["set"]):
            raise ValueError(f"{at}.set: {edit['set']!r} is not an object of attributes")
        for attr, v in edit.get("set", {}).items():
            _num(f"{at}.set.{_text(f'{at}.set', attr)}", v)
    for p, param in t.params.items():
        at = f"{where}.params.{p}"
        if not _NAME.match(p) or p in ("template", "columns", "colour", "seek"):
            raise ValueError(f"{at}: {p!r} is not a param name (lower case; not template, columns, colour or seek)")
        _keys(at, param, ("default", "range", "writes"), ("auto",))
        default = _num(f"{at}.default", param["default"])
        span = _list(f"{at}.range", param["range"])
        if len(span) != 2 or not _num(f"{at}.range", span[0]) < _num(f"{at}.range", span[1]):
            raise ValueError(f"{at}.range: {span!r} is not [low, high] rising")
        if not span[0] <= default <= span[1]:
            raise ValueError(f"{at}.default: {default:g} is outside its range {span!r} (D42)")
        if "auto" in param and param["auto"] not in AUTO:
            raise ValueError(f"{at}.auto: {param['auto']!r} is not one of {', '.join(AUTO)}")
        if not _list(f"{at}.writes", param["writes"]):
            raise ValueError(f"{at}.writes: it writes nothing")
        for j, w in enumerate(param["writes"]):
            if isinstance(w, dict) and "engine" in w:
                _keys(f"{at}.writes[{j}]", w, ("engine",))
                if w["engine"] not in ENGINE_FIELDS[engine]:
                    raise ValueError(f"{at}.writes[{j}].engine: {w['engine']!r} is not one of {engine}'s "
                                     f"{', '.join(ENGINE_FIELDS[engine])}")
                continue
            _keys(f"{at}.writes[{j}]", w, ("record", "attr"), ("factor",))
            _record(f"{at}.writes[{j}].record", w["record"], names, (_text(f"{at}.writes[{j}].attr", w["attr"]),))
            _num(f"{at}.writes[{j}].factor", w.get("factor", 1))
    if t.colour is not None:
        at = f"{where}.colour"
        _keys(at, t.colour, ("default",), ("writes", "recolor"))
        rgb = _list(f"{at}.default", t.colour["default"])
        if len(rgb) != 3:
            raise ValueError(f"{at}.default: {rgb!r} is not [r, g, b]")
        for c in rgb:
            _num(f"{at}.default", c)
        for j, w in enumerate(_list(f"{at}.writes", t.colour.get("writes", []))):
            _keys(f"{at}.writes[{j}]", w, ("record", "attrs"))
            if len(_list(f"{at}.writes[{j}].attrs", w["attrs"])) != 3:
                raise ValueError(f"{at}.writes[{j}].attrs: {w['attrs']!r} is not three attributes (r, g, b)")
            _record(f"{at}.writes[{j}].record", w["record"], names, w["attrs"])
        for j, rc in enumerate(_list(f"{at}.recolor", t.colour.get("recolor", []))):
            _keys(f"{at}.recolor[{j}]", rc, ("record",), ("stage",))
            kind = _record(f"{at}.recolor[{j}].record", rc["record"], names)[2]
            if kind not in ("pRendererB", "platform") or ("stage" in rc and kind != "platform"):
                raise ValueError(f"{at}.recolor[{j}]: a {kind} draws no texture to recolour"
                                 + (" by stage" if kind == "pRendererB" else ""))
            stage = rc.get("stage", 0)
            if isinstance(stage, bool) or not isinstance(stage, int) or stage < 0:
                raise ValueError(f"{at}.recolor[{j}].stage: {stage!r} is not a stage index")
    for j, s in enumerate(t.show):
        at = f"{where}.show[{j}]"
        _keys(at, s, ("record", "attr", "value"))
        _record(f"{at}.record", s["record"], names, (_text(f"{at}.attr", s["attr"]),))
        _num(f"{at}.value", s["value"])
    if engine == "bound" and not t.show:
        raise ValueError(f"{where}.show: X38 raises a bound template's show attributes, and it has none")
    if engine == "throw":
        body = t.body
        if not isinstance(body, dict) or ("key" in body) == ("authored" in body):
            raise ValueError(f"{where}.body: {body!r} is neither {{key, pose}} (a body of the game's) nor "
                             "{authored} (ours)")
        _keys(f"{where}.body", body, (), ("key", "pose") if "key" in body else ("authored",))
        for k, v in body.items():
            _text(f"{where}.body.{k}", v)
        if t.impact is not None:
            _donor(f"{where}.impact", _keys(f"{where}.impact", t.impact, ("archive", "key")))
        if t.hit is not None:
            _text(f"{where}.hit", t.hit)
    return t


def load(doc) -> tuple[dict[str, Graft], dict[str, Template]]:
    """A templates document's grafts and templates, checked with no game
    data (the module docstring); :class:`ValueError` names what isn't
    (D35)."""
    _keys("fx templates", doc, ("grafts", "templates"))
    for part in ("grafts", "templates"):
        if not isinstance(doc[part], dict):
            raise ValueError(f"{part}: {doc[part]!r} is not an object")
        for name in doc[part]:
            if not _NAME.match(name):
                raise ValueError(f"{part}.{name}: {name!r} is not a name (lower case, digits, _)")
    grafts = {name: _graft(f"grafts.{name}", spec) for name, spec in doc["grafts"].items()}
    if HOLDER not in grafts or len(grafts[HOLDER].records) != 1 or grafts[HOLDER].records[0][2] != "transform":
        raise ValueError(f"grafts.{HOLDER}: one transform, the holder a bound template hangs under")
    templates = {name: _template(f"templates.{name}", name, spec, grafts) for name, spec in doc["templates"].items()}
    return grafts, templates


_DOC = json.loads(PATH.read_text(encoding="utf-8"))
GRAFTS, TEMPLATES = load(_DOC)
"""The shipped file's named grafts and templates."""

ROLL = "roll forward"
"""The roll's ``attacks_anims`` column, which plays no effect (garret4's roll)."""


@dataclass(frozen=True)
class Effect:
    """One ``effects`` row (:func:`effects`): its template, the
    ``attacks_anims`` columns that play it, its colour (the template's
    unless given), every param's value (the template's default unless
    given; ``"auto"`` where the param takes one) and, for a projectile,
    whether its throw seeks (D761)."""
    template: Template
    columns: tuple[str, ...]
    colour: tuple[float, float, float] | None
    values: dict
    seek: bool = False


def template_sha(name: str) -> str:
    """sha256[:12] of template ``name``'s record and the grafts it plays
    as the shipped file holds them: what a recipe's ``effects`` row folds
    into its sha (``<name>@<sha>``, as a weapon's)."""
    import hashlib
    t = _DOC["templates"][name]
    doc = {"template": t, "grafts": {g: _DOC["grafts"][g] for g in ((HOLDER,) if t["engine"] == "bound" else ())
                                     + tuple(t["sets"])}}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def effects(where: str, rows) -> tuple[Effect, ...]:
    """A recipe's (or a weapon style's) ``effects``, checked with no game
    data (D35): a list of objects, each a ``template`` of
    :data:`TEMPLATES`, its
    ``columns`` (one or more distinct names, each in one row; the build
    checks them against ``attacks_anims``), an optional ``colour`` (three
    finite numbers), any of the template's params (any finite number,
    D23: the range is a hint; ``"auto"`` where the param has one) and,
    on a projectile row, ``seek`` (D761, Step 2.194b: true aims each
    throw at the critter the target finder gives within the kit's 14 m
    and 45 degrees of the facing; false, the default, flies it straight
    along the facing).  One
    projectile row at most: X42 throws one species, ``debug`` (W30); and
    :data:`BOUND_ROWS` shield and beam rows (Step 2.167c: X38's keys)."""
    rows = _list(where, rows)
    out, seen = [], {}
    for k, row in enumerate(rows):
        at = f"{where}[{k}]"
        if not isinstance(row, dict):
            raise ValueError(f"{at}: {row!r} is not an object")
        name = row.get("template")
        if name not in TEMPLATES:
            raise ValueError(f"{at}.template: {name!r} is not one of {', '.join(TEMPLATES)}")
        t = TEMPLATES[name]
        _keys(at, row, ("template", "columns"), ("colour", "seek") + tuple(t.params))
        seek = row.get("seek", False)
        if not isinstance(seek, bool):
            raise ValueError(f"{at}.seek: {seek!r} is not true or false")
        if seek and t.engine != "throw":
            raise ValueError(f"{at}.seek: a {t.group} plays on the body; only a projectile row's throw seeks")
        columns = _list(f"{at}.columns", row["columns"])
        if not columns:
            raise ValueError(f"{at}.columns: it names no attacks_anims column")
        for j, c in enumerate(columns):
            _text(f"{at}.columns[{j}]", c)
            if c == ROLL:
                raise ValueError(f"{at}.columns[{j}]: the roll throws nothing (it keeps garret4's roll)")
            if c in seen:
                raise ValueError(f"{at}.columns[{j}]: {c!r} is {seen[c]}'s too (a column plays one effect)")
            seen[c] = at
        colour = None
        if "colour" in row:
            rgb = _list(f"{at}.colour", row["colour"])
            if len(rgb) != 3:
                raise ValueError(f"{at}.colour: {rgb!r} is not [r, g, b]")
            colour = tuple(_num(f"{at}.colour", c) for c in rgb)
        elif t.colour is not None:
            colour = tuple(float(c) for c in t.colour["default"])
        values = {}
        for p, param in t.params.items():
            v = row.get(p, param["default"])
            values[p] = v if v == "auto" and "auto" in param else _num(f"{at}.{p}", v)
        if t.engine == "throw" and any(e.template.engine == "throw" for e in out):
            raise ValueError(f"{at}: a second projectile row: X42 throws one species a build, debug (W30), so one "
                             "row names a projectile")
        if t.engine == "bound" and sum(e.template.engine == "bound" for e in out) == BOUND_ROWS:
            raise ValueError(f"{at}: a {BOUND_ROWS + 1}th shield or beam row: X38's table holds {BOUND_ROWS} bound keys "
                             "beside the body's own graph and a stand")
        out.append(Effect(t, tuple(columns), colour, values, seek))
    return tuple(out)


__all__ = ["AUTO", "BOUND_ROWS", "ENGINE_FIELDS", "Effect", "GRAFTS", "GROUPS", "Graft", "HOLDER", "PATH", "PLACED",
           "ROLES", "ROLL", "TEMPLATES", "Template", "effects", "load", "scope", "template_sha"]
