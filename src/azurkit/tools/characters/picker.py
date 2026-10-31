"""The Characters tab's pickers (Step 4.3d; Modkit's Player page, its
``gui/pages/patches.py``, and its gallery picker's pictures): what the tab
shows, decided here once for both hosts (D882), so the page decides
nothing of its own.

- :func:`view`: every usable species in ``critters_engine``'s order in its
  grade's colour (D111; the untested greyed and marked, D877, AZ-807),
  Azurik-Custom-Content's entries as the community group (D913: each
  marked community, its state Install, installed or Update, its variants
  once installed), and the chosen model's info panel, its Weapon box (each
  pick marked by its fit and coloured by the grade its build would read:
  an untested model's picks grey), which options its recipe decides and
  the character recipe a build takes from the tab. With no image read,
  the species are those both releases' images give (:data:`SPECIES`,
  ``species.json``, which ``scripts/record_goldens.py`` records from them),
  graded as with one, and no weapons.
- :func:`preview`: a body drawn from the front and from behind by
  ``draw.py`` (D772, numpy, no Blender), a dressed variant's from its
  dress (:func:`dressed`).
- :func:`match_text`: a G4 button's value as its box shows it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

STATUS_COLOURS = {"green": "#3fae49", "yellow": "#d4a017", "red": "#e5534b", "unseen": "#8a8a8a"}
"""Each grade's colour (Modkit's, D111 refined; unseen grey)."""
GRADE_WORDS = {"green": "Fully playable", "yellow": "Playable, rough edges", "red": "Not playable",
               "unseen": "Not yet tested"}
MODE_TITLES = {"own": "Balanced", "garret4": "Skin only"}
MODE_TIP = "Balanced: its own size and attacks, evened. Skin only: Garret's attacks."
TRACKS = {"scale": (0.25, 3.0, 0.05), "attack_reach": (0.25, 3.0, 0.05), "attack_damage": (0.25, 3.0, 0.05),
          "attack_speed": (0.25, 3.0, 0.05), "jiggle_strength": (0.0, 3.0, 0.05),
          "jiggle_stiffness": (0.25, 4.0, 0.05), "shape": (0.5, 1.4, 0.05)}
"""Each number's track (min, max, step): display hints only, every box taking any finite number (D23), 1 on it (D42)."""
TITLES = {"scale": "Model size", "attack_reach": "Attack reach", "attack_damage": "Attack damage",
          "attack_speed": "Attack speed", "jiggle_strength": "Jiggle strength", "jiggle_stiffness": "Jiggle stiffness"}
MATCH_TIPS = {"scale": "Match garret4's height (2.00 m).", "attack_reach": "Match garret4's reach (2.76 m).",
              "attack_damage": "Match garret4's damage per second.", "attack_speed": "Match garret4's timing."}
OWN_HANDS = "its own attacks are its bare hands"
WEAPON_FITS = {"odd": "odd look", "look + tip hits": "look + tip hits", "look": "look only",
               "same": "the default's build", "refused": "can't build", OWN_HANDS: "its own attacks"}
"""How the Weapon box marks a pick's fit (Modkit's; a good fit unmarked)."""
COMMUNITY = "Community"
PREVIEW = 160
SPECIES = Path(__file__).with_name("species.json")   # [species, body] of each the player can wear (module docstring)
"""A preview's side, px (Modkit's gallery picker's)."""


def match_text(value: float) -> str:
    """A G4 match ``value`` as its box takes it: 4 significant figures
    rounded up, never to nearest, so a match never falls short of garret4
    (Modkit's ``match_text``, Step 2.165b's review)."""
    exact = Decimal(value)
    return f"{float(exact.quantize(Decimal(1).scaleb(exact.adjusted() - 3), rounding=ROUND_CEILING)):.4g}"


def grade(species: str, mode: str, size: str, scale: float = 1.0) -> str:
    """``species``' grade in ``mode`` at ``size`` drawn ``scale`` times it,
    as the picker shows it: red "untested" reads as unseen (grey)."""
    from azurkit.tools.characters._player_character import UNTESTED, mode_status

    found = mode_status(species, mode, size, scale)
    return "unseen" if found == UNTESTED else found[0]


_OFFERS: dict[tuple, dict] = {}   # a body's Weapon box offers by (characters.xbr's digest, species, mode, variant)


def _offers(characters_xbr: bytes, digest: str, body: str | None, mode: str, variant) -> dict[str, tuple[str, str]]:
    """``_player_weapons.offers`` of ``body`` (``{}`` for none it can read), kept for the process."""
    from azurkit.tools.characters._player_weapons import offers
    from azurkit.tools.characters.characters import read_body

    key = (digest, body, mode, getattr(variant, "sha", None))
    if key not in _OFFERS:
        try:
            _OFFERS[key] = offers(characters_xbr, read_body(characters_xbr, body), mode, variant) if body else {}
        except (KeyError, TypeError, ValueError):
            _OFFERS[key] = {}
    return _OFFERS[key]


def _weapons(offers: dict, default: str | None, grade_of) -> list[dict]:
    """The Weapon box's entries (Modkit's ``weapon_entries``): "Default
    (<title>)" first (``name`` ``None``), then every other weapon, its fit
    marked; each pick's colour and tip from ``grade_of(name, fit)``
    (``None``: the theme's)."""
    from azurkit.tools.characters._player_weapons import DEFAULT, OWN, weapons

    found = weapons()

    def title(name: str | None) -> str:
        return "its own attacks" if name in (None, OWN) else found[name].title if name in found else name
    mine = default or next((n for n, (fit, _) in offers.items() if fit == DEFAULT), None)
    out = [{"name": None, "label": f"Default ({title(mine)})" if offers or default else "Default", "colour": None,
            "tip": "The model's own weapon."}]
    for name, (fit, why) in offers.items():
        if name == mine:
            continue
        mark = WEAPON_FITS[OWN_HANDS] if fit == "same" and why.endswith(OWN_HANDS) else WEAPON_FITS.get(fit)
        colour, tip = (None, f"Builds the default: {why}") if fit in (DEFAULT, "same") else grade_of(name, fit)
        out.append({"name": name, "label": title(name) + (f" ({mark})" if mark else ""), "colour": colour,
                    "tip": tip, "fit": fit})
    return out


def _variants_of(root, record: Mapping) -> dict[str, tuple[str, list[str]]]:
    """``{entry id: (its variant.json's recipes' names, ...)}`` of each installed variant entry (``record``:
    the content folder's ``installed.json``)."""
    out = {}
    for name, held in record.items():
        recipe = f"variants/{name}/variant.json"
        if recipe not in held.get("files", {}):
            continue
        try:
            doc = json.loads((root / recipe).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[name] = list(doc) if isinstance(doc, dict) else []
    return out


def _entry_of(name: str, entries: list[dict], held: dict[str, list[str]]) -> dict | None:
    """The community entry that holds the variant ``name``: an installed
    one listing it, else the one whose id begins it (booblord's holds
    booblord_high)."""
    by_id = {e["id"]: e for e in entries}
    for entry, names in held.items():
        if name in names and entry in by_id:
            return by_id[entry]
    starts = [e for e in entries if e["kind"] == "variant" and (name == e["id"] or name.startswith(e["id"] + "_"))]
    return max(starts, key=lambda e: len(e["id"])) if starts else None


def view(config_xbr: bytes | None, characters_xbr: bytes | None, character: Mapping, community: Mapping | None,
         root) -> dict:
    """The Characters tab's view (module docstring) of the image's
    ``config_xbr`` and ``characters_xbr`` (``None`` both: no image read, the
    graded species only and no weapons), the tab's ``character`` (a
    recipe's, :func:`~azurkit.tools.characters.normalize` d), Azurik-Custom-
    Content as ``sdk.content`` gives it (``community``: its ``entries`` with
    their states; ``None``: none read) and the content folder ``root``."""
    from azurkit.tools.characters import _player_character as swap
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import content, jiggle_rt
    from azurkit.tools.characters._player_weapons import DEFAULT, attack_recipe, pick_grade, seen, weapons

    species = character.get("species", swap.PLAYER)
    mode, size = character.get("mode", swap.DEFAULT_MODE), character.get("size", swap.DEFAULT_SIZE)
    scale = character.get("scale", 1.0)
    if config_xbr is not None and characters_xbr is not None:
        listed = [m for m in swap.player_models(config_xbr, characters_xbr, mode, size, scale) if m.status != swap.REFUSED]
        why = ""
    else:
        listed = [swap.PlayerModel(name, body, *swap.mode_status(name, mode, size, scale))
                  for name, body in species_list()]
        why = "Choose your image to build, and to see each model's weapons."
    bodies = {m.species: m.body for m in listed}
    record = content.installed(root)
    entries = (community or {}).get("entries") or content.states(None, record)
    held = _variants_of(root, record)
    built = variants.builtins()
    worn = built.get(species)
    if worn is not None and character.get("shapes"):
        worn = variants.reshaped(worn, character["shapes"])
    unit = worn.scale * scale if worn is not None else scale
    digest = hashlib.sha256(characters_xbr).hexdigest() if characters_xbr is not None else ""
    base = worn.base if worn is not None else species
    wear_mode = worn.mode if worn is not None else mode
    offered = _offers(characters_xbr, digest, bodies.get(base), wear_mode, worn) if characters_xbr else {}
    weapon = character.get("weapon")

    def model_grade(name: str, v=None) -> tuple[str, str]:
        if v is not None:   # Modkit's picker: at its recipe's scale times Model size, its shapes as set
            return variants.status(v, v.scale * scale, shapes=character.get("shapes") if v.name == species else None)
        found = swap.mode_status(name, mode, size, scale)
        return ("unseen", found[1]) if found == swap.UNTESTED else found

    def grade_of(name: str, fit: str) -> tuple[str | None, str]:
        if fit == "refused":
            return STATUS_COLOURS["red"], "Red: can't build"
        own = swap.mode_status(base, mode, size, scale) if worn is None else variants.status(worn, unit)
        graded = pick_grade(species if worn is not None else base, wear_mode, name,
                            seen(size, unit, worn), bodies.get(base), fit, own)
        if graded is None:
            return STATUS_COLOURS["unseen"], "Grey: Not yet tested."
        colour, note = graded
        return STATUS_COLOURS[colour], f"{GRADE_WORDS[colour]}" + ("; not seen in game." if "not seen" in note else ".")
    picks = _weapons(offered, getattr(worn, "weapon", None), grade_of) if characters_xbr else _weapons({}, None, grade_of)
    if weapon is not None and weapon not in {p["name"] for p in picks} and offered:
        weapon = None   # a pick the body doesn't offer: its default
    rows = []
    if worn is not None:
        colour = model_grade(species, worn)[0]
        entry = _entry_of(species, entries, held)
        source = (f"community {entry['id']} v{record.get(entry['id'], {}).get('version', entry.get('version'))}"
                  if entry else "built-in") + f", recipe {worn.sha}"
        rows += [["Variant of", worn.base, None], ["Body", bodies.get(worn.base) or "unknown (no image read)", None],
                 ["Recipe", f"{MODE_TITLES[worn.mode]}, damage x{worn.damage:.2f}, reach x{worn.reach:g}, speed "
                            f"x{worn.speed:g}, balance {'off' if worn.balance is False else 'on'}"
                            + (", hits through walls" if worn.through_walls else ""), None],
                 ["Grade", GRADE_WORDS[colour], STATUS_COLOURS[colour]]]
    else:
        rows.append(["Body", bodies.get(species) or "unknown (no image read)", None])
        for m, title in MODE_TITLES.items():
            colour = grade(species, m, size, scale)
            rows.append([title, GRADE_WORDS[colour], STATUS_COLOURS[colour]])
    pick = next((p for p in picks if p["name"] == weapon and weapon is not None), None)
    if pick is not None and pick.get("fit") not in (DEFAULT, "same"):
        rows.append([f"With {weapons()[weapon].title if weapon in weapons() else weapon}",
                     pick["tip"].split(":")[-1].strip().rstrip(".").split(";")[0], pick["colour"]])
    if worn is not None:
        rows += [["Notes", worn.notes, None], ["Source", source, None]]
    else:
        rows.append(["Graded at", ("garret4's height" if size == "garret4" else "its own size")
                     + (f" x{scale:g}" if scale != 1.0 else ""), None])
    springs = (bool(jiggle_rt.spring_bones(worn.jiggle)) if worn is not None and worn.jiggle is not None
               else bool(bodies.get(base) and variants.chain_springs(bodies[base])))
    armed = attack_recipe(worn, weapon) if worn is not None else None
    defaults = swap.ATTACK_DEFAULTS[wear_mode]
    weighs = (worn is None and species != swap.PLAYER) or (
        species == swap.PLAYER and mode == "own" and weapon in weapons() and weapons()[weapon].prop is None)
    locked = {}
    if worn is not None:   # its recipe decides these (Modkit's _show_model, greyed)
        locked = {"mode": worn.mode, "size": worn.size, "sounds": worn.sounds,
                  "attack_balance": defaults[0] if armed.balance is None else armed.balance,
                  "attack_ground": defaults[1] if armed.ground is None else armed.ground}
    build = {k: v for k, v in character.items() if k not in locked and k != "variant_file"} | {"species": species}
    if weapon is None:
        build.pop("weapon", None)
    if not weighs:
        build.pop("attack_balance", None)
        build.pop("attack_ground", None)
    if not springs:
        build.pop("jiggle_strength", None)
        build.pop("jiggle_stiffness", None)
    for key in ("scale", "attack_reach", "attack_damage", "attack_speed", "jiggle_strength", "jiggle_stiffness"):
        if build.get(key) == 1.0:
            del build[key]
    if build.get("mode") == swap.DEFAULT_MODE:
        del build["mode"]
    if build.get("size") == swap.DEFAULT_SIZE:
        del build["size"]
    if build.get("sounds") == "own":
        del build["sounds"]
    if build.get("anims") == swap.MODE_ANIMS[wear_mode]:
        del build["anims"]
    if not build.get("shapes"):
        build.pop("shapes", None)
    entry = _entry_of(species, entries, held) if worn is not None else None
    refused = None
    if worn is not None and entry is not None and entry["id"] not in record and _needs_files(entry):
        refused = f"Install {entry['title']} (community) first"
    groups = []
    for e in entries:
        if e["kind"] != "variant":
            continue
        names = [n for n in held.get(e["id"], []) if n in built] if e["id"] in record else []
        groups.append(e | {"variants": [{"name": n, "title": built[n].title, "base": built[n].base,
                                         "colour": STATUS_COLOURS[model_grade(n, built[n])[0]]} for n in names]})
    return {
        "modes": [{"id": m, "title": t} for m, t in MODE_TITLES.items()], "mode_tip": MODE_TIP,
        "tracks": TRACKS, "titles": TITLES, "match_tips": MATCH_TIPS, "colours": STATUS_COLOURS, "grade_words": GRADE_WORDS,
        "why": why,
        "species": [{"name": m.species, "body": m.body, "colour": STATUS_COLOURS[grade(m.species, mode, size, scale)],
                     "untested": swap.status(m.species) == swap.UNTESTED,
                     "label": f"{m.species}  (not yet tested)" if swap.status(m.species) == swap.UNTESTED
                     else m.species} for m in listed],
        "community": groups,
        "chosen": {"name": species, "variant": worn is not None, "community": entry["id"] if entry else None,
                   "info": rows, "weapons": picks, "weapon": weapon, "springs": springs,
                   "shapes": [{"name": s.name, "title": s.title} for s in (worn.shapes if worn is not None else ())],
                   "locked": locked, "live": {"anims": worn is None and species != swap.PLAYER,
                                              "attack_balance": weighs, "attack_ground": weighs},
                   "defaults": {"mode": swap.DEFAULT_MODE, "anims": swap.MODE_ANIMS[wear_mode],
                                "attack_balance": defaults[0], "attack_ground": defaults[1]},
                   "refused": refused},
        "character": build,
    }


def species_list() -> list[list[str]]:
    """:data:`SPECIES`' ``[species, body]`` rows."""
    return json.loads(SPECIES.read_text(encoding="utf-8"))


def _needs_files(entry: Mapping) -> bool:
    """Whether a community variant entry carries files beside its recipe (booblord's clips and voice), which a
    build reads from the content folder; beamlord's recipe names none."""
    return any(not f["path"].endswith("/variant.json") for f in entry.get("files", [])) if "files" in entry else True


def body_of(config_xbr: bytes, characters_xbr: bytes, species: str) -> str:
    """The body ``species`` wears as a player model; ``ValueError`` names a species the player can't wear."""
    from azurkit.tools.characters import _player_character as swap

    found = {m.species: m for m in swap.player_models(config_xbr, characters_xbr)}.get(species)
    if found is None or found.status == swap.REFUSED or not found.body:
        raise ValueError(f"{species!r} is no species the player can wear" + (f" ({found.note})" if found else ""))
    return found.body


def preview(characters_xbr: bytes, body: str, size: int = PREVIEW) -> dict[str, bytes]:
    """``characters/<body>`` of ``characters_xbr`` drawn from its front, a
    quarter round and a little above (``draw.PREVIEW_VIEW``), and from
    behind: ``{"front": PNG, "back": PNG}``, ``size`` px each
    (``draw.draw_batched``); the player's recoloured copy (W38's
    ``characters/<body>/v/skin``) where the archive holds one."""
    from azurkit.core.xbr.nodes import named_resources, parse_toc
    from azurkit.tools.characters import draw
    from azurkit.tools.characters.paint import skin_key

    toc, names = parse_toc(characters_xbr), {n.casefold(): i for i, n in named_resources(characters_xbr).items()}
    index = names.get(skin_key(body))
    if index is None:
        index = names.get(f"characters/{body}".casefold())
    if index is None:
        raise ValueError(f"characters.xbr: no body {body!r} to draw")
    parts = draw.body_parts(characters_xbr, toc, index)
    yaw, pitch = draw.PREVIEW_VIEW
    return {view: draw.png_rgba(draw.draw_batched(parts, at, size, pitch), 6)
            for view, at in (("front", yaw), ("back", yaw - 180.0))}


def dressed(staging, species: str) -> dict[str, bytes]:
    """:func:`preview` of the body the player wears in a dress's
    ``staging`` (its config.xbr's ``critters_engine`` row for garret4
    names it), from that staging's characters.xbr."""
    from azurkit.tools.characters._player_character import PLAYER
    from azurkit.tools.characters.ports import XbrDocument

    config = bytes(staging["config.xbr"])
    cell = XbrDocument.from_bytes(config).keyed_section("critters_engine").find_cell(PLAYER, "body")
    body = cell.string_value if cell is not None and cell.type_code == 2 else None
    if not body:
        raise ValueError(f"{species}: the dress names no body for the player")
    return preview(bytes(staging["characters.xbr"]), body)
