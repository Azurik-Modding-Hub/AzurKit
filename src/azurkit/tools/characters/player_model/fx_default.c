/* X40: the player's default fx is the build's own clone (Step 2.157,
 * D446, the owner: "let's also make it possible with tooling to create
 * new effects and duplicate effects and such without replacing assets if
 * we want").
 *
 * Why.  A body's default fx, characters/<body>/fx/fx_default, is one
 * graph that 0x43700 builds on every critter wearing the body, the
 * player too: the critter init 0x408E0 calls it once (0x408F8), and it
 * formats the key with 'characters/%s/fx/fx_default' (0x19FD34; Europe
 * 0x1A1EEC) and the body string.  So a variant's fx edits made in that
 * graph changed every NPC of the body too (D417: the airship boss in a
 * beamlord build).  The build now adds the player's own copy of the
 * graph, characters/<body>/v/fx/fx_default, with the edits.
 *
 * What.  This shim takes the 5-byte `push 0x19FD34` at 0x43719 (the same
 * VA and code in both releases): when the critter's species record
 * (EAX, [critter+0x178]) has the player's ai class at +0xC (the registry
 * value the `ai` cell named 'player' gave it, the factory 0x8D750; Europe
 * 0x8D700: only garret4 and the unplaced noship have it), it pushes
 * 'characters/%s/v/fx/fx_default', else the vanilla format (its own copy
 * of the string), and goes back.  Every other key the body string forms
 * (the body, its clips, 0x437A0's '*' keys) is untouched.
 *
 * ABI: a CALL trampoline; at it EAX = the species record (reloaded at
 * 0x43727), ECX = the body string already pushed (dead: snprintf 0x178C0
 * reads its arguments from the stack), EDX unused before 0x4373A, and no
 * flag is read before 0x43722.  The shim pops its return address
 * (0x4371E) into EDX, pushes the format where the vanilla push put it
 * and returns to it (push EDX, a plain RET: L1's ret 0 for the inline
 * push it took), so the stack is as the push left it.
 */

#include "azurik_vanilla.h"   /* player_ai_factory */

__attribute__((used))
const char player_model_fx_npc[] = "characters/%s/fx/fx_default";
__attribute__((used))
const char player_model_fx_player[] = "characters/%s/v/fx/fx_default";

/* 0x43719: push the player's clone's format for the player, the vanilla one for the rest. */
__attribute__((naked))
void c_player_model_fx_default(void)
{
    __asm__ volatile (
        "popl %%edx                              \n\t"   /* the return, 0x4371E */
        "movl $_player_model_fx_npc, %%ecx       \n\t"
        "cmpl $_player_ai_factory, 0x0C(%%eax)   \n\t"   /* the species' ai class: the player's? */
        "jne 1f                                  \n\t"
        "movl $_player_model_fx_player, %%ecx    \n\t"
        "1:                                      \n\t"
        "pushl %%ecx                             \n\t"   /* the format, as the vanilla push */
        "pushl %%edx                             \n\t"   /* back through a plain RET (ret 0: the push it took) */
        "ret                                     \n\t"
        : : : "memory"
    );
}
