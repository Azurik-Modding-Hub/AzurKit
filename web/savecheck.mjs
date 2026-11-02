// The site's Save's check, in a worker of its own (app.mjs's checkSave): reading the image's 2.9 GB through ArrayBuffers
// leaves up to 1.7 GiB resident in WebKit until a GC comes, which an idle page never asks for. A worker that ends gives it
// back. In: {source, rows} (a File or a Blob; hasher.mjs's files). Out: {done, total} of its bytes, each as read, then
// {digests} or {error}.
import { hashed } from "./hasher.mjs";

self.onmessage = ({ data: { source, rows } }) => {
  hashed(source, rows, (done, total) => self.postMessage({ done, total })).then(
    (digests) => self.postMessage({ digests }), (error) => self.postMessage({ error: String(error?.message ?? error) }));
};
