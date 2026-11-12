// hashedApart's worker (hasher.mjs): an image's hash in a worker that ends: reading the image through ArrayBuffers left
// up to 1.7 GiB resident in WebKit until a GC came, which an idle thread never asks for (hashed now frees each run's).
// In: {source, rows, longest, yields, wide} (a File or a Blob; hashed's files; its longest run; whether it gives way to
// a character's dress, hasher.mjs's dressed(); its runs joined up to wide once an ask waits on it, none given: longest).
// Out: {done, total} of its bytes, each as read, and {at} (hashed's: where each of its reads is), then {digests} or
// {error}. Its lanes read AHEAD (hasher.mjs: Safari's) ahead.
import { AHEAD, dressed, hashed } from "./hasher.mjs";

self.onmessage = ({ data: { source, rows, longest, yields, wide } }) => {
  hashed(source, rows, (done, total) => self.postMessage({ done, total }), longest, (at) => self.postMessage({ at }),
    AHEAD, yields ? dressed : null, wide ?? longest).then(
    (digests) => self.postMessage({ digests }), (error) => self.postMessage({ error: String(error?.message ?? error) }));
};
