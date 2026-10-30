/* X14: a player model speaks with its own species' sounds (Step 2.71;
 * D224, D231, D232; design: Step 2.62).
 *
 * A critter's clip sounds bind by species and slot name, never by body:
 * species_bind_clip_sounds (0x4B680; EDI = the species record, stack
 * slot and clip, RET 8) binds "<sound dir>/<clip>" and its _a .. _s
 * variants to the slot, the dir being the record's +8.  The player
 * stays garret4 under the swap, so every slot bound garret4's dir
 * (loc/english/speech/azurik_speech): a swapped body spoke Garret's
 * lines and none of its own species'.
 *
 * This shim replaces two CALLs of 0x4B680, one object landed once per
 * hook (the qol_save_warp pattern): 0x4B93C (0x4B8E0: the 82 base
 * clips as slots 0-81, once per species) and 0x7E3DD
 * (load_attacks_anims_config: each attacks_anims Anim as slot 0x52 +
 * column).  For the player's species (the `player` flag 0x20 in
 * S+0x64) it looks the slot up in player_model_sounds, a table the
 * build writes (BytesParam; azurik_mod/patches/_player_sounds.py
 * encodes it):
 *
 *   +0  u16  offset of the model's sound dir (a NUL-terminated name)
 *   +2  u16  how many slots the table covers
 *   +4  u16  per slot: 0 = a miss, else the offset of the clip name to
 *            bind (an empty name binds nothing, as 0x4B680 does for an
 *            empty clip)
 *   ...      the names
 *
 * A hit points S+8 at the model's dir, calls 0x4B680(slot, that name)
 * and puts S+8 back; a miss calls 0x4B680 unchanged, so the slot keeps
 * Garret's sound (D232).  Any other species takes the vanilla call.
 * Slots a level adds (0x4B840: Garret's scripted lines) and
 * critters_special_anims (0x4B2AE) come through other CALLs and are
 * untouched.
 *
 * ABI: both sites push the clip and the slot and load EDI with the
 * species record; neither reads EAX, ECX or EDX after the call, and
 * 0x7E3E2 reads EDI.  The entry pops 8 bytes as 0x4B680 does and keeps
 * EBX, ESI, EDI and EBP.
 */

#include "azurik_vanilla.h"

#define SP_SOUND_DIR  0x008   /* species: its `sound dir` (char *)        */
#define SP_FLAGS      0x064   /* species: its kind flags                  */
#define PLAYER_FLAG   0x20    /* the `player` feature                     */

#define TABLE_SIZE    1024    /* _player_sounds.TABLE_SIZE                */

AZURIK_BYTES_PARAM(player_model_sounds, TABLE_SIZE);

static unsigned u16_at(unsigned at)
{
    return player_model_sounds[at] | (unsigned)player_model_sounds[at + 1] << 8;
}

__attribute__((stdcall, used))
void player_model_sounds_bind(char *species, unsigned slot, const char *clip)
{
    unsigned at = 0;
    char *dir;

    if ((*(unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) && slot < u16_at(2))
        at = u16_at(4 + 2 * slot);
    if (!at) {
        species_bind_clip_sounds_call(species, (int)slot, clip);
        return;
    }
    dir = *(char **)(species + SP_SOUND_DIR);
    *(const char **)(species + SP_SOUND_DIR) =
        (const char *)&player_model_sounds[u16_at(0)];
    species_bind_clip_sounds_call(species, (int)slot,
                                  (const char *)&player_model_sounds[at]);
    *(char **)(species + SP_SOUND_DIR) = dir;
}

/* The hook's entry: EDI = the species, [ESP + 4] the slot, [ESP + 8]
 * the clip; RET 8, as 0x4B680. */
__attribute__((naked))
void c_player_model_sounds(void)
{
    __asm__ volatile (
        "pushl 8(%%esp)                          \n\t"   /* the clip     */
        "pushl 8(%%esp)                          \n\t"   /* the slot     */
        "pushl %%edi                             \n\t"   /* the species  */
        "calll \"_player_model_sounds_bind@12\"   \n\t"
        "retl $8                                 \n\t"
        : : : "memory"
    );
}
