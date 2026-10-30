/* X38: a worn body's ranged attack effects play out in their own fx
 * instances, which the next attack never touches (Step 2.149; D429, the
 * owner: "is it possible to make the wind puff visual effect not rewind
 * back to the player (or not abruptly end) when the next attack is used?";
 * D430: "have this be generalized to all models' ranged attacks").
 *
 * Why.  A body's attack effects are parts of its one fx_default instance
 * (critter+0x230), bound by name to markers its clip keys: a switch
 * marker's translateZ drives an emitter's rate through a link, a carrier
 * marker moves the emitter (and, under it, a marker-space particle
 * system: the air elemental's puff).  The next clip change crossfades
 * every marker to the new clip's keys or the body's rest in 0.1-0.25 s, so
 * the puff rides home with all its particles and every other effect stops
 * where it was.
 *
 * What.  Each ranged attack's look is a second instance of the graph
 * (fx_instantiate 0x649E0 into a handle of this object's ring, flags 0:
 * a release only unlinks it), bound to the player's markers as the own
 * one is, so the clip drives it as it drives the own one; the own
 * instance's emitters a copy shows are written off (by value, every
 * tick: list OWN), so nothing draws twice.  When the clip is replaced (the
 * next attack, a held re-throw, a hit reaction, the idle after it) the
 * copy is detached (fx_instance_detach 0x634B0): its nodes stay in the
 * world where they were, its particles age where they were born, and each
 * emitter the clip had on (a window of the table) runs on to its window's
 * end on the clip's clock (the layer's time at the detach, then the clock
 * times the layer's rate), or, on the body's rig, 0.33 s after the
 * detach; then its rate fades to 0 over RAMP_S, its close attribute (one
 * no link writes; none when that is its system's enable, which would
 * blank the system's particles at once) goes to 0, and once every window
 * is closed and its tail (the longest particle life) is over the copy is
 * marked dead (instance+0x2C bit 0): the scene's sweep deletes it and
 * the engine zeroes this ring's handle (0x63170 -> 0xA4420).  A P key (the air
 * elemental's own graph, whose puff a throw carries) keeps one copy bound
 * at all times, carrying the body's ambient look: a throw arms it, the
 * next clip change detaches it out where the throw left it, and a fresh
 * one is spawned at the body.  The own instance's emitters a copy shows
 * stay off for the crossfade and a tick after its detach, while the
 * clip change slides their markers home.  Hits never travel: a copy's
 * damage platforms are zeroed (D115).  An E copy armed on one clip has
 * its key's other clips' windows closed, so a copy spawned in another
 * clip's crossfade shows none of that clip's emitters (AZ-652).
 *
 * A STAND key (D434, Step 2.155: the worn air elemental's gust ends in
 * spideyzar's tornado standing where it ends): another graph, spawned
 * bound and dark (every switch of it rests at z 0 on the body's grown
 * markers, its at-rest emitters closed) at each entry of a clip whose
 * tail it has, carried by the clip's marker, detached by the next clip
 * change like any armed copy; then its nodes stand where they were and
 * its HOLD ops (the trigger's translateZ) go value x z, z rising as
 * spideyzar's own trigger does, 1 - (1 - a/0.8)^2 over a = 0.8 s from
 * the detach, held to its key's hold, falling to 0 over STAND_FALL_S; the
 * graph's links grow the funnel and feed its emitters.  It is dead once
 * that and its tail are over.  A copy detached before its carrier left
 * (the clip's ClipSpec.first, ms) or never loaded while bound stands
 * nothing: dead at the detach.  A STAND key wraps only onto a faded copy
 * (AZ-689): with every handle of it holding a live copy, the oldest let
 * go hold + STAND_FALL_S ago or more (its trigger back at 0: the funnel
 * gone, only its particles' tail left) ends and the gust takes its
 * handle; with none faded no copy is spawned, so no funnel still showing
 * is cut (AZ-661).  Every gust spawns its copy; one let go by
 * the next gust's entry (a held chain: an attack whose clip carries its
 * key) stands nothing, dead at the detach, while another of its key
 * stands that was let go under STAND_GAP ago (AZ-664: about every other
 * gust of a held chain stands, so the funnels spread over a funnel's life
 * and one is always rising, where four let go in 2.6 s faded together);
 * one let go by any other clip change (the idle after a chain's or a
 * double tap's last gust, another attack's entry), a hit or the death
 * always stands (AZ-671).  No pSystem attribute is written (2.146's
 * updateRate write hung the game).
 *
 * A drain row (AZ-653, Step 2.153c: Balthazar's attack_2 with X37
 * installed): its switch turns on an emitter and a damage platform under
 * a mode-7 node, which X37 anchors on the drain's target.  Its copy plays
 * the drain bound as the own instance does (their boxes coincide: one
 * hit a tick), and at the detach (the next swing) the platform's damage
 * goes to 0 (list DETACH: the link rewrote the SPAWN write while bound)
 * and {the copy, X37's target} goes into X37's held list (bytes param
 * player_model_fx_ring_drain_at, X37's state; 0 without X37), so its
 * mode-7 nodes stay on the target and the stream plays on there.  Its
 * window closes by its switch (Win flag SWITCH) at the window's end: the
 * switch's translateZ := 0, the links take the emitter's enable and the
 * platform's damage to 0, the particles age out, and the copy leaves the
 * held list.  It closes so at once, before the window's end, when its
 * held entry has no target (AZ-684, Step 2.153d: X37 dropped it, dead or
 * deleted, or held none at the detach, and anchors the copy's nodes on
 * the player), so its stream
 * never plays at the wearer; the copy still lives to the window's end
 * and its tail.  Inside the drain (D567, Step 2.153e, the owner: "Stop
 * when it dies"), a bound drain row's copy whose drain held a target
 * since its arm (X37's seen stamp moved past the one noted at the arm,
 * so a target left from an earlier window counts for nothing, and its
 * target was set) and holds none now (X37 dropped it, dead or deleted,
 * and picked no other in reach) is detached at the tick that sees it:
 * held with no target, its switch closes at once as above, its last
 * particles age out where the target was; the own instance's emitters
 * it showed stay off until the clip changes and that crossfade and a
 * tick are over (Ring.cut), so the stream never plays at the wearer up
 * to his next swing (the anchor's no-target rule).  A drain that never
 * held a target streams as before.  Another clip's copy closes a SWITCH
 * window through its close (the stream's pool [2]'s enable: no link
 * writes it) at the arm,
 * so a beam copy spawned in the drain's crossfade draws no drain stream
 * (2.155's spawn close, moved to others_off), and takes none of its box's
 * damage (AZ-683, Step 2.175d): at the arm the links into a drain box's
 * damage (a DETACH op's) get factor 0 on it (the records pass 0x663B0
 * runs a bound switch's links each tick it moves and writes curve(z x
 * weight) x factor, 0x6646E), so the fading switch rewrites no damage; and
 * at the load every copy's damage platform drops the level its graph
 * authored at once (its world object's byte +0x27E, which the sync 0x6ADE7
 * writes from (int) damage and the touch tests at 0x7A189), where the
 * SPAWN write reaches it only at the copy's first records pass, after a
 * touch in the spawn's frame.
 *
 * A BOUND key (Step 2.167c, D538's E3: a recipe's or a weapon style's
 * shield or beam effects row) is a graph of its own (the template's sets
 * under a holder bound to m_root or placed at the feet or the hand), one
 * handle past the own and stand keys' 16.  At each entry of a clip that
 * plays it (ClipSpec.first 1) its live copy is re-armed, else one is
 * spawned bound and armed; while armed its SHOW ops are written at their
 * values every tick; the next clip change, a hit or the death lets it go
 * (no detach: it stays on the body), its SHOW ops falling to 0 over its
 * fade (KeySpec.hold_ms), and it is dead its clip's tail (its particles'
 * life) after the fade.
 *
 * The table (bytes param player_model_fx_ring_table, the build's
 * _player_fx_ring.py): its key (the body's fx_default: its mode, its
 * slots in the ring, its record count, whether its carried emitters wait
 * out the crossfade, its writes), each row's clip (24 attacks_anims
 * columns, then X10's ring entries) and per clip its windows and tail.
 *
 * Three landings of this object:
 *   c_player_model_fx_ring_spawn at player_attack_enter's (0x88990) CALL
 *   of quat_from_euler 0x4FF10 at 0x88A5E (Europe 0x88A0E), every attack
 *   entry after its clip change (0x889A6) and its rate (0x889BB): the
 *   call, then fx_ring_spawn(EDI, the PlayerControl): every armed copy
 *   detached, the live layer noted, the row's copies spawned (or the P
 *   key's resting one) and armed on it.
 *   c_player_model_fx_ring_tick at the anim step's (0x43A00, ESI the
 *   critter) CALL of anim_sample_markers 0xCBC80 at 0x43A62 (Europe
 *   0x43A62, its CALL 0xCBE00): the call, then fx_ring_tick(ESI), which
 *   returns at once for every critter but the player and else: the own
 *   instance's writes, the death (HP at +0x210 <= 0: every bound copy
 *   detached, no spawn until HP is back over 0), a clip change (the live
 *   layer, anim+0x10's, another one, another clip, or its time gone back)
 *   detaching the armed copies, a P key's resting copy, and each
 *   copy's writes, delay, windows and end.  Every step keys on the clock
 *   and the layers, so the anim step's two callers (0x43AAD, 0x8C8F7) may
 *   both run it in a tick.
 *   c_player_model_fx_ring_hit at the player hit handler's (0x8D600, ESI
 *   the PlayerControl) CALL of apply_damage 0x44640 at 0x8D6AF (Europe
 *   0x8D65F), after X7's reaction change at 0x8D682 (AZ-650, Step 2.155):
 *   the call, then fx_ring_hit(the critter): the change noted and the
 *   armed copies detached where they are, before the re-samples of the
 *   tick's instance ticks (0x4030B, inside the bind sets' walk) move
 *   their markers to the reaction's pose.  No spawn, sweep or death rule
 *   there: the tick does those.
 * The state (the ring) is the spawn landing's .bss; the other landings
 * reach it through bytes param player_model_fx_ring_at (0 in the spawn
 * landing: its own).  Bytes param player_model_fx_rotation_at is X10's
 * ring when the build has one (0: none): a rotating column's row is the
 * entry it just played; player_model_fx_ring_drain_at is X37's state
 * when the build has X37 (0: none), whose held list the detach of a
 * drain row's copy fills, its switch close empties and every tick prunes
 * of copies no slot plays out.
 *
 * ABI.  0x88A5E: quat_from_euler is __stdcall(12) with ESI the out
 * quaternion; player_attack_enter reads none of EAX, ECX and EDX after it
 * (0x88A63 reloads ECX) and EDI is its PlayerControl.  0x43A62: the
 * sampler is __stdcall(8), no register input; the anim step reloads EAX,
 * ECX and EDX after it (0x43A67) and ESI is its critter.  0x8D6AF:
 * apply_damage is __stdcall(12) (the critter, its new HP, 0); the
 * handler reloads EAX and ECX after it (0x8D6B4, 0x8D6B7), never reads
 * EDX again, and ESI is its PlayerControl.  The stubs keep
 * EBX, ESI, EDI and EBP and pop the callee's arguments; the C helpers are
 * cdecl; the x87 stack is empty at the three sites; x87 only (AZ-021).
 */

#include "azurik_vanilla.h"   /* the game's calls; and azurik.h: AZURIK_BYTES_PARAM */

#define CR_WORLD     0x154   /* critter -> its world                      */
#define CR_CELL      0x158   /* critter -> its cell (0 unplaced)          */
#define CR_BIND      0x170   /* critter: its bind interface               */
#define CR_ANIM      0x17C   /* critter -> its anim                       */
#define CR_HP        0x210   /* critter: its HP (i32)                     */
#define CR_OWN_FX    0x230   /* critter: its fx_default's handle          */
#define WD_PLAYER    0x0BC   /* world -> the player critter               */
#define WD_CELLS     0x0D4   /* world -> its cells (+0x28 the first)      */
#define CELL_SIZE    0xB4
#define NO_CELL      0xFFFF
#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define PC_ATTACK    0x134   /* PlayerControl: the attacks_anims column   */
#define AN_CLOCK     0x004   /* anim -> its clock (+0x10: now, f64)       */
#define AN_LIVE      0x010   /* anim: the layer the last clip change took */
#define AN_FADE      0x014   /* anim: that change's crossfade, s          */
#define AN_LAYERS    0x040   /* anim: three 0x40-byte layers              */
#define LAYERS       3
#define LY_CLIP      0x004   /* layer: its clip                           */
#define LY_TIME      0x018   /* layer: its time, clip s                   */
#define LY_RATE      0x020   /* layer: its rate                           */
#define HANDLE_AT    0x020   /* instance: its handle list (a handle's head points here) */
#define IN_RECORDS   0x024   /* instance -> its nodes                     */
#define IN_END       0x028   /* instance -> their end                     */
#define IN_FLAGS     0x02C   /* instance: bit 0 dead                      */
#define IN_STATE     0x0A0   /* instance: low 16 bits, 2 loaded           */
#define ND_ATTRS     0x008   /* node -> its attributes (f32)              */
#define ND_DIRTY     0x010   /* node: its dirty bits                      */
#define ND_TYPE      0x014   /* node -> its type (+0xC its attribute count) */
#define ND_LINKS     0x00C   /* node -> its first link (the records pass 0x663B0 walks them) */
#define ND_OBJECT    0x020   /* node -> its world object (a platform's: the sync 0x6AE45) */
#define LK_NEXT      0x000   /* link -> the next                          */
#define LK_PLUG      0x006   /* link: its target attribute (u16)          */
#define LK_TARGET    0x008   /* link -> its target node                   */
#define LK_FACTOR    0x014   /* link: its factor, the last multiply (0x6646E) */
#define PF_LEVEL     0x27E   /* platform object: its damage level (byte) a touch tests (0x7A189) */
#define LINK_CAP     64      /* the most links walked from one node       */
#define LOADED       2
#define EMIT_RATE    5
#define TRANSLATE_Z  3       /* a transform's translateZ: a switch's level */
#define DAMAGE       17      /* a platform's damage: (int) of it is its level */
#define DEAD         1u

#define COLUMNS      24
#define ROWS         48      /* the columns, then X10's ring entries      */
#define KEYS         5       /* the own graph's, a stand's, three bound   */
#define CLIPS        16
#define SLOTS        20      /* the own and stand keys' 16, the bound keys' */
#define WINDOWS      16      /* the most windows a clip has in one key    */
#define OPS          96
#define WINS         64
#define KEY_SIZE     64
#define TABLE_SIZE   2612
#define NONE         0xFF

#define MODE_P       1
#define MODE_STAND   2
#define MODE_BOUND   3
#define SPAWN        0       /* an op's list: on a copy once loaded       */
#define DELAY        1       /* 0 there, its value once the crossfade is over */
#define ARM          2       /* at the arm                                */
#define OWN          3       /* on the own instance, by value, every tick */
#define HOLD         4       /* a STAND copy's, value x its level once detached */
#define DETACH       5       /* on a copy at its detach                   */
#define SHOW         6       /* a BOUND copy's, value x its level, every tick */

#define WIN_RIG      1       /* closes 0.33 s after the detach at the latest */
#define WIN_SWITCH   2       /* closes by its switch's translateZ at its end */
#define HELD         16      /* X37's held list                           */

#define RIG_CLOSE    0.33    /* s after the detach a rig window closes    */
#define RAMP_S       (10.0 / 30.0)
#define TICK_S       (1.0 / 30.0)
#define REWIND       0.05f   /* clip s a layer's time goes back: a restart */
#define RISE_S       0.8     /* s a STAND copy's level takes to reach 1   */
#define STAND_FALL_S 1.2     /* s it takes to fall to 0; births then stop and the pool lifts off its foot */
#define STAND_GAP    1.5     /* s from a standing copy's let-go before a chained one stands (AZ-664, AZ-671) */

typedef struct Op {
    unsigned short record;
    unsigned char attr;
    unsigned char list;
    float value;
} Op;

typedef struct Win {
    unsigned short record;   /* the emitter, whose rate fades             */
    unsigned short target;   /* the record its close writes: itself, or its system (not written) */
    unsigned char attr;      /* the attribute it writes 0 (no link writes it) */
    unsigned char flags;     /* WIN_RIG, WIN_SWITCH                       */
    unsigned short swtch;    /* WIN_SWITCH: the switch whose translateZ its end writes 0 */
    float off;               /* clip s its window ends                    */
} Win;

typedef struct KeySpec {
    unsigned char mode;      /* 0 E, MODE_P, MODE_STAND                   */
    unsigned char slots;     /* its share of the ring                     */
    unsigned char delay;     /* its DELAY ops wait out the crossfade      */
    unsigned char first;     /* its first slot                            */
    unsigned short records;  /* its graph's record count: the write guard */
    unsigned short first_op, n_ops;
    unsigned short hold_ms;  /* a STAND key's: ms its HOLD writes stay at their value; a BOUND key's: its fade */
} KeySpec;

typedef struct ClipSpec {
    unsigned short first, n; /* its windows (a STAND key's: no windows, first the ms its carrier leaves; a
                              * BOUND key's: none, first 1 where the clip plays it) */
    float tail;              /* s its copy lives once they are closed     */
} ClipSpec;

typedef struct Table {
    unsigned char n_keys, n_clips;
    unsigned short n_ops, n_wins, pad;
    unsigned char row_clip[ROWS];
    KeySpec key[KEYS];
    ClipSpec clip[CLIPS][KEYS];
    char name[KEYS][KEY_SIZE];
    Op op[OPS];
    Win win[WINS];
} Table;

_Static_assert(sizeof(Op) == 8 && sizeof(Win) == 12 && sizeof(KeySpec) == 12 && sizeof(ClipSpec) == 8,
               "_player_fx_ring.py packs these sizes");
_Static_assert(sizeof(Table) == TABLE_SIZE, "_player_fx_ring.py packs the table at this size");

typedef struct Slot {
    char *head, *next;       /* the engine's handle: 12 bytes, flags 0    */
    unsigned flags;
    unsigned char used, key, bound, armed;
    unsigned char loaded, dying, clip, aimed;   /* aimed: its drain held a target since its arm (D567) */
    int layer;               /* the layer it was armed on, and its clip   */
    const char *layer_clip;
    float rate, age_det;     /* the layer's rate; its clip s at the detach */
    double t_spawn, t_arm, t_det, delay_until;
    double aim_seen;         /* X37's seen stamp at its arm               */
    float r0[WINDOWS];       /* each window's rate at the detach          */
} Slot;

typedef struct Ring {
    char *critter;
    unsigned runs, guarded, spawns, detaches;   /* read by the sitting    */
    int live;
    const char *live_clip;
    float live_time;
    int dead;
    int cut;                 /* a drain copy was cut in the live clip: the own emitters off (D567) */
    Slot slot[SLOTS];
    double own_until;        /* the own instance's shown emitters off until */
} Ring;

/* X37's state (drain.c's struct drain_state, the layout both assert):
 * the drain window's target and its held list, each a detached drain
 * copy's instance and the target its mode-7 nodes stay on, each target
 * with the identity X37 checks (AZ-682); X37 reads them, this copies the
 * target into a held entry and reads the window's target and seen stamp
 * (D567). */
typedef struct Kept {
    char *critter;
    const void *vtable;
    unsigned serial;
} Kept;

typedef struct Held {
    char *instance;
    Kept target;
} Held;

typedef struct DrainState {
    char *best;
    Kept target;
    int active, passes;
    double seen;
    char *passed[8];
    Held held[HELD];
    double hold[8];
} DrainState;

_Static_assert(sizeof(Held) == 16 && sizeof(DrainState) == 384, "drain.c's struct drain_state");

volatile const Table player_model_fx_ring_table __attribute__((used, section(".rdata"))) = {0};
AZURIK_BYTES_PARAM(player_model_fx_ring_at, 4);
AZURIK_BYTES_PARAM(player_model_fx_rotation_at, 4);
AZURIK_BYTES_PARAM(player_model_fx_ring_drain_at, 4);

Ring player_model_fx_ring_state;

#define T player_model_fx_ring_table
#define AT(p, off, type) (*(type *)((char *)(p) + (off)))

static Ring *state(void)
{
    unsigned at = *(const volatile unsigned *)player_model_fx_ring_at;

    return at ? (Ring *)at : &player_model_fx_ring_state;
}

static double clock_now(const char *anim)
{
    return *(const double *)(*(const char *const *)(anim + AN_CLOCK) + 0x10);
}

static char *instance(const Slot *s)
{
    return s->head - HANDLE_AT;
}

/* The instance is loaded with key k's graph. */
static int ready(char *inst, int k)
{
    char **records = AT(inst, IN_RECORDS, char **);

    return (AT(inst, IN_STATE, unsigned) & 0xFFFF) == LOADED
        && (unsigned)(AT(inst, IN_END, char **) - records) == T.key[k].records;
}

static unsigned *attr_at(char *inst, unsigned record, unsigned attr)
{
    char **records = AT(inst, IN_RECORDS, char **);
    char *node;

    if (record >= (unsigned)(AT(inst, IN_END, char **) - records))
        return 0;
    node = records[record];
    if (!node || attr >= AT(AT(node, ND_TYPE, char *), 0xC, unsigned))
        return 0;
    return AT(node, ND_ATTRS, unsigned *) + attr;
}

/* record.attr := value, marked dirty, when it differs. */
static void put(char *inst, unsigned record, unsigned attr, float value)
{
    unsigned *a = attr_at(inst, record, attr);
    union { float f; unsigned u; } v;
    char **records;

    v.f = value;
    if (!a || *a == v.u)
        return;
    *a = v.u;
    records = AT(inst, IN_RECORDS, char **);
    AT(records[record], ND_DIRTY, unsigned) |= attr < 30 ? 1u << attr : 0x80000000u;
}

static float get(char *inst, unsigned record, unsigned attr)
{
    unsigned *a = attr_at(inst, record, attr);

    return a ? *(float *)a : 0.0f;
}

/* Key k's ops of `list` written on inst; DELAY ops write 0 unless `restore`. */
static void write_ops(char *inst, int k, int list, int restore)
{
    unsigned i, end = T.key[k].first_op + T.key[k].n_ops;

    for (i = T.key[k].first_op; i < end && i < OPS; i++)
        if (T.op[i].list == list)
            put(inst, T.op[i].record, T.op[i].attr, list == DELAY && !restore ? 0.0f : T.op[i].value);
}

static DrainState *drain(void)
{
    return (DrainState *)*(const volatile unsigned *)player_model_fx_ring_drain_at;
}

/* inst leaves X37's held list. */
static void release(const char *inst)
{
    DrainState *d = drain();
    unsigned i;

    for (i = 0; d && i < HELD; i++)
        if (d->held[i].instance == inst) {
            d->held[i].instance = 0;
            d->held[i].target.critter = 0;
        }
}

/* inst is held with no target: X37 dropped it as dead or deleted (AZ-684). */
static int orphaned(const char *inst)
{
    DrainState *d = drain();
    unsigned i;

    for (i = 0; d && i < HELD; i++)
        if (d->held[i].instance == inst)
            return !d->held[i].target.critter;
    return 0;
}

/* Held entries whose copy no slot keeps playing out (dead, wrapped, a new
 * critter's ring, deleted by the engine) leave the list. */
static void prune(const Ring *r)
{
    DrainState *d = drain();
    unsigned i, j;

    for (i = 0; d && i < HELD; i++) {
        int live = 0;
        if (!d->held[i].instance)
            continue;
        for (j = 0; j < SLOTS && !live; j++)
            live = r->slot[j].head && !r->slot[j].dying && instance(&r->slot[j]) == d->held[i].instance;
        if (!live) {
            d->held[i].instance = 0;
            d->held[i].target.critter = 0;
        }
    }
}

/* s's clip is a drain row: a window of it closes by its switch. */
static int drain_row(const Slot *s)
{
    unsigned j;

    if (s->clip >= T.n_clips)
        return 0;
    for (j = 0; j < T.clip[s->clip][s->key].n; j++)
        if (T.win[T.clip[s->clip][s->key].first + j].flags & WIN_SWITCH)
            return 1;
    return 0;
}

/* At a drain row's detach: the copy's mode-7 nodes stay on X37's target; with
 * none (no pick, or dropped: dead or deleted) it is listed without one,
 * so the next tick closes it (AZ-684). */
static void hold(char *inst, const Slot *s)
{
    DrainState *d = drain();
    unsigned i;

    if (!d || !drain_row(s))
        return;
    release(inst);
    for (i = 0; i < HELD; i++)
        if (!d->held[i].instance) {
            d->held[i].target.critter = d->target.critter;   /* with X37's identity of it */
            d->held[i].target.vtable = d->target.vtable;
            d->held[i].target.serial = d->target.serial;
            d->held[i].instance = inst;
            return;
        }
}

/* A window of the copy's clip closes through record.attr. */
static int is_window(const Slot *s, unsigned record, unsigned attr)
{
    unsigned j;

    if (s->clip >= T.n_clips)
        return 0;
    for (j = 0; j < T.clip[s->clip][s->key].n; j++)
        if (T.win[T.clip[s->clip][s->key].first + j].target == record
            && T.win[T.clip[s->clip][s->key].first + j].attr == attr)
            return 1;
    return 0;
}

/* AZ-652: an E copy armed on one clip has the key's other clips' windows
 * closed (their close attribute 0, which no link writes), so a spawn in
 * another clip's crossfade draws none of that clip's emitters while its
 * switches fade (the outgoing copy, detached, plays them).  A close
 * through a system is skipped: it may feed this clip's windows, and its
 * enable would blank its particles; but a SWITCH window's (a drain row's
 * stream, whose pool only it feeds: AZ-653) is closed.  A P key's other
 * clips carry the ambient look the copy shows at rest. */
static void others_off(char *inst, const Slot *s)
{
    unsigned c, j;

    if (T.key[s->key].mode != 0 || s->clip >= T.n_clips)
        return;
    for (c = 0; c < T.n_clips && c < CLIPS; c++)
        for (j = 0; c != s->clip && j < T.clip[c][s->key].n; j++) {
            const volatile Win *w = &T.win[T.clip[c][s->key].first + j];
            if ((w->target == w->record || (w->flags & WIN_SWITCH)) && !is_window(s, w->target, w->attr))
                put(inst, w->target, w->attr, 0.0f);
        }
}

/* AZ-683: a copy armed on a clip that is no drain row takes nothing from
 * the links into a drain box's damage (a DETACH op's record), so one armed
 * in the drain's crossfade keeps SPAWN's 0 while the bound switch fades. */
static void unlinked(char *inst, const Slot *s)
{
    char **records = AT(inst, IN_RECORDS, char **);
    unsigned n = (unsigned)(AT(inst, IN_END, char **) - records), i, j, m, end = T.key[s->key].first_op + T.key[s->key].n_ops;

    if (drain_row(s))
        return;
    for (i = T.key[s->key].first_op; i < end && i < OPS; i++) {
        char *box = T.op[i].list == DETACH && T.op[i].record < n ? records[T.op[i].record] : 0;
        for (j = 0; box && j < n; j++) {
            char *lk = records[j] ? AT(records[j], ND_LINKS, char *) : 0;
            for (m = 0; lk && m < LINK_CAP; m++, lk = AT(lk, LK_NEXT, char *))
                if (AT(lk, LK_TARGET, char *) == box && AT(lk, LK_PLUG, unsigned short) == T.op[i].attr)
                    AT(lk, LK_FACTOR, float) = 0.0f;
        }
    }
}

/* AZ-683: SPAWN's damage 0 on the platform's world object at once (the
 * records pass syncs it a tick later); till then it holds the authored level. */
static void disarmed(char *inst, int k)
{
    char **records = AT(inst, IN_RECORDS, char **);
    unsigned i, end = T.key[k].first_op + T.key[k].n_ops;

    for (i = T.key[k].first_op; i < end && i < OPS; i++)
        if (T.op[i].list == SPAWN && T.op[i].attr == DAMAGE && attr_at(inst, T.op[i].record, DAMAGE)) {
            char *object = AT(records[T.op[i].record], ND_OBJECT, char *);
            if (object)
                AT(object, PF_LEVEL, unsigned char) = 0;
        }
}

/* What a detached copy needs when it is loaded: a P copy's other
 * emitters closed, its DETACH ops, each window's rate. */
static void detached(char *inst, Slot *s)
{
    int k = s->key;
    unsigned i, j, end = T.key[k].first_op + T.key[k].n_ops;

    if (T.key[k].mode == MODE_P)
        for (i = T.key[k].first_op; i < end && i < OPS; i++)
            if (T.op[i].list == OWN && !is_window(s, T.op[i].record, T.op[i].attr))
                put(inst, T.op[i].record, T.op[i].attr, 0.0f);
    write_ops(inst, k, DETACH, 0);
    if (s->clip < T.n_clips)
        for (j = 0; j < T.clip[s->clip][k].n && j < WINDOWS; j++)
            s->r0[j] = get(inst, T.win[T.clip[s->clip][k].first + j].record, EMIT_RATE);
}

static void load(Ring *r, Slot *s)
{
    char *inst = instance(s);

    if (!ready(inst, s->key)) {
        r->guarded++;
        return;
    }
    write_ops(inst, s->key, SPAWN, 0);
    disarmed(inst, s->key);
    write_ops(inst, s->key, DELAY, 0);
    if (s->armed) {
        write_ops(inst, s->key, ARM, 0);
        others_off(inst, s);
        unlinked(inst, s);
    }
    if (!s->bound)
        detached(inst, s);
    s->loaded = 1;
}

/* Another copy of s's key stands (let go, not ended) that was let go
 * under STAND_GAP ago (AZ-664). */
static int stands_young(const Ring *r, const Slot *s, double now)
{
    unsigned i;

    for (i = 0; i < SLOTS; i++) {
        const Slot *c = &r->slot[i];
        if (c != s && c->head && c->key == s->key && !c->bound && !c->dying && now - c->t_det < STAND_GAP)
            return 1;
    }
    return 0;
}

/* The clip changes: the own emitters a cut drain copy showed stay off for
 * its crossfade and a tick (D567). */
static void uncut(Ring *r, const char *anim, double now)
{
    if (!r->cut)
        return;
    r->cut = 0;
    if (now + AT(anim, AN_FADE, float) + TICK_S > r->own_until)
        r->own_until = now + AT(anim, AN_FADE, float) + TICK_S;
}

/* `chain`: the clip the next attack's entry plays when that entry lets it
 * go (D429); NONE for another clip change, a hit or the death.  A STAND
 * copy is chained only by a clip that carries its key (the next gust's),
 * so one a melee swing lets go stands. */
static void detach(Ring *r, Slot *s, const char *anim, double now, unsigned chain)
{
    const char *layer = anim + AN_LAYERS + 0x40 * s->layer;

    if (s->armed && s->layer >= 0 && s->layer < LAYERS && AT(layer, LY_CLIP, const char *) == s->layer_clip)
        s->age_det = AT(layer, LY_TIME, float);
    else
        s->age_det = (float)((now - s->t_arm) * s->rate);
    if (s->armed && now + AT(anim, AN_FADE, float) + TICK_S > r->own_until)
        r->own_until = now + AT(anim, AN_FADE, float) + TICK_S;   /* its markers slide home meanwhile */
    if (s->clip >= T.n_clips)
        s->delay_until = 0.0;   /* a resting copy: no window would close what the delay turns on */
    fx_instance_detach_call(instance(s));
    s->bound = 0;
    s->t_det = now;
    hold(instance(s), s);
    if (s->loaded)
        detached(instance(s), s);
    if (T.key[s->key].mode == MODE_STAND
        && (!s->loaded || s->clip >= T.n_clips || s->age_det * 1000.0f < (float)T.clip[s->clip][s->key].first
            || (chain < T.n_clips && T.clip[chain][s->key].tail > 0.0f && stands_young(r, s, now)))) {
        AT(instance(s), IN_FLAGS, unsigned) |= DEAD;   /* never posed bound, its carrier never left, or chained */
        s->dying = 1;
    }
    r->detaches++;
}

/* A new player critter: every copy still alive ends (dead; its handle
 * stays linked until the engine deletes it and zeroes it, or a spawn
 * releases it), the rest of the ring starts over. */
static void reset(Ring *r, char *critter)
{
    unsigned i, j;

    for (i = 0; i < SLOTS; i++) {
        Slot *s = &r->slot[i];
        char *head = s->head, *next = s->next, *p = (char *)s;
        if (head)
            AT(instance(s), IN_FLAGS, unsigned) |= DEAD;
        for (j = 0; j < sizeof(Slot); j++)
            p[j] = 0;
        s->head = head;
        s->next = next;
        s->used = s->dying = head != 0;
    }
    r->critter = critter;
    r->live = -1;
    r->live_clip = 0;
    r->live_time = 0.0f;
    r->dead = 0;
    r->cut = 0;
    r->own_until = 0.0;
}

/* Slots whose instance the engine deleted (it zeroed the handle). */
static void sweep(Ring *r)
{
    unsigned i, j;

    for (i = 0; i < SLOTS; i++) {
        Slot *s = &r->slot[i];
        if (s->used && !s->head) {
            char *p = (char *)s;
            for (j = 0; j < sizeof(Slot); j++)
                p[j] = 0;
        }
    }
}

/* A let-go STAND copy whose trigger is back at 0: its funnel faded, only
 * its particles' tail left (AZ-689). */
static int faded(const Slot *s, double now)
{
    return !s->bound && !s->dying && now - s->t_det >= T.key[s->key].hold_ms / 1000.0 + STAND_FALL_S;
}

/* A BOUND copy: its SHOW writes at value x its level (1 while armed, then
 * falling to 0 over its fade from its let-go), dead its tail past the fade. */
static void bound_show(Slot *s, double now)
{
    char *inst = instance(s);
    int k = s->key;
    unsigned i, end = T.key[k].first_op + T.key[k].n_ops;
    double fade = T.key[k].hold_ms / 1000.0, a = now - s->t_det, level = 1.0;
    float tail = s->clip < T.n_clips ? T.clip[s->clip][k].tail : 0.0f;

    if (!s->armed)
        level = a < fade ? 1.0 - a / fade : 0.0;
    for (i = T.key[k].first_op; i < end && i < OPS; i++)
        if (T.op[i].list == SHOW)
            put(inst, T.op[i].record, T.op[i].attr, (float)(T.op[i].value * level));
    if (!s->armed && a >= fade + tail) {
        AT(inst, IN_FLAGS, unsigned) |= DEAD;
        s->dying = 1;
    }
}

static Slot *spawn(Ring *r, char *critter, const char *anim, int k, double now)
{
    char *world = AT(critter, CR_WORLD, char *), *cell = AT(critter, CR_CELL, char *);
    unsigned at = NO_CELL, i, n = T.key[k].slots;
    Slot *s = 0, *f = 0;

    for (i = T.key[k].first; i < T.key[k].first + n && i < SLOTS; i++) {
        Slot *c = &r->slot[i];
        if (!c->head) {
            s = c;
            break;
        }
        if (!c->bound && (T.key[k].mode != MODE_STAND || c->dying) && (!s || c->t_spawn < s->t_spawn))
            s = c;   /* the oldest; a STAND key's only once it has ended (AZ-661) */
        if (T.key[k].mode == MODE_STAND && faded(c, now) && (!f || c->t_det < f->t_det))
            f = c;   /* else the oldest whose funnel has faded (AZ-689) */
    }
    if (!s)
        s = f;
    if (!s || !world)
        return 0;
    if (s->head)
        AT(instance(s), IN_FLAGS, unsigned) |= DEAD;   /* the oldest copy ends: the wrap */
    if (cell)
        at = (unsigned)((cell - AT(AT(world, WD_CELLS, char *), 0x28, char *)) / CELL_SIZE);
    s->flags = 0;
    fx_instantiate(&s->head, (const char *)T.name[k], world, at, 0, critter + CR_BIND, 0, 0, 0);
    s->used = s->head != 0;
    if (!s->head)
        return 0;
    s->key = (unsigned char)k;
    s->bound = 1;
    s->armed = s->loaded = s->dying = 0;
    s->clip = NONE;
    s->layer = -1;
    s->t_spawn = now;
    s->delay_until = T.key[k].delay ? now + AT(anim, AN_FADE, float) + TICK_S : 0.0;
    r->spawns++;
    load(r, s);
    return s;
}

static void arm(Slot *s, const char *anim, unsigned clip, double now)
{
    int live = AT(anim, AN_LIVE, int);
    const char *layer = anim + AN_LAYERS + 0x40 * live;
    DrainState *d = drain();

    s->aimed = 0;
    s->aim_seen = d ? d->seen : 0.0;
    s->armed = 1;
    s->clip = (unsigned char)clip;
    s->t_arm = now;
    s->layer = live;
    s->layer_clip = live >= 0 && live < LAYERS ? AT(layer, LY_CLIP, const char *) : 0;
    s->rate = live >= 0 && live < LAYERS ? AT(layer, LY_RATE, float) : 1.0f;
    if (s->loaded && ready(instance(s), s->key)) {
        write_ops(instance(s), s->key, ARM, 0);
        others_off(instance(s), s);
        unlinked(instance(s), s);
        if (T.key[s->key].mode == MODE_BOUND)
            bound_show(s, now);
    }
}

/* Note the live layer; nonzero when it isn't the one noted last. */
static int changed(Ring *r, const char *anim)
{
    int live = AT(anim, AN_LIVE, int), was;
    const char *layer, *clip;
    float t;

    if (live < 0 || live >= LAYERS)
        return 0;
    layer = anim + AN_LAYERS + 0x40 * live;
    clip = AT(layer, LY_CLIP, const char *);
    t = AT(layer, LY_TIME, float);
    was = live != r->live || clip != r->live_clip || t < r->live_time - REWIND;
    r->live = live;
    r->live_clip = clip;
    r->live_time = t;
    return was;
}

static void detach_all(Ring *r, const char *anim, double now, int armed_only, unsigned chain)
{
    unsigned i;

    uncut(r, anim, now);
    for (i = 0; i < SLOTS; i++) {
        Slot *s = &r->slot[i];
        if (!s->head || !s->bound || s->dying || !(s->armed || !armed_only))
            continue;
        if (T.key[s->key].mode != MODE_BOUND) {
            detach(r, s, anim, now, chain);
        } else if (s->armed) {   /* let go on the body: its fade */
            s->armed = 0;
            s->t_det = now;
        }
    }
}

/* The own instance's emitters a copy shows: 0 while a bound armed copy
 * shows them and until own_until (a P key's always), else as authored. */
static void own_mute(const Ring *r, const char *critter, double now)
{
    char *handle = AT(critter, CR_OWN_FX, char *), *inst;
    unsigned i, end = T.key[0].first_op + T.key[0].n_ops;
    int shown = T.key[0].mode == MODE_P || now < r->own_until || r->cut;

    if (!handle || T.key[0].mode == MODE_BOUND)   /* no own key: the table's are effects rows' */
        return;
    inst = handle - HANDLE_AT;
    if (!ready(inst, 0))
        return;
    for (i = 0; i < SLOTS && !shown; i++)
        shown = r->slot[i].head && r->slot[i].key == 0 && r->slot[i].bound && r->slot[i].armed;
    for (i = T.key[0].first_op; i < end && i < OPS; i++)
        if (T.op[i].list == OWN)
            put(inst, T.op[i].record, T.op[i].attr, shown ? 0.0f : T.op[i].value);
}

static float key_tail(int k)
{
    unsigned c;
    float tail = 0.0f;

    for (c = 0; c < T.n_clips; c++)
        if (T.clip[c][k].tail > tail)
            tail = T.clip[c][k].tail;
    return tail;
}

/* A detached STAND copy: its HOLD writes at value x its level, then its end. */
static void stand(Slot *s, double now)
{
    char *inst = instance(s);
    int k = s->key;
    unsigned i, end = T.key[k].first_op + T.key[k].n_ops;
    double a = now - s->t_det, hold = T.key[k].hold_ms / 1000.0, u = a < RISE_S ? 1.0 - a / RISE_S : 0.0;
    double z = 1.0 - u * u, fall = 1.0 - (a - hold) / STAND_FALL_S;
    float tail = s->clip < T.n_clips ? T.clip[s->clip][k].tail : key_tail(k);

    if (fall < z)
        z = fall;
    if (z < 0.0)
        z = 0.0;
    for (i = T.key[k].first_op; i < end && i < OPS; i++)
        if (T.op[i].list == HOLD)
            put(inst, T.op[i].record, T.op[i].attr, (float)(T.op[i].value * z));
    if (a >= hold + STAND_FALL_S + tail) {
        AT(inst, IN_FLAGS, unsigned) |= DEAD;
        s->dying = 1;
    }
}

/* A detached copy: its windows' fades and closes, then its end. */
static void play_out(Slot *s, double now)
{
    char *inst = instance(s);
    int k = s->key;
    double last = s->t_det, rate = s->rate > 0.0f ? s->rate : 1.0f;
    float tail = key_tail(k);
    int open = 0;
    unsigned j;

    if (T.key[k].mode == MODE_STAND) {
        stand(s, now);
        return;
    }
    if (s->clip < T.n_clips) {
        const volatile ClipSpec *cs = &T.clip[s->clip][k];
        tail = cs->tail;
        for (j = 0; j < cs->n && j < WINDOWS; j++) {
            const volatile Win *w = &T.win[cs->first + j];
            double close_at = w->off, t_close, level;
            if ((w->flags & WIN_RIG) && s->age_det + RIG_CLOSE * rate < close_at)
                close_at = s->age_det + RIG_CLOSE * rate;
            t_close = s->t_det + (close_at > s->age_det ? (close_at - s->age_det) / rate : 0.0);
            if (w->flags & WIN_SWITCH) {   /* at its end, or its target gone, the switch; then off the target */
                if (t_close > last)
                    last = t_close;
                if (now < t_close && !orphaned(inst)) {
                    open = 1;
                    continue;
                }
                put(inst, w->swtch, TRANSLATE_Z, 0.0f);
                release(inst);
                continue;
            }
            if (t_close + RAMP_S > last)
                last = t_close + RAMP_S;
            if (now < t_close) {
                open = 1;
                continue;
            }
            level = 1.0 - (now - t_close) / RAMP_S;
            if (level > 0.0) {
                put(inst, w->record, EMIT_RATE, (float)(s->r0[j] * level));
                open = 1;
            } else {
                put(inst, w->record, EMIT_RATE, 0.0f);
                if (w->target == w->record)   /* a system's enable would blank its particles */
                    put(inst, w->target, w->attr, 0.0f);
            }
        }
    }
    if (!open && now - last >= tail) {
        AT(inst, IN_FLAGS, unsigned) |= DEAD;
        s->dying = 1;
    }
}

/* D567: a bound drain row's copy whose drain held a target since its arm
 * and holds none now (X37 dropped it, dead or deleted, and found no other
 * in reach) is let go: held with no target, play_out closes its switch at
 * once (AZ-684); the own emitters it showed stay off until the clip
 * changes (uncut). */
static void aim(Ring *r, Slot *s, const char *anim, double now)
{
    DrainState *d = drain();

    if (!d || !s->armed || !drain_row(s))
        return;
    if (d->target.critter) {
        if (d->seen != s->aim_seen)   /* X37 evaluated this drain and holds one */
            s->aimed = 1;
    } else if (s->aimed) {
        detach(r, s, anim, now, NONE);
        r->cut = 1;
    }
}

/* The clip of the row the PlayerControl's attack entry plays: its
 * attacks_anims column's, or X10's entry it just played; NONE. */
static unsigned entered_clip(const char *pc)
{
    unsigned ring = *(const volatile unsigned *)player_model_fx_rotation_at;
    const volatile unsigned *rot = (const volatile unsigned *)ring;
    int column = AT(pc, PC_ATTACK, int), row = column;

    if (column < 0 || column >= COLUMNS)
        return NONE;
    if (rot && (int)rot[0] > 0 && ((rot[2] >> column) & 1))   /* X10: the entry it just played */
        row = COLUMNS + (int)(((int)rot[1] - 1 + (int)rot[0]) % (int)rot[0]);
    return row < ROWS ? T.row_clip[row] : NONE;
}

__attribute__((used))
void fx_ring_spawn(char *pc)
{
    Ring *r;
    char *critter = AT(pc, PC_CRITTER, char *), *anim;
    int k;
    unsigned clip;
    double now;

    if (!critter || !T.n_keys || !(anim = AT(critter, CR_ANIM, char *)))
        return;
    r = state();
    if (critter != r->critter)
        reset(r, critter);
    now = clock_now(anim);
    sweep(r);
    clip = entered_clip(pc);
    detach_all(r, anim, now, 1, clip);   /* "when the next attack is used" (D429) */
    changed(r, anim);              /* this change is the attack's own: the tick sees none */
    if (r->dead || AT(critter, CR_HP, int) <= 0)
        return;
    if (clip >= T.n_clips)
        return;
    for (k = 0; k < T.n_keys && k < KEYS; k++) {
        Slot *s = 0;
        unsigned i;
        if (T.key[k].mode == MODE_BOUND ? !T.clip[clip][k].first
            : !T.clip[clip][k].n && !(T.key[k].mode == MODE_STAND && T.clip[clip][k].tail > 0.0f))
            continue;   /* a STAND key: the clips that carry it; a BOUND key: those that play it */
        if (T.key[k].mode == MODE_P || T.key[k].mode == MODE_BOUND)   /* the resting copy; a live BOUND one */
            for (i = T.key[k].first; i < T.key[k].first + T.key[k].slots && i < SLOTS; i++)
                if (r->slot[i].head && r->slot[i].bound && !r->slot[i].dying
                    && (!r->slot[i].armed || T.key[k].mode == MODE_BOUND))
                    s = &r->slot[i];
        if (!s)
            s = spawn(r, critter, anim, k, now);
        if (s)
            arm(s, anim, clip, now);
    }
}

__attribute__((used))
void fx_ring_tick(char *critter)
{
    Ring *r;
    char *world = AT(critter, CR_WORLD, char *), *anim;
    unsigned i;
    int k;
    double now;

    if (!T.n_keys || !world || AT(world, WD_PLAYER, char *) != critter || !(anim = AT(critter, CR_ANIM, char *)))
        return;
    r = state();
    r->runs++;
    if (critter != r->critter)
        reset(r, critter);
    now = clock_now(anim);
    sweep(r);
    prune(r);
    own_mute(r, critter, now);
    if (AT(critter, CR_HP, int) <= 0) {
        if (!r->dead)
            detach_all(r, anim, now, 0, NONE);
        r->dead = 1;
    } else {
        r->dead = 0;
    }
    if (changed(r, anim))
        detach_all(r, anim, now, 1, NONE);
    if (!r->dead && AT(critter, CR_CELL, char *))
        for (k = 0; k < T.n_keys && k < KEYS; k++) {
            int held = 0;
            if (T.key[k].mode != MODE_P)
                continue;
            for (i = T.key[k].first; i < T.key[k].first + T.key[k].slots && i < SLOTS; i++)
                held |= r->slot[i].head && r->slot[i].bound && !r->slot[i].dying;
            if (!held)
                spawn(r, critter, anim, k, now);
        }
    for (i = 0; i < SLOTS; i++) {
        Slot *s = &r->slot[i];
        if (!s->head || s->dying)
            continue;
        if (!ready(instance(s), s->key)) {
            r->guarded++;
            continue;
        }
        if (!s->loaded)
            load(r, s);
        if (s->delay_until > 0.0 && now >= s->delay_until) {
            write_ops(instance(s), s->key, DELAY, 1);
            s->delay_until = 0.0;
        }
        if (T.key[s->key].mode == MODE_BOUND) {
            bound_show(s, now);
            continue;
        }
        if (s->bound)
            aim(r, s, anim, now);
        if (!s->bound)
            play_out(s, now);
    }
}

/* AZ-650: the hit's clip change (X7's, at 0x8D682) noted before any
 * re-sample moves the bound copies to the reaction's pose: the armed
 * copies detached where the attack left them.  The tick's next change
 * check sees none; its death rule and resting spawn follow there. */
__attribute__((used))
void fx_ring_hit(char *critter)
{
    char *world, *anim;
    Ring *r;

    if (!critter || !T.n_keys || !(world = AT(critter, CR_WORLD, char *)) || AT(world, WD_PLAYER, char *) != critter
        || !(anim = AT(critter, CR_ANIM, char *)))
        return;
    r = state();
    if (critter == r->critter && changed(r, anim))   /* a new critter: the tick resets the ring */
        detach_all(r, anim, clock_now(anim), 1, NONE);
}

/* 0x88A5E: CALL quat_from_euler (ESI the out, three floats), then the spawn. */
__attribute__((naked))
void c_player_model_fx_ring_spawn(void)
{
    __asm__ volatile (
        "pushl 0xc(%%esp)                    \n\t"
        "pushl 0xc(%%esp)                    \n\t"
        "pushl 0xc(%%esp)                    \n\t"
        "calll \"_quat_from_euler@12\"       \n\t"   /* pops the copies */
        "pushl %%edi                         \n\t"   /* the PlayerControl */
        "calll _fx_ring_spawn                \n\t"
        "addl $4, %%esp                      \n\t"
        "retl $12                            \n\t"
        : : : "memory"
    );
}

/* 0x43A62: CALL anim_sample_markers (the anim, the flags), then the tick. */
__attribute__((naked))
void c_player_model_fx_ring_tick(void)
{
    __asm__ volatile (
        "pushl 0x8(%%esp)                    \n\t"
        "pushl 0x8(%%esp)                    \n\t"
        "calll \"_anim_sample_markers@8\"    \n\t"   /* pops the copies */
        "pushl %%esi                         \n\t"   /* the critter */
        "calll _fx_ring_tick                 \n\t"
        "addl $4, %%esp                      \n\t"
        "retl $8                             \n\t"
        : : : "memory"
    );
}

/* 0x8D6AF: CALL apply_damage (the critter, its new HP, 0), then the hit. */
__attribute__((naked))
void c_player_model_fx_ring_hit(void)
{
    __asm__ volatile (
        "pushl 0xc(%%esp)                    \n\t"
        "pushl 0xc(%%esp)                    \n\t"
        "pushl 0xc(%%esp)                    \n\t"
        "calll \"_apply_damage@12\"          \n\t"   /* pops the copies */
        "pushl 0x20(%%esi)                   \n\t"   /* the PlayerControl's critter */
        "calll _fx_ring_hit                  \n\t"
        "addl $4, %%esp                      \n\t"
        "retl $12                            \n\t"
        : : : "memory"
    );
}
