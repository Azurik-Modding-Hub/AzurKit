/* qol_memory_upper256: the RAM from 128 to 256 MiB, T3 of the upper heap
 * (D600, Step 2.162l), on top of qol_memory_upper64 and
 * qol_memory_upper64_gpu.  xemu only: v0.16.2 or later at mem_limit 256
 * (Modkit's docs/XEMU_ONLY.md).
 *
 * The run allocator 0xA4890 weighs every contiguous (mode-1) run against
 * the load budget (0xA48CC-0xA48E7: [0x1BF400] plus the rounded size
 * against [0x1BF404]); qol_memory_upper64_gpu's hook at 0xA48DD passes a
 * run that fits the upper heap (Step 2.162m, D616), and its CALL hook at
 * 0xA48FA places it there.  This shim makes T3 part of that heap, once
 * per boot, just before them:
 *
 *   c_upper256_probe   replaces the 6-byte `lea esi, [edi+0xfff]` at
 *                      0xA48D7 (the rounding of the run's size; the CALL
 *                      and a NOP), under the runs' spinlock [0x1BF538]:
 *                      the lea replayed, EAX (the limit), ECX
 *                      ([0x1BF400]) and EDX kept.  upper256_map sets T2
 *                      up as the other hooks do and runs T3's probe once
 *                      per boot (qol_memory_heap.h, upper256_ready), so the fit
 *                      test at 0xA48DD and the take at 0xA48FA see T3
 *                      from the first mode-1 run on.  Below 256 MiB the
 *                      probe finds no RAM and nothing changes.
 *
 * Both releases: the shim names no address of the image (the hardware's
 * and the page directory's addresses are the same on both).
 *
 * Ported from Modkit's azurik_mod/patches/qol_memory_upper256/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_memory_upper256.o beside it.
 */

#include "azurik_vanilla.h"

#include "qol_memory_heap.h"

/* 1 when T3 is mapped (now or earlier this boot), else 0 (cdecl, from
 * c_upper256_probe). */
int upper256_map(void)
{
    return upper256_ready();
}

__attribute__((naked))
void c_upper256_probe(void)
{
    __asm__ volatile (
        "leal 0xfff(%%edi), %%esi            \n\t"   /* the replaced lea */
        "pushl %%eax                         \n\t"   /* the limit [0x1BF404] */
        "pushl %%ecx                         \n\t"   /* the runs' bytes [0x1BF400] */
        "pushl %%edx                         \n\t"
        "calll _upper256_map                 \n\t"
        "popl %%edx                          \n\t"
        "popl %%ecx                          \n\t"
        "popl %%eax                          \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}
