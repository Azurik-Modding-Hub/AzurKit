"""The in-game oracle: xemu sandboxes, their slots and queue, warm build states (dev only).

``oracle`` is the harness (Step 4.14a2): sandboxed copies of the owner's xemu
fork on the oracle's fixtures, their slots (D108), QMP, gdbstub and pad, and
its offline ``selftest``; ``shim_ranges`` what a build's shims write while
the game runs, which its code check leaves out; ``queue`` the sittings'
first-come tickets and the batch token that gives way to them, ``warm`` one
sitting's warm build states. ``sitting`` is the sitting kit (Step 4.14a3):
a slot, a private folder and a teardown that always runs, declarative
specs (``sittings/*.toml``), the exec server and its queue; ``sittings``'s
``model_kit`` the model-swap rows; ``demo`` the owner demos' recorder,
re-plug watcher and body switches. ``chain`` plays a plan's segments
in one sandbox, ``route`` walks the player to a target and ``minigames``
solves the progression minigames (the reach engine's xemu checks, Step
4.13d2). Modkit's kit and this one share these
files' folders, so they keep one D108 budget. No test launches xemu
(D108). Its verbs: :data:`VERBS`.
"""

VERBS: dict[str, str] = {
    "oracle": "the xemu harness: sandboxes on the oracle's fixtures (up, down, jump, loadvm, boot-build, snapshot, "
              "replay, slots, tags, selftest, ...)",
    "sitting": "the sitting kit: run a spec (TOML), serve a sitting, exec a driver in it, queue drivers on N serves, "
               "selftest",
    "demo": "the owner demos: record a trace, replug the owner's pad, add-body, replay a run, fit-cams",
    "chain": "play a plan's segments in one sandbox, each searched in L3 and replayed, park-checked and resumed",
}
