/* X26: a baked body drawn at a model scale stays on the floor as it
 * settles into its stance after a ladder's top (Step 2.116, D286's
 * limit 2; D115's default: X23's builds only).
 *
 * Why.  critter_model_matrix (0x42200) places the drawn origin at the
 * glide origin (0x42070) plus 0x402E0's aligned-node term (the CALL at
 * 0x42253, added by 0xA36E0 at 0x4225A), unscaled: the node named at
 * +0x1F8 in the clip at the top layer's time less the same node in the
 * blended pose.  In a crossfade it holds the drawn body where the old
 * pose put the node, which keeps garret4 still at x1 as climb_up_edge
 * turns into his stance: state 0's walk places m_feet (0x866D9's
 * 0x42E40, unscaled) and the term holds back 1 x his climb pose's m_feet.
 * The bones are drawn x D (+0x188), so on a body drawn D times its model
 * the hold is (D - 1) x m_feet short: X23's lowered glide end comes
 * undone in one tick, the drawn body popping up (D - 1) x 2.647 m (3.0 m
 * at town_male_6 x2, 7.9 m computed at keylord own x2) and sinking back
 * over the crossfade (sitting 2.107 C) [verified static: capstone].
 *
 * What.  This shim replaces that CALL.  It calls the game's 0x402E0; for
 * the player's species (flag 0x20) with a PlayerControl (+0x180) whose
 * hold is on, it multiplies the term by the critter's drawn scale, so the
 * drawn body stays where X23 put it, its feet on the floor, as the pose
 * settles.  The hold comes on in move state 0 (+0x94) right after
 * climb_up_edge (the call before saw the 0x100 bit with +0x200 0x3F:
 * player_model_stance_edge, this object's own), or after a hoist (0x41,
 * 0x42: X23 ends it on the ledge's floor the same way, Step 2.127,
 * AZ-572), when the aligned node is
 * "m_feet" and the term is longer than 1 mm, stays on in any state while
 * both hold (a jump, an attack or a hit in the crossfade keeps m_feet:
 * 0x89278, 0x8D66B's 0x42750), and goes off otherwise
 * (player_model_stance_held).  Every other crossfade keeps the game's
 * term: the step-up's end (0x100, anim 53), a landing (the zipline's end
 * and let-go), an attack's end, the walk and run changes, where scaling
 * it moved the drawn body (D - 1) x the term in one tick (0.84 m at
 * keylord own x2's step-up end: sitting 2.116's skeptic), and the ladder
 * latches (node m_grab).  The camera shim X8 keeps the
 * same hold for its point (eye.c).  The build installs it exactly where
 * X23 is but on a body with no clips (Step 2.127: its root rides
 * m_feet / D, so the game's term already holds it): without X23's
 * lowered glide end the scaled term would drop the body (D - 1) x
 * m_feet at the switch.
 *
 * The climb-over's glide (Step 2.175b, AZ-529 (c)).  X23 moves
 * climb_up_edge's glide ends to the drawn scale, but between them the
 * clip's own pose rises over its origin x D: keylord own x2 (D 4) drew
 * its lowest point up to 2.86 m over the top floor 8 ticks into the
 * glide, where garret4's stays within 0.05 m of it (sitting 2.175b on
 * main; sitting 2.106 2.87 m).  Where the build writes
 * player_model_stance_glide_on (1, with player_model_stance_glide_end the
 * clip's lowest bone at its end over its origin, model units), in that
 * glide (state 0x100, +0x200 0x3F, +0x19C 2) the drawn lowest point (the
 * glide origin 0x42070 gives plus the term plus D x the lowest posed
 * bone: the pose being drawn) is held no higher than the glide's end
 * puts it (+0x1BC plus D x that end bone: the top floor, X23's end), the
 * term lowered by the excess; under it, the game's.  So the body goes
 * over the top with its lowest point on the floor at most, as garret4's.
 *
 * ABI: at the CALL EAX is the critter (0x42251) and EDI the term's out
 * (0x4224A); 0x402E0 takes those, keeps ESI and EDI and returns EAX =
 * EDI, and 0x42200 reads ESI (its matrix) and then EAX and ECX (0xA36E0)
 * next.  The stub keeps EBX, ESI, EDI and EBP, clobbers ECX and EDX as
 * 0x402E0 does, leaves the x87 stack empty and returns EAX = EDI with a
 * plain RET.
 */

#include "azurik_vanilla.h"

#define CR_SPECIES   0x178   /* critter -> its species                     */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl (the player's) */
#define CR_SCALE     0x188   /* critter: the scale its model is drawn at   */
#define CR_NODE      0x1F8   /* critter: the aligned node's name           */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                       */
#define CR_MOVE_ANIM 0x200   /* critter: the aligned move's anim (0x42430)  */
#define PC_STATE     0x094   /* PlayerControl: its move state              */
#define CLIMB_STATE  0x100   /* the climb-over's move state bit            */
#define UP_EDGE      0x3F    /* climb_up_edge                              */
#define HOIST        0x41    /* hoist                                      */
#define HOIST_WAIST  0x42    /* hoist_waist                                */
#define HELD_MIN     1e-6f   /* (1 mm)^2: a shorter term is no crossfade   */
#define CR_ANIM      0x17C   /* critter -> its anim object                 */
#define CR_MODE      0x19C   /* critter: 0x42E40's glide mode, 2 gliding    */
#define CR_GLIDE_END 0x1BC   /* critter: the glide's end                    */
#define GLIDING      2
#define AN_BODY      0x000   /* anim object -> its body (+0: its bones)    */
#define AN_BONES     0x008   /* anim object -> its posed bones            */
#define BONE_SIZE    0xB0    /* one posed bone                            */
#define BONE_Z       0xA8    /* its matrix's translation z (model units)   */

int player_model_stance_held __attribute__((used));   /* 1: the stance's hold is on */
int player_model_stance_edge __attribute__((used));   /* 1: the last call saw climb_up_edge or a hoist */

static const char feet_name[7] = "m_feet";

/* 1: the climb-over's glide is held (Step 2.175b); its clip's lowest bone
 * at its end over its origin, model units.  Written by the build. */
AZURIK_FLOAT_PARAM(player_model_stance_glide_on, 0.0f);
AZURIK_FLOAT_PARAM(player_model_stance_glide_end, 0.0f);

/* The climb-over's glide: the term lowered so the drawn lowest point is
 * no higher than the glide's end puts it. */
static void glide_hold(char *critter, float *term)
{
    const char *anim = *(const char *const *)(critter + CR_ANIM);
    const char *bones = anim ? *(const char *const *)(anim + AN_BONES) : 0;
    const char *body = anim ? *(const char *const *)(anim + AN_BODY) : 0;
    int n = body ? *(const int *)body : 0, b;
    float at[3], k = *(const float *)(critter + CR_SCALE), low = 0.0f, z, top;

    if (!bones || n <= 0)
        return;
    for (b = 0; b < n; b++) {
        z = *(const float *)(bones + BONE_SIZE * b + BONE_Z);
        if (b == 0 || z < low)
            low = z;
    }
    glide_origin(critter, at);
    top = *(const float *)(critter + CR_GLIDE_END + 8) + k * player_model_stance_glide_end;
    low = at[2] + term[2] + k * low;
    if (low > top)
        term[2] -= low - top;
}

static int is_feet(const char *name)
{
    int i;

    for (i = 0; i < 7; i++)
        if (name[i] != feet_name[i])
            return 0;
    return 1;
}

/* After the game's 0x402E0 wrote the term: scale it while the hold is on. */
__attribute__((used))
void stance_term(char *critter, float *term)
{
    const char *species = *(const char *const *)(critter + CR_SPECIES);
    const char *control, *node;
    float k;
    int i, held, state, anim;

    if (!species || !(*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG))
        return;
    control = *(const char *const *)(critter + CR_CONTROL);
    node = *(const char *const *)(critter + CR_NODE);
    state = control ? *(const int *)(control + PC_STATE) : 0;
    held = control && ((state == 0 && player_model_stance_edge) || player_model_stance_held)
        && node && is_feet(node)
        && term[0] * term[0] + term[1] * term[1] + term[2] * term[2] > HELD_MIN;
    player_model_stance_held = held;
    anim = *(const int *)(critter + CR_MOVE_ANIM);
    player_model_stance_edge = control && (state & CLIMB_STATE)
        && (anim == UP_EDGE || anim == HOIST || anim == HOIST_WAIST);
    if (!held) {
        if (player_model_stance_glide_on > 0.0f && control && (state & CLIMB_STATE) && anim == UP_EDGE
                && *(const int *)(critter + CR_MODE) == GLIDING)
            glide_hold(critter, term);
        return;
    }
    k = *(const float *)(critter + CR_SCALE);
    for (i = 0; i < 3; i++)
        term[i] *= k;
}

/* 0x42253 in critter_model_matrix (0x42200): the CALL of 0x402E0 (EAX
 * the critter, EDI the out; a plain RET, EAX = EDI). */
__attribute__((naked))
void c_player_model_stance_term(void)
{
    __asm__ volatile (
        "pushl %%eax                  \n\t"   /* the critter, kept */
        "calll _aligned_node_offset   \n\t"
        "popl %%eax                   \n\t"
        "pushl %%edi                  \n\t"   /* the term */
        "pushl %%eax                  \n\t"
        "calll _stance_term           \n\t"
        "addl $8, %%esp               \n\t"
        "movl %%edi, %%eax            \n\t"   /* as 0x402E0 returns */
        "retl                         \n\t"
        : : : "memory"
    );
}
