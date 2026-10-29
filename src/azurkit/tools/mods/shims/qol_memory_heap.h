/* The upper heap (Steps 2.162e, 2.162h, 2.162l): RAM the title's kernel
 * never manages, mapped 1:1 (VA = 0x80000000 | physical) in two tiers.
 * qol_memory_upper64's shim (the mode-0 load runs),
 * qol_memory_upper64_gpu's (the mode-1, GPU runs and their budget
 * compare) and qol_memory_upper256's (T3's probe) all include it.  A build
 * lands a shim once per hook, so the copies share no static data: what
 * they share lives in T2's last page.
 *
 *   T2  VA 0x84000000-0x87FFFFFF, phys 0x04000000-0x07FFFFFF,
 *       PDE[0x210..0x21F]: set up by the first run on a 128 MiB machine
 *       (NV_PFB_CSTATUS 0x08000000) whose kernel leaves it unmapped.
 *   T3  VA 0x88000000-0x8FFFFFFF, phys 0x08000000-0x0FFFFFFF,
 *       PDE[0x220..0x23F]: mapped only by qol_memory_upper256's probe
 *       (upper256_ready), once per boot, on a machine whose RAM reaches
 *       256 MiB (CSTATUS reads 128 MiB there too, so a word is probed).
 *       Without that pack, or below 256 MiB, it stays unmapped and every
 *       run is placed as at 128 MiB.
 *
 * 48 blocks of 4 MiB (T2's 16, then T3's 32: VA 0x84000000 + k * 4 MiB
 * on phys 0x04000000 + k * 4 MiB, PDE[0x210 + k]), each typed by its
 * first run: a CPU block (write-back PDE, 0x...E3) takes mode-0 runs, a
 * GPU block (write-combined, 0x...EB: PWT, PAT entry 1, the flags of the
 * kernel's own view of BAR1) mode-1 runs, which mode-1 runs get from the
 * kernel too (PAGE_WRITECOMBINE).  A block that empties is untyped
 * again; a block that changes type gets its PDE rewritten and its TLB
 * entry dropped (INVLPG), and a write-back block that turns
 * write-combined has the caches written back first (WBINVD), so no line
 * of its old use lands on the GPU's data later.  Block 15 holds T2's
 * state page and block 47 T3's bitmap: both stay CPU.  In T2 a mode-0
 * (CPU) run takes the highest free pages that hold it and a mode-1 (GPU)
 * run the lowest (Step 2.162n, D625): the CPU runs pack from T2's top
 * down and the GPU runs from its bottom up, so the one span between them
 * holds a body's mesh run, which asks after the boot's runs: at a1's save
 * 43.09 MiB, where the first fit (CPU and GPU blocks in turn from the
 * bottom) left 36 and both kinds from the top down 40 (xemu).  A run T2
 * can't hold takes the first fit in T3 (once mapped).
 *
 * State (VA 0x87FFF000, layout 3): +0x00 the mark 'UP64', +0x04 T2's CPU
 * part (placements, frees, pages in use, placements that found no room
 * in T2), +0x14 the layout (3), +0x18 T2's GPU part, +0x28 the 48
 * blocks' types (a byte each: 0 untyped, 1 CPU, 2 GPU); T3's record:
 * +0x58 the mark 'U256' (T3 mapped), +0x5C the probe's verdict (0 not
 * probed, 1 RAM, 2 fold, 3 hole, 4 the kernel's), +0x60 the RAM it found
 * (0x10000000 or 0x08000000), +0x64 T3's CPU part, +0x74 its GPU part.
 * T2's page bitmap (a bit a page) at +0x800; T3's is T3's last page,
 * VA 0x8FFFF000.
 *
 * Ported from Modkit's azurik_mod/patches/qol_memory_upper64/heap.h at the
 * packs oracle's tag.
 */

#ifndef UPPER64_HEAP_H
#define UPPER64_HEAP_H

#define HI_VA        0x84000000u   /* T2: phys 0x04000000-0x07FFFFFF         */
#define HI_PAGES     0x3FFFu       /* pages T2 hands out; its last is the state */
#define T3_VA        0x88000000u   /* T3: phys 0x08000000-0x0FFFFFFF         */
#define T3_PAGES     0x7FFFu       /* pages T3 hands out; its last is its bitmap */
#define RAM_128      0x08000000u
#define RAM_256      0x10000000u
#define PDE_BLOCKS   16            /* T2's blocks                            */
#define ALL_BLOCKS   48            /* T2's and T3's                          */
#define BLOCK_SHIFT  10            /* 4 MiB: 1024 pages a block */
#define PDE_WB       0x040000E3u   /* 4 MiB page, present, writable, A, D    */
#define PDE_WC       0x040000EBu   /* the same, write-combined (PWT)         */
#define PDE_UC       0x040000FBu   /* the same, uncached (PCD, PWT): the probe */
#define PDE_STEP     0x00400000u
#define MAGIC        0x34365055u   /* 'UP64': this boot's heap is set up     */
#define T3_MAGIC     0x36353255u   /* 'U256': this boot's T3 is mapped       */
#define LAYOUT       3u

#define UNTYPED      0
#define CPU          1             /* mode-0 runs (qol_memory_upper64)       */
#define GPU          2             /* mode-1 runs (qol_memory_upper64_gpu)   */

#define PROBE_RAM    1             /* the probe's verdicts                   */
#define PROBE_FOLD   2
#define PROBE_HOLE   3
#define PROBE_KERNEL 4

/* NV_PFB_CSTATUS: the RAM's size in bytes (0x04000000 or 0x08000000; a
 * 256 MiB xemu reads 0x08000000 too). */
#define CSTATUS      (*(volatile u32 *)0xFD10020Cu)
/* PDE[0x210..0x23F], VA 0x84000000-0x8FFFFFFF, through the self-map. */
#define PDE_HI       ((volatile u32 *)0xC0300840u)

typedef struct {
    u32 allocs;     /* placements in the tier   */
    u32 frees;      /* tier runs freed          */
    u32 pages;      /* tier pages in use        */
    u32 nofit;      /* placements with no room in the tier */
} Upper64Part;

typedef struct {
    u32 magic;
    Upper64Part cpu;
    u32 layout;
    Upper64Part gpu;
    u8 type[ALL_BLOCKS];
    u32 t3_magic;
    u32 verdict;
    u32 ram;
    Upper64Part t3_cpu;
    Upper64Part t3_gpu;
} Upper64;

#define STATE        ((Upper64 *)(HI_VA + (HI_PAGES << 12)))
#define BITMAP       ((u32 *)(HI_VA + (HI_PAGES << 12) + 0x800u))
#define T3_BITMAP    ((u32 *)(T3_VA + (T3_PAGES << 12)))
/* The probe's words: W2 in T2's state page (phys 0x07FFF7FC) and its
 * alias 128 MiB up (phys 0x0FFFF7FC, in T3's bitmap page). */
#define W2           (*(volatile u32 *)(HI_VA + (HI_PAGES << 12) + 0x7FCu))
#define W2_ALIAS     (*(volatile u32 *)(T3_VA + (T3_PAGES << 12) + 0x7FCu))

/* 1 when this boot's heap is set up: its last PDE the setup's (block 15
 * is never retyped) and its mark there; never on a 64 MiB machine (the
 * PDE is 0) or under a kernel that maps the range itself. */
static int upper64_mapped(void)
{
    return PDE_HI[PDE_BLOCKS - 1] == PDE_WB + (PDE_BLOCKS - 1) * PDE_STEP
        && STATE->magic == MAGIC;
}

/* 1 when this boot's T3 is mapped: T2 set up, T3's last PDE the probe's
 * (block 47 is never retyped) and T3's mark there. */
static int upper256_mapped(void)
{
    return upper64_mapped()
        && PDE_HI[ALL_BLOCKS - 1] == PDE_WB + (ALL_BLOCKS - 1) * PDE_STEP
        && STATE->t3_magic == T3_MAGIC;
}

/* The heap, set up by the first caller on a 128 MiB machine whose kernel
 * leaves VA 0x84000000 unmapped: 1, or 0 for no heap. */
static int upper64_ready(void)
{
    u32 k, flags;

    if (upper64_mapped())
        return 1;
    if (CSTATUS < RAM_128)
        return 0;                   /* a 64 MiB machine */
    for (k = 0; k < PDE_BLOCKS; k++)
        if (PDE_HI[k])
            return 0;               /* the kernel maps it: its RAM */
    __asm__ volatile ("pushfl\n\tpopl %0\n\tcli" : "=r"(flags) : : "memory");
    for (k = 0; k < PDE_BLOCKS; k++)
        PDE_HI[k] = PDE_WB + k * PDE_STEP;
    __asm__ volatile ("movl %%cr3, %%eax\n\tmovl %%eax, %%cr3" : : : "eax", "memory");
    for (k = 0; k < 0x1000u / 4; k++)
        ((volatile u32 *)STATE)[k] = 0;
    STATE->layout = LAYOUT;
    STATE->type[PDE_BLOCKS - 1] = CPU;
    STATE->magic = MAGIC;
    __asm__ volatile ("pushl %0\n\tpopfl" : : "r"(flags) : "memory", "cc");
    return 1;
}

/* Gives block ``k`` (0-47) the type ``kind``, its PDE the matching cache
 * type. */
static void upper64_type(u32 k, u32 kind)
{
    u32 pde = (kind == GPU ? PDE_WC : PDE_WB) + k * PDE_STEP;

    STATE->type[k] = (u8)kind;
    if (PDE_HI[k] == pde)
        return;
    PDE_HI[k] = pde;
    __asm__ volatile ("invlpg (%0)" : : "r"(HI_VA + k * PDE_STEP) : "memory");
    if (kind == GPU)
        __asm__ volatile ("wbinvd" : : : "memory");
}

/* A part's counters: tier ``t`` (0 T2, 1 T3), ``kind``'s. */
static Upper64Part *upper64_part(u32 t, u32 kind)
{
    if (t)
        return kind == GPU ? &STATE->t3_gpu : &STATE->t3_cpu;
    return kind == GPU ? &STATE->gpu : &STATE->cpu;
}

/* A fit of ``need`` pages in tier ``t``'s blocks of type ``kind`` or
 * none, or 0: the lowest free pages that hold it, or with ``down`` the
 * highest (the scan from the tier's top).  ``dry``: the fit's address,
 * nothing changed or counted. */
static void *upper64_tier_take(u32 t, u32 need, u32 kind, int dry, int down)
{
    u32 va = t ? T3_VA : HI_VA, pages = t ? T3_PAGES : HI_PAGES;
    u32 first = t ? PDE_BLOCKS : 0, *bmp = t ? T3_BITMAP : BITMAP;
    u8 *type = STATE->type + first;
    Upper64Part *part = upper64_part(t, kind);
    u32 run = 0, i, j, b, k;

    if (need > pages)
        return 0;
    for (k = 0; k < pages; k++) {
        i = down ? pages - 1 - k : k;       /* the page the scan is at */
        b = type[i >> BLOCK_SHIFT];
        if (b != UNTYPED && b != kind) {
            run = 0;                        /* past the block's other end */
            k += down ? i & ((1u << BLOCK_SHIFT) - 1) : ~i & ((1u << BLOCK_SHIFT) - 1);
            continue;
        }
        if ((i & 31) == (down ? 31u : 0u) && bmp[i >> 5] == 0xFFFFFFFFu) {
            run = 0;
            k += 31;
            continue;
        }
        if (bmp[i >> 5] & (1u << (i & 31))) {
            run = 0;
            continue;
        }
        if (++run < need)
            continue;
        if (!down)
            i += 1 - need;                  /* the run's first page */
        if (dry)
            return (void *)(va + (i << 12));
        for (b = i >> BLOCK_SHIFT; b <= (i + need - 1) >> BLOCK_SHIFT; b++)
            if (type[b] == UNTYPED)
                upper64_type(first + b, kind);
        for (j = i; j < i + need; j++)
            bmp[j >> 5] |= 1u << (j & 31);
        part->allocs++;
        part->pages += need;
        return (void *)(va + (i << 12));
    }
    if (!dry)
        part->nofit++;
    return 0;
}

/* ``size``'s pages in T2 (a CPU run's highest fit, a GPU run's lowest),
 * then T3's first fit once it is mapped, or 0; ``dry`` as
 * upper64_tier_take's. */
static void *upper64_take(u32 size, u32 kind, int dry)
{
    u32 need = (size + 0xFFFu) >> 12;
    void *run;

    if (!need)
        return 0;
    run = upper64_tier_take(0, need, kind, dry, kind == CPU);
    if (!run && upper256_mapped())
        run = upper64_tier_take(1, need, kind, dry, 0);
    return run;
}

/* Clears a heap run's pages and untypes each block it empties (cdecl,
 * from the free hooks). */
void upper64_release(u32 run, u32 size)
{
    u32 t = run >= T3_VA, pages = t ? T3_PAGES : HI_PAGES;
    u32 blocks = t ? ALL_BLOCKS - PDE_BLOCKS : PDE_BLOCKS, *bmp = t ? T3_BITMAP : BITMAP;
    u8 *type = STATE->type + (t ? PDE_BLOCKS : 0);
    u32 first = (run - (t ? T3_VA : HI_VA)) >> 12, end = first + ((size + 0xFFFu) >> 12), j, k;
    Upper64Part *part = upper64_part(t, type[first >> BLOCK_SHIFT] == GPU ? GPU : CPU);

    if (end > pages)
        end = pages;
    for (j = first; j < end; j++)
        bmp[j >> 5] &= ~(1u << (j & 31));
    part->frees++;
    part->pages -= end - first;
    for (k = first >> BLOCK_SHIFT; k < blocks - 1 && k <= (end - 1) >> BLOCK_SHIFT; k++) {
        for (j = k << 5; j < (k + 1) << 5 && !bmp[j]; j++)
            ;
        if (j == (k + 1) << 5)
            type[k] = UNTYPED;
    }
}

/* T3, mapped by the first caller on a machine whose RAM reaches 256 MiB:
 * 1, or 0 for none (qol_memory_upper256 only).  Once per boot, with T2
 * set up and PDE[0x220..0x23F] all 0 (else the kernel maps that range:
 * no T3), interrupts off: PDE[0x23F] maps phys 0x0FC00000 uncached for
 * the probe, W2 := 0 written back, then 'U256' and its complement stored
 * at W2's alias 128 MiB up and read back, W2 read after each (from RAM:
 * the caches written back first).  RAM: both read back and W2 still 0.
 * A machine that folds at 128 MiB puts the store on W2 (fold); xemu at
 * 128 MiB drops it (hole).  W2 and PDE[0x23F] are put back either way;
 * on RAM PDE[0x220..0x23F] := phys 0x08000000 + k * 4 MiB write-back, CR3
 * reloaded, T3's bitmap page zeroed and the mark written.  The verdict
 * stays in T2's state page for the boot. */
static int upper256_ready(void)
{
    u32 k, flags, saved, ram, fold;

    if (upper256_mapped())
        return 1;
    if (!upper64_ready() || STATE->verdict)
        return 0;
    for (k = PDE_BLOCKS; k < ALL_BLOCKS; k++)
        if (PDE_HI[k]) {
            STATE->verdict = PROBE_KERNEL;
            return 0;
        }
    __asm__ volatile ("pushfl\n\tpopl %0\n\tcli" : "=r"(flags) : : "memory");
    PDE_HI[ALL_BLOCKS - 1] = PDE_UC + (ALL_BLOCKS - 1) * PDE_STEP;
    __asm__ volatile ("invlpg (%0)" : : "r"(HI_VA + (ALL_BLOCKS - 1) * PDE_STEP) : "memory");
    saved = W2;
    W2 = 0;
    __asm__ volatile ("wbinvd" : : : "memory");
    W2_ALIAS = T3_MAGIC;
    ram = W2_ALIAS == T3_MAGIC;
    fold = W2;
    __asm__ volatile ("wbinvd" : : : "memory");
    W2_ALIAS = ~T3_MAGIC;
    ram = ram && W2_ALIAS == ~T3_MAGIC;
    fold |= W2;
    W2 = saved;
    PDE_HI[ALL_BLOCKS - 1] = 0;
    __asm__ volatile ("invlpg (%0)" : : "r"(HI_VA + (ALL_BLOCKS - 1) * PDE_STEP) : "memory");
    ram = ram && !fold;
    if (ram) {
        for (k = PDE_BLOCKS; k < ALL_BLOCKS; k++)
            PDE_HI[k] = PDE_WB + k * PDE_STEP;
        __asm__ volatile ("movl %%cr3, %%eax\n\tmovl %%eax, %%cr3" : : : "eax", "memory");
        for (k = 0; k < 0x1000u / 4; k++)
            ((volatile u32 *)T3_BITMAP)[k] = 0;
        STATE->type[ALL_BLOCKS - 1] = CPU;
        STATE->t3_magic = T3_MAGIC;
    }
    STATE->ram = ram ? RAM_256 : RAM_128;
    STATE->verdict = ram ? PROBE_RAM : fold ? PROBE_FOLD : PROBE_HOLE;
    __asm__ volatile ("pushl %0\n\tpopfl" : : "r"(flags) : "memory", "cc");
    return (int)ram;
}

#endif
