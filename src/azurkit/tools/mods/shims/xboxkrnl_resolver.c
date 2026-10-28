/* The shared kernel-export resolver: xboxkrnl_resolve_by_ordinal(ordinal)
 * returns the address of the Xbox kernel's export with that ordinal, or 0
 * when it has none.
 *
 * A shim may call a kernel function the game doesn't import (so the XBE's
 * thunk table has no slot for it): its stub asks this resolver once and
 * keeps the answer (Step 4.1f2 lands those stubs). It walks the PE export
 * table of xboxkrnl.exe, which the retail loader maps at 0x80010000 before
 * the game starts. It uses no kernel import, no game function and no
 * globals, and reads each 4-byte field a byte at a time, so it assumes no
 * alignment. cdecl, so its stubs push the ordinal, call it and pop it.
 *
 * Ported from Modkit's shims/shared/xboxkrnl_resolver.c; shimkit builds it
 * into xboxkrnl_resolver.o beside it.
 */

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;

#define XBOXKRNL_BASE_VA  0x80010000u

/* A little-endian u32 at p, read a byte at a time. */
static u32 read_u32(const u8 *p)
{
    return ((u32)p[0])
         | ((u32)p[1] << 8)
         | ((u32)p[2] << 16)
         | ((u32)p[3] << 24);
}

void *xboxkrnl_resolve_by_ordinal(unsigned ordinal)
{
    const u8 *base = (const u8 *)XBOXKRNL_BASE_VA;

    /* The DOS header's e_lfanew (+0x3C) gives the PE header. */
    u32 pe_offset = read_u32(base + 0x3C);
    const u8 *pe  = base + pe_offset;

    /* Past the PE signature (4 bytes) and the file header (20) is the
     * optional header, whose first data directory, the exports, is at
     * +0x60: its address, then its size. */
    const u8 *opt = pe + 4 + 20;

    u32 exp_rva = read_u32(opt + 0x60);
    if (exp_rva == 0) {
        return (void *)0;  /* no export directory */
    }

    const u8 *exp = base + exp_rva;

    /* The export directory: the first ordinal at +0x10, the number of
     * functions at +0x14 and the address of their table at +0x1C. */
    u32 ord_base   = read_u32(exp + 0x10);
    u32 n_funcs    = read_u32(exp + 0x14);
    u32 funcs_rva  = read_u32(exp + 0x1C);

    const u8 *funcs = base + funcs_rva;

    if (ordinal < ord_base) {
        return (void *)0;  /* below the first ordinal */
    }
    u32 idx = ordinal - ord_base;
    if (idx >= n_funcs) {
        return (void *)0;  /* past the last */
    }

    u32 func_rva = read_u32(funcs + idx * 4);
    if (func_rva == 0) {
        return (void *)0;  /* an empty slot */
    }
    return (void *)(base + func_rva);
}
