# devkit/mcp: the azurik MCP server (dev only)

```bash
uv run --locked python -m devkit.mcp        # what .mcp.json launches
uv run --locked python -m devkit mcp serve  # the same, through devkit's dispatcher
```

`serve` serves the 8 tools of `tools.py` (Modkit's names, D64) over stdio on
mcp 2's `MCPServer`. [`docs/MCP.md`](../../docs/MCP.md) is the reference:
setup, the envelope, each tool's parameters and reply, and how they differ
from Modkit's.
