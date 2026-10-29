"""Live's one error: what the link (``link.py``) and the game's reads
(``game.py``) raise when Live can't read xemu."""

from __future__ import annotations


class LiveError(Exception):
    """Live can't read xemu; ``str()`` is the tracker's text, naming one fix."""
