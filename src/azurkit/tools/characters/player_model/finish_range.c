/* X50: the magic finisher's line is met on the level (Step 2.202b;
 * AZ-803, D829, the owner: "Blast where it hits, beam beyond").
 *
 * Why.  W40 makes the transition search 0x7EF10 call a target long range
 * past the build's line, the finish column's blast box's far face ahead
 * of the feet (finish_line), so row 30 (basic3 -> finish3, the beam)
 * plays past it and row 31 (finish, the blast) nearer.  The search
 * compares its finder's distance less radius (the result's +0x18), the
 * bounds centres' distance, which counts the height between them: f6's
 * blaze sentinel's centre stands about 1.0 m over the player's, so at
 * the line the sentinel's side was still 0.15-0.3 m short of the box's
 * face and the beam's 28-30 HP played where the blast's 84-97 hits
 * (Step 2.202's record).  The blast hits a target whose side (its centre
 * on the level less its radius) its box's face reaches, whatever the
 * heights (Step 2.202b's sitting, 0.1 m steps on five bodies and two
 * sizes: town_male_6 hit at 1.275 m and missed at 1.375 against its
 * 1.302 m face, Balthazar 1.50 / 1.60 against 1.574, Balthazar x0.7 1.05
 * / 1.15 against 1.102, keylord missed at 1.00 against 0.995).
 *
 * What.  This shim takes the search's `fld dword [esp+0x30]; mov
 * [esp+0x54], esi` at 0x7F0B2 (Europe 0x7F062), 8 bytes, just before its
 * long-range compare `fcomp [0x1A2730]` (0x7F0BA): it stores ESI as the
 * mov did and loads, for a target the finder kept (its count, +0, above
 * 0), its distance less radius on the level: the result's distance less
 * radius less its vector's (+4, x y z) length over that vector's length
 * on the level, so the compare meets the line where the blast meets the
 * target; with none, the result's +0x18 as the game loads it.
 *
 * ABI: inside 0x7EF10's frame the finder's result is at [esp+0x18] (the
 * count, the vector to the target's bounds centre at +4, distance less
 * radius at +0x18), [esp+0x1C] here past the return address.  The value
 * goes in ST0, as the fld left it (a float the C part returns); EAX, ECX
 * and EDX are written before the search reads them again (0x7F0C0's
 * fnstsw, 0x7F0CF-0x7F0DA); EBX, ESI, EDI and EBP kept.
 */

#define FOUND_VECTOR 0x04   /* the finder's result: the vector to its target's bounds centre */
#define FOUND_DR     0x18   /* ... its distance less radius                                  */

/* The finder's distance less radius on the level, or the game's with no target. */
__attribute__((used))
float finish_range(const char *found)
{
    const float *v = (const float *)(found + FOUND_VECTOR);
    float dr = *(const float *)(found + FOUND_DR), whole, level;

    if (*(const int *)found <= 0)
        return dr;
    whole = v[0] * v[0] + v[1] * v[1] + v[2] * v[2];
    level = v[0] * v[0] + v[1] * v[1];
    __asm__ ("fsqrt" : "=t"(whole) : "0"(whole));   /* x87: no libm */
    __asm__ ("fsqrt" : "=t"(level) : "0"(level));
    return dr - (whole - level);
}

/* 0x7F0B2: the long-range byte's store, and its distance on the level in ST0. */
__attribute__((naked))
void c_player_model_finish_range(void)
{
    __asm__ volatile (
        "movl %%esi, 0x58(%%esp)            \n\t"   /* mov [esp+0x54], esi, past the return address */
        "leal 0x1c(%%esp), %%eax            \n\t"   /* the finder's result */
        "pushl %%eax                        \n\t"
        "calll _finish_range                \n\t"
        "addl $4, %%esp                     \n\t"
        "retl                               \n\t"
        : : : "memory"
    );
}
