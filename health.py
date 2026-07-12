"""Compatibility entry point for the SMAI Analytics health probe."""

import sys

from smai_analytics.monitoring import health as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
