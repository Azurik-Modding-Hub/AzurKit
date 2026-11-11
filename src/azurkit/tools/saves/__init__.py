"""Azurik's saves (D919's save editor): open a slot, see what its files
hold, change a text save's line, sign it again with the player's own
console key and save it as a new folder or a zip.

    Slot(id, files)             a slot in memory (container.py): Slot.read(folder), slot.write(out), slot.zip()
    slots(image)                the slots on an xemu HDD image, read-only (fatx.py)
    decode(slot)                what each file holds, by path
    edit(slot, edits)           the slot with text saves' lines changed, and what each held: all or none (D35)
    key(flash, mcpx, xbe)       the console's signature key for the game, in memory only (sign.py)
    resign(slot, key)           the slot with its signature.sav made again
    signed(slot, key)           whether its signature.sav is the one the game expects

The player's BIOS files and the key derived from them stay in memory and are
never kept or sent; AzurKit holds only the certificate key's fingerprint."""

from __future__ import annotations

import dataclasses
import hmac
from collections.abc import Iterable, Mapping

from azurkit.tools.saves.container import SIGNATURE, TITLE, Meta, Slot, Text, check_name, check_path, is_text
from azurkit.tools.saves.fatx import slots
from azurkit.tools.saves.sign import CERT_KEY_SHA256_12, cert_key, signature, signature_key, title_key
from azurkit.tools.saves import container as _container

__all__ = ["CERT_KEY_SHA256_12", "SIGNATURE", "TITLE", "Meta", "Slot", "Text", "cert_key", "check_name", "check_path",
           "decode", "edit", "is_text", "key", "resign", "signature", "signature_key", "signed", "slots", "title_key"]


def decode(slot: Slot) -> list[dict]:
    """What each of ``slot``'s files holds (``container.decode``), in path order."""
    return [_container.decode(path, data) for path, data in slot.files.items()]


def edit(slot: Slot, edits: Iterable[Mapping]) -> tuple[Slot, list[dict]]:
    """``slot`` with each edit (``{"file", "line", "value"}``: a text save's
    path, its line's index after the ``fileversion`` line, the new text)
    made, and ``{file, line, old, new}`` per edit. ``ValueError`` names every
    edit that can't be made (a file the slot hasn't or no text save, a line
    past its last, a value with a line break, a NUL or a character latin-1
    can't hold, a file the edits leave reading as other lines or no text
    save: a headerless one holds printable ASCII alone) before any is made.
    Its signature.sav is the old one:
    :func:`resign` it."""
    texts: dict[str, Text] = {}
    bad, done = [], []
    for item in edits:
        try:
            path, line, value = item["file"], item["line"], item["value"]
        except (KeyError, TypeError):
            bad.append(f"{item!r}: an edit is {{file, line, value}}")
            continue
        where = f"{path}[{line}]" if isinstance(path, str) else repr(path)
        if not isinstance(path, str) or path not in slot.files:
            bad.append(f"{where}: no such file in the save")
            continue
        if path not in texts:
            if not is_text(slot.files[path]):
                bad.append(f"{where}: not a text save")
                continue
            texts[path] = Text.from_bytes(slot.files[path])
        text = texts[path]
        if type(line) is not int or not 0 <= line < len(text.lines):
            bad.append(f"{where}: no such line (it has {len(text.lines)})")
        elif not isinstance(value, str) or any(c in value for c in "\r\n\x00") or any(ord(c) > 0xFF for c in value):
            bad.append(f"{where}: {value!r} isn't one line of latin-1 text")
        else:
            done.append({"file": path, "line": line, "old": text.lines[line], "new": value})
            text.lines[line] = value
    for path, text in texts.items():   # a headerless one (options.sav) stays text only in printable ASCII
        made = text.to_bytes()
        back = Text.from_bytes(made) if is_text(made) else None
        if back is None or (back.version, back.lines) != (text.version, text.lines):
            bad.append(f"{path}: the edits wouldn't read back as its lines (a save with no fileversion line holds "
                       "printable ASCII alone)")
    if bad:
        raise ValueError("can't make the edits: " + "; ".join(bad))
    files = dict(slot.files) | {path: text.to_bytes() for path, text in texts.items()}
    return dataclasses.replace(slot, files=files), done


def key(flash: bytes, mcpx: bytes | None, xbe: bytes) -> bytes:
    """The ``XboxSignatureKey`` a console gives the game: its kernel's
    certificate key (from the flash image and its boot ROM, or a key file)
    over the game XBE's signature key."""
    return signature_key(cert_key(flash, mcpx), title_key(xbe))


def _signature_path(slot: Slot) -> str:
    return next((path for path in slot.files if path.lower() == SIGNATURE), SIGNATURE)


def resign(slot: Slot, key: bytes) -> Slot:
    """``slot`` with the ``signature.sav`` the game expects under ``key``."""
    return dataclasses.replace(slot, files=dict(slot.files) | {_signature_path(slot): signature(slot, key)})


def signed(slot: Slot, key: bytes) -> bool:
    """Whether ``slot``'s ``signature.sav`` is the one the game expects under ``key``."""
    return hmac.compare_digest(slot.files.get(_signature_path(slot), b""), signature(slot, key))
