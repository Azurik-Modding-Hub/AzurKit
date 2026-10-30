# Notices and credits

## JTCPP (Jett Tripp): Elemental_Games_Modding

Jett Tripp (JTCPP) is a fellow developer in the Azurik modding effort. His
[Elemental_Games_Modding](https://github.com/JTCPP/Elemental_Games_Modding)
randomizer is where Azurik_Modkit began. Thank you, JTCPP.

## Azurik: Rise of Perathia

Azurik: Rise of Perathia's files and bytes in this repository (a game file, a
snippet, a byte literal) belong to their rights holders and are not under the
MIT licence, which covers our own work. The game's image is never here: you
bring your own copy.

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
