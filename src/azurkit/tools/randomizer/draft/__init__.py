"""Randomizer authoring drafts: tools that derive logic data from the game.

Authoring only (REORG_PLAN Phase R1, §12.1's layout): the planner and the
writer never import this package.  :mod:`.envelope` holds the movement
tiers as margins over the physics envelope (``tiers.toml``,
:mod:`azurkit.tools.randomizer.physics`);
:mod:`.reach` is the reach model (:mod:`.geometry`, :mod:`.floors`,
:mod:`.flights`, :mod:`.wiring`, :mod:`.moves`, :mod:`.gates`,
:mod:`.coverage`), which needs numpy (a runtime dependency), and
:mod:`.export` writes its derived data (``azurik-mod rando derive``).
"""
