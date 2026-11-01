// The tracker's pictures (Step 4.3f, D961): the level maps, the world map and the item icons, Modkit's own files,
// drawn once from the game (scripts/record_goldens.py's art family: the engine's sdk.art, Modkit's drawing) and
// shipped with the page in art/<version>/, the drawing's version (the tracker's world.art.version). No image is needed
// and nothing is drawn: the site reads art/index.json and its maps.json, the app api/art (the same files, in its
// bundle), and a picture is read from art/<version>/<name>.png the first time it shows. A coarse level's floors ship
// again finer (Step 4.3l, Modkit's detail pictures: index.json's detail, {level: how many times finer}), each read
// from art/<version>/detail/<floor>.png only when its map is zoomed near its own pixels, one held at a time.
//
// Each level's floor table (Step 4.3's floors: art/<version>/floors.json, the art's maps.storeys), which Live's Follow
// reads for the floor under the player, is read the first time Follow asks for one.
//
// artStore({app, changed}) -> {status, load(), bitmap(name), detail(name), drop(), floors(level)}: status is {version,
// error, levels: {level: maps.json entry}, index (maps.json), icons: [name], detail: {level: factor}}, read once by
// load(), which runs changed() once it is.
export function artStore({ app, changed }) {
  const status = { version: null, error: null, levels: {}, index: null, icons: null, detail: {} };
  const bitmaps = new Map();   // name -> Promise<ImageBitmap | null>
  const tables = new Map();    // level -> Promise<its floor table | null>
  let loading = null, held = null;   // held: the detail picture kept, {name, read: Promise<{bitmap, error}>}
  let shippedFloors = null;    // floors.json, read once

  const json = async (url, init) => {
    const reply = await fetch(url, init);
    if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
    return reply.json();
  };
  const read = async () => {
    try {
      const shipped = app ? await json("api/art", { method: "POST", headers: { "Content-Type": "application/json" },
                                                     body: "{}" })
        : await json("art/index.json");
      const index = app ? shipped.index : await json(`art/${shipped.version}/maps.json`);
      Object.assign(status, { version: shipped.version, index, levels: index?.levels ?? {}, icons: shipped.icons,
                              detail: shipped.detail ?? {} });
    } catch (error) {   // the grid and the chips show instead
      status.error = `The maps couldn't be read: ${error?.message ?? error}`;
    }
    changed();
  };

  return {
    status,
    load: () => loading ??= read(),
    // A picture as a bitmap (null: there is none), read once.
    bitmap: (name) => {
      if (!bitmaps.has(name)) {
        bitmaps.set(name, (async () => {
          try {
            const reply = await fetch(`art/${status.version}/${name}.png`);
            if (reply.ok) return await createImageBitmap(await reply.blob());
          } catch {}
          return null;
        })());
      }
      return bitmaps.get(name);
    },
    // A floor's detail picture: {bitmap} (null and why: {bitmap: null, error}), the one held; asking another's
    // closes it (the browser's cache keeps the file).
    detail: (name) => {
      if (held?.name === name) return held.read;
      held?.read.then(({ bitmap }) => bitmap?.close());
      held = { name, read: (async () => {
        try {
          const reply = await fetch(`art/${status.version}/detail/${name}.png`);
          if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
          return { bitmap: await createImageBitmap(await reply.blob()), error: null };
        } catch (error) {
          return { bitmap: null, error: error?.message ?? String(error) };
        }
      })() };
      return held.read;
    },
    drop: () => {   // the held detail picture closed (another level shows)
      held?.read.then(({ bitmap }) => bitmap?.close());
      held = null;
    },
    // A level's floor table (decodeFloors), read once (null: none, or it couldn't be read).
    floors: (level) => {
      if (!tables.has(level)) {
        tables.set(level, (async () => {
          try {
            shippedFloors ??= json(`art/${status.version}/floors.json`);
            const all = await shippedFloors, e = status.levels[level];
            return all.levels?.[level] && e ? await decodeFloors(all.levels[level], e.size[0], e.size[1], all.unit) : null;
          } catch {
            return null;
          }
        })());
      }
      return tables.get(level);
    },
  };
}

// A level's floor table from floors.json's text (maps.storeys' packing: zlib's deflate of each pixel's code, 0 no
// storey, k + 1 all on floor k, 255 on several; each 255 pixel's count; then those storeys' lowest tops as steps, low
// bytes then high, their heights and their floors), as {w, h, code, first, count, lo, hi, floor}: a 255 pixel p's
// storeys are first[p] .. first[p] + count[p] - 1, lo and hi in metres.
export async function decodeFloors(text, w, h, unit) {
  const zipped = Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
  const raw = new Uint8Array(await new Response(new Blob([zipped]).stream()
    .pipeThrough(new DecompressionStream("deflate"))).arrayBuffer());
  const P = w * h, code = raw.subarray(0, P), first = new Int32Array(P).fill(-1), count = new Uint8Array(P);
  let m = 0, n = 0;
  for (let p = 0; p < P; p++) {
    if (code[p] !== 255) continue;
    first[p] = n;
    n += count[p] = raw[P + m++];
  }
  const at = P + m, lo = new Float32Array(n), hi = new Float32Array(n);
  for (let i = 0, v = 0; i < n; i++) {
    const step = raw[at + i] | (raw[at + n + i] << 8);
    v += step >= 0x8000 ? step - 0x10000 : step;
    lo[i] = v * unit;
    hi[i] = (v + raw[at + 2 * n + i]) * unit;
  }
  return { w, h, code, first, count, lo, hi, floor: raw.subarray(at + 3 * n, at + 4 * n) };
}
