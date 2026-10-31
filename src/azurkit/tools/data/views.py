"""The Data tab's views (Modkit's Game Data editor's Player, Critters, Items,
Armor and Weapons tabs, D262): one entity's cells of every config.xbr table
that holds it, as :class:`Section` s of :class:`Block` s (mini-tables), each
cell a :data:`Ref` into its table, by the file's own names.

Every view reads the tables as they are now (an edit that points a
critter's damageType at another record moves its Attack), and a cell the
view shows holds a value or one the game reads for it empty (``default``,
schema.json's ``empty_default``: an attack's empty multiplier is 1).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from azurkit.core.xbr.keyed import Table

# config.xbr's tables by category, each with its name in the tab, in the list's order (D151).
CATEGORIES: dict[str, dict[str, str]] = {
    "Player": {"settings_foo": "Player global settings",
               "magic": "Magic (spells)",
               "attacks_anims": "Attack animations",
               "attacks_transitions": "Attack transitions"},
    "Critters": {"critters_critter_data": "Stats (speed, range, drops)",
                 "critters_damage": "HP and damage taken",
                 "critters_flocking": "Flocking",
                 "critters_walking": "Walking",
                 "critters_engine": "Engine",
                 "critters_special_anims": "Special animations",
                 "critters_damage_fx": "Damage effects",
                 "critters_sounds": "Sounds",
                 "critters_mutate": "Mutations",
                 "critters_maya_stuff": "Model settings (unused)"},
    "Damage": {"damage": "Damage types (all sources)"},
    "Armor": {"armor_properties": "Armor properties",
              "armor_hit_fx": "Armor hit effects"},
    "Items": {"critters_item_data": "Pickups (gems, items)"},
}
#: The player's own species: the critter tables' column the Player view shows.
PLAYER = "garret4"
#: The levels the player's spells and plain staff reach: the game holds a spell's level to 1-3 and the plain
#: staff's is spow + 1 (0x83994-0x839A5), and finds the record by type and level, the first that matches (0x46A30).
PLAYER_LEVELS = (1, 2, 3)
#: The electro shield's damage records' Type: config.xbr links them to nothing (the shield's armor Type is elec),
#: but they are the shield's, shield_lightning_1-3.
SHIELD_TYPE = "litx"
#: A name and its number: trailing (norm_1, drop1, fall height 1) or before a word of its own (lev 2 obs).
_NUMBERED = re.compile(r"^(.*?[^\d _])[ _]?(\d+)((?:[ _]|(?=[A-Z][a-z])).*)?$")
#: The Items picker's groups: a pickup's invType code against each pattern in turn, else "gems".
ITEM_GROUPS = (("fragments", r"^fg"), ("keys", r"^[a-z]\dk"), ("fuels", r"f$"), ("health", r"^heal$"),
               ("powers", r"pow$"))
#: A spell's elements by the letters of its name.
ELEMENTS = {"E": "earth", "A": "air", "F": "fire", "W": "water"}

Ref = tuple[str, int, int]
"""A cell: (table, column, row)."""


@dataclass(frozen=True)
class Noted:
    """A read-only cell whose note says more: ``cell`` in the block, ``note`` whole."""
    cell: str
    note: str


@dataclass(frozen=True)
class Block:
    """A mini-table: ``title`` ("" for its section's own rows), ``columns``
    its headings, ``rows`` each a label and, per column, a cell (a
    :data:`Ref`), a read-only text (a str or a :class:`Noted`) or ``None``."""
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, tuple], ...]
    open: bool = True       # its heading starts open (an entity family's starts closed)


@dataclass(frozen=True)
class Section:
    """One table's part of an entity's view (or one joined from several, a critter's Attack)."""
    title: str
    blocks: tuple[Block, ...]


def families(names: list[str], bare: bool = False) -> tuple[dict[str, dict[int, int]], list[int]]:
    """``names`` in families, those two or more of which share a stem and
    differ in a number, trailing or before a word (norm_1 ... norm_4, drop1
    ... drop5; lev 2 obs ... lev 4 obs, stem "lev obs"), as ``{stem:
    {number: position}}`` in first-seen order, and the positions of the
    rest. With ``bare`` a name that is a family's stem (finish, beside
    finish2 and finish3) joins it as its number -1."""
    stems: dict[str, dict[int, int]] = {}
    for i, name in enumerate(names):
        if m := _NUMBERED.match(name):
            stems.setdefault(m.group(1) + (m.group(3) or ""), {}).setdefault(int(m.group(2)), i)
    found = {stem: members for stem, members in stems.items() if len(members) > 1}
    for i, name in enumerate(names):
        if bare and name in found:
            found[name].setdefault(-1, i)
    member = {i for members in found.values() for i in members.values()}
    return ({stem: dict(sorted(members.items())) for stem, members in found.items()},
            [i for i in range(len(names)) if i not in member])


def format_value(value: object) -> str:
    """A cell's value as the tab shows it: numbers to 6 significant digits, ``-0`` as ``0``."""
    if isinstance(value, float):
        return "0" if value == 0 else f"{value:.6g}"
    return "" if value is None else str(value)


@dataclass(frozen=True)
class Grid:
    """A table's values: ``cells[col][row]``, ``None`` for an empty cell;
    ``col_at`` and ``row_at`` each name's first column and row."""
    rows: tuple[str, ...]
    cols: tuple[str, ...]
    cells: tuple[tuple[float | str | None, ...], ...]
    col_at: Mapping[str, int]
    row_at: Mapping[str, int]

    @classmethod
    def of(cls, table: Table) -> Grid:
        n = len(table.rows)
        first = lambda names: {name: k for k, name in reversed(list(enumerate(names)))}   # noqa: E731
        return cls(table.rows, table.cols, tuple(tuple(c.value for c in table.cells[k * n:(k + 1) * n])
                                                 for k in range(len(table.cols))), first(table.cols), first(table.rows))


class Views:
    """The views of config.xbr's ``tables`` as they are now; ``default(ref)``
    is what the game reads for the empty cell ``ref`` (a str), else ``None``."""

    def __init__(self, tables: Mapping[str, Table], default: Callable[[Ref], str | None]):
        self.tables, self.default = tables, default
        self._grids: dict[str, Grid] = {}
        self._drops: dict[str, list[tuple[str, int]]] | None = None

    def grid(self, table: str) -> Grid | None:
        if table not in self._grids and table in self.tables:
            self._grids[table] = Grid.of(self.tables[table])
        return self._grids.get(table)

    def text(self, table: str, entity: str, prop: str) -> str:
        """The cell ``table/entity/prop`` (its first column of that name) as the tab shows it, else ""."""
        grid = self.grid(table)
        if grid is None or entity not in grid.col_at or prop not in grid.row_at:
            return ""
        return format_value(grid.cells[grid.col_at[entity]][grid.row_at[prop]])

    # -- the pickers' lists

    def critters(self) -> list[str]:
        """config.xbr's critters: critters_engine's species but its pickups (critters_item_data's) and the player."""
        pickups = set(getattr(self.grid("critters_item_data"), "cols", ()))
        return [n for n in dict.fromkeys(getattr(self.grid("critters_engine"), "cols", ()))
                if n not in pickups and n != PLAYER]

    def critter_groups(self) -> dict[str, str]:
        """Each critter's heading in the picker, in the picker's order: its
        realm; else its body's folder when two or more of the realm-less
        share it (townspeople); else "no realm", or "no body" with none.
        Realms first, then folders, then those two."""
        text = functools.partial(self.text, "critters_engine")
        critters = self.critters()
        folder = {n: text(n, "body").rpartition("/")[0] for n in critters if not text(n, "realm")}
        shared = {f for f in folder.values() if f and list(folder.values()).count(f) > 1}
        groups = {n: text(n, "realm") or (folder[n] if folder[n] in shared else "no realm" if text(n, "body")
                                          else "no body") for n in critters}
        rank = {"no realm": 2, "no body": 3}
        return dict(sorted(groups.items(), key=lambda g: (rank.get(g[1], g[1] in shared), g[1])))

    def critter_info(self, name: str) -> list[tuple[str, str]]:
        """The picker's rows for critter ``name``: its body, realm, HP, attack and drops."""
        drops = [self.text("critters_critter_data", name, f"drop{n}") for n in range(1, 6)]
        rows = [("Body", self.text("critters_engine", name, "body")),
                ("Realm", self.text("critters_engine", name, "realm")),
                ("HP", self.text("critters_damage", name, "hitPoints")),
                ("Attack", self.text("critters_damage", name, "damageType")),
                ("Drops", ", ".join(d for d in drops if d))]
        return [(label, text) for label, text in rows if text]

    def _level(self, record: str) -> int | None:
        try:
            return int(float(self.text("damage", record, "Level")))
        except ValueError:
            return None

    def record_users(self) -> dict[str, tuple[str, list[str]]]:
        """Each damage record's users: the player's spell or plain staff
        (magic's Damage types) at the level that reaches it (the first record
        of that type and level), or the electro shield's, as "player L1" or
        "electro shield L1", else ""; and the critters whose damageType names
        it (the player's own species is the player)."""
        damage = self.grid("damage")
        if damage is None:
            return {}
        users: dict[str, tuple[str, list[str]]] = {name: ("", []) for name in damage.cols}
        kinds = [(self.text("damage", name, "Type"), self._level(name)) for name in damage.cols]
        types = {self.text("magic", spell, "Damage") for spell in getattr(self.grid("magic"), "cols", ())} - {""}
        for kind, who in [(k, "player") for k in sorted(types)] + [(SHIELD_TYPE, "electro shield")]:
            for level in PLAYER_LEVELS:
                first = next((c for c, k in enumerate(kinds) if k == (kind, level)), None)
                if first is not None:
                    users[damage.cols[first]] = (f"{who} L{level}", users[damage.cols[first]][1])
        for name in getattr(self.grid("critters_damage"), "cols", ()):
            record = self.text("critters_damage", name, "damageType")
            if record in users and name != PLAYER:
                users[record][1].append(name)
        return users

    def used_by(self, record: str, users: Mapping | None = None) -> str:
        """Who deals damage record ``record``, in a line that starts short
        (``player L1 + 28 critters``) and names them all."""
        player, critters = (users or self.record_users()).get(record, ("", []))
        who = ([player] if player else []) + (
            [", ".join(critters)] if 0 < len(critters) <= 2 else [f"{len(critters)} critters"] if critters else [])
        if not who:
            return "no spell or critter"
        listed = (f": {', '.join(critters[:8])}" + (f" and {len(critters) - 8} more" if len(critters) > 8 else "")
                  if len(critters) > 2 else "")
        shared = "; an edit here changes what each of them deals" if bool(player) + len(critters) > 1 else ""
        return " + ".join(who) + listed + shared

    def used_cell(self, record: str, users: Mapping | None = None) -> Noted:
        """A Used by row's cell: who deals ``record`` in short, the whole :meth:`used_by` line in its note."""
        users = users or self.record_users()
        player, critters = users.get(record, ("", []))
        line = self.used_by(record, users)
        if player and critters:
            return Noted(f"{player.removeprefix('player ')} + {len(critters)} critter{'s' * (len(critters) > 1)}",
                         line)
        return Noted(line.split(": ")[0].split("; ")[0], line)

    # -- one entity's view

    def critter_view(self, name: str, attack: bool = True) -> list[Section]:
        """Critter ``name``'s cells, a section per critter table it is in
        (CATEGORIES' order and labels) and, with ``attack``, the damage
        record its damageType names after its stats (its damageType there,
        not under HP). Properties it leaves empty are left out."""
        sections = []
        for table, title in CATEGORIES["Critters"].items():
            grid = self.grid(table)
            cols = [c for c, n in enumerate(getattr(grid, "cols", ())) if n == name]
            if not cols:
                continue
            if len(cols) > 1:       # named twice (good_noreht in flocking): a column each
                rows = [(grid.rows[r] or "(no name)", tuple((table, c, r) for c in cols))
                        for r in range(1, len(grid.rows)) if any(grid.cells[c][r] is not None for c in cols)]
                blocks = [Block("", tuple(str(k) for k in range(1, len(cols) + 1)), tuple(rows))] if rows else []
            else:
                moved = "damageType" if attack and table == "critters_damage" else None
                blocks = self._item_blocks([(grid.rows[r], (table, cols[0], r)) for r in range(1, len(grid.rows))
                                            if grid.rows[r] != moved])
            if blocks:
                sections.append(Section(title, tuple(blocks)))
            if table == "critters_critter_data" and attack:
                sections += self._attack(name)
        return sections

    def player_view(self) -> list[Section]:
        """The player's cells: the settings, spells, attacks, the damage
        records the player deals, armor, the hazards (the records no spell
        or critter names), then the player's critter tables (but his Attack:
        the player's are the spells)."""
        sections = []
        if (settings := self.grid("settings_foo")) is not None:
            sections.append(Section("Settings", tuple(self._item_blocks(
                [(n, ("settings_foo", c, 1)) for c, n in enumerate(settings.cols)]))))
        if (magic := self.grid("magic")) is not None:
            props = [r for r in range(1, len(magic.rows)) if any(col[r] is not None for col in magic.cells)]
            sections.append(Section("Spells (magic)", (Block("", tuple(magic.rows[r] for r in props), tuple(
                (spell, tuple(("magic", c, r) for r in props)) for c, spell in enumerate(magic.cols))),)))
        users = self.record_users()
        for title, table, cols in (
                ("Attacks (attack animations)", "attacks_anims", None),
                ("Damage the player deals", "damage", [n for n, (player, _c) in users.items() if player]),
                ("Armor", "armor_properties", None),
                ("Hazards (no spell or critter)", "damage",
                 [n for n, (player, critters) in users.items() if not player and not critters])):
            if (grid := self.grid(table)) is not None:
                picked = [c for c, n in enumerate(grid.cols) if cols is None or n in cols]
                if blocks := self._entity_blocks(table, picked, users if table == "damage" else None):
                    sections.append(Section(title, tuple(blocks)))
        return sections + self.critter_view(PLAYER, attack=False)

    def _filled(self, ref: Ref) -> bool:
        """Whether a view shows the cell: it holds a value, or the game reads a known default for it."""
        return self.grid(ref[0]).cells[ref[1]][ref[2]] is not None or self.default(ref) is not None

    def _item_blocks(self, items: list[tuple[str, Ref]]) -> list[Block]:
        """One entity's ``items`` (a property and its cell each) as blocks:
        the filled ones not in a family as its section's own rows; the
        families whose stems share a first word as a mini-table each, a stem
        per row and a number per column (drop, dropCount and dropChance by 1
        ... 5), a first word of one stem as own rows; and the properties
        named for a damage record as one by type and level."""
        records = set(getattr(self.grid("damage"), "cols", ()))
        named = [(name, ref) for name, ref in items if name in records and self._filled(ref)]
        items = [(name, ref) for name, ref in items if name not in records]
        names = [name for name, _ref in items]
        found, rest = families(names)
        words: dict[str, list[str]] = {}
        for stem, members in found.items():
            if any(self._filled(items[i][1]) for i in members.values()):
                words.setdefault(re.match(r".[^ _A-Z]*", stem).group(), []).append(stem)
        own = set(rest) | {i for stems in words.values() if len(stems) == 1 for i in found[stems[0]].values()}
        rows = tuple((names[i] or "(no name)", (items[i][1],)) for i in sorted(own) if self._filled(items[i][1]))
        blocks = [Block("", ("",), rows)] if rows else []
        for word, stems in words.items():
            if len(stems) > 1:
                numbers = sorted({n for stem in stems for n in found[stem]})
                blocks.append(Block(word, tuple(map(str, numbers)), tuple(
                    (stem, tuple(items[found[stem][n]][1] if n in found[stem] else None for n in numbers))
                    for stem in stems)))
        return blocks + self._record_block(named)

    def _record_block(self, named: list[tuple[str, Ref]]) -> list[Block]:
        """The cells named for damage records as one mini-table: a row per
        record Type, a column per Level (L1 ... L4), each record under its
        own Level. A record whose Type's row holds its Level already is a row
        of its own; a row of one record is labelled with its name, a row of
        more with their stem."""
        rows: list[tuple[list[str], dict[int, Ref]]] = []
        row_of: dict[str, int] = {}
        loose = []
        for name, ref in named:
            kind, level = self.text("damage", name, "Type"), self._level(name)
            if level is None:
                loose.append((name, (ref,)))
                continue
            r = row_of.get(kind)
            if r is None or level in rows[r][1]:
                row_of.setdefault(kind, len(rows))
                rows.append(([], {}))
                r = len(rows) - 1
            rows[r][0].append(name)
            rows[r][1][level] = ref
        levels = sorted({n for _names, cells in rows for n in cells})

        def label(names: list[str]) -> str:
            stems = {re.sub(r"[ _]?\d+$", "", n) for n in names}
            return names[0] if len(names) == 1 or len(stems) > 1 else stems.pop()

        blocks = [Block("per damage type", tuple(f"L{n}" for n in levels), tuple(
            (label(names), tuple(cells.get(n) for n in levels)) for names, cells in rows))] if rows else []
        return blocks + ([Block("damage records with no level", ("",), tuple(loose))] if loose else [])

    def _entity_blocks(self, table: str, cols: list[int], users: Mapping | None = None) -> list[Block]:
        """Table ``table``'s entities ``cols`` as blocks in table order, each
        starting closed: each family (norm_1 ... norm_4; finish, finish2,
        finish3) one, its members as columns and the table's properties as
        rows, each other entity one of its own; with damage records'
        ``users``, a "Used by" row under each."""
        grid = self.grid(table)
        names = [grid.cols[c] for c in cols]
        found, rest = families(names, bare=True)
        groups = sorted([(stem, [cols[i] for i in m.values()]) for stem, m in found.items()]
                        + [(names[i], [cols[i]]) for i in rest], key=lambda g: g[1][0])
        blocks = []
        for title, members in groups:
            props = [r for r in range(1, len(grid.rows)) if any(self._filled((table, c, r)) for c in members)]
            rows = [(grid.rows[r] or "(no name)", tuple((table, c, r) for c in members)) for r in props]
            if users is not None:
                rows.append(("Used by", tuple(self.used_cell(grid.cols[c], users) for c in members)))
            blocks.append(Block(title, tuple(grid.cols[c] for c in members), tuple(rows), open=False))
        return blocks

    def _attack(self, name: str) -> list[Section]:
        """Critter ``name``'s Attack: its damageType and the record it names, with who else deals it."""
        taken = self.grid("critters_damage")
        record = self.text("critters_damage", name, "damageType")
        if not record:
            return []
        own = ("damageType", (("critters_damage", taken.cols.index(name), taken.rows.index("damageType")),))
        damage = self.grid("damage")
        if record not in damage.cols:
            return [Section("Attack", (Block("", ("",), (own, ("Record", (f"{record} names no damage record",)))),))]
        c = damage.cols.index(record)
        rows = [(damage.rows[r], (("damage", c, r),)) for r in range(1, len(damage.rows))
                if damage.cells[c][r] is not None]
        return [Section("Attack", (Block("", (record,), (own, *rows, ("Used by", (self.used_cell(record),)))),))]

    # -- the Items, Armor and Weapons views

    def _cols(self, table: str, cols: list[int], headings: Iterable[str] | None = None, extra: tuple = ()) -> Block:
        """Table ``table``'s columns ``cols`` side by side as one open block,
        headed by their names (else ``headings``): the properties any of
        them fills as rows, then ``extra`` rows."""
        grid = self.grid(table)
        rows = [(grid.rows[r] or "(no name)", tuple((table, c, r) for c in cols)) for r in range(1, len(grid.rows))
                if any(self._filled((table, c, r)) for c in cols)]
        return Block("", tuple(headings or (grid.cols[c] for c in cols)), (*rows, *extra))

    def _at(self, table: str, col: int, prop: str) -> str:
        """Column ``col``'s ``prop`` in ``table`` (by position: attacks_transitions' columns are all a or z)."""
        grid = self.grid(table)
        return format_value(grid.cells[col][grid.rows.index(prop)] if grid is not None and prop in grid.rows
                            else None)

    def _naming(self, table: str, prop: str, names: Iterable[str]) -> list[int]:
        """The columns of ``table`` whose ``prop`` names one of ``names``."""
        names = set(names)
        return [c for c in range(len(getattr(self.grid(table), "cols", ()))) if self._at(table, c, prop) in names]

    def items(self) -> dict[str, str]:
        """The pickups (critters_item_data's) and each one's group in the
        Items picker (by its invType), the groups in the order the table
        first holds them."""
        groups = {}
        for name in dict.fromkeys(getattr(self.grid("critters_item_data"), "cols", ())):
            code = self.text("critters_item_data", name, "invType")
            groups[name] = next((g for g, pattern in ITEM_GROUPS if re.search(pattern, code)), "gems")
        first = {g: k for k, g in reversed(list(enumerate(groups.values())))}
        return dict(sorted(groups.items(), key=lambda item: first[item[1]]))

    def _droppers(self, item: str) -> list[tuple[str, int]]:
        """The critters that drop ``item`` and the slot (drop1 ... drop5)."""
        if self._drops is None:
            self._drops = {}
            for critter in getattr(self.grid("critters_critter_data"), "cols", ()):
                for n in range(1, 6):
                    self._drops.setdefault(self.text("critters_critter_data", critter, f"drop{n}"), []).append(
                        (critter, n))
        return list(self._drops.get(item, ())) if item else []

    def item_info(self, name: str) -> list[tuple[str, str]]:
        """The picker's rows for pickup ``name``: its type, amount, duration, body and who drops it."""
        droppers = list(dict.fromkeys(critter for critter, _n in self._droppers(name)))
        rows = [("Type", self.text("critters_item_data", name, "invType")),
                ("Amount", self.text("critters_item_data", name, "invAmount")),
                ("Lasts", self.text("critters_item_data", name, "duration")),
                ("Body", self.text("critters_engine", name, "body")),
                ("Dropped by", ", ".join(droppers[:6])
                 + (f" and {len(droppers) - 6} more" if len(droppers) > 6 else ""))]
        return [(label, text) for label, text in rows if text]

    def item_view(self, name: str) -> list[Section]:
        """Pickup ``name``'s cells: its pickup row, the drop slots of the
        critters that drop it, then a section per critter table it is in."""
        grid, sections = self.grid("critters_item_data"), []
        if grid is not None and name in grid.cols:
            c = grid.cols.index(name)
            sections.append(Section(CATEGORIES["Items"]["critters_item_data"], tuple(self._item_blocks(
                [(grid.rows[r], ("critters_item_data", c, r)) for r in range(1, len(grid.rows))]))))
        data = self.grid("critters_critter_data")
        drops = [(f"{critter} (slot {n})", tuple(("critters_critter_data", data.cols.index(critter),
                                                  data.rows.index(f"{prop}{n}"))
                                                 for prop in ("drop", "dropCount", "dropChance")))
                 for critter, n in self._droppers(name)]
        if drops:
            sections.append(Section("Dropped by", (Block("", ("drop", "dropCount", "dropChance"), tuple(drops)),)))
        return sections + self.critter_view(name, attack=False)

    def armor_families(self) -> dict[str, dict[int, int]]:
        """armor_properties' families (no_armor; earth_armor, ice_armor ...
        at levels 1-3), each ``{level: column}``, in table order."""
        names = list(getattr(self.grid("armor_properties"), "cols", ()))
        found, rest = families(names)
        for i in rest:         # a family of one (no_armor_1)
            m = _NUMBERED.match(names[i])
            found.setdefault(m.group(1) + (m.group(3) or "") if m else names[i], {int(m.group(2)) if m else 1: i})
        return dict(sorted(found.items(), key=lambda f: min(f[1].values())))

    def armor_info(self, family: str) -> list[tuple[str, str]]:
        """The picker's rows for armor ``family``: its type, levels, the
        spell that casts it and what it is strong and weak against."""
        grid, members = self.grid("armor_properties"), self.armor_families().get(family, {})
        first = grid.cols[min(members.values())] if members else ""
        kind = self.text("armor_properties", first, "Type")
        spells = [s for s in getattr(self.grid("magic"), "cols", ()) if kind and self.text("magic", s, "Armor") == kind]
        rows = [("Type", kind), ("Levels", ", ".join(map(str, members))), ("Spell", ", ".join(spells)),
                ("Strong vs", self.text("armor_properties", first, "Strong vs")),
                ("Weak vs", self.text("armor_properties", first, "Weak vs"))]
        return [(label, text) for label, text in rows if text]

    def armor_view(self, family: str) -> list[Section]:
        """Armor ``family``'s cells: one mini-table, its properties as rows
        (every one of armor_properties', filled or not) and its levels as
        columns; the spell that casts it; and its hit effects by level."""
        grid, members = self.grid("armor_properties"), self.armor_families().get(family, {})
        cols = list(members.values())
        rows = tuple((grid.rows[r], tuple(("armor_properties", c, r) for c in cols))
                     for r in range(1, len(grid.rows)) if grid.rows[r])
        sections = [Section(CATEGORIES["Armor"]["armor_properties"], (Block("", tuple(map(str, members)), rows),))]
        kind = self.text("armor_properties", grid.cols[cols[0]], "Type") if cols else ""
        spells = [c for c, s in enumerate(getattr(self.grid("magic"), "cols", ()))
                  if kind and self.text("magic", s, "Armor") == kind]
        if spells:
            sections.append(Section("Spell (magic)", (self._cols("magic", spells),)))
        if fx := self._naming("armor_hit_fx", "armor type", [grid.cols[c] for c in cols]):
            hits = self.grid("armor_hit_fx")
            levels = {grid.cols[c]: str(n) for n, c in members.items()}
            sections.append(Section(CATEGORIES["Armor"]["armor_hit_fx"], (Block(
                "", tuple(levels[self._at("armor_hit_fx", c, "armor type")] for c in fx),
                (("effect", tuple(hits.cols[c] for c in fx)),
                 ("armor type", tuple(("armor_hit_fx", c, hits.rows.index("armor type")) for c in fx)))),)))
        return sections

    def _staff_records(self, spell: str, users: Mapping | None = None) -> list[str]:
        """The damage records staff spell ``spell`` deals: the first of its Damage type at each player level."""
        kind = self.text("magic", spell, "Damage")
        users = users or self.record_users()
        return [n for n, (player, _c) in users.items() if player.startswith("player")
                and self.text("damage", n, "Type") == kind]

    def weapons(self) -> dict[str, str]:
        """The player's weapons, magic's staff spells (the plain staff,
        magic's none, and the nine elemental staffs), each with its list
        text, named for the records it deals ("water staff (W)")."""
        users, out = self.record_users(), {}
        for spell in getattr(self.grid("magic"), "cols", ()):
            if self.text("magic", spell, "Type") == "staff":
                records = self._staff_records(spell, users)
                stem = "plain" if spell == "none" else re.sub(r"[ _]?\d+$", "", records[0]) if records else spell
                out[spell] = f"{stem} staff ({spell})"
        return out

    def weapon_info(self, spell: str) -> list[tuple[str, str]]:
        """The picker's rows for staff spell ``spell``: its elements, the
        records it deals, one-shot or not and its own moves."""
        records = self._staff_records(spell)
        moves = [self._at("attacks_transitions", c, "next move")
                 for c in self._naming("attacks_transitions", "damage type", records)]
        rows = [("Elements", ", ".join(ELEMENTS[k] for k in spell if k in ELEMENTS) or "none"),
                ("Deals", f"{self.text('magic', spell, 'Damage')}: {', '.join(records)}"),
                ("One-shot", "yes" if self.text("magic", spell, "Auto") not in ("", "0") else ""),
                ("Own moves", ", ".join(dict.fromkeys(moves)))]
        return [(label, text) for label, text in rows if text]

    def weapon_view(self, spell: str) -> list[Section]:
        """Staff spell ``spell``'s cells: its magic column; the damage
        records it deals at levels 1-3 side by side (with who else deals
        each); the attack transitions those records gate (three to a
        mini-table) and the moves they start; the records' hit effects; and
        each critter table's cells named for the records, a critter per row."""
        magic = self.grid("magic")
        sections = [Section("Spell (magic)", (self._cols("magic", [magic.cols.index(spell)]),))]
        users = self.record_users()
        records = self._staff_records(spell, users)
        damage = self.grid("damage")
        if records:
            sections.append(Section("Damage it deals", (self._cols(
                "damage", [damage.cols.index(n) for n in records],
                extra=(("Used by", tuple(self.used_cell(n, users) for n in records)),)),)))
        gates = self._naming("attacks_transitions", "damage type", records)
        chunks = [gates[k:k + len(PLAYER_LEVELS)] for k in range(0, len(gates), len(PLAYER_LEVELS))]
        if chunks:      # the water staff's six: #4-#6 and #7-#9
            sections.append(Section(CATEGORIES["Player"]["attacks_transitions"], tuple(
                replace(self._cols("attacks_transitions", chunk, (f"#{c + 1}" for c in chunk)),
                        title=f"#{chunk[0] + 1}-#{chunk[-1] + 1}" if len(chunks) > 1 else "") for chunk in chunks)))
        anims = self.grid("attacks_anims")
        moves = dict.fromkeys(self._at("attacks_transitions", c, "next move") for c in gates)
        if own := [c for c, n in enumerate(getattr(anims, "cols", ())) if n in moves]:
            sections.append(Section(CATEGORIES["Player"]["attacks_anims"], tuple(
                replace(b, open=True) for b in self._entity_blocks("attacks_anims", own))))
        if fx := self._naming("armor_hit_fx", "damage type", records):
            hits = self.grid("armor_hit_fx")
            sections.append(Section(CATEGORIES["Armor"]["armor_hit_fx"], (Block(
                "", tuple(self._at("armor_hit_fx", c, "damage type") for c in fx),
                (("effect", tuple(hits.cols[c] for c in fx)),
                 ("damage type", tuple(("armor_hit_fx", c, hits.rows.index("damage type")) for c in fx)))),)))
        for table, title in CATEGORIES["Critters"].items():
            grid = self.grid(table)
            named = [grid.rows.index(n) for n in records if grid is not None and n in grid.rows]
            rows = tuple((critter, tuple((table, c, r) for r in named)) for c, critter in enumerate(
                getattr(grid, "cols", ())) if named and any(self._filled((table, c, r)) for r in named))
            if rows:      # critters_damage's only the records' rows: what each takes, no HP
                title = "Damage taken" if table == "critters_damage" else title
                sections.append(Section(f"{title}, per critter", (Block("", tuple(grid.rows[r] for r in named), rows),)))
        return sections
