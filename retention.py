"""Compatibility entry point for SMAI Analytics retention."""

import sys

from smai_analytics.operations import retention as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
