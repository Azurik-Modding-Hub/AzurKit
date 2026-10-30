/* X16: the air armor's wings flap on a player model (Step 2.77), and
 * every armor piece rides the body's bones (Step 2.118, AZ-447, AZ-448).
 *
 * The wings aren't the body's: they are the air armor's own fx graph
 * (config.xbr `magic` row A: fx/magic/fx_jump1/2/3), posed by the timer
 * fx_jumpWings:Wing_timer.  The only thing that restarts that timer is
 * the graph's transform `m_jump` (no children, only a link source),
 * bound by name to the wearer's body marker `m_jump`: its translateX
 * sets the timer's window (X >= 1.5: start 1.8, stop 10.333) and its
 * translateZ (x 0.01) the timer's and Rumble_timer's reset.  Each flap
 * wing_flap asks for anim 17, superjump (the CALL 0x42910 at 0x89412),
 * and garret4's superjump keys m_jump X = 2 and pulses Z from 5 to 0
 * within 0.033 s, so every flap resets the timer to 1.8: the stroke,
 * the flap and fly sounds and the rumble play again.
 *
 * Only garret4's body has an `m_jump` marker.  On any other body the
 * bind (0x62A20 asks the critter's bind interface, critter+0x170, slot
 * 1 = 0x44270, which looks the name up with the CALL 0xCA1D0 at
 * 0x44355) finds nothing and the transform keeps its authored
 * (2, -4, 0): the timer plays once after the cast and holds its
 * wings-out end pose, whatever the player does.  The armors' pieces
 * (the helm, breastplate, wings, shoulder, wrist and ankle pieces, the
 * shields' cores) bind the same way to garret4's ten armor nodes
 * (m_root, m_chest, m_waist, m_skull and the six limb markers), which
 * no other body has but m_root (11 bodies) and m_waist (one), so each
 * kept W15's fixed point in the model whatever the clip did.
 *
 * X16 gives the player virtual nodes, at two CALLs:
 *
 *   c_player_model_wings_bind, at 0x44355 (slot 1, 0x44270): calls
 *   0xCA1D0 as the game does; when the critter's species (this+8,
 *   critter+0x178) has the `player` flag 0x20 in +0x64, a name of the
 *   build's armor table (player_model_wings_armor, n = 1.., the body's
 *   own m_root or m_waist too) binds to 0xC000 | n, and a missing
 *   "m_jump" to 0xC000.  0xCA1D0 returns i|0x8000 (a marker) or
 *   i|0x4000 (a bone), never both bits.  0x62A20 keeps the index and
 *   hands it back to slot 2 every frame (0x62C40 at 0x62CBB), whatever
 *   its value.  Since Step 2.134b (W27) a baked body the build grew an
 *   `m_root` on for the player's swim (player_model_wings_grown, its
 *   name) binds no `m_root` for any other critter that wears it (the
 *   species' body name, S+4, case-blind): an NPC's own clips don't key
 *   the grown marker, so the damage fx that bind it (fx_electric_hit,
 *   fx_force_hit) would sit at its feet, not at their authored point.
 *
 *   c_player_model_wings_pose, at 0x44389 (slot 2, 0x44370, which the
 *   fx update calls for each bound transform every frame): for 0xC000
 *   it fills the transform record as 0xCCDF0 fills it from a marker:
 *   T (x, -4, z), Q identity, S 1, +0x68 = 1 (bound) and +0x69 = 0 (no
 *   bone matrix).  x is what garret4's own m_jump keys in the clip the
 *   critter plays (this+0x90 = critter+0x200, the anim index
 *   anim_change 0x42910 stores at 0x4296C, an empty slot's too): 2 in
 *   superjump (17), 1 in jump and jump_standing (15, 16), 0 in every
 *   other (Step 2.134b: an x held at 2 kept the timer's window at
 *   [1.8, 10.333], so 4.27 s after a flap the wings held the stroke's
 *   raised end pose, on the ground too, until the next flap; x 0 gives
 *   [1, 1], the fold).  z is 5 on the first evaluation that sees the flap
 *   counter (PlayerControl+0xD8, PlayerControl = this+0x10 =
 *   critter+0x180; +1 per flap at 0x8937B, 0 at a jump and a landing)
 *   at a new nonzero value, else 0.  The graph pass that follows in the
 *   same fx update (0x664E0 at 0x6333C) runs m_jump's links before the
 *   timer's update, so one such evaluation resets the timer to 1.8.
 *   For 0xC000 | n it fills the record as 0xCCDF0 fills it from a bone:
 *   the matrix M = C_n x the bone's runtime matrix (the anim object's
 *   +8, 0xB0 bytes a bone, its +0x70: the bone in the model) into
 *   +0x00, and M's translation, rotation (a quaternion, Shoemake's, as
 *   0xA0520 reads one) and row lengths into +0x50, +0x40 and +0x5C,
 *   +0x68 = +0x69 = 1.  0x68DE0 then writes those into the transform's
 *   attributes (so its links, the shoulder pads' rotateY, see the
 *   piece's turn) and M into its local (0x68FA0, mode 6).  C_n is the
 *   build's F x B^-1: F the piece's local at W15's point, B the bone's
 *   bind, so at the bind pose the piece is where W15 puts it and then
 *   it moves rigidly with its bone, as a vertex skinned to it would.
 *   Any other index jumps to 0xCCDF0 unchanged.
 *
 * At 0x44355: ECX the anim object, EDI and [ESP + 4] the name, EBP the
 * bind interface (this); 0xCA1D0 is thiscall(name), RET 4, and its
 * caller pops EDI, ESI, EBP and EBX after it and reads only EAX.  At
 * 0x44389: ECX the anim object, EDX the index, EAX the transform
 * record, EDI this; 0xCCDF0 takes those registers and returns with a
 * plain RET, and its caller reads none of EAX, ECX and EDX after it.
 * Both keep EBX, ESI, EDI and EBP (the C helpers are cdecl).
 */

#include "azurik_vanilla.h"

#define IF_SPECIES    0x08    /* the bind interface: the critter's species  */
#define SP_BODY       0x04    /* species: its body's name                   */
#define SP_FLAGS      0x64    /* species: its kind flags                    */
#define GROWN_SIZE    64      /* _player_character.WINGS_GROWN               */
#define PLAYER_FLAG   0x20    /* the `player` feature                       */
#define AN_BONES      0x08    /* the anim object: its runtime bones         */
#define BONE_SIZE     0xB0    /* one runtime bone                           */
#define BONE_MATRIX   0x70    /* its matrix in the model (D3D rows)         */
#define VIRTUAL       0xC000u /* a virtual node: m_jump (0), armor n (1..)  */
#define ARMOR_MAX     10      /* _player_character.ARMOR_NODES              */
#define ARMOR_ENTRY   84      /* name[16], bone (i32), C (16 f32)           */
#define ARMOR_SIZE    (4 + ARMOR_MAX * ARMOR_ENTRY)
#define REC_Q         16      /* the record, in floats: +0x40 the rotation  */
#define REC_T         20      /* +0x50 the translation                      */
#define REC_S         23      /* +0x5C the scale                            */
#define REC_BOUND     0x68    /* bytes: bound, and +0x69 its matrix given   */
#define FLAT_ROW      1e-20f  /* a row this short (squared) has no direction */

/* The flap counter the pose hook last saw (its .bss: shim data). */
unsigned int player_model_wings_flaps;

/* The build's armor table (armor_table): a count, then its entries. */
AZURIK_BYTES_PARAM(player_model_wings_armor, ARMOR_SIZE);

/* The body W27 grew m_root on, NUL-ended; empty when none. */
AZURIK_BYTES_PARAM(player_model_wings_grown, GROWN_SIZE);

static const char jump_name[7] = "m_jump";
static const char root_name[7] = "m_root";

static int armor_count(void)
{
    int n = *(const volatile int *)player_model_wings_armor;

    return n < ARMOR_MAX ? n : ARMOR_MAX;
}

static const volatile unsigned char *armor_entry(unsigned n)
{
    return player_model_wings_armor + 4 + ARMOR_ENTRY * (n - 1);
}

/* name equals the NUL-ended name at want (at most 16 bytes). */
static int same_name(const char *name, const volatile unsigned char *want)
{
    int i;

    for (i = 0; i < 16; i++) {
        if ((unsigned char)name[i] != want[i])
            return 0;
        if (!want[i])
            return 1;
    }
    return 0;
}

/* body (NUL-ended) is the body W27 grew m_root on (ASCII case-blind). */
static int grown_body(const char *body)
{
    int i;
    unsigned char a, b;

    if (!body || !player_model_wings_grown[0])
        return 0;
    for (i = 0; i < GROWN_SIZE; i++) {
        a = (unsigned char)body[i];
        b = player_model_wings_grown[i];
        if (a - 'A' < 26u)
            a += 'a' - 'A';
        if (b - 'A' < 26u)
            b += 'a' - 'A';
        if (a != b)
            return 0;
        if (!a)
            return 1;
    }
    return 0;
}

static float root(float x)
{
    float r;

    __asm__("fsqrt" : "=t"(r) : "0"(x));
    return r;
}

/* Slot 1's result for name: found (0xCA1D0's), or a virtual node. */
__attribute__((used))
unsigned player_model_wings_node(const char *name, const char *iface, unsigned found)
{
    const char *species = *(const char *const *)(iface + IF_SPECIES);
    int n;

    if (!species)
        return found;
    if (!(*(const unsigned char *)(species + SP_FLAGS) & PLAYER_FLAG))
        return found && same_name(name, (const volatile unsigned char *)root_name)
            && grown_body(*(const char *const *)(species + SP_BODY)) ? 0 : found;
    for (n = 1; n <= armor_count(); n++)
        if (same_name(name, armor_entry(n)))
            return VIRTUAL | n;
    if (!found && same_name(name, (const volatile unsigned char *)jump_name))
        return VIRTUAL;
    return found;
}

/* The record for armor node index (0xC000 | n): its bone's frame. */
__attribute__((used))
void player_model_wings_armor_pose(const char *anim, unsigned index, float *rec)
{
    unsigned n = index & 0x3FFFu;
    const char *bones = *(const char *const *)(anim + AN_BONES);
    const volatile unsigned char *e;
    const float *b;
    float c[16], m[16], s[3], r[3][3], q[4], t, k;
    int i, j, x, y, z;

    if (n < 1 || (int)n > armor_count() || !bones) {
        ((unsigned char *)rec)[REC_BOUND] = 0;
        ((unsigned char *)rec)[REC_BOUND + 1] = 0;
        return;
    }
    e = armor_entry(n);
    b = (const float *)(bones + *(const volatile int *)(e + 16) * BONE_SIZE + BONE_MATRIX);
    for (i = 0; i < 16; i++)
        c[i] = *(const volatile float *)(e + 20 + 4 * i);
    for (i = 0; i < 4; i++)
        for (j = 0; j < 4; j++)
            m[4 * i + j] = c[4 * i] * b[j] + c[4 * i + 1] * b[4 + j] + c[4 * i + 2] * b[8 + j]
                + c[4 * i + 3] * b[12 + j];
    for (i = 0; i < 16; i++)
        rec[i] = m[i];
    q[0] = q[1] = q[2] = 0.0f;
    q[3] = 1.0f;
    for (i = 0; i < 3; i++) {
        rec[REC_T + i] = m[12 + i];
        s[i] = m[4 * i] * m[4 * i] + m[4 * i + 1] * m[4 * i + 1] + m[4 * i + 2] * m[4 * i + 2];
    }
    if (s[0] > FLAT_ROW && s[1] > FLAT_ROW && s[2] > FLAT_ROW) {
        for (i = 0; i < 3; i++)
            s[i] = root(s[i]);
        for (i = 0; i < 3; i++)       /* r[i][j]: column vectors, M's row j over its length */
            for (j = 0; j < 3; j++)
                r[i][j] = m[4 * j + i] / s[j];
        t = r[0][0] + r[1][1] + r[2][2];
        if (t > 0.0f) {
            k = root(t + 1.0f);
            q[3] = 0.5f * k;
            k = 0.5f / k;
            q[0] = (r[2][1] - r[1][2]) * k;
            q[1] = (r[0][2] - r[2][0]) * k;
            q[2] = (r[1][0] - r[0][1]) * k;
        } else {
            x = r[1][1] > r[0][0] ? 1 : 0;
            if (r[2][2] > r[x][x])
                x = 2;
            y = (x + 1) % 3;
            z = (x + 2) % 3;
            k = root(r[x][x] - r[y][y] - r[z][z] + 1.0f);
            q[x] = 0.5f * k;
            k = 0.5f / k;
            q[y] = (r[y][x] + r[x][y]) * k;
            q[z] = (r[z][x] + r[x][z]) * k;
            q[3] = (r[z][y] - r[y][z]) * k;
        }
    } else {
        for (i = 0; i < 3; i++)
            s[i] = root(s[i]);
    }
    for (i = 0; i < 3; i++)
        rec[REC_S + i] = s[i];
    for (i = 0; i < 4; i++)
        rec[REC_Q + i] = q[i];
    ((unsigned char *)rec)[REC_BOUND] = 1;
    ((unsigned char *)rec)[REC_BOUND + 1] = 1;
}

__attribute__((naked))
void c_player_model_wings_bind(void)
{
    __asm__ volatile (
        "pushl 4(%%esp)                      \n\t"   /* the name */
        "calll _anim_node_by_name            \n\t"   /* ECX the anim object; RET 4 */
        "pushl %%eax                         \n\t"   /* found */
        "pushl %%ebp                         \n\t"   /* this */
        "pushl 12(%%esp)                     \n\t"   /* the name */
        "calll _player_model_wings_node      \n\t"
        "addl $12, %%esp                     \n\t"
        "retl $4                             \n\t"
        : : : "memory"
    );
}

__attribute__((naked))
void c_player_model_wings_pose(void)
{
    __asm__ volatile (
        "cmpl $0xC000, %%edx                 \n\t"
        "jb 9f                               \n\t"   /* a node of the body's, or none */
        "je 1f                               \n\t"   /* the virtual m_jump */
        "pushl %%eax                         \n\t"   /* the record */
        "pushl %%edx                         \n\t"   /* the index */
        "pushl %%ecx                         \n\t"   /* the anim object */
        "calll _player_model_wings_armor_pose \n\t"
        "addl $12, %%esp                     \n\t"
        "retl                                \n\t"
        "1:                                  \n\t"
        "movl 0x10(%%edi), %%ecx             \n\t"   /* this -> PlayerControl */
        "xorl %%edx, %%edx                   \n\t"   /* z = 0.0f */
        "testl %%ecx, %%ecx                  \n\t"
        "jz 2f                               \n\t"
        "movl 0xD8(%%ecx), %%ecx             \n\t"   /* the flap counter */
        "cmpl _player_model_wings_flaps, %%ecx \n\t"
        "je 2f                               \n\t"
        "movl %%ecx, _player_model_wings_flaps \n\t"
        "testl %%ecx, %%ecx                  \n\t"
        "jz 2f                               \n\t"
        "movl $0x40A00000, %%edx             \n\t"   /* a new flap: z = 5.0f */
        "2:                                  \n\t"
        "movl 0x90(%%edi), %%ecx             \n\t"   /* the anim playing (critter+0x200) */
        "cmpl $17, %%ecx                     \n\t"
        "je 3f                               \n\t"   /* superjump */
        "subl $15, %%ecx                     \n\t"
        "cmpl $1, %%ecx                      \n\t"
        "movl $0x3F800000, %%ecx             \n\t"   /* jump, jump_standing: x = 1.0f */
        "jbe 4f                              \n\t"
        "xorl %%ecx, %%ecx                   \n\t"   /* any other: x = 0.0f */
        "jmp 4f                              \n\t"
        "3:                                  \n\t"
        "movl $0x40000000, %%ecx             \n\t"   /* x = 2.0f */
        "4:                                  \n\t"
        "movl %%ecx, 0x50(%%eax)             \n\t"   /* T = (x, -4.0f, z) */
        "movl $0xC0800000, 0x54(%%eax)       \n\t"
        "movl %%edx, 0x58(%%eax)             \n\t"
        "xorl %%edx, %%edx                   \n\t"
        "movl %%edx, 0x40(%%eax)             \n\t"   /* Q = (0, 0, 0, 1.0f) */
        "movl %%edx, 0x44(%%eax)             \n\t"
        "movl %%edx, 0x48(%%eax)             \n\t"
        "movl $0x3F800000, %%edx             \n\t"
        "movl %%edx, 0x4C(%%eax)             \n\t"
        "movl %%edx, 0x5C(%%eax)             \n\t"   /* S = (1.0f, 1.0f, 1.0f) */
        "movl %%edx, 0x60(%%eax)             \n\t"
        "movl %%edx, 0x64(%%eax)             \n\t"
        "movw $1, 0x68(%%eax)                \n\t"   /* +0x68 = 1, +0x69 = 0 */
        "retl                                \n\t"
        "9:                                  \n\t"
        "jmp \"@anim_node_transform@8\"      \n\t"
        : : : "memory"
    );
}
