/* X49: a recipe's seeking columns turn to their target at the attack's
 * start (Step 2.194b; D762, the owner: "let's make beamlord's beams
 * seek"; D761: seeking is an opt-in field, a clip's "seek": true).
 *
 * Why.  player_attack_enter (0x88990, EDI the PlayerControl) faces every
 * attack by the swing's yaw PC+0x138, which attack_anim_record_copy
 * (0x7F1F0) wrote at the transition search's end: the stick heading H,
 * or the bearing B of the target attack_target_find (0x7EBB0) gave within
 * 60 degrees of it, less the column's Aim angle (degrees, PC+0xE8, the
 * record's +0xC; 1e5 empty: none taken off).  It loads the yaw at
 * 0x88A3A, makes it a quaternion (quat_from_euler 0x4FF10 at 0x88A5E),
 * and the attack's first tick (player_attack_root_motion 0x8C630) turns
 * the body by it (0x42E40 at 0x8C7AF); every later tick keeps the
 * body's own orientation.  The finder looks 3 m out (X21's radius), so
 * beamlord's 14 m beam turned to no target past 3 m.
 *
 * What.  At that load (Europe 0x889EA), for a column of float param
 * player_model_seek_columns (bit i: attacks_anims column i, PC+0x134)
 * whose own slot plays (critter+0x200 == 0x52 + it: anim_change ran at
 * 0x889A6): attack_target_find(the player, the heading h = the yaw plus
 * the column's Aim) with X21's radius (bytes param
 * player_model_seek_radius_at, its VA) at float param
 * player_model_seek_range (14 m, distance less radius) for the call;
 * when it counted one and the one it kept (the smallest |bearing - h|
 * in range, wrapped: the result's +0x14) is within float param
 * player_model_seek_cone (45 degrees) of h, the yaw := its bearing (the
 * result's +0x10) less the Aim: the game's own B, from a farther
 * search; and into PC+0x90, the next search's heading (input+0x38,
 * 0x8529D), which both callers set to the yaw just before
 * player_attack_enter (0x88D92, 0x88FCC), so a held chain whose target
 * dies keeps the turned heading.  So the body faces the target from the attack's first tick,
 * and with it whatever rides its markers: the hit box (m_damage, X3's
 * and X13's box) and the effects bound to them (beamlord's lightning).
 * Then the game's load.
 *
 * ABI.  0x88A3A: `mov eax, [edi+0x138]` (6 bytes: the CALL and a NOP).
 * EDI the PlayerControl, EBX the input, EDX the new state (0x88A40
 * stores it); ECX (0x88A63) and ESI (0x88A54) are written before they
 * are read again, and the x87 stack is empty.  The entry keeps EBX, ECX,
 * EDX, ESI, EDI and EBP and returns with EAX the yaw.  The C helper is
 * cdecl; x87 and SSE1 only (AZ-021).
 */

#include "azurik_vanilla.h"   /* attack_target_find; and azurik.h: the params */

#define PC_CRITTER    0x020   /* PlayerControl -> its critter                */
#define PC_AIM        0x0E8   /* the playing column's Aim angle, degrees      */
#define PC_COLUMN     0x134   /* the attacks_anims column it plays           */
#define PC_HEADING    0x090   /* the next search's heading: the yaw's copy  */
#define PC_YAW        0x138   /* the swing's yaw                             */
#define CR_SLOT       0x200   /* critter: the anim slot anim_change took     */
#define SLOT_ATTACK   0x52    /* an attack column's slot: 0x52 + it          */
#define COLUMNS       24
#define FOUND_WORDS   14      /* the finder's 0x38-byte result               */
#define FOUND_COUNT   0       /* +0x00 how many it counted in range (int)    */
#define FOUND_BEARING 4       /* +0x10 the kept one's bearing (float)        */
#define FOUND_OFF     5       /* +0x14 |its bearing - h|, wrapped (float)    */
#define EMPTY         1e5f    /* an empty Aim angle (0x198198)               */
#define DEGREE        0.0174532925f

AZURIK_FLOAT_PARAM(player_model_seek_columns, 0.0f);
AZURIK_FLOAT_PARAM(player_model_seek_range, 14.0f);
AZURIK_FLOAT_PARAM(player_model_seek_cone, 45.0f);
AZURIK_BYTES_PARAM(player_model_seek_radius_at, 4);

__attribute__((used))
void seek_turn(char *pc)
{
    int column = *(const int *)(pc + PC_COLUMN);
    char *critter = *(char **)(pc + PC_CRITTER);
    float *radius = *(float *const volatile *)player_model_seek_radius_at;
    float aim = *(const float *)(pc + PC_AIM);
    float turn, was = 0.0f;
    int found[FOUND_WORDS];

    if (column < 0 || column >= COLUMNS || !(((int)player_model_seek_columns >> column) & 1) || !critter
            || *(const int *)(critter + CR_SLOT) != SLOT_ATTACK + column)
        return;
    turn = aim == EMPTY ? 0.0f : aim * DEGREE;
    if (radius) {
        was = *radius;
        *radius = player_model_seek_range;
    }
    attack_target_find(critter, *(const float *)(pc + PC_YAW) + turn, found);
    if (radius)
        *radius = was;
    if (found[FOUND_COUNT] > 0 && ((const float *)found)[FOUND_OFF] <= player_model_seek_cone * DEGREE) {
        float yaw = ((const float *)found)[FOUND_BEARING] - turn;
        *(float *)(pc + PC_YAW) = yaw;
        *(float *)(pc + PC_HEADING) = yaw;
    }
}

/* 0x88A3A: the seek, then the game's `mov eax, [edi+0x138]`. */
__attribute__((naked))
void c_player_model_seek(void)
{
    __asm__ volatile (
        "pushl %%ecx                         \n\t"
        "pushl %%edx                         \n\t"
        "pushl %%edi                         \n\t"
        "calll _seek_turn                    \n\t"
        "addl $4, %%esp                      \n\t"
        "popl %%edx                          \n\t"
        "popl %%ecx                          \n\t"
        "movl 0x138(%%edi), %%eax            \n\t"
        "retl                                \n\t"
        : : : "memory");
}
