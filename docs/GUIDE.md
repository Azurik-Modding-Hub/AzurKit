# AzurKit guide

Every feature in detail. [README](../README.md) is the short version: what AzurKit is, what you need and how to start.

## Patches and sliders

- **17 patch packs:** every one works on both releases, USA and Europe, in three groups: Player, Enemies and
  Quality of Life.
- **Frame-rate unlock:** 60 FPS by default, or any whole frame rate up to 1,905, with game time keeping pace.
- **Gravity:** set the world's gravity; your jump and flap heights stay the same.
- **Movement:** walk, jump, swim, climb and roll speed, roll distance, air control, flap height and ceiling, and
  flap fuel costs.
- **Speed toggle:** click the left stick (L3) in game to flip a movement setting between yours and the original.
- **Starting health:** your starting HP and the health bar's full scale.
- **Air shield flaps:** how many wing flaps each air shield tier gives.
- **Damage enemies take:** multipliers for neutral hits, weaknesses and immunities, across all 33 of your attacks.
- **Enemy and boss scaling:** health, damage, attack speed, move speed and size, set apart for enemies and bosses.
- **Save-point warp:** on a save platform, hold LT and press A, B, X, Y to go to town and back.
- **Photo mode:** click both sticks to freeze the game, hide the HUD and fly the camera, slower or faster.
- **Fewer popups:** hide the first-time gem popups, and the tutorial, key, health and power-up ones.
- **Skip the waits:** skip the pickup celebration (the item still counts) and the unskippable Adrenium logo at boot.
- **Crash fix:** on by default, it cures a rare crash in the original game while a level loads.
- **Loading fix:** on by default, it ends a "Loading..." hang at level changes, and a bigger load budget fits a
  larger player model.
- **More RAM in xemu:** on by default: with xemu set to 128 MiB, levels, textures and meshes load past 64 MiB.
  256 MiB is optional.
- **Any number you like:** a setting takes any finite number, never clamped, and its slider widens to hold it.
- **The original values:** each slider shows the game's own value (gravity and the load budget read from your
  copy).
- **Clear refusals:** only a value the game can't hold is refused, and by name.
- **Linked packs:** a pack that needs another ticks it too.
- **Community packs:** ready-made setups from our Azurik-Custom-Content, listed in the Patches tab with Install and
  Update; a ticked one sets its packs and game data for you, every file checked first, and stays at its version until
  you update it. None are published yet.

## Randomizer

- **Your choice of shuffle:** disc fragments, elemental powers, upgrades, gems, obsidians and fuel pickups; keys and
  barriers stay put.
- **Whole-game logic:** all 22 levels and their 1,418 item locations.
- **Movement difficulty:** Standard, Hard or Frame-perfect jumps and flaps.
- **Seed difficulty:** Easy, Normal, Hard or Expert, with any settings. Harder levels put key items deeper in the chain
  of finds, in side rooms and dead ends, and behind the hardest tricks you allowed, so you need those tricks more; Easy
  puts them early and close. Normal gives the seeds as before, and every seed stays beatable.
- **36 rated skips:** each on or off, or by group, whose tick turns on all of its: power storage, roll and flap tricks,
  barriers, dark rooms, out of bounds, super jumps.
- **Dark areas:** they need Fire 1, unless a dark-room skip is on; then no fire.
- **Obsidian cost:** any number per lock (the game's is 10).
- **Save-point warp:** off by default; tick it (it ticks its pack too) and the logic counts it, which can add seed
  variety.
- **Seeds:** any text is a seed (an empty one is refused, never a default), or New draws one; the same seed and
  settings give the same game everywhere.
- **Share strings and files:** one `AZR-` string holds every setting; settings files save and load,
  Azurik_Modkit's too.
- **Plan files:** Open a plan… builds a plan file (`azurkit plan`'s, Azurik_Modkit's too) exactly, its seed and
  settings locked until Close plan; one from another version, edited, or not beatable is refused, saying why.
- **Warns before you build** when your settings can't make a seed, saying why and what to change, and greys Build
  until you do. Keeping obsidians vanilla is one: most of the spots the disc fragments and elemental powers may take
  hold an obsidian, so tick Obsidians, or keep those two vanilla too.
- **Works with movement mods:** your jump, speed, gravity and flap settings pick the movement difficulty the seed is
  made at (stronger moves play like Hard or Frame-perfect, weaker like Safe), in no time and never refused; a seed
  with any moved setting isn't promised beatable, and the page and spoiler say so.
- **Sealed items stay sealed:** an item placed in an ice or acid block, a gem rock or behind a force field can be
  picked up only once it opens, however wide the item reaches.
- **Character builds share alike:** the body you wear folds its size into the share string, so a seed you track or
  share wearing it is the one its build places.
- **Checked before it's saved:** the finished image is read back against its plan, and any mismatch no later
  change explains stops the build.
- **Logic verdict:** whether the logic still holds, and why not (a pack over an item spot, an unmodelled setting,
  a costlier lock, a worn body).
- **One build:** randomize and patch together, on USA or Europe.
- **Spoiler log:** each sphere, every key item with its way in and its way back, and the traps; view or save it.
  It's written once the build is done, so the build is ready sooner. On the command line, `azurkit build --spoiler`
  and `--save-settings` write it and the settings beside the build.

## Item tracker

- **Track any seed:** a randomized build (the one you just built, or any you open on the Tools tab: Track this
  build), a seed you haven't built yet, or a plan file.
- **Quick to open:** on our Mac the Randomizer tab opens, and Track this seed shows its plan, within 3 s of the
  click, in the app and in the browser.
- **What a seed took:** under the head line, how many key-item steps the seed has, how many key items lie off the way
  through and how many points need a trick; with Spoiler on, which tricks, e.g. "needs Roll jumps twice".
- **Where you stand:** what you've collected and what you can reach right now, sphere by sphere.
- **Skips shown apart:** spots you can reach only with a skip have their own colour.
- **Spoiler-free:** each item stays hidden until you collect it, unless you turn Spoiler on.
- **Maps at once:** 22 level maps, a world map and 41 icons come with AzurKit, so the world map shows the moment you
  open the tracker, before you pick your image or a seed.
- **Browse the maps:** before you track a seed, pick any level on Map (or click it on the world map) to see its map
  in full, with the item the unmodified game puts at each spot.
- **Level maps:** floors, zoom and pan; click a spot to mark it, or an exit to jump to its level. Each item shows
  on the floor of the room it stands in, and each floor's button shows how many are left on it; the other floors'
  items show faintly, fainter the further the floor. Sharp when zoomed in: 18 levels carry each floor again at 2 px
  a metre, up to 5 times finer.
- **Every lock labelled:** exits, barriers, key locks and disc seals show what they need, and so does each spot
  you hover; save points and teleporters are marked.
- **World map:** each level with a badge of the spots you can reach now.
- **Table view:** the same as a list of items and places.
- **Gems:** a coloured dot for each of the 1,215 gem spots, and the gems taken and left on each level.
- **Collected spots leave the map:** Show collected brings them back, dimmed. A pickup Live sees flashes on the map
  and says what you got.
- **Remembers your marks** for your last 20 seeds, never your image; Reset clears them.
- **Live, in the app:** marks what you pick up in a running xemu and shows where you are, with Find me and Follow,
  which switches the map to the floor you stand on.
- **Live only reads:** it never writes to xemu or pauses the game.
- **Play, in the app:** starts your xemu with the build you saved last in its tray and tracks that build's seed with
  Live on, changing no xemu setting; it finds xemu itself (or asks which, or where) and remembers your pick. With
  xemu already running it starts no second one and offers to attach.
- **Attach…, on a Mac:** reads an xemu you started yourself after one password prompt, through a small read-only
  helper; an xemu signed with Apple's hardened runtime can't be read.
- **Your game's seed:** turning Live on in the app first tracks the seed of the randomized AzurKit build in xemu's tray.
- **Live keeps up:** it finds an xemu started with QMP on port 4444, tells USA from Europe and follows deaths,
  reloads and save states.
- **Live says what's off:** if xemu runs another seed or build, it counts the level's spots that differ and says
  what to check, or that the game isn't randomized.

## Characters

In the page's Characters tab, or from the command line (`azurkit build --character '{"species": "keylord"}'`).

- **Pick by grade:** every creature in its grade's colour and mark, so it reads without colour too: ✓ green fully
  playable, ~ yellow rough edges, ✕ red not playable; the 73 nobody has tested yet are greyed and marked ?, and the
  weapons on them greyed.
- **Any weapon on any model:** all five are listed even before you pick your image, a pick nobody has seen in game says
  (not tested), and Preview shows the weapon in a small popup.
- **Objects tucked away:** the 76 pickups, keys and statues you can wear stay out of the list until you tick Show
  objects (remembered); one you already wear stays listed.
- **See it first:** the chosen model from the front and from behind, at once and before you pick your image; the
  whole list and every weapon show straight away too, and G4 and how a weapon fits say they need your image.
- **Match Garret in one click:** a G4 button beside model size, attack reach, damage and speed sets the body to
  Garret's height, reach, damage per second or timing.
- **Play as almost anyone:** 178 of the game's 184 creatures, bosses to critters, on both releases. The 30
  weaponless townsfolk fight bare-handed, and the air elemental's gust whirls up a tornado; nothing to download.
- **Two ways to play:** the creature's own moves (the default), or Garret's exact moves in its skin.
- **Any size:** the body's own or Garret's height, times any scale you like.
- **Borrowed moves:** Garret's moves fill a body's gaps, fitted onto 36 different skeletons.
- **Speed that fits:** walk and roll speed scale with the body, and the speed toggle flips to its own pace.
- **Weapons:** Garret's Axion staff, the farmer's hoe, Balthazar's magic, the spin attack or bare hands.
- **Attacks:** reach, damage and speed multipliers.
- **Combos on a hit:** a body's combo goes on to its next attack only after a hit, as Garret's does, in every one of
  its attack sets; Chain on any press (off by default, beside Gameplay; `"chain": "any"`) lets any press in the
  window chain instead, for any model.
- **Attack sets:** a creature with more than one set of attacks switches sets with LB in game, the set's moves
  shown top-left; once your image is read the tab says so, each set's moves in the line's tip.
- **Voice:** the creature's own sounds, or Garret's.
- **Target RAM:** the machine the build is for, From your packs (the default), 64 MiB for a retail Xbox, or 128 or
  256 MiB for xemu; it moves only how large a model may be (`"ram": 64`), and another model and Reset keep it.
- **Variants:** Beamlord, and Booblord (blue skin, a high black ponytail, red eyes, an orange top and sash over
  black satin shorts) as she is, in high detail, in human colours (tan skin, brown eyes, an indigo top and sash) or
  both, each a recipe over a creature's body applied to your own copy; or your own: a recipe file, or a variant you
  saved, worn by name (a folder each in `variants` in AzurKit's data folder, where Modkit saves them), its shapes
  sized as you like (a moved shape shows the nearest one at once, marked Preview, until its own pictures are
  drawn). Booblord's four need her own moves and voice, extra files from our Azurik-Custom-Content; a build without
  them stops, naming the file.
- **Make your own (the Variants view):** beside Models, a list of the built-in variants and yours, each in its
  grade's colour as in Models (one that won't load is marked, saying why). New starts one on any species' body, New from this copies the one open with all its
  files so every field is yours, Save, Save as and Delete (after a yes) keep your library, and Import and Export move
  one as a zip (naming any file in it made from the game's, which isn't yours to share). Body sets its size, scale,
  arms out, rotate, title and notes, Gameplay its mode, Shape a slider for each of its shapes (a drag shows the
  nearest shape at once, marked Preview; let go, a quick preview of it once checked, else the Check) with its mesh's
  ops, Jiggle each spring's stiffness, damping and strength (add one on a free bone, or remove one), Moves and Attacks
  the clip each move and attack plays (its own, or once you pick your image another body's, Garret's too; Attacks also
  sets its weapon and attack numbers and switches), Sounds its own or Garret's sounds, a silent voice, a WAV per role
  (Add WAV copies one into its folder) and a made sound's numbers, Effects its fireball, shield or beam rows on the
  attack columns you tick (each row's template, colour and numbers; a Check shows the bytes each adds), and JSON shows
  the whole recipe (Apply checks it first and keeps the old one if it's refused). The status line gives its recipe's
  checksum, its grade, and whether it's saved and checked; Check with game data (once you pick your image) dresses it
  as a build would, answers, then draws it: a first Check of new content takes a while, with a bar, a copy of a
  variant checked before (New from this, under any name, on a later visit too) takes a few seconds, as does a first
  Check of a built-in or its own copy (it fetches its parts the first time) and a Check after an edit on the Jiggle
  tab (a spring's numbers), a colour or a sound, and checking it again unchanged answers at once. Unsaved edits are
  asked about before you leave them, build that variant or close the page, and the app asks too before its window
  closes. The app keeps your variants where Modkit does; the web page keeps them in your browser (Clear in the Tools
  tab removes them: Export one to keep a copy). Yours show under the models too, as Yours, and Edit… opens a chosen
  variant here.
  Writing a recipe by hand, or sharing one: [VARIANTS.md](VARIANTS.md).
- **Colours (the Variants view's Colours tab):** pick a row of the body's textures (or all), then drag on the colour
  wheel to move its main colour, with a bar for brightness and boxes for the hex colour, hue, saturation and value;
  limit it to a range of hues, or click a palette colour to swap it for one you pick on a wheel. The row tiles and the
  front and back views redraw as you drag. Once you pick your image, Export PNGs saves each row's texture as
  built (the app: a folder in Downloads; the web page: a zip), and Import PNG brings an edited one back as that
  row's texture. Undo (⌘Z or Ctrl+Z) takes back any edit in the view, a drag as one step.
- **Three drop-downs:** the models list folds into Species (open), Community and Yours (shut until you open one);
  each heading counts its models and names the one you chose, its group opens when you choose one in it, and a
  search opens the groups it finds models in.
- **Community variants:** ours from Azurik-Custom-Content sit under the species, marked community, with Install
  and Update (or `azurkit content install booblord`); every file's size and checksum is checked first, so a bad
  download keeps nothing, and an installed one stays at its version until you update it. An update only goes up, from
  where it was installed (one that can't is refused before anything downloads), an install never replaces another
  installed entry's file, and a web source is https: the
  web page reads ours from GitHub, or any https repository you set as Content from. A repository's own characters
  work too: listed under their entry and in the Variants view, built, checked and shared by name like ours; one
  whose files changed since its install, or named like ours, yours or a species, is refused, saying why. In the
  browser, Booblord's pictures and G4 values can run out of memory: the app draws them.
- **Ready-made bodies:** every body's size at its defaults ships with AzurKit, and Booblord's whole build at the
  defaults comes with her download, for both releases, so their first Build skips that work; any other choice builds
  as before.
- **Effects of its own:** a recipe can give its attacks a fireball, ice shard, arrow, bubble, dome, barrier, stream,
  bolts or laser, made from the game's own effects.
- **Works with every pack and the randomizer:** a seed can wear a character, made at the movement difficulty the
  body's walk and roll play like, and the verdict says what the body changes (its height, its attacks).
- **In links and recipes:** a share link and a build's recipe carry the character, by name and numbers; a variant
  whose recipe has changed since is named, with what to install or update.

## Data

In the page's Data tab, in the browser and the app alike, or read from the command line (`azurkit data`). It works
before you pick your image: AzurKit ships the game's original config.xbr, the same on both releases.

- **Views:** the Player, Critters, Items, Armor and Weapons, each entity's numbers from every table that holds them,
  with a search box; All tables, each as a grid you can sort, or show only what you changed.
- **Pictures:** the Critters and Items lists show each one's body, before you pick your image too.
- **All files:** with your image picked, every .xbr file of it and each one's tables (only config.xbr has any on the
  original disc); greyed until you pick it. On the command line, `azurkit data --iso PATH --files` or `--file FILE`.
- **Read a build:** on the command line, `azurkit data --iso PATH` reads any image's tables, a build's too, and
  `--input FILE` a loose .xbr file; `azurkit diff` and `entity diff` take one too. They never write it.
- **Edit any cell:** any number, never clamped; only a value the game can't store is refused, saying why. Each cell
  has a note on what it does.
- **Lists and word lists:** a cell with a set of values is a dropdown, and a list of words a checklist that stops at
  as many words as the game holds; a value the cell can't take yet is greyed, saying it needs a new string.
- **Marks:** ● on what you changed, with the original value; ⚠ where a ticked pack also writes it (your edit wins,
  and the build says so).
- **Changes:** every value your edits or a loaded mods file change, the original beside it, and its byte edits: what
  a build will change, before you build (`azurkit diff` prints a mods file's, each edit numbered).
- **Compare two entities:** `azurkit entity diff` sets two critters' (or any two entities') values side by side,
  table by table, with what only one of them has.
- **A template to edit:** `azurkit mod-template` writes a table's (or one entity's) original values as a mods file;
  change what you like and build with it.
- **Undo and Redo,** Revert a cell, Reset a table, Clear edits. Your edits join each build after the packs, and a
  link, a mods file and the remembered setup keep them.

## Tools

In the page's Tools tab, in the browser and the app alike, or from the command line (`azurkit files`).

- **Your image:** its release, size and kind (original, an AzurKit build with what made it, or modded with the first
  file that differs); greyed until you pick it.
- **Verify every file:** all 1,195 checked against the original disc, with a bar; it reads only what the first
  check left, and asked again it reads nothing.
- **Its files:** the whole list, with a filter; Extract one (the browser downloads it from your own file, the app
  writes it where you choose, never over your image).
- **Recipes and files:** open any AzurKit build for its recipe, load or save a mods file, view or save a plan file's
  spoiler and the last build's report.
- **Build logs, in the app:** each build's log (its recipe and report, or why it failed, and where it was saved) is
  kept on your computer; open the folder or the last one from the Tools tab.
- **AzurKit's storage:** what AzurKit keeps on this computer, by name, and Clear; never your image.

## Building and sharing

- **Checks your game first:** the files a build reads against the original USA or Europe disc (`azurkit verify`
  checks every file); a modded image is refused, naming the first file that differs.
- **Checked once:** your image is checked the first time you pick it, then trusted until it changes, across launches
  of the app and visits in the browser; saved on the same Mac drive as your original, a build writes only what it
  changed.
- **Your original stays safe:** a build never writes over the image it reads.
- **All or nothing:** if anything fails, nothing is written, and the error says what and why.
- **Save editor:** in the Tools tab or with `azurkit save`, read a save slot's folder or the slots on an xemu hard disk
  (`azurkit save inspect` reads one save file too), change a text save's line, sign it again with your own BIOS files
  (read in memory, never kept) and save it new, never inside the slot's own folder; `azurkit save` also takes a file
  of edits (`--plan`, Modkit's too) and prints JSON (`--json`).
- **Replace files:** pick a file from your computer to stand in for one of the image's, at any size, in the Tools tab
  or with `azurkit build --file`; the recipe names it, never holds it, and a share link refuses it.
- **Clashes named:** when two changes touch the same spot, the later one wins and the build says so.
- **In game:** after a build, one line lists the controls it adds, such as the save warp, LB's attack sets, the
  speed toggle and photo mode.
- **Builds carry their recipe:** two small files on the disc; `azurkit open`, or picking the build in the page,
  gives it back.
- **Tamper check:** a build changed after it was made is refused by name.
- **Share links:** Copy link makes a short link with your packs, settings, seed and character, never your image or
  a path.
- **Starts fresh each visit:** tick Remember settings to keep your setup for next time, never your image.
- **Game data edits:** a mods file can set any value in `config.xbr` by name, replace bytes in an XBR file, or move
  a level's item or critter; `azurkit build` takes several, applied in order, and says where a later one changes what
  an earlier one set.
- **Modkit's mod files:** a mod file from Azurik_Modkit loads and builds too (its patches, sections,
  `_keyed_patches`, `xbr_edits` and its level's moves, each by the name the original level gives it, even in a
  randomized build); what AzurKit can't apply as written, such as a rename, is refused by name.
- **Same bytes everywhere:** the page, the app and the command line make the identical image; only a character
  swap's float maths may round its last digits otherwise in the browser or on another computer.
- **Proven exact:** packs, randomized seeds and character swaps are checked byte for byte against AzurKit's own
  records, which began as those of Azurik_Modkit, the toolkit AzurKit replaces.
- **Nothing to compile:** AzurKit's C code, for the game and for the randomizer's fast search, ships prebuilt for
  each computer and the browser, so nothing compiles on yours.
- **Fast:** from the command line on our Mac: a patched image in about 3 s, a swap in 8 s, a seed under 30 s.

## Where it runs

- **On a computer:** a Mac or a PC; on a phone or a tablet the page says to use a computer.
- **The web page:** the whole builder, randomizer and tracker run in your browser through WebAssembly, tested in
  Chromium, Safari's engine and Firefox.
- **Builds back to back:** the page keeps its engine loaded after a build, so the next one starts at once.
- **Offline once loaded:** the web page keeps itself in your browser on the first visit, so later visits start from
  there, with no network, and an update waits until you click Reload.
- **Ready when you click:** the web page plans the seed you typed and builds what you set up in a second engine while
  you look it over, so Track and Build often answer at once; a change drops that work.
- **Nothing uploaded:** the page asks for nothing but its own files, and the browser checks its engine's integrity.
- **No tracking:** no logging, analytics or tracking.
- **The app:** the same page in its own window, with real file dialogs; Save writes the image where you choose
  (by default Downloads, or its AzurKit folder when your usa.iso or europe.iso is there).
- **No console window on Windows:** the app opens its window alone; what it would print goes to `app.log` in its
  log folder, which the Tools tab opens, and its commands print in the terminal you run them from (to wait for one
  and get its exit code, run it with `start /wait` in cmd or `Start-Process -Wait -PassThru` in PowerShell).
- **Unsigned apps:** CI builds the app for Apple Silicon and Intel Macs, Windows and Linux, unsigned, each with a
  checksum and a build attestation ([Download and check it](#download-and-check-it), below).
- **Greyed until it can work:** Build, Save and the original values wait on your image (or a build) and say so.
- **Progress bars:** a build, a save and the tracker's Track show their step and percent, as your image's first check
  does on the web page; in the app that check, like anything slower than a second, shows what it is doing.
- **Cancel any time:** Cancel stops a build or a save (in the app, a build at once); closing the app mid-build or
  mid-save leaves no half-written file.
- **The app stays quick while it builds:** a build runs in a process of its own, so picking an image and the other
  tabs answer at once, and dressing a character spreads over your CPU's cores.
- **Save is quick in the app:** it writes the image Build made, already checked while you chose where to save it.
- **Dressed once, in the app:** a character's body, pictures and G4 numbers are kept in your cache folder (AzurKit
  keeps at most about 5 GB, the oldest out first), so building or drawing it again, after a relaunch too, takes a
  second or two.
- **Dressed once, on the web page too:** the last 32 characters you built are kept in your browser, so building one
  again, on a later visit too, skips dressing it.
- **A private app:** its page is served only to itself, with a fresh key each launch.
- **The command line:** `azurkit verify`, `packs`, `build`, `open`, `plan` and `spoiler`; the app doubles as it.
- **Dark or light:** your pick is remembered, and both are easy to read.
- **Platform:** About names where AzurKit runs: the app its system and processor, the web page Pyodide in your
  browser.

## The command line

Install it with `uv tool install azurkit` or `pipx install azurkit` (Python 3.14), from PyPI; `azurkit --help`
lists every command.

```bash
azurkit verify [--iso PATH]              # is it vanilla USA or Europe, every file of it?
azurkit packs                            # the packs, and which a build applies by default
azurkit build --iso PATH --out PATH [--mods FILE ...] [--pack NAME ...] [--no-pack NAME ...] \
    [--no-defaults] [--pack-param PACK.SLIDER=VALUE ...] \
    [--seed SEED [--settings FILE | --share STRING] | --plan FILE] [--obsidian-cost N] [--character JSON] \
    [--spoiler FILE] [--save-settings FILE]   # a seed's spoiler and settings file beside its build
azurkit open BUILD                       # a build's recipe, as a mods file for build --mods
azurkit plan --seed SEED [--settings FILE | --share STRING] [--out FILE]   # a plan; needs no game
azurkit spoiler PLAN                     # that plan's spoiler
azurkit diff MODS ... [--input FILE | --iso PATH]   # what mods files (Modkit's too) change, before a build
azurkit mod-template TABLE ... [--entity NAME] [--out FILE]   # their original values, as a mods file to edit
azurkit entity diff A B [--all] [--json] [--config FILE | --iso PATH]   # two entities side by side, by table
azurkit files | data | save              # an image's files, config.xbr's tables, a save slot (each --help)
azurkit content [install ID | update ID] [--source URL|DIR]   # Azurik-Custom-Content's entries
```

A flag is read only as spelled: `--no-def` is refused, never taken for `--no-defaults`.
A mods file a build can't read is named in the error, with the line where it goes wrong.
A build never writes over its game image, nor beside a vanilla image named `usa.iso` or `europe.iso` (or the one
`AZURKIT_ISO` or `AZURKIT_ISO_EUROPE` names), nor anywhere in an `iso` folder that holds one.

## Download and check it

These hold from the first release:

- **Download only from [Releases](https://github.com/Azurik-Modding-Hub/AzurKit/releases).** An app is code that runs as
  you, and a copy posted anywhere else may not be ours. Each release holds `AzurKit-<version>-macos-arm64.zip`,
  `-macos-x86_64.zip` (Intel), `-windows-x86_64.zip` and `-linux-x86_64.tar.gz`, the wheel and sdist, and `SHA256SUMS`.
- **The command line alone:** `uv tool install azurkit` or `pipx install azurkit` (Python 3.14), from PyPI.
- **Opening it the first time:** the apps are unsigned. On a Mac, open it, then choose Open Anyway in System Settings ›
  Privacy & Security; never turn Gatekeeper off. On Windows, choose More info › Run anyway.
- **Checking it:** GitHub signed a record of the run that built each file, so this says it came from this repository's
  own release job ([GitHub CLI](https://cli.github.com)):

  ```bash
  gh attestation verify AzurKit-<version>-macos-arm64.zip --repo Azurik-Modding-Hub/AzurKit
  shasum -a 256 -c SHA256SUMS --ignore-missing   # the same file's checksum (Linux: sha256sum -c)
  ```

## xemu only

AzurKit targets [xemu](https://xemu.app), the Xbox emulator. Every in-game
check of a build is made in xemu, and some packs rely on what xemu gives
them, such as the RAM above 64 MiB. Real Xbox hardware is not a target: a
build may work on a console, but nothing here has been checked on one.

## Your image and the game's files

You bring your own copy of the game: AzurKit builds from your ISO, and no
ISO image, whole or in parts, is ever in AzurKit's repository.

- Builds read your ISO and stay on your computer: your image never leaves it.
- What ships from the game, so it shows before you pick your image: the
  game's original config.xbr (the Data tab's numbers) in the Python package,
  the app and the site, and pictures drawn from the game's files (the
  characters' front and back views, the tracker's maps and icons) in the app
  and on the site.
- Share presets (recipes), never ISOs.
- The game's files and bytes belong to its rights holders, not to AzurKit's
  licence ([`NOTICE.md`](../NOTICE.md)).

*Unofficial fan tool. Not affiliated with or endorsed by the rights holders of
Azurik: Rise of Perathia or Xbox.*
