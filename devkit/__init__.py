"""devkit (dev only, D950, D990): AzurKit's developer side, ported from
Modkit: the xemu oracle, the simulator, the RE and Ghidra tools, the azurik
MCP server, the randomizer's database tools, the reach engine and the model
verbs, each an area (a subpackage, ``devkit/<area>/``).

None of it ships: the wheel packs only ``src/azurkit``, the site runs that
wheel, the app freezes only what ``azurkit`` imports, and nothing under
``src/azurkit`` imports ``devkit`` (``tests/test_contracts.py``).
``devkit/README.md`` says what stays out of the repository and where it
lives.

An area's ``__init__`` imports only the standard library and names its
verbs in ``VERBS``, ``{verb: its line}``. The verb ``v`` is the module
``devkit.<area>.v`` (a hyphen in ``v`` is an underscore there), whose
``main(argv: list[str]) -> int`` runs it. Its dependencies are the
``devkit`` group's (``pyproject.toml``, installed by default).

    uv run --locked python -m devkit                        # the areas
    uv run --locked python -m devkit AREA                   # an area's verbs
    uv run --locked python -m devkit AREA VERB [ARGS ...]   # run one
"""
