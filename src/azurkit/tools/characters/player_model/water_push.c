/* X29: a water push never leaves a tiny player body's camera under its
 * point (Step 2.116b, AZ-556; D115's default: framed as garret4 at x1,
 * whose pushes always leave his camera over his point).
 *
 * Why.  The level camera's water push 0x81E10 (called once a frame at
 * 0x81BEA; [ESP+4] the camera, EAX the point it aims at, RET 4) asks
 * 0x60BD0 for the water depth a0 at its probe point, the camera's place
 * less 0.4 m in z (cam.x, cam.y, cam.z - 0.4, its frame's +0x30..+0x38),
 * and acts only for 0 < a0 < 0.8: the camera within 0.4 m of the
 * surface (surface = probe.z + a0).  Its two candidates are built on
 * that probe point (0x81EEC-0x81F8B): over the surface (a0 <= 0.4,
 * 0x81F45) the first is the other side, c1.z = (a0 - 0.5) + probe.z =
 * surface - 0.5, the second its own side, c2.z = (a0 + 0.4) + probe.z =
 * surface + 0.4; under it (0x81EFD) the mirror, surface + 0.5 then
 * surface - 0.4; x and y the camera's.  0x81DB0 (camera_reach) puts each
 * at the point plus its offset as 0x81CA0 clamps it to the push's reach
 * (X25 scales both bounds), a clear sweep from the camera commits it
 * (+0x170, 0x61100) and 0x820E0 re-aims the camera from there, latching
 * the pitch and distance as the wanted ones; the first candidate's sweep
 * hit, the second's (0x82036); both hit, nothing.  Garret4's camera rises
 * 2.5 m over his point, so a push leaves it over (-20.6, -21.1, -29.6
 * degrees seen).  A body drawn under about 0.37 of his size has its
 * camera within the push's 0.9 m of its point (0.5 D(s) < 0.9), so the
 * far side put it under the point it aims at and the re-aim latched a
 * camera looking up at the body (+14 to +78 degrees, kept for hundreds of
 * ticks: x0.37, flicken, boulder, x0.1, water_tentacle3; read-az556).
 *
 * What.  This shim replaces the push's first 0x81DB0 CALL, at 0x81FEB
 * (EAX = &c1 at the caller's [ESP+0x2C], c2 at [ESP+0x20], 12 bytes
 * before it; ESI = &P, the point's copy at [ESP+0x14]; EDI = &out at
 * [ESP+0x50]; EBP the camera).  When the camera's target (+0x190) is the
 * player (its species' `player` flag 0x20) and c1.z < P.z <= c2.z (the far
 * side would put the camera under its point and its own side keeps it
 * at or over it), it swaps c1's and c2's 12 bytes in the caller's frame
 * and counts it (player_model_push_swaps); then it jumps to 0x81DB0.  So
 * the game sweeps its own side first and, if that hits (a ceiling within
 * 0.5 m over the water), takes the far side as its fallback (0x82036
 * reads [ESP+0x20], now c1's), as before.  A camera already under its
 * point in the band is swapped too (its own side over it).  Both under
 * the point (a camera under the water with the point high over it) or
 * both over keeps the game's order; so does every other critter's camera.
 * The candidates, the sweeps, the commit and the re-aim are the game's.
 *
 * R2 (Step 2.116d's, again in Step 2.116e; AZ-556 item 1): the hoist out
 * of the water (the 0x100 bit of PlayerControl's move state, the
 * critter's anim +0x200 0x41 hoist or 0x42 hoist_waist) keeps the game's
 * order.  Through the hoist
 * town_male_6's drawn origin stays at garret4's hang place and sinks
 * 0.566 m at every size, so x0.1's and x0.2's bodies are under the
 * water, and X29's swaps held a camera 0.4 m over an opaque surface: the
 * body not drawn (x0.1, 45 of 89 hoist ticks) or the frame dark (x0.2).
 * The game's order takes the camera under and the re-aim looks up at the
 * body, as main's (drawn 89 of 89: the view from under, the game's own
 * degrade; garret4's above-behind frame can't hold from either side
 * while the body is under the water).  R1 keeps that latch through the
 * hoist and, once the stand has lifted the rest place out of the band,
 * writes the base back and snaps to it.  Where the far
 * side's sweep hits the ledge the game's own fallback is the own side
 * (x0.37's hoist: pushed on every tick from about k322 in main, over the
 * water at +0.4 m), as before.  R2 needs R1: without it the beach after
 * an under-water hoist keeps main's +46 / +35 degree latch.
 * The build installs it with X27 (camera_plan's `near`, a rig scale under
 * 0.5): at the rest pitch it binds only under about s 0.374, and up to
 * 0.5 at a shallower stick pitch.
 *
 * ABI: 0x81DB0 takes EAX = the candidate, ESI = the point, EDI = the out
 * (a plain RET; returns EAX = EDI; clobbers ECX and EDX, which it writes
 * before it reads them), so the swap entry may use ECX and EDX, keeps EAX, EBX,
 * ESI, EDI and EBP and the x87 stack as it found them, and jumps to it
 * with the return to 0x81FF0 on the stack.  fucomip is a P6 instruction,
 * which the Pentium III has.
 */

#include "azurik_vanilla.h"   /* camera_reach, camera_water_push, volume_query */

int player_model_push_swaps __attribute__((used));   /* how many pushes took the camera's own side first */

__attribute__((naked))
void c_player_model_water_push(void)
{
    __asm__ volatile (
        "movl 0x190(%%ebp), %%edx            \n\t"   /* the camera's target */
        "testl %%edx, %%edx                  \n\t"
        "jz 9f                               \n\t"
        "movl 0x178(%%edx), %%ecx            \n\t"   /* its species */
        "testl %%ecx, %%ecx                  \n\t"
        "jz 9f                               \n\t"
        "testb $0x20, 0x64(%%ecx)            \n\t"   /* the player? */
        "jz 9f                               \n\t"
        "movl 0x180(%%edx), %%ecx            \n\t"   /* its PlayerControl */
        "testl %%ecx, %%ecx                  \n\t"
        "jz 1f                               \n\t"
        "testl $0x100, 0x94(%%ecx)           \n\t"   /* an aligned move? */
        "jz 1f                               \n\t"
        "movl 0x200(%%edx), %%ecx            \n\t"   /* its anim */
        "cmpl $0x41, %%ecx                   \n\t"   /* hoist */
        "je 9f                               \n\t"
        "cmpl $0x42, %%ecx                   \n\t"   /* hoist_waist: the game's order (R2) */
        "je 9f                               \n\t"
        "1:                                  \n\t"
        "flds 8(%%esi)                       \n\t"   /* P.z */
        "flds 8(%%eax)                       \n\t"   /* c1.z, P.z */
        "fucomip %%st(1), %%st               \n\t"
        "jp 8f                               \n\t"
        "jae 8f                              \n\t"   /* c1 not under the point: the game's */
        "flds -4(%%eax)                      \n\t"   /* c2.z, P.z */
        "fucomip %%st(1), %%st               \n\t"
        "jb 8f                               \n\t"   /* c2 under it too (or NaN): the game's */
        "fstp %%st(0)                        \n\t"
        "movl (%%eax), %%ecx                 \n\t"   /* swap c1 and c2, 12 bytes */
        "movl -0xc(%%eax), %%edx             \n\t"
        "movl %%ecx, -0xc(%%eax)             \n\t"
        "movl %%edx, (%%eax)                 \n\t"
        "movl 4(%%eax), %%ecx                \n\t"
        "movl -8(%%eax), %%edx               \n\t"
        "movl %%ecx, -8(%%eax)               \n\t"
        "movl %%edx, 4(%%eax)                \n\t"
        "movl 8(%%eax), %%ecx                \n\t"
        "movl -4(%%eax), %%edx               \n\t"
        "movl %%ecx, -4(%%eax)               \n\t"
        "movl %%edx, 8(%%eax)                \n\t"
        "incl _player_model_push_swaps       \n\t"
        "jmp 9f                              \n\t"
        "8:                                  \n\t"
        "fstp %%st(0)                        \n\t"
        "9:                                  \n\t"
        "jmp _camera_reach                   \n\t"
        : : : "memory"
    );
}

/* R1 (Step 2.116e, AZ-556; D115's default: at rest framed as garret4 at
 * x1, the game's -30 degrees and D(s), or the player's own pitch and zoom):
 * a push no longer latches a tiny body's camera at rest where the water
 * would let it rest.
 *
 * Why.  0x820E0's re-aim writes the pushed pitch and distance into the
 * wanted ones (+0x1A0, +0x1A4), and the update eases the pitch (+0x198)
 * toward the wanted one only by the sticks' sum (0x81872-0x81891:
 * [0x38BBE4] 30 deg/s x the sum, at most [0x38BBF4] 60 deg/s), so with
 * no stick held a pushed camera keeps the push's pitch and distance for
 * good.  With X29 a tiny body's placed rest latched -20 to -23 degrees
 * (garret4's own -20.6), a plunge -43 to -48 (his -20.6) and x0.1's beach
 * after the hoist level (-0.11) with its box out of the frame (2.116b's
 * sitting).  The update re-derives +0x198 and +0x19C from the committed
 * place every tick right after the push (0x81C37, 0x81C81), so the
 * wanted values are what a fix can hold, and the ease is where the pitch
 * moves (the Step 2.116d design's static-81BEF-81CA0).  Step 2.116d's R1
 * held each pushed value at what it was before the push and ended the
 * hold after a third of a second of pushes in a row; that guard tripped
 * inside the kit's placement and on x0.2's shore walk, and after a trip
 * the game's latch became the value every later hold restored, so it was
 * dropped.  This one owes no push anything.
 *
 * The latch entry (c_player_model_push_latch), at the push's CALL at
 * 0x81BEA (Europe 0x81B9A -> 0x81DC0), for the level camera whose target
 * is the player, each tick:
 *   1. base is what another writer last asked for: the reset's -30
 *      degrees and D(s) (0x811E0: [0x38BBFC] and [0x19814C], X25's rig),
 *      the player's stick pitch (0x81832) or D-pad zoom (0x81943), a
 *      room's pitch (0x81855), the early exit's re-aim (0x813A8).  A
 *      wanted value whose bits differ from what this entry left last call
 *      was written between calls; it is an ask (base := it, no longer
 *      held; the pitch's also disarms the snap) only when the camera
 *      wanted its base then, and, for the pitch, showed it: the stick
 *      writes +0x1A0 := +0x198 - rate x stick and the zoom +0x1A4 :=
 *      +0x19C - its step, the committed values, so a stick touched while
 *      a push's line still shows (held off, in the air or the hoist, or
 *      easing back after a push at rest) is a nudge of that line, never
 *      an ask (the Step 2.116e critique's 1).  `easing` keeps that state
 *      for the pitch: R1 holds it and the pitch committed at the call's
 *      end isn't its base.  The zoom has no such check (the regrow's few
 *      ticks after a restore; X25's sight pull keeps +0x19C short of its
 *      wanted value in a tight spot, where a check would refuse every
 *      zoom).
 *   2. The push runs (camera_water_push); `acts` counts the calls it
 *      changed a wanted value on.  A push that changes the pitch in the
 *      hoist out of the water (the 0x100 bit, anim 0x41 hoist or 0x42
 *      hoist_waist) arms the snap.
 *   3. At rest (move state 0, the ground, or 6, swimming), with a wanted
 *      value off its base: R is the place the camera would rest at,
 *      P + d (cos p u, -sin p) with (p, d) the base and u the unit of the
 *      camera's (+0x15C) horizontal from P (the camera's own x and y under
 *      1 mm).  The game's own volume query (volume_query, 0x60BD0) at R
 *      less 0.4 m in z, asked as the push asks it at the camera (touch 0:
 *      it sends no message), gives the depth a0; 0 < a0 < 0.8 is the
 *      push's own band at R, where the push would act every tick, so R1
 *      holds off (`off`, counted in `inband`) and the game's latch stays:
 *      a tiny body on the shore with its camera over the water, a wade,
 *      the stand before its pop.  Else each wanted value off its base is
 *      written back (held; `restores` counts the calls).  Swimming, X8's
 *      margins keep R 0.6 m over or under the surface, outside the band,
 *      so it restores every tick there.
 *   4. The snap's window: 0.5 s of rest calls that didn't hold off, from
 *      the hoist push that armed it (a held-off stand doesn't use it up:
 *      the critique's 2); out of rest and the hoist it disarms.
 * In the air (2), the hoist and the ladder the push's latch stays, the
 * game's; the next rest call that isn't held off writes the base back.
 *
 * The ease entry (c_player_model_push_ease), at the ease's dt multiply
 * 0x81891 (fmul [esp+0xbc], 7 bytes: a CALL and 2 NOPs; Europe 0x81841;
 * the one jump into the site, 0x81887's, lands on its first byte): the
 * game's rate unless the player is at rest with the pitch held and +0x1A0
 * holding its base (R1's write); then with the snap armed +0x198 := +0x1A0
 * at once (rate 0, so the clamp after adds nothing; counted in `snaps`),
 * which repeats on each later ease in the window, i.e. each tick the
 * stand's push or X8's re-derive put the committed pitch back off it, else
 * the rate is at least EASE_RATE, the game's 30 deg/s ([0x38BBE4]'s boot
 * value, which fps_unlock keeps by redirecting 0xFB608).  X25's regrow
 * (0x8196F NOPed; X29 builds always have the rig) brings +0x19C to the
 * held distance at 10 s m/s.  Its landing reads the latch landing's hold
 * through player_model_push_hold_at, a bytes param the build writes (each
 * hook lands its own copy of this object).
 *
 * ABI.  The latch entry is entered as 0x81E10 is ([ESP+4] the camera, EAX
 * the point, RET 4; the update's dt, its [ESP+0xBC], at [ESP+0xC4] over
 * the pushed camera and the return), keeps EBX (the update's 0), ESI,
 * EDI, EBP and an empty x87 stack, and may use EAX, ECX and EDX (0x81BEF,
 * 0x81BF3 and 0x81BF5 write them before any read).  The ease entry is
 * entered with ST0 the game's rate, ECX the camera and dt at
 * [ESP+4+0xBC], returns ST0 = the rate x dt, keeps ECX, EDX, EBX, ESI,
 * EDI and EBP, and may use EAX (0x818CE writes it).
 */

#define CA_WORLD      0x154   /* camera -> its world (+0xAC its volume tree) */
#define CA_PLACE      0x15C   /* camera: its place, float[3]                 */
#define CA_TARGET     0x190   /* camera -> the critter it follows            */
#define CA_PITCH      0x198   /* camera: its pitch, rad                      */
#define CA_WANT       0x1A0   /* camera: the wanted pitch, then distance     */
#define WD_TREE       0x0AC   /* world -> its volume tree                    */
#define CR_SPECIES    0x178   /* critter -> its species                      */
#define CR_CONTROL    0x180   /* critter -> its PlayerControl                */
#define CR_ANIM_INDEX 0x200   /* critter: its playing anim index             */
#define SP_FLAGS      0x064   /* species: its kind flags                     */
#define PLAYER_FLAG   0x20    /* the `player` feature                        */
#define PC_STATE      0x094   /* PlayerControl: its move state               */
#define GROUND        0
#define SWIMMING      6
#define HOIST_STATE   0x100   /* an aligned move (the hoist, the ladder)     */
#define HOIST         0x41    /* hoist                                       */
#define HOIST_WAIST   0x42    /* hoist_waist                                 */
#define BAND          0.4f    /* the push's band and probe drop: [0x198150]  */
#define SNAP_S        0.5f    /* s of rest calls a hoist latch's snap waits  */
#define EASE_RATE     0.52359878f   /* 30 deg/s in rad/s: [0x38BBE4]          */

struct push_hold {      /* offsets the model kit reads (scripts/sittings/model_kit.py) */
    unsigned base[2];   /* 0x00 what another writer last asked for (bits)  */
    unsigned last[2];   /* 0x08 the wanted two as this entry left them     */
    char *camera;       /* 0x10 whose                                      */
    int held;           /* 0x14 written back: bit 0 the pitch, 1 distance  */
    int snap;           /* 0x18 a hoist push latched the pitch             */
    float snap_s;       /* 0x1C s of rest calls not held off since         */
    int off;            /* 0x20 this call held off: the rest place in band */
    int restores;       /* 0x24 calls that wrote a value back              */
    int acts;           /* 0x28 calls whose push changed a wanted value    */
    int inband;         /* 0x2C calls held off                             */
    int snaps;          /* 0x30 snaps the ease entry made                  */
    int easing;         /* 0x34 the held pitch not committed at call's end */
};

struct push_hold player_model_push_hold __attribute__((used));
AZURIK_BYTES_PARAM(player_model_push_hold_at, 4);   /* the ease landing: the latch landing's hold */

static struct push_hold *hold(void)
{
    struct push_hold *at = *(struct push_hold *const volatile *)player_model_push_hold_at;

    return at ? at : &player_model_push_hold;
}

/* The camera's target when it is the player, else 0. */
static char *player_of(const char *camera)
{
    char *target = *(char *const *)(camera + CA_TARGET);
    const char *species;

    if (!target)
        return 0;
    species = *(const char *const *)(target + CR_SPECIES);
    return species && (*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) ? target : 0;
}

/* Its move state, -1 with no PlayerControl. */
static int move_state(const char *critter)
{
    const char *control = *(const char *const *)(critter + CR_CONTROL);

    return control ? *(const int *)(control + PC_STATE) : -1;
}

/* camera_water_push(camera) with EAX the point. */
__attribute__((naked, noinline, used))
static void water_push_at(char *camera, const float *point)
{
    __asm__ volatile (
        "movl 0x8(%%esp), %%eax              \n\t"   /* the point */
        "pushl 0x4(%%esp)                    \n\t"   /* the camera: RET 4 pops it */
        "calll \"_camera_water_push@4\"      \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}

static float as_float(unsigned bits)
{
    union { unsigned u; float f; } v;

    v.u = bits;
    return v.f;
}

static float rootf(float x)   /* SSE1's sqrtss: no libm */
{
    float r;

    __asm__ ("sqrtss %1, %0" : "=x"(r) : "x"(x));
    return r;
}

/* Whether the place the camera would rest at, its base pitch and distance
 * from the point, is inside the push's band: the game's own test there. */
static int rest_in_band(char *camera, const float *point, const struct push_hold *h)
{
    const float *at = (const float *)(camera + CA_PLACE);
    float pitch = as_float(h->base[0]), distance = as_float(h->base[1]);
    float dx = at[0] - point[0], dy = at[1] - point[1], across = rootf(dx * dx + dy * dy);
    float sine, cosine, probe[3], depth = 0.0f;
    unsigned flags[6];
    char *tree = *(char *const *)(*(char *const *)(camera + CA_WORLD) + WD_TREE);

    __asm__ ("fsin" : "=t"(sine) : "0"(pitch));     /* x87: no libm */
    __asm__ ("fcos" : "=t"(cosine) : "0"(pitch));
    if (across > 0.001f) {
        probe[0] = point[0] + distance * cosine * dx / across;
        probe[1] = point[1] + distance * cosine * dy / across;
    } else {
        probe[0] = at[0];
        probe[1] = at[1];
    }
    probe[2] = point[2] - distance * sine - BAND;
    volume_query(tree, probe, camera, flags, &depth, 0);
    return depth > 0.0f && depth < BAND + BAND;
}

__attribute__((stdcall, used))
void player_model_push_latched(char *camera, const float *point, float dt)
{
    struct push_hold *h = hold();
    unsigned *want = (unsigned *)(camera + CA_WANT);
    char *player = player_of(camera);
    unsigned pre[2];
    int state, k;

    if (!player) {
        water_push_at(camera, point);
        return;
    }
    state = move_state(player);
    if (h->camera != camera) {   /* a new camera: its values are the base */
        h->camera = camera;
        h->held = h->snap = h->easing = 0;
        h->snap_s = 0.0f;
        h->base[0] = h->last[0] = want[0];
        h->base[1] = h->last[1] = want[1];
    }
    for (k = 0; k < 2; k++) {
        if (want[k] != h->last[k] && h->last[k] == h->base[k] && !(k == 0 && h->easing)) {
            h->base[k] = want[k];   /* another writer's ask */
            h->held &= ~(1 << k);
            if (!k)
                h->snap = 0;
        }
        pre[k] = want[k];
    }
    water_push_at(camera, point);
    if (want[0] != pre[0] || want[1] != pre[1]) {
        h->acts++;
        if (want[0] != pre[0] && state != -1 && (state & HOIST_STATE)) {
            int anim = *(const int *)(player + CR_ANIM_INDEX);

            if (anim == HOIST || anim == HOIST_WAIST) {
                h->snap = 1;
                h->snap_s = 0.0f;
            }
        }
    }
    h->off = 0;
    if (state == GROUND || state == SWIMMING) {
        if (want[0] != h->base[0] || want[1] != h->base[1]) {
            if (rest_in_band(camera, point, h)) {   /* where the game itself pushes: its latch */
                h->off = 1;
                h->inband++;
            } else {
                for (k = 0; k < 2; k++)
                    if (want[k] != h->base[k]) {
                        want[k] = h->base[k];
                        h->held |= 1 << k;
                    }
                h->restores++;
            }
        }
        if (h->snap && !h->off) {
            h->snap_s += dt;
            if (h->snap_s > SNAP_S)
                h->snap = 0;
        }
    } else if (state == -1 || !(state & HOIST_STATE))
        h->snap = 0;
    h->last[0] = want[0];
    h->last[1] = want[1];
    h->easing = (h->held & 1) && *(const unsigned *)(camera + CA_PITCH) != h->base[0];
}

__attribute__((naked))
void c_player_model_push_latch(void)
{
    __asm__ volatile (
        "pushl 0xc4(%%esp)                   \n\t"   /* dt, the update's [ESP+0xBC] */
        "pushl %%eax                         \n\t"   /* the point  */
        "pushl 0xc(%%esp)                    \n\t"   /* the camera */
        "calll \"_player_model_push_latched@12\" \n\t"
        "retl $4                             \n\t"
        : : : "memory"
    );
}

__attribute__((stdcall, used))
float player_model_push_eased(char *camera, float rate)
{
    struct push_hold *h = hold();
    char *player;
    int state;

    if (h->camera != camera || !(h->held & 1) || *(const unsigned *)(camera + CA_WANT) != h->base[0])
        return rate;
    player = player_of(camera);
    state = player ? move_state(player) : -1;
    if (state != GROUND && state != SWIMMING)
        return rate;
    if (h->snap) {   /* after a hoist latch: the base pitch at once, again while the window lasts */
        *(float *)(camera + CA_PITCH) = *(const float *)(camera + CA_WANT);
        h->snaps++;
        return 0.0f;
    }
    return rate > EASE_RATE ? rate : EASE_RATE;
}

__attribute__((naked))
void c_player_model_push_ease(void)
{
    __asm__ volatile (
        "pushl %%ecx                         \n\t"   /* kept */
        "pushl %%edx                         \n\t"   /* kept */
        "subl $4, %%esp                      \n\t"
        "fstps (%%esp)                       \n\t"   /* the game's rate */
        "pushl %%ecx                         \n\t"   /* the camera      */
        "calll \"_player_model_push_eased@8\" \n\t"
        "fmuls 0xc8(%%esp)                   \n\t"   /* x dt, the game's [ESP+0xBC] */
        "popl %%edx                          \n\t"
        "popl %%ecx                          \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}
