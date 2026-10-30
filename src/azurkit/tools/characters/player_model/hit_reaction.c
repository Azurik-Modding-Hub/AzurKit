/* X7: a player model's hit reaction lasts garret4's (Step 2.21d; D112,
 * AZ-291).
 *
 * The player's hit handler 0x8D600 (a PlayerControl vtable slot)
 * lets the chooser 0x30BD0 pick the reaction: anim 37-39 (ouch_1,
 * ouch_2, ouch_3) by the damage, falling back to the first the body
 * has, then 40-42 (ouch_1r, ouch_1l, ouch_1b) by the direction when
 * the body has them.  The names are the XBE's base clip table
 * (0x1A9F78), which the engine resolves per body into the species'
 * clip slots +0x124 (-1: the body has no such clip); no config.xbr
 * cell names them.  The CALL at 0x8D682 plays it through 0x42750 at
 * rate 1 and the handler sets state 0x102; on the ground the player
 * stays in 0x100, without control, until that clip ends.  garret4's
 * ouch clips are 0.4 s, so it recovers in 12 ticks plus the air
 * time (xemu sitting modelswap: 13-32 ticks); a swapped body's are
 * its own, 0.67-5 s (keylord 63 ticks on its 2.07 s ouch_2), and a
 * body with no ouch clip plays nothing, leaving the clip already
 * playing, which a looping walk or idle never ends [inferred].
 *
 * This shim replaces that CALL.  Whatever the chooser picked, it plays
 * the body's ouch_1 (garret4 plays only ouch_1 and its directional
 * twins), else its idle, else the clip its roll plays (W3 gives the
 * roll one of the body's clips), under the picked index, so the index
 * 0x42750 gets and records (critter+0x200) stays the game's.  It puts
 * that clip in the picked slot for the call and then puts the slot
 * back, and sets the new layer's rate to the clip's length over
 * player_model_hit_seconds, garret4's 0.4 s: the reaction ends when
 * garret4's would.
 *
 * A 0 there (the retired "Fully the model" mode wrote it, Step 2.65,
 * D230; no build has since Step 2.129, D329) plays the chooser's pick
 * as the game plays it, at its own length, when the body has that
 * clip; a body with no ouch clip still plays the fallback above in
 * garret4's 0.4 s (D229).
 *
 * It also ends the crossfade at once (Step 2.22l, AZ-304).  0x42750
 * plays the reaction on a fresh layer (0xCAD40: weight 0.01, fading
 * in), and the layers already playing fade out over 0.25 s while their
 * clips keep running; a body's damage marker reads the layers' blend.
 * So when the interrupted attack's clip reached its own damage window
 * during the fade, the body's m_damage came on inside the reaction at
 * that layer's share, 0.99 down to 0.07 (xemu sitting modelswap3: hits
 * dealt 2-3 ticks into reactions on sleeth, firedrake and guard_air).
 * The shim frees every other layer (flags 0, weight 0, as the engine
 * does when a fade-out finishes) and gives the reaction's weight 1.0,
 * so only the reaction clip, which has no damage window, drives the
 * marker.
 *
 * ABI: 0x42750 is __stdcall(16) (the critter, the anim index, the
 * flags 4 and the node "m_feet"; RET 0x10) with no register input, and
 * the handler reads neither EAX, ECX nor EDX after it (0x8D687 on).
 * The shim is __stdcall(16) too and keeps EBX, ESI, EDI and EBP.
 */

#include "azurik_vanilla.h"   /* and azurik.h: AZURIK_FLOAT_PARAM */

AZURIK_FLOAT_PARAM(player_model_hit_seconds, 0.4f);

#define CR_SPECIES   0x178   /* critter -> its species                    */
#define CR_ANIM      0x17C   /* critter -> its anim object, or NULL       */
#define SP_SLOTS     0x124   /* species: a clip handle per anim index      */
#define AN_ACTIVE    0x010   /* anim: the active layer's index             */
#define AN_LAYERS    0x040   /* anim: three 0x40-byte layers               */
#define N_LAYERS     3
#define LY_CLIP      0x004   /* layer: its clip ('banm')                   */
#define LY_FLAGS     0x008   /* layer: 0 free, 8 fading in, 0x10 out      */
#define LY_WEIGHT    0x01C   /* layer: its blend weight, 0 to 1            */
#define LY_RATE      0x020   /* layer: its rate                            */
#define CLIP_LENGTH  0x010   /* banm: its length, s                        */

#define NO_CLIP      (-1)
#define IDLE         1               /* base clip table indices      */
#define OUCH_1       0x25
#define ROLL         (0x52 + 20)     /* attacks_anims 'roll forward' */
#define HIT_SECONDS  0.4f            /* garret4's ouch_1, _1r, _1l, _1b */

__attribute__((stdcall))
void c_player_model_hit(char *critter, int index, int flags, const char *node)
{
    float seconds = player_model_hit_seconds;
    int *slots = (int *)(*(char **)(critter + CR_SPECIES) + SP_SLOTS);
    int kept = slots[index];
    int own = seconds <= 0.0f && kept != NO_CLIP;
    int clip = own ? kept
             : slots[OUCH_1] != NO_CLIP ? slots[OUCH_1]
             : slots[IDLE] != NO_CLIP ? slots[IDLE] : slots[ROLL];
    char *anim, *layer, *banm;
    int active, n;

    slots[index] = clip;
    anim_change_at_node(critter, index, flags, node);
    slots[index] = kept;
    anim = *(char **)(critter + CR_ANIM);
    if (clip == NO_CLIP || !anim)
        return;
    active = *(int *)(anim + AN_ACTIVE);
    for (n = 0; n < N_LAYERS; n++) {
        layer = anim + AN_LAYERS + AN_LAYERS * n;
        if (n == active) {
            *(float *)(layer + LY_WEIGHT) = 1.0f;
        } else {
            *(int *)(layer + LY_FLAGS) = 0;
            *(float *)(layer + LY_WEIGHT) = 0.0f;
        }
    }
    if (own)
        return;
    if (seconds <= 0.0f)
        seconds = HIT_SECONDS;
    layer = anim + AN_LAYERS + AN_LAYERS * active;
    banm = *(char **)(layer + LY_CLIP);
    if (banm && *(float *)(banm + CLIP_LENGTH) > 0.0f)
        *(float *)(layer + LY_RATE) = *(float *)(banm + CLIP_LENGTH) / seconds;
}
