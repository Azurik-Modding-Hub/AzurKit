"""``python -m devkit.mcp``: the azurik MCP server over stdio (``.mcp.json``)."""

import sys

from devkit.mcp.serve import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
