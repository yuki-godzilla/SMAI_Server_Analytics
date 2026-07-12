"""Compatibility import for SMAI Analytics task monitoring."""

import sys

from smai_analytics.monitoring import task_monitor as _implementation


sys.modules[__name__] = _implementation
