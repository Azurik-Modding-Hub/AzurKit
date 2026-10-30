/* X37: Balthazar's drain beam, worn, drains the enemy it lands on, never
 * its wearer, and heals the wearer what it deals (Step 2.135; D324, the
 * owner: "Beam drains enemies": the beam of his attack_2 comes back when
 * the player wears him and its damage hits the enemies it touches, never
 * the wearer; D357: "Heals you a little"; Step 2.153, D452: "let's make it
 * heal 100%. also the drain life attack should heal per enemy hit, and
 * give it a bigger and wider range so that it does not miss much").
 *
 * Why.  His attack_2 keys m_lifedrainswitch, which turns on his default
 * fx's pEmitterShape1 and its damageBox platform (norm level 2, 15 HP).
 * Both hang under 'onPlayer', inherit mode 7, which transform_world
 * (0x681E0's case at 0x68A43) places at [[[node+4]+0x44]+0xC0], the
 * player critter (the load at 0x68A49): NPC Balthazar's drain lands on
 * the player and the stream is pulled into his hand.  On a player wearing
 * him that is himself, so the box hit its wearer (AZ-453) and W17 played a
 * copy of attack_2 without the switch, losing the beam.  The box's hit is
 * a platform touch: the touching critter's own volume query (the player's
 * at 0x85587, an AI's at 0x379AC, both with touch 1) sends the platform a
 * touch, and its slot 0x79F80 sends the toucher a type-3 hit through the
 * toucher's vtable +0xB4 at 0x7A1CB, whose slot (0x43210 on a critter)
 * takes the HP at once.  Only Balthazar's two fx graphs hold mode-7 nodes
 * (the airship's and the spider's fx_default: Step 2.135's scan), and so
 * the player's clone of one (X40) and X38's copies of it; the airship
 * boss's own and every platform of another graph stay the game's (Step
 * 2.161c, the review's P1: inside the player's drain the boss's box went
 * on its target, himself, 0.0-0.23 m from him, where the game puts it on
 * the player, and the touch hook took every norm platform's touches).
 *
 * What.  One object, three entries landed once per hook, the finder's
 * landing first and owning the state (the others' bytes param
 * player_model_drain_state_at holds its address):
 *
 *   c_player_model_drain_find, inside attack_target_find (0x7EBB0) at its
 *   `mov edx, [esi+0x168]` (0x7EE3B, Europe 0x7EDEB), where it records a
 *   better candidate (ESI): the state's best := ESI, then the mov.  The
 *   finder's result holds no critter pointer, so the pick reads it here.
 *
 *   c_player_model_drain_anchor, at mode 7's load 0x68A49 (Europe
 *   0x689F9): ESI := [EAX+0xC0] (the game's player critter), which a node
 *   of an instance not the player's keeps (its graph's asset,
 *   instance+0x4C, not that of his own fx_default's instance, critter+0x230's
 *   handle less 0x20; X38's copies share his asset); a node of
 *   an instance (EDX, [node+4], loaded at 0x68A43) in the held list goes
 *   on its target while that lives, else on the player (AZ-653, Step
 *   2.153c: X38's detached drain copy, listed at its detach with this
 *   state's target, plays its stream out there); and while the
 *   player's drain plays (a column of float param
 *   player_model_drain_columns in PC+0x134, its slot playing: critter+0x200
 *   == 0x52 + it, a root-motion attack: PC+0x16C & 8) ESI := its target:
 *   on the window's first evaluation attack_target_find(player, the
 *   swing's yaw PC+0x138) with X21's radius (bytes param
 *   player_model_drain_radius_at) at float param player_model_drain_range
 *   (16 m) for the call, at any bearing (the finder prefers the one
 *   nearest the yaw); while the window holds no live target (none found,
 *   or its HP, +0x210, is 0) each evaluation picks again, the player the
 *   anchor meanwhile.  Each evaluation in the window stamps seen := now;
 *   one 0.5 s or more after the last (or before it) opens a new window,
 *   so a new beam picks its own target even if no evaluation ran between
 *   the two, and clears the window's passed list (below), which a re-pick
 *   keeps.  Once the drain stops the target is kept for TAIL past the
 *   window's last evaluation while it lives (AZ-653: the own box and
 *   stream fade there, and a copy spawned then, X38's next swing's, sits
 *   there, its two ticks of the box's damage meeting the target's no-hit
 *   window [inferred]); then the player.
 *
 *   "Lives" is the identity kept with the critter (AZ-682, Step 2.153d):
 *   each critter kept across ticks (the window's target, each held
 *   entry's) is kept with its vtable and its serial and, before its HP is
 *   read or it is returned, dropped as gone when either differs or its HP
 *   is 0 or less.  The game's delete (0x40930 -> 0x40FA0 -> 0x60F80, then
 *   the heap free at 0x4094C) writes the base vtable 0x19DF08 at 0x60F94
 *   before it clears +0xE4 (0x60FA5: what glide_origin reads at 0x42137
 *   for the anchor) and leaves the HP; a block the heap gives again holds
 *   a new serial (+0xE0's low 24 bits, the counter 0x1BF588 the world
 *   object's constructor 0x60E40 takes at 0x60EC1; the delete never
 *   writes it, the top byte is a tag the game sets later).  A held entry
 *   whose target is gone keeps its instance with no target, so its nodes
 *   go on the player until X38 closes the copy (AZ-684).
 *
 *   An instance neither the player's nor held whose graph is the drain
 *   stream's (19 records, [6] inherit 7: AZ-759's, below; the boss's two
 *   mode-7 graphs hold more) also gets its pull [12] and box sink [14]
 *   translateZ := float param player_model_drain_chest plus how far a
 *   clip lifts the player (his lowest posed bone, anim object +8, 0xB0
 *   bytes each, z at +0xA8, over float param player_model_drain_feet,
 *   his bind pose's lowest, times player_model_drain_drawn), each with
 *   its dirty bit (1 << 3): the records pass (0x663B0) runs records in
 *   order, so [6]'s update, whose transform_world makes this call, comes
 *   first and theirs rebuild their local matrices this pass (0x68120's
 *   0x3FE test).  So the stream ends at his drawn chest while a clip
 *   lifts him (AZ-764, Step 2.196's skeptic F2: Balthazar's basic3 and
 *   finish3 raise his feet 2.0 m, beamlord's jump attack 1.6 m, and mode
 *   7 follows his critter frame, glide_origin, alone).  Since Step 2.202
 *   the box sink spans his standing chest to the lifted one instead:
 *   translateZ := the chest plus half the lift, scaleZ (1 << 9) := float
 *   param player_model_drain_sink (its standing height) plus the lift's
 *   size, so a particle still flying at the chest the pull left dies in
 *   it rather than passing under the lifted box and being flung 12-17 m
 *   by the pull's 1/d field (beamlord's jump attack on main); since Step
 *   2.202b the lift it spans is the largest within the particles' 1.3 s
 *   life (by the player's clock), so the box keeps a lift's span after
 *   the lift ends (a stream from 10 m flung 11-13 m off its line there).
 *
 *   The beam's aim (AZ-769, Step 2.197b, D797: "the beam's bolts aim at
 *   the target, drawn reaching it"): his bolts' three targets, the
 *   locators under m_balth_lightning (the bytes param
 *   player_model_drain_aim: their count, then each record), are inherit
 *   mode 7 on the player's clone (data, W34's overlay), so this anchor
 *   places them (EBX the node).  While the player's beam plays (a column
 *   of float param player_model_drain_beams, its slot playing, a
 *   root-motion attack) each goes on the beam's target, its translate
 *   (side, 0, its chest) in the target's frame; else on the player, its
 *   translate (side, ahead, height) straight ahead to the beam's reach
 *   (float params player_model_drain_aim_reach and _aim_chest).  The
 *   target, picked on the beam's first evaluation and kept while it lives
 *   and stands in the box (AZ-805: one knocked out of it is picked again;
 *   a new beam, 0.5 s or more after the last evaluation, picks its own):
 *   the drain's last pick where it stands in the beam's box, else what
 *   attack_target_find gives along the swing's yaw (PC+0x138: X49's seek
 *   turned it) within the reach (X21's radius raised for the call) where
 *   it stands in the box: from the player within the reach ahead and the
 *   box's half-width (float param player_model_drain_aim_half) either
 *   side of that yaw, each grown by its radius (the review's F2: a 45
 *   degree cone drew the bolts onto a critter 2 m to the side at 4 m,
 *   which the 1.04 m wide box misses).  Its chest: 0.7 of the way up its
 *   world bounds (critter +0xF8, min then max) over glide_origin's
 *   point.  A translate written here rebuilds the node's matrix on the
 *   next records pass (0x663B0 clears +0x10 before the update, whose
 *   local rebuild 0x68120 into +0x70 comes before transform_world), so
 *   the anchor is the one the matrix built this pass holds (its local y
 *   past 0.5 m: straight ahead's, on the player; else the target its
 *   last translate was written for, kept per node while it is that
 *   object, dead or alive, so a target knocked out of the box or killed
 *   keeps the bolts a tick more, never its offset on the player: the
 *   review's P1 and the late review's F1; only a deleted one's falls back
 *   to him): a change shows whole a tick late.
 *
 *   c_player_model_drain_touch, at the platform's hit send 0x7A1CA (Europe
 *   0x7A17A; `push eax; call [edi+0xb4]`, 7 bytes: EAX the hit, ECX the
 *   toucher, EDI its vtable, EBP the platform): for a damage platform (+0x27E level != 0) of type norm
 *   (+0x280) one of the player's graphs made (the node at its +0x294,
 *   that node's instance at +4: the anchor's test) in the world of a player whose drain plays or played under
 *   0.5 s ago (the switch fades over the crossfade after a cancel: the
 *   critique's C1), a touch by the player is dropped (no hit: never the
 *   wearer, also with no target, when the box sits on him) and a touch by
 *   the window's target (its live pick, kept with its identity) is sent,
 *   then the player heals by float param player_model_drain_share (100 %)
 *   of the HP it lost, at least 1, through apply_damage (0x44640, clamped
 *   to his max) while he lives.  A touch by any other critter is dropped
 *   too (AZ-758, Step 2.196, D765: "can you make it just drain the
 *   nearest?"; the box's size is data, [45] on the player's clone,
 *   _player_variants.DRAIN_BOX, 24 x 24 x 4 m, so it drained every
 *   critter within 12 m of the pick), unless float param
 *   player_model_drain_every is 1 (a recipe's or weapon style's
 *   drain.targets "all": beamlord's, D782): then each critter the
 *   box touches is sent and heals him, as before Step 2.196.  Each sent
 *   hit that took HP from a critter, a killing one too, plays the graph
 *   bytes param player_model_drain_fx names (the build's drain stream,
 *   _player_character.DRAIN_STREAM, appended to fx.xbr) on that critter
 *   through critter_play_fx (0x440F0, its +0x23C handle, where the hit's
 *   own visual, played inside the send, is replaced: the stream's graph
 *   keeps the plain hit's flash), so red particles stream from each
 *   critter the drain takes life from into the player's chest (AZ-759,
 *   Step 2.196, D764: "can you have some visual particles coming from the
 *   enemy into the player to indicate their life was drained?"): its
 *   pull and sink hang under an inherit-mode-7 node, which the anchor
 *   leaves to the game (another graph's), the player.  The handle's
 *   flags are then 2, so whatever releases it next (the game's 1 stops
 *   the instance, ending its particles: the AI's death clip at 0x37D16
 *   plays key 0 there, another hit's visual, the critter's delete at
 *   0x4127F) detaches the stream where it is, its emitter frozen on the
 *   victim's last hit location and its pull still on the player, and it
 *   plays out its 0.67 s and unloads (Step 2.196's skeptic, F1: a killing
 *   hit, a third of the drain's hits on 30 HP sleeths, streamed nothing).
 *   A common AI critter's (its controller's hit slot, +0x180's vtable
 *   +0x18, the common AI handler ai_hit_handler 0x38C60; bosses have
 *   their own) first touch in a window passes its no-hit window (+0x1E0,
 *   s, tested > 0 at 0x4323C) when that is 0 < w <= 3.5 s: +0x1E0 := 0
 *   for the send, then max(w, the window the hit gave it), so columns
 *   8-9's hits on the pick just before don't void the drain; the critter
 *   goes into the window's list (8), and its later touches in the window
 *   are the game's.  A sent hit that took HP from a listed critter and
 *   gave it a heavy reaction's window (the handler's level 2 or 3 at
 *   0x38EED: 0.25 s plus its ouch clip or 1 s, the longer, which 0x4356E keeps:
 *   2.58 s on f6's blaze sentinel, norm_2's 15 HP over its threshold 5)
 *   leaves it the window a light hit would (+0x1E0 and +0x1E4 := the
 *   longer of w and the hit record's Delay, 0.33 s; record +0x10, the
 *   message's +8), and X37 drops its own touches by that critter in the
 *   window until that reaction's window would have ended (the list's
 *   hold), so the drain still hits it once a reaction and the wearer's
 *   next swing lands (AZ-765, Step 2.197, D789: in plain play the 2.58 s
 *   voided the beam and finish3 after the drain, on main too).  A sent
 *   hit that took HP from such a critter loses
 *   its knock's horizontal part (AZ-672, Step 2.153c): the handler's
 *   reaction chooser 0x30BD0 (called at 0x38D85, inside the send) writes
 *   the knock velocity at the controller's +0x24 (x, y, z: along the
 *   target less the box's centre, which sits off the pick, and 0.5 v up)
 *   and the handler never reads it again, so after the send +0x24 and
 *   +0x28 := 0: the target hops where it stands (main's 12 m box, centred
 *   on it, knocked it straight up) and stays in his next swing's line.
 *   Every other touch is the game's.  The player is read from the
 *   platform's own world (+0x154, the world's +0xC0) on every touch,
 *   never cached.
 *
 * ABI.  0x7EE3B: ESI the candidate; EAX, ECX are reloaded right after
 * (0x7EE41, 0x7EE4B) and EDX is the mov's; the entry keeps the rest and
 * the flags' consumers come later.  0x68A49: EAX the world, EBX the node
 * (0x681ED: transform_world's argument, kept),
 * EDX the node's instance ([node+4]: the fx instance, whose +0x44 the
 * loader 0x65E50 sets to its world at 0x633FA and whose +0x24 nodes each
 * get it in their init's context at 0x66124 [the store inferred]); EAX,
 * ECX and EDX are dead after (0x68A53-0x68A5D reload them, 0x68ACF
 * reads none), the x87 stack empty (the case starts from the jump table).
 * 0x7A1CA: the entry replaces the push and the indirect call (so its own
 * RET is plain), makes them itself to send (the callee thiscall RET 4),
 * and the caller reads no register after (0x7A1D1 pops).
 * Every C helper is cdecl (it keeps EBX, ESI, EDI and EBP); x87 and SSE1
 * only (AZ-021).
 */

#include "azurik_vanilla.h"   /* attack_target_find, apply_damage, ai_hit_handler, critter_play_fx, glide_origin;
                                 and azurik.h */

#define WD_PLAYER    0x0C0   /* world: the player critter                   */
#define CR_WORLD     0x154   /* a critter or platform: its world           */
#define CR_FLAGS     0x168   /* a critter: its kind flags                   */
#define CR_CONTROL   0x180   /* critter: its PlayerControl, an AI's controller */
#define CT_KNOCK     0x024   /* an AI controller: its knock velocity, m/s (x, y, z) */
#define CR_WINDOW    0x1E0   /* critter: its no-hit window, s (float)        */
#define CR_WINDOW_OF 0x1E4   /* critter: the window its last hit gave (the hit tint's) */
#define HT_RECORD    0x008   /* a hit message: its damage record             */
#define RC_DELAY     0x010   /* a damage record: its Delay, s (f32; 0x43584) */
#define CR_SLOT      0x200   /* critter: the anim slot anim_change took     */
#define CR_HP        0x210   /* critter: its HP (int)                       */
#define OB_SERIAL    0x0E0   /* a world object: its serial, low 24 bits     */
#define SERIAL       0xFFFFFF
#define PC_CLOCK     0x00C   /* PlayerControl -> the clock (+0x10: now)     */
#define PC_COLUMN    0x134
#define PC_YAW       0x138
#define PC_MOVE      0x16C   /* move flags: 8 a root-motion attack          */
#define PF_LEVEL     0x27E   /* platform: its damage level (byte)           */
#define PF_TYPE      0x280   /* platform: its damage type (fourcc)          */
#define CLOCK_NOW    0x010
#define CRITTERS     0x4040  /* the kinds the finder takes                  */
#define NORM         0x6D726F6E   /* "norm" as the engine keeps a fourcc    */
#define ROOT_MOTION  0x08
#define SLOT_ATTACK  0x52
#define COLUMNS      24
#define FOUND_WORDS  14      /* attack_target_find's 0x38-byte result      */
#define HIT_SLOT     6       /* controller vtable +0x18: its hit handler    */
#define PASSES       8       /* critters a window passes                    */
#define PASS_MAX     3.5f    /* s: the longest no-hit window passed         */
#define TAIL         0.5     /* s a drop outlasts the drain: the fade       */
#define SINK_HOLD    1.3     /* s the box sink keeps a lift's span: the stream's particles' life (AZ-764) */
#define HELD         16      /* X38's detached drain copies              */
#define CR_OWN_FX    0x230   /* critter: its fx_default's handle (its instance + 0x20) */
#define CR_HIT_FX    0x23C   /* critter: critter_play_fx's handle            */
#define HD_FLAGS     0x008   /* a handle: how 0x64CE0 releases its instance  */
#define HD_DETACH    2       /* detach it (bit 0, the game's 1: stop it)     */
#define IN_HANDLE    0x020   /* fx instance: where a handle points (0x64C81) */
#define IN_ASSET     0x04C   /* fx instance: its graph's asset (0x63250 at 0x6325C) */
#define PF_NODE      0x294   /* platform: the fx node that made it          */
#define ND_INSTANCE  0x004   /* fx node: its instance                       */
#define ND_ATTRS     0x008   /* fx node: its attributes (f32)               */
#define ND_DIRTY     0x010   /* fx node: its dirty mask (bit i: attribute i) */
#define ND_INHERIT   0x0F0   /* transform: its inherit mode                 */
#define AT_TZ        3       /* a transform's translateZ                    */
#define AT_SZ        9       /* a transform's scaleZ                        */
#define IN_RECORDS   0x024   /* fx instance: its records (begin, end)       */
#define ST_RECORDS   19      /* _player_character.DRAIN_STREAM's records:   */
#define ST_ON_PLAYER 6       /*   [6] onPlayer (inherit 7),                 */
#define ST_PULL      12      /*   [12] pGravity1 and                        */
#define ST_SINK      14      /*   [14] pBoxSink1 under it                   */
#define CR_ANIM      0x17C   /* critter: its anim object                    */
#define AN_BONES     0x008   /* anim object: its posed bones                */
#define BONE_SIZE    0x0B0
#define BONE_Z       0x0A8   /* a bone: its runtime matrix's z, model units */
#define AT_TX        1       /* a transform's translateX                    */
#define AT_TY        2       /* a transform's translateY                    */
#define CR_CENTRE    0x15C   /* critter: its centre (x, y, z), m            */
#define CR_RADIUS    0x090   /* critter: its collision radius, m            */
#define CR_LOW_Z     0x100   /* critter: its world bounds' lowest z (+0xF8 min x, y, z) */
#define CR_HIGH_Z    0x10C   /* ... and highest (+0x104 max x, y, z)        */
#define AIM_NODES    3       /* the bolts' targets                          */
#define AIM_SIDE     0.4f    /* m either side of the facing line, straight ahead */
#define AIM_ON       0.15f   /* m either side of a target's chest           */
#define AIM_CHEST    0.7f    /* a target's chest: this share of its height  */
#define ND_LOCAL_TY  0x0A4   /* fx node: its local matrix's (0x68120's +0x70) translation y */
#define AIM_BUILT    0.5f    /* m: a local y past this is straight ahead's (a target's is 0) */

AZURIK_FLOAT_PARAM(player_model_drain_columns, 0.0f);
AZURIK_FLOAT_PARAM(player_model_drain_share, 1.0f);
AZURIK_FLOAT_PARAM(player_model_drain_range, 16.0f);
AZURIK_FLOAT_PARAM(player_model_drain_every, 0.0f);
AZURIK_FLOAT_PARAM(player_model_drain_chest, 0.0f);   /* m over his model origin; 0: no stream */
AZURIK_FLOAT_PARAM(player_model_drain_bones, 0.0f);   /* his rig's bones                       */
AZURIK_FLOAT_PARAM(player_model_drain_feet, 0.0f);    /* his bind pose's lowest bone, model units */
AZURIK_FLOAT_PARAM(player_model_drain_sink, 0.0f);    /* the box sink's height standing, m; 0: kept */
AZURIK_FLOAT_PARAM(player_model_drain_drawn, 1.0f);   /* metres a model unit                   */
AZURIK_FLOAT_PARAM(player_model_drain_beams, 0.0f);   /* the beam's columns (AZ-769)           */
AZURIK_FLOAT_PARAM(player_model_drain_aim_reach, 0.0f);   /* m: straight ahead, and the search's radius */
AZURIK_FLOAT_PARAM(player_model_drain_aim_chest, 0.0f);   /* m over his model origin, straight ahead */
AZURIK_FLOAT_PARAM(player_model_drain_aim_half, 0.0f);    /* m: the beam box's half-width either side */
AZURIK_BYTES_PARAM(player_model_drain_radius_at, 4);
AZURIK_BYTES_PARAM(player_model_drain_state_at, 4);
AZURIK_BYTES_PARAM(player_model_drain_fx, 32);   /* _player_character.DRAIN_FX_SIZE */
AZURIK_BYTES_PARAM(player_model_drain_aim, 4);   /* the aim nodes: their count, then each one's record */

struct kept {         /* a critter kept across ticks, with its identity (AZ-682) */
    char *critter;    /* 0 none, or gone                                */
    const void *vtable;   /* its vtable when kept                       */
    unsigned serial;      /* its serial when kept                       */
};

struct held {
    char *instance;   /* a detached drain copy (X38 writes it)          */
    struct kept target;   /* where its mode-7 nodes stay while it lives */
};

struct drain_state {
    char *best;       /* the finder's last better candidate             */
    struct kept target;   /* the window's target                        */
    int active;       /* a window is open                                */
    int passes;       /* critters in passed                              */
    double seen;      /* the clock at the drain's last evaluation        */
    char *passed[PASSES];   /* the window's critters whose window it passed (compared, never read) */
    struct held held[HELD]; /* X38's (fx_ring.c's DrainState, the same layout) */
    double hold[PASSES];    /* each listed critter's: no drain touch sent before this clock (AZ-765) */
};

_Static_assert(sizeof(struct held) == 16 && sizeof(struct drain_state) == 384, "fx_ring.c's DrainState");

struct drain_state player_model_drain_state = {0, {0, 0, 0}, 0, 0, -1e300, {0}, {{0, {0, 0, 0}}}, {0}};

static struct kept aim;         /* the anchor landing's: the beam's target (AZ-769)  */
static struct kept drained;     /* ... the drain's last pick, while it lives         */
static struct kept shown[AIM_NODES];   /* each aim node's: the target its last translate is for */
static double aim_seen = -1e300;   /* the clock at the beam's last evaluation         */
static double aim_at = -1e300;     /* the clock its target was last chosen at          */
static float held_lift;            /* the follow's: the largest lift within SINK_HOLD  */
static double held_at = -1e300;    /* ... and the clock it was last reached at         */
static char *heal_player;  /* the touch landing's: the player its last sent hit heals */
static int hp_before;
static char *window_critter;   /* the critter whose window the last send passed */
static float window_before;
static int sent_at;            /* the last send's critter's place in the list, or -1 */
static float sent_window;      /* its window before the touch */
static double sent_now;        /* the clock at the touch */

/* The instance plays the player's own graph: his fx_default's instance or
 * another of its asset (X38's copies), never another critter's (the
 * airship boss's) or another graph's (Step 2.161c, the review's P1). */
static int mine(const char *player, const char *instance)
{
    const char *handle = player ? *(const char *const *)(player + CR_OWN_FX) : 0;
    const char *own = handle ? handle - IN_HANDLE : 0;

    return own && instance
        && (instance == own || *(const int *)(instance + IN_ASSET) == *(const int *)(own + IN_ASSET));
}

static struct drain_state *state(void)
{
    unsigned at = *(const volatile unsigned *)player_model_drain_state_at;

    return at ? (struct drain_state *)at : &player_model_drain_state;
}

static double clock_now(const char *pc)
{
    return *(const double *)(*(const char *const *)(pc + PC_CLOCK) + CLOCK_NOW);
}

/* The player's PlayerControl when a column of ``mask`` plays now, else 0. */
static const char *playing(const char *player, float mask)
{
    const char *pc = *(const char *const *)(player + CR_CONTROL);
    int column;

    if (!pc)
        return 0;
    column = *(const int *)(pc + PC_COLUMN);
    if (column < 0 || column >= COLUMNS || !(((unsigned)(int)mask >> column) & 1)
            || *(const int *)(player + CR_SLOT) != SLOT_ATTACK + column
            || !(*(const unsigned char *)(pc + PC_MOVE) & ROOT_MOTION))
        return 0;
    return pc;
}

/* The player's PlayerControl when its drain plays now, else 0. */
static const char *draining(const char *player)
{
    return playing(player, player_model_drain_columns);
}

/* The critter nearest the swing's yaw within the drain's range, else 0. */
static char *pick(char *player, const char *pc, struct drain_state *s)
{
    float *radius = *(float *const volatile *)player_model_drain_radius_at;
    float was;
    int found[FOUND_WORDS];

    if (!radius)
        return 0;
    was = *radius;
    *radius = player_model_drain_range;
    s->best = 0;
    attack_target_find(player, *(const float *)(pc + PC_YAW), found);
    *radius = was;
    return found[0] ? s->best : 0;
}

/* k := critter, with its identity. */
static void keep(struct kept *k, char *critter)
{
    k->critter = critter;
    k->vtable = critter ? *(const void *const *)critter : 0;
    k->serial = critter ? *(const unsigned *)(critter + OB_SERIAL) & SERIAL : 0;
}

/* k's critter while it is the object kept (its vtable and serial), dead
 * or alive, else 0. */
static char *same(const struct kept *k)
{
    const char *c = k->critter;

    return c && *(const void *const *)c == k->vtable && (*(const unsigned *)(c + OB_SERIAL) & SERIAL) == k->serial
        ? k->critter : 0;
}

/* k's critter while it is the object kept and lives, else 0 and k
 * dropped: its identity first, so the HP of a deleted critter, or of
 * another one in its block, is never read for it (AZ-682). */
static char *live(struct kept *k)
{
    char *c = same(k);

    if (c && *(const int *)(c + CR_HP) > 0)
        return c;
    keep(k, 0);
    return 0;
}

/* How far a clip lifts the player's drawn body: his lowest posed bone
 * over his bind pose's, in metres (Balthazar's basic3 2.0 m); 0 with no
 * anim object. */
static float lift(const char *player)
{
    const char *anim = *(const char *const *)(player + CR_ANIM);
    const char *bones = anim ? *(const char *const *)(anim + AN_BONES) : 0;
    int n = (int)player_model_drain_bones, i;
    float low, z;

    if (!bones || n <= 0)
        return 0.0f;
    low = *(const float *)(bones + BONE_Z);
    for (i = 1; i < n; i++)
        if ((z = *(const float *)(bones + i * BONE_SIZE + BONE_Z)) < low)
            low = z;
    return (low - player_model_drain_feet) * player_model_drain_drawn;
}

static void put(char *node, int k, float v)
{
    float *at = *(float *const *)(node + ND_ATTRS);

    if (at && at[k] != v) {
        at[k] = v;
        *(unsigned *)(node + ND_DIRTY) |= 1u << k;
    }
}

static void put_z(char *node, float z)
{
    put(node, AT_TZ, z);
}

/* The lift the box sink spans (AZ-764): the largest (by size) within
 * SINK_HOLD of the clock, so the box keeps a lift's span while particles
 * born toward the lifted chest still fly; ``up`` itself with no clock. */
static float span(const char *player, float up)
{
    const char *pc = *(const char *const *)(player + CR_CONTROL);
    double now, since;

    if (!pc || !*(const char *const *)(pc + PC_CLOCK))
        return up;
    now = clock_now(pc);
    since = now - held_at;
    if ((up < 0.0f ? -up : up) >= (held_lift < 0.0f ? -held_lift : held_lift)
            || !(since >= 0.0 && since < SINK_HOLD)) {
        held_lift = up;
        held_at = now;
    }
    return held_lift;
}

/* AZ-764: the drain stream's pull at the player's drawn chest, raised by
 * what a clip lifts his body (its onPlayer node, which this evaluation
 * places, comes before them in the records pass); its box sink spans his
 * standing chest to the lifted one, the standing height
 * (player_model_drain_sink) taller by the lift, so a particle still
 * flying at the chest the pull left meets it (Step 2.202: as the pull
 * rose 0.5-0.6 m a tick, particles at 20-50 m/s passed under the lifted
 * box and the pull's 1/d field flung them 12-17 m before their 1.3 s
 * ended); and it keeps the largest lift's span for the particles' 1.3 s
 * life after the lift ends (Step 2.202b: as basic3's 2.1 m lift ended,
 * the pull dropping 0.6-0.7 m a tick, particles flying in at 30-40 m/s
 * from a target 10 m off passed over the standing box and flew 11-13 m
 * off the stream's line). */
static void follow(const char *instance, const char *player)
{
    char *const *recs = *(char *const *const *)(instance + IN_RECORDS);
    char *const *end = *(char *const *const *)(instance + IN_RECORDS + 4);
    float up, held;

    if (!recs || end - recs != ST_RECORDS || *(const int *)(recs[ST_ON_PLAYER] + ND_INHERIT) != 7)
        return;
    up = lift(player);
    put_z(recs[ST_PULL], player_model_drain_chest + up);
    if (player_model_drain_sink > 0.0f) {
        held = span(player, up);
        put_z(recs[ST_SINK], player_model_drain_chest + 0.5f * held);
        put(recs[ST_SINK], AT_SZ, player_model_drain_sink + (held < 0.0f ? -held : held));
    } else
        put_z(recs[ST_SINK], player_model_drain_chest + up);
}

/* Whether critter t stands in the beam's box from the player: ahead of
 * him within its reach and within its half-width either side of the
 * swing's yaw, each grown by t's radius. */
static int in_beam(const char *player, const char *t, float yaw)
{
    const float *p = (const float *)(player + CR_CENTRE), *q = (const float *)(t + CR_CENTRE);
    float dx = q[0] - p[0], dy = q[1] - p[1], r = *(const float *)(t + CR_RADIUS), sine, cosine, ahead, side;

    __asm__ ("fsin" : "=t"(sine) : "0"(yaw));     /* x87: no libm */
    __asm__ ("fcos" : "=t"(cosine) : "0"(yaw));
    ahead = -sine * dx + cosine * dy;   /* forward is (-sin, cos) */
    side = cosine * dx + sine * dy;
    return ahead + r >= 0.0f && ahead - r <= player_model_drain_aim_reach
        && side <= player_model_drain_aim_half + r && -side <= player_model_drain_aim_half + r;
}

/* What attack_target_find gives along the yaw within the beam's reach
 * where it stands in the beam's box, else 0. */
static char *look(char *player, float yaw, struct drain_state *s)
{
    float *radius = *(float *const volatile *)player_model_drain_radius_at;
    float was;
    int found[FOUND_WORDS];

    if (!radius)
        return 0;
    was = *radius;
    *radius = player_model_drain_aim_reach;
    s->best = 0;
    attack_target_find(player, yaw, found);
    *radius = was;
    return found[0] && s->best && in_beam(player, s->best, yaw) ? s->best : 0;
}

/* The beam's target (AZ-769): kept while it lives and stands in the
 * beam's box (AZ-805: one knocked out of it is picked again), else the
 * drain's last pick in the beam's line, else the finder's; chosen once a
 * tick. */
static char *beam_target(char *player, const char *pc, struct drain_state *s)
{
    double now = clock_now(pc), since = now - aim_seen;
    float yaw = *(const float *)(pc + PC_YAW);
    char *t;

    aim_seen = now;
    if (!(since >= 0.0 && since < TAIL))   /* a new beam: its own target */
        keep(&aim, 0);
    if ((t = live(&aim)) != 0 && !in_beam(player, t, yaw))   /* out of the box: picked again */
        keep(&aim, 0), t = 0;
    if (t || now == aim_at)   /* kept, or none found this tick */
        return t;
    aim_at = now;
    t = live(&drained);
    keep(&aim, t && in_beam(player, t, yaw) ? t : look(player, yaw, s));
    return live(&aim);
}

/* A critter's chest over its drawn origin, m: 0.7 of its world bounds' height. */
static float chest_of(const char *t)
{
    float low = *(const float *)(t + CR_LOW_Z), high = *(const float *)(t + CR_HIGH_Z), origin[3];

    if (!(high >= low && high - low < 100.0f))
        return 1.0f;
    glide_origin(t, origin);
    return low + AIM_CHEST * (high - low) - origin[2];
}

/* The aim node of its instance's place k, or -1. */
static int aim_slot(const char *instance, const char *node)
{
    int n = player_model_drain_aim[0], k;
    char *const *recs = n ? *(char *const *const *)(instance + IN_RECORDS) : 0;
    char *const *end = n ? *(char *const *const *)(instance + IN_RECORDS + 4) : 0;

    for (k = 0; recs && k < n && k < AIM_NODES; k++)
        if (player_model_drain_aim[1 + k] < end - recs && recs[player_model_drain_aim[1 + k]] == node)
            return k;
    return -1;
}

/* AZ-769: aim node k on the beam's target, else straight ahead on the player.
 * Its translate is written for the next records pass, and it goes on
 * the anchor the matrix this pass built from the last one holds (the
 * target that one was written for, y 0, while it is that object, dead or
 * alive, or straight ahead's), so a change shows whole a tick late, never
 * a target's offset on the player or his on the target (the review's P1;
 * the late review's F1: a target the beam killed with another critter in
 * the box put its offset on him for that tick).  Only a deleted target's
 * last translate falls back to him. */
static char *aim_node(char *player, char *node, int k, struct drain_state *s)
{
    static const float side[AIM_NODES] = {-1.0f, 1.0f, 0.0f}, ahead[AIM_NODES] = {0.8f, 0.8f, 1.0f};
    const char *pc = playing(player, player_model_drain_beams);
    char *t = pc ? beam_target(player, pc, s) : 0, *built;

    built = *(const float *)(node + ND_LOCAL_TY) > AIM_BUILT ? 0 : same(&shown[k]);
    keep(&shown[k], t);
    if (t) {
        put(node, AT_TX, side[k] * AIM_ON);
        put(node, AT_TY, 0.0f);
        put(node, AT_TZ, chest_of(t));
    } else {
        put(node, AT_TX, side[k] * AIM_SIDE);
        put(node, AT_TY, ahead[k] * player_model_drain_aim_reach);
        put(node, AT_TZ, player_model_drain_aim_chest);
    }
    return built ? built : player;
}

__attribute__((used))
char *drain_anchor(const char *world, const char *instance, char *node)
{
    struct drain_state *s = state();
    char *player = *(char *const *)(world + WD_PLAYER), *target;
    const char *pc = player ? draining(player) : 0;
    double now, since;
    int k;

    for (k = 0; instance && k < HELD; k++)   /* a detached drain copy: on its target while it lives */
        if (s->held[k].instance == instance)
            return (target = live(&s->held[k].target)) != 0 ? target : player;   /* gone: X38 closes it */
    if (!mine(player, instance)) {   /* the airship boss's own: the game's, the state untouched */
        if (player && instance && player_model_drain_chest > 0.0f)   /* or the drain's stream (AZ-764) */
            follow(instance, player);
        return player;
    }
    if (node && (k = aim_slot(instance, node)) >= 0)   /* the beam's bolts (AZ-769) */
        return aim_node(player, node, k, s);
    if (!pc) {   /* the drain stopped: its target kept for TAIL while it lives */
        const char *control = player ? *(const char *const *)(player + CR_CONTROL) : 0;
        since = control ? clock_now(control) - s->seen : -1.0;
        if (s->active && since >= 0.0 && since < TAIL && (target = live(&s->target)) != 0)
            return target;
        s->active = 0;
        keep(&s->target, 0);
        return player;
    }
    now = clock_now(pc);
    since = now - s->seen;
    s->seen = now;
    if (!s->active || !(since >= 0.0 && since < TAIL)) {   /* a new window, though none ran between */
        s->active = 1;
        s->passes = 0;
        keep(&s->target, 0);
    }
    if (!live(&s->target)) {   /* none live: pick again, the list kept */
        keep(&s->target, pick(player, pc, s));
        if (s->target.critter)   /* the beam's first choice (AZ-769) */
            keep(&drained, s->target.critter);
    }
    return (target = live(&s->target)) != 0 ? target : player;
}

/* 0x68A49: ESI := the drain's anchor (the game's player critter, or its target). */
__attribute__((naked))
void c_player_model_drain_anchor(void)
{
    __asm__ volatile (
        "pushl %%ebx                        \n\t"   /* the node */
        "pushl %%edx                        \n\t"   /* the node's instance */
        "pushl %%eax                        \n\t"   /* the world */
        "calll _drain_anchor                \n\t"
        "addl $12, %%esp                    \n\t"
        "movl %%eax, %%esi                  \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void drain_found(char *candidate)
{
    state()->best = candidate;
}

/* 0x7EE3B: the finder's better candidate (ESI) recorded, then mov edx, [esi+0x168]. */
__attribute__((naked))
void c_player_model_drain_find(void)
{
    __asm__ volatile (
        "pushl %%esi                        \n\t"
        "calll _drain_found                 \n\t"
        "addl $4, %%esp                     \n\t"
        "movl 0x168(%%esi), %%edx           \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

/* The toucher's controller when its hit slot is the common AI handler, else 0. */
static char *ai_control(const char *toucher)
{
    char *control = *(char *const *)(toucher + CR_CONTROL);
    const void *const *vtable = control ? *(const void *const *const *)control : 0;

    return vtable && vtable[HIT_SLOT] == (const void *)&ai_hit_handler ? control : 0;
}

/* A common AI critter's place in the window's list, -1 for another
 * critter or a full list: its first touch in the window lists it (no hold)
 * and passes its no-hit window (0 < w <= PASS_MAX), cleared for the send. */
static int listed(char *toucher, struct drain_state *s)
{
    float w = *(const float *)(toucher + CR_WINDOW);
    int k;

    window_critter = 0;
    if (!ai_control(toucher))
        return -1;
    for (k = 0; k < s->passes && k < PASSES; k++)
        if (s->passed[k] == toucher)
            return k;
    if (s->passes >= PASSES)
        return -1;
    s->passed[k = s->passes++] = toucher;
    s->hold[k] = -1e300;
    if (w > 0.0f && w <= PASS_MAX) {
        window_critter = toucher;
        window_before = w;
        *(float *)(toucher + CR_WINDOW) = 0.0f;
    }
    return k;
}

/* AZ-765: a sent hit that gave the listed critter (place k) a heavy
 * reaction's window leaves it a light hit's, the longer of its window
 * before the touch and the hit record's Delay, and holds the drain's own
 * touches off it until the heavy one would have ended. */
static void hold_off(char *toucher, const char *hit, struct drain_state *s, int k)
{
    float *w = (float *)(toucher + CR_WINDOW), light = sent_window > 0.0f ? sent_window : 0.0f;
    const char *record;

    if (!(*w > light))
        return;
    record = *(const char *const *)(hit + HT_RECORD);
    if (record && *(const float *)(record + RC_DELAY) > light)
        light = *(const float *)(record + RC_DELAY);
    if (!(*w > light))
        return;
    s->hold[k] = sent_now + *w;
    *w = light;
    *(float *)(toucher + CR_WINDOW_OF) = light;
}

/* 0: drop the hit; 1: send it; 2: send it, then heal the player. */
__attribute__((used))
int drain_touch_before(char *toucher, const char *platform)
{
    struct drain_state *s = state();
    const char *world = *(const char *const *)(platform + CR_WORLD);
    char *player = world ? *(char *const *)(world + WD_PLAYER) : 0;
    const char *node = *(const char *const *)(platform + PF_NODE), *pc;
    double now, since;
    int k;

    if (!player || !*(const unsigned char *)(platform + PF_LEVEL) || *(const unsigned *)(platform + PF_TYPE) != NORM
            || !node || !mine(player, *(const char *const *)(node + ND_INSTANCE)))   /* the boss's box, the world's */
        return 1;
    pc = *(const char *const *)(player + CR_CONTROL);
    if (!pc)
        return 1;
    now = clock_now(pc);
    since = now - s->seen;
    if (!draining(player) && !(since >= 0.0 && since < TAIL))
        return 1;
    if (toucher == player)
        return 0;
    if (!toucher || !(*(const unsigned *)(toucher + CR_FLAGS) & CRITTERS))
        return 1;
    if (!(player_model_drain_every > 0.5f) && toucher != live(&s->target))
        return 0;   /* AZ-758 (D765): the nearest alone, its target */
    sent_window = *(const float *)(toucher + CR_WINDOW);
    k = listed(toucher, s);
    if (k >= 0 && now < s->hold[k])
        return 0;   /* AZ-765: held off it for its heavy reaction's window */
    sent_at = k;
    sent_now = now;
    heal_player = player;
    hp_before = *(const int *)(toucher + CR_HP);
    return 2;
}

__attribute__((used))
void drain_touch_after(char *toucher, int what, const char *hit)
{
    char *player = heal_player, *control;
    int lost, heal, hp;

    if (what != 2 || !player)
        return;
    if (window_critter == toucher) {   /* the critter's window: the longer of its old and the hit's */
        float *w = (float *)(toucher + CR_WINDOW);

        if (*w < window_before)
            *w = window_before;
        window_critter = 0;
    }
    lost = hp_before - *(const int *)(toucher + CR_HP);
    if (lost > 0 && sent_at >= 0)   /* AZ-765: a light hit's window, the drain held off */
        hold_off(toucher, hit, state(), sent_at);
    if (lost > 0 && (control = ai_control(toucher)) != 0) {   /* AZ-672: it hops where it stands */
        *(float *)(control + CT_KNOCK) = 0.0f;
        *(float *)(control + CT_KNOCK + 4) = 0.0f;
    }
    if (lost > 0 && player_model_drain_fx[0]) {   /* AZ-759: its stream, a killing hit's too */
        critter_play_fx((void *)toucher, (const char *)player_model_drain_fx);
        if (*(char *const *)(toucher + CR_HIT_FX))   /* let go where it is, never stopped */
            *(unsigned *)(toucher + CR_HIT_FX + HD_FLAGS) = HD_DETACH;
    }
    hp = *(const int *)(player + CR_HP);
    if (lost <= 0 || hp <= 0)
        return;
    heal = (int)(player_model_drain_share * (float)lost + 0.5f);
    apply_damage((int)player, hp + (heal < 1 ? 1 : heal), 0);
}

/* 0x7A1CA: drop the player's touch, or PUSH EAX; CALL [EDI+0xB4] (ECX the toucher) and heal. */
__attribute__((naked))
void c_player_model_drain_touch(void)
{
    __asm__ volatile (
        "pushl %%eax                        \n\t"   /* the hit, kept */
        "pushl %%ecx                        \n\t"   /* the toucher, kept */
        "pushl %%ebp                        \n\t"   /* the platform */
        "pushl %%ecx                        \n\t"
        "calll _drain_touch_before          \n\t"
        "addl $8, %%esp                     \n\t"
        "popl %%ecx                         \n\t"
        "testl %%eax, %%eax                 \n\t"
        "jz 1f                              \n\t"
        "pushl %%eax                        \n\t"   /* what after */
        "pushl %%ecx                        \n\t"   /* the toucher */
        "pushl 8(%%esp)                     \n\t"   /* the hit */
        "calll *0xb4(%%edi)                 \n\t"   /* pops it */
        "calll _drain_touch_after           \n\t"
        "addl $8, %%esp                     \n\t"
        "1:                                 \n\t"
        "addl $4, %%esp                     \n\t"   /* the hit */
        "retl                               \n\t"
        : : : "memory"
    );
}
