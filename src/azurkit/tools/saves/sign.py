"""A slot's ``signature.sav``, and the key it is made with (Modkit's
``save_format.signature`` and ``console_key``, ported).

The game signs a slot with HMAC-SHA1 under ``XboxSignatureKey`` (the USA
code's ``calculate_save_signature`` at 0x5C920 and its tree walk 0x5C4B0;
Europe's 0x50 lower): in each folder its ``.sav`` files but
``signature.sav`` (both matched blind to case), then its folders, each list
sorted by byte order (an inlined ``strcmp``); a file adds its name, a NUL
and its bytes, a folder its name and a NUL and then its own walk. The game
refuses a slot whose signature doesn't match.

The key: when the kernel starts an XBE it sets ``XboxSignatureKey`` to
HMAC-SHA1 keyed with its certificate key over the XBE certificate's
signature key (cert+0xC0), cut to 16 bytes (Modkit Step 2.37: a cold-booted
USA game's key, which signs a real save). The certificate key is the same
in every retail kernel. AzurKit never holds it, only its fingerprint
(:data:`CERT_KEY_SHA256_12`): :func:`cert_key` finds it in the player's own
files, read in memory and never kept: a flash BIOS image with its MCPX 1.0
boot ROM (xemu's pair: the image's second-stage loader, the 0x6000 bytes
below its top 0x200, is RC4 under the 16 bytes at the boot ROM's 0x1A5), or
a file that holds the key as it is (a 16-byte key file, Cxbx-Reloaded's
``keys.bin``)."""

from __future__ import annotations

import hashlib
import hmac
import struct

from azurkit.tools.saves.container import SIGNATURE, Slot

CERT_KEY_SHA256_12 = "0961021c45b7"     # sha256[:12] of the retail kernels' certificate key
_MCPX_KEY = slice(0x1A5, 0x1B5)
_LOADER = slice(-0x6200, -0x200)


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray(len(data))
    i = j = 0
    for n, c in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out[n] = c ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(out)


def _scan(data: bytes, fingerprint: str) -> bytes | None:
    view, sha256 = memoryview(data), hashlib.sha256
    for at in range(len(data) - 15):
        if sha256(view[at:at + 16]).hexdigest()[:12] == fingerprint:
            return bytes(view[at:at + 16])
    return None


def cert_key(data: bytes, mcpx: bytes | None = None, *, fingerprint: str = CERT_KEY_SHA256_12) -> bytes:
    """The kernel's certificate key: in ``data``'s second-stage loader
    decrypted with the boot ROM ``mcpx``, or in ``data`` as it is.
    ``ValueError`` when it is in neither."""
    key = None
    if mcpx is not None and len(mcpx) >= _MCPX_KEY.stop and len(data) >= -_LOADER.start:
        key = _scan(_rc4(mcpx[_MCPX_KEY], data[_LOADER]), fingerprint)
    if key is None:
        key = _scan(data, fingerprint)
    if key is None:
        raise ValueError("it holds no Xbox kernel certificate key" + (
            "" if mcpx is not None else " (a flash BIOS image also needs its MCPX boot ROM)"))
    return key


def title_key(xbe: bytes) -> bytes:
    """The signature key of the XBE's certificate (cert+0xC0)."""
    if len(xbe) < 0x11C or xbe[:4] != b"XBEH":
        raise ValueError("not an XBE (no XBEH header)")
    base, cert = struct.unpack_from("<I", xbe, 0x104)[0], struct.unpack_from("<I", xbe, 0x118)[0]
    at = cert - base + 0xC0
    if not 0 <= at <= len(xbe) - 16:
        raise ValueError("the XBE's certificate is outside its file")
    return bytes(xbe[at:at + 16])


def signature_key(cert: bytes, title: bytes) -> bytes:
    """``XboxSignatureKey`` for a title: HMAC-SHA1(cert, title)[:16]."""
    return hmac.new(cert, title, hashlib.sha1).digest()[:16]


def signature(slot: Slot, key: bytes) -> bytes:
    """The 20-byte ``signature.sav`` the game expects of ``slot`` under ``key``."""
    if len(key) != 16:
        raise ValueError(f"a signature key is 16 bytes, not {len(key)}")
    h = hmac.new(key, digestmod=hashlib.sha1)
    files: dict[str, list[str]] = {}
    folders: dict[str, list[str]] = {}
    for path in slot.files:
        parent, _, name = path.rpartition("/")
        if name.lower().endswith(".sav") and name.lower() != SIGNATURE:
            files.setdefault(parent, []).append(name)
    for path in slot.folders:
        parent, _, name = path.rpartition("/")
        folders.setdefault(parent, []).append(name)

    def walk(folder: str) -> None:
        prefix = folder + "/" if folder else ""
        for name in sorted(files.get(folder, ()), key=str.encode):
            h.update(name.encode() + b"\x00")
            h.update(slot.files[prefix + name])
        for name in sorted(folders.get(folder, ()), key=str.encode):
            h.update(name.encode() + b"\x00")
            walk(prefix + name)

    walk("")
    return h.digest()
