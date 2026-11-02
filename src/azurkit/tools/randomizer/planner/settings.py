"""The randomizer's options (D144; docs/RANDOMIZER_DB.md §7): a settings
table's rules, which skips it turns on, and the share string.

There are no presets. A settings file sets ``skip_ceiling`` (0-4),
``movement_tier``, ``dark_fire`` (always 1, D1061) and ``[skip_override]``, the per-skip
toggles, which win over the ceiling but never turn on a held or manual
skip; ``exclude_categories`` (Step R1.10b, optional) names the item
categories whose items keep their vanilla places. In format /1 and share
strings before version 3, ``powers`` keeps the upgrades too (Step 2.90a
split them off, an old file's meaning kept); keeping the elemental powers
alone takes format /2 or version 3 (:func:`category_table`). ``skips`` arguments map
a skip id to its ``[[skip]]`` table (its ``status``, ``difficulty`` and
``confirmed`` are read). ``Settings.sliders`` (AZ-383) holds the build's
movement sliders that aren't vanilla's, which pick the tier its seed is
filled at (``movement.played``, D1066); a settings file can't hold them
(its format stays /1), the share string does (its version 2).

``Settings.seed_difficulty`` (D1031, D1037, D1039; :mod:`.difficulty`) is the
level the fill shapes a seed to: 0 (Any, the default: today's seeds), or a
rating, 2 Standard, 3 Hard, 4 Frame-perfect, never above what the movement
tier and the skips on allow (:func:`top_rating`). A file writes
``seed_difficulty`` only when it is over 0, and a share string takes version 4
then, so every other file and string is as before.

D275 (Step R1.31): skips that cross the same thing and differ only in the
kit they need are variants of one batch (each variant's ``batch`` and
``batch_name``). A toggle, and so a share string's registry, names a pick:
a batch's id, or a lone skip's own. A toggle on a batch turns on its
in-logic variants; the ceiling admits each variant by its own tier. An old
per-variant id in a settings table, or a share string made for the
per-variant registry, loads as its batch (on when any of its ids is on).
"""

from __future__ import annotations

import base64
import hashlib
import math
import struct
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

SETTINGS_FORMAT = "azurik-rando-settings/1"
SETTINGS_FORMAT_ELEMENTAL = "azurik-rando-settings/2"   # /1, but its "powers" is the elemental powers alone
MOVEMENT_TIERS = ("safe", "standard", "hard", "frame_perfect")   # index + 1 = an edge's difficulty (§4.3)
SKIP_CEILINGS = (0, 1, 2, 3, 4)   # 0 none, 1 safe (D259: no skip is rated 1, so none), 2 standard ... 4 frame-perfect
DARK_FIRE = 1   # D1061: a dark area always needs Fire 1, unless its own nolight skip is on. A file and a settings digest
#                 keep the key at 1 for good: dropping it would move every seed (settings_digest seeds every stream)
OPTIONS = ("skip_ceiling", "movement_tier", "dark_fire")
# exclude_categories' values and the share string's mask bits: append only (a bit is its index)
CATEGORIES = ("fragments", "powers", "gems", "obsidians", "consumables", "upgrades")
UPGRADES = ("power_life", "power_staff1", "power_staff2", "power_ammo")   # "upgrades"; the other power_* "powers"
SEED_DIFFICULTIES = (0, 2, 3, 4)   # the ratings a seed may be shaped to, 0 none: no Safe level, a Safe rating needs no trick
SEED_DIFFICULTY_FILL = 1           # level > 0's algorithm: bumped when the same inputs give such a seed another placement
RATING_NAMES = ("None", "Safe", "Standard", "Hard", "Frame-perfect")   # a rating's name, 0 none
RETIRED_KEYS = ("name", "default", "knobs", "tricks")             # the presets' keys (D113, D144)
SHARE_PREFIX = "AZR-"
SHARE_VERSION = 0   # the payload's byte 0: its first layout (§7.3)
SHARE_VERSION_CATEGORIES = 1   # version 0 plus, after the toggles, the excluded categories' mask byte
SHARE_VERSION_SLIDERS = 2      # version 1 plus, after the mask, the movement sliders: a count byte, then each
#                                slider's index in SHARE_SLIDERS and its value (float64, little-endian)
SHARE_VERSION_ELEMENTAL = 3    # version 2 (its slider count may be 0) whose mask's "powers" bit is the
#                                elemental powers alone; before it, that bit keeps the upgrades too
SHARE_VERSION_DIFFICULTY = 4   # a seed difficulty over 0: the head, the toggles, a literal category mask (a bit per
#                                CATEGORIES entry, never folded), the slider count (0 too) and sliders, then one byte,
#                                SEED_DIFFICULTY_FILL << 3 | the level
# The movement sliders (physics.SLIDERS) by their share-string index: append only, an index never changes
SHARE_SLIDERS = (
    ("player_physics", "walk_speed_scale"), ("player_physics", "gravity"), ("player_physics", "jump_speed_scale"),
    ("player_physics", "air_control_scale"), ("player_physics", "flap_height_scale"),
    ("player_physics", "wing_flap_ceiling_scale"), ("player_physics", "flap_below_peak_scale"),
    ("player_physics", "flap_descent_fuel_cost_scale"), ("player_physics", "flap_entry_fuel_cost_scale"),
    ("player_physics", "roll_speed_scale"), ("player_physics", "swim_speed_scale"),
    ("air_shield_flaps", "air_shield_1_flaps"), ("air_shield_flaps", "air_shield_2_flaps"),
    ("air_shield_flaps", "air_shield_3_flaps"), ("fps_unlock", "target_fps"),
    ("player_physics", "roll_time_scale"), ("player_physics", "climb_speed_scale"))


def category(item: str) -> str | None:
    """The ``exclude_categories`` category of an item (its base name):
    None for a key, which the fill never moves (I-9)."""
    if item.startswith("key_"):
        return None
    if item.startswith("frag_"):
        return "fragments"
    if item in UPGRADES:
        return "upgrades"
    if item.startswith("power_"):
        return "powers"
    if item in ("diamond", "emerald", "ruby", "sapphire"):
        return "gems"
    return "obsidians" if item == "obsidian" else "consumables"


@dataclass(frozen=True)
class Settings:
    skip_ceiling: int
    movement_tier: str
    skip_override: Mapping[str, bool] = field(default_factory=dict)
    exclude_categories: frozenset[str] = frozenset()
    sliders: Mapping[str, Mapping[str, float]] = field(default_factory=dict)   # {pack: {slider: value}}, AZ-383
    seed_difficulty: int = 0   # D1037: one of SEED_DIFFICULTIES


D144_DEFAULTS = Settings(0, "standard", {})   # D186: standard movement (was hard, D144)


class SettingsError(ValueError):
    """A settings table or share string the rules refuse; ``problems`` holds
    ``(code, key, detail)`` for each reason."""

    def __init__(self, where: str, problems: list[tuple[str, str, str]]):
        self.problems = problems
        super().__init__(f"{where}: " + "; ".join(f"{key}: {detail}" for _, key, detail in problems))


def category_table(excluded: Iterable[str]) -> tuple[str, list[str]]:
    """The settings format and ``exclude_categories`` list a settings table
    holds ``excluded`` (literal categories) in: format /1, whose ``powers``
    keeps the upgrades too (so both kept are ``powers`` alone, an old
    file's meaning), unless the elemental powers are kept without the
    upgrades, which takes /2 (Step 2.90a)."""
    cats = sorted(excluded, key=CATEGORIES.index)
    if "powers" not in cats:
        return SETTINGS_FORMAT, cats
    if "upgrades" not in cats:
        return SETTINGS_FORMAT_ELEMENTAL, cats
    return SETTINGS_FORMAT, [c for c in cats if c != "upgrades"]


def _int_in(value, allowed) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value in allowed


def turnable(skip: Mapping) -> bool:
    """A skip a setting may turn on: in logic, so confirmed (D114)."""
    return skip.get("status") == "in_logic" and skip.get("confirmed", "no") != "no"


def pick_of(sid: str, skips: Mapping[str, Mapping]) -> str:
    """D275: the pick ``sid`` stands for: a variant's batch id, else ``sid`` itself."""
    s = skips.get(sid)
    return s.get("batch", sid) if isinstance(s, Mapping) else sid


def picks(skips: Mapping[str, Mapping]) -> dict[str, list[str]]:
    """D275: each pick (a batch's id, or a lone skip's own) -> its skips' ids, sorted."""
    out: dict[str, list[str]] = {}
    for sid in sorted(skips):
        out.setdefault(pick_of(sid, skips), []).append(sid)
    return dict(sorted(out.items()))


def _registry(skips) -> list[str]:
    """The share string's registry: the picks of ``skips`` (id -> table), or the given ids as they are."""
    return list(picks(skips)) if isinstance(skips, Mapping) else sorted(skips)


def _folded(toggles: Mapping[str, bool], skips: Mapping[str, Mapping]) -> dict[str, bool]:
    """D275: the toggles by pick: an old per-variant id loads as its batch, on when any of its ids is on (the
    batch's own id, when given too, wins)."""
    out: dict[str, bool] = {}
    for sid, value in toggles.items():
        pid = pick_of(sid, skips)
        if pid == sid:
            out[sid] = value
        elif pid not in toggles:
            out[pid] = out.get(pid, False) or value
    return out


def settings_problems(table: Mapping, skips: Mapping[str, Mapping]) -> list[tuple[str, str, str]]:
    """Every reason §7.2 refuses ``table`` (a parsed settings file), as
    ``(code, key, detail)``; empty when it is valid."""
    out = []
    for key in table:
        if key in RETIRED_KEYS:
            out.append(("settings_retired_key", key, "a retired preset key (D144: no presets)"))
        elif key not in ("format", "skip_override", "exclude_categories", "seed_difficulty", *OPTIONS):
            out.append(("unknown_key", key, "not a settings key"))
    if table.get("format") not in (SETTINGS_FORMAT, SETTINGS_FORMAT_ELEMENTAL):
        out.append(("unknown_format", "format", f"{table.get('format')!r}, not {SETTINGS_FORMAT!r} "
                                                f"or {SETTINGS_FORMAT_ELEMENTAL!r}"))
    for key in OPTIONS:
        if key not in table:
            out.append(("settings_missing_option", key, "every option is written (§7.2)"))
    if "skip_ceiling" in table and not _int_in(table["skip_ceiling"], SKIP_CEILINGS):
        out.append(("settings_bad_skip_ceiling", "skip_ceiling", f"{table['skip_ceiling']!r} is not 0-4"))
    if "movement_tier" in table and table["movement_tier"] not in MOVEMENT_TIERS:
        out.append(("settings_bad_movement_tier", "movement_tier",
                    f"{table['movement_tier']!r} is not one of {', '.join(MOVEMENT_TIERS)}"))
    if "dark_fire" in table and not _int_in(table["dark_fire"], (DARK_FIRE,)):
        out.append(("settings_bad_dark_fire", "dark_fire", f"{table['dark_fire']!r}: dark areas always need Fire 1 now; "
                                                           "this seed can't be remade"))
    level = table.get("seed_difficulty", 0)
    if not _int_in(level, SEED_DIFFICULTIES):
        out.append(("settings_bad_seed_difficulty", "seed_difficulty", f"{level!r} is not one of 0, 2, 3, 4"))
    excluded = table.get("exclude_categories", [])
    if not (isinstance(excluded, list) and all(c in CATEGORIES for c in excluded)
            and excluded == sorted(set(excluded), key=CATEGORIES.index)):
        out.append(("settings_bad_exclude_categories", "exclude_categories",
                    f"{excluded!r} is not a list of distinct categories in the order {', '.join(CATEGORIES)}"))
    toggles = table.get("skip_override", {})
    if not isinstance(toggles, Mapping):
        return out + [("settings_bad_override", "skip_override", "not a table")]
    batches = picks(skips)
    for sid, value in toggles.items():
        key = f"skip_override.{sid}"
        variants = batches.get(pick_of(sid, skips), ())
        if not variants:
            out.append(("settings_unknown_skip", key, "the database has no such skip"))
        elif not isinstance(value, bool):
            out.append(("settings_bad_override", key, f"{value!r} is not true or false"))
        elif value and not any(turnable(skips[v]) for v in variants):
            status = [skips[v].get("status") for v in variants]
            why = next((s for s in ("held", "manual") if s in status), "unconfirmed")
            out.append(("settings_enables_held_or_manual_skip", key,
                        f"turns on a {why} skip; a toggle never does (D144, D114)"))
    if level and not out:
        top = top_rating(Settings(table["skip_ceiling"], table["movement_tier"], _folded(toggles, skips)), skips)
        if level > top:
            out.append(("settings_seed_difficulty_above_top", "seed_difficulty",
                        f"{level} asks for {RATING_NAMES[level]} tricks; Movement and Skips allow "
                        f"{RATING_NAMES[top]} at most"))
    return out


def settings_from_table(table: Mapping, skips: Mapping[str, Mapping], where: str = "settings") -> Settings:
    """A valid settings table as :class:`Settings`; raises :class:`SettingsError`."""
    problems = settings_problems(table, skips)
    if problems:
        raise SettingsError(where, problems)
    excluded = set(table.get("exclude_categories", ()))
    if "powers" in excluded and table["format"] == SETTINGS_FORMAT:
        excluded.add("upgrades")      # /1's powers keep the upgrades too
    return Settings(table["skip_ceiling"], table["movement_tier"],
                    _folded(table.get("skip_override", {}), skips), frozenset(excluded),
                    seed_difficulty=table.get("seed_difficulty", 0))


def skips_on(settings: Settings, skips: Mapping[str, Mapping]) -> list[str]:
    """The sorted skip ids ``settings`` turns on: a turnable skip whose pick's
    toggle (its batch's, D275) says true, or that has none and is rated at or
    below the ceiling."""
    return sorted(sid for sid, s in skips.items() if turnable(s) and settings.skip_override.get(
        s.get("batch", sid), s.get("difficulty", len(SKIP_CEILINGS)) <= settings.skip_ceiling) is True)


def picks_on(settings: Settings, skips: Mapping[str, Mapping]) -> dict[str, list[str]]:
    """D275: each pick ``settings`` turns any skip of on -> those skip ids (what a reader is shown)."""
    out: dict[str, list[str]] = {}
    for sid in skips_on(settings, skips):
        out.setdefault(pick_of(sid, skips), []).append(sid)
    return dict(sorted(out.items()))


def top_rating(settings: Settings, skips: Mapping[str, Mapping]) -> int:
    """The highest rating ``settings`` allow: their movement tier's, or that of a skip they turn on (the ceiling's or
    a toggle's, D258)."""
    return max(MOVEMENT_TIERS.index(settings.movement_tier) + 1,
               *(skips[sid].get("difficulty", 0) for sid in skips_on(settings, skips)), 0)


def registry_tag(skip_ids: Iterable[str]) -> bytes:
    """§7.3: the first 4 bytes of the sha256 of the sorted skip ids, each
    followed by LF."""
    return hashlib.sha256("".join(i + "\n" for i in sorted(skip_ids)).encode()).digest()[:4]


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        low, n = n & 0x7F, n >> 7
        out.append(low | (0x80 if n else 0))
        if not n:
            return bytes(out)


def share_encode(settings: Settings, skips: Mapping[str, Mapping] | Iterable[str]) -> str:
    """The share string of valid ``settings`` against the registry of ``skips``
    (id -> table: its picks, D275; or the registry's ids) (§7.3)."""
    return _encode(settings, _registry(skips))


def _encode(settings: Settings, registry: list[str]) -> str:
    toggles = settings.skip_override
    head = settings.skip_ceiling | MOVEMENT_TIERS.index(settings.movement_tier) << 3 | (0x80 if toggles else 0)   # bits 5-6: D1061
    level = settings.seed_difficulty
    form, kept = category_table(settings.exclude_categories)
    mask = sum(1 << CATEGORIES.index(c) for c in (settings.exclude_categories if level else kept))
    sliders = sorted((SHARE_SLIDERS.index((pack, name)), float(v))
                     for pack, values in settings.sliders.items() for name, v in values.items())
    version = SHARE_VERSION_DIFFICULTY if level else SHARE_VERSION_ELEMENTAL if form == SETTINGS_FORMAT_ELEMENTAL \
        else SHARE_VERSION_SLIDERS if sliders else SHARE_VERSION_CATEGORIES if mask else SHARE_VERSION
    out = bytearray([version, head])
    if toggles:
        out += registry_tag(registry) + _varint(len(toggles))
        prev = -1
        for index, value in sorted((registry.index(sid), v) for sid, v in toggles.items()):
            out += _varint((index - prev - 1) << 1 | int(value))
            prev = index
    if version != SHARE_VERSION:
        out.append(mask)
    if sliders or version in (SHARE_VERSION_ELEMENTAL, SHARE_VERSION_DIFFICULTY):
        out.append(len(sliders))
        for index, v in sliders:
            out += bytes([index]) + struct.pack("<d", v)
    if level:
        out.append(SEED_DIFFICULTY_FILL << 3 | level)
    return SHARE_PREFIX + base64.b32encode(bytes(out)).decode().rstrip("=")


def share_sliders(text: str, skips: Mapping[str, Mapping]) -> dict[str, dict[str, float]]:
    """The movement sliders a share string holds (a plan file's, AZ-383):
    none before version 2, else :func:`share_decode`'s (which refuses a bad one)."""
    body = text.strip().upper().removeprefix(SHARE_PREFIX) if isinstance(text, str) else ""
    try:
        version = base64.b32decode(body + "=" * (-len(body) % 8))[:1]
    except ValueError:
        version = b""
    return {p: dict(v) for p, v in share_decode(text, skips).sliders.items()} \
        if version in (bytes([SHARE_VERSION_SLIDERS]), bytes([SHARE_VERSION_ELEMENTAL]),
                       bytes([SHARE_VERSION_DIFFICULTY])) else {}


def share_decode(text: str, skips: Mapping[str, Mapping]) -> Settings:
    """The settings a share string holds, checked as a settings file is.
    Refuses an unknown version, an out-of-range field, a string made for
    another skip registry, trailing bytes and a non-canonical string."""
    def fail(detail: str):
        raise SettingsError("share string", [("share_invalid", "share", detail)])

    registry, ids = _registry(skips), sorted(skips)
    t = text.strip().upper() if isinstance(text, str) else ""
    if not t.startswith(SHARE_PREFIX):
        fail(f"no {SHARE_PREFIX} prefix")
    body = t[len(SHARE_PREFIX):]
    try:
        raw = base64.b32decode(body + "=" * (-len(body) % 8))
    except ValueError as exc:
        fail(f"not base32 ({exc})")
    if len(raw) < 2 or raw[0] not in (SHARE_VERSION, SHARE_VERSION_CATEGORIES, SHARE_VERSION_SLIDERS,
                                      SHARE_VERSION_ELEMENTAL, SHARE_VERSION_DIFFICULTY):
        fail(f"unknown version {raw[0] if raw else None!r}")
    head, k = raw[1], 2
    table = {"format": SETTINGS_FORMAT_ELEMENTAL if raw[0] in (SHARE_VERSION_ELEMENTAL, SHARE_VERSION_DIFFICULTY)
             else SETTINGS_FORMAT,
             "skip_ceiling": head & 7, "movement_tier": MOVEMENT_TIERS[head >> 3 & 3],
             "dark_fire": (head >> 5 & 3) + 1, "skip_override": {}}
    if head & 0x80:
        if raw[k:k + 4] == registry_tag(registry):
            ids = registry
        elif raw[k:k + 4] != registry_tag(ids):    # D275: a string made before its batches names their variants
            fail("made for another skip registry (load the settings file instead)")
        k += 4

        def varint() -> int:
            nonlocal k
            n = shift = 0
            while True:
                if k >= len(raw):
                    fail("truncated")
                byte = raw[k]
                k += 1
                n |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    return n
        count, index = varint(), -1
        if count < 1:
            fail("the toggle flag is set with no toggle")
        for _ in range(count):
            value = varint()
            index += (value >> 1) + 1
            if index >= len(ids):
                fail("a toggle index past the registry")
            table["skip_override"][ids[index]] = bool(value & 1)
    if raw[0] != SHARE_VERSION:
        if k >= len(raw) or raw[k] >> len(CATEGORIES):
            fail("no category mask, or a bit past the categories")
        table["exclude_categories"] = [c for i, c in enumerate(CATEGORIES) if raw[k] >> i & 1]
        k += 1
    sliders: dict[str, dict[str, float]] = {}
    if raw[0] in (SHARE_VERSION_SLIDERS, SHARE_VERSION_ELEMENTAL, SHARE_VERSION_DIFFICULTY):
        count, k = (raw[k], k + 1) if k < len(raw) else (-1, k)
        if count < (raw[0] == SHARE_VERSION_SLIDERS) or k + 9 * count > len(raw):
            fail("no movement slider, or a truncated one")
        for _ in range(count):
            index, (value,) = raw[k], struct.unpack_from("<d", raw, k + 1)
            k += 9
            if index >= len(SHARE_SLIDERS) or not math.isfinite(value):
                fail(f"slider {index}: no such slider, or a value that isn't a number")
            pack, name = SHARE_SLIDERS[index]
            sliders.setdefault(pack, {})[name] = value
    if raw[0] == SHARE_VERSION_DIFFICULTY:
        if k >= len(raw):
            fail("no seed difficulty")
        level, made = raw[k] & 7, raw[k] >> 3
        k += 1
        if made != SEED_DIFFICULTY_FILL:
            fail(f"made with Seed difficulty's fill {made}; this AzurKit plans with fill {SEED_DIFFICULTY_FILL}: "
                 "the same seed would place items differently")
        if level not in SEED_DIFFICULTIES[1:]:
            fail(f"seed difficulty {level} is not one of 2, 3, 4")
        table["seed_difficulty"] = level
    if k != len(raw):
        fail("trailing bytes")
    settings = replace(settings_from_table(table, skips, "share string"), sliders=sliders)
    if _encode(replace(settings, skip_override=table["skip_override"]), ids if head & 0x80 else registry) != t:
        fail("not canonical")
    return settings
