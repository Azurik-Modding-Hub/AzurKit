/* death_realm's shim (Step 4.71a, AZ-836; D201): Spideyzar fights far
 * harder and faster until the player holds all five discs.  The pack's
 * death_realm.py lands both entries, each with its own copy of the params.
 * docs/RE_XBE.md § "Spideyzar's speed, his attacks and the damage the
 * player takes" has the reads below.
 *
 * The five discs are the gameState's own test (0x711C0's fragment case,
 * 0x712B6-0x712FA): disc d (earth, air, fire, water, life) is complete
 * when its four fragment counts, the dwords at inv + 0xAC + 0x30 d + 0xC k
 * (inv = [pd + 0xE0], pd = [scene + 0x2C], scene = [the scene pointer]),
 * are all non-zero.  It is read live at every call; a scene, player data
 * or inventory not there counts as complete, which leaves the game as it
 * is.  While a disc lacks a fragment:
 *
 * - c_death_realm_think, over his think's (0x2B9D0, vtable 0x1A08C4 slot 0;
 *   Europe 0x1A2A7C) `call 0x37950` at 0x2BBF4 (the same VA in Europe),
 *   ECX his AI: before the base think (ai_think_base, thiscall, its RET
 *   plain), which runs his state machine through vtable +0x24 that tick,
 *   his AI+0x180, the rate every clip of his plays at, := the speed slider
 *   x vanilla's own (1.0, 1.25 below 2/3 health, 1.5 below 1/3: the
 *   think's block 0x2BAD5-0x2BB37, which only raises it, so it leaves a
 *   value past 1.5 as it is); his AI+0x178, the wait before his next
 *   attack (the think takes dt off it), := at most the wait slider; and
 *   his species' walkSpeed and runSpeed (species +0x38, +0x40) := the
 *   movement slider x the values the first call found there, as loaded.
 *   Once the discs are complete, a call after one that scaled puts those
 *   back and his rate to vanilla's for his health now.  The x87 stack is
 *   empty there, and EBX, ESI and EDI are the think's, kept by the cdecl
 *   helper.
 * - c_death_realm_hit, over the player hit handler's (0x8D600) `lea ecx,
 *   [esp + 0xC]; push ecx` at 0x8D657 (Europe 0x8D607), past the damage's
 *   call (0x8D648, enemy_scaling's hook) and its zero test: EDI is the
 *   integer damage the rest of the hit reads (0x8D665, 0x8D6AB), EBX the
 *   hit message (+4 its source); EAX and EDX are
 *   written before any read (0x8D660, 0x8D65C) and no flag is read.  A hit
 *   whose source's critter (its vtable +0x74, as enemy_scaling reads it;
 *   none for a damage platform) is a spideyzar costs trunc(k x the damage),
 *   past an int32's ends its end; the landing then does the two
 *   instructions it replaces, as at vanilla's ESP, and returns to 0x8D65C
 *   (EAX, which it leaves holding that return, is dead there).
 *
 * Float maths is SSE1 or x87, never SSE2 (AZ-021).
 */

#include "azurik_vanilla.h"   /* ai_think_base, the param macros */

#define SCENE_PD     0x02C   /* scene -> the player data              */
#define PD_INV       0x0E0   /* player data -> the inventory          */
#define INV_FRAG     0x0AC   /* inventory: disc 0's fragment 1's count */
#define DISC_SIZE    0x030
#define FRAG_SIZE    0x00C
#define DISCS        5
#define FRAGMENTS    4
#define AI_CRITTER   0x020   /* AI -> its critter                     */
#define AI_WAIT      0x178   /* spideyzar's AI: seconds to his next attack */
#define AI_SPEED     0x180   /* spideyzar's AI: the rate his clips play at */
#define CR_SPECIES   0x178   /* critter -> its species, +0 its name   */
#define CR_HP        0x210   /* critter: its health (int)             */
#define CR_HP_MAX    0x214   /* critter: its full health (int)        */
#define SP_WALK      0x038   /* species: walkSpeed                    */
#define SP_RUN       0x040   /* species: runSpeed                     */
#define VT_CRITTER   0x074   /* an entity's vtable: its critter       */

AZURIK_FLOAT_PARAM(death_realm_damage, 1.0f);
AZURIK_FLOAT_PARAM(death_realm_speed, 1.0f);
AZURIK_FLOAT_PARAM(death_realm_wait, 15.0f);
AZURIK_FLOAT_PARAM(death_realm_move, 1.0f);
AZURIK_BYTES_PARAM(death_realm_game, 24);   /* the scene pointer's VA; vanilla's 1.0, 1.25, 1.5, 1/3 and 2/3 as
                                               floats: the release's own, read through volatile */

typedef const char *(__attribute__((thiscall)) *critter_of_fn)(const char *self);

static float held_speeds[2];   /* the species' walkSpeed and runSpeed as the first call found them */
static int held, scaled;

static float game_float(int k)
{
    union { unsigned bits; float value; } word;

    word.bits = *(const volatile unsigned *)(death_realm_game + 4 + 4 * k);
    return word.value;
}

static int discs_complete(void)
{
    const char *scene = *(const char *const *)*(const volatile unsigned *)death_realm_game;
    const char *pd, *inv;
    int d, k;

    if (!scene || !(pd = *(const char *const *)(scene + SCENE_PD)) || !(inv = *(const char *const *)(pd + PD_INV)))
        return 1;
    for (d = 0; d < DISCS; d++)
        for (k = 0; k < FRAGMENTS; k++)
            if (!*(const int *)(inv + INV_FRAG + DISC_SIZE * d + FRAG_SIZE * k))
                return 0;
    return 1;
}

/* Vanilla's rate for his health: its 1.5 under its 1/3, its 1.25 under its 2/3, else its 1.0 (0x2BAD5's FCOMs
 * of the ints' quotient, a double's here; no full health: 1.0). */
static float vanilla_speed(const char *critter)
{
    int max = *(const int *)(critter + CR_HP_MAX);
    double ratio = max ? (double)*(const int *)(critter + CR_HP) / (double)max : 1.0;

    if (ratio < (double)game_float(3))
        return game_float(2);
    return ratio < (double)game_float(4) ? game_float(1) : game_float(0);
}

static int same(const char *a, const char *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a == *b;
}

__attribute__((used))
void death_realm_think(char *ai)
{
    char *critter = *(char *const *)(ai + AI_CRITTER);
    char *species = critter ? *(char *const *)(critter + CR_SPECIES) : 0;

    if (!species)
        return;
    if (!held) {
        held_speeds[0] = *(const float *)(species + SP_WALK);
        held_speeds[1] = *(const float *)(species + SP_RUN);
        held = 1;
    }
    if (discs_complete()) {
        if (scaled) {
            *(float *)(species + SP_WALK) = held_speeds[0];
            *(float *)(species + SP_RUN) = held_speeds[1];
            *(float *)(ai + AI_SPEED) = vanilla_speed(critter);
            scaled = 0;
        }
        return;
    }
    *(float *)(ai + AI_SPEED) = death_realm_speed * vanilla_speed(critter);
    if (*(const float *)(ai + AI_WAIT) > death_realm_wait)
        *(float *)(ai + AI_WAIT) = death_realm_wait;
    *(float *)(species + SP_WALK) = death_realm_move * held_speeds[0];
    *(float *)(species + SP_RUN) = death_realm_move * held_speeds[1];
    scaled = 1;
}

__attribute__((used))
int death_realm_hit(int damage, const char *const *msg)
{
    const char *from = msg[1], *attacker, *species, *name;
    float dealt;

    if (!from)
        return damage;
    attacker = (*(const critter_of_fn *)(*(const char *const *)from + VT_CRITTER))(from);
    if (!attacker || !(species = *(const char *const *)(attacker + CR_SPECIES))
            || !(name = *(const char *const *)species) || !same(name, "spideyzar") || discs_complete())
        return damage;
    dealt = death_realm_damage * (float)damage;
    if (dealt >= 2147483648.0f)   /* past an int32: its end */
        return 0x7FFFFFFF;
    return dealt <= -2147483648.0f ? (int)0x80000000 : (int)dealt;
}

/* 0x2BBF4: CALL 0x37950 (thiscall, ECX the AI): the writes, then the base think, which returns to 0x2BBF9. */
__attribute__((naked))
void c_death_realm_think(void)
{
    __asm__ volatile (
        "pushl %%ecx                 \n\t"   /* kept for the base think */
        "pushl %%ecx                 \n\t"   /* the AI */
        "calll _death_realm_think    \n\t"
        "addl $4, %%esp              \n\t"
        "popl %%ecx                  \n\t"
        "jmp _ai_think_base          \n\t"
        : : : "memory"
    );
}

/* 0x8D657: EDI := the hit's cost, then `lea ecx, [esp + 0xC]; push ecx` as vanilla's ESP has them (4 above
 * this landing's): ECX's value goes where the return was, the return above it, and RET takes it to 0x8D65C. */
__attribute__((naked))
void c_death_realm_hit(void)
{
    __asm__ volatile (
        "pushl %%ebx                 \n\t"   /* the hit message */
        "pushl %%edi                 \n\t"   /* the damage */
        "calll _death_realm_hit      \n\t"
        "addl $8, %%esp              \n\t"
        "movl %%eax, %%edi           \n\t"
        "movl (%%esp), %%eax         \n\t"   /* the return, 0x8D65C */
        "leal 0x10(%%esp), %%ecx     \n\t"   /* lea ecx, [esp + 0xC] */
        "movl %%ecx, (%%esp)         \n\t"   /* push ecx */
        "pushl %%eax                 \n\t"
        "retl                        \n\t"
        : : : "memory"
    );
}
