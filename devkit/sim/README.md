# devkit/sim: the simulator (dev only)

The game's own code under Unicorn, from a build's structure (L0) to its
movement in a running game (L3), with L3's search and trick explorer.
[`docs/SIMULATOR.md`](../../docs/SIMULATOR.md) has the levels, the API, the
xemu validation and the limits. Its modules are Modkit's `azurik_mod/sim`
at its cut (Step 4.13a), their imports pointed at AzurKit's engine through
`ports.py`; `data/` holds the code L2 can't judge (`sim_blind_spots.toml`)
and the kernel's exports L2 and L3 stub (`kernel.toml`).

## `l3-hold`: the snapshots no cleanup deletes

```bash
uv run --locked python -m devkit sim l3-hold [--store DIR] [--checkout DIR ...] [--check PATH ...]
```

A snapshot in the L3 store (`l3-snapshots/` in the user data folder, or
`--store`) is held when it is in a `reach-live` folder (the reach engine's
starts), named by a running process's command line, or the start of a
`proofs.jsonl` record in a checkout (each `--checkout`, by default this
checkout's worktrees). Without `--check` it counts the held snapshots by
why; with it, it names each held snapshot at or under a PATH and exits 1 if
there is one, so a cleanup asks it first. It reads the standard library
only (`$EV/tools/prune` loads the file by its path).
