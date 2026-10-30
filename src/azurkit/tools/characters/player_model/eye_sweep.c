/* X19: the camera keeps its distance from a player model's tall camera
 * point where a line from garret4's eye height is clear (Step 2.104,
 * AZ-520's zipline part; D115's default: garret4's camera there, the
 * point's height aside).
 *
 * Why.  The level camera's 0x80FB0 (ESI the camera, ECX the point it
 * aims at; its wanted place is that point less the camera's forward,
 * EDI's quaternion through 0xA08D0, times the distance on the stack:
 * Step 2.107) sweeps a 0.096 m ellipsoid (collision_sweep, 0x60870; radii
 * [0x38BC00], mask 0x40) from its target's body centre (the target is
 * the camera's +0x190; its +0x15C) to the point it aims at (0x81061),
 * then from that point to the wanted camera place (the CALL at
 * 0x810F3), and on a hit pulls the camera in to the hit (0x810FC on).
 * The camera's distance (+0x19C) then grows back toward the wanted one
 * only while a stick is held (0x81952: 10 x the stick deflections m/s),
 * so a camera pulled in at rest stays in (but under X25's rig, which
 * regrows it at rest: Step 2.107).  X8 puts a body's point at
 * its top, which on a tall body (golem own 1.80 m above garret4's eye,
 * a body drawn x2 about 2 m above) runs the second sweep into geometry
 * garret4's passes under: at the high end of f3's zipline its anchor
 * beam, 0.26-0.62 m above the cable's end, pulled the camera to
 * 0.6-0.7 m from the point at -30 degrees, where the control keeps 5.0
 * (sitting 2.103's row C, AZ-520) [inferred: the beam from f3's static
 * collision at the D98 spot; the sitting row checks AL and the
 * fraction at 0x810F8].
 *
 * What.  This shim replaces that CALL.  It runs the game's sweep; on a
 * hit, when the camera's target is the player (its species' `player`
 * flag 0x20) and not swimming (PlayerControl, critter+0x180, move state
 * 6 at +0x94: X8's swim point has its own rules), it sweeps again from
 * the point lowered by player_model_eye_lift (how far the build's point
 * sits above garret4's eye height, metres) along the line from the
 * body's centre to the point, never below the centre, to the same
 * place, into a hit record of its own.  When that is clear it returns
 * AL 0, so the camera keeps its wanted place (the line from the lowered
 * point to it was swept, so the camera can't sit inside geometry, and
 * it is never nearer than the game's); otherwise the game's own hit,
 * its record untouched by the second sweep.  The build installs it only
 * when the lift is above 0.
 *
 * The line of sight (Step 2.107, SITTING-PLAN F2 as the code has it).
 * On every tick 0x80C40's slide completes (AL 1, hit or not; a failed
 * slide places the camera at its wanted distance), the level camera
 * tests its line of sight (0x80C10, its CALL of collision_sweep at
 * 0x80C35) from its own place (its +0x15C) to the point; blocked for
 * 0.8 s ([0x19817C], the timer
 * +0x1B4) it puts the camera back through 0x80FB0, which pulls it to the
 * point's hit.  A camera X19 kept by its lowered line then still lost
 * the sight of the high point: on a1's ladder every body drawn x2 or
 * more snapped in 7-14 m each climb (sitting 2.107 C).  The second entry
 * tests the same lowered point, the same way: on a hit for the player,
 * not swimming, it sweeps again from the camera's place to the point
 * lowered by the lift (the sweep's `to` end here), and a clear line is
 * a clear sight.  The camera's place is the game's; only the 0.8 s pull
 * follows garret4's eye height instead of the drawn top.
 *
 * The pull at garret4's 0.33 s, where the game's 0.8 s would pull (Step
 * 2.116b, D286's limit 4, AZ-555).  Where both lines stay blocked the
 * game's own 0x81B94 / 0x81BAA / 0x81BC6 pull the camera on its 24th
 * blocked test at 30 a second (the timer +0x1B4 strictly past 0.8 s,
 * [0x19817C]), in one step onto the first hit from the point: a rig
 * drawn x2 or more on a1's ladder, its camera over the floor slab the
 * body climbs under, was hidden 24 tests and then pulled 7.4-9.4 m,
 * where garret4's line, blocked 8-9 tests by a beam, slides in onto the
 * same rim; at a1's wall turned 180 degrees (s 3.0-3.3) 24 tests, then
 * 5.2-5.8 m.  Step 2.116's near-hit pull at 0.29 s (the game's hit
 * within 5.11 m) also pulled runs that clear by themselves (x2's drop
 * into a1's pit after 11 tests, x2.7's climb after 21), so it was
 * dropped.  This entry now asks the game's own question early: on a
 * blocked test whose lowered line is blocked too, for the player on the
 * ground or the ladder climb (move state 0 or 1, PlayerControl +0x94, as
 * lowered() reads it), with the timer at entry (before 0x81B94 adds this
 * tick's dt) at least 0.29 s (9 x dt = 0.3 at the 10th test, the 19th at
 * 60 a second; garret4's longest blocked run is 10 tests), dt = that
 * timer less the last call's in (0, 0.1], and the motion steady since
 * the last call (the camera's yaw +0x194, pitch +0x198 and distance
 * +0x19C each moved under 0.002, so it follows the point rigidly: they
 * hold still while the camera rises with the point; the point's step v,
 * this call's `to` less the last's, within 0.5 |v| + 0.6 m/s x dt of the
 * last step), it moves both of the game's lines on by m = (0.8 - timer)
 * / dt - 1 steps (14 at the 10th test: to the game's 24th test) and
 * sweeps them, from + m v to to + m v and to low + m v, into its own
 * record with the game's radii and mask.  Both blocked: the game would
 * pull this run on its 24th test, so the entry writes 1.0 into +0x1B4
 * and the game pulls it this tick onto the same first hit (hidden 0.33
 * s, garret4's longest, not 0.8 s).  Either clear (x2.7's climb, whose
 * 24th line clears, 2 ticks of climb of margin): the timer is the
 * game's.  Over Step 2.116's 106 blocked runs of the X19 builds it moved
 * each of the 27 timer pulls 14 tests sooner and added none
 * (design-b's rb-rule-scan.txt; a scan of the before builds' own 24th
 * lines under rigid motion).  The rule's error is one tick of the
 * point's motion (the float timer may pull on the 24th test or the 25th),
 * which at x2.6 on a1's ladder is its whole margin (0-1 tick).  Named,
 * not changed: the one-tick step itself (now 14 ticks sooner), the
 * rim's close frame, the regrow over the floor, f3's ride at x3.3 (a
 * failed slide, not the timer), and a steady walk whose present and
 * 24th-test lines are both blocked but the ticks between clear (pillars),
 * the one way it can add a pull (a sitting row).
 *
 * B2: the regrow waits for garret4's own line (Step 2.116d, AZ-555; D115's
 * default: framed as garret4 is at x1).  X25's regrow (0x81952-0x81A04,
 * its stick multiply NOPed) grows a pulled-in camera's distance (+0x19C)
 * toward the wanted one (+0x1A4) by its step, 10 s m/s, from the tick the
 * point's -30 degree line clears the rim's corner; a rig's point is
 * 1.9925 (s - 1) m over garret4's, so on a1's ladder x2.2 regrew at k138
 * against his k173, leaving his close frame 35 ticks early (the Step
 * 2.116d design's b2-sim; its sitting's pictures show main's body in the
 * hatch then, not under the floor).  The third entry replaces
 * the step's add, `fld [esp+0x1c]; fadd [eax+0x19c]` at 0x819C9 (10 bytes,
 * a CALL and 5 NOPs; Europe 0x81979; the game's fstp at 0x819D3 stores the
 * ST0 it returns): on a growing step, for the player not swimming with the
 * point over its centre (lowered(), as the other two entries) and the
 * camera's place (+0x15C) over 1 mm from the point, it sweeps from the
 * point lowered by the lift out along the camera's direction from the
 * point to the grown distance, d + step (the tree, radii and mask the
 * sight's 0x80C10-0x80C35 uses: the radius the sight entry's landing keeps
 * from the game's arguments, read through player_model_sight_radius_at,
 * a bytes param the build writes); blocked, the distance holds (counted in
 * player_model_regrow_holds); clear, it grows.  A shrinking step, another
 * target, swimming, no radius yet (before any sight test) and a point at or
 * under the centre are the game's.  On the zipline ride X20 puts the point
 * at the centre or over it (x3.3's 0.0, x2's 0.0-0.504 m: the read-limit4
 * k5-f3 rows), so lowered() returns the centre itself as the low point
 * where the point sits under the lift: B2 sweeps from there, garret4's own
 * ride point, and is inert where no pull happened.  The build installs it
 * when X19 and X25's rig both are.  Its price: the rim's overfilled close
 * frame (garret4's own s times larger) holds until garret4's line clears
 * (modelled 56-60 ticks, the game's regrow 16-29).
 *
 * ABI: collision_sweep is __stdcall(36) (the tree, the camera, 0, from,
 * to, the two radii, the mask, the hit record; RET 0x24), AL its answer,
 * with no register input; 0x80FB0 reads only AL after it (0x810F8) and
 * the record only on a hit.  The first two entries are __stdcall(36) too,
 * keep EBX, ESI, EDI and EBP, and leave the x87 stack empty.  The regrow
 * entry is entered with EAX the camera (0x819C5), the step at
 * [ESP+4+0x1C], the point at [ESP+4+0x50] and an empty x87 stack, returns
 * ST0 the new distance and keeps every register (ECX is rewritten at
 * 0x819D9).
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

#define CA_TARGET    0x190   /* camera -> the critter it follows          */
#define CR_CENTRE    0x15C   /* critter: its body centre (x, y, z)        */
#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl (the player's) */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define PC_STATE     0x094   /* PlayerControl: its move state              */
#define SWIMMING     6
#define HIT_SIZE     0x50    /* collision_sweep writes 0x48 bytes on a hit */
#define CA_YAW       0x194   /* camera: its yaw, rad                        */
#define CA_PITCH     0x198   /* camera: its pitch, rad                      */
#define CA_DISTANCE  0x19C   /* camera: its distance from the point, m      */
#define CA_BLOCKED   0x1B4   /* camera: how long its sight has been blocked, s */
#define GROUND       0       /* move states R-B acts in: the ground          */
#define LADDER       1       /* and the ladder climb                         */
#define SIGHT_WAIT   0.29f   /* the 10th blocked test at 30 a second (9 x dt = 0.3), the 19th at 60 */
#define SIGHT_AT     0.8f    /* the game's pull: past [0x19817C] (0x81BAA), unscaled */
#define SIGHT_PULL   1.0f    /* past it: the game pulls this tick          */
#define DT_MAX       0.1f    /* a longer gap since the last call: another run's */
#define HELD         0.002f  /* the camera's yaw, pitch (rad) and distance (m) held */
#define STEP_SHARE   0.5f    /* the point's step held: within 0.5 x its length */
#define STEP_SLACK   0.6f    /* + 0.6 m/s x dt                             */

/* The last call's to (0-2), the camera's yaw, pitch and distance (3-5),
 * the point's step (6-8) and the timer at entry (9). */
float player_model_sight_last[10] __attribute__((used));
float player_model_sight_radius __attribute__((used));   /* the rxy the game passes the sight test (B2's) */
int player_model_regrow_holds __attribute__((used));     /* regrow steps B2 held */

AZURIK_FLOAT_PARAM(player_model_eye_lift, 0.0f);
AZURIK_BYTES_PARAM(player_model_sight_radius_at, 4);    /* the regrow landing: the sight landing's radius */

/* The point ``end`` lowered by the lift on the line from the camera's
 * target's centre, never below it, into ``low``: 1 when the target is the
 * player, not swimming, with the point over its centre (its move state in
 * ``state``); else 0. */
static int lowered(const char *camera, const float *end, float *low, int *state)
{
    const char *target, *control;
    const float *centre;
    float dz, t, lift = player_model_eye_lift;
    int k;

    if (!(lift > 0.0f) || !camera)
        return 0;
    target = *(const char *const *)(camera + CA_TARGET);
    if (!target || !(*(const unsigned *)(*(const char *const *)(target + CR_SPECIES) + SP_FLAGS) & PLAYER_FLAG))
        return 0;
    control = *(const char *const *)(target + CR_CONTROL);
    *state = control ? *(const int *)(control + PC_STATE) : -1;
    if (*state == SWIMMING)
        return 0;
    centre = (const float *)(target + CR_CENTRE);
    dz = end[2] - centre[2];
    if (!(dz > 0.0f))
        return 0;
    t = dz > lift ? (dz - lift) / dz : 0.0f;
    for (k = 0; k < 3; k++)
        low[k] = centre[k] + (end[k] - centre[k]) * t;
    return 1;
}

/* X19: 0x80FB0's sweep from the point (``from``) to the wanted place. */
__attribute__((stdcall))
unsigned char c_player_model_eye_sweep(void *tree, char *camera, int zero, const float *from, const float *to,
                                       float rxy, float rz, unsigned mask, void *hit)
{
    unsigned char got = collision_sweep(tree, camera, zero, from, to, rxy, rz, mask, hit);
    float low[3];
    unsigned mine[HIT_SIZE / 4];
    int state;

    if (!got || !lowered(camera, from, low, &state))
        return got;
    if (collision_sweep(tree, camera, zero, low, to, rxy, rz, mask, mine))
        return got;
    return 0;
}

static float absf(float x)
{
    return x < 0.0f ? -x : x;
}

static float rootf(float x)   /* SSE1's sqrtss: no libm */
{
    float r;

    __asm__ ("sqrtss %1, %0" : "=x"(r) : "x"(x));
    return r;
}

/* R-B: whether the game will pull this blocked run on its 24th test, by
 * its two lines (from -> to, from -> low) moved there by the steady point
 * (the comment at the top); the sweeps into ``mine``. */
static int pulls(void *tree, char *camera, int zero, const float *from, const float *to, const float *low,
                 float rxy, float rz, unsigned mask, unsigned *mine, int state)
{
    const float *last = player_model_sight_last;
    float e = *(const float *)(camera + CA_BLOCKED), dt = e - last[9], v[3], a[3], b[3], c[3], step = 0.0f,
          off = 0.0f, m;
    int k;

    if ((state != GROUND && state != LADDER) || !(e >= SIGHT_WAIT) || !(dt > 0.0f && dt <= DT_MAX))
        return 0;
    if (!(absf(*(const float *)(camera + CA_YAW) - last[3]) < HELD)
            || !(absf(*(const float *)(camera + CA_PITCH) - last[4]) < HELD)
            || !(absf(*(const float *)(camera + CA_DISTANCE) - last[5]) < HELD))
        return 0;
    for (k = 0; k < 3; k++) {
        v[k] = to[k] - last[k];
        step += v[k] * v[k];
        off += (v[k] - last[6 + k]) * (v[k] - last[6 + k]);
    }
    if (!(rootf(off) <= STEP_SHARE * rootf(step) + STEP_SLACK * dt))
        return 0;
    m = (SIGHT_AT - e) / dt - 1.0f;
    for (k = 0; k < 3; k++) {
        a[k] = from[k] + m * v[k];
        b[k] = to[k] + m * v[k];
        c[k] = low[k] + m * v[k];
    }
    return collision_sweep(tree, camera, zero, a, b, rxy, rz, mask, mine)
        && collision_sweep(tree, camera, zero, a, c, rxy, rz, mask, mine);
}

/* The line of sight: 0x80C10's sweep from the camera's place to the point
 * (``to``). */
__attribute__((stdcall))
unsigned char c_player_model_eye_sight(void *tree, char *camera, int zero, const float *from, const float *to,
                                       float rxy, float rz, unsigned mask, void *hit)
{
    unsigned char got = collision_sweep(tree, camera, zero, from, to, rxy, rz, mask, hit);
    float low[3], e;
    unsigned mine[HIT_SIZE / 4];
    int state, k;

    player_model_sight_radius = rxy;   /* B2's radius */
    if (!got || !lowered(camera, to, low, &state))
        return got;
    e = *(const float *)(camera + CA_BLOCKED);
    if (!collision_sweep(tree, camera, zero, from, low, rxy, rz, mask, mine))
        got = 0;
    else if (pulls(tree, camera, zero, from, to, low, rxy, rz, mask, mine, state))
        *(float *)(camera + CA_BLOCKED) = SIGHT_PULL;   /* the game pulls it this tick */
    for (k = 0; k < 3; k++) {   /* this call, for the next */
        player_model_sight_last[6 + k] = to[k] - player_model_sight_last[k];
        player_model_sight_last[k] = to[k];
    }
    player_model_sight_last[3] = *(const float *)(camera + CA_YAW);
    player_model_sight_last[4] = *(const float *)(camera + CA_PITCH);
    player_model_sight_last[5] = *(const float *)(camera + CA_DISTANCE);
    player_model_sight_last[9] = e;
    return got;
}

#define CA_WORLD     0x154   /* camera -> its world                          */
#define WORLD_TREE   0x0AC   /* world -> its collision tree                  */
#define CA_PLACE     0x15C   /* camera: its place (x, y, z)                  */
#define SIGHT_MASK   0x40    /* the sight's sweep mask (0x80C1D)             */
#define NEAR_MIN     0.001f  /* 1 mm: a camera on its point has no direction */

/* B2: the regrow step's add at 0x819C9, the new distance. */
__attribute__((stdcall, used))
float player_model_eye_regrown(char *camera, float step, const float *point)
{
    const float *at = *(const float *const volatile *)player_model_sight_radius_at;
    const float *c = (const float *)(camera + CA_PLACE);
    float d = *(const float *)(camera + CA_DISTANCE), r = at ? *at : player_model_sight_radius, low[3], to[3], v[3],
          n = 0.0f, k;
    unsigned mine[HIT_SIZE / 4];
    int state, i;

    if (!(step > 0.0f) || !(r > 0.0f) || !lowered(camera, point, low, &state))
        return d + step;
    for (i = 0; i < 3; i++) {
        v[i] = c[i] - point[i];
        n += v[i] * v[i];
    }
    n = rootf(n);
    if (!(n > NEAR_MIN))
        return d + step;
    k = (d + step) / n;
    for (i = 0; i < 3; i++)
        to[i] = low[i] + v[i] * k;
    if (!collision_sweep(*(void *const *)(*(const char *const *)(camera + CA_WORLD) + WORLD_TREE), camera, 0, low, to,
                         r, r, SIGHT_MASK, mine))
        return d + step;
    player_model_regrow_holds++;   /* garret4's line still blocked: held */
    return d;
}

__attribute__((naked))
void c_player_model_eye_regrow(void)
{
    __asm__ volatile (
        "pushl %%eax                         \n\t"   /* kept: 0x819D3 stores through it */
        "pushl %%ecx                         \n\t"
        "pushl %%edx                         \n\t"
        "leal 0x60(%%esp), %%ecx             \n\t"   /* the point, the update's [ESP+0x50] */
        "pushl %%ecx                         \n\t"
        "pushl 0x30(%%esp)                   \n\t"   /* the step, its [ESP+0x1C] */
        "pushl %%eax                         \n\t"   /* the camera */
        "calll \"_player_model_eye_regrown@12\" \n\t"
        "popl %%edx                          \n\t"
        "popl %%ecx                          \n\t"
        "popl %%eax                          \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}
