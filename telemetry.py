"""Compatibility import for durable SMAI Analytics telemetry."""

import sys

from smai_analytics.monitoring import telemetry as _implementation


sys.modules[__name__] = _implementation
