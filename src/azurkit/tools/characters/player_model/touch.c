/* X34: a player body touches pickups at its size (Step 2.133; D344,
 * D356, the owner: "a leg is touching a pickup but it is not
 * collected").
 *
 * Why.  The player's tick 0x8C520 asks collision_sweep (0x60870) for
 * what an ellipsoid round the body's centre (+0x15C..+0x164, garret4's
 * 1 m over the feet at every drawn size) touches: horizontal radius
 * arg 6, vertical arg 7, both the one constant [0x1980BC] (1.0, its
 * only reader, the MOV EDX at 0x8C553, pushed twice at 0x8C55E and
 * 0x8C55F; 0x60870 widens the box by arg 6 in x and y and arg 7 in z
 * at 0x60913-0x60975, and 0x418B0 takes an item when the centre is in
 * the ellipsoid R = r + arg 6, Z = r a + arg 7 round it, 0x4195E and
 * 0x41968).  So a body drawn x8 touched what garret4 does (kingkong own:
 * its leg on a gem 5 m from its centre, nothing).
 *
 * What.  This shim replaces those 13 bytes (MOV EDX, [0x1980BC]; PUSH
 * 0x80; PUSH EDX; PUSH EDX) with a CALL and 8 NOPs.  It pops its return
 * (the NOPs, then 0x8C560's LEA EDX, which overwrites EDX), pushes the
 * mask 0x80 as the game does, player_model_touch_z and
 * player_model_touch_xy, so the stack is as the game's, and rewrites
 * ECX, the centre's z bits 0x8C548 loaded and 0x8C56A stores, as
 * +0x164 + player_model_touch_dz.  The build writes, for the body's
 * size s (its drawn height over garret4's): above 1 xy = s, z = sqrt(s),
 * dz = 0 (the centre garret4's: the critique's rule S, which contains
 * x1's test and reaches sqrt(s) - 1 + r a under the feet, 0.46 m at x2,
 * where z = s would reach s - 1 + r a, 1.05 m); below 1 xy = z = s and
 * dz = s - 1 (the centre feet + s, so an item resting on the floor stays
 * touchable at any size: |s - r a| <= r a + s).  Installed only off s 1.
 *
 * ABI: at the CALL EAX holds the entity (read again at 0x8C5CA and
 * 0x8C5D2), ECX the z bits, EDX &out (pushed at 0x8C552, overwritten at
 * 0x8C560); nothing up to 0x8C5DA reads EFLAGS.  The shim keeps EAX,
 * EBX, ESI, EDI and EBP, leaves the x87 stack empty and returns (a RET
 * to its own return address, pushed again) with the game's three pushes
 * made.
 */

#include "azurik.h"   /* AZURIK_FLOAT_PARAM */

AZURIK_FLOAT_PARAM(player_model_touch_xy, 1.0f);
AZURIK_FLOAT_PARAM(player_model_touch_z, 1.0f);
AZURIK_FLOAT_PARAM(player_model_touch_dz, 0.0f);

__attribute__((naked))
void c_player_model_touch(void)
{
    __asm__ volatile (
        "popl %%edx                          \n\t"   /* the return: the hook's NOPs */
        "pushl $0x80                         \n\t"   /* the query's mask, as the game's */
        "pushl _player_model_touch_z         \n\t"   /* arg 7: the vertical radius */
        "pushl _player_model_touch_xy        \n\t"   /* arg 6: the horizontal radius */
        "flds 0x164(%%eax)                   \n\t"   /* the centre's z */
        "fadds _player_model_touch_dz        \n\t"
        "pushl %%ecx                         \n\t"
        "fstps (%%esp)                       \n\t"
        "popl %%ecx                          \n\t"   /* its bits, which 0x8C56A stores */
        "pushl %%edx                         \n\t"
        "retl                                \n\t"   /* to the hook's NOPs, the game's pushes made */
        : : : "memory"
    );
}
