/* A file's md5 on the site (web/hasher.mjs): a level file's filelist.txt line, as
 * WebCrypto has no md5. RFC 1321 over the bytes the page copies into md5_buffer. No
 * libc: wasm32 is little-endian and reads a word at any address. */

#include <stdint.h>

#define EXPORT(name) __attribute__((export_name(name)))
#define CHUNK (1u << 20)   /* web/hasher.mjs's */

static unsigned char buffer[CHUNK + 128];   /* room for the padding past a last chunk */
static uint32_t state[4];
static uint64_t total;

#define F(x, y, z) ((z) ^ ((x) & ((y) ^ (z))))
#define G(x, y, z) ((y) ^ ((z) & ((x) ^ (y))))
#define H(x, y, z) ((x) ^ (y) ^ (z))
#define I(x, y, z) ((y) ^ ((x) | ~(z)))
#define STEP(f, a, b, c, d, g, k, s) \
  a += f(b, c, d) + x[g] + k;        \
  a = ((a << s) | (a >> (32 - s))) + b

static void blocks(const unsigned char *at, uint32_t n) {
  uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
  for (; n; n--, at += 64) {
    const uint32_t *x = (const uint32_t *)at, A = a, B = b, C = c, D = d;
    STEP(F, a, b, c, d, 0, 0xd76aa478, 7);
    STEP(F, d, a, b, c, 1, 0xe8c7b756, 12);
    STEP(F, c, d, a, b, 2, 0x242070db, 17);
    STEP(F, b, c, d, a, 3, 0xc1bdceee, 22);
    STEP(F, a, b, c, d, 4, 0xf57c0faf, 7);
    STEP(F, d, a, b, c, 5, 0x4787c62a, 12);
    STEP(F, c, d, a, b, 6, 0xa8304613, 17);
    STEP(F, b, c, d, a, 7, 0xfd469501, 22);
    STEP(F, a, b, c, d, 8, 0x698098d8, 7);
    STEP(F, d, a, b, c, 9, 0x8b44f7af, 12);
    STEP(F, c, d, a, b, 10, 0xffff5bb1, 17);
    STEP(F, b, c, d, a, 11, 0x895cd7be, 22);
    STEP(F, a, b, c, d, 12, 0x6b901122, 7);
    STEP(F, d, a, b, c, 13, 0xfd987193, 12);
    STEP(F, c, d, a, b, 14, 0xa679438e, 17);
    STEP(F, b, c, d, a, 15, 0x49b40821, 22);
    STEP(G, a, b, c, d, 1, 0xf61e2562, 5);
    STEP(G, d, a, b, c, 6, 0xc040b340, 9);
    STEP(G, c, d, a, b, 11, 0x265e5a51, 14);
    STEP(G, b, c, d, a, 0, 0xe9b6c7aa, 20);
    STEP(G, a, b, c, d, 5, 0xd62f105d, 5);
    STEP(G, d, a, b, c, 10, 0x02441453, 9);
    STEP(G, c, d, a, b, 15, 0xd8a1e681, 14);
    STEP(G, b, c, d, a, 4, 0xe7d3fbc8, 20);
    STEP(G, a, b, c, d, 9, 0x21e1cde6, 5);
    STEP(G, d, a, b, c, 14, 0xc33707d6, 9);
    STEP(G, c, d, a, b, 3, 0xf4d50d87, 14);
    STEP(G, b, c, d, a, 8, 0x455a14ed, 20);
    STEP(G, a, b, c, d, 13, 0xa9e3e905, 5);
    STEP(G, d, a, b, c, 2, 0xfcefa3f8, 9);
    STEP(G, c, d, a, b, 7, 0x676f02d9, 14);
    STEP(G, b, c, d, a, 12, 0x8d2a4c8a, 20);
    STEP(H, a, b, c, d, 5, 0xfffa3942, 4);
    STEP(H, d, a, b, c, 8, 0x8771f681, 11);
    STEP(H, c, d, a, b, 11, 0x6d9d6122, 16);
    STEP(H, b, c, d, a, 14, 0xfde5380c, 23);
    STEP(H, a, b, c, d, 1, 0xa4beea44, 4);
    STEP(H, d, a, b, c, 4, 0x4bdecfa9, 11);
    STEP(H, c, d, a, b, 7, 0xf6bb4b60, 16);
    STEP(H, b, c, d, a, 10, 0xbebfbc70, 23);
    STEP(H, a, b, c, d, 13, 0x289b7ec6, 4);
    STEP(H, d, a, b, c, 0, 0xeaa127fa, 11);
    STEP(H, c, d, a, b, 3, 0xd4ef3085, 16);
    STEP(H, b, c, d, a, 6, 0x04881d05, 23);
    STEP(H, a, b, c, d, 9, 0xd9d4d039, 4);
    STEP(H, d, a, b, c, 12, 0xe6db99e5, 11);
    STEP(H, c, d, a, b, 15, 0x1fa27cf8, 16);
    STEP(H, b, c, d, a, 2, 0xc4ac5665, 23);
    STEP(I, a, b, c, d, 0, 0xf4292244, 6);
    STEP(I, d, a, b, c, 7, 0x432aff97, 10);
    STEP(I, c, d, a, b, 14, 0xab9423a7, 15);
    STEP(I, b, c, d, a, 5, 0xfc93a039, 21);
    STEP(I, a, b, c, d, 12, 0x655b59c3, 6);
    STEP(I, d, a, b, c, 3, 0x8f0ccc92, 10);
    STEP(I, c, d, a, b, 10, 0xffeff47d, 15);
    STEP(I, b, c, d, a, 1, 0x85845dd1, 21);
    STEP(I, a, b, c, d, 8, 0x6fa87e4f, 6);
    STEP(I, d, a, b, c, 15, 0xfe2ce6e0, 10);
    STEP(I, c, d, a, b, 6, 0xa3014314, 15);
    STEP(I, b, c, d, a, 13, 0x4e0811a1, 21);
    STEP(I, a, b, c, d, 4, 0xf7537e82, 6);
    STEP(I, d, a, b, c, 11, 0xbd3af235, 10);
    STEP(I, c, d, a, b, 2, 0x2ad7d2bb, 15);
    STEP(I, b, c, d, a, 9, 0xeb86d391, 21);
    a += A;
    b += B;
    c += C;
    d += D;
  }
  state[0] = a;
  state[1] = b;
  state[2] = c;
  state[3] = d;
}

EXPORT("md5_buffer") unsigned char *md5_buffer(void) { return buffer; }

EXPORT("md5_begin") void md5_begin(void) {
  state[0] = 0x67452301;
  state[1] = 0xefcdab89;
  state[2] = 0x98badcfe;
  state[3] = 0x10325476;
  total = 0;
}

/* The next n bytes of the file, a multiple of 64, from md5_buffer. */
EXPORT("md5_blocks") void md5_blocks(uint32_t n) {
  blocks(buffer, n / 64);
  total += n;
}

/* Its last n bytes (at most CHUNK), from md5_buffer: its 16 bytes' address. */
EXPORT("md5_end") const unsigned char *md5_end(uint32_t n) {
  total += n;
  uint32_t end = n;
  buffer[end++] = 0x80;
  while (end % 64 != 56) buffer[end++] = 0;
  for (uint32_t i = 0; i < 8; i++) buffer[end++] = (unsigned char)((total * 8) >> (8 * i));
  blocks(buffer, end / 64);
  return (const unsigned char *)state;
}
