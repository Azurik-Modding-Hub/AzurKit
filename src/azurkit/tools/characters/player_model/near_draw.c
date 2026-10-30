/* X27: a tiny player body is drawn with the level camera near its
 * collision centre (Step 2.116, AZ-541; D115's default: only under half
 * garret4's size).
 *
 * Why.  The critter camera-pass draw 0x3EA00 skips a critter whose box
 * centre (the draw list's entry+8, its distance to the render eye) is
 * under 1.0 m from the eye (0x3EA69 and 0x3EC6B, [0x1A250C]) and fades
 * it by 2(d - 1) up to 1.5 m (0x3ECA7), while "movie mode" is off
 * ([[0x380E04]+4] == 0) under the level camera.  The player's box centre
 * is +0x15C, garret4's collision centre, 1.0 m over the drawn feet at
 * any drawn size, so X25's rig at its 0.1 floor brings the eye 0.70-0.91
 * m from it at rest and the body isn't drawn at all, only its shadow and
 * its armor (sitting 2.107 B: T6g4x0.1, splinter, firefly and
 * water_tentacle3 own; 6802 shadow-only ticks against 280 drawn with the
 * eye under 0.95 m from the centre) [verified static: capstone].
 *
 * What.  Two hooks, each its own copy of this object, at the two 9-byte
 * loads of the movie-mode flag: 0x3EA57 (mov edx, [cvar]; mov eax,
 * [edx + 4]) and 0x3EC58 (mov ecx, [cvar]; mov ecx, [ecx + 4]), each a
 * CALL and 4 NOPs.  Each loads the flag as the game did (the cvar
 * record's address is the build's bytes param player_model_movie_cvar,
 * read from the image's own instruction: USA 0x380E04, Europe
 * 0x382DA4), and when it is 0 and the critter (ESI at both: 0x3EA24,
 * 0x3EC2A) is the player by the game's own test, [[critter+0x154]+0xC0]
 * == critter (0x3EC8A), gives 1: the movie-mode branch skips both near
 * exits and the fade (0x3ECA0 tests the same ECX), so the player's body
 * is drawn opaque however near the eye.  Every other critter keeps the
 * 1.0 m hide and the fade.  The build installs it when X25's rig scale
 * is under 0.5: there the 1 m sphere round a centre at or over the drawn
 * top covers where the rig rightly orbits; from 0.5 the game's hide
 * stays, as for garret4 (it hides him only with the camera in his body).
 *
 * ABI: site 1 returns in EAX and keeps ECX (&entry) and EDX as vanilla
 * left it ([cvar]); site 2 returns in ECX and keeps EAX and EDX; both
 * keep EBX, ESI, EDI and EBP and return with a plain RET.  The caller's
 * compare follows each site, so the flags needn't survive.
 */

#include "azurik.h"   /* AZURIK_BYTES_PARAM */

AZURIK_BYTES_PARAM(player_model_movie_cvar, 4);

/* 0x3EA57 in 0x3EA00: the flag into EAX. */
__attribute__((naked))
void c_player_model_near_draw(void)
{
    __asm__ volatile (
        "movl _player_model_movie_cvar, %%edx \n\t"   /* the cvar record's address */
        "movl (%%edx), %%edx                  \n\t"   /* [cvar], as vanilla leaves EDX */
        "movl 4(%%edx), %%eax                 \n\t"   /* movie mode */
        "testl %%eax, %%eax                   \n\t"
        "jnz 1f                               \n\t"
        "pushl %%ecx                          \n\t"   /* &entry, kept */
        "movl 0x154(%%esi), %%ecx             \n\t"   /* the critter's world */
        "testl %%ecx, %%ecx                   \n\t"
        "jz 2f                                \n\t"
        "cmpl %%esi, 0xc0(%%ecx)              \n\t"   /* the player? */
        "jne 2f                               \n\t"
        "movl $1, %%eax                       \n\t"
        "2:                                   \n\t"
        "popl %%ecx                           \n\t"
        "1:                                   \n\t"
        "retl                                 \n\t"
        : : : "memory"
    );
}

/* 0x3EC58 in 0x3EA00: the flag into ECX. */
__attribute__((naked))
void c_player_model_near_fade(void)
{
    __asm__ volatile (
        "movl _player_model_movie_cvar, %%ecx \n\t"
        "movl (%%ecx), %%ecx                  \n\t"
        "movl 4(%%ecx), %%ecx                 \n\t"   /* movie mode */
        "testl %%ecx, %%ecx                   \n\t"
        "jnz 1f                               \n\t"
        "pushl %%eax                          \n\t"   /* kept */
        "movl 0x154(%%esi), %%eax             \n\t"   /* the critter's world */
        "testl %%eax, %%eax                   \n\t"
        "jz 2f                                \n\t"
        "cmpl %%esi, 0xc0(%%eax)              \n\t"   /* the player? */
        "jne 2f                               \n\t"
        "movl $1, %%ecx                       \n\t"
        "2:                                   \n\t"
        "popl %%eax                           \n\t"
        "1:                                   \n\t"
        "retl                                 \n\t"
        : : : "memory"
    );
}
