"""The randomizer database loader (docs/RANDOMIZER_DB.md, format v1; Step R1.4).

:func:`check_database` reads a database folder (``azurik_mod/randomizer/data``
by default) and applies every load check of §9: each file's format, keys,
types and enum values; the requirement grammar; every reference; the
bindings of generated gates ("no gate goes unexplained"); the declared
non-monotone mechanisms; that only the victory reads a terminal event
(rule 21); the skips and their confirmations (D113, D114); ``tricks.toml``
and its projection into the level files; the time-savers, never in logic
(D145); the settings (D144); the
``proven`` marks (D122, D143); the vanilla route; and, once
all of that passes, that the start and the hub reach each other with every
item (rule 10, the solver's escape, Step R1.6). It returns a
:class:`Report` of every issue and of what is still open. A ``draft``
level is a stub: its open fields and its pool locations with no node are
counted, not refused; an ``authored`` level has none of either.
:func:`load_database` returns the :class:`Database` or raises
:class:`DatabaseError` naming every issue (fail closed).

Pure stdlib but for ``platformdirs`` (the user cache of :mod:`.dbcache`):
the planner never imports numpy, capstone or the draft tools
(``tests/test_import_isolation.py``).
"""

from __future__ import annotations

import collections
import gzip
import hashlib
import json
import pickle
import re
import time
import tomllib
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.core import progress
from azurkit.tools.randomizer.planner import proofs as pr
from azurkit.tools.randomizer.planner.grammar import COUNTERS, DISCS, ParseError, atoms, parse
from azurkit.tools.randomizer.planner.settings import (
    D144_DEFAULTS,
    DARK_FIRE,
    MOVEMENT_TIERS,
    SKIP_CEILINGS,
    Settings,
    picks,
    registry_tag,
    settings_from_table,
    settings_problems,
    share_decode,
    share_encode,
    skips_on,
)
from azurkit.tools.randomizer.planner.solver import Logic

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VERSION = 1
# Each of the checks :func:`check_database` runs and "building its logic" is a core.progress note ("checking the
# levels, 5 of 15"), which the call on this thread folds into its stage. A host's hook, None by default:
# SHIPPED(root, key=key) is a Logic of ``root``'s checked database the host already holds (AzurKit's shipped one,
# found by ``key``, :func:`.dbcache.entry`'s name, so it is worked out once), or None, and :func:`kept_logic` builds it
# as before
SHIPPED: Callable[..., Logic | None] | None = None
FORMATS = {kind: f"azurik-rando-{kind}/{VERSION}"
           for kind in ("generated", "derived", "level", "items", "world", "settings", "tricks", "route", "movement",
                        "contact")}

LEVEL_STATUSES = frozenset({"draft", "authored"})
EDGE_KINDS = frozenset({"walk", "drop", "exit", "teleport", "cart"})
DIFFICULTIES = frozenset({1, 2, 3, 4})            # a skip's: 1 safe .. 4 frame-perfect
EDGE_DIFFICULTIES = DIFFICULTIES | {0}             # an edge's: the envelope's tiers, 0 its `phys` row (R_phys only)
CONFIDENCES = ("assumed", "data", "physics", "probed", "owner")     # RANDOMIZER_PLAN §4.5, weakest first
PERSISTS = frozenset({"permanent", "timed", "level_reset", "mixed", "unknown"})
SKIP_STATUSES = frozenset({"in_logic", "held", "manual"})
CONFIRMED_BY = ("xemu", "owner", "l3")     # l3: an L3 string, its proofs.jsonl record (D177; no xemu replay owed, D277)
PROVEN_BY = ("data", "xemu", "l3", "route")
REALMS = {"town_water": ("town", "w1", "w2", "w3", "w4"),     # authored at Step R1.8
          "air": ("a1", "a3", "a5", "a6", "airship"),         # Step R1.11a
          "fire": ("f1", "f2", "f3", "f4", "f6"),             # Step R1.11b; f2 at Step R1.8d (AZ-343)
          "earth": ("e2", "e5", "e6", "e7"),                  # Step R1.11c; e5 at Step R1.8d (AZ-343)
          "life_death": ("life", "d1", "d2")}                 # Step R1.11d
REALM_OF = {lvl: realm for realm, lvls in REALMS.items() for lvl in lvls}
NON_GEM = ("major", "obsidian", "consumable")   # a gem or a gem cluster never takes a progression item (D78)
ITEM_CLASSES = frozenset({"progression", "progression_counted", "useful", "filler"})
MECHANISM_KINDS = frozenset({"one_shot_teleport", "respawn", "toggle", "capacity", "cycle", "cart", "spend"})
HANDLINGS = frozenset({"forfeitable", "product_bit", "out_of_logic", "harmless", "keys_vanilla"})
ROUTE_ACTIONS = frozenset({"use_keylock", "kill", "open_obsidian_lock", "touch_seal", "hit_crystal"})
GEN_KINDS = ("locations", "geodes", "barriers", "keylocks", "keylords", "obsidian_locks", "seals",
             "save_points", "exits", "spots", "teleporters", "bosses", "latches", "game_states")
ANCHOR_KINDS = frozenset({"save_points", "exits", "spots", "barriers", "keylocks", "seals", "obsidian_locks",
                          "teleporters"})

# --- the schema (§3, §4, §6, §7 and the tricks and route files): key -> (kind, required) -------------------------
# A kind is str, bool, int or dict (that type), STRS / TABLES (a list of them), ANY, a frozenset (an enum) or a
# tuple (any of its kinds). A key outside a table's spec is refused (rule 1).
R, O = True, False
STRS, TABLES, ANY, NONE = "strs", "tables", "any", "none"

SPECS: dict[str, dict] = {
    "level": {"format": (str, R), "level": (str, R), "status": (LEVEL_STATUSES, R), "default_node": (str, O),
              "known_traps": (TABLES, O), "route": (STRS, O), "node": (TABLES, O), "edge": (TABLES, O),
              "barrier": (TABLES, O), "button": (TABLES, O), "event": (TABLES, O), "location": (TABLES, O),
              "skip": (TABLES, O)},
    "level.known_traps": {"node": (str, R), "note": (str, R)},
    "level.node": {"id": (str, R), "anchors": (STRS, O), "locations": (STRS, O), "start": (bool, O),
                   "hub": (bool, O), "dark": ((bool, str), O), "note": (str, O)},
    "level.edge": {"from": (str, R), "to": (str, R), "kind": (EDGE_KINDS, R), "requires": (str, O),
                   "exit": (str, O), "teleporter": (str, O), "disc": (frozenset(DISCS), O), "through": (STRS, O),
                   "assumes": (STRS, O), "logic": (bool, O), "lock": (str, O), "dark": ((bool, str), O),
                   "casts": (int, O), "difficulty": (EDGE_DIFFICULTIES, O),
                   "confidence": (frozenset(CONFIDENCES), O), "proven": (ANY, O)},
    "level.barrier": {"id": (str, R), "of": (str, R), "destroy_from": (STRS, O), "bypass": (dict, O),
                      "requires": (str, O), "override_requires": (str, O), "override_reason": (str, O),
                      "persist": (PERSISTS, O), "persist_reason": (str, O), "contains": (STRS, O),
                      "required_for": (STRS, O)},
    "level.button": {"id": (str, R), "of": (str, O), "at": (str, R), "mode": (frozenset({"latch", "toggle"}), R),
                     "requires": (str, O), "override_requires": (str, O), "override_reason": (str, O)},
    "level.event": {"id": (str, R), "of": (str, O), "at": (str, R), "requires": (str, O), "terminal": (bool, O)},
    "level.location": {"id": (str, R), "requires": (str, O), "exclude": (bool, O), "farmable": (bool, O),
                       "proven": (ANY, O), "note": (str, O)},
    "level.skip": {"id": (str, R), "name": (str, R), "tricks": (STRS, R), "requires": (str, O),
                   "difficulty": (DIFFICULTIES, O), "status": (SKIP_STATUSES, R), "confirmed": (ANY, R),
                   "from": (str, O), "to": (str, O), "gates": (STRS, O), "tiers": (STRS, O), "note": (str, O),
                   "batch": (str, O), "batch_name": (str, O)},
    "items": {"format": (str, R), "counters": (dict, R), "item": (TABLES, R)},
    "items.item": {"name": (str, R), "base": (str, O), "counters": (dict, R), "class": (ITEM_CLASSES, R)},
    "world": {"format": (str, R), "start": (str, R), "hub": (str, R), "victory": (str, R),
              "starting_items": (STRS, R), "trick": (TABLES, R), "time_saver": (TABLES, O), "mechanism": (TABLES, O)},
    "world.trick": {"name": (str, R), "description": (str, R)},
    "world.time_saver": {"id": (str, R), "name": (str, R), "level": (str, R), "tricks": (STRS, R)},
    "world.mechanism": {"id": (str, R), "kind": (MECHANISM_KINDS, R), "handling": (HANDLINGS, R), "note": (str, O)},
    "generated": {"_meta": (dict, R), "level": (str, R), "kind": (frozenset({"realm", "hub", "boss", "tutorial"}), R),
                  "cells": (STRS, R), "graphs": (TABLES, R), "counts": (dict, R),
                  **{kind: (TABLES, R) for kind in GEN_KINDS}},
    "generated._meta": {"format": (str, R), "generator": (str, R), "date": (str, R), "source": (dict, R)},
    "generated.graphs": {k: (int, R) for k in ("g", "toc_index", "ndbg_toc_index", "records", "links",
                                                "saved_nodes", "padding_after")},
    "generated.locations": {
        "id": (str, R), "class": (frozenset({"major", "obsidian", "gem", "cluster", "consumable"}), R),
        "item": (str, R), "pool": (bool, R), "gated_by": (STRS, O), "cell": ((str, NONE), O),
        **{k: (ANY, O) for k in ("name", "template", "yield", "unbounded", "points", "on_load", "enabled_by", "dead",
                                 "geode", "keylord", "obsidian_lock", "inside_barrier", "guardian_slot", "saved",
                                 "parent", "namespace", "name_ref", "note")}},
    "generated.barriers": {
        "id": (str, R), "kind": (frozenset({"firewall", "iceblock", "acidblock", "crystal", "trap", "other"}), R),
        "persist": (PERSISTS, R), "requires": ((str, NONE), R),
        **{k: (ANY, O) for k in ("name", "damage", "damage_mix", "elements", "level", "levels_seen", "shapes",
                                 "switches", "contains", "near_locations")}},
    "generated.geodes": {
        "id": (str, R), "requires": ((str, NONE), R),
        **{k: (ANY, O) for k in ("name", "kind", "damage", "damage_mix", "elements", "level", "levels_seen",
                                 "persist", "shapes", "switches", "variant", "locations", "contents")}},
    "generated.keylocks": {
        "id": (str, R), "coded": (bool, R), "requires": ((str, NONE), O),
        **{k: (ANY, O) for k in ("namespace", "records", "trigger", "key_fourcc", "key_type", "consumes",
                                 "lock_toggle", "saved", "drives", "drives_out", "relay_of")}},
    "generated.keylords": {
        "id": (str, R), "complete": (bool, R), "event": (str, R),
        **{k: (ANY, O) for k in ("namespace", "keylord", "key_location", "key_item", "cage", "latch_toggle")}},
    "generated.obsidian_locks": {
        "id": (str, R), "requires": (str, R),
        **{k: (ANY, O) for k in ("namespace", "lock", "threshold", "open_combiner", "lock_toggle", "saved",
                                 "locations")}},
    "generated.seals": {
        "id": (str, R), "requires": ((str, NONE), R),
        **{k: (ANY, O) for k in ("name", "activate", "touch", "saved", "sets_globals", "drives",
                                 "activate_also_drives")}},
    "generated.save_points": {"id": (str, R), **{k: (ANY, O) for k in ("name", "save_id", "saved", "do_save")}},
    "generated.exits": {
        "id": (str, R), "kind": (frozenset({"exit", "teleport", "ending", "start"}), R),
        "live": (bool, R), "dest_level": ((str, NONE), O),
        "arrival_by": (frozenset({"spot", "spot+Shape", "startspot", "origin", None}), O),
        **{k: (ANY, O) for k in ("name", "dest", "spot", "movie", "arrival", "arrival_graph_known",
                                 "dest_string_shared_by", "gate_hint", "disc_teleport")}},
    "generated.spots": {"id": (str, R), "name": (ANY, O), "teleport_gate": (ANY, O)},
    "generated.teleporters": {"id": (str, R), "namespace": (ANY, O), "locators": (STRS, R), "routes": (TABLES, R)},
    "generated.teleporters.routes": {"to": (str, R), "touch": (str, R), "needs": (STRS, R)},
    "generated.bosses": {"id": (str, R), "event": (str, R),
                         **{k: (ANY, O) for k in ("name", "critter", "saved", "on_load", "enabled_by",
                                                  "num_dead_drives")}},
    "generated.latches": {"id": (str, R), "global": ((str, NONE), R),
                          **{k: (ANY, O) for k in ("name", "saved", "update", "input")}},
    "generated.game_states": {"id": (str, R), "name": (ANY, O), "vars": (ANY, O), "links": (ANY, O)},
    "tricks": {"format": (str, R), "owner_refs": (STRS, R), "trick": (TABLES, R), "skip": (TABLES, R),
               "skip_rule": (TABLES, O), "time_saver": (TABLES, O),
               "candidate": (TABLES, O), "db_change": (TABLES, O)},
    "tricks.trick": {"name": (str, R), "description": (str, R), "mechanism": (str, R), "confidence": (ANY, R),
                     "evidence": (STRS, R)},
    "tricks.skip": {"id": (str, R), "name": (str, R), "level": (str, R), "bypasses": (str, R), "tricks": (STRS, R),
                    "requires": (str, R), "difficulty_reason": (str, R), "status": (SKIP_STATUSES, R),
                    "confirmed": (ANY, R), "confidence": (str, R), "evidence": (STRS, R), "source": (str, R),
                    "d145": (str, R), "from": (str, O), "to": (str, O), "gates": (STRS, O), "tiers": (STRS, O),
                    "difficulty": (DIFFICULTIES, O),
                    "held_reason": (str, O), "priority": (str, O), "clause": (str, O), "plugs_into": (str, O),
                    "xemu": (str, O), "xemu_ref": ((str, STRS), O), "zones": (str, O), "dark_node": (str, O),
                    "batch": (str, O), "batch_name": (str, O), "rolls": (bool, O)},
    # D145: a time-saver has none of a skip's logic keys (status, confirmed, difficulty, requires, clause, ...)
    "tricks.time_saver": {"id": (str, R), "name": (str, R), "level": (str, R), "replaces": (str, R),
                          "tricks": (STRS, R), "kit": (str, R), "video": (STRS, R), "source": (str, R),
                          "saves": (str, R), "plain": (str, R), "evidence": (STRS, R), "d145_evidence": (STRS, R),
                          "was": (str, R), "d145": (str, R), "from": (str, O), "to": (str, O), "gates": (STRS, O),
                          "zones": (str, O), "reopen": (str, O)},
    "tricks.skip_rule": {"id": (str, R), "tricks": (STRS, R), "id_pattern": (str, R), "applies": (str, R),
                         "requires_rule": (str, R), "difficulty_rule": (str, R), "status": (SKIP_STATUSES, R),
                         "once_confirmed": (SKIP_STATUSES, R), "confirmed_rule": (str, R), "source": (str, R)},
    "tricks.candidate": {"name": (str, R), "skips": (STRS, O)},
    "tricks.db_change": {"id": (str, R), "file": (str, R), "what": (str, R), "confidence": (str, R),
                         "adds_flags": (STRS, O), "removes_flags": (STRS, O), "requires": (str, O)},
    "route": {"format": (str, R), "status": (LEVEL_STATUSES, R), "step": (TABLES, R), "variant": (str, O),
              "location_steps": (int, R), "action_steps": (int, R), "replay_problems": (int, R),
              "matches_temple_order": (bool, O), "power_order": (STRS, O), "sources": (dict, O),
              "area_to_level": (dict, O)},
    "route.step": {"step": (int, R), "leg": (str, R), "level": (str, R), "kind": (frozenset({"location", "action"}), R),
                   "requires": (str, R), "ok": (bool, R), "sources": (STRS, R), "id": (str, O), "item": (str, O),
                   "class": (str, O), "action": (ROUTE_ACTIONS, O), "sets": (str, O), "consumes": (str, O),
                   "community": ((int, "ints"), O), "match": (str, O), "pool": (str, O), "note": (str, O)},
}
# tricks.toml's review material (§12): dated provenance, rules in prose, the envelope tables and per-entry notes. Any
# value; the loader reads none of it.
_REVIEW = {
    "tricks": re.compile(r"made|corrected|restructured|gated|decided(_\d+)?|xemu_applied(_\d+)?|difficulty_names|"
                         r"difficulty_rule|skip_status|confirmation_rule|envelope_rule|superseded|video_notes|"
                         r"envelope|time_saver_rule"),
    "tricks.trick": re.compile(r"needs|difficulty_basis|buffering|video_limits|questions|measured_xemu|answered|"
                               r"superseded|entry_paths|carry_rule|interactions|negatives|release_hypothesis|"
                               r"corrections|site_rule|candidates|clause_rule|uses|source|registered"),
    "tricks.skip": re.compile(r"superseded|note|method"),
    "tricks.skip_rule": re.compile(r"example|superseded|note"),
    "tricks.candidate": re.compile(r"description|note"),
}
_ROUTE_OPEN = frozenset({"unresolved_flag", "unresolved_button", "unresolved_event", "unresolved_barrier",
                         "unresolved_skip", "unresolved_generated", "unknown_level", "route_misses_location",
                         "route_repeats_location"})
_TODO_FIELDS = ("edge.from", "edge.to", "edge.exit", "button.at", "event.at", "barrier.destroy_from",
                "node.anchors", "level.route")
_HEX_RUN = re.compile(r"\b[0-9A-Fa-f]{16,}\b")
_TRIPLE = re.compile(r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]")
_XEMU_REF = re.compile(r"[^/\s]+/[A-Z][0-9]*[a-z]?(:[a-z0-9_.]+)?")


def _names(x) -> bool:
    """A non-empty list of non-empty strings (a route mark's ``unless`` or ``only``, AZ-725)."""
    return isinstance(x, list) and bool(x) and all(isinstance(s, str) and s for s in x)


def proof_problem(pv, by=PROVEN_BY) -> str | None:
    """Why ``pv`` is no proof mark ``{ by = ..., ref = "..." }`` (D122, D169, D170), else None: an L3 proof's ref
    names the sitting whose xemu replay matched, the input string and the snapshot (D170); whether it resolves to
    a ``proofs.jsonl`` record is :meth:`_Checker.resolve_proof`'s."""
    if not (isinstance(pv, dict) and {"by", "ref"} <= pv.keys() <= {"by", "ref", "unless", "only"} and pv["by"] in by
            and isinstance(pv["ref"], str) and pv["ref"].strip()):
        return f'not {{ by = {" | ".join(map(repr, by))}, ref = "..." }}'.replace("'", '"')
    if pv.keys() - {"by", "ref"} and (pv["by"] != "route" or not _names(pv.get("unless"))
                                      or ("only" in pv and not _names(pv["only"]))):
        return ("only a by-route mark names the skips it needs off (unless, a list of picks or save_warp) and the "
                "items it holds for with them on (only, a list; AZ-725)")
    if pv["by"] == "l3" and not pr.REF.fullmatch(pv["ref"]):
        return "an l3 ref is <sitting>/<input string sha12>@<snapshot meta sha12> (D170)"
    return None


@dataclass(frozen=True)
class Issue:
    """One refusal: a stable ``code``, ``where`` (file: object.field) and why."""
    code: str
    where: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.where}: {self.code}" + (f" ({self.detail})" if self.detail else "")


class DatabaseError(ValueError):
    """The database failed a load check; ``issues`` names each one."""

    def __init__(self, root: Path, issues: list[Issue]):
        self.issues = issues
        shown = "\n".join(f"  {i}" for i in issues[:40])
        more = f"\n  ... and {len(issues) - 40} more" if len(issues) > 40 else ""
        super().__init__(f"the randomizer database {root} fails {len(issues)} load check(s):\n{shown}{more}")


@dataclass
class Database:
    """A database that passed every load check. The tables are as read; the
    registries map ids to ``(level, table)`` (``hand``: ``(level, kind, table)``,
    ``generated_objects``: ``(level, kind, object)``)."""
    root: Path
    generated: dict[str, dict]
    levels: dict[str, dict]
    items: dict
    world: dict
    tricks: dict
    route: dict
    settings: dict[str, Settings]
    stubs: frozenset[str]
    nodes: dict[str, tuple[str, dict]]
    hand: dict[str, tuple[str, str, dict]]
    skips: dict[str, tuple[str, dict]]
    generated_objects: dict[str, tuple[str, str, dict]]
    flags: frozenset[str]
    counters: frozenset[str]
    node_of: dict[str, str]
    derived: dict[str, dict]
    proofs: dict[str, dict]            # proofs.jsonl's records by ref (D170): evidence, outside db_digest
    movement: dict[str, dict] = field(default_factory=dict)   # movement/<level>.json (Step R1.14b): outside db_digest
    contact: dict = field(default_factory=dict)               # contact.json (Step X.11): outside db_digest

    @property
    def defaults(self) -> Settings:
        return self.settings["defaults"]


@dataclass
class Report:
    """What :func:`check_database` found: ``issues`` (empty = loads),
    ``summary`` (counts, the open fields and the settings) and the
    ``database`` when there is no issue."""
    issues: list[Issue]
    summary: dict
    database: Database | None = None


def _is(kind, value) -> bool:
    if kind == ANY:
        return True
    if kind == NONE:
        return value is None
    if isinstance(kind, tuple):
        return any(_is(k, value) for k in kind)
    if isinstance(kind, frozenset):
        return isinstance(value, (str, int, type(None))) and not isinstance(value, bool) and value in kind
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == STRS:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == TABLES:
        return isinstance(value, list) and all(isinstance(v, dict) for v in value)
    if kind == "ints":
        return isinstance(value, list) and all(_is(int, v) for v in value)
    return isinstance(value, kind)


class _NonInteger(ValueError):
    pass


def _refuse_float(text: str):
    raise _NonInteger(f"non-integer number {text}")


class _RepeatedKey(ValueError):
    pass


def _refuse_repeats(pairs: list[tuple[str, object]]) -> dict:
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise _RepeatedKey(f"key {key!r} appears twice in one object")
        seen.add(key)
    return dict(pairs)


def _confirmed_by(c) -> str:
    """How the summary counts a skip's ``confirmed`` (a malformed one is an issue too)."""
    if isinstance(c, str):
        return c
    return c["by"] if isinstance(c, dict) and isinstance(c.get("by"), str) else "malformed"


class _Checker:
    def __init__(self, root: Path, texts: Mapping[str, str] | None = None):
        self.root = Path(root)
        self.texts = dict(texts or {})          # rel path -> the text read in place of the file's (the authoring's)
        self.issues: list[Issue] = []
        self.todo = collections.Counter()
        self.unassigned = collections.Counter()
        self.exprs = 0
        self.gen: dict[str, dict] = {}
        self.derived: dict[str, dict] = {}
        self.levels: dict[str, dict] = {}
        self.settings_tables: dict[str, dict] = {}
        self.items = self.world = self.tricks = self.route = None
        self.raw_toml: dict[str, str] = {}
        self.node_of: dict[str, str] = {}
        self.undecoded: set[str] = set()
        self.barrier_uses: list[tuple[str, str]] = []
        self.reads: list[tuple[str, str]] = []                     # (where, flag) a level file's requirement reads
        self.todo_gates = 0
        self.route_open: list[Issue] = []
        self.bound = collections.Counter()                           # (generated kind, id) -> binders
        self.asts: dict[tuple, list] = collections.defaultdict(list)   # ("barrier" | "skip", id) -> its ASTs
        self.logic_edges: list[tuple[str, dict, tuple | None]] = []
        self.proofs: dict[str, dict] = {}                              # proofs.jsonl: ref -> record (D170)
        self.movement: dict[str, dict] = {}                            # movement/<level>.json (Step R1.14b)
        self.contact: dict = {}                                        # contact.json (Step X.11)

    def issue(self, code: str, where: str, detail: str = "") -> None:
        self.issues.append(Issue(code, where, detail))

    def _names(self, node: str) -> set[str]:
        """A node's id and its zone anchors: what a proof record's edge claim may name."""
        n = self.nodes.get(node)
        return {node} | {a[5:] for a in (n[1].get("anchors", []) if n else []) if a.startswith("zone:")}

    def resolve_proof(self, pv: dict, **claim) -> str | None:
        """Why an ``l3`` mark resolves to no ``proofs.jsonl`` record claiming this location or edge (D170), else
        None; another backend's mark resolves to nothing here."""
        if pv["by"] != "l3":
            return None
        rec = self.proofs.get(pv["ref"])
        if rec is None:
            return f"no record in {pr.FILE} for {pv['ref']}"
        return pr.claim_matches(rec, **claim)

    # ---- reading ----------------------------------------------------------------------------------------------
    def _toml(self, path: Path) -> dict | None:
        rel = path.relative_to(self.root).as_posix()
        try:
            text = self.texts[rel] if rel in self.texts else path.read_text(encoding="utf-8")
            table = tomllib.loads(text)
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            self.issue("unreadable_file", rel, str(exc))
            return None
        self.raw_toml[rel] = text
        return table

    def _json(self, path: Path) -> dict | None:
        rel = path.relative_to(self.root).as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"), parse_float=_refuse_float,
                             parse_constant=_refuse_float, object_pairs_hook=_refuse_repeats)
        except _NonInteger as exc:   # FORMAT §4.4: no coordinates; generated data holds integers only
            self.issue("generated_non_integer_number", rel, str(exc))
            return None
        except _RepeatedKey as exc:  # tomllib refuses a repeated TOML key; json would keep the last value
            self.issue("generated_duplicate_key", rel, str(exc))
            return None
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self.issue("unreadable_file", rel, str(exc))
            return None
        if not isinstance(doc, dict):
            self.issue("unreadable_file", rel, "not a JSON object")
            return None
        return doc

    def read(self) -> None:
        root = self.root
        if not root.is_dir():
            self.issue("missing_file", str(root), "no database folder")
            return
        known = {"generated", "derived", "levels", "settings", "movement", "items.toml", "world.toml", "tricks.toml",
                 "route.toml", "contact.json", "forcing.json", "slider_tiers.json", pr.FILE}
        for p in sorted(root.iterdir()):
            if p.name.startswith("."):
                continue
            if p.name == "presets":      # D144: a leftover preset would look like a setting (§7.2)
                self.issue("retired_presets", "presets/", "presets are retired (D144); use settings/")
            elif p.name not in known:
                self.issue("unknown_file", p.name, "not part of the database layout (§1)")
        for name in ("items.toml", "world.toml", "tricks.toml", "route.toml"):
            path = root / name
            table = self._toml(path) if path.is_file() else None
            if not path.is_file():
                self.issue("missing_file", name)
            setattr(self, name[:-5], table)
        for sub, suffix in (("generated", ".json"), ("levels", ".toml"), ("settings", ".toml"), ("derived", "")):
            folder = root / sub
            if not folder.is_dir():
                if sub in ("generated", "levels", "settings"):
                    self.issue("missing_file", f"{sub}/")
                continue
            for p in sorted(folder.iterdir()):
                rel = f"{sub}/{p.name}"
                if p.name.startswith("."):
                    continue
                if sub == "derived":
                    self.derived_file(p, rel)
                elif not p.is_file() or p.suffix != suffix:
                    self.issue("unknown_file", rel, f"{sub}/ holds only *{suffix} files")
                elif sub == "generated":
                    doc = self._json(p)
                    if doc is not None:
                        self.gen[p.stem] = doc
                else:
                    table = self._toml(p)
                    if table is not None:
                        (self.levels if sub == "levels" else self.settings_tables)[p.stem] = table
        if "defaults" not in self.settings_tables and (root / "settings").is_dir():
            self.issue("settings_no_defaults", "settings/defaults.toml", "missing (D144)")
        names = {p.name for p in (root / "movement").iterdir() if not p.name.startswith(".")} \
            if (root / "movement").is_dir() else set()
        names |= {rel.split("/", 1)[1] for rel in self.texts if rel.startswith("movement/")}   # the authoring's
        for name in sorted(names):
            self.movement_file(root / "movement" / name, f"movement/{name}")
        if (root / "contact.json").is_file():
            self.contact_file(root / "contact.json")
        self.proofs, problems = pr.read_proofs(root / pr.FILE)         # evidence: outside db_digest
        for n, why in problems:
            self.issue("bad_proof", f"{pr.FILE}:{n}", why)

    def derived_file(self, p: Path, rel: str) -> None:
        """A ``derived/<level>.json.gz`` (§16): gzip-compressed JSON, an
        object with its format, its playable level (one with generated data)
        and its derive stamp.  Whether the stamp is current is the derive's
        own check (``rando derive --check``), which needs the draft tools."""
        if not p.is_file() or not p.name.endswith(".json.gz"):
            self.issue("unknown_file", rel, "derived/ holds only <level>.json.gz files")
            return
        level = p.name.removesuffix(".json.gz")
        try:
            doc = json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
        except (OSError, EOFError, UnicodeDecodeError, ValueError, zlib.error) as exc:
            self.issue("unreadable_file", rel, str(exc))
            return
        meta = doc.get("_meta") if isinstance(doc, dict) else None
        if not isinstance(meta, dict):
            self.issue("unreadable_file", rel, "not a JSON object with a _meta table")
            return
        self.fmt(f"{rel}: _meta", meta.get("format"), "derived")
        if level not in self.gen or level == "training_room" or doc.get("level") != level or meta.get("level") != level:
            self.issue("derived_unknown_level", rel, f"level {doc.get('level')!r}: not a playable level of generated/")
        if not (isinstance(meta.get("stamp"), str) and re.fullmatch(r"[0-9a-f]{64}", meta["stamp"])):
            self.issue("derived_no_stamp", rel, "_meta.stamp is not a sha256 (rando derive writes it)")
        self.derived[level] = doc

    def movement_file(self, p: Path, rel: str) -> None:
        """A ``movement/<level>.json`` (§17, Step R1.14b): the derive's witness flights of the level's edges (a
        build re-checked them under its own movement until D1066; outside db_digest).  Its rows are checked
        against the level file once that is read (:meth:`movement_rules`)."""
        if (rel not in self.texts and not p.is_file()) or p.suffix != ".json":
            self.issue("unknown_file", rel, "movement/ holds only <level>.json files")
            return
        try:
            doc = json.loads(self.texts[rel] if rel in self.texts else p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self.issue("unreadable_file", rel, str(exc))
            return
        if not isinstance(doc, dict) or set(doc) != {"format", "level", "certs", "edges", "nodes", "jumps"}:
            self.issue("unreadable_file", rel, "not a movement file (format, level, certs, edges, nodes, jumps)")
            return
        self.fmt(rel, doc["format"], "movement")
        self.movement[p.stem] = doc

    def contact_file(self, p: Path) -> None:
        """``contact.json`` (§17, Step X.11): flights of the movement files measured in L3 at modified movement,
        each certificate's slider ranges.  Each must measure a certificate of its level's movement file
        (:meth:`movement_rules`)."""
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self.issue("unreadable_file", "contact.json", str(exc))
            return
        if not isinstance(doc, dict) or set(doc) != {"format", "flights", "free"} \
                or not isinstance(doc["flights"], list) or not isinstance(doc["free"], dict):
            self.issue("unreadable_file", "contact.json", "not a contact file (format, flights, free)")
            return
        self.fmt("contact.json", doc["format"], "contact")
        self.contact = doc

    # ---- rule 1: formats, keys, types, enums -------------------------------------------------------------------
    def fields(self, where: str, obj: Mapping, spec_name: str) -> bool:
        """Check ``obj`` against ``SPECS[spec_name]``; False when a required
        key is missing or a value has the wrong type (the object is then left
        out of later checks)."""
        spec, review = SPECS[spec_name], _REVIEW.get(spec_name)
        ok = True
        for key, value in obj.items():
            if key in spec:
                kind = spec[key][0]
                if not _is(kind, value):
                    self.issue("bad_enum_value" if isinstance(kind, frozenset) else "bad_type", f"{where}.{key}",
                               f"{value!r}" if isinstance(kind, frozenset) else f"not {kind!r}")
                    ok = False
            elif not (review and review.fullmatch(key)):
                self.issue("unknown_key", f"{where}.{key}", "not defined by the format (§9 rule 1)")
        for key, (_, required) in spec.items():
            if required and key not in obj:
                self.issue("missing_key", f"{where}.{key}")
                ok = False
        return ok

    def fmt(self, where: str, value, kind: str) -> None:
        if value != FORMATS[kind]:
            self.issue("unknown_format", f"{where}.format", f"{value!r}, not {FORMATS[kind]!r}")

    def tables(self, where: str, parent: Mapping, key: str, spec_name: str, label) -> list[dict]:
        out = []
        for i, obj in enumerate(parent.get(key, []) if isinstance(parent.get(key), list) else []):
            w = f"{where}: {key}[{label(obj, i)}]"
            if isinstance(obj, dict) and self.fields(w, obj, spec_name):
                out.append(obj)
        return out

    def schema(self) -> None:
        def ident(o, i):
            return o.get("id", i) if isinstance(o, dict) else i

        def edge_label(o, i):
            return f"{o.get('from', '')}->{o.get('to', '')}" if isinstance(o, dict) else i

        for lvl, doc in list(self.gen.items()):
            w = f"generated/{lvl}.json"
            if not self.fields(w, doc, "generated"):
                del self.gen[lvl]
                continue
            if self.fields(f"{w}: _meta", doc["_meta"], "generated._meta"):
                self.fmt(f"{w}: _meta", doc["_meta"]["format"], "generated")
            if doc["level"] != lvl:
                self.issue("level_name_mismatch", f"{w}: level", f"{doc['level']!r}")
            self.tables(w, doc, "graphs", "generated.graphs", lambda o, i: i)
            for kind in GEN_KINDS:
                doc[kind] = self.tables(w, doc, kind, f"generated.{kind}", ident)
                for o in doc[kind]:
                    pattern = rf"({re.escape(lvl)}{'|characters' if kind == 'locations' else ''})/g\d+/r\d+"
                    if not re.fullmatch(pattern, o["id"]):
                        self.issue("bad_generated_id", f"{w}: {kind}[{o['id']}]", "not <file>/g<G>/r<R> (§2.1)")
                    if kind == "teleporters":
                        self.teleporter_routes(lvl, f"{w}: {kind}[{o['id']}]", o)
        for lvl, doc in list(self.levels.items()):
            w = f"levels/{lvl}.toml"
            if not self.fields(w, doc, "level"):
                del self.levels[lvl]
                continue
            self.fmt(w, doc["format"], "level")
            if doc["level"] != lvl:
                self.issue("level_name_mismatch", f"{w}: level", f"{doc['level']!r}")
            doc["known_traps"] = self.tables(w, doc, "known_traps", "level.known_traps", lambda o, i: i)
            doc["edge"] = self.tables(w, doc, "edge", "level.edge", edge_label)
            for kind in ("node", "barrier", "button", "event", "location", "skip"):
                doc[kind] = self.tables(w, doc, kind, f"level.{kind}", ident)
        for name, kind in (("items", "items"), ("world", "world"), ("tricks", "tricks"), ("route", "route")):
            doc = getattr(self, name)
            if doc is None:
                continue
            w = f"{name}.toml"
            if not self.fields(w, doc, kind):
                setattr(self, name, None)
                continue
            self.fmt(w, doc["format"], kind)
        if self.items:
            self.items["item"] = self.tables("items.toml", self.items, "item", "items.item",
                                             lambda o, i: o.get("name", i))
        if self.world:
            self.world["trick"] = self.tables("world.toml", self.world, "trick", "world.trick",
                                              lambda o, i: o.get("name", i))
            for key in ("time_saver", "mechanism"):
                self.world[key] = self.tables("world.toml", self.world, key, f"world.{key}", ident)
        if self.tricks:
            for key in ("trick", "candidate"):
                self.tricks[key] = self.tables("tricks.toml", self.tricks, key, f"tricks.{key}",
                                               lambda o, i: o.get("name", i))
            for key in ("skip", "skip_rule", "time_saver", "db_change"):
                self.tricks[key] = self.tables("tricks.toml", self.tricks, key, f"tricks.{key}", ident)
        if self.route:
            self.route["step"] = self.tables("route.toml", self.route, "step", "route.step",
                                             lambda o, i: o.get("step", i))
        for lvl in self.levels:
            if lvl not in self.gen:
                self.issue("level_without_generated", f"levels/{lvl}.toml", f"no generated/{lvl}.json")

    def teleporter_routes(self, lvl: str, tw: str, o: dict) -> None:
        """§3.6: each route's ``to`` is one of the teleporter's locators, and its
        field pad (``touch``) and the reset pads it ``needs`` are record ids of
        its level (pads are in no generated table, so only their form and level
        are checked)."""
        for i, r in enumerate(o["routes"]):
            rw = f"{tw}: routes[{i}]"
            if not self.fields(rw, r, "generated.teleporters.routes"):
                continue
            if r["to"] not in o["locators"]:
                self.issue("unresolved_generated", f"{rw}.to", f"{r['to']} is no locator of this teleporter")
            for key, ids in (("touch", [r["touch"]]), ("needs", r["needs"])):
                for x in ids:
                    if not re.fullmatch(rf"{re.escape(lvl)}/g\d+/r\d+", x):
                        self.issue("bad_generated_id", f"{rw}.{key}", f"{x} is not {lvl}/g<G>/r<R> (§2.1)")

    # ---- registries -------------------------------------------------------------------------------------------
    def registries(self) -> None:
        self.gobj: dict[str, tuple[str, str, dict]] = {}
        self.teleporters: dict[str, tuple[str, str, dict]] = {}   # keyed by a locator, which is also a spot (§3.6)
        for lvl, doc in self.gen.items():
            for kind in GEN_KINDS:
                for o in doc[kind]:
                    if kind == "teleporters":
                        self.teleporters[o["id"]] = (lvl, kind, o)
                        continue
                    if o["id"] in self.gobj:
                        self.issue("generated_id_collision", f"generated/{lvl}.json: {kind}[{o['id']}]")
                    self.gobj.setdefault(o["id"], (lvl, kind, o))
        items = self.items or {"counters": {}, "item": []}
        self.item_names = {it["name"] for it in items["item"]}
        adds = {it["name"]: it["counters"] for it in items["item"] if isinstance(it["counters"], dict)}
        self.slots = collections.Counter(       # a disc's guardian slots: pool locations holding one of its fragments
            disc for doc in self.gen.values() for loc in doc["locations"] if loc["pool"] and loc.get("guardian_slot")
            for disc, c in DISCS.items() if c in adds.get(loc["item"], {}))
        self.counters = set(items["counters"]) | {
            c for it in items["item"] if isinstance(it["counters"], dict) for c in it["counters"]
            if isinstance(c, str) and c.startswith("key.")}
        world = self.world or {"trick": [], "mechanism": []}
        self.families = {t["name"]: t for t in world["trick"]}
        self.mechanisms = {m["id"]: m for m in world["mechanism"]}
        self.skips: dict[str, tuple[str, dict]] = {}
        self.nodes: dict[str, tuple[str, dict]] = {}
        self.hand: dict[str, tuple[str, str, dict]] = {}
        self.flags: set[str] = set()
        for lvl, doc in self.levels.items():
            w = f"levels/{lvl}.toml"
            for n in doc["node"]:
                if n["id"] in self.nodes:
                    self.issue("node_id_duplicate", f"{w}: node[{n['id']}]")
                if not re.fullmatch(rf"{re.escape(lvl)}_[a-z0-9_]+", n["id"]):
                    self.issue("node_id_prefix", f"{w}: node[{n['id']}]", f"not {lvl}_<area> in [a-z0-9_] (§2.2)")
                self.nodes.setdefault(n["id"], (lvl, n))
            for s in doc["skip"]:
                if s["id"] in self.skips:
                    self.issue("skip_id_duplicate", f"{w}: skip[{s['id']}]")
                if not re.fullmatch(rf"{re.escape(lvl)}(\.[a-z0-9_]+)+", s["id"]):
                    self.issue("object_id_prefix", f"{w}: skip[{s['id']}]", f"not {lvl}.<slug> (§2.2)")
                self.skips.setdefault(s["id"], (lvl, s))
            for kind, flag in (("barrier", ".destroyed"), ("button", ".open"), ("event", "")):
                for o in doc[kind]:
                    if o["id"] in self.hand:
                        self.issue("object_id_duplicate", f"{w}: {kind}[{o['id']}]")
                    if not re.fullmatch(rf"{re.escape(lvl)}(\.[A-Za-z0-9_]+)+", o["id"]):
                        self.issue("object_id_prefix", f"{w}: {kind}[{o['id']}]", f"not {lvl}.<part> (§2.2)")
                    self.hand.setdefault(o["id"], (lvl, kind, o))
                    self.flags.add(o["id"] + flag)
        for doc in self.gen.values():
            for latch in doc["latches"]:
                if latch["global"]:
                    self.flags.add("global." + re.sub(r"[^A-Za-z0-9_]", "_", latch["global"]))
        self.owner_refs = set(self.tricks["owner_refs"]) if self.tricks else None   # None: tricks.toml is refused
        # D145: a time-saver, listed in tricks.toml and world.toml, is never in logic (§4.9)
        self.time_savers = {t["id"] for doc in (self.tricks, self.world) if doc for t in doc.get("time_saver", [])}
        self.stubs = {lvl for lvl, doc in self.levels.items() if doc["status"] == "draft"}
        self.stubs |= {lvl for lvl in self.gen if lvl not in self.levels}   # no level file: an unauthored stub

    # ---- rules 2 and 3: expressions and references ------------------------------------------------------------
    def expr(self, where: str, text: str) -> tuple | None:
        self.exprs += 1
        try:
            ast = parse(text, self.families)
        except ParseError as exc:
            self.issue("parse_error", where, str(exc))
            return None
        for a in atoms(ast):
            if a[0] in ("flag", "event") and where.startswith("levels/"):
                self.reads.append((where, a[1]))
            if a[0] == "counter" and a[1] not in self.counters:
                self.issue("unknown_counter", where, a[1])
            elif a[0] == "flag" and a[1] not in self.flags:
                self.issue("unresolved_flag", where, a[1])
            elif a[0] == "skip" and a[1] in self.time_savers:
                self.issue("time_saver_in_logic", where, f"{a[1]} is a time-saver: never in logic (D145)")
            elif a[0] == "skip" and a[1] not in self.skips:
                self.issue("unresolved_skip", where, a[1])
            elif a[0] in ("barrier", "button", "event") and self.hand.get(a[1], (0, 0))[1] != a[0]:
                self.issue(f"unresolved_{a[0]}", where, a[1])
            elif a[0] == "barrier":
                self.barrier_uses.append((where, a[1]))
                if a[2] != "destroy" and not all(n in self.nodes for n in a[2]):
                    self.issue("unresolved_node", where, f"{a[1]} pass {a[2][0]}->{a[2][1]}")
        return ast

    def node_ref(self, where: str, node: str, *, level: str | None = None) -> bool:
        if node not in self.nodes:
            self.issue("unresolved_node", where, node)
            return False
        if level is not None and self.nodes[node][0] != level:
            self.issue("node_in_another_level", where, f"{node} is in {self.nodes[node][0]}, not {level}")
        return True

    def gen_ref(self, where: str, gid: str, kinds, level: str) -> dict | None:
        lvl, kind, obj = self.gobj.get(gid, (None, None, None))
        if kind not in kinds and "teleporters" in kinds and gid in self.teleporters:
            lvl, kind, obj = self.teleporters[gid]
        if kind not in kinds or lvl != level:
            self.issue("unresolved_generated", where, f"{gid} is no {'/'.join(sorted(kinds))} of {level}")
            return None
        return obj

    def open_field(self, lvl: str, name: str, where: str) -> None:
        """An open field: counted in a stub, refused in an authored level (§8)."""
        if lvl in self.stubs:
            self.todo[name] += 1
        else:
            self.issue("open_field", where, f"an authored level has no open {name}")

    def levels_rules(self) -> None:
        world = self.world
        if world:
            self.expr("world.toml: victory", world["victory"])
            for key, flag in (("start", "start"), ("hub", "hub")):
                if self.node_ref(f"world.toml: {key}", world[key]):
                    marked = sorted(n for n, (_, t) in self.nodes.items() if t.get(flag))
                    if marked != [world[key]]:
                        self.issue(f"{key}_mismatch", f"world.toml: {key}",
                                   f"nodes marked {flag} = true: {marked or 'none'}")
            for name in world["starting_items"]:
                if name not in self.item_names:
                    self.issue("unknown_item", "world.toml: starting_items", name)
        for lvl, doc in self.levels.items():
            w = f"levels/{lvl}.toml"
            gen = self.gen.get(lvl)
            if gen is None:
                continue
            cells = set(gen["cells"])
            if "default_node" in doc:
                self.node_ref(f"{w}: default_node", doc["default_node"], level=lvl)
            for t in doc["known_traps"]:
                self.node_ref(f"{w}: known_traps", t["node"])
            if not doc.get("route") and any(loc["pool"] for loc in gen["locations"]):     # a level with no pool location has none
                self.open_field(lvl, "level.route", f"{w}: route")
            for x in doc.get("route", []):
                self.gen_ref(f"{w}: route", x, ("locations",), lvl)
            claimed = collections.Counter()
            zones = {z.get("id") for z in self.derived.get(lvl, {}).get("zones", []) if isinstance(z, dict)}
            zoned = collections.Counter()
            for n in doc["node"]:
                nw = f"{w}: node[{n['id']}]"
                self.dark_ref(f"{nw}.dark", n.get("dark", False), lvl, (n["id"],))
                if not n.get("anchors"):
                    self.open_field(lvl, "node.anchors", f"{nw}.anchors")
                for a in n.get("anchors", []):
                    if a.startswith("cell:"):
                        if a[5:] not in cells:
                            self.issue("unresolved_cell", f"{nw}.anchors", a)
                    elif a.startswith("zone:"):     # a zone of derived/<level>.json.gz (§4.2, §16; Step R1.8)
                        zoned[a[5:]] += 1
                        if a[5:] not in zones:
                            self.issue("unresolved_zone", f"{nw}.anchors", f"{a}: no zone of derived/{lvl}.json.gz")
                    else:
                        self.gen_ref(f"{nw}.anchors", a, ANCHOR_KINDS, lvl)
            for z, k in zoned.items():
                if k > 1:
                    self.issue("zone_in_two_nodes", f"{w}: node.anchors", z)
                for x in n.get("locations", []):
                    claimed[x] += 1
                    self.gen_ref(f"{nw}.locations", x, ("locations",), lvl)
            for x, k in claimed.items():
                if k > 1:
                    self.issue("location_in_two_nodes", f"{w}: node.locations", x)
            for e in doc["edge"]:
                self.edge(lvl, w, e)
            self.objects(lvl, w, doc)
            self.membership(lvl, w, doc)
        for lvl, doc in self.gen.items():
            for loc in doc["locations"]:
                if self.items is not None and loc["item"] not in self.item_names:
                    self.issue("unknown_item", f"generated/{lvl}.json: locations[{loc['id']}].item", loc["item"])
                for gid in loc.get("gated_by", []):
                    if self.gobj.get(gid, (0, 0))[1] not in ("geodes", "keylords", "obsidian_locks", "bosses"):
                        self.issue("unresolved_gated_by", f"generated/{lvl}.json: locations[{loc['id']}].gated_by", gid)
                if lvl not in self.levels and loc["pool"]:      # a level with no level file is a stub
                    self.unassigned[lvl] += 1

    def edge(self, lvl: str, w: str, e: dict) -> None:
        ew = f"{w}: edge[{e['from']}->{e['to']}]"
        for end in ("from", "to"):
            if not e[end]:
                self.open_field(lvl, f"edge.{end}", f"{ew}.{end}")
            else:
                self.node_ref(f"{ew}.{end}", e[end], level=lvl if end == "from" or e["kind"] in ("walk", "drop")
                              else None)
        kind = e["kind"]
        if kind in ("exit", "teleport", "cart") and not (kind == "teleport" and "teleporter" in e):
            if not e.get("exit"):
                self.open_field(lvl, "edge.exit", f"{ew}.exit")
            else:
                x = self.gen_ref(f"{ew}.exit", e["exit"], ("exits",), lvl)
                if x is not None:
                    self.bound[("exits", e["exit"])] += 1
                    if not (x["live"] and x["kind"] in ("exit", "teleport")):
                        self.issue("dead_exit_bound", f"{ew}.exit", f"{e['exit']} is {x['kind']}, live {x['live']}")
                    elif e["to"] in self.nodes and self.nodes[e["to"]][0] != x.get("dest_level"):
                        self.issue("exit_lands_elsewhere", f"{ew}.to",
                                   f"{e['exit']} leads to {x.get('dest_level')}, not {self.nodes[e['to']][0]}")
        elif "exit" in e:
            self.issue("unexpected_key", f"{ew}.exit", f"a {kind} edge takes no exit")
        if "teleporter" in e:
            self.gen_ref(f"{ew}.teleporter", e["teleporter"], ("teleporters",), lvl)
        if kind == "exit" and e.get("through"):
            self.issue("exit_with_through", f"{ew}.through", "an exit edge never passes a barrier (rule 6)")
        if kind == "cart":
            mech = self.mechanisms.get(e.get("lock"))
            if not mech or mech["kind"] != "cart":
                self.issue("cart_lock_undeclared", f"{ew}.lock",
                           f"{e.get('lock')!r} is no declared cart mechanism (rule 7)")
        elif "lock" in e:
            self.issue("unexpected_key", f"{ew}.lock", "only a cart edge has a lock")
        if "disc" in e and not self.mechanism_kind("one_shot_teleport"):
            self.issue("undeclared_mechanism", f"{ew}.disc", "the disc teleport needs a one_shot_teleport mechanism")
        if "disc" in e and self.slots[e["disc"]] != 1:
            self.issue("disc_teleport_slot", f"{ew}.disc", f"the {e['disc']} disc teleport is spent by its one guardian "
                       f"slot (a pool location holding one of its fragments), but {self.slots[e['disc']]} are found")
        for f in e.get("assumes", []):
            self.reads.append((f"{ew}.assumes", f))
            if f not in self.flags:
                self.issue("unresolved_flag", f"{ew}.assumes", f)
        if "proven" in e:       # a walked edge (D170): proven in xemu or by an L3 string xemu replayed
            if why := proof_problem(e["proven"], ("xemu", "l3")):
                self.issue("bad_proven", f"{ew}.proven", why)
            elif e.get("confidence") != "probed":
                self.issue("bad_proven", f"{ew}.proven", "a proven edge's confidence is probed")
            elif why := self.resolve_proof(e["proven"], level=lvl, from_names=self._names(e["from"]),
                                           to_names=self._names(e["to"])):
                self.issue("bad_proven", f"{ew}.proven", why)
        for b in e.get("through", []):
            if self.hand.get(b, (0, 0))[1] != "barrier":
                self.issue("unresolved_barrier", f"{ew}.through", b)
        self.dark_ref(f"{ew}.dark", e.get("dark", False), lvl, (e["from"], e["to"]))
        ast = self.expr(f"{ew}.requires", e.get("requires", "true"))
        if e.get("logic", True):
            self.logic_edges.append((ew, e, ast))

    def dark_ref(self, where: str, dark, level: str, ends: tuple[str, ...]) -> None:
        """§4.2, §4.3: ``dark`` is true, false or the id of the nolight skip
        that lifts this dark area's light need (§7.1): a skip of this level
        and, when its tricks.toml row names the area's ``dark_node``, on that
        node or an edge it ends (D144: its own dark area only)."""
        if not isinstance(dark, str):
            return
        area = {s["id"]: s.get("dark_node") for s in (self.tricks or {}).get("skip", [])}.get(dark)
        if dark not in self.skips:
            self.issue("unresolved_skip", where, dark)
        elif "nolight" not in self.skips[dark][1]["tricks"]:
            self.issue("dark_skip_not_nolight", where, f"{dark} is no skip of the nolight family")
        elif self.skips[dark][0] != level:
            self.issue("dark_skip_other_level", where, f"{dark} is a skip of {self.skips[dark][0]}")
        elif area is not None and area not in ends:
            self.issue("dark_skip_other_area", where, f"{dark} lifts the dark area at {area} (tricks.toml dark_node)")

    def mechanism_kind(self, kind: str) -> bool:
        return any(m["kind"] == kind for m in self.mechanisms.values())

    def objects(self, lvl: str, w: str, doc: dict) -> None:
        wants = {"barrier": ("barriers",), "button": ("keylocks", "seals", "obsidian_locks"),
                 "event": ("keylords", "bosses")}
        for kind in ("barrier", "button", "event"):
            for o in doc[kind]:
                ow = f"{w}: {kind}[{o['id']}]"
                gen = None
                if "of" in o:
                    gen = self.gen_ref(f"{ow}.of", o["of"], wants[kind], lvl)
                    if gen is not None:
                        self.bound[(self.gobj[o["of"]][1], o["of"])] += 1
                if "at" in o:
                    if not o["at"]:
                        self.open_field(lvl, f"{kind}.at", f"{ow}.at")
                    else:
                        self.node_ref(f"{ow}.at", o["at"])
                for key in ("requires", "override_requires"):
                    if key in o:
                        ast = self.expr(f"{ow}.{key}", o[key])
                        if kind == "barrier" and ast is not None:
                            self.asts[("barrier", o["id"])].append(ast)
                for key, reason in (("override_requires", "override_reason"), ("persist", "persist_reason")):
                    if key in o and reason not in o:
                        self.issue("missing_reason", f"{ow}.{reason}", f"{key} carries its reason (§4.4)")
                if kind != "barrier":
                    continue
                if not o.get("destroy_from"):
                    self.open_field(lvl, "barrier.destroy_from", f"{ow}.destroy_from")
                for n in o.get("destroy_from", []):
                    self.node_ref(f"{ow}.destroy_from", n)
                for key, value in o.get("bypass", {}).items():
                    m = re.fullmatch(r"([A-Za-z0-9_]+)->([A-Za-z0-9_]+)", key)
                    if not m or not isinstance(value, str):
                        self.issue("bad_bypass", f"{ow}.bypass[{key}]", "a key A->B and an expression")
                        continue
                    for n in m.groups():
                        self.node_ref(f"{ow}.bypass[{key}]", n)
                    ast = self.expr(f"{ow}.bypass[{key}]", value)
                    if ast is not None:
                        self.asts[("barrier", o["id"])].append(ast)
                for x in o.get("contains", []):
                    self.gen_ref(f"{ow}.contains", x, ("locations",), lvl)
                for x in o.get("required_for", []):
                    if self.hand.get(x, (0, 0))[1] != "event":
                        self.issue("unresolved_event", f"{ow}.required_for", x)
                if gen is not None:
                    self.barrier_gate(lvl, ow, o, gen)
        for o in doc["location"]:
            ow = f"{w}: location[{o['id']}]"
            loc = self.gen_ref(ow, o["id"], ("locations",), lvl)
            if "requires" in o:
                self.expr(f"{ow}.requires", o["requires"])
            if "proven" in o:
                if why := proof_problem(o["proven"]):
                    self.issue("bad_proven", f"{ow}.proven", why)
                elif loc is not None and not loc["pool"]:
                    self.issue("bad_proven", f"{ow}.proven", "a location out of the pool is never placed")
                elif why := self.resolve_proof(o["proven"], location=o["id"]):
                    self.issue("bad_proven", f"{ow}.proven", why)

    def barrier_gate(self, lvl: str, ow: str, o: dict, gen: dict) -> None:
        """A barrier's generated destroy requirement, parsed. An undecoded one
        (requires = null) is explained only by override_requires (``"false"``
        declares it out of logic): open in a stub, refused when authored, and
        never usable by logic while unexplained (§4.4)."""
        if gen["requires"] is not None:
            ast = self.expr(f"{ow}: generated requires", gen["requires"])
            if ast is not None:
                self.asts[("barrier", o["id"])].append(ast)
        elif "override_requires" not in o:
            self.undecoded.add(o["id"])
            if lvl in self.stubs:
                self.todo_gates += 1
            else:
                self.issue("gate_undecoded", f"{ow}.override_requires", "its generated requires is null")

    def membership(self, lvl: str, w: str, doc: dict) -> None:
        """Rule 9: each pool location has a node (§4.2's rules 1-4; rule 3
        reads the zone ``derived/<level>.json.gz`` puts it in, which is the
        derive's nearest-floor computation, §16)."""
        by_cell = {a[5:]: n["id"] for n in doc["node"] for a in n.get("anchors", []) if a.startswith("cell:")}
        by_zone = {a[5:]: n["id"] for n in doc["node"] for a in n.get("anchors", []) if a.startswith("zone:")}
        zone_of = {x.get("id"): x.get("zone") for x in self.derived.get(lvl, {}).get("locations", [])
                   if isinstance(x, dict)}
        for n in doc["node"]:
            for x in n.get("locations", []):
                self.node_of[x] = n["id"]
        for loc in self.gen[lvl]["locations"]:
            if not loc["pool"] or loc["id"] in self.node_of:
                continue
            node = by_cell.get(loc.get("cell")) or by_zone.get(zone_of.get(loc["id"])) or doc.get("default_node")
            if node:
                self.node_of[loc["id"]] = node
            elif lvl in self.stubs:
                self.unassigned[lvl] += 1
            else:
                self.issue("location_without_node", f"{w}: location[{loc['id']}]", "rule 9")

    # ---- skips (§4.8, rule 12) and their reference cycles ------------------------------------------------------
    def skip_rules(self) -> None:
        for sid, (lvl, s) in sorted(self.skips.items()):
            w = f"levels/{lvl}.toml: skip[{sid}]"
            fams = s["tricks"]
            if not fams:
                self.issue("skip_without_trick", f"{w}.tricks")
            for f in fams:
                if f not in self.families:
                    self.issue("unknown_trick", f"{w}.tricks", f)
            status = s["status"]
            if "difficulty" not in s and status != "held":
                self.issue("skip_unrated", f"{w}.difficulty", f"an {status} skip carries a difficulty")
            if "saveanywhere" in fams and status not in ("manual", "held"):
                self.issue("saveanywhere_skip_not_manual", f"{w}.status", status)
            if status == "manual" and "saveanywhere" not in fams:
                self.issue("manual_skip_without_saveanywhere", f"{w}.status")
            self.skip_refs(w, s)
            if status in ("in_logic", "manual") and s["confirmed"] == "no":
                self.issue("skip_in_logic_unconfirmed", f"{w}.confirmed",
                           f"an {status} skip is confirmed in xemu or by the owner (D114); else it is held")
            ast = self.expr(f"{w}.requires", s.get("requires", "true"))
            if ast is not None:
                self.asts[("skip", sid)].append(ast)
        self.batch_rules()

    def batch_rules(self) -> None:
        """D275: a batch's variants (``batch``, ``batch_name``) cross the same thing, its level's ends and gates
        by the same tricks, and differ only in kit: two or more of them, of one level, under one name; its id is
        ``<level>.<slug>``, no skip's or time-saver's."""
        batches = collections.defaultdict(list)
        for sid, (lvl, s) in sorted(self.skips.items()):
            if "batch" in s or "batch_name" in s:
                batches[s.get("batch")].append((lvl, s))
        for bid, rows in sorted(batches.items(), key=lambda kv: str(kv[0])):
            w = f"levels/{rows[0][0]}.toml: skip[{rows[0][1]['id']}].batch"
            same = {key: {json.dumps(s.get(key, default)) for _, s in rows} for key, default in (
                ("batch_name", None), ("from", ""), ("to", ""), ("gates", []), ("tricks", []))}
            why = ("a variant names batch and batch_name both" if bid is None or "batch_name" not in rows[0][1]
                   else f"{bid} is a skip's or a time-saver's id" if bid in self.skips or bid in self.time_savers
                   else f"not {rows[0][0]}.<slug>" if not re.fullmatch(rf"{re.escape(rows[0][0])}\.[a-z0-9_]+", bid)
                   else "a batch has two or more variants" if len(rows) < 2
                   else "its variants are of other levels" if len({lvl for lvl, _ in rows}) > 1
                   else next((f"its variants' {k} differ" for k, v in same.items() if len(v) > 1), None))
            if why:
                self.issue("bad_batch", w, why)

    def skip_refs(self, w: str, s: dict) -> None:
        """A skip's ``confirmed`` (D114: "no", an xemu row, an owner ref that
        tricks.toml's ``owner_refs`` lists, or D177's proofs.jsonl record of an
        L3 string xemu replayed, claiming this skip), its ``tiers`` (D145: a record of
        the movement tiers where it adds reach, checked, never a gate), its
        ``from`` and ``to`` nodes and its ``gates``, checked alike in a level
        file and in tricks.toml."""
        tiers = s.get("tiers")
        if tiers is not None and not (tiers and all(t in MOVEMENT_TIERS for t in tiers)
                                      and tiers == sorted(set(tiers), key=MOVEMENT_TIERS.index)):
            self.issue("bad_tiers", f"{w}.tiers", "distinct movement tiers, at least one, in tier order (D145)")
        c = s["confirmed"]
        if c != "no" and not (isinstance(c, dict) and sorted(c) == ["by", "ref"] and c["by"] in CONFIRMED_BY
                              and isinstance(c["ref"], str) and c["ref"].strip()):
            self.issue("bad_confirmed", f"{w}.confirmed", f"{c!r}")
        elif isinstance(c, dict) and c["by"] == "xemu" and not _XEMU_REF.fullmatch(c["ref"]):
            self.issue("bad_confirmed", f"{w}.confirmed", "an xemu ref is <sitting>/<row>[:<skip id>]")
        elif isinstance(c, dict) and c["by"] == "l3" and (why := self.resolve_proof(c, skip=s.get("id"))):
            self.issue("bad_confirmed", f"{w}.confirmed", why)
        elif isinstance(c, dict) and c["by"] == "owner" and self.owner_refs is not None \
                and c["ref"] not in self.owner_refs:
            self.issue("bad_confirmed", f"{w}.confirmed", f"{c['ref']!r} is no owner_refs entry of tricks.toml (D114)")
        self.ends(w, s)

    def ends(self, w: str, s: dict) -> None:
        """The ``from`` and ``to`` nodes and the ``gates`` of a skip or a time-saver."""
        for end in ("from", "to"):
            if s.get(end):
                self.node_ref(f"{w}.{end}", s[end])
        for g in s.get("gates", []):
            if g not in self.hand:
                self.issue("unresolved_gate", f"{w}.gates", g)

    def _children(self, key: tuple) -> set[tuple]:
        out = set()
        for ast in self.asts.get(key, ()):
            for a in atoms(ast):
                if a[0] in ("barrier", "skip"):
                    out.add((a[0], a[1]))
        return out

    def cycles(self) -> None:
        """§5.4: indirect references may chain (barrier: and skip: atoms
        expand); a cycle is a load error."""
        state: dict[tuple, int] = {}

        def visit(key, trail):
            if state.get(key) == 1:
                self.issue("reference_cycle", f"{key[0]} {key[1]}",
                           " -> ".join(f"{k}:{i}" for k, i in trail + [key]))
                return
            if state.get(key) == 2:
                return
            state[key] = 1
            for child in sorted(self._children(key)):
                visit(child, trail + [key])
            state[key] = 2
        for key in sorted(self.asts):
            visit(key, [])

    def reached(self, ast: tuple | None, through: list[str]) -> set[tuple]:
        """Every atom an edge's requirement reaches through barrier: and skip:
        expansions and the barriers it passes."""
        seen, out = set(), set()
        todo = [("barrier", b) for b in through] + ([("ast", ast)] if ast is not None else [])
        while todo:
            item = todo.pop()
            asts = [item[1]] if item[0] == "ast" else self.asts.get(item, [])
            if item[0] != "ast":
                if item in seen:
                    continue
                seen.add(item)
                out.add(item)
            for a in (x for t in asts for x in atoms(t)):
                out.add(a[:2])
                if a[0] in ("barrier", "skip"):
                    todo.append(a[:2])
        return out

    # ---- §3.1 and §7: non-monotone mechanisms; "no gate goes unexplained" --------------------------------------
    def gates(self) -> None:
        toggles = {i for i, (_, kind, o) in self.hand.items() if kind == "button" and o["mode"] == "toggle"}
        if toggles and not self.mechanism_kind("toggle"):
            self.issue("undeclared_mechanism", "world.toml: mechanism",
                       f"toggle buttons ({', '.join(sorted(toggles))}) need a toggle mechanism (§3.1)")
        for where, b in self.barrier_uses:
            if b in self.undecoded:
                self.issue("undecoded_gate_in_logic", where,
                           f"barrier {b}: its generated requires is null and it has no override_requires (§4.4)")
        for ew, e, ast in self.logic_edges:
            hits = self.reached(ast, e.get("through", []))
            used = {i for k, i in hits if k == "button"} | {
                i[:-5] for k, i in hits if k == "flag" and i.endswith(".open")}
            for t in sorted(used & toggles):
                self.issue("toggle_gates_edge", ew, f"toggle button {t} (rule 8)")
            for b in sorted(set(e.get("through", [])) & self.undecoded):
                self.issue("undecoded_gate_in_logic", f"{ew}.through",
                           f"barrier {b}: its generated requires is null and it has no override_requires (§4.4)")
            for b in e.get("through", []):
                lvl, kind, o = self.hand.get(b, (None, None, None))
                gen = self.gobj.get(o.get("of"), (0, 0, {}))[2] if kind == "barrier" else {}
                persist = o.get("persist", gen.get("persist")) if kind == "barrier" else "permanent"
                if persist != "permanent" and not self.mechanism_kind("respawn"):
                    self.issue("undeclared_mechanism", f"{ew}.through",
                               f"{b} ({persist}) needs a respawn mechanism (§7)")
        for gid, (lvl, kind, o) in self.gobj.items():
            if lvl not in self.levels:
                continue
            need = (kind in ("barriers", "obsidian_locks", "seals", "bosses") or (kind == "keylocks" and o["coded"])
                    or (kind == "keylords" and o["complete"]))
            n = self.bound[(kind, gid)]
            if need and n != 1:
                self.issue("gate_bound_twice" if n else "gate_unexplained", f"generated/{lvl}.json: {kind}[{gid}]",
                           f"bound by {n} hand objects; each generated gate is bound exactly once (rule 4)")
            if kind == "exits" and o["live"] and o["kind"] in ("exit", "teleport") and n != 1:
                self.issue("exit_bound_twice" if n else "exit_unexplained", f"generated/{lvl}.json: exits[{gid}]",
                           f"bound by {n} edges; each live exit is bound exactly once")

    # ---- rule 21: the game ends at a terminal event (plan §2.13 rule 4, D76) ------------------------------------
    def terminal_reads(self) -> None:
        """Only the victory may read a terminal event: no requirement or
        ``assumes`` in a level file, and no location ``gated_by`` the gate
        it is bound to (§5.6). The route and tricks.toml's pending changes
        are no solver input."""
        terminal = {oid for oid, (_, _, o) in self.hand.items() if o.get("terminal")}
        gates = {o["of"]: oid for oid, (_, _, o) in self.hand.items() if oid in terminal and "of" in o}
        reads = list(self.reads)
        for lvl, doc in sorted(self.gen.items()):
            reads += [(f"generated/{lvl}.json: locations[{loc['id']}].gated_by", gates[g])
                      for loc in doc["locations"] for g in loc.get("gated_by", []) if g in gates]
        for where, flag in reads:
            if flag in terminal:
                self.issue("terminal_event_read", where, f"{flag} ends the game: only the victory reads it (rule 21)")

    # ---- tricks.toml (tricks_check's rules) and its projection into the levels ---------------------------------
    def tricks_rules(self) -> None:
        doc = self.tricks
        if doc is None:
            return
        w = "tricks.toml"
        names = {t["name"]: t for t in doc["trick"]}
        if sorted(names) != sorted(self.families):
            self.issue("families_differ", f"{w}: trick", f"{sorted(names)} != world.toml {sorted(self.families)}")
        for n, t in names.items():
            if n in self.families and self.families[n]["description"] != t["description"]:
                self.issue("families_differ", f"{w}: trick[{n}].description", "differs from world.toml")
        cands = {c["name"]: c for c in doc["candidate"]}
        for c in cands:
            if c in self.families:
                self.issue("candidate_registered", f"{w}: candidate[{c}]")
        flags = set(self.flags)
        for ch in doc["db_change"]:
            for f in ch.get("adds_flags", []):
                if f in flags:
                    self.issue("stale_db_change", f"{w}: db_change[{ch['id']}].adds_flags", f"{f} already exists")
                flags.add(f)
            for f in ch.get("removes_flags", []):
                if f not in flags:
                    self.issue("stale_db_change", f"{w}: db_change[{ch['id']}].removes_flags", f"{f} is absent")
                flags.discard(f)
        saved, self.flags = self.flags, flags        # a db_change's flags resolve its own and the skips' clauses
        rows = {}
        for s in doc["skip"]:
            sw = f"{w}: skip[{s['id']}]"
            if s["id"] in rows:
                self.issue("skip_id_duplicate", sw)
            rows[s["id"]] = s
            if s["level"] not in self.levels or not re.fullmatch(rf"{re.escape(s['level'])}\.[a-z0-9_]+", s["id"]):
                self.issue("object_id_prefix", sw, f"not <level>.<slug> of a level file ({s['level']!r})")
            if not s["d145"].strip():
                self.issue("empty_field", f"{sw}.d145", "why it is a skip, not a time-saver (D145)")
            for f in s["tricks"]:
                if f not in self.families and f not in cands:
                    self.issue("unknown_trick", f"{sw}.tricks", f)
            status, c = s["status"], s["confirmed"]
            if any(f in cands for f in s["tricks"]) and status != "held":
                self.issue("candidate_skip_not_held", f"{sw}.status")
            if status == "held" and not s.get("held_reason"):
                self.issue("held_without_reason", f"{sw}.held_reason")
            self.skip_refs(sw, s)
            if c == "no" and status != "held":
                self.issue("skip_in_logic_unconfirmed", f"{sw}.confirmed", "an unconfirmed skip is held (D114)")
            elif c == "no":
                reason = s.get("held_reason", "")
                if not (reason.startswith("unconfirmed (D114)")
                        or ("xemu" in s and reason.startswith("failed in xemu ("))):
                    self.issue("held_reason_unconfirmed", f"{sw}.held_reason",
                               "an unconfirmed skip's reason starts 'unconfirmed (D114)' or 'failed in xemu ('")
            elif "priority" in s:
                self.issue("priority_on_confirmed", f"{sw}.priority")
            if "xemu" in s and not (s["xemu"].startswith("failed: ") and c == "no" and status == "held"):
                self.issue("bad_xemu_failure", f"{sw}.xemu", "a failed skip is held, confirmed = 'no'")
            if "priority" in s and (s["priority"] != "video" or "video:" not in s["source"]):
                self.issue("bad_priority", f"{sw}.priority", "only 'video', on a skip whose source names a video")
            d = s.get("difficulty")
            if d is None and (status != "held" or not s["difficulty_reason"].startswith("unrated")):
                self.issue("skip_unrated", f"{sw}.difficulty", "only a held skip may be unrated ('unrated ...')")
            if d is not None and d < 3 and ("tjump" in s["tricks"] or "itrig" in s["tricks"]):
                self.issue("rating_too_low", f"{sw}.difficulty", "a tjump or itrig skip is hard or above")
            if d is not None and d < 2 and status == "in_logic" and "rjump" in s["tricks"] \
                    and s["source"].startswith("video"):
                self.issue("rating_too_low", f"{sw}.difficulty", "a video rjump skip is standard or above")
            for key in ("requires", "clause"):
                if key in s:
                    ast = self.expr(f"{sw}.{key}", s[key])
                    if key == "clause" and status == "in_logic" and ast is not None and (
                            ("skip", s["id"]) not in {a[:2] for a in atoms(ast)}):
                        self.issue("clause_without_skip", f"{sw}.clause", f"names no skip:{s['id']}")
        savers = {}
        for t in doc["time_saver"]:     # D145 (§4.9): where plain movement with the same kit goes, only faster
            tw = f"{w}: time_saver[{t['id']}]"
            if t["id"] in rows or t["id"] in savers:
                self.issue("time_saver_id_duplicate", tw, "an id is a skip's or a time-saver's, never both")
            savers[t["id"]] = t
            if t["level"] not in self.levels or not re.fullmatch(rf"{re.escape(t['level'])}\.[a-z0-9_]+", t["id"]):
                self.issue("object_id_prefix", tw, f"not <level>.<slug> of a level file ({t['level']!r})")
            if not t["tricks"]:
                self.issue("skip_without_trick", f"{tw}.tricks")
            for f in t["tricks"]:
                if f not in self.families:
                    self.issue("unknown_trick", f"{tw}.tricks", f)
            for v in t["video"]:
                if not re.fullmatch(r"[A-Za-z0-9_-]{11}@\d{1,3}:\d{2}(:\d{2})?", v):
                    self.issue("bad_video_ref", f"{tw}.video", f"{v!r} is not <video id>@mm:ss")
            for key in ("saves", "plain", "was", "d145"):
                if not t[key].strip():
                    self.issue("empty_field", f"{tw}.{key}")
            self.ends(tw, t)
            ast = self.expr(f"{tw}.kit", t["kit"])
            if ast is not None and any(a[0] == "skip" for a in atoms(ast)):
                self.issue("time_saver_kit_names_skip", f"{tw}.kit", "a kit names items and powers only")
        if self.world:      # world.toml lists exactly the time-savers' id, name, level and tricks (§4.9)
            want = {i: (t["name"], t["level"], t["tricks"]) for i, t in savers.items()}
            got = collections.Counter(t["id"] for t in self.world["time_saver"])
            listed = {t["id"]: (t["name"], t["level"], t["tricks"]) for t in self.world["time_saver"]}
            for i in sorted(set(want) | set(listed)):
                if want.get(i) != listed.get(i) or got[i] > 1:
                    self.issue("time_saver_projection_differs", f"world.toml: time_saver[{i}]",
                               "not listed once with tricks.toml's name, level and tricks")
        for ch in doc["db_change"]:
            if "requires" in ch:
                self.expr(f"{w}: db_change[{ch['id']}].requires", ch["requires"])
        self.flags = saved
        for r in doc["skip_rule"]:
            rw = f"{w}: skip_rule[{r['id']}]"
            for f in r["tricks"]:
                if f not in self.families:
                    self.issue("unknown_trick", f"{rw}.tricks", f)
            if not r["id_pattern"].startswith("<level>."):
                self.issue("bad_skip_rule", f"{rw}.id_pattern", "starts '<level>.'")
            want = "manual" if "saveanywhere" in r["tricks"] else "in_logic"
            if r["status"] != "held" or r["once_confirmed"] != want:
                self.issue("bad_skip_rule", f"{rw}.status", f"a generated skip starts held, then {want} (D114)")
        for c in cands.values():
            for sid in c.get("skips", []):
                if not (sid in rows and c["name"] in rows[sid]["tricks"] and rows[sid]["status"] == "held"):
                    self.issue("bad_candidate", f"{w}: candidate[{c['name']}]", f"{sid} is no held skip naming it")
        projected = {i: s for i, s in rows.items() if all(f in self.families for f in s["tricks"])}
        for sid, s in projected.items():
            if sid not in self.skips:
                self.issue("skip_not_projected", f"{w}: skip[{sid}]", f"not in levels/{s['level']}.toml")
                continue
            lvl, t = self.skips[sid]
            if lvl != s["level"]:
                self.issue("skip_not_projected", f"{w}: skip[{sid}]", f"in levels/{lvl}.toml")
            for key in ("name", "tricks", "requires", "difficulty", "status", "confirmed", "from", "to", "gates",
                        "tiers", "batch", "batch_name"):
                default = {"from": "", "to": "", "gates": [], "requires": "true"}.get(key)
                if s.get(key, default) != t.get(key, default):
                    self.issue("skip_projection_differs", f"levels/{lvl}.toml: skip[{sid}].{key}",
                               "differs from tricks.toml (§4.8)")
        for sid in self.skips:
            if sid not in projected:
                self.issue("skip_not_in_tricks", f"levels/{self.skips[sid][0]}.toml: skip[{sid}]",
                           "every level skip is a registered-family skip of tricks.toml")
        for rel, text in sorted(self.raw_toml.items()):     # D145: no level file names one, comments included
            for i in sorted(self.time_savers) if rel.startswith("levels/") else ():
                if re.search(rf"(?<![\w.]){re.escape(i)}(?!\w)", text):
                    self.issue("time_saver_named_in_level_file", rel, i)
        self.strings_without_trick_atoms(doc)

    def strings_without_trick_atoms(self, doc) -> None:
        def walk(o, path):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from walk(v, path + (k,))
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v, path)
            elif isinstance(o, str) and "trick:" in o and not {"superseded", "answered"} & set(path):
                yield ".".join(path)
        for path in walk(doc, ()):
            self.issue("retired_trick_atom", f"tricks.toml: {path}", "'trick:' outside superseded text (D113)")

    # ---- settings (§7, rule 12) ---------------------------------------------------------------------------------
    def settings(self) -> None:
        self.parsed_settings: dict[str, Settings] = {}
        skips = {sid: s for sid, (_, s) in self.skips.items()}
        for name, table in sorted(self.settings_tables.items()):
            problems = settings_problems(table, skips)
            for code, key, detail in problems:
                if code == "settings_unknown_skip" and key.split(".", 1)[1] in self.time_savers:
                    code, detail = "time_saver_in_logic", "a time-saver has no toggle (D145)"
                self.issue(code, f"settings/{name}.toml: {key}", detail)
            if problems:
                continue
            st = settings_from_table(table, skips, f"settings/{name}.toml")
            self.parsed_settings[name] = st
            try:
                if share_decode(share_encode(st, skips), skips) != st:
                    raise ValueError("decodes to other settings")
            except ValueError as exc:
                self.issue("settings_share_roundtrip", f"settings/{name}.toml", str(exc))
        dflt = self.parsed_settings.get("defaults")
        if dflt is not None and dflt != D144_DEFAULTS:
            self.issue("defaults_differ_from_d144", "settings/defaults.toml",
                       f"{dflt} (D144: {D144_DEFAULTS}); a new default needs a recorded decision")

    # ---- the vanilla route (route.toml) -------------------------------------------------------------------------
    def route_rules(self) -> None:
        doc = self.route
        if doc is None:
            return
        w = "route.toml"
        steps = doc["step"]
        before = len(self.issues)
        if [s["step"] for s in steps] != list(range(1, len(steps) + 1)):
            self.issue("route_steps_out_of_order", f"{w}: step", "numbered 1..N in order")
        kinds = collections.Counter(s["kind"] for s in steps)
        for key, kind in (("location_steps", "location"), ("action_steps", "action")):
            if doc[key] != kinds[kind]:
                self.issue("route_count_differs", f"{w}: {key}", f"{doc[key]} != {kinds[kind]}")
        if doc["replay_problems"] != sum(1 for s in steps if not s["ok"]):
            self.issue("route_count_differs", f"{w}: replay_problems")
        for i, text in enumerate(doc.get("power_order", [])):
            ast = self.expr(f"{w}: power_order[{i}]", text)
            if ast is not None and ast[0] != "counter":
                self.issue("bad_power_order", f"{w}: power_order[{i}]", text)
        for area, v in doc.get("area_to_level", {}).items():
            if not (isinstance(v, dict) and sorted(v) == ["evidence", "level"] and isinstance(v["level"], str)
                    and v["level"] in self.gen):
                self.issue("bad_area_to_level", f"{w}: area_to_level[{area}]")
        seen = collections.Counter()
        for s in steps:
            sw = f"{w}: step[{s['step']}]"
            if s["level"] not in self.gen:
                self.issue("unknown_level", f"{sw}.level", s["level"])
            self.expr(f"{sw}.requires", s["requires"])
            if s["kind"] == "location":
                if not all(k in s for k in ("id", "item", "class")):
                    self.issue("missing_key", sw, "a location step has id, item and class")
                    continue
                seen[s["id"]] += 1
                loc = self.gen_ref(f"{sw}.id", s["id"], ("locations",), s["level"])
                if loc is not None and (loc["item"], loc["class"], loc["pool"]) != (s["item"], s["class"], True):
                    self.issue("route_step_differs", sw, f"{s['id']} holds {loc['item']} ({loc['class']}) in vanilla")
            else:
                if not all(k in s for k in ("action", "sets")):
                    self.issue("missing_key", sw, "an action step has action and sets")
                    continue
                ast = self.expr(f"{sw}.sets", s["sets"])
                if ast is not None and ast[0] not in ("button", "flag", "event"):
                    self.issue("bad_route_sets", f"{sw}.sets", "one button:, event: or flag: atom")
                if "consumes" in s and (not s["consumes"].startswith("key.") or s["consumes"] not in self.counters):
                    self.issue("unknown_counter", f"{sw}.consumes", s["consumes"])
        non_gem = {gid for gid, (lvl, kind, o) in self.gobj.items()
                   if kind == "locations" and o["pool"] and o["class"] in NON_GEM}
        for gid in sorted(non_gem - set(seen)):
            self.issue("route_misses_location", f"{w}: step", gid)
        for gid, n in sorted(seen.items()):
            if n > 1:
                self.issue("route_repeats_location", f"{w}: step", gid)
        if doc["status"] == "draft":   # a draft route is a stub: what doesn't resolve yet is open; what
                                       # contradicts the data (route_step_differs) or is malformed is refused
            found, self.issues[before:] = self.issues[before:], []
            for i in found:
                (self.route_open if i.code in _ROUTE_OPEN else self.issues).append(i)

    # ---- the movement files (§17): each row, node and location is the level file's -------------------------------
    def movement_rules(self) -> None:
        """A movement file whose level isn't authored, or whose row, node or
        location the level file doesn't have as it says (a level re-authored
        without it), is stale: ``rando author`` writes both."""
        for lvl, doc in sorted(self.movement.items()):
            rel, level = f"movement/{lvl}.json", self.levels.get(lvl)
            if doc.get("level") != lvl or level is None or level.get("status") != "authored":
                self.issue("movement_stale", rel, "not an authored level's")
                continue
            rows = {(e["from"], e["to"], e.get("difficulty", 1), e.get("confidence"), tuple(e.get("through", ()))):
                    e.get("requires", "true") for e in level.get("edge", [])}
            n = len(doc["certs"])
            for r in doc["edges"]:
                key = (r["from"], r["to"], r["difficulty"], r["confidence"], tuple(r.get("through", ())))
                texts = sorted(t for t, _ in r["terms"])
                joined = " | ".join(f"({x})" if " & " in x and len(texts) > 1 else x for x in texts)
                if rows.get(key) != joined or any(not 0 <= i < n for _, ids in r["terms"] for i in ids):
                    self.issue("movement_stale", f"{rel}: {r['from']} -> {r['to']}",
                               "not the level file's row (re-run rando author)")
            nodes = {x.get("id") for x in level.get("node", [])}
            for node in doc["nodes"]:
                if node not in nodes:
                    self.issue("movement_stale", f"{rel}: nodes.{node}", "no node of the level file")
            pool = {x["id"] for x in self.gen.get(lvl, {}).get("locations", []) if x.get("pool")}
            for loc in doc["jumps"]:
                if loc not in pool:
                    self.issue("movement_stale", f"{rel}: jumps.{loc}", "no pool location of the level")
        for f in self.contact.get("flights", []):     # contact.json (Step X.11): each measures a certificate in use
            lvl = f.get("level")
            if f.get("cert") not in self.movement.get(lvl, {}).get("certs", []):
                self.issue("contact_stale", f"contact.json: {lvl} {f.get('hop')}",
                           "its certificate is in no movement file of its level (re-measure: scripts/l3_contact.py)")

    # ---- hygiene (§4.4, D87): no coordinates and no long hex runs in the hand files ---------------------------
    def hygiene(self) -> None:
        for rel, text in sorted(self.raw_toml.items()):
            if _TRIPLE.search(text):
                self.issue("coordinate_like_triple", rel, f"{len(_TRIPLE.findall(text))} found")
            if _HEX_RUN.search(text):
                self.issue("long_hex_run", rel, f"{len(_HEX_RUN.findall(text))} found")

    # ---- items ---------------------------------------------------------------------------------------------------
    def item_rules(self) -> None:
        if self.items is None:
            return
        missing = set(COUNTERS) - set(self.items["counters"])
        for c in sorted(set(self.items["counters"]) - set(COUNTERS)):
            self.issue("unknown_key", f"items.toml: counters.{c}", "not a fixed counter (§2.4)")
        for c in sorted(missing):
            self.issue("missing_key", f"items.toml: counters.{c}")
        names = collections.Counter(it["name"] for it in self.items["item"])
        for it in self.items["item"]:
            iw = f"items.toml: item[{it['name']}]"
            if names[it["name"]] > 1:
                self.issue("item_duplicate", iw)
            if "base" in it and it["base"] not in names:
                self.issue("unknown_item", f"{iw}.base", it["base"])
            for c, n in it["counters"].items():
                if not (c in COUNTERS or re.fullmatch(r"key\.[a-z0-9_]+", c)) or not _is(int, n) or n < 1:
                    self.issue("unknown_counter", f"{iw}.counters", f"{c} = {n!r}")

    # ---- the summary -----------------------------------------------------------------------------------------------
    def summary(self) -> dict:
        skips = {sid: s for sid, (_, s) in self.skips.items()}
        ids = list(picks(skips))     # the share string's registry: the picks (D275)
        savers = (self.tricks or {}).get("time_saver", [])
        settings = {}
        for name, st in sorted(self.parsed_settings.items()):
            on = skips_on(st, skips)
            settings[name] = {"skip_ceiling": st.skip_ceiling, "movement_tier": st.movement_tier,
                              "dark_fire": DARK_FIRE, "overrides": len(st.skip_override), "skips_on": len(on),
                              "nolight_on": sum(1 for i in on if "nolight" in skips[i]["tricks"]),
                              "skips_on_ids": on, "share": share_encode(st, skips)}
        by_ceiling = {str(c): len(skips_on(Settings(c, "hard", {}), skips)) for c in SKIP_CEILINGS}
        proven = collections.Counter({by: 0 for by in PROVEN_BY})
        by_realm = {REALM_OF.get(lvl, lvl): 0 for lvl in sorted(self.levels, key=lambda v: (REALM_OF.get(v, "~"), v))}
        for lvl, doc in self.levels.items():
            for o in doc["location"]:
                pv = o.get("proven")
                if isinstance(pv, dict) and pv.get("by") in proven:
                    proven[pv["by"]] += 1
                    if self.gobj.get(o["id"], (0, 0, {}))[2].get("class") in NON_GEM:
                        by_realm[REALM_OF.get(lvl, lvl)] += 1
        with_node = collections.Counter()
        for lvl, doc in self.gen.items():
            for loc in doc["locations"]:
                if loc["pool"] and loc["id"] in self.node_of:
                    with_node[loc["class"]] += 1
        edges = [e for doc in self.levels.values() for e in doc["edge"]]
        codes = collections.Counter(i.code for i in self.issues)
        live = [o for lvl, kind, o in self.gobj.values()
                if kind == "exits" and lvl in self.levels and o["live"] and o["kind"] in ("exit", "teleport")]
        return {
            "format_version": VERSION,
            "files": {"generated": len(self.gen), "levels": len(self.levels), "settings": len(self.settings_tables)},
            "levels": {"authored": sorted(set(self.levels) - self.stubs), "stubs": sorted(self.stubs & set(self.levels)),
                       "without_a_level_file": sorted(set(self.gen) - set(self.levels))},
            "nodes": len(self.nodes), "edges": len(edges),
            "edges_by_confidence": {c: sum(1 for e in edges if e.get("confidence", "assumed") == c)
                                    for c in CONFIDENCES},
            "hand_objects": dict(sorted(collections.Counter(k for _, k, _ in self.hand.values()).items())),
            "live_exits": len(live),
            "skips": {"total": len(skips),
                      "by_status": dict(sorted(collections.Counter(s["status"] for s in skips.values()).items())),
                      "by_confirmed": dict(sorted(collections.Counter(
                          _confirmed_by(s["confirmed"]) for s in skips.values()).items())),
                      "by_difficulty": {str(k): v for k, v in sorted(collections.Counter(
                          s.get("difficulty", 0) for s in skips.values()).items())}},
            "skip_registry": {"picks": len(ids), "batches": sum(1 for p in picks(skips).values() if len(p) > 1),
                              "tag": registry_tag(ids).hex()},
            "skips_on_by_ceiling": by_ceiling,
            "time_savers": {"total": len(savers), "by_level": dict(sorted(collections.Counter(
                t["level"] for t in savers).items()))},
            "movement_tiers": list(MOVEMENT_TIERS),
            "settings": settings,
            "locations_proven": dict(sorted(proven.items())),
            "nongem_proven_by_realm": by_realm,     # Q295: each realm's proven non-gem spots (P1)
            "proofs": {"records": len(self.proofs), "by_kind": dict(sorted(collections.Counter(
                r["claim"]["kind"] for r in self.proofs.values()).items()))},
            "expressions_parsed": self.exprs,
            "todo_fields": {k: self.todo[k] for k in _TODO_FIELDS if self.todo[k]},
            "todo_fields_total": sum(self.todo.values()),
            "undecoded_gates_open": self.todo_gates,
            "pool_locations_with_a_node": dict(sorted(with_node.items())),
            "pool_locations_without_a_node": dict(sorted(self.unassigned.items())),
            "pool_locations_without_a_node_total": sum(self.unassigned.values()),
            "route": {"steps": len(self.route["step"]) if self.route else 0,
                      "status": self.route["status"] if self.route else None,
                      "open": [str(i) for i in self.route_open]},
            "issues": dict(sorted(codes.items())),
            "issues_total": len(self.issues),
        }

    def run(self) -> Report:
        steps = len(_CHECKS) + 1
        for k, (label, check) in enumerate(_CHECKS):
            _note(label, k, steps)
            getattr(self, check)()
        database = None
        if not self.issues:
            _note("building its logic", len(_CHECKS), steps)
            database = Database(
                root=self.root, generated=self.gen, levels=self.levels, items=self.items, world=self.world,
                tricks=self.tricks, route=self.route, settings=self.parsed_settings, stubs=frozenset(self.stubs),
                nodes=self.nodes, hand=self.hand, skips=self.skips, generated_objects=self.gobj,
                flags=frozenset(self.flags), counters=frozenset(self.counters), node_of=dict(self.node_of),
                derived=self.derived, proofs=self.proofs, movement=self.movement, contact=self.contact)
            logic = Logic(database)
            if not logic.anchored():      # rule 10's reach, which needs the rest to load
                self.issue("start_hub_apart", "world.toml: hub", "with every item, under no skip and the safe tier, "
                           "the start doesn't reach the hub or the hub doesn't get back to it (plan §2.13 rule 1)")
            marks = {o["id"]: (lvl, o["proven"]) for lvl, doc in self.levels.items() for o in doc["location"]
                     if isinstance(o.get("proven"), dict) and o["proven"].get("by") == "route"}
            walks = logic.route_walks(marks) if marks and not self.issues else None
            for loc, (lvl, pv) in sorted(marks.items()) if walks is not None else ():   # D169: checked, never trusted
                if why := logic.mark_short(loc, pv, walks.get(loc)):
                    self.issue("bad_proven", f"levels/{lvl}.toml: location[{loc}].proven", f"by route (D169): {why}")
            for lvl, doc in sorted(self.levels.items()) if not self.issues else ():
                marks = [*(("location", o["id"], o.get("proven"), o) for o in doc["location"]),
                         *(("edge", f"{e['from']}->{e['to']}", e.get("proven"), e) for e in doc["edge"]),
                         *(("skip", s["id"], s["confirmed"], s) for s in doc["skip"])]
                for kind, name, pv, o in marks:     # AZ-543, AZ-544: an L3 string's kit, held to D169's rule
                    if not (isinstance(pv, dict) and pv.get("by") == "l3"):
                        continue
                    kit = self.proofs[pv["ref"]]["claim"]["kit"]
                    code, mark = ("bad_confirmed", "confirmed") if kind == "skip" else ("bad_proven", "proven")
                    where = f"levels/{lvl}.toml: {kind}[{name}].{mark}"
                    if unknown := sorted(set(kit) - self.counters):
                        self.issue(code, where, f"by l3: its record's kit names no counter: {', '.join(unknown)}")
                    elif kind == "location" and (bad := logic.kit_short(name, kit)):
                        self.issue(code, where, f"by l3: {bad[1]}; its record's string ran from a new game "
                                   f"holding {bad[0]} {kit.get(bad[0], 0)} (its kit) and took the spot's own item")
                    elif kind != "location" and (bad := logic.use_short(kit, skip=name) if kind == "skip"
                                                 else logic.use_short(kit, edge=(lvl, o))):
                        self.issue(code, where, f"by l3: {bad[1]}; its record's string ran holding {bad[0]} "
                                   f"{kit.get(bad[0], 0)} (its kit)")
            if self.issues:
                database = None
        return Report(self.issues, self.summary(), database)


_CHECKS = (("reading its files", "read"), ("checking their format", "schema"), ("checking the registries", "registries"),
           ("checking the items", "item_rules"), ("checking the levels", "levels_rules"),
           ("checking the skips", "skip_rules"), ("checking for cycles", "cycles"), ("checking the gates", "gates"),
           ("checking the victory's reads", "terminal_reads"), ("checking the tricks", "tricks_rules"),
           ("checking the settings", "settings"), ("checking the vanilla route", "route_rules"),
           ("checking the movement", "movement_rules"), ("checking the rest", "hygiene"))   # _Checker.run's, in order


def _note(label: str, done: int, total: int) -> None:
    progress.note(f"{label}, {done + 1} of {total}")   # the check that starts, counted


def check_database(root: Path | str = DATA_DIR, texts: Mapping[str, str] | None = None) -> Report:
    """Apply every load check to the database at ``root``; never raises for
    bad data (each problem is an :class:`Issue` in the report). ``texts``
    (path relative to ``root`` -> text) stands in for those files: the
    authoring checks the level files it is about to write."""
    return _Checker(Path(root), texts).run()


def load_database(root: Path | str = DATA_DIR) -> Database:
    """The database at ``root``, or :class:`DatabaseError` naming every
    issue. The shipped one is read back from the user cache while its
    inputs are unchanged (:mod:`.dbcache`, Step 2.47)."""
    from azurkit.tools.randomizer import dbcache

    return dbcache.load(Path(root), _load)


_KEPT: dict[Path, tuple[str, Database, bytes, Logic]] = {}   # root -> (its cache key, its database, its tables' digest)
_MEMOS = frozenset({"db", "_compiled", "_native", "_defaults", "_inside", "_kit_memo", "_named_sets",
                    "_opener_sets", "_reached"})   # what a Logic fills in as it is asked
# kept_logic's reads in flight, by root (one at a time): the engine holds no threads, so no lock (as fill's fills in
# flight): a dict whose setdefault is atomic, and a waiter that looks every _POLL s and tells a note each WAIT s
_READING: dict[Path, list] = {}
_POLL, WAIT = 0.02, 0.1


def kept_logic(root: Path | str = DATA_DIR) -> Logic:
    """``Logic(load_database(root))``, built once a process (Step X.57: a
    test run built the shipped database's 38 times in its 8 processes;
    :data:`SHIPPED`'s when it has one). It is served again while
    ``root``'s files and the planner's code are as they were
    (:func:`.dbcache.entry`'s key: a different database never gets it),
    while it holds the database it was built with (the same object), and
    while its own tables pickle to the sha256 they had then (a table changed
    in place, or a location or skip row of its database, which they hold).
    Step 2.221: the database's own 87.5 MB pickle is no longer hashed a
    call (0.7 s, 87 times in the tracker's first ask), so treat the Logic
    and its database as read-only: a holder that wants another database
    hands it one (``logic.db = replace(logic.db, ...)``) or builds its own.
    One is read or built at a time: a caller meanwhile (the app's server:
    the Randomizer tab's ask beside the tracker's view and the read ahead)
    waits for it and is served it, never reading another (Step 4.4bd)."""
    from azurkit.tools.randomizer import dbcache

    root = Path(root).resolve()
    key = dbcache.entry(root).name
    while (logic := _served(root, key)) is None:
        if (busy := _READING.setdefault(root, mine := [False])) is mine:
            break
        told = time.monotonic()
        while not busy[0]:   # another thread's read: served it once it ends (read again if it raised)
            time.sleep(_POLL)
            if time.monotonic() - told >= WAIT:
                told = time.monotonic()
                progress.note("reading its logic")   # a cancel point
    else:
        return logic
    try:
        if (logic := _served(root, key)) is not None:   # kept since the first look
            return logic
        if (logic := SHIPPED(root, key=key) if SHIPPED is not None else None) is None:
            db = load_database(root)
            _note("building its logic", 0, 1)
            logic = Logic(db)
        if (tables := _tables(logic)) is not None:
            _KEPT[root] = (key, logic.db, tables, logic)
        return logic
    finally:
        del _READING[root]
        mine[0] = True


def logic_read(root: Path | str = DATA_DIR) -> bool:
    """Whether this process has read the Logic :func:`kept_logic` keeps for ``root``, none being read now (work ahead
    that only uses it waits for it: never the 87.6 MB read of its own at low priority, which holds the GIL the calls
    the player waits on need)."""
    root = Path(root).resolve()
    return root in _KEPT and root not in _READING


def _served(root: Path, key: str) -> Logic | None:
    """The Logic kept for ``root`` while :func:`kept_logic` may serve it again, else None."""
    if (kept := _KEPT.get(root)) is not None:
        was, db, tables, logic = kept
        if was == key and logic.db is db and _tables(logic) == tables:
            return logic
    return None


def _digest(value) -> bytes:
    return hashlib.sha256(pickle.dumps(value, pickle.HIGHEST_PROTOCOL)).digest()


def _tables(logic: Logic) -> bytes | None:
    """The digest of the tables ``Logic.__init__`` made (not its memos);
    None when something unpicklable was set on it (never served again)."""
    try:
        return _digest({k: v for k, v in vars(logic).items() if k not in _MEMOS})
    except Exception:  # noqa: BLE001
        return None


def _load(root: Path) -> Database:
    report = check_database(root)
    if report.issues:
        raise DatabaseError(root, report.issues)
    return report.database
