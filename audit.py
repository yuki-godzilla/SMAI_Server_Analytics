"""Compatibility import for SMAI Analytics audit events."""

import sys

from smai_analytics.operations import audit as _implementation


sys.modules[__name__] = _implementation
