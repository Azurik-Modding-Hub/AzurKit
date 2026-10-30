/* X23: a baked body drawn at a model scale goes over the ladder's top
 * onto the floor (Step 2.106, AZ-529's ladder; D115's default: only away
 * from x1, so x1's builds keep their bytes), and ends a hoist on the
 * ledge's floor (Step 2.127, AZ-572).
 *
 * Why.  climb_up_edge (anim 0x3F, state 0x100: the top dismount
 * 0x87950's setter call at 0x87F47) is an aligned move: 0x42430 glides the drawn
 * origin from +0x1B0 to +0x1BC over the move's window (0x42070 draws
 * the straight-line blend while +0x19C, the glide mode, is 2).  Its
 * start is 0x41E50's world place of the start node, m_grab (every latch
 * sets +0x1FC to it: 0x870AC, 0x873FC, 0x878DE), which multiplies the
 * node by the critter's scale (+0x188, at 0x41E97), less the new clip's
 * m_grab at t0 unscaled; its end is the ledge's target less the clip's
 * m_feet at t1, unscaled.  So a body drawn D times its model (a baked
 * body: garret4's clips and markers on its rig, Step 2.87) starts the
 * move (D - 1) x his m_grab too high (sitting 2.105: town_male_6 own x2,
 * D 2.3, its +0x1B0 2.950 m over the control's, 1.3 x 2.269) and ends it with its drawn feet (D - 1) x his m_feet over the floor,
 * then drops into its stance (1.8-3.1 m over the top floor, 2.95 m in a
 * tick at x2) [verified static; the start to the mm].
 *
 * What.  This shim takes the CALL of 0x8C080 (the state's landing, EAX
 * the PlayerControl, two stack arguments, RET 8) at 0x87F65, right after
 * that setter and its rate (0x87F55).  For the player's species (flag
 * 0x20) in state 0x100 (PlayerControl +0x94) whose aligned move is
 * climb_up_edge (+0x200 0x3F), gliding (+0x19C 2), at a scale D other
 * than 1 (+0x188): the glide's start moves down by (D - 1) x garret4's
 * m_grab at the clip's start and its end by (D - 1) x his m_feet at its
 * end, each turned by the critter's turn (+0x18C) with the game's
 * 0xA1420, so the drawn grab starts where the climb held it and the
 * drawn feet end on the floor, as x1's do.  Then the game's 0x8C080.
 * The build installs it on a baked body drawn at a model scale other
 * than 1; X9's bodies glide on garret4's offsets with no markers of
 * their own, which the game doesn't scale.
 *
 * The hoist (Step 2.127, AZ-572).  0x86920 (from the airborne tick
 * 0x897A0 and the swim tick 0x8BAC6) sets state 0x100 with hoist (anim
 * 0x41, a tall ledge) or hoist_waist (0x42) through the same setter
 * (0x86D91), its rate (0x86D9E) and the same landing CALL at 0x86DAE.
 * Its aligned nodes are m_feet both, so the glide ends at the ledge less
 * the clip's m_feet at t1 unscaled while the bones are drawn x D: the
 * drawn feet ended (D - 1) x his m_feet off the floor (garret4 x2 +1.68
 * m, x0.5 -0.90, keylord own x2 +5.05: sitting 2.123's h65).  The second
 * landing moves that end by (D - 1) x his m_feet at the clip's end, the
 * same turn and gates; a hoist's start stays the game's (its start node
 * m_feet is sampled on the clip playing, the jump's at most 0.1 m and
 * swim_start's 0.41 m off, x (D - 1)).  The build lands it on the same
 * bodies but one with no clips.
 *
 * A body with no clips (Step 2.127, AZ-562).  Its timers' root bone
 * rides garret4's m_feet / D (retarget.py's bake), so the game's
 * unscaled ends already put the drawn prop at its entity and only the
 * start term is owed (0x41E50 scales the start node): the build writes
 * player_model_over_feet_k 0 there (1 elsewhere), which takes every end
 * term off.
 *
 * ABI: the stub keeps EAX for 0x8C080 (which reads no ECX or EDX
 * before writing them), keeps EBX, ESI, EDI and EBP and leaves the x87
 * stack empty; 0x8C080 returns to 0x87F6A with its RET 8.  0xA1420
 * takes EAX = the quaternion, EDX = the vector and ESI = out (a plain
 * RET; it keeps ESI).
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

AZURIK_FLOAT_PARAM(player_model_over_feet_k, 1.0f);   /* the end term's share: 0 on a body with no clips */

#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define PC_STATE     0x094   /* PlayerControl: its move state             */
#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_SCALE     0x188   /* critter: the scale its model is drawn at  */
#define CR_TURN      0x18C   /* critter: its turn (a quaternion)          */
#define CR_MODE      0x19C   /* critter: 0x42E40's glide mode, 2 gliding   */
#define CR_ORIGIN    0x1B0   /* critter: the glide's start                 */
#define CR_GLIDE_END 0x1BC   /* critter: the glide's end                   */
#define CR_MOVE_ANIM 0x200   /* critter: the aligned move's anim (0x42430) */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define CLIMB_STATE  0x100   /* the ladder's move state                   */
#define UP_EDGE      0x3F    /* climb_up_edge                             */
#define GLIDING      2

#define HOIST        0x41    /* hoist (a tall ledge)                      */
#define HOIST_WAIST  0x42    /* hoist_waist (a waist-high one)            */

/* garret4's m_grab in climb_up_edge (constant over the clip: two equal
 * keys) and his m_feet at the end of each move this corrects, model
 * units: x right, y forward, z up.  climb_up_edge's m_feet is constant
 * too; a hoist's rises from about its start (0x41: (0, -0.003, 0.111),
 * 0x42: (0, 0.211, -0.192)) to these. */
static const float g4_grab[3] = {0.0f, 0.596712828f, 2.26866341f};
static const float g4_feet[3] = {0.0f, 1.36404443f, 2.26890564f};
static const float g4_hoist_feet[3] = {0.0f, 1.22300005f, 1.77436328f};
static const float g4_waist_feet[3] = {0.0f, 0.701313615f, 1.00312757f};

static int is_player(const char *critter)
{
    const char *species = *(const char *const *)(critter + CR_SPECIES);

    return species && (*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) != 0;
}

/* out := v turned by the quaternion turn, by the game's 0xA1420. */
__attribute__((naked, noinline, used))
static void turned(const float *turn, const float *v, float *out)
{
    __asm__ volatile (
        "pushl %%esi             \n\t"
        "movl 0x8(%%esp), %%eax  \n\t"   /* the turn   */
        "movl 0xc(%%esp), %%edx  \n\t"   /* v          */
        "movl 0x10(%%esp), %%esi \n\t"   /* out        */
        "calll _quat_rotate      \n\t"
        "popl %%esi              \n\t"
        "retl                    \n\t"
        : : : "memory"
    );
}

/* point -= k x v turned by turn. */
static void step_back_by(float *point, const float *turn, const float *v, float k)
{
    float kv[3], off[3];
    int i;

    for (i = 0; i < 3; i++)
        kv[i] = k * v[i];
    turned(turn, kv, off);
    for (i = 0; i < 3; i++)
        point[i] -= off[i];
}

/* After climb_up_edge's or a hoist's setter: its glide's ends at the
 * drawn scale (a hoist's start is m_feet on the airborne or swim clip,
 * left as the game puts it). */
__attribute__((used))
void over_top(const char *control)
{
    char *critter = control ? *(char *const *)(control + PC_CRITTER) : 0;
    const float *feet;
    float k;
    int anim;

    if (!critter || !is_player(critter) || *(const int *)(control + PC_STATE) != CLIMB_STATE
            || *(const int *)(critter + CR_MODE) != GLIDING)
        return;
    anim = *(const int *)(critter + CR_MOVE_ANIM);
    if (anim == UP_EDGE)
        feet = g4_feet;
    else if (anim == HOIST)
        feet = g4_hoist_feet;
    else if (anim == HOIST_WAIST)
        feet = g4_waist_feet;
    else
        return;
    k = *(const float *)(critter + CR_SCALE) - 1.0f;
    if (!(k != 0.0f))
        return;
    if (anim == UP_EDGE)
        step_back_by((float *)(critter + CR_ORIGIN), (const float *)(critter + CR_TURN), g4_grab, k);
    if (player_model_over_feet_k != 0.0f)
        step_back_by((float *)(critter + CR_GLIDE_END), (const float *)(critter + CR_TURN), feet,
                     k * player_model_over_feet_k);
}

/* 0x87F65 in the top dismount (0x87950) and 0x86DAE in the hoist
 * (0x86920): the CALL of 0x8C080 (EAX the PlayerControl; two stack
 * arguments, RET 8). */
__attribute__((naked))
void c_player_model_over_top(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"   /* the PlayerControl, kept */
        "pushl %%eax              \n\t"
        "calll _over_top          \n\t"
        "addl $4, %%esp           \n\t"
        "popl %%eax               \n\t"
        "jmp _player_landing@8    \n\t"
        : : : "memory"
    );
}
