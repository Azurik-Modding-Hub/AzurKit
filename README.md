# AzurKit

<img src="https://raw.githubusercontent.com/Azurik-Modding-Hub/AzurKit/main/assets/icon/AzurKit.svg"
width="128" height="128" align="right" alt="AzurKit's icon: a disc of the four elements broken in four, its gold air piece lifted out">

AzurKit mods *Azurik: Rise of Perathia* (Xbox): patch packs and sliders, a randomizer with an item tracker, and
almost any creature to play as. It builds a new image from your own copy of the game, in your browser or in the
app, for you to play in xemu.

**Version 1.0:** [open it in your browser](https://azurik-modding-hub.github.io/AzurKit/) or
[download the app](https://github.com/Azurik-Modding-Hub/AzurKit/releases) for macOS, Windows or Linux.

## What you need

- **Your own copy of the game,** USA or Europe, as an ISO image. AzurKit reads it and builds on your computer, and
  your image never leaves it.
- **A Mac or a PC** (not a phone or a tablet).
- **[xemu](https://xemu.app),** the Xbox emulator, to play what you build.

AzurKit never holds the game's disc image. So that it works before you pick yours, it ships the game's original
config.xbr (the Data tab's numbers) and pictures drawn from the game's files (the characters' front and back views,
the tracker's maps and icons).

## Use it

- **In your browser:** [azurik-modding-hub.github.io/AzurKit](https://azurik-modding-hub.github.io/AzurKit/).
  Nothing to install, nothing uploaded, no tracking, and it works offline once loaded.
- **The app:** the same page in its own window, for macOS (Apple Silicon or Intel), Windows and Linux (below).
- **The command line:** `uv tool install azurkit` or `pipx install azurkit` (Python 3.14), then `azurkit --help`.
- **Play:** open the image you built in xemu. With xemu's memory at 128 MiB, levels get room past 64 MiB. Real
  Xbox hardware isn't tested.

### Download and check it

- **Download only from [Releases](https://github.com/Azurik-Modding-Hub/AzurKit/releases):** a copy posted anywhere
  else may not be ours.
- **Opening it the first time:** the apps are unsigned. On a Mac, open it, then choose Open Anyway in System
  Settings › Privacy & Security (never turn Gatekeeper off). On Windows, choose More info › Run anyway.
- **Checking it:** every file has a checksum in `SHA256SUMS` and a GitHub build attestation;
  [the guide shows how to check them](https://github.com/Azurik-Modding-Hub/AzurKit/blob/main/docs/GUIDE.md#download-and-check-it).

## Features

- **Patches and sliders:** 17 packs and 47 settings, all on USA and Europe: 60 FPS (or up to 1,905), gravity,
  movement, health, enemy scaling, a save-point warp, photo mode, fewer popups, and fixes for a crash and a
  "Loading..." hang. No setting is ever clamped.
- **Randomizer:** shuffle disc fragments, powers, upgrades, gems, obsidians and fuel across all 22 levels, with
  logic at the movement difficulty you pick, 36 rated skips and a spoiler log.
- **Item tracker and maps:** what you've collected and can reach now, on every level's map and the world map,
  spoiler-free; in the app, Live marks your pickups in a running xemu.
- **Characters:** play as 178 of the game's 184 creatures, with moves and speed fitted to each body, any weapon and
  any size, seen front and back before you build.
- **Community content:** character variants, and packs as they're published, from Azurik-Custom-Content or any https
  content repository, each file checked before it's kept.
- **Data:** edit every critter's, item's, armor's and spell's numbers.
- **Tools:** check your image file by file, extract or replace a file, or edit and re-sign a save.
- **Sharing:** Copy link shares your packs, settings, seed and character, never your image; every build carries its
  recipe, so opening it gives your setup back.

Every feature in detail: [the guide](https://github.com/Azurik-Modding-Hub/AzurKit/blob/main/docs/GUIDE.md).

## Help and bug reports

Ask a question or report a bug in [Issues](https://github.com/Azurik-Modding-Hub/AzurKit/issues). Say what you did
and what you saw, AzurKit's version (the About tab shows it), your computer and browser, and a share link if a build
is involved; never attach your game image.

Contributing: [docs/DEVELOPMENT.md](https://github.com/Azurik-Modding-Hub/AzurKit/blob/main/docs/DEVELOPMENT.md)
(building and testing) and [AGENTS.md](https://github.com/Azurik-Modding-Hub/AzurKit/blob/main/AGENTS.md) (the
rules).

## Licence and credits

MIT ([`LICENSE`](https://github.com/Azurik-Modding-Hub/AzurKit/blob/main/LICENSE)), for our own work: the game's
files and bytes in this repository belong to its rights holders and are not under it.
[`NOTICE.md`](https://github.com/Azurik-Modding-Hub/AzurKit/blob/main/NOTICE.md) holds every third-party licence,
thanks Jett Tripp (JTCPP), a fellow developer in the Azurik modding effort, whose Elemental_Games_Modding
randomizer is where Azurik_Modkit, AzurKit's forerunner, began, and credits Azurik Perathia's Azurik Debug Menu,
the photo mode's design.

*Unofficial fan tool. Not affiliated with or endorsed by the rights holders of Azurik: Rise of Perathia or Xbox.*
