/* qol_photo_mode: photo mode (D489, Step 2.160).
 *
 * Click both sticks (L3 + R3) and the game freezes where it is, the HUD
 * hides and the camera flies free; L3 + R3 again, START or BACK resumes
 * it as it was.  The freeze and the camera are the game's own: the cheat
 * owner's free camera (cheat code 3, action 3 of 0x16610, owner state 1),
 * in which the world doesn't step (0x15F60).  Design ported from Azurik
 * Debug Menu 1.1.0 by Azurik Perathia (MIT; NOTICE.md), reimplemented
 * here: its hook round the cheat-owner tick and its CALL of action 3.
 *
 * Two hooks, two entry points.  a build lands this object once per
 * hook, so the hooks share no static data (the camera hook needs none).
 *
 *   c_photo_mode_tick    replaces scene_state_tick's CALL of
 *                        cheat_owner_tick (0x15DA0) at 0x55BB9, its only
 *                        caller: EDI = the cheat owner, the scene and dt
 *                        on the stack, RET 8.  Before the tick it turns a
 *                        fresh L3 + R3, or a START press, in photo mode
 *                        into state 4 (the tick then destroys the camera
 *                        and sets state 0 in this same call); after it,
 *                        a fresh L3 + R3 in normal play opens the free
 *                        camera, hides the HUD and clears the world text
 *                        (0x50950; paused, the world keeps its last
 *                        update's lines on screen).  Either way every
 *                        held button's press is taken, so nothing held
 *                        fires in the game or the camera afterwards.
 *   c_photo_mode_camera  replaces the frame function's call of the active
 *                        camera's update (vtable slot +0xCC) at 0x548E3,
 *                        its `push eax; mov ecx, ebp; call [edx+0xCC]`
 *                        (EBP = the camera, EAX = dt; a plain RET, as the
 *                        inline code it replaced): it makes that thiscall
 *                        itself.  For the free camera dt is multiplied by
 *                        fly_speed, a quarter while B is held and four
 *                        times while Y is held; any other camera gets dt
 *                        as it was.
 *
 * Both releases: the shim names no address of the image (it calls
 * vanilla functions by name, which Europe's map relocates, and reads the
 * pad through active_controller_state).
 *
 * Ported from Modkit's azurik_mod/patches/qol_photo_mode/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_photo_mode.o beside it.
 */

#include "azurik_vanilla.h"

/* cheat_owner_tick(scene, dt) takes the cheat owner in EDI: this loads it,
 * saving EDI, and pops its three arguments. */
static inline __attribute__((naked, stdcall))
void cheat_owner_tick_call(void *owner, void *scene, float dt)
{
    __asm__("pushl %edi\n\t"
            "movl 8(%esp), %edi\n\t"
            "pushl 16(%esp)\n\t"
            "pushl 16(%esp)\n\t"
            "calll \"_cheat_owner_tick@8\"\n\t"
            "popl %edi\n\t"
            "retl $12");
}

/* The cheat owner, [scene+0x40] (Modkit's scripts/xemu_sitting.py cheat_owner). */
#define OWNER_PROG    0x00   /* int: steps of the code being matched     */
#define OWNER_CODE    0x04   /* int: the code being matched              */
#define OWNER_GEMS    0x0C   /* u8: the cheats' gem mode                 */
#define OWNER_STATE   0x1C   /* int: 0 idle, 1 free camera, 2-4 menus    */
#define OWNER_CAMERA  0x2C   /* the free camera, or 0                    */

#define STATE_IDLE    0
#define STATE_CAMERA  1
#define STATE_CLOSE   4      /* pop every menu, destroy the camera, 0    */
#define ACTION_FREE_CAMERA 3

/* The chord a cheat code's own steps make stays the code's (the codes:
 * Modkit's scripts/xemu_sitting.py CHEATS).  Code 2 ends on L3 + R3 together;
 * codes 0, 3, 6 and 7 take R3 then L3, and code 9 L3 then R3, as steps in
 * a row, and clicking the second before letting go of the first makes the
 * chord, which the walker doesn't match (it finishes the code once the
 * first is let go).  By code (owner +0x04): the steps matched (+0x00)
 * when the next step is that chord or that second click; -1 none. */
static const signed char CODE_CHORD_STEP[10] = {5, -1, 4, 6, -1, -1, 4, 4, -1, 2};

#define SCENE_WORLD   0x2C
#define SCENE_PAD_OUT 0x4C   /* u8: paused for a pulled controller      */
#define SCENE_CUT     0x168  /* u8: an in-engine cutscene plays         */
#define W_CRITTER     0xC0   /* the player critter                      */
#define W_REQUEST     0xD8   /* +0x10 level request, +0x14 save request */
#define CAM_HIDE_HUD  0x194  /* u8: the free camera hides the HUD (A)   */
#define CAM_UPDATE    (0xCC / 4)

#define PAD_BUTTONS   12     /* A .. BACK at +0x18, their latches +0x48 */
#define LATCH_START   10

#define SLOW 0.25f           /* B held */
#define FAST 4.0f            /* Y held */

AZURIK_FLOAT_PARAM(photo_mode_fly_speed, 1.0f);

typedef void (__attribute__((thiscall)) *camera_update_fn)(void *camera, f32 dt);

/* L3 + R3 both held at the last update: a chord counts once it forms. */
static u8 g_chord_prev;

/* Take the press of every button held, as the game takes one it acts on:
 * the polling loop clears a latch only once its button is released. */
static void take_held(ControllerState *pad)
{
    const f32 *b = (const f32 *)((u8 *)pad + 0x18);
    int i;
    for (i = 0; i < PAD_BUTTONS; i++)
        if (b[i] > 0.0f)
            pad->edge_state[i] = 1;
}

/* Photo mode opens only in play: a world with its player, no gem mode,
 * no cutscene, no pulled controller and no level load or save waiting
 * (a load would free the world under the camera). */
static int can_enter(u8 *owner, u8 *scene)
{
    u8 *world, *request;
    if (owner[OWNER_GEMS] || scene[SCENE_CUT] || scene[SCENE_PAD_OUT])
        return 0;
    world = *(u8 **)(scene + SCENE_WORLD);
    if (!world || !*(void **)(world + W_CRITTER))
        return 0;
    request = *(u8 **)(world + W_REQUEST);
    return request && !*(void **)(request + 0x10) && !*(void **)(request + 0x14);
}

void photo_mode_tick(u8 *owner, u8 *scene, f32 dt)
{
    ControllerState *pad = active_controller_state();
    int chord = pad->stick_left_click > 0.0f && pad->stick_right_click > 0.0f;
    int edge = chord && !g_chord_prev;
    int state_in = *(int *)(owner + OWNER_STATE);
    u32 code = *(u32 *)(owner + OWNER_CODE);
    int code_step = code < 10 && *(int *)(owner + OWNER_PROG) == CODE_CHORD_STEP[code];
    int state;
    u8 *camera;

    g_chord_prev = (u8)chord;
    if (state_in == STATE_CAMERA) {
        if (edge) {
            *(int *)(owner + OWNER_STATE) = STATE_CLOSE;
            edge = 0;
        } else if (pad->start_button > 0.0f && !pad->edge_state[LATCH_START]
                   && !scene[SCENE_PAD_OUT]) {
            pad->edge_state[LATCH_START] = 1;   /* no pause menu over it */
            *(int *)(owner + OWNER_STATE) = STATE_CLOSE;
        }
    }

    cheat_owner_tick_call(owner, scene, dt);

    state = *(int *)(owner + OWNER_STATE);
    if (state_in == STATE_CAMERA && state == STATE_IDLE)
        take_held(pad);                         /* any way out */
    if (state != STATE_IDLE || !edge || code_step || !can_enter(owner, scene))
        return;
    cheat_owner_action(owner, ACTION_FREE_CAMERA, scene);
    camera = *(u8 **)(owner + OWNER_CAMERA);
    if (*(int *)(owner + OWNER_STATE) == STATE_CAMERA && camera) {
        camera[CAM_HIDE_HUD] = 1;
        take_held(pad);
        world_text_clear();     /* the paused world would keep its lines */
    }
}

__attribute__((naked))
void c_photo_mode_tick(void)
{
    __asm__ volatile (
        "pushl 8(%%esp)                      \n\t"   /* dt */
        "pushl 8(%%esp)                      \n\t"   /* the scene */
        "pushl %%edi                         \n\t"   /* the cheat owner */
        "calll _photo_mode_tick              \n\t"
        "addl $12, %%esp                     \n\t"
        "retl $8                             \n\t"
        : : : "memory"
    );
}

void photo_mode_camera(void *camera, f32 dt)
{
    camera_update_fn update = (camera_update_fn)(*(void ***)camera)[CAM_UPDATE];
    if ((void *)update == (void *)free_camera_update) {
        ControllerState *pad = active_controller_state();
        f32 k = photo_mode_fly_speed;
        if (pad->button_b > 0.0f)
            k *= SLOW;
        if (pad->button_y > 0.0f)
            k *= FAST;
        dt *= k;
    }
    update(camera, dt);
}

__attribute__((naked))
void c_photo_mode_camera(void)
{
    __asm__ volatile (
        "pushl %%eax                         \n\t"   /* dt */
        "pushl %%ebp                         \n\t"   /* the active camera */
        "calll _photo_mode_camera            \n\t"
        "addl $8, %%esp                      \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}
