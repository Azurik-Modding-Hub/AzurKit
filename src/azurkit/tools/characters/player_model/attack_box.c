/* X13: the player's attack box, its reach and its fill (Step 2.70;
 * D222 amended, D223; the fill: Step 2.132, D347, D341, AZ-605).
 *
 * The damage pass 0x43A80 (a critter's +0xD8 task) builds a hit box for
 * each of the critter's damage markers that is on, through the CALL
 * 0xCA390 at 0x43B47: a 4x4 matrix (rows 0-2 the box's axes in model
 * space, from the marker's quaternion; row 3 its centre, the marker's
 * position) and the box's local min/max (-/+ extents x length).  Then
 * 0x43B4C-0x43B8F scale the centre and the min/max by the critter's
 * scale (+0x188) and the critter's world matrix places the box; the
 * target test (0xB6A70) takes any min/max, an uneven one too.  A
 * swapped body's box is its own (characters.xbr's markers, shared with
 * the same species as an enemy, so no data edit can change it only for
 * the player): keylord's sits from 1.11 m up, Balthazar's from 1.23 m,
 * and they pass over a sleeth (0.53 m tall) or a flicken (Step 2.61);
 * guard_air's stay 1.27 m ahead or overhead, and X3's on a hand beside
 * the facing line (Step 2.132's read).
 *
 * This shim replaces that CALL, calls 0xCA390 with the game's registers,
 * then, for the player's species only (the `player` flag 0x20 in
 * S+0x64, as X6 and X8 test), in model units before the game's scale
 * (so every threshold below is the feet, at any scale):
 *
 *  1. reach, per attacks_anims column (the PlayerControl's +0x134,
 *     critter+0x180): player_attack_reach (default 1.0, any finite
 *     value, D23), times player_attack_bump (D223's reach bump, 1.25)
 *     for a column whose bit is in player_attack_bump_mask (Step 2.69:
 *     a melee column whose own reach is under 0.75 of garret4's basic1
 *     reach, with the attack balance on): the box's centre moves that
 *     many times as far ahead (row 3's x and y; its height stays) and
 *     its min/max grow that many times about the centre, so the box
 *     reaches k times as far;
 *  2. the fill, for an attack whose attacks_anims column has its bit in
 *     player_attack_ground_mask (every attack column but the roll, Step
 *     2.132; 0 = off): the box becomes its model-space bounds (rows 0-2
 *     the identity, row 3 their centre, the min/max -/+ their half
 *     sizes), so it holds the oriented box and is the box the build's
 *     W19 samples (characters.first_contact); then, unless the whole box
 *     is behind the feet (its far y under 0: a spin's rear phase, never
 *     dragged forward), its near face comes back to the feet (y = 0) and
 *     it widens to the facing line (x = 0); and a bottom above the feet
 *     comes down to them (z = 0).  Its far faces and top stay, so its
 *     reach does.
 *
 * Every other critter's box is 0xCA390's.  Each mask is a whole number
 * below 2^24 (24 columns), so the float holds it exactly.
 *
 * At entry (the CALL's): ECX the matrix, EAX the min/max, EDX the
 * marker; EBX the damage task, critter+0xD8, throughout the two-marker
 * loop (ESI is reused there).  0xCA390 keeps ECX and clobbers EAX and
 * EDX; 0x43A80 reads none of EAX, ECX and EDX after it, so the shim
 * keeps only EBX, ESI, EDI and EBP (the C part's callee-saved ones) and
 * returns with a plain RET and an empty x87 stack, as 0xCA390 does.
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

AZURIK_FLOAT_PARAM(player_attack_reach, 1.0f);
AZURIK_FLOAT_PARAM(player_attack_ground_mask, 0.0f);
AZURIK_FLOAT_PARAM(player_attack_bump_mask, 0.0f);
AZURIK_FLOAT_PARAM(player_attack_bump, 1.0f);

#define CR_SPECIES    0x178   /* critter -> species                         */
#define CR_CONTROL    0x180   /* critter -> its PlayerControl (the player's) */
#define SP_FLAGS      0x64
#define SP_PLAYER     0x20    /* the species' `player` flag                 */
#define PC_ATTACK     0x134   /* the attacks_anims column playing; -1 none  */
#define COLUMNS       24

/* m: the box's matrix (16 floats by rows); b: min x, y, z, max x, y, z. */
__attribute__((used))
void attack_box_adjust(float *m, float *b, const char *critter)
{
    const char *species = *(const char *const *)(critter + CR_SPECIES);
    const char *control;
    float k, lo[3], hi[3], p, q;
    int column, mask, i, j;

    if (!species || !(*(const unsigned char *)(species + SP_FLAGS) & SP_PLAYER))
        return;
    control = *(const char *const *)(critter + CR_CONTROL);
    column = control ? *(const int *)(control + PC_ATTACK) : -1;
    if (column >= COLUMNS)
        column = -1;
    k = player_attack_reach;
    if (column >= 0 && (((int)player_attack_bump_mask >> column) & 1))
        k *= player_attack_bump;
    if (k != 1.0f) {
        m[12] *= k;
        m[13] *= k;
        for (j = 0; j < 6; j++)
            b[j] *= k;
    }
    mask = (int)player_attack_ground_mask;
    if (column < 0 || !((mask >> column) & 1))
        return;
    for (i = 0; i < 3; i++) {                 /* the box's model-space bounds */
        lo[i] = hi[i] = m[12 + i];
        for (j = 0; j < 3; j++) {
            p = m[4 * j + i] * b[j];
            q = m[4 * j + i] * b[3 + j];
            lo[i] += p < q ? p : q;
            hi[i] += p < q ? q : p;
        }
    }
    if (hi[1] >= 0.0f) {                      /* not wholly behind the feet */
        if (lo[1] > 0.0f)
            lo[1] = 0.0f;                     /* back to the feet */
        if (lo[0] > 0.0f)
            lo[0] = 0.0f;                     /* across to the facing line */
        if (hi[0] < 0.0f)
            hi[0] = 0.0f;
    }
    if (lo[2] > 0.0f)
        lo[2] = 0.0f;                         /* down to the floor */
    for (i = 0; i < 3; i++) {
        for (j = 0; j < 4; j++)
            m[4 * i + j] = i == j ? 1.0f : 0.0f;
        m[12 + i] = (lo[i] + hi[i]) * 0.5f;
        b[3 + i] = (hi[i] - lo[i]) * 0.5f;
        b[i] = -b[3 + i];
    }
}

__attribute__((naked))
void c_player_attack_box(void)
{
    __asm__ volatile (
        "pushl %%ecx                         \n\t"   /* the matrix */
        "pushl %%eax                         \n\t"   /* the min/max */
        "calll \"@anim_marker_box@8\"        \n\t"
        "popl %%eax                          \n\t"
        "popl %%ecx                          \n\t"
        "leal -0xd8(%%ebx), %%edx            \n\t"   /* the critter */
        "pushl %%edx                         \n\t"
        "pushl %%eax                         \n\t"
        "pushl %%ecx                         \n\t"
        "calll _attack_box_adjust            \n\t"
        "addl $12, %%esp                     \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}
