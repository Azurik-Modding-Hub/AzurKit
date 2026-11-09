# Web tool plan: AzurKit in the browser (archive)

> **Archived from Azurik_Modkit's `docs/ToDo/WEB_TOOL_PLAN.md`** (Step
> 4.24d), the plan of 2026-10-10 that the site (`web/`) was built from.
> AzurKit's code cites it as "WEB §n" (`web/app.mjs`, `web/worker.mjs`,
> `src/azurkit/edits/preset.py`, `scripts/web_tools.py`); this file keeps
> §1-§6 under their own numbers. Left out: the preamble, §7 (steps),
> §8 (risks), §9 (owner questions) and §10 (sources), in Modkit's
> history (the private archived repository). It is a record, not a rule:
> AGENTS.md § The two hosts and the code win where they differ, and its
> REORG_PLAN, Q and D ids are Modkit's plan's.

---

## 1. Goal and non-goals

**Goal.** A player who won't install Python, uv or Qt opens a URL, picks their own Azurik ISO, chooses
mods and saves a modded ISO locally. For the same recipe and version, the bytes equal `azurkit build`'s.

**In v1:**
- **Pick a local ISO** and pass the identity gate (D27). The verdict is kept in memory while the page is open.
- **A Mods tab** generated from `sdk.catalog()`, with free number boxes (D23). It holds every live
  non-randomizer pack: 9 of today's 14 [verified, registry dump, the plan's evidence §2].
  `qol_skip_save_signature` is retired (Step 2.37), so WQ-6 is moot.
- **Presets.** Copy a link (URL fragment), export or import `.azurkit.json`, or load the recipe from your own
  AzurKit-built ISO's `/azurkit.json` (Step 4.4) and rebuild it from vanilla.
- **Build, then Save,** with progress and Cancel. A failure names the edit, pack or site (D35).

**Not in v1:**

| Out | Why |
|---|---|
| Randomizer | D7: AzurKit ports it in 4.10; the web follows in W4 |
| Data grid (`config.xbr` cells) | It waits for 4.7; web v2 |
| Compiling shims; pack plugins | zig can't run in a browser, so prebuilt objects only (Q76); a plugin is third-party code in the page |
| External tools, level-editor handoff | D31, Step 4.9; a page can't launch processes |
| Foreign base, `--allow-modded-input` | D27; the same as the hub (§12.7 D) |
| Saves, RE, simulator, MCP | Dev-only, or per-console key material |
| "Changed files only" export | It hands out modified game files; revisit if users ask |
| Remembering the ISO, verdict or file handles across visits | Nothing is stored (§2.3); the gate runs once per page load |
| Mobile | A randomizer build needs a 1.0–1.2 GB wasm heap [verified]. Safari kills a tab that outgrows memory instead of failing the allocation [verified, WebKit bug 221530, 2026-10-10] |
| Any server, account, upload, telemetry or hosted game data | §2 |
| A public preview on Azurik_Modkit's code | That repo is the private oracle (D2); W0 is evidence only |

## 2. Constraints

### 2.1 Legal
- **No game data is hosted, embedded or fetched.**
  - The site is the Pyodide runtime, the AzurKit wheel and HTML/JS/CSS.
  - Before every deploy, the release job runs the §12.3 leak guard over the unpacked wheel and the built site
    (§6.2).
- **The site carries no vanilla bytes (WQ-2).**
  - Today's package holds three kinds of game bytes [verified, legal review E1–E2]:
    - 54 vanilla spans in the registry (292 B, up to 58 B each; `fps_unlock` has 50 of them);
    - module constants read from game code (`player_physics/__init__.py:518, 728, 739`,
      `patching/shim_builder.py:37`);
    - disassembly or decompiler listings in 6 docstrings.
  - AzurKit's package stores each span as sha256 + length. The build has already proven vanilla through the
    full gate, so per-site checks lose nothing.
  - The package holds no byte constant read from game code, and no disassembly or decompiler listing in any
    docstring or comment.
  - If Q67 keeps raw spans for the stand-in XBE, they live only in the public repo's `tests/facts/`, which
    never ships in the wheel or the site.
- **Presets carry the recipe only.** §12.2's manifest records `changes` with raw `before` bytes, and
  `/azurkit.bin` holds whole files [verified, REORG_PLAN §12.2]. So nothing public carries a manifest; presets
  use the share profile (§4.2).
- **Users bring their own copy.** This disclaimer goes under the picker and on an About page:

  > "Unofficial fan tool. Not affiliated with or endorsed by the rights holders of *Azurik: Rise of
  > Perathia* or Xbox. No game files are provided or downloaded: use your own legally obtained copy. Builds
  > stay on your computer and are for personal use; share presets, not ISOs or game files. Provided as is,
  > with no warranty; keep backups of your ISO and saves."

  The site uses no game art, logos, screenshots, fonts, music or text.
- **Licences. Nothing GPL ships.**
  - Q85 (regenerate `azurik_kernel.h`; review the JSON derived from game data) gates public AzurKit, and so
    the site.
  - Prebuilt shim objects (Q76) ship only after Q85 has regenerated that header from our own facts.
    `vendor/xbox-includes` is GPL-2.0 [verified, E5].
  - The Pyodide core tarball has no licence or notice file [verified, E7]. So `web/THIRD_PARTY_NOTICES` is a
    static, reviewed file that lists:
    - Pyodide, MPL-2.0 [verified, GitHub API, 2026-10-10], with a link to the exact source tag
      `https://github.com/pyodide/pyodide/tree/314.0.7`;
    - CPython, PSF-2.0;
    - the Emscripten runtime, MIT/UIUC;
    - every library linked into `pyodide.asm.wasm`, taken from Pyodide 314.0.7's build recipes [unverified
      list];
    - AzurKit, MIT.
- **`qol_skip_save_signature` is retired** (Step 2.37: `save edit --kernel` re-signs an edited save), so WQ-6
  is moot.

### 2.2 Decisions it honours

| Decision | What it means for the web tool |
|---|---|
| D2 | Parity with this repo's goldens G1–G3, through AzurKit's copies of the hash manifests. No new goldens |
| D7 | No randomizer before 4.10; W4 adds its tab |
| D10, D37 | Four new tests, each in its behavior-area file. Parity reuses the parity tests of 4.3 and 4.5 through a `runtime` parameter (§5) |
| D22 | Pyodide 314.x ships CPython 3.14.2 [verified, Pyodide changelog]. AzurKit uses only syntax that Pyodide's Python runs (R4) |
| D23 | Number boxes accept any finite value and carry no HTML `min`/`max`. `tools/mods` re-validates in Python, because JSON turns NaN into `null` |
| D24 | **Pyodide:** the core is a `tools.toml` entry with `tier = "web"` (this amends §6a.3's "no tier key"). `bootstrap.py --with web` fetches it from its GitHub release asset. **Playwright for Python** goes in the default `dev` group. **No browser download:** tests drive an installed Chrome (`channel="chrome"`); ubuntu-24.04 runners ship Chrome 154 [verified, runner-images 20261004, 2026-10-10]. No npm, no bundler |
| D26, D27 | The `web` marker behaves like `vanilla`: selected by default, and a missing Chrome or Pyodide core fails the run (never skips). Modded input is refused; the web has no override |
| D28 | A preset with several layers lists its conflicts before Build |
| D32 | The hub stays Qt. This is a separate, static, serverless product. §12.7's "Why Qt: over web" scored a local-server hub |
| D34 | Extended to every runtime: CPython and Pyodide produce the same bytes (the `runtime` parameter) |
| D35 | Python builds the whole `Image` before any output byte exists; after that, only I/O can fail. Cancel or a failure during a Chromium save calls `abort()`, so the swap file never replaces the target. A failed `<a download>` leaves only the browser's partial-download file, never a file under the final name [inferred; WV-1] |
| D36 | A download always creates a new file. With the save dialog, a target that `isSameEntry` the input handle is refused. If the input has no handle (it came from `<input>`, or from a drop without `getAsFileSystemHandle()`), an existing target whose `getFile()` name, size and `lastModified` all equal the input's is refused too. Chromium writes to a swap file and replaces the target only on `close()` [MDN `createWritable`] |
| D39, D63 | ~~USA only (R2, WQ-5).~~ Superseded by D146: both releases build. Where AzurKit's full tier runs is D63's trust decision for AzurKit as a whole, and the web adds no special case. The hosting origin is WQ-3 |
| D55 | Its twin: in the vanilla tier, the preset of G3 `apply-physics:zero-scales` is built and saved in Chrome, and the CPython test process checks the saved file against its own `azurkit build` of the same preset (REORG Step 4.0 round 2: S2-1, J-1) |
| D61 | The output includes the rewritten `filelist.txt`, so players needn't clear the game's HDD cache |

### 2.3 Privacy
- **The ISO never leaves the machine.**
  - There is no upload code path. Test 4 records every request a build makes.
  - The line under the picker reads: "This page never uploads your ISO. It is read only inside this browser
    tab." The page can't vouch for synced download folders or browser extensions, so it promises only what it
    controls.
- **No third parties.**
  - No analytics, cookies, CDNs, external fonts or third-party scripts.
  - Pyodide is self-hosted, and `loadPyodide` gets explicit same-origin URLs (§6.3).
  - The page sets `<meta name="referrer" content="no-referrer">`.
- **Nothing is stored in v1.** There's no IndexedDB.
  - The verdict lives in memory.
  - The recipe lives in the URL fragment, which browsers never send. `history.replaceState` keeps it
    current, so a reload restores it, and the recipe appears in browser history.
  - The only storage is a `sessionStorage` "build running" flag (§3.8).
  - File handles are never stored. The input is opened in `read` mode, and the page never asks for
    `readwrite` on it (D36).
- **Pages logs visitor IPs** [verified, GitHub docs, 2026-10-10]: GitHub's own servers do, on every Pages site, and
  a site owner can't turn that off. ~~The About page says so.~~ *2026-10-28 (D883, amending D85's note):* the About
  page carries no IP-logging line. AzurKit itself adds no logging, analytics or tracking; the About page may say
  only that, and that the ISO never leaves the player's computer.

## 3. Architecture

### 3.1 Recommended: the AzurKit wheel under Pyodide in a module worker

```
page (main thread)   UI generated from sdk.catalog(); [Build], then [Save ISO…]
   │  postMessage: File + recipe JSON  →          ← progress; segments + per-file sha256
worker (module, started from a blob: URL)   Pyodide 314 + the azurkit wheel; calls azurkit.sdk
   │  directly through Pyodide's proxies (no separate Python adapter)
   │  WORKERFS mount of the user's File → a real path, /in/<name>
   ▼
Python   verify(path) → verdict + stamp;  image(path, recipe, stamp=…) → Image;  Image.segments()
page     Blob([file.slice(a, b) | Uint8Array | zeros …]); the [Save ISO…] click saves it
```

**Why this design:**
- **One engine,** so there is no second implementation to keep in parity.
- **The composed output matched the native sha256 in all three engines** [verified].
- **A small first visit:** about 6–13 MB. Pages serves gzip, not brotli [verified, curl, 2026-10-10];
  whether it gzips the 9.6 MB `.wasm` is checked in W3. Our code adds 582 KB zipped [verified].
- **Measured timings:**
  - A full randomize was planned in 15.5 s (Chrome), 14.4 s (WebKit) and 66.5 s (Firefox), against 6.7 s
    native.
  - Those times exclude the spike's diff pass and the 19–73 s download. In Firefox, pick to saved file took
    218 s [verified, `spike/ff2.log`].
  - All figures are warm-cache on an M2 Ultra. Mods builds read far less; WV-2 measures them.

**JS budget:** ≤ ~600 LOC, with no byte logic [inferred budget]. A review rule in `CONTRIBUTING` says: "code
that decides an output byte lives in Python."

### 3.2 Rejected alternatives

| Alternative | Why not |
|---|---|
| A TypeScript port of the apply step, fed precomputed patches | Fixed packs would be easy, but the randomizer, the shim allocator and the packer for growing files need a second implementation, and D34 would then need permanent cross-runtime checks. Precomputed "before" bytes are game bytes |
| A Rust/wasm core (the `xdvdfs-web` precedent) | A rewrite of AzurKit, against D1 and D10 |
| A server-side build | It uploads a 2.7 GB copyrighted image, costs money to host and breaks the privacy promise |
| A local-server web hub (NiceGUI) | Already scored and rejected for the hub (§12.7: Qt 7.5, web 6.9) |
| OPFS staging or StreamSaver for the output | Unneeded: a composed Blob downloads in all three engines [verified]. OPFS doubles disk use and meets Firefox's default quota of min(10% of disk, 10 GiB) [verified, MDN] |
| Precomputed patches as the engine | Valid only for the exact image and per pack combination: `qol_skip_logo`'s landing VA moves with other shims [verified, the plan's evidence §5]. At most an "instant preset" path later |
| A separate Python adapter shipped in the site | A second layer to keep in sync. The worker calls `azurkit.sdk`, which the 4.8 API snapshot pins |
| A new `Source` type, an injected hasher, or a new `Plan` type | WORKERFS gives the core a real path, and D55's `Image` already is "input + writes + size" (§3.3–§3.4) |
| PyScript | A layer over Pyodide that the page doesn't need |

### 3.3 The core/I-O boundary (amendments to 4.2, 4.3, 4.5 and 4.8)

The worker calls the `azurkit.sdk` functions below. They take and return JSON-shaped data and are pinned by
the 4.8 API snapshot. They are thin re-exports of the `tools/mods` and `edits` functions that the MCP tools
`pack_list` and `pack_build_iso` also call, so §12.1's import contracts hold.
- `catalog()`: packs, params, units, display ranges, vanilla values and descriptions.
- `verify(path, progress)` returns one of three verdicts: vanilla USA (with a stamp), not vanilla (with the
  first differing file), or an AzurKit build (with its recipe).
- `image(path, recipe, progress, *, stamp)` returns D55's `Image`, or raises an exception that names the
  edit, pack or site.
  - `stamp` is the verdict `verify` returned.
  - With a stamp, `image` re-hashes `default.xbe` (as the desktop's stamp path does, `assets/vanilla.py:111-114`
    [verified]) and each file the build reads. On a mismatch it raises `NotVanillaError`.
  - The name avoids §12.2's `plan(layer)`.
- `preset_encode` / `preset_decode` work on the link fragment itself (§4.2).

What the core must provide. None of it changes output bytes.
1. **Paths stay.** WORKERFS gives the core a real path. The spike ran the unmodified reader, `packed()` and
   staging on it in all three engines, `os.path.getsize` and the `platformdirs` import included [verified,
   `spike/web/worker2.mjs:14-40`]. There is no `Source` type. Staging's per-file re-open is a desktop
   performance item for 4.2, not a web requirement.
2. **No threads in the core (4.2).** Hashing and the `filelist.txt` md5s run serially everywhere.
   - Natively the gate takes 0.49 s serially against 0.11 s threaded [verified, the plan's evidence §2, warm
     cache].
   - Today the build stops at `assets/vanilla.py:249` (the 8-thread gate), and `assets/filelist.py:267` (the md5
     pool) would fail next [verified].
   - There is no injected executor and no `sys._emscripten_info` branch.
3. **Nothing CLI-shaped or native on the build path:** no `subprocess`, no `sys.exit` (4.2, Q32) and no `print`
   used as an API.
   - Shim objects come from package data and are never compiled at build time (4.3, Q76; 4.8's exit already
     proves a no-compiler build).
   - Today `xboxkrnl_resolver.o` compiles even with auto-compile off (`shim_session.py:322` [verified]), so
     AzurKit must not inherit that.
4. **`build()` = `pack(image(...))` (4.5).** The CLI and the hub call both; the web calls only `image`.
5. **Byte-safe errors (4.3).**
   - Every exception the core raises to a user names the pack, site, VA, file offset, length and `sha256[:12]`,
     never byte values or hex.
   - Today `apply.py:120`, `apply.py:553` and `shim_builder.py:290` print `got … expected …` as hex [verified,
     E3], and users paste errors into public issues.
   - The page has no "copy diagnostics" button that attaches anything more.

### 3.4 From `Image` to a streamed output
- **Today.** `packed()` returns `Image(iso, writes, size)` [verified, `xiso.py:204–295`].
  - The writes are whole-file `(offset, bytes)` pairs, each laid over the ones before, zero-filled up to
    `size`.
  - A randomizer build lays 46 writes totalling 700 MB, of which only 465 KB differ from the input [verified,
    the plan's evidence].
  - A mods build writes whole files: `default.xbe` (1.79 MB), `config.xbr` (0.57 MB), `filelist.txt`, and any
    level XBR a QoL pack touches. The largest mods-only G3 case changes 5 files, 40.2 MB [verified, the plan's evidence
    §16 item 4].
- **W1 adds one method, `Image.segments()`.**
  - It returns the sorted, non-overlapping cover of `[0, size)` by `Copy(src_off, n)`, `Bytes(data)` and
    `Zero(n)`. Python resolves overlapping writes.
  - `pack()` writes through `segments()`, so D55's existing pin (`tests/test_iso_roundtrip.py:115`) covers it.
  - Writes stay whole files in v1. Range-level writes come only with 4.10's planner, and only if its heap needs
    them.
  - Planning never re-reads the input to diff.
- **JS only concatenates:** `Copy` becomes `file.slice`, `Bytes` a `Uint8Array`, `Zero` zeros. The output can be
  larger than the input: with every pack on, `default.xbe` moves past the end and the image grows by
  1,835,008 B [verified, `measure/maxbuild.py`].
- **Save (two clicks).**
  1. `[Build]` runs verify and image in the worker and creates no file.
  2. The status bar then shows `Ready · <size> · changed: …` and enables `[Save ISO…]`.
  3. That second click is the user gesture. Chromium calls `showSaveFilePicker` inside it and streams the Blob
     into the handle (`createWritable`, with `abort()` on Cancel). Other engines click an `<a download>` inside
     it.

  Nothing opens a picker or starts a download after awaiting the build: `showSaveFilePicker` needs transient
  user activation [verified, MDN, 2026-10-10], and Safari may ignore a scripted download without a gesture
  [unverified, WebKit bug 156056].

  Measured: compose 3–16 ms; `<a download>` 19 s (Chrome) and 73 s (Firefox) [verified, headless; automation
  auto-accepted the download]. The save-dialog path is unmeasured (WV-1).
- **The Blob references the input,** so the UI says "keep the ISO in place until the save finishes". A
  `NotReadableError` gets a clear message (R6).

### 3.5 The identity check (D27)
- **One per-file gate, with 8 MiB reads.**
  - `verify()` takes today's `require_vanilla_iso` shape: the sha256 of `default.xbe` and every vanilla
    `gamedata/` file (43 files, 999 MB), checked against `vanilla_manifest.json` and read through
    `XisoReader.chunks` (8 MiB) [verified, `assets/vanilla.py:171-188`, `xiso.py:159`].
  - The first differing file comes from the same pass.
  - The web never runs the whole-image fast path or `first_difference` (2.6–2.7 GB each). Those use
    `file_digest`'s 256 KiB reads, which run at 72 / 34 / 33 MB/s on WORKERFS (Chrome / WebKit / Firefox):
    about 38 / 81 / 83 s [rates verified; totals inferred].
  - If AzurKit keeps that fast path, it is desktop-only.
- **Speed.** 8 MiB reads ran at 137 / 147 / 44 MB/s, so the gate takes about 7 / 7 / 23 s [throughput verified;
  totals inferred; warm cache, M2 Ultra].
- **Python hashlib only.** WebCrypto (412 / 462 / 130 MB/s) isn't planned. About 7 s in Chromium and WebKit is
  acceptable, and Firefox's ~23 s is accepted for v1. WV-2 records the gate on a modest machine.
- **The product never reads its output back.** The per-file sha256s come from Python's `Image` before any byte
  is saved; only the parity test hashes a saved file, in the CPython test process. In WebKit, reading a
  composed Blob back through a second WORKERFS mount threw an undiagnosed `NoGilError` [verified].

### 3.6 Workers
- **One module worker per build,** started from a `blob:` URL so that it inherits the page's CSP (§6.4).
  - It starts when the page opens; Pyodide loads in 1.3–2.1 s [verified].
  - It is replaced after each build: wasm memory never shrinks, and no state carries over.
  - A `blob:` module worker can't resolve `/…` or `./…` specifiers [verified, Node 26 URL parser]. So the page
    passes absolute URLs (`new URL("pyodide/", location.href).href`) for the import and for
    `loadPyodide({indexURL})`.
- **Cancel** is `worker.terminate()` during Build, and `abort()` on the writable during a Chromium save.
  - So there's no interrupt buffer, SharedArrayBuffer or COOP/COEP; all runs had `crossOriginIsolated=false`
    [verified].
  - Progress uses `postMessage` (the core's `Reporter`).

### 3.7 Memory

| Item | Size | Label |
|---|---|---|
| Pyodide core | about 13 MB raw; 6–13 MB over Pages' gzip (5.5 MB with brotli, which Pages doesn't serve) | sizes verified; gzip of `.wasm` unverified (W3) |
| Mods build | whole-file writes, at most 5 files / 40.2 MB in today's mods-only G3 cases | verified (the plan's evidence §16) |
| Randomizer build today | wasm heap 1,004 MiB (Node), 1,170 MiB (browsers) | verified |
| Randomizer after 4.10's planner | target below 300 MiB: about one level (e2, 85 MB) plus scratch | inferred target |
| wasm32 ceiling | 4 GB in Chrome and Firefox; 3,840 MiB allocated in Node. Safari kills the tab instead of failing `memory.grow` | Node verified; V8 blog; WebKit bug 221530 |
| Summed browser RSS, randomizer build | 4.6–5.4 GB (shared pages double-counted) | verified |

### 3.8 Browser support

| Browser (2026-10) | v1 | Save path | Measured (headless, M2 Ultra) |
|---|---|---|---|
| Chrome, Edge (desktop) | reference | save dialog, else download | planned in 15.5 s; reads about 500–600 MB/s |
| Firefox (desktop) | supported once W0 passes | download | planned in 66.5 s; reads 75–124 MB/s, likely Firefox's IPC-backed `File` reads rather than headless mode [inferred; WV-2] |
| Safari (desktop) | supported once W0 passes | download | WebKit 26.6: 14.4 s; real Safari 27 untested |
| iOS, iPadOS, Android | unsupported; a message points to the desktop app | — | — |

**Fallbacks:**
- **No save dialog → download.** `showSaveFilePicker` reaches about 30% of users: Chrome and Edge 105+, not
  Firefox ≤ 160 or Safari ≤ 27.1 [verified, caniuse, Sep 2026].
- **A download that fails on some engine in W0** → first retry with the plain input `File` (one 2.7 GB part).
  That tells "a large Blob download fails" apart from "a composed Blob fails".
  - OPFS staging helps only the second case. It costs a second 2.7 GB on disk and meets Firefox's
    min(10% of disk, 10 GiB) quota.
  - If the plain `File` also fails, that engine is unsupported in v1.
- **Out of memory.** Before Build, the page sets a `sessionStorage` "build running" flag and clears it at Ready.
  If the flag is still set on the next load (Safari killed the tab) or the worker fires `error`, the page shows
  "use the desktop app".
- **No WebAssembly** → a static message.

## 4. UX flows and presets

### 4.1 One window: §12.7's screens A (Mods only), C and D, with these differences
- **Open.**
  - A file picker or a drop replaces the path box.
  - Chromium uses `showOpenFilePicker` in `read` mode, so it holds a handle for the D36 check.
  - Under the picker go the §2.3 line and the disclaimer.
- **Verify.** The badges are §12.7 D's:
  - ✔ Vanilla USA · verified;
  - ✖ Not vanilla: `<first differing file>` (Build disabled);
  - ◆ AzurKit build · N layers, which offers [Load its recipe] and then "pick your vanilla ISO".
- **Choose.**
  - Only the Mods tab works; Randomizer and Data are shown disabled ("later").
  - There's no edits tree and no per-ISO autosave: the recipe lives in the URL fragment.
- **Build, then save (two clicks, §3.4).**
  - `[Build]` shows progress and Cancel and ends at `Ready · <size> · changed: default.xbe …`. It adds "matches
    the preset ✔" when the preset carried `result` hashes and they match.
  - `[Save ISO…]` then suggests `<stem> (AzurKit).iso`.
- **Share.** `[Copy link]` copies the fragment that `sdk.preset_encode` returns; `[Export preset]` saves
  `<name>.azurkit.json`.
- **Load.**
  - Sources: a link, a dropped preset, or the recipe from **your own** AzurKit-built ISO's `/azurkit.json`.
  - From a full manifest, only the recipe is taken. External layers are refused ("needs the desktop app").
  - A preset made with another version shows "Made with AzurKit 0.4". The page builds it with the current
    version and compares the `result` hashes when the preset has them.
- **Messages.** On mobile, without WebAssembly, or when a crash flag is left over (§3.8), the page says "use the
  desktop app".

### 4.2 Presets: the share profile (4.4 amendment; narrows Q59)

```json
{"format": "azurkit-preset", "schema_version": 1, "azurkit": "0.5.0",
 "base": {"kind": "vanilla", "region": "USA", "iso_sha256": "6989c84e…84be"},
 "layers": [{"tool": "mods", "tool_version": "0.5.0", "kind": "packs",
             "recipe": {"player_physics": {"jump_speed_scale": 1.5}, "qol_skip_logo": {}}}],
 "result": {"default.xbe": "<sha256>"}}
```

- **No `changes`, `claims` or blobs.**
  - Claims and header metadata are recomputed (§12.2). The optional `result` holds hashes only.
  - **The recipe is enough,** because a rebuild from vanilla with the same tool versions is deterministic
    (D34).
  - Generators (later) carry their recipe only: the generator version, the settings, the seed and `db_digest` (REORG §12.2, round 2: A2-5). A preset whose generator version or `db_digest` differs is refused by name; an exact world across versions travels as the CLI's Plan file.
- **One codec, in Python.**
  - `sdk.preset_encode` returns the link fragment itself: `#p=` plus base64url of raw deflate (zlib,
    `wbits=-15`). `preset_decode` reverses it.
  - So JS only stores and copies strings, and needs no `CompressionStream`.
  - `tools/mods` normalizes every recipe once, for the hub, CLI, MCP and web: a value equal to vanilla drops the
    setting, and NaN/inf and unknown keys are refused. D23 keeps every finite value.
  - 4.5's `--mods FILE` reads a mods file, a share preset or a manifest. There's no `--preset` flag.
- **Untrusted input.** That means links, dropped files, a foreign ISO's `/azurkit.json`, and the XDVDFS file
  names shown in ✖.
  - Text reaches the DOM only through `textContent`: no `innerHTML`, no `insertAdjacentHTML`.
  - `#p=` is capped at 8 KB encoded and 64 KB inflated; decompression stops at the cap. JSON nested deeper than 8
    levels is refused.
  - A version must match `^\d+\.\d+\.\d+$` before it is shown.
  - Pack and param names must exist in `catalog()`.
  - Loading a preset never starts a build or opens a picker, and every changed value shows ● before Build.
- **Size:** about 1 KB of JSON, or 0.5–0.7 KB in a link [inferred].
- **Versions.** The site serves only the latest version (§6.1); determinism across versions is never promised.

## 5. Testing and parity

**Four new tests,** each in its behavior-area file (D10, D37):

| # | Test (step, file) | Tier and CI | Pins |
|---|---|---|---|
| 1 | `test_build_path_runs_without_threads` (4.2; `tests/test_build_validity.py`) | pure; `ci.yml` | With `threading.Thread.start` patched to raise, a synthetic build succeeds, and so does the gate on a synthetic manifest. This checks Pyodide's constraint without Pyodide |
| 2 | `test_patch_errors_name_the_site_not_its_bytes` (4.3; `tests/test_build_validity.py`) | synthetic; `ci.yml` | A forced site mismatch raises an error that names the pack, site, VA, offset, length and `sha256[:12]`, and holds no hex run of 8 bytes or more |
| 3 | `test_share_profile_round_trips_and_carries_no_game_bytes` (4.4; `tests/test_edit_layers.py`) | pure; `ci.yml` | Encode → decode gives equality, the fragment form included. Refused: unknown keys and names, NaN/inf, more than 8 KB encoded or 64 KB inflated, nesting deeper than 8. The leak guard passes the encoded form |
| 4 | `test_web_build_makes_only_same_origin_requests` (W1; `tests/test_web_build.py`) | synthetic, `web`; `ci.yml` and `full.yml` | Over a whole pick → Build → Save run, Playwright's request log holds only same-origin GETs. It holds **zero** requests between [Build] and Ready. It includes the worker's own fetches of `pyodide.asm.wasm` and the wheel, so a log blind to worker traffic fails. No `securitypolicyviolation` fires in the page or the worker |

**Parity: a `runtime` parameter, not new tests.**
- The parity tests of 4.3 and 4.5 gain `runtime = cpython | pyodide`. They cover two tiers:
  - the vanilla tier: G1/G2 (including `qol_skip_logo` with 4.3's prebuilt objects) and G3's non-randomizer
    cases;
  - the synthetic tier: the stand-in XBE (4.3) in a tiny in-test XISO.
- For `pyodide`, the same recipe is built in headless Chrome through the web worker, which returns per-file
  sha256s.
- One case, the preset of G3 `apply-physics:zero-scales`, also clicks [Save ISO…] (REORG Step 4.0 round 2,
  S2-1: G3's `pack_build_iso:starting_hp=500` carries a mod that a recipe-only preset can't express). The
  CPython test process hashes the saved file against its own `azurkit build` of the same preset (round 2,
  J-1: the root manifest keeps G3's `ISO` hash out of reach): this is the D55 twin.
- W4 adds ~~the G3 randomizer cases~~ AzurKit's randomizer golden (`RANDOMIZER_PLAN.md` §8.3 item 4, D83(a); applied 2026-10-10). `tests/test_web_build.py` holds only test 4 and the `runtime` fixture.

**Running browser tests.**
- **The `web` marker (§12.3 amendment)** behaves like `vanilla` under D26.
  - It is selected by default, and a missing Chrome or Pyodide core fails the run with one message.
  - Contributors opt out with `-m "not web"`.
- **CI setup.** `ci.yml` and `full.yml` run `bootstrap --with web` in their dependency step. In `full.yml`
  that step comes before any secret or ISO exists.
- **The full tier.**
  - `full.yml` runs these tests under `--ci-full` like every other test.
  - GitHub release downloads redirect to `release-assets.githubusercontent.com` [verified, `curl -sI` of the
    Pyodide asset, 2026-10-10]. That host isn't on `full.yml`'s egress allow-list, so §12.4 adds it.
  - The tests run under `sudo unshare -n`, where loopback may be down. Playwright's request routing serves the
    site from `web/`'s build, so there's no local server.
  - Chrome needs `--no-sandbox` when it runs as root [inferred]. WV-3 settles both.
- **Hygiene in public CI.**
  - Playwright tracing, video and screenshots are off.
  - Downloads and the browser profile live under `$RUNNER_TEMP` and are deleted in teardown.
  - Console and worker messages pass through the §12.3 byte-safe scrubber before they reach the log.
  - The vanilla cases run only in `full.yml`, under §12.4's job hygiene (no artifacts, no caches).
- **Firefox and Safari** aren't in CI:
  - Playwright's own Firefox and WebKit builds would be a browser download outside the egress allow-list.
  - Playwright's WebKit isn't Safari anyway.
  - W2's owner test and one manual build per release cover them.
- **Oracle.** The parity tests read AzurKit's copies of the G1–G3 hash manifests (D2); nothing new is recorded.
- **libm drift.** A float transform (`math.pow`, `exp`, `sin`) before an f32 pack may round differently under
  wasm's musl than under macOS or glibc [inferred]. The `runtime` parameter catches it.
- **Release gates replace a site test** (§6.2). The §12.3 leak guard gains two rules:
  - no x86 disassembly run of 4 or more consecutive instruction lines in any text file;
  - with WQ-2's default, no `original_bytes` exemption.

  Its existing test gains one case per rule.
- **In-game.** Hash parity carries the desktop's xemu sign-offs over to the web. W2 owes one cold boot (WV-5).
  The web tool needs no save states.

## 6. Hosting, release and security

### 6.1 Hosting
*D85 (owner, 2026-10-10) answers WQ-3 against this section's default: the site is hosted on GitHub Pages at `<org>.github.io`, with no custom domain, and the owner accepts the shared-origin trade-off described below (R8). The custom-domain bullets are superseded; the no-service-worker rule and the controller check stay.* *2026-10-28 (D884, amending D85's `<org>.github.io` root): the site is served from the AzurKit repo at `https://azurik-modding-hub.github.io/AzurKit/`, a project path; there is no separate org site repo.*
- **Own origin (WQ-3).**
  - A project site on `<org>.github.io/<repo>` shares its origin with every other Pages site in that org
    [verified, GitHub docs, E10]. CSP `'self'`, storage and test 4's "same-origin" would all cover other repos.
  - The org's root `<org>.github.io` repo could register a root-scoped service worker that intercepts AzurKit's
    pages [inferred, Service Worker scope rules]. In Azurik-Modding-Hub, another developer controls that repo.
  - So the site is served from a dedicated custom (sub)domain set on AzurKit's public repo. That domain is
    verified under the org (GitHub domain verification prevents takeover), and HTTPS is enforced.
  - There is no public deploy until that domain exists.
  - The page registers no service worker. As defense in depth, it refuses to run if
    `navigator.serviceWorker.controller` is set.
- **One path.** v1 deploys `/` only. A Pages deploy from Actions replaces the whole site, so keeping old versions
  would mean rebuilding old tags [inferred]. Add versioned paths only if a release changes a shared preset's
  output.
- **Limits.** Pages allows ≤ 1 GB per site and a soft 100 GB/month [verified, GitHub docs, 2026-10-10]. That is
  about 8,000–16,000 first visits a month [inferred].

### 6.2 Release and deploy integrity
- **`release.yml` on `v*` tags** builds the wheel once, with Q76's shim objects, then builds the site from that
  wheel. Site version = wheel version = tag.
- **The site job checks:**
  - the site holds a closed file list, enumerated in `release.yml`:
    - the five Pyodide files, copied from the sha256-checked tarball (§6.3);
    - the wheel;
    - `web/`'s static files;
  - the §12.3 leak guard passes over the unpacked wheel and the site, with no `original_bytes` exemption;
  - `web/THIRD_PARTY_NOTICES` covers every shipped file.
- **A separate deploy job:**
  - environment `github-pages`, with the owner as required reviewer;
  - a deployment policy of `v*` tags only, and a tag ruleset that limits `v*` creation to maintainers;
  - `permissions: pages: write, id-token: write` only in that job;
  - actions pinned by SHA (§12.4) and no secrets.
- **The Release publishes `site-v<x.y.z>.tar` and `SHA256SUMS`,** so anyone can compare them with the served
  files.

### 6.3 Supply chain
- **Pyodide is self-hosted,** never loaded from a CDN.
  - The `pyodide-core-314.0.7.tar.bz2` tarball is pinned in `tools.toml` by URL and sha256:
    `2abdcc2e35208af406e07724cffa85bc582ced97e9028383ecf5462541393f95`, 6,757,104 B. That equals the GitHub
    release asset's `digest` field [verified, `gh api …/releases/tags/314.0.7`, 2026-10-10, E6].
  - `release.yml` copies only `pyodide.mjs`, `pyodide.asm.mjs`, `pyodide.asm.wasm`, `python_stdlib.zip` and
    `pyodide-lock.json` [verified, listing E7].
  - It never copies `python.exe` (a Windows PE), `python`, `python.bat`, `python_cli_entry.mjs`, `pyodide.js`
    or `*.d.ts`.
  - `loadPyodide` gets explicit same-origin `indexURL`, `lockFileURL` and `packageBaseUrl`. The default
    `packageBaseUrl` is jsDelivr [verified, E8].
  - There's no `micropip` and no `loadPackage` from PyPI. The wheel is fetched with
    `fetch(url, {integrity: "sha256-…"})`, with the hash baked in at build time, then loaded with
    `unpackArchive`.
  - A bump changes the version, URL and sha256 in one reviewed PR, within 314.x. Pyodide 315 comes only when
    AzurKit moves (D22).
- **Playwright** lives only in the `dev` group and never ships.
- **Protected paths (Q56):** add `web/index.html` (the CSP `<meta>`) and `web/worker.mjs`. The deploy config is
  already protected under `.github/**`.

### 6.4 CSP and page hardening
- **The policy.** The CSP `<meta>` is the first child of `<head>`:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self';
  object-src 'none'; base-uri 'none'; form-action 'none'`.
- **`'unsafe-eval'` (WV-4).** `pyodide.asm.mjs` calls `eval()` to install EM_ASM and EM_JS [verified, E8].
  - W1 runs the build under exactly the policy above, with a `securitypolicyviolation` listener in both the page
    and the worker, and test 4 fails on any violation.
  - `'unsafe-eval'` is added only if the core path hits `eval`.
- **Worker CSP.** Pages sends no CSP or X-Frame-Options header [verified, curl, E9]. A worker loaded from a
  same-origin URL takes its CSP from its own response headers, not from the page's `<meta>`.
  - So the worker starts from a `blob:` URL, which inherits the page's policy. That is documented for Chromium;
    for Firefox and WebKit it is WV-4.
  - The worker then imports Pyodide through absolute URLs (§3.6).
- **Framing.** `frame-ancestors` is header-only and Pages can't send it, so the page refuses to run when
  `window.top !== window.self`.
- **COOP/COEP** aren't needed [verified]. If a later feature needs SharedArrayBuffer, use `coi-serviceworker`
  (which conflicts with §6.1's no-service-worker rule) or a host that serves header files [unverified].

