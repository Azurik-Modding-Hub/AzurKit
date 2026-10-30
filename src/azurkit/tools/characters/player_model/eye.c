/* X8: the camera aims at the top of a player model's body, not its feet
 * (Step 2.23c; D128, AZ-304).
 *
 * The cameras aim at a critter's camera point, its vtable slot +0xB0
 * (0x41F40; only the camera classes call that slot: 0x80A23, 0x81271,
 * 0x821B4, 0x825C3).  0x41F40 looks the critter's body's marker
 * "m_head" up by exact name with the CALL 0xCB2A0 at 0x41F67, turns it
 * into the world by the critter's matrix (0x42200) scaled by its
 * +0x188, and writes that point.  0xCB2A0 gives zeros for a body
 * without the marker, so the camera aimed at the critter's feet.  Of
 * the usable bodies only garret4's (1.993 m, the top of its 2.01 m
 * bind pose), balthazar_airship's and fire_elemental's have one, so
 * every other player model was framed from its feet up: a tall one's
 * body hung above the frame (xemu sitting modelswap3: guard_air, whose
 * bind pose rises to 5.54 m, showed only its tail; guard_fire1 its jet
 * and hands).
 *
 * This shim replaces that CALL.  For the player's species (the `player`
 * flag 0x20 in S+0x64: garret4, whose body the swap retargets) the
 * point is (0, 0, player_model_eye_height), which the build writes in
 * model units (0x41F40 then scales it by the critter's +0x188 as it
 * scales m_head): garret4's fraction of the drawn body's height, his
 * m_head over his mesh's top (0.9954) times the body's mesh top, so the
 * camera aims where it aims on garret4 at any drawn size (Step 2.107,
 * D280; sized to garret4's height, his eye height over the size's scale,
 * the same point).  Every other critter jumps to 0xCB2A0 unchanged.  The
 * build installs it for a body with a mesh top and no usable "m_head"
 * (none, or one resting under half its mesh top: fire_elemental's rests
 * at 0), drawn at a scale above 0 that the game's float32 holds as a
 * normal number (the swim divides by it).  On land the camera's world
 * point is then that height x scale - 1 m above the critter's +0x15C, as the
 * control's m_head (1.9925 m) is 0.9925 m above it (xemu sitting
 * sight223).
 *
 * While the player swims (its PlayerControl, the critter's +0x180, in
 * move state 6 at +0x94) the level camera (0x81240) has no swim mode:
 * it keeps its distance and pitch from the point (2.5 m above it at
 * 5 m and -30 degrees), and in the water 0x81E10 only moves a camera
 * that comes within 0.4 m of the surface 0.5 m to the other side and
 * keeps the new distance and pitch (0x820E0).  A camera above the
 * water shows nothing under it (sitting 2.75a: guard_air's top 1 m
 * under, nothing in frame), and one under it frames the body from
 * below.  So in state 6 the shim measures the body against the
 * surface where the game draws it: the surface is the critter's +0x15C
 * (z at +0x164) plus its water depth (+0x27C, how far +0x15C is under
 * the surface; the input builder writes it every tick at 0x85593 from
 * its volume query at +0x15C, 0x85587), and the body stands on its
 * model origin, row 3 of critter_model_matrix (0x42200, which 0x41F40
 * calls next to place the point).  In the water the swim tick
 * (0x8B700) places that origin on the node m_root (0x8BD79's 0x42E40,
 * unscaled), which only garret4's, guard_air's and splinter's bodies
 * have, so every other body's origin is +0x15C, 1.04 m under the
 * surface at rest, where garret4's sits 1.5 m lower (AZ-445).
 * On the top's side the point is the land point, the top, raised only
 * so far that the camera stays player_model_swim_margin[0]'s height
 * over the water: max(top, surface - margin[0]) (Step 2.116, AZ-311:
 * a margin from the surface put a body drawn x2 or more floating at
 * rest at its origin, under its drawn feet, at the frame's top edge).
 * Once under, the point is player_model_swim_margin[1] under the
 * surface, so the camera goes under with it and climbs the body as it
 * sinks; never above its top, and below its feet if need be (Step
 * 2.107).  The build writes both margins (an 8-byte bytes param) from
 * its camera rig's scale s (X25, Step 2.107): the camera rises 0.5 x
 * its rest distance over the point, so they put it max(2s, 0.6) m
 * over the surface and max(0.6, s) m under it (garret4's x1 margins
 * scaled), clear of 0x81E10's 0.4 m push band; without a rig they are
 * this object's own 0.5 and 3.5 (the camera 2 m over, 1 m under, Step
 * 2.80b).  The camera goes under only when the top is
 * player_model_swim_band (0.25 m) under the surface and +0x15C is
 * deeper than player_model_swim_dive[0] (2.55 m: a dive; the placed
 * and risen rests, 1.04-1.38 m, stay over and a plunge's, 2.60-2.84 m,
 * goes under, as garret4's), and comes back over once the top is
 * 0.25 m out or +0x15C is no deeper than player_model_swim_dive[1]
 * (2.35 m): garret4's own camera crosses under once his centre is
 * 2.549 m deep and back over once it is shallower than 2.518 m (his push band against his
 * camera 2.955 m over his centre), so these are his, F2's 0.2 m
 * hysteresis kept (Step 2.116b, AZ-556: at 1.7 / 1.5 m splinter's
 * camera crossed twice in a 2.3 m dive, 0.6 s apart, where garret4's
 * crosses none); player_model_swim_under remembers the side (out of the
 * water it is the top's), so a body bobbing at the surface doesn't
 * flip it (AZ-414), and a small body floating wholly under the water
 * at rest is framed from above, hidden as garret4's is (Step 2.116).
 *
 * A body W27 surfaces (Step 2.150, AZ-642: garret4's swim clips baked
 * onto its rig, its root drawn at the swim's centre by the m_root the
 * build keys, D x the root): the swim's top (player_model_swim_top, in
 * place of the standing top above) is m_root / D + top x its m_eye
 * marker, which the build keys in each swim copy with garret4's head
 * over his root in his clip over his eye (1.9925), so the point sits
 * over the drawn root where his m_head sits over his, at the body's
 * share: at rest 0.40-0.46 m and in the stroke 0.19-0.31 m at x1, where
 * the standing top over the origin W27 lowers rode 1.5 m over a body
 * lying flat.  m_eye rests at 1 (a land clip, so a crossfade blends from
 * the top), and a body without it (0xCB2A0's zeros) keeps the top.  Out
 * of the water the land point's top is the top x the pose's m_eye too
 * (the top on every land clip), so leaving the water (the hoist's
 * crossfade from a swim copy) blends it up from the swim's as garret4's
 * m_head blends, where the standing top a tick after the swim's popped
 * the camera 1.96 m in one tick (town_female_4, Step 2.150's sitting).
 *
 * Over a ladder's top (Step 2.116, D286's limit 2), for a baked body
 * (garret4's clips on its rig; the build writes his climb_up_edge m_feet
 * into player_model_over_feet, zeros elsewhere).  climb_up_edge (state
 * 0x100, +0x200 0x3F) glides the drawn origin from +0x1B0 to +0x1BC
 * (+0x19C 2: 0x42070's straight-line blend) while the clip lifts the
 * body over the ledge, so (0, 0, top) on the drawn origin let the body
 * climb to the frame's top edge (every baked body, x1 too) and, under
 * X23's lowered glide end, sank under the hatch's floor until the 0.8 s
 * line-of-sight pull took the camera in (keylord own x2, sitting 2.107
 * C).  In the glide (+0x94 has 0x100, +0x200 0x3F, +0x19C 2) the point
 * is (0, 0, top) + t x over_feet, t the glide's fraction (0x42070's
 * origin projected on +0x1B0 -> +0x1BC; 1 on a glide under 1 mm), so it
 * rises with the body and ends at the ledge plus the top, x the scale.
 * After it the stance's crossfade (state 0, node m_feet) holds the drawn
 * origin by 0x402E0's term, which X26 (stance_term.c) scales by the
 * drawn scale; while the same hold is on here (player_model_over_held,
 * this object's own, by stance_term.c's rule: on in state 0 right after
 * climb_up_edge (player_model_over_edge) with the node "m_feet" and a
 * term over 1 mm, kept in any state while both hold; every other
 * crossfade keeps the land point) the point is (0, 0, top) less the
 * term, so it stays the glide
 * origin plus the top through the crossfade, as garret4's m_head does
 * at x1, with no step at the switch.  The hoists (Step 2.127, AZ-572:
 * X23 ends them on the ledge's floor and X26 holds them there) take the
 * same two branches with their own rows: player_model_over_feet is three
 * rows, garret4's m_feet at the end of climb_up_edge (+0x200 0x3F), hoist
 * (0x41) and hoist_waist (0x42), and a move whose row is zeros (every
 * other one) is no edge and keeps the land point.
 *
 * A body with no clips (Step 2.127, AZ-562): its timers' root bone rides
 * garret4's m_feet / D (retarget.py's bake), so the prop is drawn at the
 * drawn origin plus its m_feet marker (blended as the bone is) plus D x
 * its rest.  The build writes player_model_over_timer = 1 / D there (0
 * elsewhere) and no rows, and out of the water the point is (0, 0, top)
 * + timer x that marker, which anim_marker_position (0xCB2A0) gives for
 * the pose drawn (0x402E0 reads it so at 0x40320): on the prop's top in
 * every clip and crossfade: a ladder's top, a hoist, the zipline (where
 * X9 hangs the origin the hang's m_feet, 1.196 m, lower than main's, so
 * the land point rode that far under the top), the roll and the attacks.
 *
 * Through a clip that moves m_feet (Step 2.133, AZ-609: the roll, an
 * attack's lunge; the owner on keylord own, "the camera is not following
 * keylord as it rolls").  The drawn origin is the centre less the clip's
 * m_feet (0x42E40, unscaled, the node +0x1F8 names "m_feet"), so (0, 0,
 * top) on it trailed the roll by m_feet (keylord own: 8.1 m behind its
 * drawn body at the roll's end, D 2, the bones x D) and the level camera
 * fell behind with it.  On the land path, with the node m_feet and no
 * glide or hold above, the point adds the blended pose's m_feet x and y
 * (anim_marker_position, 0xCB2A0, by this object's own name) over the
 * critter's drawn scale D (+0x188), so it is P + D x top, over the
 * centre, through the roll and its exit: where the roll is drawn since
 * AZ-608 (retarget.centred, the pose about the centre x D).  Undivided
 * (AZ-616) it rode a body still drawn (D - 1) x m_feet ahead, and the
 * camera reached the origin of keylord drawn x2, which then wasn't
 * drawn.  A body without the marker (0xCB2A0's zeros) keeps its land
 * point, a clip whose m_feet is fixed a constant offset over D, and an
 * attack's lunge, still drawn ahead (AZ-623), the centre; the ladders
 * (node m_grab), the glide and the hold keep theirs.
 *
 * Swim-only (Step 2.126, D319, AZ-576: garret4's own body drawn under
 * x1, whose m_head is his eye on land): with player_model_eye_land 0 the
 * player out of the water (any move state but 6, or no controller)
 * gets the game's m_head, the CALL to 0xCB2A0 with ECX and the name
 * as they came (player_model_swim_under reset to the top's side), so
 * only the swim point above is the shim's; the build writes 1 for every
 * other body, which keeps the land point above.
 *
 * At entry (the CALL's, kept by 0xCB2A0's ABI): ECX the anim object,
 * EAX float out[3], [ESP + 4] the name; EDI the critter (0x41F40's
 * `this`, MOV EDI, ECX at 0x41F50).  0xCB2A0 pops the name (RET 4),
 * returns out in EAX and doesn't read EDX; 0x41F40 reads none of ECX,
 * EDX and EAX after it (0x41F6C on), nor an XMM register (it calls
 * 0x42200 itself next).  The shim keeps ECX on the path that jumps to
 * 0xCB2A0; on the others it uses ECX, EDX, XMM0-5 (through 0x42200,
 * 0x402E0, 0xCB2A0 and its own C) and the x87 stack, which it leaves empty; the
 * swim-only land jump has been through the C first, so XMM0-5 and EDX
 * may differ there too.
 * 0x402E0 takes EAX = the critter and EDI = the out (a plain RET,
 * keeping EBX, ESI, EDI and EBP); 0x42070 is __stdcall(8).  It keeps EBX, ESI, EDI
 * and EBP, returns out in EAX and pops 4 bytes too.  fucomip is a P6
 * instruction, which the Pentium III has (the game's own 0x42121 uses
 * fucomi).
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

AZURIK_FLOAT_PARAM(player_model_eye_height, 0.0f);
AZURIK_FLOAT_PARAM(player_model_eye_land, 1.0f);   /* 0: the game's m_head out of the water */
AZURIK_FLOAT_PARAM(player_model_over_timer, 0.0f);   /* 1 / D on a body with no clips, else 0 */
const float player_model_swim_margin[2] __attribute__((used, section(".rdata"))) = {0.5f, 3.5f};
const float player_model_swim_band __attribute__((used, section(".rdata"))) = 0.25f;
const float player_model_swim_dive[2] __attribute__((used, section(".rdata"))) = {2.55f, 2.35f};
volatile const float player_model_over_feet[3][3] __attribute__((used, section(".rdata"))) = {{0.0f}};
int player_model_swim_under __attribute__((used));   /* 1: the camera's under the water */
int player_model_over_held __attribute__((used));    /* 1: the stance's hold is on (X26's) */
int player_model_over_edge __attribute__((used));    /* 1: the last call saw climb_up_edge */
float player_model_swim_top __attribute__((used));  /* the swim's top, model units (eye_point's) */

#define CR_ANIM       0x17C   /* critter -> its anim object (0x41F5C's ECX)  */
#define CR_CONTROL    0x180   /* critter -> its PlayerControl (the player's) */
#define CR_SCALE      0x188   /* critter: its drawn scale D                  */
#define CR_MODE       0x19C   /* critter: 0x42070's glide mode, 2 gliding    */
#define CR_FROM       0x1B0   /* critter: the glide's start                  */
#define CR_END        0x1BC   /* critter: the glide's end                    */
#define CR_NODE       0x1F8   /* critter: the aligned node's name            */
#define CR_MOVE_ANIM  0x200   /* critter: the aligned move's anim (0x42430)  */
#define PC_STATE      0x094   /* PlayerControl: its move state               */
#define SWIMMING      6
#define CLIMB_STATE   0x100   /* the ladder's move state (a hit's 0x102 too) */
#define UP_EDGE       0x3F    /* climb_up_edge, row 0; hoist 0x41 and hoist_waist 0x42 rows 1, 2 */
#define HOIST         0x41
#define HOIST_WAIST   0x42
#define GLIDING       2
#define HELD_MIN      1e-6f   /* (1 mm)^2: a shorter term is no crossfade    */
#define GLIDE_MIN     1e-6f   /* (1 mm)^2: a shorter glide is at its end     */

static const char feet_name[7] = "m_feet";
static const char eye_name[6] = "m_eye";
static const char root_name[7] = "m_root";

static int is_feet(const char *name)
{
    int i;

    for (i = 0; i < 7; i++)
        if (name[i] != feet_name[i])
            return 0;
    return 1;
}

/* term := 0x402E0's aligned-node term for critter. */
__attribute__((naked, noinline, used))
static void node_offset(const char *critter, float *term)
{
    __asm__ volatile (
        "pushl %%edi             \n\t"
        "movl 0x8(%%esp), %%eax  \n\t"   /* the critter */
        "movl 0xc(%%esp), %%edi  \n\t"   /* the term    */
        "calll _aligned_node_offset \n\t"
        "popl %%edi              \n\t"
        "retl                    \n\t"
        : : : "memory"
    );
}

/* at := the anim object's marker `name` in the pose drawn
 * (anim_marker_position: ECX the anim, EAX the out, the name on the
 * stack, RET 4; it keeps EBX, ESI, EDI and EBP and uses no x87). */
__attribute__((naked, noinline, used))
static void marker_at(const void *anim, float *at, const char *name)
{
    __asm__ volatile (
        "movl 0x4(%%esp), %%ecx  \n\t"   /* the anim object */
        "movl 0x8(%%esp), %%eax  \n\t"   /* the out         */
        "movl 0xc(%%esp), %%edx  \n\t"
        "pushl %%edx             \n\t"   /* the name: 0xCB2A0 pops it */
        "calll _anim_marker_position \n\t"
        "retl                    \n\t"
        : : : "memory"
    );
}

/* The aligned move's row of player_model_over_feet into feet; 0 when it
 * has none (another move, or a row of zeros). */
static int over_row(const char *critter, float *feet)
{
    int anim = *(const int *)(critter + CR_MOVE_ANIM), row, i;

    row = anim == UP_EDGE ? 0 : anim == HOIST ? 1 : anim == HOIST_WAIST ? 2 : -1;
    if (row < 0)
        return 0;
    for (i = 0; i < 3; i++)
        feet[i] = player_model_over_feet[row][i];
    return feet[0] != 0.0f || feet[1] != 0.0f || feet[2] != 0.0f;
}

/* stance_term.c's hold, kept for this object; term valid when on. */
static int held_term(const char *critter, const char *control, float *term)
{
    const char *node = *(const char *const *)(critter + CR_NODE);
    int state = control ? *(const int *)(control + PC_STATE) : 0;
    int held = control && ((state == 0 && player_model_over_edge) || player_model_over_held)
        && node && is_feet(node);
    float feet[3];

    if (held) {
        node_offset(critter, term);
        held = term[0] * term[0] + term[1] * term[1] + term[2] * term[2] > HELD_MIN;
    }
    player_model_over_held = held;
    player_model_over_edge = control && (state & CLIMB_STATE) && over_row(critter, feet);
    return held;
}

/* How far the glide has gone, 0 to 1: 0x42070's origin on +0x1B0 -> +0x1BC. */
static float glide_fraction(const char *critter)
{
    const float *from = (const float *)(critter + CR_FROM), *end = (const float *)(critter + CR_END);
    float at[3], d, along = 0.0f, length = 0.0f, t;
    int i;

    glide_origin(critter, at);
    for (i = 0; i < 3; i++) {
        d = end[i] - from[i];
        along += (at[i] - from[i]) * d;
        length += d * d;
    }
    if (!(length >= GLIDE_MIN))
        return 1.0f;
    t = along / length;
    return t > 1.0f ? 1.0f : t > 0.0f ? t : 0.0f;
}

/* The player's point out of the water into out (1); 0 while it swims;
 * 2 out of the water when swim-only (the game's m_head). */
__attribute__((used))
int eye_point(const char *critter, float *out)
{
    const char *control = *(const char *const *)(critter + CR_CONTROL);
    const void *anim = *(const void *const *)(critter + CR_ANIM);
    const char *node = *(const char *const *)(critter + CR_NODE);
    int state = control ? *(const int *)(control + PC_STATE) : 0;
    float feet[3], term[3], t, timer = player_model_over_timer, scale = *(const float *)(critter + CR_SCALE);
    int i, over = 0, held = 0;

    for (i = 0; i < 9; i++)
        over |= player_model_over_feet[i / 3][i % 3] != 0.0f;
    if (over)
        held = held_term(critter, control, term);
    if (control && state == SWIMMING) {   /* W27's body: over its drawn root, garret4's head over his (AZ-642) */
        player_model_swim_top = player_model_eye_height;
        if (anim && scale != 0.0f) {
            marker_at(anim, feet, eye_name);   /* zeros on a body without it: the top */
            if (feet[2] != 0.0f) {
                marker_at(anim, term, root_name);
                t = 1.0f / scale;
                player_model_swim_top = term[2] * t + player_model_eye_height * feet[2];
            }
        }
        return 0;
    }
    player_model_swim_under = 0;   /* out of the water: the top's side */
    if (player_model_eye_land == 0.0f)
        return 2;
    out[0] = 0.0f;
    out[1] = 0.0f;
    out[2] = player_model_eye_height;
    if (anim) {   /* W27's m_eye: out of a swim copy the top blends up from the swim's (AZ-642) */
        marker_at(anim, feet, eye_name);
        if (feet[2] != 0.0f)
            out[2] *= feet[2];
    }
    if (timer != 0.0f && anim) {   /* a body with no clips: its prop's top */
        marker_at(anim, feet, feet_name);
        for (i = 0; i < 3; i++)
            out[i] += timer * feet[i];
        return 1;
    }
    if (!control)
        return 1;
    if (over && (state & CLIMB_STATE) && *(const int *)(critter + CR_MODE) == GLIDING && over_row(critter, feet)) {
        t = glide_fraction(critter);
        for (i = 0; i < 3; i++)
            out[i] += t * feet[i];
    } else if (held) {
        for (i = 0; i < 3; i++)
            out[i] -= term[i];
    } else if (anim && node && is_feet(node) && scale != 0.0f) {   /* the centre through m_feet (AZ-609, AZ-616) */
        marker_at(anim, feet, feet_name);
        t = 1.0f / scale;   /* scalar, so no packed lane divides 0 by 0 */
        out[0] += feet[0] * t;
        out[1] += feet[1] * t;
    }
    return 1;
}

__attribute__((naked))
void c_player_model_eye(void)
{
    __asm__ volatile (
        "movl 0x178(%%edi), %%edx            \n\t"   /* critter -> species */
        "testb $0x20, 0x64(%%edx)            \n\t"   /* its `player` flag? */
        "jz 1f                               \n\t"
        "pushl %%ecx                         \n\t"   /* the anim object, kept for 0xCB2A0 */
        "pushl %%eax                         \n\t"   /* out, kept */
        "pushl %%eax                         \n\t"
        "pushl %%edi                         \n\t"
        "calll _eye_point                    \n\t"   /* out of the water: the point */
        "addl $8, %%esp                      \n\t"
        "movl %%eax, %%edx                   \n\t"
        "popl %%eax                          \n\t"
        "popl %%ecx                          \n\t"
        "cmpl $1, %%edx                      \n\t"
        "jb 3f                               \n\t"   /* swimming (move state 6) */
        "ja 1f                               \n\t"   /* swim-only, out of the water: the game's m_head */
        "retl $4                             \n\t"
        "3:                                  \n\t"
        "pushl %%esi                         \n\t"
        "pushl %%ebp                         \n\t"
        "movl %%esp, %%ebp                   \n\t"
        "subl $0x40, %%esp                   \n\t"
        "andl $-16, %%esp                    \n\t"   /* a 16-byte aligned 4x4, as 0x41F40's */
        "movl %%esp, %%esi                   \n\t"
        "pushl %%eax                         \n\t"
        "pushl %%edi                         \n\t"
        "calll \"_critter_model_matrix@4\"   \n\t"
        "popl %%eax                          \n\t"
        "flds 0x164(%%edi)                   \n\t"   /* +0x15C's height */
        "fadds 0x27c(%%edi)                  \n\t"   /* + its depth: the surface's */
        "fsubs 0x38(%%esi)                   \n\t"   /* - the model origin's: d, m */
        "movl %%ebp, %%esp                   \n\t"
        "popl %%ebp                          \n\t"
        "popl %%esi                          \n\t"
        "flds _player_model_swim_top         \n\t"
        "fmuls 0x188(%%edi)                  \n\t"   /* its top x its scale, m */
        "fsub %%st(1), %%st                  \n\t"   /* e: how far its top is out */
        "movl _player_model_swim_under, %%ecx\n\t"   /* its side now */
        "flds _player_model_swim_band        \n\t"
        "testl %%ecx, %%ecx                  \n\t"
        "jne 6f                              \n\t"
        "fchs                                \n\t"   /* on the top's side: under past -band */
        "6:                                  \n\t"
        "fucomip %%st(1), %%st               \n\t"   /* the edge above e? */
        "fstp %%st(0)                        \n\t"   /* e */
        "seta %%dl                           \n\t"
        "flds _player_model_swim_dive(,%%ecx,4)\n\t"
        "flds 0x27c(%%edi)                   \n\t"
        "fucomip %%st(1), %%st               \n\t"   /* +0x15C deeper than its side's dive edge? */
        "fstp %%st(0)                        \n\t"
        "seta %%cl                           \n\t"
        "andb %%cl, %%dl                     \n\t"   /* both: the camera goes (or stays) under */
        "movzbl %%dl, %%edx                  \n\t"
        "movl %%edx, _player_model_swim_under\n\t"
        "fsubs _player_model_swim_margin(,%%edx,4)\n\t"   /* d - its side's margin */
        "fdivs 0x188(%%edi)                  \n\t"   /* in model units */
        "flds _player_model_swim_top         \n\t"
        "testl %%edx, %%edx                  \n\t"
        "jnz 5f                              \n\t"
        "fucomip %%st(1), %%st               \n\t"   /* over the water: at least its top */
        "jbe 7f                              \n\t"
        "fstp %%st(0)                        \n\t"
        "flds _player_model_swim_top         \n\t"
        "jmp 7f                              \n\t"
        "5:                                  \n\t"
        "fucomip %%st(1), %%st               \n\t"   /* under it: at most its top */
        "jae 7f                              \n\t"
        "fstp %%st(0)                        \n\t"
        "flds _player_model_swim_top         \n\t"
        "7:                                  \n\t"
        "xorl %%edx, %%edx                   \n\t"
        "movl %%edx, (%%eax)                 \n\t"
        "movl %%edx, 4(%%eax)                \n\t"
        "fstps 8(%%eax)                      \n\t"
        "retl $4                             \n\t"
        "1:                                  \n\t"
        "jmp _anim_marker_position           \n\t"
        : : : "memory"
    );
}
