/* X36: WHITE cycles a swapped body's attack sets, named in the HUD's
 * top-left corner for two seconds; direction no longer picks attacks
 * (Step 2.135; D325, the owner: "cycle which attacks are used ... i dont
 * want to restrict certain attacks to having to press a specific
 * direction while attacking to use them"; D326, D352; Step 2.153, D441:
 * "can it perhaps show up as a part of the gui, maybe in the top left
 * corner in normal sized or small text?").
 *
 * Why.  A press reaches player_ground_attack_start 0x88A80, whose CALL
 * 0x7EF10 attack_transition_search at 0x88D78 (Europe 0x88D28) picks the
 * column: the first attacks_transitions row whose last move (PC+0x134,
 * read at 0x7EF29), button and target direction match.  Its direction is
 * the stick heading against the facing (or a target within 60 deg of the
 * stick), so a stick held sideways played right1/left1 (rows 21-26, which
 * need no target) and the combo's rows 28-31 (forward) never matched.
 * The search ends in attack_anim_record_copy 0x7F1F0, which writes the
 * column to PC+0x134, its 0x58-byte attacks_anims record to PC+0xDC and
 * the swing's yaw to PC+0x138 (the stick heading H, or the bearing B of
 * a target within 60 deg of it, less the column's Aim angle; H alone for
 * an empty Aim).  Every per-column feature keys on PC+0x134 or that
 * record (X3, X13, X18, X33, W5, W14, W19).  WHITE's latch is read by
 * no retail gameplay path: its one use, swimming up (0x8B700), reads its
 * analog value (the attack state reads A, B and BLACK's latches).
 *
 * What.  One object, three entries landed once per hook, the search's
 * landing owning the state (the other two get its address in the bytes
 * param player_model_sets_state_at); and four byte edits in 0x7EF10 that
 * the build makes beside them (je -> jmp at 0x7EF90 and the imm32 1 at
 * 0x7F08F, 0x7F09F, 0x7F0AE: every press takes the forward row; the 60
 * deg target gate and the yaw are kept).
 *
 *   c_player_model_attack_sets_search, at 0x88D78 (Europe 0x88D28): when
 *   the last swing was a set's (logical >= 0), PC+0x134 still holds its
 *   source column and the critter's slot still plays it (+0x200 == 0x52 +
 *   it), PC+0x134 := the combo column it stood for, so the search's last
 *   move and X21's basic1-3 test see the combo's place; then the game's
 *   search; then, in a set other than 0, for a combo column C (basic1-3,
 *   finish, finish2, finish3) the set maps to another S, 0x7F1F0 again
 *   with S and the same target: B := the yaw plus C's Aim angle (C's are 0
 *   or empty, so this is exact; empty: B 1e5, the stick heading), H the
 *   stick heading.  PC+0x134, the record and the yaw are S's; logical :=
 *   C, source := S.  A chain out of a set's fourth (the swing still
 *   playing stood for finish, finish2 or finish3) that the search answers
 *   with a finisher again plays the set's first instead, C := basic1
 *   (AZ-680): keyed on a finisher, which no chain row leaves, the first
 *   row a stunned target matches is row 32's finish2 (it names no last
 *   move), so a fourth that chains while its own hit's stun holds played
 *   itself on every press; a fresh press on a stunned target still plays
 *   the set's fourth, as the game's combo plays finish2.  The air search
 *   (0x88FB2), B's sweeps, the casts and the roll are never remapped.
 *
 *   c_player_model_attack_sets_white, at player_input_build's (0x84F90)
 *   CALL 0x84940 player_input_tick at 0x854B4 (Europe 0x85464): the call,
 *   then: outside the attack state (+0x94 != 0x100) logical := -1 (a
 *   later air attack or landing keeps the game's last move); a fresh WHITE
 *   press (button_pressed_once, ECX 5, the latch the poll clears on
 *   release, 0xA28FF) while input+0x30 is clear and not swimming (+0x94 !=
 *   6) selects the next set, pressed := now; the latch is taken in every
 *   state, so WHITE held from the water or a wait onto land never cycles
 *   (no retail path reads WHITE's latch; the swim reads its analog value);
 *   shown := 0 <= now - pressed < 2.0, so a clock set back by a warp never
 *   holds it up.  The set and the press time live from boot (a level load
 *   keeps them).
 *
 *   c_player_model_attack_sets_hud, at the HUD draw's (0x1B2B0) CALL
 *   0x1B110 hud_list_draw at 0x1B306 (the same VA in Europe), its last
 *   draw, so the line shows only when the HUD does (the 'Show UI' cvar):
 *   the call, then while shown the set's line (bytes param
 *   player_model_sets_lines, 80 bytes a set, '\n' splitting it) in the
 *   courier font (hud_font 0xD09E0) anchored at the screen's title-safe
 *   top-left corner at 0.8 (hud_anchor 0xD0830(9, {0.8, 0.8}): 64 px from
 *   the left and 48 from the top of 640x480), yellow (the material
 *   0x97420, Europe 0x974F0, through bytes param
 *   player_model_sets_material), a line a font_draw_text 0xD0D60, as the game's own 'show
 *   profile' overlay 0x22170 draws its lines: the pen x 2, y -2 - font[+8]
 *   stepped by -font[+4] a line.  Then 0xD0830(5, {1, 1}), the anchor
 *   0x1B2B0 sets before its list, so whatever draws after it sees an
 *   anchor vanilla leaves there (its list leaves its last entry's, 5 or 6
 *   at 0x1B151, or 5 when empty).
 *
 * Bytes param player_model_sets_map: the set count, then per set the
 * column each of basic1-3, finish, finish2, finish3 plays (set 0 its own).
 *
 * ABI.  0x88D78: EDI the PlayerControl, ESI the input, AL and CL the
 * search's register inputs (kept round the pre-step), its six stack
 * arguments copied again for the game's call (RET 0x18 pops the copies,
 * the entry's own RET 0x18 the originals); the caller reads PC+0x16C and
 * PC+0x138 after, no register.  0x854B4: ECX = ESI the input, EBP the
 * PlayerControl; 0x84940 touches EAX, ECX, EDX and the caller reads none
 * of them after (0x854B9 push esi).  0x1B306: the HUD on the stack,
 * 0x1B110 stdcall (RET 4); the caller reads no register after (0x1B30B
 * pop ebx).  Every C helper is cdecl (it keeps EBX, ESI, EDI and EBP); x87
 * only (AZ-021).
 */

#include "azurik_vanilla.h"   /* the game's calls; and azurik.h: the params */

#define PC_CLOCK     0x00C   /* PlayerControl -> the clock (+0x10: now, f64) */
#define PC_CRITTER   0x020   /* PlayerControl -> its critter              */
#define PC_STATE     0x094   /* its move state                            */
#define PC_RECORD    0x0DC   /* the playing column's attacks_anims record */
#define PC_AIM       0x0E8   /* that record's Aim angle (its +0xC)        */
#define PC_COLUMN    0x134   /* the column playing (the last move)        */
#define PC_YAW       0x138   /* the swing's yaw                           */
#define CR_SLOT      0x200   /* critter: the anim slot anim_change took   */
#define CLOCK_NOW    0x010
#define IN_LOCKED    0x030   /* input: set, the presses wait (0x8D3D5)    */
#define IN_HEADING   0x038   /* input: the stick heading H                */
#define ATTACK       0x100   /* the ground attack's state                 */
#define SWIM         6       /* the swim's state                          */
#define WHITE        5       /* ControllerState +0x18 + 4 x 5             */
#define SLOT_ATTACK  0x52    /* an attack column's slot: 0x52 + it        */
#define REMAPPED     6       /* basic1-3, finish, finish2, finish3        */
#define FINISH       3       /* finish, finish2, finish3: a set's fourth  */
#define SETS         8
#define LINE         80
#define EMPTY        1e5f    /* an empty Aim angle (0x198198)             */
#define DEGREE       0.0174532925f
#define SHOWN        2.0     /* s the line shows after a press            */
#define CORNER       9       /* hud_anchor: left | top                    */
#define HUD_CORNER   5       /* left | bottom: 0x1B2B0's last anchor      */
#define HUD_TEXT     0.8f    /* the line's scale: the HUD's gem counts'    */
#define FONT_STEP    0x004   /* font: the line step (int)                 */
#define FONT_TOP     0x008   /* font: the top (int)                       */

AZURIK_BYTES_PARAM(player_model_sets_map, 1 + SETS * REMAPPED);
AZURIK_BYTES_PARAM(player_model_sets_lines, SETS * LINE);
AZURIK_BYTES_PARAM(player_model_sets_state_at, 4);
AZURIK_BYTES_PARAM(player_model_sets_material, 4);

struct sets_state {
    int set;         /* the set WHITE selected (0: the game's combo)     */
    int logical;     /* the combo column a set's swing stands for; -1    */
    int source;      /* the column it plays                              */
    int shown;       /* 1 while the line shows (2.0 s after a press)     */
    double pressed;  /* the clock at the last WHITE press                */
};

struct sets_state player_model_sets_state = {0, -1, -1, 0, -1e300};

static const float yellow[4] = {1.0f, 0.9f, 0.2f, 1.0f};

static struct sets_state *state(void)
{
    unsigned at = *(const volatile unsigned *)player_model_sets_state_at;

    return at ? (struct sets_state *)at : &player_model_sets_state;
}

static int sets(void)
{
    int n = ((const volatile unsigned char *)player_model_sets_map)[0];

    return n < 1 ? 1 : n > SETS ? SETS : n;
}

/* AL 0 when the 2D material (0x97420, its release's VA in the bytes param
 * player_model_sets_material: the first byte of its MOV EAX, imm32 keeps
 * it out of the vanilla-symbol registry) for ``colour`` (ESI) and
 * ``texture`` (EDI, the font) fails; stdcall(0, 1) as text takes it. */
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
        "calll *_player_model_sets_material \n\t"   /* RET 8 */
        "popl %%edi                         \n\t"
        "popl %%esi                         \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

/* AL: a fresh WHITE press on ``pad`` (its latch then taken). */
__attribute__((naked, noinline))
static unsigned char white_pressed(void *pad)
{
    __asm__ volatile (
        "movl 4(%%esp), %%edx               \n\t"
        "movl $5, %%ecx                     \n\t"
        "jmp _button_pressed_once           \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void sets_before(char *pc)
{
    struct sets_state *s = state();
    const char *critter = *(const char *const *)(pc + PC_CRITTER);

    if (s->logical >= 0 && *(const int *)(pc + PC_COLUMN) == s->source && critter
            && *(const int *)(critter + CR_SLOT) == SLOT_ATTACK + s->source)
        *(int *)(pc + PC_COLUMN) = s->logical;
    else
        s->logical = -1;   /* the search isn't keyed on a set's swing */
}

__attribute__((used))
void sets_after(char *pc, const char *input)
{
    struct sets_state *s = state();
    int found = *(const int *)(pc + PC_COLUMN), last = s->logical, c = found, source;
    float aim, bearing;

    s->logical = -1;
    if (s->set <= 0 || s->set >= sets() || c < 0 || c >= REMAPPED)
        return;
    if (last >= FINISH && c >= FINISH)   /* out of the set's fourth: its first (AZ-680) */
        c = 0;
    source = ((const volatile unsigned char *)player_model_sets_map)[1 + REMAPPED * s->set + c];
    if (source == found)   /* the game's record is already S's */
        return;
    aim = *(const float *)(pc + PC_AIM);
    bearing = aim == EMPTY ? EMPTY : *(const float *)(pc + PC_YAW) + aim * DEGREE;
    attack_anim_record_copy_call(pc + PC_RECORD, source, *(const float *)(input + IN_HEADING), bearing);
    s->logical = c;
    s->source = source;
}

/* 0x88D78: the logical key, CALL attack_transition_search (AL, CL), the set's column. */
__attribute__((naked))
void c_player_model_attack_sets_search(void)
{
    __asm__ volatile (
        "pushl %%eax                        \n\t"   /* AL, CL: the search's inputs */
        "pushl %%ecx                        \n\t"
        "pushl %%edi                        \n\t"   /* the PlayerControl */
        "calll _sets_before                 \n\t"
        "addl $4, %%esp                     \n\t"
        "popl %%ecx                         \n\t"
        "popl %%eax                         \n\t"
        "pushl 0x18(%%esp)                  \n\t"   /* its six arguments again */
        "pushl 0x18(%%esp)                  \n\t"
        "pushl 0x18(%%esp)                  \n\t"
        "pushl 0x18(%%esp)                  \n\t"
        "pushl 0x18(%%esp)                  \n\t"
        "pushl 0x18(%%esp)                  \n\t"
        "calll \"_attack_transition_search@24\" \n\t"   /* pops the copies */
        "pushl %%esi                        \n\t"   /* the input */
        "pushl %%edi                        \n\t"   /* the PlayerControl */
        "calll _sets_after                  \n\t"
        "addl $8, %%esp                     \n\t"
        "retl $0x18                         \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void sets_tick(const char *input, const char *pc)
{
    struct sets_state *s = state();
    int n = sets(), state_now = *(const int *)(pc + PC_STATE);
    int fresh = white_pressed(active_controller_state())   /* the latch taken in every state */
        && !*(const unsigned char *)(input + IN_LOCKED) && state_now != SWIM;
    double now = *(const double *)(*(const char *const *)(pc + PC_CLOCK) + CLOCK_NOW);
    double since;

    if (state_now != ATTACK)
        s->logical = -1;
    if (s->set < 0 || s->set >= n)
        s->set = 0;
    if (fresh) {
        s->set = (s->set + 1) % n;
        s->pressed = now;
    }
    since = now - s->pressed;
    s->shown = since >= 0.0 && since < SHOWN;
}

/* 0x854B4: CALL player_input_tick (ECX), then WHITE. */
__attribute__((naked))
void c_player_model_attack_sets_white(void)
{
    __asm__ volatile (
        "calll \"@player_input_tick@4\"     \n\t"   /* ECX the input, as the game set it */
        "pushl %%ebp                        \n\t"   /* the PlayerControl */
        "pushl %%esi                        \n\t"   /* the input */
        "calll _sets_tick                   \n\t"
        "addl $8, %%esp                     \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}

__attribute__((used))
void sets_hud(void)
{
    const struct sets_state *s = state();
    const volatile unsigned char *line;
    const char *font;
    float scale[2] = {HUD_TEXT, HUD_TEXT}, y;
    char text[LINE];
    int set = s->set, i;

    if (!s->shown || set < 0 || set >= sets() || !(font = hud_font()))
        return;
    hud_anchor(CORNER, scale);
    if (hud_material(yellow, font)) {
        line = player_model_sets_lines + LINE * set;
        y = -2.0f - (float)*(const int *)(font + FONT_TOP);
        for (;;) {   /* 0xD0D60 draws '\n' as a glyph: a line a call */
            float pen[9] = {2.0f, y, 0.0f, 0.0f, 1.0f, 0.0f, 1.0f, 0.0f, 0.0f};

            for (i = 0; i < LINE - 1 && line[i] && line[i] != '\n'; i++)
                text[i] = (char)line[i];
            text[i] = 0;
            font_draw_text_call(pen, font, text);
            if (i >= LINE - 1 || line[i] != '\n')
                break;
            line += i + 1;
            y -= (float)*(const int *)(font + FONT_STEP);
        }
    }
    scale[0] = scale[1] = 1.0f;
    hud_anchor(HUD_CORNER, scale);
}

/* 0x1B306: CALL hud_list_draw (the HUD on the stack), then the set's line. */
__attribute__((naked))
void c_player_model_attack_sets_hud(void)
{
    __asm__ volatile (
        "pushl 4(%%esp)                     \n\t"   /* the HUD */
        "calll \"_hud_list_draw@4\"         \n\t"
        "calll _sets_hud                    \n\t"
        "retl $4                            \n\t"
        : : : "memory"
    );
}
