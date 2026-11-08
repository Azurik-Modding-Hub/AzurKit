"""Which of a level's platform solids the game's collision world holds at a snapshot (Step R2.17's census, the kernel
route's since Step R2.19d: ``devkit.reach.native.backend.census_of``, L3's own collision_sweep 0x60870 on the
player's world, the body swept into each platform's largest faces), so the kernel's world (``reach_native.solid``)
leaves out the ones the game doesn't collide with there.  ``devkit/reach/reach_engine.py --backend kernel`` makes and
caches it per snapshot itself; this prints its counts and writes the absent owners' indices (ids) as JSON to OUT.
    nice -n 10 uv run --locked python -B -m devkit reach native-census LEVEL SNAPSHOT OUT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from devkit.reach import reach_engine as RE  # noqa: E402

from devkit.sim.ports import vanilla_iso  # noqa: E402
from devkit.sim.ports import read_file  # noqa: E402
from azurkit.tools.randomizer.draft.geometry import Level  # noqa: E402
from devkit.reach.native.backend import census_of  # noqa: E402
from devkit.reach.l3_pool import Worker  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m devkit reach native-census", description=__doc__.split("\n\n")[0])
    ap.add_argument("level")
    ap.add_argument("snapshot")
    ap.add_argument("out", help="the absent owners' indices, as JSON")
    a = ap.parse_args(argv)
    level, label, out = a.level, a.snapshot, a.out
    W = Worker(label, RE._store(None), read_file(str(vanilla_iso()), "default.xbe"), None)
    got = census_of(W.sim(False, deep=False), Level.read(vanilla_iso(), level))
    Path(out).write_text(json.dumps({"level": level, "absent": got["absent"]}), encoding="utf-8")
    print(json.dumps({"level": level, "platform_owners": got["platforms"], "present_in_l3": got["present"],
                      "absent": len(got["absent"]), "unclear_kept": got["unclear"]}))


if __name__ == "__main__":
    main()
