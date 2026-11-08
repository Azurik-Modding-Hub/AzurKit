"""The data a build's shims write while the game runs, which the xemu harness's code check leaves out (Step
4.14a2; AZ-300, AZ-817).

``oracle.Sandbox.code_identity`` compares the guest's ``.text`` and ``SHIMS`` with the build's ``default.xbe``, so
the guest must run the build under test. A running build's shims rewrite their landed ``.data`` and ``.bss``: the
player-model shims' (X3's damage marker every tick, AZ-300) and the copy gate's (qol_alloc_race, on in every
default build: its state from main's first frame, AZ-817). Each range is read from the build: the hook's CALL or
JMP, the landed ``.text`` matched against its shim's object, and the ``.text`` relocations that place its writable
sections (``ports.trampoline_shim_data``), never a fixed address. A hook's vanilla bytes come from its release's
own image (``gate.find``), each file read checked against the release's manifest (D27).
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from pathlib import Path

from azurkit.core import facts, gate
from azurkit.tools.characters import ports
from azurkit.tools.mods import engine
from azurkit.tools.mods.packs import qol_alloc_race


def _copy_gate() -> ports.TrampolinePatch:
    """qol_alloc_race's door (vanilla's dead evict-all, jumped to the copy gate), whose landing holds the gate's
    state (the tick's and the park's landings reach it through the door and write none of their own)."""
    hook = next(s for s in qol_alloc_race.sites(lambda va, size: bytes(size))
                if isinstance(s, engine.TrampolinePatch) and s.va == qol_alloc_race.DOOR)
    return ports.TrampolinePatch(
        name="copy_gate", label=hook.label, va=hook.va, replaced_bytes=bytes(facts.of(gate.USA).site(hook.va).size),
        shim_object=Path(engine.__file__).with_name("shims") / f"{hook.shim}.o", shim_symbol=hook.symbol,
        mode=hook.mode)


COPY_GATE = _copy_gate()


@functools.cache
def _vanilla(release: gate.Release) -> ports.Vanilla:
    if (path := gate.find(release)) is None:
        raise ValueError(f"no {release.label} image to read the hooks' vanilla bytes from: {gate.missing(release)}")
    return ports.Vanilla(release, path)


@contextlib.contextmanager
def building(xbe: bytes) -> Iterator[None]:
    """The port's build context for ``xbe``: its release's vanilla files (:func:`_vanilla`); ``ValueError`` names
    a missing image."""
    with ports.building(ports.Build(_vanilla(facts.xbe_layout(xbe).release))):
        yield


def copy_gate(xbe: bytes) -> list[tuple[int, int]]:
    """The ``[start, end)`` VAs the copy gate writes in ``xbe``'s ``SHIMS`` while the game runs: its door
    landing's ``.bss`` (g_main from main's first frame on, the park, ask and lock words); ``[]`` without the
    gate. ``ValueError`` when the code at the door isn't the gate's."""
    with building(xbe):
        return ports.trampoline_shim_data(xbe, COPY_GATE)


def player_model(xbe: bytes) -> list[tuple[int, int]]:
    """The ``[start, end)`` VAs the player-model shims in ``xbe`` write while the game runs
    (``_player_character.shim_data``); ``[]`` for a build with none."""
    from azurkit.tools.characters import _player_character   # the swap's 11k lines: only a build check loads them

    with building(xbe):
        return _player_character.shim_data(xbe)
