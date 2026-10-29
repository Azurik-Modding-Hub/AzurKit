/* qol_memory_upper64_gpu: the GPU's load runs in the upper 64 MiB of a
 * 128 MiB machine (D576, Step 2.162h), on top of qol_memory_upper64.
 *
 * The run allocator's contiguous (mode-1) runs are the GPU's data:
 * textures, meshes and push buffers.  This shim puts them in the upper
 * 64 MiB heap qol_memory_upper64 maps (qol_memory_heap.h: the same page directory
 * entries and state page), in write-combined 4 MiB blocks of their own,
 * outside the load budget's counter [0x1BF400] and past its compare
 * (Step 2.162m), and in T3 above 128 MiB where qol_memory_upper256
 * mapped it (Step 2.162l).  For the GPU to
 * reach them, the 22 (Europe 23) D3D address masks 0x3FFFFFF become
 * 0x0FFFFFFF (the pack's byte sites: the same output below 128 MiB) and
 * D3D's seven DMA objects whose limit is 0x03FFAFFF (textures, vertices,
 * the push buffer's) get 0x0FFFEFFF, T3's top (xemu checks only an
 * offset against it, so it is inert at 128 MiB).  On a 64 MiB machine
 * (NV_PFB_CSTATUS 0x04000000), or one whose kernel maps the range
 * itself, it changes nothing.
 *
 * Four hooks, four entry points (each landing of this object is its
 * own; what they share lives in the heap's last page):
 *
 *   c_upper64_gpu_budget replaces the run allocator's (0xA4890) 6-byte
 *                        `and esi, 0xfffff000` at 0xA48DD (the rounding
 *                        of the run's size; the CALL and a NOP), on its
 *                        mode-1 path before the budget compare
 *                        (0xA48E3-0xA48E7: [0x1BF400] plus the size
 *                        against [0x1BF404]), under the runs' spinlock:
 *                        the and replayed, EAX (the limit) and EDX kept.
 *                        When the rounded size fits the heap (a dry take
 *                        of its GPU blocks, the scan c_upper64_gpu_alloc
 *                        then makes under the same lock: T2, then T3
 *                        once qol_memory_upper256 mapped it), ECX :=
 *                        -size, so 0xA48E3's `add ecx, esi` gives 0 and
 *                        the compare passes (Step 2.162m, D616: a run
 *                        past the budget that fits high loads); else ECX
 *                        ([0x1BF400]) is kept and the compare is
 *                        vanilla's.
 *
 *   c_upper64_gpu_alloc  replaces the run allocator's (0xA4890) CALL
 *                        XPhysicalAlloc (0xF4EB0) at 0xA48FA, its mode-1
 *                        path, under the runs' spinlock [0x1BF538]:
 *                        stdcall(16) (the size, -1, 0x1000, 0x404).  A
 *                        first fit in the heap's GPU or untyped blocks
 *                        (T2's, from its bottom up, below the CPU runs
 *                        that pack from its top down since Step 2.162n;
 *                        then T3's once mapped) returns its VA
 *                        with ESI (0xA4890's rounded size)
 *                        0, so 0xA4903 adds nothing to [0x1BF400];
 *                        with no room, or no heap, XPhysicalAlloc.
 *   c_upper64_gpu_free   replaces the run free's (0xBAD10) CALL
 *                        XPhysicalFree (0xF4F09, the import thunk of
 *                        MmFreeContiguousMemory) at 0xBAD46, its mode-1
 *                        arm: stdcall(4).  A run in this boot's heap
 *                        (T2, or T3 once mapped) clears its pages and
 *                        leaves EDI (0xBAD10's size) 0, so
 *                        0xBAD5A takes nothing off [0x1BF400]; any other
 *                        address goes on to the kernel's
 *                        MmFreeContiguousMemory (through a stub of the
 *                        game's own thunk slot).
 *   c_upper64_gpu_limit  replaces CMiniport_CreateCtxDmaObject's (0x12D4AB)
 *                        9-byte store of its limit argument at 0x12D552
 *                        (`mov eax, [ebp+0x14]; mov [ecx+0x700004], eax`,
 *                        RAMIN + 4): a limit of 0x03FFAFFF becomes
 *                        0x0FFFEFFF (T3's top less its bitmap page) when
 *                        NV_PFB_CSTATUS reads 128 MiB (at 256 too); any
 *                        other, as
 *                        given.  It runs once per object at device
 *                        creation, before any run loads.
 *
 * Both releases: the shim names no address of the image (its callees by
 * name, which Europe's map and kernel thunk table relocate; the
 * hardware's, the page directory's and RAMIN's offsets are the same on
 * both).
 *
 * Ported from Modkit's azurik_mod/patches/qol_memory_upper64_gpu/shim.c at the packs oracle's tag; shimkit builds
 * it into qol_memory_upper64_gpu.o beside it.
 */

#include "azurik_vanilla.h"

#include "qol_memory_heap.h"

/* A mode-1 run's place in the heap, or 0 (cdecl, from c_upper64_gpu_alloc). */
void *upper64_gpu_place(u32 size)
{
    return upper64_ready() ? upper64_take(size, GPU, 0) : 0;
}

__attribute__((naked))
void c_upper64_gpu_alloc(void)
{
    __asm__ volatile (
        "pushl 4(%%esp)                      \n\t"   /* the size (0xA4890's ESI) */
        "calll _upper64_gpu_place            \n\t"
        "addl $4, %%esp                      \n\t"
        "testl %%eax, %%eax                  \n\t"
        "jz 1f                               \n\t"   /* no heap, or no room */
        "xorl %%esi, %%esi                   \n\t"   /* 0xA4903 adds 0 to [0x1BF400] */
        "retl $16                            \n\t"
        "1:                                  \n\t"
        "jmp _XPhysicalAlloc@16              \n\t"
        : : : "memory"
    );
}

/* 1 when a mode-1 run of ``size`` (rounded) bytes fits the heap, T2 or
 * (once mapped) T3, else 0 (cdecl, from c_upper64_gpu_budget). */
int upper64_gpu_fits(u32 size)
{
    return upper64_ready() && upper64_take(size, GPU, 1) != 0;
}

__attribute__((naked))
void c_upper64_gpu_budget(void)
{
    __asm__ volatile (
        "andl $0xFFFFF000, %%esi             \n\t"   /* the replaced and: the rounded size */
        "pushl %%eax                         \n\t"   /* the limit [0x1BF404] */
        "pushl %%ecx                         \n\t"   /* the runs' bytes [0x1BF400] */
        "pushl %%edx                         \n\t"
        "pushl %%esi                         \n\t"
        "calll _upper64_gpu_fits             \n\t"
        "addl $4, %%esp                      \n\t"
        "popl %%edx                          \n\t"
        "popl %%ecx                          \n\t"
        "testl %%eax, %%eax                  \n\t"
        "jz 1f                               \n\t"   /* no heap, or no room: vanilla's compare */
        "movl %%esi, %%ecx                   \n\t"
        "negl %%ecx                          \n\t"   /* 0xA48E3 adds the size back: 0 */
        "1:                                  \n\t"
        "popl %%eax                          \n\t"
        "retl                                \n\t"
        : : : "memory"
    );
}

/* Frees ``run`` when the heap holds it: 1, else 0 (cdecl, from
 * c_upper64_gpu_free).  The tier must be this boot's: a kernel that
 * manages 128 (256) MiB hands out contiguous memory at VA 0x84000000
 * (0x88000000) too. */
int upper64_gpu_unplace(u32 run, u32 size)
{
    if (run - HI_VA < 0x04000000u ? !upper64_mapped()
                                  : run - HI_VA >= 0x0C000000u || !upper256_mapped())
        return 0;
    upper64_release(run, size);
    return 1;
}

__attribute__((naked))
void c_upper64_gpu_free(void)
{
    __asm__ volatile (
        "pushl %%edi                         \n\t"   /* its size: 0xBAD10's EDI */
        "pushl 8(%%esp)                      \n\t"   /* the run */
        "calll _upper64_gpu_unplace          \n\t"
        "addl $8, %%esp                      \n\t"
        "testl %%eax, %%eax                  \n\t"
        "jz 1f                               \n\t"   /* not the heap's */
        "xorl %%edi, %%edi                   \n\t"   /* 0xBAD5A takes 0 off [0x1BF400] */
        "retl $4                             \n\t"
        "1:                                  \n\t"
        "jmp _MmFreeContiguousMemory@4       \n\t"
        : : : "memory"
    );
}

__attribute__((naked))
void c_upper64_gpu_limit(void)
{
    __asm__ volatile (
        "movl 0x14(%%ebp), %%eax             \n\t"   /* the limit it was given */
        "cmpl $0x03FFAFFF, %%eax             \n\t"
        "jne 1f                              \n\t"
        "cmpl $0x08000000, 0xFD10020C        \n\t"   /* NV_PFB_CSTATUS: 128 MiB */
        "jb 1f                               \n\t"
        "movl $0x0FFFEFFF, %%eax             \n\t"   /* T3's top less its bitmap page */
        "1:                                  \n\t"
        "movl %%eax, 0x700004(%%ecx)         \n\t"   /* RAMIN + 4: the object's limit */
        "retl                                \n\t"
        : : : "memory"
    );
}
