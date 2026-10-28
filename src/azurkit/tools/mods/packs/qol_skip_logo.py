"""qol_skip_logo: the boot skips the Adrenium logo movie; the prophecy movie,
which has the story's opening, still plays. Off by default.

The boot's state machine (0x5F620) plays two movies before the title. For
the first it pushes two arguments (a zero and the movie's name) and calls
the movie player (stdcall, it pops them; AL is 1 when a movie started) at
0x5F6E5. The state it goes to next depends on AL: 1 waits for the movie
to end, 0 goes on to the prophecy movie. The pack hooks that call with a
call into its shim (``shims/qol_skip_logo.c``), which clears AL and pops the
two arguments, as the player returns when no movie plays. Clearing AL is
what matters: with the call simply removed, the machine waited for a movie
that never started (a black screen).

5 bytes at the site and 5 of shim, which land where the carve allocator
puts them: in ``.text``'s gap before BINK on USA, in an appended section on
Europe, which has none. Ported from Modkit's
``azurik_mod/patches/qol_skip_logo`` at the packs oracle's tag
(oracle-packs-2); its legacy byte patch (``AZURIK_NO_SHIMS``) isn't ported:
the shim ships prebuilt, so every host can apply it.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, TrampolinePatch

PACK = Pack(
    name="qol_skip_logo",
    description="Skips the unskippable Adrenium logo at boot (the prophecy intro still plays).",
    sites=(TrampolinePatch(label="the logo movie's call", va=0x0005F6E5, shim="qol_skip_logo",
                           symbol="_c_skip_logo"),),
)
