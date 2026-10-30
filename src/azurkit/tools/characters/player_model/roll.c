/* X4: the roll moves a player model whose roll clip has no root motion
 * (Step 2.21b; D112, AZ-284).
 *
 * The roll is BLACK's attack move 'roll forward' (config.xbr
 * attacks_anims entry 20).  Every tick player_attack_root_motion
 * (0x8C630) asks the root-motion sampler 0xCACD0 how far the active
 * clip's m_feet node moves between the clip times t0 and t1 = t0 +
 * Rate x dt, multiplies that by 30 (1/dt; 60 under fps_unlock), turns
 * it by the heading (0xA1420) and hands it to gravity_integrate_raw
 * (0x85700; roll_speed_scale's hook at 0x8C745).  garret4's
 * roll_forward moves m_feet 4.07 m forward; a model's own clip (W3
 * plays its run, walk or idle) moves it 0, so the roll ended but didn't
 * move (xemu sitting swapb: 0.003-0.005 m against garret4's 3.05 m).
 *
 * This shim replaces the 5-byte CALL 0xCACD0 at 0x8C6AE.  During
 * 'roll forward' it returns garret4's m_feet displacement over the same
 * fraction of the clip, [t0/L, t1/L] of garret4's 1.1666666 s, L the
 * playing clip's length: garret4's distance in the model's own roll
 * time (D112: the model's own clip speed).  Any other move, or a clip
 * with no length, goes to 0xCACD0 unchanged.
 *
 * At entry (the CALL's stack and registers, kept by 0xCACD0's ABI):
 *
 *   [ESP + 0x04]  the anim object      ESI  float out[3]
 *   [ESP + 0x08]  the node name        EDI  the active clip ('banm')
 *   [ESP + 0x0C]  t0                   EBX, EBP  the caller's
 *   [ESP + 0x10]  t1
 *   [ESP + 0x1B8] the entity: player_attack_root_motion's first
 *                 argument.  Its frame is SUB ESP,0x190 and four
 *                 pushes, so its argument sits at [ESP + 0x1A4] in its
 *                 body (0x8C733), +0x10 for the CALL's four pushes and
 *                 +4 for the CALL's return address.  Both of its
 *                 callers pass the entity first (0x88A6A, 0x8C7F1).
 *
 * The sampler returns out in EAX and pops its 16 bytes (RET 0x10); so
 * does this shim.  ESI, EDI, EBX and EBP are preserved.
 */

#include "azurik_vanilla.h"

#define ROLL_FORWARD 20     /* entity+0x134 during 'roll forward' */
#define ATTACK(entity) (*(const int *)((const char *)(entity) + 0x134))
#define CLIP_LENGTH(clip) (*(const float *)((const char *)(clip) + 0x10))

/* garret4's roll_forward m_feet track (characters.xbr, 'banm'
 * characters/garret4/roll_forward, the node's component 1, forward;
 * components 0 and 2 have no track, so they never move): each key's
 * time (s), value (m), in- and out-tangent (m/s).  Its pre- and
 * post-infinity modes are 0: before the first key it holds the first
 * value, after the last the last. */
#define G4_KEYS 8
static const float g4_roll[G4_KEYS][4] = {
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
    {0.0f, 0.0f, 0.0f, 0.0f},
};
#define G4_LENGTH 1.16666663f   /* the clip's length: its last key */

/* garret4's m_feet forward position t seconds into roll_forward, as the
 * game's key-track evaluator 0xD8300 computes it: a cubic Hermite
 * between the keys around t, its tangents scaled by the keys' spacing. */
static float g4_feet(float t)
{
    int k = 0;
    float dt, s, p0, p1, m0, m1, d;

    if (t <= g4_roll[0][0])
        return g4_roll[0][1];
    if (t >= g4_roll[G4_KEYS - 1][0])
        return g4_roll[G4_KEYS - 1][1];
    while (t >= g4_roll[k + 1][0])
        k++;
    dt = g4_roll[k + 1][0] - g4_roll[k][0];
    s = (t - g4_roll[k][0]) / dt;
    p0 = g4_roll[k][1];
    p1 = g4_roll[k + 1][1];
    m0 = dt * g4_roll[k][3];
    m1 = dt * g4_roll[k + 1][2];
    d = p0 - p1;
    return (((d + d + m1 + m0) * s + ((p1 - p0) * 3.0f - (m0 + m0) - m1)) * s + m0) * s + p0;
}

/* Write garret4's roll displacement for the clip window [t0, t1] into
 * out and return 1 during 'roll forward' on a clip with a length;
 * else return 0 and write nothing. */
__attribute__((used))
int roll_feet_delta(const void *entity, const void *clip, float t0, float t1, float *out)
{
    float scale;

    if (ATTACK(entity) != ROLL_FORWARD || !clip || !(CLIP_LENGTH(clip) > 0.0f))
        return 0;
    scale = G4_LENGTH / CLIP_LENGTH(clip);
    out[0] = 0.0f;
    out[1] = g4_feet(t1 * scale) - g4_feet(t0 * scale);
    out[2] = 0.0f;
    return 1;
}

__attribute__((naked))
void c_player_model_roll(void)
{
    __asm__ volatile (
        "movl 0x1b8(%%esp), %%eax  \n\t"   /* the entity */
        "pushl %%esi               \n\t"   /* out */
        "pushl 0x14(%%esp)         \n\t"   /* t1 */
        "pushl 0x14(%%esp)         \n\t"   /* t0 */
        "pushl %%edi               \n\t"   /* the clip */
        "pushl %%eax               \n\t"
        "calll _roll_feet_delta    \n\t"
        "addl $20, %%esp           \n\t"
        "testl %%eax, %%eax        \n\t"
        "jz 1f                     \n\t"
        "movl %%esi, %%eax         \n\t"
        "retl $16                  \n\t"
        "1:                        \n\t"
        "jmp \"_anim_root_motion_delta@16\"\n\t"
        : : : "memory"
    );
}
