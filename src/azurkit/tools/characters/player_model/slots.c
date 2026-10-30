/* X11: a player model's empty base clip slots play one of its own clips
 * (Step 2.66; D219, D226, D229).
 *
 * A species' clip slots 0-0x51 (S+0x124 + 4 x index) are the XBE's base
 * clip table 0x1A9F78 (idle, walk, jump, superjump, fall, die, ouch_1,
 * swim_idle, victory_1, use, ...), resolved once when the species loads:
 * the species load 0x4B8E0 calls species_clip_lookup (0x4B600) with the
 * CALL at 0x4B948 for each index, the name as a whole asset key, else
 * as characters/<body>/<name>, -1 when neither exists.  No config.xbr
 * cell reaches these slots.  Only garret4's body has most of the names
 * the player asks for (52 of 57; every other body at most 9), and an
 * empty slot plays nothing: the clip already playing goes on (a run on
 * the idle, a walk while swimming), a body with neither idle nor idle_1
 * shows its bind pose from each level start (town_female_4, channeler:
 * a T-pose), and a death with no die clip ends at once.
 *
 * This shim replaces that CALL.  For the player's species (the `player`
 * flag 0x20 in S+0x64: garret4, whose body the swap retargets) a slot
 * the build wrote a name for into player_model_slots (the table below)
 * is looked up under that name first: one of the body's own clips, by
 * its name in characters/<body>/ (the same lookup, so the same archive
 * and case rules); when the table names none, or that lookup gives -1,
 * the slot is looked up under its own name, as the game does (Step
 * 2.131: table first, so W22's q/die can take a death slot the body
 * fills by name; only W22's and the jump family's tables name such a
 * slot, and no base name is a whole asset key).  Every other species
 * resolves as before.  The build names a slot the body fills by name
 * only for W22 and the jump family: a worn boss's death
 * (bosses/air_guardian, bosses/fire_guardian, balthazar_airship) plays
 * q/die, its die without the m_dying tracks that start the boss's death
 * camera and fragment drop (AZ-603), and on a body the bake serves,
 * under anims garret4, the jump slot 15 plays g4/jump
 * (_player_slots.JUMPS, Step 2.194a, D760: the five children ship a
 * run-like jump of their own).  The
 * build leaves empty the slots X9 (player_model/climb.c) serves (the
 * ladder, hoist and step moves 53, 60, 62-66 and the climb loops 55-59:
 * it plays its stand-in when a slot is -1) and, but on a body the bake
 * serves (where they name his baked clips), the hard landing 11, the
 * overhead hang 68, the victories 75-80 and use 81, aligned moves X9
 * plays its stand-in for in garret4's time (Step 2.66b; the victories
 * and use since Step 2.103, AZ-444, where an empty slot dropped the
 * move; the victories only where _player_victory.py gives none, Step
 * 2.121), and
 * fills a hit reaction's slot (37-42) only with another ouch clip: X7
 * (hit_reaction.c) plays its fallback for the rest in garret4's 0.4 s.
 * A slot whose garret4 clip deals no damage never gets one of the
 * body's damage clips (the damage pass 0x43A80 reads m_damage in any
 * state).
 *
 * The table is filled per body by the build (_player_slots.py): a very
 * similar own clip (the slot's semantic chain: idle -> idle_1..4, walk
 * -> stalk, run, jump <-> jump_standing <-> superjump, fall <->
 * fall_big, the deaths, swim_idle -> swim_idle_up/down, hover, ...)
 * plays in its own time;
 * any other slot garret4 has gets the body's closest own clip and,
 * with --player-character-anims garret4 (the default, D226/D229), is
 * marked garret4-timed: garret4_length holds garret4's clip length,
 * which X12 (borrow.c, Step 2.67; its own table carries the same
 * lengths) gives the stand-in.  On a body the bake serves (the
 * humanoids, retarget.py; a body with no clips, as timers) such a slot
 * names garret4's clip baked onto it, g4/<clip>.
 *
 * One-time: the species load runs before any of the species' critters,
 * and its preload (0xA6110, after the CALL) covers the handle.
 *
 * ABI at the CALL (kept by species_clip_lookup's): EAX the name, EDI
 * int *out, the species pushed (RET 4), out back in EAX; ESI the base
 * index; the caller reads only EAX after it (0x4B94D on, ECX reloaded
 * there) and 0x4B600 clobbers ECX itself.  The shim keeps EBX, ESI, EDI
 * and EBP, returns out in EAX and pops 4 bytes too.
 */

#include "azurik_vanilla.h"

#define N_BASE   0x52        /* base clip slots, 0x4B8E0's loop             */
#define N_NAMES  2048        /* the table's name bytes                      */

/* Filled in by the build after the shim lands: at[i] is 1 + the offset
 * of slot i's clip name in names (0: leave the slot as the lookup left
 * it); garret4_length[i] > 0 marks a garret4-timed stand-in (D229). */
volatile const struct {
    unsigned short at[N_BASE];
    float garret4_length[N_BASE];
    char names[N_NAMES];
} player_model_slots __attribute__((used, section(".rdata"))) = {{0}};

/* The clip name the build gave base slot `index`, or NULL. */
__attribute__((used))
const char *slot_fallback(unsigned index)
{
    unsigned at = index < N_BASE ? player_model_slots.at[index] : 0;

    return at ? (const char *)player_model_slots.names + at - 1 : 0;
}

__attribute__((naked))
void c_player_model_slots(void)
{
    __asm__ volatile (
        "movl 4(%%esp), %%ecx               \n\t"   /* the species        */
        "testb $0x20, 0x64(%%ecx)           \n\t"   /* the player's?      */
        "jz 2f                              \n\t"
        "pushl %%eax                        \n\t"   /* the base name      */
        "pushl %%esi                        \n\t"   /* the base index     */
        "calll _slot_fallback               \n\t"
        "addl $4, %%esp                     \n\t"
        "testl %%eax, %%eax                 \n\t"
        "jz 1f                              \n\t"
        "pushl 8(%%esp)                     \n\t"
        "calll \"_species_clip_lookup@4\"   \n\t"   /* the table's name   */
        "cmpl $-1, (%%edi)                  \n\t"
        "jne 3f                             \n\t"
        "1:                                 \n\t"
        "popl %%eax                         \n\t"   /* the base name      */
        "2:                                 \n\t"
        "pushl 4(%%esp)                     \n\t"
        "calll \"_species_clip_lookup@4\"   \n\t"   /* EAX name, EDI out  */
        "jmp 4f                             \n\t"
        "3:                                 \n\t"
        "addl $4, %%esp                     \n\t"
        "4:                                 \n\t"
        "movl %%edi, %%eax                  \n\t"
        "retl $4                            \n\t"
        : : : "memory"
    );
}
