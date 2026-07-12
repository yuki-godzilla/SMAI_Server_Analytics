"""Compatibility entry point for the local SMAI Analytics console."""

import sys

from smai_analytics.ui import dashboard as _implementation


if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
