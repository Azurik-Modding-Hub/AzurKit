"""The xemu sittings' grades as data (Step X.85; D838, D853).

``weapon_grades.json`` (``_player_weapons.WEAPON_GRADES``),
``mode_grades.json`` (``_player_character.MODE_GRADES``) and
``variant_grades.json`` (``_player_variants.VARIANT_GRADES``) each hold
a JSON list: its first item says what the file holds, and each other
item, one a line, is a grade: its key's fields, its ``colour`` and its
``why``, each line after the first starting with a comma.  A new grade
is a new line before the closing bracket, so two lanes' new grades
merge by union (``.gitattributes``); the union's copy of a line both
lanes changed is a key held twice, which :func:`load_grades` refuses.
A line one lane deleted comes back with no error when the other lane
adds a line beside it: after a rebase, check that a deleted grade is
still gone."""
from __future__ import annotations

import json
from pathlib import Path


def load_grades(path: Path, key: tuple[str, ...]) -> dict[tuple[str, ...], tuple[str, str]]:
    """``path``'s grades in the file's order, each ``(colour, why)``
    keyed by its ``key`` fields' values; a key held twice fails by name
    (D35)."""
    _about, *rows = json.loads(path.read_text(encoding="utf-8"))
    grades: dict[tuple[str, ...], tuple[str, str]] = {}
    for row in rows:
        graded = tuple(row[field] for field in key)
        if graded in grades:
            raise ValueError(f"{path.name}: {graded} is graded twice: keep one of its lines")
        grades[graded] = row["colour"], row["why"]
    return grades
