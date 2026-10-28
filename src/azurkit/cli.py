"""The ``azurkit`` command."""

from __future__ import annotations

import argparse

from azurkit import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="azurkit", description="Mods for Azurik: Rise of Perathia.")
    parser.add_argument("--version", action="version", version=f"azurkit {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
