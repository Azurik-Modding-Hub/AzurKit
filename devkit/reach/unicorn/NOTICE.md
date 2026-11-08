unicorn_fastl3.patch is a patch to Unicorn 2.1.4's sources (QEMU's TCG and
Unicorn's own files), so it is licensed as those files are: the GNU General
Public License, version 2 (Unicorn: https://github.com/unicorn-engine/unicorn,
its COPYING).

It is AzurKit's developer side only. build_unicorn.py downloads PyPI's
unicorn 2.1.4 source distribution, applies the patch and builds the library
into the user cache; neither the patch nor anything built from it ships in
AzurKit's wheel, its app or its site (devkit/README.md says why none of
devkit ships). The rest of this folder, and fastl3_step.c beside it (which
calls Unicorn only through its public C API), is AzurKit's own, under its
licence.
