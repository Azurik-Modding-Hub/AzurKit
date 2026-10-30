/* player_physics' speed toggle (Step 2.186; D713, the owner: "Add a
 * toggle option where the player speed patches are toggled when a button
 * is pressed, toggling them on or off"; the button "Click left stick";
 * "have a checkbox with options of which to toggle").
 *
 * A left stick click (L3) flips the sliders the build selected between
 * the build's values and vanilla's while the game runs (as it is let
 * go, so L3 + R3, photo mode's chord, flips nothing), and for 2 s the
 * HUD's top-left corner says "Speed mods on" or "Speed mods off".  The
 * mods start on at boot and after every game start (a new game, a load,
 * a continue).  L3 is free in play: retail reads it only in the free
 * camera behind the cvar 'enable cheat buttons' (0x82854) and in the
 * cheat-code walker, which reads every button (Modkit's docs/RE_XBE.md).
 *
 * The values.  The build writes each selected slider as before; the
 * table (bytes param speed_toggle_table: a count, then per 4-byte slot
 * its VA, the build's dword and vanilla's) names where its value lives:
 * gravity's .rdata float, the jump, flap and swim sliders' carved floats,
 * the hand shims' k, the air-control and fuel immediates in .text.  A
 * click writes each slot's other dword.  Those pages aren't all writable
 * (.text 0x36, .rdata 0x6: AZ-220), so the writes run with CR0.WP clear
 * and interrupts off, the way ring-0 code patches itself.  The walk is
 * garret4's runSpeed in his CritterData (+0x40), which the critter loader
 * fills from config.xbr: speed_toggle_walk holds whether the build
 * selected it and its two dwords, written there every tick.
 *
 * Three hooks, one object landed once per hook; the tick's landing owns
 * the state (the others get its address in speed_toggle_state_at):
 *
 *   c_speed_toggle_tick   the PlayerControl tick's CALL of
 *                         player_physics_state_machine (0x8CCC0) at
 *                         0x8C37D (Europe 0x8C32D): a click flips the
 *                         state when L3 is let go, then the walk, then
 *                         the state machine.  The click starts at L3's
 *                         fresh press (button_pressed_once, ECX 8, the
 *                         latch the poll clears on release) and is
 *                         dropped if R3 is held on any tick L3 is down,
 *                         or if the world stood still between two ticks
 *                         while it was (KeTickCount, more than GAP ms):
 *                         L3 + R3 is photo mode's chord and cheat code
 *                         2's, and photo mode freezes the world on the
 *                         tick the chord forms, so this tick never sees
 *                         an R3 that comes a tick after L3.
 *   c_speed_toggle_hud    the frame draw's `mov edx, [ecx]; call [edx+8]`
 *                         at 0x5545A, the HUD draw (0x1B2B0, slot +8 of
 *                         the HUD's vtable 0x1A1858) under the 'Show UI'
 *                         cvar: the call, then the note while it shows.
 *   c_speed_toggle_start  game_start_setup's first instruction (0x52F50,
 *                         `sub esp, 0x138`; its five callers: a new game,
 *                         a menu load, a continue, a 'last-save-spot'
 *                         request): the build's values back, then that
 *                         instruction.
 *
 * ABI.  0x8C37D: [esp+4] the PlayerControl, EAX the input; the stub keeps
 * EAX, ECX and EDX for 0x8CCC0 and jumps to it (its RET 4 returns to the
 * tick).  0x5545A: ECX the HUD, its slot +8 a thiscall with no argument,
 * plain RET; the frame draw reloads EAX, ECX and EDX after it.  0x52F50:
 * EAX, ECX and EDX are written before they are read; the stub pops its
 * return address, makes the frame and returns there, to the hook's NOP.  The C helpers are cdecl
 * (they keep EBX, ESI, EDI and EBP); x87 and SSE1 only (AZ-021).
 *
 * Both releases: the shim names no address of the image (vanilla calls by
 * name; the table's and the material's VAs are the build's).
 *
 * Ported from Modkit's azurik_mod/patches/player_physics/speed_toggle.c at the packs oracle's tag; shimkit builds
 * it into player_physics.o beside it.
 */

#include "azurik_vanilla.h"   /* the game's calls and the params */
#include "azurik_kernel.h"    /* KeTickCount */

#define PC_CLOCK     0x00C   /* PlayerControl -> its clock (+0x10: now, f64) */
#define CLOCK_NOW    0x010
#define IN_SPECIES   0x034   /* input: the player's CritterData              */
#define CD_RUN_SPEED 0x040   /* CritterData: runSpeed, the walk speed (f32)  */
#define L3           8       /* ControllerState +0x18 + 4 x 8: the left click */
#define SLOTS        24
#define SHOWN        2.0     /* s the note shows after a click               */
#define GAP          250u    /* ms between two ticks: the world stood still  */
#define CORNER       9       /* hud_anchor: left | top                       */
#define HUD_CORNER   5       /* left | bottom: the HUD draw's last anchor    */
#define HUD_TEXT     0.8f    /* the note's scale: X36's line's               */
#define FONT_TOP     0x008   /* font: the top (int)                          */
#define CR0_WP       0x10000u

AZURIK_BYTES_PARAM(speed_toggle_table, 4 + SLOTS * 12);
AZURIK_BYTES_PARAM(speed_toggle_walk, 12);
AZURIK_BYTES_PARAM(speed_toggle_state_at, 4);
AZURIK_BYTES_PARAM(speed_toggle_material, 4);

struct toggle_state {
    int off;         /* 1 while the selected sliders hold vanilla's values */
    int shown;       /* 1 while the note shows                            */
    double pressed;  /* the clock at the last click                       */
    int armed;       /* 1 from L3's fresh press until it is let go        */
    unsigned last;   /* KeTickCount at the click's last tick with L3 down  */
};

struct toggle_state speed_toggle_state = {0, 0, -1e300, 0, 0};

static const float on_colour[4] = {0.4f, 1.0f, 0.4f, 1.0f};
static const float off_colour[4] = {1.0f, 1.0f, 1.0f, 1.0f};   /* white: orange was lost on f6's floor */

static struct toggle_state *state(void)
{
    unsigned at = *(const volatile unsigned *)speed_toggle_state_at;

    return at ? (struct toggle_state *)at : &speed_toggle_state;
}

/* Each slot's build dword (off 0) or vanilla's (off 1), written with
 * CR0.WP clear and interrupts off. */
static void write_slots(int off)
{
    const volatile unsigned *t = (const volatile unsigned *)speed_toggle_table;
    unsigned n = t[0], i, flags, cr0;

    if (n > SLOTS)
        n = SLOTS;
    __asm__ volatile ("pushfl\n\tpopl %0\n\tcli\n\tmovl %%cr0, %1" : "=r"(flags), "=r"(cr0) : : "memory");
    __asm__ volatile ("movl %0, %%cr0" : : "r"(cr0 & ~CR0_WP) : "memory");
    for (i = 0; i < n; i++)
        *(volatile unsigned *)t[1 + 3 * i] = t[2 + 3 * i + (off ? 1 : 0)];
    __asm__ volatile ("movl %0, %%cr0\n\tpushl %1\n\tpopfl" : : "r"(cr0), "r"(flags) : "memory", "cc");
}

/* AL: a fresh L3 press on ``pad`` (its latch then taken). */
__attribute__((naked, noinline))
static unsigned char l3_pressed(void *pad)
{
    __asm__ volatile (
        "movl 4(%%esp), %%edx               \n\t"
        "movl $8, %%ecx                     \n\t"
        "jmp _button_pressed_once           \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void toggle_tick(const char *pc, const char *input)
{
    struct toggle_state *s = state();
    ControllerState *pad = active_controller_state();
    const volatile unsigned *walk = (const volatile unsigned *)speed_toggle_walk;
    double now = *(const double *)(*(const char *const *)(pc + PC_CLOCK) + CLOCK_NOW);
    unsigned ms = KeTickCount;
    double since;
    char *species;

    if (s->armed && ms - s->last > GAP)
        s->armed = 0;            /* a pause, photo mode or a load since its last tick */
    if (l3_pressed(pad))
        s->armed = 1;
    if (pad->stick_right_click > 0.0f)
        s->armed = 0;            /* L3 + R3: photo mode's, cheat code 2's */
    if (s->armed) {              /* the state changes only during a click: the image's at rest */
        if (pad->stick_left_click > 0.0f) {
            s->last = ms;
        } else {
            s->armed = 0;        /* let go: the click */
            s->off = !s->off;
            write_slots(s->off);
            s->pressed = now;
        }
    }
    if (walk[0] && (species = *(char *const *)(input + IN_SPECIES)))
        *(volatile unsigned *)(species + CD_RUN_SPEED) = walk[s->off ? 2 : 1];
    since = now - s->pressed;
    s->shown = since >= 0.0 && since < SHOWN;
}

/* 0x8C37D: the click and the walk, then player_physics_state_machine. */
__attribute__((naked))
void c_speed_toggle_tick(void)
{
    __asm__ volatile (
        "pushl %%eax                        \n\t"   /* the input, for 0x8CCC0 */
        "pushl %%ecx                        \n\t"
        "pushl %%edx                        \n\t"
        "pushl %%eax                        \n\t"   /* the input */
        "pushl 20(%%esp)                    \n\t"   /* the PlayerControl */
        "calll _toggle_tick                 \n\t"
        "addl $8, %%esp                     \n\t"
        "popl %%edx                         \n\t"
        "popl %%ecx                         \n\t"
        "popl %%eax                         \n\t"
        "jmp \"_player_physics_state_machine@4\" \n\t"
        : : : "memory"
    );
}

/* AL 0 when the 2D material (0x97420, its release's VA in the bytes param
 * speed_toggle_material, as X36's: its MOV EAX, imm32 first byte keeps it
 * out of the vanilla-symbol registry) for ``colour`` (ESI) and ``texture``
 * (EDI, the font) fails; stdcall(0, 1) as text takes it. */
__attribute__((naked, noinline))
static unsigned char hud_material(const float *colour, const void *texture)
{
    __asm__ volatile (
        "pushl %%esi                        \n\t"
        "pushl %%edi                        \n\t"
        "movl 12(%%esp), %%esi              \n\t"
        "movl 16(%%esp), %%edi              \n\t"
        "pushl $1                           \n\t"
        "pushl $0                           \n\t"
        "calll *_speed_toggle_material      \n\t"   /* RET 8 */
        "popl %%edi                         \n\t"
        "popl %%esi                         \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void toggle_hud(void)
{
    const struct toggle_state *s = state();
    const char *font;
    float scale[2] = {HUD_TEXT, HUD_TEXT};

    if (!s->shown || !(font = hud_font()))
        return;
    hud_anchor(CORNER, scale);
    if (hud_material(s->off ? off_colour : on_colour, font)) {
        float pen[9] = {2.0f, -2.0f - (float)*(const int *)(font + FONT_TOP), 0.0f,
                        0.0f, 1.0f, 0.0f, 1.0f, 0.0f, 0.0f};

        font_draw_text_call(pen, font, s->off ? "Speed mods off" : "Speed mods on");
    }
    scale[0] = scale[1] = 1.0f;
    hud_anchor(HUD_CORNER, scale);
}

/* 0x5545A: the HUD draw (ECX the HUD, its vtable's slot +8), then the note. */
__attribute__((naked))
void c_speed_toggle_hud(void)
{
    __asm__ volatile (
        "movl (%%ecx), %%edx                \n\t"
        "calll *8(%%edx)                    \n\t"
        "calll _toggle_hud                  \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void toggle_start(void)
{
    struct toggle_state *s = state();

    if (s->off)
        write_slots(0);
    s->off = 0;
    s->shown = 0;
    s->armed = 0;
    s->pressed = -1e300;
}

/* 0x52F50: the build's values back, then game_start_setup's `sub esp,
 * 0x138`, returning to 0x52F55 (the hook's NOP) below the frame it made. */
__attribute__((naked))
void c_speed_toggle_start(void)
{
    __asm__ volatile (
        "calll _toggle_start                \n\t"
        "popl %%eax                         \n\t"   /* 0x52F55 */
        "subl $0x138, %%esp                 \n\t"
        "pushl %%eax                        \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}
