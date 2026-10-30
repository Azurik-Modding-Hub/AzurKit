/* X44: a picked weapon's baked attacks before the body's own (Step 2.161b2,
 * AZ-688).
 *
 * A body that borrows garret4's attacks for a picked weapon (the Axion
 * staff, the hoe: _player_weapons.Loadout.borrowing) keeps every
 * attacks_anims Anim vanilla, and B bakes garret4's clip for each onto
 * its rig as g4/<name>.  X12's attack hook (borrow.c) plays g4/<name> only
 * for a name the body can't resolve, so a body that owns one of those
 * names (attack_1 and attack_2 of keylord, golem, kingkong, overlord and
 * water_elemental; attack_1-3 of balthazar, air_elemental and
 * air_elemental_boss) swung its own clip in that column with the prop's
 * tip away from garret4's box.  The build installs this hook in X12's
 * attack hook's place for such a body (_player_borrow.FIRST).
 *
 * c_player_model_borrow_first, the attacks_anims loader's CALL
 * species_clip_lookup at 0x7E3F0 (EAX the name, EDI the out, the species
 * pushed, RET 4): for the player's species (S+0x64 flag 0x20) it looks up
 * g4/<name> first (characters/<body>/g4/<name>) and the name itself only
 * where that finds none; any other species looks the name up as the game
 * does.  The helper is cdecl and keeps EDI; 0x7E3F5 reads only EAX, the
 * out.
 */

#include "azurik_vanilla.h"

/* g4/<name> in a buffer, or NULL for an empty name. */
static char key[64];

__attribute__((used))
const char *first_key(const char *name)
{
    static const char prefix[] = "g4/";
    unsigned i = 0, j = 0;

    if (!name || !name[0])
        return 0;
    while (prefix[i]) {
        key[i] = prefix[i];
        i++;
    }
    while (name[j] && i < sizeof key - 1)
        key[i++] = name[j++];
    key[i] = 0;
    return key;
}

__attribute__((naked))
void c_player_model_borrow_first(void)
{
    __asm__ volatile (
        "movl 4(%%esp), %%ecx               \n\t"   /* the species        */
        "testb $0x20, 0x64(%%ecx)           \n\t"   /* the player's?      */
        "jz 2f                              \n\t"
        "pushl %%eax                        \n\t"   /* the name, kept     */
        "pushl %%eax                        \n\t"
        "calll _first_key                   \n\t"
        "addl $4, %%esp                     \n\t"
        "testl %%eax, %%eax                 \n\t"
        "jz 1f                              \n\t"
        "pushl 8(%%esp)                     \n\t"   /* the species        */
        "calll \"_species_clip_lookup@4\"   \n\t"   /* EAX g4/<name>      */
        "cmpl $-1, (%%edi)                  \n\t"
        "je 1f                              \n\t"
        "addl $4, %%esp                     \n\t"   /* its baked clip     */
        "movl %%edi, %%eax                  \n\t"
        "retl $4                            \n\t"
        "1:                                 \n\t"
        "popl %%eax                         \n\t"   /* the name           */
        "2:                                 \n\t"
        "pushl 4(%%esp)                     \n\t"   /* the species        */
        "calll \"_species_clip_lookup@4\"   \n\t"   /* EAX the name       */
        "movl %%edi, %%eax                  \n\t"
        "retl $4                            \n\t"
        : : : "memory"
    );
}
