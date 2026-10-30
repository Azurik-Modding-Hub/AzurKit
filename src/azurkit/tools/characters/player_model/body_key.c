/* X47: the player binds its own recoloured copy of its body (Step 2.170b,
 * D539, D734: "prove recolor works and make a booblord recolor that makes
 * her have human (white/tan) colors").
 *
 * Why.  A species binds its body once (0x4B8E0, the [ebp+0x12] flag): it
 * formats 'characters/%s' (0x19F270; Europe 0x1A1428, the string's only
 * user) with the body string (+4) and keeps asset_find's result at +0x120.
 * Every species wearing the body binds the same entry, so a recolour made
 * in it changed every NPC wearing it too.  A recipe's `colours` are made
 * in a copy of the body, characters/<body>/v/skin (W38,
 * azurik_mod/assets/paint.py), which this shim binds for the player alone.
 * The clips stay where they were: 0x4B600 formats 'characters/%s/%s' from
 * the body string, not the key.
 *
 * What.  It takes the 5-byte `push 0x19F270` at 0x4B900 (the same VA and
 * code in both releases): for the player's species (the `player` flag
 * 0x20 in its +0x64, as X11 and X14 test it later in this function) it
 * pushes 'characters/%s/v/skin', for any other species its own copy of the
 * vanilla format, and goes back.
 *
 * ABI: a CALL trampoline; at it EBP = the species record, ECX the key's
 * buffer (pushed next, at 0x4B905: kept), EAX the body string already
 * pushed and EDX unused (both dead: the snprintf 0x4B90A reads its
 * arguments from the stack and returns in EAX), and no flag is read
 * before 0x4B90A.  The shim pops its return (0x4B905) into EDX, pushes
 * the format where the vanilla push put it and returns through it (push
 * EDX, a plain RET: L1's ret 0 for the inline push it took).
 */

__attribute__((used))
const char player_model_body_npc[] = "characters/%s";
__attribute__((used))
const char player_model_body_player[] = "characters/%s/v/skin";

/* 0x4B900: the player's copy's key format for the player, the vanilla one for the rest. */
__attribute__((naked))
void c_player_model_body_key(void)
{
    __asm__ volatile (
        "popl %%edx                              \n\t"   /* the return, 0x4B905 */
        "movl $_player_model_body_npc, %%eax     \n\t"
        "testb $0x20, 0x64(%%ebp)                \n\t"   /* the player's species? */
        "jz 1f                                   \n\t"
        "movl $_player_model_body_player, %%eax  \n\t"
        "1:                                      \n\t"
        "pushl %%eax                             \n\t"   /* the format, as the vanilla push */
        "pushl %%edx                             \n\t"   /* back through a plain RET (ret 0: the push it took) */
        "ret                                     \n\t"
        : : : "memory"
    );
}
