"""The in-game oracle: xemu sandboxes, their slots and queue, warm build states (dev only).

``oracle`` is the harness (Step 4.14a2): sandboxed copies of the owner's xemu
fork on the oracle's fixtures, their slots (D108), QMP, gdbstub and pad, and
its offline ``selftest``; ``shim_ranges`` what a build's shims write while
the game runs, which its code check leaves out; ``queue`` the sittings'
first-come tickets and the batch token that gives way to them, ``warm`` one
sitting's warm build states. The sitting kit and the demos come with Step
4.14a3; until then the sittings run Modkit's, and both harnesses share
these files' folders, so they keep one D108 budget. No test launches xemu
(D108). Its verbs: :data:`VERBS`.
"""

VERBS: dict[str, str] = {
    "oracle": "the xemu harness: sandboxes on the oracle's fixtures (up, down, jump, loadvm, boot-build, snapshot, "
              "replay, slots, tags, selftest, ...)",
}
