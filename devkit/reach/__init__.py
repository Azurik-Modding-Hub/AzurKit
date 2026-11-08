"""The reach engine: which floors the player reaches from which, by running the game's own player tick from every
floor's boundary (dev only).

Modkit's at its freeze (Step 4.13d1): :mod:`.engine` is the engine (its nodes, launches, runner, cache, graph,
verdicts, aims, pair stage and rigs), :mod:`.native` its native movement and collision kernel (``kernel.c`` and
``controllers.c``, built by zig into the user cache) and the kernel's launch backend, :mod:`.l3_fast` FastL3 (L3 on
the patched Unicorn ``unicorn/`` builds, its C step ``fastl3_step.c``) and :mod:`.l3_pool` the many-at-once L3 pool.
:mod:`.models` reads the reach models the L3 store keeps.  The frozen truth set is read from ``reach-truth/`` in the
user data folder.  Its verbs: :data:`VERBS`; ``devkit/reach/README.md`` has them and ``docs/REACH.md`` the engine.

Beside the standard library it imports the randomizer's art, first: the shipped draft's geometry and the art import
each other, so a module here that reads the geometry first (a verb, a pool's worker) would meet the art half-made.
"""

import azurkit.tools.randomizer.art  # noqa: F401

VERBS: dict[str, str] = {
    "reach-engine": "sample, run, graph, diff and witness a level's reach on L3 (the kernel route by --backend kernel)",
    "reach-truth": "the truth set: its frame, R's reference search, recall against a graph and the calibrations",
    "rig-triggers": "the triggers that move each level's rigs: a census of the wiring, or each rig's start witnessed",
    "native-trace": "trace launches on FastL3 with the move code's internals, for native-check",
    "native-check": "the native kernel against a native-trace file: its moves, launches and speed",
    "native-census": "the platforms a snapshot's collision world doesn't hold, which the kernel leaves out",
    "build-unicorn": "build FastL3's patched libunicorn and its x87 check flavour into the user cache",
}
