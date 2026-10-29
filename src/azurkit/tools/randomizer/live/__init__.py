"""Live (Step 4.2c2): the tracker's link to a running xemu, which marks the
spots the game shows taken and follows the player. The app's alone (D882: a
browser can't reach a running xemu); the tracker itself (``..tracker``)
runs on both hosts and reads only :mod:`.game`'s events.

``game.py`` (the game's reads through a link and the events they give),
``link.py`` (the link: the xemu fork's shared guest RAM, or QMP),
``pages.py`` (the guest's page tables) and ``recipes.py`` (the game's RAM
layout) are Modkit's, which ``scripts/oracle_sync.py`` installs through its
rewrites: never edit them by hand. ``errors.py`` (the one
:class:`~.errors.LiveError`) and ``regions.py`` (each release's addresses,
from the facts) are AzurKit's. This folder is the contracts' app-only one:
its link opens sockets and shared memory, and its session runs on the app's
thread (``azurkit.app``).
"""
