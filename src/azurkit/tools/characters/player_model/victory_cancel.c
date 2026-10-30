/* X46: a recipe's victory ends when the player pushes the stick, after
 * its minimum (Step 2.181, D702; the owner: "for her victory animation,
 * can we make it break early if the player wants to move?").
 *
 * Why.  A victory (0x887D0, from the ground state: a key, a fragment, a
 * power, an obsidian or a guardian's death posts it) plays slot 74+v in
 * state 0x100, and the state machine 0x8CCC0 drops the 0x100 bit only
 * when the active layer's end flag is set (0x8CF56-0x8CF8C), so the
 * player stands through the whole clip: booblord's victory holds
 * 0x100 121 ticks (4.0 s).  The stick is read meanwhile (input +0x1C
 * 1.0 from the push on) and ignored (sitting 2.181, a real key pickup:
 * the request is cleared on the move's first tick, the key counted at
 * the touch before it, the camera's yaw unchanged, nothing else waits).
 *
 * What.  This shim replaces the 6 bytes at 0x8CF84 (Europe 0x8CF34),
 * `test eax, ecx; jne 0x8CF8C; test al, 1`, with a CALL and a NOP, so
 * the game's `jne 0x8CFA0` at 0x8CF8A reads its ZF: set, the move ends
 * there as at its clip's end (0x8CF8C clears 0x100 and the ground state
 * runs this tick, walk_state taking the stick).  It ends the move where
 * the game would (the layer's end flags, EAX & ECX, or its playing bit
 * 0 clear) and also when the move is a victory (critter +0x200, the slot
 * playing, 75-80), its own clock (critter +0x1E4 - +0x1E0: 0x887D0 sets
 * both to the clip's length and only +0x1E0 runs down; not PlayerControl
 * +0x9C, which keeps an attack's time when the victory starts on the
 * tick the attack ends, 0x8C3CC) has reached
 * player_model_victory_cancel_after (the recipe's victory_cancel, s)
 * and the stick (input +0x1C, 0 inside the
 * game's own dead zone) is past STICK_MIN with the control the player's
 * (input +0x30 clear: no scripted move or cutscene holds it).  Then it
 * also ends the victory's hit timer (critter +0x1E0 := 0: its
 * immunity, and the pickup deferral 0x46FE0 makes while it runs), as
 * the clip's end leaves it.  Every other move (attacks, the roll, the
 * hoist, the use) and every other body's build are unchanged: the build
 * installs it only for a recipe with victory_cancel.
 *
 * ABI at the CALL: EAX the active layer's flags, ECX the end mask (0x20
 * or 0x80), EBP the PlayerControl, EDI the input, EBX the critter, ESI
 * the state; the x87 stack empty.  The stub keeps every register but
 * the flags and returns ZF set to end the move.
 */

#include "azurik.h"   /* AZURIK_FLOAT_PARAM */

#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define CR_SLOT      0x200   /* critter: the slot playing                 */
#define CR_HIT_T     0x1E0   /* critter: the hit timer's remainder (s)    */
#define CR_HIT_LEN   0x1E4   /* critter: the hit timer's length (s)       */
#define IN_STICK     0x01C   /* input: the stick's magnitude, dead-zoned  */
#define IN_HELD      0x030   /* input: the control taken (a script's)     */
#define FIRST        75      /* the victories 75-80 (anim 0x4A + v)       */
#define LAST         80
#define STICK_MIN    0.1f    /* past the game's own dead zone: a push     */

AZURIK_FLOAT_PARAM(player_model_victory_cancel_after, 0.5f);

/* Whether the victory playing ends now: past its minimum, the stick pushed. */
__attribute__((used))
int victory_cancel(char *control, const char *input)
{
    char *critter = *(char *const *)(control + PC_CRITTER);
    int slot;

    if (!critter || input[IN_HELD])
        return 0;
    slot = *(const int *)(critter + CR_SLOT);
    if (slot < FIRST || slot > LAST)
        return 0;
    if (!(*(const float *)(critter + CR_HIT_LEN) - *(const float *)(critter + CR_HIT_T)
            >= player_model_victory_cancel_after)
            || !(*(const float *)(input + IN_STICK) > STICK_MIN))
        return 0;
    *(float *)(critter + CR_HIT_T) = 0.0f;
    return 1;
}

/* 0x8CF84: ZF set, the move ends (the game's `jne 0x8CFA0` at 0x8CF8A). */
__attribute__((naked))
void c_player_model_victory_cancel(void)
{
    __asm__ volatile (
        "testl %%ecx, %%eax       \n\t"   /* an end flag: it ends      */
        "jnz 1f                   \n\t"
        "testb $1, %%al           \n\t"   /* not playing: it ends (ZF) */
        "jz 2f                    \n\t"
        "pushl %%eax              \n\t"
        "pushl %%ecx              \n\t"
        "pushl %%edx              \n\t"
        "pushl %%edi              \n\t"   /* the input          */
        "pushl %%ebp              \n\t"   /* the PlayerControl  */
        "calll _victory_cancel    \n\t"
        "addl $8, %%esp           \n\t"
        "xorl $1, %%eax           \n\t"   /* ZF: cancelled      */
        "popl %%edx               \n\t"
        "popl %%ecx               \n\t"
        "popl %%eax               \n\t"
        "retl                     \n\t"
        "1:                       \n\t"
        "cmpl %%eax, %%eax        \n\t"   /* ZF set             */
        "2:                       \n\t"
        "retl                     \n\t"
        : : : "memory"
    );
}
