"""The simulator: the game's own code under Unicorn, from a build's structure to its movement in a running game
(dev only).

Level 0 (:mod:`.static`) checks a build's structure in pure Python; Level 1 (:mod:`.l1`) checks that its patched
code is well-formed; Level 2 (:mod:`.l2`) runs the game's own code on a named fake state; Level 3 (:mod:`.l3`)
runs the game's own player update or simulation step from a guest RAM snapshot of a running game
(:mod:`.snapshot`: the file, its private store and the pad, which the xemu harness writes and reads), with
teleports, per-tick pad and camera input and resets. :mod:`.l3_search` searches an input string to a goal over
it, :mod:`.l3_explore` explores a level's tricks with :mod:`.l3_options` (and :mod:`.tricks_detect` names the
tricks a trace used), :mod:`.douse` casts and walks a douse leg, :mod:`.faces` finds the face a contact touched,
:mod:`.obs` is the one observation reader L3 and the xemu replayer share, :mod:`.corpus` keeps every replay's
verdict to re-run offline, :mod:`.overlay` lays a modded build over a vanilla snapshot, :mod:`.envelope` flies
the movement envelope's flights under L2 and :mod:`.inputs` is the pad's geometry. :mod:`.ports` points the
imports Modkit's modules had at AzurKit's engine (Step 4.13a), and ``data/`` holds the blind spots L2 can't
judge and the kernel's exports. The RAM recipes and the page walk are the randomizer's
(:mod:`azurkit.tools.randomizer.live`); the many-at-once pool and FastL3 are the reach engine's. docs/SIMULATOR.md
has the API and the xemu validation. Its verbs: :data:`VERBS`.

L1-L3 run the USA release's code only (D146): Europe's per-tick code is the same, but their VAs, stubs and blind
spots are USA's, so each refuses a Europe XBE by name (:func:`require_usa`).
"""

VERBS: dict[str, str] = {
    "l3-hold": "the L3 store's snapshots no cleanup deletes; --check PATH ... exits 1 naming each held one",
}


def require_usa(xbe: bytes) -> None:
    """Raise ``ValueError`` naming ``xbe``'s release unless it is USA's
    (by its kernel-thunk address; a stand-in XBE counts as USA)."""
    from azurkit.core import facts, gate
    from azurkit.tools.randomizer.ports import xbe_layout
    if (region := xbe_layout(xbe)) is not facts.of(gate.USA):
        raise ValueError(f"the simulator runs the USA release only; this XBE is the "
                         f"{region.release.label} release (D146)")
