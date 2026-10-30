/* X20: on the zipline ride the camera aims no lower than a larger-drawn
 * body's centre (Step 2.105, AZ-520's ride; D115's default: the point
 * raised to the centre exactly, on hang_start, the ride and X22's ease
 * off it only; hang_start since Step 2.107).
 *
 * Why.  X9's ride hangs a body drawn X times its size X times garret4's
 * hang m_grab (3.693 m) under the cable, so its camera point (the
 * origin plus X x the point's height: X8's, or a body's own m_head)
 * sits 1.43-1.62 m under the body's centre at x2 (town_male_6 own,
 * kingkong at garret4's height, Balthazar own), where the control's
 * sits 0.06-0.71 m over it.  The level camera 0x81240 aims from that
 * point: its line-of-sight test 0x80C10 (from the camera to the point)
 * hit on every ride tick from tick 10-18, its slide 0x80C40 failed at
 * tick 28-29, and 0x80FB0 then put the camera 0.26-0.44 m from the
 * point for the rest of the ride (sitting 2.104), where the control's
 * keeps 5.0 m with no hit.  The low point and the camera's lowered
 * place graze sloping faces of f3's start platform the centre's line
 * clears [inferred: f3's static collision offline], and X19's second
 * sweep, which runs only inside 0x80FB0, can't help: the slide and the
 * line-of-sight test have used the low point already.
 *
 * What.  0x81240 gets the point from its target (the camera's +0x190)
 * through the target's vtable +0xB0 (a critter's 0x41F40) at 0x81271
 * into its local at ESP + 0x50, and every path then reaches 0x81292
 * before anything reads it.  This shim replaces the 10 bytes there
 * (`mov edi, [esp+0x10]` the camera; `mov edx, [edi+0x154]`) with a CALL
 * and 5 NOPs.  When the target is the player (its species' `player`
 * flag 0x20) and its PlayerControl (critter +0x180) is on the zipline
 * ride (move state 5 at +0x94) or hanging onto it (hang_start, 0x105:
 * Step 2.107, so the point doesn't jump 1.1-1.4 m at x2 as hang_start
 * turns into the ride), or airborne (state 2) with its drawn
 * origin (+0x1BC) more than 1.25 m under its centre, it raises the
 * point's z to the centre's (critter +0x164) when it is lower; x and y
 * stay.  Then it does the two loads.  The airborne tick places m_feet,
 * and so the origin, 1.0 m under the centre every tick, so a lower one
 * is X22 still easing the body off the ride: on the let-go's tick and
 * the cable's end's the x2 point is still 0.5-0.8 m under the centre,
 * in state 2 [computed: sitting 2.104's ride less X22's first step].
 * Another target, every other state and a body drawn at its stance (a
 * short one's point may sit under its centre) keep the game's point.
 * The 1.25 m stays unscaled: the stance is garret4's collision, the
 * centre less 1.0 m, at every scale.  The build installs it on a body
 * drawn taller than garret4 (Step 2.107: its drawn height over his
 * above 1, any size and model scale above 0), and away from x1 on one
 * whose point rides under its centre on X9's hang (RIDE_CENTRE).
 *
 * ABI: at 0x81292 ESI holds the controller and EBX 0, both read later;
 * EAX and ECX are written (0x8129C, 0x812A2) before they are read, and
 * the x87 stack is empty.  The shim sets EDI and EDX as the replaced
 * loads do, keeps EBX, ESI and EBP, and returns with a plain RET.
 */

#include "azurik.h"

#define CA_TARGET    0x190   /* camera -> the critter it follows          */
#define CR_CENTRE    0x15C   /* critter: its body centre (x, y, z)        */
#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_CONTROL   0x180   /* critter -> its PlayerControl (the player's) */
#define SP_FLAGS     0x064   /* species: its kind flags                    */
#define PLAYER_FLAG  0x20    /* the `player` feature                      */
#define CR_ORIGIN    0x1BC   /* critter: the drawn origin at rest          */
#define PC_STATE     0x094   /* PlayerControl: its move state              */
#define AIRBORNE     2       /* player_airborne_tick's                     */
#define RIDING       5       /* the zipline ride (0x8A510)                 */
#define HANG_START   0x105   /* hanging onto the cable, before the ride    */
#define EASING       1.25f   /* m: the origin under the centre, airborne    */

/* The point (x, y, z) the camera got from its target: its z no lower
 * than the centre's while the player hangs onto or rides the zipline or
 * eases off it. */
__attribute__((used))
void eye_hang(const char *camera, float *point)
{
    const char *target, *species, *control;
    float z;
    int state;

    target = camera ? *(const char *const *)(camera + CA_TARGET) : 0;
    if (!target)
        return;
    species = *(const char *const *)(target + CR_SPECIES);
    if (!species || !(*(const unsigned *)(species + SP_FLAGS) & PLAYER_FLAG))
        return;
    control = *(const char *const *)(target + CR_CONTROL);
    if (!control)
        return;
    state = *(const int *)(control + PC_STATE);
    z = ((const float *)(target + CR_CENTRE))[2];
    if (state != RIDING && state != HANG_START && !(state == AIRBORNE
            && ((const float *)(target + CR_ORIGIN))[2] < z - EASING))
        return;
    if (point[2] < z)
        point[2] = z;
}

/* 0x81292 in 0x81240: the camera at [ESP + 0x10], the point at
 * ESP + 0x50 (the caller's ESP; +4 here for the return address). */
__attribute__((naked))
void c_player_model_eye_hang(void)
{
    __asm__ volatile (
        "leal 0x54(%%esp), %%eax  \n\t"   /* the point            */
        "pushl %%eax              \n\t"
        "pushl 0x18(%%esp)        \n\t"   /* the camera           */
        "calll _eye_hang          \n\t"
        "addl $8, %%esp           \n\t"
        "movl 0x14(%%esp), %%edi  \n\t"   /* mov edi, [esp+0x10]  */
        "movl 0x154(%%edi), %%edx \n\t"   /* mov edx, [edi+0x154] */
        "retl                     \n\t"
        : : : "memory"
    );
}
