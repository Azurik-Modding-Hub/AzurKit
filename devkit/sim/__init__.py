"""The simulator: the guest RAM snapshot's file, the player's observation and the pad (dev only).

``snapshot`` is simulator Level 3's file and pad format without its Unicorn
CPU, which the xemu harness writes and reads; ``obs`` the observation L3 and
the harness read alike; ``inputs`` the pad's geometry. The levels themselves
(L0-L3 on Unicorn) and the sim's verbs come with Step 4.13a. Its verbs:
:data:`VERBS` (none yet).
"""

VERBS: dict[str, str] = {}
