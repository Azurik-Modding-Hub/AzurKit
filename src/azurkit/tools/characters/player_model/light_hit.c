/* X18: the player's hit in a column garret4 hits light stuns, whatever
 * its Damage multiplier (Step 2.104, AZ-525; D228's balance kept).
 *
 * Why.  The hit-level chooser 0x30BD0 (called by the AI's hit handler
 * 0x38C60 at 0x38D85 and the player's own at 0x8D66B; EAX the damage,
 * ECX the hit record, EDX whose +0x20 is the target critter) takes a
 * level from the damage against the target's species' thresholds
 * (S+0x48, S+0x4C), then, unless the target is dead, compares the hit
 * record's +0xC, the attack row's Damage multiplier, with 1.0
 * (0x30C11: FLD [ECX+0xC], FCOMP [0x1A250C], FNSTSW AX) and makes any
 * hit under 1.0 level 1 (0x30C1C: TEST AH,5; JP 0x30C26; MOV EBX,1).
 * Level 1 sets the target's stun bit 0x8000 (0x38EFF -> 0x37A70); level
 * 2 or 3 sets its hit timer instead and clears a stun it had (0x37A70
 * clears 0x58000 first).  The combo's chains from basic1, basic2 and
 * basic3 (0x7EF10's rows 28-31) need a stunned target ahead, and
 * garret4's light columns (basic1-3, right1, up1: 0.5) stun.  Own
 * mode's attack balance (W14, D228) multiplies each column's multiplier
 * by the body's B, which takes many bodies' basics to 1.0 or more
 * (guard_water's basic1 1.1667), and the damage slider at 2 takes
 * every one there: their hits never stun, so their combo stopped at
 * basic1 (xemu sitting 2.103, rows A1-A5 and M).  The damage reads the
 * same multiplier (0x38CD6), so no data edit keeps the damage and the
 * stun.
 *
 * What.  This shim replaces the 10 bytes at 0x30C1C (a CALL and 5
 * NOPs, so it returns to 0x30C26's FLD).  It applies the game's rule
 * first (under 1.0: EBX := 1).  Otherwise, when the hit is the
 * player's melee in this attack (the attacker at the record's +4 is
 * the player critter, the world's +0xBC, the target's +0x154 its world,
 * the test the game makes at 0x38F20; and the record's +0xC is the
 * player critter's +0x224, the attack row's multiplier its damage pass
 * copied into the record at 0x43BD9) and the attack column the player's
 * PlayerControl (critter+0x180) plays (+0x134) is one of
 * player_model_light_columns (a 24-bit mask: the columns whose vanilla
 * Damage multiplier is under 1.0, written by the build), EBX := 1, as
 * garret4's hit there is.  So is it (Step 4.3, D1045) when X36's attack
 * sets are on and the swing is a set's standing for basic1-3: X36's
 * state (its search landing's, its VA in the bytes param
 * player_model_light_sets_at; 0 on a body with one set) holds the combo
 * column the swing stands for (+4, logical: 0-2) and the column it plays
 * (+8, source) while that swing plays, and the column is that one.  A
 * set's column (a gust, a sweep, a cast) is often heavy in the game
 * (sweep1's multiplier 1.0), so without this its hit never stunned and
 * the set's combo, which by default chains only onto a stunned target
 * (rows 28-31's gate kept), never went past its first attack.  Damage
 * stays the multiplier's; every other hit (an enemy's on the player, AI
 * on AI, the player's heavy columns, B's sweeps, a set's fourth, a hit
 * whose multiplier isn't the attack's) keeps the game's level.
 *
 * ABI: at the CALL, AX holds the FPU status FNSTSW stored, EBX the
 * level, ECX the hit record, ESI the target's species, EDI the target
 * critter, EBP the caller's argument; 0x30C26 on reads EBX, ECX, ESI,
 * EDI and the x87 stack (empty here) and writes EAX and EDX before
 * reading them.  The shim keeps ECX, ESI, EDI, EBP and the x87 stack,
 * and changes only EBX, EAX and EDX.
 */

#include "azurik.h"   /* AZURIK_FLOAT_PARAM */

#define CR_WORLD     0x154   /* critter -> its world                      */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl (the player's) */
#define CR_MULTIPLY  0x224   /* critter: the attack row's Damage multiplier */
#define WD_PLAYER    0x0BC   /* world -> the player critter               */
#define PC_COLUMN    0x134   /* PlayerControl: the attack column it plays  */
#define HIT_ATTACKER 0x004   /* hit record -> its attacker                */
#define HIT_MULTIPLY 0x00C   /* hit record: its Damage multiplier          */
#define COLUMNS      24
#define SET_LOGICAL  0x004   /* X36's state: the combo column a set's swing stands for; -1 */
#define SET_SOURCE   0x008   /* X36's state: the column it plays          */
#define BASICS       3       /* basic1-3: the combo columns a chain leaves */

AZURIK_FLOAT_PARAM(player_model_light_columns, 0.0f);
AZURIK_BYTES_PARAM(player_model_light_sets_at, 4);

/* Whether the hit is the player's melee in a light column, or in a set's
 * swing standing for basic1-3. */
__attribute__((used))
int light_hit(const char *hit, const char *target)
{
    const char *world = *(const char *const *)(target + CR_WORLD);
    const char *player, *control, *sets;
    unsigned column;

    if (!world)
        return 0;
    player = *(const char *const *)(world + WD_PLAYER);
    if (!player || *(const char *const *)(hit + HIT_ATTACKER) != player
            || *(const unsigned *)(hit + HIT_MULTIPLY) != *(const unsigned *)(player + CR_MULTIPLY))
        return 0;
    control = *(const char *const *)(player + CR_CONTROL);
    if (!control)
        return 0;
    column = *(const unsigned *)(control + PC_COLUMN);
    if (column >= COLUMNS)
        return 0;
    if (((unsigned)(int)player_model_light_columns >> column) & 1)
        return 1;
    sets = *(const char *const volatile *)player_model_light_sets_at;
    if (!sets)
        return 0;
    {
        int logical = *(const volatile int *)(sets + SET_LOGICAL);

        return logical >= 0 && logical < BASICS && *(const volatile unsigned *)(sets + SET_SOURCE) == column;
    }
}

/* 0x30C1C: TEST AH,5 / JP 0x30C26 / MOV EBX,1, then the player's light
 * hit. */
__attribute__((naked))
void c_player_model_light_hit(void)
{
    __asm__ volatile (
        "testb $5, %%ah           \n\t"   /* the game's compare: under 1.0? */
        "jp 1f                    \n\t"
        "movl $1, %%ebx           \n\t"   /* yes: level 1 */
        "retl                     \n\t"
        "1:                       \n\t"
        "pushl %%ecx              \n\t"
        "pushl %%edi              \n\t"   /* the target     */
        "pushl %%ecx              \n\t"   /* the hit record */
        "calll _light_hit         \n\t"
        "addl $8, %%esp           \n\t"
        "popl %%ecx               \n\t"
        "testl %%eax, %%eax       \n\t"
        "jz 2f                    \n\t"
        "movl $1, %%ebx           \n\t"   /* the player's light hit: level 1 */
        "2:                       \n\t"
        "retl                     \n\t"
        : : : "memory"
    );
}
