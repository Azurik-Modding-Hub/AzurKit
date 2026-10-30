/* X3: a damage marker for the attacks whose clip has none (Step 2.21c;
 * D112; per column since Step 2.64, D219).  Hooked at the CALL 0x8C8A0
 * at VA 0x8C3B0 in the PlayerControl tick (0x8C230), only in a
 * --player-character build where some attack plays a clip that
 * switches no damage marker on (flicken and the townspeople, whose
 * clips switch none on; Balthazar's attack_2), a standardized one, or
 * one whose body has no clips (garret4's clips as timers, Step 2.67).
 *
 * Why.  The per-critter damage pass (0x43A80) builds a hit box only
 * from the markers critter_init cached at critter+0x218 (m_damage)
 * and +0x21C (m_damage2), and only while a marker's active value
 * (+0x30) is at least 0.5 and its length (+0x2C) above 0.  For a clip
 * that switches none on, +0x218 is NULL (or a marker that clip leaves
 * off), so that attack never queries a target (xemu sitting swapb,
 * 2026-10-12: flicken, 0 queries and 0 HP dealt over 172 attack ticks).
 *
 * What.  Each tick, before the staff-wall check it replaces, the shim
 * keeps the marker critter_init cached (critter+0x218 whenever it isn't
 * this shim's) and points +0x218 at the static marker below for the
 * attacks_anims columns in `player_model_x3_columns` (a 24-bit mask:
 * the columns whose clip has no damage window), and at that kept marker
 * for every other column, so a clip with its own damage window hits
 * with the body's own box.  The static marker is on from 20% to 50% of
 * the attack move: while PlayerControl+0x94 has the attack bit 0x100
 * and the attacks_anims column playing (+0x134) is an attack (not -1,
 * none, and not 20, the roll).  The move runs from its row's Move start
 * (+0xF8) to Move end2 (+0x100), as fractions of the clip; +0x178 is
 * the clip's time over its length, which the caller stores just before
 * the call (0x8C3AA).  A combo chains its next attack inside state
 * 0x100 (player_attack_enter 0x88990 re-times the clip but the time in
 * state, +0x9C, runs on), so the window follows the move, not the time
 * in state.  A hit reaction keeps it off (AZ-295): the hit handler
 * 0x8D600 sets state 0x102, which has the attack bit, and leaves the
 * interrupted attack's column at +0x134; the reaction's anim, 37-42
 * (ouch_1 to ouch_1b), is at critter+0x200, which 0x42750 writes (an
 * attack's is 0x52 + its column, written by anim_change 0x42910).  The
 * damage pass does the rest: the box, the critter's world matrix, the
 * targets (0x460B0), the damage type and the attack's Damage
 * multiplier.
 *
 * Where (D219: one action point per body, shared with the element
 * effects).  The box's centre, in model units (the damage pass scales
 * it by the critter's +0x188), is the action point plus
 * `player_model_x3_offset_*` over that scale (garret4's units, so the
 * offset is garret4's size on any model): the action point is the
 * runtime matrix of bone `player_model_x3_bone` (its translation, row 3
 * of the 4x4 at the bone's runtime record +0x70; the records, 0xB0
 * bytes each, at the anim object's (critter+0x17C) +8, as 0xCCDF0 reads
 * them for a bound fx transform) when that is 0 or more, else the fixed
 * point `player_model_x3_point_*`.  A hand body's box follows its hand
 * with garret4's box ahead of it, the hand's sideways place (x) times
 * `player_model_x3_side` (Step 2.103, AZ-521: the build's 1 over a model
 * scale above 1, so a scaled-up body's box stays as far to the side of
 * its facing line as at x1, where the hand x the scale would carry
 * garret4's narrow box off a small target; 1 otherwise); a body without a hand has it at its
 * own hit box's anchor or in front of its chest.  Standardized (D131)
 * the point is 0 and the offset garret4's box position (0.1625, 1.2341,
 * 0.564): garret4's box on every column, as before.  Its extents are
 * garret4's attack_1 box's, (0.2412, 3.0497, 1.3889) x length 0.5,
 * divided by the scale too, so the box is garret4's size on any model.
 *
 * garret4's exact (Step 2.68), and a body with no clips in every mode
 * (Step 2.75e, AZ-473).  When the build sets `g_boxes.exact`,
 * each column takes its own row of `g_boxes` instead: garret4's box
 * and window for the clip that column plays in vanilla (its m_damage's
 * windows on garret4's body, from characters.xbr): the marker is on
 * while the clip's time over its length (+0x178) is within the row's
 * window, garret4's own (basic1's 0.375-0.49, left1's 0.15-0.23), and
 * its centre is the row's (from the action point, garret4's units) and
 * its extents the row's (the box bounding garret4's boxes over the
 * window), both over the scale as above.  In this mode W5 plays each
 * move in garret4's time and X10 isn't installed (each column plays its
 * one clip), so the clip's fraction is garret4's.  A row with no window
 * (the roll) keeps the marker off.  And +0x21C, the body's m_damage2,
 * when it has one, points at `g_off`, a marker that is never on, so
 * only garret4's box hits (the water tentacles' attack clips switch
 * their m_damage2 on).  Every other build leaves the table zero (the
 * build writes it where it landed, its own .data$x3 section) and
 * +0x21C alone.
 *
 * The damage pass never reads a marker's +0 (the body's marker
 * record), and the pose update (0xCBC80) resets only the markers in
 * the model's own array, so this one keeps what the shim writes.
 *
 * ABI: the replaced CALL pushes the PlayerControl (0x8C3A9); the staff
 * check is __stdcall(4) and its AL return is ignored (0x8C3B5 moves
 * EDI to ESI and calls 0x8C520).  The shim is __stdcall(4) too and
 * ends by calling the staff check, so the game sees the same call.
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

#define PC_CRITTER     0x020   /* PlayerControl -> its critter              */
#define PC_STATE       0x094   /* bit 0x100: an attack move plays           */
#define PC_MOVE_START  0x0F8   /* the move's start, a fraction of the clip  */
#define PC_MOVE_END2   0x100   /* the move's end                            */
#define PC_ATTACK      0x134   /* the attacks_anims column; -1 none         */
#define PC_CLIP_TIME   0x178   /* the clip's time over its length           */
#define CR_ANIM        0x17C   /* critter -> its anim object, or NULL       */
#define CR_SCALE       0x188   /* critter scale (the species' `scale`)      */
#define CR_ANIM_INDEX  0x200   /* critter's playing anim index              */
#define CR_DAMAGE      0x218   /* critter's m_damage marker pointer         */
#define CR_DAMAGE2     0x21C   /* critter's m_damage2 marker pointer        */
#define AN_BONES       0x008   /* anim object -> its runtime bone records   */
#define BONE_SIZE      0xB0
#define BONE_ORIGIN    0x0A0   /* the runtime matrix's (+0x70) translation  */

#define STATE_ATTACK   0x100
#define ATTACK_NONE    (-1)
#define ATTACK_ROLL    20      /* attacks_anims column 'roll forward'       */
#define COLUMNS        24
#define ANIM_HIT_FIRST 37      /* ouch_1: the hit reactions are 37-42       */
#define ANIM_HIT_LAST  42      /* ouch_1b                                   */
#define WINDOW_START   0.2f    /* of the move                               */
#define WINDOW_END     0.5f

AZURIK_FLOAT_PARAM(player_model_x3_columns, 16777215.0f);   /* every column */
AZURIK_FLOAT_PARAM(player_model_x3_bone, -1.0f);
AZURIK_FLOAT_PARAM(player_model_x3_point_x, 0.0f);
AZURIK_FLOAT_PARAM(player_model_x3_point_y, 0.0f);
AZURIK_FLOAT_PARAM(player_model_x3_point_z, 0.0f);
AZURIK_FLOAT_PARAM(player_model_x3_offset_x, 0.1625f);
AZURIK_FLOAT_PARAM(player_model_x3_offset_y, 1.2341f);
AZURIK_FLOAT_PARAM(player_model_x3_offset_z, 0.564f);
AZURIK_FLOAT_PARAM(player_model_x3_side, 1.0f);   /* the hand's sideways place x this */

/* The runtime marker 0xCA2B0 returns (0x34 bytes; the damage pass reads
 * +0x04..+0x30). */
typedef struct DamageMarker {
    const void *record;   /* +0x00 */
    float position[3];    /* +0x04 */
    float rotation[4];    /* +0x10 quaternion x, y, z, w */
    float extent[3];      /* +0x20 */
    float length;         /* +0x2C */
    float active;         /* +0x30 */
} DamageMarker;

_Static_assert(sizeof(DamageMarker) == 0x34, "a runtime marker is 0x34 bytes");

static DamageMarker g_marker = {
    0, {0.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 0.0f, 1.0f},
    {0.2412f, 3.0497f, 1.3889f}, 0.0f, 0.0f,
};
static DamageMarker *g_own;   /* the body's m_damage, as critter_init cached it */
static DamageMarker g_off;    /* never on (length and active 0): garret4's exact's m_damage2 */

/* garret4's exact: one row per attacks_anims column (Step 2.68). */
typedef struct ColumnBox {
    float on;                 /* +0x00 the window's start, a fraction of the clip */
    float off;                /* +0x04 its end                                    */
    float centre[3];          /* +0x08 the box's centre from the action point     */
    float extent[3];          /* +0x14 its extents (x the marker's length 0.5)    */
} ColumnBox;

typedef struct ColumnBoxes {
    int exact;                /* +0x00 1: every column takes its row              */
    ColumnBox column[COLUMNS];/* +0x04                                           */
} ColumnBoxes;

_Static_assert(sizeof(ColumnBox) == 0x20, "the build writes 32-byte rows");
_Static_assert(sizeof(ColumnBoxes) == 4 + 0x20 * COLUMNS, "the build writes the table at this size");

__attribute__((section(".data$x3"), used))
static ColumnBoxes g_boxes = {0};

__attribute__((stdcall))
unsigned char c_player_damage_marker(char *pc)
{
    char *critter = *(char **)(pc + PC_CRITTER);
    DamageMarker **slot = (DamageMarker **)(critter + CR_DAMAGE);
    float scale = *(float *)(critter + CR_SCALE);
    float k = scale > 0.0f ? 1.0f / scale : 1.0f;
    float start = *(float *)(pc + PC_MOVE_START);
    float span = *(float *)(pc + PC_MOVE_END2) - start;
    float clip = *(float *)(pc + PC_CLIP_TIME);
    float done = clip - start;
    int attack = *(int *)(pc + PC_ATTACK);
    int anim = *(int *)(critter + CR_ANIM_INDEX);
    unsigned columns = (unsigned)(int)player_model_x3_columns;
    int bone = (int)player_model_x3_bone;
    char *pose = *(char **)(critter + CR_ANIM);
    float *at = 0;
    const ColumnBox *box = 0;
    int on;

    if (*slot != &g_marker)
        g_own = *slot;
    if (g_boxes.exact && *(DamageMarker **)(critter + CR_DAMAGE2))
        *(DamageMarker **)(critter + CR_DAMAGE2) = &g_off;   /* only garret4's box hits */
    if ((unsigned)attack < COLUMNS && !((columns >> attack) & 1)) {
        *slot = g_own;   /* this clip has its own damage window */
        return player_staff_wall_check(pc);
    }
    if (g_boxes.exact && (unsigned)attack < COLUMNS)
        box = &g_boxes.column[attack];
    on = (*(unsigned int *)(pc + PC_STATE) & STATE_ATTACK)
         && attack != ATTACK_NONE && attack != ATTACK_ROLL
         && (anim < ANIM_HIT_FIRST || anim > ANIM_HIT_LAST)
         && (g_boxes.exact
             ? box && box->off > box->on && clip >= box->on && clip <= box->off
             : span > 0.0f && done >= WINDOW_START * span && done <= WINDOW_END * span);
    if (bone >= 0 && pose && *(char **)(pose + AN_BONES))
        at = (float *)(*(char **)(pose + AN_BONES) + BONE_SIZE * bone + BONE_ORIGIN);
    g_marker.position[0] = (at ? at[0] * player_model_x3_side : player_model_x3_point_x)
                           + (box ? box->centre[0] : player_model_x3_offset_x) * k;
    g_marker.position[1] = (at ? at[1] : player_model_x3_point_y)
                           + (box ? box->centre[1] : player_model_x3_offset_y) * k;
    g_marker.position[2] = (at ? at[2] : player_model_x3_point_z)
                           + (box ? box->centre[2] : player_model_x3_offset_z) * k;
    if (box) {
        g_marker.extent[0] = box->extent[0];
        g_marker.extent[1] = box->extent[1];
        g_marker.extent[2] = box->extent[2];
    }
    g_marker.length = 0.5f * k;
    g_marker.active = on ? 1.0f : 0.0f;
    *slot = &g_marker;
    return player_staff_wall_check(pc);
}
