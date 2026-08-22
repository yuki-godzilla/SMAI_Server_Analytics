"""Compatibility entry point for the SMAI host-maintenance preflight."""

import sys

from smai_analytics.operations import host_maintenance as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
