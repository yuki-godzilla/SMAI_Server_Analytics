"""Compatibility entry point for the browser-based SMAI Analytics console."""

import sys

from smai_analytics.ui import web_dashboard as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
