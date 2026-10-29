/* qol_memory_budget: the stream pump's start, retried (AZ-687, Step 2.162e).
 *
 * A stream open starts the stream pump (0xB5940) through 0xB5CC0:
 * CreateThread (0x8000-byte stack) at 0xB5CED, the handle stored at
 * [0x1BEFEC] and the pump marked running ([0x1BF544] := 1) whatever
 * CreateThread returned.  With free memory near 0 at a level change (a
 * raised budget, a large body) CreateThread returns NULL: no pump ever
 * fills the stream, every later open only signals the missing pump, and
 * "Loading..." holds for good (Step 2.162c: rows RH5 and FR-cnull).
 *
 *   c_pump_create  replaces the CALL CreateThread at 0xB5CED (stdcall(24),
 *                  RET 0x18): CreateThread with the same arguments until
 *                  it returns a handle, 20 ms (Sleep) between tries, as the
 *                  game waits elsewhere; 0xB5CF2-0xB5CFE then store a real
 *                  handle.  A try that works first is vanilla's call.
 *                  At most TRIES tries (about 5 s), then the NULL goes on
 *                  as vanilla's: the opener holds the stream lock
 *                  [0x1BF540] (0xB5F04-0xB5F85) across this call, so a
 *                  refusal that never clears would otherwise stop every
 *                  other stream open for good, where vanilla can go on
 *                  without a pump (Step 2.162c, row FV-pnull).
 *
 * Both releases: the shim calls its two vanilla functions by name, which
 * Europe's map relocates, and names no address of the image.
 *
 * Ported from Modkit's azurik_mod/patches/qol_memory_budget/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_memory_budget.o beside it.
 */

#include "azurik_vanilla.h"

#define RETRY_MS 20
#define TRIES    250   /* 249 sleeps of 20 ms: about 5 s */

__attribute__((stdcall))
unsigned int c_pump_create(int security, unsigned int stack, int start, int param,
                           unsigned int flags, int id)
{
    unsigned int thread;
    int tries = TRIES;

    while (!(thread = CreateThread(security, stack, start, param, flags, id)) && --tries)
        Sleep(RETRY_MS);
    return thread;
}
