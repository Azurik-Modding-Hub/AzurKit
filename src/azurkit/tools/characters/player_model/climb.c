/* X9: a player model with no climb clips latches onto a ladder, climbs
 * it and leaves it as garret4 does (Step 2.63; D112, D219).
 *
 * The ladder's moves are aligned clip changes.  The move-state setter
 * 0x8BDB0 (its callers: the latch from a walk 0x86DD0, climb_start; from
 * a jump 0x87120, climb_from_jump; from the top 0x87470,
 * climb_down_edge; the top dismount 0x87950, climb_up_edge; the ledge
 * hoist from a walk 0x86920, hoist or hoist_waist; the step out of the
 * water 0x8B1D0, step_up) writes the state (0x100 or 0x101) and hands
 * the anim, the target, the turn and two node names to 0x42430.  That
 * plays the clip on a fresh layer from t0 to t1 and glides the model's
 * origin from where the start node is (+0x1B0) to where the end node
 * lands on the target (+0x1BC) (mode 2, +0x19C; 0x42070); the state's
 * attack bit clears when the clip ends, and the climb tick (state 1)
 * takes over.  But 0x42430 returns at 0x424AA when the species' slot
 * for the anim is -1, and only garret4's body has climb, hang and hoist
 * clips: every other body entered the state with no clip to end it,
 * stuck in it until a jump (the owner, of Balthazar: "he had trouble
 * latching onto the ladder").  The climb tick then asks for climb_idle,
 * climb_up, climb_down, climb_left or climb_right (anim_change, looping)
 * and places the model so that its m_grab marker sits on the rung
 * (0x42E40); a body without m_grab samples zero there, so its feet were
 * drawn where garret4's hands go, 2.27 m up.
 *
 * Seventeen hooks of this one source, each landed on its own:
 *
 * - c_player_model_climb_move, the setter's CALL 0x42430 at 0x8BDF3
 *   (__stdcall(36)), and since Step 2.66b the hard landing's two
 *   (touchdown, 0x8B0D4 and 0x8B18C, state 0x100) and the overhead
 *   hang's (hang_start, 0x8A4E3, state 0x105), which call 0x42430
 *   directly: with no clip there the state waited for whatever clip
 *   played to end (xemu 2.75a: balthazar and flicken locked 33-45+
 *   ticks after a hard landing against garret4's 13, flicken held in the
 *   hang 77+ ticks on a fidget).  For the player's species (the `player` flag 0x20
 *   in S+0x64) an empty slot plays the body's stand-in clip (below) for
 *   the call and is put back after, and the move lasts garret4's time:
 *   the window ends at t0 + (t1 - t0) x garret4's length over the
 *   stand-in's, and a shorter stand-in plays its whole window at its
 *   layer's rate x its length over his (AZ-489: it ended at its own end,
 *   a 2.93 s golem idle holding the hoist 59 ticks against his 89).  A
 *   stand-in has no m_grab, and its m_feet is the body's own, so the
 *   glide starts where the body is and ends with its m_feet on the
 *   target, where garret4's ends for climb_start, the hoists and step_up
 *   (his feet end there, his origin that clip's m_feet at t1 off it: zero for
 *   climb_start, (0, 1.223, 1.774) for hoist, (0, 0.701, 1.003) for
 *   hoist_waist, (0, 0.269, 0.261) for step_up); for climb_down_edge and
 *   climb_from_jump the target moves by garret4's m_feet at t1 (turned
 *   by the move's turn), so the glide ends at his origin, where the climb
 *   places him, and for climb_up_edge, whose end node is m_grab, by his
 *   m_grab less his m_feet, so it ends at his feet, where the walk
 *   places him.
 * - c_player_model_climb_rate, the CALL of 0x30940 (the active layer's
 *   rate := its argument; EAX the PlayerControl, +0x20 its critter;
 *   RET 4) that each of the setter's six callers makes right after it
 *   (0x86D9E hoist, 0x870F7 climb_start, 0x87444 climb_from_jump,
 *   0x87929 climb_down_edge, 0x87F55 climb_up_edge: 1.5, [0x1980E0];
 *   0x8B6CD step_up: from the speed): it writes the rate, x the
 *   stand-in's length over garret4's when the move 0x42430 just started
 *   (critter +0x200 the anim, +0x204 its clip, on the active layer)
 *   plays a stand-in shorter than his clip, so the rate the caller sets
 *   doesn't undo the setter's.  The direct calls set no rate after.
 * - c_player_model_climb_loop and c_player_model_climb_idle, the climb
 *   tick's CALLs of anim_change at 0x883CB (in 0x87F80: climb_idle, _up,
 *   _down, _left, _right) and 0x88733 (in 0x88490: climb_idle): for the
 *   player's species an empty slot loops the stand-in, as X6 does at the
 *   level start, and, whatever the slot holds (the build installs X9 only
 *   on a body without m_grab), the rung point the tick then hands 0x42E40
 *   with m_grab (its local at
 *   B + 0xA8, resp. B + 0x98, B the caller's ESP before the CALL's
 *   pushes; the turn 0x10 below it) moves by garret4's m_grab in that
 *   clip, turned by the turn the tick hands 0x42E40 with it: the body,
 *   which samples zero there, sits where garret4's origin does.
 * - The victories and the use (Step 2.103, AZ-444): the ground state's
 *   0x887D0 consumes the request (a victory 1-6, anim 0x4A + it; a use
 *   target, anim 0x51) and then drops the move when the species' slot is
 *   -1 (the CMP at 0x888C2, before state 0x100 and its CALL 0x42430 at
 *   0x88951), which X11 leaves empty on these bodies (the victories
 *   only where _player_victory.py gives none, Step 2.121).
 *   c_player_model_climb_use takes that CMP (CALL + 3 NOPs; EAX the anim,
 *   EDX the species, all three dead after): for the player's species
 *   with a stand-in the move plays; c_player_model_climb_move takes the
 *   CALL at 0x88951 (the stand-in in garret4's time, as at touchdown);
 *   and c_player_model_climb_immune takes the 9 bytes at 0x88958 that
 *   load the clip's length for the hit timer (critter +0x1E0, +0x1E4: no
 *   hit for the move's length) and returns garret4's length in ST0 for a
 *   stand-in (ECX isn't read after, the x87 stack empty on entry).
 * - c_player_model_climb_ride (Step 2.103, AZ-443), the zipline ride's
 *   (state 5, 0x8A510) CALL of anim_apply_translation (0x42E40) at
 *   0x8AB32, which puts the body's m_grab on the cable point each tick:
 *   a body without one (X9's) rode with its origin, its feet, on the
 *   cable, 3.7 m above where garret4 hangs.  For the player's species
 *   the point (a copy, not read after) moves down by garret4's m_grab in
 *   hang at t 0, turned by the ride's turn (ECX), so the body hangs
 *   where his origin does; EAX and ECX are kept for 0x42E40 (EDX it
 *   writes first).  And hang_start (0x8A4E3, above), whose target is the
 *   cable point on these bodies (0x84A40's hang_start entries are zero,
 *   its slot empty): its glide end (+0x1BC) := the target less garret4's
 *   m_grab at its end, turned by the move's turn, where his glide ends
 *   (with or without the body's own m_root), so the ride starts 0.494 m
 *   below it, as his does.
 *   A body drawn X times its size (the model scale, Step 2.98) hangs X
 *   times x1's offset below the cable (Step 2.104, AZ-526: neither
 *   0x42E40 nor 0x42430 reads the critter's scale, so the drawn body
 *   rode (X - 1) x its top higher): the ride moves the point by
 *   (X - G) x garret4's m_grab and hang_start's stand-in ends at the
 *   target less X x his end m_grab, where G (player_model_climb_grab) is
 *   1 when the game already hangs the body's own m_grab there (a baked
 *   body, which gains his) and 0 for X9's bodies; a clip of its own in
 *   hang_start's slot has (X - 1) x his end m_grab taken off the end the
 *   game glides it to.  On a baked body only the ride and hang landings
 *   are made, and only above or below x1.
 *
 * - c_player_model_climb_offsets (Step 2.63b; on every swapped body
 *   without garret4's m_root or his ladder clips), the PlayerPhysics
 *   constructor's CALL of player_move_offsets_init (0x84A40) at 0x84E59
 *   (__stdcall(4)): once per boot that samples m_root, m_feet and m_grab
 *   at both ends of each of the player's clips into three arrays the
 *   ladder latches (0x86DD0, 0x87120), the top moves (0x87470, 0x87950)
 *   and the overhead hang (0x8A200) read, zeros for a slot the body
 *   lacks or a marker it doesn't have; the latch sweeps for the rungs at
 *   m_grab's height over m_root at climb_start's start, and with zeros
 *   no swapped body latched (xemu 2.75a: 0x86DD0 returned 0 on the face
 *   garret4 latched on).  After it each ladder offset those read that it
 *   left (0, 0, 0) takes garret4's (g4_offsets), so the latch and the
 *   moves aim as his do.  The hang's two (hang_start's m_root and m_grab
 *   at its end: its target is the cable point plus their difference)
 *   stay as sampled: a body that leaves them zero aims hang_start at the
 *   cable point, which X9's hang_start and ride move to garret4's places
 *   (above).  The arrays'
 *   addresses are the build's (player_model_climb_offsets_at), as each
 *   release has them.
 *
 * The turns use the game's own 0xA1420 (quat_rotate), the one 0x42430
 * and 0x42E40 turn a marker by.
 *
 * The stand-in: the body's idle, else idle_1, else walk, else run, else
 * the clip W3 gave the roll (every body with clips has that one).
 * garret4's numbers are his body's (characters.xbr, characters/garret4):
 * each clip's length, and the m_grab and m_feet markers' keys, which are
 * constant over each of these clips (two equal keys).
 *
 * ABIs: 0x42430 is __stdcall(36) (the critter, the anim, the place, the
 * target, the turn, the end node, the next start node, t0 and t1; RET
 * 0x24; no register input) and the setter's RET 0x20 follows it.
 * anim_change is __stdcall(12), and neither climb caller reads EAX, ECX
 * or EDX after it; nor does any of the six after 0x30940 (each loads
 * EAX for its CALL of 0x8C080 next).  0xA1420 takes EAX = the
 * quaternion, EDX = the vector and ESI = out (a plain RET; it keeps
 * ESI).
 */

#include "azurik_vanilla.h"

#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_ANIM      0x17C   /* critter -> its anim object, or NULL       */
#define CR_WINDOW    0x1A0   /* critter: an aligned move's t1 - t0        */
#define CR_GLIDE_END 0x1BC   /* critter: where the glide ends the origin  */
#define CR_MOVE_ANIM 0x200   /* critter: the aligned move's anim (0x42430) */
#define CR_MOVE_CLIP 0x204   /* critter: its clip ('banm')                */
#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define SP_SLOTS     0x124   /* species: a clip handle per anim index      */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define AN_ACTIVE    0x010   /* anim: the active layer's index             */
#define AN_LAYERS    0x040   /* anim: three 0x40-byte layers               */
#define LY_CLIP      0x004   /* layer: its clip ('banm')                   */
#define LY_RATE      0x020   /* layer: its rate                            */
#define LY_END       0x024   /* layer: its end time, s                     */
#define CLIP_LENGTH  0x010   /* banm: its length, s                        */

#define NO_CLIP      (-1)
#define IDLE         1               /* base clip table indices      */
#define IDLE_1       2
#define WALK         8
#define RUN          9
#define CLIMB_IDLE   0x37            /* .. climb_right 0x3B          */
#define CLIMB_RIGHT  0x3B
#define DOWN_EDGE    0x3E            /* climb_down_edge, _up_edge,   */
#define FROM_JUMP    0x40            /* climb_from_jump              */
#define HANG_START   0x44            /* hang_start                   */
#define ROLL         (0x52 + 20)     /* attacks_anims 'roll forward' */

/* garret4's clip length (s) per aligned move X9 times: the setter's,
 * touchdown's, hang_start's and the victories' and use's. */
static const struct {
    unsigned char index;
    float length;
} g4_length[] = {
    {0x0B, 0.433333278f},   /* touchdown       */
    {0x35, 0.899999976f},   /* step_up         */
    {0x3C, 1.66666675f},    /* climb_start     */
    {0x3E, 3.0f},           /* climb_down_edge */
    {0x3F, 3.46666718f},    /* climb_up_edge   */
    {0x40, 0.800000012f},   /* climb_from_jump */
    {0x41, 4.4000001f},     /* hoist           */
    {0x42, 1.79999995f},    /* hoist_waist     */
    {0x44, 0.733333349f},   /* hang_start      */
    {0x4B, 2.33333325f},    /* victory_1       */
    {0x4C, 2.33333325f},    /* victory_2       */
    {0x4D, 4.0666666f},     /* victory_3       */
    {0x4E, 4.0666666f},     /* victory_4       */
    {0x4F, 3.66666675f},    /* victory_5       */
    {0x50, 5.26666689f},    /* victory_6       */
    {0x51, 1.39999998f},    /* use             */
};

/* garret4's length for an aligned move's anim, else 0. */
static float g4_time(int index)
{
    unsigned i;

    for (i = 0; i < sizeof(g4_length) / sizeof(g4_length[0]); i++)
        if (g4_length[i].index == index)
            return g4_length[i].length;
    return 0.0f;
}

/* What a stand-in's layer rate is multiplied by so that its whole window
 * lasts garret4's time when it is shorter than his clip: its length over
 * his; else 1 (a longer one's window ends early instead). */
static float slower(int index, const char *banm)
{
    float g = g4_time(index), length = *(const float *)(banm + CLIP_LENGTH);

    return g > 0.0f && length > 0.0f && length < g ? length / g : 1.0f;
}

/* garret4's m_grab in climb_idle, climb_up, climb_down, climb_left and
 * climb_right (model units: x right, y forward, z up). */
static const float g4_grab[CLIMB_RIGHT - CLIMB_IDLE + 1][3] = {
    {0.0f, 0.586924493f, 2.26900005f},
    {0.0f, 0.586924493f, 2.26900005f},
    {0.0f, 0.586924493f, 2.26900005f},
    {0.0f, 0.614494860f, 2.20000005f},
    {0.0f, 0.645374954f, 2.20000005f},
};

/* What garret4's end node adds at t1 of climb_down_edge and
 * climb_from_jump (his m_feet: the glide ends at his origin, where the
 * climb places him), and of climb_up_edge (his m_grab less his m_feet:
 * it ends at his feet, where the walk places him). */
static const float g4_end[FROM_JUMP - DOWN_EDGE + 1][3] = {
    {0.0f, -0.0932982489f, 0.408657730f},
    {0.0f, -0.767331600f, -0.000242233f},
    {0.0f, 0.0135513749f, 0.0f},
};

/* garret4's m_grab at the end of hang_start (where his glide ends his
 * origin: the cable point less it, turned) and in hang at t 0 (where the
 * ride puts his origin each tick), model units. */
static const float g4_hang_end[3] = {0.0284325983f, 0.555833936f, 3.19920397f};
static const float g4_hang_grab[3] = {0.0814792067f, 0.464330018f, 3.69323754f};

/* The model scale X the body is drawn at, and G: 1 when the game puts the
 * body's own m_grab on the cable, else 0 (both written by the build on
 * the ride's and the hang's landings). */
AZURIK_FLOAT_PARAM(player_model_climb_scale, 1.0f);
AZURIK_FLOAT_PARAM(player_model_climb_grab, 0.0f);

/* player_move_offsets_init's arrays: m_root, m_feet and m_grab, each an
 * entry of two points (at t 0, at the clip's length) per clip slot. */
#define ROOT         0
#define FEET         1
#define GRAB         2
#define ENTRY        0x18

/* Their addresses in this release, written by the build. */
volatile const unsigned player_model_climb_offsets_at[3]
    __attribute__((used, section(".rdata"))) = {0};

/* garret4's ladder offsets the game reads (his clips sampled by 0x84A40):
 * the array, the slot, the end (0 start, 1 end) and the point;
 * climb_start's m_feet at its end, the other one read, is (0, 0, 0). */
static const struct {
    unsigned char array, slot, end;
    float point[3];
} g4_offsets[] = {
    {ROOT, 0x3C, 0, {0.0f, 0.0500000007f, 1.07341492f}},          /* climb_start     */
    {GRAB, 0x3C, 0, {0.0f, 0.613130987f, 2.26900005f}},
    {GRAB, 0x3C, 1, {0.0f, 0.613130987f, 2.26900005f}},
    {FEET, 0x3E, 1, {0.0f, -0.0932982489f, 0.40865773f}},         /* climb_down_edge */
    {GRAB, 0x3E, 1, {0.0f, 0.0164448712f, 2.24077463f}},
    {FEET, 0x3F, 1, {0.0f, 1.36404443f, 2.26890564f}},            /* climb_up_edge   */
    {GRAB, 0x3F, 0, {0.0f, 0.596712828f, 2.26866341f}},
    {FEET, 0x40, 1, {0.0f, 0.0135513749f, 0.0f}},                 /* climb_from_jump */
    {GRAB, 0x40, 1, {0.0f, 0.352722555f, 1.61442935f}},
};

static int is_player(const char *critter)
{
    return (*(const unsigned *)(*(const char *const *)(critter + CR_SPECIES) + SP_FLAGS)
            & PLAYER_FLAG) != 0;
}

/* The body's stand-in for a clip it lacks. */
static int stand_in(const int *slots)
{
    static const unsigned char order[] = {IDLE, IDLE_1, WALK, RUN, ROLL};
    unsigned i;

    for (i = 0; i < sizeof(order); i++)
        if (slots[order[i]] != NO_CLIP)
            return slots[order[i]];
    return NO_CLIP;
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

/* point -= v turned by turn. */
static void step_back(float *point, const float *turn, const float *v)
{
    float off[3];

    turned(turn, v, off);
    point[0] -= off[0];
    point[1] -= off[1];
    point[2] -= off[2];
}

/* point -= k x v turned by turn (the turn is linear). */
static void step_back_by(float *point, const float *turn, const float *v, float k)
{
    float kv[3];

    kv[0] = k * v[0];
    kv[1] = k * v[1];
    kv[2] = k * v[2];
    step_back(point, turn, kv);
}

__attribute__((stdcall))
void c_player_model_climb_move(char *critter, int index, void *place, const float *target,
                               const float *turn, const char *node, const char *next,
                               float t0, float t1)
{
    int *slots = (int *)(*(char **)(critter + CR_SPECIES) + SP_SLOTS);
    int kept = slots[index];
    int clip = kept == NO_CLIP && is_player(critter) ? stand_in(slots) : NO_CLIP;
    float aim[3];
    char *anim, *layer, *banm;
    float g, length, end;

    aim[0] = target[0];
    aim[1] = target[1];
    aim[2] = target[2];
    if (clip != NO_CLIP) {
        slots[index] = clip;
        if (index >= DOWN_EDGE && index <= FROM_JUMP)
            step_back(aim, turn, g4_end[index - DOWN_EDGE]);
    }
    anim_change_aligned(critter, index, place, aim, (void *)turn, node, next, t0, t1);
    slots[index] = kept;
    if (index == HANG_START && clip == NO_CLIP && kept != NO_CLIP && is_player(critter)
            && player_model_climb_scale != 1.0f)   /* its own clip, drawn X times: (X - 1) x his */
        step_back_by((float *)(critter + CR_GLIDE_END), turn, g4_hang_end, player_model_climb_scale - 1.0f);
    anim = *(char **)(critter + CR_ANIM);
    if (clip == NO_CLIP || !anim)
        return;
    g = g4_time(index);
    layer = anim + AN_LAYERS + AN_LAYERS * *(int *)(anim + AN_ACTIVE);
    banm = *(char **)(layer + LY_CLIP);
    if (!banm)
        return;
    if (index == HANG_START) {
        float *end_at = (float *)(critter + CR_GLIDE_END);

        end_at[0] = target[0];
        end_at[1] = target[1];
        end_at[2] = target[2];
        step_back_by(end_at, turn, g4_hang_end, player_model_climb_scale);
    }
    *(float *)(layer + LY_RATE) *= slower(index, banm);
    length = *(float *)(banm + CLIP_LENGTH);
    if (!(g > 0.0f) || !(length > g))
        return;
    end = t0 + (t1 - t0) * g / length;
    *(float *)(layer + LY_END) = end * length;
    *(float *)(critter + CR_WINDOW) = end - t0;
}

/* After the setter: the active layer's rate := rate, as 0x30940 writes
 * it, x slower() while it plays the stand-in the move just started. */
__attribute__((used))
void climb_rate(const char *control, float rate)
{
    const char *critter = *(const char *const *)(control + PC_CRITTER);
    const char *banm = *(const char *const *)(critter + CR_MOVE_CLIP);
    int index = *(const int *)(critter + CR_MOVE_ANIM);
    char *anim = *(char *const *)(critter + CR_ANIM);
    char *layer;

    if (!anim)
        return;
    layer = anim + AN_LAYERS + AN_LAYERS * *(int *)(anim + AN_ACTIVE);
    if (banm && *(const char *const *)(layer + LY_CLIP) == banm && g4_time(index) > 0.0f
            && is_player(critter)
            && ((const int *)(*(const char *const *)(critter + CR_SPECIES) + SP_SLOTS))[index] == NO_CLIP)
        rate *= slower(index, banm);
    *(float *)(layer + LY_RATE) = rate;
}

/* 0x30940's CALL after the setter: EAX the PlayerControl, the rate
 * pushed; RET 4 as 0x30940's. */
__attribute__((naked))
void c_player_model_climb_rate(void)
{
    __asm__ volatile (
        "pushl 4(%%esp)           \n\t"   /* the rate          */
        "pushl %%eax              \n\t"   /* the PlayerControl */
        "calll _climb_rate        \n\t"
        "addl $8, %%esp           \n\t"
        "retl $4                  \n\t"
        : : : "memory"
    );
}

/* 0x84E59 in the PlayerPhysics constructor: the offsets, then garret4's
 * for each one read that they left (0, 0, 0). */
__attribute__((stdcall))
void c_player_model_climb_offsets(void *critter)
{
    unsigned i, k;

    player_move_offsets_init(critter);
    for (i = 0; i < sizeof(g4_offsets) / sizeof(g4_offsets[0]); i++) {
        float *at = (float *)(player_model_climb_offsets_at[g4_offsets[i].array]
                              + ENTRY * g4_offsets[i].slot + 12 * g4_offsets[i].end);

        if (at[0] == 0.0f && at[1] == 0.0f && at[2] == 0.0f)
            for (k = 0; k < 3; k++)
                at[k] = g4_offsets[i].point[k];
    }
}

/* The climb tick's anim_change, with the rung point and the turn the
 * tick then hands 0x42E40. */
__attribute__((used))
void climb_loop(char *critter, int index, int flags, float *point, const float *turn)
{
    int *slots = (int *)(*(char **)(critter + CR_SPECIES) + SP_SLOTS);
    int kept = slots[index];

    if (is_player(critter)) {
        if (kept == NO_CLIP)
            slots[index] = stand_in(slots);
        if (index >= CLIMB_IDLE && index <= CLIMB_RIGHT)
            step_back(point, turn, g4_grab[index - CLIMB_IDLE]);
    }
    anim_change(critter, index, flags);
    slots[index] = kept;
}

/* 0x883CB in player_climb_tick: the point at B + 0xA8, the turn at
 * B + 0x98 (B = the entry ESP + 0x10); RET 0xC as anim_change. */
__attribute__((naked))
void c_player_model_climb_loop(void)
{
    __asm__ volatile (
        "leal 0x10(%%esp), %%eax  \n\t"
        "leal 0x98(%%eax), %%ecx  \n\t"   /* the turn  */
        "leal 0xa8(%%eax), %%eax  \n\t"   /* the point */
        "pushl %%ecx              \n\t"
        "pushl %%eax              \n\t"
        "pushl 0x14(%%esp)        \n\t"   /* flags     */
        "pushl 0x14(%%esp)        \n\t"   /* the anim  */
        "pushl 0x14(%%esp)        \n\t"   /* critter   */
        "calll _climb_loop        \n\t"
        "addl $20, %%esp          \n\t"
        "retl $12                 \n\t"
        : : : "memory"
    );
}

/* 0x88733 in 0x88490: the point at B + 0x98, the turn at B + 0x88. */
__attribute__((naked))
void c_player_model_climb_idle(void)
{
    __asm__ volatile (
        "leal 0x10(%%esp), %%eax  \n\t"
        "leal 0x88(%%eax), %%ecx  \n\t"
        "leal 0x98(%%eax), %%eax  \n\t"
        "pushl %%ecx              \n\t"
        "pushl %%eax              \n\t"
        "pushl 0x14(%%esp)        \n\t"
        "pushl 0x14(%%esp)        \n\t"
        "pushl 0x14(%%esp)        \n\t"
        "calll _climb_loop        \n\t"
        "addl $20, %%esp          \n\t"
        "retl $12                 \n\t"
        : : : "memory"
    );
}

/* 0x887D0's check before it starts a victory or the use: whether the move
 * plays, the species' slot holding a clip or, for the player's species,
 * the body having a stand-in for it. */
__attribute__((used))
int climb_plays(const char *species, int index)
{
    const int *slots = (const int *)(species + SP_SLOTS);

    return slots[index] != NO_CLIP
        || ((*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) && stand_in(slots) != NO_CLIP);
}

/* 0x888C2: the game's `cmp [edx + eax*4 + 0x124], -1` (EAX the anim, EDX
 * the species), whose ZF the JE at 0x888CA reads: set, the move drops. */
__attribute__((naked))
void c_player_model_climb_use(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"   /* the anim    */
        "pushl %%edx              \n\t"   /* the species */
        "calll _climb_plays       \n\t"
        "addl $8, %%esp           \n\t"
        "testl %%eax, %%eax       \n\t"   /* ZF: drop it */
        "retl                     \n\t"
        : : : "memory"
    );
}

/* The hit timer a victory or the use sets after its 0x42430 (critter
 * +0x1E0 and +0x1E4): garret4's length when the player's move played a
 * stand-in for an empty slot (in his time), else the clip's own. */
__attribute__((used))
float climb_immune(const char *critter)
{
    int index = *(const int *)(critter + CR_MOVE_ANIM);
    const char *banm = *(const char *const *)(critter + CR_MOVE_CLIP);
    float g = g4_time(index);

    if (g > 0.0f && is_player(critter)
            && ((const int *)(*(const char *const *)(critter + CR_SPECIES) + SP_SLOTS))[index] == NO_CLIP)
        return g;
    return *(const float *)(banm + CLIP_LENGTH);
}

/* 0x88958: the game's `mov ecx, [edi + 0x204]; fld [ecx + 0x10]` (EDI the
 * critter): the length in ST0, as the FLD left it; ECX isn't read after. */
__attribute__((naked))
void c_player_model_climb_immune(void)
{
    __asm__ volatile (
        "pushl %%edi              \n\t"   /* the critter */
        "calll _climb_immune      \n\t"
        "addl $4, %%esp           \n\t"
        "retl                     \n\t"
        : : : "memory"
    );
}

/* The ride's cable point, before 0x42E40 puts the body's m_grab on it:
 * for the player's species it moves down by garret4's m_grab in hang,
 * turned by the ride's turn, so the body, which samples zero there,
 * hangs where garret4's origin does; drawn X times its size, by
 * (X - G) x his, G 1 when 0x42E40 already takes off the body's own. */
__attribute__((used))
void climb_ride(const char *critter, float *point, const float *turn)
{
    if (is_player(critter))
        step_back_by(point, turn, g4_hang_grab, player_model_climb_scale - player_model_climb_grab);
}

/* 0x8AB32 in the ride (0x8A510): the CALL of anim_apply_translation
 * (0x42E40: ECX the turn, EAX a buffer it hands 0x61100; the critter,
 * 0.0, "m_grab" and the point pushed; RET 0x10).  EAX and ECX kept, then
 * on to 0x42E40, which returns to 0x8AB37. */
__attribute__((naked))
void c_player_model_climb_ride(void)
{
    __asm__ volatile (
        "pushl %%eax              \n\t"
        "pushl %%ecx              \n\t"
        "pushl %%ecx              \n\t"   /* the turn    */
        "pushl 0x1c(%%esp)        \n\t"   /* the point   */
        "pushl 0x14(%%esp)        \n\t"   /* the critter */
        "calll _climb_ride        \n\t"
        "addl $12, %%esp          \n\t"
        "popl %%ecx               \n\t"
        "popl %%eax               \n\t"
        "jmp _anim_apply_translation \n\t"
        : : : "memory"
    );
}
