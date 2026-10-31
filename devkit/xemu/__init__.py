"""The in-game oracle: xemu sandboxes, their slots and queue, warm build states (dev only).

``queue`` holds the sittings' first-come tickets and the batch token that
gives way to them, ``warm`` one sitting's warm build states. The harness
that runs the sandboxes and its verbs come with Step 4.14a2; until then the
sittings run Modkit's, and both share these files' folders, so they keep
one D108 budget. No test launches xemu (D108). Its verbs: :data:`VERBS`
(none yet).
"""

VERBS: dict[str, str] = {}
