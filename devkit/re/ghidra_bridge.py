# /// script
# requires-python = ">=3.14"
# dependencies = ["mcp==1.30.0", "requests==2.34.2"]
# ///
"""The ``ghidra`` MCP server: the stock GhydraMCP bridge
(``.tools/ghydra-bridge/bridge_mcp_hydra.py``, which ``bootstrap.py --with
re`` installs) run in this script's own environment, which
``ghidra_bridge.py.lock`` pins whole (Step 4.11d2):

    uv run --locked --script devkit/re/ghidra_bridge.py .tools/ghydra-bridge/bridge_mcp_hydra.py

Not the bridge's own header: it pins mcp 1.6.0 and nothing under it, and
the pydantic it then gets has dropped what that mcp imports. Nor AzurKit's
environment: devkit's mcp 2 has no ``mcp.server.fastmcp``, which the bridge
imports. The pins are those Modkit ran the bridge on (mcp 1.30.0, requests
2.34.2). Stdlib only itself; it never runs inside AzurKit's environment."""

import runpy
import sys

if __name__ == "__main__":
    sys.argv = sys.argv[1:]   # the bridge sees its own path as argv[0]
    runpy.run_path(sys.argv[0], run_name="__main__")
