/* X32: a worn body's plain hits show a small flash of their own (Step
 * 2.132, D333; Step 2.180, D700, the owner: "why does she have the smash
 * power visual effect when she hits enemies? This makes it confusing as
 * if she is using the smash power, for any visual effects like this, make
 * sure they dont conflict with element effects and also it is too
 * obtrusive, make the effect smaller and less in the way").
 *
 * Why.  An AI critter's hit handler 0x38C60 picks a hit's visual by the
 * hit's damage record, in the VICTIM species' critters_damage_fx row:
 * 0x38FEA-0x39006 push S_victim+0x90[index] (index = the record's place
 * in config `damage`, kept at the body's [esp+0x14]) and call 0x440F0
 * (critter_play_fx) on the victim.  The player stays species garret4
 * under the swap, and his hit's record is armor_mgr+0x18 (0x8C31B every
 * tick: the plain staff's norm_1-norm_3, else the selected power's), so
 * a worn body's hits showed fx/damage/fx_norm_N where its NPC's show its
 * own type's (the fire elemental's fire_elemental record: fx_fire_3, the
 * owner's "fire blast"; guard_air's wind_3: fx_whirlwind_3).  The table
 * is per victim and shared, so no config.xbr edit reaches the player's
 * hits alone.
 *
 * What.  This shim takes the CALL 0x440F0 at 0x39006 (the same VA and
 * code in both releases).  When the hit's attacker is the player (hit+4
 * equals the world's +0xBC, the test 0x38F20 makes for the rumble fx)
 * and its record is a plain one (index 0-3, norm_1-norm_4: a power keeps
 * its element's visual), it pushes the key player_model_hit_fx names
 * (the build's own flash, appended to fx.xbr: a copy of the plain
 * staff's fx_norm_1 at half its size, shorter and fainter) instead, on
 * every victim; then it jumps on to 0x440F0.  Since D700 no body's plain
 * hit shows an element power's effect (Step 2.132's fire elemental drew
 * fx_fire_3, the bare-hands kit the smash power's fx_smash_1).  The
 * damage, the stun, the Delay, the hit sound and the rumble fx keep the
 * hit's own record.
 *
 * ABI: at the CALL, ECX = EBX = the victim critter, [esp+4] the key
 * 0x39003 pushed, and in 0x38C60's frame (sub esp 0x74 and four pushes,
 * then the key and the return address) the record's index at
 * [esp+0x1C] and the hit (the handler's argument) at [esp+0x90].  The C
 * part keeps EBX, ESI, EDI and EBP; the thunk keeps ECX and jumps to
 * 0x440F0 with the return address and the key as the CALL left them, so
 * its RET 4 pops the key and returns to 0x3900B.  No x87 value is live.
 */

#include "azurik_vanilla.h"   /* critter_play_fx; and azurik.h: AZURIK_BYTES_PARAM */

#define CR_WORLD    0x154   /* critter -> its world                    */
#define WD_PLAYER   0x0BC   /* world -> the player critter             */
#define NORMS       4       /* norm_1-norm_4, config `damage`'s first  */
#define NAME_SIZE   32      /* _player_character.HIT_FX_NAME_SIZE      */

AZURIK_BYTES_PARAM(player_model_hit_fx, NAME_SIZE);

/* The key the hit of record `index` shows on `victim`. */
__attribute__((used))
const char *hit_fx_key(const char *key, const char *victim, const char *const *hit, int index)
{
    const char *world;

    if (!player_model_hit_fx[0] || index < 0 || index >= NORMS || !hit)
        return key;
    world = *(const char *const *)(victim + CR_WORLD);
    if (!world || hit[1] != *(const char *const *)(world + WD_PLAYER))
        return key;
    return (const char *)player_model_hit_fx;
}

/* 0x39006: CALL critter_play_fx, the build's flash on the player's plain hit. */
__attribute__((naked))
void c_player_model_hit_fx(void)
{
    __asm__ volatile (
        "pushl %%ecx                         \n\t"   /* the victim, kept */
        "pushl 0x20(%%esp)                   \n\t"   /* the record's index */
        "pushl 0x98(%%esp)                   \n\t"   /* the hit */
        "pushl %%ecx                         \n\t"
        "pushl 0x14(%%esp)                   \n\t"   /* the key pushed for 0x440F0 */
        "calll _hit_fx_key                   \n\t"
        "addl $16, %%esp                     \n\t"
        "popl %%ecx                          \n\t"
        "movl %%eax, 4(%%esp)                \n\t"
        "jmp _critter_play_fx                \n\t"
        : : : "memory"
    );
}
