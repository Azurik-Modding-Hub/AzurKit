// hashedApart's worker (hasher.mjs): an image's hash in a worker that ends: reading the image through ArrayBuffers leaves
// up to 1.7 GiB resident in WebKit until a GC comes, which an idle thread never asks for. In: {source, rows, longest} (a File or a
// Blob; hashed's files; its longest run). Out: {done, total} of its bytes, each as read, then {digests} or {error}.
import { hashed } from "./hasher.mjs";

self.onmessage = ({ data: { source, rows, longest } }) => {
  hashed(source, rows, (done, total) => self.postMessage({ done, total }), longest).then(
    (digests) => self.postMessage({ digests }), (error) => self.postMessage({ error: String(error?.message ?? error) }));
};
