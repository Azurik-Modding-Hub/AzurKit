"""The Characters tab's pickers (Step 4.3d; Modkit's Player page, its
``gui/pages/patches.py``, and its gallery picker's pictures): what the tab
shows, decided here once for both hosts (D882).

- :func:`match_text`: a G4 button's value as its box shows it.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal


def match_text(value: float) -> str:
    """A G4 match ``value`` as its box takes it: 4 significant figures
    rounded up, never to nearest, so a match never falls short of garret4
    (Modkit's ``match_text``, Step 2.165b's review)."""
    exact = Decimal(value)
    return f"{float(exact.quantize(Decimal(1).scaleb(exact.adjusted() - 3), rounding=ROUND_CEILING)):.4g}"
