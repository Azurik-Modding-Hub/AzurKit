/* qol_save_warp: the save-point warp (D202, RANDOMIZER_PLAN section 7 R2.1).
 *
 * Step R2.1a; seen in xemu (Modkit's README.md).  VAs: Modkit's docs/RE_XBE.md
 * section "Save points, level requests and arrivals".
 *
 * Two hooks, two entry points.  a build lands this object once per
 * hook, so the hooks share no static data: the ritual hook passes the
 * target save point to the arrival hook inside the level request's spot
 * string ("rzwarp:<save-point id>"), which the game's own spot lookup
 * doesn't find (it then uses startspot).
 *
 *   c_save_warp_tick   replaces CALL player_armor_state_tick at 0x8C2EC
 *                      (the player tick 0x8C230): runs it, then watches
 *                      for the ritual: LT held while each of A, B, X and
 *                      Y is pressed.  Power selection needs the power
 *                      (0x83410), so the shim tracks the buttons itself
 *                      and the ritual works with no powers owned.
 *   c_save_warp_load   replaces CALL load_level_from_path at 0x55F80
 *                      (scene_state_tick): runs it, then for a warp
 *                      points the arrival (request +0x08) at the target
 *                      save point's place, as a continue does (0x53487).
 *
 * The return point is one dword in the global map (world +0xE4,
 * global_var_find_or_create), which shared.sav keeps: the 1-based row
 * of ROWS below, 0 = none.
 *
 * Both releases (Step R2.1b): the shim names no address of the image.
 * It calls vanilla functions by name (Europe's address map relocates
 * them), reads the pad through active_controller_state, takes the
 * scene from its hook's argument and keeps its own identity matrix.
 *
 * Ported from Modkit's azurik_mod/patches/qol_save_warp/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_save_warp.o beside it.
 */

#include "azurik_vanilla.h"

/* matrix_to_quat(matrix) takes the matrix in ECX and writes the quaternion
 * through EBX: this loads both, saving EBX, and pops its two arguments. */
static inline __attribute__((naked, stdcall))
void matrix_to_quat_call(const float *matrix, float *quat)
{
    __asm__("pushl %ebx\n\t"
            "movl 8(%esp), %ecx\n\t"
            "movl 12(%esp), %ebx\n\t"
            "calll _matrix_to_quat\n\t"
            "popl %ebx\n\t"
            "retl $8");
}

#define SCENE_WORLD 0x2C   /* the scene's world */
#define W_CRITTER   0xC0   /* the player critter; body centre +0x15C, HP +0x210 */
#define W_REQUEST   0xD8   /* +0x08 arrival place, +0x10 level request, +0x14 save request */
#define W_GRAPH     0xDC   /* node pointers at +0x24 .. +0x28 */
#define W_GLOBALS   0xE4

#define VAR_NAME    "rz_save_warp"
#define SPOT_TAG    "rzwarp:"
#define TOWN_PATH   "levels/town"
#define TOWN_ID     "Temple"

/* "On the platform": the body centre within this of the save point's place. */
#define NEAR_XY2    (2.0f * 2.0f)
#define NEAR_Z      3.0f

typedef unsigned char *(__attribute__((thiscall)) *node_slot_fn)(void *node);

/* A save point with no parent takes the identity (0x70F90 reads the
 * game's own, at 0x1AA800 on USA). */
static const f32 IDENTITY[16] = {1.0f, 0, 0, 0, 0, 1.0f, 0, 0, 0, 0, 1.0f, 0, 0, 0, 0, 1.0f};

/* Every save point but town's (the return) and training_room's (the
 * tutorial), from Modkit's azurik_mod/randomizer/data/generated/<level>.json. */
static const char *const ROWS[][2] = {
    {"levels/air/a1", "a1_1"},      {"levels/air/a3", "A3_2"},
    {"levels/air/a3", "A3_1"},      {"levels/air/a5", "a5_2"},
    {"levels/air/a5", "a5_1"},      {"levels/air/a6", "A6_1"},
    {"levels/death/d1", "D1_1"},    {"levels/death/d1", "D1_2"},
    {"levels/death/d2", "D2_1"},    {"levels/death/d2", "D2_2"},
    {"levels/earth/e2", "e2save_1"}, {"levels/earth/e2", "E2_2"},
    {"levels/earth/e5", "e5_1"},    {"levels/earth/e5", "e5_2"},
    {"levels/earth/e6", "e6_1"},    {"levels/earth/e6", "E6_2"},
    {"levels/earth/e7", "E7_1"},
    {"levels/fire/f1", "F1_1"},     {"levels/fire/f1", "F1_2"},
    {"levels/fire/f2", "F2_1"},     {"levels/fire/f2", "F1_2"},
    {"levels/fire/f2", "F1_3"},
    {"levels/fire/f3", "f3_1"},     {"levels/fire/f3", "F3_2"},
    {"levels/fire/f3", "F3_3"},
    {"levels/fire/f4", "f4_1"},     {"levels/fire/f4", "f4_2"},
    {"levels/fire/f4", "f4_3"},
    {"levels/fire/f6", "F6_1"},     {"levels/fire/f6", "F6_2"},
    {"levels/life", "L1_1"},
    {"levels/water/w1", "w1_1"},    {"levels/water/w1", "W1_2"},
    {"levels/water/w1", "W1_3"},
    {"levels/water/w2", "w2_2"},    {"levels/water/w2", "w2_1"},
    {"levels/water/w2", "W2_3"},
    {"levels/water/w3", "w3_save1"}, {"levels/water/w3", "w3_2"},
    {"levels/water/w4", "W4_1"},    {"levels/water/w4", "w4_2"},
};
#define NROWS ((u32)(sizeof(ROWS) / sizeof(ROWS[0])))

/* ---- small freestanding helpers ------------------------------------ */

static int lower(int c) { return (c >= 'A' && c <= 'Z') ? c + 32 : c; }

static int same(const char *a, const char *b)          /* case-blind */
{
    while (*a && lower(*a) == lower(*b)) { a++; b++; }
    return lower(*a) == lower(*b);
}

static int exact(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static const char *after_prefix(const char *s, const char *p)
{
    while (*p) { if (*s++ != *p++) return 0; }
    return s;
}

static char *copy(char *d, const char *s, int room)
{
    while (*s && room > 1) { *d++ = *s++; room--; }
    *d = 0;
    return d;
}

/* scene_state_tick's scene, which it passes to load_level_from_path:
 * both its callers read it from the game's one scene pointer. */
static unsigned char *world_of_scene(int *scene)
{
    return scene ? *(unsigned char **)((unsigned char *)scene + SCENE_WORLD) : 0;
}

/* ---- save points ----------------------------------------------------- */

/* The save point objects of the level's main graph: slot 15 of each
 * node returns its gameSaveControl (0x671B0), or 0 (0x65710). */
static unsigned char *save_point(unsigned char *world, int *cursor)
{
    unsigned char *graph = *(unsigned char **)(world + W_GRAPH);
    void **it, **end;
    if (!graph) return 0;
    it = *(void ***)(graph + 0x24);
    end = *(void ***)(graph + 0x28);
    for (it += *cursor; it < end; it++) {
        void *node = *it;
        unsigned char *gsc;
        (*cursor)++;
        if (!node) continue;
        gsc = ((node_slot_fn)((*(void ***)node)[15]))(node);
        if (gsc) return gsc;
    }
    return 0;
}

/* Its matrix: the parent's (+0x18, matrix at +0x30), else the identity. */
static const f32 *save_point_matrix(unsigned char *gsc)
{
    unsigned char *parent = *(unsigned char **)(gsc + 0x18);
    return parent ? (const f32 *)(parent + 0x30) : IDENTITY;
}

/* Its place as 0x70F90 builds it: matrix x attributes +0x04..+0x0C. */
static void save_point_pos(unsigned char *gsc, f32 out[3])
{
    const f32 *v = *(const f32 **)(gsc + 0x08);
    const f32 *m = save_point_matrix(gsc);
    f32 x = v[1], y = v[2], z = v[3];
    out[0] = m[0] * x + m[4] * y + m[8] * z + m[12];
    out[1] = m[1] * x + m[5] * y + m[9] * z + m[13];
    out[2] = m[2] * x + m[6] * y + m[10] * z + m[14];
}

/* ---- hook 1: the ritual ---------------------------------------------- */

static u8 g_buttons;    /* A 1, B 2, X 4, Y 8 seen during this LT hold */
static u8 g_tried;      /* the ritual completed during this LT hold */
static u8 g_warped;     /* a warp was posted: keep the LT byte clear */
static char g_request[0x30C];   /* movie +0, level +0x104, spot +0x208 */

static unsigned char *platform_under(unsigned char *world, unsigned char *critter)
{
    const f32 *c = (const f32 *)(critter + 0x15C);
    int cursor = 0;
    unsigned char *gsc;
    while ((gsc = save_point(world, &cursor)) != 0) {
        f32 p[3], dx, dy, dz;
        save_point_pos(gsc, p);
        dx = c[0] - p[0]; dy = c[1] - p[1]; dz = c[2] - p[2];
        if (dz < 0) dz = -dz;
        if (dx * dx + dy * dy <= NEAR_XY2 && dz <= NEAR_Z) return gsc;
    }
    return 0;
}

static void post(unsigned char *request, const char *level, const char *id)
{
    char *spot = g_request + 0x208;
    g_request[0] = 0;
    copy(g_request + 0x104, level, 0x104);
    spot = copy(spot, SPOT_TAG, 0x104);
    copy(spot, id, 0x104 - 7);
    *(char **)(request + 0x10) = g_request;
}

static int is_town(const char *level)
{
    return same(level, TOWN_PATH);
}

static int ritual(unsigned char *world)
{
    unsigned char *critter = *(unsigned char **)(world + W_CRITTER);
    unsigned char *request = *(unsigned char **)(world + W_REQUEST);
    const char *level = (const char *)world;   /* the current level path */
    unsigned char *gsc;
    u32 *var;
    u32 row;

    if (!critter || !request) return 0;
    if (*(int *)(critter + 0x210) <= 0) return 0;              /* dead */
    if (*(void **)(request + 0x10) || *(void **)(request + 0x14)) return 0;
    gsc = platform_under(world, critter);
    if (!gsc) return 0;
    var = global_var_find_or_create(*(void **)(world + W_GLOBALS), VAR_NAME);
    if (!var) return 0;

    if (is_town(level)) {                       /* the return trip */
        row = *var;
        if (row == 0 || row > NROWS) return 0;
        *var = 0;
        post(request, ROWS[row - 1][0], ROWS[row - 1][1]);
        return 1;
    }
    for (row = 0; row < NROWS; row++) {         /* the trip out */
        if (same(level, ROWS[row][0]) && exact((const char *)(gsc + 0x22), ROWS[row][1])) {
            *var = row + 1;
            post(request, TOWN_PATH, TOWN_ID);
            return 1;
        }
    }
    return 0;
}

__attribute__((stdcall))
void c_save_warp_tick(void *armor_mgr)
{
    unsigned char *am = (unsigned char *)armor_mgr;
    ControllerState *cs;

    player_armor_state_tick(armor_mgr);

    cs = active_controller_state();
    if (!(cs->trigger_left > 0.0f)) {
        g_buttons = 0; g_tried = 0; g_warped = 0;
        return;
    }
    if (g_warped) {             /* no cast and no armor drop on LT's release */
        am[0x0C] = 0;
        *(u32 *)(am + 0x10) = 0;
        return;
    }
    if (cs->button_a > 0.0f) g_buttons |= 1;
    if (cs->button_b > 0.0f) g_buttons |= 2;
    if (cs->button_x > 0.0f) g_buttons |= 4;
    if (cs->button_y > 0.0f) g_buttons |= 8;
    if (g_buttons != 0x0F || g_tried) return;
    g_tried = 1;
    if (ritual(*(unsigned char **)am)) {        /* armor_mgr +0 is the world */
        g_warped = 1;
        am[0x0C] = 0;
        *(u32 *)(am + 0x10) = 0;
    }
}

/* ---- hook 2: the arrival --------------------------------------------- */

static f32 g_place[8];   /* pos[3], quat[4], cell (u16) + pad */

__attribute__((stdcall))
void c_save_warp_load(int *scene, const char *path, const char *spot, char is_movie)
{
    const char *id;
    unsigned char *world, *gsc;
    int cursor = 0;

    load_level_from_path(scene, path, spot, is_movie);
    if (is_movie || !spot) return;
    id = after_prefix(spot, SPOT_TAG);
    if (!id) return;
    world = world_of_scene(scene);
    if (!world) return;
    while ((gsc = save_point(world, &cursor)) != 0) {
        if (exact((const char *)(gsc + 0x22), id)) {
            save_point_pos(gsc, g_place);
            matrix_to_quat_call(save_point_matrix(gsc), g_place + 3);
            *(u16 *)(g_place + 7) = *(u16 *)(gsc + 0x20);
            *(f32 **)(*(unsigned char **)(world + W_REQUEST) + 0x08) = g_place;
            return;
        }
    }
}
