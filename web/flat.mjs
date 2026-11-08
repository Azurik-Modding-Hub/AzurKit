// outputs.mjs's written(): a Blob's bytes into a named build file of this origin's private file system, a run at a time,
// each read whole (FileReaderSync) and written through the file's sync access handle, a worker's: in Firefox that writes
// each run straight to the file, where a Response's Blob of the same 835 MB (a seed's bytes between its three longest
// copies) took 3.7x the CPU and 1.6x the time (Step 4.5q). In: {name, blob, run}. Out: {share} of the bytes after each
// run, then {file} (the file's File) or {error}.
self.onmessage = async ({ data: { name, blob, run } }) => {
  let sync = null;
  try {
    const handle = await (await navigator.storage.getDirectory()).getFileHandle(name, { create: true });
    sync = await handle.createSyncAccessHandle();
    const reader = new FileReaderSync();
    for (let at = 0; at < blob.size;) {
      const wrote = sync.write(new Uint8Array(reader.readAsArrayBuffer(blob.slice(at, at + run))), { at });
      if (!wrote) throw new Error(`the build file took no byte at ${at}`);
      at += wrote;
      self.postMessage({ share: at / blob.size });
    }
    sync.flush();
    sync.close();
    sync = null;
    self.postMessage({ file: await handle.getFile() });
  } catch (error) {
    try {
      sync?.close();
    } catch {}   // the page hears the failure whatever the close says, or it would wait on it for good
    self.postMessage({ error: String(error?.message ?? error) });
  }
};
