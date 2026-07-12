"""Compatibility entry point for SMAI incident automation."""

import sys

from smai_analytics.operations import incident_automation as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
