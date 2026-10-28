/* qol_skip_logo's shim: the boot's call of the movie player for the
 * Adrenium logo (0x5F6E5) calls this instead.
 *
 * The movie player is stdcall with two arguments, which the boot pushed
 * before the call, and returns AL = 1 when a movie started. This returns
 * as the player does when none did: AL cleared and the two arguments
 * popped, so the boot goes straight on to the prophecy movie.
 *
 * It is naked (no prologue), so its code is exactly those two
 * instructions, written below in GNU assembler syntax.
 *
 * Ported from Modkit's azurik_mod/patches/qol_skip_logo/shim.c; shimkit
 * builds it into qol_skip_logo.o beside it.
 */

__attribute__((naked))
void c_skip_logo(void)
{
    __asm__ volatile (
        "xorb %%al, %%al  \n\t"
        "ret  $8          \n\t"
        : /* no outputs */
        : /* no inputs  */
        : "memory"
    );
}
