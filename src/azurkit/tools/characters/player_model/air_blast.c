/* X39: a variant's air blast holds its bolt in the air and plays its blast
 * where the body lands (Step 2.153; D451, the owner: "give beamlord an air
 * attack which is him firing a bolt straight downwards that expands into
 * an aoe blast that knocks back enemies"; Step 2.153b: on the ground).
 *
 * Why.  The air attack (the jump attack's column, 13) enters state 0x102
 * from the air search (0x88FB2); a soft landing makes it 0x100 (the
 * classifier 0x85920 at 0x89982) and the clip plays on to its end.  No
 * damage box ever meets the floor (the hit sender tests objects), so a
 * blast "on impact" needs the landing: a recipe's air_blast clip holds
 * its bolt phase until its impact time, and this shim moves the clip to
 * that time on the first ground tick after a landing.  Step 2.153's
 * sitting saw a long fall reach the impact in the air (E4: the blast 17
 * ticks into a 3 m drop) and a hard landing's touchdown take the slot and
 * cut the blast short, so the bolt is now held while airborne and a hard
 * landing in the blast column lands soft.
 *
 * What.  Four landings of one object, each with float params
 * player_model_blast_columns (a 24-bit mask) and player_model_blast_impact
 * (clip s).  "The blast plays" below: the column playing (PC+0x134) is one
 * of the mask's, the critter's slot still plays it (+0x200 == 0x52 + it:
 * a hard landing's touchdown takes the slot) and the anim's top layer
 * (anim + 0x40 x ([anim+0x10] + 1), 0xCB020's own walk) has a clip (+4).
 *
 *   c_player_model_air_blast, at the attack state's chain check's CALL
 *   0xCB020 anim_layer_fraction at 0x8D44D (Europe 0x8D3FD), which runs
 *   in state 0x100 only: when the state is 0x100 and the blast plays, the
 *   layer's time (+0x18, clip seconds) := max(it, the impact); then
 *   0xCB020 with ECX as the game set it, so the chain check reads the new
 *   fraction.
 *
 *   c_player_model_air_blast_hold, at the state machine's CALL 0x89480
 *   player_airborne_tick at 0x8D39A (Europe 0x8D34A), every airborne tick
 *   of state 0x102: while the blast plays and the layer's time is short of
 *   the impact, it := min(it, the impact - HOLD_LEAD), so the bolt phase
 *   lasts until the landing; a blast already past its impact (a ground
 *   blast whose floor went, 0x100 -> 0x102 at the classifier's 0x85AF5)
 *   plays on; then 0x89480 as the game called it.
 *
 *   c_player_model_air_blast_land, at both of player_land_classify's CALLs
 *   of the hard landing 0x8B100 (0x85A7C and 0x85B65; Europe 0x85A2C and
 *   0x85B15, callee 0x8B0B0), each followed by the classifier's epilogue
 *   alone: in state 0x102 while the blast plays, the soft landing's two
 *   writes (0x85A8A-0x85A9A: PC+0x16C |= 4, PC+0x94 := 0x100), the hard
 *   landing's copy of the move result's velocity (+0xC0) into PC+0x24
 *   (0x8B140-0x8B16F: fall_damage_dispatch reads its z later in the tick,
 *   0x8C15F) and a plain RET, no touchdown clip (slot 11) and no landing
 *   sound, so the blast replaces the 13-tick recovery; else 0x8B100 as
 *   the game called it.
 *
 * Every other tick, column and body is the game's.
 *
 * ABI.  0x8D44D: ECX the anim object ([[input]+0x17C]), EBP the
 * PlayerControl, EDI the input; 0xCB020 takes ECX, returns st(0) and
 * clobbers only EAX and ECX, so the entry keeps EDX (0x8D46E's call of
 * 0x8C7D0 may read any register), EBX, ESI, EDI and EBP.  0x8D39A: EDI the
 * PlayerControl, [esp+4] the input (pushed at 0x8D397); the entry keeps
 * every register and JMPs to 0x89480 (stdcall, RET 4), which returns to
 * the game.  0x85A7C / 0x85B65: EAX the move result, ECX the
 * PlayerControl, EDX the input (0x8B100 reads all three; plain RET); the
 * entry keeps them for its JMP, and the epilogue reads EDI, EBP, EBX and
 * ESP alone.  Every C helper is cdecl (it keeps EBX, ESI, EDI and EBP);
 * x87 only (AZ-021).
 */

#include "azurik_vanilla.h"   /* the game's calls; and azurik.h: the params */

#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define PC_VELOCITY  0x024   /* its velocity (x, y, z)                    */
#define PC_STATE     0x094   /* its move state                            */
#define PC_COLUMN    0x134   /* the column playing                        */
#define PC_FLAGS     0x16C   /* the byte the soft landing sets bit 2 of   */
#define CR_ANIM      0x17C   /* critter -> its anim object, or NULL       */
#define CR_SLOT      0x200   /* critter: the anim slot anim_change took   */
#define ANIM_TOP     0x010   /* anim: the top layer's index               */
#define LAYER        0x040   /* bytes a layer; layer k at anim + 0x40(k+1) */
#define LAYER_CLIP   0x004   /* layer: its clip                           */
#define LAYER_TIME   0x018   /* layer: its time, clip seconds             */
#define MOVE_VELOCITY 0x0C0  /* the move result's velocity, 0x8B100's copy */
#define ATTACK       0x100   /* the ground attack's state                 */
#define AIR_ATTACK   0x102   /* the air attack's state                    */
#define LANDED       0x04    /* PC+0x16C's bit the soft landing sets      */
#define SLOT_ATTACK  0x52    /* an attack column's slot: 0x52 + it        */
#define COLUMNS      24
/* How far short of the impact the hold keeps the layer's time: the anim
 * step 0x43A00 advances the layer (0xCB730) after the state machine and
 * before the markers are sampled (0xCBC80), 0.1 clip s a 30 Hz tick at
 * beamlord's rate (sitting 2.153 E1: 1.2 clip s in 11 ticks), so the
 * sampled time stays at least 0.2 clip s inside the bolt phase. */
#define HOLD_LEAD    0.3f

AZURIK_FLOAT_PARAM(player_model_blast_columns, 0.0f);
AZURIK_FLOAT_PARAM(player_model_blast_impact, 0.0f);

/* The time of anim's top layer if ``pc`` is in ``state`` and the blast
 * plays (its column, its slot, a clip on the top layer), else NULL. */
static float *blast_time(const char *anim, const char *pc, int state)
{
    int column = *(const int *)(pc + PC_COLUMN);
    const char *critter = *(const char *const *)(pc + PC_CRITTER);
    char *layer;

    if (*(const int *)(pc + PC_STATE) != state || column < 0 || column >= COLUMNS
            || !(((int)player_model_blast_columns >> column) & 1)
            || !critter || *(const int *)(critter + CR_SLOT) != SLOT_ATTACK + column || !anim)
        return 0;
    layer = (char *)anim + LAYER * (*(const int *)(anim + ANIM_TOP) + 1);
    if (!*(void *const *)(layer + LAYER_CLIP))
        return 0;
    return (float *)(layer + LAYER_TIME);
}

/* The critter's anim object, or NULL. */
static const char *anim_of(const char *pc)
{
    const char *critter = *(const char *const *)(pc + PC_CRITTER);
    return critter ? *(const char *const *)(critter + CR_ANIM) : 0;
}

__attribute__((used))
void blast_land(const char *anim, const char *pc)
{
    float *time = blast_time(anim, pc, ATTACK);

    if (time && *time < player_model_blast_impact)
        *time = player_model_blast_impact;
}

__attribute__((used))
void blast_hold(const char *pc)
{
    float *time = blast_time(anim_of(pc), pc, AIR_ATTACK);
    float hold = player_model_blast_impact - HOLD_LEAD;

    if (time && *time > hold && *time < player_model_blast_impact)
        *time = hold;
}

__attribute__((used))
int blast_soft(char *pc, const char *result)
{
    unsigned *velocity = (unsigned *)(pc + PC_VELOCITY);
    const unsigned *moved = (const unsigned *)(result + MOVE_VELOCITY);

    if (!blast_time(anim_of(pc), pc, AIR_ATTACK))
        return 0;
    velocity[0] = moved[0];   /* as 0x8B100 copies it: dwords, no x87 */
    velocity[1] = moved[1];
    velocity[2] = moved[2];
    *(unsigned char *)(pc + PC_FLAGS) |= LANDED;
    *(int *)(pc + PC_STATE) = ATTACK;
    return 1;
}

/* 0x8D44D: the blast's jump on a landing, then JMP anim_layer_fraction (ECX). */
__attribute__((naked))
void c_player_model_air_blast(void)
{
    __asm__ volatile (
        "pushl %%ecx                        \n\t"   /* the anim object */
        "pushl %%edx                        \n\t"
        "pushl %%ebp                        \n\t"   /* the PlayerControl */
        "pushl %%ecx                        \n\t"
        "calll _blast_land                  \n\t"
        "addl $8, %%esp                     \n\t"
        "popl %%edx                         \n\t"
        "popl %%ecx                         \n\t"
        "jmp \"@anim_layer_fraction@4\"     \n\t"   /* st(0) the fraction, to the game's caller */
        : : : "memory"
    );
}

/* 0x8D39A: the bolt held in the air, then JMP player_airborne_tick (EDI, [esp+4]). */
__attribute__((naked))
void c_player_model_air_blast_hold(void)
{
    __asm__ volatile (
        "pushl %%eax                        \n\t"
        "pushl %%ecx                        \n\t"
        "pushl %%edx                        \n\t"
        "pushl %%edi                        \n\t"   /* the PlayerControl */
        "calll _blast_hold                  \n\t"
        "addl $4, %%esp                     \n\t"
        "popl %%edx                         \n\t"
        "popl %%ecx                         \n\t"
        "popl %%eax                         \n\t"
        "jmp \"_player_airborne_tick@4\"    \n\t"   /* RET 4 to the game's caller */
        : : : "memory"
    );
}

/* 0x85A7C, 0x85B65: the blast lands soft (a plain RET), else JMP player_hard_land (EAX, ECX, EDX). */
__attribute__((naked))
void c_player_model_air_blast_land(void)
{
    __asm__ volatile (
        "pushl %%eax                        \n\t"   /* the move result */
        "pushl %%ecx                        \n\t"   /* the PlayerControl */
        "pushl %%edx                        \n\t"   /* the input */
        "pushl %%eax                        \n\t"
        "pushl %%ecx                        \n\t"
        "calll _blast_soft                  \n\t"
        "testl %%eax, %%eax                 \n\t"
        "popl %%edx                         \n\t"   /* the two arguments (pops keep the flags) */
        "popl %%edx                         \n\t"
        "popl %%edx                         \n\t"
        "popl %%ecx                         \n\t"
        "popl %%eax                         \n\t"
        "jnz 1f                             \n\t"
        "jmp \"@player_hard_land@8\"        \n\t"   /* the game's touchdown, to the classifier's epilogue */
        "1:                                 \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}
