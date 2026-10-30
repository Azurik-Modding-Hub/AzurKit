/* qol_alloc_race: the copy thread's out-of-memory evictions go through main
 * (AZ-817, Step 2.172g).
 *
 * The run lists (the expiry wheel 0x37BD00's 30 slots, the expired list
 * 0x1AA7F0) have no lock; main advances, touches and evicts them every
 * frame.  The DVD-copy thread 0xB0C70 evicts them itself at two places:
 * its stream object's heap failure (0xB5D00's handler loop, 0xB5D35 ->
 * 0xA66A0) and its stream buffer's refused commit (the pack's 0xB54D0
 * loop, AZ-814).  The pack sends both to a door, vanilla's dead
 * evict-all 0xA66C0 (no caller, no reference), jumped to c_copy_gate:
 *
 *   - on main (the movie's stream, 0xD0074), or before main's first
 *     frame (main unknown), it evicts at once: vanilla's 0xA64D0(size, 3);
 *   - while main sleeps in its wait on the copy (0xB14E1), it evicts at
 *     once, and main's wake (OP_WAKE) waits until it is done: main wakes
 *     only on the copy thread's own PulseEvent (0xB0D49, 0xB0DBE), which
 *     can come just before this open (the previous copy's), so "parked"
 *     may mean "pulsed, not yet run"; holding main at its wake keeps it
 *     off the lists either way;
 *   - else it asks main and sleeps 1 ms at a time: main's frame
 *     (c_main_tick, the main loop's run-manager tick, 0x59C90) evicts
 *     the size on main and hands back the answer;
 *   - if neither comes within TRIES sleeps (main busy in a load that
 *     doesn't wait on this copy, or at exit, where main waits on the
 *     copy thread's handle) it evicts itself, vanilla's way.
 *
 * No wait here can deadlock: the copy thread holds no lock at either
 * site (0xB06B0 calls 0xB5D00 with none; the buffer loop releases the
 * page lock first; the copy mutex [0x1BEFE0] is released around the
 * copy, 0xB0D10/0xB0D8F), so main's eviction never waits on it; our
 * own lock is held for a few instructions, never across an eviction or
 * a sleep, and main's tick only tries it.  Main's wake waits only on an
 * eviction the copy thread began while main was parked, holding what it
 * held asleep (its wait gave up the copy mutex; it takes it again only
 * at 0xB14EF, after the wake): an eviction that needed any of it would
 * hang the same with main still asleep, as vanilla's does.  Other threads'
 * out-of-memory evictions (malloc's and operator new's handler table
 * [0x1BEF80], D3D's 0x906A0 at boot) stay vanilla: their threads may
 * hold a lock (the sound lock [0x1BEFAC] around the sound thread's
 * work) that main's eviction can need (an asset's unload callback), so
 * asking main there could deadlock.
 *
 * Three entry points; apply_pack lands this object once per hook, so the
 * state lives in the door's landing and the other two reach it through
 * the door (run_evict_all, 0xA66C0) with an op in ECX:
 *
 *   c_copy_gate        the door's JMP target (fastcall, ECX = bytes or an
 *                      op; AL = 1 when something was freed; plain RET).
 *   c_main_tick        replaces the main loop's CALL of the wheel advance
 *                      0xA62B0 at 0x59C90: OP_TICK, then the advance.
 *   c_main_park_wait   replaces 0xB13B0's CALL SignalObjectAndWait at
 *                      0xB14E1 (stdcall(16)): OP_PARK, the wait, OP_WAKE.
 *
 * Both releases: the shim calls vanilla functions by name, which Europe's
 * map relocates, and names no address of the image.
 *
 * Ported from Modkit's azurik_mod/patches/qol_alloc_race/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_alloc_race.o beside it.
 */

#include "azurik_vanilla.h"

#define OP_TICK  0xFFFFFFFDu   /* main's frame: learn main, serve an ask */
#define OP_PARK  0xFFFFFFFEu   /* main is about to sleep in its wait on the copy */
#define OP_WAKE  0xFFFFFFFFu   /* main is back from it */
#define TRIES    500           /* 1 ms sleeps (about half a second) before the copy evicts itself */
#define LEVEL    3             /* 0xA66A0's: the expired list, then the wheel's slots */

enum { IDLE, ASKED, TAKEN, SERVED };

static volatile u32 g_lock;     /* our state's spinlock: held for a few instructions, never across an eviction */
static volatile u32 g_main;     /* main's KTHREAD (fs:[0x28]) from its first frame; 0 before */
static volatile u32 g_parked;   /* main sleeps in 0xB14E1's wait (or was pulsed and hasn't woken) */
static volatile u32 g_busy;     /* the copy thread's evictions begun while main was parked */
static volatile u32 g_state;    /* IDLE, ASKED (g_size wanted), TAKEN (main evicting), SERVED (g_freed) */
static volatile u32 g_size;
static volatile u32 g_freed;

static u32 current_thread(void)
{
    u32 thread;
    __asm__ volatile ("movl %%fs:0x28, %0" : "=r"(thread));
    return thread;
}

static int try_take(void)
{
    return !__atomic_exchange_n(&g_lock, 1, __ATOMIC_ACQUIRE);
}

static void take(void)
{
    while (!try_take())
        Sleep(1);                      /* not 0: a holder of lower priority gets to run */
}

static void give(void)
{
    __atomic_store_n(&g_lock, 0, __ATOMIC_RELEASE);
}

static u8 evict(u32 size)
{
    return run_evict_until(size, LEVEL);
}

/* With the lock held, main parked: evict on this thread, main held at its
 * wake until done (g_busy is set before the lock goes, so a wake that
 * takes it next sees it). */
static u8 evict_parked(u32 size)
{
    u8 freed;

    g_busy++;
    give();
    freed = evict(size);
    __atomic_sub_fetch(&g_busy, 1, __ATOMIC_RELEASE);
    return freed;
}

/* Main's frame: an ask is taken under the lock and evicted outside it. */
static void serve(u32 me)
{
    u32 size;

    g_main = me;
    if (!try_take())
        return;                        /* the copy thread holds it for a few instructions: next frame */
    if (g_state != ASKED) {
        give();
        return;
    }
    g_state = TAKEN;
    size = g_size;
    give();
    size = evict(size);
    take();
    g_freed = size;
    g_state = SERVED;
    give();
}

__attribute__((fastcall))
u8 c_copy_gate(u32 size)
{
    u32 me = current_thread();
    int asked = 0, i;
    u8 freed;

    if (size >= OP_TICK) {
        if (size == OP_TICK)
            serve(me);
        else if (me == g_main) {
            take();
            while (size == OP_WAKE && g_busy) {
                give();                /* the copy thread evicts: main stays off the lists */
                Sleep(1);
                take();
            }
            g_parked = size == OP_PARK;
            give();
        }
        return 0;
    }
    if (!g_main || me == g_main)
        return evict(size);
    for (i = 0; i < TRIES; i++) {
        take();
        if (asked && g_state == SERVED) {
            freed = (u8)g_freed;
            g_state = IDLE;
            give();
            return freed;
        }
        if (g_parked && (!asked || g_state == ASKED)) {
            if (asked)
                g_state = IDLE;        /* withdrawn before main took it */
            return evict_parked(size);
        }
        if (!asked && g_state == IDLE) {
            g_size = size;
            g_state = ASKED;
            asked = 1;
        }
        give();
        Sleep(1);
    }
    for (;;) {
        take();
        if (!asked || g_state == ASKED) {
            if (asked)
                g_state = IDLE;
            give();
            return evict(size);        /* main neither came nor slept on us: vanilla's way */
        }
        if (g_state == SERVED) {
            freed = (u8)g_freed;
            g_state = IDLE;
            give();
            return freed;
        }
        give();                        /* TAKEN: main is evicting for us now */
        Sleep(1);
    }
}

void c_main_tick(void)
{
    run_evict_all(OP_TICK);
    run_wheel_advance();
}

__attribute__((stdcall))
int c_main_park_wait(int signal, int wait, unsigned int ms, int alertable)
{
    int r;

    run_evict_all(OP_PARK);
    r = SignalObjectAndWait(signal, wait, ms, alertable);
    run_evict_all(OP_WAKE);
    return r;
}
