/* X48: a big body's crossfade off the zipline and into a landing is
 * drawn over the floor, no higher than it needs (Step 2.189b, AZ-706,
 * AZ-711; a landing's at once since Step 2.200, D800; the floor under
 * each low bone since Step 2.200c, AZ-780).
 *
 * Why.  Over the first ticks of a move the anim layers cross from the
 * old clip into the new one, the pose summing the layers' raw rotations
 * (docs/RE_XBE.md, "The anim layers' crossfade"), and on some bodies
 * drawn larger than garret4 that blend swings the pose far under its
 * origin: guard_air own x2's lowest point 3.29 m under it 4 ticks after
 * letting go of f3's cable (sittings 2.118c, 2.175b), 2.95 m through the
 * end platform 2 ticks after landing off the cable's end and 3.15 m 5
 * ticks into f6's jump landing (sittings 2.127, 2.118c), main's to the
 * mm.  Step 2.175b's let-go hold (X22, a table of the crossfade's least
 * over the hang's phases, rising a step a tick ahead) held the let-go
 * over the floor but lifted the body up to 3.95 m over it (a 3 m hop,
 * the table's least and its 2-tick widening, where this let-go's own
 * pose dipped less and had already risen), and held it 2.56 m over its
 * stance when it landed inside the hold, which the ground's placement
 * undid in one tick (3.56 m, sitting 2.175b, AZ-711); the landings had
 * no hold (AZ-706).  A landing can't be risen to early, and the pose a
 * tick will draw is known only once it is posed: here.
 *
 * What.  This shim takes critter_model_matrix's (0x42200) CALL of
 * glide_origin (0x42070) at 0x42237, the drawn origin before the
 * aligned-node term.  For the player's species (flag 0x20) within
 * FADE_TICKS of the clock after its PlayerControl (+0x180) left the ride
 * (the state its last tick started in, +0x98, 5, and its state now,
 * +0x94, not 5: the let-go or the cable's end), landed (+0x98 2, +0x94
 * 0, 0x100, or a slope's 3 or 4 since Step 2.200b: a soft, a hard or a
 * slope landing; or slid to a slope's foot, +0x98 3 or 4 and +0x94 0 or
 * 0x100, since Step 2.200c) or took off (+0x98 0, 3, 4 or
 * 0x100, +0x94 2: Step 2.199, below), each weight-bearing posed bone's
 * drawn lowest point (the origin plus 0x402E0's term plus the drawn scale
 * +0x188 x the bone, less player_model_fade_sole, the mesh under the
 * lowest bone), from the lowest up, is held no lower than the lower of
 * the first floor under that bone itself (its x, y in the world, from
 * player_model_fade_ray over the centre's height; Step 2.200c, below) and
 * the first under the centre (collision_sweep, mask 0x10, within
 * player_model_fade_ray under it, as X22's and X28's) plus
 * player_model_fade_low (how far under the floor the body's own ground
 * clips draw it at its stance: 0 or less): the origin is raised by the
 * most any bone falls short.  The pose is this frame's (0x42200 runs after the pose
 * update 0xCBC80), so the body is lifted only on the ticks its pose
 * dips, and the rest is the game's.  The lift moves at most FADE_STEP a
 * tick of the clock (X22's and X28's step: D293's "never more than 0.85
 * m a tick", D115's default), and past the window or out of it lets go
 * a step a tick, never more than the pose still needs: held exactly,
 * the lift followed the pose's dip and jerked the drawn body and the
 * camera with it, guard_air own x2 up to 2.11 m a tick at f3's cable's
 * end, and dropped 3.76 m where the window ended mid-dip on f6's
 * run-off (sitting 2.189b), and the pose model's water_tentacle1 own x2
 * up to 9.6 m a tick (record/results/x48-cap-*); capped, the deepest
 * and fastest dips are partly the game's again.  A hoist
 * (the aligned move at critter+0x200 0x41 or 0x42, state 0x100 from the
 * air too: the setter's ECX at 0x86D88) is never held: it puts the
 * centre on the ledge on its first tick while the drawn body glides up
 * from 1.5-1.7 m under it, so a hold would lift it onto the ledge and
 * drop it back at the twelfth tick (keylord own x1, sitting 2.123's
 * H3; X23 ends the hoist on the ledge's floor).  Only where
 * it is drawn: the centre, collision, the state and the timing are the
 * game's, and so is the camera point (Step 2.192, AZ-746): 0x41F40's
 * CALL of 0x42200 (USA and Europe 0x41FB0) puts X8's fixed model point
 * into the world through this same origin, and the level camera keeps
 * its distance from that point every tick, so the lift bobbed the screen
 * with every dip (booblord's hard landing: +0.16, -0.10, +0.17, -0.23 m
 * in 11 ticks, where garret4's stays within 9 mm); the call whose
 * 0x42200 returns to player_model_fade_camera (the build's, that CALL's
 * end) gets the game's origin and leaves the hold as it was.  The damage
 * pass and the draws keep to the drawn body.  The bones held are the
 * body's weight-bearing ones: a bone of player_model_fade_loose (the
 * build's bit mask: its hair and cloth chains and a carried prop's) is
 * left out, so a flap swinging through the floor (booblord's sash in the
 * touchdown she borrows, 0.36 m, AZ-728) never floats the body 0.24 m
 * over it.  The build installs it where the let-go's or a landing's
 * crossfade takes those bones more than 0.05 m past the body's own
 * ground clips' lowest (HoldPlan.fade_ray).
 *
 * Takeoffs (Step 2.199, AZ-706).  Leaving the ground crosses the same way
 * into the airborne clip (the jump's and the fall's anim changes restart
 * their clip, flag 4, so a body whose every slot plays its idle crosses
 * from one phase of it into another), and the body is still at the floor
 * over the first ticks: guard_air own x2's lowest point 2.84 m through it
 * 3 ticks into f6's standing jump and 3.82 m 3 ticks after running off a
 * ledge, main's to the mm (Step 2.189b's record sitting), which the hold
 * didn't arm on.  It arms on a takeoff too: the last tick started on the
 * ground (+0x98 0, a slope 3 or 4, or 0x100) and the state now is
 * airborne (2), and the build gates on the takeoffs' crossfades with the
 * rest (fade_dip).
 *
 * Landings stop at the floor (Step 2.200, AZ-706, D800: "Stop at the
 * floor", the owner).  Rising a step a tick, a landing's dip faster than
 * that stayed partly the game's: guard_air own x2's lowest point 1.04,
 * 1.61 and 1.25 m through f6's floor 3-4 ticks after its 2, 6 and 13 m
 * falls and 1.01 m after its standing jump (Step 2.199's sitting).  A
 * hold armed at a landing (+0x98 2, +0x94 0 or 0x100) now holds the
 * drawn lowest point at the floor exactly over its window, the lift the
 * shortfall each tick with no step either way (the impact; eased down a
 * step a tick, the lift held guard_air own x2's lowest point up to 1.06 m
 * over that line for 2 ticks after its 6 m fall's dip, in a replay of
 * Step 2.199's rows), and past the window lets go a step a tick, as before
 * (the ease-out: held exactly to its end, Step 2.189b's first build
 * dropped 3.76 m where a window ended mid-dip).  The let-go's, the cable's
 * end's and the takeoffs' move a step a tick still (D293's limit, which
 * D800 keeps for the hangs and Step 2.199's held takeoffs).
 *
 * Off the ride and onto a slope (Step 2.200b, AZ-780, D815: "Fix all
 * three", the owner).  Held exactly, a landing that ends a fall begun
 * off the ride followed its pose's one-tick swings: water_tentacle1 own
 * x2's after its let-go off f3's cable popped 2.73 m up and 2.65 m down
 * on consecutive ticks (its dip lasts a tick), and guard_air own x2's at
 * the cable's end dropped 1.87 m and rose 1.86 m as its tail tip flicked
 * up for a tick (Step 2.200's record seat).  Such a landing (the hold
 * armed off the ride since the body last stood: +0x98 5, then airborne
 * only, under RODE_TICKS ago) now moves a step a tick, as the let-go
 * before it does, so a dip eases in over a few ticks and a flick is
 * ridden over; a longer fall's landing is a fall's, held exactly (D800;
 * the review's S1: the two seen landed 12 and 6 ticks after the arm).
 * And a landing
 * onto a slope (+0x98 2, +0x94 3 or 4) arms as a landing too, held at
 * the floor exactly as a flat one (water_tentacle1 own x2's run-off onto
 * f6's ledge went 1.42 m under its line for a tick, unheld).
 *
 * The cable's end's flick (Step 2.200c, AZ-780, D802: "completely
 * finish model work").  Stepped, guard_air own x2's landing at f3's
 * cable's end still dropped a step and came back as its tail tip, the
 * held point, flicked up 1.87 m for one tick (the drawn origin -0.85 then
 * +0.83 m, its torso 19 px down and up in one frame; main 41: Step
 * 2.200b's record seat).  On such a landing (HOLD_RODE) a lift that met
 * its need the clock before is now kept the clock its need first falls
 * more than a step under it, then steps as before: a one-tick rise of the
 * held point is ridden over with the body still.  A dip's end faster than
 * a step a tick pauses its descent that tick (the hold can't tell the two
 * apart until the next).  A let-go's in the air and a takeoff's step at
 * once, and a dip's end within a step a tick is followed as before.
 *
 * The slide's end (Step 2.200c, AZ-780, D802).  A slide down a slope
 * that ends at its foot (+0x98 3 or 4, +0x94 0 or the touchdown 0x100)
 * crosses from the slide clip into the ground's as a landing does, and
 * armed nothing: guard_air own x2's lowest point went 5.49 m under the
 * floor at f6's ramp's foot after its 2 m fall (5.26 m under its line)
 * and 3.64 m after its 6 m fall, where the slope landing's window ended
 * mid-dip (Step 2.200b's sitting).  It now arms as a landing, held at the
 * floor exactly (D800).
 *
 * The floor under each low bone (Step 2.200c, AZ-780, D802).  Cast
 * under the centre, the floor was the held point's only on a flat one:
 * guard_air own x2 holds its tail's tip (Tail13, 3.3 m from the centre
 * at rest, 3.5-4.0 m on the landings' lifted ticks), so on f6's ramp (nz
 * 0.61, 1.30 m a metre) the slope's own drop under it read as a dip and
 * its 2 m ramp landing bobbed twice, and where the floor under the centre
 * changed the exact hold dropped it 1.50 m in a tick (Step 2.200b's
 * record seat).  Each low bone is now held over the lower of the first
 * floor under it (its x, y the origin plus (D x the bone + 0x402E0's
 * term) turned by the matrix's rows (0xA0770's, from the critter's
 * quaternion +0x18C, which 0x42200 writes before this CALL and 0x42270
 * scales by D), as the body is drawn, cast from the ray's length over the
 * centre's height to the ray's under it) and the first under the centre
 * (main's), and the lift is the most any needs: a downhill tip is held
 * over its own floor, an uphill one over the centre's as before, a bone
 * with no floor under it within its cast (out over a drop) needs nothing,
 * and one whose cast first meets a wall or an underside (no floor to
 * read) the centre's.  The bones are taken from the lowest up, and one
 * drawn over the centre's line less the need so far can need no more,
 * nor can any higher, so a flat floor costs two casts (at most
 * FLOOR_CASTS).  Held by its lowest bone alone, cast from the centre's
 * height (only 1 m over its floor), the hold found an uphill floor less
 * than 1 m over the centre's and lifted the body by it, and missed one
 * higher, holding nothing (the review's F1: guard_air own x2's 2 m ramp
 * landing popped 3.11 m up and 3.83 m down in two ticks, its let-go at
 * ride tick 12 went 1.7 m deeper into its uphill floor than main's); and
 * the bones next to it went into the floor it lifted none of them for
 * (its run-off takeoff 2.38, 2.15 and 1.77 m into the ledge it left,
 * main's 1.14, 0.91, 0.52), and cast from over the body 2-4 of them a
 * tick met that ledge's wall first (Step 2.200c's sitting and record
 * seat).  On a flat floor every cast is main's.  An uphill bone is never
 * held over its own floor: at f3's cable's end guard_air own x2's tail
 * lies 1.2-3.9 m into a rise 2.1-3.9 m over the platform on several
 * ticks in every tree (the game's own pose), which main's lift for the
 * tip out over the edge cleared on two.
 *
 * ABI: 0x42070 is __stdcall(8), the critter and float out[3], RET 8,
 * EAX = out; 0x42200 reads EAX and keeps EBX (the critter), ESI (its
 * matrix, rows 0-2 its rotation by then: 0x42211) and EDI.  At the CALL
 * at 0x42237 0x42200 has pushed EBX and EDI under its 0x18 bytes of
 * locals and the two arguments, so its own return address is at
 * [ESP + 0x2C] on the stub's entry.  The stub
 * keeps EBX, ESI, EDI and EBP, leaves the x87 stack empty and returns
 * EAX = out with RET 8; aligned_node_offset takes EAX the critter and
 * EDI the out, a plain RET (keeps EBX, ESI, EDI and EBP).
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

#define CR_CLOCK     0x0E4   /* critter -> its clock (+0x10 its time)      */
#define CK_TIME      0x010   /* the clock: its time, a double (s)          */
#define CR_LEVEL     0x154   /* critter -> its level (+0xAC: the tree)     */
#define CR_CENTRE    0x15C   /* critter: its body centre (x, y, z)        */
#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_ANIM      0x17C   /* critter -> its anim object                */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl              */
#define CR_SCALE     0x188   /* critter: its drawn scale D                */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define PC_STATE     0x094   /* PlayerControl: its move state             */
#define PC_LAST      0x098   /* PlayerControl: the state its last tick started in */
#define AIRBORNE     2
#define SLOPE        3       /* and 4: the slope states                   */
#define RIDE         5
#define ALIGNED      0x100   /* an aligned move (the hard landing's touchdown) */
#define CR_MOVE_ANIM 0x200   /* critter: the aligned move's anim (0x42430)  */
#define HOIST        0x41    /* hoist                                      */
#define HOIST_WAIST  0x42    /* hoist_waist                                */
#define AN_BODY      0x000   /* anim object -> its body (+0: its bones)    */
#define AN_BONES     0x008   /* anim object -> its posed bones            */
#define BONE_SIZE    0xB0    /* one posed bone                            */
#define BONE_X       0xA0    /* its matrix's translation x, y, z (model units) */
#define BONE_Z       0xA8    /* its matrix's translation z (model units)   */
#define LV_TREE      0x0AC   /* level -> its collision tree               */
#define FLOOR_MASK   0x10    /* 0x8AE10's faces                           */
#define HIT_SIZE     0x50    /* collision_sweep writes 0x48 bytes on a hit */
#define HIT_NORMAL_Z 0x14    /* hit: its normal's z                        */
#define HIT_FRACTION 0x18    /* hit: its fraction of the way               */
#define HIT_FLAGS    0x20    /* hit: its flags (bit 0: not a floor)        */
#define FADE_TICKS   12      /* the crossfade's 7.5 ticks and 2 more either way */
#define RODE_TICKS   24      /* a landing this soon after the off-ride arm ends its fall (2 x FADE_TICKS) */
#define FADE_STEP    0.847f  /* the most the lift moves a tick (m): X22's and X28's step */
#define LIFT_FOR     0.1     /* the last lift counts this long (s), as X28's LAST_FOR */
#define TICK_HZ      30.0
#define LOOSE_BYTES  32      /* player_model_fade_loose: a bit a bone, 256 bones */
#define FLOOR_CASTS  8       /* the most bones a draw casts a floor under, the lowest first */
#define HOLD_STEP    0       /* off the ride, a takeoff: a step a tick either way */
#define HOLD_EXACT   1       /* a landing: the shortfall each tick */
#define HOLD_RODE    2       /* a landing ending a fall begun off the ride: a step a tick, a met lift kept a tick */

/* How far under the centre's height (and over it, under a bone) the hold
 * looks for a floor (m), the mesh under
 * the lowest posed bone (m, drawn), and how far under the floor the body's
 * own ground clips draw it at its stance (m, 0 or less).  Written by the
 * build. */
AZURIK_FLOAT_PARAM(player_model_fade_ray, 0.0f);
AZURIK_FLOAT_PARAM(player_model_fade_sole, 0.0f);
AZURIK_FLOAT_PARAM(player_model_fade_low, 0.0f);

/* The camera point's return address from 0x42200 (its CALL's end, the
 * build's release's), and the bones left out of the lowest (bit b & 7 of
 * byte b >> 3: bone b).  Written by the build. */
AZURIK_BYTES_PARAM(player_model_fade_camera, 4);
AZURIK_BYTES_PARAM(player_model_fade_loose, LOOSE_BYTES);

double player_model_fade_from;          /* the clock when the hold last armed */
const char *player_model_fade_critter;  /* the critter it armed for           */
int player_model_fade_landed;           /* how it holds: HOLD_STEP, HOLD_EXACT or HOLD_RODE */
int player_model_fade_rode;             /* 1: it armed off the ride, and the body has stood nowhere since */
int player_model_fade_met;              /* 1: the lift then met a need over 0 (its held point at the floor) */
int player_model_fade_was_met;          /* the same, the clock before it */
double player_model_fade_at;            /* the clock last drawn                  */
float player_model_fade_lift;           /* the lift then (m)                     */
float player_model_fade_was;            /* the lift the clock before it (m)      */
float player_model_fade_step;           /* how far the lift may move from it (m) */

static int is_player(const char *critter)
{
    const char *species = *(const char *const *)(critter + CR_SPECIES);

    return species && (*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) != 0;
}

/* term := 0x402E0's aligned-node term for critter, which the draw adds
 * to the origin next (0x42200's CALL at 0x42253, unscaled). */
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

/* *z := the first floor from up over at to the ray under it (any slope): 1; 0: no hit
 * (a drop); -1: the first hit isn't a floor (a wall or an underside). */
static int floor_under(const char *critter, const float *at, float up, float *z)
{
    const char *level = *(const char *const *)(critter + CR_LEVEL);
    void *tree = level ? *(void *const *)(level + LV_TREE) : 0;
    float from[3], to[3], ray = player_model_fade_ray;
    unsigned hit[HIT_SIZE / 4];
    unsigned char *flags = (unsigned char *)hit + HIT_FLAGS;
    int k;

    if (!tree)
        return 0;
    for (k = 0; k < 3; k++)
        from[k] = to[k] = at[k];
    from[2] += up;
    to[2] -= ray;
    ray += up;
    for (k = 0; k < HIT_SIZE / 4; k++)
        hit[k] = 0;
    flags[1] = 0x80;   /* as 0x8AE10: the word 0x8000, then 0, 0xCC */
    flags[3] = 0xCC;
    if (!collision_sweep(tree, (void *)critter, 0, from, to, 0.0f, 0.0f, FLOOR_MASK, hit))
        return 0;
    if ((flags[0] & 1) || !(*(const float *)((const char *)hit + HIT_NORMAL_Z) > 0.0f))
        return -1;
    *z = from[2] - ray * *(const float *)((const char *)hit + HIT_FRACTION);
    return 1;
}

/* 1: the move from last to state crosses into a clip with the body at
 * the floor: off the ride, a landing (airborne to the ground, a slope or
 * the touchdown, or a slide's end: a slope to the ground or the
 * touchdown) or a takeoff (the ground, a slope or an aligned move into
 * the air).  Every arm but off the ride's and a takeoff's is a landing. */
static int arms(int last, int state)
{
    if (last == RIDE)
        return state != RIDE;
    if (last == AIRBORNE)
        return state == 0 || state == SLOPE || state == SLOPE + 1 || state == ALIGNED;
    if (last == SLOPE || last == SLOPE + 1)
        return state == AIRBORNE || state == 0 || state == ALIGNED;
    return state == AIRBORNE && (last == 0 || last == ALIGNED);
}

/* 1: critter's crossfade hold is on now (armed off the ride, at a
 * landing or at a takeoff, within FADE_TICKS of it, and not in a hoist).
 * A landing is held exactly unless the fall it ends began off the ride
 * (armed off it under RODE_TICKS ago, the body airborne on every tick
 * drawn since). */
static int fading(const char *critter)
{
    const char *control = *(const char *const *)(critter + CR_CONTROL);
    const char *clock = *(const char *const *)(critter + CR_CLOCK);
    int last, state, anim;
    double now;

    if (!control || !clock)
        return 0;
    now = *(const double *)(clock + CK_TIME);
    last = *(const int *)(control + PC_LAST);
    state = *(const int *)(control + PC_STATE);
    anim = *(const int *)(critter + CR_MOVE_ANIM);
    if ((state & ALIGNED) && (anim == HOIST || anim == HOIST_WAIST))
        return 0;
    if (arms(last, state)) {
        if (player_model_fade_critter != critter || now - player_model_fade_from >= 1.0 / TICK_HZ
                || now < player_model_fade_from) {
            int rode = player_model_fade_critter == critter && player_model_fade_rode
                && now - player_model_fade_from < RODE_TICKS / TICK_HZ;

            player_model_fade_from = now;   /* a tick's draws arm it once */
            player_model_fade_critter = critter;
            player_model_fade_landed = last == RIDE || state == AIRBORNE ? HOLD_STEP : rode ? HOLD_RODE : HOLD_EXACT;
            player_model_fade_rode = last == RIDE;
        }
    } else if (state != AIRBORNE) {
        player_model_fade_rode = 0;   /* not airborne (stood, climbed, hit): a later fall starts here */
    }
    return player_model_fade_critter == critter && now >= player_model_fade_from
        && now - player_model_fade_from < FADE_TICKS / TICK_HZ;
}

/* 1: bone b is left out of the lowest (the build's mask). */
static int loose(int b)
{
    return b < 8 * LOOSE_BYTES && (player_model_fade_loose[b >> 3] >> (b & 7) & 1);
}

/* How far the drawn body is under the floor's hold this frame (m, 0 or
 * more; 0: no weight-bearing bones or no floor under the centre): the most
 * any weight-bearing bone needs, from the lowest up, to be drawn no lower
 * than the lower of the first floor under it (its x, y: the origin plus
 * (D x the bone + the term) by the matrix's rows, as 0x42200 and 0x42270
 * draw it, cast from the ray's length over the centre's height) and the
 * first under the centre, plus fade_low.  A bone no floor is under within
 * its cast needs nothing, one whose cast first meets a wall or an
 * underside the centre's floor (main's); one whose drawn height is over the centre's line
 * less the need so far can need no more, nor can any higher (at most
 * FLOOR_CASTS casts a draw). */
static float shortfall(const char *critter, const float *origin, const float *matrix)
{
    const char *anim, *bones, *body;
    const float *bone, *centre = (const float *)(critter + CR_CENTRE);
    float term[3] = {0.0f, 0.0f, 0.0f}, at[3], z, lz = 0.0f, last = 0.0f, d, top, base, floor, want, need = 0.0f;
    int n, b, k, casts, held, prev = -1;

    anim = *(const char *const *)(critter + CR_ANIM);
    bones = anim ? *(const char *const *)(anim + AN_BONES) : 0;
    body = anim ? *(const char *const *)(anim + AN_BODY) : 0;
    n = body ? *(const int *)body : 0;
    if (!bones || n <= 0 || floor_under(critter, centre, 0.0f, &top) <= 0)
        return 0.0f;
    node_offset(critter, term);
    d = *(const float *)(critter + CR_SCALE);
    top += player_model_fade_low;                              /* main's line, under the centre */
    base = origin[2] + term[2] - player_model_fade_sole;       /* a bone of model z drawn: base + d x z */
    at[2] = centre[2];
    for (casts = 0; casts < FLOOR_CASTS; casts++) {
        held = -1;   /* the next weight-bearing bone up, by (z, index) */
        for (b = 0; b < n; b++) {
            if (loose(b))
                continue;
            z = *(const float *)(bones + BONE_SIZE * b + BONE_Z);
            if (prev >= 0 && (z < last || (z == last && b <= prev)))
                continue;
            if (held < 0 || z < lz) {
                lz = z;
                held = b;
            }
        }
        if (held < 0 || top - (base + d * lz) <= need)
            break;   /* none left, or none this high needs more even over the centre's floor */
        last = lz;
        prev = held;
        bone = (const float *)(bones + BONE_SIZE * held + BONE_X);
        for (k = 0; k < 2; k++)
            at[k] = origin[k] + (d * bone[0] + term[0]) * matrix[k] + (d * bone[1] + term[1]) * matrix[4 + k]
                + (d * bone[2] + term[2]) * matrix[8 + k];
        k = floor_under(critter, at, player_model_fade_ray, &floor);
        if (!k)
            continue;   /* over a drop: it needs nothing */
        want = k < 0 || floor + player_model_fade_low >= top ? top : floor + player_model_fade_low;   /* main's at most */
        if (want - (base + d * lz) > need)
            need = want - (base + d * lz);
    }
    return need;
}

/* After 0x42070 wrote the drawn origin for a 0x42200 returning to ret:
 * raise it by the shortfall, the lift moving at most a step a tick from
 * the last clock's (a landing's exactly; one ending a fall begun off the
 * ride keeps a lift that met its need the tick its need first falls more
 * than a step under it), and past the window let go a step a tick; the
 * camera point's gets the game's origin and changes nothing. */
__attribute__((used))
void fade_floor(char *critter, float *origin, unsigned ret, const float *matrix)
{
    const char *clock;
    float lift, need;
    double now, dt;
    int held, met = 0;

    if (!critter || !(player_model_fade_ray > 0.0f) || !is_player(critter)
            || ret == *(const volatile unsigned *)player_model_fade_camera)
        return;
    held = fading(critter);
    clock = *(const char *const *)(critter + CR_CLOCK);
    if (!clock || player_model_fade_critter != critter)
        return;
    now = *(const double *)(clock + CK_TIME);
    if (now != player_model_fade_at) {   /* a new clock: its start, and how far the lift may move */
        dt = now - player_model_fade_at;
        player_model_fade_was = dt > 0.0 && dt < LIFT_FOR ? player_model_fade_lift : 0.0f;
        player_model_fade_was_met = dt > 0.0 && dt < LIFT_FOR && player_model_fade_met;
        player_model_fade_step = FADE_STEP * (float)(dt > 0.0 && dt < LIFT_FOR ? dt * TICK_HZ : 1.0);
        player_model_fade_at = now;
    }
    lift = 0.0f;
    if (held || player_model_fade_was > 0.0f) {
        need = shortfall(critter, origin, matrix);
        if (held) {
            lift = need;
            if (player_model_fade_landed != HOLD_EXACT) {
                if (lift > player_model_fade_was + player_model_fade_step)
                    lift = player_model_fade_was + player_model_fade_step;
                if (lift < player_model_fade_was - player_model_fade_step) {
                    lift = player_model_fade_was - player_model_fade_step;
                    if (player_model_fade_landed == HOLD_RODE && player_model_fade_was_met)
                        lift = player_model_fade_was;   /* a met lift kept over its need's fall */
                }
                met = need > 0.0f && lift == need;
            }
        } else {
            lift = player_model_fade_was - player_model_fade_step;
            if (need < lift)
                lift = need;
        }
        if (lift < 0.0f)
            lift = 0.0f;
    }
    player_model_fade_met = met;
    player_model_fade_lift = lift;
    origin[2] += lift;
}

/* 0x42237: critter_model_matrix's CALL of glide_origin (the critter and
 * the out on the stack, 0x42200's return address at [ESP + 0x2C], ESI
 * its matrix, the rotation rows written; RET 8, EAX = out). */
__attribute__((naked))
void c_player_model_fade_floor(void)
{
    __asm__ volatile (
        "pushl 0x8(%%esp)         \n\t"   /* the out     */
        "pushl 0x8(%%esp)         \n\t"   /* the critter */
        "calll _glide_origin@8    \n\t"
        "pushl %%eax              \n\t"   /* the out, kept */
        "pushl %%esi              \n\t"   /* the matrix  */
        "pushl 0x34(%%esp)        \n\t"   /* 0x42200's return address */
        "pushl %%eax              \n\t"
        "pushl 0x14(%%esp)        \n\t"   /* the critter */
        "calll _fade_floor        \n\t"
        "addl $16, %%esp          \n\t"
        "popl %%eax               \n\t"
        "retl $8                  \n\t"
        : : : "memory"
    );
}
