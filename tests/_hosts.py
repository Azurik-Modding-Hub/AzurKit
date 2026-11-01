"""Which host's float maths the goldens hold (D1016): they were recorded on macOS on Apple Silicon, numpy on Accelerate.
There a test compares byte for byte; another host's matrix products and libm round otherwise (Linux and Windows on
OpenBLAS, x86's SIMD), so there it compares close enough, and says how far apart what it found is."""

from __future__ import annotations

import platform
import sys

import numpy as np


def recording() -> bool:
    """Whether this host does the float maths the goldens were recorded with."""
    return (sys.platform == "darwin" and platform.machine() == "arm64"
            and np.show_config(mode="dicts")["Build Dependencies"]["blas"]["name"] == "accelerate")
