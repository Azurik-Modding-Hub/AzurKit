// The tracker's pictures (Step 4.3f, D961): the level maps, the world map and the item icons, Modkit's own files,
// drawn once from the game (scripts/record_goldens.py's art family: the engine's sdk.art, Modkit's drawing) and
// shipped with the page in art/<version>/, the drawing's version (the tracker's world.art.version). No image is needed
// and nothing is drawn: the site reads art/index.json and its maps.json, the app api/art (the same files, in its
// bundle), and a picture is read from art/<version>/<name>.png the first time it shows.
//
// artStore({app, changed}) -> {status, load(), bitmap(name)}: status is {version, error, levels: {level: maps.json
// entry}, index (maps.json), icons: [name]}, read once by load(), which runs changed() once it is.
export function artStore({ app, changed }) {
  const status = { version: null, error: null, levels: {}, index: null, icons: null };
  const bitmaps = new Map();   // name -> Promise<ImageBitmap | null>
  let loading = null;

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
      Object.assign(status, { version: shipped.version, index, levels: index?.levels ?? {}, icons: shipped.icons });
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
  };
}
