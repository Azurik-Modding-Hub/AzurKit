/* X31: the player's hits give a no-hit window shortened by the attack
 * speed (Step 2.126, AZ-573; D318, the owner: "Shorten the window").
 *
 * Why.  A critter's message slot 0x43210 drops a hit while the target's
 * timer +0x1E0 is above 0 (0x4323C), and once the AI's slot +0x18
 * returns a nonzero damage for a hit it sets +0x1E4 and +0x1E0 to the
 * damage record's Delay (+0x10; 0.33 s for every player type, so 10
 * ticks: 0x43584-0x43591).  --player-attack-speed multiplies the
 * attacks' Rates, so from about speed 1.3 garret4's basic2 meets the
 * enemy basic1 just hit 7-8 ticks after that hit, inside its 10, and
 * deals it nothing (sitting 2.123's re-run: 0 of 3 at 1.3, 1.5, 1.6).
 * The damage types are shared with the enemies (Balthazar's norm_1-3),
 * so no config.xbr edit shortens the player's alone.
 *
 * What.  This shim replaces the 9 bytes at 0x43584 (FLD [EAX+0x10];
 * FST [EDX+0x1E4]) with a CALL and 4 NOPs, so 0x4358D and 0x43591 store
 * its ST0 into +0x1E0 as the game's.  It loads the record's Delay as the
 * game does, and when the hit is the player's (the attacker, the
 * source's vtable slot +0x74 as the game resolves it at 0x4327E: a
 * critter's 0x11D20 returns itself, a platform's 0x606A0 0, has the
 * species flag `player` 0x20 at S+0x64, X8's test, and isn't the
 * target) multiplies it by player_model_hit_delay_scale, 1 / the attack
 * speed, which the build writes (installed only above speed 1.0: below
 * it the window would grow, F1).  The window is then f32(f32(Delay) x
 * f32(1 / speed)), +0x1E4 as +0x1E0 (the critter draw's tint at
 * 0x3EAB8-0x3EBB4 reads the hit's +0x1E0 against +0x1E4, so equal values
 * keep its flash from its start).  Every other hit keeps the record's
 * Delay: an enemy's on anyone (the player's own handler sets his +0x1E0
 * to 2.0 before 0x4356E, so a hit on him never reaches here), a self
 * hit, a platform's, no source.
 *
 * ABI: at the CALL, EAX the damage record, EDX the target critter, EBX
 * the message, EBP &message.source (+4), ECX the AI's nonzero return
 * (read again at 0x435C3), ESI and EDI dead, the x87 stack empty
 * (0x43574's FCOMP popped it).  0x4358D reloads EDX and 0x43597 EAX.
 * The shim keeps ECX, EBX, ESI, EDI and EBP, returns with the Delay in
 * ST0 (the only x87 value) and +0x1E4 written, and may change EAX and
 * EDX.  The virtual call is __thiscall with no stack arguments, as the
 * game's at 0x4327E.
 */

#include "azurik.h"   /* AZURIK_FLOAT_PARAM */

#define CR_SPECIES  0x178   /* critter -> its species record       */
#define SP_FLAGS    0x064   /* species: its flags                  */
#define SP_PLAYER   0x20    /* the `player` flag                   */
#define VT_CRITTER  0x074   /* an entity's vtable: its critter     */

AZURIK_FLOAT_PARAM(player_model_hit_delay_scale, 1.0f);

typedef const char *(__attribute__((thiscall)) *critter_of_fn)(const char *self);

/* Whether the hit from *source on target is the player's. */
__attribute__((used))
int players_hit(const char *target, const char *const *source)
{
    const char *from = *source, *attacker, *species;

    if (!from || from == target)
        return 0;
    attacker = (*(const critter_of_fn *)(*(const char *const *)from + VT_CRITTER))(from);
    if (!attacker || attacker == target)
        return 0;
    species = *(const char *const *)(attacker + CR_SPECIES);
    return species && (*(const unsigned char *)(species + SP_FLAGS) & SP_PLAYER);
}

/* 0x43584: FLD [EAX+0x10]; FST [EDX+0x1E4], the player's hit's Delay
 * shortened. */
__attribute__((naked))
void c_player_model_hit_delay(void)
{
    __asm__ volatile (
        "pushl %%ecx                         \n\t"   /* the AI's return */
        "pushl %%edx                         \n\t"   /* the target, kept */
        "pushl %%eax                         \n\t"   /* the record, kept */
        "pushl %%ebp                         \n\t"   /* &message.source */
        "pushl %%edx                         \n\t"
        "calll _players_hit                  \n\t"
        "addl $8, %%esp                      \n\t"
        "movl %%eax, %%ecx                   \n\t"
        "popl %%eax                          \n\t"
        "popl %%edx                          \n\t"
        "flds 0x10(%%eax)                    \n\t"   /* its Delay, as the game loads it */
        "testl %%ecx, %%ecx                  \n\t"
        "jz 1f                               \n\t"
        "fmuls _player_model_hit_delay_scale \n\t"   /* the player's hit: x 1 / speed */
        "1:                                  \n\t"
        "fsts 0x1e4(%%edx)                   \n\t"
        "popl %%ecx                          \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}
