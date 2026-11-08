"""Your own variants (Step 4.6a; Modkit's ``authoring/variant_library``,
D372, D480): one folder each, which the Characters tab's picker lists after
the built-ins and a build wears by name, as it wears a built-in.

:func:`root` is ``AZURKIT_VARIANTS``, else ``variants`` in the user data
folder (beside ``content`` and the images' links: the folder Modkit keeps
them in, so a Modkit user's saved variants open unmoved); the site's worker
(no user data folder) reads ``variants`` in its working folder, or the
:data:`ROOT` a host sets. A folder ``<root>/<name>/`` holds
``recipe.json``, ``{"<name>": {recipe}}`` (``variant_file``'s shape, one
recipe), and the files the recipe names beside it, where the build reads
them. Its other files aren't part of the variant.

The format and its checks are the loader's
(``_player_variants.load_variants``, a built-in's name refused); the
library adds its own rules, each refusal naming the folder
(:func:`listing`): the file holds one recipe, named as its folder; no
species the player can wear (``species.json``) has that name; and it
nests at most :data:`NESTING` deep. The loader already holds every file a
recipe names to its folder (D992's SEC-14), so a recipe you download reads
only its own folder.

The writers check first (:func:`checked`) and write whole or not at all
(D35, D36): :func:`save` (a folder's recipe again), :func:`save_as` (a new
folder), :func:`own_copy` (New from this on a built-in: a new folder of its
whole recipe and files) and :func:`copy_as` (New from this and Save as:
either), :func:`delete`; :func:`new` is New's recipe on a species. The
Variants view's Export packs a folder as a zip (:func:`pack`), its Import
makes a folder of one (:func:`import_`: an Export's zip, or a recipe.json
alone), and the site keeps each folder's :func:`files_of` in its browser
(Step 4.6c).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import jsondepth
from azurkit.tools.characters import _player_variants as variants
from azurkit.tools.characters import mesh_edit

RECIPE = "recipe.json"
ENV = "AZURKIT_VARIANTS"
NESTING = 64
"""A recipe file nests at most this deep (variants.json nests 8), refused past it before it is parsed
(``core.jsondepth``: the parser's own limit is each platform's)."""
ROOT: Path | None = None
"""A host's library folder, which wins over :func:`root`'s (``None``: none set)."""


def root() -> Path:
    """The library's folder: :data:`ROOT`, else ``AZURKIT_VARIANTS``, else
    ``variants`` in the user data folder (``variants`` in the working
    folder where there is none: the site's worker)."""
    if ROOT is not None:
        return ROOT
    if named := os.environ.get(ENV):
        return Path(named)
    try:
        from platformdirs import user_data_path
    except ImportError:
        return Path("variants")
    return user_data_path("AzurKit", appauthor=False) / "variants"


@functools.cache
def species() -> frozenset[str]:
    """The species the player can wear on either release (``species.json``): no variant of yours takes one's name."""
    from azurkit.tools.characters.picker import species_list

    return frozenset(name for name, _, _ in species_list())


@dataclass(frozen=True)
class Entry:
    """A folder of the library: its variant, or why it isn't one."""

    name: str
    folder: Path
    variant: variants.Variant | None
    refusal: str | None


_parsed: dict[Path, tuple[tuple[int, int], tuple[variants.Variant | None, str | None]]] = {}


def named_files(node) -> list[str]:
    """Every file a recipe names (``file``, ``files`` and ``wavs``' lists, at any depth), read beside it."""
    if isinstance(node, list):
        return [f for x in node for f in named_files(x)]
    if not isinstance(node, dict):
        return []
    out = []
    for k, v in node.items():
        if k == "file" and isinstance(v, str):
            out.append(v)
        elif k == "files" and isinstance(v, list):
            out += [f for f in v if isinstance(f, str)]
        elif k == "wavs" and isinstance(v, dict):
            out += [f for fs in v.values() if isinstance(fs, list) for f in fs if isinstance(f, str)]
        else:
            out += named_files(v)
    return out


def checked(text: str, name: str, file: Path) -> variants.Variant:
    """``text`` as the library's ``name`` would hold it in ``file`` (its
    folder's ``recipe.json``), checked as :func:`listing` checks a folder:
    at most :data:`NESTING` deep, the loader's checks, a built-in's name
    refused, then one recipe named as its folder; :class:`ValueError` says
    why not."""
    if jsondepth.deeper(text, NESTING):
        raise ValueError(f"{file}: not a recipe (it nests deeper than {NESTING})")
    try:
        found = variants.load_variants(text, str(file), tuple(variants.builtins()))
    except TypeError as exc:   # the loader's lookup of a list ("mode": [])
        raise ValueError(f"{file}: not a recipe ({type(exc).__name__}: {exc})") from None
    if list(found) != [name]:
        raise ValueError(f"{file}: it holds {', '.join(map(repr, found)) or 'no recipe'}; a library folder holds "
                         f"one recipe, named as the folder ({name!r})")
    return found[name]


def _load(folder: Path) -> tuple[variants.Variant | None, str | None]:
    """``folder``'s variant or refusal, read again only when its
    ``recipe.json`` changes (its modification time or size), so an
    unchanged one stays the same :class:`Variant`."""
    file = folder / RECIPE
    try:
        stat = file.stat()
    except OSError:
        return None, f"{folder}: no {RECIPE}"
    key = (stat.st_mtime_ns, stat.st_size)
    if (cached := _parsed.get(file)) is None or cached[0] != key:
        try:
            found = checked(file.read_text(encoding="utf-8"), folder.name, file), None
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            found = None, str(exc)
        cached = _parsed[file] = (key, found)
    return cached[1]


def _not_species(name: str, taken: Iterable[str] | None) -> str | None:
    if name in (species() if taken is None else set(taken)):
        return f"variant {name!r}: a species has that name, so a character can't name the variant"
    return None


def listing(taken: Iterable[str] | None = None) -> list[Entry]:
    """Every folder of :func:`root` by name (none while it doesn't exist; a
    dot folder, a writer's, left out), each with its variant or its refusal
    (the module docstring); one named as a species (``taken``, else
    :func:`species`) is refused too."""
    try:
        folders = sorted(p for p in root().iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []
    out = []
    for folder in folders:
        variant, why = _load(folder)
        if variant is not None and (clash := _not_species(folder.name, taken)):
            variant, why = None, clash
        out.append(Entry(folder.name, folder, variant, why))
    return out


def find(name: str) -> variants.Variant | None:
    """Your variant ``name`` (``_player_variants.resolve``'s, after the
    built-ins), or ``None``: no folder has the name, or a species does.
    :class:`ValueError` says why a folder of the name isn't one."""
    if not variants._NAME.match(name) or name in species() or not (folder := root() / name).is_dir():
        return None
    found, why = _load(folder)
    if found is None:
        raise ValueError(why)
    return found


def stamp(name: str) -> str | None:
    """The sha256 of what a build of your variant ``name`` reads (its
    ``recipe.json`` and each file it names, by their bytes, a glTF's with
    the buffers it reads beside it), which an
    answer kept for it stands on (its recipe's bytes alone where it builds
    nothing: refused); ``None`` when ``name`` is none of yours."""
    folder = root() / name
    try:
        if name in variants.builtins() or find(name) is None:
            return None
        named = sorted(set(named_files(json.loads((folder / RECIPE).read_text(encoding="utf-8"))[name])))
    except (OSError, ValueError):
        named = []
    try:
        return _stamp(folder / RECIPE, (folder / RECIPE).read_bytes(), named)
    except OSError:
        return None


def _stamp(file: Path, data: bytes, named: Iterable[str]) -> str:
    h = hashlib.sha256(data)
    for f in named:
        h.update(json.dumps([f, _file_sha(file.parent / f)]).encode())
    return h.hexdigest()


def _file_sha(path: Path) -> str | None:
    """A named file's sha256 as a dress reads it: a glTF's as its recipe's pin
    hashes it (``mesh_edit.file_sha256``: its bytes, then each external
    buffer's, which the dress reads beside it), else its bytes; ``None``
    when it can't be read."""
    try:
        if path.suffix.casefold() in (".gltf", ".glb"):
            try:
                return mesh_edit.file_sha256(path)
            except ValueError:   # not a glTF the dress reads: its bytes
                pass
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def file_stamp(file: str | Path, data: bytes | None = None) -> str | None:
    """:func:`stamp`'s for a recipe file (``variant_file``; ``data``: the
    bytes it would hold, read from it where none): the sha256 of its
    recipes but their labels (``variants.LABELS``: no dress reads a title
    or notes), or of its bytes where it holds none, and of each file its
    recipes name beside it, so an answer kept for a recipe file stands on
    what it dresses, never on its path; ``None`` when it can't be read."""
    file = Path(file)
    try:
        data = file.read_bytes() if data is None else data
    except OSError:
        return None
    try:
        doc = json.loads(data)
    except (ValueError, RecursionError):
        doc = None
    if not isinstance(doc, dict) or not all(isinstance(recipe, dict) for recipe in doc.values()):
        return _stamp(file, data, [])
    named = sorted({f for recipe in doc.values() for f in named_files(recipe)})
    dressed = {name: {k: v for k, v in recipe.items() if k not in variants.LABELS} for name, recipe in doc.items()}
    return _stamp(file, json.dumps(dressed, sort_keys=True).encode(), named)


def text_of(name: str, recipe: dict) -> str:
    """The ``recipe.json`` holding ``recipe`` as ``name``: ``variant_file``'s shape, one recipe."""
    return json.dumps({name: recipe}, indent=1) + "\n"


def new(base: str) -> dict:
    """New's recipe on the species ``base``: its body with its own moves (garret4: his own build)."""
    return {"base": base} if base == variants.PLAYER else {"base": base, "mode": "own"}


def opened(name: str) -> dict:
    """The recipe the variant ``name`` opens as: yours as saved; a
    built-in's own where it is ``from`` others, else one ``from`` it with
    its labels (New from this and Save as make an own copy of it,
    :func:`copy_as`). :class:`ValueError` for neither."""
    doc = json.loads(variants.BUILTIN.read_text(encoding="utf-8"))
    if name in doc:
        own = doc[name]
        return dict(own) if "from" in own else {"from": name, **{k: own[k] for k in variants.LABELS if k in own}}
    if find(name) is None:
        raise ValueError(f"variant {name!r}: no built-in and none of yours")
    return json.loads((root() / name / RECIPE).read_text(encoding="utf-8"))[name]


def _checked_new(name: str, recipe: dict, taken: Iterable[str] | None) -> variants.Variant:
    """New variant ``name`` of ``recipe``, once its name is free (no folder, built-in or species has it) and
    :func:`checked` passes."""
    if not isinstance(name, str) or not variants._NAME.match(name):
        raise ValueError(f"{name!r}: a variant's name is a lower-case letter, then lower-case letters, digits and _")
    if (folder := root() / name).exists():
        raise ValueError(f"variant {name!r}: {folder} exists (delete it first, or give another name)")
    found = checked(text_of(name, recipe), name, folder / RECIPE)
    if clash := _not_species(name, taken):
        raise ValueError(clash)
    return found


def save(name: str, recipe: dict, taken: Iterable[str] | None = None) -> Path:
    """``recipe`` written as your variant ``name`` (its folder, which
    :func:`save_as` made) once :func:`checked` passes and no species
    (``taken``, else :func:`species`) has the name: the file replaced whole
    (``os.replace``), nothing written on a refusal (:class:`ValueError`,
    D35). Returns the file."""
    folder = root() / name
    file, text = folder / RECIPE, text_of(name, recipe)
    checked(text, name, file)
    if clash := _not_species(name, taken):
        raise ValueError(clash)
    if not folder.is_dir():
        raise ValueError(f"variant {name!r}: the library has no folder {folder} (Save as makes one)")
    part = folder / f".{RECIPE}.{os.getpid()}.part"
    part.write_text(text, encoding="utf-8")
    os.replace(part, file)
    return file


def save_as(name: str, recipe: dict, files_from: Path | None = None, taken: Iterable[str] | None = None) -> Path:
    """A new folder ``name`` holding ``recipe`` and a copy of each file it
    names from ``files_from`` (the folder it was read beside), once
    :func:`checked` passes and the name is free (a lower-case letter, then
    lower-case letters, digits and ``_``; no folder, built-in or species
    has it): made beside the library's folders under a dot name, then
    renamed, so a failure leaves nothing (D35). Returns its ``recipe.json``."""
    _checked_new(name, recipe, taken)
    folder, named = root() / name, named_files(recipe)
    if missing := [f for f in named if files_from is None or not (Path(files_from) / f).is_file()]:
        raise ValueError(f"variant {name!r}: it names {', '.join(map(repr, missing))}, which "
                         f"{files_from or 'no folder'} doesn't hold")
    root().mkdir(parents=True, exist_ok=True)
    part = Path(tempfile.mkdtemp(prefix=f".{name}.part-", dir=root()))
    try:
        for f in named:
            (part / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(files_from) / f, part / f)
        (part / RECIPE).write_text(text_of(name, recipe), encoding="utf-8")
        part.rename(folder)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return folder / RECIPE


def own_copy(name: str, recipe: dict, files_from: Path | None = None, taken: Iterable[str] | None = None) -> Path:
    """A new folder ``name`` holding ``recipe`` (one ``from`` a built-in)
    as it builds (``_player_variants.recipe_of``: that one's fields under
    its own, no ``from``) and a copy of every file it names, from
    ``files_from`` (its folder, if saved) else the folders its build reads
    them in (its sounds', clips' and fx's: the content folder's and the
    package's), so every field is its own to edit and the built-in's later
    changes no longer reach it; a weapon over its moves left out
    (``_player_variants.own_recipe``) and the built-in's notes with it,
    notes of your own kept. :func:`save_as`'s checks and its whole-or-nothing
    write; a recipe from no built-in, or a file no folder holds, is refused
    by name (D35). Returns its ``recipe.json``."""
    parent = recipe.get("from") if isinstance(recipe, dict) else None
    if not isinstance(parent, str) or parent not in variants.builtins():
        raise ValueError(f"variant {name!r}: an own copy is of a recipe from a built-in (this one is from "
                         f"{parent!r})" if parent is not None else f"variant {name!r}: an own copy is of a recipe "
                         "from a built-in (this one is from none: Save as copies it)")
    variant = _checked_new(name, recipe, taken)
    laid = variants.own_recipe(variants.recipe_of({name: recipe}, name, str(root() / name / RECIPE))[0])
    if recipe.get("notes") not in (None, variants.builtins()[parent].notes):   # your own notes stay
        laid = {**laid, "notes": recipe["notes"]}
    folders = [*([Path(files_from)] if files_from is not None else []), variants.sound_folder(variant),
               variants.clip_folder(variant), variants.fx_folder(variant)]
    root().mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{name}.own-", dir=root()))
    try:
        for f in named_files(laid):
            found = next((d / f for d in folders if (d / f).is_file()), None)
            if found is None:
                raise ValueError(f"variant {name!r}: it names {f!r}, which none of {', '.join(map(str, folders))} "
                                 "holds")
            (staged / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, staged / f)
        return save_as(name, laid, staged, taken)
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def copy_as(name: str, recipe: dict, files_from: Path | None = None, taken: Iterable[str] | None = None) -> Path:
    """New from this and Save as: a new folder ``name`` of the open
    ``recipe`` (``files_from``: its folder, if saved), :func:`own_copy` for
    one from a built-in (so every field of the copy is its own), else
    :func:`save_as`."""
    parent = recipe.get("from") if isinstance(recipe, dict) else None
    if isinstance(parent, str) and parent in variants.builtins():
        return own_copy(name, recipe, files_from, taken)
    return save_as(name, recipe, files_from, taken)


def delete(name: str) -> None:
    """Your folder ``name`` (a :func:`listing` entry, refused or not) and everything in it, removed."""
    folder = root() / name
    if not name or name.startswith(".") or Path(name).name != name or not folder.is_dir():
        raise ValueError(f"variant {name!r}: the library ({root()}) has no such folder")
    shutil.rmtree(folder)


def unshareable(folder: Path) -> list[str]:
    """The files ``folder``'s recipe names that aren't yours to share
    (D372, D393): every one but a WAV. A glTF or glb holds a body's mesh,
    or keys on its bones; a PNG is a game texture made over."""
    recipe = json.loads((folder / RECIPE).read_text(encoding="utf-8"))[folder.name]
    return sorted({f for f in named_files(recipe) if not f.casefold().endswith(".wav")})


MOST = 256 * 1024 * 1024
"""The most bytes an import's files hold unpacked (the community content's cap on one entry)."""


def files_of(name: str) -> dict[str, bytes]:
    """Your folder ``name`` as the variant it is: its ``recipe.json`` and each
    file its recipe names, by path inside it (what an Export packs and the
    site keeps in the browser); a file it names that isn't there is left
    out (the listing names the refusal)."""
    folder = root() / name
    if not variants._NAME.match(name) or not (folder / RECIPE).is_file():
        raise ValueError(f"variant {name!r}: the library ({root()}) has no such folder")
    out = {RECIPE: (folder / RECIPE).read_bytes()}
    try:
        recipe = json.loads(out[RECIPE])[name]
    except (ValueError, KeyError, TypeError, RecursionError):
        return out
    for f in sorted(set(named_files(recipe))):
        if _inside(f) and (folder / f).is_file():
            out[f] = (folder / f).read_bytes()
    return out


def _inside(path: object) -> bool:
    """``path`` names a file inside a variant's folder: relative, POSIX, no ``..``, no empty or dot part."""
    return isinstance(path, str) and bool(path) and "\\" not in path and ":" not in path and \
        not path.startswith("/") and all(part not in ("", ".", "..") for part in path.split("/"))


def pack(name: str) -> tuple[bytes, list[str]]:
    """Export: your variant ``name`` as a zip, ``<name>/recipe.json`` and
    each file it names beside it (:func:`files_of`), and the files of it
    that aren't yours to share (:func:`unshareable`), which the zip holds
    all the same: it is yours to keep, the sharing is your call."""
    import io
    import zipfile

    files = files_of(name)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr(zipfile.ZipInfo(f"{name}/{path}", (2026, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
    try:
        held = unshareable(root() / name)
    except (OSError, ValueError, KeyError, TypeError):
        held = []
    return out.getvalue(), held


def unpacked(data: bytes) -> tuple[str, dict, dict[str, bytes]]:
    """An import's file read: a zip holding one variant (``recipe.json``
    and its files, at its top or in one folder: an Export's) or a
    ``recipe.json`` alone. Its name (the recipe's), its recipe and its
    files by path beside the recipe; :class:`ValueError` names what isn't
    one (two recipes, a path outside its folder, more than :data:`MOST`
    bytes unpacked, a member zipfile can't read, no recipe)."""
    import io
    import zipfile
    import zlib

    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("import: a zip or a recipe.json's bytes")
    if data[:2] != b"PK":
        text, files = bytes(data), {}
    else:
        try:
            z = zipfile.ZipFile(io.BytesIO(bytes(data)))
            infos = [i for i in z.infolist() if not i.is_dir()]
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            raise ValueError(f"import: not a zip ({exc})") from None
        recipes = [i.filename for i in infos if i.filename.rsplit("/", 1)[-1] == RECIPE]
        if len(recipes) != 1:
            raise ValueError(f"import: the zip holds {len(recipes) or 'no'} {RECIPE} files; a variant's holds one")
        top = recipes[0][:-len(RECIPE)]
        if sum(i.file_size for i in infos) > MOST:
            raise ValueError(f"import: the zip unpacks past {MOST:,} B")
        files = {}
        for info in infos:
            if not info.filename.startswith(top) or not _inside(path := info.filename[len(top):]):
                raise ValueError(f"import: {info.filename!r} is outside the variant's folder")
            try:   # a member zipfile can't read (a bad CRC, a broken stream, an encrypted one or another method)
                with z.open(info) as f:
                    files[path] = f.read(MOST + 1)
            except (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, EOFError) as exc:
                raise ValueError(f"import: {info.filename!r} can't be read ({exc})") from None
        text = files.pop(RECIPE)
    if jsondepth.deeper(text.decode("utf-8", "replace"), NESTING):
        raise ValueError(f"import: not a recipe (it nests deeper than {NESTING})")
    try:
        doc = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"import: {RECIPE} is not JSON ({exc})") from None
    if not isinstance(doc, dict) or len(doc) != 1 or not isinstance(next(iter(doc.values())), dict):
        raise ValueError(f"import: {RECIPE} holds one recipe, {{\"<name>\": {{recipe}}}}")
    (name, recipe), = doc.items()
    return name, recipe, files


def import_(data: bytes, taken: Iterable[str] | None = None) -> str:
    """Import: the variant in ``data`` (:func:`unpacked`) as a new folder of
    the library, with the files its recipe names (its other files left
    out), once :func:`save_as`'s checks pass: its name free, the loader
    taking it, each file it names in the import (D35). Its name."""
    name, recipe, files = unpacked(data)
    _checked_new(name, recipe, taken)
    root().mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{name}.import-", dir=root()))
    try:
        for f in named_files(recipe):
            if f in files:
                (staged / f).parent.mkdir(parents=True, exist_ok=True)
                (staged / f).write_bytes(files[f])
        save_as(name, recipe, staged, taken)
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    return name
