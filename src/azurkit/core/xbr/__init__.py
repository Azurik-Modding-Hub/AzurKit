"""The game's data archives (``.xbr``): :mod:`.document` (the header, the
table of contents and the trailer, parsed and written back), :mod:`.keyed`
(config.xbr's keyed tables) and :mod:`.edits` (a cell's writes, planned
against the table as parsed)."""

from azurkit.core.xbr.document import Document

__all__ = ["Document"]
