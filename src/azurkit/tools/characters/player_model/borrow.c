/* X12: garret4's timing on a swapped body's stand-ins, and his clips on
 * a body with none (Step 2.67; D219, D226, D229; Step 2.89, D239).
 *
 * garret4's own clips reach a swapped body only baked onto its rig
 * (azurik_mod/assets/retarget.py: characters/<body>/g4/<clip>), since a
 * clip binds to a body by raw index (docs/RE_DATA.md "How a clip binds
 * to a body").  The clip change 0xCAD40 starts a clip on a free layer of
 * the anim object (anim+0x40 + 0x40 x n, n = anim+0x10: +4 the clip,
 * +0x20 the rate) and calls 0xCB080 (EAX = the anim) to bind its tracks.
 *
 * The build (_player_borrow.py) fills player_model_borrow below: the
 * return of anim_change's (0x42910) CALL of 0xCAD40 and the garret4
 * clip length of each base slot X11 marked garret4-timed (D229: a body
 * the bake doesn't map, a stand-in that isn't very similar).
 *
 * One source, three hooks, each landed on its own with its own copy of
 * the table:
 *
 * - c_player_model_borrow_bind, the CALL 0xCB080 at 0xCAF6B: after the
 *   bind, when anim_change made the change (0xCAD40's return is its
 *   0x429DF), for the player's species (S+0x64 flag 0x20) a base slot
 *   X11 marked garret4-timed plays at the rate that ends its clip in
 *   garret4's clip length.  anim_change's arguments, the critter and the
 *   index, sit 0x28 bytes above 0xCAD40's return.  (Not at anim_change's
 *   own CALL of 0xCAD40, 0x429DA: L2's movement probes stub anim_change,
 *   tests/facts/sim_blind_spots.toml.)
 * - c_player_model_borrow_reuse, 0xCAD40's `mov al, [esp+0x18]; test
 *   al, 4` at 0xCAEC0: when the clip is already on a playing or fading
 *   layer and the change's flag 4 is clear (anim_change's flags 2: a
 *   fall after a jump that plays the same stand-in), 0xCAD40 makes that
 *   layer active again, sets its rate to 1.0 (0xCAEA7) and returns
 *   without 0xCB080, so the bind hook never sees it; this one gives the
 *   slot its garret4-timed rate the same way.  After the FPU compare at
 *   0xCAE98 is stored (0xCAEBD), so the x87 stack is empty; it ends on
 *   the replaced test, whose ZF the JE at 0xCAEC6 reads.
 * - c_player_model_borrow_attack, the attacks_anims loader's CALL
 *   species_clip_lookup at 0x7E3F0 (EAX the name, EDI the out, the species
 *   pushed, RET 4), for a body with no clips (gargoylestone, tesla_tree),
 *   which the bake gives garret4's clips as timers: for the player's
 *   species a column the body can't resolve plays g4/<name>
 *   (characters/<body>/g4/<name>).
 *
 * The C helpers are cdecl and keep EBX, ESI, EDI and EBP; 0xCAD40 reads
 * none of EAX, ECX or EDX after 0xCB080 (0xCAF70 on) and only ECX (kept)
 * and ZF after 0xCAEC6, and 0x7E3F5 reads only EAX, the out.
 */

#include "azurik_vanilla.h"

#define N_BASE     0x52

#define CR_SPECIES   0x178   /* critter -> its species                  */
#define CR_ANIM      0x17C   /* critter -> its anim object, or NULL     */
#define SP_FLAGS     0x064   /* species: its kind flags                  */
#define PLAYER_FLAG  0x20    /* the `player` feature                    */
#define AN_ACTIVE    0x010   /* anim: the active layer's index           */
#define AN_LAYERS    0x040   /* anim: three 0x40-byte layers             */
#define LY_CLIP      0x004   /* layer: its clip ('banm')                 */
#define LY_RATE      0x020   /* layer: its rate                          */
#define CLIP_LENGTH  0x010   /* banm: its length, s                      */

/* Filled in by the build after each landing (_player_borrow.py). */
volatile const struct {
    unsigned anim_change_return;   /* anim_change's return from 0xCAD40  */
    float garret4_length[N_BASE];  /* a garret4-timed slot's length, s   */
} player_model_borrow __attribute__((used, section(".rdata"))) = {0};

#define T player_model_borrow
#define I32(p, at) (*(const int *)((const char *)(p) + (at)))

/* After a clip change anim_change (`back` its return) made: a
 * garret4-timed slot's clip, just started or played again, in garret4's
 * time (`critter`, `index`: anim_change's arguments). */
__attribute__((used))
void borrow_timing(unsigned back, const char *critter, unsigned index)
{
    const char *anim, *layer, *clip;
    float length;

    if (back != T.anim_change_return || index >= N_BASE || !(T.garret4_length[index] > 0.0f)
            || !(*(const unsigned char *)(*(const char *const *)(critter + CR_SPECIES) + SP_FLAGS)
                 & PLAYER_FLAG))
        return;
    anim = *(const char *const *)(critter + CR_ANIM);
    if (!anim)
        return;
    layer = anim + AN_LAYERS + AN_LAYERS * I32(anim, AN_ACTIVE);
    clip = *(const char *const *)(layer + LY_CLIP);
    length = clip ? *(const float *)(clip + CLIP_LENGTH) : 0.0f;
    if (length > 0.0f)
        *(float *)(layer + LY_RATE) = length / T.garret4_length[index];
}

/* g4/<name> in a buffer, or NULL for an empty name. */
static char key[64];

__attribute__((used))
const char *baked_key(const char *name)
{
    static const char prefix[] = "g4/";
    unsigned i = 0, j = 0;

    if (!name || !name[0])
        return 0;
    while (prefix[i]) {
        key[i] = prefix[i];
        i++;
    }
    while (name[j] && i < sizeof key - 1)
        key[i++] = name[j++];
    key[i] = 0;
    return key;
}

__attribute__((naked))
void c_player_model_borrow_bind(void)
{
    __asm__ volatile (
        /* [ESP + 0x10] 0xCAD40's return; from anim_change (0x429DF) its
         * arguments the critter and the index are at [ESP + 0x38] and
         * [ESP + 0x3C] (its frame at 0x429DA is 0x10 above 0xCAD40's).  */
        "calll _anim_bind_clip_tracks       \n\t"   /* EAX the anim       */
        "pushl 0x3c(%%esp)                  \n\t"   /* the index          */
        "pushl 0x3c(%%esp)                  \n\t"   /* the critter        */
        "pushl 0x18(%%esp)                  \n\t"   /* 0xCAD40's return   */
        "calll _borrow_timing               \n\t"
        "addl $12, %%esp                    \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

__attribute__((naked))
void c_player_model_borrow_reuse(void)
{
    __asm__ volatile (
        /* [ESP + 0x10] 0xCAD40's return, the critter and the index at
         * [ESP + 0x38] and [ESP + 0x3C] (as at 0xCAF6B), ECX the layer.  */
        "pushl %%ecx                        \n\t"
        "pushl 0x40(%%esp)                  \n\t"   /* the index          */
        "pushl 0x40(%%esp)                  \n\t"   /* the critter        */
        "pushl 0x1c(%%esp)                  \n\t"   /* 0xCAD40's return   */
        "calll _borrow_timing               \n\t"
        "addl $12, %%esp                    \n\t"
        "popl %%ecx                         \n\t"
        "movb 0x1c(%%esp), %%al             \n\t"   /* the change's flags */
        "testb $4, %%al                     \n\t"   /* for the JE after   */
        "retl                               \n\t"
        : : : "memory"
    );
}

__attribute__((naked))
void c_player_model_borrow_attack(void)
{
    __asm__ volatile (
        "pushl %%eax                        \n\t"   /* the name           */
        "pushl 8(%%esp)                     \n\t"   /* the species        */
        "calll \"_species_clip_lookup@4\"   \n\t"   /* EAX name, EDI out  */
        "popl %%eax                         \n\t"
        "cmpl $-1, (%%edi)                  \n\t"
        "jne 1f                             \n\t"
        "movl 4(%%esp), %%ecx               \n\t"
        "testb $0x20, 0x64(%%ecx)           \n\t"   /* the player's?      */
        "jz 1f                              \n\t"
        "pushl %%eax                        \n\t"
        "calll _baked_key                   \n\t"
        "addl $4, %%esp                     \n\t"
        "testl %%eax, %%eax                 \n\t"
        "jz 1f                              \n\t"
        "pushl 4(%%esp)                     \n\t"
        "calll \"_species_clip_lookup@4\"   \n\t"   /* its baked timer    */
        "1:                                 \n\t"
        "movl %%edi, %%eax                  \n\t"
        "retl $4                            \n\t"
        : : : "memory"
    );
}
