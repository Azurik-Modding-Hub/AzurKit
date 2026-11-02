// The site's build files (P7, Step 4.3r4l; X10): a character's build writes its pieces into one OPFS file of its own, so the
// image's Blob is slices of your image and of that file and no process holds the pieces in memory. The file a Save reads
// must outlive the job and can't be deleted under it (reading a gone File throws), and a crashed page's must not stay
// forever, so each holder takes a Web Lock on the file's name, shared: the worker from before the file exists, the page
// from the message that names it. A file is removed only while no one holds it (its exclusive lock granted at once): when
// its build is forgotten, later if it was saved (a download's end can't be seen from a page: SAVED_MS past its Save is the
// default), and at each page's load, which is what removes a crashed page's. The Tools tab's Storage counts them.
export const PREFIX = "azurkit-build-";
export const SAVED_MS = 30 * 60 * 1000;
const holds = new Map();   // a file's name -> this page's hold on it: {release, over: its lock's end}

const folder = () => navigator.storage.getDirectory();

// The page's hold on a named file, from the worker's message: resolved once held, so the worker may let go of its own.
export const hold = (name) => new Promise((held) => {
  if (holds.has(name)) return held();
  const entry = { release: null, over: null };
  holds.set(name, entry);
  entry.over = navigator.locks.request(name, { mode: "shared" }, () => new Promise((release) => {
    entry.release = release;
    held();
  })).catch(() => held());
});

// Remove the file if no page or worker holds it.
const removed = (name) => navigator.locks.request(name, { mode: "exclusive", ifAvailable: true }, async (lock) => {
  if (!lock) return false;
  await (await folder()).removeEntry(name).catch(() => null);
  return true;
});

// This page is done with the file (saved: a download may still be reading it, so later).
export function letGo(name, saved = false) {
  const entry = holds.get(name);
  if (!entry) return;
  if (saved) return void setTimeout(() => letGo(name), SAVED_MS);
  holds.delete(name);
  entry.release?.();
  entry.over.then(() => removed(name)).catch(() => null);
}

// [{name, size}] of the build files this origin keeps; none where OPFS refuses.
export async function listed() {
  const out = [];
  try {
    for await (const [name, handle] of (await folder()).entries()) {
      if (name.startsWith(PREFIX) && handle.kind === "file") out.push({ name, size: (await handle.getFile()).size });
    }
  } catch {}   // no OPFS here (a private window): none kept
  return out;
}

// Every build file no page or worker holds removed: a page's load, a dropped job's, the Tools tab's Clear.
export const sweep = async () => {
  for (const { name } of await listed()) await removed(name).catch(() => null);
};
