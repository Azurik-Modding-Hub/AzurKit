/* X10: a player model's attacks rotate through its attack clips, one per
 * swing (Step 2.64; D219 amended: "give them as many attacks as we
 * can"; D227).  Hooked at player_attack_enter's (0x88990) CALL of
 * anim_change (0x42910) at VA 0x889A6, only in a --player-character
 * build whose body has more attack clips than the three of the combo
 * (balthazar_spider's ten: attack_1-7, deathbeam, jump, whirlwind).
 *
 * Why.  Each attacks_anims column plays one clip, the one its Anim names
 * (W3 picks one of the body's attack clips per column), resolved per
 * body into the species' clip slot 0x52 + the column.  The player
 * reaches only a few columns (the combo basic1-3, the jump attack, a few
 * by direction), so most of a body with many attack clips never shows.
 *
 * What.  player_attack_enter plays the attack's anim (0x52 + its
 * column, PlayerControl+0xE0) through anim_change with flags 4.  For
 * the player's species (the `player` flag 0x20 in S+0x64) and a column
 * in the ring's `rotate` mask (the attack columns that rotate), the shim
 * takes the ring's next entry and puts the clip of that entry's column
 * (the first column holding it) into the swinging column's slot for the
 * call, then puts the slot back, as X7 does, so the index anim_change
 * records (critter+0x200) stays the game's and the move keeps its
 * column's Move cells (and its Rate and Damage multiplier, unless the
 * ring carries the entry's: below).  The rotation is
 * deterministic (rotation, not a random pick): each swing takes the next
 * entry, round again, and the ring's place persists (D227: a combo's
 * end, an idle, a kill or the next enemy never resets it; it lives in
 * the shim's .data in SHIMS, zero only at boot, so it carries across
 * level loads too).  Every other call is anim_change's own.
 *
 * The ring (`g_ring`, in .data) is filled by the build (the Python side
 * writes it where the shim landed): a count, the next entry, the rotate
 * mask, whether the entries carry their own numbers, and one struct per
 * entry: its column, and (Step 2.69, the attack balance, D223/D228) the
 * Rate its clip plays at and the Damage multiplier its clip deals in
 * each column (garret4's for that column x the balance of that clip in
 * that column's move x the damage slider, so a swing stays within the
 * balance's 0.5-4.0 of garret4's for the column swinging).  When the
 * ring carries them, the swing takes its entry's: the shim writes the
 * multiplier for the swinging column into the PlayerControl
 * (critter+0x180) at +0xEC, the attack row's Damage multiplier, which
 * each tick copies to critter+0x224 for the damage pass, and the Rate at
 * +0x104, which player_attack_enter reads right after this call
 * (0x889BB) into the layer's rate; the row was copied to +0xDC before
 * the call, so nothing overwrites them until the next attack.
 * Otherwise the move keeps its column's, as before.  In a column of the
 * ring's `chained` mask (own body's basic1-3, Step 2.104, AZ-523: their
 * next move needs a stunned target; and a column some entry of which
 * would chain before it touches its target, Step 2.106, AZ-495), with
 * the balance or without it, the
 * shim also writes the entry's chain point, W19's for its clip at the
 * Rate the swing plays at (+0x104, the entry's or the column's): its
 * first damage tick plus 0.2 s at that Rate, as fractions of the clip
 * (`hit` + `after` x the Rate), never past the row's Move end2 fraction
 * (+0x100), into +0xFC, the row's Move end1 fraction, which the chain
 * check 0x8D452 reads each tick: one column's fraction fits one clip,
 * and the entries' clips differ.
 *
 * ABI: anim_change is __stdcall(12) (the critter, the anim index, the
 * flags; RET 0xC) with no register input, and player_attack_enter reads
 * none of EAX, ECX and EDX after it (0x889AB on).  The shim is
 * __stdcall(12) too and keeps EBX, ESI, EDI and EBP.
 */

#include "azurik_vanilla.h"

#define CR_SPECIES   0x178   /* critter -> its species                    */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define SP_SLOTS     0x124   /* species: a clip handle per anim index      */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl (the player's) */
#define PC_MULTIPLY  0x0EC   /* PlayerControl: the attack row's Damage multiplier */
#define PC_CHAIN     0x0FC   /* PlayerControl: the attack row's Move end1 fraction */
#define PC_END2      0x100   /* PlayerControl: the attack row's Move end2 fraction */
#define PC_RATE      0x104   /* PlayerControl: the attack row's Rate       */
#define ATTACK_ANIMS 0x52    /* attacks_anims column 0's anim index       */
#define COLUMNS      24

typedef struct RingEntry {
    int column;              /* +0 the column whose slot holds its clip    */
    float rate;              /* +4 its Rate (when `carry`)                 */
    float hit;               /* +8 its first damage tick, a fraction of its clip (in a `chained` column) */
    float after;             /* +0xC 0.2 s at Rate 1, a fraction of its clip (0: the column's chain point) */
    float multiplier[COLUMNS]; /* +0x10 its Damage multiplier in each column (when `carry`) */
} RingEntry;

typedef struct Ring {
    int count;               /* +0x00 entries in use                       */
    int next;                /* +0x04 the entry the next swing takes       */
    unsigned rotate;         /* +0x08 the columns whose swings rotate      */
    unsigned carry;          /* +0x0C nonzero: a swing takes its entry's multiplier and Rate */
    unsigned chained;        /* +0x10 the columns whose swings take its chain point (with or without `carry`) */
    RingEntry entry[COLUMNS];/* +0x14                                      */
} Ring;

_Static_assert(sizeof(RingEntry) == 16 + 4 * COLUMNS, "the build writes 112-byte entries");
_Static_assert(sizeof(Ring) == 0x14 + sizeof(RingEntry) * COLUMNS, "the build writes the ring at this size");

__attribute__((section(".data"), used))
static Ring g_ring = {0};

__attribute__((stdcall))
void c_player_model_attack(char *critter, int index, int flags)
{
    char *species = *(char **)(critter + CR_SPECIES);
    char *control;
    unsigned column = (unsigned)(index - ATTACK_ANIMS);
    int *slots, kept, at;

    if (!species || !(*(unsigned *)(species + SP_FLAGS) & PLAYER_FLAG) || column >= COLUMNS
            || !((g_ring.rotate >> column) & 1) || g_ring.count <= 0) {
        anim_change(critter, index, flags);
        return;
    }
    at = g_ring.next >= 0 && g_ring.next < g_ring.count ? g_ring.next : 0;
    g_ring.next = at + 1 < g_ring.count ? at + 1 : 0;
    slots = (int *)(species + SP_SLOTS);
    kept = slots[index];
    slots[index] = slots[ATTACK_ANIMS + g_ring.entry[at].column];
    control = *(char **)(critter + CR_CONTROL);
    if (control && g_ring.carry) {
        *(float *)(control + PC_MULTIPLY) = g_ring.entry[at].multiplier[column];
        *(float *)(control + PC_RATE) = g_ring.entry[at].rate;
    }
    if (control && ((g_ring.chained >> column) & 1) && g_ring.entry[at].after > 0.0f) {
        float chain = g_ring.entry[at].hit + g_ring.entry[at].after * *(float *)(control + PC_RATE);
        float end = *(float *)(control + PC_END2);
        *(float *)(control + PC_CHAIN) = chain < end ? chain : end;
    }
    anim_change(critter, index, flags);
    slots[index] = kept;
}
