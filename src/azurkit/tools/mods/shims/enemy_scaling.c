/* enemy_scaling's shim (Step 2.205, D817): the damage a hit costs the
 * player by who deals it, how fast a boss swings and (Step 2.205c,
 * AZ-788) how far an enemy reaches at its size.  Modkit's docs/RE_DATA.md
 * § "What scales an enemy" has the reads below; the pack's __init__.py
 * installs a landing only for a slider off 1.0.
 *
 * Bosses are the critters whose species name the build lists in
 * enemy_scaling_bosses (the pack's BOSSES: NUL-separated, an empty name
 * ends it); a critter's species is its +0x178, whose +0 is its
 * critters_engine name (the species load, 0x496E1).  The other enemies,
 * the ones the enemy sliders scale, are listed the same way in
 * enemy_scaling_enemies (the pack's ENEMIES).
 *
 * Five landings of this object, each with its own copy of the params:
 *
 * - c_enemy_scaling_damage, the player hit handler's (0x8D600) CALL of
 *   the player's damage 0x83FE0 (armor_mgr, the hit's damage record;
 *   stdcall, RET 8) at 0x8D648 (Europe 0x8D5F8), EBX the hit message
 *   (+4 its source), ESI the PlayerControl (+0x20 the player critter).
 *   The source's critter (its vtable +0x74, as the game asks at 0x4327E:
 *   a critter's 0x11D20 returns itself, a platform's 0x606A0 0) picks
 *   the factor: a boss's enemy_scaling_boss_damage, any other critter's
 *   but the player's enemy_scaling_enemy_damage; a hit with no critter
 *   (a damage platform: a field, a beam, a break, a trap) takes the
 *   factor its record's name has in enemy_scaling_records ('B' boss, 'E'
 *   enemy, else 1).  Off 1, the player's species' int slot for the
 *   record (CritterData+0x8C, the slot 0x83FE0 reads at 0x84050: the
 *   record's index in the array at enemy_scaling_calls[1], 0x20 bytes
 *   each) holds trunc(k x itself) for the call and is put back after, so
 *   the hit costs k times its base before the armor takes its share, as
 *   a config.xbr cell of k x base would; a record outside the array (no
 *   slot: 0x83FE0 reads the int before the table) has 0x83FE0's result
 *   scaled instead.
 * - c_enemy_scaling_clip, over anim_change's (0x42910) `mov edx, [esp +
 *   0x18]; mov ecx, [esp + 0x1C]` at 0x429F7 (the same VA in Europe),
 *   past its play (CALL anim_play_clip 0xCAD40 at 0x429DA, kept vanilla:
 *   the player-model swap's X12 times a slot by that CALL's return,
 *   0x429DF) and the fraction's restore; it does the two loads (the
 *   critter and the anim index, 0x1C and 0x20 bytes above the return).
 *   A boss's attack clip (an anim index in 0x2B-0x31, attack to
 *   attack_6, or a species slot from 0x52 on, where the bosses' own
 *   attack tables point) that played (its species' slot,
 *   species+0x124[index], isn't -1, as 0x42980 reads it) plays at
 *   enemy_scaling_boss_attack times the rate the change gave it (1.0).
 * - c_enemy_scaling_rate, a JMP over the first 9 bytes of the layer-rate
 *   setter 0x30940 (EAX the AI, the rate pushed; RET 4), which it does
 *   in full: the active layer's rate := the rate, times
 *   enemy_scaling_boss_attack for a boss whose last anim_change index
 *   (critter+0x200) is an attack clip's, so the walking AI's attack
 *   state (0x39E47) and Balthazar's and spideyzar's tables (0x2776C,
 *   0x2BCA3-0x2C5FE) scale as the guardians' plain changes do.
 * - c_enemy_scaling_speed, over spideyzar's `fld dword ptr [esi +
 *   0x180]` at 0x2C7E2 (the same VA in Europe; his message handler
 *   0x2C790, after its anim_change to slot 0x59): the rate his speed
 *   (AI+0x180) gives that clip, stored into the active layer at 0x2C7EB
 *   past 0x30940, times enemy_scaling_boss_attack as the setter's would
 *   be; EAX and EDX, live there, kept.
 * - c_enemy_scaling_reach, a JMP over the first 9 bytes of the attack
 *   range 0x256B0 (EAX the AI; the range in ST0, plain RET), which it
 *   does in full: vanilla's max(scale, 1) x attackRange (critter+0x188,
 *   species+0xC4) with the 1 the size slider that scaled the critter (a
 *   boss's enemy_scaling_boss_size, another enemy's
 *   enemy_scaling_enemy_size, 1 for any other critter), so below 1 an
 *   enemy reaches k times its vanilla range as it does above 1 (D816)
 *   and a small one (catalisk_baby's 0.5) above 1 too; its callers, the
 *   walking AI's attack checks and chase (0x393D9, 0x39B61, 0x39C51) and
 *   the air guardian's (0x26182), read only ST0 after it; EDX, which
 *   vanilla leaves, kept.
 *
 * The C helpers are cdecl and keep EBX, ESI, EDI and EBP; float maths is
 * SSE1 or x87, never SSE2 (AZ-021); the x87 stack is empty at the five
 * sites.  0x8D64D reads only EAX, 0x429FF EDX and ECX (the clip landing
 * sets them as the two loads it replaces) and no flag, 0x30940's callers
 * nothing it leaves in EAX, ECX or EDX, and 0x2C7E8 EDX and EAX (ECX is
 * written at 0x2C800 before any read) and no flag.
 *
 * Ported from Modkit's azurik_mod/patches/enemy_scaling/shim.c at the packs oracle's tag; shimkit builds
 * it into enemy_scaling.o beside it.
 */

#include "azurik_vanilla.h"   /* the param macros */

#define CR_SPECIES   0x178   /* critter -> its species                   */
#define CR_ANIM      0x17C   /* critter -> its anim object, or NULL      */
#define CR_SCALE     0x188   /* critter: its scale (critters_engine scale) */
#define CR_INDEX     0x200   /* critter: anim_change's last anim index   */
#define SP_SLOTS     0x124   /* species: its clip slot per anim index, -1 none */
#define SP_FLAGS     0x064   /* species: its kind flags                  */
#define SP_PLAYER    0x20    /* the `player` flag                        */
#define SP_TABLE     0x08C   /* species -> its int32 damage slot per record */
#define SP_RANGE     0x0C4   /* species: its attackRange                 */
#define PC_CRITTER   0x020   /* PlayerControl -> the player critter      */
#define AR_OWNER     0x004   /* armor_mgr -> its owner, 0x150 into the critter */
#define OWNER_AT     0x150
#define AI_CRITTER   0x020   /* AI -> its critter                        */
#define AI_SPEED     0x180   /* spideyzar's AI: the rate his clips play at */
#define AN_ACTIVE    0x010   /* anim: the active layer's index           */
#define AN_RATES     0x060   /* anim: layer 0's rate; 0x40 bytes a layer */
#define VT_CRITTER   0x074   /* an entity's vtable: its critter          */
#define RECORD_SIZE  0x20
#define FIRST_ATTACK 0x2B    /* attack                                   */
#define LAST_ATTACK  0x31    /* attack_6                                 */
#define FIRST_EXTRA  0x52    /* past the base clip table (0x1A9F78)      */
#define LAST_SLOT    0xFF

AZURIK_FLOAT_PARAM(enemy_scaling_enemy_damage, 1.0f);
AZURIK_FLOAT_PARAM(enemy_scaling_boss_damage, 1.0f);
AZURIK_FLOAT_PARAM(enemy_scaling_boss_attack, 1.0f);
AZURIK_FLOAT_PARAM(enemy_scaling_enemy_size, 1.0f);
AZURIK_FLOAT_PARAM(enemy_scaling_boss_size, 1.0f);
AZURIK_BYTES_PARAM(enemy_scaling_bosses, 256);   /* names, NUL-separated, "" ends */
AZURIK_BYTES_PARAM(enemy_scaling_enemies, 640);  /* the other enemies' names, the same way */
AZURIK_BYTES_PARAM(enemy_scaling_records, 128);  /* a class byte and a name, NUL-ended; class 0 ends */
AZURIK_BYTES_PARAM(enemy_scaling_calls, 8);      /* 0x83FE0, the record array (0x38C364): the release's VAs,
                                                    read through volatile so they aren't folded to 0 */

typedef const char *(__attribute__((thiscall)) *critter_of_fn)(const char *self);
typedef int (__attribute__((stdcall)) *damage_fn)(void *armor, const char *record);

static int same(const char *a, const volatile unsigned char *b)
{
    while (*a && *a == (char)*b) {
        a++;
        b++;
    }
    return *a == (char)*b;
}

/* The name a list entry at p holds, and where the next starts. */
static const volatile unsigned char *next_name(const volatile unsigned char *p)
{
    while (*p)
        p++;
    return p + 1;
}

/* Whether critter's species name is in the list of size bytes at list. */
static int listed(const char *critter, const volatile unsigned char *list, unsigned size)
{
    const char *species = *(const char *const *)(critter + CR_SPECIES);
    const char *name;
    const volatile unsigned char *p = list;

    if (!species || !(name = *(const char *const *)species))
        return 0;
    for (; *p && p < list + size; p = next_name(p))
        if (same(name, p))
            return 1;
    return 0;
}

static int is_boss(const char *critter)
{
    return listed(critter, enemy_scaling_bosses, sizeof enemy_scaling_bosses);
}

static int attack_clip(const char *critter, int index)
{
    return ((index >= FIRST_ATTACK && index <= LAST_ATTACK) || (index >= FIRST_EXTRA && index <= LAST_SLOT))
        && is_boss(critter);
}

/* The factor a platform's hit (no critter) takes: its record's class. */
static float record_scale(const char *record)
{
    const char *name = record ? *(const char *const *)record : 0;
    const volatile unsigned char *p = enemy_scaling_records;

    if (!name)
        return 1.0f;
    for (; *p && p < enemy_scaling_records + sizeof enemy_scaling_records; p = next_name(p + 1))
        if (same(name, p + 1))
            return *p == 'B' ? enemy_scaling_boss_damage : enemy_scaling_enemy_damage;
    return 1.0f;
}

static float hit_scale(const char *record, const char *pc, const char *const *msg)
{
    const char *from = msg[1], *attacker = 0, *species;

    if (from)
        attacker = (*(const critter_of_fn *)(*(const char *const *)from + VT_CRITTER))(from);
    if (!attacker)
        return record_scale(record);
    species = *(const char *const *)(attacker + CR_SPECIES);
    if (attacker == *(const char *const *)(pc + PC_CRITTER)
            || (species && (*(const unsigned char *)(species + SP_FLAGS) & SP_PLAYER)))
        return 1.0f;
    return is_boss(attacker) ? enemy_scaling_boss_damage : enemy_scaling_enemy_damage;
}

/* The player's int slot 0x83FE0 reads for record, or 0 for none. */
static int *damage_slot(const char *armor, const char *record)
{
    const char *owner = *(const char *const *)(armor + AR_OWNER), *species, *base;
    int *table;
    unsigned count;
    const char *const *records = (const char *const *)*(const volatile unsigned *)(enemy_scaling_calls + 4);

    if (!owner || !record)
        return 0;
    species = *(const char *const *)(owner - OWNER_AT + CR_SPECIES);
    table = species ? *(int *const *)(species + SP_TABLE) : 0;
    base = records[0];
    count = *(const unsigned *)(records + 1);
    if (!table || record < base || record >= base + count * RECORD_SIZE)
        return 0;
    return table + (record - base) / RECORD_SIZE;
}

__attribute__((used))
int enemy_scaling_hit(void *armor, const char *record, const char *pc, const char *const *msg)
{
    damage_fn damage = (damage_fn)*(const volatile unsigned *)enemy_scaling_calls;
    float k = hit_scale(record, pc, msg);
    int *slot, held, dealt;

    if (k == 1.0f)
        return damage(armor, record);
    slot = damage_slot((const char *)armor, record);
    if (!slot)
        return (int)(k * (float)damage(armor, record));
    held = *slot;
    *slot = (int)(k * (float)held);
    dealt = damage(armor, record);
    *slot = held;
    return dealt;
}

__attribute__((used))
void enemy_scaling_clip(const char *critter, int index)
{
    char *anim = *(char *const *)(critter + CR_ANIM);
    const char *species = *(const char *const *)(critter + CR_SPECIES);

    if (anim && attack_clip(critter, index) && *(const int *)(species + SP_SLOTS + 4 * index) != -1)
        *(float *)(anim + AN_RATES + (*(const int *)(anim + AN_ACTIVE) << 6)) *= enemy_scaling_boss_attack;
}

__attribute__((used))
void enemy_scaling_rate(const char *ai, float rate)
{
    const char *critter = *(const char *const *)(ai + AI_CRITTER);
    char *anim = *(char *const *)(critter + CR_ANIM);

    if (!anim)
        return;
    if (attack_clip(critter, *(const int *)(critter + CR_INDEX)))
        rate *= enemy_scaling_boss_attack;
    *(float *)(anim + AN_RATES + (*(const int *)(anim + AN_ACTIVE) << 6)) = rate;
}

__attribute__((used))
float enemy_scaling_speed(const char *ai)
{
    const char *critter = *(const char *const *)(ai + AI_CRITTER);
    float rate = *(const float *)(ai + AI_SPEED);

    return attack_clip(critter, *(const int *)(critter + CR_INDEX)) ? rate * enemy_scaling_boss_attack : rate;
}

/* The attack range: max(scale, k) x attackRange, k the size the pack gave
 * the critter (1 for one it didn't), so k x vanilla's max(scale, 1) x
 * attackRange; in double, as vanilla's x87 product of two floats. */
__attribute__((used))
double enemy_scaling_reach(const char *ai)
{
    const char *critter = *(const char *const *)(ai + AI_CRITTER);
    float scale = *(const float *)(critter + CR_SCALE);
    float k = is_boss(critter) ? enemy_scaling_boss_size
        : listed(critter, enemy_scaling_enemies, sizeof enemy_scaling_enemies) ? enemy_scaling_enemy_size : 1.0f;

    if (!(scale > k))   /* vanilla's FCOM: a NaN takes the floor too */
        scale = k;
    return (double)scale * (double)*(const float *)(*(const char *const *)(critter + CR_SPECIES) + SP_RANGE);
}

/* 0x8D648: CALL 0x83FE0 (armor_mgr, record), the factor applied. */
__attribute__((naked))
void c_enemy_scaling_damage(void)
{
    __asm__ volatile (
        "pushl %%ebx                 \n\t"   /* the hit message */
        "pushl %%esi                 \n\t"   /* the PlayerControl */
        "pushl 0x10(%%esp)           \n\t"   /* the record */
        "pushl 0x10(%%esp)           \n\t"   /* armor_mgr */
        "calll _enemy_scaling_hit    \n\t"
        "addl $0x10, %%esp           \n\t"
        "retl $8                     \n\t"
        : : : "memory"
    );
}

/* 0x429F7 (8 bytes): a boss's played attack clip's rate, then the two
 * loads it replaces (EDX the critter, ECX the anim index). */
__attribute__((naked))
void c_enemy_scaling_clip(void)
{
    __asm__ volatile (
        "pushl 0x20(%%esp)           \n\t"   /* anim_change's index */
        "pushl 0x20(%%esp)           \n\t"   /* anim_change's critter */
        "calll _enemy_scaling_clip   \n\t"
        "addl $8, %%esp              \n\t"
        "movl 0x1c(%%esp), %%edx     \n\t"   /* mov edx, [esp + 0x18] */
        "movl 0x20(%%esp), %%ecx     \n\t"   /* mov ecx, [esp + 0x1C] */
        "retl                        \n\t"
        : : : "memory"
    );
}

/* 0x30940 (JMP): the layer-rate setter, EAX the AI, the rate pushed. */
__attribute__((naked))
void c_enemy_scaling_rate(void)
{
    __asm__ volatile (
        "pushl 4(%%esp)              \n\t"   /* the rate */
        "pushl %%eax                 \n\t"   /* the AI */
        "calll _enemy_scaling_rate   \n\t"
        "addl $8, %%esp              \n\t"
        "retl $4                     \n\t"
        : : : "memory"
    );
}

/* 0x2C7E2 (6 bytes): spideyzar's FLD of his speed, times k for an attack
 * clip; EAX and EDX kept. */
__attribute__((naked))
void c_enemy_scaling_speed(void)
{
    __asm__ volatile (
        "pushl %%eax                 \n\t"
        "pushl %%edx                 \n\t"
        "pushl %%esi                 \n\t"   /* the AI */
        "calll _enemy_scaling_speed  \n\t"   /* ST0: the rate */
        "addl $4, %%esp              \n\t"
        "popl %%edx                  \n\t"
        "popl %%eax                  \n\t"
        "retl                        \n\t"
        : : : "memory"
    );
}

/* 0x256B0 (JMP): the attack range, EAX the AI, the range in ST0; EDX kept. */
__attribute__((naked))
void c_enemy_scaling_reach(void)
{
    __asm__ volatile (
        "pushl %%edx                 \n\t"
        "pushl %%eax                 \n\t"   /* the AI */
        "calll _enemy_scaling_reach  \n\t"   /* ST0: the range */
        "addl $4, %%esp              \n\t"
        "popl %%edx                  \n\t"
        "retl                        \n\t"
        : : : "memory"
    );
}
