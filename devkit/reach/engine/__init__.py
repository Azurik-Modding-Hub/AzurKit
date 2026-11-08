"""The exhaustive reach engine (Step R2.16a; the R2.16 design): which floors the player reaches from which, by running
the game's own player tick (simulator Level 3, :mod:`devkit.sim.l3`) from every floor's boundary.

On the ground the player's state is the floor region he stands on, so reach is single launches from each region's
boundary, closed per kit.  The pieces, in the order a run uses them:

- :mod:`.nodes`: the nodes (the game's walkable regions, ``floors.walk_game``: nz > 0.7071; slides and other
  landable floors; the water; trigger, push, damage and pickup volumes), each keyed by its cells, and the takeoffs:
  a boundary sample every 2 m of each region with its outward normal;
- :mod:`.macros`: the launch set R0 (run walk-off, run jump and stand jump, with 0, 1, 2 or 5 flaps chained from
  each fall's start in the air shield's kit branch, none in rank 0's; the stick held toward the heading), each a
  closed-loop controller whose pads are the witness string;
- :mod:`.aim`: the targeted aims at each derived flight's landing and the refinement on what a run left, steered by
  the predictive landing control (keyed apart from R0's fan: an aim-only change re-runs only the aims);
- :mod:`.runner`: one job (a takeoff and a heading) on L3: a teleport a run-up (1 m) or a stand (0.3 m) back along
  the heading, a settle that must stand where it was put (else the level's next cell, AZ-488; else the start is
  dropped and counted), the kit, then each macro from that saved start to settled ground, a death or the fall cap;
  its outcome (where it settled and first touched down, privately; the volumes the body centre passed; HP, flaps,
  :mod:`devkit.sim.tricks_detect`'s labels, the taint);
- :mod:`.cache`: the outcomes in the AzurKit user cache, mode 700, one file per job written atomically, keyed by
  the L3 core (not L3's ``engine_sha12``, which hashes the randomizer's data), the snapshot and the start, so a
  derive change re-maps outcomes to nodes and zones without running them again;
- :mod:`.graph`: outcomes into edges (from node, to node, the least air rank its witness needs) and the closure per
  kit;
- :mod:`.verdict`: FOUND, DATA, MAY, NO or N/A per derived zone edge, hand edge and level row (a found witness is
  the evidence: no jitter replays, D661), the witness as a ``proofs.jsonl`` ``azurik-l3-proof/1`` edge record (no
  coordinate), and the recall report.

``devkit/reach/reach_engine.py`` runs it (docs/REACH.md).  Shadow only until R1.17 (the plan freeze): nothing here
writes ``src/azurkit/tools/randomizer/data``.  Dev tooling (Unicorn, numpy); positions stay in memory or in the private
cache, never printed.  It lives outside ``devkit/sim/`` and ``devkit/rando/draft/`` so that its edits don't move L3's
``engine_sha12`` (``l3.ENGINE_FILES``).
"""

R0 = "r0/1"   # the launch set's version: part of every job's key (a change here re-runs the jobs)
