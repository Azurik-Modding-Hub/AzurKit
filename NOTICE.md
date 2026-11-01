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

## Azurik Level Studio contributors: Azurik Level Studio

`src/azurkit/tools/characters/gltf.py` ports two pieces of
[Azurik Level Studio](https://github.com/Azurik-Modding-Hub/Azurik-Level-Editor),
commit `6c23060`: `asset_export.py`'s `write_gltf` buffer and accessor
layout (one 4-byte aligned buffer view per accessor, the bounds on POSITION
and every sampler input, the root's X -90 degree quaternion) and
`validate_asset_export.py`'s `validate_gltf` structural checks (the
export's C8). The skin, animation, texture and engine-model code is ours.
`src/azurkit/tools/characters/textures.py` ports its `asset_editing.py`'s
`_dxt` BC1/BC2 block encoder and its `_rgb565`/`_rgb888` conversions (the
same commit): the endpoint pick along the block's longest colour axis, the
edge replication, the four-colour order and the DXT3 alpha nibbles; the
chain, header, list, recolour and PNG code is ours. Azurik_Modkit ported
both from a shallow clone, running none of its code, and AzurKit carries
Modkit's ports. The mesh readers in `src/azurkit/tools/characters/render.py`
and `src/azurkit/tools/randomizer/art/render.py` use knowledge from its
readers; none of their code was copied. Its licence, MIT:

```text
MIT License

Copyright (c) 2026 Azurik Level Studio contributors

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

## Azurik Modding Hub contributors: Azurik Dialogue Studio

`src/azurkit/tools/characters/xbox_adpcm.py` ports the mono Xbox ADPCM
codec and WAV reader of
[Azurik Dialogue Studio](https://github.com/Azurik-Modding-Hub/Azurik-Dialogue-Studio),
commit `1436af4`, from its `audio_formats.py`: the IMA step and index
tables, `_expand`, `_quantize`, `encode_xbox_adpcm` (as `encode`, mono
only), `decode_xbox_adpcm` (as `decode`), `_read_wav` (as `read_wav`) and
`_resampled_frame` (as `_resampled`). The stereo paths are left out; the
downmix, the 22050 Hz rule and the wave entry it writes (`wave_entry`) are
ours, and so is `src/azurkit/tools/characters/synth.py`. Azurik_Modkit
ported it from a shallow clone, running none of its code, and AzurKit
carries Modkit's port. Its licence, MIT:

```text
MIT License

Copyright (c) 2026 Azurik Modding Hub contributors

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

## Sun Microsystems: fdlibm

`src/azurkit/core/fdlibm.py` ports to pure Python the algorithms of
[fdlibm](https://netlib.org/fdlibm/), Sun's freely distributable maths
library, as FreeBSD's msun and [musl](https://musl.libc.org/) carry them
(musl below): musl's `sin`, `cos` and `tan`, their kernels `__sin`, `__cos`
and `__tan`, `__rem_pio2`'s small and medium arguments, `acos`, `atan`,
`atan2` and `cbrt` (`__rem_pio2` and `cbrt` optimized by Bruce D. Evans),
fdlibm 5.3's `exp` and musl 1.1's `log` (FreeBSD's `e_log.c`). The exact
integer reduction past 2**20 pi/2, `pow`, `sq` and `cube` are ours. Each
source carries one of Sun's notices, which is its licence, and the module
keeps the first. `__rem_pio2`, `__sin`, `__cos`, `acos`, `atan2` and `log`
(`e_rem_pio2.c`, `k_sin.c`, `k_cos.c`, `e_acos.c`, `e_atan2.c`, `e_log.c`):

```text
Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.

Developed at SunSoft, a Sun Microsystems, Inc. business.
Permission to use, copy, modify, and distribute this
software is freely granted, provided that this notice
is preserved.
```

`sin`, `cos`, `tan`, `atan` and `cbrt` (`s_sin.c`, `s_cos.c`, `s_tan.c`,
`s_atan.c`, `s_cbrt.c`):

```text
Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.

Developed at SunPro, a Sun Microsystems, Inc. business.
Permission to use, copy, modify, and distribute this
software is freely granted, provided that this notice
is preserved.
```

`__tan` (`k_tan.c`):

```text
Copyright 2004 Sun Microsystems, Inc.  All Rights Reserved.

Permission to use, copy, modify, and distribute this
software is freely granted, provided that this notice
is preserved.
```

`exp` (fdlibm 5.3's `e_exp.c`):

```text
Copyright (C) 2004 by Sun Microsystems, Inc. All rights reserved.

Permission to use, copy, modify, and distribute this
software is freely granted, provided that this notice
is preserved.
```

## Rich Felker, et al.: musl

`src/azurkit/core/fdlibm.py` follows [musl](https://musl.libc.org/)'s code
for the functions above (its results are musl's bit for bit where musl's
code is fdlibm's). musl's licence, from its `COPYRIGHT` (release 1.2.5):

```text
musl as a whole is licensed under the following standard MIT license:

----------------------------------------------------------------------
Copyright © 2005-2020 Rich Felker, et al.

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
----------------------------------------------------------------------
```

Of its maths library the same file says:

```text
Much of the math library code (src/math/* and src/complex/*) is
Copyright © 1993,2004 Sun Microsystems or
Copyright © 2003-2011 David Schultz or
Copyright © 2003-2009 Steven G. Kargl or
Copyright © 2003-2009 Bruce D. Evans or
Copyright © 2008 Stephen L. Moshier or
Copyright © 2017-2018 Arm Limited
and labelled as such in comments in the individual source files. All
have been licensed under extremely permissive terms.
```

## Zig contributors: compiler_rt

The compiled kernels' libraries in `src/azurkit/core/_native/` (built by
`nativekit` with zig 0.16.0, the `ziglang` package) each carry zig's
`compiler_rt`, the runtime routines zig links into every library it builds.
Zig's licence, from its `LICENSE`:

```text
The MIT License (Expat)

Copyright (c) Zig contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## The mingw-w64 project: mingw-w64 runtime

The Windows library, `src/azurkit/core/_native/windows-x86_64.dll`, holds
the mingw-w64 runtime's DLL startup code, which zig's `x86_64-windows-gnu`
target links from the mingw-w64 sources zig ships. Those files are in the
public domain or under the Zope Public License 2.1; its `COPYING`:

```text
With exception of certain parts that are prominently marked as being
in the Public Domain, BSD, or LGPL this Software is provided under the
Zope Public License (ZPL) Version 2.1.

Copyright (c) 2009 - 2013 by the mingw-w64 project

See the AUTHORS file for the list of contributors to the mingw-w64 project.

This license has been certified as open source. It has also been designated
as GPL compatible by the Free Software Foundation (FSF).

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

   1. Redistributions in source code must retain the accompanying copyright
      notice, this list of conditions, and the following disclaimer.
   2. Redistributions in binary form must reproduce the accompanying
      copyright notice, this list of conditions, and the following disclaimer
      in the documentation and/or other materials provided with the
      distribution.
   3. Names of the copyright holders must not be used to endorse or promote
      products derived from this software without prior written permission
      from the copyright holders.
   4. The right to distribute this software or to use it for any purpose does
      not give you the right to use Servicemarks (sm) or Trademarks (tm) of
      the copyright holders.  Use of them is covered by separate agreement
      with the copyright holders.
   5. If any files are modified, you must cause the modified files to carry
      prominent notices stating that you changed the files and the date of
      any change.

Disclaimer

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ``AS IS'' AND ANY EXPRESSED
OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
EVENT SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
