/* X43: bare hands' hits land with a soft thud (Step 2.159a; D502, the
 * owner: "Whoosh + impact thud": bare-hand swings get a short
 * synthesized whoosh and hits a soft thud).
 *
 * Why.  An AI critter's hit handler 0x38C60 plays a hit's sound by the
 * hit's damage record, from the VICTIM species' critters_sounds hit
 * rows: 0x38D08-0x38D2F push S_victim+0xB4[index] (the handle 0x4A7E1
 * resolved for the row, index = the record's place in config `damage`,
 * kept at the body's [esp+0x14]) and call 0xA2630 (sound_play_at) at the
 * victim's point.  The player stays species garret4 under the swap, and
 * his plain hit's record is norm_1-norm_3, so a weaponless townsperson's
 * punch sounded as the staff's hit on that victim (fx/sound/hits/flesh1
 * on most), and the table is per victim and shared, so no config.xbr
 * edit reaches the player's hits alone.
 *
 * What.  This shim takes the CALL 0xA2630 at 0x38D2F (the same VA and
 * code in both releases).  When the hit's attacker is the player (hit+4
 * equals the world's +0xBC, the test 0x38F20 makes for the rumble fx, as
 * X32's) and its record is a plain one (index 0-3, norm_1-norm_4: a
 * power keeps its element's sound), it plays the wave player_model_thud
 * names (the build's kit thud, appended to fx.xbr), when asset_find
 * (0xA5CA0) has it, in place of the victim's; then it jumps on to
 * 0xA2630.  The victim's ouch after it (0x38D54) and every other sound
 * are the game's.
 *
 * ABI: at the CALL, EBX = the victim critter, the handle, the point and
 * a 0 pushed (0xA2630 pops 12), EAX = 0 (0xA1C70's flag; the vanilla
 * XOR at 0x38D2D), and in 0x38C60's frame (sub esp 0x74 and four
 * pushes, then the three arguments and the return address) the record's
 * index at [esp+0x24] and the hit (the handler's argument) at
 * [esp+0x98].  The C part keeps EBX, ESI, EDI and EBP; the thunk puts
 * the handle in its slot, zeroes EAX again and jumps to 0xA2630 with the
 * return address and the arguments as the CALL left them, so its RET 0xC
 * returns to 0x38D34.  No x87 value is live.
 */

#include "azurik_vanilla.h"   /* asset_find, sound_play_at; and azurik.h: AZURIK_BYTES_PARAM */

#define CR_WORLD    0x154   /* critter -> its world                 */
#define WD_PLAYER   0x0BC   /* world -> the player critter          */
#define NORMS       4       /* norm_1-norm_4, config `damage`'s first */
#define NAME_SIZE   32      /* _player_character.THUD_NAME_SIZE     */

AZURIK_BYTES_PARAM(player_model_thud, NAME_SIZE);

/* The sound the hit of record `index` on `victim` plays. */
__attribute__((used))
int thud_handle(int handle, const char *victim, const char *const *hit, int index)
{
    const char *world;
    int found;

    if (!player_model_thud[0] || index < 0 || index >= NORMS || !hit)
        return handle;
    world = *(const char *const *)(victim + CR_WORLD);
    if (!world || hit[1] != *(const char *const *)(world + WD_PLAYER))
        return handle;
    found = asset_find((const char *)player_model_thud, 0, 2);
    return found == -1 ? handle : found;
}

/* 0x38D2F: CALL sound_play_at, the kit's thud on the player's plain hit. */
__attribute__((naked))
void c_player_model_thud(void)
{
    __asm__ volatile (
        "pushl 0x24(%%esp)                   \n\t"   /* the record's index */
        "pushl 0x9c(%%esp)                   \n\t"   /* the hit */
        "pushl %%ebx                         \n\t"   /* the victim */
        "pushl 0x10(%%esp)                   \n\t"   /* the handle pushed for 0xA2630 */
        "calll _thud_handle                  \n\t"
        "addl $16, %%esp                     \n\t"
        "movl %%eax, 4(%%esp)                \n\t"
        "xorl %%eax, %%eax                   \n\t"
        "jmp \"_sound_play_at@12\"            \n\t"
        : : : "memory"
    );
}
