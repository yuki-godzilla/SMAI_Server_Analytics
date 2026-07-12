"""Compatibility entry point for SMAI Analytics backups."""

import sys

from smai_analytics.operations import backup as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
