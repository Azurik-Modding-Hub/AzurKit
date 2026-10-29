/* qol_memory_upper64: the upper 64 MiB of a 128 MiB machine (D520,
 * Step 2.162e).
 *
 * The title's kernel manages 64 MiB on every machine we run, 128 MiB ones
 * too (TotalPhysicalPages 0x4000), so on xemu at mem_limit 128 physical
 * 0x04000000-0x07FFFFFF is RAM nobody uses (real hardware: unmeasured).
 * This shim maps it at VA 0x84000000 through the page directory and puts
 * the virtual (mode-0) load runs there, outside the load budget's counter
 * [0x1BF400], so the low 64 MiB keeps everything else.  On a 64 MiB
 * machine (NV_PFB_CSTATUS 0x04000000), or one whose kernel maps that
 * range itself, it changes nothing.
 *
 * Two hooks, two entry points.  a build lands this object once per
 * hook, so they share no static data: what they share lives in the high
 * heap's last page (its state and a bit a page; qol_memory_heap.h, which
 * qol_memory_upper64_gpu's shim shares, Step 2.162h: the mode-0 runs take
 * the heap's CPU blocks, write-back, and leave its GPU blocks alone).
 *
 *   c_upper64_alloc  replaces the run allocator's (0xA4890) CALL
 *                    run_pages_alloc (0xBAB60) at 0xA490C, its mode-0
 *                    path, which holds the runs' spinlock [0x1BF538]:
 *                    stdcall(4), the size, RET 4.  The first call on a
 *                    128 MiB machine sets the heap up: with interrupts
 *                    off, PDE[0x210..0x21F] := phys 0x04000000 + k * 4 MiB
 *                    as 4 MiB pages, CR3 reloaded, the state page zeroed.
 *                    Then the size's pages in its CPU or untyped blocks
 *                    (T2's highest fit, from its top down, Step 2.162n;
 *                    then T3's first fit once mapped),
 *                    counted neither in [0x1BF400] nor
 *                    against the budget; with no room, or no heap,
 *                    run_pages_alloc as before.
 *   c_upper64_free   replaces the run free's (0xBAD10) CALL VirtualFree at
 *                    0xBAD55, its mode-0 arm, under the same spinlock:
 *                    stdcall(12), RET 12.  A run in the heap (VA
 *                    0x84000000-0x8FFFFFFF: T2, or T3 where
 *                    qol_memory_upper256 mapped it, Step 2.162l) clears
 *                    its pages and leaves EDI (0xBAD10's size) 0, so
 *                    0xBAD5A takes nothing from [0x1BF400], which never
 *                    counted it; any other address (VirtualAlloc's, below
 *                    0x80000000) goes on to VirtualFree.
 *
 * Both releases: the shim names no address of the image (its callees by
 * name, which Europe's map relocates; the hardware's and the page
 * directory's addresses are the same on both).
 *
 * Ported from Modkit's azurik_mod/patches/qol_memory_upper64/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_memory_upper64.o beside it.
 */

#include "azurik_vanilla.h"

#include "qol_memory_heap.h"

__attribute__((stdcall))
void *c_upper64_alloc(u32 size)
{
    void *run = upper64_ready() ? upper64_take(size, CPU, 0) : 0;
    return run ? run : run_pages_alloc(size);
}

__attribute__((naked))
void c_upper64_free(void)
{
    __asm__ volatile (
        "movl 4(%%esp), %%eax                \n\t"   /* the run */
        "subl $0x84000000, %%eax             \n\t"
        "cmpl $0x0C000000, %%eax             \n\t"   /* T2 or T3 */
        "jae 1f                              \n\t"   /* not the heap's */
        "pushl %%edi                         \n\t"   /* its size: 0xBAD10's EDI */
        "pushl 8(%%esp)                      \n\t"   /* the run */
        "calll _upper64_release              \n\t"
        "addl $8, %%esp                      \n\t"
        "xorl %%edi, %%edi                   \n\t"   /* 0xBAD5A takes 0 off [0x1BF400] */
        "movl $1, %%eax                      \n\t"   /* VirtualFree's TRUE */
        "retl $12                            \n\t"
        "1:                                  \n\t"
        "jmp _VirtualFree@12                 \n\t"
        : : : "memory"
    );
}
