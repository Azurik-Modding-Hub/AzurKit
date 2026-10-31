// The tracker's pictures (Step 4.3f, D961): the level maps, the world map and the item icons, Modkit's own files,
// drawn once from the game (scripts/record_goldens.py's art family: the engine's sdk.art, Modkit's drawing) and
// shipped with the page in art/<version>/, the drawing's version (the tracker's world.art.version). No image is needed
// and nothing is drawn: the site reads art/index.json and its maps.json, the app api/art (the same files, in its
// bundle), and a picture is read from art/<version>/<name>.png the first time it shows. A coarse level's floors ship
// again finer (Step 4.3l, Modkit's detail pictures: index.json's detail, {level: how many times finer}), each read
// from art/<version>/detail/<floor>.png only when its map is zoomed near its own pixels, one held at a time.
//
// artStore({app, changed}) -> {status, load(), bitmap(name), detail(name), drop()}: status is {version, error,
// levels: {level: maps.json entry}, index (maps.json), icons: [name], detail: {level: factor}}, read once by load(),
// which runs changed() once it is.
export function artStore({ app, changed }) {
  const status = { version: null, error: null, levels: {}, index: null, icons: null, detail: {} };
  const bitmaps = new Map();   // name -> Promise<ImageBitmap | null>
  let loading = null, held = null;   // held: the detail picture kept, {name, read: Promise<{bitmap, error}>}

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
  };
}
