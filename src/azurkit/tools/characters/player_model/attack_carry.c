/* X33: a flying or hovering body, and a spin attack, attacks while
 * moving (Step 2.132; D334, D346, D351, the owner: "Floaters and spins":
 * every flying or hovering body and spin attacks attack while moving;
 * walkers keep the game's stop-and-swing); and for the same columns a
 * held button repeats, a jump cancels the swing into the air and an air
 * attack's landing ends it (Step 2.140; D377, D380, D381, D383).
 *
 * Why.  While the player attacks only the attack state's tick runs
 * (+0x94 = 0x100: 0x8D3D5 -> 0x8C7D0 player_ground_attack_tick), and for
 * a root-motion attack (+0x16C & 8, which player_attack_enter 0x88990
 * sets) it calls 0x8C630 player_attack_root_motion, which hands the
 * move code (0x85700) the clip's root motion alone, turned by
 * input+0xD0 (the critter's own orientation, re-copied each tick at
 * 0x852B6), so an attack neither moves with the stick nor turns.  The
 * stick is read every tick all the same (0x8C2A0 -> 0x854B4): input+0x124
 * its magnitude, +0x128..+0x130 its world direction, and 0x84710 the
 * walk's rate-limited facing into +0x78 (yaw) and +0x7C (its
 * quaternion), which the walk faces the body by (0x866CF).  0x8C7D0's
 * other branch (+0x16C & 8 clear: its CALL 0x307E0 at 0x8C805, after
 * which it zeroes the velocity, and 0x85700 at 0x8C835) is an aligned
 * move's glide (hoists, ladder tops, the hard landing), not the air
 * (AZ-625): an air attack is state 0x102, ticked by
 * player_airborne_tick 0x89480, which steers it with the stick.
 *
 * Presses are latched edges.  The attack state stamps a fresh A, B or
 * BLACK press's time (the clock [[PC+0xC]+0x10], f64) into PC+0xA0,
 * +0xA8, +0xB0 through 0xA30D0 (0x8D3DC-0x8D436; skipped while input+0x30
 * is set), and at Move end1's fraction its chain 0x88A80(0) starts the
 * next move for a stamp under 0.3 s old, writing it -1.0; a held button
 * stays latched (ControllerState +0x48 + button) until released, so it
 * was one press.  The jump is never read in state 0x100 (player_jump_init
 * 0x89060 isn't called there), and on landing the classifier 0x85920
 * turns an air attack's 0x102 into 0x100 (0x85A94), so its clip played
 * on, frozen, to its end.
 *
 * What.  The entries, in one object landed once per hook (each copy with
 * the same float param player_model_carry_columns, the PlayerControl's
 * +0x134 column's bit; never the roll's, 20), act for a column of the
 * mask whose own slot plays (the critter's +0x200 is 0x52 + the column:
 * not a hit reaction, 37-42, nor an aligned move):
 *
 *   c_player_model_attack_carry, at 0x8C630's CALL 0x307E0 at 0x8C728
 *   (Europe 0x8C6D8; a clear of the move query's struct at
 *   EAX+0x6C..+0x158 that clobbers ECX and EDX, keeps ESI and returns
 *   with a plain RET): calls it with EAX unchanged, then on an air
 *   attack's entry tick (the state's low byte 2: 0x88990 writes 0x102 at
 *   0x88A40 before its 0x8C630 tick) adds the current velocity
 *   (PC+0x24..+0x2C) to the desired one, so the jump's arc carries
 *   instead of the clip's root motion alone; else with the stick off
 *   centre (+0x124 above 0)
 *    - adds garret4's runSpeed (the input's CritterData +0x40, the walk's
 *      speed, D342's size scaling with it) x the magnitude along the
 *      stick's direction to the desired velocity's x and y, the clip's
 *      root motion kept (the move code's ground cap brings it to a run in
 *      2-3 ticks);
 *    - copies the walk's facing (+0x7C, 16 bytes) over +0xD0, so 0x42E40
 *      at 0x8C7AF faces the body, and its boxes, the way the walk would
 *      this tick.  (The entry tick's 0x42E40 turns by the quaternion
 *      0x88990 builds, not +0xD0, so the air entry copies none.)
 *
 *   c_player_model_attack_held, at the attack state's CALLs 0xA30D0 at
 *   0x8D3E5 (A) and 0x8D406 (B) (Europe 0x8D395, 0x8D3B6): a button held
 *   (its analog above 0, latched, so the game reads no press: AL 0) in a
 *   root-motion attack is stamped HELD_AGE (0.25 s) back, never over a
 *   newer stamp, and AL stays 0, the latch untouched: the chain 0x88A80
 *   takes a stamp under 0.3 s old, so a button still held at the chain
 *   point (this tick's, or the next tick's for a column whose Move end1
 *   is its end) starts the next move (D377), and a tap released two
 *   ticks or more before it doesn't (AZ-633: stamped now, a tap's last
 *   held tick chained a second swing, and its sound, Step 2.145).
 *
 *   c_player_model_attack_air, at the airborne state's CALL 0x88E70 at
 *   0x8D38A (Europe 0x8D33A; state 2 only): with the jump attack's
 *   column (13) in the mask, a held A or B is stamped first (HELD_AGE
 *   back, as every held stamp: read that tick), so the air
 *   attack starts again after a take-off and each time one ends in the
 *   air (D377, D380).
 *
 *   c_player_model_attack_jump, at the attack state's CALL 0x8C7D0 at
 *   0x8D46F (Europe 0x8D41F): a jump press (input+0x20 & 4) in a
 *   root-motion attack on the ground (PC+0x30, the contact the attack
 *   tick's 0x8C080 relinks each tick, 0 in the air: 0x8C121; the game's
 *   own jump tests it, 0x8D1D8) calls player_jump_init, so a swing
 *   carried off a ledge can't jump from the air; when it jumps, with
 *   column 13 in the mask the attack goes on in the air (A stamped, then
 *   player_air_attack_start: the game's air row, state 0x102), else every
 *   stamp is consumed (-1.0, the game's 0x88F53), so the next tick's own
 *   air start finds none and the jump stands; either way no 0x8C7D0 tick
 *   this frame (D383).  Anything else ticks 0x8C7D0 as before.
 *
 *   c_player_model_attack_ground_jump, at state 0's CALL
 *   player_jump_init at 0x8D15A (Europe 0x8D10A): with no ground contact
 *   (PC+0x30 0, or 0x150: the game's two forms of none, 0x8C0E5-0x8C121,
 *   as its own jump tests them at 0x8D1D8-0x8D1EA) AL 0, no jump, so the
 *   case goes on to walk_state, which classifies the air that tick; else
 *   the game's jump (D413, AZ-630).  The game leaves state 0 without a
 *   contact only on the tick a transition bypasses the classifier: the
 *   attack's end (0x8CF8C drops 0x100 to 0 and dispatches state 0 at
 *   once), which a carried swing reaches in the air when it is carried
 *   off a ledge, so a jump press on that tick jumped from mid-air.
 *
 *   c_player_model_attack_land, at the airborne tick's CALL 0x85920 at
 *   0x89982 (Europe 0x89932): an air attack (0x102) that the classifier
 *   lands (0x100: the soft landing, or the hard landing 0x8B100) becomes
 *   state 0, the walk, at once, and a held A or B is stamped (HELD_AGE
 *   back: 0.283 s old when read) so state 0's 0x88A80(1) at 0x8D13B starts
 *   the ground attack next tick (D381).
 *   Fall damage (0x8BF90, after the CALL) is the game's.
 *
 * The held entries also act for a column of the second float param,
 * player_model_held_columns, never carried: a thrown attack whose box
 * travels in the body's frame (W23's gust; Step 2.145, D414) repeats
 * while its button is held, and nothing else of X33's touches it.
 *
 * Every stamp waits while input+0x30 is set, as the game's do.
 *
 * ABI.  0x8C728: inside the shim (after 0x8C630's sub esp 0x190 and four
 * pushes, then the CALL) the velocity is [esp+0x24..0x2C], the
 * PlayerControl (0x8C630's first argument) [esp+0x1A8], the input EBX;
 * 0x8C72D-0x8C745 reload EAX, ECX, EDX and ESI, so it keeps EBX, EBP and
 * EDI and returns with a plain RET and an empty x87 stack, as 0x307E0
 * does.  0x8D3E5/0x8D406: EDX the ControllerState, ECX the button, EBP
 * the PlayerControl; the caller reads only AL after.  0x8D38A: EAX the
 * PlayerControl, [esp+4] the input; 0x88E70 pops it (RET 4).  0x8D15A:
 * EAX the input and ESI the PlayerControl, which player_jump_init reads
 * (0x8906E: mov edi, eax), so the entry tests the contact in memory and
 * jumps to it with both as they came; the caller reads only AL after
 * (0x8D15F) and loads EAX again.  0x8D46F:
 * [esp+4] the PlayerControl, EDI the input; RET 4.  0x89982: ESI and EDI
 * the PlayerControl, EBP the input, three stack args popped by the
 * callee (RET 0xC); the caller reads none of EAX, ECX and EDX after.
 * Every C helper is cdecl (it keeps EBX, ESI, EDI and EBP); x87 only
 * (AZ-021).
 */

#include "azurik_vanilla.h"   /* the game's calls; and azurik.h: AZURIK_FLOAT_PARAM */

#define PC_CLOCK      0x00C   /* PlayerControl -> the clock (+0x10: now, f64) */
#define PC_CRITTER    0x020   /* PlayerControl -> its critter            */
#define PC_VELOCITY   0x024   /* its velocity (x, y, z)                  */
#define PC_CONTACT    0x030   /* the ground contact's link; 0 in the air */
#define PC_STATE      0x094   /* its move state                          */
#define PC_STAMP_A    0x0A0   /* A's last fresh press (f64; -1.0 none)   */
#define PC_STAMP_B    0x0A8   /* B's                                     */
#define PC_ATTACK     0x134   /* the attacks_anims column playing        */
#define PC_MOVE       0x16C   /* move flags: 8 a root-motion attack      */
#define CR_SLOT       0x200   /* critter: the anim slot anim_change took */
#define CLOCK_NOW     0x010
#define IN_FLAGS      0x020   /* input: 4 the jump's press               */
#define IN_LOCKED     0x030   /* input: set, the stamps wait (0x8D3D5)   */
#define IN_DATA       0x034   /* input -> garret4's CritterData          */
#define CD_RUN        0x040   /* CritterData: runSpeed                   */
#define IN_FACING     0x07C   /* input: the walk's facing quaternion     */
#define IN_TURN       0x0D0   /* input: the attack's facing quaternion   */
#define IN_STICK      0x124   /* input: the stick's magnitude            */
#define IN_DIR        0x128   /* input: its world direction (x, y, z)    */
#define PAD_BUTTONS   0x018   /* ControllerState: the analog A, B, ...   */
#define ROOT_MOTION   0x08
#define JUMP_PRESS    0x04
#define AIR_ATTACK    0x102
#define ATTACK        0x100
#define SLOT_ATTACK   0x52    /* an attack column's slot: 0x52 + it      */
#define JUMP_COLUMN   13      /* "jump attack": the air row's column     */
#define ROLL_COLUMN   20
#define COLUMNS       24
#define CONSUMED      (-1.0)  /* a stamp the game consumed (0x88F53)     */
#define HELD_AGE      0.25    /* a held button's stamp, s before now: the chain's 0.3 s
                                 (0x1A28C0) takes it this tick and the next at 30 fps */

AZURIK_FLOAT_PARAM(player_model_carry_columns, 0.0f);
AZURIK_FLOAT_PARAM(player_model_held_columns, 0.0f);

static int in_mask(float mask, int column)
{
    return column >= 0 && column < COLUMNS && column != ROLL_COLUMN && (((int)mask >> column) & 1);
}

static int masked(int column)
{
    return in_mask(player_model_carry_columns, column);
}

/* The column playing is the carry mask's (or, ``held``, the held one's)
 * and its own slot plays. */
static int playing(const char *pc, int held)
{
    int column = *(const int *)(pc + PC_ATTACK);
    const char *critter;

    if (!masked(column) && !(held && in_mask(player_model_held_columns, column)))
        return 0;
    critter = *(const char *const *)(pc + PC_CRITTER);
    return critter && *(const int *)(critter + CR_SLOT) == SLOT_ATTACK + column;
}

static int carried(const char *pc)
{
    return playing(pc, 0);
}

/* ... in a root-motion attack (``held``: or the held mask's). */
static int attacking_as(const char *pc, int held)
{
    return (*(const unsigned char *)(pc + PC_MOVE) & ROOT_MOTION) && playing(pc, held);
}

static int attacking(const char *pc)
{
    return attacking_as(pc, 0);
}

static double clock_now(const char *pc)
{
    return *(const double *)(*(const char *const *)(pc + PC_CLOCK) + CLOCK_NOW);
}

/* A held button's stamp (A 0, B 1): HELD_AGE before now, as a fresh press
 * stamps now (0x8D3EE, 0x8D40F), never over a newer one (a real press's). */
static void stamp_button(char *pc, int button)
{
    double *stamp = (double *)(pc + PC_STAMP_A + 8 * button);
    double held = clock_now(pc) - HELD_AGE;

    if (*stamp < held)
        *stamp = held;
}

/* A held A or B stamped. */
static void stamp_held(char *pc, const char *input)
{
    const float *buttons;
    int b;

    if (*(const unsigned char *)(input + IN_LOCKED))
        return;
    buttons = (const float *)((const char *)active_controller_state() + PAD_BUTTONS);
    for (b = 0; b < 2; b++)
        if (buttons[b] > 0.0f)
            stamp_button(pc, b);
}

/* v: the desired velocity 0x8C630 hands the move code. */
__attribute__((used))
void attack_carry(float *v, const char *pc, char *input)
{
    const char *data;
    float mag, s;
    int j;

    if (!carried(pc))
        return;
    if ((*(const int *)(pc + PC_STATE) & 0xFF) == (AIR_ATTACK & 0xFF)) {
        for (j = 0; j < 3; j++)
            v[j] += ((const float *)(pc + PC_VELOCITY))[j];
        return;
    }
    mag = *(const float *)(input + IN_STICK);
    data = *(const char *const *)(input + IN_DATA);
    if (!(mag > 0.0f) || !data)
        return;
    s = *(const float *)(data + CD_RUN) * mag;
    v[0] += s * *(const float *)(input + IN_DIR);
    v[1] += s * *(const float *)(input + IN_DIR + 4);
    for (j = 0; j < 4; j++)
        ((float *)(input + IN_TURN))[j] = ((const float *)(input + IN_FACING))[j];
}

/* 0x8C728: CALL move_query_clear (EAX the struct), then the carry. */
__attribute__((naked))
void c_player_model_attack_carry(void)
{
    __asm__ volatile (
        "calll _move_query_clear             \n\t"
        "pushl %%ebx                         \n\t"   /* the input */
        "pushl 0x1ac(%%esp)                  \n\t"   /* the PlayerControl */
        "leal 0x2c(%%esp), %%eax             \n\t"   /* the velocity */
        "pushl %%eax                         \n\t"
        "calll _attack_carry                 \n\t"
        "addl $12, %%esp                     \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}

/* AL as 0xA30D0 gave it; a held A or B in a carried (or held) attack stamped. */
__attribute__((used))
int attack_held(int pressed, int button, const char *pad, char *pc)
{
    if (!pressed && (unsigned)button <= 1 && attacking_as(pc, 1)
            && ((const float *)(pad + PAD_BUTTONS))[button] > 0.0f)
        stamp_button(pc, button);
    return pressed;
}

/* 0x8D3E5, 0x8D406: CALL button_pressed_once (ECX, EDX kept), then. */
__attribute__((naked))
void c_player_model_attack_held(void)
{
    __asm__ volatile (
        "calll _button_pressed_once          \n\t"
        "pushl %%ebp                         \n\t"   /* the PlayerControl */
        "pushl %%edx                         \n\t"   /* the pad */
        "pushl %%ecx                         \n\t"   /* the button */
        "movzbl %%al, %%eax                  \n\t"
        "pushl %%eax                         \n\t"
        "calll _attack_held                  \n\t"
        "addl $16, %%esp                     \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void attack_air(char *pc, const char *input)
{
    if (masked(JUMP_COLUMN))
        stamp_held(pc, input);
}

/* 0x8D38A: the stamps, then JMP player_air_attack_start (EAX, [esp+4]). */
__attribute__((naked))
void c_player_model_attack_air(void)
{
    __asm__ volatile (
        "pushl %%eax                         \n\t"   /* the PlayerControl */
        "pushl 8(%%esp)                      \n\t"   /* the input */
        "pushl %%eax                         \n\t"
        "calll _attack_air                   \n\t"
        "addl $8, %%esp                      \n\t"
        "popl %%eax                          \n\t"
        "jmp \"_player_air_attack_start@4\"  \n\t"
        : : : "memory"
    );
}

/* 1: it jumped (no attack tick this frame); 0: the game's tick. */
__attribute__((used))
int attack_jump(char *pc, char *input)
{
    if (!(*(const unsigned char *)(input + IN_FLAGS) & JUMP_PRESS) || !attacking(pc)
            || !*(const char *const *)(pc + PC_CONTACT) || !player_jump_init_call(pc, input))
        return 0;
    if (masked(JUMP_COLUMN) && !*(const unsigned char *)(input + IN_LOCKED)) {
        *(double *)(pc + PC_STAMP_A) = clock_now(pc);
        player_air_attack_start_call(pc, input);
    } else {
        *(double *)(pc + PC_STAMP_A) = CONSUMED;
        *(double *)(pc + PC_STAMP_B) = CONSUMED;
    }
    return 1;
}

/* 0x8D46F: the jump, else JMP player_ground_attack_tick (EDI, [esp+4]). */
__attribute__((naked))
void c_player_model_attack_jump(void)
{
    __asm__ volatile (
        "pushl %%edi                         \n\t"   /* the input */
        "pushl 8(%%esp)                      \n\t"   /* the PlayerControl */
        "calll _attack_jump                  \n\t"
        "addl $8, %%esp                      \n\t"
        "testl %%eax, %%eax                  \n\t"
        "jz 1f                               \n\t"
        "retl $4                             \n\t"
        "1:                                  \n\t"
        "jmp \"_player_ground_attack_tick@4\" \n\t"
        : : : "memory"
    );
}

/* 0x8D15A: no contact (0 or 0x150), AL 0; else JMP player_jump_init. */
__attribute__((naked))
void c_player_model_attack_ground_jump(void)
{
    __asm__ volatile (
        "cmpl $0, 0x30(%%esi)                \n\t"   /* PC_CONTACT */
        "je 1f                               \n\t"
        "cmpl $0x150, 0x30(%%esi)            \n\t"
        "je 1f                               \n\t"
        "jmp _player_jump_init               \n\t"
        "1:                                  \n\t"
        "xorl %%eax, %%eax                   \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}

__attribute__((used))
int attack_land_before(const char *pc)
{
    return *(const int *)(pc + PC_STATE) == AIR_ATTACK && attacking(pc);
}

__attribute__((used))
void attack_land_after(char *pc, const char *input, int was)
{
    if (!was || *(const int *)(pc + PC_STATE) != ATTACK)
        return;
    *(int *)(pc + PC_STATE) = 0;
    stamp_held(pc, input);
}

/* 0x89982: CALL player_land_classify (ESI, its three args), then. */
__attribute__((naked))
void c_player_model_attack_land(void)
{
    __asm__ volatile (
        "pushl %%esi                         \n\t"   /* the PlayerControl */
        "calll _attack_land_before           \n\t"
        "popl %%ecx                          \n\t"
        "pushl %%eax                         \n\t"   /* was: [esp] */
        "pushl 0x10(%%esp)                   \n\t"   /* its three args again */
        "pushl 0x10(%%esp)                   \n\t"
        "pushl 0x10(%%esp)                   \n\t"
        "calll \"_player_land_classify@12\"  \n\t"   /* pops the copies */
        "pushl %%ebp                         \n\t"   /* the input */
        "pushl %%edi                         \n\t"   /* the PlayerControl */
        "calll _attack_land_after            \n\t"
        "addl $12, %%esp                     \n\t"   /* and was */
        "retl $12                            \n\t"
        : : : "memory"
    );
}
