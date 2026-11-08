"""The azurik MCP server over stdio (``.mcp.json`` launches it: ``uv run
--locked python -m devkit.mcp``): :mod:`devkit.mcp.tools`' 8 tools on mcp 2's
``MCPServer``. ``python -m devkit mcp serve`` runs it too.

The replies keep a copy of fd 1, and fd 1 then points at stderr, so nothing a
tool, the engine or a child process prints reaches the JSON-RPC stream
(Modkit's AZ-154 move: mcp 2's own claim of fd 1 let a tool's print through).
"""

from __future__ import annotations

import os
import sys
from io import TextIOWrapper

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.stdio import stdio_server

from azurkit import __version__
from devkit.mcp import tools

INSTRUCTIONS = """\
Azurik: Rise of Perathia's game data, offline (no Ghidra), on AzurKit's engine.

Tools: entity_list / entity_get (config.xbr by its own names, from a config.xbr
or an image), xbr_edit (a modded .xbr), pack_list (the packs and their
sliders), pack_build_iso (a build with packs and a mods file), rando_build_iso
(a randomized build), iso_extract / iso_repack (an image's files, and a folder
of edits packed into the vanilla image). Everything else is the azurkit command
and devkit's verbs.

Every tool answers {"success": true, "result": ...} or {"success": false,
"error": "..."}. Nothing is clamped: a slider's min and max are hints.
"""

SERVER = MCPServer("azurik", instructions=INSTRUCTIONS, version=__version__)
for tool in tools.TOOLS:
    SERVER.add_tool(tool)


def main(argv: list[str]) -> int:
    """Serve over stdio until the client closes stdin."""
    if argv:
        print("usage: python -m devkit.mcp (the azurik MCP server over stdio; no arguments)", file=sys.stderr)
        return 2
    sys.stdout.flush()
    protocol = TextIOWrapper(os.fdopen(os.dup(1), "wb"), encoding="utf-8")
    os.dup2(2, 1)
    anyio.run(_serve, anyio.wrap_file(protocol))
    return 0


async def _serve(stdout) -> None:
    """``MCPServer.run_stdio_async``, its replies written to ``stdout``."""
    async with stdio_server(stdout=stdout) as (read, write):
        low = SERVER._lowlevel_server
        await low.run(read, write, low.create_initialization_options())
