"""Compatibility import for SMAI Analytics connection observations."""

import sys

from smai_analytics.monitoring import connection_watch as _implementation


sys.modules[__name__] = _implementation
