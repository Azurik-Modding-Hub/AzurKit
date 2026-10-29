# Notices and credits

## JTCPP (Jett Tripp): Elemental_Games_Modding

AzurKit is the rewrite of Azurik_Modkit, which grew out of a fork of Jett
Tripp's (JTCPP's)
[Elemental_Games_Modding](https://github.com/JTCPP/Elemental_Games_Modding).
Its randomizer tool (`tools/randomizer/`, commits `b487012` "Randomizer Tool
0.1.0" and `696fc70` "v0.2.0 Entity editor improvements", March 2026) is where
Modkit's item solver and logic database, the `config.xbr` table reader and
property schema, the level shufflers, the randomizer commands and the entity
editor started. Thank you, JTCPP.

That repository has no licence file: its README states an MIT intent and links
a `LICENSE` that isn't there. So none of his code is ported here until he
grants it, and nothing in AzurKit is taken from a Modkit file that credits his
lines: Modkit's `NOTICE.md` lists those files, and the ones since removed.
[`tests/test_provenance.py`](tests/test_provenance.py) checks every tracked text
file against line fingerprints of that whole list
([`tests/provenance/jtcpp_lines.txt`](tests/provenance/jtcpp_lines.txt), sha256s,
not the lines; written by
[`scripts/provenance_fingerprints.py`](scripts/provenance_fingerprints.py)).
The parts he started, among them the keyed `config.xbr` cells, are written new
from the format.

## Azurik Perathia: Azurik Debug Menu

The photo mode pack (`src/azurkit/tools/mods/packs/qol_photo_mode.py` and its
shim, `src/azurkit/tools/mods/shims/qol_photo_mode.c`) takes its design from
[Azurik Debug Menu](https://github.com/Azurik-Modding-Hub/Azurik-Debug-Menu)
1.1.0, commit `d807b8d`: a hook round the cheat-owner tick (0x15DA0) that
opens the game's own free camera through the action dispatcher's action 3
(0x16610), the world and player checked before it, and the gesture's presses
taken so they don't fire elsewhere. None of its code was copied: the pack is
Azurik_Modkit's own C shim, reimplemented from that design and ported here.
Ours: the world kept paused (its Freecam runs the world), the L3 + R3 chord and
its guard for the cheat codes, START as an exit, the entry refusals, the held
buttons taken on entry and exit, and the camera speed hook. Its licence, MIT:

```text
MIT License

Copyright (c) 2026 Azurik Perathia

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
