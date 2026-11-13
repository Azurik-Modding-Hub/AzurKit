"""The Tools tab's Saves (D919's save editor; Step 4.7e's hub half): the one
ask each host answers, ``ask({"do": ...})``, over the slots this process has
open (:data:`SLOTS`, in memory until the next open; nothing is kept).

    open   {folder} | {image} | {id, files, folders}   the slot(s) as a host shows them
    edit   {id, edits}                                  text saves' lines changed, all or none
    sign   {id, iso, flash[, mcpx]}                     its signature made again with the player's own BIOS files
    save   {id, out}                                    a new folder (the app's, the CLI's), never in its own
    zip    {id}                                         a zip's bytes (the site's)

The BIOS files and the key derived from them live for one call, in memory:
never kept, never sent back, and a file too large to be one is refused before
it is scanned. Files a host's folder holds that the game never wrote (macOS's
``.DS_Store`` and ``._x`` AppleDouble files) are left out of a folder's slot,
so they are neither hashed nor saved."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit.tools import saves
from azurkit.tools.saves.container import Slot

SLOTS: dict[str, Slot] = {}
FOLDERS: dict[str, Path] = {}   # the folder each open slot was read from, which a save never writes into (D36)
MAX_BIOS = 16 << 20    # a flash image's or MCPX ROM's most bytes (a scan with no MCPX is slower: MAX_SCAN)
MAX_SCAN = 4 << 20     # the most a flash image with no boot ROM is scanned (cert_key's whole-file walk, 0.4 s a MiB)


def view(slot: Slot) -> dict:
    """``slot`` as a host shows it: its id, each file decoded and its folders' count."""
    return {"id": slot.id, "files": saves.decode(slot), "folders": len(slot.folders)}


def _kept(slot: Slot) -> Slot:
    """``slot`` less the host's own files in a folder (the module's docstring)."""
    def host(path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        return name == ".DS_Store" or name.startswith("._")
    return Slot(slot.id, {path: data for path, data in slot.files.items() if not host(path)}, slot.folders)


def _opened(given: Mapping) -> list[Slot]:
    if "folder" in given:
        return [_kept(Slot.read(given["folder"]))]
    if "image" in given:
        return saves.slots(given["image"])
    if not isinstance(given.get("id"), str) or not isinstance(given.get("files"), Mapping):
        raise ValueError("saves: open a folder, an image or {id, files}")
    return [_kept(Slot(given["id"], given["files"], frozenset(given.get("folders", ()))))]


def _slot(given: Mapping) -> Slot:
    try:
        return SLOTS[given.get("id")]
    except (KeyError, TypeError):
        raise ValueError(f"saves: no slot {given.get('id')!r} is open: open it again") from None


def _signed(given: Mapping, xbe: Callable[[str], bytes]) -> dict:
    slot = _slot(given)
    flash, mcpx = given.get("flash"), given.get("mcpx")
    if not isinstance(flash, (bytes, bytearray)):
        raise ValueError("saves: signing needs your flash image (and its MCPX boot ROM)")
    if len(flash) > MAX_BIOS or (mcpx is not None and len(mcpx) > MAX_BIOS) or (mcpx is None and len(flash) > MAX_SCAN):
        raise ValueError(f"saves: that is no BIOS file: {len(flash):,} B, past the "
                         f"{MAX_BIOS if mcpx is not None else MAX_SCAN:,} B AzurKit reads as one")
    key = saves.key(bytes(flash), None if mcpx is None else bytes(mcpx), xbe(given["iso"]))
    was = saves.signed(slot, key)
    SLOTS[slot.id] = done = saves.resign(slot, key)
    return {"slot": view(done), "was": was, "signed": True}


def ask(given: object, xbe: Callable[[str], bytes]) -> dict:
    """The module's asks; ``xbe(path)`` is the image's ``default.xbe``. Every
    refusal is a ``ValueError`` or ``OSError`` naming what and why."""
    if not isinstance(given, Mapping) or (do := given.get("do")) not in ("open", "edit", "sign", "save", "zip"):
        raise ValueError("saves: do is open, edit, sign, save or zip")
    if do == "open":
        slots = _opened(given)
        SLOTS.clear()
        SLOTS.update({slot.id: slot for slot in slots})
        FOLDERS.clear()
        FOLDERS.update({slot.id: Path(given["folder"]).resolve() for slot in slots if "folder" in given})
        return {"slots": [view(slot) for slot in slots]}
    if do == "edit":
        slot, changes = saves.edit(_slot(given), given.get("edits") or [])
        SLOTS[slot.id] = slot
        return {"slot": view(slot), "changes": changes}
    if do == "sign":
        return _signed(given, xbe)
    if do == "save":
        slot, out = _slot(given), Path(given["out"])
        if (folder := FOLDERS.get(slot.id)) and _inside(out, folder):
            raise ValueError(f"saves: {out} is inside {folder}, the slot's own folder, which a save never writes into")
        return {"out": str(slot.write(out))}
    slot = _slot(given)
    return {"name": f"{slot.id}.zip", "data": slot.zip()}


def _inside(out: Path, folder: Path) -> bool:
    """Whether ``out`` is ``folder`` (resolved) or inside it: by its path,
    then by file identity (as ``core.gate``'s outputs), so on a disk that
    folds case (macOS's) the folder named in another case is it too."""
    real = out.resolve()
    return real.is_relative_to(folder) or folder.exists() and any(
        d.exists() and os.path.samefile(d, folder) for d in (real, *real.parents))
