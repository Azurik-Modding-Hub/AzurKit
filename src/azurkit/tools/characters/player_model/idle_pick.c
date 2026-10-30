/* X45: a variant's idles: its base between fidgets for a drawn wait, and
 * never the same fidget twice in a row (Step 2.168; D553, D331: "the
 * idle animations should not be spammed").
 *
 * Why.  The walk state's standing picker 0x85C60 (Europe 0x85C10) adds
 * dt to a standing timer (USA 0x38DC50, Europe 0x38FBF8) while slot 1
 * plays; past 10.0 s ([0x1A25B4], a constant other code reads too) and
 * once 0x308F0 says the clip has ended it calls the fidget pick 0x309A0
 * (EAX 1: one of the filled slots from 1 up, uniformly, no memory).  A
 * fidget (slots 2-7) seeds the timer U(0, 6) on every tick it plays,
 * walking U(0, 3).  So with five fidgets in slots 3-7 a fidget came every
 * 4-10 s and one in five repeated the last (DESIGN.txt A4's simulation),
 * and no table of slots can do better: the pick has no memory and the
 * threshold is shared.
 *
 * What.  This shim replaces the picker's one CALL of 0x309A0 at 0x85CD7
 * (Europe 0x85C87; 0x309A0 has ten other callers, NPCs among them).
 * Until the timer reaches a wait drawn from [lo, hi] it returns 1: the
 * base plays on and the game asks again on its next tick.  Then it
 * returns a fidget, one of the mask's slots (2-7) the species fills (its
 * slot -1 skipped) other than the last one it returned (that one only
 * when it is the only one), draws the next wait and remembers the slot.
 * The draws are a xorshift32 that mixes in the timer's bits, which the
 * game's own generator seeded.  The build writes the table: the mask, lo
 * and hi (f32) and the timer's address, read from the image's own
 * `fadd dword ptr [timer]` at 0x85CAA (Europe 0x85C5A), so one object
 * serves both releases.  A wait under 10 s acts as 10: the game's check
 * comes first.  Installed only for a recipe whose `idles` names a fidget.
 *
 * ABI at the CALL (0x309A0's): ECX the PlayerControl (+0x20 the critter,
 * whose +0x178 is its species, slots at +0x124 + 4 x index), EAX 1, one
 * dword pushed, popped by the callee (RET 4), the slot back in EAX; the
 * caller reads only EAX after it (0x85CDC: pop esi, ret).  The x87 stack
 * is empty there (0x85CB6's fcomp popped it).  The shim keeps EBX, ESI,
 * EDI and EBP, leaves the x87 stack empty and returns with RET 4.
 */

#include "azurik.h"   /* AZURIK_BYTES_PARAM */

#define PC_CRITTER   0x20    /* PlayerControl -> its critter               */
#define CR_SPECIES   0x178   /* critter -> its species (0x309A0's read)    */
#define SP_SLOTS     0x124   /* species -> its clip slots, 4 bytes each   */
#define FIRST        2       /* the fidget slots: 2-7                      */
#define LAST         7

/* Written by the build (_player_slots.idle_table): u32 mask (bit k: slot
 * k is a fidget), f32 lo, f32 hi, u32 the timer's address. */
AZURIK_BYTES_PARAM(player_model_idle_pick, 16);

/* The state the sitting reads (.bss): the wait drawn, whether it is,
 * the last fidget returned and the generator's word. */
__attribute__((used)) float player_model_idle_wait;
__attribute__((used)) int player_model_idle_drawn;
__attribute__((used)) int player_model_idle_last;
__attribute__((used)) unsigned player_model_idle_seed;

static unsigned word(int at)
{
    const volatile unsigned char *p = player_model_idle_pick + at;

    return p[0] | p[1] << 8 | p[2] << 16 | (unsigned)p[3] << 24;
}

static float real(int at)
{
    union { unsigned u; float f; } v;

    v.u = word(at);
    return v.f;
}

/* The next draw, the timer's bits mixed in. */
static unsigned next(unsigned bits)
{
    unsigned x = player_model_idle_seed ^ bits;

    if (!x)
        x = 0x9E3779B9u;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    player_model_idle_seed = x;
    return x;
}

static void draw(unsigned bits)
{
    float lo = real(4), hi = real(8);

    player_model_idle_wait = lo + (hi - lo) * (float)(next(bits) >> 8) * (1.0f / 16777216.0f);
    player_model_idle_drawn = 1;
}

/* The slot the standing player plays next: 1 (the base) or a fidget. */
__attribute__((used))
int idle_pick(const char *control)
{
    union { float f; unsigned u; } now;
    const char *critter, *species;
    unsigned mask = word(0);
    const float *timer = (const float *)word(12);
    int slots[LAST - FIRST + 1], n = 0, k;

    if (!timer)
        return 1;
    now.f = *timer;
    if (!player_model_idle_drawn)
        draw(now.u);
    if (!(now.f >= player_model_idle_wait))
        return 1;
    critter = *(const char *const *)(control + PC_CRITTER);
    species = critter ? *(const char *const *)(critter + CR_SPECIES) : 0;
    if (!species)
        return 1;
    for (k = FIRST; k <= LAST; k++)
        if (mask >> k & 1 && *(const int *)(species + SP_SLOTS + 4 * k) != -1 && k != player_model_idle_last)
            slots[n++] = k;
    if (!n) {
        k = player_model_idle_last;
        if (k < FIRST || k > LAST || !(mask >> k & 1) || *(const int *)(species + SP_SLOTS + 4 * k) == -1)
            return 1;
        slots[n++] = k;
    }
    k = slots[next(now.u) % (unsigned)n];
    player_model_idle_last = k;
    draw(now.u);
    return k;
}

/* 0x85CD7: CALL 0x309A0, the standing picker's fidget pick. */
__attribute__((naked))
void c_player_model_idle_pick(void)
{
    __asm__ volatile (
        "pushl %%ecx                         \n\t"   /* the PlayerControl */
        "calll _idle_pick                    \n\t"
        "addl $4, %%esp                      \n\t"
        "retl $4                             \n\t"   /* the pushed 0, as 0x309A0 pops it */
        : : : "memory"
    );
}
