// hashedApart's worker (hasher.mjs): an image's hash in a worker that ends: reading the image through ArrayBuffers left
// up to 1.7 GiB resident in WebKit until a GC came, which an idle thread never asks for (hashed now frees each run's). In: {source, rows, longest} (a File or a
// Blob; hashed's files; its longest run). Out: {done, total} of its bytes, each as read, and {at} (hashed's: where each
// of its reads is), then {digests} or {error}. Its lanes read AHEAD (hasher.mjs: Safari's) ahead.
import { AHEAD, hashed } from "./hasher.mjs";

self.onmessage = ({ data: { source, rows, longest } }) => {
  hashed(source, rows, (done, total) => self.postMessage({ done, total }), longest, (at) => self.postMessage({ at }),
    AHEAD).then(
    (digests) => self.postMessage({ digests }), (error) => self.postMessage({ error: String(error?.message ?? error) }));
};
