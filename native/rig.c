/* The rig's tube riders, compiled (D1009, Step 4.55c): tools/characters/jiggle.py's _rides (each rider's skin
 * vertices within its reach, found in a grid of reach-wide cells, nearest cells first, each weighed (1 - d / r2)^2,
 * their sum and the nearest of all, az_rides) and _ridden's mix of a jiggle bone's shares over them (az_ridden).
 * Every operation is its Python twin's, in the twin's order, on doubles, with no contraction, so the two agree bit for
 * bit (tests/test_native.py): the grid's cells and their keys are the twin's floor(p / reach), worked out by its
 * caller; a vertex is its rank in the twin's sorted order, so a tie by vertex is a tie by rank. No libm, no libc, no
 * allocation: the caller passes every buffer. Built by nativekit (C99, zig cc). */
#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef int64_t i64;

static double sq(double x) { return x * x; }   /* fdlibm.sq */

/* The cell (x, y, z) among the ncells keys (3 each, ascending as tuples), or -1. */
static i64 find(const i64 *keys, i64 ncells, i64 x, i64 y, i64 z) {
    i64 lo = 0, hi = ncells;
    while (lo < hi) {
        i64 mid = lo + (hi - lo) / 2;
        const i64 *k = keys + 3 * mid;
        int less = k[0] != x ? k[0] < x : k[1] != y ? k[1] < y : k[2] < z;
        if (less)
            lo = mid + 1;
        else
            hi = mid;
    }
    if (lo < ncells && keys[3 * lo] == x && keys[3 * lo + 1] == y && keys[3 * lo + 2] == z) return lo;
    return -1;
}

/* _rides of nq riders q (3 doubles each, their cells qc, 3 each) over the nf skin vertices fp (3 doubles each, by
 * rank): the cells' keys (ncells, ascending) and their vertices cpts[cstart[c]..cstart[c + 1]) by rank. For each
 * rider, the spans 1, 2, 4, 8 while its weights sum to 0, each cell (a, b, c) of the span's cube in that order, each
 * vertex j of it: d = (p - q)^2 summed x, y, z; d < r2 adds w = (1 - d / r2)^2 to its sum and (j, w) to its list; the
 * least (d, j) is its nearest. Into nstart (nq + 1 offsets), nj and nw (its list: room for cap) and total, bestd and
 * bestj (-1 none) by rider; *need the lists' length. 0; 1 where an index is out of range; 3 where cap is short (the
 * lists unwritten past it: call again with *need). */
API i64 az_rides(const double *fp, i64 nf, const i64 *keys, i64 ncells, const i64 *cstart, const i64 *cpts,
                 const double *q, const i64 *qc, i64 nq, double r2, i64 *nstart, i64 *nj, double *nw, i64 cap,
                 double *total, double *bestd, i64 *bestj, i64 *need) {
    if (cstart[0] != 0 || cstart[ncells] > nf) return 1;
    for (i64 c = 0; c < ncells; c++) {
        if (cstart[c + 1] < cstart[c]) return 1;
        for (i64 e = cstart[c]; e < cstart[c + 1]; e++)
            if (cpts[e] < 0 || cpts[e] >= nf) return 1;
    }
    i64 count = 0;
    for (i64 i = 0; i < nq; i++) {
        const double *p = q + 3 * i;
        const i64 *ci = qc + 3 * i;
        double sum = 0.0, bd = 0.0;
        i64 bj = -1;
        nstart[i] = count;
        for (i64 span = 1; sum == 0.0 && span <= 8; span *= 2)
            for (i64 a = -span; a <= span; a++)
                for (i64 b = -span; b <= span; b++)
                    for (i64 c = -span; c <= span; c++) {
                        i64 cell = find(keys, ncells, ci[0] + a, ci[1] + b, ci[2] + c);
                        if (cell < 0) continue;
                        for (i64 e = cstart[cell]; e < cstart[cell + 1]; e++) {
                            i64 j = cpts[e];
                            const double *s = fp + 3 * j;
                            double d = sq(s[0] - p[0]) + sq(s[1] - p[1]) + sq(s[2] - p[2]);
                            if (d < r2) {
                                double w = sq(1.0 - d / r2);
                                sum += w;
                                if (count < cap) nj[count] = j, nw[count] = w;
                                count++;
                            }
                            if (bj < 0 || d < bd || (d == bd && j < bj)) bd = d, bj = j;
                        }
                    }
        total[i] = sum, bestd[i] = bd, bestj[i] = bj;
    }
    nstart[nq] = count;
    *need = count;
    return count > cap ? 3 : 0;
}

/* _ridden's mix of the shares m (by rank, nf; 0.0 where a vertex has none) over each of nq riders' lists (az_rides'
 * nstart, nj, nw, total, bestj): mixed = the sum of w m[j] in list order from 0.0; with a sum of 0 and a nearest, 1
 * and its share; out[i] mixed / total and got[i] 1 where both are above 0, else got[i] 0. 0, or 1 where an index is
 * out of range. */
API i64 az_ridden(const i64 *nstart, const i64 *nj, const double *nw, const double *total, const i64 *bestj, i64 nq,
                  const double *m, i64 nf, double *out, unsigned char *got) {
    for (i64 i = 0; i < nq; i++) {
        if (nstart[i + 1] < nstart[i] || bestj[i] >= nf) return 1;
        for (i64 e = nstart[i]; e < nstart[i + 1]; e++)
            if (nj[e] < 0 || nj[e] >= nf) return 1;
    }
    for (i64 i = 0; i < nq; i++) {
        double mixed = 0.0, sum = total[i];
        for (i64 e = nstart[i]; e < nstart[i + 1]; e++) mixed += nw[e] * m[nj[e]];
        if (sum == 0.0 && bestj[i] >= 0) sum = 1.0, mixed = m[bestj[i]];
        got[i] = sum > 0.0 && mixed > 0.0;
        out[i] = got[i] ? mixed / sum : 0.0;
    }
    return 0;
}
