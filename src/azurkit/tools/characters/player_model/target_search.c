/* X21: the combo chains on a stunned target out to the reach of the
 * body's basics (Step 2.105, AZ-523's 3 m rule; D115's default: past
 * 3 m only onto a stunned or frozen target).
 *
 * Why.  The attack transition search 0x7EF10 asks its target finder
 * 0x7EBB0 (attack_target_find, the CALL at 0x7EF80, its only caller)
 * for a target, and the combo's rows 28-31 (basic1 -> basic2 -> basic3
 * -> finish, finish3) need one stunned or frozen ahead.  0x7EBB0 takes
 * only a critter whose distance less radius (between the bounds
 * centres) is at most 3.0 m: it reads the 3.0 at 0x1A25BC for its query
 * cube (0x7EC10, 0x7EC20, 0x7EC36, 0x7EC53, 0x7EC5D, 0x7EC67) and for
 * that test (0x7EDA4) [verified static], a constant 35 instructions
 * share.  A body whose basics hit farther couldn't chain: golem own hit
 * and stunned f6's lone blaze sentinel 3.6 m out and the search counted
 * no target, basic1 again in 12 of 12 presses (sitting 2.104).
 *
 * What.  The build points those seven operands at
 * player_model_search_radius (3.0, writable shim data) and this shim
 * replaces the CALL at 0x7EF80.  It runs the game's search.  When the
 * critter is the player's species (flag 0x20), its PlayerControl
 * (critter +0x180) plays basic1-3 (+0x134, the transitions' last move:
 * 0x7EF10's [EBP+0x58], EBP the PlayerControl's +0xDC; attacks_anims'
 * columns 0-2), the search found no target and
 * player_model_search_reach (R, the farthest any box of the build's
 * basic1-3 reaches from the feet, x X13's reach and bump) is above 3.0,
 * it searches again with the radius at R and keeps that result only
 * when its target is stunned or frozen (0x18000 in the record's +0x1C,
 * the target's +0x168); otherwise the first result stands.  The radius
 * is 3.0 again before the shim returns.  Any target within 3 m, another
 * critter, a press outside basic1-3 (a fresh one: rows 16 and 32, up2
 * and finish2 onto a stunned target, keep 3 m) and a body whose basics
 * reach 3 m or less get the game's one search; in basic1-3 the
 * directional rows (17-26), which take any target the search returns,
 * see a farther one only when it is stunned.  garret4's own body drawn
 * s times his size at reach r (Step 2.123) takes R = 3 m x s x r, where
 * that passes 3.
 *
 * ABI: attack_target_find is __stdcall(12) (the critter, its facing
 * angle, a 0x38-byte result; RET 0xC), no register input; 0x7EF10 reads
 * the result's count (+0) next and sets ESI, and keeps EBX, EBP and EDI.
 * The shim is __stdcall(12) too and keeps EBX, ESI, EDI and EBP.
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl (the player's) */
#define PC_COLUMN    0x134   /* PlayerControl: the attack column it plays  */
#define CHAINED      3       /* basic1-3: attacks_anims' columns 0-2       */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define FOUND_COUNT  0       /* result: how many targets passed (int)      */
#define FOUND_FLAGS  7       /* result +0x1C: the target's +0x168 (int)    */
#define FOUND_WORDS  14      /* the 0x38-byte result                      */
#define STUNNED      0x18000 /* stunned (0x8000) or frozen (0x10000)       */
#define VANILLA      3.0f    /* 0x1A25BC                                  */

/* The radius 0x7EBB0's seven repointed operands read (the build writes
 * its address into them). */
volatile float player_model_search_radius = VANILLA;

AZURIK_FLOAT_PARAM(player_model_search_reach, 0.0f);

__attribute__((stdcall))
void c_player_model_target_search(char *critter, float facing, int *found)
{
    const char *species = critter ? *(const char *const *)(critter + CR_SPECIES) : 0;
    const char *control;
    float reach = player_model_search_reach;
    int kept[FOUND_WORDS];
    int k;

    attack_target_find(critter, facing, found);
    if (found[FOUND_COUNT] || !(reach > VANILLA) || !species
            || !(*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG))
        return;
    control = *(const char *const *)(critter + CR_CONTROL);
    if (!control || *(const unsigned *)(control + PC_COLUMN) >= CHAINED)
        return;
    for (k = 0; k < FOUND_WORDS; k++)
        kept[k] = found[k];
    player_model_search_radius = reach;
    attack_target_find(critter, facing, found);
    player_model_search_radius = VANILLA;
    if (found[FOUND_COUNT] && (found[FOUND_FLAGS] & STUNNED))
        return;
    for (k = 0; k < FOUND_WORDS; k++)
        found[k] = kept[k];
}
